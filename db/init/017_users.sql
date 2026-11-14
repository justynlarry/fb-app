-- App login: user accounts, login sessions, and login attempts (for rate limiting).

CREATE TABLE users (
    id                      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username                TEXT NOT NULL,
    password_hash           TEXT NOT NULL,
    is_admin                BOOLEAN NOT NULL DEFAULT false,
    must_change_password    BOOLEAN NOT NULL DEFAULT true,
    active                  BOOLEAN NOT NULL DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at           TIMESTAMPTZ
);

-- "Justyn" and "justyn" are same user.
CREATE UNIQUE INDEX users_username_lower ON users (lower(username));

CREATE TABLE sessions (
    token_hash      TEXT PRIMARY KEY,       -- sha256 of the cookie value, not value itself
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL
);
CREATE INDEX sessions_user ON sessions (user_id);

CREATE TABLE login_attempts (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username    TEXT NOT NULL,
    ip          INET,
    success     BOOLEAN NOT NULL,
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX login_attempts_at ON login_attempts (at);