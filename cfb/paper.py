"""Paper models: predicted every morning beside the live model, stored in paper_predictions (030), never used for a
pick or shown as our line (docs/plan-2027.md section 4).  Their records judge the 2027 hypotheses (H-T4, H-T2b,
H-AVG, H-TOT-B1), graded at bet time from the morning row in force then.

    docker compose exec worker python -m cfb.paper 2026          # predict now (replaces today's rows)
    docker compose exec worker python -m cfb.paper 2026 --check  # only the health check
    docker compose exec worker python -m cfb.paper 2026 --nfl    # NFL (also with --check)

The worker runs it inside the college daily update (job 'paper_models'), sharing that morning's walk-forward rows,
then checks that every version wrote its rows (job 'paper_check'; a failed check shows on /admin and in /metrics).
"""

import os
import sys

import pandas as pd

from cfb import benchmark
from cfb import model
from cfb import nfl_model
from cfb import paper_features
from cfb.db import connect
from cfb.status import job_run

TZ = os.environ.get("TZ", "America/Denver")

# Points-model versions on paper (plan-2027 section 8).  The live model (model.MODEL_VERSION) is always saved first as
# the champion's raw line and isn't repeated from this list, so at the 2027 freeze MODEL_VERSION becomes "v6" and "v5"
# keeps running on paper with no change here.
# v6-ht4 and v6-ht2b need their own rows (ROW_BUILDERS); the others use the morning's rows as they are.
POINTS_VERSIONS = ["v6", "v6-ht4", "v6-ht2b", "v6-noT1", "v6-pts", "v5"]
ROW_BUILDERS = {
    "v6-ht4": paper_features.add_t4_columns,
    "v6-ht2b": paper_features.state_space_rows,
}


def points_versions():
    """The champion's raw line first (plan-2027 8.1: challengers are compared with it, overrides left out), then the
    challengers.  The champion's line is the same model as the live prediction, saved here every morning so its value
    at bet time is kept like everyone else's."""
    return [model.MODEL_VERSION] + [v for v in POINTS_VERSIONS if v != model.MODEL_VERSION and v in model.VERSION_FEATURES]


def all_versions():
    """Every college paper version that should write rows each morning."""
    return points_versions() + [benchmark.VERSION]


# NFL (plan-2027 section 8.3): the champion's raw line (nfl-v3), nfl-v2 (reported) and nfl-v3-wk (judged 2027-28).
NFL_VERSIONS = ["nfl-v3", "nfl-v2", "nfl-v3-wk"]


def nfl_versions():
    return [nfl_model.MODEL_VERSION] + [v for v in NFL_VERSIONS
                                        if v != nfl_model.MODEL_VERSION and v in nfl_model.VERSION_FEATURES]


def versions_for(league):
    return nfl_versions() if league == "nfl" else all_versions()


def save(games, version):
    """Store one morning's predictions (rows from model.pair_predictions or benchmark.upcoming_predictions)."""
    with connect() as conn:
        for g in games.itertuples():
            home_pts, away_pts = float(g.home_points), float(g.away_points)
            conn.execute(
                """
                INSERT INTO paper_predictions (game_id, model_version, run_date, home_points, away_points,
                                               spread, total, weeks_played)
                VALUES (%s, %s, (now() AT TIME ZONE %s)::date, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id, model_version, run_date) DO UPDATE SET
                    created_at   = now(),
                    home_points  = EXCLUDED.home_points,
                    away_points  = EXCLUDED.away_points,
                    spread       = EXCLUDED.spread,
                    total        = EXCLUDED.total,
                    weeks_played = EXCLUDED.weeks_played
                """,
                (int(g.game_id), version, TZ, round(home_pts, 2), round(away_pts, 2),
                 round(away_pts - home_pts, 2), round(home_pts + away_pts, 2), int(g.weeks_played)),
            )
    return len(games)


