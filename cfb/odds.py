"""Sportsbook lines from The Odds API (free Starter plan: 500 credits a month).

One request returns every upcoming college game for every book in the region.
Cost = markets x regions = 2 credits (spreads + totals, US books).
Market lines are for display and grading only, not model inputs.
"""

import os
import unicodedata
from datetime import datetime, timezone

import httpx
from psycopg.types.json import Jsonb

from cfb.db import connect

BASE_URL = "https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf"
PARAMS = {"regions": "us", "markets": "spreads,totals", "oddsFormat": "american"}

# Their name -> our "school mascot", where it differs by more than accents or punctuation
NAME_FIXES = {
    "Appalachian State Mountaineers": "App State Mountaineers",
    "Sam Houston State Bearkats": "Sam Houston Bearkats",
    "Southern Mississippi Golden Eagles": "Southern Miss Golden Eagles",
}


def simplify(name):
    """'San José State Spartans' -> 'san jose state spartans' (no accents, apostrophes or periods)."""
    name = NAME_FIXES.get(name, name)
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return "".join(ch for ch in name.lower() if ch.isalnum() or ch == " ")


def team_lookup(conn):
    """{simplified 'school mascot': team id} for every college team."""
    rows = conn.execute("SELECT id, school, mascot FROM teams WHERE league = 'cfb'").fetchall()
    return {simplify(f"{school} {mascot or ''}".strip()): team_id for team_id, school, mascot in rows}


def find_game(conn, home_id, away_id, kickoff):
    """(our game id, swapped) for this matchup within 36 hours of kickoff, or (None, None).

    swapped = True when their home team is our away team (it happens at neutral sites).
    """
    row = conn.execute(
        """
        SELECT id, home_id <> %(home)s AS swapped
        FROM games
        WHERE league = 'cfb'
          AND ((home_id = %(home)s AND away_id = %(away)s)
            OR (home_id = %(away)s AND away_id = %(home)s))
          AND start_time BETWEEN %(kickoff)s - interval '36 hours'
                             AND %(kickoff)s + interval '36 hours'
        """,
        {"home": home_id, "away": away_id, "kickoff": kickoff},
    ).fetchone()
    return row if row else (None, None)


def fetch_odds():
    """Download current spreads and totals for every upcoming game (2 credits)."""
    params = {"apiKey": os.environ["ODDS_API_KEY"], **PARAMS}
    resp = httpx.get(f"{BASE_URL}/odds", params=params, timeout=30)
    if resp.status_code != 200:
        # Not raise_for_status(): its message includes the URL, and the URL contains our key
        raise RuntimeError(f"Odds API error {resp.status_code}: {resp.text[:200]}")
    print(f"Odds API: {resp.headers.get('x-requests-last')} credits used, "
          f"{resp.headers.get('x-requests-remaining')} left this month")
    return resp.json()


def book_line(book, home_team):
    """One book's spread (home side) and total for one game, with prices."""
    line = {"book": book["key"], "book_updated": book.get("last_update"),
            "spread": None, "home_price": None, "away_price": None,
            "total": None, "over_price": None, "under_price": None}
    for market in book["markets"]:
        for outcome in market["outcomes"]:
            if market["key"] == "spreads":
                if outcome["name"] == home_team:
                    line["spread"] = outcome["point"]
                    line["home_price"] = outcome["price"]
                else:
                    line["away_price"] = outcome["price"]
            elif market["key"] == "totals":
                line["total"] = outcome["point"]
                if outcome["name"] == "Over":
                    line["over_price"] = outcome["price"]
                else:
                    line["under_price"] = outcome["price"]
    return line


def save_snapshot():
    """Fetch every book's current lines and save them as one snapshot (2 credits)."""
    events = fetch_odds()
    fetched_at = datetime.now(timezone.utc)
    saved = 0
    unmatched = []
    with connect() as conn:
        # Keep the raw response, like every CFBD response, so we can re-read it later
        conn.execute(
            """
            INSERT INTO api_responses (source, endpoint, params, status, body)
            VALUES ('odds_api', '/odds', %s, 200, %s)
            """,
            (Jsonb({**PARAMS, "snapshot": fetched_at.isoformat()}), Jsonb(events)),
        )
        teams = team_lookup(conn)

        for event in events:
            home_id = teams.get(simplify(event["home_team"]))
            away_id = teams.get(simplify(event["away_team"]))
            kickoff = datetime.fromisoformat(event["commence_time"])
            game_id, swapped = (None, None)
            if home_id and away_id:
                game_id, swapped = find_game(conn, home_id, away_id, kickoff)
            if game_id is None:
                unmatched.append(f"{event['away_team']} @ {event['home_team']}")
                continue
            for book in event["bookmakers"]:
                line = book_line(book, event["home_team"])
                if swapped:
                    # Turn it around so it's from OUR home team's side
                    if line["spread"] is not None:
                        line["spread"] = -line["spread"]
                    line["home_price"], line["away_price"] = line["away_price"], line["home_price"]
                conn.execute(
                    """
                    INSERT INTO odds_snapshots (game_id, book, fetched_at, book_updated,
                                                spread, home_price, away_price,
                                                total, over_price, under_price)
                    VALUES (%(game_id)s, %(book)s, %(fetched_at)s, %(book_updated)s,
                            %(spread)s, %(home_price)s, %(away_price)s,
                            %(total)s, %(over_price)s, %(under_price)s)
                    ON CONFLICT (game_id, book, fetched_at) DO NOTHING
                    """,
                    {**line, "game_id": game_id, "fetched_at": fetched_at},
                )
                saved += 1
    print(f"odds snapshot: {saved} book lines for {len(events) - len(unmatched)} games")
    if unmatched:
        print(f"  not matched to our games: {unmatched}")
    return saved
