
import numpy as np
d = load(); G = d["games"]
with connect() as conn:
    dbs = pd.DataFrame(conn.execute("SELECT g.espn_id, s.team_id, g.season, s.epa_per_play::float, s.explosiveness::float, s.success_rate::float FROM team_game_stats s JOIN games g ON g.id=s.game_id WHERE g.league='nfl' AND g.season BETWEEN 2016 AND 2025").fetchall(), columns=["espn_id","team_id","season","epa_db","exp_db","suc_db"])
m = d["stats"].merge(G[["game_id","espn_id"]], on="game_id").merge(dbs, on=["espn_id","team_id"])
for s, x in m.groupby("season"):
    print(s, f"epa file {x.epa_per_play.mean():+.4f} db {x.epa_db.mean():+.4f} r {np.corrcoef(x.epa_per_play, x.epa_db)[0,1]:.4f} | expl file {x.explosiveness.mean():.3f} db {x.exp_db.mean():.3f} r {np.corrcoef(x.explosiveness, x.exp_db)[0,1]:.3f} | succ file {x.success_rate.mean():.3f} db {x.suc_db.mean():.3f}")
import httpx
r = httpx.get("https://api.github.com/repos/nflverse/nflverse-data/releases/tags/pbp", timeout=30).json()
a = [x for x in r.get("assets", []) if x["name"] in ("play_by_play_2016.parquet", "play_by_play_2024.parquet")]
for x in a: print(x["name"], x["updated_at"])
