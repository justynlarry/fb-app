-- TV / streaming networks per game, as ESPN's scoreboard lists them (free, each poll).
-- One row per game, market and network. first_seen / last_seen say when we saw it, so an
-- analysis can use only what was known before bet time, and a network that was dropped
-- (flex scheduling) keeps its old last_seen.
CREATE TABLE game_broadcasts (
    game_id    integer     NOT NULL REFERENCES games (id),
    market     text        NOT NULL,          -- ESPN's market: 'national', 'home', 'away'
    network    text        NOT NULL,          -- e.g. 'ABC', 'ESPN+', 'CBS', 'Prime Video'
    first_seen timestamptz NOT NULL DEFAULT now(),
    last_seen  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (game_id, market, network)
);
