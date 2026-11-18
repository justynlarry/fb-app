-- Head-coach detector (027): the head coach ESPN lists for each team-season,
-- and coach changes waiting to be confirmed.

-- Coach changes found by the detector wait for an admin; the model reads confirmed
-- rows only.
ALTER TABLE coach_changes
    ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('pending', 'confirmed', 'rejected')),
    ADD COLUMN detected_at TIMESTAMPTZ;     -- when the detector found it; NULL for loader and hand entries

-- The head coach ESPN listed for each team, each season, as the detector saw it.
CREATE TABLE head_coach_watch (
    team_id         INTEGER NOT NULL REFERENCES teams (id),
    season          SMALLINT NOT NULL,
    espn_coach_id   INTEGER NOT NULL,
    coach_name      TEXT NOT NULL,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, season, espn_coach_id)
);
