"""The August no-harm check before the 2027 freeze (docs/plan-2027.md 2.2). Run ONCE, in August, never before.

    docker compose exec worker python -m cfb.freeze_check

It rebuilds every candidate stack in memory (walk-forward 2018-2025, like model.backtest, nothing saved), judges each
against v5 on the Rule C games (2021-25, FBS-involved, Bovada open and Bovada close, median close of books), and walks
the fallback order fixed on 2026-11-18 until a stack passes:

    1. v5 + T1 + T-OCDC (+ coach career only if Holdout 5A was "Confirmed": not built yet, see COACH_CAREER)
    2. without T-OCDC
    3. without coach career
    4. v5 + T1
    5. v5 unchanged (if nothing above passes)

Checks (each vs v5, paired season-week bootstrap, 2,000):
    spread MAE better (all 2021-25 games with a closing line); delta result slope at the Bovada open >= -1 SE;
    ATS 3+ at the open not down by more than 1.0 pp; CLV % not down by more than 1.0 pp; CLV points not down by
    more than 2 SE.  Reported, not judged: calibration by weeks played (0-2, 3-4, 5-9, 10+), CLV % both definitions.
Writes nothing to the database and calls no API.
"""

import json
import sys

import numpy as np
import pandas as pd
from psycopg.rows import dict_row
from sklearn.linear_model import LinearRegression

import cfb.model as model
from cfb.db import connect

BOOKS = ["Bovada", "DraftKings", "ESPN Bet", "William Hill (New Jersey)", "Caesars Sportsbook (Colorado)",
         "Caesars (Pennsylvania)", "SugarHouse"]
COACH_CAREER = False        # set True only after Holdout 5A is "Confirmed" AND the coach-career columns are built
FIRST, LAST = 2018, 2025
SEED = 20270801

STACKS = [   # (name, extra columns on top of v5), in the fixed fallback order
    ("v5 + T1 + T-OCDC", model.MATCH_FEATURES + model.COORDINATOR_FEATURES),
    ("v5 + T1", model.MATCH_FEATURES),
]

GAMES_SQL = """
SELECT g.id AS game_id, g.season, g.week, g.season_type, g.completed,
       (g.away_points - g.home_points)::float AS r
FROM games g
WHERE g.league = 'cfb' AND g.season BETWEEN 2021 AND 2025
  AND 'fbs' IN (g.home_classification, g.away_classification)
"""
LINES_SQL = """
SELECT l.game_id, l.provider, l.spread::float AS close, l.spread_open::float AS open
FROM lines l JOIN games g ON g.id = l.game_id
WHERE g.league = 'cfb' AND g.season BETWEEN 2021 AND 2025
"""


def walk(rows, features, home_of):
    """Walk-forward home-spread predictions: season S from a points model trained on seasons before S."""
    rows = rows.copy()
    rows["is_home"] = rows["team_id"] == rows["game_id"].map(home_of)
    parts = []
    for season in range(FIRST, LAST + 1):
        known = rows[rows["season"] < season].dropna(subset=["points"])
        fit = LinearRegression().fit(known[features].astype(float), known["points"].astype(float))
        test = rows[rows["season"] == season].copy()
        test["pred"] = fit.predict(test[features].astype(float))
        home = test[test["is_home"]].set_index("game_id")
        away = test[~test["is_home"]].set_index("game_id")
        parts.append(pd.DataFrame({"line": away["pred"] - home["pred"], "wp": home["weeks_played"]}))
    return pd.concat(parts)


def slope(x, y):
    x = np.asarray(x, float) - np.mean(x)
    y = np.asarray(y, float)
    return float((x * (y - y.mean())).sum() / (x * x).sum())


