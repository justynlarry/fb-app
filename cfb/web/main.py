"""Web UI. Pages only read from Postgres; the worker does all the fetching."""
import hmac
import ipaddress
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from cfb import coordinators, paper, schedule
from cfb import settings as app_settings
from cfb.auth import (
    SESSION_DAYS,
    authenticate,
    change_password,
    create_session,
    end_session,
    session_user,
)
from cfb.db import connect
from cfb.model import MODEL_VERSION
from cfb.nfl_model import MODEL_VERSION as NFL_MODEL_VERSION
from cfb.picks import make_pick, recorded_pick
from cfb.qbs import qb_out_suggestion
from cfb.users import UserError, add_user, all_users, reset_password, set_active, set_admin

WEB_DIR = Path(__file__).parent
LOCAL_TZ = ZoneInfo(os.environ.get("TZ", "America/Denver"))

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

SESSION_COOKIE = "session"
DOCKER_NETWORK = ipaddress.ip_network("172.16.0.0/12")   # the cloudflared container lives here


def client_ip(request):
    """The visitor's real IP. Through the tunnel, Cloudflare puts it in a header."""
    direct = request.client.host if request.client else None
    if direct and ipaddress.ip_address(direct) in DOCKER_NETWORK:
        return request.headers.get("cf-connecting-ip") or direct
    return direct


def same_origin(request):
    """True if a POST came from one of our own pages (blocks cross-site form posts)."""
    origin = request.headers.get("origin")
    if origin is None:
        return False
    return urlsplit(origin).netloc == request.headers.get("host")


def safe_next(url):
    """Only redirect to our own pages (blocks /login?next_url=https://evil.example)."""
    if url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return "/"


def set_session_cookie(request, response, token):
    """Store the session token in an HttpOnly cookie."""
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=request.headers.get("x-forwarded-proto") == "https",
    )


def require_admin(request):
    """Stop non-admins from changing data."""
    if not request.state.user["is_admin"]:
        raise HTTPException(status_code=403, detail="Only admins can do that.")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Every page needs a logged-in user, except the login page and static files."""
    path = request.url.path
    # Plain http:// through Cloudflare: send the browser to https:// before anything else
    if request.headers.get("x-forwarded-proto") == "http" and request.headers.get("cf-connecting-ip"):
        return RedirectResponse(str(request.url.replace(scheme="https")), status_code=301)
    if request.method == "POST" and not same_origin(request):
        return PlainTextResponse("Forbidden", status_code=403)
    if path == "/login" or path.startswith("/static/"):
        return await call_next(request)
    if path == "/metrics":
        return metrics(request)     # its own check: a bearer token, LAN only (no login session)

    with connect() as conn:
        user = session_user(conn, request.cookies.get(SESSION_COOKIE))

    if user is None:
        if request.headers.get("hx-request"):
            # HTMX refresh (scores page): tell the browser to go to the login page
            return Response(status_code=401, headers={"HX-Redirect": "/login"})
        if request.method != "GET":
            return PlainTextResponse("Please log in.", status_code=401)
        return RedirectResponse("/login?next_url=" + quote(path), status_code=303)

    if user["must_change_password"] and path not in ("/account/password", "/logout"):
        return RedirectResponse("/account/password", status_code=303)

    request.state.user = user
    return await call_next(request)


def metrics(request: Request):
    """Prometheus scrape: paper-model rows and the worker jobs' last runs (cfb/paper.py metrics_text).
    Off (404) unless METRICS_TOKEN is set in .env; needs "Authorization: Bearer <METRICS_TOKEN>"; refused through
    Cloudflare (a CF-Connecting-IP header), so it's reachable only on the LAN address."""
    token = os.environ.get("METRICS_TOKEN", "")
    if not token or request.method != "GET":
        return PlainTextResponse("Not Found", status_code=404)
    if request.headers.get("cf-connecting-ip"):
        return PlainTextResponse("Forbidden", status_code=403)
    given = request.headers.get("authorization", "")
    if not hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
        return PlainTextResponse("Unauthorized", status_code=401)
    today = datetime.now()
    season = today.year if today.month >= 8 else today.year - 1     # January bowls belong to last fall's season
    with connect() as conn:
        in_season = {
            league: conn.execute(
                """SELECT EXISTS (SELECT 1 FROM games WHERE league = %s AND season = %s
                                  AND start_time BETWEEN now() - interval '3 days' AND now() + interval '10 days')""",
                (league, season),
            ).fetchone()[0]
            for league in ("cfb", "nfl")
        }
    return PlainTextResponse(paper.metrics_text(season, in_season), media_type="text/plain; version=0.0.4")


# One week's games for one league (FBS only for college) with their latest live snapshot (if any).
# Which week: the one asked for (season, week, season_type), or when week is NULL, "this week" =
# the week of the next game that hasn't been over for 24+ hours (12+ for the NFL: Monday night rolls over Tuesday morning).
# Live snapshots exist only since Nov 15, 2026; older games fall back to the final score in games.
SCORES_SQL = """
WITH current_week AS (
    SELECT season, week, season_type
    FROM games
    WHERE league = %(league)s
      AND (league <> 'cfb' OR 'fbs' IN (home_classification, away_classification))
      AND (
            (%(week)s::int IS NULL AND start_time > now() - (CASE WHEN league = 'nfl' THEN interval '12 hours' ELSE interval '24 hours' END))
         OR (season = %(season)s::int AND week = %(week)s::int AND season_type = %(season_type)s::text)
      )
    ORDER BY start_time
    LIMIT 1
)
SELECT a.school AS away,
    h.school AS home,
    g.start_time,
    g.start_time_tbd,
    w.season AS view_season, w.week AS view_week, w.season_type AS view_season_type,
    COALESCE(l.state, CASE WHEN g.completed THEN 'post' END) AS state,
    l.status_detail,
    COALESCE(l.away_score, g.away_points) AS away_score,
    COALESCE(l.home_score, g.home_points) AS home_score,
    l.possession_team_id = g.away_id AS away_has_ball,
    l.possession_team_id = g.home_id AS home_has_ball,
    l.away_timeouts,
    l.home_timeouts,
    l.down_distance,
    a.espn_id AS away_espn_id,
    h.espn_id AS home_espn_id,
    l.odds_details,
    l.over_under,
    l.away_rank, l.home_rank,
    l.away_record, l.home_record,
    l.away_conf_record, l.home_conf_record
FROM games g
JOIN current_week w ON w.season = g.season
                    AND w.week = g.week
                    AND w.season_type = g.season_type
JOIN teams h ON h.id = g.home_id
JOIN teams a ON a.id = g.away_id
LEFT JOIN live_scores l ON l.game_id = g.id
WHERE g.league = %(league)s
  AND (g.league <> 'cfb' OR 'fbs' IN (g.home_classification, g.away_classification))
ORDER BY g.start_time, a.school
"""

# Weeks the scores page can show: every week with at least one game (FBS only for college).
SCORE_WEEKS_SQL = """
SELECT season, week, season_type, min(start_time) AS first_kickoff
FROM games
WHERE league = %(league)s
  AND (league <> 'cfb' OR 'fbs' IN (home_classification, away_classification))
GROUP BY season, week, season_type
ORDER BY first_kickoff
"""

# "This week" on the scores page (same 24-hour / NFL 12-hour rule as SCORES_SQL), so the picker knows which week is current.
SCORES_CURRENT_WEEK_SQL = """
SELECT season, week, season_type
FROM games
WHERE league = %(league)s
  AND (league <> 'cfb' OR 'fbs' IN (home_classification, away_classification))
  AND start_time > now() - CASE WHEN league = 'nfl' THEN interval '12 hours' ELSE interval '24 hours' END
ORDER BY start_time
LIMIT 1
"""

