# Sports Predictor (college football + NFL) — Claude instructions

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
   This week = 24 h after the last game, 12 h for the NFL (2026-11-17). Week picker (2026-11-17): `/scores?league=&season=&week=[&season_type=postseason]`, every week since 2016; past
   weeks don't poll and fall back to `games` final scores (live_scores only since 2026-11-15). Claude typed the
   `main.py` part at the user's request (rule unchanged).
2. **Predictions.** visiting team | home team | day, date, kickoff |
   predicted line | predicted over/under, each with an uncertainty band from the backtest
   (e.g. "−6.5 ±11"; wider early season / vs FCS). Market spread/total and the difference
   were hidden by default to avoid anchoring; **since 2026-11-12 the user wants them shown by default**
   ("Hide market & picks" button, remembered per browser). Pick column: Play / Caution / Pass with backtest
   win rate and game count. The live tier rule lives in `cfb/picks.py make_pick()` (used by the page AND the
   worker's `record_picks`, so the pick shown is the pick recorded); `PICK_RATES_SQL` repeats it for the
   backtest rates: change both together. Market "now" = median of The Odds API books (`market_now` view).
   Week picker (2026-11-16): `/predictions?season=&week=[&season_type=postseason]`, lists weeks with live
   (non-backtest) predictions, i.e. from 2026 week 11. "This week" on predictions/overrides = week of the next game not
   over for 12+ h (scores page keeps 24 h). Past weeks show the last pre-game line and recorded pick, graded.
3. Later: team ratings page, backtest report, overrides entry.
4. **League toggles (2026-11-17):** Results, Backtest and Overrides take `?league=nfl` (shared `league_tabs` macro).
   NFL Results/Backtest hide the opener-based columns (no NFL opener) and the Caution tier; NFL Overrides hides the
   college-only "Starting QB out" helper. `NFL_PREDICTIONS_SQL` now applies overrides like the college page, so the
   NFL page and the NFL pick logger (`picks.UPCOMING_SQL`) show the same line. Phones/tablets (≤1024 px) show NFL
   nicknames only (`team_name` macro, `.team-city`). Claude typed the `main.py` part at the user's request (rule
   unchanged).

## Model

- **Goal: our own independent line, not a copy of the market.** Market lines (CFBD `lines`,
  ESPN odds) are NEVER model inputs or features, and never blended into predictions. They are
  used only to evaluate the model (backtest, CLV) and to display side by side. Confidence comes
  from backtest evidence, especially ATS record when we disagree by 3+/5+ and closing line value.
  Treat large disagreements as "investigate" flags (injuries, QB changes) handled via overrides.
- Per-play efficiency only (EPA/play split pass/rush, success rate, explosiveness), plus plays (pace) and
  points, garbage time excluded (`cfb/ratings.py` METRICS). Points per opportunity is NOT a v5 metric
  (corrected 2026-11-13; drive-based ppo was tested in Round 4).
- Opponent adjustment by ridge regression on game-level data:
  `metric ~ team_offense + opponent_defense + home_field`. Group or down-weight FCS opponents.
- Predict **each team's points** (adjusted offense vs. opponent adjusted defense, plus pace),
  so one model gives both outputs: line = home − away, total = home + away.
- Preseason information enters two ways: last season's games stay in the ratings regression at weight
  0.25 × fade (fade 1 → 0 over PRIOR_WEEKS = 6), and talent / returning production / new coach are
  points-model features faded linearly over PRIOR_INPUT_WEEKS = 16. Ridge (ALPHA=1) shrinks teams toward
  league average. Home field = one points-model coefficient, refit each season on all earlier seasons.
  No explicit special teams (only through the opponent-adjusted points rating).
