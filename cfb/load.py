"""Parse raw CFBD responses (already saved in api_responses) into our tables.

Costs no API calls when the data is already saved.
"""
from datetime import datetime

from cfb import cfbd
from cfb.backfill import season_calls
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
                                   home_id, away_id, home_points, away_points, completed,
                                   home_classification, away_classification)
                VALUES ('cfb', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (league, cfbd_id) DO UPDATE SET
                    start_time          = EXCLUDED.start_time,
                    start_time_tbd      = EXCLUDED.start_time_tbd,
                    neutral_site        = EXCLUDED.neutral_site,
                    home_points         = EXCLUDED.home_points,
                    away_points         = EXCLUDED.away_points,
                    completed           = EXCLUDED.completed,
                    home_classification = EXCLUDED.home_classification,
                    away_classification = EXCLUDED.away_classification
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
                    g.get("homeClassification"),
                    g.get("awayClassification"),
                ),
            )
            loaded += 1

    print(f"games {year}: {loaded} loaded, {skipped} skipped (untracked opponent)")


def load_lines(year):
    """Insert or update every sportsbook line for one season."""
    games = cfbd.get("/lines", {"year": year, "seasonType": "both"})
    with connect() as conn:
        # Map CFBD game id -> our games.id
        game_ids = dict(
            conn.execute("SELECT cfbd_id, id FROM games WHERE league = 'cfb'").fetchall()
        )

        loaded = 0
        skipped = 0
        for g in games:
            game_id = game_ids.get(g["id"])
            if game_id is None:
                skipped += 1        # game we don't track
                continue

            # Each game has a list of lines, one per sportsbook
            for line in g["lines"]:
                conn.execute(
                    """
                    INSERT INTO lines (game_id, provider, spread, spread_open,
                                       over_under, over_under_open,
                                       home_moneyline, away_moneyline)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (game_id, provider) DO UPDATE SET
                        spread          = EXCLUDED.spread,
                        spread_open     = EXCLUDED.spread_open,
                        over_under      = EXCLUDED.over_under,
                        over_under_open = EXCLUDED.over_under_open,
                        home_moneyline  = EXCLUDED.home_moneyline,
                        away_moneyline  = EXCLUDED.away_moneyline
                    """,
                    (
                        game_id,
                        line["provider"],
                        line.get("spread"),
                        line.get("spreadOpen"),
                        line.get("overUnder"),
                        line.get("overUnderOpen"),
                        line.get("homeMoneyline"),
                        line.get("awayMoneyline"),
                    ),
                )
                loaded += 1

    print(f"lines {year}: {loaded} lines loaded, {skipped} games skipped")


def load_team_game_stats(year):
    """Insert or update each team's offensive advanced stats for every game in a season."""
    stats = cfbd.get(
        "/stats/game/advanced",
        {"year": year, "seasonType": "both", "excludeGarbageTime": True},
    )
    with connect() as conn:
        game_ids = dict(
            conn.execute("SELECT cfbd_id, id FROM games WHERE league = 'cfb'").fetchall()
        )
        # This endpoint gives team NAMES, not ids, so map school name -> our teams.id
        team_ids = dict(
            conn.execute("SELECT school, id FROM teams WHERE league = 'cfb'").fetchall()
        )

        loaded = 0
        skipped = 0
        for s in stats:
            game_id = game_ids.get(s["gameId"])
            team_id = team_ids.get(s["team"])
            opponent_id = team_ids.get(s["opponent"])
            if game_id is None or team_id is None or opponent_id is None:
                skipped += 1
                continue

            o = s["offense"]
            conn.execute(
                """
                INSERT INTO team_game_stats (
                    game_id, team_id, opponent_id, plays, drives,
                    epa_per_play, success_rate, explosiveness,
                    pass_epa, pass_success_rate, pass_explosiveness,
                    rush_epa, rush_success_rate, rush_explosiveness,
                    standard_downs_epa, passing_downs_epa,
                    line_yards, stuff_rate, power_success)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id, team_id) DO UPDATE SET
                    opponent_id        = EXCLUDED.opponent_id,
                    plays              = EXCLUDED.plays,
                    drives             = EXCLUDED.drives,
                    epa_per_play       = EXCLUDED.epa_per_play,
                    success_rate       = EXCLUDED.success_rate,
                    explosiveness      = EXCLUDED.explosiveness,
                    pass_epa           = EXCLUDED.pass_epa,
                    pass_success_rate  = EXCLUDED.pass_success_rate,
                    pass_explosiveness = EXCLUDED.pass_explosiveness,
                    rush_epa           = EXCLUDED.rush_epa,
                    rush_success_rate  = EXCLUDED.rush_success_rate,
                    rush_explosiveness = EXCLUDED.rush_explosiveness,
                    standard_downs_epa = EXCLUDED.standard_downs_epa,
                    passing_downs_epa  = EXCLUDED.passing_downs_epa,
                    line_yards         = EXCLUDED.line_yards,
                    stuff_rate         = EXCLUDED.stuff_rate,
                    power_success      = EXCLUDED.power_success
                """,
                (
                    game_id,
                    team_id,
                    opponent_id,
                    o.get("plays"),
                    o.get("drives"),
                    o.get("ppa"),
                    o.get("successRate"),
                    o.get("explosiveness"),
                    o["passingPlays"].get("ppa"),
                    o["passingPlays"].get("successRate"),
                    o["passingPlays"].get("explosiveness"),
                    o["rushingPlays"].get("ppa"),
                    o["rushingPlays"].get("successRate"),
                    o["rushingPlays"].get("explosiveness"),
                    o["standardDowns"].get("ppa"),
                    o["passingDowns"].get("ppa"),
                    o.get("lineYards"),
                    o.get("stuffRate"),
                    o.get("powerSuccess"),
                ),
            )
            loaded += 1

    print(f"team_game_stats {year}: {loaded} loaded, {skipped} skipped")


def load_season(year):
    """Load one season: teams first, then games, then everything that points to games."""
    load_teams(year)
    load_games(year)
    load_lines(year)
    load_team_game_stats(year)


# The data that changes during a season (scores, stats, betting lines)
REFRESH_ENDPOINTS = {"/games", "/stats/game/advanced", "/lines"}


def refresh_season(year):
    """Re-download this season's games, stats and lines (3 API calls), then reload them."""
    for endpoint, params in season_calls(year):
        if endpoint in REFRESH_ENDPOINTS:
            cfbd.get(endpoint, params, refresh=True)
    load_season(year)


if __name__ == "__main__":
    import sys

    for arg in sys.argv[1:]:
        load_season(int(arg))
