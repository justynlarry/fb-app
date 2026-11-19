"""NFL points model.  Same idea as cfb/model.py:  rate each team's offense and defense from
its games, then turn the two teams' ratings into a predicted score for each side.

Everything NFL-specific lives here.  The ratings come from cfb/ratings.py with league='nfl'.
Player adjustments (starting QB, injured players) will be added as extra feature columns.
"""

import math

import pandas as pd
from psycopg.rows import dict_row
from sklearn.linear_model import LinearRegression

from cfb.db import connect
from cfb.nfl_qbs import add_qb_features
from cfb.ratings import METRICS, ratings_as_of

LEAGUE = "nfl"
MODEL_VERSION = "nfl-v3"
# Full matchup (T-MATCH, model-tests.md section 9): team's own defense and the opponent's offense
MATCH_FEATURES = ["def_" + m for m in METRICS] + ["oppoff_" + m for m in METRICS]
FIRST_SEASON = 2016         # first season with NFL stats in team_game_stats
NO_CROWD_SEASONS = {2020}   # used for ratings, but not to train the points model

V1_FEATURES = ["off_" + m for m in METRICS] + ["oppdef_" + m for m in METRICS] + ["home"]
QB_FEATURES = ["qb_adj", "opp_qb_adj"]      # starting-QB adjustment (T-QB, model-tests.md section 9)
FEATURES = V1_FEATURES + QB_FEATURES + MATCH_FEATURES
# Paper models (plan-2027 section 8.3): each version's columns.  nfl-v2 = nfl-v3 without the matchup rows (reported).
VERSION_FEATURES = {
    "nfl-v3": FEATURES,
    "nfl-v2": V1_FEATURES + QB_FEATURES,
}
# Chosen 2026-11-16 by choose_settings() on 2017-19 (model-tests.md section 9). Frozen: don't re-tune.
SETTINGS = {"half_life": 6, "last_weight": 0.5, "prior_weeks": 12}

# Every regular-season and playoff game in one season
SEASON_GAMES_SQL = """
SELECT id AS game_id, season, week, season_type, start_time, neutral_site,
    home_id, away_id, home_points, away_points
FROM games
WHERE league = 'nfl'
  AND season = %(season)s
  AND season_type IN ('regular', 'postseason')
ORDER BY start_time
"""


def load_season_games(season):
    """Every NFL game in one season, earliest first."""
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(SEASON_GAMES_SQL, {"season": season}).fetchall()
    return pd.DataFrame(rows)


def rating_args(settings):
    """Turn {"half_life", "last_weight", "prior_weeks"} into ratings_as_of() arguments."""
    half_life = settings["half_life"]
    return {
        "league": LEAGUE,
        "half_life": half_life,
        "prior_weeks": settings["prior_weeks"],
        # a game this many weeks old has weight last_weight
        "offseason_age": half_life * math.log2(1 / settings["last_weight"]),
    }


def side_row(game, team, opponent, home, points, ratings, weeks_played):
    """One team's row:  its offense and defense ratings, and the opponent's defense and offense ratings."""
    row = {
        "game_id": game["game_id"],
        "season": game["season"],
        "team_id": team,
        "opponent_id": opponent,
        "is_home": team == game["home_id"],
        "home": home,
        "points": points,
        "week": game["week"],
        "weeks_played": weeks_played,
    }
    for m in METRICS:
        row["off_" + m] = ratings.at[team, "off_" + m]
        row["oppdef_" + m] = ratings.at[opponent, "def_" + m]
        row["def_" + m] = ratings.at[team, "def_" + m]          # this team's own defense
        row["oppoff_" + m] = ratings.at[opponent, "off_" + m]   # this opponent's offense
    return row