# Our predictions for one week's games, with the typical miss for that point in
# the season (from the backtest), any manual overrides, and the market line for comparison.
# Which week: the one asked for (season, week, season_type), or when week is NULL, "this week" =
# the week of the next game that hasn't been over for 12+ hours. 12, not 24 like the scores page,
# so a normal Saturday rolls over Sunday morning, before the Sunday 4 PM openers.
PREDICTIONS_SQL = """
WITH current_week AS (
    SELECT season, week, season_type
    FROM games
    WHERE league = 'cfb'
      AND 'fbs' IN (home_classification, away_classification)
      AND (
            (%(week)s::int IS NULL AND start_time > now() - interval '12 hours')
         OR (season = %(season)s::int AND week = %(week)s::int AND season_type = %(season_type)s::text)
      )
    ORDER BY start_time
    LIMIT 1
),
model_miss AS (
    SELECT LEAST(p.weeks_played, 6) AS bucket,
           avg(abs((g.away_points - g.home_points) - p.spread)) AS spread_miss,
           avg(abs((g.home_points + g.away_points) - p.total)) AS total_miss
    FROM predictions p
    JOIN games g ON g.id = p.game_id
    WHERE p.is_backtest AND p.model_version = %(version)s AND g.completed
    GROUP BY 1
),
market AS (
    SELECT game_id,
           avg(spread) AS spread,
           avg(over_under) AS total,
           -- The open is Bovada's only: other books' "open" can be a days-old lookahead line
           avg(spread_open) FILTER (WHERE provider = 'Bovada') AS open_spread,
           max(spread_open) FILTER (WHERE provider = 'Bovada') AS open_hi,
           min(spread_open) FILTER (WHERE provider = 'Bovada') AS open_lo,
           avg(over_under_open) FILTER (WHERE provider = 'Bovada') AS open_total
    FROM lines
    GROUP BY game_id
),
adjustments AS (
    SELECT o.game_id,
           sum(o.points) FILTER (WHERE o.team_id = g.home_id) AS home_adj,
           sum(o.points) FILTER (WHERE o.team_id = g.away_id) AS away_adj,
           string_agg(t.school || ' ' || o.points || ': ' || o.reason, '; ') AS notes
    FROM overrides o
    JOIN games g ON g.id = o.game_id
    JOIN teams t ON t.id = o.team_id
    WHERE o.active
    GROUP BY o.game_id
)
SELECT g.id AS game_id,
       a.school AS away,
       h.school AS home,
       a.espn_id AS away_espn_id,
       h.espn_id AS home_espn_id,
       g.start_time,
       g.start_time_tbd,
       p.spread AS model_spread,
       p.total AS model_total,
       (p.away_points + COALESCE(adj.away_adj, 0))
         - (p.home_points + COALESCE(adj.home_adj, 0)) AS spread,
       p.total + COALESCE(adj.home_adj, 0) + COALESCE(adj.away_adj, 0) AS total,
       adj.notes AS adjustment_notes,
       p.weeks_played,
       p.model_version,
       g.start_time <= now() AS started,
       r.tier AS rec_tier, r.side AS rec_side,
       r.our_spread AS rec_our_spread, r.market_spread AS rec_market_spread,
       r.bet_spread AS rec_bet_spread, r.bet_price AS rec_bet_price, r.bet_book AS rec_bet_book,
       r.spread_outcome, r.spread_units,
       r.our_total AS rec_our_total, r.market_total AS rec_market_total,
       r.total_side AS rec_total_side, r.bet_total AS rec_bet_total,
       r.total_price AS rec_total_price, r.total_book AS rec_total_book,
       r.total_outcome, r.total_units,
       mm.spread_miss,
       mm.total_miss,
       COALESCE(mn.spread, l.spread, m.spread) AS market_spread,
       COALESCE(mn.total, l.over_under, m.total) AS market_total,
       m.open_spread,
       m.open_hi,
       m.open_lo,
       m.open_total,
       mn.books AS books_count,
       mn.best_home_book, mn.best_home_spread, mn.best_home_price,
       mn.best_away_book, mn.best_away_spread, mn.best_away_price,
       mn.best_over_book, mn.best_over_total, mn.best_over_price,
       mn.best_under_book, mn.best_under_total, mn.best_under_price,
       w.season AS view_season, w.week AS view_week, w.season_type AS view_season_type,
       -- live_scores only holds recent games; older finals come from the games table
       COALESCE(l.state, CASE WHEN g.completed THEN 'post' END) AS state,
       COALESCE(l.away_score, g.away_points) AS away_score,
       COALESCE(l.home_score, g.home_points) AS home_score,
       l.away_rank, l.home_rank,
       l.away_record, l.home_record,
       l.away_conf_record, l.home_conf_record,
       ven.dome,
       wf.temperature_f, wf.wind_mph, wf.gust_mph, wf.precip_in
FROM games g
JOIN current_week w ON w.season = g.season
                   AND w.week = g.week
                   AND w.season_type = g.season_type
JOIN LATERAL (          -- this version's prediction, or else the latest pre-game one from an older version
    SELECT *
    FROM predictions pr
    WHERE pr.game_id = g.id
      AND NOT pr.is_backtest
    ORDER BY pr.model_version = %(version)s DESC, pr.created_at DESC
    LIMIT 1
) p ON true
JOIN teams h ON h.id = g.home_id
JOIN teams a ON a.id = g.away_id
LEFT JOIN model_miss mm ON mm.bucket = LEAST(p.weeks_played, 6)
LEFT JOIN market m ON m.game_id = g.id
LEFT JOIN adjustments adj ON adj.game_id = g.id
LEFT JOIN live_scores l ON l.game_id = g.id
LEFT JOIN venues ven ON ven.id = g.venue_id
LEFT JOIN market_now mn ON mn.game_id = g.id
LEFT JOIN pick_results r ON r.game_id = g.id
                        AND r.model_version = p.model_version
                        AND r.taken = 'last'
LEFT JOIN LATERAL (
    SELECT temperature_f, wind_mph, gust_mph, precip_in
    FROM weather_forecasts f
    WHERE f.game_id = g.id
    ORDER BY f.forecast_date DESC
    LIMIT 1
) wf ON true
WHERE g.league = 'cfb'
  AND 'fbs' IN (g.home_classification, g.away_classification)
ORDER BY g.start_time, a.school
"""


# How each kind of pick did in the backtest (2021+, the seasons with a Bovada opening line), using the
# CURRENT pick-rule settings (play_gap, move_min, total_gap; admin page), so the rates describe the rule in force.
# Play and Pass are graded at the Bovada OPEN, because that's when we bet: play_gap+ apart = play, else pass.
# Caution needs a line that has already moved, so it can only be graded later: play_gap+ apart at the CLOSE
# after Bovada's line moved move_min+ away from us (the same test as cfb/picks.py make_pick()).
# Totals are graded at the close. graded_at tells the page which line each rate used.
PICK_RATES_SQL = """
SELECT CASE WHEN abs(open_diff) >= %(play_gap)s THEN 'play' ELSE 'pass' END AS tier,
       'open' AS graded_at,
       count(open_win) AS games,
       avg(open_win::int) AS win_rate
FROM backtest_games
WHERE model_version = %(version)s
  AND is_backtest
  AND season >= 2021
  AND open_spread IS NOT NULL
GROUP BY 1

UNION ALL

SELECT 'caution',
       'close',
       count(spread_win),
       avg(spread_win::int)
FROM backtest_games
WHERE model_version = %(version)s
  AND is_backtest
  AND season >= 2021
  AND open_spread IS NOT NULL
  AND abs(spread_diff) >= %(play_gap)s
  AND abs(open_book_close - open_spread) >= %(move_min)s
  AND sign(open_book_close - open_spread) <> sign(model_spread - open_spread)

UNION ALL

SELECT CASE WHEN total_diff > 0 THEN 'over' ELSE 'under' END,
       'close',
       count(total_win),
       avg(total_win::int)
FROM backtest_games
WHERE model_version = %(version)s
  AND is_backtest
  AND season <> 2020
  AND abs(total_diff) >= %(total_gap)s
GROUP BY 1
"""


# Weeks the predictions page can show: every week with at least one pre-game (live) prediction.
# Backtest predictions aren't included: they're walk-forward replays, not what the page showed at the time.
PREDICTION_WEEKS_SQL = """
SELECT g.season, g.week, g.season_type, min(g.start_time) AS first_kickoff
FROM games g
WHERE g.league = %(league)s
  AND (g.league <> 'cfb' OR 'fbs' IN (g.home_classification, g.away_classification))
  AND EXISTS (SELECT 1 FROM predictions p WHERE p.game_id = g.id AND NOT p.is_backtest)
GROUP BY g.season, g.week, g.season_type
ORDER BY first_kickoff
"""


