"""NFL backfill from nflverse (free files on GitHub, no API key, no quota).

    python -m cfb.nflverse 2016-2025          (or single years: 2024 2025)

For each season:
  1. teams:     all 32 from ESPN's team list (same ids and names the live poller uses)
  2. games:     nflverse schedule -> games (matched to ESPN by ESPN's game id), final scores
  3. lines:     nflverse closing spread/total -> lines (provider 'nflverse'), for evaluation only
  4. stats:     nflverse play-by-play -> team_game_stats (EPA/play, success, explosiveness),
                garbage time removed with a win-probability filter

Files are re-downloadable at any time, so nothing raw is kept. Re-running a season updates it
in place (every insert is an upsert), which is also how to refresh the current season.
"""

import csv
import io
import os
import sys
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pandas as pd

from cfb.db import connect

LEAGUE = "nfl"
SCHEDULE_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"

# nflverse uses the team's abbreviation at the time; ESPN keeps one id per franchise
NFLVERSE_TO_ESPN = {"LA": "LAR", "OAK": "LV", "SD": "LAC", "WAS": "WSH"}

# nflverse game times are US Eastern
EASTERN = ZoneInfo("America/New_York")

# Garbage time: drop plays when one team's win probability is below 5% or above 95%
WP_MIN = 0.05
WP_MAX = 0.95

# Only the play-by-play columns we use (the files have ~370)
PBP_COLUMNS = ["game_id", "posteam", "pass", "rush", "epa", "success", "wp",
               "down", "ydstogo", "drive", "two_point_attempt",
               "qb_dropback", "passer_player_id", "rusher_player_id"]


def to_int(value):
    """'7' -> 7; '' or anything odd -> None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value):
    """'2.5' -> 2.5; '' or anything odd -> None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def download(url):
    """GET a URL (following GitHub's redirects) and return the response."""
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    return resp


# ---------- 1. Teams ----------

def load_teams(conn):
    """Insert or update all 32 NFL teams from ESPN.  Returns {ESPN abbreviation: our team id}."""
    data = download(ESPN_TEAMS_URL).json()
    teams = data["sports"][0]["leagues"][0]["teams"]
    ids = {}
    for entry in teams:
        t = entry["team"]
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
            (LEAGUE, to_int(t["id"]), t["displayName"], t.get("name"), t["abbreviation"]),
        ).fetchone()
        ids[t["abbreviation"]] = row[0]
    print(f"teams: {len(ids)} loaded")
    return ids


def team_id(team_ids, nflverse_abbr):
    """Our team id for an nflverse abbreviation such as 'OAK' (-> Raiders)."""
    return team_ids[NFLVERSE_TO_ESPN.get(nflverse_abbr, nflverse_abbr)]


# ---------- 2 and 3. Games and closing lines ----------

def fetch_schedule():
    """The whole nflverse schedule (1999 to now) as a list of dicts, one per game."""
    text = download(SCHEDULE_URL).text
    return list(csv.DictReader(io.StringIO(text)))


def kickoff_utc(row):
    """Kickoff as a UTC-aware datetime, and whether the time is still TBD."""
    if row["gametime"]:
        local = datetime.strptime(f"{row['gameday']} {row['gametime']}", "%Y-%m-%d %H:%M")
        tbd = False
    else:
        local = datetime.strptime(f"{row['gameday']} 13:00", "%Y-%m-%d %H:%M")
        tbd = True
    return local.replace(tzinfo=EASTERN), tbd


