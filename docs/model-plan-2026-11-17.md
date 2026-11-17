# Model test plan, round 1 (2026-11-17): DRAFT, not approved, nothing run

Stage 1 was six diagnostics (D1–D6) that judge nothing; their results are in section 1. Section 2 is the plan,
with every rule written before any judged run. **No judged test has been run.** All research runs in scratch
(`dx/dx.py`, session 2026-11-17). 0 CFBD calls (scripts run with `CFBD_API` unset), 0 paid calls.

---

## 1. Diagnostics (information only)

### D1. College calibration (stored v5 backtest)
Calibration = slope of the result (away − home) on our predicted margin. 1.00 = right size; above 1 = our line is
too flat (the real margins are wider than ours); below 1 = too steep.

| Games | Calibration (ours) | Calibration (Bovada close) | SD ours | SD close |
|---|---|---|---|---|
| 2021–25, all v5 games | 0.992 ± 0.017 (n = 4,455) | 0.999 ± 0.016 | 13.65* | 14.58* |
| Weeks played 0–4 | **0.944 ± 0.022** (n = 1,821) | 0.995 ± 0.023 | 17.56 | 16.90 |
| Weeks played 5+ | **1.061 ± 0.028** (n = 2,634) | 1.000 ± 0.026 | 11.07 | 12.16 |
| FBS vs FBS only | 1.000 ± 0.021 (n = 3,929) | – | 12.24 | 13.34 |

\* games with a Bovada open and close (n = 4,169). By season: 0.95 to 1.07, no trend.

- **Same pattern as nfl-v1, much smaller:** too steep early, too flat late. NFL was 1.16–1.37 even in-sample.
- **Where it matters:** the flat part (weeks 5+) is where the edge lives (result slope at the open +0.210 ± 0.071
  in weeks 5+ vs +0.003 ± 0.067 in weeks 0–4).
- **Row structure:** the college points model has the nfl-v1 flaw. Each row is one team: its offense ratings (7),
  the opponent's defense ratings (7), home, two FCS flags, coach change ×2, and preseason inputs ×6. The team's
  own defense and the opponent's offense never enter that row. They enter only the other row of the same game.
  `cfb/model.py side_row()`:
  ```
  row = {team, opponent, home, fcs_offense, fcs_defense, points,
         off_<m> = rating[team, off_m], oppdef_<m> = rating[opponent, def_m]}   # for the 7 METRICS
  ```

### D2. Rating dynamics
**Setup.** v5's ratings rebuilt in memory. They match the app's `ratings_as_of` exactly for 133 FBS teams; the 5
2023 transition teams differ only by the FCS adjustment. Seasons: 2017–19 and 2021–23. 2024–25 were left out so
that any later selection stays clean.

**(i) How fast ratings move.** Median over weeks 3–12 of SD(week-to-week change) / SD(rating level), FBS teams:
| | EPA/play | Success | Explosiveness | Pass EPA | Rush EPA | Plays | Points |
|---|---|---|---|---|---|---|---|
| Offense | 0.35 | 0.33 | 0.50 | 0.43 | 0.43 | 0.45 | 0.35 |
| Defense | 0.38 | 0.35 | 0.51 | 0.46 | 0.43 | 0.46 | 0.35 |

**(ii) Persistence.** Correlation between a team's rating from weeks 1–W and from weeks W+1 to the end, each season
on its own, equal weights:
| W | EPA/play | Success | Explosiveness | Pass EPA | Rush EPA | Plays | Points |
|---|---|---|---|---|---|---|---|
| 4 (off / def) | 0.52 / 0.50 | 0.57 / 0.55 | 0.23 / 0.21 | 0.34 / 0.30 | 0.34 / 0.38 | 0.24 / 0.28 | 0.53 / 0.51 |
| 8 (off / def) | 0.54 / 0.53 | 0.58 / 0.56 | 0.21 / 0.18 | 0.35 / 0.31 | 0.36 / 0.40 | 0.31 / 0.29 | 0.57 / 0.54 |

