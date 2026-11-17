"""Load NFL line-movement tables into nfl_line_moves (for evaluating the model only).

The files live in reference/ on the host, which the containers can't see, so each file is
passed on standard input:

    docker compose exec -T worker python -m cfb.line_moves picksfootball < reference/point_spread_moves_2026.csv
    docker compose exec -T worker python -m cfb.line_moves sbro < reference/nfl_lines_2007-2022.csv

picksfootball: one block per week ("SEASON: WEEK: Nov 12-16, 2026"), two rows per game (away,
    then home). Each column (Opn, Mon ... Sat, Game Day) has the spread on the favourite's row
    and the total on the underdog's row; they swap when the favourite changes.
sbro (sportsbookreviewsonline): two rows per game (V/H, or N/N at a neutral site) with Open and
    Close in the same favourite-row/underdog-row layout. Dates are MMDD without a year.

Games are matched to our games table; games we don't have (sbro before 2016) are skipped and
counted. Re-running a file updates its rows in place.
"""

import csv
import sys
from collections import Counter
from datetime import date, timedelta

from cfb.db import connect

LEAGUE = "nfl"

# picksfootball columns, in order, starting at column 3 ("Opn"). None = a spacer column.
# "Cur" is kept only as a stand-in when Game Day is blank (Thursday games); "Proj" is the
# site's own guess, so it isn't stored.
PICKS_COLUMNS = ["open", "cur", "mon", "tue", "wed", "thu", "fri", "sat", None, "gameday", "proj"]
PICKS_SNAPSHOTS = ["open", "mon", "tue", "wed", "thu", "fri", "sat", "gameday"]
DAILY = ["mon", "tue", "wed", "thu", "fri", "sat", "gameday"]

MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}

# picksfootball uses nicknames; older names map to today's
NICKNAME_FIX = {"Redskins": "Commanders"}

# sbro writes city names without spaces; this maps them to our teams.school names
SBRO_TEAMS = {
    "Arizona": "Arizona Cardinals", "Atlanta": "Atlanta Falcons", "Baltimore": "Baltimore Ravens",
    "Buffalo": "Buffalo Bills", "BuffaloBills": "Buffalo Bills", "Carolina": "Carolina Panthers",
    "Chicago": "Chicago Bears", "Cincinnati": "Cincinnati Bengals", "Cleveland": "Cleveland Browns",
    "Dallas": "Dallas Cowboys", "Denver": "Denver Broncos", "Detroit": "Detroit Lions",
    "GreenBay": "Green Bay Packers", "Houston": "Houston Texans", "HoustonTexans": "Houston Texans",
    "Indianapolis": "Indianapolis Colts", "Jacksonville": "Jacksonville Jaguars",
    "KansasCity": "Kansas City Chiefs", "Kansas": "Kansas City Chiefs", "KCChiefs": "Kansas City Chiefs",
    "LAChargers": "Los Angeles Chargers", "SanDiego": "Los Angeles Chargers",
    "LARams": "Los Angeles Rams", "StLouis": "Los Angeles Rams", "St.Louis": "Los Angeles Rams",
    "Oakland": "Las Vegas Raiders", "LasVegas": "Las Vegas Raiders", "LVRaiders": "Las Vegas Raiders",
    "Miami": "Miami Dolphins", "Minnesota": "Minnesota Vikings", "NewEngland": "New England Patriots",
    "NewOrleans": "New Orleans Saints", "NYGiants": "New York Giants", "NYJets": "New York Jets",
    "Philadelphia": "Philadelphia Eagles", "Pittsburgh": "Pittsburgh Steelers",
    "SanFrancisco": "San Francisco 49ers", "Seattle": "Seattle Seahawks",
    "TampaBay": "Tampa Bay Buccaneers", "Tampa": "Tampa Bay Buccaneers", "Tennessee": "Tennessee Titans",
    "Washington": "Washington Commanders", "Washingtom": "Washington Commanders",
}

# A swap this big within a day can't be a real line move: the source put the daily
# columns on the wrong rows. Smaller flips are real (e.g. a QB ruled out) and are kept.
SWAP_GAP = 7


# ---------------------------------------------------------------- cells