def season_rows(season, settings):
    """Walk-forward feature rows for every game in a season (two rows per game).

    Each week's teams are rated using only games that kicked off before that week's
    first game, so no game ever sees its own result.
    """
    games = load_season_games(season)
    rows = []
    for _, week_games in games.groupby(["season_type", "week"]):
        cutoff = week_games["start_time"].min()
        if season == FIRST_SEASON and cutoff == games["start_time"].min():
            continue    # First week of our data:  nothing to rate teams on yet
        ratings, weeks_played = ratings_as_of(season, cutoff, **rating_args(settings))
        for _, g in week_games.iterrows():
            if g["home_id"] not in ratings.index or g["away_id"] not in ratings.index:
                continue        # a team with no games to rate yet
            home_flag = 0 if g["neutral_site"] else 1
            rows.append(side_row(g, g["home_id"], g["away_id"], home_flag,
                                 g["home_points"], ratings, weeks_played))
            rows.append(side_row(g, g["away_id"], g["home_id"], -home_flag,
                                 g["away_points"], ratings, weeks_played))
    return pd.DataFrame(rows)


# ------ ------ Training and Predictions ------ ------


def train(rows, features=FEATURES):
    """Fit the points model on rows with a final score, leaving out seasons without crowds."""
    known = rows.dropna(subset=["points"])
    known = known[~known["season"].isin(NO_CROWD_SEASONS)]
    model = LinearRegression()
    model.fit(known[features].astype(float), known["points"].astype(float))
    return model


def predict_games(model, rows, features=FEATURES):
    """One row per game:  both teams' predicted points, our spread (home side) and total.

    Also keeps the actual score, so the backtest can measure the miss.
    """
    rows = rows.copy()
    rows["pred"] = model.predict(rows[features].astype(float))
    home = rows[rows["is_home"]].set_index("game_id")
    away = rows[~rows["is_home"]].set_index("game_id")
    games = pd.DataFrame({
        "season": home["season"],
        "weeks_played": home["weeks_played"],
        "home_pred": home["pred"],
        "away_pred": away["pred"],
        "home_points": home["points"],
        "away_points": away["points"],
    })
    games["spread"] = games["away_pred"] - games["home_pred"]       # Negative = home favored, like lines
    games["total"] = games["home_pred"] + games["away_pred"]
    return games


def build_rows(settings, first_season, last_season, with_qbs=True):
    """Walk-forward rows for every season from first_season to last_season."""
    rows = pd.concat(
        [season_rows(s, settings) for s in range(first_season, last_season + 1)],
        ignore_index=True,
    )
    if with_qbs:
        rows = add_qb_features(rows, settings)
        rows[QB_FEATURES] = rows[QB_FEATURES].fillna(0.0)    # no known starter: no adjustment
    return rows


def walk_forward(rows, seasons, features=FEATURES):
    """Predict each season with a model trained only on earlier seasons."""
    parts = []
    for season in seasons:
        model = train(rows[rows["season"] < season], features)
        parts.append(predict_games(model, rows[rows["season"] == season], features))
    return pd.concat(parts)


def spread_mae(games):
    """Average miss of our spread, over games with a final score."""
    done = games.dropna(subset=["home_points", "away_points"])
    actual = done["away_points"] - done["home_points"]
    return float((actual - done["spread"]).abs().mean())


def save_predictions(games, is_backtest, version=MODEL_VERSION):
    """Save one row per game in the predictions table (same table as college).

    A backtest replay never overwrites a real pre-game prediction:  the WHERE on the
    update only lets a backtest row replace another backtest row.
    """
    with connect() as conn:
        for game_id, g in games.iterrows():
            conn.execute(
                """
                INSERT INTO predictions (game_id, model_version, home_points, away_points,
                                         spread, total, weeks_played, is_backtest)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id, model_version) DO UPDATE SET
                    home_points  = EXCLUDED.home_points,
                    away_points  = EXCLUDED.away_points,
                    spread       = EXCLUDED.spread,
                    total        = EXCLUDED.total,
                    weeks_played = EXCLUDED.weeks_played,
                    is_backtest  = EXCLUDED.is_backtest,
                    created_at   = now()
                WHERE predictions.is_backtest OR NOT EXCLUDED.is_backtest
                """,
                (
                    int(game_id),
                    version,
                    round(float(g["home_pred"]), 2),
                    round(float(g["away_pred"]), 2),
                    round(float(g["spread"]), 2),
                    round(float(g["total"]), 2),
                    int(g["weeks_played"]),
                    is_backtest,
                ),
            )
    return len(games)


