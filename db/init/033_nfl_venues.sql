-- NFL stadiums in venues, keyed by ESPN's venue id (college venues keep cfbd_id).
-- Filled by cfb/nfl_venues.py from ESPN's NFL scoreboard.  Coordinates from Open-Meteo's geocoder by ZIP code.
-- Lets NFL games get kickoff weather forecasts like college (weather_forecasts).

ALTER TABLE venues ADD COLUMN IF NOT EXISTS espn_id INTEGER UNIQUE;
