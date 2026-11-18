-- Bets people actually placed (023).  Each user's own record, graded by the bet_results view.

-- Per-user settings for the bets page
ALTER TABLE users
    ADD COLUMN unit_size    NUMERIC(10,2) CHECK (unit_size > 0),        -- dollars per unit; NULL = not set yet
    ADD COLUMN share_bets   BOOLEAN NOT NULL DEFAULT false;             -- let other users see my record

CREATE TABLE bets (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    game_id     INTEGER NOT NULL REFERENCES games (id),
    bet_type    TEXT NOT NULL CHECK (bet_type IN ('spread', 'total', 'moneyline')),
    side        TEXT NOT NULL,
    line        NUMERIC(5,1),           -- spread: the HOME team's number (-7 = home favored); total: the total; moneyline: NULL
    price       INTEGER NOT NULL CHECK (price <= -100 OR price >= 100),
    book        TEXT NOT NULL,
    stake       NUMERIC(10,2) NOT NULL CHECK (stake > 0),   -- dollars risked
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    removed_at  TIMESTAMPTZ,            -- set when the user removes it; the row is kept for history
    -- each bet type has its own sides, and only moneyline has no line
    CHECK (
        (bet_type = 'spread'    AND side IN ('home', 'away') AND line IS NOT NULL) OR
        (bet_type = 'total'     AND side IN ('over', 'under') AND line IS NOT NULL) OR
        (bet_type = 'moneyline' AND side IN ('home', 'away') AND line IS NULL)
    )
);

CREATE INDEX bets_user ON bets (user_id);
CREATE INDEX bets_game ON bets (game_id);


-- Each bet graded from the final score, with profit in dollars.  Removed bets are left out.
CREATE VIEW bet_results AS
WITH graded AS (
    SELECT b.*,
        g.league,
        g.start_time,
        g.home_points,
        g.away_points,
        b.created_at > g.start_time AS logged_after_kickoff,
        CASE
            WHEN NOT g.completed THEN NULL
            WHEN b.bet_type = 'spread' THEN
                CASE
                    WHEN g.away_points - g.home_points = b.line THEN 'push'
                    WHEN b.side = 'home' AND g.away_points - g.home_points < b.line THEN 'win'
                    WHEN b.side = 'away' AND g.away_points - g.home_points > b.line THEN 'win'
                    ELSE 'loss'
                END
            WHEN b.bet_type = 'total' THEN
                CASE
                    WHEN g.away_points + g.home_points = b.line THEN 'push'
                    WHEN b.side = 'over' AND g.away_points + g.home_points > b.line THEN 'win'
                    WHEN b.side = 'under' AND g.away_points + g.home_points < b.line THEN 'win'
                    ELSE 'loss'
                END
            ELSE   -- moneyline
                CASE
                    WHEN g.home_points = g.away_points THEN 'push'
                    WHEN b.side = 'home' AND g.home_points > g.away_points THEN 'win'
                    WHEN b.side = 'away' AND g.away_points > g.home_points THEN 'win'
                    ELSE 'loss'
                END
        END AS outcome
    FROM bets b
    JOIN games g ON g.id = b.game_id
    WHERE b.removed_at IS NULL
)
SELECT graded.*,
    -- A win at -110 pays 100/110 of the stake, at +150 pays 1.5x; a loss costs the stake
    CASE outcome
        WHEN 'win'  THEN round(stake * CASE WHEN price > 0 THEN price / 100.0 ELSE 100.0 / -price END, 2)
        WHEN 'loss' THEN -stake
        WHEN 'push' THEN 0
    END AS profit
FROM graded;