def to_number(cell):
    """One table cell -> number, or None (blank), 'off' (off the board), 'bad' (typo).

    '47½' -> 47.5, '-3' -> -3.0, 'pk' -> 0.0.
    """
    text = cell.replace("\xa0", "").strip().lower()
    if text == "":
        return None
    if text == "pk":
        return 0.0
    if text == "off":
        return "off"
    text = text.replace("½", ".5")
    if text in (".5", "-.5"):
        text = text.replace(".5", "0.5")
    try:
        value = float(text)
    except ValueError:
        return "bad"
    if value * 2 != int(value * 2):     # lines are always whole or half points
        return "bad"
    return value


def split_pair(away_value, home_value):
    """The away and home cells of one column -> (home_spread, total).

    The smaller number is the spread and sits on the favourite's row; the other is the total.
    If both rows show a spread (same size, opposite signs) and no total, return (spread, None).
    Returns None when the pair makes no sense.
    """
    if abs(away_value) == abs(home_value) and abs(home_value) < 25:
        if away_value == -home_value:
            return home_value, None
        return None
    if abs(away_value) < abs(home_value):
        home_spread, total = abs(away_value), home_value     # away favoured -> home line is +
    else:
        home_spread, total = -abs(home_value), away_value    # home favoured -> home line is -
    if abs(home_spread) > 30 or not 25 <= total <= 75:
        return None
    return home_spread + 0.0, total      # + 0.0 turns a pick'em's -0.0 into 0.0


def read_pair(snapshots, flags, name, away_cell, home_cell):
    """Parse one column for one game into snapshots[name], noting problems in flags."""
    away_value, home_value = to_number(away_cell), to_number(home_cell)
    if away_value is None and home_value is None:
        return
    if "off" in (away_value, home_value):
        flags.append(f"{name}_off_board")
        return
    if "bad" in (away_value, home_value) or None in (away_value, home_value):
        flags.append(f"{name}_unreadable")
        return
    pair = split_pair(away_value, home_value)
    if pair is None:
        flags.append(f"{name}_unreadable")
        return
    if pair[1] is None:
        flags.append(f"{name}_no_total")
    snapshots[name] = pair


def to_moneyline(cell):
    try:
        return int(cell.replace("\xa0", "").strip())
    except ValueError:
        return None


# ---------------------------------------------------------------- picksfootball

def week_start(label):
    """'Nov 12-16, 2026', 'Oct 29, 2026 - Nov 2, 2026' or 'Jan 28, 2024' -> first day."""
    first = label.split(" - ")[0]                 # 'Nov 12-16, 2026' or 'Oct 29, 2026'
    month_day, year = first.rsplit(",", 1)
    month, day = month_day.split()
    day = day.split("-")[0]
    return date(int(year), MONTHS[month], int(day))


def fix_swapped_rows(snapshots, flags, away_ml, home_ml):
    """Some weeks show the daily lines on the wrong team's rows. Detect and fix that.

    Signs: the current line ('cur') agrees with the moneyline favourite. If a daily line has
    the other sign AND is SWAP_GAP+ points from 'cur', the rows were swapped (flip its sign).
    A smaller gap is a real change of favourite during the week: keep it, note it.
    """
    if "cur" not in snapshots or away_ml is None or home_ml is None:
        return
    current = snapshots["cur"][0]
    swapped = False
    flipped = False
    for name in DAILY:
        if name not in snapshots:
            continue
        spread, total = snapshots[name]
        if spread * current < 0:                       # opposite favourites
            if abs(spread - current) >= SWAP_GAP:
                snapshots[name] = (-spread, total)
                swapped = True
            else:
                flipped = True
    if swapped:
        flags.append("daily_rows_swapped_sign_fixed")
    if flipped:
        flags.append("favourite_flipped")


