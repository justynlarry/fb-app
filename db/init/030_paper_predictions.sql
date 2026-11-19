-- Paper models (030): predicted every morning beside the live model, never used for a pick or shown as our line
-- (docs/plan-2027.md section 4). Their own table, not `predictions`, for two reasons:
--   1. the pages fall back to "the latest prediction from any version" when the live one is missing a game, so a
--      paper row there could show up as our line;
--   2. the 2027 tests grade them at BET TIME (e.g. H-TOT-B1: B1-total - bettable open), so we keep every morning's
--      value, not just the last one before kickoff. The value at a moment = the latest row created before it.
-- One row per game, version and local day; re-running the same day replaces that day's row.

CREATE TABLE paper_predictions (
    game_id         integer NOT NULL REFERENCES games(id),
    model_version   text NOT NULL,              -- 'v6', 'v6-ht4', 'v6-ht2b', 'v5' (after the freeze), 'b1-total'
    run_date        date NOT NULL,              -- the morning it was made (America/Denver)
    created_at      timestamptz NOT NULL DEFAULT now(),
    home_points     numeric(5,2) NOT NULL,
    away_points     numeric(5,2) NOT NULL,
    spread          numeric(5,2) NOT NULL,      -- home side: away - home, negative = home favored
    total           numeric(5,2) NOT NULL,
    weeks_played    smallint,
    PRIMARY KEY (game_id, model_version, run_date)
);

CREATE INDEX paper_predictions_version_created ON paper_predictions (model_version, created_at);
