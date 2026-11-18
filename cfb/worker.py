"""Background worker.

- Live scores from ESPN, college and NFL: every 30 s while games are on, every 10 min otherwise.
- Every morning: refresh this season from CFBD (games, stats, lines, latest week's QBs: 4 calls),
  re-predict upcoming games, save kickoff weather forecasts (Open-Meteo); retried if it didn't finish.
  Then the NFL update (nflverse) and the odds snapshots, each followed by our picks.

The times and poll speeds are settings (cfb/schedule.py has the format and the defaults), editable on
the admin page.  The worker re-reads them every 5 minutes and rebuilds its jobs if they changed.
"""

import os
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from cfb import espn, nfl_model, nflverse, schedule
from cfb import settings as app_settings
from cfb.backfill import refresh_recent_qbs
from cfb.db import connect
from cfb.load import refresh_season
from cfb.model import predict_upcoming
from cfb.odds import save_snapshot
from cfb.picks import record_picks
from cfb.status import job_run, ran_ok_today
from cfb.weather import update_forecasts

FAST = 30           # fallback poll speeds (seconds), used only if the settings can't be read
SLOW = 600
TIMEZONE = os.environ.get("TZ", "America/Denver")
RELOAD_MINUTES = 5  # how often the worker re-reads its schedule from the settings

loaded_schedule = {}    # the schedule the scheduler is running now (job name -> times)


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


# Job name (as in cfb/schedule.py) -> the function that runs it
JOB_FUNCTIONS = {
    "daily_update": daily_update,
    "daily_retry": daily_retry,
    "nfl_daily_update": nfl_daily_update,
    "odds_snapshot": odds_snapshot,
}


def wanted_schedule():
    """The schedule in the settings, checked the same way the admin page checks it."""
    jobs = schedule.check(app_settings.get("job_schedule"), schedule.DEFAULT_JOB_SCHEDULE)
    odds = schedule.check(app_settings.get("odds_schedule"), schedule.DEFAULT_ODDS_SCHEDULE)
    return {**jobs, **odds}


def apply_schedule(scheduler):
    """(Re)build the scheduled jobs from the settings, if they changed.  A bad or unreadable
    schedule is reported and the jobs already running are kept."""
    try:
        wanted = wanted_schedule()
    except Exception as err:
        print(f"schedule NOT reloaded, keeping the current one: {err!r}")
        return
    if wanted == loaded_schedule:
        return
    for job in scheduler.get_jobs():
        if job.id != "reload_schedule":
            scheduler.remove_job(job.id)
    for name, entries in wanted.items():
        for i, entry in enumerate(entries):
            scheduler.add_job(JOB_FUNCTIONS[name], schedule.trigger(entry, TIMEZONE), id=f"{name}_{i}",
                              misfire_grace_time=3600, coalesce=True)
    loaded_schedule.clear()
    loaded_schedule.update(wanted)
    for name, entries in wanted.items():
        print(f"schedule: {name}: {schedule.describe(entries)}")


def poll_speeds():
    """Seconds between ESPN polls (while games are on, otherwise), from the settings."""
    try:
        return app_settings.get("poll_fast_seconds"), app_settings.get("poll_slow_seconds")
    except Exception as err:
        print(f"poll speeds not readable, using {FAST}/{SLOW} s: {err!r}")
        return FAST, SLOW


def main():
    print("worker started")

    # Scheduled jobs run in the background; the live-score loop below keeps going
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    apply_schedule(scheduler)
    scheduler.add_job(apply_schedule, "interval", minutes=RELOAD_MINUTES, args=[scheduler],
                      id="reload_schedule", coalesce=True)
    scheduler.start()
    first = min((j for j in scheduler.get_jobs() if j.id != "reload_schedule"), key=lambda j: j.next_run_time)
    print(f"next scheduled job: {first.id} at {first.next_run_time}")

    while True:
        live = 0
        try:
            live = espn.poll()
        except Exception as err:
            # A network blip or a strange ESPN response shouldn't kill the worker
            print(f"ESPN poll failed: {err!r}")

        fast, slow = poll_speeds()
        if live > 0 or games_window_open():
            time.sleep(fast)
        else:
            time.sleep(slow)


if __name__ == "__main__":
    main()
