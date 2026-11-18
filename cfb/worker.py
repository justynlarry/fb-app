"""Background worker.

- Every 30 s (game time) or 10 min (otherwise): live scores from ESPN, college and NFL.
- Every day at 5 AM: refresh this season from CFBD (games, stats, lines, latest week's QBs:
  4 calls), re-predict upcoming games, and save kickoff weather forecasts (Open-Meteo).
  If it didn't finish, it's retried at 5:30 and 7:30.
"""

import os
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from cfb import espn, nfl_model, nflverse
from cfb.backfill import refresh_recent_qbs
from cfb.db import connect
from cfb.load import refresh_season
from cfb.model import predict_upcoming
from cfb.odds import save_snapshot
from cfb.picks import record_picks
from cfb.status import job_run, ran_ok_today
from cfb.weather import update_forecasts

FAST = 30           # seconds between polls while games are on
SLOW = 600          # seconds between polls otherwise (10 minutes)
DAILY_HOUR = 5      # local time for the daily CFBD refresh + predictions
RETRY_HOURS = "5,7"     # retry at 5:30 and 7:30 if the 5 AM update didn't finish


def games_window_open():
    """True if any game (any league) kicked off in the last 5 hours or kicks off in the next 15 minutes."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM games
                WHERE start_time BETWEEN now() - interval '5 hours'
                                       AND now() + interval '15 minutes'
            )
            """
        ).fetchone()
    return row[0]


def current_season():
    """The football season for today. January bowls belong to the previous fall's season."""
    today = datetime.now()
    return today.year if today.month >= 8 else today.year - 1


def games_near(season, league="cfb"):
    """True if the league has games within 3 days back or 10 days ahead (i.e. it's in season)."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM games
                WHERE league = %s
                  AND season = %s
                  AND start_time BETWEEN now() - interval '3 days'
                                     AND now() + interval '10 days'
            )
            """,
            (league, season),
        ).fetchone()
    return row[0]


def daily_update():
    """Refresh this season from CFBD and re-predict upcoming games. Skips in the off-season."""
    season = current_season()
    with job_run("daily_update") as run:
        if not games_near(season):
            print(f"daily update: no {season} games this week or next, skipping")
            run.message = "skipped: no games this week or next"
            return
        print(f"daily update: refreshing {season} (4 CFBD calls) and re-predicting")
        try:
            refresh_season(season)
            refresh_recent_qbs(season)
            predict_upcoming(season)
            update_forecasts()
            run.message = f"refreshed {season}, re-predicted, weather saved"
        except Exception as err:
            print(f"daily update FAILED: {err!r}")
            run.fail(repr(err))


def daily_retry():
    """Run the daily update again if this morning's didn't finish (checked in job_runs, so restarts don't matter)."""
    if not ran_ok_today("daily_update"):
        print("daily update hasn't finished today, retrying.")
        daily_update()


def nfl_daily_update():
    """Reload this NFL season from nflverse (free, no API key) and re-predict upcoming games."""
    season = current_season()
    with job_run("nfl_daily_update") as run:
        if not games_near(season, "nfl"):
            print(f"NFL daily update: no {season} games this week or next, skipping")
            run.message = "skipped: no NFL games this week or next"
            return
        print(f"NFL daily update: reloading {season} from nflverse and re-predicting")
        try:
            nflverse.load_seasons([season])
            nfl_model.predict_upcoming(season)
            run.message = f"reloaded {season} from nflverse and re-predicted"
        except Exception as err:
            print(f"NFL daily update FAILED: {err!r}")
            run.fail(repr(err))


def odds_snapshot():
    """Save every book's current lines (2 Odds API credits per league in season), then our picks."""
    season = current_season()
    with job_run("odds_snapshot") as run:
        saved = []
        for league in ("cfb", "nfl"):
            if not games_near(season, league):
                continue
            try:
                save_snapshot(league)
            except Exception as err:
                print(f"odds snapshot ({league}) FAILED: {err!r}")
                run.fail(f"{league} snapshot: {err!r}")
                continue        # no fresh lines: don't record picks against old ones
            try:
                record_picks(league)
            except Exception as err:
                print(f"recording {league} picks FAILED: {err!r}")
                run.fail(f"{league} picks: {err!r}")
                continue
            saved.append(league)
        if run.ok:
            run.message = "saved " + (", ".join(saved) if saved else "nothing (no games near)")


def main():
    print("worker started")

    # Daily job runs in the background; the live-score loop below keeps going
    scheduler = BackgroundScheduler(timezone=os.environ.get("TZ", "America/Denver"))
    scheduler.add_job(daily_update, "cron", hour=DAILY_HOUR, minute=0, id="daily_update",
                      misfire_grace_time=3600, coalesce=True)
    scheduler.add_job(daily_retry, "cron", hour=RETRY_HOURS, minute=30, id="daily_retry",
                      misfire_grace_time=3600, coalesce=True)
    scheduler.add_job(nfl_daily_update, "cron", hour=5, minute=30, id="nfl_daily_update",
                      misfire_grace_time=3600, coalesce=True)
    # Odds API snapshots: every morning, Sunday for the openers, Saturday before kickoffs
    # ~47 snapshots x 2 credits per league in season = ~94 (one league) to ~190 (both) of our 500 credits a month
    scheduler.add_job(odds_snapshot, "cron", hour=6, minute=0, id="odds_daily",
                      misfire_grace_time=3600, coalesce=True)
    scheduler.add_job(odds_snapshot, "cron", day_of_week="sun", hour="16,20", minute=0, id="odds_openers",
                      misfire_grace_time=3600, coalesce=True)
    scheduler.add_job(odds_snapshot, "cron", day_of_week="sat", hour="9,12", minute=0, id="odds_gameday",
                      misfire_grace_time=3600, coalesce=True)
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
