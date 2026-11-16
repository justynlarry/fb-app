-- pick_results: the 'first' pick is now the pick at BET TIME, not the first one ever logged.
-- The Odds API also returns lookahead lines: one or two books posting next week's game before this
-- week's games are played. Our line for that game doesn't have this week's results yet, so grading
-- that pick as our "early bet" mixes two different bets (audit 2026-11-16, 1.2).
-- Bet time = the first snapshot that is (a) at least 8 hours after both teams' previous kickoff and
-- (b) has 4 or more books, which in practice is Sunday 4 PM Mountain for Saturday teams.
-- Lookahead picks stay in pick_log; they just aren't graded here. The 'last' pick is unchanged.
-- Same columns as 014, so CREATE OR REPLACE keeps everything that reads this view working.

CREATE OR REPLACE VIEW pick_results AS
WITH bet_time AS (      -- for each game we have picks for: when the real market for it can open
    SELECT g.id AS game_id,
           g.start_time,
           -- the latest earlier kickoff by either team this season (NULL = first game of the season)
           (SELECT max(e.start_time)
            FROM games e
            WHERE e.league = g.league
              AND e.season = g.season
              AND e.start_time < g.start_time
              AND (e.home_id IN (g.home_id, g.away_id) OR e.away_id IN (g.home_id, g.away_id))
           ) + interval '8 hours' AS earliest      -- game over, and our 5 AM update has its stats
    FROM games g
    WHERE g.id IN (SELECT game_id FROM pick_log)
),
first_pick AS (         -- the pick at bet time: the first one made against a real opening market
    SELECT DISTINCT ON (p.game_id, p.model_version) p.*, 'first' AS taken
    FROM pick_log p
    JOIN bet_time b ON b.game_id = p.game_id
    WHERE p.recorded_at < b.start_time
      AND p.books >= 4                                          -- lookahead lines sit at 1-2 books
      AND (b.earliest IS NULL OR p.recorded_at >= b.earliest)   -- after both teams' previous games
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