Success rate, EPA and points repeat about twice as well as explosiveness and plays. Pass and rush EPA are in between.

**(iii) Best in-season half-life by metric.** Change in plays-weighted error predicting each metric's *next* game,
against v5's half-life of 4 weeks (negative = better). Last season's weight was held at v5's value:
| Metric | Best, weeks played 0–4 | Best, weeks played 5+ |
|---|---|---|
| EPA/play | 2 (−0.2%) | 6 (−0.2%) |
| Success rate | 2 (−0.3%) | 6–8 (−0.3%) |
| Explosiveness | 2 (−0.8%) | 4 (0) |
| Pass EPA | 2 (−0.5%) | 4–6 (0) |
| Rush EPA | 2 (−0.5%) | 4 (0) |
| Plays | 2 (−1.0%) | 2 (−0.4%) |
| Points | 2 (−0.1%) | 8 (−0.5%) |

- **One half-life does fit them all, almost.** The best per-metric choice beats half-life 4 by at most 0.3–1.0% of
  next-game error. The stable metrics (success, EPA, points) would like a slightly longer memory late in the season,
  pace a shorter one.
- **This is the same ground as Test C** (per-metric shrinkage, rejected 2026-11-16). There, ratings predicted
  next-game metrics 1–9% better and the points model still got worse. Here the possible gain is smaller still.

### D3. Early-season prior
**What the ratings shrink toward today:**
- Ridge (α = 1) shrinks each team's offense and defense coefficients toward zero, i.e. toward the weighted league
  average of the games in the fit.
- The only team-specific prior inside the ratings is last season's games: weight 0.25 (0.5^(8/4)), fading linearly
  to 0 by 6 weeks played. There's no prior after week 6.
- Talent, returning production and new coach enter only the points model, faded over 16 weeks.

**How the ratings behave in weeks 0–5.** Mean over 2017–19 and 2021–25. "Prior" = week-0 ratings (last season's
games only). "Eventual" = that season's full regular season, equal weights. Shown: off EPA/play (def is within 0.03).
| Weeks played | corr(ours, prior) | corr(ours, eventual) | SD(ours) / SD(eventual) |
|---|---|---|---|
| 0 | 0.99 | 0.53 | 0.74 |
| 1 | 0.88 | 0.66 | 0.81 |
| 2 | 0.80 | 0.73 | 0.83 |
| 3 | 0.73 | 0.78 | 0.87 |
| 4 | 0.65 | 0.81 | 0.89 |
| 5 | 0.59 | 0.84 | 0.90 |

- The prior predicts the eventual rating only moderately: r = 0.51–0.58 for EPA, success and points, 0.21–0.28 for
  explosiveness.
- By weeks played 3, our ratings are already closer to the eventual rating than to the prior. Early ratings are
  compressed (SD 74–90% of the eventual spread).
- D1 shows the opposite at the line level: early lines are too *steep* (calibration 0.944). So the points model
  over-converts early ratings into points; the ratings themselves aren't over-confident. The likely cause is that it
  fits one set of coefficients for every week, which T-WEEK (NFL) tried to fix and couldn't.

### D4. Season drift (team-game averages, FBS-involved games)
| Season | Plays | EPA/play | Success | Pass EPA | Points | Totals bias, ours (v5) | Totals bias, close |
|---|---|---|---|---|---|---|---|
| 2018 | 63.4 | 0.110 | 0.428 | 0.172 | 28.7 | +0.70 ± 0.60 | – |
| 2019 | 62.5 | 0.113 | 0.427 | 0.178 | 28.0 | −0.85 ± 0.57 | +0.17 |
| 2021 | 60.7 | 0.153 | 0.424 | 0.234 | 27.6 | −0.18 ± 0.59 | −0.71 |
| 2022 | 60.4 | 0.110 | 0.419 | 0.221 | 27.4 | +0.68 ± 0.54 | −0.27 |
| 2023 | 59.5 | 0.118 | 0.419 | 0.234 | 26.8 | **+2.02 ± 0.54** | +1.22 |
| 2024 | 59.1 | 0.117 | 0.420 | 0.178 | 26.9 | +1.35 ± 0.55 | +1.39 |
| 2025 | 59.5 | 0.105 | 0.417 | 0.198 | 26.4 | +0.74 ± 0.52 | +0.30 |