# NFL predictions for one week: our line and total (nfl model), the projected or actual starting QBs,
# and the nflverse line beside them. Picks are paper only (not bets): our NFL lines trail the close and are too
# flat (model-tests.md section 9). Started games carry the last pick saved before kickoff (pick_results 'last',
# Odds API books) and its official result, like the college page. Same week rule as PREDICTIONS_SQL.
NFL_PREDICTIONS_SQL = """
WITH current_week AS (
    SELECT season, week, season_type
    FROM games
    WHERE league = 'nfl'
      AND (
            (%(week)s::int IS NULL AND start_time > now() - interval '12 hours')
         OR (season = %(season)s::int AND week = %(week)s::int AND season_type = %(season_type)s::text)
      )
    ORDER BY start_time
    LIMIT 1
),
model_miss AS (         -- typical miss in the NFL backtest, by weeks of data (2020 left out)
    SELECT LEAST(p.weeks_played, 6) AS bucket,
           avg(abs((g.away_points - g.home_points) - p.spread)) AS spread_miss,
           avg(abs((g.home_points + g.away_points) - p.total)) AS total_miss
    FROM predictions p
    JOIN games g ON g.id = p.game_id
    WHERE p.is_backtest AND p.model_version = %(version)s AND g.completed AND g.season <> 2020
    GROUP BY 1
),
adjustments AS (        -- active overrides, same as the college page
    SELECT o.game_id,
           sum(o.points) FILTER (WHERE o.team_id = g.home_id) AS home_adj,
           sum(o.points) FILTER (WHERE o.team_id = g.away_id) AS away_adj,
           string_agg(t.school || ' ' || o.points || ': ' || o.reason, '; ') AS notes
    FROM overrides o
    JOIN games g ON g.id = o.game_id
    JOIN teams t ON t.id = o.team_id
    WHERE o.active
    GROUP BY o.game_id
)
SELECT g.id AS game_id,
       a.school AS away, h.school AS home,
       a.espn_id AS away_espn_id, h.espn_id AS home_espn_id,
       g.start_time, g.start_time_tbd,
       g.start_time <= now() AS started,
       w.season AS view_season, w.week AS view_week, w.season_type AS view_season_type,
       p.spread AS model_spread, p.total AS model_total,
       (p.away_points + COALESCE(adj.away_adj, 0))
         - (p.home_points + COALESCE(adj.home_adj, 0)) AS spread,
       p.total + COALESCE(adj.home_adj, 0) + COALESCE(adj.away_adj, 0) AS total,
       adj.notes AS adjustment_notes,
       p.weeks_played, p.model_version,
       mm.spread_miss, mm.total_miss,
       ln.spread AS market_spread, ln.over_under AS market_total,
       sa.qb_name AS away_qb, sh.qb_name AS home_qb,
       COALESCE(l.state, CASE WHEN g.completed THEN 'post' END) AS state,
       COALESCE(l.away_score, g.away_points) AS away_score,
       COALESCE(l.home_score, g.home_points) AS home_score,
       l.away_record, l.home_record,
       r.tier AS rec_tier, r.side AS rec_side,
       r.our_spread AS rec_our_spread, r.market_spread AS rec_market_spread,
       r.bet_spread AS rec_bet_spread, r.bet_price AS rec_bet_price, r.bet_book AS rec_bet_book,
       r.spread_outcome, r.spread_units,
       r.our_total AS rec_our_total, r.market_total AS rec_market_total,
       r.total_side AS rec_total_side, r.bet_total AS rec_bet_total,
       r.total_price AS rec_total_price, r.total_book AS rec_total_book,
       r.total_outcome, r.total_units
FROM games g
JOIN current_week w ON w.season = g.season
                   AND w.week = g.week
                   AND w.season_type = g.season_type
JOIN teams h ON h.id = g.home_id
JOIN teams a ON a.id = g.away_id
LEFT JOIN LATERAL (     -- this version's pre-game prediction, or else the latest from an older version
    SELECT *
    FROM predictions pr
    WHERE pr.game_id = g.id
      AND NOT pr.is_backtest
    ORDER BY pr.model_version = %(version)s DESC, pr.created_at DESC
    LIMIT 1
) p ON true
LEFT JOIN model_miss mm ON mm.bucket = LEAST(p.weeks_played, 6)
LEFT JOIN adjustments adj ON adj.game_id = g.id
LEFT JOIN lines ln ON ln.game_id = g.id AND ln.provider = 'nflverse'
LEFT JOIN nfl_starters sa ON sa.game_id = g.id AND sa.team_id = g.away_id
LEFT JOIN nfl_starters sh ON sh.game_id = g.id AND sh.team_id = g.home_id
LEFT JOIN live_scores l ON l.game_id = g.id
LEFT JOIN pick_results r ON r.game_id = g.id
                        AND r.model_version = p.model_version
                        AND r.taken = 'last'
WHERE g.league = 'nfl'
ORDER BY g.start_time, a.school
"""

# How each NFL tier did in the NFL backtest (2021-25), graded at the CLOSING line: there are no NFL
# opening lines yet, so this is the only grade we have. Same play_gap / total_gap settings as the college page.
NFL_PICK_RATES_SQL = """
SELECT CASE WHEN abs(model_spread - close_spread) >= %(play_gap)s THEN 'play' ELSE 'pass' END AS tier,
       count(spread_win) AS games,
       avg(spread_win::int) AS win_rate
FROM backtest_games
WHERE model_version = %(version)s
  AND is_backtest
  AND season >= 2021
GROUP BY 1

UNION ALL

SELECT CASE WHEN total_diff > 0 THEN 'over' ELSE 'under' END,
       count(total_win),
       avg(total_win::int)
FROM backtest_games
WHERE model_version = %(version)s
  AND is_backtest
  AND season >= 2021
  AND abs(total_diff) >= %(total_gap)s
GROUP BY 1
"""

NFL_CURRENT_WEEK_SQL = """
SELECT season, week, season_type
FROM games
WHERE league = 'nfl' AND start_time > now() - interval '12 hours'
ORDER BY start_time
LIMIT 1
"""


RESULTS_SUMMARY_SQL = """
SELECT taken,
       tier,
       count(*) FILTER (WHERE spread_outcome IS NOT NULL) AS graded,
       count(*) FILTER (WHERE spread_outcome = 'win') AS wins,
       count(*) FILTER (WHERE spread_outcome = 'loss') AS losses,
       count(*) FILTER (WHERE spread_outcome = 'push') AS pushes,
       COALESCE(sum(spread_units), 0) AS units,
       count(*) FILTER (WHERE spread_outcome IS NULL AND side IS NOT NULL AND start_time <= now()) AS awaiting,
       count(*) FILTER (WHERE spread_outcome IS NULL AND side IS NOT NULL AND start_time > now()) AS upcoming
FROM pick_results
WHERE model_version = %(version)s
GROUP BY taken, tier

UNION ALL

SELECT taken,
       'total',
       count(*) FILTER (WHERE total_outcome IS NOT NULL),
       count(*) FILTER (WHERE total_outcome = 'win'),
       count(*) FILTER (WHERE total_outcome = 'loss'),
       count(*) FILTER (WHERE total_outcome = 'push'),
       COALESCE(sum(total_units), 0),
       count(*) FILTER (WHERE total_outcome IS NULL AND start_time <= now()),
       count(*) FILTER (WHERE total_outcome IS NULL AND start_time > now())
FROM pick_results
WHERE model_version = %(version)s
  AND total_side IS NOT NULL
GROUP BY taken
"""


# The same picks graded at the BETTABLE number and price (view 029, the Nov 17 rule that rule 5C and H-TOT use),
# with the best-anywhere units beside them for comparison.  no_line = picks whose snapshot had no bettable book.
BETTABLE_SUMMARY_SQL = """
SELECT taken,
       tier,
       count(*) FILTER (WHERE b_spread_outcome IS NOT NULL) AS graded,
       count(*) FILTER (WHERE b_spread_outcome = 'win') AS wins,
       count(*) FILTER (WHERE b_spread_outcome = 'loss') AS losses,
       count(*) FILTER (WHERE b_spread_outcome = 'push') AS pushes,
       COALESCE(sum(b_spread_units), 0) AS units,
       COALESCE(sum(spread_units) FILTER (WHERE b_spread_outcome IS NOT NULL), 0) AS units_anywhere,
       count(*) FILTER (WHERE side IS NOT NULL AND b_spread IS NULL) AS no_line
FROM pick_results_bettable
WHERE model_version = %(version)s
GROUP BY taken, tier

UNION ALL

SELECT taken,
       'total',
       count(*) FILTER (WHERE b_total_outcome IS NOT NULL),
       count(*) FILTER (WHERE b_total_outcome = 'win'),
       count(*) FILTER (WHERE b_total_outcome = 'loss'),
       count(*) FILTER (WHERE b_total_outcome = 'push'),
       COALESCE(sum(b_total_units), 0),
       COALESCE(sum(total_units) FILTER (WHERE b_total_outcome IS NOT NULL), 0),
       count(*) FILTER (WHERE total_side IS NOT NULL AND b_total IS NULL)
FROM pick_results_bettable
WHERE model_version = %(version)s
  AND total_side IS NOT NULL
GROUP BY taken
"""


