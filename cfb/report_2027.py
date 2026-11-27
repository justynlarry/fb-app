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
  nfl_tot_b1      NFL N-TOT-B1 (judged, plan-2027 8.3): Monday -> last median total move on nfl-v3's raw gap, B1 in
Conference tier (Holdout T) is added only if Holdout T is "supported" on December 7.
"""

import json
import sys

import numpy as np
import pandas as pd
from psycopg.rows import dict_row
from scipy.stats import norm
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


# ------------------------------------------------------------------------------- bettable lines at bet time, any side
# The bettable books, fixed as in 029_bettable_grading.sql (user, 2026-11-17), so a later edit of the bet-form setting
# can't change a past record.
BETTABLE_BOOKS = ["mybookieag", "draftkings", "fanduel", "betmgm", "williamhill_us", "fanatics"]

# Every bettable book's line in the snapshot each game's bet-time ('first') pick was made from: the latest snapshot
# saved at or before the pick, as in pick_results_bettable.
BET_TIME_LINES_SQL = """
SELECT f.game_id, s.book, s.spread::float, s.home_price, s.away_price, s.total::float, s.over_price, s.under_price
FROM pick_results f
JOIN games g ON g.id = f.game_id
JOIN LATERAL (SELECT max(s2.fetched_at) AS at
              FROM odds_snapshots s2
              WHERE s2.game_id = f.game_id AND s2.fetched_at <= f.recorded_at) snap ON true
JOIN odds_snapshots s ON s.game_id = f.game_id AND s.fetched_at = snap.at
WHERE f.taken = 'first' AND f.model_version = %(version)s AND g.season = %(season)s AND g.league = %(league)s
  AND s.book = ANY(%(books)s)
"""


def bet_time_lines(season, league, version):
    """Bettable books' lines at each game's bet time, one row per game and book."""
    return query(BET_TIME_LINES_SQL, {"season": season, "league": league, "version": version, "books": BETTABLE_BOOKS})


def best_bet(lines, side):
    """Best bettable (number, price) for one side among one game's lines: best number first, then best price.
    side: 'home' / 'away' (home-side spreads) or 'over' / 'under'.  None if no book has that market."""
    if side in ("home", "away"):
        col, price_col = "spread", "home_price" if side == "home" else "away_price"
    else:
        col, price_col = "total", "over_price" if side == "over" else "under_price"
    d = lines.dropna(subset=[col, price_col])                  # a book without that price can't be bet
    number, price = d[col], d[price_col]
    if side == "home":
        better = number         # home-side spreads: home wants +7 over +3
    elif side == "away":
        better = -number        # away wants -7 (away +7) over -3 (away +3)
    elif side == "over":
        better = -number        # over wants the lowest total
    else:
        better = number         # under wants the highest total
    if d.empty:
        return None
    order = pd.DataFrame({"better": better, "price": price}).sort_values(["better", "price"], ascending=False)
    i = order.index[0]
    return float(number[i]), int(price[i])


def grade(side, number, price, result, actual_total):
    """('win' / 'loss' / 'push', units) for one bet, graded like pick_results (result = away - home points)."""
    if side in ("home", "away"):
        if result == number:
            return "push", 0.0
        won = result < number if side == "home" else result > number
    else:
        if actual_total == number:
            return "push", 0.0
        won = actual_total > number if side == "over" else actual_total < number
    if not won:
        return "loss", -1.0
    return "win", price / 100 if price > 0 else 100 / -price


# ---------------------------------------------------------------- C-WX / N-WX: forecast weather and the totals move
# Thresholds as registered 2026-11-27 (model-tests.md, C-WX and N-WX): a game is tagged if its forecast at bet time
# meets any one of them (None = not used in that league).
WX_RULES = {"cfb": {"wind_mph": None, "gust_mph": 25, "precip_in": 0.1},
            "nfl": {"wind_mph": 15, "gust_mph": 25, "precip_in": 0.1}}
WX_BAR = {"cfb": 2.54, "nfl": 2.24}

# Open-air games with their bet-time and last pre-kickoff median totals and the forecast used:
#   college: the latest forecast fetched before the bet-time pick;
#   NFL: the forecast saved on the bet day (Monday); if it was fetched after bet time, the game is left out.
WX_GAMES_SQL = """
SELECT f.game_id, g.season_type, g.week, f.recorded_at, f.our_total::float,
       f.market_total::float AS bet_tmedian, l.market_total::float AS last_tmedian, f.actual_total,
       w.fetched_at AS wx_fetched_at, w.wind_mph::float, w.gust_mph::float, w.precip_in::float
