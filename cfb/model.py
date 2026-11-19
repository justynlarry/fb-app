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

MODEL_VERSION = "v5"        # the live model until the 2027 freeze (docs/plan-2027.md); "v6" is built below

# Preseason inputs (from cfb/priors.py), faded out over the regular season
PRIOR_INPUTS = ["talent", "ret_ppa", "new_coach"]
PRIOR_INPUT_WEEKS = 16

# Mid-season head-coach changes (cfb/coaches.py fills history; current season entered by hand)
COACH_CHANGES_SQL = """
SELECT team_id, changed_at
FROM coach_changes
WHERE season = %(season)s
  AND status = 'confirmed'
"""

FEATURES = (
    ["off_" + m for m in METRICS]
    + ["oppdef_" + m for m in METRICS]
    + ["home", "fcs_offense", "fcs_defense", "coach_change", "opp_coach_change"]
    + ["pr_" + p for p in PRIOR_INPUTS]
    + ["oppr_" + p for p in PRIOR_INPUTS]
)

# v6 (the frozen 2027 candidate, docs/plan-2027.md 2.1) = v5 + two tested additions:
#   T1, full matchup rows (Round 1, 2026-11-17): the team's own defense and the opponent's offense ratings
#   T-OCDC, new coordinators (2026-11-18): this team has a new offensive coordinator, the opponent a new
#   defensive coordinator, from table coordinators, faded like the other preseason inputs
MATCH_FEATURES = ["def_" + m for m in METRICS] + ["oppoff_" + m for m in METRICS]
COORDINATOR_FEATURES = ["pr_new_oc", "oppr_new_dc"]
VERSION_FEATURES = {
    "v5": FEATURES,
    "v6": FEATURES + MATCH_FEATURES + COORDINATOR_FEATURES,
}

# Which teams start this season with a new coordinator (coordinators.is_new; NULL = no previous season = not new)
NEW_COORDINATORS_SQL = """
SELECT team_id, unit, COALESCE(is_new, false) AS is_new
FROM coordinators
WHERE season = %(season)s
"""

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


def add_match_columns(df):
    """T1: each row also gets its own team's defense ratings and the opponent's offense ratings (from the
    opponent's row of the same game)."""
    if df.empty:
        return df
    partner = df[["game_id", "team_id"] + ["off_" + m for m in METRICS] + ["oppdef_" + m for m in METRICS]].rename(
        columns={"team_id": "opponent_id",
                 **{"off_" + m: "oppoff_" + m for m in METRICS},
                 **{"oppdef_" + m: "def_" + m for m in METRICS}})
    return df.merge(partner, on=["game_id", "opponent_id"], how="left")


def add_coordinator_inputs(df, season):
    """T-OCDC: new offensive coordinator for this team, new defensive coordinator for the opponent,
    faded out over PRIOR_INPUT_WEEKS like the other preseason inputs."""
    if df.empty:
        return df
    with connect() as conn:
        rows = conn.execute(NEW_COORDINATORS_SQL, {"season": season}).fetchall()
    new_oc = {team for team, unit, is_new in rows if unit == "offense" and is_new}
    new_dc = {team for team, unit, is_new in rows if unit == "defense" and is_new}
    fade = (1 - df["weeks_played"] / PRIOR_INPUT_WEEKS).clip(lower=0)
    df["pr_new_oc"] = df["team_id"].isin(new_oc).astype(float) * fade
    df["oppr_new_dc"] = df["opponent_id"].isin(new_dc).astype(float) * fade
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
    df = add_prior_inputs(pd.DataFrame(rows), season)
    # v6's extra columns; v5 ignores them (each version picks its own columns from VERSION_FEATURES)
    df = add_match_columns(df)
    return add_coordinator_inputs(df, season)


def train(rows, version=MODEL_VERSION):
    """Fit the points model on rows whose result is known, with this version's columns."""
    features = VERSION_FEATURES[version]
    known = rows.dropna(subset=["points"])
    model = LinearRegression()
    model.fit(known[features].astype(float), known["points"].astype(float))
    return model