# Our first saved line graded against Bovada's opening line (from CFBD) at an assumed -110.
# No line movement exists yet at the open, so 3+ apart = 'play', otherwise 'pass' (no 'caution').
OPEN_RESULTS_SQL = """
WITH opening AS (
    SELECT game_id,
        avg(spread_open) FILTER (WHERE provider = 'Bovada') AS open_spread,
        avg(over_under_open) FILTER (WHERE provider = 'Bovada') AS open_total
    FROM lines
    GROUP BY game_id
),
picks AS (
    SELECT p.start_time, p.our_spread, p.our_total,
        o.open_spread, o.open_total,
        g.completed,
        g.away_points - g.home_points AS result,
        g.away_points + g.home_points AS actual_total
    FROM pick_results p
    JOIN opening o ON o.game_id = p.game_id
    JOIN games g ON g.id = p.game_id
    WHERE p.model_version = %(version)s
      AND p.taken = 'first'
      AND o.open_spread IS NOT NULL
),
graded AS (
    SELECT start_time,
        CASE WHEN abs(our_spread - open_spread) >= 3 THEN 'play' ELSE 'pass' END AS tier,
        CASE
            WHEN NOT completed OR our_spread = open_spread THEN NULL
            WHEN result = open_spread THEN 'push'
            WHEN our_spread < open_spread AND result < open_spread THEN 'win'
            WHEN our_spread > open_spread AND result > open_spread THEN 'win'
            ELSE 'loss'
        END AS spread_outcome,
        abs(our_total - open_total) >= 3 AS total_pick,
        CASE
            WHEN NOT completed THEN NULL
            WHEN actual_total = open_total THEN 'push'
            WHEN our_total > open_total AND actual_total > open_total THEN 'win'
            WHEN our_total < open_total AND actual_total < open_total THEN 'win'
            ELSE 'loss'
        END AS total_outcome
    FROM picks
)
SELECT 'open' AS taken,
    tier,
    count(spread_outcome) AS graded,
    count(*) FILTER (WHERE spread_outcome = 'win') AS wins,
    count(*) FILTER (WHERE spread_outcome = 'loss') AS losses,
    count(*) FILTER (WHERE spread_outcome = 'push') AS pushes,
    sum(CASE spread_outcome WHEN 'win' THEN 100.0 / 110 WHEN 'loss' THEN -1 ELSE 0 END) AS units
FROM graded
GROUP BY tier

UNION ALL

SELECT 'open',
    'total',
    count(total_outcome),
    count(*) FILTER (WHERE total_outcome = 'win'),
    count(*) FILTER (WHERE total_outcome = 'loss'),
    count(*) FILTER (WHERE total_outcome = 'push'),
    sum(CASE total_outcome WHEN 'win' THEN 100.0 / 110 WHEN 'loss' THEN -1 ELSE 0 END)
FROM graded
WHERE total_pick
"""


# The last pick before kickoff for every Play, Caution or total from the last 3 weeks (graded or not)
RECENT_PICKS_SQL = """
SELECT r.game_id, r.start_time, r.tier, r.side, r.our_spread, r.our_total,
       r.market_spread, r.bet_spread, r.bet_price, r.bet_book, r.spread_outcome, r.spread_units,
       r.total_side, r.market_total, r.bet_total, r.total_price, r.total_book, r.total_outcome, r.total_units,
       a.school AS away, h.school AS home,
       a.espn_id AS away_espn_id, h.espn_id AS home_espn_id,
       g.away_points, g.home_points, g.completed
FROM pick_results r
JOIN games g ON g.id = r.game_id
JOIN teams a ON a.id = g.away_id
JOIN teams h ON h.id = g.home_id
WHERE r.model_version = %(version)s
  AND r.taken = 'last'
  AND (r.tier IN ('play', 'caution') OR r.total_side IS NOT NULL)
  AND r.start_time > now() - interval '21 days'
ORDER BY r.start_time DESC, a.school
"""


# The same picks graded at the median line of all books at -110, to show what line shopping adds.
# pick_log doesn't save a median price, so -110 (the usual price) stands in for it.
SHOPPING_SQL = """
WITH graded AS (
    SELECT tier AS kind,
        spread_units AS best_units,
        abs(bet_spread - market_spread) AS points_gained,
        CASE
            WHEN result = market_spread THEN 0
            WHEN side = 'home' AND result < market_spread THEN 100.0 / 110
            WHEN side = 'away' AND result > market_spread THEN 100.0 / 110
            ELSE -1
        END AS median_units
    FROM pick_results
    WHERE model_version = %(version)s
      AND taken = 'last'
      AND tier IN ('play', 'caution')
      AND spread_outcome IS NOT NULL
      AND market_spread IS NOT NULL

    UNION ALL

    SELECT 'total',
        total_units,
        abs(bet_total - market_total),
        CASE
            WHEN actual_total = market_total THEN 0
            WHEN total_side = 'over' AND actual_total > market_total THEN 100.0 / 110
            WHEN total_side = 'under' AND actual_total < market_total THEN 100.0 / 110
            ELSE -1
        END
    FROM pick_results
    WHERE model_version = %(version)s
      AND taken = 'last'
      AND total_outcome IS NOT NULL
      AND market_total IS NOT NULL
)
SELECT kind,
    count(*) AS graded,
    sum(best_units) AS best_units,
    sum(median_units) AS median_units,
    avg(points_gained) AS avg_points,
    count(*) FILTER (WHERE points_gained > 0) AS better_number
FROM graded
GROUP BY kind
"""


# One user's bets, newest game first, with team names for the page
BETS_SQL = """
SELECT r.id, r.bet_type, r.side, r.line, r.price, r.book, r.stake, r.note,
       r.created_at, r.logged_after_kickoff, r.outcome, r.profit,
       r.league, r.start_time, r.home_points, r.away_points,
       h.school AS home, a.school AS away,
       h.espn_id AS home_espn_id, a.espn_id AS away_espn_id
FROM bet_results r
JOIN games g ON g.id = r.game_id
JOIN teams h ON h.id = g.home_id
JOIN teams a ON a.id = g.away_id
WHERE r.user_id = %(user_id)s
ORDER BY r.start_time DESC, r.id DESC
"""

# One user's record by bet type, plus an "all bets" row (bet_type NULL) from ROLLUP
BET_SUMMARY_SQL = """
SELECT bet_type,
       count(*) FILTER (WHERE outcome = 'win')  AS wins,
       count(*) FILTER (WHERE outcome = 'loss') AS losses,
       count(*) FILTER (WHERE outcome = 'push') AS pushes,
       count(*) FILTER (WHERE outcome IS NULL)  AS pending,
       coalesce(sum(stake) FILTER (WHERE outcome IS NOT NULL), 0) AS risked,
       coalesce(sum(profit), 0) AS profit
FROM bet_results
WHERE user_id = %(user_id)s
GROUP BY ROLLUP (bet_type)
ORDER BY bet_type NULLS LAST
"""

# Bets on the Results page, for one league: the viewer's own and those of users who share their record
RESULTS_BETTORS_SQL = """
SELECT u.username,
       u.id = %(me)s AS is_me,
       count(*) FILTER (WHERE r.outcome = 'win')  AS wins,
       count(*) FILTER (WHERE r.outcome = 'loss') AS losses,
       count(*) FILTER (WHERE r.outcome = 'push') AS pushes,
       count(*) FILTER (WHERE r.outcome IS NULL)  AS pending,
       coalesce(sum(r.stake) FILTER (WHERE r.outcome IS NOT NULL), 0) AS risked,
       coalesce(sum(r.profit), 0) AS profit
FROM bet_results r
JOIN users u ON u.id = r.user_id
WHERE r.league = %(league)s
  AND (u.id = %(me)s OR (u.share_bets AND u.active))
GROUP BY u.id, u.username
ORDER BY u.id <> %(me)s, lower(u.username)
"""

# The same users' bets on games from the last 3 weeks (and upcoming ones), newest game first
RESULTS_BETS_SQL = """
SELECT u.username, r.bet_type, r.side, r.line, r.price, r.book, r.stake,
       r.outcome, r.profit, r.logged_after_kickoff, r.league, r.start_time,
       r.home_points, r.away_points, h.school AS home, a.school AS away
FROM bet_results r
JOIN users u ON u.id = r.user_id
JOIN games g ON g.id = r.game_id
JOIN teams h ON h.id = g.home_id
JOIN teams a ON a.id = g.away_id
WHERE r.league = %(league)s
  AND (u.id = %(me)s OR (u.share_bets AND u.active))
  AND r.start_time > now() - interval '21 days'
ORDER BY r.start_time DESC, lower(u.username)
"""

# Every pick-rule change (settings_log), newest first, for the Results page.  %(keys)s = settings.RULE_KEYS.
RULE_CHANGES_SQL = """
SELECT l.changed_at, l.key, l.old_value, l.new_value, l.reason, u.username
FROM settings_log l
LEFT JOIN users u ON u.id = l.changed_by
WHERE l.key = ANY(%(keys)s)
ORDER BY l.changed_at DESC, l.id DESC
"""

