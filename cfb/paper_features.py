"""Extra feature columns for two 2027 paper models (docs/model-tests.md H-T4 and H-T2b). Never used for a pick.

    v6-ht4   v6 + the P1-T4 cached-stats batch: 8 more CFBD advanced stats, opponent-adjusted exactly like the
             v5 ratings (same weights, same ridge), as off_<stat> and oppdef_<stat> columns (add_t4_columns).
    v6-ht2b  v6 with all 7 metrics' ratings from a state-space (Kalman) filter instead of the weekly ridge, at the
             T2(b) parameters frozen on 2026-11-18 (state_space_rows).  The T1 matchup columns are rebuilt from them.

Both are ports of the research scripts that were judged (round 1 plan1/t1t4.py, 2026-11-17; t2b.py, 2026-11-18),
checked column for column against them.  Neither uses market lines; neither changes anything the live model reads.
"""

import numpy as np
import pandas as pd

import cfb.ratings as R
from cfb.db import connect

# cfb.model is imported inside the functions: cfb.model reads T4_FEATURES from here.

# ---------------------------------------------------------------------------------------------------------- T4
# The 8 stats, as named in CFBD's /stats/game/advanced 'offense' object (already cached daily, 0 extra calls)
T4_STATS = {
    "line_yards": "lineYards",
    "stuff_rate": "stuffRate",
    "power_success": "powerSuccess",
    "second_level": "secondLevelYards",
    "open_field": "openFieldYards",
    "std_down_sr": "standardDowns.successRate",
    "pass_down_sr": "passingDowns.successRate",
    "pass_down_ppa": "passingDowns.ppa",
}
T4_FEATURES = ["off_" + s for s in T4_STATS] + ["oppdef_" + s for s in T4_STATS]

TEAM_GAMES_SQL = """
SELECT s.game_id, s.team_id, s.opponent_id, g.season, g.week, g.season_type, g.start_time, s.plays,
       CASE WHEN g.neutral_site THEN 0 WHEN s.team_id = g.home_id THEN 1 ELSE -1 END AS home,
       COALESCE(CASE WHEN s.team_id = g.home_id THEN g.home_classification
                     ELSE g.away_classification END = 'fcs', false) AS fcs_offense,
       COALESCE(CASE WHEN s.team_id = g.home_id THEN g.away_classification
                     ELSE g.home_classification END = 'fcs', false) AS fcs_defense
FROM team_game_stats s
JOIN games g ON g.id = s.game_id
WHERE g.league = 'cfb'
  AND g.home_classification IN ('fbs', 'fcs')
  AND g.away_classification IN ('fbs', 'fcs')
"""

# The latest stored /stats/game/advanced response per season (garbage time excluded)
ADVANCED_SQL = """
SELECT DISTINCT ON (params->>'year') (params->>'year')::int, body
FROM api_responses
WHERE source = 'cfbd'
  AND endpoint = '/stats/game/advanced'
  AND params->>'excludeGarbageTime' = 'true'
ORDER BY params->>'year', fetched_at DESC
"""


def dig(d, path):
    """d['a']['b'] for path 'a.b', or None if any step is missing."""
    for key in path.split("."):
        if not isinstance(d, dict) or key not in d:
            return None
        d = d[key]
    return d


def t4_team_games():
    """Every college team-game with the 8 T4 stats for that team's offense (None where CFBD has none)."""
    with connect() as conn:
        advanced = conn.execute(ADVANCED_SQL).fetchall()
        game_ids = dict(conn.execute("SELECT cfbd_id, id FROM games WHERE league = 'cfb' AND cfbd_id IS NOT NULL").fetchall())
        team_ids = dict(conn.execute("SELECT school, id FROM teams WHERE league = 'cfb'").fetchall())
        tg = pd.read_sql(TEAM_GAMES_SQL, conn)
    records = []
    for _, body in advanced:
        for entry in body:
            game_id, team_id = game_ids.get(entry.get("gameId")), team_ids.get(entry.get("team"))
            if game_id is None or team_id is None:
                continue
            record = {"game_id": game_id, "team_id": team_id}
            for stat, path in T4_STATS.items():
                record[stat] = dig(entry.get("offense", {}), path)
            records.append(record)
    stats = pd.DataFrame(records, columns=["game_id", "team_id"] + list(T4_STATS)).drop_duplicates(["game_id", "team_id"])
    return tg.merge(stats, on=["game_id", "team_id"], how="left")


