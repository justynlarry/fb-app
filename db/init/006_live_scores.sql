-- Latest live snapshot per game from ESPN, overwritten every poll.
-- games = the offical record (CFBD), live_scores = what's happening right now.

CREATE TABLE live_scores (
    game_id             INTEGER PRIMARY KEY REFERENCES games (id),
    state               TEXT NOT NULL,          -- 'pre', 'in', 'post'
    status_detail       TEXT,                   -- ESPN's text: '6:11 - 1st', 'Halftime', 'Final/OT'
    period              SMALLINT,               -- quarter: 1-4, 5+ = overtime
    clock               TEXT,                   -- '6:11'
    home_score          SMALLINT,
    away_score          SMALLINT,
    possession_team_id  INTEGER REFERENCES teams (id),   -- NULL between plays / not live
    home_timeouts       SMALLINT,
    away_timeouts       SMALLINT,
    down_distance       TEXT,                   -- '3rd & 8 at WMU 41'
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
