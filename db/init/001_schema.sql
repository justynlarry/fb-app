-- Every team seen, including FCS opponents
CREATE TABLE teams (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    league          TEXT NOT NULL CHECK (league IN ('cfb', 'nfl')),
    cfbd_id          INTEGER,       -- CollegeFootballData team id (cfb only)
    espn_id         INTEGER,        -- ESPN team id, for live scores
    school          TEXT NOT NULL,  -- 'Oklahoma' for CFB, or 'Denver' for NFL
    mascot          TEXT,           -- 'Sooners' for CFB, or 'Broncos' for NFL
    abbreviation    TEXT,           -- 'OU', 'DEN'
    conference      TEXT,           -- 'SEC', or 'AFC'
    division        TEXT,           -- 'AFC West' (NFL), NULL for most cfb
    classification  TEXT,           -- 'fbs', 'fcs', 'ii', 'iii', NULL for NFL
    UNIQUE (league, cfbd_id),
    UNIQUE (league, espn_id),
    UNIQUE (league, school)
);

-- One row per game, past and future
CREATE TABLE games (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    league          TEXT NOT NULL CHECK (league IN ('cfb', 'nfl')),
    cfbd_id         INTEGER,                    -- CollegeFootballData game id (cfb only)
    espn_id         INTEGER,                    -- ESPN event id, for live scores
    season          SMALLINT NOT NULL,
    week            SMALLINT NOT NULL,
    season_type     TEXT NOT NULL,              -- 'preseason', 'regular', 'postseason'
    start_time      TIMESTAMPTZ NOT NULL,       -- stored in UTC
    start_time_tbd  BOOLEAN NOT NULL DEFAULT false,
    neutral_site    BOOLEAN NOT NULL DEFAULT false,
    home_id         INTEGER NOT NULL REFERENCES teams (id),
    away_id         INTEGER NOT NULL REFERENCES teams (id),
    home_points     SMALLINT,                   -- NULL until the game is played
    away_points     SMALLINT,
    completed       BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (league, cfbd_id),
    UNIQUE (league, espn_id)
);


-- The pages look games up by league + week and sort by kickoff
CREATE INDEX games_league_season_week_idx ON games (league, season, week);
CREATE INDEX games_start_time_idx         ON games (start_time);