def weeks_played(regular, season, before):
    """Regular-season weeks whose last game kicked off before 'before' (as ratings.count_weeks_played)."""
    weeks = regular[regular["season"] == season]
    return int((weeks.groupby("week")["start_time"].max() < before).sum())


def t4_ratings(tg, regular, season, before):
    """{stat: ratings} using only team-games before 'before', weighted exactly like ratings.ratings_as_of."""
    wp = weeks_played(regular, season, before)
    current = tg[(tg["season"] == season) & (tg["start_time"] < before)].copy()
    week = current["week"].where(current["season_type"] == "regular", wp)
    current["weight"] = 0.5 ** ((wp - week).clip(lower=0) / R.RECENCY_HALF_LIFE)
    parts = [current]
    fade = max(0.0, 1 - wp / R.PRIOR_WEEKS)
    if fade > 0:
        last = tg[tg["season"] == season - 1].copy()
        if len(last):
            last["weight"] = fade * 0.5 ** (R.OFFSEASON_AGE_WEEKS / R.RECENCY_HALF_LIFE)
            parts.append(last)
    history = pd.concat(parts, ignore_index=True)
    out = {}
    for stat in T4_STATS:
        h = history.dropna(subset=[stat]).copy()
        h[stat] = h[stat].astype(float)
        out[stat], _ = R.fit_ratings(h, stat)
    return out


def add_t4_columns(rows):
    """rows (from model.build_rows) plus the 16 T4 columns, each week rated from games before its first kickoff."""
    from cfb.model import load_season_games
    tg = t4_team_games()
    with connect() as conn:
        regular = pd.read_sql("SELECT season, week, start_time FROM games WHERE league = 'cfb' AND season_type = 'regular'", conn)
    games = pd.concat([load_season_games(s) for s in sorted(rows["season"].unique())])
    keyed = []
    for (season, _, _), week_games in games.groupby(["season", "season_type", "week"]):
        sub = rows[rows["game_id"].isin(week_games["game_id"])][["game_id", "team_id", "opponent_id"]].copy()
        if sub.empty:
            continue
        ratings = t4_ratings(tg, regular, season, week_games["start_time"].min())
        for stat in T4_STATS:
            r = ratings[stat]
            sub["off_" + stat] = sub["team_id"].map(r["off"]).fillna(r["off"].mean())
            sub["oppdef_" + stat] = sub["opponent_id"].map(r["def"]).fillna(r["def"].mean())
        keyed.append(sub)
    return rows.merge(pd.concat(keyed), on=["game_id", "team_id", "opponent_id"], how="left")


# -------------------------------------------------------------------------------------------------------- T2(b)
# Frozen 2026-11-18 (model-tests.md H-T2b): per metric (q weekly drift, p0 preseason variance, rho offseason carry-over)
STATE_PARAMS = {
    "epa_per_play": (0.005, 0.15, 0.8),
    "success_rate": (0.005, 0.15, 0.8),
    "explosiveness": (0.001, 0.05, 0.6),
    "pass_epa": (0.001, 0.15, 0.6),
    "rush_epa": (0.005, 0.05, 0.8),
    "plays": (0.005, 0.05, 0.6),
    "points": (0.005, 0.15, 0.8),
}
FIRST_SEASON = 2016             # the filter starts here; its scales come from 2016-2020, as in the judged run
N_GLOBALS = 4                   # league average, home edge, FCS offense, FCS defense

