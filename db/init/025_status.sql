-- What the worker did and how much API quota is left, for the admin status panel (025).

-- One row per scheduled job run (daily update, odds snapshots, NFL update...).
CREATE TABLE job_runs (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job          TEXT NOT NULL,              -- 'daily_update', 'odds_snapshot', ...
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,                -- NULL while running, or if the worker died mid-run
    ok           BOOLEAN,                    -- NULL while running
    message      TEXT                        -- short result, or the error
);
CREATE INDEX job_runs_job_time ON job_runs (job, started_at DESC);

-- The latest quota each limited API reported in its response headers
CREATE TABLE api_quota (
    source       TEXT PRIMARY KEY,           -- 'cfbd', 'odds_api'
    remaining    INTEGER,
    used_last    INTEGER,                    -- what the last call cost (the Odds API says; CFBD doesn't)
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
