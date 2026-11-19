-- Picks graded at the BETTABLE number and price (029): the Nov 17 rule for rule 5C and H-TOT.
-- pick_results grades each pick at the best number and price anywhere in the feed (Bovada, LowVig, BetOnline...),
-- which the user can't bet. This view takes the same picks (bet-time 'first' and last-before-kickoff 'last'), finds
-- the odds snapshot each pick was made from (the latest one saved at or before the pick, for that game), and grades
-- them at the best number, then best price, among the bettable books in that snapshot.
-- The bettable books are fixed here (user, 2026-11-17), not read from the admin setting, so a later edit of the
-- bet-form list can't change a past record: MyBookie, DraftKings, FanDuel, BetMGM, Caesars (williamhill_us), Fanatics.
-- A pick whose snapshot had no bettable book on its side gets NULLs (counted, not graded).

CREATE VIEW pick_results_bettable AS
WITH bettable (book) AS (
    VALUES ('mybookieag'), ('draftkings'), ('fanduel'), ('betmgm'), ('williamhill_us'), ('fanatics')
),
pick_snapshot AS (      -- the snapshot each pick was made from
    SELECT r.*,
           (SELECT max(s.fetched_at)
            FROM odds_snapshots s
            WHERE s.game_id = r.game_id
              AND s.fetched_at <= r.recorded_at
           ) AS snapshot_at
    FROM pick_results r
),
lines AS (              -- the bettable books' lines in that snapshot
    SELECT ps.game_id, ps.model_version, ps.taken, s.book, s.spread, s.home_price, s.away_price,
           s.total, s.over_price, s.under_price
    FROM pick_snapshot ps
    JOIN odds_snapshots s ON s.game_id = ps.game_id AND s.fetched_at = ps.snapshot_at
    JOIN bettable b ON b.book = s.book
),
best_spread AS (        -- best for our side: most points for a home bettor, fewest for an away bettor, then best price
    SELECT DISTINCT ON (ps.game_id, ps.model_version, ps.taken)
           ps.game_id, ps.model_version, ps.taken,
           l.book AS b_book, l.spread AS b_spread,
           CASE WHEN ps.side = 'home' THEN l.home_price ELSE l.away_price END AS b_price
    FROM pick_snapshot ps
    JOIN lines l USING (game_id, model_version, taken)
    WHERE ps.side IS NOT NULL AND l.spread IS NOT NULL
    ORDER BY ps.game_id, ps.model_version, ps.taken,
             CASE WHEN ps.side = 'home' THEN l.spread ELSE -l.spread END DESC,
             CASE WHEN ps.side = 'home' THEN l.home_price ELSE l.away_price END DESC
),
best_total AS (         -- best for an over: lowest total; for an under: highest total; then best price
    SELECT DISTINCT ON (ps.game_id, ps.model_version, ps.taken)
           ps.game_id, ps.model_version, ps.taken,
           l.book AS b_total_book, l.total AS b_total,
           CASE WHEN ps.total_side = 'over' THEN l.over_price ELSE l.under_price END AS b_total_price
    FROM pick_snapshot ps
    JOIN lines l USING (game_id, model_version, taken)
    WHERE ps.total_side IS NOT NULL AND l.total IS NOT NULL
    ORDER BY ps.game_id, ps.model_version, ps.taken,
             CASE WHEN ps.total_side = 'over' THEN -l.total ELSE l.total END DESC,
             CASE WHEN ps.total_side = 'over' THEN l.over_price ELSE l.under_price END DESC
),
graded AS (
    SELECT ps.game_id, ps.model_version, ps.taken, ps.recorded_at, ps.snapshot_at, ps.season, ps.week, ps.start_time,
           ps.tier, ps.side, ps.total_side, ps.result, ps.actual_total,
           -- best anywhere, as recorded (for comparison)
           ps.bet_spread, ps.bet_price, ps.bet_book, ps.spread_outcome, ps.spread_units,
           ps.bet_total, ps.total_price, ps.total_book, ps.total_outcome, ps.total_units,
           -- bettable
           bs.b_book, bs.b_spread, bs.b_price,
           CASE
               WHEN ps.result IS NULL OR bs.b_spread IS NULL THEN NULL
               WHEN ps.result = bs.b_spread THEN 'push'
               WHEN ps.side = 'home' AND ps.result < bs.b_spread THEN 'win'
               WHEN ps.side = 'away' AND ps.result > bs.b_spread THEN 'win'
               ELSE 'loss'
           END AS b_spread_outcome,
           bt.b_total_book, bt.b_total, bt.b_total_price,
           CASE
               WHEN ps.actual_total IS NULL OR bt.b_total IS NULL THEN NULL
               WHEN ps.actual_total = bt.b_total THEN 'push'
               WHEN ps.total_side = 'over' AND ps.actual_total > bt.b_total THEN 'win'
               WHEN ps.total_side = 'under' AND ps.actual_total < bt.b_total THEN 'win'
               ELSE 'loss'
           END AS b_total_outcome
    FROM pick_snapshot ps
    LEFT JOIN best_spread bs USING (game_id, model_version, taken)
    LEFT JOIN best_total bt USING (game_id, model_version, taken)
)
SELECT graded.*,
       -- Profit risking 1 unit at the bettable price
       CASE b_spread_outcome
           WHEN 'win' THEN CASE WHEN b_price > 0 THEN b_price / 100.0 ELSE 100.0 / -b_price END
           WHEN 'loss' THEN -1
           WHEN 'push' THEN 0
       END AS b_spread_units,
       CASE b_total_outcome
           WHEN 'win' THEN CASE WHEN b_total_price > 0 THEN b_total_price / 100.0 ELSE 100.0 / -b_total_price END
           WHEN 'loss' THEN -1
           WHEN 'push' THEN 0
       END AS b_total_units
FROM graded;
