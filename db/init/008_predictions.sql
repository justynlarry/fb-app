-- Our model's predictions, one row per game per model version.
-- Spread is from the HOME team's side, same as lines: -10 means we have home by 10.

CREATE TABLE predictions (
    game_id         INTEGER NOT NULL REFERENCES games (id),
    model_version   TEXT NOT NULL,          -- 'v1', 'v2' ... so versions can be compared
    home_points     NUMERIC(5,2) NOT NULL,
    away_points     NUMERIC(5,2) NOT NULL,
    spread          NUMERIC(5,2) NOT NULL,  -- away_points - home_points
    total           NUMERIC(5,2) NOT NULL,  -- home_points + away_points
    weeks_played    SMALLINT,               -- current-season weeks the ratings had
    is_backtest     BOOLEAN NOT NULL,       -- true = walk-forward replay of a past game
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (game_id, model_version)
);
