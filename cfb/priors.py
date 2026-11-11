"""Preseason inputs per team: roster talent, returning production, new head coach.

Built from CFBD responses we already saved, so it costs no API calls.
Talent and returning production are standardized among FBS teams each season
(0 = average, 1 = one standard deviation better), so seasons compare fairly.
"""

import pandas as pd

from cfb import cfbd
from cfb.db import connect


def head_coaches(season, cfbd_to_id):
    """{team_id: set of (first, last) names} for everyone who was head coach that season."""
    coaches = {}
    for coach in cfbd.get("/coaches", {"year": season}):
        name = (coach["firstName"], coach["lastName"])
        for s in coach.get("seasons", []):
            team_id = cfbd_to_id.get(s.get("teamId"))
            if team_id is not None and s.get("year") == season:
                coaches.setdefault(team_id, set()).add(name)
    return coaches


def season_priors(season):
    """One row per FBS team: talent, ret_ppa (standardized) and new_coach (1 or 0)."""
    with connect() as conn:
        fbs_ids = dict(
            conn.execute(
                "SELECT school, id FROM teams WHERE league = 'cfb' AND classification = 'fbs'"
            ).fetchall()
        )
        cfbd_to_id = dict(
            conn.execute("SELECT cfbd_id, id FROM teams WHERE league = 'cfb'").fetchall()
        )

    talent = {}
    for r in cfbd.get("/talent", {"year": season}):
        team_id = fbs_ids.get(r["team"])
        if team_id is not None:
            talent[team_id] = r["talent"]

    returning = {}
    for r in cfbd.get("/player/returning", {"year": season}):
        team_id = fbs_ids.get(r["team"])
        if team_id is not None:
            returning[team_id] = r.get("percentPPA")

    coaches_now = head_coaches(season, cfbd_to_id)
    coaches_before = head_coaches(season - 1, cfbd_to_id)

    rows = []
    for team_id in set(talent) | set(returning):
        now = coaches_now.get(team_id, set())
        before = coaches_before.get(team_id, set())
        new_coach = bool(now) and bool(before) and not (now & before)
        rows.append({
            "team_id": team_id,
            "talent": talent.get(team_id),
            "ret_ppa": returning.get(team_id),
            "new_coach": 1.0 if new_coach else 0.0,
        })
    priors = pd.DataFrame(rows)

    # Standardize: 0 = average FBS team, 1 = one standard deviation above
    for col in ["talent", "ret_ppa"]:
        priors[col] = (priors[col] - priors[col].mean()) / priors[col].std()
    return priors.fillna(0.0)
