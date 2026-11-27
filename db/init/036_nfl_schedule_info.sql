-- nflverse schedule columns we don't keep in games, saved each day the season is loaded, so we know what
-- was known when (rest days change with flex scheduling; retractable roofs are decided on game day;
-- temp / wind are observed, filled in only after the game).  Backfilled seasons get the load date as
-- as_of, so they aren't pre-game information.
CREATE TABLE nfl_schedule_info (
    game_id    integer     NOT NULL REFERENCES games (id),
    as_of      date        NOT NULL,          -- the day this copy of the nflverse file was loaded (Mountain)
    div_game   boolean,                       -- the two teams are in the same division
    away_rest  integer,                       -- days since each team's previous game
    home_rest  integer,
    roof       text,                          -- 'outdoors', 'dome', 'closed', 'open', or NULL (not decided yet)
    surface    text,
    temp       integer,                       -- observed at the game, degrees F (NULL before kickoff)
    wind       integer,                       -- observed at the game, mph (NULL before kickoff)
    stadium_id text,                          -- nflverse's stadium code, e.g. 'PIT00'
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (game_id, as_of)
);
