-- Stadiums (from CFBD /venues), so every game knows where it's played and whether it's indoors.
CREATE TABLE venues (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cfbd_id     INTEGER UNIQUE,
    name        TEXT NOT NULL,
    city        TEXT,
    state       TEXT,
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION,
    dome        BOOLEAN NOT NULL DEFAULT false
);

ALTER TABLE games ADD COLUMN venue_id INTEGER REFERENCES venues (id);

-- One kickoff weather forecast per game per day it was fetched, kept as history so a
-- "bet the weather" idea can later be tested on real forecasts instead of hindsight.
CREATE TABLE weather_forecasts (
    game_id         INTEGER NOT NULL REFERENCES games (id),
    forecast_date   DATE NOT NULL,              -- the day this forecast was made
    temperature_f   NUMERIC(5,1),               -- average over kickoff hour + 3 hours
    wind_mph        NUMERIC(4,1),
    gust_mph        NUMERIC(4,1),
    precip_in       NUMERIC(4,2),               -- total over kickoff hour + 3 hours
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (game_id, forecast_date)
);
