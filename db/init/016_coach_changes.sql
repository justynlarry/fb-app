-- Mid-season head-coach changes (regular season). Games that kick off after changed_at
-- are played under the new coach.  History comes from cached /coaches;  the current season
-- is entered by hand, because CFBD fills in this season's coaches only after it ends.

CREATE TABLE coach_changes (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id     integer NOT NULL REFERENCES teams(id),
    season      smallint NOT NULL,
    changed_at  timestamptz NOT NULL,           -- games after this have the new coach
    outgoing    text,                           -- coach who left
    incoming    text,                           -- interim or new coach
    source      text NOT NULL DEFAULT 'manual', -- 'cfbd' (from /coaches) or 'manual'
    note        text,
    UNIQUE (team_id, season)
);
