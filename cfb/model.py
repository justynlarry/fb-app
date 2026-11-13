"""Points model. Turns two teams' ratings into a predicted score for each side.

Each game becomes two rows, one per team: that team's offense ratings vs. the
opponent's defense ratings -> points that team scored. A linear regression learns
how ratings translate into points. Spread and total come from the two predictions.
"""

import pandas as pd
from psycopg.rows import dict_row
from sklearn.linear_model import LinearRegression

from cfb.db import connect
from cfb.priors import season_priors
from cfb.ratings import METRICS, ratings_as_of

MODEL_VERSION = "v5"

# Preseason inputs (from cfb/priors.py), faded out over the regular season
PRIOR_INPUTS = ["talent", "ret_ppa", "new_coach"]
PRIOR_INPUT_WEEKS = 16

# Mid-season head-coach changes (cfb/coaches.py fills history; current season entered by hand)
COACH_CHANGES_SQL = """
SELECT team_id, changed_at
FROM coach_changes
WHERE season = %(season)s
"""

FEATURES = (
    ["off_" + m for m in METRICS]
    + ["oppdef_" + m for m in METRICS]
    + ["home", "fcs_offense", "fcs_defense", "coach_change", "opp_coach_change"]
    + ["pr_" + p for p in PRIOR_INPUTS]
    + ["oppr_" + p for p in PRIOR_INPUTS]
)

# Games we predict: any game with an FBS team (FCS opponents allowed)
SEASON_GAMES_SQL = """
SELECT id AS game_id, season, week, season_type, start_time, neutral_site,
       home_id, away_id, home_points, away_points,
       home_classification, away_classification
FROM games
WHERE league = 'cfb'
    AND season = %(season)s
    AND home_classification IN ('fbs', 'fcs')
    AND away_classification IN ('fbs', 'fcs')
    AND 'fbs' IN (home_classification, away_classification)
ORDER BY start_time
"""


def load_season_games(season):
    """Every game in a season that involves an FBS team."""
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute(SEASON_GAMES_SQL, {"season": season}).fetchall()
    return pd.DataFrame(rows)


def side_row(game, team, opponent, home, team_class, opp_class, points, ratings):
    """One team's row: its offense ratings vs. the opponent's defense ratings."""
    row = {
        "game_id": game["game_id"],
        "team_id": team,
        "opponent_id": opponent,
        "home": home,
        "fcs_offense": team_class == "fcs",
        "fcs_defense": opp_class == "fcs",
        "points": points,
    }
    for m in METRICS:
        row["off_" + m] = ratings.at[team, "off_" + m]
        row["oppdef_" + m] = ratings.at[opponent, "def_" + m]
    return row


def add_prior_inputs(df, season):
    """Attach each team's and its opponent's preseason inputs, faded out over PRIOR_INPUT_WEEKS."""
    if df.empty:
        return df
    priors = season_priors(season)
    own = priors.rename(columns={p: "pr_" + p for p in PRIOR_INPUTS})
    opp = priors.rename(columns={"team_id": "opponent_id", **{p: "oppr_" + p for p in PRIOR_INPUTS}})
    df = df.merge(own, on="team_id", how="left").merge(opp, on="opponent_id", how="left")

    # Full weight before week 1, fading to zero by the end of the regular season
    fade = (1 - df["weeks_played"] / PRIOR_INPUT_WEEKS).clip(lower=0)
    for p in PRIOR_INPUTS:
        for col in ["pr_" + p, "oppr_" + p]:
            df[col] = df[col].fillna(0.0) * fade
    return df


def load_coach_changes(season):
    """{team_id: changed_at} for teams that changed head coach mid-season."""
    with connect() as conn:
        return dict(conn.execute(COACH_CHANGES_SQL, {"season": season}).fetchall())


def after_change(changes, team, game):
    """1 if this team's head coach changed before this regular-season game, else 0."""
    changed_at = changes.get(team)
    if changed_at is None or game["season_type"] != "regular":
        return 0
    return 1 if game["start_time"] > changed_at else 0


