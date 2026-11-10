# Project brief: College Football Betting Model (personal use)

You're setting up a self-hosted web app on this VM that predicts college football point spreads and compares them with betting lines. It's for my own use and is reached only over my home LAN or Tailscale. Everything below was decided in an earlier session. Build from it and don't revisit these decisions unless something is actually broken.

## Environment
- VM: Debian (check the version with `cat /etc/os-release`; Debian 13 Trixie expected), 2 vCPU, 4GB RAM, 60GB disk.
- Stack: Docker Engine with the Compose plugin, Python, Postgres.
- Install Docker from **Docker's official apt repository** (docs.docker.com/engine/install/debian), not Debian's `docker.io` package. Add my user to the `docker` group.
- Tailscale runs **on the host**, not in a container. Install it if it's missing, but I'll run `tailscale up` myself to authenticate.
- **Docker bypasses ufw/nftables for published ports.** Never publish the Postgres port. Bind the web port to a specific LAN IP, or publish only on 127.0.0.1 and expose it with `tailscale serve`. Ask me which way I want before you finish networking.

## Data source: CollegeFootballData (CFBD) API
- Base URL: `https://api.collegefootballdata.com`, with the header `Authorization: Bearer <key>`.
- The API key goes in the project's `.env` file as `CFBD_API=...`. I'll paste it in. Never print it, commit it, or build it into an image.
- **Free tier: 1,000 calls per month**, resetting on the 1st. Check usage with `/info` and keep the call budget in mind at all times:
  - Pull whole seasons in one call where possible. Leaving out the `team` parameter returns every team, e.g. `/stats/game/advanced?year=2024`.
  - Cache everything in Postgres and never re-fetch data you already have.
  - Backfill several past seasons once. After that, refresh only the current week, about 5–10 calls per week.
- **Not on the free tier:** adjusted metrics/WEPA, weather, scoreboard, live play-by-play, GraphQL. Don't use those endpoints.
- OpenAPI spec (free, doesn't count toward the quota): `https://api.collegefootballdata.com/api-docs.json`. Read it for parameters and response fields.
- Key endpoints:
  - `/games`, `/games/teams`: games, scores, team box scores
  - `/stats/game/advanced`, `/stats/season/advanced`, `/ppa/games`: EPA/PPA, success rate, explosiveness, havoc, line yards, points per opportunity. These accept `excludeGarbageTime=true`; always use it.
  - `/lines`: each game includes `homeScore`/`awayScore` and a `lines[]` array per sportsbook with `spread` (latest, treat as closing), `spreadOpen`, `overUnder`, `overUnderOpen`, and moneylines.
  - Priors: `/player/returning`, `/talent`, `/recruiting/teams`, `/coaches`, `/player/portal`
  - Also useful: `/teams/fbs`, `/calendar`, `/ratings/sp`, `/ratings/srs`, `/ratings/elo` (for comparison only)

## Modeling approach
1. **Per-play efficiency, never raw totals.** Use EPA/play (passing and rushing separately), success rate, explosiveness and points per opportunity, all with garbage time excluded.
2. **Do the opponent adjustment ourselves**, because CFBD's adjusted metrics are paid. Fit ridge regression on game-level results: `offense_metric ~ team_offense + opponent_defense + home_field`. This gives adjusted offense and defense ratings for every team. Handle games against FCS teams sensibly, e.g. group FCS opponents or down-weight those games.
3. **Preseason priors:** last season's ratings, returning production, talent composite, recruiting, coaching changes and transfer portal movement. Blend priors with current-season data and fade the priors out by about weeks 5–6.
4. **Output:** a predicted point spread for each game.
5. **Manual overrides:** CFBD has no injury data. Add a table and UI where I can enter adjustments, e.g. "QB out, -N points for team X, game Y", that get applied before predictions.

## Backtest (this is how we'll judge the model)
- **Walk-forward only.** To predict a game in week W of season S, use only data from before week W of season S, plus the priors. Rebuild the ratings week by week. Any lookahead makes the results worthless.
- For each past game, store: the model's spread, the opening line, the closing line and the final margin.
- Reports:
  - Average error of the model vs. the final margin, compared with the closing line's average error vs. the final margin
  - Cover rate when the model disagrees with the line by 3 or more points, and by 5 or more
  - **Closing line value:** how often the model's side moved in its favor between `spreadOpen` and `spread`
- I expect the first version to roughly match the market, not beat it. Report the results honestly.

## Architecture
```
docker-compose.yml
├── db      postgres:17, named volume, no published port
├── app     FastAPI + Jinja templates + HTMX + a JS chart library (web UI)
└── worker  Python ingestion + model + predictions, on a schedule
            (daily in season, weekly off-season; APScheduler or cron)
```
- The worker is separate from the app, so a slow ingestion run never slows the web UI.
- Secrets live in `.env`, read by Compose at runtime. Commit a `.env.example`.
- A nightly `pg_dump` to a mounted backup directory. My overrides and bet log can't be re-fetched, so they need backing up.
- Pick a project directory (e.g. `~/cfb-model`) and initialize git.

## First web pages
1. **This week:** each game with the model's line, the market line and the difference, highlighting big disagreements
2. **Team page:** adjusted offense and defense ratings over the season
3. **Backtest:** model vs. closing line vs. final score, by season, with the metrics above
4. **Overrides:** enter injury and other manual adjustments

## Build order
1. Install Docker, check that Tailscale is present, and scaffold the project: compose file, `.env.example`, database schema
2. Ingestion worker: backfill several seasons (ask me how many, and check `/info` for remaining calls first)
3. Opponent-adjusted ratings plus the spread model
4. Walk-forward backtest and its report
5. Web UI pages
6. Priors, overrides and scheduling

Check with me after steps 1 and 2 before going further. Tell me how many API calls each step used.
