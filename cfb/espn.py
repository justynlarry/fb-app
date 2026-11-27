"""Live scores from ESPN's public scoreboard feed.

ESPN doesn't document this feed and can change it without notice, so every
field is read with .get() and one strange game never stops the rest.
For college football, ESPN's event and team ids are the same as CFBD's.
For the NFL, ESPN is also the schedule source: each poll adds or updates
that week's teams and games (sync_schedule).  ESPN reuses id numbers across
leagues, so every lookup is by (league, espn_id).
"""

from datetime import datetime

import httpx

from cfb.db import connect

# One ESPN scoreboard per league.  "groups": 80 = all FBS games; the NFL feed needs no filter.
SCOREBOARDS = {
    "cfb": ("https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard",
            {"groups": 80, "limit": 300}),
    "nfl": ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
            {}),
}
LEAGUES = ("cfb", "nfl")
SCHEDULE_FROM_ESPN = ("nfl",)       # leagues whose teams/games come from ESPN (college uses CFBD)
SEASON_TYPES = {1: "preseason", 2: "regular", 3: "postseason"}  # ESPN's season "type" codes

# ESPN numbers NFL playoff weeks 1-5; nflverse (our schedule of record) numbers them 19-22.
# ESPN's week 4 is the Pro Bowl, which we don't store.
NFL_PLAYOFF_WEEKS = {1: 19, 2: 20, 3: 21, 5: 22}   # wild card, divisional, conference, Super Bowl


def fetch_scoreboard(league, week=None, season_type=None):
    """Download one league's scoreboard from ESPN: this week's, or a given week.
    season_type uses ESPN's numbers: 2 = regular season, 3 = postseason."""
    url, params = SCOREBOARDS[league]
    params = dict(params)          # a copy, so the shared defaults never change
    if week is not None:
        params["week"] = week
        params["seasontype"] = season_type
    resp = httpx.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def parse_time(value):
    """ESPN's '2026-11-15T18:00Z' as a UTC datetime.  Missing or odd becomes None."""
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def to_int(value):
    """Turn '7' or 7 into 7.  Anything missing or odd becomes None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def team_rank(side):
    """Poll ranking 1-25, or None.  ESPN uses 99 for unranked."""
    rank = to_int(side.get("curatedRank", {}).get("current"))
    if rank is None or rank > 25:
        return None
    return rank


def team_record(side, record_type):
    """Record summary like '7-2'.  record_type: 'total' (overall) or 'vsconf' (conference)."""
    for record in side.get("records", []):
        if record.get("type") == record_type:
            return record.get("summary")
    return None


def team_info(side):
    """The team fields we store, from one competitor."""
    team = side.get("team", {})
    return {
        "espn_id": to_int(team.get("id")),
        "name": team.get("displayName"),            # 'Detroit Lions'
        "mascot": team.get("name"),                 # 'Lions'
        "abbreviation": team.get("abbreviation"),   # 'DET'
    }


def broadcast_list(comp):
    """TV / streaming networks for one game as [(market, network), ...], e.g. [('national', 'ABC')].
    Anything missing or oddly shaped is skipped, so a strange broadcast entry never costs us the score."""
    pairs = []
    for b in comp.get("broadcasts") or []:
        if not isinstance(b, dict):
            continue
        market = str(b.get("market") or "unknown")
        for name in b.get("names") or []:
            if isinstance(name, str) and name:
                pairs.append((market, name))
    return pairs


def parse_event(event):
    """Turn one ESPN event into a flat dict of the fields we store."""
    comp = event["competitions"][0]
    status = event.get("status", {})
    status_type = status.get("type", {})
    situation = comp.get("situation", {})       # Only present while a game is live
    odds = (comp.get("odds") or [{}])[0]        # Only present before kickoff

    # Competitors is a list of two teams.  Index them by 'home' / 'away'
    sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    home = sides.get("home", {})
    away = sides.get("away", {})

    return {
        "espn_id": to_int(event.get("id")),
        "start_time": parse_time(event.get("date")),
        "time_valid": comp.get("timeValid", True),      # False while the kickoff is TBD
        "completed": status_type.get("completed", False),   # True only for a real final
        "season": event.get("season", {}).get("year"),
        "season_type": SEASON_TYPES.get(event.get("season", {}).get("type")),
        "week": event.get("week", {}).get("number"),
        "neutral_site": comp.get("neutralSite", False),
        "broadcasts": broadcast_list(comp),
        "home_team": team_info(home),
        "away_team": team_info(away),
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
        "spread": odds.get("spread"),
        "over_under": odds.get("overUnder"),
        "odds_details": odds.get("details"),
        "away_rank": team_rank(away),
        "home_rank": team_rank(home),
        "away_record": team_record(away, "total"),
        "home_record": team_record(home, "total"),
        "away_conf_record": team_record(away, "vsconf"),
        "home_conf_record": team_record(home, "vsconf"),
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


def schedule_week(league, g):
    """The week number we store.  NFL playoff weeks are renumbered to match nflverse."""
    if league == "nfl" and g["season_type"] == "postseason":
        return NFL_PLAYOFF_WEEKS.get(g["week"])     # None for the Pro Bowl
    return g["week"]


def sync_schedule(league, games):
    """Add or update this week's teams and games from ESPN (leagues in SCHEDULE_FROM_ESPN)."""
    with connect() as conn:
        for g in games:
            home, away = g["home_team"], g["away_team"]
            week = schedule_week(league, g)
            needed = (g["espn_id"], g["start_time"], g["season"], week, g["season_type"],
                      home["espn_id"], home["name"], away["espn_id"], away["name"])
            if None in needed:
                print(f"ESPN: {league} game {g['espn_id']} is missing schedule fields, skipping")
                continue

            team_ids = {}
            for side, t in (("home", home), ("away", away)):
                row = conn.execute(
                    """
                    INSERT INTO teams (league, espn_id, school, mascot, abbreviation)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (league, espn_id) DO UPDATE SET
                        school       = EXCLUDED.school,
                        mascot       = EXCLUDED.mascot,
                        abbreviation = EXCLUDED.abbreviation
                    RETURNING id
                    """,
                    (league, t["espn_id"], t["name"], t["mascot"], t["abbreviation"]),
                ).fetchone()
                team_ids[side] = row[0]

            # Final scores go in games only once ESPN says the game is over (not postponed);
            # live scores stay in live_scores.
            done = g["completed"]
            conn.execute(
                """
                INSERT INTO games (league, espn_id, season, week, season_type, start_time,
                                   start_time_tbd, neutral_site, home_id, away_id,
                                   home_points, away_points, completed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (league, espn_id) DO UPDATE SET
                    season         = EXCLUDED.season,
                    week           = EXCLUDED.week,
                    season_type    = EXCLUDED.season_type,
                    start_time     = EXCLUDED.start_time,
                    start_time_tbd = EXCLUDED.start_time_tbd,
                    neutral_site   = EXCLUDED.neutral_site,
                    home_id        = EXCLUDED.home_id,
                    away_id        = EXCLUDED.away_id,
                    home_points    = EXCLUDED.home_points,
                    away_points    = EXCLUDED.away_points,
                    completed      = EXCLUDED.completed
                """,
                (league, g["espn_id"], g["season"], week, g["season_type"], g["start_time"],
                 not g["time_valid"], g["neutral_site"], team_ids["home"], team_ids["away"],
                 g["home_score"] if done else None, g["away_score"] if done else None, done),
            )