# Coach changes the detector found, waiting for an admin, newest first
PENDING_COACH_SQL = """
SELECT c.id, t.school, c.season, c.changed_at, c.outgoing, c.incoming, c.detected_at
FROM coach_changes c
JOIN teams t ON t.id = c.team_id
WHERE c.status = 'pending'
ORDER BY c.detected_at DESC
"""

# Coordinator changes the coordinator detector found, waiting for an admin, newest first
PENDING_COORD_SQL = """
SELECT c.id, t.school, c.season, c.unit, c.old_names, c.new_names, c.source_title, c.detected_at
FROM coordinator_changes c
JOIN teams t ON t.id = c.team_id
WHERE c.status = 'pending'
ORDER BY c.detected_at DESC, t.school, c.unit
"""

# Latest run of each scheduled worker job
JOB_RUNS_SQL = """
SELECT DISTINCT ON (job) job, started_at, finished_at, ok, message
FROM job_runs
ORDER BY job, started_at DESC
"""

# When each kind of data last arrived
FRESHNESS_SQL = """
SELECT (SELECT max(updated_at)  FROM live_scores)                         AS live_scores,
       (SELECT max(fetched_at)  FROM odds_snapshots)                      AS odds_snapshot,
       (SELECT max(recorded_at) FROM pick_log)                            AS picks,
       (SELECT max(created_at)  FROM predictions WHERE NOT is_backtest)   AS predictions,
       (SELECT max(fetched_at)  FROM api_responses WHERE source = 'cfbd') AS cfbd_fetch,
       (SELECT max(fetched_at)  FROM weather_forecasts)                   AS weather
"""


# Backtest results, grouped by {group_by} (filled in from GROUPINGS below, never from user input)
BACKTEST_SQL = """
SELECT {group_by} AS label,
       count(*) AS games,
       avg(abs(result - model_spread))       AS model_spread_miss,
       avg(abs(result - close_spread))       AS market_spread_miss,
       avg(abs(actual_total - model_total))  AS model_total_miss,
       avg(abs(actual_total - close_total))  AS market_total_miss,
       count(*) FILTER (WHERE abs(spread_diff) >= 3 AND spread_win)     AS ats3_w,
       count(*) FILTER (WHERE abs(spread_diff) >= 3 AND NOT spread_win) AS ats3_l,
       count(*) FILTER (WHERE abs(spread_diff) >= 5 AND spread_win)     AS ats5_w,
       count(*) FILTER (WHERE abs(spread_diff) >= 5 AND NOT spread_win) AS ats5_l,
       count(*) FILTER (WHERE abs(total_diff) >= 3 AND total_win)       AS ou3_w,
       count(*) FILTER (WHERE abs(total_diff) >= 3 AND NOT total_win)   AS ou3_l,
       count(*) FILTER (WHERE abs(open_diff) >= 3 AND clv_win)          AS clv_w,
       count(*) FILTER (WHERE abs(open_diff) >= 3 AND NOT clv_win)      AS clv_l,
       count(*) FILTER (WHERE abs(open_diff) >= 3 AND open_win)         AS open3_w,
       count(*) FILTER (WHERE abs(open_diff) >= 3 AND NOT open_win)     AS open3_l,
       count(*) FILTER (WHERE abs(open_diff) >= 3 AND best_open_win)    AS best3_w,
       count(*) FILTER (WHERE abs(open_diff) >= 3 AND NOT best_open_win) AS best3_l
FROM backtest_games
WHERE model_version = %(version)s
  AND is_backtest
  AND (%(include_2020)s OR season <> 2020)
GROUP BY 1
ORDER BY 1
"""

GROUPINGS = {"all": "'all'", "season": "season", "weeks": "weeks_bucket"}

# "This week" (same 12-hour rule as the predictions page), shared by the overrides queries
CURRENT_WEEK_CTE = """
current_week AS (
    SELECT season, week, season_type
    FROM games
    WHERE league = %(league)s
      AND (league <> 'cfb' OR 'fbs' IN (home_classification, away_classification))
      AND start_time > now() - interval '12 hours'
    ORDER BY start_time
    LIMIT 1
)
"""

# This week's games that haven't kicked off, for the overrides form
OVERRIDE_GAMES_SQL = f"""
WITH {CURRENT_WEEK_CTE}
SELECT g.id AS game_id,
       g.start_time,
       g.away_id,
       g.home_id,
       a.school AS away,
       h.school AS home
FROM games g
JOIN current_week w ON w.season = g.season
                   AND w.week = g.week
                   AND w.season_type = g.season_type
JOIN teams h ON h.id = g.home_id
JOIN teams a ON a.id = g.away_id
WHERE g.league = %(league)s
  AND (g.league <> 'cfb' OR 'fbs' IN (g.home_classification, g.away_classification))
  AND g.start_time > now()
ORDER BY g.start_time, a.school
"""

# Active overrides for recent and upcoming games
ACTIVE_OVERRIDES_SQL = """
SELECT o.id,
       o.points,
       o.reason,
       o.created_at,
       t.school AS team,
       a.school AS away,
       h.school AS home,
       g.start_time
FROM overrides o
JOIN games g ON g.id = o.game_id
JOIN teams t ON t.id = o.team_id
JOIN teams h ON h.id = g.home_id
JOIN teams a ON a.id = g.away_id
WHERE o.active
  AND g.league = %(league)s
  AND g.start_time > now() - interval '7 days'
ORDER BY g.start_time, a.school
"""


# This week's NFL injury reports (nflverse, loaded daily by cfb/nfl_injuries.py) for the panel on
# /overrides?league=nfl: players listed Out, Doubtful or Questionable for the given games.
# season_dropbacks is filled only for QBs: it shows whether an injured QB is the usual starter.
NFL_INJURIES_SQL = """
SELECT g.id AS game_id,
       i.team_id,
       i.full_name,
       i.position,
       i.report_status,
       i.injury,
       i.practice_status,
       i.loaded_at,
       (SELECT sum(q.dropbacks)
        FROM nfl_qb_games q
        JOIN games g2 ON g2.id = q.game_id
        WHERE q.qb_id = i.gsis_id
          AND g2.season = i.season) AS season_dropbacks
FROM nfl_injuries i
JOIN games g ON g.league = 'nfl'
            AND g.season = i.season
            AND g.week = i.week
            AND i.team_id IN (g.home_id, g.away_id)
WHERE g.id = ANY(%(game_ids)s)
  AND i.report_status IS NOT NULL
ORDER BY g.id,
         i.team_id,
         CASE i.report_status WHEN 'Out' THEN 1 WHEN 'Doubtful' THEN 2 ELSE 3 END,
         array_position(ARRAY['QB', 'WR', 'TE', 'RB', 'FB', 'T', 'G', 'C',
                              'DE', 'DT', 'LB', 'CB', 'S', 'K', 'P', 'LS'], i.position),
         i.full_name
"""


class OverrideIn(BaseModel):
    """What the overrides form sends."""
    game_id: int
    team_id: int
    points: float = Field(ge=-30, le=30)
    reason: str = Field(min_length=1, max_length=200)


class BetIn(BaseModel):
    """What the bet form sends.  For a spread, line is the HOME team's number (the form converts it)."""
    game_id: int
    bet_type: Literal["spread", "total", "moneyline"]
    side: Literal["home", "away", "over", "under"]
    line: float | None = Field(default=None, ge=-100, le=200)
    price: int = Field(ge=-10000, le=10000)
    book: str = Field(min_length=1, max_length=40)
    stake: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    note: str = Field(default="", max_length=200)


# Which sides go with which bet type
BET_SIDES = {
    "spread": ("home", "away"),
    "total": ("over", "under"),
    "moneyline": ("home", "away"),
}


class BetSettingsIn(BaseModel):
    """What the settings form on the bets page sends."""
    unit_size: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    share_bets: bool


class NewUserIn(BaseModel):
    """What the add-account form on the admin page sends."""
    username: str = Field(min_length=2, max_length=40)
    is_admin: bool = False


class UserChangeIn(BaseModel):
    """One change to an existing account; the actions match the cfb.users commands."""
    username: str = Field(min_length=1, max_length=40)
    action: Literal["reset", "disable", "enable", "make-admin", "remove-admin"]


class RulesIn(BaseModel):
    """The pick-rule thresholds from the admin page.  A reason is required for any change."""
    play_gap: float = Field(ge=0.5, le=20)
    total_gap: float = Field(ge=0.5, le=20)
    move_min: float = Field(ge=0, le=10)
    reason: str = Field(max_length=300)


class ScheduleIn(BaseModel):
    """The schedule editor on the admin page.  check_only = just return the warnings and credits."""
    job_schedule: dict
    odds_schedule: dict
    poll_fast_seconds: int = Field(ge=10, le=300)
    poll_slow_seconds: int = Field(ge=60, le=3600)
    reason: str = Field(default="", max_length=300)
    check_only: bool = False


