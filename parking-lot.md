# Parking lot

Ideas we want to remember but aren't building yet. Each item says where it came from.
When we decide to build one, move it into the build order in `CLAUDE.md` and delete it here.

## Pages / UI

### Time zone toggle
Let each viewer choose the time zone used to show kickoff times, instead of only the
`TZ` set in `.env`. The choices for now are the mainland US zones:
- Eastern (`America/New_York`)
- Central (`America/Chicago`)
- Mountain (`America/Denver`), the default
- Arizona (`America/Phoenix`, Mountain time without daylight saving)
- Pacific (`America/Los_Angeles`)

Notes:
- Times are already stored in UTC, so this only changes how they're displayed.
- The pages are rendered on the server, so save the choice in a cookie that the server
  reads. Pages, including the HTMX fragments that refresh every 30 s, then render in the
  viewer's zone. `.env` `TZ` stays the default when there's no cookie.
- Show the zone abbreviation next to times (MST/MDT etc.) so it's clear which zone is active.
- Adding Alaska/Hawaii later is just more entries in the list.
- *Source: user request, 2026-11-10.*

### Team ratings page
Adjusted offense and defense ratings for each team, with a chart of how they changed
week by week through the season.
*Source: design brief "First web pages" #2; CLAUDE.md Pages #3 ("Later").*

### Charts
Add a small JS chart library for rating trends and backtest results.
*Source: design brief, Architecture (app container).*

## Model / data

### Compare with outside ratings
Show our ratings next to SP+, FPI, Elo, SRS and CFBD's CORE as a sanity check, and
possibly use them as extra preseason priors. SP+ is already cached; the others cost
about 1 call per season each.
*Source: design brief (lists them "for comparison only"); `reference/cfbd-free-tier-metrics.md` §8.*

### Try the newer CFBD endpoints
`/passing/*` (CPOE, target depth), `/rushing/*` (run direction, offensive line splits) and
`/punting/*` may be useful model features. Test one call each to confirm they're on the free tier.
*Source: `reference/cfbd-free-tier-metrics.md`.*

### Moneyline / win probability
Turn the predicted margin into a win probability and compare it with the market
moneylines (`/lines` already includes `homeMoneyline`/`awayMoneyline`).
*Source: the moneyline data is already in the cached `/lines` responses.*

## Tracking

### Bet log
A table and page to record the bets placed (game, side, line, odds, stake, result) and
track results and closing line value. It needs the nightly backup because it can't be
re-fetched.
*Source: design brief (backups section mentions "my overrides and bet log").*

## Bigger scope

### NFL support
Add NFL as a second league. The schema is already league-aware (`league` column, our own
ids, source ids unique per league). Likely sources: ESPN for live scores, nflverse for
stats/EPA. NFL-specific logic goes in NFL-only modules.
*Source: CLAUDE.md Decisions.*
