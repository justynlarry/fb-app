-- NFL lines at several moments before kickoff, from pasted/downloaded tables (no API calls).
-- Filled by cfb/line_moves.py. Used only to evaluate the model (line movement, "at the open"
-- tests), never as a model input.
--
-- source       snapshots                                          seasons
-- picksfootball open, mon, tue, wed, thu, fri, sat, gameday        2023- (Monday line = the one to use;
--                                                                         'open' is a lookahead line)
-- sbro          open, close                                        2007-2021 (open is mostly a lookahead
--                                                                         line; 2021 closes are suspect)
--
-- home_spread uses the same sign as lines.spread: negative = home team favoured.

CREATE TABLE nfl_line_moves (
    game_id         INTEGER NOT NULL REFERENCES games (id),
    source          TEXT NOT NULL,
    snapshot        TEXT NOT NULL,
    home_spread     NUMERIC(5,2),
    total           NUMERIC(5,2),
    home_moneyline  INTEGER,         -- only where the source gives one (picksfootball 'gameday', sbro 'close')
    away_moneyline  INTEGER,
    flags           TEXT NOT NULL DEFAULT '',   -- ';'-separated notes about this game from this source
    PRIMARY KEY (game_id, source, snapshot)
);
