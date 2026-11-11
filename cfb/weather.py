"""Kickoff weather forecasts for upcoming open-air games, from Open-Meteo (free, no key, not CFBD).

Run once a day by the worker. Each run saves one forecast per game for that day, so the
forecasts build up as history.
"""
from datetime import datetime, timedelta, timezone

import httpx

from cfb.db import connect

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAYS_AHEAD = 7          # forecast games kicking off within this many days

UPCOMING_GAMES_SQL = """
SELECT g.id, g.start_time, v.id AS venue_id, v.latitude, v.longitude
FROM games g
JOIN venues v ON v.id = g.venue_id
WHERE g.league = 'cfb'
  AND g.start_time BETWEEN now() AND now() + make_interval(days => %s)
  AND 'fbs' IN (g.home_classification, g.away_classification)
  AND NOT v.dome
  AND v.latitude IS NOT NULL
ORDER BY v.id, g.start_time
"""


def fetch_hourly(latitude, longitude, first_day, last_day):
    """Hourly forecast for one location: {'time': [...], 'temperature_2m': [...], ...} in UTC."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": first_day.isoformat(),
        "end_date": last_day.isoformat(),
        "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
    }
    resp = httpx.get(FORECAST_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["hourly"]


def kickoff_weather(hourly, kickoff):
    """Average temp/wind/gusts and total rain over the kickoff hour and the 3 hours after."""
    first_hour = kickoff.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    wanted = {(first_hour + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(4)}
    idx = [i for i, t in enumerate(hourly["time"]) if t in wanted]
    if not idx:
        return None

    def values(key):
        return [hourly[key][i] for i in idx if hourly[key][i] is not None]

    temps, winds, gusts, rain = (values(k) for k in
                                 ("temperature_2m", "wind_speed_10m", "wind_gusts_10m", "precipitation"))
    if not temps or not winds:
        return None
    return {
        "temperature_f": round(sum(temps) / len(temps), 1),
        "wind_mph": round(sum(winds) / len(winds), 1),
        "gust_mph": round(sum(gusts) / len(gusts), 1) if gusts else None,
        "precip_in": round(sum(rain), 2),
    }


def update_forecasts():
    """Fetch and save today's forecast for every upcoming open-air game (one request per stadium)."""
    with connect() as conn:
        games = conn.execute(UPCOMING_GAMES_SQL, (DAYS_AHEAD,)).fetchall()

    # Group games by stadium so each stadium needs only one request
    by_venue = {}
    for game_id, start_time, venue_id, lat, lon in games:
        by_venue.setdefault((venue_id, lat, lon), []).append((game_id, start_time))

    today = datetime.now(timezone.utc).date()
    saved = 0
    failed = 0
    for (venue_id, lat, lon), venue_games in by_venue.items():
        first_day = min(start for _, start in venue_games).astimezone(timezone.utc).date()
        last_day = max(start for _, start in venue_games).astimezone(timezone.utc).date() + timedelta(days=1)
        try:
            hourly = fetch_hourly(lat, lon, first_day, last_day)
        except httpx.HTTPError as err:
            print(f"weather: venue {venue_id} failed: {err!r}")
            failed += 1
            continue

        with connect() as conn:
            for game_id, start_time in venue_games:
                w = kickoff_weather(hourly, start_time)
                if w is None:
                    continue
                conn.execute(
                    """
                    INSERT INTO weather_forecasts (game_id, forecast_date, temperature_f,
                                                   wind_mph, gust_mph, precip_in)
                    VALUES (%(game_id)s, %(day)s, %(temperature_f)s, %(wind_mph)s,
                            %(gust_mph)s, %(precip_in)s)
                    ON CONFLICT (game_id, forecast_date) DO UPDATE SET
                        temperature_f = EXCLUDED.temperature_f,
                        wind_mph      = EXCLUDED.wind_mph,
                        gust_mph      = EXCLUDED.gust_mph,
                        precip_in     = EXCLUDED.precip_in,
                        fetched_at    = now()
                    """,
                    {"game_id": game_id, "day": today, **w},
                )
                saved += 1

    print(f"weather: {saved} game forecasts saved from {len(by_venue)} stadiums ({failed} failed)")
    return saved
