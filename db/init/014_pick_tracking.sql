-- Real-results tracking.
-- market_now: every game's current market from our latest odds snapshot (one row per game)
-- pick_log: our pick for each upcoming game, saved after every odds snapshot.  Never edited.
-- pick_results: the first and last pick before kickoff for each game, graded once it's final.

CREATE VIEW market_now AS
WITH latest AS (        -- each book's most recent line for each game
    SELECT DISTINCT ON (game_id, book)
        game_id, book, spread, home_price, away_price, total, over_price, under_price
    FROM odds_snapshots
    ORDER BY game_id, book, fetched_at DESC
),
books_now AS (          -- the middle of all books
    SELECT game_id,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY spread) AS spread,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY total) AS total,
        count(*) AS books
    FROM latest
    GROUP BY game_id
),
best_home AS (          -- best for a home bettor: most points, then best price
    SELECT DISTINCT ON (game_id) game_id, book, spread, home_price AS price
    FROM latest WHERE spread IS NOT NULL
    ORDER BY game_id, spread DESC, home_price DESC
),
best_away AS (          -- best for an away bettor: lowest home number, then best price
    SELECT DISTINCT ON (game_id) game_id, book, spread, away_price AS price
    FROM latest WHERE spread IS NOT NULL
    ORDER BY game_id, spread ASC, away_price DESC
),
best_over AS (          -- best over: lowest total
    SELECT DISTINCT ON (game_id) game_id, book, total, over_price AS price
    FROM latest WHERE total IS NOT NULL
    ORDER BY game_id, total ASC, over_price DESC
),
best_under AS (     -- best under: highest total
    SELECT DISTINCT ON (game_id) game_id, book, total, under_price AS price
    FROM latest WHERE total IS NOT NULL
    ORDER BY game_id, total DESC, under_price DESC
)
SELECT bn.game_id,
       bn.books,
       bn.spread,
       bn.total,
       bh.book AS best_home_book,  bh.spread AS best_home_spread, bh.price AS best_home_price,
       ba.book AS best_away_book,  ba.spread AS best_away_spread, ba.price AS best_away_price,
       bo.book AS best_over_book,  bo.total AS best_over_total,   bo.price AS best_over_price,
       bu.book AS best_under_book, bu.total AS best_under_total,  bu.price AS best_under_price
FROM books_now bn
LEFT JOIN best_home bh ON bh.game_id = bn.game_id
LEFT JOIN best_away ba ON ba.game_id = bn.game_id
LEFT JOIN best_over bo ON bo.game_id = bn.game_id
LEFT JOIN best_under bu ON bu.game_id = bn.game_id;

CREATE TABLE pick_log (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id         integer NOT NULL REFERENCES games(id),
    model_version   text NOT NULL,
    recorded_at     timestamptz NOT NULL,
    our_spread      numeric(5,2) NOT NULL,      -- our line, overrides included (home side)
    our_total       numeric(5,2) NOT NULL,
    market_spread   numeric(5,2),               -- median of the books at that moment
    market_total    numeric(5,2),
    open_spread     numeric(5,2),               -- CFBD opening line (average of books)
    books           smallint,
    tier            text NOT NULL,              -- 'play', 'caution' or 'pass'
    side            text,                       -- 'home' or 'away'; NULL if we match the market exactly
    bet_spread      numeric(5,2),               -- best number for our side (home-side sign)
    bet_price       smallint,                   -- American odds at that book
    bet_book        text,
    total_side      text,                       -- 'over' or 'under' when 3+ off, else NULL
    bet_total       numeric(5,2),
    total_price     smallint,
    total_book      text,
    UNIQUE (game_id, model_version, recorded_at)
);

CREATE VIEW pick_results AS
WITH first_pick AS (    -- earliest pick we recorded for each game
    SELECT DISTINCT ON (p.game_id, p.model_version) p.*, 'first' AS taken
    FROM pick_log p
    JOIN games g ON g.id = p.game_id
    WHERE p.recorded_at < g.start_time
    ORDER BY p.game_id, p.model_version, p.recorded_at
),
last_pick AS (          -- the last one before kickoff
    SELECT DISTINCT ON (p.game_id, p.model_version) p.*, 'last' AS taken
    FROM pick_log p
    JOIN games g ON g.id = p.game_id
    WHERE p.recorded_at < g.start_time
    ORDER BY p.game_id, p.model_version, p.recorded_at DESC
),
picks AS (
    SELECT * FROM first_pick
    UNION ALL
    SELECT * FROM last_pick
),
graded AS (
    SELECT p.*,
           g.season, g.week, g.start_time,
           g.away_points - g.home_points AS result,
           g.away_points + g.home_points AS actual_total,
           CASE
               WHEN NOT g.completed OR p.side IS NULL THEN NULL
               WHEN g.away_points - g.home_points = p.bet_spread THEN 'push'
               WHEN p.side = 'home' AND g.away_points - g.home_points < p.bet_spread THEN 'win'
               WHEN p.side = 'away' AND g.away_points - g.home_points > p.bet_spread THEN 'win'
               ELSE 'loss'
           END AS spread_outcome,
           CASE
               WHEN NOT g.completed OR p.total_side IS NULL THEN NULL
               WHEN g.away_points + g.home_points = p.bet_total THEN 'push'
               WHEN p.total_side = 'over' AND g.away_points + g.home_points > p.bet_total THEN 'win'
               WHEN p.total_side = 'under' AND g.away_points + g.home_points < p.bet_total THEN 'win'
               ELSE 'loss'
           END AS total_outcome
    FROM picks p
    JOIN games g ON g.id = p.game_id
)
SELECT graded.*,
       -- Profit risking 1 unit: a win pays 100/110 at -110, 1.5 at +150; a loss costs 1
       CASE spread_outcome
           WHEN 'win' THEN CASE WHEN bet_price > 0 THEN bet_price / 100.0 ELSE 100.0 / -bet_price END
           WHEN 'loss' THEN -1
           WHEN 'push' THEN 0
       END AS spread_units,
       CASE total_outcome
           WHEN 'win' THEN CASE WHEN total_price > 0 THEN total_price / 100.0 ELSE 100.0 / -total_price END
           WHEN 'loss' THEN -1
           WHEN 'push' THEN 0
       END AS total_units
FROM graded;
