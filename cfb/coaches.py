"""Mid-season head-coach changes, for the v5 coach_change feature.

History (2016-2025) is derived from cached /coaches responses, so it costs no API calls.
The current season is entered by hand: CFBD fills in this season's coaches only after it ends.
"""

from datetime import timedelta

from cfb import cfbd
from cfb.db import connect

# A team's games in a season, in order (all types: the coach's game count includes bowls)
TEAM_GAMES_SQL = """
SELECT start_time, season_type
FROM games
WHERE league = 'cfb'
  AND season = %(season)s
  AND completed
  AND %(team_id)s IN (home_id, away_id)
ORDER BY start_time
"""

SAVE_CHANGE_SQL = """
INSERT INTO coach_changes (team_id, season, changed_at, outgoing, incoming, source)
VALUES (%(team_id)s, %(season)s, %(changed_at)s, %(outgoing)s, %(incoming)s, 'cfbd')
ON CONFLICT (team_id, season) DO UPDATE SET
    changed_at = EXCLUDED.changed_at,
    outgoing   = EXCLUDED.outgoing,
    incoming   = EXCLUDED.incoming
WHERE coach_changes.source = 'cfbd'
"""


def coach_seasons(season, cfbd_to_id):
    """{team_id: {coach name: games coached}} for one season, from the cached /coaches response."""
    teams = {}
    for coach in cfbd.get("/coaches", {"year": season}):
        name = coach["firstName"] + " " + coach["lastName"]
        for s in coach.get("seasons", []):
            team_id = cfbd_to_id.get(s.get("teamId"))
            if team_id is not None and s.get("year") == season:
                teams.setdefault(team_id, {})[name] = s.get("games") or 0
    return teams


def load_coach_changes(first_season=2016, last_season=2025):
    """Find regular-season coach changes and save them to coach_changes (source = 'cfbd').

    A team with two head coaches in one season changed coaches mid-season. The outgoing coach is
    the one who also coached the team the season before; his game count says after which game
    the change came. Changes after the regular season (bowls, playoffs) are left out.
    """
    with connect() as conn:
        cfbd_to_id = dict(conn.execute("SELECT cfbd_id, id FROM teams WHERE league = 'cfb'").fetchall())

    saved = 0
    skipped = 0
    last_year = coach_seasons(first_season - 1, cfbd_to_id)
    for season in range(first_season, last_season + 1):
        this_year = coach_seasons(season, cfbd_to_id)
        with connect() as conn:
            for team_id, coaches in this_year.items():
                if len(coaches) != 2:
                    continue
                before = last_year.get(team_id, {})
                outgoing = [name for name in coaches if name in before]
                if len(outgoing) != 1:
                    skipped += 1        # neither (or both) coached here last season: can't tell who left
                    continue
                outgoing = outgoing[0]
                incoming = [name for name in coaches if name != outgoing][0]
                games_coached = coaches[outgoing]

                games = conn.execute(TEAM_GAMES_SQL, {"season": season, "team_id": team_id}).fetchall()
                if games_coached == 0 or games_coached >= len(games):
                    skipped += 1        # left before the season, or our game list doesn't match
                    continue
                last_start, _ = games[games_coached - 1]
                _, next_type = games[games_coached]
                if next_type != "regular":
                    continue            # change came after the regular season (bowl/playoff): not used

                conn.execute(SAVE_CHANGE_SQL, {
                    "team_id": team_id,
                    "season": season,
                    "changed_at": last_start + timedelta(days=1),
                    "outgoing": outgoing,
                    "incoming": incoming,
                })
                saved += 1
        last_year = this_year
    print(f"{saved} regular-season coach changes saved, {skipped} skipped")
