-- Every book's lines from the Odds API, saved several times a day.
-- Our "open" = the first snapshot of a game; "now" = the latest one.

CREATE TABLE odds_snapshots (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id         INTEGER NOT NULL REFERENCES games(id),
    book            TEXT NOT NULL,              -- e.g. 'draftkings'
    fetched_at      TIMESTAMPTZ NOT NULL,       -- when we took the snapshot
    book_updated    TIMESTAMPTZ,                -- when the book last changed its line
    spread          NUMERIC(5,2),               -- home side: negative = home favored
    home_price      SMALLINT,                   -- American Odds, e.g. -110
    away_price      SMALLINT,
    total           NUMERIC(5,2),
    over_price      SMALLINT,
    under_price     SMALLINT,
    UNIQUE (game_id, book, fetched_at)
);

CREATE INDEX odds_snapshots_game_time ON odds_snapshots (game_id, fetched_at);