def pair_predictions(model, rows, version=MODEL_VERSION):
    """Predict every row and pair each game's two sides: one row per game with
    game_id, home_points, away_points, weeks_played."""
    rows = rows.copy()
    rows["pred"] = model.predict(rows[VERSION_FEATURES[version]].astype(float))
    game_ids = [int(x) for x in rows["game_id"].unique()]
    with connect() as conn:
        home_ids = dict(
            conn.execute("SELECT id, home_id FROM games WHERE id = ANY(%s)", (game_ids,)).fetchall()
        )
    rows["is_home"] = rows["team_id"] == rows["game_id"].map(home_ids)
    home = rows[rows["is_home"]].set_index("game_id")
    away = rows[~rows["is_home"]].set_index("game_id")
    return pd.DataFrame({
        "home_points": home["pred"],
        "away_points": away["pred"].reindex(home.index),
        "weeks_played": home["weeks_played"],
    }).rename_axis("game_id").reset_index()


def save_predictions(model, rows, is_backtest, version=MODEL_VERSION):
    """Predict every row, pair each game's two sides, and save one row per game."""
    games = pair_predictions(model, rows, version)
    with connect() as conn:
        for g in games.itertuples():
            home_pts = float(g.home_points)
            away_pts = float(g.away_points)
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
                -- A backtest replay never overwrites a live (pre-game) prediction, the real record
                WHERE predictions.is_backtest OR NOT EXCLUDED.is_backtest
                """,
                (
                    int(g.game_id),
                    version,
                    round(home_pts, 2),
                    round(away_pts, 2),
                    round(away_pts - home_pts, 2),      # home side: negative = home favored
                    round(home_pts + away_pts, 2),
                    int(g.weeks_played),
                    is_backtest,
                ),
            )
    return len(games)


def backtest(first_season=2018, last_season=2025, version=MODEL_VERSION):
    """Walk-forward backtest: each season is predicted by a model trained only on earlier seasons."""
    print("building walk-forward rows (a few minutes)...")
    all_rows = pd.concat(
        [season_rows(s) for s in range(first_season - 1, last_season + 1)],
        ignore_index=True,
    )
    for season in range(first_season, last_season + 1):
        model = train(all_rows[all_rows["season"] < season], version)
        saved = save_predictions(model, all_rows[all_rows["season"] == season], is_backtest=True, version=version)
        print(f"  {season}: {saved} games predicted")


def upcoming_game_ids(season):
    """Games of this season that haven't kicked off."""
    with connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT id FROM games WHERE season = %s AND start_time > now()", (season,)
            ).fetchall()
        }


def build_rows(season, first_training_season=2017):
    """Walk-forward rows for every season from first_training_season to this one (a few minutes).
    Built once each morning and shared by the live model and the paper models."""
    print("building walk-forward rows (a few minutes)...")
    return pd.concat(
        [season_rows(s) for s in range(first_training_season, season + 1)],
        ignore_index=True,
    )


def upcoming_predictions(rows, season, version):
    """Train this version on every finished game and predict the season's games that haven't kicked off
    (one row per game, as pair_predictions)."""
    model = train(rows, version)            # train() skips games without a final score
    upcoming = rows[rows["game_id"].isin(upcoming_game_ids(season))]
    return pair_predictions(model, upcoming, version)


def predict_upcoming(season, first_training_season=2017, version=MODEL_VERSION, rows=None):
    """Train on every finished game so far and save predictions for games that haven't kicked off.

    Re-running updates those predictions with the latest data. Once a game kicks off it's
    no longer 'upcoming', so its last pre-game prediction stays as the permanent record.
    Pass rows (from build_rows) to reuse rows already built this morning.
    """
    if rows is None:
        rows = build_rows(season, first_training_season)
    model = train(rows, version)            # train() skips games without a final score
    upcoming = rows[rows["game_id"].isin(upcoming_game_ids(season))]
    saved = save_predictions(model, upcoming, is_backtest=False, version=version)
    print(f"{saved} upcoming games predicted ({version})")
    return saved
