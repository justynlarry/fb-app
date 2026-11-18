"""What the worker did and how much API quota is left (job_runs, api_quota), for the admin status panel."""

import os
from contextlib import contextmanager

from cfb.db import connect


def to_int(value):
    """A header value as an int, or None if it's missing or not a number."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def record_quota(source, remaining, used_last=None):
    """Save the latest quota an API reported.  Header values arrive as strings, or None if missing."""
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO api_quota (source, remaining, used_last, checked_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (source) DO UPDATE SET
                remaining  = EXCLUDED.remaining,
                used_last  = EXCLUDED.used_last,
                checked_at = now()
            """,
            (source, to_int(remaining), to_int(used_last)),
        )


class JobRun:
    """The run being recorded.  Set .message when it's done, or call .fail(...) if part of it went wrong."""

    def __init__(self):
        self.ok = True
        self.message = None

    def fail(self, message):
        self.ok = False
        self.message = message if self.message is None else f"{self.message}; {message}"


@contextmanager
def job_run(job):
    """Record one run of a scheduled job: a job_runs row when it starts, filled in when it ends."""
    with connect() as conn:
        run_id = conn.execute("INSERT INTO job_runs (job) VALUES (%s) RETURNING id", (job,)).fetchone()[0]
    run = JobRun()
    try:
        yield run
    except Exception as err:
        run.fail(repr(err))
        raise
    finally:
        with connect() as conn:
            conn.execute(
                "UPDATE job_runs SET finished_at = now(), ok = %s, message = %s WHERE id = %s",
                (run.ok, run.message[:500] if run.message else None, run_id),
            )


def ran_ok_today(job):
    """True if this job finished OK today (local time).  It's read from job_runs, so a worker
    restart doesn't forget it, unlike a variable in memory."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM job_runs
                WHERE job = %s
                  AND ok
                  AND started_at >= date_trunc('day', now(), %s)
            )
            """,
            (job, os.environ.get("TZ", "America/Denver")),
        ).fetchone()
    return row[0]