def season_rows(season):
    """Walk-forward feature rows for every game in a season.

    For each week, teams are rated using only games before that week's first
    kickoff, so no game ever 'sees' its own result.
    """
    games = load_season_games(season)
    changes = load_coach_changes(season)
    rows = []
    for (season_type, week), week_games in games.groupby(["season_type", "week"]):
        cutoff = week_games["start_time"].min()
        ratings, weeks_played = ratings_as_of(season, cutoff)

        for _, g in week_games.iterrows():
            if g["home_id"] not in ratings.index or g["away_id"] not in ratings.index:
                continue        # A team with no games yet (e.g. new to FBS)
            home_flag = 0 if g["neutral_site"] else 1
            home = side_row(g, g["home_id"], g["away_id"], home_flag,
                            g["home_classification"], g["away_classification"],
                            g["home_points"], ratings)
            away = side_row(g, g["away_id"], g["home_id"], -home_flag,
                            g["away_classification"], g["home_classification"],
                            g["away_points"], ratings)
            for r in (home, away):
                r["season"] = season
                r["weeks_played"] = weeks_played
                r["coach_change"] = after_change(changes, r["team_id"], g)
                r["opp_coach_change"] = after_change(changes, r["opponent_id"], g)
                rows.append(r)
    return add_prior_inputs(pd.DataFrame(rows), season)


def train(rows):
    """Fit the points model on rows whose result is known."""
    known = rows.dropna(subset=["points"])
    model = LinearRegression()
    model.fit(known[FEATURES].astype(float), known["points"].astype(float))
    return model


def save_predictions(model, rows, is_backtest, version=MODEL_VERSION):
    """Predict every row, pair each game's two sides, and save one row per game."""
    rows = rows.copy()
    rows["pred"] = model.predict(rows[FEATURES].astype(float))

    game_ids = [int(x) for x in rows["game_id"].unique()]
    with connect() as conn:
        home_ids = dict(
            conn.execute("SELECT id, home_id FROM games WHERE id = ANY(%s)", (game_ids,)).fetchall()
        )
        rows["is_home"] = rows["team_id"] == rows["game_id"].map(home_ids)
        home = rows[rows["is_home"]].set_index("game_id")
        away = rows[~rows["is_home"]].set_index("game_id")

        for game_id in home.index:
            home_pts = float(home.at[game_id, "pred"])
            away_pts = float(away.at[game_id, "pred"])
            conn.execute(
                """
                INSERT INTO predictions (game_id, model_version, home_points, away_points,
                                         spread, total, weeks_played, is_backtest)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id, model_version) DO UPDATE SET
                    home_points     = EXCLUDED.home_points,
                    away_points     = EXCLUDED.away_points,
                    spread          = EXCLUDED.spread,
                    total           = EXCLUDED.total,
                    weeks_played    = EXCLUDED.weeks_played,
                    is_backtest     = EXCLUDED.is_backtest,
                    created_at      = now()
                """,
                (
                    int(game_id),
                    version,
                    round(home_pts, 2),
                    round(away_pts, 2),
                    round(away_pts - home_pts, 2),      # home side: negative = home favored
                    round(home_pts + away_pts, 2),
                    int(home.at[game_id, "weeks_played"]),
                    is_backtest,
                ),
            )
    return len(home)


def backtest(first_season=2018, last_season=2025, version=MODEL_VERSION):
    """Walk-forward backtest: each season is predicted by a model trained only on earlier seasons."""
    print("building walk-forward rows (a few minutes)...")
    all_rows = pd.concat(
        [season_rows(s) for s in range(first_season - 1, last_season + 1)],
        ignore_index=True,
    )
    for season in range(first_season, last_season + 1):
        model = train(all_rows[all_rows["season"] < season])
        saved = save_predictions(model, all_rows[all_rows["season"] == season], is_backtest=True, version=version)
        print(f"  {season}: {saved} games predicted")


def predict_upcoming(season, first_training_season=2017):
    """Train on every finished game so far and save predictions for games that haven't kicked off.

    Re-running updates those predictions with the latest data. Once a game kicks off it's
    no longer 'upcoming', so its last pre-game prediction stays as the permanent record.
    """
    print("building walk-forward rows (a few minutes)...")
    all_rows = pd.concat(
        [season_rows(s) for s in range(first_training_season, season + 1)],
        ignore_index=True,
    )
    model = train(all_rows)         # train() skips games without a final score

    with connect() as conn:
        not_started = {
            row[0]
            for row in conn.execute(
                "SELECT id FROM games WHERE season = %s AND start_time > now()", (season,)
            ).fetchall()
        }
    upcoming = all_rows[all_rows["game_id"].isin(not_started)]
    saved = save_predictions(model, upcoming, is_backtest=False)
    print(f"{saved} upcoming games predicted")
