"""Parse raw CFBD responses (already saved in api_responses) into our tables.

Costs no API calls when the data is already saved.
"""
from datetime import datetime

from cfb import cfbd
from cfb.db import connect


def load_teams(year):
    """Insert or update every team listed for one season."""
    teams = cfbd.get("/teams", {"year": year})
    with connect() as conn:
        for t in teams:
            conn.execute(
                """
                INSERT INTO teams (league, cfbd_id, espn_id, school, mascot,
                                   abbreviation, conference, classification)
                VALUES ('cfb', %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (league, cfbd_id) DO UPDATE SET
                    school          = EXCLUDED.school,
                    mascot          = EXCLUDED.mascot,
                    abbreviation    = EXCLUDED.abbreviation,
                    conference      = EXCLUDED.conference,
                    classification  = EXCLUDED.classification
                """,
                (
                    t["id"],
                    t["id"],        # CFBD team ids are ESPN's ids
                    t["school"],
                    t.get("mascot"),
                    t.get("abbreviation"),
                    t.get("conference"),
                    t.get("classification"),
                ),
            )
    print(f"teams {year}: {len(teams)} loaded")


def load_games(year):
    """Insert or update every game for one season (regular + postseason)."""
    games = cfbd.get("/games", {"year": year, "seasonType": "both"})
    with connect() as conn:
        # Map CFBD team id -> our teams.id, e.g. {66: 412, 2306: 98, ...}
        team_ids = dict(
            conn.execute("SELECT cfbd_id, id FROM teams WHERE league = 'cfb'").fetchall()
        )

        loaded = 0
        skipped = 0
        for g in games:
            home_id = team_ids.get(g["homeId"])
            away_id = team_ids.get(g["awayId"])
            if home_id is None or away_id is None:
                skipped += 1    # a non-NCAA opponent we don't track
                continue

            conn.execute(
                """
                INSERT INTO games (league, cfbd_id, espn_id, season, week, season_type,
                                   start_time, start_time_tbd, neutral_site,
                                   home_id, away_id, home_points, away_points, completed)
                VALUES ('cfb', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (league, cfbd_id) DO UPDATE SET
                    start_time          = EXCLUDED.start_time,
                    start_time_tbd      = EXCLUDED.start_time_tbd,
                    neutral_site        = EXCLUDED.neutral_site,
                    home_points         = EXCLUDED.home_points,
                    away_points         = EXCLUDED.away_points,
                    completed           = EXCLUDED.completed
                """,
                (
                    g["id"],
                    g["id"],        # CFBD game ids are ESPN event ids
                    g["season"],
                    g["week"],
                    g["seasonType"],
                    datetime.fromisoformat(g["startDate"]),
                    g["startTimeTBD"],
                    g["neutralSite"],
                    home_id,
                    away_id,
                    g.get("homePoints"),
                    g.get("awayPoints"),
                    g["completed"],
                ),
            )
            loaded += 1

    print(f"games {year}: {loaded} loaded, {skipped} skipped (untracked opponent)")