- Manual overrides table (e.g. "QB out, −N points, team X, game Y") applied before predictions.
- **Coaching & injuries (planned, 2026-11-11):**
  - Head coaches: automatic. `/coaches` (already cached) for season-to-season changes;
    `/coaches/tenures` for interim/mid-season changes. Use as a model-v2 input.
  - Coordinators: no source in CFBD or ESPN (CFBD is head coaches only, checked 2026-11-18). **Table `coordinators`
    (026, Claude typed it at the user's request, rule unchanged; applied and loaded 2026-11-18):** one row per team,
    season, unit (`offense`/`defense`): `names` (everyone listed, incl. in-season replacements; empty = head coach calls
    it), `is_new` (no name in common with last season; NULL = no previous season), `raw_field`, `source`
    ('wikipedia' | 'manual'), `source_title`. History 2015–2025 from Wikipedia infoboxes: 2,874 rows, new OC 533 / DC 482
    (= the T-OCDC flags). Each August add the new season (Wikipedia pull + hand check); mid-season changes by hand
    ('manual', from FootballScoop / On3 / 247 / CBS trackers; Claude doesn't scrape those).
  - **Head-coach detector (built 2026-11-18; user typed 027, the model line and coach_watch.py part C1; Claude typed C2 and
    part D at the user's request, rule unchanged):** `027_coach_watch.sql` (`coach_changes.status` pending/confirmed/
    rejected, default confirmed; `detected_at`; table `head_coach_watch`). The model reads `status = 'confirmed'` only.
    `cfb/coach_watch.py`: ESPN core API `seasons/{s}/teams/{espn_id}/coaches` (2 free requests per FBS team); first
    sighting = baseline; a new coach id → pending row (`source 'espn'`, changed_at = last game before seen + 1 day),
    skipped if the team already has a change that season. Worker job `coach_watch` daily 04:30 (schedule setting;
    `schedule.check` fills jobs missing from a saved schedule with their defaults). Dry run 2026-11-18: 138 teams; ESPN
    showed interims for the 5 firings a week+ old, but still Butch Jones (Arkansas State) and no coach (UTEP) 2 days
    after those firings: ESPN lags a few days. **Part E done (user-typed; Claude fixed a `::text` cast it had given
    wrong and the f-string that would have written the whole user dict into the note):** `PENDING_COACH_SQL`,
    `CoachChangeIn`, `POST /api/admin/coach-changes/{id}` (confirm with optional corrected `changed_at`, or reject;
    pending only, 404 otherwise; note gets "confirmed/rejected by <user>"); "Coach changes to confirm" panel on /admin.
    Rejected rows stay, so the same team-season is never flagged twice.
  - **Coordinator detector (built 2026-11-18, Claude typed all of it at the user's request, rule unchanged):** no
    better source than Wikipedia (ESPN core API and roster list head coaches only; CFBD none; school staff pages are
    138 different sites; Sports-Reference and media trackers forbid scraping). `028_coordinator_changes.sql` (team,
    season, unit, old_names, new_names, source_title, status pending/confirmed/rejected, note). `cfb/coordinators.py`
    (the T-OCDC parser moved into the app: reads all 2,874 stored rows identically; title map; 50 pages per request):
    no row for the season → **adds it with `is_new`** (this is the automatic August load); a name not in the stored
    row → pending change (a dropped name is not a change; an identical pending change isn't repeated). Worker job
    `coordinator_watch` Mondays 04:45. Confirm on /admin adds the new names to the season row (is_new unchanged).
  - Injuries: no API (CFBD has none; ESPN college game summaries have none, checked). ESPN team endpoints
    also checked 2026-11-14, all 138 FBS teams: `site/.../teams/{id}` has no injury field (also with
    `?enable=injuries`), `.../teams/{id}/injuries` returns `{}`, roster `injuries` lists are all empty, and core
    `sports.core.api.espn.com/.../teams/{id}/injuries` holds only 5 stale 2020–22 notes. ESPN keeps no college data.
    Paid APIs (docs only, 2026-11-14): SportsDataIO CFB has `/v3/cfb/scores/json/InjuredPlayers` (tracked since
    2024), but its free trial covers only UEFA Champions League, so CFB needs a paid plan. API-Sports American
    Football (`APISPORTS_KEY` in `.env`, free 100 req/day, seasons 2022–24 only) tested 2026-11-14: `/injuries?team=`
    returned 0 for Alabama, Ohio State and Toledo in-season but 10 for an NFL team. Its `/leagues` table lists
    NCAA injuries only for 2026, and returns nothing. No CFB injury feed; possibly useful if NFL is added. **Correction
    (2026-11-12):** all Power 4 conferences publish availability reports for conference games (SEC since
    2024, ACC and Big 12 since 2025, Big Ten 4/week since 2026, last one 2 h before kickoff), as web pages in
    four formats, name + status only. Not covered: non-conference and G5 games. Use: flag key absences on the
    overrides page, not a model feature (the market reacts at once).
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
  - **Result (2026-11-11, research in scratch, not in the app):** Open-Meteo hourly archive per
    open-air venue-season (1,295 requests, CFBD `/venues` for coordinates/dome), kickoff hour +3h,
    5,843 games 2017–2025 excl. 2020. Market prices normal weather well (avg vs close ≈ +0.4, under
    ≈50% for wind <10 mph). Possible edges only in extremes, small samples: gusts 30+ mph n=205,
    −1.7 vs close, under 57.8%; rain 0.1–0.3 in n=183, under 55.5%; wind 20+ n=18. Our model
    ignores weather and over-predicts totals in bad weather (−2.3 at 15–20 mph, −4.5 at 30+ gusts,
    −3 in heavy rain) but walk-forward weather terms only moved model total miss 13.006 → 12.996.
    Under-bets when weather said close was 1+ too high: 56.8% (n=155) — uses OBSERVED weather
    (hindsight) and best of several cuts, so optimistic. Decision: don't add to the model; show a
    forecast weather flag (gusts 25+ / rain) on the predictions page and log daily forecasts for a
    future honest out-of-sample test.

- **Model v4 (2026-11-12):** ratings weight this season's games by recency (half-life 4 weeks; last
  season's games treated as 8+ weeks old) and ridge ALPHA=1. Backtest 2018–25: spread miss 12.87 (v3 12.88),
  ATS 3+ at open 52.3%, best open number 53.4%, CLV(3+) 61%. Chosen over half-life 3 (slightly better ATS,
  worse accuracy, edge of the tested range) after 7 variants; expect real results a bit lower.
  Rejected: gradient boosting (worse in every variant).
- **2026 season to date (v4 trained on ≤2025, 685 games to Nov 9):** ATS 3+ at open 50.0%, at close 44.4%,
  CLV 64.8%. The market moves toward us; a gap still there at kickoff loses. Hence the opening line +
  movement on the predictions page. Gaps of 2–3 pts went 49.0% (backtest), overs at 3+ 49.0%.
- **Drift seen 2024–26:** home teams beat our spread by ~1 pt/season; we under-predict totals ~2 pts
  (2023, 2026). Tested and rejected (2026-11-12): (a) weighting recent seasons in the points model
  (half-life 1/2/4 seasons): accuracy slightly better, ATS at open and CLV worse; (b) current-season bias
  correction of spread/total (residual mean so far, shrunk K=100/300, ± half of last season's): no ATS
  gain, CLV down, total miss worse (the in-season bias is too noisy). Don't retry without new information.
- **Round 3 (2026-11-12, scratch, 0 calls), all rejected:** on v4 rows, walk-forward 2018–2026:
  (a) last season's final SP+ off/def as faded priors: spread 12.860→12.841, total 13.111→13.044 (best total
  gain yet) but ATS 3+ at open 51.9→50.0, CLV 61.3→60.0, worse in 4 of 6 seasons; O/U at open unchanged
  (51.8%). It makes us agree with the market more (fewer 3+ gaps), not beat it. (b) Transfer portal
  (stars in − out before Aug 20, incoming 3★+ QB; data 2021+ only): coefficients ~0.1 pt/SD, open3 +0.5,
  CLV flat/down in 3 of 5 seasons = noise. (c) Schedule spots (bye, short week ≤5 days, travel km, time
  zones, 2nd straight road game): short week ≈ −3.9 pts for that team, but ATS/CLV worse (priced in).
  None helped weeks 0–3. Lesson: information the market already uses (SP+, schedule) raises accuracy and
  lowers edge; our edge comes from the recency-weighted EPA ratings.
- **Round 4 (2026-11-12), rejected: drive metrics.** `/drives?year=` is 1 call/season (all games, regular
  season only by default; FBS-involved games only before 2022); cached for 2016–2026 (11 calls). Per team-game,
  garbage time removed: points per scoring opportunity (drive ending at/inside the 40, TD=7 FG=3), opportunity
  rate, average starting yards-to-goal; each opponent-adjusted like the other ratings. Best variant (+field
  position): spread 12.860→12.847, weeks 0–3 13.12→13.10, CLV 61.3→61.8 (up in 5 of 6 seasons) but ATS 3+ at
  open flat (51.9) and down in 4 of 6 seasons; finishing drives alone: open3 +0.3, total miss worse. All within
  noise. EPA per play already contains field position and red-zone results. After 4 rounds, v4 is near what
  this data can do; the next evidence is v4's real pre-game record.
- **Round 5 (2026-11-12), promising: mid-season head-coach changes.** From cached `/coaches` (0 calls): a team
  with 2 coaches in a season = mid-season change; the outgoing coach is the one who also coached the year before,
  and his game count says after which game it happened (110 usable changes 2016–25, 14 skipped). After a change,
  teams did worse than v4's line by 3.6 pts/game (310 games; regular season −3.1, bowls −6.4, n=46) and worse
  than the open by 1.7 (cover the open 44.3%); our ratings keep the old coach's form. Walk-forward correction
  (x = mean miss in earlier seasons, shrunk with 100 games of prior, ≈ −2.4 to −2.6 pts, applied to the changed
  team in games after the change), 2021–25: ATS 3+ at open 52.29 → 52.91%, spread miss 12.782 → 12.766, CLV
  flat; **ATS up in all 5 seasons** (+0.2 to +0.9), miss better in 4 of 5. Affected games only: 3+ picks at open
  51.5% → 60.6% (n=143). Regular season only: 52.61%; "3rd+ game after" only: 52.42% (weaker).
  Live data problem: CFBD's 2026 `/coaches` (cached Nov 10) lists one coach per team with 0 games; it is filled in
  after the season, so live changes must be entered by hand (team, date). `/coaches/tenures` needs `team` or
  `coachId` (one call per team), so it isn't a cheap feed either. Research script: scratch `coach_change.py`.
  **Decision (user, 2026-11-12): regular season only** (conference title games count as regular). Bowls are
  excluded (opt-outs, coaches leaving for other jobs); playoffs too: a playoff team that loses its coach was
  poached, not fired, and the only case (2025, 3 CFP games) beat our line by +26/+10/+1. Regular-only walk-forward:
  52.29 → 52.61%, ATS up or flat in every season 2022–25 (+0.2, 0, +0.9, +0.5), miss better in 3 of 4.
  **Correction (2026-11-12):** the research counted coaches listed with 0 games (left before the season) as
  mid-season changes, flagging whole seasons (58 of 292 regular rows). Without them (as the loader does): regular
  season −3.2 vs our line (n=207; 1st–2nd game after −1.2 and they cover the open 55%; 3rd+ game −4.6, cover 41%),
  walk-forward 52.29 → 52.56%, by season +0.1/0/+0.6/+0.6, never worse. `/coaches` 2015 fetched (1 call) so
  2016 changes can be found; the loader saves 69 changes 2016–25.
- **Model v5 (adopted 2026-11-12 by the user, as an accuracy fix, not a proven betting edge):
  mid-season coach change as a points-model feature.**
  - `coach_changes` table (016): team, season, `changed_at` (games kicking off after it have the new coach),
    outgoing/incoming, `source` ('cfbd' derived from cached `/coaches`, or 'manual' for the live season).
  - Loader fills 2016–25 from cached `/coaches` (0 calls); 2026 firings are entered by hand.
  - Feature in `side_row`: `coach_change` (this team) and `opp_coach_change`, 1 only in regular-season games after
    the change. The regression learns the size walk-forward (no hand-picked constant, no lookahead) and moves
    both spread and total. Judge it with the usual backtest; accept only if ATS at open/CLV hold up by season.
  - **Backtest:** spread 12.870 → 12.859, ATS 3+ open 52.3 → 52.4%, CLV 61.2 → 61.1%; affected games miss
    12.43 → 12.14, 3+ picks 55.1 → 57.3% (n≈105). ATS by season 2021–25 +0.4/0/+0.1/−0.4/+0.5, CLV
    −0.2/+0.7/−0.6/+0.5/−0.6: CLV did not clearly hold up under the stated rule; the user adopted it for accuracy.
  - **Learned coefficients:** changed team scores ≈ −1.9 and allows ≈ +2.2 pts (margin ≈ −4, total ≈ 0;
    2021–25 trainings −3.8 to −4.7 margin). Bias on affected teams: −3.3 under v4 → +0.4 under v5. The market
    already prices most of it (teams only −1.2 vs the open), so corrections mostly remove bad picks or land
    under the 3-pt threshold. **2026 changes must be entered by hand** in `coach_changes`, or v5 = v4 for 2026.
  - **2026 entered 2026-11-18** (source 'manual', list from the user, dates checked against news reports and our game
    logs; changed_at = last old-coach kickoff + 1 day, like the loader): Maryland (Oct 17), NC State (Oct 23), Baylor
    (Oct 24), Sam Houston (Oct 27), Florida State (Oct 31), UTEP and Arkansas State (Nov 14). Live predictions pick it
    up from the next `predict_upcoming` (5 AM); games already played since the changes keep their recorded predictions.

## Parking lot (not started; pick up when the user asks)

- **NFL live scores (built 2026-11-15; Claude typed the Python that day at the user's request, rule unchanged).**
  `cfb/espn.py` polls `LEAGUES = ("cfb", "nfl")`, each in its own try. For leagues in `SCHEDULE_FROM_ESPN` (NFL),
  `sync_schedule` upserts that week's teams (`school` = ESPN displayName, e.g. "Detroit Lions") and games by
  (league, espn_id); final scores go into `games` only when ESPN's `status.type.completed` is true (postponed games
  are also state "post"). Scores page: `/scores?league=nfl` (tabs), `SCORES_SQL` takes `%(league)s`, FBS filter
  only for cfb. NFL logos: `teamlogos/nfl/500/{espn_id}.png`. Next NFL steps: backtest (Dec–Jan), live
  predictions for 2027. NFL odds snapshots since 2026-11-16: `odds.save_snapshot(league)`, 2 credits per league in
  season (~190 of 500 a month with both); picks stay college-only.
  **Playoff weeks:** ESPN numbers them 1–5, nflverse 19–22. `espn.schedule_week()` converts before saving (the Pro
  Bowl, ESPN week 4, is skipped). `nfl_qbs.py` orders games by season × 100 + week, so a wrong week breaks the QB
  adjustment.
- **NFL backfill (`cfb/nflverse.py`, Claude-typed 2026-11-15):** `python -m cfb.nflverse 2016-2025` (any years;
  re-running upserts, which is also how to refresh 2026). Teams from ESPN's team list (32); games from nflverse
  `nfldata/games.csv`, matched by its `espn` column = ESPN event id; closing spread/total → `lines` provider
  'nflverse' (sign flipped: nflverse `spread_line` +3 = home favored); play-by-play parquet → `team_game_stats`
  (pass/rush plays with EPA, no 2-pt tries, garbage time = win prob outside 5–95%; explosiveness = mean EPA on
  successful plays; success = nflverse's EPA>0, not CFBD's yardage rule, so never mix leagues in one metric).
  Abbreviation fixes LA→LAR, OAK→LV, SD→LAC, WAS→WSH. No raw files kept (free to re-download). ~4 s per season.
  NFL 2020 had no crowds (home field ≈ 0): flag it in the backtest.
- **NFL player research R1/R2 (2026-11-16, scratch `nfl_r1_r2.py`, nflverse files only, no results vs lines):**
  free data: starting QB per game (schedule file), injury reports 2009+, weekly rosters (IR = status `RES`, game-day
  inactive = `INA`, 2019+ only), snap counts, play-by-play player ids; all link by gsis id (OAK→LV, SD→LAC, STL→LA).
  R1: of skill regulars who missed a game, 80–84% were flagged before game day (IR, Out/Doubtful, off the roster),
  +8–9% only by game-day inactives; a flag means he really sat (≈100%). QB "misses" include benchings (60% flagged).
  8,898 absent team-games 2016–25, 4,308 of them the 4th+ game of a spell (ratings already absorbing it).
  R2: per-play efficiency barely repeats for RB/WR/TE (split-half r 0.10–0.16; ~400–650 opportunities for half
  reliability), QB EPA/dropback r 0.36 (~410 dropbacks); usage shares repeat (r 0.81–0.93). Shrunk EPA/game above
  replacement: QB median +2.4, top ~+7; RB/WR/TE median ~0, 90th pct +0.3–0.4, top ~+0.7–1.7 (Bijan +0.77 in 2025).
  nfl-v1 settings chosen 2026-11-16 on 2017–19 (model-tests.md §9): half-life 6, last-season weight 0.5, fade 12 weeks.
  nfl-v1 backtest 2021–25: spread miss 10.22 vs close 9.76, slope at close −0.09 ± 0.09; line too flat (SD 4.0 vs 6.1).
  T-QB passed (accuracy): spread miss 10.22 → 10.14 (4 of 5 seasons), total 10.64 → 10.57, line SD 4.0 → 4.8; 26 pts per EPA/dropback.
  T-skill rejected: 10.14 → 10.25 (2 of 5 seasons); an absence costs ≈ 0.6 × the player's own EPA/game for 3 games,
  then 0. Use only for override suggestions.
  **nfl-v2 built 2026-11-16:** tables `nfl_qb_games`, `nfl_starters` (020); `cfb/nflverse.py` loads starters + QB
  dropbacks with the season; `cfb/nfl_qbs.py` (QB value, team-recent value, `add_qb_features`); `cfb/nfl_model.py`
  FEATURES = V1_FEATURES + QB_FEATURES (`choose_settings` keeps v1 inputs). Reproduces T-QB exactly (10.1405); backtest
  saved as `nfl-v2` (2,494 games; `nfl-v1` rows kept). nflverse lists projected starters for upcoming games.
  **Live NFL predictions (2026-11-16):** `nfl_model.predict_upcoming(season)` (first run: 123 games); worker job
  `nfl_daily_update` at 5:30 AM MT (moved from 6:30 on 2026-11-17 so the 6 AM snapshot's picks include Sunday's games) = `nflverse.load_seasons([season])` + predict (skips when no NFL games within 3 days
  back / 10 ahead; `games_near(season, league)`). Watch-list item 3 done once the worker is restarted.
  **NFL tab on the predictions page (2026-11-16):** `/predictions?league=nfl` (`nfl_predictions.html`,
  `NFL_PREDICTIONS_SQL`, `make_week_nav` shared with college; `PREDICTION_WEEKS_SQL` takes `%(league)s`). Our line/total
  with ±, starting QBs, nflverse line, no picks. Claude typed the main.py part at the user's request (rule unchanged).
  T-CAL rejected (2026-11-16): spread × k learned from earlier seasons; k came out 0.92–1.04 (< 1), MAE 10.140 → 10.144.
  Cause look (2026-11-16, model-tests.md §9): flat even in-sample (1.16–1.37 in 10 of 11 seasons); early backtest
  seasons looked steep only because their models had 1–3 seasons of training. Too steep early (0–2 weeks 0.89), too
  flat late (10+ weeks 1.34). Candidates: full matchup rows (own defense + opponent offense), weights by weeks played.
  T-MATCH rejected on season count (3 of 5) though pooled 10.141 → 10.088, calibration 1.14 → 0.92, SD 4.8 → 6.0,
  in-sample 1.22 → 1.00 (diagnosis confirmed); now too steep early (0–2 weeks 0.71). User kept the rule: nfl-v2 stayed until nfl-v3 (below);
  T-WEEK rejected (2026-11-16): 10.141 → 10.178 (1 of 5 seasons), 2026 worse by 2.5 SE; interactions with uncentred
  ratings were nearly collinear with progress (r ≈ 0.99). nfl-v2 stayed until nfl-v3 (below). Any centred/combined retry: judged on 2026+ only.
  **NFL audit 2026-11-16 (`docs/nfl-audit-2026-11-16.md`).** No lookahead found. Main points:
  - No bettable NFL line: nflverse gives one number per game, no opener, time or book; its source changes in 2023 and
    2025 (2026 matches ESPN's scoreboard line). Every NFL result is accuracy at roughly the close, never edge.
  - nfl-v2's 3+ gaps were 87% underdogs (50.9% vs 51.0% for every underdog blind): a product of the flat line.
  - T-QB's gain is 93% in games where a starter changed since the previous game (kickoff knowledge). Any "at open"
    grading needs a starter rule that uses only what was known then. nflverse lists the wrong starter in 54 team-games.
  - Injury files hold only the final (Friday) report, ~47–55 h before kickoff; the 2025 file has no timestamp.
  - Key numbers: 3 = 14.7% of margins, 7 = 8.5%. +3.5 instead of +3 is worth about 5 points of win rate.
  **T-HIST (2026-11-16, scratch, not judged):** nfl-v2 trained from 1999 on 2006–2016 (n=2,937): miss 10.737 vs close
  10.557, slope +0.081 ± 0.089, calibration 1.23, 88% underdogs. 2006–2016 are the clean NFL judging seasons.
  Pre-2016 data is NOT in the DB: loading it would change live QB values (`nfl_qbs.py` reads every `nfl_qb_games`
  row), and 12 pre-2011 games share an ESPN id.
  **nfl-v3 (adopted 2026-11-16, accuracy and calibration only, not edge):** nfl-v2 + full matchup rows
  (`MATCH_FEATURES`: own defense and opponent offense ratings). T-MATCH re-run unchanged on 2006–2016 passed:
  calibration 1.234 → 0.994 (3.6 SE), miss 10.737 → 10.730, slope at close +0.081 → +0.196 (info only; +0.003 on
  2021–25). App backtest 2021–25: miss 10.088, calibration 0.92, SD 6.01 (close 6.07), 3+ gaps 50.6% at the close.
  Too steep with 0–2 weeks of data (0.75). nfl-v1/v2 backtest rows kept.
  **T-OPEN (free data, Monday 8 AM ET line, run 2026-11-17): supported by the rule, no betting value shown.** Line moved
  toward us +0.388 ± 0.073 pts on 3+ gaps (5.3 SE, all 7 seasons positive), but slope at Monday +0.04 ± 0.10 and ATS 3+
  50.0% ± 4.5 (n=466). Per the rule: paper-track NFL Monday picks through 2027, no real bets. Measure 1 may be inflated by
  Monday-line noise; **T-OPEN-B (same day) ruled that out**: with a market-implied benchmark (B1, ridge on earlier closes) in the regression, our gap still predicts the move (a = +0.087 ± 0.014, 6.1 SE; B1's own move +0.10) but not results (+0.03 ± 0.11). Agreed consequence: build NFL paper-tracking at the Monday 6 AM MT snapshot for 2027.
  **NFL paper-tracking, step 1 done 2026-11-17:** `record_picks(league)` (`picks.VERSIONS`) logs NFL picks to `pick_log`
  (model_version 'nfl-v3') after every NFL snapshot; tiers are play/pass only (no NFL opener in `lines`). Decisions (user,
  2026-11-17): live picks use nflverse's projected starter and the live 2016+ training (T-OPEN used the previous-starter/IR
  rule and 1999+); step 2 grades as "the" NFL bet the first snapshot at/after Monday 6:00 AM MT of game week with 4+ books
  (not college's 8-hours-after-previous-kickoff rule).
  **Step 2 done 2026-11-17 (`022_nfl_bet_time.sql`, applied live; Claude typed it and the `main.py` part at the user's
  request, rule unchanged):** `pick_results` 'first' for NFL = first 4+-book save from Monday 6:00 AM MT of game week
  (Monday on/before the week's first kickoff) to Tuesday 6:00 AM, **Monday only** (user): no Monday save = no Early
  pick, no later stand-in. 2026 week 11 has none (NFL logging began with the Nov 18 6 AM snapshot: the worker was
  restarted after that morning's run). College unchanged (verified 0 rows differ). NFL predictions page: started games
  show the 'last' saved pick with official W/L + units, like college; older games keep the nflverse-line check.
  Wild Card Monday-night winners' divisional games may have no Early pick (matchup not set by Monday 6 AM).
  T-LOOK still needs timed lookahead lines (The Odds API history, paid, ask first).
  T-QB2 rejected 2026-11-16 (QB value from full careers, faded, draft-slot prior): miss 10.268 → 10.268 on
  2011–25, n=3,827. The simple QB adjustment already captures it; don't retry without new information.
- **NFL line movement (loaded 2026-11-17; Claude typed `021_nfl_line_moves.sql` and `cfb/line_moves.py` at the user's
  request, rule unchanged).** Table `nfl_line_moves` (game_id, source, snapshot, home_spread, total, moneylines, flags),
  evaluation only. Load: `docker compose exec -T worker python -m cfb.line_moves picksfootball|sbro < reference/<file>.csv`
  (files on stdin: containers mount only `cfb/`; re-runs upsert).
  - `picksfootball`: picksfootball.com "point spread moves" tables the user copied by hand (site terms: personal use only, no
    reuse without written permission; Claude does not scrape it). 2023–2026 incl. playoffs, 1,005 games; snapshots open, mon–sat,
    gameday. **Monday = the usable opener** (0.91 from nflverse close; 'open' is a lookahead line, 2.64). Daily lines are flipped
    back only when 7+ pts from the current line with the opposite sign (2 games); real flips are kept, flagged `favourite_flipped`.
  - `sbro`: sportsbookreviewsonline archive 2007–2021 (same no-reuse terms; user's copy), open/close; only 2016–21 load (1,622
    games, 2,403 earlier games skipped). Its open is mostly a lookahead line (best match ~7 days before kickoff); 2021 closes suspect.
  - Other NFL line files in `reference/` (not loaded): `line_history.csv` (TeamRankings consensus, timestamped, 2018–22),
    `sc_lines.csv` (SuperContest, fixed Wed/Thu, 2013–20), `bookmaker_odds.csv` + `games-selected-columns.csv` (per book, opens
    2023–26 untimed), `nfl.csv` (aussportsbetting: Pinnacle 2014–Feb 2018, bet365 2018–Feb 2025, betr from Sep 2025 = unreliable),
    `spreadspoke_scores.csv` (closes 1966–2025). Clean Monday-line window: 2018–22 (line_history) + 2023– (picksfootball).
- **NFL situations, exploratory only (2026-11-16, scratch `nfl_situations.py`, nflverse closing lines 1999–2025):**
  division underdogs 52.0% ±1.9 (n=2,611) vs 50.5% non-division, not steady by era (50.1% in 2010–19); division unders
  51.7%. Late season, a team at ≤ .350 vs one at .500+ covers 47.6% ±4.6 (n=445, −1.5 pts); final week, a team not
  starting its usual QB 43.4% ±7.5 (n=166). Head-to-head barely carries forward (r +0.03 ± 0.014; pairs 5+ pts one way
  repeat 50.3%). Bills vs Patriots 1999–2019 −4.8 vs the line, but the Patriots were +3.3 vs everyone else in
  2001–19, so it was the Patriots, not the matchup; Bills 2020–25 +1.3. Hypotheses only; none tested.
  **Decisions (user, 2026-11-16):** late-season stakes = worth a pre-registered test once nfl-v1 exists, with a
  standings-based "games left vs playoff position" measure instead of the record proxy, judged on later seasons, not
  these. Division games and head-to-head: parked (not steady by era; head-to-head repeats college Test 4). Resting
  starters: covered by T-QB.
- **Year-rollover watch list (noted 2026-11-16):**
  1. `cfb/model.py backtest()` defaults to `last_season=2025`. **Never backtest a season that has live predictions
     under the same model version** (2026 for v5): `save_predictions` upserts on (game_id, model_version) and would
     overwrite the real pre-game record with replays. Planned guard: don't overwrite rows where `is_backtest` is false.
     **Guard built 2026-11-18** (Claude-typed at the user's request): `model.save_predictions` upsert has
     `WHERE predictions.is_backtest OR NOT EXCLUDED.is_backtest`, like `nfl_model` already did; tested (backtest save on a
     live row: 0 rows changed). Still don't do it on purpose: the replay simply isn't saved for those games.
     **Weather fetch (same day):** `weather.fetch_hourly` retries connection errors / 429 / 5xx after 3, 10, 30 s and
     pauses 0.5 s between stadiums (Nov 17–18 lost 4 and 9 of ~68 stadiums to connection resets).
  2. `cfb/coaches.py load_coach_changes(last_season=2025)`: each August, once CFBD fills last season's `/coaches`,
     run it with the new `last_season` (replaces hand-entered 'manual' rows only where source is 'cfbd').
  3. NFL daily refresh is done (`nfl_daily_update`, 5:30 AM MT). Still to do each August: check the first NFL
     snapshot and nflverse load for the new season.

- **Remote access: LIVE since 2026-11-14** at `https://www.lokistoboggan.com` (moved from `cfb.` on 2026-11-17; site renamed "Sports Predictor") (Cloudflare Tunnel, `cloudflared` service
  in compose, pinned 2026.10.7, token `CLOUDFLARE_TUNNEL_TOKEN` in `.env`; Access app "CFB", team `sr-one`, email
  allow-list, one-time PIN). Lesson: the tunnel first went live with NO Access policy attached (pages and
  `POST /api/overrides` open for a few minutes; no writes happened). After any Cloudflare change, check unauthenticated
  `curl` on `/`, `/docs` and a POST: expect a redirect to a login (Access's or ours), never a 200.
- **App login: LIVE since 2026-11-14** (user's choice over Access-only: friends get accounts in the app).
  - Tables `users`, `sessions`, `login_attempts` (017). `cfb/auth.py`: argon2id password hashes, session token =
    `secrets.token_urlsafe(32)` in an HttpOnly SameSite=Lax cookie `session` (Secure when `X-Forwarded-Proto: https`),
    only its sha256 stored, 30 days; rate limit 5 fails/username and 20/IP per 15 min; same message + dummy hash for
    unknown users; `change_password` logs out other devices.
  - `cfb/web/main.py`: `require_login` middleware (fails closed: every path except `/login` and `/static/` needs a
    session; HTMX gets 401 + `HX-Redirect`; temporary passwords forced to `/account/password`); every POST must have a
    matching `Origin` (CSRF); `safe_next` blocks open redirects; `client_ip` trusts `CF-Connecting-IP` only from the
    Docker network (172.16/12); `/docs`/`/openapi.json` disabled; overrides POSTs admin-only (`require_admin`).
    Never add `--forwarded-allow-ips='*'` to uvicorn.
  - Accounts: `docker compose exec app python -m cfb.users add|reset|list|disable|enable <name> [--admin]`; the user runs
    `add`/`reset` themselves so temporary passwords never appear in chat. LAN logins required too (no IP exceptions).
  - Tested 2026-11-14 (18 LAN checks + real login through the tunnel, real public IP logged).
  - **Cloudflare Access app "CFB" deleted 2026-11-14**; the app login is the only gate. Verified over the internet:
    every page 303 → `/login` (incl. `/docs`), HTMX 401 + `HX-Redirect`, POST without Origin 403 / without session 401,
    forged cookie rejected, `next_url=https://…` → `/`, cookie `Secure` over HTTPS, real visitor IP logged (Cloudflare
    itself 403s a client-sent `CF-Connecting-IP`).
  - **HTTP → HTTPS is done in the app** (first lines of `require_login`: `X-Forwarded-Proto: http` + `CF-Connecting-IP`
    → 301 to the same URL on https). Cloudflare's "Always Use HTTPS" was switched on twice on 2026-11-14 but never took
    effect (cause unknown); the app redirect works regardless. LAN `http://192.168.0.81:8000` is unaffected.
    HSTS not enabled yet (hard to undo; consider after a few weeks on HTTPS).
  - Typing rule exceptions (one-off, user's request 2026-11-14): Claude typed step 4f and the rest of step 4 in
    `main.py`. The rule itself is unchanged.
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
- **Coach-change adjustment:** adopted as v5, see the Model section. The live season needs hand entries in
  `coach_changes` (an entry form on the overrides page would help). (`weeks_played` was fixed in v3, commit
  70f6be1: a week counts once its last game kicks off.)
- **Bet log / "Bets taken" (user idea 5, 2026-11-18):** each logged-in user records bets they actually placed
  (game, spread/total/moneyline, side, line, price, book, stake), graded from `games`, with a "My bets" page (record,
  units, ROI) vs pick_log's hypothetical best price. Largest of the 2026-11-18 ideas: new table (user_id, game_id, ...),
  POST endpoint (login + Origin check, a user edits only their own rows), grading view, page. Button on the predictions
  page (it already has the line, price and book to prefill). **Decisions (user, 2026-11-18):** built before the admin
  page; private by default with a per-user opt-in to share the record; stakes in dollars plus a per-user unit size
  (shows $ and units); spread, total and moneyline (no parlays/props). Bets can be logged after kickoff (flagged as
  such on the page); removing a bet is soft (`removed_at`) and only before kickoff. Migration `023_bets.sql`.
  **Built 2026-11-18:** `023_bets.sql` (applied live; `bets`, `users.unit_size/share_bets`, view `bet_results`),
  `main.py` `BetIn`/`add_bet`/`remove_bet`/`bets_page` (`/bets?user=`)/`save_bet_settings` (user-typed), `bets.html`,
  `bet_button`/`bet_dialog` macros + `static/bet-form.js` on both predictions pages (no button on final games; book
  prefilled only if bettable). Not yet tested in a real browser at the time of writing.
  **Results page "Bets placed" (2026-11-18; Claude typed the Python at the user's request, rule unchanged):**
  `RESULTS_BETTORS_SQL` (record per user) + `RESULTS_BETS_SQL` (last 21 days), per league tab; shows the viewer's own
  bets and those of users with `share_bets` (user's choice: opt-in kept); notes never shown. `money`/`bet_text` macros
  moved to `_macros.html`.
- **Admin settings page (user idea, 2026-11-18):** admin-only page (`require_admin` + Origin check) to change
  settings without editing code. Likely a `settings` table (key, value, updated_by, updated_at) read by the app and
  the worker at each run, plus a change log. Candidates: odds snapshot times, poll interval, leagues on/off, the
  bettable-book list, reminder dates, and user management (add / reset / disable, now the `cfb.users` CLI; a
  temporary password shown once to the admin on screen is fine). Keep pre-registered rules (tier thresholds,
  bet-time rule, model version) read-only or logged loudly: changing them mid-season changes what `pick_log`
  records, and the 2027 record must be frozen.
  **Decisions (user, 2026-11-18):** first version has all four parts: user management, a read-only status panel,
  editable schedules (worker re-reads settings and reschedules), the bettable-books list. Pick rules (PLAY_GAP,
  TOTAL_GAP, MOVE_MIN) are **editable with a change log** (user's choice over read-only); every change is logged
  (who, when, old → new, reason) and shown on the Results page. Model version stays code (it names the code that
  made a prediction, not a setting). Build order: 1 `024_settings.sql` (`settings`, `settings_log`) + `cfb/settings.py`
  (defaults, get, set with log) → 2 users → 3 status → 4 books → 5 pick rules → 6 schedules.
  Done 2026-11-18: step 1 (024 applied live; `cfb/settings.py`), step 2a–c (`cfb/users.py` returns/raises `UserError`,
  last-active-admin rule, `make-admin`/`remove-admin` commands; Claude typed 2c at the user's request, rule unchanged).
  Step 2d (`/admin`, `/api/admin/users`, `/api/admin/users/change`; not on your own account) and step 3 (025 applied:
  `job_runs`, `api_quota`; `cfb/status.py` `job_run()` / `record_quota()`; worker jobs and cfbd/odds record into them;
  `admin_status()` + status panel) done 2026-11-18, worker restarted 11:58 AM.
  **Found 2026-11-18:** `last_daily_ok` lives in memory, so a worker restart before 7:30 AM makes `daily_retry` re-run
  the whole update (4 CFBD calls wasted that morning, 626 → 622). **Fixed the same day** (Claude typed it at the
  user's request, rule unchanged): `status.ran_ok_today(job)` reads `job_runs` (today in `TZ`), `daily_retry` uses it,
  `last_daily_ok` removed. A skipped (off-season) run counts as OK, so it isn't retried.
  Step 4 done 2026-11-18: `/api/admin/settings/books` (user-typed), editor on `/admin`, bet form reads the setting
  (`bet_dialog(bettable_books)`). **Open for step 5:** picks' "best number/price" (`market_now` best_*, `pick_log`)
  comes from EVERY book in the feed (Bovada included), not only the bettable ones, contrary to the "Bettable open"
  rule above. Restricting it changes what `pick_log` records: decide as a logged pick-rule change.
  **Decided (user, 2026-11-18): keep all books.** Picks stay priced at the best number/price anywhere in the feed
  (on 805 picks to Nov 18, 56% came from non-bettable books: LowVig 237, BetRivers 122, Bovada 58, BetUS 30, BetOnline 5),
  so Results units/ROI are the best-anywhere record, optimistic for real betting. The Nov 17 "bettable books only"
  rule does NOT apply to pick prices; the bettable list drives the bet form only. Real ROI = the bets log.
  Step 5 decisions: thresholds editable with a reason; backtest rates (`PICK_RATES_SQL`, `NFL_PICK_RATES_SQL`) are
  recomputed with the current thresholds. Step 5a done 2026-11-18 (user typed the start; Claude finished it at the
  user's request, rule unchanged): `make_pick(g, rules)`, constants removed, callers read `app_settings.get_all()`
  once; old vs new make_pick identical on all 95 upcoming picks at the defaults.
  Step 5b done 2026-11-18 (Claude typed it at the user's request, rule unchanged): `PICK_RATES_SQL` /
  `NFL_PICK_RATES_SQL` take `%(play_gap)s` `%(move_min)s` `%(total_gap)s` (identical rates at the defaults);
  `POST /api/admin/settings/rules` (`RulesIn`, reason ≥ 5 chars, logs only changed keys, rounds to 0.1); editor on
  `/admin`; predictions legends and the NFL page's own tier check follow `rules`. The 5+ "Check news"/dark-row cut
  is display only, not a setting. Step 5c done the same day (Claude-typed at the user's request): `RULE_CHANGES_SQL`
  (settings_log for `RULE_KEYS`, newest first) → "Pick rules" section on Results (rules now + every change: when,
  from → to, reason, by). Step 5 complete.
  **Step 6 done 2026-11-18 (Claude typed it at the user's request, rule unchanged):** `cfb/schedule.py` (format
  `{"days": "daily"|"mon".."sun", "time": "HH:MM"}` per job, defaults = the old six schedules in check() order,
  `check`, `trigger`, `describe`, `warnings` (no Mon 6:00–Tue 6:00 snapshot = no NFL Early pick; no Sunday-afternoon
  snapshot; a snapshot within 3 h before / 30 min after a morning update), `monthly_credits` (defaults ≈ 189/500).
  Settings `odds_schedule` (in `RULE_KEYS`: reason, Results log), `job_schedule`, `poll_fast_seconds`,
  `poll_slow_seconds`; `get`/`get_all` return deep copies; `set_value` asks for a reason only on a real change.
  Worker builds jobs `<name>_<i>` from the settings and re-reads them every 5 min (`reload_schedule`); a bad setting
  keeps the running jobs. Old vs new triggers: identical run times over 4 weeks (156). League on/off: not now (user).
- **UI ideas (user, 2026-11-18; 2–4 done the same day on both predictions pages: sort in
  `static/predictions-sort.js`, `lean_badge` macro, rate label "52% in backtest (W–L)"):**
  1. *Results page updates more often.* `pick_results` is a plain view, but college final scores reach `games` only
     at the 5 AM CFBD refresh. Fix at 0 CFBD calls: the ESPN poller writes college finals into `games` when
     `status.type.completed` is true (as it already does for NFL); CFBD's 5 AM load still overwrites them.
     **Built 2026-11-18** (`espn.save_final_scores`, worker restarted ~8:30 AM); first live check = that night's games.
  2. *Sort options on predictions:* kickoff (default), spread pick, O/U pick, by team. Client-side JS on the
     table, no backend. "Confidence" = tier (Play > Caution > Pass), then gap; label it honestly: bigger gaps are not
     more reliable (5+ gaps went 41% at the close in 2026).
  3. *Clearer rate label* than "50% · 1,032 games", e.g. "Backtest 516–516 (50%)". Template only.
  4. *W/L on every finished game,* incl. Pass games and games before pick tracking: grade our lean (side of the
     market we were on) and show it apart from real picks (e.g. "lean ✓"), so it isn't read as the bet record.
     Template only (`provisional_outcome` macro exists).
- **sportsdataverse play-by-play (verified 2026-11-12):** free ESPN-derived parquet files per season
  (2016–26, ~50 MB each; `EPA`, `wp_before`, `fumble_lost`; `game_id` = ESPN id = games.espn_id). Needs
  `pyarrow`. Would allow fumble-luck and win-probability garbage-time adjustments, or replacing
  /stats/game/advanced. A different EPA model from CFBD's: don't mix them in one metric.
- **The Odds API team totals:** `team_totals` only via /events/{id}/odds, 1 credit per game per market
  (~60 per snapshot); no history to backtest. Skipped for now.
- **Weather** (see Model section) and **overrides page** (step 6), coordinator table.
- **Backtest page:** version selector / side-by-side v1 vs v2.

## Backtest (how the model is judged)

- Walk-forward only: a week-W prediction uses data from before week W plus priors. No lookahead.
- Store model spread/total, opening and closing lines, final score per game.
- Report: model MAE vs. closing-line MAE (spread and total); cover rate at 3+ and 5+ point
  disagreements; closing line value (did the line move toward the model between open and close).
- Report results honestly; matching the market is the realistic first goal.
- **Statistics to quote with every result:** n, SE = sqrt(p(1-p)/n), 95% interval ±1.96 SE. Per season
  n≈400–450 3+ picks (±4.7); pooled 2021–25 n≈2,150 (±2.1). Telling 53.4% from 52.4%: ±1 pt at 95% needs
  ≈9,600 picks (≈22 seasons); 80% power to detect it needs ≈19,600 (≈45 seasons). Opening lines exist only
  2021+ (DraftKings 2023+, ESPN Bet 2023–25, Bovada); 2018–20 have close only, so every "at open" figure is
  2021–25. "Best open" = at most 3 books (1 in 2021–22), no prices.
- **Bettable books (user, 2026-11-17):** MyBookie (main), DraftKings, FanDuel, BetMGM, Caesars, Fanatics (ex-PointsBet).
  In our feed: mybookieag, draftkings, fanduel, betmgm. Caesars/Fanatics are in the Odds API us region but not returned.
  Every other book (Bovada, LowVig, BetOnline, BetUS, BetRivers) is a reference line only.
- **Bettable open** = best number among the bettable books in the first snapshot at bet time (019 rule: 8+ h after both
  teams' previous kickoff, 4+ books). Live decisions, tiers, ROI and stopping rule 5C use it. History has no bettable
  open (CFBD's DraftKings open is a lookahead), so 2021–25 research keeps the Bovada open, labelled "reference open".
- **Prices, vig, ROI:** bettable books only (vig 4.3–4.8%; break-even at the median bettable price 52.4–52.6%).
- **Pass bar per plan:** one-sided Bonferroni, 5% family: 1 test 1.645 SE, 3: 2.13, 5: 2.33, 10: 2.58; each plan states
  its count and bar before running. Already-registered tests keep their bars.
- **Paid data:** pre-registered before buying (tests, rules, bars, exact pulls and credits); nothing else run on it first.
  These rules apply to tests registered after 2026-11-17; Holdout 5A, Test B, Holdout T, Test L are unchanged.
  Odds API purchase decision (2026-11-17): not now; keep collecting free snapshots.
- **CLV is direction only.** On 3+ picks the line moves +0.6 pts toward us vs a 6.3-pt average gap
  (~10% of the gap); that's how 2026 shows 64.8% CLV with 50% ATS at open. Report CLV in points too.
  Rule A's "CLV not down >1.0" means 1.0 percentage point of CLV %.
- **Slope metric (2026-11-13):** regress (result − line) on (our line − line) over all games. v5: +0.104 ± 0.048
  at open (2021–25, n=4,256), +0.015 ± 0.037 at close (2018–25). Paired Δslope (same games, 2,000-game bootstrap)
  has SE ≈ 0.008–0.009 for one feature. Open/close sanity check holds: on v5's 3+-at-open picks, 52.40% at
  open vs 50.74% at close (gap 1.67) ≈ CLV 0.614 pts × 2.5–3.3% per pt. **Rule B (slope main test) approved
  2026-11-13 for all tests from Test 6 on**; adoption policy (edge vs accuracy), pre-registrations A–C and
  combined-test candidates: all in `docs/model-tests.md`. Under Rule A, v5 vs v4 passes (4 of 5 seasons); T4 coach career fails Rule A but has
  Δslope +0.026 ± 0.009 (hypothesis for the 2026 holdout, not a reversal).
- **Holdouts and multiple testing (2026-11-12):** ~25 variants tried. The tier rule and Rounds 2–4 looked
  at 2026, so 2026 is used up for those; v4's own 2026 record is roughly clean. Clean from here: pick_log
  since 2026-11-12 and the 2027 season with the model frozen at kickoff. **Write the acceptance rule before
  every test** and don't loosen it after seeing results.
- **Outside review (2026-11-12), 0-call findings:** P(cover) from N(gap, σ) is wrong for us (σ of our miss
  16.3 vs market 15.5; actual cover 48–55% at every gap size, a naive σ=15 model says 59–77%). Key numbers:
  3 = 9.4%, 7 = 7.9% of margins (value half-points there when line shopping). Gaps still 3+ at close won
  50.3% in 2021–25 (−4.0% ROI at −110; the earlier −2.9% was the 2018–25 rate, 50.8%): bet early. Bowls
  53.6% (n=97), not worse; CFP 46% (n=13). Home-field drift real (2024–26 ≈ −1.1/season) but already tested
  3 ways, rejected. Fumble luck impossible from CFBD advanced stats.
- **Test 1 (pre-registered, 2026-11-12), one-shot holdout on 2026 games through Nov 9:** weeknight (Mon–Thu ET)
  games with MAC/Sun Belt/C-USA, 3+ at open: discovery 2021–25 74-44 (62.7% ± 8.7), holdout 2026 11-9
  (55.0% ± 21.8, n=20) → **kept as a hypothesis**: tag and track, no model change. Don't quote the pooled
  61.6%: discovery games can't confirm their own finding. FCS opponent: 2021–25 131-95, 2026 37-45
  (45.1%) → **rejected**. 2026 is now used up for both questions.
- **Test 2 (pre-registered, 2026-11-12), rejected:** weight last season's games per team by returning
  production (× max(0.1, 1 + k·z), z = mean of both teams' standardized returning PPA; k=0.25, 0.5, 0.5 + QB
  passing-PPA term), baseline v5, 2021–25. Weeks 0–5 miss moved ≤0.006 (12.995 → 12.994–13.001), ATS 3+ open
  52.43 → 52.29/52.51/52.40%, not lower in only 2 of 5 seasons each, CLV +0.2–0.3. Last season's games carry too
  little weight (0.25, gone by week 6) and returning production is already a feature, so this path can't move
  early-season accuracy. **Test 3 (shrink toward each team's prior) was not run**: its precondition (a weeks
  0–5 gain in Test 2) failed. Don't retry either without new information. Script: scratch `test2_returning.py`.
- **Test 4 (pre-registered, 2026-11-13), rejected: coach / matchup history.** Residual = team's actual margin −
  v5's predicted margin (v5 walk-forward 2018–25, 2020 excluded); correction = shrunk mean of prior-season residuals.
  Rule: pooled ATS 3+ at open 2021–25 up, ≥ baseline in 4 of 5 seasons, CLV not down >1, MAE not worse.
  (C) coach career, K=100: ATS 52.40 → 52.86% (n=2,079, ±2.1) but by season +0.7/−0.9/−0.4/+0.4/+2.3 (3 of 5) → fails;
  CLV 61.1 → 61.8, spread miss 12.77 → 12.70, better in all 5 seasons (K=50/200 similar). Accuracy gain is consistent,
  betting gain isn't. (H) team vs same opponent, K=5: 52.43%, 2 of 5 seasons, CLV −1.7, miss worse. (CC) coach vs
  coach, K=5: 51.93%. 2026 not looked at for this question (possible one-shot holdout for C if pre-registered).
  Script: scratch `coach_test.py` (session 2026-11-13).
- **Test 5 (pre-registered, 2026-11-13), rejected: fumble-recovery luck** from sportsdataverse play-by-play
  (scrimmage fumbles; off_luck = 0.5·fumbles − lost, def_luck = opp lost − 0.5·opp fumbles, season-to-date means as
  points-model features `off_fumluck`/`oppdef_fumluck`). Same rule as Test 4. ATS 3+ open 52.43 → 52.25% (n≈2,170),
  ≥ baseline in 1 of 5 seasons, CLV 61.2 → 60.8, spread miss 12.83 = 12.83. Coefficients tiny and wrong-signed
  (+0.9 / −0.2 pts per fumble/game; feature SD 0.24). PBP covers 96–100% of our FBS games, but fumble counts in
  2021–23 are ~25% lower than other seasons (ESPN text parsing), so 2021 is noisy. pyarrow is in requirements.txt;
  read only the needed columns (files have 506 columns; 4 GB VM). Script: scratch `fumble_test.py`.
- **Test 6 (pre-registered, Rule B, 2026-11-13): combined weak features.** v5 + coach career (T4 residual, K=100,
  now a learned feature) + Round 4 drive metrics; points model Ridge(α=1) on standardized features; this
  reproduces stored v5 (mean |diff| 0.004 pts).
  - (A) **Passed:** Δslope at open +0.044 ± 0.021 (2.1 SE), ATS 3+ open 52.41 → 53.38% (n=2,132), CLV pts
    0.615 → 0.610, spread miss 12.826 → 12.737.
  - (B) Leave-one-out: coach career carries it (+0.038 ± 0.019); the drive metrics add nothing.
  - (C) Selection on 2021–23 → v5 + coach career, confirmed once on 2024–25: 1.80 SE vs a 1.96 bar → **failed**.
  - **User decision (2026-11-13): not adopted; wait for the 2026 holdout**, amended to v5 + coach career as a learned
    feature (model-tests.md section 5A). Rule B was approved after T4's slope was known, and the candidates were
    picked from the same data, so A is biased upward.
  - **NEXT ACTION: run holdout 5A once, on or after 2026-12-07** (after conference championship weekend).
    **2027 season plan: `docs/plan-2027.md`** (DRAFT 2026-11-18): frozen `v6` = v5 + T1 + T-OCDC (+ coach career if 5A
    Confirmed), one no-harm check in August, paper models v6-ht4 / v6-ht2b / v5, betting rules, judged items, open decisions.
    Amended 2026-11-16, before any 2026 result: graded at the **Bovada open**, mixed open reported beside it.
  - **Audit 2026-11-16 (`docs/audit-2026-11-16.md`):** CFBD `spreadOpen` differs by book. Bovada = true Sunday-evening
    opener; DraftKings (and partly ESPN Bet) = lookahead line from before the previous week's games (v5 "wins" 55.4%
    against it: an artifact). From now on "the open" = Bovada `spread_open` with Bovada's close for CLV: v5 2021–25
    1,097–997 (52.39%), slope +0.113 ± 0.048, CLV 0.56 pts. Drop "best open". New tests need 2.24 paired SE.
    Done 2026-11-16: view `018_bovada_open.sql` (adds `open_book_close`), Bovada filter in `UPCOMING_SQL`,
    `PREDICTIONS_SQL`, `OPEN_RESULTS_SQL` (Claude typed these three at the user's request, rule unchanged), "Best #" removed.
    5A bar raised to 2.24. Approved tests A, B, C, F: model-tests.md section 8. Also done (Claude-typed, same exception): `PICK_RATES_SQL`
    grades Play/Pass at the Bovada open (Caution and totals at the close; `graded_at` column), and `019_pick_bet_time.sql`
    makes `pick_results` "first" the pick at bet time (4+ books, 8+ h after both teams' previous kickoff).
    Tests run 2026-11-16 (scratch `test_cf.py`): **C per-metric shrinkage rejected** (Δslope −0.36 SE, MAE worse all 5
    seasons, CLV −3.5 SE); **F DraftKings lookahead supported** (slope +0.175 ± 0.063 at the DK open 2023–25, Bovada open
    moved +0.73 pts toward us): track lookahead picks in 2027, don't bet on it alone. A and B wait for Dec 6–7.
    Reminders: this line, a project memory, and a notice on the predictions page from Dec 7.
    **Test L run 2026-11-18 (edge plan Step 2): supported.** The open overreacts to last week's luck (actual − deserved
    margin): line-move slope −0.0112 ± 0.0032 (−3.5 SE), all 5 seasons; result slope −0.020 ± 0.026; not inside v5.
    Small (~0.4 pts top vs bottom third). Tracked in 2027 as a bet-selection input, no betting on it alone.
  - Live use of the drive metrics would also cost 1 CFBD call/day (`/drives`); coach career needs none.
  - Script: scratch `t6.py`, plan `combined_test_plan.md`.
- **Test 7 (pre-registered, 2026-11-13), rejected: weather for totals.** Open-Meteo historical-forecast archive
  2021–25 (947 requests incl. a gap refetch; 98% coverage), observed ERA5 for training, judged at the close.
  Total slope Δ +0.014 ± 0.015 (0.97 SE), O/U 3+ close 50.0%, total miss 12.965 vs 12.971. Weather stays a
  page flag only.
- **Round 1 plan (docs/model-plan-2026-11-17.md), run 2026-11-17, Rule C at 1.96:** Step 1 sanity passed (v1→v5 slopes
  rise together, rho +1.00) → Rule C is the main test. **T1 full matchup rows PASSED** (Δ line-move +0.0084 ± 0.0031,
  2.7 SE, all 5 seasons; MAE 12.826 → 12.803; SD 13.65 → 14.52; weeks 0–4 calibration 0.943 → 0.912): candidate for
  the frozen 2027 record (not live). **T4 cached-stats batch FAILED** (line-move −1.5 SE; slope left at the close
  +4.0 SE); no more backtest variants, kept only as a pre-registered 2027 hypothesis (model-tests.md §4, H-T4).
  Dropped: T2(a), T3 (= Test 3), T6 (= Test D). Round 2 candidates: T2(b) state-space, T5 (special teams;
  WP garbage time), each under the accuracy rule.
  **T5a special teams REJECTED (2026-11-18, model-tests.md §10):** spread MAE 12.826 → 12.812 (4 of 5 seasons) but
  CLV points −0.029 ± 0.012 (−2.4 SE, bar −2) and line-move slope −3.2 SE: priced-in information. Don't retry.
  **T-OCDC PASSED the accuracy rule (2026-11-18, model-tests.md §10), small:** offseason new OC / DC from Wikipedia
  infoboxes (`off_coach`, `def_coach`, co-coordinator fields; all 1,437 FBS team-seasons 2015–25; change = no name in
  common with last season's field, amended by the user before running), as `pr_new_oc` + `oppr_new_dc` faded like
  `new_coach`. Spread MAE 12.826 → 12.820 (4 of 5), weeks 0–4 12.900 → 12.883, totals better 5 of 5, betting checks flat.
  Accuracy only. **CFBD has no coordinator data** (head coaches only, checked against the spec 2026-11-18).
  **User decision (2026-11-18): T-OCDC goes into the frozen 2027 model candidate** (v5 + T1 + T-OCDC, + coach career if
  5A confirms), checked together for no harm before the freeze; data from table `coordinators`.
  **T5b REJECTED (2026-11-18):** six metrics rebuilt from sportsdataverse play-by-play with OUR market-free WP cut
  (their `wp_before` uses the betting spread, so it can't be used: market leak). Spread MAE 12.826 → 12.876, worse in
  all 5 seasons; CLV points −2.5 SE. CFBD's metrics are better; don't retry WP garbage time or the sdv EPA model.
  **T2(b) state-space (Kalman) ratings REJECTED on betting checks (2026-11-18), but the biggest accuracy gain yet:**
  spread MAE 12.826 → 12.732 (5 of 5 seasons), totals 12.969 → 12.895, weeks 0–4 12.900 → 12.757, late-season
  calibration 1.064 → 0.982, all 7 metrics predicted better one step ahead; but ATS 3+ at open 52.41 → 50.92% (−1.5 pp,
  bar −1.0) and CLV % −1.6 pp, with 17% fewer 3+ gaps (agrees with the market more). No variants. Round 2 complete.
  **Pre-registered as 2027 hypothesis H-T2b (user, 2026-11-18; model-tests.md after H-T4):** frozen params, paper only,
  judged once after the 2027 regular season on MAE + Δ result slope at open + Δ line-move slope (≥ −1 SE each).
  **Outside review 2026-11-18 (`docs/plan-2026-11-18.md`):** diagnostics D-CLV (CLV % 61.2 = moved-only vs 52.6 = all
  picks; 14% of 3+ picks don't move), D-TOT (**totals line-move slope at the open +0.111, +9 SE**, every season; nothing
  left at the close), D-EARLY (v5 + T1 0.85–0.87 in weeks 3–9), D-SEL, D-ML (no opening moneylines; nothing at the close).
  Accuracy rule now uses continuous no-harm checks (new registrations). H-AVG and H-TOT registered for 2027. Bar 2.24 for
  4 tests: **B1-spreads supported** (+4.8 SE; college B1 is a weak benchmark), **B1-totals supported** (+8.7 SE); TOT-1
  dropped. **B1-spreads supports the spread signal but is a weak benchmark** (college B1 is less accurate than the
  opener, 13.8 vs 12.3 MAE, and the line moves away from it): **the bet-time-median → last-median line move in 2027 is the
  real opener-noise check** (plan-2027.md). Result version: spreads a +0.115 ± 0.050 (2.3 SE) with B1 in; **totals a
  +0.050 ± 0.062 (consistent with 0 and with the ~0.105 the line move implies: can't tell them apart), while B1-total's own gap predicts total results +0.31 ± 0.07 (4.5 SE, all 5
  seasons)** → registered H-TOT-B1 (2027, paper, bar 1.96). Moneylines (`h2h`) added to the odds snapshots 2026-11-18
  (Claude typed it at the user's request): 3 credits per league per snapshot, ≈ 283 a month in season (of 500).
  **EARLY-1 rejected** (calibration error +3.7 SE better, but line-move −1.3 SE and CLV points −2.1 SE: shrinking lines
  shrinks the disagreements the market follows). **SEL-v0 failed** (Δr +0.025 ± 0.037; nothing ranks line moves within 3+
  gaps out of sample). All 4 judged tests of the plan are done; calibration stays a reported item for the August check.
  **B1-total beats the close (information, leak-free):** (result − close) on (B1-total − close) +0.198 ± 0.062 (3.2 SE),
  with season-week fixed effects +0.173 ± 0.065 (2.7 SE); 2021 and 2024 carry it, 2022 = 0. B1-total is fit on earlier
  closing totals only (no scores); leakage audit on all 4,160 games clean. Small at the close (implied 51.3% on 3+ gaps,
  below break-even). H-TOT-B1 unchanged. **No new tests on 2021–25 until Dec 7** (user).
  **2027 build #1 (2026-11-18, Claude typed `029_bettable_grading.sql` at the user's request, rule unchanged):** view
  `pick_results_bettable` grades pick_results' first/last picks at the best bettable number then price in the snapshot
  each pick was made from (books fixed in the view). Dry run: so far 8–9 graded Plays, units nearly equal; one example
  +9 anywhere vs +7.5 bettable. Totals "agree" tag (our total and B1-total same side) registered, reported only.
  Results page: "At the books you can bet" section (`BETTABLE_SUMMARY_SQL`, Early/Late by tier, best-anywhere units
  beside). **Build #2 (2026-11-18, Claude typed it at the user's request, rule unchanged):** `cfb/model.py` has v6 =
  v5 + `MATCH_FEATURES` (T1) + `COORDINATOR_FEATURES` (T-OCDC, from table `coordinators`), chosen per version through
  `VERSION_FEATURES`; `train`, `backtest`, `predict_upcoming` take `version`; `MODEL_VERSION` stays "v5" until the freeze.
  Equivalence (read-only): all 15,182 rows match the research stack (max diff 7e-14), v5 via the app code vs stored v5
  0.0025, v6 app vs research stack 0.0000 on 6,727 games. `cfb/freeze_check.py`: the August no-harm check (plan-2027
  2.2) with the fixed fallback order; **not run** (it is the August gate; no tests on 2021–25 before Dec 7). Coach career
  is a stub (`COACH_CAREER = False`) until 5A is decided and built.
  **Build #3 (2026-11-18, Claude typed it at the user's request, rule unchanged):** paper models in their own table
  `paper_predictions` (030), NOT `predictions` (the pages fall back to any version's prediction, and the 2027 tests
  grade paper models at bet time, so every morning's row is kept). `cfb/paper.py` (versions, save, `health`, `check`,
  `metrics_text`), `cfb/benchmark.py` (B1, matches research exactly). `model.build_rows` is built once in
  `daily_update` and shared; paper models run after the live prediction (jobs `paper_models`, `paper_check`, shown on
  /admin), so a paper failure can't touch v5. `/metrics` (Prometheus): only with `METRICS_TOKEN` in `.env`, bearer
  token, refused through Cloudflare. First run 2026-11-19 05:05: v6 131, b1-total 129, check OK; h2h confirmed (3
  credits per league call). **v6-ht4 / v6-ht2b built 2026-11-19 (Claude typed them at the user's request, rule
  unchanged):** `cfb/paper_features.py` (`add_t4_columns`: 8 cached advanced stats rated like v5; `state_space_rows`:
  Kalman ratings at the frozen `STATE_PARAMS`, filter from 2016, T1 columns rebuilt), `paper.ROW_BUILDERS`,
  `model.VERSION_FEATURES` entries; checked against the research scripts column for column.
  **Builds #5 / #6 (2026-11-19, Claude typed them at the user's request, rule unchanged):** `cfb/report_2027.py`
  (read-only report: median line moves, totals agree tag, Test 1 weeknight, Test L's X, DK lookahead; dry run on 2026 OK,
  B1 at bet time empty until B1's first full week); weeks 3–9 "≈ effective" gap note on the predictions page, keyed to v6.
  **Challengers registered 2026-11-19 (user; plan-2027 §8, model-tests "2027 college family"):** college family of 6
  judged items at **2.39** (H-T4, H-TOT, H-TOT-B1, v6-pts; H-T2b / H-AVG need ΔMAE ≥ 1 SE); v6-noT1, EARLY-1, v5
  reported; v6-hl3 dropped. NFL: N-TOT-B1 (2027) and nfl-v3-wk (2027–28) at 1.96, nfl-v2 reported. Overrides apply to no
  model in comparisons; the champion's raw line is saved daily in `paper_predictions` (college built; NFL runner in the
  spring). Built the same day (Claude-typed at the user's request): `v6-noT1`, `v6-pts` version switches. NFL D-TOT (info):
  +0.124 ± 0.020 (6.3 SE, 2023–25). C-HIST not pursued (only 2014–15 usable, ~19 CFBD calls, can't resolve v6 vs v5).
- **Hypotheses noted 2026-11-13 (untested):** (1) 2026 3+ at close 44.4% ± 5.3 may reflect more injury news at the
  close (Big Ten availability reports 4/week from 2026; SEC 2024+, ACC/B12 2025+); test 0-call by conference games
  with reports vs without, difference-in-differences across each conference's first report season.
  (2) Totals bias +2.08 (2026) ≈ +2.04 (2023); the market was also low (+1.07, +1.28). No new test.

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
- Scheduling (times editable on /admin since 2026-11-18; these are the defaults): the worker runs `daily_update()` at 5 AM Mountain (refresh current season's
  `/games`, `/stats/game/advanced`, `/lines` = 3 calls, then the latest week's passing box scores
  via `refresh_recent_qbs` = 1 call, then `predict_upcoming`; ~4 calls/day), skipped when no
  games are within 3 days back / 10 days ahead. **Each August, backfill the new season once by
  hand** (`python -m cfb.backfill <year>` then `python -m cfb.load <year>`, ~11 calls).
- Every CFBD response is stored raw in `api_responses` before parsing; check it before any
  call. `/info` itself costs a call.
- Schema changes: new numbered files in `db/init/` (runs only on a fresh volume), applied by
  hand to the live DB with `docker compose exec -T db psql -U fb-user -d football < file`.
  Never suggest `down -v` once real data is loaded. DB user is `fb-user`, DB is `football`.
