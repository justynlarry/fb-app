# CFBD free-tier metrics reference

Source: CFBD OpenAPI spec v5.33.2 (`https://api.collegefootballdata.com/api-docs.json`,
read 2026-11-10; reading the spec costs no quota). Field names below are the JSON keys
the API returns.

**Tier notes**
- Paid, don't use: `/scoreboard`, `/live/plays`, all `/wepa/*` (adjusted metrics),
  `/games/weather`, `/games/{id}/preview/adjusted`.
- Everything else is open to any API key. Several endpoints (`/passing/*`, `/rushing/*`,
  `/punting/*`, `/ratings/core`, `/game/box/advanced`) are newer additions. The spec doesn't
  mark them as paid, but test each one with a single call before relying on it.
- **Cached** = already stored in `api_responses` for 2016–2026.
- `excludeGarbageTime` is available only on: `/stats/season/advanced`, `/stats/game/advanced`,
  `/ppa/teams`, `/ppa/games`, `/ppa/players/*`, `/stats/player/success*`, `/player/usage`.

**PPA = EPA.** CFBD calls expected points added "PPA" (Predicted Points Added). Throughout
this file, `ppa` is the *average per play* and `totalPPA` is the *sum*.

---

## 1. Core efficiency (the model's main inputs)

Endpoints: `/stats/game/advanced` (per game, **cached**), `/stats/season/advanced`
(per season), `/teams/season/overview` (per season, includes postseason). Each row has
the same fields under `offense` and under `defense`. For defense, the numbers are what
the team *allowed*.

| Metric | What it is |
|---|---|
| `ppa` | Average expected points added per play. The best single measure of how efficient an offense (or defense) is. |
| `totalPPA` | Sum of EPA over every play. Depends on how many plays were run, so use `ppa` when comparing teams. |
| `successRate` | Share of plays that count as "successful": 50% of the yards needed on 1st down, 70% on 2nd, 100% on 3rd/4th. Measures consistency. |
| `explosiveness` | Average EPA on successful plays only. Measures how big the good plays are. |
| `plays`, `drives` | Number of plays and drives. A basic pace input, since plays per game drive the total. |
| `passingPlays.*` / `rushingPlays.*` | `ppa`, `totalPPA`, `successRate`, `explosiveness` for passes and runs separately (season overview adds `rate`, the share of plays). |
| `standardDowns.*` | The same metrics on "normal" downs (1st down, 2nd-and-7 or shorter, 3rd/4th-and-4 or shorter), where the offense can either run or pass. |
| `passingDowns.*` | The same metrics on obvious passing downs (2nd-and-8+, 3rd/4th-and-5+). Shows how a team handles being behind the chains. |

**Season-only extras** (`/stats/season/advanced`, `/teams/season/overview`):

| Metric | What it is |
|---|---|
| `pointsPerOpportunity` | Points scored per drive that reaches the opponent's 40 ("scoring opportunity"). Measures finishing drives. |
| `totalOpportunies` | Number of scoring opportunities. (The API really does misspell it.) |
| `fieldPosition.averageStart` | Average starting yard line of drives. Reflects special teams, turnovers and the defense. |
| `fieldPosition.averagePredictedPoints` | Expected points at the average starting spot. The same field-position idea, measured in points. |
| `havoc.total` / `.frontSeven` / `.db` | Share of plays with a tackle for loss, forced fumble, interception or pass breakup, split by defensive line/linebackers vs. defensive backs. |

## 2. Rushing / offensive line

In the advanced stats above, and in more detail in `/rushing/teams/games` and
`/rushing/teams/season` (which add a `directions.left/middle/right` split).

| Metric | What it is |
|---|---|
| `lineYards` | Rushing yards credited to the offensive line: 0–3 yards at full value, 4–8 at half, losses at 120%. Average per carry (`lineYardsTotal` is the sum). |
| `secondLevelYards` | Yards gained 5–10 past the line of scrimmage, per carry. Tracks running back plus line play. |
| `openFieldYards` | Yards gained more than 10 past the line, per carry. Tracks breakaway ability. |
| `stuffRate` | Share of runs stopped at or behind the line. Lower is better for the offense. |
| `powerSuccess` | Conversion rate on 3rd/4th down or goal-line runs needing 2 yards or less. |
| `yardsPerCarry`, `sacks`, `kneels`, `teamRushes` | Basic run totals. The rushing endpoints count sacks and kneels separately so they don't distort the run numbers. |

