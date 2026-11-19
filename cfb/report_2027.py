"""Reported measures and tags for the 2027 record (docs/plan-2027.md sections 4 and 6). Read-only: it reads pick_results,
pick_results_bettable, paper_predictions, odds_snapshots, games and team_game_stats, and writes nothing.

    docker compose exec worker python -m cfb.report_2027 2027

None of these decides anything during the season. Each is reported once after the regular season beside the judged items:
  line_moves      bet-time median -> last pre-kickoff median (spreads and totals): share toward us on Plays / totals
                  picks, and the slope of the move on our gap at bet time (the opener-noise check, plan-2027 section 6)
  totals_agree    totals picks tagged agree / disagree: our total and B1-total on the same side of the bettable open
                  total at bet time (registered 2026-11-18, reported only)
  weeknight       Test 1: Mon-Thu (US Eastern) games involving MAC, Sun Belt or C-USA (each game's own conferences)
  luck            Test L: X = home team's luck in its previous game - away team's (actual - deserved margin), as
                  registered in docs/edge-plan-2026-11-16.md; slope of the line move on X, X in thirds
  dk_lookahead    Test F: our line against DraftKings' first-seen line when that line was posted before bet time
                  (a lookahead line), graded at DraftKings' number and price on 3+ gaps
Conference tier (Holdout T) is added only if Holdout T is "supported" on December 7.
"""

import json
import sys

import numpy as np
import pandas as pd
from psycopg.rows import dict_row
from sklearn.linear_model import LinearRegression

from cfb.db import connect
from cfb.model import MODEL_VERSION

G5_MIDWEEK = {"Mid-American", "Sun Belt", "Conference USA"}
LUCK_STATS = ["epa_per_play", "success_rate", "explosiveness", "plays"]


def query(sql, params=None):
    with connect() as conn:
        conn.row_factory = dict_row
        return pd.DataFrame(conn.execute(sql, params or {}).fetchall())


def slope_se(x, y, seed=2027, n_boot=2000):
    """Slope of y on x and its game-bootstrap SE (None if fewer than 10 games)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 10 or np.var(x) == 0:
        return None, None
    def sl(a, b):
        a = a - a.mean()
        return float((a * (b - b.mean())).sum() / (a * a).sum())
    rng = np.random.default_rng(seed)
    boots = [sl(x[i], y[i]) for i in (rng.integers(0, len(x), len(x)) for _ in range(n_boot))]
    return sl(x, y), float(np.std(boots))


def record(outcomes, units):
    """W-L-P, win % with 95% interval, units, ROI for a set of graded picks."""
    o = pd.Series(outcomes).dropna()
    w, l, p = int((o == "win").sum()), int((o == "loss").sum()), int((o == "push").sum())
    n = w + l
    u = float(pd.Series(units).dropna().sum())
    if n == 0:
        return {"W-L-P": f"{w}-{l}-{p}", "n": 0}
    rate = w / n
    return {"W-L-P": f"{w}-{l}-{p}", "win %": round(100 * rate, 1), "±95%": round(196 * np.sqrt(rate * (1 - rate) / n), 1),
            "units": round(u, 2), "ROI %": round(100 * u / (n + p), 1)}


# ------------------------------------------------------------------------------------------------- picks at bet time
PICKS_SQL = """
SELECT f.game_id, f.season, f.week, f.start_time, f.tier, f.side, f.total_side, f.recorded_at,
       f.our_spread::float, f.our_total::float, f.market_spread::float AS bet_median, f.market_total::float AS bet_tmedian,
       l.market_spread::float AS last_median, l.market_total::float AS last_tmedian,
       b.b_spread::float, b.b_spread_outcome, b.b_spread_units::float, b.b_total::float, b.b_total_outcome,
       b.b_total_units::float