STATE_TEAM_GAMES_SQL = """
SELECT s.game_id, s.team_id, s.opponent_id, g.season, g.week, g.season_type, g.start_time, s.plays,
       s.epa_per_play, s.success_rate, s.explosiveness, s.pass_epa, s.rush_epa,
       CASE WHEN s.team_id = g.home_id THEN g.home_points ELSE g.away_points END AS points,
       CASE WHEN g.neutral_site THEN 0 WHEN s.team_id = g.home_id THEN 1 ELSE -1 END AS home,
       COALESCE(CASE WHEN s.team_id = g.home_id THEN g.home_classification
                     ELSE g.away_classification END = 'fcs', false) AS fcs_offense,
       COALESCE(CASE WHEN s.team_id = g.home_id THEN g.away_classification
                     ELSE g.home_classification END = 'fcs', false) AS fcs_defense
FROM team_game_stats s
JOIN games g ON g.id = s.game_id
WHERE g.league = 'cfb'
  AND g.season BETWEEN %(first)s AND %(last)s
  AND g.home_classification IN ('fbs', 'fcs')
  AND g.away_classification IN ('fbs', 'fcs')
"""


def state_team_games(last_season):
    """Team-games 2016..last_season with each week block numbered in kickoff order."""
    with connect() as conn:
        tg = pd.read_sql(STATE_TEAM_GAMES_SQL, conn, params={"first": FIRST_SEASON, "last": last_season})
    tg = tg.dropna(subset=["plays"])
    tg["plays_w"] = tg["plays"] / tg[tg["season"].between(2016, 2020)]["plays"].mean()      # like v5's play weights
    blocks = (tg.groupby(["season", "season_type", "week"])["start_time"].min().reset_index()
              .sort_values(["season", "start_time"]))
    blocks["b"] = range(len(blocks))
    tg = tg.merge(blocks[["season", "season_type", "week", "b"]], on=["season", "season_type", "week"])
    return tg.reset_index(drop=True), blocks


class StateFilter:
    """One metric's ratings as a Kalman filter: every team's offense and defense drift a little each week, are
    pulled toward average between seasons, and each team-game updates them, weighted by its plays."""

    def __init__(self, tg, teams, metric):
        self.q, self.p0, self.rho = STATE_PARAMS[metric]
        self.n = len(teams)
        self.size = N_GLOBALS + 2 * self.n
        self.scale = float(tg[tg["season"].between(2016, 2020)][metric].std())
        self.z = (tg[metric] / self.scale).values
        self.x = np.zeros(self.size)
        self.P = np.zeros((self.size, self.size))
        self.x[0] = float(np.nanmean(self.z[tg["season"].values == FIRST_SEASON]))
        self.P[0, 0] = self.P[1, 1] = self.P[2, 2] = self.P[3, 3] = 1.0
        self.team_diag = np.arange(N_GLOBALS, self.size)
        self.P[self.team_diag, self.team_diag] = self.p0
        self.seen = np.zeros(self.n, bool)

    def new_season(self):
        """Offseason: shrink every team toward average, add preseason uncertainty, reset teams never seen."""
        carry = np.ones(self.size)
        carry[N_GLOBALS:] = self.rho
        self.x *= carry
        self.P *= np.outer(carry, carry)
        self.P[self.team_diag, self.team_diag] += self.p0
        for k in np.where(~np.r_[self.seen, self.seen])[0]:
            i = N_GLOBALS + k
            self.P[i, :] = 0
            self.P[:, i] = 0
            self.P[i, i] = self.p0
            self.x[i] = 0

    def new_week(self):
        """A week passes: ratings get less certain (drift)."""
        self.P[self.team_diag, self.team_diag] += self.q
        self.P[np.arange(N_GLOBALS), np.arange(N_GLOBALS)] += self.q / 100

    def ratings(self, fcs_teams, teams):
        """(offense, defense) arrays in the metric's own units, FCS teams with the FCS adjustment."""
        mu = self.x[0]
        off = self.x[N_GLOBALS:N_GLOBALS + self.n] + mu
        dfn = self.x[N_GLOBALS + self.n:] + mu
        is_fcs = np.array([t in fcs_teams for t in teams])
        return (off + is_fcs * self.x[2]) * self.scale, (dfn + is_fcs * self.x[3]) * self.scale

    def update(self, games):
        """Learn from one week block's team-games."""
        n = self.n
        for oi, dj, home, fo, fd, z, w in zip(games["oi"].values, games["dj"].values, games["home"].values,
                                              games["fcs_offense"].values, games["fcs_defense"].values,
                                              self.z[games.index.values], games["plays_w"].values):
            if np.isnan(z):
                continue
            idx = np.array([0, 1, 2, 3, N_GLOBALS + oi, N_GLOBALS + n + dj])
            v = np.array([1.0, home, float(fo), float(fd), 1.0, 1.0])
            PH = self.P[:, idx] @ v
            S = v @ PH[idx] + 1.0 / w
            K = PH / S
            self.x += K * (z - v @ self.x[idx])
            self.P -= np.outer(K, PH)
        self.seen[np.unique(games["oi"].values)] = True
        self.seen[np.unique(games["dj"].values)] = True


