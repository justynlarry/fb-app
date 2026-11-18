-- Coordinator changes found by the coordinator detector (028), waiting for an admin.
-- Confirming one adds the new names to that season's row in coordinators; the preseason is_new flag never changes.

CREATE TABLE coordinator_changes (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id      INTEGER NOT NULL REFERENCES teams (id),
    season       SMALLINT NOT NULL,
    unit         TEXT NOT NULL CHECK (unit IN ('offense', 'defense')),
    old_names    TEXT[] NOT NULL,       -- what coordinators held when the change was seen
    new_names    TEXT[] NOT NULL,       -- what the Wikipedia infobox lists now
    source_title TEXT,                  -- the Wikipedia page, for checking
    status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'rejected')),
    detected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    note         TEXT
);
CREATE INDEX coordinator_changes_open ON coordinator_changes (status, team_id, season);
