-- NFL injury reports from nflverse (free file, refreshed daily by nflverse around midnight MT).
-- One row per player per team-week.  Each load overwrites that week's row with the latest status.
-- Display only (Overrides page).  Not a model input:  T-skill, 2026-11-16, was rejected.

CREATE TABLE IF NOT EXISTS nfl_injuries (
    season          smallint    NOT NULL,
    week            smallint    NOT NULL,   -- nflverse numbering (playoffs 19-22), same as games.week
    team_id         integer     NOT NULL REFERENCES teams(id),
    gsis_id         text        NOT NULL,   -- nflverse player id, same as nfl_qb_games.qb_id
    full_name       text        NOT NULL,
    position        text,
    report_status   text,                   -- Out / Doubtful / Questionable; NULL = practised, not listed for the game
    injury          text,                   -- the report's injury, else the practice report's
    practice_status text,                   -- last practice of the week
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (season, week, team_id, gsis_id)
);