FROM pick_results f
JOIN games g ON g.id = f.game_id
JOIN venues v ON v.id = g.venue_id
LEFT JOIN pick_results l ON l.game_id = f.game_id AND l.model_version = f.model_version AND l.taken = 'last'
LEFT JOIN LATERAL (
    SELECT w2.fetched_at, w2.wind_mph, w2.gust_mph, w2.precip_in
    FROM weather_forecasts w2
    WHERE w2.game_id = f.game_id
      AND CASE WHEN %(league)s = 'nfl'
               THEN w2.forecast_date = (f.recorded_at AT TIME ZONE 'UTC')::date
               ELSE w2.fetched_at < f.recorded_at END
    ORDER BY w2.fetched_at DESC
    LIMIT 1) w ON true
WHERE f.taken = 'first' AND f.model_version = %(version)s AND g.season = %(season)s AND g.league = %(league)s
  AND NOT v.dome
"""


def wx_tag(row, rules):
    """'tagged' / 'untagged', or why the game is left out ('no forecast', 'fetched after bet time')."""
    if pd.isna(row["wx_fetched_at"]):
        return "no forecast"
    if row["wx_fetched_at"] >= row["recorded_at"]:
        return "fetched after bet time"
    hit = any(limit is not None and pd.notna(row[col]) and row[col] >= limit for col, limit in rules.items())
    return "tagged" if hit else "untagged"


def cluster_diff(values, tagged, clusters, seed=2027, n_boot=2000):
    """Mean of values in tagged games minus the mean in untagged games, and its bootstrap SE resampling whole
    clusters (weeks), so games of the same week move together.  (None, None) if either group is empty."""
    v, t, c = np.asarray(values, float), np.asarray(tagged, bool), np.asarray(clusters)
    if not t.any() or t.all():
        return None, None
    def diff(i):
        return float(v[i][t[i]].mean() - v[i][~t[i]].mean())
    keys = np.unique(c)
    where = {k: np.where(c == k)[0] for k in keys}
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        i = np.concatenate([where[k] for k in rng.choice(keys, len(keys))])
        if t[i].any() and not t[i].all():          # a draw with no tagged (or no untagged) game can't give a difference
            boots.append(diff(i))
    return diff(np.arange(len(v))), float(np.std(boots))


def weather_totals(season, league, version):
    """C-WX (college) / N-WX (NFL), registered 2026-11-27.  Judged: mean total move (bet-time median -> last
    pre-kickoff median) in tagged minus untagged open-air games.  Reported: the under at the bettable number and price
    in tagged games, scoring against our total and the market, counts."""
    d = query(WX_GAMES_SQL, {"season": season, "league": league, "version": version})
    if d.empty:
        return {"games": 0}
    rules = WX_RULES[league]
    d["tag"] = d.apply(lambda row: wx_tag(row, rules), axis=1)
    out = {"left out": d.loc[~d["tag"].isin(["tagged", "untagged"]), "tag"].value_counts().to_dict()}
    d = d[d["tag"].isin(["tagged", "untagged"])].dropna(subset=["bet_tmedian", "last_tmedian"])
    d["move"] = d["last_tmedian"] - d["bet_tmedian"]
    d["week_key"] = d["season_type"] + d["week"].astype(str)

    # College is judged on the regular season (conference championships included); bowls and the CFP are reported
    if league == "cfb":
        groups = {"judged": d[d["season_type"] == "regular"], "bowls and CFP (reported)": d[d["season_type"] != "regular"]}
    else:
        groups = {"judged": d}

    lines = bet_time_lines(season, league, version)
    by_game = dict(tuple(lines.groupby("game_id")))
    for name, g in groups.items():
        tagged = g["tag"] == "tagged"
        res = {"tagged": int(tagged.sum()), "untagged": int((~tagged).sum()),
               "tagged by condition": {col: int((g.loc[tagged, col] >= limit).sum())
                                       for col, limit in rules.items() if limit is not None}}
        delta, se = cluster_diff(g["move"], tagged, g["week_key"])
        if delta is not None and se:
            res["Δ move, tagged − untagged (pts)"] = (f"{delta:+.2f} ± {se:.2f} ({delta / se:+.2f} SE; "
                                                       f"supported if ≤ −{WX_BAR[league]} SE)")
        # The under at the best bettable number and price at bet time, tagged games
        outcomes, units = [], []
        for row in g[tagged].itertuples():
            best = best_bet(by_game[row.game_id], "under") if row.game_id in by_game else None
            if best is None or pd.isna(row.actual_total):
                continue
            o, u = grade("under", best[0], best[1], None, row.actual_total)
            outcomes.append(o)
            units.append(u)
        res["under at the bettable number (tagged)"] = record(outcomes, units)
        # Scoring against our total and against the bet-time market total, tagged vs untagged
        done = g.dropna(subset=["actual_total"])
        done_tagged = done["tag"] == "tagged"
        for label, col in (("result − our total", "our_total"), ("result − bet-time total", "bet_tmedian")):
            diff = done["actual_total"] - done[col]
            res[f"mean {label} (pts)"] = {"tagged": round(float(diff[done_tagged].mean()), 2) if done_tagged.any() else None,
                                          "untagged": round(float(diff[~done_tagged].mean()), 2) if (~done_tagged).any() else None}
        out[name] = res
    return out


# ------------------------------------------------------------------- reversal check, both leagues (reported only)
# Registered 2026-11-27 (model-tests.md): Moskowitz (2021) finds about half of an NFL open -> close move reversed by
# the result.  Do the moves toward us hold up (information) or reverse (sentiment)?
REVERSAL_SQL = """
SELECT f.game_id, f.tier, f.side, f.total_side, f.result, f.actual_total,
       f.our_spread::float AS bet_ours, f.market_spread::float AS bet_line, f.market_total::float AS bet_tline,
       l.our_spread::float AS last_ours, l.market_spread::float AS last_line,
       l.our_total::float AS last_tours, l.market_total::float AS last_tline
