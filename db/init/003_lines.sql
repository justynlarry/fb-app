-- Betting lines, one row per game per sportsbook.
-- Spreads are from the HOME team's side: -7 means home is favored by 7.

CREATE TABLE lines (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id         INTEGER NOT NULL REFERENCES games (id),
    provider        TEXT NOT NULL,          -- 'Bovada', 'DraftKings', 'ESPN Bet'
    spread          NUMERIC(5,2),           -- Latest line (treated as closing)
    spread_open     NUMERIC(5,2),           -- Opening Line, NULL if the book didn't give one
    over_under      NUMERIC(5,2),
    over_under_open NUMERIC(5,2),
    home_moneyline  INTEGER,                -- American odds, e.g. -140 or +120
    away_moneyline  INTEGER,
    UNIQUE (game_id, provider)
);
