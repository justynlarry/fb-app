import pandas as pd
from cfb import nfl_model as m
from cfb.ratings import METRICS
rows = m.season_rows_through(2026)
model = m.train(rows, m.FEATURES)
coef = pd.Series(model.coef_, index=m.FEATURES)
r25 = rows[rows.season == 2025]; r26 = rows[rows.season == 2026]
print("metric          coef(off+oppdef)  coef(def+oppoff)  mean off_ rating 2025 -> 2026")
own = 0.0
for k in METRICS:
    a = coef["off_"+k] + coef["oppdef_"+k]; b = coef["def_"+k] + coef["oppoff_"+k]
    shift = r26["off_"+k].mean() - r25["off_"+k].mean()
    own += (a + b) * shift
    print(f"{k:15s} {a:+16.2f}  {b:+16.2f}  {r25['off_'+k].mean():.4f} -> {r26['off_'+k].mean():.4f} (shift {shift:+.4f})")
print(f"implied change in each team's predicted points from the 2026 rating shifts: {own:+.2f}  (total x2 = {2*own:+.2f})")
