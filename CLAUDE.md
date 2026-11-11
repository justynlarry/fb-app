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
  - when the user asks Claude to "check and correct" a file, fixes the errors in place
    (bugs, typos, indentation, style), without adding new features, and explains each fix
    so the user learns from it,
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
   predicted line | predicted over/under, each with an uncertainty band from the backtest
   (e.g. "−6.5 ±11"; wider early season / vs FCS). Market spread/total and the difference
   are **hidden by default** (one-click reveal, to avoid anchoring); when shown, highlight
   disagreements of 3+ and 5+ points.
3. Later: team ratings page, backtest report, overrides entry.

## Model

- **Goal: our own independent line, not a copy of the market.** Market lines (CFBD `lines`,
  ESPN odds) are NEVER model inputs or features, and never blended into predictions. They are
  used only to evaluate the model (backtest, CLV) and to display side by side. Confidence comes
  from backtest evidence, especially ATS record when we disagree by 3+/5+ and closing line value.
  Treat large disagreements as "investigate" flags (injuries, QB changes) handled via overrides.
- Per-play efficiency only (EPA/play split pass/rush, success rate, explosiveness,
  points per opportunity), garbage time excluded.
- Opponent adjustment by ridge regression on game-level data:
  `metric ~ team_offense + opponent_defense + home_field`. Group or down-weight FCS opponents.
- Predict **each team's points** (adjusted offense vs. opponent adjusted defense, plus pace),
  so one model gives both outputs: line = home − away, total = home + away.
- Preseason priors (last season's ratings, returning production, talent, recruiting,
  coaching changes, portal), faded out by weeks 5–6.
- Manual overrides table (e.g. "QB out, −N points, team X, game Y") applied before predictions.
- **Coaching & injuries (planned, 2026-11-11):**
  - Head coaches: automatic. `/coaches` (already cached) for season-to-season changes;
    `/coaches/tenures` for interim/mid-season changes. Use as a model-v2 input.
  - Coordinators: no source in CFBD or ESPN. User enters OC/DC in a manual table each
    offseason (step 6).
  - Injuries: no free feed (CFBD has none; ESPN college game summaries have none, checked).
    Instead: detect QB changes automatically from who actually threw passes each game — usable in
    the backtest to measure what a backup QB costs. **Correction (2026-11-11):** `/passing/players/games`
    is NOT one call per season; it requires `team`, `week` or `passerId` besides `year` (400 otherwise).
    `/games/players` needs `week`, `team` or `conference`. Cheapest full-season pull is
    `/games/players?year=&conference=&category=passing` (~11-12 calls/season). Always read the
    parameter *descriptions* in the spec, not just the `required` flag.
  - **`conference` must be the ABBREVIATION** (`B1G`, `B12`, `AAC`, `CUSA`, `MAC`, `MWC`, `PAC`,
    `SBC`, `Ind`, `ACC`, `SEC`) from `/conferences` (cached). A full name like "Big Ten" returns an
    empty list, not an error, and the empty result still costs a call and gets cached. Lesson
    (2026-11-11, ~90 calls wasted): before any multi-call pull, test 1 call for a case that differs
    from the one that worked (e.g. a conference whose name ≠ abbreviation), and stop on 0-row results.
  - **Result (2026-11-11): QB-change detection from past box scores does NOT improve the model.**
    Tested two variants on v2 walk-forward rows 2018–2025 (excl. 2020): (a) "last starter ≠ season
    QB1" + shrunk YPA gap; (b) "fresh change" (first start) × team pass EPA. Both left spread miss
    at 12.87 overall and ~12.66–12.70 in the 1,481 QB-change games (market 12.23). Reasons: market
    already knows last week's starter; ratings absorb a backup within one game; the flag is noisy
    (13% of team-games, incl. permanent benchings). Don't retry without new information.
    What it IS good for: **suggested override values** — a switch to a non-QB1 costs ~1 pt on
    average, plus ~3.7 pts per +1.0 team pass EPA lost (elite passer ≈ 2–4 pts total). QB news
    (starter out *this* week) belongs in the overrides page, not the model.
- **Rate limit:** every CFBD response carries `x-calllimit-remaining`; `cfbd.get` prints it. Value players
    with `/ppa/players/season` and `/player/usage` to *suggest* override points when the user
    marks a player out; the user accepts or edits.

- **Weather (to investigate, user request 2026-11-11):** weather affects games, especially
  totals (wind, rain/snow, cold). CFBD's weather is paid, so instead:
  - Forecast: ESPN scoreboard events include `weather` (temperature, conditionId) and
    `venue.indoor` for every game, free, already fetched by the poller. No wind speed, though.
  - History + wind: we already have every stadium's lat/long and `dome` flag in cached `/teams`
    (`location`). A free service such as Open-Meteo (no key, not CFBD) can give hourly wind, precip
    and temperature at kickoff for past games, so weather can be **backtested**. Neutral-site games
    need venue locations (CFBD `/venues`, 1 call).
  - Measure first whether weather beyond what the market prices in helps (mostly totals) before
    adding it to the model.

## Parking lot (not started; pick up when the user asks)

- **Remote access (user request 2026-11-11):** reach the app from anywhere, not just LAN/Tailscale.
  - Domain on Cloudflare + **Cloudflare Tunnel**: a `cloudflared` container in compose connects
    *outbound* to Cloudflare and forwards to `http://app:8000` on the Docker network. No inbound
    ports opened on the router, the LAN-IP port binding can stay, Postgres stays unpublished.
  - **Login / users:** recommended first layer is **Cloudflare Access** (Zero Trust, free tier,
    email one-time code or Google login, allow-list of emails) in front of the whole site, so no
    request reaches the app unauthenticated. Add app-level accounts only if per-user features are
    wanted (e.g. personal bet log, per-user overrides): `users` table, argon2/bcrypt password
    hashes, secure session cookies, login page; never roll our own crypto.
  - Tunnel token goes in `.env` (never committed). Ask the user before creating anything on Cloudflare.
- **Model v3:** (QB-change detection tested and rejected, see above), head-coach tenures for
  mid-season changes, and fix `weeks_played`: it counts a week as played if any FBS/FCS game in it kicked off
  before the cutoff (2026 week 1 starts at 1 because an FCS game kicked off first). Count weeks
  strictly before the current week instead, then re-run the backtest.
- **Weather** (see Model section) and **overrides page** (step 6), coordinator table.
- **Backtest page:** version selector / side-by-side v1 vs v2.

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

- Backfill: seasons 2016–2025 plus current 2026 (~14 calls/season, ~155 total). Flag 2020
  (COVID) so the backtest can exclude it. Test each endpoint on one season first.
- Scheduling: the worker runs `daily_update()` at 5 AM Mountain (refresh current season's
  `/games`, `/stats/game/advanced`, `/lines` = 3 calls, then `predict_upcoming`), skipped when no
  games are within 3 days back / 10 days ahead. **Each August, backfill the new season once by
  hand** (`python -m cfb.backfill <year>` then `python -m cfb.load <year>`, ~11 calls).
- Every CFBD response is stored raw in `api_responses` before parsing; check it before any
  call. `/info` itself costs a call.
- Schema changes: new numbered files in `db/init/` (runs only on a fresh volume), applied by
  hand to the live DB with `docker compose exec -T db psql -U fb-user -d football < file`.
  Never suggest `down -v` once real data is loaded. DB user is `fb-user`, DB is `football`.