def run(season, rows=None):
    """Predict every paper version for the season's upcoming games.  Each version runs on its own, so one failure
    doesn't stop the others.  Returns ({version: games saved}, [errors])."""
    saved, errors = {}, []
    for version in points_versions():
        try:
            if rows is None:
                rows = model.build_rows(season)
            build = ROW_BUILDERS.get(version)
            version_rows = build(rows) if build else rows
            saved[version] = save(model.upcoming_predictions(version_rows, season, version), version)
        except Exception as err:
            errors.append(f"{version}: {err!r}")
    try:
        saved[benchmark.VERSION] = save(benchmark.upcoming_predictions(season), benchmark.VERSION)
    except Exception as err:
        errors.append(f"{benchmark.VERSION}: {err!r}")
    print(f"paper models: {saved}" + (f", errors: {errors}" if errors else ""))
    return saved, errors


def nfl_frame(games):
    """nfl_model.predict_games output (indexed by game_id) in the shape save() takes."""
    return pd.DataFrame({"game_id": games.index, "home_points": games["home_pred"].values,
                         "away_points": games["away_pred"].values, "weeks_played": games["weeks_played"].values})


def run_nfl(season, rows=None):
    """Predict every NFL paper version for the season's upcoming games.  Returns ({version: games saved}, [errors])."""
    saved, errors = {}, []
    for version in nfl_versions():
        try:
            if rows is None:
                rows = nfl_model.season_rows_through(season)
            saved[version] = save(nfl_frame(nfl_model.upcoming_predictions(rows, season, version)), version)
        except Exception as err:
            errors.append(f"{version}: {err!r}")
    print(f"NFL paper models: {saved}" + (f", errors: {errors}" if errors else ""))
    return saved, errors


# For each paper version: rows written today, and the live model's upcoming games for comparison.
# A paper version is short if it wrote nothing today, or fewer rows than 90% of the live model's upcoming games
# (B1 can miss a few games the points model rates, and vice versa; a real failure writes none or few).
HEALTH_SQL = """
WITH upcoming AS (
    SELECT id FROM games WHERE league = %(league)s AND season = %(season)s AND start_time > now()
),
live AS (
    SELECT count(*) AS n
    FROM predictions p JOIN upcoming u ON u.id = p.game_id
    WHERE p.model_version = %(live)s AND NOT p.is_backtest
)
SELECT v.version,
       count(pp.game_id) FILTER (WHERE pp.run_date = (now() AT TIME ZONE %(tz)s)::date) AS rows_today,
       extract(epoch FROM now() - max(pp.created_at))::int AS newest_age_seconds,
       (SELECT n FROM live) AS live_upcoming
FROM unnest(%(versions)s::text[]) AS v(version)
LEFT JOIN paper_predictions pp ON pp.model_version = v.version
GROUP BY v.version
ORDER BY v.version
"""


def health(season, league="cfb"):
    """[{version, rows_today, newest_age_seconds, live_upcoming, ok}] for every paper version of the league."""
    live = nfl_model.MODEL_VERSION if league == "nfl" else model.MODEL_VERSION
    with connect() as conn:
        rows = conn.execute(HEALTH_SQL, {"season": season, "league": league, "live": live, "tz": TZ,
                                         "versions": versions_for(league)}).fetchall()
    out = []
    for version, rows_today, age, live in rows:
        ok = rows_today > 0 and rows_today >= 0.9 * (live or 0)
        out.append({"version": version, "rows_today": rows_today, "newest_age_seconds": age,
                    "live_upcoming": live, "ok": ok, "league": league})
    return out


def check(season, league="cfb"):
    """The daily health check, recorded in job_runs as 'paper_check' ('paper_check_nfl'), not OK if any version is short."""
    with job_run("paper_check_nfl" if league == "nfl" else "paper_check") as run:
        result = health(season, league)
        short = [f"{h['version']} {h['rows_today']}/{h['live_upcoming']}" for h in result if not h["ok"]]
        if short:
            run.fail("short: " + ", ".join(short))
        else:
            run.message = ", ".join(f"{h['version']} {h['rows_today']}" for h in result)
        print(f"paper check ({league}):", run.message)
    return result


