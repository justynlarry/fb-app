"""Head-coach detector: notice mid-season head-coach changes on ESPN and queue them for an admin to confirm.

Run daily by the worker (job "coach_watch").  For every FBS team it asks ESPN's core API who the head coach
is this season (2 free requests per team).  The first time a team is seen in a season, it only records the
baseline.  If the coach later differs, it adds a *pending* row to coach_changes; nothing reaches the model
until an admin confirms it on the admin page.

    docker compose exec worker python -m cfb.coach_watch 2026 --dry-run    (print only, saves nothing)
    docker compose exec worker python -m cfb.coach_watch 2026
"""

import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

from cfb.db import connect

CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football"
PAUSE = 0.2     # seconds between teams (~280 requests a run)

# Every team that plays as an FBS team this season, with its ESPN id
FBS_TEAMS_SQL = """
SELECT DISTINCT t.id, t.espn_id, t.school
FROM games g
JOIN teams t ON t.id IN (g.home_id, g.away_id)
WHERE g.league = 'cfb'
  AND g.season = %(season)s
  AND t.espn_id IS NOT NULL
  AND ((t.id = g.home_id AND g.home_classification = 'fbs')
       OR (t.id = g.away_id AND g.away_classification = 'fbs'))
ORDER BY t.school
"""


def espn_head_coach(season, espn_team_id):
    """(ESPN coach id, "First Last") for the team's current head coach, or None if ESPN lists none."""
    listing = httpx.get(f"{CORE}/seasons/{season}/teams/{espn_team_id}/coaches", timeout=20)
    listing.raise_for_status()
    items = listing.json().get("items", [])
    if not items:
        return None
    # The listing only links to the coach; a second request gets the name
    coach = httpx.get(items[0]["$ref"].replace("http://", "https://"), timeout=20)
    coach.raise_for_status()
    c = coach.json()
    return int(c["id"]), f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()


def last_game_before(conn, team_id, season, moment):
    """Kickoff of the team's last game this season before 'moment', or None if it hasn't played yet."""
    row = conn.execute(
        """
        SELECT max(start_time) FROM games
        WHERE season = %s AND %s IN (home_id, away_id) AND start_time < %s
        """,
        (season, team_id, moment),
    ).fetchone()
    return row[0]


def check_team(conn, team_id, season, coach_id, name, now):
    """Record what ESPN says for one team.  Returns 'baseline', 'same', 'pending' or 'skipped'."""
    current = conn.execute(
        """
        SELECT espn_coach_id, coach_name FROM head_coach_watch
        WHERE team_id = %s AND season = %s
        ORDER BY last_seen DESC
        LIMIT 1
        """,
        (team_id, season),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO head_coach_watch (team_id, season, espn_coach_id, coach_name, first_seen, last_seen)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (team_id, season, espn_coach_id) DO UPDATE SET last_seen = EXCLUDED.last_seen
        """,
        (team_id, season, coach_id, name, now, now),
    )
    if current is None:
        return "baseline"
    if current[0] == coach_id:
        return "same"

    # A different coach than last time.  coach_changes keeps one change per team-season.
    exists = conn.execute(
        "SELECT 1 FROM coach_changes WHERE team_id = %s AND season = %s", (team_id, season)
    ).fetchone()
    if exists:
        return "skipped"
    last = last_game_before(conn, team_id, season, now)
    changed_at = last + timedelta(days=1) if last else now
    conn.execute(
        """
        INSERT INTO coach_changes (team_id, season, changed_at, outgoing, incoming,
                                   source, status, detected_at, note)
        VALUES (%s, %s, %s, %s, %s, 'espn', 'pending', %s, %s)
        """,
        (team_id, season, changed_at, current[1], name, now,
         "found by the coach detector; changed_at = last game before it was seen + 1 day"),
    )
    return "pending"


def run(season, dry_run=False):
    """Check every FBS team once.  Returns how many teams had each outcome."""
    now = datetime.now(timezone.utc)
    counts = {"baseline": 0, "same": 0, "pending": 0, "skipped": 0, "no coach listed": 0, "failed": 0}
    with connect() as conn:
        teams = conn.execute(FBS_TEAMS_SQL, {"season": season}).fetchall()
    for team_id, espn_id, school in teams:
        time.sleep(PAUSE)
        try:
            found = espn_head_coach(season, espn_id)
        except (httpx.HTTPError, KeyError, ValueError) as err:
            print(f"coach watch: {school} failed: {err!r}")
            counts["failed"] += 1
            continue
        if found is None:
            counts["no coach listed"] += 1
            continue
        coach_id, name = found
        if dry_run:
            print(f"{school:28} {name} ({coach_id})")
            continue
        with connect() as conn:
            outcome = check_team(conn, team_id, season, coach_id, name, now)
        counts[outcome] += 1
        if outcome == "pending":
            print(f"coach watch: {school}: new head coach {name}, waiting for confirmation")
    return counts


if __name__ == "__main__":
    season = int(sys.argv[1])
    print(run(season, dry_run="--dry-run" in sys.argv))
