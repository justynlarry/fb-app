-- market_now: use only snapshots taken BEFORE kickoff.
-- The Odds API also returns games in progress with live in-game lines; those aren't the market we bet into.
-- After kickoff, "now" becomes the closing line (the last snapshot before the game started).
CREATE OR REPLACE VIEW market_now AS
WITH latest AS (        -- each book's most recent pre-kickoff line for each game
    SELECT DISTINCT ON (s.game_id, s.book)
           s.game_id, s.book, s.spread, s.home_price, s.away_price, s.total, s.over_price, s.under_price
    FROM odds_snapshots s
    JOIN games g ON g.id = s.game_id
    WHERE s.fetched_at < g.start_time
    ORDER BY s.game_id, s.book, s.fetched_at DESC
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