def read_picksfootball(lines):
    """The pasted table -> list of games (dicts)."""
    rows = list(csv.reader(lines))
    games = []
    label = None
    i = 0
    while i < len(rows):
        row = rows[i]
        if not any(cell.strip() for cell in row):
            i += 1
            continue
        if row[0].startswith("SEASON"):
            label = row[0].split("WEEK:")[1].strip()
            i += 1
            if i < len(rows) and "Away/Home" in rows[i][1]:
                i += 1                                   # the column-heading row
            continue
        away_row, home_row = rows[i], rows[i + 1]
        i += 2
        if home_row[0].startswith("SEASON"):
            raise ValueError(f"week {label}: odd number of team rows near {away_row[1]}")

        snapshots, flags = {}, []
        for name, away_cell, home_cell in zip(PICKS_COLUMNS, away_row[3:14], home_row[3:14]):
            if name is not None:
                read_pair(snapshots, flags, name, away_cell, home_cell)
        away_ml, home_ml = to_moneyline(away_row[0]), to_moneyline(home_row[0])
        fix_swapped_rows(snapshots, flags, away_ml, home_ml)
        if "gameday" not in snapshots and "cur" in snapshots:
            snapshots["gameday"] = snapshots["cur"]
            flags.append("gameday_from_cur")

        away = away_row[1].strip()
        home = home_row[1].strip()
        games.append({
            "label": label,
            "start": week_start(label),
            "away": NICKNAME_FIX.get(away, away),
            "home": NICKNAME_FIX.get(home, home),
            "away_ml": away_ml,
            "home_ml": home_ml,
            "away_pts": away_row[15].replace("\xa0", "").strip(),
            "home_pts": home_row[15].replace("\xa0", "").strip(),
            "snapshots": snapshots,
            "flags": flags,
        })
    return games


# ---------------------------------------------------------------- sbro

def sbro_team(name, season):
    name = name.strip()
    if name == "LosAngeles" and season == 2016:
        return "Los Angeles Rams"            # the only LA team in 2016
    if name == "NewYork" and season == 2013:
        return "New York Giants"             # 2013-11-10 Raiders at Giants, the only case
    if name not in SBRO_TEAMS:
        raise ValueError(f"unknown sbro team name: {name!r} ({season})")
    return SBRO_TEAMS[name]


def read_sbro(lines):
    """The archive table -> list of games (dicts)."""
    rows = [row for row in csv.reader(lines) if any(cell.strip() for cell in row)]
    rows = [row for row in rows if row[0] != "Season"]        # header, repeated once per season
    games = []
    for i in range(0, len(rows), 2):
        away_row, home_row = rows[i], rows[i + 1]
        if away_row[3] not in ("V", "N") or home_row[3] not in ("H", "N") or away_row[0] != home_row[0]:
            raise ValueError(f"rows don't pair up: {away_row[:5]} / {home_row[:5]}")
        season = int(away_row[0][:4])
        mmdd = away_row[1].strip().zfill(4)
        month, day = int(mmdd[:-2]), int(mmdd[-2:])
        year = season if month >= 7 else season + 1     # Jan/Feb games belong to the next year

        snapshots, flags = {}, []
        read_pair(snapshots, flags, "open", away_row[10], home_row[10])
        read_pair(snapshots, flags, "close", away_row[11], home_row[11])
        if season == 2021:
            flags.append("season_2021_close_suspect")

        games.append({
            "label": away_row[0],
            "season": season,
            "date": date(year, month, day),
            "away": sbro_team(away_row[4], season),
            "home": sbro_team(home_row[4], season),
            "away_ml": to_moneyline(away_row[12]),
            "home_ml": to_moneyline(home_row[12]),
            "away_pts": away_row[9].strip(),
            "home_pts": home_row[9].strip(),
            "snapshots": snapshots,
            "flags": flags,
        })
    return games


# ---------------------------------------------------------------- matching and saving

GAMES_SQL = """
    SELECT g.id, (g.start_time AT TIME ZONE 'America/New_York')::date AS game_date,
           h.school AS home, a.school AS away, g.home_points, g.away_points, l.spread
    FROM games g
    JOIN teams h ON h.id = g.home_id
    JOIN teams a ON a.id = g.away_id
    LEFT JOIN lines l ON l.game_id = g.id AND l.provider = 'nflverse'
    WHERE g.league = %s
"""

