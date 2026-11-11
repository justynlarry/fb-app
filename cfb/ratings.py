"""Opponent-adjusted team ratings.

A team's EPA per play in a game depends on how good the opposing defense was and
where the game was played. Ridge regression untangles that:
    metric = offense strength + defense strength + home edge (+ FCS adjustment)
"""

import pandas as pd
from psycopg.rows import dict_row
from sklearn.linear_model import Ridge

from cfb.db import connect

METRICS = ["epa_per_play", "success_rate", "explosiveness", "pass_epa", "rush_epa", "plays", "points"]
ALPHA = 2.0         # Ridge shrinkage. ~2 average games pulling each team toward average
PRIOR_WEEKS = 6     # Last season's games fade out over this many weeks


# One row per team per game (that team's offense). FBS and FCS games only.
GAME_STATS_SQL = """
SELECT s.team_id,
       s.opponent_id,
       g.week,
       g.season_type,
       s.plays,
       s.epa_per_play, s.success_rate, s.explosiveness, s.pass_epa, s.rush_epa,
       CASE WHEN s.team_id = g.home_id THEN g.home_points
            ELSE g.away_points END AS points,
       CASE WHEN g.neutral_site THEN 0
            WHEN s.team_id = g.home_id THEN 1
            ELSE -1 END AS home,
       CASE WHEN s.team_id = g.home_id THEN g.home_classification
            ELSE g.away_classification END = 'fcs' AS fcs_offense,
       CASE WHEN s.team_id = g.home_id THEN g.away_classification
            ELSE g.home_classification END = 'fcs' AS fcs_defense
FROM team_game_stats s
JOIN games g ON g.id = s.game_id
WHERE g.league = 'cfb'
  AND g.season = %(season)s
  AND g.start_time < %(before)s
  AND g.home_classification IN ('fbs', 'fcs')
  AND g.away_classification IN ('fbs', 'fcs')
"""


def load_game_stats(season, before):
    """Every FBS/FCS team-game in a season that kicked off before 'before' (a datetime)."""
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(GAME_STATS_SQL, {"season": season, "before": before}).fetchall()
    return pd.DataFrame(rows)


def fit_ratings(df, metric, alpha=ALPHA):
    """Fit adjusted ratings for one metric.

    Returns (ratings, home_edge).  ratings has one row per team id with:
      off = expected metric for this offense vs. an average FBS defense, neutral field
      def = expected metric this defense allows to an average FBS offense
    """
    # One column per team as offense, one per team as defense (1 = this row's team)
    offense = pd.get_dummies(df["team_id"], prefix="off")
    defense = pd.get_dummies(df["opponent_id"], prefix="def")
    extras = df[["home", "fcs_offense", "fcs_defense"]]
    X = pd.concat([offense, defense, extras], axis=1).astype(float)
    y = df[metric].astype(float)

    # Games with more plays tell us more. Scale so the average game counts as 1
    weights = df["plays"] / df["plays"].mean() * df["weight"]

    model = Ridge(alpha=alpha)
    model.fit(X, y, sample_weight=weights)
    coefs = pd.Series(model.coef_, index=X.columns)

    # Pull the team coefficients back out, keyed by team id
    off = coefs.filter(regex="^off_")
    off.index = off.index.str.removeprefix("off_").astype(int)
    dfn = coefs.filter(regex="^def_")
    dfn.index = dfn.index.str.removeprefix("def_").astype(int)

    # FCS teams also get the FCS-wide adjustment
    fcs_teams = set(df.loc[df["fcs_offense"], "team_id"])
    is_fcs = pd.Series(off.index.isin(fcs_teams), index=off.index)

    ratings = pd.DataFrame({
        "off": model.intercept_ + off + is_fcs * coefs["fcs_offense"],
        "def": model.intercept_ + dfn + is_fcs * coefs["fcs_defense"],
    })
    return ratings, coefs["home"]


# A regular-season week counts as played once its LAST game has kicked off
WEEKS_PLAYED_SQL = """
SELECT count(*)
FROM (
    SELECT week
    FROM games
    WHERE league = 'cfb'
      AND season = %(season)s
      AND season_type = 'regular'
    GROUP BY week
    HAVING max(start_time) < %(before)s
) AS finished_weeks
"""


def count_weeks_played(season, before):
    """How many regular-season weeks were completely finished before 'before'."""
    with connect() as conn:
        return conn.execute(WEEKS_PLAYED_SQL, {"season": season, "before": before}).fetchone()[0]


def ratings_as_of(season, before):
    """Rate every team using only games that kicked off before 'before'.

    Early in a season there's little data, so last season's games are mixed in with
    a weight that fades from 1 to 0 over PRIOR_WEEKS weeks.
    Returns (ratings, weeks_played). ratings has columns off_<metric>, def_<metric>.
    """
    parts = []
    weeks_played = count_weeks_played(season, before)
    current = load_game_stats(season, before)
    if len(current) > 0:
        current["weight"] = 1.0
        parts.append(current)

    fade = max(0.0, 1 - weeks_played / PRIOR_WEEKS)
    if fade > 0:
        last_season = load_game_stats(season - 1, before)
        last_season["weight"] = fade
        parts.append(last_season)
    history = pd.concat(parts, ignore_index=True)

    ratings = pd.DataFrame()
    for metric in METRICS:
        r, home_edge = fit_ratings(history, metric)
        ratings["off_" + metric] = r["off"]
        ratings["def_" + metric] = r["def"]
    return ratings, weeks_played