## 3. Passing

`/passing/teams/games`, `/passing/teams/season`, and the player versions. Each has
`offense`/`defense`, plus a `locations.short/deep` split.

| Metric | What it is |
|---|---|
| `completionRate`, `attempts`, `interceptions` | Basic passing numbers. |
| `cpoe` | Completion % over expected: actual completion rate minus the rate the model expects for those throws. Measures QB accuracy (or pass defense). |
| `expectedCompletionRate` | The model's expected completion rate given depth and location. |
| `averageDepthOfTarget` | Average air yards per attempt. Shows how aggressive the passing game is. |
| `averageYardsAfterCatch` | Yards after the catch per completion. |
| `ppa`, `successRate`, `explosiveness` | The same efficiency metrics as section 1, for passes only. |
| `*AttemptsAvailable` | How many attempts had that data point charted. Check this before trusting a rate based on a small sample. |

## 4. EPA (PPA) breakdowns

| Endpoint | Metrics |
|---|---|
| `/ppa/games` | Per team per game: `offense`/`defense` × `overall`, `passing`, `rushing`, `firstDown`, `secondDown`, `thirdDown`. Average EPA per play. Supports `excludeGarbageTime`. |
| `/ppa/teams` | The same breakdown for a whole season (`cumulative` sums and per-play averages). |
| `/ppa/players/games`, `/ppa/players/season` | Player `averagePPA` and `totalPPA` split into `all`, `pass`, `rush`, by down, and standard vs. passing downs. |
| `/ppa/predicted` | Expected-points value for a given down and distance at each yard line. This is the EP curve that EPA is built from. |
| `/metrics/fg/ep` | Expected points of a field goal attempt by distance. |

## 5. Havoc

`/stats/game/havoc` (per game) and the `havoc` block in season advanced stats.

| Metric | What it is |
|---|---|
| `havocRate` | Havoc events (TFL, forced fumble, INT, pass breakup) per play. A defensive disruption measure that predicts turnovers. |
| `frontSevenHavocRate` / `dbHavocRate` | The same, split by defensive line/linebackers vs. defensive backs. |
| `totalHavocEvents`, `totalPlays` | The raw counts behind the rates. |

## 6. Special teams

| Endpoint | Metrics |
|---|---|
| `/punting/teams/games`, `/punting/teams/season` | `punting.*` (your punts) and `returning.*` (opponent punts you returned): `yardsPerPunt`, `netYardsPerPunt`, `inside20`, `touchbacks`, `fairCatches`, `blocked`, `yardsPerReturn`, `returnTouchdowns`, `muffs`. Covers field-position swings from punts. |
| `/metrics/fg/ep` | Expected points of field goals by distance (see section 4). |
| SP+ `specialTeams.rating` | One overall special-teams rating (see section 8). |

## 7. Pace, drives and play-by-play (raw data)

| Endpoint | Metrics |
|---|---|
| `/drives` | One row per drive: start/end yard line, `plays`, `yards`, `elapsed` time, `driveResult`, score before/after. Use to build pace (seconds per play), points per drive, and red-zone rates. |
| `/plays` | One row per play: down, distance, `yardsToGoal`, `yardsGained`, `playType`, `ppa`, score, clock, timeouts. The rawest data; everything above can be rebuilt from it. Big (one call per week). |
| `/plays/stats` | Which player was involved in each play (passer, rusher, tackler...). Max 2,000 rows per call. |

## 8. Team ratings (outside power ratings)

Good as priors and as benchmarks to compare our model against. Each is one row per team per season unless noted.

