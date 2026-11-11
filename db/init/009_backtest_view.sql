-- One row per graded prediction: the model vs. the market vs. what happened.
-- Spreads are HOME side (-7 = home by 7); result = away_points - home_points uses the same sign.

CREATE VIEW backtest_games AS
WITH market AS (
    SELECT game_id,
           avg(spread)      AS close_spread,
           avg(spread_open) AS open_spread,
           avg(over_under)  AS close_total
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
       END AS clv_win
FROM predictions p
JOIN games g  ON g.id = p.game_id
JOIN market m ON m.game_id = p.game_id
WHERE g.completed
  AND m.close_spread IS NOT NULL;
