
# ---- checks (appended after hist.py) : season sanity + 2016-25 replay vs stored nfl-v3 backtest. No results graded.
import numpy as np
d = load()
G, S, Q, ST = d["games"], d["stats"], d["qb_games"], d["starters"]
S2 = S.merge(G[["game_id", "season"]], on="game_id")
Q2 = Q.merge(G[["game_id", "season"]], on="game_id")
print("season  games  team-games  plays/tg  epa/play  success  dropbacks/tg  starters%  no_close  no_score")
for s, g in G.groupby("season"):
    t = S2[S2["season"] == s]
    q = Q2[Q2["season"] == s]
    print(f"{s}  {len(g):5d}  {len(t):10d}  {t['plays'].mean():8.1f}  {t['epa_per_play'].mean():+8.3f}  "
          f"{t['success_rate'].mean():7.3f}  {q['dropbacks'].sum() / max(len(t), 1):12.1f}  "
          f"{100 * len(ST[ST['game_id'].isin(g['game_id'])]) / (2 * len(g)):8.1f}  "
          f"{int(g['close_spread'].isna().sum()):8d}  {int(g['home_points'].isna().sum()):8d}")
missing_stats = set(G["game_id"]) - set(S["game_id"])
print("games without stats:", len(missing_stats), "| ids shared by 2+ games (espn):",
      int(G["espn_id"].dropna().duplicated().sum()))

# Replay: files restricted to 2016-25 with ESPN ids, the app's code, vs stored nfl-v3 backtest
Gr = patch(2016, 2025, espn_only=True)
rows = nfl_model.build_rows(nfl_model.SETTINGS, 2016, 2025)
pred = nfl_model.walk_forward(rows, range(2017, 2026), nfl_model.FEATURES)
with connect() as conn:
    stored = pd.DataFrame(conn.execute(
        "SELECT g.espn_id, p.spread::float, p.total::float FROM predictions p JOIN games g ON g.id = p.game_id "
        "WHERE p.model_version = 'nfl-v3' AND p.is_backtest AND g.league = 'nfl'").fetchall(),
        columns=["espn_id", "s_spread", "s_total"])
pred = pred.join(Gr.set_index("game_id")["espn_id"]).merge(stored, on="espn_id")
dd = (pred["spread"] - pred["s_spread"]).abs()
print(f"replay 2017-25: {len(pred)} games matched, spread mean |diff| {dd.mean():.4f}, max {dd.max():.3f}, "
      f"total mean |diff| {(pred['total'] - pred['s_total']).abs().mean():.4f}")
print(pred.assign(d=dd).groupby("season")["d"].mean().round(4).to_dict())