| Endpoint | Metrics |
|---|---|
| `/ratings/sp` (**cached**) | Bill Connelly's SP+. `rating` (points better than an average team), `offense.rating`, `defense.rating`, `specialTeams.rating`, plus sub-ratings (`success`, `explosiveness`, `rushing`, `passing`, standard/passing downs, `pace`, `runRate`), `sos`, `secondOrderWins`. |
| `/ratings/srs` | Simple Rating System: average scoring margin adjusted for schedule. Basic but easy to understand. (`/ratings/srs/expanded` also includes FCS.) |
| `/ratings/elo` | Elo rating that updates after each game from the result. `week` lets you get it as of any point in the season. |
| `/ratings/fpi` | ESPN's Football Power Index: `fpi`, `efficiencies.offense/defense/specialTeams`, and résumé ranks (strength of record, SOS, game control). |
| `/ratings/core` | CFBD's own CORE opponent-adjusted efficiency rating: `overall`, `offense`, `defense`, with `throughWeek` so you can get it as of a given week. |
| `/games` (**cached**) | Each game carries `homePregameElo`/`awayPregameElo` and `homePostgameWinProbability`. |

## 9. Preseason priors / roster strength

| Endpoint | Metrics |
|---|---|
| `/player/returning` (**cached**) | Returning production: `percentPPA` (share of last season's EPA that is back), split into passing/rushing/receiving, plus `usage` versions. A key preseason input. |
| `/talent` (**cached**) | 247Sports Team Talent Composite: a weighted rating of the whole roster's recruiting stars. |
| `/recruiting/teams` (**cached**) | Team recruiting class `rank` and `points` for one signing class. |
| `/recruiting/groups` | Average recruit rating by position group (QB, OL, DB...) across classes. |
| `/recruiting/players` | Individual recruits: stars, rating, ranking, position, school. |
| `/player/portal` (**cached**) | Transfer portal entries: origin, destination, position, rating, eligibility. |
| `/player/usage` | Share of team plays each player was involved in, overall and by down/pass/rush. Helps estimate how much an injury matters. |
| `/coaches` (**cached**), `/coaches/tenures`, `/coaches/seasons` | Head coach by team and season, with records. Use to flag coaching changes. |
| `/roster` | Roster by team and season (position, class year, height/weight). |

## 10. Betting markets and results

| Endpoint | Metrics |
|---|---|
| `/lines` (**cached**) | Per game per sportsbook: `spread`, `spreadOpen`, `overUnder`, `overUnderOpen`, `homeMoneyline`, `awayMoneyline`, plus the final score. The source for market lines and closing line value. Opening lines are missing for some books and older games. |
| `/metrics/wp/pregame` | CFBD's pregame `homeWinProbability` and the `spread` it is based on. |
| `/teams/ats` | Against-the-spread record per team per season: `atsWins`, `atsLosses`, `atsPushes`, `avgCoverMargin`. |
| `/metrics/wp` | Win probability after every play of one game. |

## 11. Traditional box score

| Endpoint | Metrics |
|---|---|
| `/games/teams` | Team box score per game as `category`/`stat` string pairs (first downs, total yards, 3rd/4th-down efficiency, turnovers, penalties, time of possession...). The spec doesn't list the category names, so read them from a cached response. |
| `/stats/season` | The same kind of totals per team per season as `statName`/`statValue` rows. `/stats/categories` lists the names. |
| `/games/players`, `/stats/player/season` | Player box score stats by game or by season. |
| `/game/box/advanced` | Full advanced box score for one game (team and player PPA, success rate, havoc, field position, win probability). One call per game, so too expensive for bulk pulls. |
| `/records` | Win/loss records by season: overall, home, away, conference, postseason. |

## 12. Schedule and reference data (not metrics)

`/games`, `/games/schedule`, `/calendar`, `/games/media` (TV network), `/teams`, `/teams/fbs`,
`/conferences*`, `/venues` (location, elevation, dome/grass), `/rankings` (AP/Coaches/CFP polls),
`/playoffs/cfp*`, `/teams/matchup` (head-to-head history), `/draft/*` (NFL draft picks),
`/plays/types`, `/plays/stats/types`, `/info` (remaining calls, which itself costs a call),
`/info/usage`.
