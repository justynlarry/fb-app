-- Offensive and defensive coordinators per team-season (026).
-- History 2015-2025 comes from Wikipedia team-season infoboxes (off_coach / def_coach, co-coordinator fields
-- included): the season's listed staff, which may include in-season replacements ("first 4 games", "interim").
-- Used by T-OCDC (docs/model-tests.md section 10) and for override suggestions.  Later seasons and mid-season
-- changes can be added by hand with source = 'manual'.

CREATE TABLE coordinators (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_id      INTEGER NOT NULL REFERENCES teams (id),
    season       SMALLINT NOT NULL,
    unit         TEXT NOT NULL CHECK (unit IN ('offense', 'defense')),
    names        TEXT[] NOT NULL,       -- everyone listed for the season; empty = none listed (head coach calls it)
    is_new       BOOLEAN,               -- none of these names was listed last season (T-OCDC rule); NULL = no previous season
    raw_field    TEXT,                  -- the infobox text as fetched, for checking
    source       TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('wikipedia', 'manual')),
    source_title TEXT,                  -- Wikipedia page title
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (team_id, season, unit)
);
CREATE INDEX coordinators_season ON coordinators (season, team_id);
