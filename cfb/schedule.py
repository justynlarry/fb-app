"""The worker's job schedule: its format, the defaults, checks, warnings, and APScheduler triggers.

A schedule is a dict of job name -> list of times, each {"days": "daily" or "mon".."sun", "time": "HH:MM"},
in the worker's time zone (TZ, Mountain).  Two settings hold it (cfb/settings.py):

    odds_schedule  the odds snapshots (and the picks recorded after each).  It decides which lines picks
                   are recorded at, so a change needs a reason and is listed on the Results page.
    job_schedule   the daily updates and their retries.

The web app and the worker both use this module, so the admin page checks a schedule exactly the
way the worker will read it.
"""

import re

from apscheduler.triggers.cron import CronTrigger

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_NAMES = {"daily": "Daily", "mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri",
             "sat": "Sat", "sun": "Sun"}

# Job name -> what it does (admin page labels)
JOBS = {
    "daily_update": "College update: CFBD, predictions, weather",
    "daily_retry": "Retry the college update if it hasn't finished",
    "nfl_daily_update": "NFL update: nflverse, predictions",
    "odds_snapshot": "Odds snapshot + picks",
}
OPTIONAL_JOBS = {"daily_retry"}         # may have no times at all; every other job needs at least one

# Today's schedule (the one every pick so far was recorded under), in check()'s order (daily, then Mon..Sun),
# so a saved schedule that matches it compares equal
DEFAULT_JOB_SCHEDULE = {
    "daily_update": [{"days": "daily", "time": "05:00"}],
    "daily_retry": [{"days": "daily", "time": "05:30"}, {"days": "daily", "time": "07:30"}],
    "nfl_daily_update": [{"days": "daily", "time": "05:30"}],
}
DEFAULT_ODDS_SCHEDULE = {
    "odds_snapshot": [
        {"days": "daily", "time": "06:00"},     # morning lines (and the NFL Monday 6 AM bet time)
        {"days": "sat", "time": "09:00"},       # before Saturday's kickoffs
        {"days": "sat", "time": "12:00"},
        {"days": "sun", "time": "16:00"},       # college openers (the usual college bet time)
        {"days": "sun", "time": "20:00"},
    ],
}

CREDITS_PER_SNAPSHOT = 4        # 2 Odds API credits per league (spreads + totals), both leagues in season
MONTHLY_CREDITS = 500           # our Odds API plan
UPDATE_MINUTES = 30             # give a daily update this long to finish before a snapshot uses its predictions

TIME_PATTERN = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def sort_key(entry):
    """Daily times first, then Monday..Sunday, each by time."""
    day = -1 if entry["days"] == "daily" else DAYS.index(entry["days"])
    return (day, entry["time"])


def check(schedule, required):
    """A cleaned copy of a schedule (sorted, duplicates dropped), or ValueError with a message for the page.

    required: the default schedule for this setting; its job names are the ones that must be present.
    """
    if not isinstance(schedule, dict) or set(schedule) != set(required):
        raise ValueError("The schedule must list exactly these jobs: " + ", ".join(required) + ".")
    clean = {}
    for job in required:
        entries = schedule[job]
        if not isinstance(entries, list) or len(entries) > 20:
            raise ValueError(f"{JOBS[job]}: up to 20 times.")
        times = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"{JOBS[job]}: each time needs a day and a time.")
            days = str(entry.get("days", "")).strip().lower()
            time = str(entry.get("time", "")).strip()
            if days != "daily" and days not in DAYS:
                raise ValueError(f"{JOBS[job]}: {days!r} isn't a day (daily, mon ... sun).")
            if not TIME_PATTERN.fullmatch(time):
                raise ValueError(f"{JOBS[job]}: {time!r} isn't a time like 06:00 (24-hour clock).")
            item = {"days": days, "time": time}
            if item not in times:
                times.append(item)
        if not times and job not in OPTIONAL_JOBS:
            raise ValueError(f"{JOBS[job]} needs at least one time.")
        clean[job] = sorted(times, key=sort_key)
    return clean


def trigger(entry, timezone):
    """An APScheduler cron trigger for one {"days", "time"} entry."""
    hour, minute = entry["time"].split(":")
    day_of_week = "*" if entry["days"] == "daily" else entry["days"]
    return CronTrigger(day_of_week=day_of_week, hour=int(hour), minute=int(minute), timezone=timezone)


def describe(entries):
    """'Daily 06:00 · Sun 16:00, 20:00 · Sat 09:00, 12:00' (for logs and the change log)."""
    if not entries:
        return "none"
    groups = {}
    for entry in sorted(entries, key=sort_key):
        groups.setdefault(entry["days"], []).append(entry["time"])
    return " · ".join(f"{DAY_NAMES[day]} {', '.join(times)}" for day, times in groups.items())


def runs_on(entry, day):
    """True if this entry runs on that weekday ('mon'..'sun')."""
    return entry["days"] == "daily" or entry["days"] == day


def snapshots_per_week(odds_schedule):
    return sum(7 if e["days"] == "daily" else 1 for e in odds_schedule["odds_snapshot"])


def monthly_credits(odds_schedule):
    """Odds API credits a month in season (both leagues), at 30 days a month."""
    return round(snapshots_per_week(odds_schedule) * CREDITS_PER_SNAPSHOT * 30 / 7)


def minutes(time):
    hour, minute = time.split(":")
    return int(hour) * 60 + int(minute)


def warnings(odds_schedule, job_schedule):
    """Things the admin should know before saving.  They don't stop a save."""
    found = []
    snapshots = odds_schedule["odds_snapshot"]

    # NFL "Early" pick = the first snapshot from Monday 6:00 AM to Tuesday 6:00 AM (the T-OPEN bet time)
    monday = [e for e in snapshots if runs_on(e, "mon") and minutes(e["time"]) >= 6 * 60]
    tuesday_early = [e for e in snapshots if runs_on(e, "tue") and minutes(e["time"]) < 6 * 60]
    if not monday and not tuesday_early:
        found.append("No snapshot between Monday 6:00 AM and Tuesday 6:00 AM: NFL games would get no Early pick "
                     "(the NFL bet time).")

    # College "Early" pick = the first 4+-book snapshot 8+ h after both teams' previous kickoff: Sunday afternoon
    if not [e for e in snapshots if runs_on(e, "sun") and minutes(e["time"]) >= 12 * 60]:
        found.append("No Sunday afternoon or evening snapshot: college Early picks would move to Monday morning "
                     "(the openers are usually first saved Sunday at 4 PM).")

    # A snapshot soon after (or before) a morning update records picks from the previous day's predictions
    for job in ("daily_update", "nfl_daily_update"):
        for update in job_schedule.get(job, []):
            for snap in snapshots:
                same_day = [d for d in DAYS if runs_on(update, d) and runs_on(snap, d)]
                if same_day and minutes(update["time"]) - 180 <= minutes(snap["time"]) < minutes(update["time"]) + UPDATE_MINUTES:
                    found.append(f"The {DAY_NAMES[snap['days']]} {snap['time']} snapshot runs before the "
                                 f"{update['time']} {JOBS[job].split(':')[0]} has had {UPDATE_MINUTES} minutes to "
                                 f"finish: its picks may use the previous day's predictions.")

    credits = monthly_credits(odds_schedule)
    if credits > MONTHLY_CREDITS * 0.9:
        found.append(f"About {credits} Odds API credits a month in season, against {MONTHLY_CREDITS} on the plan.")
    return found