- **What drifts:**
  - Plays fall 64.8 → 59.5, mostly with the 2023 clock rule.
  - Points per team-game fall 29.0 → 26.4.
  - Pass EPA jumps in 2021–23 (0.22–0.23), then returns to 0.18–0.20.
  - 2021's EPA/play (0.153) is an outlier.
- **FCS vs FCS (in the data from 2022):** levels are close to FBS-involved games (points 25.6–27.2, EPA/play 0.08–0.12).
- **Does it explain the totals bias?** Not clearly.
  - Across seasons, our totals bias doesn't track the scoring level (r = 0.01) or EPA/play (r = 0.12). Pass EPA is weak (r = 0.34, 8 seasons).
  - The market's total missed in the same direction in 2023–24 (+1.2, +1.4).
  - The 2026 live sample is 61 games (−3.6 ± 1.9). The "+2.08 in 2026" figure was v4 replayed on 685 games, a different sample.
- **Reading:** drift is real, but it isn't a bias that a season-centering fix would remove. It matches the earlier
  finding that dropped Test D (FCS-vs-FCS moves scoring ≤ 0.05 pts/team; a totals-only issue).

### D5. Data availability
- **Cached `/stats/game/advanced`:** these fields are filled for 100% of FBS-involved team-games in every season
  2016–2026, offense and defense:
  - line yards, stuff rate, power success, second-level and open-field yards
  - standard-down and passing-down success rate and explosiveness
  - rushing and passing success rate

  `havoc` is not in our cached responses (0%). FCS-vs-FCS games are in the files from 2022 (2,918–3,316 entries a
  season vs 1,714–1,774 before).
- **sportsdataverse play-by-play** (cached files, 2016–2026):

  | | 2016–20 | 2021 | 2022 | 2023–25 | 2026 |
  |---|---|---|---|---|---|
  | Covers our FBS games | 98–100% | 94.6% | 95.6% | 98–100% | 92.2% |
  | Kickoffs / punts / FG attempts per game | 11.0–11.3 / 8.9–10.2 / 3.0 | 11.2 / 9.1 / 3.1 | 10.9 / 9.1 / 3.0 | 10.7–10.9 / 8.4–8.8 / 3.0–3.1 | 10.7 / 8.4 / 3.1 |
  | Win probability (`wp_before`) and EPA on scrimmage plays | 100% | 100% | 100% | 100% | 100% |
  | Scrimmage fumbles per team-game | 1.04–1.12 | **0.66** | 0.87 | 0.83–0.92 | 0.95 |

  - Extra points are not separate rows (0–0.02 per game); they sit inside touchdown plays.
  - Fumble counts break in 2021 (−40%) and stay about 20% lower after, so any fumble-based input is unusable across
    that break.
  - Kicks, punts, field goals and win probability look consistent.

### D6. Rule C readiness
- **Edge-plan Step 1 has not been run or approved.** CLAUDE.md lists it as "Not run (needs approval)". Rule C's
  wording was amended on 2026-11-17: close = median of books.
- **What Step 1 needs** (0 new models, about 10 minutes):
  1. Stored v1, v3, v4, v5 backtests (in the database, 2018–25).
  2. Saved Test 6 rows (`t6_results.pkl`: base and combined).
  3. Score each on the line-move slope (Bovada open → median close of books) and the result slope (Bovada open),
     2021–25. Report paired differences from v5.
  4. **Sanity check (written 2026-11-16):** from v1 to v5 the two slopes must rise together. If they don't, Rule C is dropped.
- **This plan's main test:** Rule C if Step 1's sanity check holds, Rule B if it doesn't (section 2.1). Step 1 runs
  before any test in this plan and judges nothing.

---

## 2. The plan

