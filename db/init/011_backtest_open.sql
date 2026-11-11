-- Same view as 009, plus grading at the OPENING line (average and best number across books).
-- CREATE OR REPLACE VIEW keeps existing columns in place; new columns are added at the end.
CREATE OR REPLACE VIEW backtest_games AS
WITH market AS (
    SELECT game_id,
           avg(spread)      AS close_spread,
           avg(spread_open) AS open_spread,
           avg(over_under)  AS close_total,
           max(spread_open) AS open_high,      -- best opening number if we take the home team
           min(spread_open) AS open_low        -- best opening number if we take the away team
    FROM lines
    GROUP BY game_id
)
SELECT p.game_id,
       p.model_version,
       p.is_backtest,
       g.season,
       LEAST(p.weeks_played, 6)        AS weeks_bucket,
       g.away_points - g.home_points   AS result,
       g.home_points + g.away_points   AS actual_total,
       p.spread                        AS model_spread,
       p.total                         AS model_total,
       m.close_spread,
       m.open_spread,
       m.close_total,
       p.spread - m.close_spread       AS spread_diff,
       p.total - m.close_total         AS total_diff,
       p.spread - m.open_spread        AS open_diff,
       -- Did our side cover the closing line? (NULL = push)
       CASE WHEN g.away_points - g.home_points = m.close_spread THEN NULL
            WHEN p.spread < m.close_spread THEN g.away_points - g.home_points < m.close_spread
            ELSE g.away_points - g.home_points > m.close_spread
       END AS spread_win,
       -- Did our over/under side win? (NULL = push)
       CASE WHEN g.home_points + g.away_points = m.close_total THEN NULL
            WHEN p.total > m.close_total THEN g.home_points + g.away_points > m.close_total
            ELSE g.home_points + g.away_points < m.close_total
       END AS total_win,
       -- Closing line value: did the line move from open toward our number? (NULL = didn't move)
       CASE WHEN m.open_spread IS NULL OR m.close_spread = m.open_spread THEN NULL
            ELSE sign(m.close_spread - m.open_spread) = sign(p.spread - m.open_spread)
       END AS clv_win,
       -- NEW: did our side (chosen vs the opening line) cover the average opening line?
       CASE WHEN m.open_spread IS NULL OR g.away_points - g.home_points = m.open_spread THEN NULL
            WHEN p.spread < m.open_spread THEN g.away_points - g.home_points < m.open_spread
            ELSE g.away_points - g.home_points > m.open_spread
       END AS open_win,
       -- NEW: the best opening number for our side (line shopping across books)
       CASE WHEN p.spread < m.open_spread THEN m.open_high ELSE m.open_low END AS best_open,
       -- NEW: did our side cover that best opening number?
       CASE WHEN m.open_spread IS NULL THEN NULL
            WHEN p.spread < m.open_spread THEN
                 CASE WHEN g.away_points - g.home_points = m.open_high THEN NULL
                      ELSE g.away_points - g.home_points < m.open_high END
            ELSE CASE WHEN g.away_points - g.home_points = m.open_low THEN NULL
                      ELSE g.away_points - g.home_points > m.open_low END
       END AS best_open_win
FROM predictions p
JOIN games g  ON g.id = p.game_id
JOIN market m ON m.game_id = p.game_id
WHERE g.completed
  AND m.close_spread IS NOT NULL;
