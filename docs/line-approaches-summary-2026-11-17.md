# How we've tried to get the best possible lines: CFB and NFL, to 2026-11-17

A single overview of every approach taken so far to build our own college and NFL lines, judge them and look for
betting value. It summarises `CLAUDE.md`, `docs/model-tests.md`, `docs/audit-2026-11-16.md`,
`docs/nfl-audit-2026-11-16.md` and `docs/edge-plan-2026-11-16.md`, which remain the detailed record. If this file
and those disagree, those win.

**Contents:** 1. Ground rules · 2. College model history · 3. College tests · 4. College evaluation fixes and
market-side work · 5. College: where things stand · 6. NFL model history · 7. NFL tests · 8. NFL line data and the
opener tests · 9. NFL exploratory ideas · 10. Lessons across both leagues · 11. Open items and dates

---

## 1. Ground rules (apply to both leagues)

### What "best line" means here
- **Our own independent number, not a copy of the market.** Market lines are never model inputs or features and are
  never blended into predictions. They are used only to judge the model and to display beside it.
- A bet-selection layer that uses market data (movement, book spreads) was allowed on 2026-11-16, **kept separate**
  from the rating model. It has not been built yet.
- One model per league predicts **each team's points**, so one model gives both numbers:
  line = home − away, total = home + away.

### How a model is judged
- **Walk-forward only.** A week-W prediction uses games before week W plus preseason priors; each season's points
  model is trained only on earlier seasons. 2020 (COVID) is never evaluated.
- **Measures:** spread and total MAE vs the closing line; ATS at 3+ and 5+ gaps at the open and the close; CLV
  (direction *and* points); and, since 2026-11-13, the **slope**: regress (result − line) on (our line − line) over
  all games. 0 = we add nothing beyond the line; 0.10 = a 6-pt disagreement is worth ~0.6 pts our way.
- **Statistics with every result:** n, SE = √(p(1−p)/n), 95% interval ±1.96 SE. Break-even at −110 is 52.4%.
  One college season of 3+ picks ≈ ±4.7 pts; pooled 2021–25 ≈ ±2.1. Telling 53.4% from 52.4% takes ≈ 9,600 picks
  to measure and ≈ 19,600 for 80% power, which is why the slope (uses every game, paired between models) became
  the main test.

### Acceptance rules (written before each test, never loosened after)
| Rule | Used for | Pass condition |
|---|---|---|
| **A** | College Tests 4–5 | ATS 3+ at open up pooled, ≥ baseline in 4 of 5 seasons, CLV % not down > 1 pp, spread MAE not worse |
| **B** | College Test 6 on (approved 2026-11-13) | Paired Δslope at the open ≥ 1.645 paired SE (bootstrap of 2,000), plus supporting checks (ATS, CLV %, CLV pts, MAE) |
| **B, amended 2026-11-16** | Every test registered from that date | Bar raised to **2.24 paired SE**; "the open" = **Bovada's** `spread_open`; a pass only earns a frozen-holdout candidacy |
| **Accuracy adoption** | Changes that improve MAE but can't show edge | MAE better pooled and in ≥ 4 of 5 seasons, no harm to betting measures; labelled "accuracy", never quoted as edge |
| **NFL accuracy rule** | All NFL model tests | Spread MAE better pooled and in ≥ 4 of 5 seasons, slope at the close not down > 1 paired SE, total MAE not worse (+ a 2026 check on some tests) |
| **C (proposed, not approved)** | Future model changes | Paired change in *line-move* slope ≥ 2.24 SE, result slope not negative, slope left at the close not up > 2 SE, MAE not worse |

### Holdouts and multiple testing
- About 45 variants have been tried across both leagues. 2026 college data is **used up** for the tier rule, Rounds
  2–4 and Tests 1–2. Clean evidence from here: `pick_log` since 2026-11-12 and the 2027 season with frozen models.

---

## 2. College model history (v1 → v5)

