"""Live scores from ESPN's public scoreboard feed.

ESPN doesn't document this feed and can change it without notice, so every
field is read with .get() and one strange game never stops the rest.
For college football, ESPN's event and team ids are the same as CFBD's.
"""

import httpx

from cfb.db import connect

SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
)
FBS_GROUP = 80      # ESPN's code for "all FBS games"


def fetch_scoreboard():
    """Download this week's FBS scoreboard from ESPN."""
    resp = httpx.get(SCOREBOARD_URL, params={"groups": FBS_GROUP, "limit": 300}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def to_int(value):
    """Turn '7' or 7 into 7.  Anything missing or odd becomes None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_event(event):
    """Turn one ESPN event into a flat dict of the fields we store."""
    comp = event["competitions"][0]
    status = event.get("status", {})
    status_type = status.get("type", {})
    situation = comp.get("situation", {})       # Only present while a game is live

    # Competitors is a list of two teams.  Index them by 'home' / 'away'
    sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    home = sides.get("home", {})
    away = sides.get("away", {})

    return {
        "espn_id": to_int(event.get("id")),
        "state": status_type.get("state"),              # 'pre', 'in', 'post'
        "status_detail": status_type.get("shortDetail"),
        "period": status.get("period"),
        "clock": status.get("displayClock"),
        "home_score": to_int(home.get("score")),
        "away_score": to_int(away.get("score")),
        "possession_espn_id": to_int(situation.get("possession")),
        "home_timeouts": situation.get("homeTimeouts"),
        "away_timeouts": situation.get("awayTimeouts"),
        "down_distance": situation.get("downDistanceText"),
    }


def parse_scoreboard(data):
    """Parse every event, skipping (and reporting) any that ESPN sent in a strange shape."""
    games = []
    for event in data.get("events", []):
        try:
            games.append(parse_event(event))
        except (KeyError, IndexError, TypeError) as err:
            print(f"ESPN: couldn't parse event {event.get('id')}: {err!r}")
    return games


def save_live_scores(games):
    """Insert or update one live_scores row per game.  Returns how many were saved."""
    with connect() as conn:
        # ESPN id -> our id, for games and for teams (possession)
        game_ids = dict(
            conn.execute(
                "SELECT espn_id, id FROM games WHERE league = 'cfb' AND espn_id IS NOT NULL"
            ).fetchall()
        )
        team_ids = dict(
            conn.execute(
                "SELECT espn_id, id FROM teams WHERE league = 'cfb' AND espn_id IS NOT NULL"
            ).fetchall()
        )

        saved = 0
        for g in games:
            game_id = game_ids.get(g["espn_id"])
            if game_id is None:
                print(f"ESPN: game {g['espn_id']} isn't in our games table, skipping")
                continue

            conn.execute(
                """
                INSERT INTO live_scores (game_id, state, status_detail, period, clock,
                                         home_score, away_score, possession_team_id,
                                         home_timeouts, away_timeouts, down_distance)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id) DO UPDATE SET
                    state              = EXCLUDED.state,
                    status_detail      = EXCLUDED.status_detail,
                    period             = EXCLUDED.period,
                    clock              = EXCLUDED.clock,
                    home_score         = EXCLUDED.home_score,
                    away_score         = EXCLUDED.away_score,
                    possession_team_id = EXCLUDED.possession_team_id,
                    home_timeouts      = EXCLUDED.home_timeouts,
                    away_timeouts      = EXCLUDED.away_timeouts,
                    down_distance      = EXCLUDED.down_distance,
                    updated_at         = now()
                """,
                (
                    game_id,
                    g["state"],
                    g["status_detail"],
                    g["period"],
                    g["clock"],
                    g["home_score"],
                    g["away_score"],
                    team_ids.get(g["possession_espn_id"]),   # None if nobody has it
                    g["home_timeouts"],
                    g["away_timeouts"],
                    g["down_distance"],
                ),
            )
            saved += 1
    return saved


def poll():
    """One poll: fetch, parse, save.  Returns how many games are live right now."""
    games = parse_scoreboard(fetch_scoreboard())
    saved = save_live_scores(games)
    live = sum(1 for g in games if g["state"] == "in")
    print(f"ESPN poll: {saved} saved, {live} live")
    return live
