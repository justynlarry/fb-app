"""NFL starting-QB adjustment (nfl-v2; tested as T-QB in docs/model-tests.md section 9).

Each QB gets a value:  EPA per dropback above a replacement-level QB, shrunk toward
replacement until he has a few hundred dropbacks.  A team's adjustment for a game is its
starter's value minus the value of the QBs its ratings were built on.
Reads only from the database (nfl_qb_games, nfl_starters), so it costs no API calls.
"""

import pandas as pd
from psycopg.rows import dict_row

from cfb.db import connect

K_QB = 410              # dropbacks before half of a QB's difference from replacement counts (R2)
REPLACEMENT_RANK = 32   # QBs outside the top 32 by dropbacks in a season set the replacement level

QB_GAMES_SQL = """
SELECT q.qb_id, q.team_id, q.dropbacks, q.epa, g.season, g.week
FROM nfl_qb_games q
JOIN games g ON g.id = q.game_id
ORDER BY g.start_time
"""

STARTERS_SQL = "SELECT game_id, team_id, qb_id FROM nfl_starters"


def load_qb_games():
    """Every QB's dropbacks and EPA in every game, with a sortable 'order' (season, then week)."""
    with connect() as conn:
        conn.row_factory = dict_row
        games = pd.DataFrame(conn.execute(QB_GAMES_SQL).fetchall())
    games["order"] = games["season"] * 100 + games["week"]
    return games


def load_starters():
    """{(game_id, team_id): starting QB's id}"""
    with connect() as conn:
        rows = conn.execute(STARTERS_SQL).fetchall()
    return {(game_id, team_id): qb_id for game_id, team_id, qb_id in rows}


def replacement_levels(qb_games):
    """{season: EPA per dropback of a replacement-level QB}.

    Each season uses the season before's level, so nothing from later in the season leaks
    in. The first season has no season before it and uses its own.
    """
    level = {}
    for season, games in qb_games.groupby("season"):
        totals = games.groupby("qb_id")[["dropbacks", "epa"]].sum()
        backups = totals.sort_values("dropbacks", ascending=False).iloc[REPLACEMENT_RANK:]
        level[season] = backups["epa"].sum() / backups["dropbacks"].sum()
    return {season: level.get(season - 1, level[season]) for season in level}


class QBs:
    """All NFL QB data, loaded once. value() -> team_recent() -> adjustment()."""

    def __init__(self):
        games = load_qb_games()
        self.levels = replacement_levels(games)
        self.by_qb = {qb_id: g for qb_id, g in games.groupby("qb_id")}
        self.by_team = {key: g for key, g in games.groupby(["team_id", "season"])}
        self.starters = load_starters()

    def value(self, qb_id, order, season):
        """Shrunk EPA per dropback above replacement, from his dropbacks in earlier weeks (any team)."""
        games = self.by_qb.get(qb_id)
        if games is None:
            return 0.0          # no NFL dropbacks yet: treated as replacement level
        before = games[games["order"] < order]
        n = before["dropbacks"].sum()
        if n == 0:
            return 0.0
        per_dropback = before["epa"].sum() / n
        return float(n / (n + K_QB) * (per_dropback - self.levels[season]))

    def team_recent(self, team_id, season, order, weeks_played, settings):
        """Value of the QBs behind the team's current ratings, weighted the way the ratings are."""
        weights = []
        this_season = self.by_team.get((team_id, season))
        if this_season is not None:
            played = this_season[this_season["order"] < order]
            weeks_ago = (weeks_played - played["week"].clip(upper=weeks_played)).clip(lower=0)
            w = 0.5 ** (weeks_ago / settings["half_life"]) * played["dropbacks"]
            weights.append(pd.DataFrame({"qb_id": played["qb_id"], "w": w}))
        fade = max(0.0, 1 - weeks_played / settings["prior_weeks"])
        last_season = self.by_team.get((team_id, season - 1))
        if fade > 0 and last_season is not None:
            w = fade * settings["last_weight"] * last_season["dropbacks"]
            weights.append(pd.DataFrame({"qb_id": last_season["qb_id"], "w": w}))
        if not weights:
            return 0.0
        per_qb = pd.concat(weights).groupby("qb_id")["w"].sum()
        if per_qb.sum() == 0:
            return 0.0
        values = pd.Series({qb_id: self.value(qb_id, order, season) for qb_id in per_qb.index})
        return float((values * per_qb).sum() / per_qb.sum())

    def adjustment(self, game_id, team_id, season, week, weeks_played, settings):
        """Starter's value minus the team's recent QBs' value (0 when the starter isn't known)."""
        starter = self.starters.get((game_id, team_id))
        if starter is None:
            return 0.0
        order = season * 100 + week
        recent = self.team_recent(team_id, season, order, weeks_played, settings)
        return self.value(starter, order, season) - recent


def add_qb_features(rows, settings):
    """Add qb_adj (this team's starter vs. its recent QBs) and opp_qb_adj (the opponent's)."""
    qbs = QBs()
    rows = rows.copy()
    rows["qb_adj"] = [
        qbs.adjustment(g, t, s, w, wp, settings)
        for g, t, s, w, wp in zip(rows["game_id"], rows["team_id"], rows["season"],
                                  rows["week"], rows["weeks_played"])
    ]
    opponent = rows[["game_id", "team_id", "qb_adj"]].rename(
        columns={"team_id": "opponent_id", "qb_adj": "opp_qb_adj"})
    return rows.merge(opponent, on=["game_id", "opponent_id"], how="left")


POINTS_PER_EPA = 26     # points per 1.0 EPA/dropback of QB value: the points model's qb_adj coefficient (T-QB)


def last_team(qbs, qb_id, order):
    """The team a QB last played for before this week (None if he hasn't played)."""
    games = qbs.by_qb.get(qb_id)
    if games is None:
        return None
    before = games[games["order"] < order]      # games are in kickoff order (QB_GAMES_SQL)
    return before["team_id"].iloc[-1] if len(before) > 0 else None


def qb_out_suggestion(game_id, team_id, season, week):
    """Suggested override for a team whose projected starter won't play: points added to (usually
    taken off) its own score, from the starter's value vs. the backup's.  The backup is the team's
    other QB with the most dropbacks this season who is still with it, i.e. whose last game was for
    this team (replacement level if there is none).
    Returns None if we don't know the starter."""
    qbs = QBs()
    starter = qbs.starters.get((game_id, team_id))
    if starter is None:
        return None
    order = season * 100 + week

    backup = None
    team_games = qbs.by_team.get((team_id, season))
    if team_games is not None:
        others = team_games[(team_games["order"] < order) & (team_games["qb_id"] != starter)]
        still_here = [q for q in others["qb_id"].unique() if last_team(qbs, q, order) == team_id]
        others = others[others["qb_id"].isin(still_here)]
        if len(others) > 0:
            backup = others.groupby("qb_id")["dropbacks"].sum().idxmax()

    starter_value = qbs.value(starter, order, season)
    backup_value = qbs.value(backup, order, season) if backup else 0.0
    points = POINTS_PER_EPA * (backup_value - starter_value)
    return {
        "starter_id": starter,
        "backup_id": backup,
        "starter_value": round(starter_value, 3),
        "backup_value": round(backup_value, 3),
        "points": round(points * 2) / 2,
    }
