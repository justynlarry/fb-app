-- Extra fields from ESPN's scoreboard: betting line, rankings and records.
-- Spread is from the HOME team's side, same as the lines table.

ALTER TABLE live_scores
    ADD COLUMN spread              NUMERIC(5,2),
    ADD COLUMN over_under          NUMERIC(5,2),
    ADD COLUMN odds_details        TEXT,       -- ESPN's text, e.g. 'OHIO -1.5'
    ADD COLUMN away_rank           SMALLINT,   -- 1-25, NULL if unranked
    ADD COLUMN home_rank           SMALLINT,
    ADD COLUMN away_record         TEXT,       -- '7-2'
    ADD COLUMN home_record         TEXT,
    ADD COLUMN away_conf_record    TEXT,       -- '5-0'
    ADD COLUMN home_conf_record    TEXT;
