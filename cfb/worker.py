"""Background worker.

- Every 30 s (game time) or 10 min (otherwise): live scores from ESPN.
- Every day at 5 AM: refresh this season from CFBD (3 calls) and re-predict upcoming games.
"""

import os
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from cfb import espn
from cfb.db import connect
from cfb.load import refresh_season
from cfb.model import predict_upcoming

FAST = 30           # seconds between polls while games are on
SLOW = 600          # seconds between polls otherwise (10 minutes)
DAILY_HOUR = 5      # local time for the daily CFBD refresh + predictions


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


def current_season():
    """The football season for today. January bowls belong to the previous fall's season."""
    today = datetime.now()
    return today.year if today.month >= 8 else today.year - 1


def games_near(season):
    """True if the season has games within 3 days back or 10 days ahead (i.e. it's in season)."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM games
                WHERE league = 'cfb'
                  AND season = %s
                  AND start_time BETWEEN now() - interval '3 days'
                                     AND now() + interval '10 days'
            )
            """,
            (season,),
        ).fetchone()
    return row[0]


def daily_update():
    """Refresh this season from CFBD and re-predict upcoming games. Skips in the off-season."""
    season = current_season()
    if not games_near(season):
        print(f"daily update: no {season} games this week or next, skipping")
        return
    print(f"daily update: refreshing {season} (3 CFBD calls) and re-predicting")
    try:
        refresh_season(season)
        predict_upcoming(season)
    except Exception as err:
        print(f"daily update FAILED: {err!r}")


def main():
    print("worker started")

    # Daily job runs in the background; the live-score loop below keeps going
    scheduler = BackgroundScheduler(timezone=os.environ.get("TZ", "America/Denver"))
    scheduler.add_job(daily_update, "cron", hour=DAILY_HOUR, minute=0, id="daily_update")
    scheduler.start()
    print(f"next daily update: {scheduler.get_job('daily_update').next_run_time}")

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
