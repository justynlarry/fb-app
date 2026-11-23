"""NFL injury reports from nflverse, for the injury panel on the Overrides page.

nflverse publishes one CSV per season and refreshes it once a day (around midnight Mountain).
Each row is one player on one team's report for one week:  his game status (Out, Doubtful,
Questionable, or blank) and his last practice status.  Free, no API key.

Display only:  the model doesn't read this table (T-skill was rejected, 2026-11-16).

    python -m cfb.nfl_injuries 2026
"""

import csv
import io
import sys

from cfb.db import connect
from cfb.nflverse import download, team_id

INJURIES_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"


def fetch_injuries(season):
    """Every row of this season's nflverse injury file, as a list of dicts."""
    text = download(INJURIES_URL.format(season=season)).text
    return list(csv.DictReader(io.StringIO(text)))


def nfl_team_ids(conn):
    """{ESPN abbreviation: our team id} for the 32 NFL teams already in the database."""
    rows = conn.execute("SELECT abbreviation, id FROM teams WHERE league = 'nfl'").fetchall()
    return {abbr: team for abbr, team in rows}


SAVE_SQL = """
INSERT INTO nfl_injuries (season, week, team_id, gsis_id, full_name, position,
                          report_status, injury, practice_status, loaded_at)
VALUES (%(season)s, %(week)s, %(team_id)s, %(gsis_id)s, %(full_name)s, %(position)s,
        %(report_status)s, %(injury)s, %(practice_status)s, now())
ON CONFLICT (season, week, team_id, gsis_id) DO UPDATE SET
    full_name       = EXCLUDED.full_name,
    position        = EXCLUDED.position,
    report_status   = EXCLUDED.report_status,
    injury          = EXCLUDED.injury,
    practice_status = EXCLUDED.practice_status,
    loaded_at       = EXCLUDED.loaded_at
"""


def save_injuries(conn, season, rows, team_ids):
    """Insert or update every row of the season's file.  Returns how many rows were saved."""
    saved = 0
    for row in rows:
        if int(row["season"]) != season:
            continue
        conn.execute(SAVE_SQL, {
            "season": season,
            "week": int(row["week"]),
            "team_id": team_id(team_ids, row["team"]),
            "gsis_id": row["gsis_id"],
            "full_name": row["full_name"],
            "position": row["position"] or None,
            "report_status": row["report_status"] or None,
            "injury": row["report_primary_injury"] or row["practice_primary_injury"] or None,
            "practice_status": row["practice_status"] or None,
        })
        saved += 1
    return saved


def load_injuries(season):
    """Download this season's injury file and save it in one transaction.  Returns rows saved."""
    rows = fetch_injuries(season)
    with connect() as conn:
        team_ids = nfl_team_ids(conn)
        saved = save_injuries(conn, season, rows, team_ids)
        conn.commit()
    print(f"NFL injuries {season}: {saved} rows saved")
    return saved


def main():
    if len(sys.argv) != 2:
        print("usage: python -m cfb.nfl_injuries 2026")
        sys.exit(1)
    load_injuries(int(sys.argv[1]))


if __name__ == "__main__":
    main()