def save_live_scores(league, games):
    """Insert or update one live_scores row per game.  Returns how many were saved."""
    with connect() as conn:
        # ESPN id -> our id, for games and for teams (possession)
        game_ids = dict(
            conn.execute(
                "SELECT espn_id, id FROM games WHERE league = %s AND espn_id IS NOT NULL",
                (league,),
            ).fetchall()
        )
        team_ids = dict(
            conn.execute(
                "SELECT espn_id, id FROM teams WHERE league = %s AND espn_id IS NOT NULL",
                (league,),
            ).fetchall()
        )

        saved = 0
        for g in games:
            game_id = game_ids.get(g["espn_id"])
            if game_id is None:
                print(f"ESPN: {league} game {g['espn_id']} isn't in our games table, skipping")
                continue

            conn.execute(
                """
                INSERT INTO live_scores (game_id, state, status_detail, period, clock,
                                         home_score, away_score, possession_team_id,
                                         home_timeouts, away_timeouts, down_distance,
                                         spread, over_under, odds_details,
                                         away_rank, home_rank, away_record, home_record,
                                         away_conf_record, home_conf_record)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    -- ESPN drops the odds at kickoff; COALESCE keeps the last line we saw.
                    spread             = COALESCE(EXCLUDED.spread, live_scores.spread),
                    over_under         = COALESCE(EXCLUDED.over_under, live_scores.over_under),
                    odds_details       = COALESCE(EXCLUDED.odds_details, live_scores.odds_details),
                    away_rank          = EXCLUDED.away_rank,
                    home_rank          = EXCLUDED.home_rank,
                    away_record        = COALESCE(EXCLUDED.away_record, live_scores.away_record),
                    home_record        = COALESCE(EXCLUDED.home_record, live_scores.home_record),
                    away_conf_record   = COALESCE(EXCLUDED.away_conf_record, live_scores.away_conf_record),
                    home_conf_record   = COALESCE(EXCLUDED.home_conf_record, live_scores.home_conf_record),
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
                    g["spread"],
                    g["over_under"],
                    g["odds_details"],
                    g["away_rank"],
                    g["home_rank"],
                    g["away_record"],
                    g["home_record"],
                    g["away_conf_record"],
                    g["home_conf_record"],
                ),
            )
            saved += 1
    return saved


def save_broadcasts(league, games):
    """Record each game's TV / streaming networks in game_broadcasts.  A network we've seen before
    only gets its last_seen moved forward, so first_seen keeps when we first knew it.
    Returns how many (game, network) rows were saved."""
    with connect() as conn:
        game_ids = dict(
            conn.execute(
                "SELECT espn_id, id FROM games WHERE league = %s AND espn_id IS NOT NULL",
                (league,),
            ).fetchall()
        )
        saved = 0
        for g in games:
            game_id = game_ids.get(g["espn_id"])
            if game_id is None:
                continue        # save_live_scores already reports games we don't have
            for market, network in g["broadcasts"]:
                conn.execute(
                    """
                    INSERT INTO game_broadcasts (game_id, market, network)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (game_id, market, network) DO UPDATE SET last_seen = now()
                    """,
                    (game_id, market, network),
                )
                saved += 1
        return saved


def update_start_times(league, games):
    """Move kickoffs that ESPN has changed since CFBD's 5 AM refresh.  Returns how many moved."""
    moved = 0
    with connect() as conn:
        for g in games:
            # Only games that haven't started, with a real time (not TBD)
            if g["state"] != "pre" or g["start_time"] is None or not g["time_valid"]:
                continue
            row = conn.execute(
                """
                UPDATE games
                SET start_time = %s, start_time_tbd = false
                WHERE league = %s
                  AND espn_id = %s
                  AND (start_time <> %s OR start_time_tbd)
                RETURNING id
                """,
                (g["start_time"], league, g["espn_id"], g["start_time"]),
            ).fetchone()
            if row:
                print(f"ESPN: {league} game {row[0]} kickoff moved to {g['start_time']:%Y-%m-%d %H:%M} UTC")
                moved += 1
    return moved


def save_final_scores(league, games):
    """Copy ESPN's final scores into games as soon as a game ends.  Returns how many were new.

    College games come from CFBD, which fills in final scores only at the 5 AM refresh.
    Saving ESPN's final right away lets the Results page grade picks that night.
    The 5 AM refresh still overwrites these with CFBD's numbers.
    (NFL finals are already saved by sync_schedule.)
    """
    saved = 0
    with connect() as conn:
        for g in games:
            # Only real finals (not postponed games) with both scores
            if not g["completed"] or g["home_score"] is None or g["away_score"] is None:
                continue
            row = conn.execute(
                """
                UPDATE games
                SET home_points = %s, away_points = %s, completed = true
                WHERE league = %s
                  AND espn_id = %s
                  AND (NOT completed OR home_points IS NULL OR away_points IS NULL)
                RETURNING id
                """,
                (g["home_score"], g["away_score"], league, g["espn_id"]),
            ).fetchone()
            if row:
                print(f"ESPN: {league} game {row[0]} final {g['away_score']}-{g['home_score']} saved")
                saved += 1
    return saved


def poll():
    """One poll of every league: fetch, parse, save.  Returns how many games are live right now."""
    live = 0
    for league in LEAGUES:
        try:
            games = parse_scoreboard(fetch_scoreboard(league))
            if league in SCHEDULE_FROM_ESPN:
                sync_schedule(league, games)
            else:
                save_final_scores(league, games)
            saved = save_live_scores(league, games)
            update_start_times(league, games)
            try:
                save_broadcasts(league, games)
            except Exception as err:
                # A broadcast problem must never cost us the scores, which are already saved above
                print(f"ESPN {league} broadcasts failed: {err!r}")
        except Exception as err:
            # One league's feed failing must not stop the other
            print(f"ESPN {league} poll failed: {err!r}")
            continue
        league_live = sum(1 for g in games if g["state"] == "in")
        print(f"ESPN {league} poll: {saved} saved, {league_live} live")
        live += league_live
    return live