def judge(J, MA, base, cand, rng):
    """The plan's checks for one candidate column against v5 ('base'), plus the reported items."""
    clusters = (J["season"].astype(str) + "-" + J["season_type"] + "-" + J["week"].astype(str)).values
    keys = np.unique(clusters)
    where = {k: np.where(clusters == k)[0] for k in keys}
    samples = [np.concatenate([where[k] for k in rng.choice(keys, len(keys))]) for _ in range(2000)]

    def result_slope(x, col):
        return slope(x[col] - x["open"], x["r"] - x["open"])

    def clv_points(x, col):
        gap = (x[col] - x["open"]).values
        big = np.abs(gap) >= 3
        return float((np.sign(gap) * (x["bclose"] - x["open"]).values)[big].mean())

    def ats(x, col):
        gap = (x[col] - x["open"]).values
        res = (x["r"] - x["open"]).values
        keep = (np.abs(gap) >= 3) & (res != 0)
        return 100 * float((res * np.sign(gap) > 0)[keep].mean()), int(keep.sum())

    def clv_pct(x, col):
        gap = (x[col] - x["open"]).values
        move = (np.sign(gap) * (x["bclose"] - x["open"]).values)[np.abs(gap) >= 3]
        return 100 * float((move > 0).mean()), 100 * float((move > 0).sum() / (move != 0).sum())

    def paired_se(f):
        return float(np.std([f(J.iloc[i]) for i in samples]))

    d_rs = result_slope(J, cand) - result_slope(J, base)
    se_rs = paired_se(lambda x: result_slope(x, cand) - result_slope(x, base))
    d_cp = clv_points(J, cand) - clv_points(J, base)
    se_cp = paired_se(lambda x: clv_points(x, cand) - clv_points(x, base))
    mae_b = float((MA["r"] - MA[base]).abs().mean())
    mae_c = float((MA["r"] - MA[cand]).abs().mean())
    ats_b, ats_c = ats(J, base), ats(J, cand)
    clv_b, clv_c = clv_pct(J, base), clv_pct(J, cand)
    checks = {
        "spread MAE better": mae_c < mae_b,
        "delta result slope >= -1 SE": d_rs >= -se_rs,
        "ATS 3+ at open not down > 1.0 pp": ats_c[0] >= ats_b[0] - 1.0,
        "CLV % (definition A, all 3+ picks) not down > 1.0 pp": clv_c[0] >= clv_b[0] - 1.0,
        "CLV points not down > 2 SE": d_cp >= -2 * se_cp,
    }
    bands = [("0-2", 0, 2), ("3-4", 3, 4), ("5-9", 5, 9), ("10+", 10, 99)]
    calibration = {}
    for label, lo, hi in bands:
        part = MA[MA["wp"].between(lo, hi)]
        calibration[label] = {"v5": round(slope(part[base], part["r"]), 3), "candidate": round(slope(part[cand], part["r"]), 3),
                              "n": len(part)}
    return {
        "checks": checks, "PASS": all(checks.values()),
        "spread MAE v5 / candidate": [round(mae_b, 4), round(mae_c, 4)],
        "delta result slope at the open": f"{d_rs:+.4f} ± {se_rs:.4f}",
        "ATS 3+ at the open v5 / candidate": [f"{ats_b[0]:.2f}% (n={ats_b[1]})", f"{ats_c[0]:.2f}% (n={ats_c[1]})"],
        "CLV % A / B, v5": [round(clv_b[0], 2), round(clv_b[1], 2)], "CLV % A / B, candidate": [round(clv_c[0], 2), round(clv_c[1], 2)],
        "CLV points v5 / candidate": [round(clv_points(J, base), 3), round(clv_points(J, cand), 3), f"diff {d_cp:+.3f} ± {se_cp:.3f}"],
        "reported: calibration by weeks played (1 = right)": calibration,
    }


def main():
    if COACH_CAREER:
        sys.exit("Coach career is not built into cfb/model.py yet: build it (after a 'Confirmed' 5A) before this check.")
    rng = np.random.default_rng(SEED)
    print("building walk-forward rows 2017-2025 (several minutes)...", flush=True)
    rows = pd.concat([model.season_rows(s) for s in range(FIRST - 1, LAST + 1)], ignore_index=True)
    with connect() as conn:
        home_of = dict(conn.execute("SELECT id, home_id FROM games WHERE league = 'cfb'").fetchall())
        conn.row_factory = dict_row
        games = pd.DataFrame(conn.execute(GAMES_SQL).fetchall()).set_index("game_id")
        lines = pd.DataFrame(conn.execute(LINES_SQL).fetchall())
    close = lines.pivot_table(index="game_id", columns="provider", values="close")
    opens = lines.pivot_table(index="game_id", columns="provider", values="open")

    base = walk(rows, model.FEATURES, home_of).rename(columns={"line": "v5"})
    report = {"rows": len(rows), "stacks": {}}
    for name, extra in STACKS:
        cand = walk(rows, model.FEATURES + extra, home_of)["line"].rename("cand")
        D = games[games["completed"]].join(base, how="inner").join(cand, how="inner")
        D["open"] = opens["Bovada"]
        D["bclose"] = close["Bovada"]
        D["mclose"] = close[[b for b in BOOKS if b in close]].median(axis=1)
        MA = D.dropna(subset=["mclose"])
        J = D.dropna(subset=["open", "bclose", "mclose"])
        result = judge(J, MA, "v5", "cand", rng)
        result["n judged / n MAE"] = [len(J), len(MA)]
        report["stacks"][name] = result
        print(f"{name}: {'PASS' if result['PASS'] else 'fail'}", flush=True)
        if result["PASS"]:
            report["FREEZE"] = name
            break
    report.setdefault("FREEZE", "v5 unchanged (no stack passed)")
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