class CoachChangeIn(BaseModel):
    """Confirm or reject one detected coach change; the date can be corrected when confirming."""
    action: Literal["confirm", "reject"]
    changed_at: datetime | None = None


class CoordinatorChangeIn(BaseModel):
    """Confirm or reject one detected coordinator change."""
    action: Literal["confirm", "reject"]


class BooksIn(BaseModel):
    """The bettable-books list from the admin page."""
    books: list[str] = Field(min_length=1, max_length=20)


def admin_status():
    """Everything the admin status panel shows (read-only)."""
    with connect() as conn:
        conn.row_factory = dict_row
        jobs = conn.execute(JOB_RUNS_SQL).fetchall()
        quota = conn.execute(
            "SELECT source, remaining, used_last, checked_at FROM api_quota ORDER BY source"
        ).fetchall()
        freshness = conn.execute(FRESHNESS_SQL).fetchone()
    return {
        "jobs": {j["job"]: j for j in jobs},
        "quota": {q["source"]: q for q in quota},
        "freshness": freshness,
        "versions": {"College": MODEL_VERSION, "NFL": NFL_MODEL_VERSION},
        "settings": app_settings.get_all(),
        "job_labels": schedule.JOBS,
    }


@app.get("/admin")
def admin_page(request: Request):
    """The admin page: accounts for now; status, books, pick rules and schedules as they're built."""
    require_admin(request)
    with connect() as conn:
        conn.row_factory = dict_row
        pending = conn.execute(PENDING_COACH_SQL).fetchall()
        pending_coords = conn.execute(PENDING_COORD_SQL).fetchall()
    return templates.TemplateResponse(
        request,
        "admin.html",
        {"users": all_users(), "status": admin_status(), "pending_coaches": pending,
         "pending_coordinators": pending_coords, "active": "admin"},
    )


@app.post("/api/admin/users")
def admin_add_user(request: Request, form: NewUserIn):
    """Create an account.  The temporary password goes back to the admin once, to pass on."""
    require_admin(request)
    try:
        password = add_user(form.username, form.is_admin)
    except UserError as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    return {"username": form.username.strip(), "password": password}


@app.post("/api/admin/users/change")
def admin_change_user(request: Request, form: UserChangeIn):
    """Reset a password, disable or enable, or give or take admin rights."""
    require_admin(request)
    is_me = form.username.lower() == request.state.user["username"].lower()
    if is_me and form.action in ("reset", "disable", "remove-admin"):
        raise HTTPException(status_code=400, detail="Not on your own account (use Change password instead).")
    try:
        if form.action == "reset":
            return {"password": reset_password(form.username)}
        if form.action == "disable":
            set_active(form.username, False)
        elif form.action == "enable":
            set_active(form.username, True)
        elif form.action == "make-admin":
            set_admin(form.username, True)
        elif form.action == "remove-admin":
            set_admin(form.username, False)
    except UserError as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    return {"done": form.action}


@app.post("/api/admin/settings/books")
def admin_save_books(request: Request, form: BooksIn):
    """Save the list of books users can actually bet at."""
    require_admin(request)
    books = []
    for name in form.books:
        name = name.strip()
        if not name or len(name) > 40:
            raise HTTPException(status_code=400, detail="Each book needs a name of 1 to 40 characters.")
        if name.lower() not in [b.lower() for b in books]:
            books.append(name)
    app_settings.set_value("bettable_books", books, request.state.user["id"])
    return {"books": books}


@app.post("/api/admin/settings/rules")
def admin_save_rules(request: Request, form: RulesIn):
    """Change the pick-rule thresholds.  Each value that changed is logged with the reason; the rest aren't."""
    require_admin(request)
    reason = form.reason.strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="Please give a reason: it goes in the change log on the Results page.")
    changed = []
    for key in ("play_gap", "total_gap", "move_min"):
        value = round(getattr(form, key), 1)
        if app_settings.set_value(key, value, request.state.user["id"], reason):
            changed.append(key)
    return {"changed": changed}


@app.post("/api/admin/settings/schedule")
def admin_save_schedule(request: Request, form: ScheduleIn):
    """Check (and unless check_only, save) the worker's schedule.  The worker picks it up within 5 minutes.
    Changing the odds snapshot times needs a reason, like the pick rules: they decide which lines picks use."""
    require_admin(request)
    if form.poll_fast_seconds > form.poll_slow_seconds:
        raise HTTPException(status_code=400, detail="The game-time poll can't be slower than the quiet-time poll.")
    try:
        jobs = schedule.check(form.job_schedule, schedule.DEFAULT_JOB_SCHEDULE)
        odds = schedule.check(form.odds_schedule, schedule.DEFAULT_ODDS_SCHEDULE)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from None
    result = {"warnings": schedule.warnings(odds, jobs), "monthly_credits": schedule.monthly_credits(odds),
              "snapshots_per_week": schedule.snapshots_per_week(odds)}
    if form.check_only:
        return result

    reason = form.reason.strip()
    current_odds = schedule.check(app_settings.get("odds_schedule"), schedule.DEFAULT_ODDS_SCHEDULE)
    if odds != current_odds and len(reason) < 5:
        raise HTTPException(status_code=400, detail="Changing the odds snapshot times needs a reason: "
                                                    "it goes in the change log on the Results page.")
    user_id = request.state.user["id"]
    changed = []
    for key, value in (("job_schedule", jobs), ("odds_schedule", odds),
                       ("poll_fast_seconds", form.poll_fast_seconds), ("poll_slow_seconds", form.poll_slow_seconds)):
        if app_settings.set_value(key, value, user_id, reason or None):
            changed.append(key)
    result["changed"] = changed
    return result


@app.post("/api/admin/coach-changes/{change_id}")
def admin_coach_change(request: Request, change_id: int, form: CoachChangeIn):
    """Confirm a pending coach change (the model uses it from the next update) or reject it."""
    require_admin(request)
    status = "confirmed" if form.action == "confirm" else "rejected"
    with connect() as conn:
        row = conn.execute(
            """
            UPDATE coach_changes
            SET status     = %(status)s,
                changed_at = COALESCE(%(changed_at)s, changed_at),
                note       = concat_ws('; ', note, %(who)s::text)
            WHERE id = %(id)s
              AND status = 'pending'
            RETURNING id
            """,
            {"status": status, "changed_at": form.changed_at, "id": change_id,
             "who": f"{status} by {request.state.user['username']}"},
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="No pending coach change with that id.")
    return {"done": status}


@app.post("/api/admin/coordinator-changes/{change_id}")
def admin_coordinator_change(request: Request, change_id: int, form: CoordinatorChangeIn):
    """Confirm a pending coordinator change (its new names are added to that season's row) or reject it."""
    require_admin(request)
    status = "confirmed" if form.action == "confirm" else "rejected"
    who = f"{status} by {request.state.user['username']}"
    with connect() as conn:
        change = conn.execute(
            """
            UPDATE coordinator_changes
            SET status = %s, note = concat_ws('; ', note, %s::text)
            WHERE id = %s AND status = 'pending'
            RETURNING team_id, season, unit, new_names
            """,
            (status, who, change_id),
        ).fetchone()
        if change is None:
            raise HTTPException(status_code=404, detail="No pending coordinator change with that id.")
        if status == "confirmed":
            team_id, season, unit, new_names = change
            row = conn.execute(
                "SELECT names FROM coordinators WHERE team_id = %s AND season = %s AND unit = %s",
                (team_id, season, unit),
            ).fetchone()
            names = list(row[0]) if row else []
            known = {coordinators.name_key(n) for n in names}
            names += [n for n in new_names if coordinators.name_key(n) not in known]
            # The season row keeps everyone listed during the season, like the infobox; is_new stays as it was
            conn.execute(
                "UPDATE coordinators SET names = %s WHERE team_id = %s AND season = %s AND unit = %s",
                (names, team_id, season, unit),
            )
    return {"done": status}


def backtest_summary(group, include_2020, version=MODEL_VERSION):
    """Backtest results for one grouping: 'all' (one row), 'season', or 'weeks'."""
    sql = BACKTEST_SQL.format(group_by=GROUPINGS[group])
    with connect() as conn:
        conn.row_factory = dict_row
        return conn.execute(
            sql, {"version": version, "include_2020": include_2020}
        ).fetchall()


LEAGUES = ("cfb", "nfl")


def pick_league(league):
    """The league from the URL, or 'cfb' for anything we don't know."""
    return league if league in LEAGUES else "cfb"