### 2.1 Shared rules (fixed now)
- **Baseline:** v5 as stored, rebuilt in memory, and checked against the stored predictions (mean |diff| < 0.01 pts).
  Coach career (Holdout 5A, December 7) is not in any baseline or candidate. Nothing stacks on it.
- **Games:** 2021–25, FBS-involved, with a Bovada open and close (n ≈ 4,169). "The open" is the Bovada
  **reference open**: history has no bettable open (CLAUDE.md, 2026-11-17).
- **Main test, chosen by Step 1 before any candidate is scored:**
  - *Rule C* (if Step 1's sanity check holds). All four must hold:
    - paired Δ line-move slope (Bovada open → median close of books) ≥ the bar
    - paired Δ result slope at the open not negative
    - slope left at the close not up by more than 2 paired SE
    - spread MAE not worse
  - *Rule B* (otherwise). Paired Δ result slope at the Bovada open ≥ the bar, plus Rule B's supporting checks:
    - ATS 3+ not down more than 1.0 pp
    - CLV % not down more than 1.0 pp
    - CLV points not down more than 2 paired SE
    - spread MAE not worse
- **Bootstrap:** paired, 2,000 resamples of **season-weeks** (the audit's recommendation; games in a week share
  news and line moves). The game-level SE and a version with gaps clipped at ±10 are reported beside it, not judged.
- **Bar:** see 2.3.
- **A pass** earns a place in the frozen 2027 record (pre-registration 5C judges it). It is never adopted for betting on its own.
- **No variants after results.** If a test fails, its idea goes on the don't-retry list unless new information
  appears.

### 2.2 Tests

#### T1. College full matchup rows (port of nfl-v3's T-MATCH): **judged**
- **Why it could raise the slopes, not just accuracy:**
  - D1 shows the half-matchup flaw where the edge lives. Weeks played 5+ are too flat (calibration 1.061 ± 0.028,
    SD 11.1 vs the close's 12.2), and weeks 5+ carry all of the result slope (+0.21).
  - A line that is too flat understates exactly the disagreements that pay. Giving each row its own defense and the
    opponent's offense let the NFL model learn the matchup in-sample (calibration 1.23 → 0.99 on clean seasons).
- **What would make it accuracy-only:** the fix may mainly stretch lines we already agree with the market on, the
  big favourites. Then calibration improves and the slopes don't move.
- **Definition:** v5 + `MATCH_FEATURES` = `def_<m>` (the team's own defense rating) and `oppoff_<m>` (the
  opponent's offense rating) for the 7 METRICS, 14 new columns. Nothing else changes: same ratings, priors, coach
  change, LinearRegression points model, walk-forward training on seasons before S.
- **Data:** what v5 already uses. 0 calls.
- **Judged:** 2021–25, main rule (2.1) at the bar in 2.3.
- **Reported, not judged:**
  - calibration and line SD by weeks played 0–4 and 5+
  - share of 3+ picks on underdogs
  - by-season Δ of the main slope; flagged if negative in 3+ of 5 seasons
- **Effort:** small. The research version is a copy of the NFL T-MATCH script on college rows.

#### T2. Recency refinement: **not in round 1**
- **(a) Separate half-lives per metric:** D2 leaves almost no room. The best per-metric half-life improves
  next-game error by 0.3–1.0%, and the analogous per-metric shrinkage (Test C) made the points model worse while
  improving the metric predictions more than this. A judged slot spent here would mostly raise the bar for T1 and
  T4. **Recommend: don't run.**
- **(b) A rating that evolves week to week (state-space / Kalman):**
  - It's the principled answer to what D2 and D3 show: each metric has its own noise (explosiveness repeats at
    r ≈ 0.2, success at 0.57), and the right weight on the prior changes week by week.
  - But it's a new rating engine, a large build, and the audit expected accuracy rather than edge. It replaces the
    recency weighting that produced the one large edge gain (v3 → v4), so it can lose that too.
  - **Recommend: round 2, under the accuracy rule, only if T1 passes**, so it's built on the right row structure.
- If you still want one T2 in round 1, (a) can be run with half-lives fixed now from D2(iii), weeks played 5+:
  EPA 6, success 6, explosiveness 4, pass 4, rush 4, plays 2, points 8. That makes 3 judged tests (bar 2.13).

#### T3. Early-season prior: **dropped (repeats Test 3)**
- Shrinking toward each team's prior instead of the average *is* Test 3. It was skipped when Test 2's precondition
  failed (weeks 0–5 couldn't be moved), and it is on the don't-retry list. Round 3 (SP+ as a faded prior) showed the
  same thing from another side: a better prior makes us more accurate and more like the market.
- D3 adds no new information to change that. The prior itself predicts the eventual rating only at r ≈ 0.55, and the
  early-season miss is in the points model's conversion (D1: too steep), not in the ratings' starting point.
- **Fallback, as planned:** Test B (no bets before weeks played 5), graded December 7.

#### T4. One batch of unused cached stats: **judged**
- **Why it could raise the slopes:**
  - These measure the line of scrimmage and down-and-distance efficiency directly: line yards, stuff rate, power
    success, second-level and open-field yards, standard-down and passing-down success.
  - Openers react to scores and broad EPA. A team whose line wins every week but whose EPA is held down by short
    fields or turnovers is the kind of case the opener could misprice.
  - The ones that are mainly rushing-based may repeat better than explosiveness (D2) and add signal the ratings
    lack.
- **What would make it accuracy-only:** they overlap heavily with success rate and rush EPA. If the points model
  just redistributes weight among correlated inputs, MAE moves and the slopes don't (the drive metrics in Round 4
  and Test 6 did exactly this).
- **Definition (batch fixed now, all at once):** 8 metrics per team-game, offense and defense, from cached
  `/stats/game/advanced` (garbage time excluded):
  - `lineYards`, `stuffRate`, `powerSuccess`, `secondLevelYards`, `openFieldYards`
  - `standardDowns.successRate`, `passingDowns.successRate`, `passingDowns.ppa`

  Each is opponent-adjusted exactly like the current metrics (same `ratings_as_of` weights, α = 1, FCS flags) and
  enters as `off_<m>` and `oppdef_<m>` (16 columns). The points model stays LinearRegression, so the baseline is
  unchanged. Built in memory: no schema change for the test.
- **Data:** D5. Every field is filled for 100% of FBS-involved team-games 2016–2026. 0 calls.
- **Judged:** 2021–25, main rule at the bar in 2.3. Reported: the same items as T1, plus each metric's points-model
  coefficient (information only; no metric is dropped after results).
- **Effort:** medium (parse the cached JSON into team-game rows, extend the ratings loop).

#### T5. Special teams + win-probability garbage time (play-by-play): **round 2**
- **Two different things:**
  - *Special teams* is new information our ratings lack (only reachable through the points rating), but the market's
    numbers (SP+, FPI) include it. That points to accuracy, not edge.
  - *Win-probability garbage time* changes the inputs where our edge comes from, but it means rebuilding every metric
    from sportsdataverse EPA, a different EPA model from CFBD's. The two can't be mixed in one metric (CLAUDE.md).
    Play-by-play covers only 94.6–95.6% of our games in 2021–22 and 92% in 2026.
- **Recommend:** round 2, as two separate accuracy-rule tests, after T1 and T4.
  - Special-teams EPA per game (kickoffs, punts, field goals; extra points aren't separate rows) as one extra rated
    metric.
  - Win-probability garbage time as a full replacement input set, judged against v5.

#### T6. Season-centering / FCS-vs-FCS handling: **dropped**
- D4 shows real drift, but it doesn't line up with the totals bias (r = 0.01 with scoring level). The market missed
  the same way in 2023–24.
- It repeats Test D, which was dropped on 2026-11-16 for the same reason (a totals-only effect ≤ 0.05 pts/team from
  FCS-vs-FCS games). No new information.

#### NFL (separate count): QB-fault sack rate from FTN charting: **parked**
- **Data:** FTN charting covers only 2022–26. The NFL accuracy rule needs 5 judged seasons (2021–25) or the clean
  2006–16 seasons, so it can't be judged fairly.
- **Prior evidence:** T-QB2 (QB value from full careers) changed nothing, so QB refinements beyond the simple
  adjustment have little room. Revisit after 2027 adds a fifth FTN season.

### 2.3 Count, bar and order
- **Judged in round 1: T1 and T4** (2 tests). One-sided Bonferroni at a 5% family rate gives **bar = 1.96 paired SE**
  for each. If you add T2(a), it's 3 tests at **2.13**.
- **False-pass risk:** if neither change does anything, the chance at least one passes by luck is about 5% (2 tests
  at 2.5% each). In practice it's lower, because both are compared with the same v5 and share games.
- **Order:**
  1. Step 1 (information only): pick Rule C or Rule B by its sanity check, before any candidate is scored.
  2. T1.
  3. T4.
- **Dependence:** T1 and T4 are each judged against v5 alone, not stacked. T4's result doesn't depend on T1's.
- **If both pass:** v5 + T1 + T4 together is checked once for no harm (each supporting check, not a new judged test)
  before the 2027 freeze.
- **Coach career:** not in any round-1 model. If Holdout 5A is "Confirmed" on December 7, the 2027 frozen model is
  v5 + coach career + whatever passed. That stack gets the same no-harm check, never a new judged test. If 5A fails,
  coach career stays out.
- **What a pass earns:** a place in the frozen 2027 record, judged by 5C after the season. Never adoption for
  betting on its own.
- **Not run until you approve this plan.**

---

## 3. What the diagnostics change

1. **Early-season lines are over-confident, not just uninformed.** Weeks played 0–4 calibrate at 0.944 ± 0.022:
   our lines are about 6% too steep, while the ratings behind them are compressed (D3). Our early 3+ gaps are partly
   the model over-converting thin ratings into points. That backs Test B (skip weeks 0–4) as the betting rule, and
   is one more reason not to spend a test slot on early-season priors.
2. **Late-season lines are slightly too flat** (1.061 ± 0.028). A 3-point gap in weeks 5+ is "really" about 3.2
   points. This doesn't change the tier rule now; T1 is the test that would fix it properly.
3. **Recency is near its limit.** v4's half-life of 4 is within 1% of the best per-metric choice for predicting
   next-game metrics. The v3 → v4 gain came from moving off "all games equal", which is where most of the benefit
   is. More gains there would need a different rating engine (T2b), not new settings.
4. **Explosiveness and plays barely repeat** (r ≈ 0.2 half-season to half-season) but enter the model like the
   stable metrics. The points model's coefficients absorb that. Test C showed that forcing it at the rating level
   hurts, so no action.
5. **Fumble data is broken across 2021** (−40%, then about 20% low). Keep fumble-based ideas off the list (Test 5
   already rejected).
6. **Totals:** the bias years (2023–24) were years the market also ran low. No level fix is justified (T6 dropped).

---

## 4. Results (run 2026-11-17, approved by the user; scratch `plan1/`; nothing written to the DB; 0 calls)

### Step 1 (information only): Rule C's sanity check **passed** → Rule C was the main test
Line-move slope (Bovada open → median close of books) and result slope (Bovada open), 2021–25, n = 4,169:
| Version | Line-move slope | Result slope | Δ line-move vs v5 | Δ result vs v5 |
|---|---|---|---|---|
| v1 | 0.051 | 0.056 | −0.046 ± 0.007 | −0.057 ± 0.041 |
| v3 | 0.086 | 0.074 | −0.012 ± 0.004 | −0.039 ± 0.022 |
| v4 | 0.096 | 0.104 | −0.001 ± 0.001 | −0.009 ± 0.007 |
| v5 | 0.097 | 0.113 | – | – |
| Test 6 combined (v5 + coach career + drives) | 0.102 | 0.159 | +0.005 ± 0.003 | +0.046 ± 0.021 |

- **Sanity rule** (fixed before computing): v5 > v1 on both slopes, and Spearman rank correlation > 0 across v1, v3,
  v4, v5. Both held (rho = +1.00).
- SEs are a season-week bootstrap (2,000). v5's own SEs: line-move 0.024, result 0.052.

### Checks before judging
- **v5 rebuilt in memory** with the app's code: mean |diff| from stored v5 = 0.0025 pts (max 0.005, n = 6,727).
- **T4's copy of the ratings weighting** reproduces `ratings_as_of` exactly (max |diff| 0.0) on success rate.
- **Advanced-stats match:** 89% of team-games have all 8 new values. The missing ones are dropped from that metric's
  fit, as with NaNs; no column is missing after the rating step.

### T1: full matchup rows: **PASSED** (candidate for the frozen 2027 record)
| Rule C condition | Result | Pass |
|---|---|---|
| Δ line-move slope ≥ 1.96 paired SE | **+0.0084 ± 0.0031 (2.72 SE)**; 0.0973 → 0.1057 | yes |
| Δ result slope not negative | +0.0093 ± 0.0176; 0.113 → 0.122 | yes |
| Slope left at the close not up > 2 SE | +0.0009 ± 0.0174 | yes |
| Spread MAE not worse (n = 4,433) | 12.826 → 12.803 | yes |

Information only:
- Δ line-move slope by season: +0.013 / +0.003 / +0.005 / +0.010 / +0.008, **positive in all 5**. Game-level
  bootstrap SE 0.0023; gaps clipped at ±10: +0.0095.
- ATS 3+ at the open 52.41% → 52.43% (n = 2,093 → 2,020, ± 2.2). CLV on 3+ gaps 0.562 → 0.609 pts.
- Share of 3+ picks on underdogs 72% → 61%.
- Line SD 13.65 → 14.52 (close 14.57). Weeks played 5+: 10.64 → 11.82 (close 12.15).
- Calibration, weeks played 5+: 1.064 → **0.962** (now slightly steep). Weeks 0–4: 0.943 → **0.912** (steeper,
  i.e. worse).

**Reading.**
- The half-matchup flaw was real in college too. Fixing it lets the line spread out to the market's width, and the
  opener moves toward the new number a bit more. The gain is about 9% of v5's line-move slope, steady in every season.
- In points it is small: CLV +0.05 pts on 3+ gaps, ATS unchanged.
- The early-season lines get steeper still, which strengthens the case for Test B (no bets before weeks played 5).

### T4: cached-stats batch: **FAILED**
| Rule C condition | Result | Pass |
|---|---|---|
| Δ line-move slope ≥ 1.96 paired SE | **−0.0031 ± 0.0021 (−1.53 SE)**; 0.0973 → 0.0942 | **no** |
| Δ result slope not negative | +0.0336 ± 0.0095 | yes |
| Slope left at the close not up > 2 SE | **+0.0377 ± 0.0095 (4.0 SE)** | **no** |
| Spread MAE not worse | 12.826 → 12.812 | yes |

Information only:
- Δ line-move by season: −0.007 / +0.002 / −0.009 / −0.002 / +0.002, negative in 3 of 5.
- ATS 3+ at the open 52.41% → 53.22% (n = 2,172, ± 2.1). CLV 0.562 → 0.545 pts.
- Calibration and SD unchanged.
- Coefficients (points per 1 SD): the opponent-defense versions carry the weight (line yards +0.86, standard-down
  success +0.79, stuff rate +0.47, open-field +0.44); the offense versions are small and mixed in sign.

**Reading.**
- T4 makes results line up better with our number by about as much at the close (+0.038) as at the open (+0.034),
  while the opener moves toward us *less*. That's exactly the pattern Rule C was written to reject: a gain that doesn't
  work through the line moving.
- It is either information the market never prices, which would be unusual for public CFBD stats, or a fit to these
  seasons' results that won't repeat.
- Under Rule B it would have passed (result slope +3.5 SE), which is why the rule had to be fixed before the run.
- **Verdict stands: rejected.** No variants. As a hypothesis only, it could be judged on the 2027 record if it is
  pre-registered before the season.