FROM pick_results f
JOIN games g ON g.id = f.game_id
LEFT JOIN pick_results l ON l.game_id = f.game_id AND l.model_version = f.model_version AND l.taken = 'last'
LEFT JOIN pick_results_bettable b ON b.game_id = f.game_id AND b.model_version = f.model_version AND b.taken = 'first'
WHERE f.taken = 'first' AND f.model_version = %(version)s AND f.season = %(season)s AND g.league = 'cfb'
"""


def bet_time_picks(season, version=MODEL_VERSION):
    return query(PICKS_SQL, {"season": season, "version": version})


def line_moves(p):
    """Bet-time median -> last pre-kickoff median, spreads and totals (home-side spreads: lower = home favoured more)."""
    out = {}
    for kind, ours, bet, last, picked in (("spreads", "our_spread", "bet_median", "last_median", p["tier"] == "play"),
                                          ("totals", "our_total", "bet_tmedian", "last_tmedian", p["total_side"].notna())):
        d = p.dropna(subset=[ours, bet, last])
        gap, move = (d[ours] - d[bet]).values, (d[last] - d[bet]).values
        toward = np.sign(gap) * move
        sel = picked.loc[d.index].values
        b, se = slope_se(gap, move)
        out[kind] = {"games": len(d), "slope of move on our gap": None if b is None else f"{b:+.3f} ± {se:.3f}",
                     "picks": int(sel.sum()),
                     "picks: moved toward us %": round(100 * float((toward[sel] > 0).mean()), 1) if sel.any() else None,
                     "picks: mean move toward us (pts)": round(float(toward[sel].mean()), 2) if sel.any() else None}
    return out


# --------------------------------------------------------------------------------------------------- totals agree
B1_AT_BET_TIME_SQL = """
SELECT f.game_id,
       (SELECT pp.total::float FROM paper_predictions pp
        WHERE pp.game_id = f.game_id AND pp.model_version = 'b1-total' AND pp.created_at <= f.recorded_at
        ORDER BY pp.created_at DESC LIMIT 1) AS b1_total
FROM pick_results f
WHERE f.taken = 'first' AND f.model_version = %(version)s AND f.season = %(season)s AND f.total_side IS NOT NULL
"""


def totals_agree(p, season, version=MODEL_VERSION):
    b1 = query(B1_AT_BET_TIME_SQL, {"season": season, "version": version})
    d = p[p["total_side"].notna()].merge(b1, on="game_id", how="left") if len(b1) else p[p["total_side"].notna()].assign(b1_total=np.nan)
    d["b1_total"] = pd.to_numeric(d["b1_total"], errors="coerce")       # all empty before B1 existed -> object column
    ours = np.sign(d["our_total"] - d["b_total"])
    theirs = np.sign(d["b1_total"] - d["b_total"])
    d["tag"] = np.where(d["b1_total"].isna() | d["b_total"].isna() | (theirs == 0), "untagged",
                        np.where(ours == theirs, "agree", "disagree"))
    out = {"counts": d["tag"].value_counts().to_dict()}
    for tag in ("agree", "disagree"):
        g = d[d["tag"] == tag]
        rec = record(g["b_total_outcome"], g["b_total_units"])
        move = np.sign(g["our_total"] - g["bet_tmedian"]) * (g["last_tmedian"] - g["bet_tmedian"])
        rec["mean move toward our side (pts)"] = round(float(move.mean()), 2) if move.notna().any() else None
        out[tag] = rec
    return out


# ------------------------------------------------------------------------------------------------------ weeknight
CONFERENCES_SQL = """
SELECT g.id AS game_id, j->>'homeConference' AS home_conf, j->>'awayConference' AS away_conf
FROM games g
JOIN (SELECT DISTINCT ON (params->>'year') params->>'year' AS year, body
      FROM api_responses WHERE source = 'cfbd' AND endpoint = '/games'
      ORDER BY params->>'year', fetched_at DESC) r ON r.year::int = g.season
