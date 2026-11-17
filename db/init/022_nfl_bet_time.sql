-- pick_results: NFL bet time (paper-tracking step 2, decided 2026-11-17).
-- College is unchanged from 019: the first save with 4+ books, 8+ hours after both teams' previous kickoff.
-- NFL: "the" bet is the first save with 4+ books on MONDAY of game week, from 6:00 AM Mountain until
-- 6:00 AM Tuesday. That's the Monday line tested in T-OPEN. Monday of game week = the Monday on or before
-- the week's first kickoff (Thursday for most weeks, Saturday for Wild Card weekend). If there's no Monday
-- save (snapshot failed, or before logging started: week 11 of 2026), the game has no 'first' NFL pick;
-- a later save is NOT used in its place, because it isn't the line being tested.
-- Same columns as 014/019, so CREATE OR REPLACE keeps everything that reads this view working.

CREATE OR REPLACE VIEW pick_results AS
WITH pick_games AS (    -- each game we have picks for, with its week's first kickoff in Mountain time
    SELECT g.id AS game_id,
           g.league,
           g.season,
           g.start_time,
           g.home_id,
           g.away_id,
           (SELECT min(w.start_time)
            FROM games w
            WHERE w.league = g.league
              AND w.season = g.season
              AND w.week = g.week
              AND w.season_type = g.season_type
           ) AT TIME ZONE 'America/Denver' AS week_first_local
    FROM games g
    WHERE g.id IN (SELECT game_id FROM pick_log)
),
bet_time AS (           -- for each game: the window in which its bet-time pick must be saved
    SELECT pg.game_id,
           pg.start_time,
           CASE
               WHEN pg.league = 'nfl' THEN
                   -- Monday 6:00 AM Mountain of game week
                   (date_trunc('week', pg.week_first_local) + interval '6 hours') AT TIME ZONE 'America/Denver'
               ELSE
                   -- the latest earlier kickoff by either team this season (NULL = first game of the season)
                   (SELECT max(e.start_time)
                    FROM games e
                    WHERE e.league = pg.league
                      AND e.season = pg.season
                      AND e.start_time < pg.start_time
                      AND (e.home_id IN (pg.home_id, pg.away_id) OR e.away_id IN (pg.home_id, pg.away_id))
                   ) + interval '8 hours'          -- game over, and our 5 AM update has its stats
           END AS earliest,
           CASE
               WHEN pg.league = 'nfl' THEN
                   -- Tuesday 6:00 AM Mountain: Monday only
                   (date_trunc('week', pg.week_first_local) + interval '30 hours') AT TIME ZONE 'America/Denver'
           END AS latest                           -- NULL = no limit (college)
    FROM pick_games pg
),
first_pick AS (         -- the pick at bet time: the first one made against a real opening market
    SELECT DISTINCT ON (p.game_id, p.model_version) p.*, 'first' AS taken
    FROM pick_log p
    JOIN bet_time b ON b.game_id = p.game_id
    WHERE p.recorded_at < b.start_time
      AND p.books >= 4                                          -- lookahead lines sit at 1-2 books
      AND (b.earliest IS NULL OR p.recorded_at >= b.earliest)
      AND (b.latest IS NULL OR p.recorded_at < b.latest)
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