FROM pick_results f
JOIN games g ON g.id = f.game_id
JOIN pick_results l ON l.game_id = f.game_id AND l.model_version = f.model_version AND l.taken = 'last'
WHERE f.taken = 'first' AND f.model_version = %(version)s AND g.season = %(season)s AND g.league = %(league)s
  AND f.result IS NOT NULL
"""


def fmt_slope(b, se):
    return None if b is None else f"{b:+.3f} ± {se:.3f}"


def reversal(season, league, version):
    """Reversal check: (1) result slope at the last pre-kickoff line on all games (≈ 0: our information was absorbed;
    < 0: we predict moves that reverse); (2) on our picks, the result after the move regressed on the move itself,
    in points for our side (≈ −0.5 = an ordinary market move that half reverses; ≈ 0 = information); (3) the same
    for totals picks."""
    d = query(REVERSAL_SQL, {"season": season, "league": league, "version": version})
    if d.empty:
        return {"games": 0}
    out = {}

    # 1. All games, at the last line before kickoff
    s = d.dropna(subset=["last_ours", "last_line"])
    b, se = slope_se(s["last_ours"] - s["last_line"], s["result"] - s["last_line"])
    out["spreads: result slope at the last line, all games"] = {"games": len(s), "slope": fmt_slope(b, se)}
    t = d.dropna(subset=["last_tours", "last_tline", "actual_total"])
    b, se = slope_se(t["last_tours"] - t["last_tline"], t["actual_total"] - t["last_tline"])
    out["totals: result slope at the last line, all games"] = {"games": len(t), "slope": fmt_slope(b, se)}

    # 2. Our spread picks: college Plays, NFL 3+ gaps at bet time
    if league == "cfb":
        picks, label = d[d["tier"] == "play"], "spreads: Plays"
    else:
        picks, label = d[(d["bet_ours"] - d["bet_line"]).abs() >= 3], "spreads: 3+ gaps at bet time"
    picks = picks.dropna(subset=["side", "bet_line", "last_line"])
    sgn = np.where(picks["side"] == "home", 1.0, -1.0)
    move = sgn * (picks["bet_line"] - picks["last_line"])      # points the line moved our way after bet time (CLV)
    after = sgn * (picks["last_line"] - picks["result"])       # our side's margin against the last line
    b, se = slope_se(move, after)
    out[label] = {"picks": len(picks), "mean move toward us (pts)": round(float(move.mean()), 2) if len(picks) else None,
                  "slope of result-after-move on the move": fmt_slope(b, se)}

    # 3. Our totals picks
    tp = d.dropna(subset=["total_side", "bet_tline", "last_tline", "actual_total"])
    o = np.where(tp["total_side"] == "over", 1.0, -1.0)
    move = o * (tp["last_tline"] - tp["bet_tline"])            # a rising total helps an over we already hold
    after = o * (tp["actual_total"] - tp["last_tline"])
    b, se = slope_se(move, after)
    out["totals picks"] = {"picks": len(tp), "mean move toward us (pts)": round(float(move.mean()), 2) if len(tp) else None,
                           "slope of result-after-move on the move": fmt_slope(b, se)}
    return out


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


# ------------------------------------------------------------------------------------------------- NFL N-TOT-B1
# plan-2027 section 8.3: (last pre-kickoff median total - bet-time median total) = a * (nfl-v3 raw total at bet time -
# bet-time median) + b * (NFL B1-total - bet-time median) + c.  Judged after the 2027 regular season: a >= 1.96 SE
# (season-week bootstrap, 2,000).  nfl-v3's raw line = its paper_predictions row in force at bet time (no overrides).
NFL_PICKS_SQL = """
SELECT f.game_id, f.recorded_at, g.season, g.week, g.season_type,
       f.market_total::float AS bet_tmedian, l.market_total::float AS last_tmedian,
       (SELECT pp.total::float FROM paper_predictions pp
        WHERE pp.game_id = f.game_id AND pp.model_version = 'nfl-v3' AND pp.created_at <= f.recorded_at
        ORDER BY pp.created_at DESC LIMIT 1) AS ours
