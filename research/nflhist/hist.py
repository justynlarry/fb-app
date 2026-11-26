"""NFL 1999-2025 rebuilt from nflverse files, in memory only (Stage 1 of nfl-v3-wk / nfl-v3-ss, model-tests.md s9).
Kept in research/nflhist (2026-11-25). Run inside the worker: cat hist.py checks.py | docker compose exec -T worker python -

Same parsing as cfb/nflverse.py (scrimmage_plays, team_game_stats, starters, QB dropbacks), but nothing is written
to the database.  patch(first, last) swaps the five DB readers used by ratings / nfl_model / nfl_qbs for in-memory
versions, so the app's own model code runs unchanged on the rebuilt data.
Cache: processed tables in /tmp/nflhist inside the container (re-downloadable).
"""
import csv, io, os, time
import pandas as pd

from cfb import nflverse as nv
from cfb import ratings, nfl_model, nfl_qbs
from cfb.db import connect

CACHE = "/tmp/nflhist"
# Schedule abbreviations of the time -> ESPN's (nflverse.py's map plus the St. Louis Rams, 1999-2015)
ABBR = dict(nv.NFLVERSE_TO_ESPN, STL="LAR")


def team_ids():
    with connect() as conn:
        return {a: i for a, i in conn.execute("SELECT abbreviation, id FROM teams WHERE league = 'nfl'").fetchall()}


def tid(ids, abbr):
    return ids[ABBR.get(abbr, abbr)]


def build(first=1999, last=2025):
    """Download and process every season; cache games / stats / starters / qb_games as parquet."""
    os.makedirs(CACHE, exist_ok=True)
    if os.path.exists(f"{CACHE}/games.parquet"):
        return
    ids = team_ids()
    sched = list(csv.DictReader(io.StringIO(nv.download(nv.SCHEDULE_URL).text)))
    games, stats, starters, qbg = [], [], [], []
    next_id = 1
    gid_map = {}
    for row in sched:
        s = int(row["season"])
        if not first <= s <= last:
            continue
        hp, ap = nv.to_int(row["home_score"]), nv.to_int(row["away_score"])
        start, _ = nv.kickoff_utc(row)
        gid_map[row["game_id"]] = next_id
        games.append({"game_id": next_id, "nflverse_id": row["game_id"], "espn_id": nv.to_int(row["espn"]),
                      "season": s, "week": int(row["week"]),
                      "season_type": "regular" if row["game_type"] == "REG" else "postseason",
                      "start_time": pd.Timestamp(start).tz_convert("UTC"),
                      "neutral_site": row["location"] == "Neutral",
                      "home_id": tid(ids, row["home_team"]), "away_id": tid(ids, row["away_team"]),
                      "home_points": hp, "away_points": ap,
                      "close_spread": -nv.to_float(row["spread_line"]) if nv.to_float(row["spread_line"]) is not None else None,
                      "close_total": nv.to_float(row["total_line"])})
        for side in ("home", "away"):
            if row[side + "_qb_id"]:
                starters.append({"game_id": next_id, "team_id": tid(ids, row[side + "_team"]), "qb_id": row[side + "_qb_id"]})
        next_id += 1
    games = pd.DataFrame(games)
    for season in range(first, last + 1):
        t0 = time.time()
        plays = nv.scrimmage_plays(season)
        for (g, pos), tp in plays.groupby(["game_id", "posteam"]):
            gid = gid_map.get(g)
            if gid is None:
                continue
            parts = g.split("_")
            home, away = tid(ids, parts[3]), tid(ids, parts[2])
            off = tid(ids, pos)
            if off not in (home, away):
                print("  team not in game", g, pos)
                continue
            st = nv.team_game_stats(tp)
            stats.append({"game_id": gid, "team_id": off, "opponent_id": away if off == home else home,
                          "plays": st["plays"], **{m: st[m] for m in ["epa_per_play", "success_rate",
                          "explosiveness", "pass_epa", "rush_epa"]}})
        db = plays[plays["qb_dropback"] == 1].copy()
        db["qb_id"] = db["passer_player_id"].fillna(db["rusher_player_id"])
        db = db.dropna(subset=["qb_id"])
        for (g, pos, q), qp in db.groupby(["game_id", "posteam", "qb_id"]):
            gid = gid_map.get(g)
            if gid is not None:
                qbg.append({"game_id": gid, "team_id": tid(ids, pos), "qb_id": q,
                            "dropbacks": len(qp), "epa": float(qp["epa"].sum())})
        print(f"  {season} processed in {time.time() - t0:.0f}s")
    games.to_parquet(f"{CACHE}/games.parquet")
    pd.DataFrame(stats).to_parquet(f"{CACHE}/stats.parquet")
    pd.DataFrame(starters).to_parquet(f"{CACHE}/starters.parquet")
    pd.DataFrame(qbg).to_parquet(f"{CACHE}/qb_games.parquet")


def load():
    return {n: pd.read_parquet(f"{CACHE}/{n}.parquet") for n in ("games", "stats", "starters", "qb_games")}


def patch(first, last, espn_only=False):
    """Point the app's model code at the cached tables, seasons first..last.

    espn_only=True keeps only games with an ESPN id, like the DB loader (for the 2016-25 replay check)."""
    d = load()
    G = d["games"][(d["games"]["season"] >= first) & (d["games"]["season"] <= last)].copy()
    if espn_only:
        G = G[G["espn_id"].notna()]
    S = d["stats"].merge(G, on="game_id")
    S["points"] = S["home_points"].where(S["team_id"] == S["home_id"], S["away_points"])
    S["home"] = 0
    S.loc[~S["neutral_site"] & (S["team_id"] == S["home_id"]), "home"] = 1
    S.loc[~S["neutral_site"] & (S["team_id"] != S["home_id"]), "home"] = -1
    S["fcs_offense"] = False
    S["fcs_defense"] = False
    stat_cols = ["team_id", "opponent_id", "week", "season_type", "plays"] + \
        ["epa_per_play", "success_rate", "explosiveness", "pass_epa", "rush_epa", "points", "home",
         "fcs_offense", "fcs_defense"]

    def load_game_stats(season, before, league="cfb"):
        x = S[(S["season"] == season) & (S["start_time"] < before)]
        return x[stat_cols].reset_index(drop=True)

    def count_weeks_played(season, before, league="cfb"):
        r = G[(G["season"] == season) & (G["season_type"] == "regular")]
        last_ko = r.groupby("week")["start_time"].max()
        return int((last_ko < before).sum())

    def load_season_games(season):
        x = G[G["season"] == season].sort_values("start_time")
        return x[["game_id", "season", "week", "season_type", "start_time", "neutral_site",
                  "home_id", "away_id", "home_points", "away_points"]].reset_index(drop=True)

    Q = d["qb_games"].merge(G[["game_id", "season", "week", "start_time"]], on="game_id").sort_values("start_time")

    def load_qb_games():
        q = Q[["qb_id", "team_id", "dropbacks", "epa", "season", "week"]].copy().reset_index(drop=True)
        q["order"] = q["season"] * 100 + q["week"]
        return q

    st = d["starters"][d["starters"]["game_id"].isin(G["game_id"])]

    def load_starters():
        return {(g, t): q for g, t, q in zip(st["game_id"], st["team_id"], st["qb_id"])}

    ratings.load_game_stats = load_game_stats
    ratings.count_weeks_played = count_weeks_played
    nfl_model.load_season_games = load_season_games
    nfl_qbs.load_qb_games = load_qb_games
    nfl_qbs.load_starters = load_starters
    nfl_model.FIRST_SEASON = first
    return G