JOIN LATERAL jsonb_array_elements(r.body) j ON (j->>'id')::int = g.cfbd_id
WHERE g.league = 'cfb' AND g.season = %(season)s
"""


def weeknight(p, season):
    conf = query(CONFERENCES_SQL, {"season": season})
    d = p.merge(conf, on="game_id", how="left")
    dow = pd.to_datetime(d["start_time"], utc=True).dt.tz_convert("America/New_York").dt.dayofweek
    d["tag"] = dow.isin([0, 1, 2, 3]) & (d["home_conf"].isin(G5_MIDWEEK) | d["away_conf"].isin(G5_MIDWEEK))
    plays = d[d["tag"] & (d["tier"] == "play")]
    return {"tagged games": int(d["tag"].sum()), "games without conference info": int(d["home_conf"].isna().sum()),
            "Plays, at the bettable number": record(plays["b_spread_outcome"], plays["b_spread_units"])}


# ----------------------------------------------------------------------------------------------------------- luck
LUCK_GAMES_SQL = """
SELECT id AS game_id, season, start_time, home_id, away_id, home_points, away_points,
       home_classification AS hc, away_classification AS ac, completed
FROM games WHERE league = 'cfb' AND season BETWEEN %(first)s AND %(season)s
"""


def luck_x(season):
    """{game_id: X} for every game of the season with both teams' previous-game luck (Test L's input)."""
    G = query(LUCK_GAMES_SQL, {"first": 2016, "season": season})
    S = query("SELECT game_id, team_id, " + ", ".join(LUCK_STATS) + " FROM team_game_stats")
    done = G[G["completed"] & G["home_points"].notna()].copy()
    done["margin"] = done["home_points"] - done["away_points"]
    h = S.add_prefix("h_").rename(columns={"h_game_id": "game_id", "h_team_id": "home_id"})
    a = S.add_prefix("a_").rename(columns={"a_game_id": "game_id", "a_team_id": "away_id"})
    GS = done.merge(h, on=["game_id", "home_id"]).merge(a, on=["game_id", "away_id"])
    D = ["d_" + m for m in LUCK_STATS]
    for m in LUCK_STATS:
        GS["d_" + m] = GS["h_" + m].astype(float) - GS["a_" + m].astype(float)
    GS = GS.dropna(subset=D)
    fbs2 = (GS["hc"] == "fbs") & (GS["ac"] == "fbs")
    train = GS[fbs2 & (GS["season"] < season)]
    fit = LinearRegression().fit(train[D], train["margin"])         # deserved margin, from seasons before this one
    cur = GS[GS["season"] == season].copy()
    cur["home_luck"] = cur["margin"] - fit.predict(cur[D])
    tl = pd.concat([
        pd.DataFrame({"team_id": cur["home_id"], "opp_cls": cur["ac"], "t": cur["start_time"], "luck": cur["home_luck"]}),
        pd.DataFrame({"team_id": cur["away_id"], "opp_cls": cur["hc"], "t": cur["start_time"], "luck": -cur["home_luck"]}),
    ]).sort_values("t")
    games = G[G["season"] == season][["game_id", "start_time", "home_id", "away_id"]].sort_values("start_time")

    def previous(team_col):
        q = games[["game_id", "start_time", team_col]].rename(columns={team_col: "team_id"})
        m = pd.merge_asof(q, tl.rename(columns={"t": "pt"}), left_on="start_time", right_on="pt", by="team_id",
                          allow_exact_matches=False, direction="backward")
        ok = (m["opp_cls"] == "fbs") & ((m["start_time"] - m["pt"]) <= pd.Timedelta(days=15))
        return m.set_index("game_id")["luck"].where(ok.values)

    x = (previous("home_id") - previous("away_id")).dropna()
    return x.to_dict()


def luck(p, season):
    x = luck_x(season)
    d = p.assign(X=p["game_id"].map(x)).dropna(subset=["X", "bet_median", "last_median"])
    # home margin terms: the market's home margin = -spread, so its rise from bet time to the end = bet - last
    move = (d["bet_median"] - d["last_median"]).values
    b, se = slope_se(d["X"].values, move)
    out = {"games with X": len(d), "slope of line move on X (registered sign: negative)": None if b is None else f"{b:+.4f} ± {se:.4f}"}
    if len(d) >= 30:
        d = d.assign(third=pd.qcut(d["X"], 3, labels=["low X (away luckier)", "middle", "high X (home luckier)"]),
                     move=move)
        out["thirds"] = {str(k): {"n": len(g), "mean X": round(float(g["X"].mean()), 1),
                                  "mean line move (home margin)": round(float(g["move"].mean()), 2)}
                         for k, g in d.groupby("third", observed=True)}
    return out


# --------------------------------------------------------------------------------------------------- DK lookahead
DK_FIRST_SQL = """
WITH first_dk AS (
    SELECT DISTINCT ON (s.game_id) s.game_id, s.fetched_at, s.spread::float AS dk_spread, s.home_price, s.away_price
    FROM odds_snapshots s JOIN games g ON g.id = s.game_id
    WHERE s.book = 'draftkings' AND g.league = 'cfb' AND g.season = %(season)s AND s.spread IS NOT NULL
    ORDER BY s.game_id, s.fetched_at
)
SELECT d.*, g.start_time, (g.away_points - g.home_points)::float AS result, g.completed,
       (SELECT max(e.start_time) FROM games e
        WHERE e.league = 'cfb' AND e.season = g.season AND e.start_time < g.start_time
          AND (e.home_id IN (g.home_id, g.away_id) OR e.away_id IN (g.home_id, g.away_id))) + interval '8 hours' AS earliest,
       (SELECT p.our_spread::float FROM pick_log p
        WHERE p.game_id = d.game_id AND p.model_version = %(version)s
          AND p.recorded_at BETWEEN d.fetched_at AND d.fetched_at + interval '1 hour'
        ORDER BY p.recorded_at LIMIT 1) AS our_spread