def metrics_text(season, in_season):
    """Prometheus text format for /metrics: paper-model rows and every worker job's last run.
    in_season = {"cfb": bool, "nfl": bool} (games within 3 days back / 10 ahead, so paper rows are expected)."""
    lines = ["# HELP sports_in_season 1 if the league has games within 3 days back / 10 ahead (paper models expected).",
             "# TYPE sports_in_season gauge"]
    lines += [f'sports_in_season{{league="{lg}"}} {1 if on else 0}' for lg, on in in_season.items()]
    result = health(season, "cfb") + health(season, "nfl")
    label = lambda h: f'league="{h["league"]}",version="{h["version"]}"'
    lines += ["# HELP sports_paper_rows_today Paper-model predictions written today (local day), per version.",
              "# TYPE sports_paper_rows_today gauge"]
    lines += [f'sports_paper_rows_today{{{label(h)}}} {h["rows_today"]}' for h in result]
    lines += ["# HELP sports_paper_ok 1 if the version wrote at least 90% of the live model's upcoming games today.",
              "# TYPE sports_paper_ok gauge"]
    lines += [f'sports_paper_ok{{{label(h)}}} {1 if h["ok"] else 0}' for h in result]
    lines += ["# HELP sports_paper_newest_age_seconds Seconds since the version's newest row (-1 = never written).",
              "# TYPE sports_paper_newest_age_seconds gauge"]
    lines += [f'sports_paper_newest_age_seconds{{{label(h)}}} '
              f'{h["newest_age_seconds"] if h["newest_age_seconds"] is not None else -1}' for h in result]
    lines += ["# HELP sports_live_upcoming_predictions The live model's predictions for the league's upcoming games.",
              "# TYPE sports_live_upcoming_predictions gauge"]
    for lg in ("cfb", "nfl"):
        first = next((h for h in result if h["league"] == lg), None)
        lines.append(f'sports_live_upcoming_predictions{{league="{lg}"}} {first["live_upcoming"] if first else 0}')

    with connect() as conn:
        jobs = conn.execute(
            """
            SELECT DISTINCT ON (job) job, ok, extract(epoch FROM now() - started_at)::int,
                   extract(epoch FROM now() - max(started_at) FILTER (WHERE ok) OVER (PARTITION BY job))::int
            FROM job_runs
            WHERE finished_at IS NOT NULL
            ORDER BY job, started_at DESC
            """
        ).fetchall()
    lines += ["# HELP sports_job_last_ok 1 if the job's latest finished run was OK.", "# TYPE sports_job_last_ok gauge"]
    lines += [f'sports_job_last_ok{{job="{job}"}} {1 if ok else 0}' for job, ok, _, _ in jobs]
    lines += ["# HELP sports_job_last_run_age_seconds Seconds since the job's latest finished run started.",
              "# TYPE sports_job_last_run_age_seconds gauge"]
    lines += [f'sports_job_last_run_age_seconds{{job="{job}"}} {age}' for job, _, age, _ in jobs]
    lines += ["# HELP sports_job_last_ok_age_seconds Seconds since the job's latest OK run started (-1 = never).",
              "# TYPE sports_job_last_ok_age_seconds gauge"]
    lines += [f'sports_job_last_ok_age_seconds{{job="{job}"}} {ok_age if ok_age is not None else -1}'
              for job, _, _, ok_age in jobs]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    season = int(sys.argv[1])
    league = "nfl" if "--nfl" in sys.argv else "cfb"
    if "--check" not in sys.argv:
        with job_run("paper_models_nfl" if league == "nfl" else "paper_models") as job:
            saved, errors = run_nfl(season) if league == "nfl" else run(season)
            job.message = ", ".join(f"{v} {n}" for v, n in saved.items())
            for e in errors:
                job.fail(e)
    check(season, league)
