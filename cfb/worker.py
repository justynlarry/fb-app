"""Background worker: keeps live_scores up to date from ESPN.

Daily CFBD refresh jobs get added here later.
"""

import time

from cfb import espn
from cfb.db import connect

FAST = 30   # seconds between polls while games are on
SLOW = 600  # seconds between polls otherwise (10 minutes)


def games_window_open():
    """True if any game kicked off in the last 5 hours or kicks off in the next 15 minutes."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM games
                WHERE league = 'cfb'
                    AND start_time BETWEEN now() - interval '5 hours'
                                       AND now() + interval '15 minutes'
            )
            """
        ).fetchone()
    return row[0]


def main():
    print("worker started")
    while True:
        live = 0
        try:
            live = espn.poll()
        except Exception as err:
            # A network blip or a strange ESPN response shouldn't kill the worker
            print(f"ESPN poll failed: {err!r}")

        if live > 0 or games_window_open():
            time.sleep(FAST)
        else:
            time.sleep(SLOW)


if __name__ == "__main__":
    main()