def score_games(league, season=None, week=None, season_type="regular"):
    """Run SCORES_SQL for one league and week (this week when week is None), with local kickoff times."""
    params = {"league": league, "season": season, "week": week, "season_type": season_type}
    with connect() as conn:
        conn.row_factory = dict_row     # rows come back as dicts: g["away"]
        games = conn.execute(SCORES_SQL, params).fetchall()
    for g in games:
        g["local_start"] = g["start_time"].astimezone(LOCAL_TZ)
    return games


@app.get("/login")
def login_page(request: Request, next_url: str = "/"):
    """The login form."""
    return templates.TemplateResponse(
        request, "login.html", {"error": None, "next_url": safe_next(next_url), "username": ""}
    )


@app.post("/login")
def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next_url: str = Form("/"),
):
    """Check the password; on success set the session cookie and go on."""
    with connect() as conn:
        user_id, error = authenticate(conn, username, password, client_ip(request))
        token = None
        if user_id is not None:
            token = create_session(conn, user_id)
    if error:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": error, "next_url": safe_next(next_url), "username": username},
            status_code=401,
        )
    response = RedirectResponse(safe_next(next_url), status_code=303)
    set_session_cookie(request, response, token)
    return response


@app.post("/logout")
def logout(request: Request):
    """End this session and go back to the login page."""
    with connect() as conn:
        end_session(conn, request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/account/password")
def password_page(request: Request):
    """The change-password form."""
    forced = request.state.user["must_change_password"]
    return templates.TemplateResponse(
        request, "password.html", {"error": None, "done": False, "forced": forced}
    )


@app.post("/account/password")
def password_change(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(""),
    confirm_password: str = Form(""),
):
    """Change your own password."""
    user = request.state.user
    if new_password != confirm_password:
        error = "The two new passwords don't match."
    else:
        with connect() as conn:
            error = change_password(
                conn, user["id"], current_password, new_password,
                request.cookies.get(SESSION_COOKIE),
            )
    if error:
        return templates.TemplateResponse(
            request,
            "password.html",
            {"error": error, "done": False, "forced": user["must_change_password"]},
            status_code=400,
        )
    if user["must_change_password"]:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "password.html", {"error": None, "done": True, "forced": False}
    )


@app.get("/")
def home():
    return RedirectResponse("/scores")


@app.get("/scores")
def scores_page(request: Request, league: str = "cfb", season: int | None = None,
                week: int | None = None, season_type: str = "regular"):
    """The scores page for one league (?league=cfb or nfl), this week or a chosen one (&season=2026&week=11)."""
    league = pick_league(league)
    if season is None or week is None or season_type not in ("regular", "postseason"):
        season, week, season_type = None, None, "regular"      # anything incomplete: this week
    games = score_games(league, season, week, season_type)
    with connect() as conn:
        conn.row_factory = dict_row
        weeks = conn.execute(SCORE_WEEKS_SQL, {"league": league}).fetchall()
        current = conn.execute(SCORES_CURRENT_WEEK_SQL, {"league": league}).fetchone()
    return templates.TemplateResponse(
        request, "scores.html",
        {"games": games, "league": league, "active": "scores",
         "week_nav": make_week_nav(games, weeks, current, season, week, season_type)},
    )


@app.get("/scores/rows")
def scores_rows(request: Request, league: str = "cfb"):
    """Just the table rows; HTMX swaps these in every 30 seconds."""
    league = pick_league(league)
    return templates.TemplateResponse(
        request, "_score_rows.html", {"games": score_games(league), "league": league}
    )


def make_week_nav(games, weeks, current, season, week, season_type):
    """Which week is on screen, its neighbours in the list, and whether it's past, for the week picker."""
    if games:
        shown = (games[0]["view_season"], games[0]["view_week"], games[0]["view_season_type"])
    else:
        shown = (season, week, season_type)
    keys = [(w["season"], w["week"], w["season_type"]) for w in weeks]
    at = keys.index(shown) if shown in keys else None
    now_key = (current["season"], current["week"], current["season_type"]) if current else None
    now_at = keys.index(now_key) if now_key in keys else None
    return {
        "weeks": weeks,
        "shown": shown,
        "prev": keys[at - 1] if at is not None and at > 0 else None,
        "next": keys[at + 1] if at is not None and at + 1 < len(keys) else None,
        "is_current": season is None or shown == now_key,
        # before this week in the list (a week with no predictions counts as past)
        "is_past": shown != now_key and (at is None or now_at is None or at < now_at),
    }


@app.get("/predictions")
def predictions_page(request: Request, season: int | None = None, week: int | None = None,
                     season_type: str = "regular", league: str = "cfb"):
    """Our model's lines for this week, or for a past week (?season=2026&week=11); &league=nfl for the NFL."""
    if season is None or week is None or season_type not in ("regular", "postseason"):
        season, week, season_type = None, None, "regular"      # anything incomplete: this week
    if pick_league(league) == "nfl":
        return nfl_predictions_page(request, season, week, season_type)
    params = {"version": MODEL_VERSION, "season": season, "week": week, "season_type": season_type}
    rules = app_settings.get_all()
    with connect() as conn:
        conn.row_factory = dict_row
        games = conn.execute(PREDICTIONS_SQL, params).fetchall()
        rates = conn.execute(PICK_RATES_SQL, {"version": MODEL_VERSION, **rules}).fetchall()
        weeks = conn.execute(PREDICTION_WEEKS_SQL, {"league": "cfb"}).fetchall()
        current = conn.execute(f"WITH {CURRENT_WEEK_CTE} SELECT season, week, season_type FROM current_week",
                               {"league": "cfb"}).fetchone()
    week_nav = make_week_nav(games, weeks, current, season, week, season_type)
    pick_rates = {r["tier"]: r for r in rates}      # e.g. {"play": {...}, "pass": {...}}
    for g in games:
        g["local_start"] = g["start_time"].astimezone(LOCAL_TZ)
        if g["started"] and g["rec_tier"] is not None:
            g["pick"] = recorded_pick(g)    # what we actually picked before kickoff
        else:
            g["pick"] = make_pick(g, rules)        # same rule the worker uses to record picks
    return templates.TemplateResponse(
        request,
        "predictions.html",
        {"games": games, "pick_rates": pick_rates, "version": MODEL_VERSION, "active": "predictions",
         "week_nav": week_nav, "league": "cfb", "bettable_books": rules["bettable_books"], "rules": rules},
    )


def nfl_predictions_page(request, season, week, season_type):
    """NFL tab of the predictions page: our line and total beside the nflverse line, paper picks only."""
    params = {"version": NFL_MODEL_VERSION, "season": season, "week": week, "season_type": season_type}
    rules = app_settings.get_all()
    with connect() as conn:
        conn.row_factory = dict_row
        games = conn.execute(NFL_PREDICTIONS_SQL, params).fetchall()
        weeks = conn.execute(PREDICTION_WEEKS_SQL, {"league": "nfl"}).fetchall()
        current = conn.execute(NFL_CURRENT_WEEK_SQL).fetchone()
        rates = conn.execute(NFL_PICK_RATES_SQL, {"version": NFL_MODEL_VERSION, **rules}).fetchall()
    for g in games:
        g["local_start"] = g["start_time"].astimezone(LOCAL_TZ)
        # Started games with a saved pick show that pick and its official result; the others work it
        # out on the page from our line and the nflverse line.
        g["recorded"] = recorded_pick(g) if g["started"] and g["rec_tier"] is not None else None
    return templates.TemplateResponse(
        request,
        "nfl_predictions.html",
        {"games": games, "version": NFL_MODEL_VERSION, "active": "predictions", "league": "nfl",
         "bettable_books": rules["bettable_books"], "rules": rules,
         "pick_rates": {r["tier"]: r for r in rates},
         "week_nav": make_week_nav(games, weeks, current, season, week, season_type)},
    )


@app.get("/backtest")
def backtest_page(request: Request, league: str = "cfb"):
    """How the model would have done, walk-forward, vs. the market (?league=nfl for the NFL)."""
    league = pick_league(league)
    version = NFL_MODEL_VERSION if league == "nfl" else MODEL_VERSION
    return templates.TemplateResponse(
        request,
        "backtest.html",
        {
            "overall": backtest_summary("all", include_2020=False, version=version),
            "seasons": backtest_summary("season", include_2020=True, version=version),
            "weeks": backtest_summary("weeks", include_2020=False, version=version),
            "version": version,
            "active": "backtest",
            "league": league,
        },
    )