FROM first_dk d JOIN games g ON g.id = d.game_id
"""


def dk_lookahead(season, version=MODEL_VERSION):
    d = query(DK_FIRST_SQL, {"season": season, "version": version})
    if d.empty:
        return {"games": 0}
    d["lookahead"] = d["earliest"].notna() & (d["fetched_at"] < d["earliest"])
    la = d[d["lookahead"] & d["our_spread"].notna()].copy()
    la["gap"] = la["our_spread"] - la["dk_spread"]
    big = la[(la["gap"].abs() >= 3) & la["completed"]].copy()
    side_home = big["gap"] < 0                         # our home-side spread lower = we like the home team more
    res = big["result"]
    big["outcome"] = np.where(res == big["dk_spread"], "push",
                              np.where(side_home & (res < big["dk_spread"]) | ~side_home & (res > big["dk_spread"]), "win", "loss"))
    price = np.where(side_home, big["home_price"], big["away_price"]).astype(float)
    big["units"] = np.select([big["outcome"] == "win", big["outcome"] == "loss"],
                             [np.where(price > 0, price / 100, 100 / -price), -1.0], 0.0)
    return {"games with a DK line": len(d), "first DK line was a lookahead": int(d["lookahead"].sum()),
            "lookahead with our line at that snapshot": len(la),
            "3+ gaps, finished, at DK's number and price": record(big["outcome"], big["units"])}


def report(season, version=MODEL_VERSION):
    p = bet_time_picks(season, version)
    if p.empty:
        return {"season": season, "version": version, "picks": 0}
    return {"season": season, "version": version, "bet-time picks": len(p),
            "line_moves": line_moves(p), "totals_agree": totals_agree(p, season, version),
            "weeknight": weeknight(p, season), "luck": luck(p, season), "dk_lookahead": dk_lookahead(season, version)}


if __name__ == "__main__":
    print(json.dumps(report(int(sys.argv[1])), indent=1, default=str))
