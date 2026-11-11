-- Manual adjustments for news the model can't see (injuries, suspensions, weather...).
-- An override changes ONE team's predicted points for ONE game; spread and total follow.
-- The model's own predictions are never edited, so backtests stay a clean test of the model.

CREATE TABLE overrides (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id     INTEGER NOT NULL REFERENCES games (id),
    team_id     INTEGER NOT NULL REFERENCES teams (id),     -- the team whose points change
    points      NUMERIC(4,1) NOT NULL CHECK (points BETWEEN -30 AND 30),    -- e.g. -3.5
    reason      TEXT NOT NULL CHECK (length(trim(reason)) > 0),             -- 'QB Smith out (shoulder)'
    active      BOOLEAN NOT NULL DEFAULT true,              -- false = removed (kept for history)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX overrides_game_idx ON overrides (game_id) WHERE active;