# ------ ------ Settings search (model-tests.md, section 9) ------ ------


GRID = [
    {"half_life": h, "last_weight": w, "prior_weeks": p}
    for h in (4, 6, 8, 12)
    for w in (0.25, 0.5, 0.75)
    for p in (4, 8, 12)
]
TUNE_SEASONS = range(2017, 2020)        # Chosen on these only; 2021-2025 are for judging


def choose_settings():
    """Try every setting on 2017-2019 and return the one with the lowest spread miss.

    A tie (same miss to 3 decimals) goes to the longer half-life, as pre-registered.
    """
    results = []
    for settings in GRID:
        rows = build_rows(settings, FIRST_SEASON, max(TUNE_SEASONS), with_qbs=False)
        mae = spread_mae(walk_forward(rows, TUNE_SEASONS, V1_FEATURES))
        results.append((round(mae, 3), -settings["half_life"], settings))
        print(f" {settings}: spread miss {mae:.3f}")
    results.sort(key=lambda r: (r[0], r[1]))
    best = results[0][2]
    print(f"chosen: {best} (spread miss {results[0][0]:.3f})")
    return best


def backtest(first_season=2017, last_season=2025):
    """Walk-forward backtest with the frozen SETTINGS:  each season predicted by a model
    trained only on earlier seasons.  2020 is stored but never used for judging.
    """
    print("building NFL walk-forward rows...")
    rows = build_rows(SETTINGS, FIRST_SEASON, last_season)
    games = walk_forward(rows, range(first_season, last_season + 1))
    saved = save_predictions(games, is_backtest=True)
    print(f"{saved} NFL games saved as {MODEL_VERSION} backtest predictions")
    print(f"spread miss, 2021-2025: {spread_mae(games[games['season'] >= 2021]):.3f}")


def upcoming_game_ids(season):
    """This season's NFL games that haven't kicked off."""
    with connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT id FROM games WHERE league = 'nfl' AND season = %s AND start_time > now()",
                (season,),
            ).fetchall()
        }


def season_rows_through(season):
    """Every season's rows up to this one with the frozen SETTINGS (about a minute).  Built once each morning and
    shared by the live prediction and the NFL paper models."""
    print("building NFL rows (about a minute)...")
    return build_rows(SETTINGS, FIRST_SEASON, season)


def upcoming_predictions(rows, season, version=MODEL_VERSION):
    """Train this version on every finished game and predict the season's games that haven't kicked off
    (one row per game, as predict_games)."""
    features = VERSION_FEATURES[version]
    model = train(rows, features)       # train() skips games without a final score, and 2020
    upcoming = rows[rows["game_id"].isin(upcoming_game_ids(season))]
    return predict_games(model, upcoming, features)


def predict_upcoming(season, rows=None):
    """Train on every finished game and save predictions for this season's games that haven't kicked off.

    Re-running updates those predictions.  Once a game kicks off it's no longer upcoming, so its
    last pre-game prediction stays as the permanent record. Games without a projected starter
    get no QB adjustment (qb_adj = 0).  Pass rows (from season_rows_through) to reuse rows already built.
    """
    if rows is None:
        rows = season_rows_through(season)
    saved = save_predictions(upcoming_predictions(rows, season), is_backtest=False)
    print(f"{saved} upcoming NFL games predicted ({MODEL_VERSION})")
    return saved
