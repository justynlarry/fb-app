"""Who each team's quarterbacks are this season, and what losing the starter is worth.

Built from saved /games/players passing box scores (no API calls).
"""

from datetime import datetime, timezone

import pandas as pd

from cfb.db import connect
from cfb.ratings import ratings_as_of

# From the v3 backtest (2018-2025): a team starting someone other than its main QB scored
# about 0.7 points less, plus about 3.7 points per 1.0 of the team's passing EPA rating.
BASE_QB_COST = 0.7
QB_COST_PER_PASS_EPA = 3.7


def parse_attempts(c_att):
    """'17/32' -> 32 (attempts). Anything odd -> None."""
    try:
        return int(str(c_att).split("/")[1])
    except (IndexError, ValueError):
        return None


def season_passers(season):
    """One row per passer per team-game this season, from saved /games/players responses."""
    with connect() as conn:
        game_ids = dict(conn.execute("SELECT cfbd_id, id FROM games WHERE league = 'cfb'").fetchall())
        team_ids = dict(conn.execute("SELECT school, id FROM teams WHERE league = 'cfb'").fetchall())
        bodies = conn.execute(
            """
            SELECT body FROM api_responses
            WHERE endpoint = '/games/players' AND (params->>'year')::int = %s
            ORDER BY fetched_at
            """,
            (season,),
        ).fetchall()

    rows = {}
    for (body,) in bodies:
        for game in body:
            game_id = game_ids.get(game["id"])
            for team in game.get("teams", []):
                team_id = team_ids.get(team.get("team"))
                if game_id is None or team_id is None:
                    continue
                stats = {}
                for category in team.get("categories", []):
                    for stat_type in category.get("types", []):
                        for athlete in stat_type.get("athletes", []):
                            player = stats.setdefault(athlete["id"], {"name": athlete["name"]})
                            player[stat_type["name"]] = athlete["stat"]
                for passer_id, s in stats.items():
                    attempts = parse_attempts(s.get("C/ATT"))
                    if attempts:
                        # The same game appears in both teams' conference lists; the key keeps one copy
                        rows[(game_id, team_id, passer_id)] = {
                            "game_id": game_id,
                            "team_id": team_id,
                            "passer_id": passer_id,
                            "passer": s["name"],
                            "attempts": attempts,
                            "yards": float(s.get("YDS") or 0),
                        }
    return pd.DataFrame(rows.values())


def qb_out_suggestion(team_id, season):
    """Who the team's main QB is, and a suggested points change if he's out."""
    passers = season_passers(season)
    team = passers[passers["team_id"] == team_id] if len(passers) else passers
    if team.empty:
        return None

    totals = team.groupby(["passer_id", "passer"]).agg(
        attempts=("attempts", "sum"), yards=("yards", "sum"), games=("game_id", "nunique")
    ).reset_index().sort_values("attempts", ascending=False)
    totals["ypa"] = totals["yards"] / totals["attempts"]
    starter = totals.iloc[0]
    backup = totals.iloc[1] if len(totals) > 1 else None

    ratings, _ = ratings_as_of(season, datetime.now(timezone.utc))
    pass_epa = float(ratings.at[team_id, "off_pass_epa"]) if team_id in ratings.index else 0.0
    suggested = -(BASE_QB_COST + QB_COST_PER_PASS_EPA * max(0.0, pass_epa))

    return {
        "qb": starter["passer"],
        "qb_attempts": int(starter["attempts"]),
        "qb_share": round(float(starter["attempts"] / totals["attempts"].sum()), 2),
        "qb_ypa": round(float(starter["ypa"]), 1),
        "backup": None if backup is None else backup["passer"],
        "backup_attempts": 0 if backup is None else int(backup["attempts"]),
        "backup_ypa": None if backup is None else round(float(backup["ypa"]), 1),
        "team_pass_epa": round(pass_epa, 3),
        "suggested_points": round(suggested * 2) / 2,     # nearest half point
    }