def load_games(conn, season, schedule, team_ids):
    """Insert or update one season's games and closing lines.

    Returns {nflverse game_id: our game id}, used to match the play-by-play.
    """
    game_ids = {}
    skipped = 0
    lines = 0
    for row in schedule:
        if row["season"] != str(season):
            continue
        espn_id = to_int(row["espn"])
        if espn_id is None:
            skipped += 1
            continue

        start, tbd = kickoff_utc(row)
        home_points = to_int(row["home_score"])
        away_points = to_int(row["away_score"])
        completed = home_points is not None and away_points is not None
        season_type = "regular" if row["game_type"] == "REG" else "postseason"

        game_id = conn.execute(
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
            RETURNING id
            """,
            (LEAGUE, espn_id, season, int(row["week"]), season_type, start, tbd,
             row["location"] == "Neutral",
             team_id(team_ids, row["home_team"]), team_id(team_ids, row["away_team"]),
             home_points, away_points, completed),
        ).fetchone()[0]
        game_ids[row["game_id"]] = game_id

        # nflverse spread_line is the home team's expected margin (+3 = home favored by 3).
        # Our lines use the home-side spread (-3 = home favored by 3), so flip the sign.
        spread_line = to_float(row["spread_line"])
        total_line = to_float(row["total_line"])
        if spread_line is not None or total_line is not None:
            conn.execute(
                """
                INSERT INTO lines (game_id, provider, spread, over_under, home_moneyline, away_moneyline)
                VALUES (%s, 'nflverse', %s, %s, %s, %s)
                ON CONFLICT (game_id, provider) DO UPDATE SET
                    spread         = EXCLUDED.spread,
                    over_under     = EXCLUDED.over_under,
                    home_moneyline = EXCLUDED.home_moneyline,
                    away_moneyline = EXCLUDED.away_moneyline
                """,
                (game_id, -spread_line if spread_line is not None else None, total_line,
                 to_int(row["home_moneyline"]), to_int(row["away_moneyline"])),
            )
            lines += 1

    print(f"games {season}: {len(game_ids)} loaded, {lines} lines, {skipped} skipped (no ESPN id)")
    return game_ids


def whole(value):
    """'62', '62.0' -> 62;  '' or anything odd -> None."""
    number = to_float(value)
    return None if number is None else round(number)


def save_schedule_info(conn, season, schedule, game_ids):
    """Save today's copy of the nflverse schedule columns we don't keep in games (nfl_schedule_info),
    one row per game per load day.  Returns how many rows were saved."""
    as_of = datetime.now(ZoneInfo(os.environ.get("TZ", "America/Denver"))).date()
    saved = 0
    for row in schedule:
        if row["season"] != str(season):
            continue
        game_id = game_ids.get(row["game_id"])
        if game_id is None:
            continue        # load_games skipped it (no ESPN id)
        div = to_int(row["div_game"])
        conn.execute(
            """
            INSERT INTO nfl_schedule_info (game_id, as_of, div_game, away_rest, home_rest,
                                           roof, surface, temp, wind, stadium_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (game_id, as_of) DO UPDATE SET
                div_game   = EXCLUDED.div_game,
                away_rest  = EXCLUDED.away_rest,
                home_rest  = EXCLUDED.home_rest,
                roof       = EXCLUDED.roof,
                surface    = EXCLUDED.surface,
                temp       = EXCLUDED.temp,
                wind       = EXCLUDED.wind,
                stadium_id = EXCLUDED.stadium_id,
                fetched_at = now()
            """,
            (game_id, as_of, None if div is None else div == 1,
             to_int(row["away_rest"]), to_int(row["home_rest"]),
             row["roof"] or None, row["surface"] or None,
             whole(row["temp"]), whole(row["wind"]), row["stadium_id"] or None),
        )
        saved += 1
    print(f"{season}: {saved} schedule-info rows saved as of {as_of}")
    return saved


# ---------- 4. Team-game stats from play-by-play ----------

def avg(series):
    """Mean of a column as a float, or None if there are no rows (never NaN)."""
    if len(series) == 0:
        return None
    return float(series.mean())


def explosiveness(plays):
    """Average EPA on successful plays (same idea as CFBD's explosiveness)."""
    return avg(plays.loc[plays["success"] == 1, "epa"])


def team_game_stats(plays):
    """One team's offensive numbers in one game, from its scrimmage plays."""
    passes = plays[plays["pass"] == 1]
    rushes = plays[plays["rush"] == 1]
    # Passing downs (CFBD's definition): 2nd and 8+, or 3rd/4th and 5+
    passing_down = (((plays["down"] == 2) & (plays["ydstogo"] >= 8))
                    | ((plays["down"] >= 3) & (plays["ydstogo"] >= 5)))
    return {
        "plays": len(plays),
        "drives": int(plays["drive"].nunique()),
        "epa_per_play": avg(plays["epa"]),
        "success_rate": avg(plays["success"]),
        "explosiveness": explosiveness(plays),
        "pass_epa": avg(passes["epa"]),
        "pass_success_rate": avg(passes["success"]),
        "pass_explosiveness": explosiveness(passes),
        "rush_epa": avg(rushes["epa"]),
        "rush_success_rate": avg(rushes["success"]),
        "rush_explosiveness": explosiveness(rushes),
        "standard_downs_epa": avg(plays.loc[~passing_down, "epa"]),
        "passing_downs_epa": avg(plays.loc[passing_down, "epa"]),
    }


def scrimmage_plays(season):
    """Download one season's play-by-play and keep the non-garbage-time pass and rush plays."""
    with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
        tmp.write(download(PBP_URL.format(season=season)).content)
        tmp.flush()
        df = pd.read_parquet(tmp.name, columns=PBP_COLUMNS)

    is_scrimmage = (df["pass"] == 1) | (df["rush"] == 1)
    keep = (is_scrimmage
            & df["epa"].notna()
            & df["posteam"].notna()
            & (df["two_point_attempt"] != 1)
            & df["wp"].between(WP_MIN, WP_MAX))
    print(f"play-by-play {season}: {len(df)} rows, {int(keep.sum())} scrimmage plays kept "
          f"({int((is_scrimmage & ~keep).sum())} dropped: garbage time, 2-pt tries or no EPA)")
    return df[keep]


def load_stats(conn, season, game_ids, team_ids, plays):
    """Insert or update team_game_stats for one season (one row per team per game)."""
    # Each game's two teams, from its nflverse id: {game_id: (home abbr, away abbr)}
    teams_in_game = {}
    for gid in plays["game_id"].unique():
        parts = gid.split("_")             # '2025_01_DAL_PHI' -> away DAL, home PHI
        teams_in_game[gid] = (parts[3], parts[2])

    saved = 0
    missing = set()
    for (gid, posteam), team_plays in plays.groupby(["game_id", "posteam"]):
        game_id = game_ids.get(gid)
        if game_id is None:
            missing.add(gid)
            continue
        # Compare our team ids, not abbreviations: in old seasons the game id says 'OAK'/'SD'
        # while the play-by-play says 'LV'/'LAC' for the same team.
        home, away = teams_in_game[gid]
        offense_id = team_id(team_ids, posteam)
        home_id, away_id = team_id(team_ids, home), team_id(team_ids, away)
        if offense_id not in (home_id, away_id):
            print(f"team_game_stats {season}: {posteam} isn't in game {gid}, skipping")
            continue
        opponent_id = away_id if offense_id == home_id else home_id
        s = team_game_stats(team_plays)
        conn.execute(
            """
            INSERT INTO team_game_stats (game_id, team_id, opponent_id, plays, drives,
                epa_per_play, success_rate, explosiveness,
                pass_epa, pass_success_rate, pass_explosiveness,
                rush_epa, rush_success_rate, rush_explosiveness,
                standard_downs_epa, passing_downs_epa)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                passing_downs_epa  = EXCLUDED.passing_downs_epa
            """,
            (game_id, offense_id, opponent_id,
             s["plays"], s["drives"], s["epa_per_play"], s["success_rate"], s["explosiveness"],
             s["pass_epa"], s["pass_success_rate"], s["pass_explosiveness"],
             s["rush_epa"], s["rush_success_rate"], s["rush_explosiveness"],
             s["standard_downs_epa"], s["passing_downs_epa"]),
        )
        saved += 1
    print(f"team_game_stats {season}: {saved} loaded"
          + (f", {len(missing)} games not in the schedule: {sorted(missing)[:3]}" if missing else ""))


# ---------- 5. Quarterbacks (for the nfl-v2 QB adjustment) ----------

def save_starters(conn, season, schedule, game_ids, team_ids):
    """Each game's two starting QBs, from the nflverse schedule (known once the game is played)."""
    saved = 0
    for row in schedule:
        if row["season"] != str(season) or row["game_id"] not in game_ids:
            continue
        for side in ("home", "away"):
            qb_id = row[side + "_qb_id"]
            if not qb_id:
                continue        # a future game: no starter yet
            conn.execute(
                """
                INSERT INTO nfl_starters (game_id, team_id, qb_id, qb_name, source)
                VALUES (%s, %s, %s, %s, 'nflverse')
                ON CONFLICT (game_id, team_id) DO UPDATE SET
                    qb_id   = EXCLUDED.qb_id,
                    qb_name = EXCLUDED.qb_name,
                    source  = 'nflverse'
                """,
                (game_ids[row["game_id"]], team_id(team_ids, row[side + "_team"]),
                 qb_id, row[side + "_qb_name"]),
            )
            saved += 1
    print(f"starters {season}: {saved} saved")


def save_qb_games(conn, season, plays, game_ids, team_ids):
    """Every QB's dropbacks and total EPA in each game (same plays as team_game_stats)."""
    dropbacks = plays[plays["qb_dropback"] == 1].copy()
    dropbacks["qb_id"] = dropbacks["passer_player_id"].fillna(dropbacks["rusher_player_id"])
    dropbacks = dropbacks.dropna(subset=["qb_id"])
    saved = 0
    for (gid, posteam, qb_id), qb_plays in dropbacks.groupby(["game_id", "posteam", "qb_id"]):
        game_id = game_ids.get(gid)
        if game_id is None:
            continue
        conn.execute(
            """
            INSERT INTO nfl_qb_games (game_id, team_id, qb_id, dropbacks, epa)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (game_id, team_id, qb_id) DO UPDATE SET
                dropbacks = EXCLUDED.dropbacks,
                epa       = EXCLUDED.epa
            """,
            (game_id, team_id(team_ids, posteam), qb_id, len(qb_plays), float(qb_plays["epa"].sum())),
        )
        saved += 1
    print(f"qb games {season}: {saved} saved")


# ---------- Command line ----------

def parse_seasons(args):
    """['2016-2018', '2025'] -> [2016, 2017, 2018, 2025]"""
    seasons = []
    for arg in args:
        if "-" in arg:
            first, last = arg.split("-")
            seasons.extend(range(int(first), int(last) + 1))
        else:
            seasons.append(int(arg))
    return seasons


def load_seasons(seasons):
    """Load or refresh these NFL seasons: teams, games, lines, team stats, starters, QB games."""
    schedule = fetch_schedule()
    print(f"schedule: {len(schedule)} games in the nflverse file")
    with connect() as conn:
        team_ids = load_teams(conn)
        conn.commit()

    for season in seasons:
        # One transaction per season:  a failure part-way leaves earlier seasons saved
        with connect() as conn:
            game_ids = load_games(conn, season, schedule, team_ids)
            save_schedule_info(conn, season, schedule, game_ids)
            plays = scrimmage_plays(season)
            load_stats(conn, season, game_ids, team_ids, plays)
            save_starters(conn, season, schedule, game_ids, team_ids)
            save_qb_games(conn, season, plays, game_ids, team_ids)
            conn.commit()


def main():
    seasons = parse_seasons(sys.argv[1:])
    if not seasons:
        print("usage: python -m cfb.nflverse 2016-2025   (or single years)")
        sys.exit(1)
    load_seasons(seasons)


if __name__ == "__main__":
    main()