@app.get("/results")
def results_page(request: Request, league: str = "cfb"):
    """Our picks, saved before kickoff and graded at the best price we could get (?league=nfl for the NFL)."""
    league = pick_league(league)
    version = NFL_MODEL_VERSION if league == "nfl" else MODEL_VERSION
    with connect() as conn:
        conn.row_factory = dict_row
        summary = conn.execute(RESULTS_SUMMARY_SQL, {"version": version}).fetchall()
        bettable = conn.execute(BETTABLE_SUMMARY_SQL, {"version": version}).fetchall()
        if league == "cfb":
            # Bovada's opening line exists only for college
            summary += conn.execute(OPEN_RESULTS_SQL, {"version": version}).fetchall()
        recent = conn.execute(RECENT_PICKS_SQL, {"version": version}).fetchall()
        shopping = conn.execute(SHOPPING_SQL, {"version": version}).fetchall()
        rule_changes = conn.execute(RULE_CHANGES_SQL, {"keys": sorted(app_settings.RULE_KEYS)}).fetchall()
        params = {"league": league, "me": request.state.user["id"]}
        bettors = conn.execute(RESULTS_BETTORS_SQL, params).fetchall()
        bets = conn.execute(RESULTS_BETS_SQL, params).fetchall()
    for r in recent:
        r["local_start"] = r["start_time"].astimezone(LOCAL_TZ)
    for b in bets:
        b["local_start"] = b["start_time"].astimezone(LOCAL_TZ)
    return templates.TemplateResponse(
        request,
        "results.html",
        {"summary": summary, "recent": recent, "shopping": shopping, "version": version,
         "active": "results", "league": league,
         "rules": app_settings.get_all(), "rule_changes": rule_changes,
         "bettors": bettors, "bets": bets, "bettable": bettable},
    )


@app.get("/bets")
def bets_page(request: Request, user: str | None = None):
    """Your bets and record.  ?user=name shows another user's record, if they share it."""
    me = request.state.user
    with connect() as conn:
        conn.row_factory = dict_row
        settings = conn.execute(
            "SELECT unit_size, share_bets FROM users WHERE id = %s", (me["id"],)
        ).fetchone()
        # Other users who share their record, for the "view" links
        sharing = conn.execute(
            """
            SELECT username FROM users
            WHERE share_bets AND active AND id <> %s
            ORDER BY lower(username)
            """,
            (me["id"],),
        ).fetchall()

        if user is None or user.lower() == me["username"].lower():
            owner = {"id": me["id"], "username": me["username"], "unit_size": settings["unit_size"]}
        else:
            owner = conn.execute(
                """
                SELECT id, username, unit_size FROM users
                WHERE lower(username) = lower(%s) AND share_bets AND active
                """,
                (user,),
            ).fetchone()
            if owner is None:
                raise HTTPException(status_code=404, detail="No shared record for that user.")

        summary = conn.execute(BET_SUMMARY_SQL, {"user_id": owner["id"]}).fetchall()
        bets = conn.execute(BETS_SQL, {"user_id": owner["id"]}).fetchall()

    for b in bets:
        b["local_start"] = b["start_time"].astimezone(LOCAL_TZ)
    return templates.TemplateResponse(
        request,
        "bets.html",
        {"owner": owner, "is_me": owner["id"] == me["id"], "settings": settings,
         "sharing": sharing, "summary": summary, "bets": bets, "active": "bets"},
    )


@app.get("/overrides")
def overrides_page(request: Request, game_id: int | None = None, league: str = "cfb"):
    """Add or remove manual adjustments for this week's games (?league=nfl for the NFL)."""
    league = pick_league(league)
    injury_games, injuries = [], []                                     # new
    with connect() as conn:
        conn.row_factory = dict_row
        games = conn.execute(OVERRIDE_GAMES_SQL, {"league": league}).fetchall()
        overrides = conn.execute(ACTIVE_OVERRIDES_SQL, {"league": league}).fetchall()
        if league == "nfl":                                             # new: injury panel
            params = {"version": NFL_MODEL_VERSION, "season": None, "week": None, "season_type": None}
            injury_games = [g for g in conn.execute(NFL_PREDICTIONS_SQL, params).fetchall()
                            if not g["started"]]
            injuries = conn.execute(
                NFL_INJURIES_SQL, {"game_ids": [g["game_id"] for g in injury_games]}
            ).fetchall()
    for row in games + overrides + injury_games:                       # changed: + injury_games
        row["local_start"] = row["start_time"].astimezone(LOCAL_TZ)
    return templates.TemplateResponse(
        request,
        "overrides.html",
        {"games": games, "overrides": overrides, "selected_game": game_id,
         "active": "overrides", "league": league,
         "injury_games": injury_games, "injuries": injuries},          # new
    )


@app.post("/api/bets")
def add_bet(request: Request, bet: BetIn):
    """Save one bet for the logged-in user."""
    if bet.side not in BET_SIDES[bet.bet_type]:
        raise HTTPException(status_code=400, detail="That side doesn't go with that bet type.")
    if (bet.line is None) != (bet.bet_type == "moneyline"):
        raise HTTPException(status_code=400, detail="Spreads and totals need a line; moneylines don't.")
    if -100 < bet.price < 100:
        raise HTTPException(status_code=400, detail="Price must be American odds, like -110 or +150.")

    params = bet.model_dump()
    params["user_id"] = request.state.user["id"]
    params["book"] = params["book"].strip()
    params["note"] = params["note"].strip() or None
    with connect() as conn:
        added = conn.execute(
            """
            INSERT INTO bets (user_id, game_id, bet_type, side, line, price, book, stake, note)
            SELECT %(user_id)s, %(game_id)s, %(bet_type)s, %(side)s, %(line)s, %(price)s,
                   %(book)s, %(stake)s, %(note)s
            WHERE EXISTS (SELECT 1 FROM games WHERE id = %(game_id)s)
            RETURNING id
            """,
            params,
        ).fetchone()
    if added is None:
        raise HTTPException(status_code=404, detail="No such game.")
    return {"id": added[0]}


@app.post("/api/bets/{bet_id}/remove")
def remove_bet(request: Request, bet_id: int):
    """Remove one of your own bets before its game kicks off (the row is kept for history)."""
    with connect() as conn:
        removed = conn.execute(
            """
            UPDATE bets b
            SET removed_at = now()
            FROM games g
            WHERE b.id = %(bet_id)s
              AND b.user_id = %(user_id)s
              AND b.removed_at IS NULL
              AND g.id = b.game_id
              AND g.start_time > now()
            """,
            {"bet_id": bet_id, "user_id": request.state.user["id"]},
        ).rowcount
    if removed == 0:
        raise HTTPException(status_code=404, detail="No bet of yours that can still be removed.")
    return {"removed": bet_id}


@app.post("/api/bets/settings")
def save_bet_settings(request: Request, form: BetSettingsIn):
    """Save your unit size and whether other users can see your record."""
    params = form.model_dump()
    params["user_id"] = request.state.user["id"]
    with connect() as conn:
        conn.execute(
            """
            UPDATE users
            SET unit_size = %(unit_size)s, share_bets = %(share_bets)s
            WHERE id = %(user_id)s
            """,
            params,
        )
    return {"saved": True}


@app.post("/api/overrides")
def add_override(request: Request, override: OverrideIn):
    """Save one adjustment. The team must be playing in that game."""
    require_admin(request)
    params = override.model_dump()
    params["reason"] = params["reason"].strip()
    if not params["reason"]:
        raise HTTPException(status_code=400, detail="Please give a reason.")
    with connect() as conn:
        added = conn.execute(
            """
            INSERT INTO overrides (game_id, team_id, points, reason)
            SELECT %(game_id)s, %(team_id)s, %(points)s, %(reason)s
            WHERE EXISTS (
                SELECT 1 FROM games
                WHERE id = %(game_id)s AND %(team_id)s IN (home_id, away_id)
            )
            RETURNING id
            """,
            params,
        ).fetchone()
    if added is None:
        raise HTTPException(status_code=400, detail="That team isn't playing in that game.")
    return {"id": added[0]}


@app.post("/api/overrides/{override_id}/remove")
def remove_override(request: Request, override_id: int):
    """Switch an override off (kept in the table for history)."""
    require_admin(request)
    with connect() as conn:
        removed = conn.execute(
            "UPDATE overrides SET active = false WHERE id = %s AND active", (override_id,)
        ).rowcount
    if removed == 0:
        raise HTTPException(status_code=404, detail="No active override with that id.")
    return {"removed": override_id}


@app.get("/api/qb-suggestion")
def qb_suggestion(game_id: int, team_id: int):
    """Main QB for the team this season and a suggested adjustment if he's out."""
    with connect() as conn:
        row = conn.execute(
            "SELECT season FROM games WHERE id = %s AND %s IN (home_id, away_id)",
            (game_id, team_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="That team isn't playing in that game.")
    suggestion = qb_out_suggestion(team_id, row[0])
    if suggestion is None:
        raise HTTPException(status_code=404, detail="No passing data for that team this season yet.")
    return suggestion
