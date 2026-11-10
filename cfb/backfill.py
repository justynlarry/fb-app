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


def backfill(year):
    """Fetch (or read from cache) every call for one season and report row counts."""
    print(f"=== {year}")
    for endpoint, params in season_calls(year):
        try:
            body = cfbd.get(endpoint, params)
        except httpx.HTTPStatusError as err:
            # Show what CFBD complained about, e.g. a missing required parameter
            print(f"FAILED {endpoint}: {err.response.status_code} {err.response.text[:200]}")
            continue
        print(f"  {endpoint:25} {len(body):6} rows")


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        backfill(int(arg))
