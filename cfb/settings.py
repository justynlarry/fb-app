"""Settings an admin can change on the admin page, stored in the settings table.

Every setting has a default.  A key with no row in the table uses its default,
so an empty table means the app behaves exactly as the code says.
Every change is also written to settings_log: who, when, old -> new, and why.
"""

import copy

from psycopg.types.json import Jsonb

from cfb import schedule
from cfb.db import connect

DEFAULTS = {
    # Pick rules (cfb/picks.py). Changing one changes which picks are recorded from then on.
    "play_gap": 3.0,        # points off the market before a side is a Play
    "total_gap": 3.0,       # same for totals (info only)
    "move_min": 0.5,        # a line "moved" if it changed by at least this much since the open
    # Books the user can actually bet at (bet form prefill); every other book is a reference line
    "bettable_books": ["MyBookie", "DraftKings", "FanDuel", "BetMGM", "Caesars", "Fanatics"],
    # Worker schedule (cfb/schedule.py has the format).  The worker re-reads these every 5 minutes.
    "odds_schedule": schedule.DEFAULT_ODDS_SCHEDULE,    # odds snapshots: decides which lines picks are recorded at
    "job_schedule": schedule.DEFAULT_JOB_SCHEDULE,      # daily updates and retries
    "poll_fast_seconds": 30,        # ESPN live-score poll while games are on
    "poll_slow_seconds": 600,       # ... and otherwise
}

# Settings that change what pick_log records: a change needs a reason, and the Results page lists it.
RULE_KEYS = {"play_gap", "total_gap", "move_min", "odds_schedule"}


def get(key):
    """The current value of one setting (its default if nobody has changed it)."""
    if key not in DEFAULTS:
        raise KeyError(f"unknown setting {key!r}")
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = %s", (key,)).fetchone()
    if row is None:
        return copy.deepcopy(DEFAULTS[key])     # a copy, so a caller changing it can't change the default
    return row[0]


def get_all():
    """Every setting's current value, as a dict."""
    with connect() as conn:
        saved = dict(conn.execute("SELECT key, value FROM settings").fetchall())
    return {key: saved.get(key, copy.deepcopy(default)) for key, default in DEFAULTS.items()}


def set_value(key, value, user_id, reason=None):
    """Change one setting and log the change.  Returns False if the value was already that."""
    if key not in DEFAULTS:
        raise KeyError(f"unknown setting {key!r}")

    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = %s", (key,)).fetchone()
        old = None if row is None else row[0]
        current = DEFAULTS[key] if old is None else old
        if current == value:
            return False
        # Checked only once we know it's a real change: saving a rule unchanged needs no reason
        if key in RULE_KEYS and not (reason and reason.strip()):
            raise ValueError("Changing a pick rule needs a reason.")

        conn.execute(
            """
            INSERT INTO settings (key, value, updated_by, updated_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (key) DO UPDATE SET
                value       = EXCLUDED.value,
                updated_by  = EXCLUDED.updated_by,
                updated_at  = now()
            """,
            (key, Jsonb(value), user_id),
        )
        conn.execute(
            """
            INSERT INTO settings_log (key, old_value, new_value, reason, changed_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (key, None if old is None else Jsonb(old), Jsonb(value), reason, user_id),
        )
    return True