FROM pick_results f
JOIN games g ON g.id = f.game_id
LEFT JOIN pick_results l ON l.game_id = f.game_id AND l.model_version = f.model_version AND l.taken = 'last'
WHERE f.taken = 'first' AND f.model_version = 'nfl-v3' AND g.season = %(season)s AND g.league = 'nfl'
"""


def nfl_tot_b1(season, seed=2027):
    from cfb import benchmark
    p = query(NFL_PICKS_SQL, {"season": season})
    if p.empty:
        return {"games": 0}
    G = benchmark.nfl_load(season - 1, season)
    b1 = {}
    for when, x in p.groupby("recorded_at"):
        for gid, (_, total) in benchmark.nfl_predictions(G, season, when, list(x["game_id"])).items():
            b1[gid] = total
    d = p.assign(b1=p["game_id"].map(b1)).dropna(subset=["ours", "b1", "bet_tmedian", "last_tmedian"]).reset_index(drop=True)
    out = {"bet-time picks": len(p), "games with all inputs": len(d)}
    if len(d) < 20:
        return out
    g, gb, mv = (d["ours"] - d["bet_tmedian"]).values, (d["b1"] - d["bet_tmedian"]).values, (d["last_tmedian"] - d["bet_tmedian"]).values
    def fit(i):
        X = np.column_stack([g[i], gb[i], np.ones(len(i))])
        return np.linalg.lstsq(X, mv[i], rcond=None)[0]
    cl = (d["season"].astype(str) + d["season_type"] + d["week"].astype(str)).values
    keys = np.unique(cl)
    where = {k: np.where(cl == k)[0] for k in keys}
    rng = np.random.default_rng(seed)
    boots = np.array([fit(np.concatenate([where[k] for k in rng.choice(keys, len(keys))])) for _ in range(2000)])
    a, b, _ = fit(np.arange(len(d)))
    out.update({"a (our gap, B1 in)": f"{a:+.4f} ± {boots[:, 0].std():.4f} ({a / boots[:, 0].std():+.2f} SE; bar 1.96)",
                "b (B1's gap)": f"{b:+.4f} ± {boots[:, 1].std():.4f}", "week clusters": len(keys)})
    return out


# -------------------------------------------------------------- C-CENS: Arscott's censoring rule, college totals
# Registered 2026-11-27 (model-tests.md, C-CENS).  The paper's numbers, frozen: Tobit SDs of each team's points around
# the score implied by the spread and total (Arscott 2023, Table 3), and the cut for betting the over.
SIGMA_DOG = 11.280
SIGMA_FAV = 11.941
CENS_CUT = 1.00            # bet the over when biasTotals > 1.00 (the stricter 1.75 is reported)

CENS_GAMES_SQL = """
SELECT f.game_id, f.actual_total, f.our_total::float
FROM pick_results f
JOIN games g ON g.id = f.game_id
WHERE f.taken = 'first' AND f.model_version = %(version)s AND g.season = %(season)s AND g.league = 'cfb'
  AND f.actual_total IS NOT NULL
