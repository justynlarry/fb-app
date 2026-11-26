
# ---- replay vs a FRESH app run on the reloaded DB (appended after hist.py). Nothing saved.
import importlib
from cfb import ratings as R, nfl_model as M, nfl_qbs as QB
db_rows = M.build_rows(M.SETTINGS, 2016, 2025)
db_pred = M.walk_forward(db_rows, range(2017, 2026), M.FEATURES)
with connect() as conn:
    emap = dict(conn.execute("SELECT id, espn_id FROM games WHERE league='nfl'").fetchall())
db_pred["espn_id"] = [emap[g] for g in db_pred.index]
Gr = patch(2016, 2025, espn_only=True)
f_rows = M.build_rows(M.SETTINGS, 2016, 2025)
f_pred = M.walk_forward(f_rows, range(2017, 2026), M.FEATURES).join(Gr.set_index("game_id")["espn_id"])
x = f_pred.merge(db_pred[["espn_id", "spread", "total"]], on="espn_id", suffixes=("", "_db"))
dd = (x["spread"] - x["spread_db"]).abs()
print(f"replay (files vs reloaded DB) 2017-25: {len(x)} games, spread mean |diff| {dd.mean():.4f}, max {dd.max():.4f}, "
      f"total mean |diff| {(x['total'] - x['total_db']).abs().mean():.4f}")
