-- NFL quarterbacks: who started each game, and every QB's dropbacks in each game.
-- Filled from nflverse by cfb/nflverse.py (free files, no API calls). Used by cfb/nfl_qbs.py
-- for the nfl-v2 starting-QB adjustment (docs/model-tests.md section 9).

-- Every QB with a dropback in a game (passes, sacks, scrambles; garbage time removed)
CREATE TABLE nfl_qb_games (
    game_id     INTEGER NOT NULL REFERENCES games (id),
    team_id     INTEGER NOT NULL REFERENCES teams (id),
    qb_id       TEXT NOT NULL,              -- NFL player id from nflverse, e.g. '00-0033873'
    dropbacks   SMALLINT NOT NULL,
    epa         DOUBLE PRECISION NOT NULL,  -- total EPA on those dropbacks
    PRIMARY KEY (game_id, team_id, qb_id)
);

-- Each team's starting QB for a game. 'nflverse' = the actual starter (filled in after
-- the game); 'manual' = entered by hand for an upcoming game (later, on the overrides page).
CREATE TABLE nfl_starters (
    game_id     INTEGER NOT NULL REFERENCES games (id),
    team_id     INTEGER NOT NULL REFERENCES teams (id),
    qb_id       TEXT NOT NULL,
    qb_name     TEXT,
    source      TEXT NOT NULL DEFAULT 'nflverse',
    PRIMARY KEY (game_id, team_id)
);

