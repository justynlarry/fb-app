# CFB Betting Predictor — Claude instructions

Self-hosted app that predicts college football spreads and totals, compares them with
market lines, and shows live Division I scores. Personal use only; reached over the
home LAN or Tailscale. The original design brief is `cfb-model-prompt.md`. This file
overrides it where they differ.

## Who types what (most important rule)

- **The user keys all Python (`.py`) and SQL (`.sql`, and SQL inside Python strings).**
  Claude must not create or edit those files. Instead, Claude:
  - explains what the next file/function needs to do and why,
  - gives the code in chat in small, typeable chunks (one function or one table at a time),
  - reviews what the user typed (read the file, point out bugs, suggest fixes in chat),
  - runs it/tests it when asked and explains errors.
  The goal is that the user writes and understands the backend. Prefer clear, plain code
  over clever code in anything Claude suggests for the user to type.
- **Claude keys all HTML, JS and CSS**, including Jinja templates (`app/templates/*.html`)
  and static assets (`app/static/`).
- **The user runs all Linux commands that install software or change the system**
  (`apt`, `sudo`, Docker installs, `docker compose up/build`, git setup, service
  changes). Claude gives the commands in chat with a one-line explanation of each, and
  the user runs them. Claude may run read-only checks itself (`cat`, `ls`, `docker ps`,
  `--version`, viewing logs) to diagnose problems.
- Other files (`docker-compose.yml`, `Dockerfile`, `.env.example`, shell/cron scripts,
  `requirements.txt`, docs): Claude writes these unless the user says otherwise.

## Secrets

- `.env` holds `CFBD_API=...`. Never print, log, echo, commit or bake it into an image.
  Read it only via Compose `env_file`. Keep `.env` in `.gitignore`; commit `.env.example`.

## Stack

```
docker-compose.yml
├── db      postgres:17, named volume, NO published port
├── app     FastAPI + Jinja2 + HTMX (web UI, reads only from Postgres)
└── worker  Python ingestion, live-score poller, model, predictions (APScheduler)
```
- The web app never calls external APIs directly. The worker fetches and writes to
  Postgres; pages read from Postgres. One poller serves every browser.
- Networking: Docker bypasses ufw for published ports. Publish the web port only on a
  specific LAN IP (decided below), never 0.0.0.0. Never publish Postgres.
  Tailscale runs on the host, not in a container.
- Nightly `pg_dump` to a mounted `backups/` directory (overrides and bet logs can't be
  re-fetched).
- PHP isn't needed. Page speed here depends on querying cached data in Postgres and
  sending small HTML fragments, not on the backend language.

## Data sources

### CollegeFootballData (CFBD), free tier: 1,000 calls/month
- Base `https://api.collegefootballdata.com`, header `Authorization: Bearer $CFBD_API`.
- Check `/info` for remaining calls before any bulk job. Report how many calls each step used.
- Pull whole seasons per call (omit `team`). Cache everything; never re-fetch stored data.
  After the backfill, refresh only the current week (~5–10 calls/week).
- Always pass `excludeGarbageTime=true` where supported.
- OpenAPI spec (free, no quota): `https://api.collegefootballdata.com/api-docs.json`.
- Not on the free tier, don't use: `/scoreboard`, `/live/plays`, adjusted metrics/WEPA,
  weather, GraphQL.

### Live scores
CFBD can't drive the live page: `/scoreboard` and `/live/plays` are paid, `/scoreboard`
has no timeout counts, and polling every minute on a Saturday would use the monthly
quota in a day. The live poller uses a separate source (ESPN, see Decisions).
It polls only while games are in progress (from the schedule already in
Postgres), about every 30–60 s, and idles otherwise.

## Pages

Sort order on both game pages: kickoff time, then visiting team alphabetically.
Store times in UTC; display in the user's local time zone (`TZ` in `.env`).

1. **Scores (live, auto-updating).** One row per game, left to right:
   visiting team | home team | (not started: day, date, kickoff time) |
   score (visitor – home) | quarter + clock | possession | timeouts (visitor / home).
   Auto-refresh with HTMX polling (`hx-trigger="every 30s"`) of a fragment endpoint.
   Final games show "Final"; mark the team with the ball.
2. **Predictions.** visiting team | home team | day, date, kickoff |
   predicted line | predicted over/under. Also show the market spread/total and the
   difference, highlighting disagreements of 3+ and 5+ points.
3. Later: team ratings page, backtest report, overrides entry.

## Model

- Per-play efficiency only (EPA/play split pass/rush, success rate, explosiveness,
  points per opportunity), garbage time excluded.
- Opponent adjustment by ridge regression on game-level data:
  `metric ~ team_offense + opponent_defense + home_field`. Group or down-weight FCS opponents.
- Predict **each team's points** (adjusted offense vs. opponent adjusted defense, plus pace),
  so one model gives both outputs: line = home − away, total = home + away.
- Preseason priors (last season's ratings, returning production, talent, recruiting,
  coaching changes, portal), faded out by weeks 5–6.
- Manual overrides table (e.g. "QB out, −N points, team X, game Y") applied before predictions.

## Backtest (how the model is judged)

- Walk-forward only: a week-W prediction uses data from before week W plus priors. No lookahead.
- Store model spread/total, opening and closing lines, final score per game.
- Report: model MAE vs. closing-line MAE (spread and total); cover rate at 3+ and 5+ point
  disagreements; closing line value (did the line move toward the model between open and close).
- Report results honestly; matching the market is the realistic first goal.

## Build order

1. Docker (official apt repo, user in `docker` group), confirm Tailscale, git init,
   scaffold compose / `.env.example` / schema. **Check in with the user.**
2. Ingestion worker + backfill (ask how many seasons; check `/info` first). **Check in.**
3. Live-score poller + scores page (useful right away, independent of the model).
4. Ratings + points model → predictions page.
5. Walk-forward backtest + report.
6. Priors, overrides, scheduling polish.

## Decisions (2026-11-10)

- Live-score source: ESPN's public, undocumented scoreboard JSON (free, has possession
  and timeouts). It can change without notice, so parse it defensively and keep the
  parsing in one module. Map ESPN team IDs to CFBD team IDs in a lookup table.
- Scope: FBS games only (including FBS vs. FCS matchups).
- Web port: bind to the VM's LAN IP `192.168.0.81` (`"192.168.0.81:8000:8000"`), never
  `0.0.0.0`. The IP should be reserved in the router's DHCP or set as a static address.
- Display time zone: Mountain (`TZ=America/Denver`).

- NFL may be added later. Design every table, query and page to be league-aware:
  `league` column (`'cfb'`/`'nfl'`) on teams and games; our own identity `id` primary keys,
  with source ids (`cfbd_id`, `espn_id`) as columns unique per league (ESPN reuses ids
  across leagues). Likely NFL sources: ESPN (live), nflverse (stats/EPA). Don't hard-code
  cfb-only assumptions (e.g. FBS/FCS logic) outside cfb-specific modules.

## Still open

- Number of past seasons to backfill (ask at step 2, after checking `/info`).
