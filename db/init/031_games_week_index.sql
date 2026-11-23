-- Speeds up "first kickoff of this week" in pick_results (019/022): Postgres can read
-- min(start_time) for a league/season/week/season_type straight from this index.
-- Without it the lookup walked games_start_time_idx from 2016 forward (~5 ms each, hundreds per scan):
-- Results page queries 9.1 s -> 1.9 s (measured 2026-11-22).
CREATE INDEX IF NOT EXISTS games_week_start_idx
    ON games (league, season, week, season_type, start_time);
