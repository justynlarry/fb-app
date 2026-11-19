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


# ------------------------------------------------------------------------------------------------------------- NFL
# NFL B1 (plan-2027 section 8.3, N-TOT-B1): the same idea on NFL closing lines (nflverse's one number per game, in
# `lines` as provider 'nflverse'), weighted like nfl-v3's ratings (half-life 6, last season faded out over 12 weeks,
# last season's games at weight 0.5), ridge alpha 1.  Spread exactly as T-OPEN-B's B1; total = T_home + T_away + c,
# as college's B1-total.  Fit on games that kicked off before the cutoff (the NFL bet time); computed at judging.
NFL_HALF_LIFE, NFL_LAST_WEIGHT, NFL_PRIOR_WEEKS = 6, 0.5, 12

NFL_GAMES_SQL = """
SELECT g.id AS game_id, g.season, g.week, g.season_type, g.start_time, g.home_id, g.away_id, g.neutral_site,
       l.spread::float AS close_s, l.over_under::float AS close_t
FROM games g
LEFT JOIN lines l ON l.game_id = g.id AND l.provider = 'nflverse'
WHERE g.league = 'nfl' AND g.season BETWEEN %(first)s AND %(last)s
"""


def nfl_load(first, last):
    with connect() as conn:
        conn.row_factory = dict_row
        G = pd.DataFrame(conn.execute(NFL_GAMES_SQL, {"first": first, "last": last}).fetchall()).set_index("game_id")
    G["ns"] = (~G["neutral_site"].astype(bool)).astype(float)
    return G


def nfl_predictions(G, season, cutoff, game_ids):
    """{game_id: (B1 spread, B1 total)} for these games, from closes of games that kicked off before the cutoff."""
    regular = G[(G["season"] == season) & (G["season_type"] == "regular")]
    wp = int((regular.groupby("week")["start_time"].max() < cutoff).sum())
    cur = G[(G["season"] == season) & (G["start_time"] < cutoff)].copy()
    week = cur["week"].where(cur["season_type"] == "regular", wp)
    cur["w"] = 0.5 ** ((wp - week).clip(lower=0) / NFL_HALF_LIFE)
    parts = [cur]
    fade = max(0.0, 1 - wp / NFL_PRIOR_WEEKS)
    if fade > 0:
        last = G[G["season"] == season - 1].copy()
        offseason_age = NFL_HALF_LIFE * np.log2(1 / NFL_LAST_WEIGHT)
        last["w"] = fade * 0.5 ** (offseason_age / NFL_HALF_LIFE)
        parts.append(last)
    H = pd.concat(parts)
    teams = sorted(set(G["home_id"]) | set(G["away_id"]))
    ix = {t: k for k, t in enumerate(teams)}
    n = len(teams)
    out_s, out_t = {}, {}
    hs = H.dropna(subset=["close_s"])
    if len(hs):
        X = np.zeros((len(hs), n + 1))
        r = np.arange(len(hs))
        X[r, hs["away_id"].map(ix).values] = 1
        X[r, hs["home_id"].map(ix).values] = -1
        X[:, n] = -hs["ns"].values
        s = Ridge(alpha=1.0, fit_intercept=False).fit(X, hs["close_s"].values, sample_weight=hs["w"].values)
    ht = H.dropna(subset=["close_t"])
    if len(ht):
        X = np.zeros((len(ht), n))
        r = np.arange(len(ht))
        X[r, ht["away_id"].map(ix).values] = 1
        X[r, ht["home_id"].map(ix).values] += 1
        t = Ridge(alpha=1.0, fit_intercept=True).fit(X, ht["close_t"].values, sample_weight=ht["w"].values)
    out = {}
    for gid in game_ids:
        g = G.loc[gid]
        a, h = ix[g["away_id"]], ix[g["home_id"]]
        spread = float(s.coef_[a] - s.coef_[h] - s.coef_[n] * g["ns"]) if len(hs) else np.nan
        total = float(t.coef_[a] + t.coef_[h] + t.intercept_) if len(ht) else np.nan
        out[gid] = (spread, total)
    return out
