-- One row per team per game: that team's OFFENSE, garbage time excluded.
-- A team's DEFENSE in a game = its opponent's offense row for that game.
-- CFBD calls EPA "ppa"; we use the usual name, epa.

CREATE TABLE team_game_stats (
    game_id             INTEGER NOT NULL REFERENCES games (id),
    team_id             INTEGER NOT NULL REFERENCES teams (id), -- the offense
    opponent_id         INTEGER NOT NULL REFERENCES teams (id), -- the defense
    plays               SMALLINT,
    drives              SMALLINT,
    epa_per_play        DOUBLE PRECISION,
    success_rate        DOUBLE PRECISION,
    explosiveness       DOUBLE PRECISION,
    pass_epa            DOUBLE PRECISION,                       -- EPA per pass play
    pass_success_rate   DOUBLE PRECISION,
    pass_explosiveness  DOUBLE PRECISION,
    rush_epa            DOUBLE PRECISION,                       -- EPA per rush play
    rush_success_rate   DOUBLE PRECISION,
    rush_explosiveness  DOUBLE PRECISION,
    standard_downs_epa  DOUBLE PRECISION,
    passing_downs_epa   DOUBLE PRECISION,
    line_yards          DOUBLE PRECISION,
    stuff_rate          DOUBLE PRECISION,
    power_success       DOUBLE PRECISION,
    PRIMARY KEY (game_id, team_id)
);