"""


def censoring_bias(mu, sigma):
    """How much a floor at zero raises a team's expected points: E[max(0, X)] - mu for X ~ Normal(mu, sigma)."""
    return sigma * norm.pdf(mu / sigma) - mu * norm.cdf(-mu / sigma)


def bias_totals(spread, total):
    """Arscott's biasTotals (Eq. 13) from a spread (either sign) and a total."""
    s = abs(spread)
    dog = (total - s) / 2          # underdog's implied points (Eq. 6)
    fav = dog + s                  # favourite's implied points (Eq. 7)
    return censoring_bias(fav, SIGMA_FAV) + censoring_bias(dog, SIGMA_DOG)


def censoring(season, version):
    """C-CENS at bet time: the median of the bettable books' spread and total gives biasTotals; the over is graded at
    the best bettable number and price.  Stage 2 is a sign check (win % > 50) if Stage 1 passed; otherwise the same
    numbers are reported only."""
    games = query(CENS_GAMES_SQL, {"season": season, "version": version})
    if games.empty:
        return {"games": 0}
    lines = bet_time_lines(season, "cfb", version)
    by_game = dict(tuple(lines.groupby("game_id")))
    rows = []
    for g in games.itertuples():
        if g.game_id not in by_game:
            continue
        book_lines = by_game[g.game_id]
        spread, total = book_lines["spread"].median(), book_lines["total"].median()
        if pd.isna(spread) or pd.isna(total) or spread == 0:      # no line, or no underdog
            continue
        bias = bias_totals(spread, total)
        if bias <= CENS_CUT:
            continue
        best = best_bet(book_lines, "over")
        if best is None:
            continue
        outcome, units = grade("over", best[0], best[1], None, g.actual_total)
        rows.append({"bias": bias, "outcome": outcome, "units": units, "total": total,
                     "ours": g.our_total, "actual": g.actual_total})
    d = pd.DataFrame(rows)
    if d.empty:
        return {"games": len(games), "qualifying": 0}
    strict = d[d["bias"] > 1.75]
    return {"games": len(games), "qualifying (biasTotals > 1.00)": len(d),
            "over at the bettable number": record(d["outcome"], d["units"]),
            "over, biasTotals > 1.75": record(strict["outcome"], strict["units"]),
            "mean our total − market total (pts)": round(float((d["ours"] - d["total"]).mean()), 2),
            "mean result − our total (pts)": round(float((d["actual"] - d["ours"]).mean()), 2)}


def report(season, version=MODEL_VERSION):
    p = bet_time_picks(season, version)
    if p.empty:
        return {"season": season, "version": version, "picks": 0}
    return {"season": season, "version": version, "bet-time picks": len(p),
            "line_moves": line_moves(p), "totals_agree": totals_agree(p, season, version),
            "weeknight": weeknight(p, season), "luck": luck(p, season), "dk_lookahead": dk_lookahead(season, version),
            "nfl_tot_b1": nfl_tot_b1(season),
            "weather_cfb": weather_totals(season, "cfb", version),
            "weather_nfl": weather_totals(season, "nfl", "nfl-v3"),
            "reversal_cfb": reversal(season, "cfb", version),
            "reversal_nfl": reversal(season, "nfl", "nfl-v3"),
            "censoring": censoring(season, version)}


if __name__ == "__main__":
    print(json.dumps(report(int(sys.argv[1])), indent=1, default=str))
