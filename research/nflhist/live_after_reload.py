# nfl-v3 upcoming games: fresh prediction on the reloaded DB vs the live rows saved this morning (old 2016-25 stats).
# Nothing saved; tomorrow's 5:30 AM update replaces the live rows.
import pandas as pd
from cfb import nfl_model as m
from cfb.db import connect
rows = m.season_rows_through(2026)
new = m.upcoming_predictions(rows, 2026)
with connect() as conn:
    old = pd.DataFrame(conn.execute("SELECT p.game_id, p.spread::float, p.total::float, g.week FROM predictions p JOIN games g ON g.id=p.game_id "
        "WHERE p.model_version='nfl-v3' AND NOT p.is_backtest AND g.start_time > now()").fetchall(), columns=["game_id","old_spread","old_total","week"]).set_index("game_id")
x = new.join(old, how="inner")
ds, dt = x["spread"] - x["old_spread"], x["total"] - x["old_total"]
print(f"{len(x)} upcoming games: spread change mean {ds.mean():+.2f}, mean |change| {ds.abs().mean():.2f}, max |change| {ds.abs().max():.2f}")
print(f"  total change mean {dt.mean():+.2f}, range {dt.min():+.2f} to {dt.max():+.2f}")
print(f"  spread SD old {x['old_spread'].std():.2f} new {x['spread'].std():.2f}")
w = x["week"].min(); y = x[x["week"] == w]
print(f"  week {w}: spread mean |change| {(y['spread']-y['old_spread']).abs().mean():.2f}, total change {(y['total']-y['old_total']).mean():+.2f}, "
      f"games crossing 3 pts from the market not checked here")
