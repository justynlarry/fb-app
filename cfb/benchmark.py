"""B1: a market-implied benchmark built only from earlier closing lines (no football information, no scores).

Registered 2026-11-18 (docs/plan-2026-11-18.md B1; docs/model-tests.md H-TOT-B1) and frozen as it was run then:
    spread: close = R_away - R_home - H * (not neutral)      ridge alpha 1, no intercept
    total:  close_total = T_home + T_away + c                 ridge alpha 1, with an intercept
fit on the closing lines (median of the CFBD books, Bovada where the median is missing) of FBS-involved games that
kicked off before the week block's first kickoff, weighted exactly like v5's ratings (this season by recency, last
season faded out over PRIOR_WEEKS).  Saved daily by cfb/paper.py as model_version 'b1-total' (the name in
docs/plan-2027.md; the B1 spread is stored beside the total for reference), paper only.
"""

import numpy as np
import pandas as pd
from psycopg.rows import dict_row
from sklearn.linear_model import Ridge

import cfb.ratings as R
from cfb.db import connect

VERSION = "b1-total"
BOOKS = ["Bovada", "DraftKings", "ESPN Bet", "William Hill (New Jersey)", "Caesars Sportsbook (Colorado)",
         "Caesars (Pennsylvania)", "SugarHouse"]

GAMES_SQL = """
SELECT id AS game_id, season, week, season_type, start_time, home_id, away_id, neutral_site
FROM games
WHERE league = 'cfb'
  AND season BETWEEN %(first)s AND %(last)s
  AND 'fbs' IN (home_classification, away_classification)
"""
CLOSES_SQL = """
SELECT l.game_id, l.provider, l.spread::float AS close, l.over_under::float AS tclose
FROM lines l JOIN games g ON g.id = l.game_id
WHERE g.league = 'cfb' AND g.season BETWEEN %(first)s AND %(last)s
"""


def load(first, last):
    """FBS-involved games of these seasons with their closing spread and total."""
    with connect() as conn:
        conn.row_factory = dict_row
        games = pd.DataFrame(conn.execute(GAMES_SQL, {"first": first, "last": last}).fetchall()).set_index("game_id")
        lines = pd.DataFrame(conn.execute(CLOSES_SQL, {"first": first, "last": last}).fetchall())
    if lines.empty:
        games["close_s"] = np.nan
        games["close_t"] = np.nan
    else:
        close = lines.pivot_table(index="game_id", columns="provider", values="close")
        total = lines.pivot_table(index="game_id", columns="provider", values="tclose")
        median = lambda t: t[[b for b in BOOKS if b in t]].median(axis=1)
        games["close_s"] = median(close).fillna(close.get("Bovada"))
        games["close_t"] = median(total).fillna(total.get("Bovada"))
    games["ns"] = (~games["neutral_site"].astype(bool)).astype(float)
    return games


def weighted_history(G, season, cutoff):
    """Games before the cutoff this season plus last season, with v5's rating weights.  Returns (rows, weeks played)."""
    regular = G[(G["season"] == season) & (G["season_type"] == "regular")]
    wp = int((regular.groupby("week")["start_time"].max() < cutoff).sum())
    cur = G[(G["season"] == season) & (G["start_time"] < cutoff)].copy()
    week = cur["week"].where(cur["season_type"] == "regular", wp)
    cur["w"] = 0.5 ** ((wp - week).clip(lower=0) / R.RECENCY_HALF_LIFE)
    parts = [cur]
    fade = max(0.0, 1 - wp / R.PRIOR_WEEKS)
    if fade > 0:
        last = G[G["season"] == season - 1].copy()
        last["w"] = fade * 0.5 ** (R.OFFSEASON_AGE_WEEKS / R.RECENCY_HALF_LIFE)
        parts.append(last)
    return pd.concat(parts), wp


def block_predictions(G, season, season_type, week):
    """{game_id: (spread, total, weeks played)} for every game of one week block that both fits can rate."""
    block = G[(G["season"] == season) & (G["season_type"] == season_type) & (G["week"] == week)]
    cutoff = block["start_time"].min()
    H, wp = weighted_history(G, season, cutoff)
    teams = sorted(set(H["home_id"]) | set(H["away_id"]))
    ix = {t: k for k, t in enumerate(teams)}
    n = len(teams)
    fits = {}
    for kind, col in (("s", "close_s"), ("t", "close_t")):
        h = H.dropna(subset=[col])
        rows = np.arange(len(h))
        hi = h["home_id"].map(ix).values
        ai = h["away_id"].map(ix).values
        X = np.zeros((len(h), n + 1))
        if kind == "s":
            X[rows, ai] = 1
            X[rows, hi] = -1
            X[:, n] = -h["ns"].values
            fits[kind] = Ridge(alpha=R.ALPHA, fit_intercept=False).fit(X, h[col].values, sample_weight=h["w"].values)
        else:
            X[rows, ai] = 1
            X[rows, hi] += 1
            fits[kind] = Ridge(alpha=R.ALPHA, fit_intercept=True).fit(X[:, :n], h[col].values, sample_weight=h["w"].values)
    out = {}
    s, t = fits["s"], fits["t"]
    for gid, g in block.iterrows():
        if g["home_id"] not in ix or g["away_id"] not in ix:
            continue
        a, h_ = ix[g["away_id"]], ix[g["home_id"]]
        spread = s.coef_[a] - s.coef_[h_] - s.coef_[n] * g["ns"]
        total = t.coef_[a] + t.coef_[h_] + t.intercept_
        out[gid] = (float(spread), float(total), wp)
    return out


def upcoming_predictions(season):
    """B1 for every FBS-involved game of this season that hasn't kicked off: one row per game with
    game_id, home_points, away_points, weeks_played (like model.pair_predictions)."""
    G = load(season - 1, season)
    upcoming = G[(G["season"] == season) & (G["start_time"] > pd.Timestamp.now(tz="UTC"))]
    out = []
    for (season_type, week), _ in upcoming.groupby(["season_type", "week"]):
        for gid, (spread, total, wp) in block_predictions(G, season, season_type, week).items():
            if gid in upcoming.index:
                # spread is the home side (away - home): home = (total - spread) / 2, away = (total + spread) / 2
                out.append({"game_id": gid, "home_points": (total - spread) / 2, "away_points": (total + spread) / 2,
                            "weeks_played": wp})
    return pd.DataFrame(out, columns=["game_id", "home_points", "away_points", "weeks_played"])