| Version | Date | What changed | Spread miss 2018–25 | Slope at open 2021–25 |
|---|---|---|---|---|
| v1 | 2026-11-11 | Opponent-adjusted ridge ratings on per-play metrics (EPA/play pass and rush, success rate, explosiveness, plays, points; garbage time excluded; FCS grouped/down-weighted) + linear per-team points model; last season's games faded in | – | +0.049 ± 0.042 |
| v2 | 2026-11-11 | Preseason features: talent, returning production, new head coach, faded linearly over 16 weeks | – | – |
| v3 | 2026-11-11 | Bug fix: a week counts as "played" only once its last game kicks off (commit 70f6be1) | 12.88 | +0.057 ± 0.050 |
| v4 | 2026-11-12 | **Recency weighting** (half-life 4 weeks; last season's games treated as 8+ weeks old, weight 0.25 × fade over 6 weeks), ridge α = 1. Chosen over 7 variants; gradient boosting worse in all | 12.87 | +0.095 ± 0.047 |
| **v5 (live)** | 2026-11-12 | + **mid-season head-coach change** feature (`coach_change`, `opp_coach_change`), regular season only; adopted for accuracy | 12.86 | **+0.104 ± 0.048** |

- The single biggest gain in edge came from recency weighting (v3 → v4, +0.04 slope).
- v5 coach change: learned effect ≈ −1.9 pts scored, +2.2 allowed (≈ −4 margin). Bias on affected teams went from
  −3.3 (v4) to +0.4. 2026 changes must be entered by hand in `coach_changes` (CFBD fills `/coaches` after the season).
- **Overrides** (manual "QB out, −N pts" etc.) are applied before predictions. QB-change and skill-player research
  provides *suggested* override sizes (≈ 1 pt + 3.7 pts per +1.0 team pass EPA lost for a backup QB).

### v5 backtest headline (3+ gaps)
| | 2018–25 at close | 2021–25 at open (mixed books) | 2021–25 at **Bovada** open |
|---|---|---|---|
| ATS | 50.8% (n=3,148) | 52.4% (1,134–1,030) | 52.39% (1,097–997) |
| Slope | +0.015 ± 0.037 | +0.104 ± 0.048 | +0.113 ± 0.047 |
| CLV | – | 61.1%, 0.61 pts | 0.56 pts (Bovada open → Bovada close) |

Spread miss 2021–25: ours 12.83 vs close ≈ 11.5–12.5 depending on sample; total miss ours 13.12 vs close 12.59.
**Totals have never beaten the market** (O/U 3+ at close 49.6%); they are shown as information only.

---

## 3. College tests, in order

| # | Idea | Verdict | Key numbers |
|---|---|---|---|
| R1 | QB change detected from box scores (2 variants) | Rejected | Miss unchanged 12.87; market already knows last week's starter. Kept for override sizes |
| R1 | Weather (Open-Meteo, 5,843 games) | Not in model; page flag | Total miss 13.006 → 12.996; only extremes look interesting (gusts 30+ under 57.8%, n=205) |
| v4 | Recency weighting | **Adopted** | see §2 |
| R2 | Weight recent seasons in the points model | Rejected | Slightly more accurate, ATS at open and CLV worse |
| R2 | Current-season bias correction (spread/total) | Rejected | No ATS gain, CLV down, totals worse |
| R3 | Last season's SP+ as a faded prior | Rejected | Best total gain yet (13.111 → 13.044) but ATS open 51.9 → 50.0, CLV down: we agree with the market more |
| R3 | Transfer portal | Rejected | ~0.1 pt/SD, noise |
| R3 | Schedule spots (bye, short week, travel, time zones) | Rejected | Short week ≈ −3.9 pts but priced in; ATS/CLV worse |
| R4 | Drive metrics (points per opportunity, opportunity rate, field position) | Rejected | Spread 12.860 → 12.847, ATS flat, down in 4 of 6 seasons; EPA already contains it |
| R5/v5 | Mid-season head-coach change | **Adopted (accuracy)** | Spread 12.870 → 12.859, affected 3+ picks 55.1 → 57.3% (n≈105) |
| Review | Outside review | Findings | Our miss SD 16.3 vs market 15.5; naive N(gap, σ) cover probabilities are wrong for us; gaps still 3+ at close won 50.3% (−4.0% ROI) → bet early |
| T1 | Weeknight MAC/SBC/C-USA games, 3+ at open | Kept as hypothesis | Discovery 62.7% ± 8.7; holdout 2026 11–9 (±21.8). Tag and track |
| T1 | FCS opponents | Rejected | 2026 holdout 45.1% |
| T2 | Weight last season's games by returning production | Rejected | Weeks 0–5 miss moved ≤ 0.006 (Test 3 skipped as its precondition failed) |
| T4 | Coach career record vs our line (K=100) | Rejected under Rule A | ATS 52.40 → 52.86%, only 3 of 5 seasons; but Δslope +0.026 ± 0.009 (2.9 SE), MAE better all 5 seasons → **holdout candidate** |
| T4 | Team vs same opponent; coach vs coach | Rejected | Worse on every measure |
| T5 | Fumble-recovery luck (sportsdataverse PBP) | Rejected | Wrong-signed, tiny coefficients |
| T6-A | Combined: v5 + coach career + drive metrics (ridge) | Passed Rule B, **not adopted** | Δslope +0.044 ± 0.021 (2.1 SE), ATS open 53.38%; biased upward (candidates picked on the same data) |
| T6-B | Leave-one-out | Info | Coach career carries it; drive metrics add nothing |
| T6-C | Select on 2021–23, confirm on 2024–25 | Failed | 1.80 SE vs 1.96 bar |
| T7 | Weather for totals (historical forecasts) | Rejected | Total slope Δ +0.014 ± 0.015 (0.97 SE) |
| C | Per-metric ridge shrinkage | Rejected | Δslope −0.36 SE, MAE worse all 5 seasons, CLV −3.5 SE |
| F | DraftKings lookahead line (ratings one week staler) | **Supported** (track only) | Slope at DK open +0.175 ± 0.063 (2.77 SE); Bovada open later moved +0.73 pts toward us. Track lookahead picks in 2027, no betting on it alone |

**Don't retry without new information:** QB-change detection, recent-season weighting, bias correction, SP+ priors,
portal, schedule spots, drive metrics, returning-production weighting, head-to-head, fumble luck, weather for totals,
per-metric shrinkage.

**Ideas not yet tested:** win-probability garbage-time filter (PBP), CPOE/passing detail, moneyline/win probability,
comparison with outside ratings, the unused cached college stats (line yards, stuff rate, down splits, etc.).

---

## 4. College evaluation fixes and market-side work

The model was not the only lever. A lot of the work was making sure we grade against a line that could actually be
bet, and getting the best number once we have a pick.

### Getting the "open" right (audit 2026-11-16)
- CFBD's `spreadOpen` means different things per book. **Bovada's** is a true Sunday-evening opener; **DraftKings'**
  (and partly ESPN Bet's) is a lookahead line posted before the previous week's games. v5 "won" 55.4% against
  DraftKings' open: an artifact.
- Fix: "the open" = Bovada `spread_open`, with Bovada's own close for CLV (view `018_bovada_open.sql`,
  `UPCOMING_SQL`, `PREDICTIONS_SQL`, `OPEN_RESULTS_SQL`). "Best open 53.4%" was dropped as un-bettable.
- `PICK_RATES_SQL` grades Play/Pass at the Bovada open; `pick_results` "first" = the pick **at bet time** (4+ books,
  8+ h after both teams' previous kickoff, `019_pick_bet_time.sql`), so lookahead picks are not graded as real ones.

### Live market data
- **The Odds API** snapshots of 9 US books: market "now" = median (`market_now` view); best number and price per
  pick recorded in `pick_log`; line-shopping table on the Results page.
- Findings from the first snapshots (127 games, 4 days): the best book is on average **0.39 pts** better than the
  median; 0.5+ better 56% of the time. Most often off the median: BetRivers, FanDuel, Bovada. Lowest vig: LowVig
  (2.9%), BetMGM 4.3%.
- Arithmetic: model-anticipated move (0.56 pts) + best number (0.39) ≈ 0.95 pts ≈ 52.7%. Thin, but the first
  positive estimate.

### Pick tiers (live, `cfb/picks.py make_pick()`)
| Tier | Rule |
|---|---|
| Play | 3+ pts off the current median line, and the line hasn't moved 0.5+ against us since the open |
| Caution | 3+ off but the line has moved 0.5+ the other way |
| Pass | under 3 off |
| Check news (flag) | 5+ off: look for injury/QB news, enter an override |
| Totals | info only |

Betting practice: bet Sunday openers; treat a gap still 3+ at kickoff as a warning (2026: 44.4% at close).

### Line-movement analysis (edge plan, 2026-11-16)
- **The model predicts line movement far more clearly than results:** line-move slope (close − open on our gap)
  +0.096 ± 0.017 (5.6 SE, positive all 5 seasons) vs result slope +0.113 ± 0.047 (2.4 SE). Slope left at the close
  ≈ 0. Our edge is that the opener moves toward our number.
- By gap size the line moves our way +0.36 (3–5), +0.58 (5–7), +0.73 (7–10), +1.03 (10+).
- Hindsight split of 3+ picks: line moved 1+ our way afterwards → 57.2%; less than 1 → 51.7%; 1+ against → 45.2%.
  Knowing which gaps the market will agree with is worth more than any rating tweak.
- Season phase (hypothesis): weeks-played 0–4 went 47.6–49.9%, 5+ went 54.1% (slope +0.21). Power-conference
  games show higher slopes but the same win rate (weak).

### Data/news sources checked for the "news gap"
- Injuries: no usable free or cheap college feed (CFBD none; ESPN none, all 138 FBS teams checked; SportsDataIO
  paid only; API-Sports empty for CFB). Power 4 availability reports exist as web pages → overrides page flags only.
- Weather: ESPN forecast + Open-Meteo history; kept as a page flag and a forecast log.

---

## 5. College: where things stand

- **Verdict (audit):** v5 knows something the Sunday opener doesn't (slope +0.11 ± 0.05 at Bovada), worth about
  0.6 pts per pick ≈ 52.4%, i.e. break-even at −110 as a whole-season system. ~37 variants moved it by hundredths.
- **2026 so far (v5 = v4, trained ≤ 2025, through Nov 12):** ATS 3+ at open 50.1%, at close 44.4%; CLV 65%,
  +0.77 pts. The market moves toward us but only part way.
- **What's left is mostly timing and price** (Sunday openers, best of nine books, maybe weeks 5+ only) and news via
  overrides, not another feature. Realistic 2027 expectation betting openers at the best number from week 6: 52–54%,
  one-season range about ±6.

---

## 6. NFL model history (nfl-v1 → nfl-v3)

Data: ESPN live scores and team list; nflverse schedules (with closing line), play-by-play → `team_game_stats`
(EPA-based success, win-probability garbage time, so never mixed with college metrics), starters, rosters, injuries,
snap counts. Backfill 2016–2025 in the DB (`python -m cfb.nflverse`); 1999+ used in memory only for research.

| Version | Date | What changed | Key numbers (2021–25 unless noted) |
|---|---|---|---|
| nfl-v1 | 2026-11-16 | College structure: opponent-adjusted ridge ratings on 7 metrics + per-team points model + home. Settings chosen on 2017–19 only from a 36-combination grid: **half-life 6, last-season weight 0.5, fade over 12 weeks** | Spread miss 10.22 vs close 9.76; slope at close −0.09 ± 0.09; **line too flat** (SD 4.0 vs 6.1) |
| nfl-v2 | 2026-11-16 | + **starting-QB adjustment** (T-QB): starter's shrunk EPA/dropback above replacement minus the QBs behind the team's current ratings, for both sides | 10.22 → 10.14 (4 of 5 seasons), SD 4.0 → 4.8; 26 pts per 1.0 EPA/dropback |
| **nfl-v3 (live)** | 2026-11-16 | + **full matchup rows** (team's own defense and opponent's offense ratings) | 10.088, calibration 0.92, SD 6.01 (close 6.07); 2006–16 clean check: calibration 1.234 → 0.994 (3.6 SE) |

Live: worker job `nfl_daily_update` at 6:30 AM MT (nflverse refresh + `predict_upcoming`); NFL tab on the predictions
page; NFL odds snapshots from 2026-11-16 (`odds.save_snapshot('nfl')`). All adoptions are **accuracy and calibration
only, never edge**.

---

## 7. NFL tests, in order

| Test | Idea | Verdict | Key numbers |
|---|---|---|---|
| R1/R2 | Player data research (nflverse) | Info | 80–84% of absences flagged before game day; RB/WR/TE efficiency barely repeats (r 0.10–0.16), QB EPA/dropback r 0.36; usage repeats |
| Grid | nfl-v1 settings on 2017–19 | Chosen | All 36 within 10.460–10.530; choice matters little |
| T-QB | Starting-QB adjustment | **Passed** → nfl-v2 | see §6; but 93% of the gain is in games where the starter changed (kickoff knowledge) |
| T-skill | RB/WR/TE absences | Rejected | 10.14 → 10.25; an absence costs ≈ 0.6 × the player's own EPA/game for 3 games, then 0 → override sizes only |
| T-CAL | Stretch the spread by a learned k | Rejected | k came out 0.92–1.04 (< 1); flatness isn't stable over time |
| Cause look | Why the line is flat | Info | Flat even in-sample (1.16–1.37): each row saw only half the matchup; too steep early, too flat late |
| T-MATCH | Full matchup rows (on 2021–25) | Rejected on season count (3 of 5) | 10.141 → 10.088, calibration 1.14 → 0.92: diagnosis confirmed |
| T-WEEK | Rating weights that change with weeks played | Rejected | 10.141 → 10.178; uncentred interactions nearly collinear (r ≈ 0.99) |
| T-HIST | nfl-v2 on 2006–16 (trained from 1999) | Replication | Miss 10.737 vs close 10.557, calibration 1.23, 88% underdog picks; flatness is structural. 2006–16 become the clean judging seasons |
| T-MATCH clean | Same as T-MATCH, judged once on 2006–16 | **Passed** → nfl-v3 | Calibration 1.234 → 0.994, miss 10.737 → 10.730, 3+ picks on underdogs 88% → 67% |
| T-QB2 | QB value from full careers + draft prior | Rejected | 10.268 → 10.268 on 2011–25; the simple adjustment already captures it |
| T-OPEN | nfl-v3 at the Monday 8 AM ET line | **Supported by the rule, no betting value** | Line moved toward us +0.388 ± 0.073 (5.3 SE, all 7 seasons) but slope at Monday +0.04 ± 0.10, ATS 3+ 50.0% |
| T-OPEN-B | Is that move just Monday-line noise? (market-implied benchmark B1) | **Supported** | Our gap still predicts the move with B1 in the regression (a = +0.087 ± 0.014, 6.1 SE); B1's own move only +0.10. Still no link to results |

**NFL audit findings (2026-11-16):** no lookahead in the walk-forward; no bettable NFL line in nflverse (one number,
no opener/time/book, source changes 2023 and 2025); nfl-v2's 3+ "Plays" were mostly underdog picks from the flat line
(50.9% vs 51.0% for every underdog blind); playoff week numbering clash ESPN 1–5 vs nflverse 19–22 (fixed:
`espn.schedule_week()`); nflverse lists the wrong starter in 54 team-games; injury files hold only the Friday report.
Key numbers: 3 = 14.7% of margins, 7 = 8.5%; +3.5 instead of +3 ≈ 5 pts of win rate, more than the whole college edge.

---

## 8. NFL line data and the opener tests

Because nflverse only gives roughly the close, a large part of the NFL work was finding lines we could have bet.

- **Loaded into `nfl_line_moves` (evaluation only, 2026-11-17):**
  - `picksfootball` (user's hand copy, personal use only): 2023–26 incl. playoffs, 1,005 games, snapshots open,
    Mon–Sat, gameday. **Monday = the usable opener**; their "open" is a lookahead line.
  - `sbro` (user's copy): 2016–21 open/close, 1,622 games; its open is mostly a lookahead line; 2021 closes suspect.
- **In `reference/`, not loaded:** TeamRankings consensus `line_history.csv` (timestamped, 2018–22), SuperContest
  lines (2013–20), per-book opens 2023–26 (untimed), aussportsbetting `nfl.csv`, spreadspoke closes 1966–2025.
- Clean Monday-line window: 2018–22 (line_history) + 2023– (picksfootball).
- **T-OPEN / T-OPEN-B result:** nfl-v3 anticipates where the NFL market goes during the week (about 9% of its gap)
  and that is not Monday-line noise, but it has not been shown to turn into wins at the Monday price. Most of the
  lookahead model's apparent value (+0.67 move, 53% ATS) is QB news learned during the week; with a no-lookahead
  starter rule it shrinks to +0.39 and 50%.
- **Agreed consequence:** build NFL **paper-tracking** at the live Monday 6 AM MT snapshot for 2027, under the college
  stopping rule. No real NFL bets until that record exists.
- **Still parked:** T-LOOK (needs timed lookahead lines: The Odds API history, paid, $30–59/month; ask first).

---

## 9. NFL exploratory ideas (hypotheses only)

- **Teasers through 3 and 7** (no model): 6-pt underdog legs +1.5 to +2.5 won 77.6% ± 3.7 (2015–25); favourites −7.5
  to −8.5 73.4%. Break-even per leg 72.4% at −110, 75.2% at −130. Depends entirely on the price offered; needs a log
  of offered prices first.
- **Situations (1999–2025 closes):** division underdogs 52.0% ± 1.9, not steady by era (parked); late-season bad vs
  good team 47.6% ± 4.6 (worth a pre-registered standings-based test later); final-week non-usual QB 43.4% ± 7.5
  (covered by T-QB); head-to-head barely carries forward (parked). The Bills–Patriots pattern was the Patriots.

---

## 10. Lessons across both leagues

1. **Information the market already uses makes us more accurate and removes edge.** SP+, schedule spots, last week's
   starter, the QB adjustment: they move our line toward the market.
2. **Our edge, where it exists, is at the opener, not the close,** and it shows up as **line movement toward our
   number** (college +0.56 pts on 3+ gaps, NFL +0.39). Slopes at the close are ≈ 0 in both leagues.
3. **That movement alone doesn't beat −110.** It's worth ~51.6–52.4% in college and hasn't shown up in NFL results.
   What could tip it: best number across books (+0.39 college), the hook on 3 and 7 (NFL), timing (Sunday openers,
   maybe weeks 5+), and lookahead lines (college Test F).
4. **Grade against a line you could have bet.** The mixed "open" (DraftKings lookahead) and nflverse's untimed number
   both flattered the models; fixing them was worth more than any feature.
5. **Win rate is a blunt instrument.** The paired slope, and now the line-move slope, separate models in a season or
   two; win rate needs decades.
6. **The gap to the close is mostly news** (injuries, QB changes). We won't be faster than the market; overrides and
   the Check news flag stop bad bets rather than create good ones.
7. **Process:** write the rule before the test, use one judging run, no variants after results, raise the bar when
   testing several things, keep 2027 frozen and clean. Check data before multi-call pulls (CFBD conference
   abbreviations; ~90 calls once wasted).

---

## 11. Open items and dates

| When | What |
|---|---|
| **On/after 2026-12-07** | Holdout **5A**: v5 + coach career as a learned feature, 2026 at the Bovada open, bar 2.24 SE (expected outcome: "Consistent" → track in 2027) |
| 2026-12-07 | **Test B** (no bets before weeks-played 5) and **Holdout T** (conference tier), 2026 through Dec 6 |
| Not run (needs approval) | Edge plan Step 1 (re-score versions on line-move slope, Rule C), Step 2 **Test L** (does the opener overreact to last week's luck?) |
| Before 2027 week 0 | Bet log (actual bets, prices, books); NFL Monday paper-tracking; college lookahead-pick tracking (Test F) |
| After 2027 | Apply stopping rule 5C (continue / scale back / stop) on slope, CLV points, ATS at open and real ROI |
| Each August | Backfill the new college season; `load_coach_changes` with the new `last_season`; check the first NFL snapshot and nflverse load |
| Decision pending | The Odds API history purchase (timed lines for the bet-selection layer and NFL T-LOOK) |
