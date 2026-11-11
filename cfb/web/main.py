"""Web UI. Pages only read from Postgres; the worker does all the fetching."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row

from cfb.db import connect

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
