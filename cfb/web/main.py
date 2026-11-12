"""Web UI. Pages only read from Postgres; the worker does all the fetching."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from cfb.db import connect
from cfb.model import MODEL_VERSION
from cfb.qbs import qb_out_suggestion

WEB_DIR = Path(__file__).parent
LOCAL_TZ = ZoneInfo(os.environ.get("TZ", "America/Denver"))

app = FastAPI()
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
templates = Jinja2Templates(directory=WEB_DIR / "templates")

# This week's FBS games with their latest live snapshot (if any).
# "This week" = the week of the next game that hasn't been over for 24+ hours.
SCORES_SQL = """
WITH current_week AS (
    SELECT season, week, season_type
    FROM games
    WHERE league = 'cfb'
      AND 'fbs' IN (home_classification, away_classification)
      AND start_time > now() - interval '24 hours'
    ORDER BY start_time
    LIMIT 1
)
SELECT a.school AS away,
    h.school AS home,
    g.start_time,
    g.start_time_tbd,
    l.state,
    l.status_detail,
    l.away_score,
    l.home_score,
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
WHERE g.league = 'cfb'
  AND 'fbs' IN (g.home_classification, g.away_classification)
ORDER BY g.start_time, a.school
"""

# Our predictions for this week's games, with the typical miss for that point in
# the season (from the backtest), any manual overrides, and the market line for comparison.
PREDICTIONS_SQL = """
WITH current_week AS (
    SELECT season, week, season_type
    FROM games
    WHERE league = 'cfb'
      AND 'fbs' IN (home_classification, away_classification)
      AND start_time > now() - interval '24 hours'
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
           avg(spread_open) AS open_spread,
           max(spread_open) AS open_hi,
           min(spread_open) AS open_lo,
           avg(over_under_open) AS open_total
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
       mm.spread_miss,
       mm.total_miss,
       COALESCE(l.spread, m.spread) AS market_spread,
       COALESCE(l.over_under, m.total) AS market_total,
       m.open_spread,
       m.open_hi,
       m.open_lo,
       m.open_total,
       l.state,
       l.away_score, l.home_score,
       l.away_rank, l.home_rank,
       l.away_record, l.home_record,
       l.away_conf_record, l.home_conf_record,
       ven.dome,
       wf.temperature_f, wf.wind_mph, wf.gust_mph, wf.precip_in
FROM games g
JOIN current_week w ON w.season = g.season
                   AND w.week = g.week
                   AND w.season_type = g.season_type
JOIN predictions p ON p.game_id = g.id
                  AND p.model_version = %(version)s
                  AND NOT p.is_backtest
JOIN teams h ON h.id = g.home_id
JOIN teams a ON a.id = g.away_id
LEFT JOIN model_miss mm ON mm.bucket = LEAST(p.weeks_played, 6)
LEFT JOIN market m ON m.game_id = g.id
LEFT JOIN adjustments adj ON adj.game_id = g.id
LEFT JOIN live_scores l ON l.game_id = g.id
LEFT JOIN venues ven ON ven.id = g.venue_id
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


# How each kind of pick did in the backtest. The tier rule must match predictions.html
PICK_RATES_SQL = """
SELECT CASE WHEN abs(model_spread - close_spread) < 3 THEN 'pass'
            WHEN abs(close_spread - open_spread) >= 0.5
             AND sign(close_spread - open_spread) <> sign(model_spread - open_spread) THEN 'caution'
            ELSE 'play'
       END AS tier,
       count(spread_win) AS games,
       avg(spread_win::int) AS win_rate
FROM backtest_games
WHERE model_version = %(version)s
  AND is_backtest
  AND season >= 2021
  AND open_spread IS NOT NULL
  AND close_spread IS NOT NULL
GROUP BY 1

UNION ALL

SELECT CASE WHEN total_diff > 0 THEN 'over' ELSE 'under' END,
       count(total_win),
       avg(total_win::int)
FROM backtest_games
WHERE model_version = %(version)s
  AND is_backtest
  AND season <> 2020
  AND abs(total_diff) >= 3
GROUP BY 1
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

# "This week" (same rule as the scores page), shared by the overrides queries
CURRENT_WEEK_CTE = """
current_week AS (
    SELECT season, week, season_type
    FROM games
    WHERE league = 'cfb'
      AND 'fbs' IN (home_classification, away_classification)
      AND start_time > now() - interval '24 hours'
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
WHERE g.league = 'cfb'
  AND 'fbs' IN (g.home_classification, g.away_classification)
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
  AND g.start_time > now() - interval '7 days'
ORDER BY g.start_time, a.school
"""


class OverrideIn(BaseModel):
    """What the overrides form sends."""
    game_id: int
    team_id: int
    points: float = Field(ge=-30, le=30)
    reason: str = Field(min_length=1, max_length=200)


def backtest_summary(group, include_2020):
    """Backtest results for one grouping: 'all' (one row), 'season', or 'weeks'."""
    sql = BACKTEST_SQL.format(group_by=GROUPINGS[group])
    with connect() as conn:
        conn.row_factory = dict_row
        return conn.execute(
            sql, {"version": MODEL_VERSION, "include_2020": include_2020}
        ).fetchall()


def current_week_games():
    """Run SCORES_SQL and add each game's kickoff in local time."""
    with connect() as conn:
        conn.row_factory = dict_row     # rows come back as dicts: g["away"]
        games = conn.execute(SCORES_SQL).fetchall()
    for g in games:
        g["local_start"] = g["start_time"].astimezone(LOCAL_TZ)
    return games


@app.get("/")
def home():
    return RedirectResponse("/scores")


@app.get("/scores")
def scores_page(request: Request):
    """The full scores page."""
    return templates.TemplateResponse(
        request, "scores.html", {"games": current_week_games(), "active": "scores"}
    )


@app.get("/scores/rows")
def scores_rows(request: Request):
    """Just the table rows; HTMX swaps these in every 30 seconds."""
    return templates.TemplateResponse(
        request, "_score_rows.html", {"games": current_week_games()}
    )


@app.get("/predictions")
def predictions_page(request: Request):
    """Our model's lines for this week; market comparison is hidden until you ask for it."""
    with connect() as conn:
        conn.row_factory = dict_row
        games = conn.execute(PREDICTIONS_SQL, {"version": MODEL_VERSION}).fetchall()
        rates = conn.execute(PICK_RATES_SQL, {"version": MODEL_VERSION}).fetchall()
    pick_rates = {r["tier"]: r for r in rates}      # e.g. {"play": {...}, "pass": {...}}
    for g in games:
        g["local_start"] = g["start_time"].astimezone(LOCAL_TZ)
    return templates.TemplateResponse(
        request,
        "predictions.html",
        {"games": games, "pick_rates": pick_rates, "version": MODEL_VERSION, "active": "predictions"},
    )


@app.get("/backtest")
def backtest_page(request: Request):
    """How the model would have done, walk-forward, vs. the market."""
    return templates.TemplateResponse(
        request,
        "backtest.html",
        {
            "overall": backtest_summary("all", include_2020=False),
            "seasons": backtest_summary("season", include_2020=True),
            "weeks": backtest_summary("weeks", include_2020=False),
            "version": MODEL_VERSION,
            "active": "backtest",
        },
    )


@app.get("/overrides")
def overrides_page(request: Request, game_id: int | None = None):
    """Add or remove manual adjustments for this week's games."""
    with connect() as conn:
        conn.row_factory = dict_row
        games = conn.execute(OVERRIDE_GAMES_SQL).fetchall()
        overrides = conn.execute(ACTIVE_OVERRIDES_SQL).fetchall()
    for row in games + overrides:
        row["local_start"] = row["start_time"].astimezone(LOCAL_TZ)
    return templates.TemplateResponse(
        request,
        "overrides.html",
        {"games": games, "overrides": overrides, "selected_game": game_id, "active": "overrides"},
    )


@app.post("/api/overrides")
def add_override(override: OverrideIn):
    """Save one adjustment. The team must be playing in that game."""
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
def remove_override(override_id: int):
    """Switch an override off (kept in the table for history)."""
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
