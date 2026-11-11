-- Each team's division AT THE TIME of the game (teams change divisions over the years)
ALTER TABLE games ADD COLUMN home_classification TEXT;   -- 'fbs', 'fcs', 'ii', 'iii'
ALTER TABLE games ADD COLUMN away_classification TEXT;
