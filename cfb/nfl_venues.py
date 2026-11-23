"""NFL stadiums, so NFL games can get kickoff weather forecasts (cfb/weather.py).

ESPN's NFL scoreboard (this week's games) names each game's stadium, its city and whether it's
indoors.  New stadiums get coordinates once: ESPN's venue record gives the ZIP code, and
Open-Meteo's free geocoder turns it into latitude/longitude (the city name for stadiums abroad).
Each game is then linked to its stadium (games.venue_id).

    python -m cfb.nfl_venues
"""

import httpx

from cfb.db import connect
from cfb.espn import fetch_scoreboard

ESPN_VENUE_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/venues/{venue_id}"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"


def scoreboard_venues():
    """This week's NFL games and their stadiums from ESPN, as a list of dicts.  A game without a
    stadium in the feed is skipped and reported."""
    games = []
    for event in fetch_scoreboard("nfl").get("events", []):
        try:
            venue = event["competitions"][0]["venue"]
            address = venue.get("address", {})
            games.append({
                "game_espn_id": int(event["id"]),
                "venue_espn_id": int(venue["id"]),
                "name": venue["fullName"],
                "city": address.get("city"),
                "state": address.get("state"),
                "indoor": bool(venue.get("indoor", False)),
            })
        except (KeyError, IndexError, TypeError, ValueError):
            print(f"NFL venues: no stadium for ESPN event {event.get('id')}, skipping")
    return games


def locate(venue_espn_id, city):
    """(latitude, longitude) of an NFL stadium, or None if it can't be found.

    US stadiums: by the ZIP code in ESPN's venue record (exact).  Abroad (no ZIP): by city name,
    taking the geocoder's first match (it ranks big cities first: London, Munich, Madrid...).
    """
    resp = httpx.get(ESPN_VENUE_URL.format(venue_id=venue_espn_id), timeout=20)
    resp.raise_for_status()
    zip_code = resp.json().get("address", {}).get("zipCode")

    if zip_code:
        params = {"name": zip_code[:5], "count": 1, "countryCode": "US"}
    elif city:
        params = {"name": city, "count": 1}
    else:
        return None

    resp = httpx.get(GEOCODE_URL, params=params, timeout=20)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    return results[0]["latitude"], results[0]["longitude"]


VENUE_SQL = """
INSERT INTO venues (espn_id, name, city, state, dome)
VALUES (%(venue_espn_id)s, %(name)s, %(city)s, %(state)s, %(indoor)s)
ON CONFLICT (espn_id) DO UPDATE SET
    name  = EXCLUDED.name,
    city  = EXCLUDED.city,
    state = EXCLUDED.state,
    dome  = EXCLUDED.dome
RETURNING id, latitude
"""


def sync_venues():
    """Save this week's NFL stadiums, find coordinates for new ones, and link each game to its
    stadium.  Returns (games linked, games whose stadium still has no coordinates)."""
    games = scoreboard_venues()
    linked = 0
    missing = 0
    with connect() as conn:
        for g in games:
            venue_id, latitude = conn.execute(VENUE_SQL, g).fetchone()
            if latitude is None:
                try:
                    found = locate(g["venue_espn_id"], g["city"])
                except httpx.HTTPError as err:
                    print(f"NFL venues: {g['name']} lookup failed: {err!r}")
                    found = None
                if found:
                    lat, lon = found
                    conn.execute("UPDATE venues SET latitude = %s, longitude = %s WHERE id = %s",
                                 (lat, lon, venue_id))
                    print(f"NFL venues: {g['name']} ({g['city']}) at {lat:.2f}, {lon:.2f}")
                else:
                    missing += 1
            result = conn.execute(
                "UPDATE games SET venue_id = %s WHERE league = 'nfl' AND espn_id = %s",
                (venue_id, g["game_espn_id"]),
            )
            linked += result.rowcount
        conn.commit()
    print(f"NFL venues: {linked} games linked, {missing} without stadium coordinates")
    return linked, missing


def main():
    sync_venues()


if __name__ == "__main__":
    main()
