
# ---- diagnose the replay gap (appended after hist.py). No results graded.
import importlib
d = load()
G = d["games"]
with connect() as conn:
    dbg = pd.DataFrame(conn.execute("SELECT id, espn_id, season, week, season_type, start_time, neutral_site, home_id, away_id, home_points, away_points FROM games WHERE league='nfl' AND season BETWEEN 2016 AND 2025").fetchall(),
                       columns=["db_id", "espn_id", "season", "week", "season_type", "start_time", "neutral_site", "home_id", "away_id", "home_points", "away_points"])
    dbs = pd.DataFrame(conn.execute("SELECT s.game_id, s.team_id, s.plays, s.epa_per_play::float, s.success_rate::float, s.explosiveness::float, s.pass_epa::float, s.rush_epa::float FROM team_game_stats s JOIN games g ON g.id=s.game_id WHERE g.league='nfl' AND g.season BETWEEN 2016 AND 2025").fetchall(),
                       columns=["db_id", "team_id", "plays", "epa_per_play", "success_rate", "explosiveness", "pass_epa", "rush_epa"])
    dbst = pd.DataFrame(conn.execute("SELECT game_id, team_id, qb_id FROM nfl_starters").fetchall(), columns=["db_id", "team_id", "qb_id"])
    dbq = pd.DataFrame(conn.execute("SELECT game_id, team_id, qb_id, dropbacks, epa::float FROM nfl_qb_games").fetchall(), columns=["db_id", "team_id", "qb_id", "dropbacks", "epa"])
f = G[G["espn_id"].notna() & G["season"].between(2016, 2025)].merge(dbg, on="espn_id", suffixes=("", "_db"))
print("games matched", len(f), "of", len(dbg))
for c in ["season", "week", "season_type", "neutral_site", "home_id", "away_id", "home_points", "away_points"]:
    print(f"  {c} differs: {int((f[c] != f[c + '_db']).sum())}")
print("  start_time differs:", int((f["start_time"] != pd.to_datetime(f["start_time_db"], utc=True)).sum()))
m = d["stats"].merge(f[["game_id", "db_id", "season"]], on="game_id").merge(dbs, on=["db_id", "team_id"], suffixes=("", "_db"))
print("stats matched", len(m))
for c in ["plays", "epa_per_play", "success_rate", "explosiveness", "pass_epa", "rush_epa"]:
    x = (m[c] - m[c + "_db"]).abs()
    print(f"  {c}: rows differing > 1e-6: {int((x > 1e-6).sum())}, mean |diff| {x.mean():.5f}; by season "
          + str(m.assign(x=x > 1e-6).groupby("season")["x"].mean().round(2).to_dict()))
st = d["starters"].merge(f[["game_id", "db_id"]], on="game_id").merge(dbst, on=["db_id", "team_id"], how="outer", suffixes=("", "_db"), indicator=True)
print("starters:", st["_merge"].value_counts().to_dict(), "qb differs", int((st["qb_id"] != st["qb_id_db"]).sum()))
q = d["qb_games"].merge(f[["game_id", "db_id"]], on="game_id").merge(dbq, on=["db_id", "team_id", "qb_id"], how="outer", suffixes=("", "_db"), indicator=True)
print("qb_games:", q["_merge"].value_counts().to_dict(), "dropbacks differ", int((q["dropbacks"] != q["dropbacks_db"]).sum()))
