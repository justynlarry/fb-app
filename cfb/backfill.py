"""Save the raw CFBD data for whole seasons into api_responses.

Safe to re-run, anything already saved is read from the database for free.
run:    python -m cfb.backfill 2025         (One Season)
        python -m cfb.backfill 2016 2017 ... (Several)
"""

import sys

import httpx

from cfb import cfbd


def season_calls(year):
    """Every (endpoint, params) we pull once per season."""
    return [
        ("/teams", {"year": year}),
        ("/calendar", {"year": year}),
        ("/games", {"year": year, "seasonType": "both"}),
        ("/stats/game/advanced", {"year": year, "seasonType": "both", "excludeGarbageTime": True}),
        ("/lines", {"year": year, "seasonType": "both"}),
        ("/player/returning", {"year": year}),
        ("/talent", {"year": year}),
        ("/recruiting/teams", {"year": year}),
        ("/coaches", {"year": year}),
        ("/player/portal", {"year": year}),
        ("/ratings/sp", {"year": year}),
    ]


def fetch_all(calls):
    """Fetch (or read from cache) each (endpoint, params) and report row counts."""
    for endpoint, params in calls:
        label = f"{endpoint} {params.get('conference', '')}".strip()
        try:
            body = cfbd.get(endpoint, params)
        except httpx.HTTPStatusError as err:
            # Show what CFBD complained about, e.g. a missing required parameter
            print(f"FAILED {label}: {err.response.status_code} {err.response.text[:200]}")
            continue
        print(f"  {label:40} {len(body):6} rows")


def backfill(year):
    """Every once-per-season call for one season."""
    print(f"=== {year}")
    fetch_all(season_calls(year))


def fbs_conferences(year):
    """Conferences FBS teams played in that season (from the saved /teams response, no API call)."""
    teams = cfbd.get("/teams", {"year": year})
    return sorted({t["conference"] for t in teams if t.get("classification") == "fbs" and t.get("conference")})


def conference_abbreviations():
    """CFBD conference name -> abbreviation, e.g. 'Big Ten' -> 'B1G' (saved response, no API call).

    /games/players only accepts abbreviations; a full name quietly returns no games.
    """
    return {c["name"]: c["abbreviation"] for c in cfbd.get("/conferences", {}) if c.get("abbreviation")}


def qb_calls(year):
    """One call per FBS conference: every passer in every game that season, bowls included."""
    abbreviations = conference_abbreviations()
    return [
        ("/games/players", {"year": year, "conference": abbreviations.get(conf, conf),
                            "category": "passing", "seasonType": "both"})
        for conf in fbs_conferences(year)
    ]


def backfill_qbs(year):
    """Passing box scores for a whole season (about 11 API calls)."""
    print(f"=== QBs {year}")
    fetch_all(qb_calls(year))


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        backfill(int(arg))
