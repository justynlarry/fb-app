-- Settings an admin can change on the admin page (024).
-- A key with no row here uses its default from cfb/settings.py, so an empty table = today's behavior.

CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_by  INTEGER REFERENCES users (id),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every change, kept forever: who changed what, when, from what to what, and why
CREATE TABLE settings_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key         TEXT NOT NULL,
    old_value   JSONB,              -- NULL = it was still the default
    new_value   JSONB NOT NULL,
    reason      TEXT,
    changed_by  INTEGER REFERENCES users (id),
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX settings_log_key ON settings_log (key, changed_at);