SAVE_SQL = """
    INSERT INTO nfl_line_moves (game_id, source, snapshot, home_spread, total,
                                home_moneyline, away_moneyline, flags)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (game_id, source, snapshot) DO UPDATE SET
        home_spread = EXCLUDED.home_spread,
        total = EXCLUDED.total,
        home_moneyline = EXCLUDED.home_moneyline,
        away_moneyline = EXCLUDED.away_moneyline,
        flags = EXCLUDED.flags
"""


def nickname(school):
    """'New York Giants' -> 'Giants'."""
    return school.split()[-1]


def find_picks_game(our_games, game):
    """Same two teams, kickoff within the week that starts on the heading's first day."""
    matches = [g for g in our_games
               if nickname(g["away"]) == game["away"] and nickname(g["home"]) == game["home"]
               and 0 <= (g["game_date"] - game["start"]).days <= 7]
    return matches[0] if len(matches) == 1 else None


def find_sbro_game(our_games, game):
    """Same teams, same date (late games can be listed a day off either way).

    At neutral sites sbro may list the teams the other way round from our games table;
    then the game is turned around to our home/away order (lines flipped, moneylines swapped).
    """
    for shift in (0, -1, 1):
        day = game["date"] + timedelta(days=shift)
        for g in our_games:
            if g["game_date"] != day:
                continue
            if g["home"] == game["home"] and g["away"] == game["away"]:
                return g
            if g["home"] == game["away"] and g["away"] == game["home"]:
                turn_around(game)
                return g
    return None


def turn_around(game):
    """Swap home and away in a game read from a file (used for neutral-site games)."""
    game["home"], game["away"] = game["away"], game["home"]
    game["home_ml"], game["away_ml"] = game["away_ml"], game["home_ml"]
    game["home_pts"], game["away_pts"] = game["away_pts"], game["home_pts"]
    for name, (spread, total) in game["snapshots"].items():
        game["snapshots"][name] = (-spread if spread else spread, total)
    game["flags"].append("home_away_swapped_to_match")


def save(source, games):
    final = "gameday" if source == "picksfootball" else "close"
    snapshot_names = PICKS_SNAPSHOTS if source == "picksfootball" else ["open", "close"]
    report = Counter()
    with connect() as conn:
        cur = conn.cursor()
        cur.execute(GAMES_SQL, (LEAGUE,))
        columns = [c.name for c in cur.description]
        our_games = [dict(zip(columns, row)) for row in cur.fetchall()]

        rows = []
        for game in games:
            finder = find_picks_game if source == "picksfootball" else find_sbro_game
            ours = finder(our_games, game)
            if ours is None:
                report["not in our games (skipped)"] += 1
                if source == "picksfootball" or game["season"] >= 2016:   # our NFL games start in 2016
                    print("  no match:", game["label"], game["away"], "@", game["home"])
                continue
            flags = list(game["flags"])
            if game["home_pts"] and (str(ours["home_points"]), str(ours["away_points"])) != (game["home_pts"], game["away_pts"]):
                flags.append(f"score_differs_from_db({game['away_pts']}-{game['home_pts']})")
            last = game["snapshots"].get(final)
            if last and ours["spread"] is not None and abs(last[0] - float(ours["spread"])) >= 2:
                flags.append(f"{final}_vs_nflverse_2plus")
            for name in snapshot_names:
                if name not in game["snapshots"]:
                    continue
                spread, total = game["snapshots"][name]
                home_ml = game["home_ml"] if name == final else None
                away_ml = game["away_ml"] if name == final else None
                rows.append((ours["id"], source, name, spread, total, home_ml, away_ml, ";".join(flags)))
            report["games saved"] += 1
            for flag in flags:
                report["flag: " + flag.split("(")[0]] += 1
        cur.executemany(SAVE_SQL, rows)
        conn.commit()
    report["rows saved"] = len(rows)
    for key, count in sorted(report.items()):
        print(f"  {key}: {count}")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("picksfootball", "sbro"):
        sys.exit("usage: python -m cfb.line_moves picksfootball|sbro < file.csv")
    source = sys.argv[1]
    text = sys.stdin.read().lstrip("﻿").splitlines()
    games = read_picksfootball(text) if source == "picksfootball" else read_sbro(text)
    print(f"{source}: {len(games)} games read")
    save(source, games)


if __name__ == "__main__":
    main()