def state_space_ratings(last_season):
    """For every metric: {block key (season, season_type, week): (off, def)} = the ratings before that block's games,
    plus 'next' = the ratings after the last block played (for weeks with no games played yet).  Also returns teams."""
    tg, blocks = state_team_games(last_season)
    teams = sorted(set(tg["team_id"]) | set(tg["opponent_id"]))
    index = {t: k for k, t in enumerate(teams)}
    tg["oi"] = tg["team_id"].map(index)
    tg["dj"] = tg["opponent_id"].map(index)
    fcs_by_season = {s: set(tg[tg["season"].isin([s, s - 1]) & tg["fcs_offense"]]["team_id"])
                     for s in range(FIRST_SEASON, last_season + 2)}
    by_block = {b: g for b, g in tg.groupby("b")}
    out = {}
    for metric in R.METRICS:
        f = StateFilter(tg, teams, metric)
        recorded = {}
        prev_season = None
        for block in blocks.itertuples():
            season = int(block.season)
            if prev_season is not None:
                if season != prev_season:
                    f.new_season()
                else:
                    f.new_week()
            prev_season = season
            recorded[(season, block.season_type, int(block.week))] = f.ratings(fcs_by_season[season], teams)
            f.update(by_block[block.b])
        recorded[("next", prev_season)] = f.ratings(fcs_by_season[prev_season], teams)
        if last_season > prev_season:   # a new season with no games played yet: apply the offseason step
            f.new_season()
            recorded[("next", last_season)] = f.ratings(fcs_by_season[last_season], teams)
        out[metric] = recorded
    return out, teams


def state_space_rows(rows):
    """rows (from model.build_rows, v6 columns) with the 7 metrics' off_/oppdef_ ratings from the state-space filter
    and the T1 matchup columns rebuilt from them.  Weeks not yet played use the ratings after the last block."""
    from cfb.model import add_match_columns
    with connect() as conn:
        week_of = {gid: (s, st, w) for gid, s, st, w in
                   conn.execute("SELECT id, season, season_type, week FROM games WHERE league = 'cfb'").fetchall()}
    last_season = int(rows["season"].max())
    ratings, teams = state_space_ratings(last_season)
    index = {t: k for k, t in enumerate(teams)}
    out = rows.drop(columns=[c for c in rows.columns if c.startswith(("def_", "oppoff_"))]).copy()
    keys = [week_of[g] for g in out["game_id"].values]
    for metric in R.METRICS:
        recorded = ratings[metric]
        off_col, def_col = [], []
        for key, team, opp in zip(keys, out["team_id"].values, out["opponent_id"].values):
            o, d = recorded.get(key) or recorded[("next", key[0])]
            off_col.append(o[index[team]] if team in index else np.nan)
            def_col.append(d[index[opp]] if opp in index else np.nan)
        out["off_" + metric] = off_col
        out["oppdef_" + metric] = def_col
    for metric in R.METRICS:        # a team with no games at all: league average of the column, as in the judged run
        out["off_" + metric] = out["off_" + metric].fillna(out["off_" + metric].mean())
        out["oppdef_" + metric] = out["oppdef_" + metric].fillna(out["oppdef_" + metric].mean())
    return add_match_columns(out)
