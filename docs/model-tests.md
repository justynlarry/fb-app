# Model tests and rules

Every model change we've tried, the rules each one was judged by, and the result. Most entries are summaries
of `CLAUDE.md` (Model and Backtest sections), which stays the working record. Updated 2026-11-13.

**Contents:** 1. Rules · 2. Current model · 3. Season to date · 4. Tests in order (with the slope metric) ·
5. Pre-registrations · 6. Combined-test candidates · 7. What's left

---

## 1. Rules

### How the model is judged
- **Walk-forward only.** A week-W prediction uses only games before week W plus preseason priors. Each season
  is predicted by a points model trained only on earlier seasons. Any lookahead makes a result worthless.
- **2020 (COVID) is left out** of every evaluation.
- **Opening lines exist only for 2021+**, so every "at open" figure covers 2021–25. Sources: DraftKings 2023+,
  ESPN Bet 2023–25, Bovada. 2018–20 have closing lines only. "Best open" means the best of at most 3 books
  (only 1 book in 2021–22), without prices.
- **What we report:**
  - average spread and total miss (MAE), ours vs the closing line
  - cover rate when we disagree by 3+ and by 5+, at the open and at the close
  - CLV (closing line value)
- **CLV shows direction only.** On 3+ picks the line moves about 0.6–0.8 pts toward us, against an average gap
  of about 6.3 pts. So a high CLV % can sit beside a 50% cover rate. Always quote CLV in points too.
- **Market lines are never model inputs.** They're used only to evaluate the model and to display beside it.
  The goal is our own line.

### Statistics quoted with every result
- **n**, the standard error **SE = √(p(1−p)/n)**, and the **95% interval = ±1.96 SE**.
- Break-even at −110 is **52.4%**.

| Sample | n (3+ picks) | 95% interval |
|---|---|---|
| One season | ≈ 400–450 | ± 4.7 |
| Pooled 2021–25 | ≈ 2,150 | ± 2.1 |

**How many picks it takes to tell 53.4% from 52.4%** (p ≈ 0.524, q = 1 − p; at our volume of ≈ 435 3+ picks per season at open):

| Question | Formula | n | Seasons |
|---|---|---|---|
| Measure a win rate to ±1 pt (95%) | n = 1.96² · p·q / 0.01² | ≈ 9,600 | ≈ 22 |
| 80% chance of detecting a true 53.4% vs 52.4% (two-sided 5%) | n = [(1.96·√(p₀q₀) + 0.84·√(p₁q₁)) / 0.01]² | ≈ 19,600 | ≈ 45 |

The earlier "≈ 8,000" can't be reproduced from either formula and is withdrawn. Win rate alone can't settle a 1-point question;
that's why the slope metric below exists.

### The acceptance rule, Rule A (Tests 4–5; current until Rule B is approved)
Baseline is the current model, 2021–25, 3+ gaps at the **opening** line. A change is accepted only if **all four** hold:
1. Pooled ATS 3+ at open is higher than the baseline.
2. It is at or above the baseline in **at least 4 of 5 seasons**.
3. CLV (3+) pooled, as a percentage (share of picks where the line moved toward us), is not down by more than
   1.0 **percentage point**. (This is how Tests 4–5 applied it, e.g. 61.1% → 61.8%.)
4. Spread MAE is not worse.

Write the rule before seeing any result, and never loosen it afterwards. If the main variant fails, don't try
other variants.

### Rule B: slope as the main test (approved 2026-11-13; applies from Test 6 on)
**Main test.** Use the paired slope difference at the open, Δslope = slope(variant) − slope(baseline). Compute it on
all games with an opening line, 2021–25. Its SE comes from a paired bootstrap: 2,000 resamples of games, with both
models scored on the same resampled games. **Pass if Δslope ≥ 1.645 × paired SE** (one-sided 95%).

**Amended 2026-11-16 (user decision), for every test registered from this date:**
- **Pass bar 2.24 × paired SE** (one-sided 1.25%). With four new models planned, the chance that at least one
  passes by luck is about 5%; at 1.645 it would be about 19%. The cost is that real but small effects fail more
  often.
- **"The open" is Bovada's `spread_open`**, with Bovada's own close for CLV (2021–25, n ≈ 4,170). The average of
  books mixes in DraftKings and ESPN Bet lookahead lines from 2023 on.
- A pass makes a candidate for a frozen holdout, never an adoption by itself.
- Tests 6–7 keep the bar they were registered with. Holdout 5A moves to 2.24 (see 5A).

**Supporting checks** (all must hold):
- ATS 3+ at open not down by more than 1.0 percentage point.
- CLV % not down by more than 1.0 percentage point.
- Mean CLV in points not down by more than 2 paired SEs. That's about 0.02 pts for a single added feature; the
  paired SE is 0.009 for v5 vs v4. A fixed 0.05 would be about 5 SEs and too loose to catch anything.
- Spread MAE (all games, 2021–25) not worse.

**Reporting.** Report the by-season Δslope; there's no count requirement. Flag the result if it's negative in 3 or
more of 5 seasons.

**Why one-sided 95%:** about 30 variants have been tried. Typical paired SEs are 0.008–0.009 for one added feature
and 0.02–0.03 for a ratings change, so effects of about 0.015 and 0.04 respectively are detectable.

### Adoption policy (proposed): "for edge" vs "for accuracy"
One rulebook, two ways in. Both need the rule written down first.
- **Adopt for edge:** passes the acceptance rule in force (A now, B once approved).
- **Adopt for accuracy:** all of the following.
  - Spread MAE better pooled (2021–25, all games) and in at least 4 of 5 seasons.
  - No harm to betting: Δslope ≥ −1 paired SE; ATS 3+ at open not down by more than 1.0 pp; CLV % not down by more
    than 1.0 pp; CLV points not down by more than 2 paired SEs.
  - The change is labeled "accuracy" and never quoted as edge evidence.

What it would say (not re-deciding anything):

| Change | Rule A | Rule B | Accuracy |
|---|---|---|---|
| **v5 vs v4** | **Passes.** ATS 52.30 → 52.40; seasons +0.3/0/+0.1/−0.4/+0.5 = 4 of 5; CLV 61.21 → 61.13; MAE 12.839 → 12.826 | Fails main test (Δslope +0.009 ± 0.008 = 1.2 SE) | Passes (MAE better in 4 of 5) |
| **T4 coach career** | Fails (3 of 5 seasons) | Passes (Δslope +0.026 ± 0.009 = 2.9 SE) | Passes (MAE better in 5 of 5) |

So v5 wasn't only an accuracy adoption: it also passed today's Rule A. The two decisions look inconsistent because
the season-count condition is noisy, not because of a double standard.

### Holdouts and multiple testing
- About 37 variants have been tried: Rounds 1–5, v1–v5, Tests 1–5, plus Test 6 (6 runs: A, 4 leave-one-out, C)
  and Test 7 (1).
- Rule A lets a change with no real effect pass about 8–10% of the time (4 of 5 seasons by luck ≈ 19%). Rule B's
  main test lets one through about 5% of the time.
- **2026 is used up** for the tier rule, Rounds 2–4 and Tests 1–2, because those all looked at 2026 data.
  v4's own 2026 record is roughly clean.
- 2026 has **not** been looked at for Test 4's coach-career idea, so it could be a one-shot holdout if
  pre-registered.
- Clean evidence from here on: `pick_log` from 2026-11-12, and the 2027 season with the model frozen at kickoff.

### Pick rules (live)
The logic lives in `cfb/picks.py make_pick()`, which both the page and `record_picks` use. `PICK_RATES_SQL`
gives the backtest rates (since 2026-11-16: Play and Pass graded at the Bovada open, 52.4% n=2,094 and 51.0%
n=1,999; Caution at the close with the same moved-against test), so change both together. `pick_results`
"first" = the pick at bet time (first snapshot with 4+ books, 8+ hours after both teams' previous kickoff;
`019_pick_bet_time.sql`), not the first pick logged; lookahead picks stay in `pick_log` ungraded.

| Tier | Rule |
|---|---|
| **Play** | 3+ pts off the current line (median of The Odds API books), and the line hasn't moved 0.5+ against us since the open |
| **Caution** | 3+ off, but the line has moved 0.5+ the other way since it opened |
| **Pass** | under 3 pts off |
| **Check news** (flag) | 5+ off: look for injury or QB news before betting, and enter an override if needed |
| **Totals** | 3+ off is shown as Info only. Our totals have never beaten the market. |

**Betting practice (user's plan):** bet at the opening line (Sunday openers); treat a gap still 3+ at kickoff as
a warning, not an opportunity.

---

## 2. Current model: v5 (adopted 2026-11-12)
- **Ratings:**
  - Per-play efficiency: EPA/play split pass and rush, success rate, explosiveness; plus plays (pace) and
    points. Garbage time excluded. (Corrected 2026-11-13: points per opportunity is not a v5 metric.)
  - Opponent-adjusted with ridge regression (ALPHA = 1).
  - Recency half-life 4 weeks. Last season's games are treated as 8+ weeks old, at weight 0.25 × a fade
    over 6 weeks.
- **Points model:**
  - Linear model predicting each team's points, so line = home − away and total = home + away.
  - Preseason inputs: talent, returning PPA, new coach. These fade out over 16 weeks.
  - Home field is a single coefficient.
  - Mid-season coach change is a feature, regular season only.

| Version | Spread miss (2018–25) | ATS 3+ at open | CLV 3+ | Notes |
|---|---|---|---|---|
| v3 | 12.88 | | | |
| v4 | 12.87 | 52.3% | 61% | recency weighting; best open number 53.4% |
| **v5** | 12.86 | 52.4% | 61.1% | + coach-change feature; adopted for accuracy, not a proven edge |

### v5 backtest by season (3+ gaps; n excludes pushes)
| Season | ATS at close (n) | ATS at open (n) | Total bias (actual − ours) | Total miss, ours / close | O/U 3+ at close |
|---|---|---|---|---|---|
| 2018 | 50.2% (480) | – | +0.35 | 13.53 / 12.94 | 49.4% |
| 2019 | 53.9% (440) | – | −0.90 | 13.51 / 12.87 | 47.8% |
| 2021 | 49.2% (419) | 52.6% (403) | −0.18 | 13.15 / 12.50 | 48.8% |
| 2022 | 51.5% (487) | 52.2% (425) | +0.67 | 12.76 / 12.17 | 50.1% |
| 2023 | 48.9% (427) | 51.2% (447) | +2.04 | 13.10 / 12.62 | 49.3% |
| 2024 | 51.2% (447) | 54.3% (440) | +1.36 | 13.06 / 12.64 | 51.7% |
| 2025 | 50.4% (448) | 51.7% (449) | +0.74 | 12.80 / 12.42 | 50.1% |
| **All** | **50.8% (1,599–1,549, n=3,148)** | **52.4% (1,134–1,030, n=2,164)** | +0.61 | 13.12 / 12.59 | **49.6% (2,989)** |

**Count fix (2026-11-13).** The first version was off by one in the "All" row. The query's "2018+" filter also
picked up one live 2026 game (Memphis–USF, a loss), and the per-season open counts included pushes (26 in all)
while the close counts didn't. Pushes: 29 at close, 26 at open. The rates were unchanged.

**Which spread miss is which.**
- 12.86: all games, 2018–25.
- 12.83: all games, 2021–25.
- 12.77: only the games with an opening line, 2021–25. That's the set Test 4 reported.

Compare like with like.

**Market definition.** The backtest market is CFBD's average across books, while the live market is The Odds API's
median. "Best open 53.4%" is the best of at most 3 books, with no prices, so it's an upper bound and not a number
you could have bet.

---

## 3. 2026 season to date (v5 = v4, since no 2026 coach changes are entered; trained on 2017–25)
Through Nov 12, rebuilt week by week on 2026-11-13.

| | All FBS-involved (693 games) | FBS vs FBS only (570) |
|---|---|---|
| Spread miss, ours / close | 12.81 / 11.72 | 12.53 / 11.53 |
| Total miss, ours / close | 12.99 / 12.29 | 13.04 / 12.47 |
| Total bias (actual − ours) | +2.08 | +1.57 |
| ATS 3+ at open | 182–181, 50.1% (±5.1) | 145–137, 51.4% (±5.8) |
| ATS 3+ at close | 150–188, 44.4% (±5.3) | 119–145, 45.1% (±6.0) |
| ATS 5+ at open | 102–96, 51.5% (±7.0) | 75–77, 49.3% (±7.9) |
| ATS 5+ at close | 85–114, 42.7% (±6.9) | 61–88, 40.9% (±7.9) |
| O/U 3+ at open / close | 50.8% / 47.7% | 51.7% / 49.2% |
| CLV 3+ | 65.0%, +0.77 pts (n=326) | 66.1%, +0.78 pts (n=257) |

FBS vs FBS, ATS 3+ by month (at open / at close):

| Month | n (at open) | At open | At close |
|---|---|---|---|
| August (week 0–1) | 3 | 1–2 | 2–2 (n=4) |
| September | 116 | 52.6% | 46.0% |
| October | 137 | 52.6% | 45.8% |
| November | 26 | 42.3% | 37.0% |

**Reading it:** the market moves toward us, but only part of the way. A gap still there at kickoff loses, and
5+ gaps are worst, usually because of news the model doesn't have.

**Fading the model** (betting the other side) at close: 49.2% over 2018–25 (n=3,149), so it loses money. Only
2026 looks better (55.6%, ±5.2), and 2026 is used up. Not a strategy.

**Live record (`pick_log`, from 2026-11-12):** Plays 0–1 (USF +4 vs Memphis, Nov 12).

**Hypothesis (untested): more injury news at the close.** 3+ gaps at the close went 44.4% ± 5.3, so the upper
bound is below 50%.
- **Possible reason:** the Big Ten went to 4 availability reports a week this season, joining the SEC (since
  2024) and the ACC and Big 12 (since 2025). More official injury news reaches closing lines, and it's news we
  don't have.
- **Test (0 calls, all data cached):** split games into conference games where that conference publishes reports
  that season vs. all others (non-conference and G5).
- **What to compare:** (a) how much the close improves on the open, |result − open| − |result − close|;
  (b) slope at the close; (c) ATS 3+ at the close.
- **Cleanest version:** difference-in-differences. Compare the SEC from 2023 (before reports) to 2024 (after),
  against other conferences over the same years. Then repeat for the ACC and Big 12 from 2024 to 2025.
- **Expected n:** a few hundred conference games per conference per season, so ±5–7 pts per cell. Pool the
  conferences.

**Totals note.** The 2026 total bias is +2.08, about the same as 2023 (+2.04). The market was also low both years
(+1.07, +1.28), so scoring ran above everyone's expectations, with ours about 1 pt further off. Round 2 already
rejected a current-season bias correction, and nothing new has turned up. No new test.

---

## 4. Tests in order

| # | Date | Idea | Result | Key numbers |
|---|---|---|---|---|
| R1 | 11-11 | QB change from box scores, two variants | **Rejected** | Spread miss stayed 12.87, ~12.66–12.70 in 1,481 QB-change games (market 12.23). Useful only for suggested override sizes: about 1 pt plus ~3.7 pts per +1.0 team pass EPA lost. |
| R1 | 11-11 | Weather (Open-Meteo, 5,843 games) | **Not added**; forecast flag on page | Total miss 13.006 → 12.996. Extremes have small samples: gusts 30+ (n=205) under 57.8%; rain 0.1–0.3 in (n=183) under 55.5%. |
| v4 | 11-12 | Recency weighting, half-life 4 weeks | **Adopted** | Spread 12.88 → 12.87, ATS 3+ open 52.3%, CLV 61% (7 variants; gradient boosting worse in all). |
| R2 | 11-12 | Weight recent seasons in the points model | **Rejected** | Slightly more accurate, but ATS at open and CLV worse. |
| R2 | 11-12 | Current-season bias correction | **Rejected** | No ATS gain, CLV down, total miss worse. |
| R3 | 11-12 | Last season's SP+ as a faded prior | **Rejected** | Spread 12.860 → 12.841, total 13.111 → 13.044, but ATS open 51.9 → 50.0, CLV 61.3 → 60.0, worse in 4 of 6 seasons. |
| R3 | 11-12 | Transfer portal | **Rejected** | ~0.1 pt per SD, CLV flat or down: noise. |
| R3 | 11-12 | Schedule spots (bye, short week, travel) | **Rejected** | Short week ≈ −3.9 pts, but ATS and CLV worse (already priced in). |
| R4 | 11-12 | Drive metrics (finishing drives, field position) | **Rejected** | Spread 12.860 → 12.847, CLV 61.3 → 61.8, ATS open flat (51.9), down in 4 of 6 seasons. |
| R5/v5 | 11-12 | Mid-season head-coach change | **Adopted for accuracy** | Spread 12.870 → 12.859, ATS open 52.3 → 52.4%, CLV 61.2 → 61.1%. Affected 3+ picks 55.1 → 57.3% (n≈105). Learned effect ≈ −4 pts margin. Regular season only. |
| Rev | 11-12 | Outside review (0 calls) | Findings | Our miss SD 16.3 vs market 15.5. Gaps 3+ at close, 2021–25: 50.3% (n≈2,228), **−4.0% ROI at −110** (earlier "−2.9%" was the ROI of the 2018–25 rate, 50.8%). Bowls 53.6% (n=97); CFP 46% (n=13). Key numbers: 3 = 9.4%, 7 = 7.9% of margins (2021–25 FBS-involved games: 10.1% and 8.3%). |
| T1 | 11-12 | Weeknight MAC/SBC/C-USA, 3+ at open | **Kept as a hypothesis** (tag and track) | Discovery 2021–25: 74–44, 62.7% ± 8.7 (54.0–71.4). Holdout 2026: 11–9, 55.0% ± 21.8 (33–77). Too small to confirm or reject. The pooled 61.6% isn't evidence: discovery games can't confirm their own finding, and the discovery rate is inflated because it was the best of several cuts. |
| T1 | 11-12 | FCS opponents | **Rejected** | 2021–25 131–95, 2026 37–45 (45.1%). |
| T2 | 11-12 | Weight last season's games by returning production | **Rejected** | Weeks 0–5 miss moved ≤ 0.006; ATS 52.29–52.51%; not lower in only 2 of 5 seasons. Test 3 was skipped because its precondition failed. |
| T4 | 11-13 | Coach career record vs our line (K=100) | **Rejected** | ATS 52.40 → 52.86% (n=2,079), but at or above baseline in only 3 of 5 seasons (+0.7/−0.9/−0.4/+0.4/+2.3). CLV 61.1 → 61.8. Spread miss 12.77 → 12.70, better in all 5 seasons. |
| T4 | 11-13 | Team vs same opponent (K=5) | **Rejected** | 52.43%, 2 of 5 seasons, CLV −1.7, miss worse. |
| T4 | 11-13 | Coach vs same opposing coach (K=5) | **Rejected** | 51.93%. |
| T5 | 11-13 | Fumble-recovery luck (play-by-play) | **Rejected** | ATS 52.43 → 52.25%, 1 of 5 seasons, CLV 61.2 → 60.8, miss 12.83 unchanged. Coefficients tiny and wrong-signed. |
| T6-A | 11-13 | Combined: v5 + coach career + drive metrics (ppo, opp_rate, start_ytg); ridge α=1, Rule B | **Passed Rule B; adoption decision pending** | Δslope at open +0.044 ± 0.021 (2.12 SE); slope 0.104 → 0.148. ATS 3+ open 52.41 → 53.38% (n=2,132, ±2.1). CLV 61.14 → 61.55%, pts 0.615 → 0.610 (paired SE 0.028). Spread miss 12.826 → 12.737, total 12.971 → 12.936. Δslope negative only in 2023. |
| T6-B | 11-13 | Leave-one-out (diagnostic) | Info | Coach career carries it: +0.038 ± 0.019 (2.0 SE); without it ATS 3+ open 51.89%. Drive groups add nothing: ppo −0.002 ± 0.002, opp_rate −0.006 ± 0.004, start_ytg +0.001 ± 0.003. |
| T6-C | 11-13 | Selection on 2021–23 (drops all 3 drive groups) → v5 + coach career, confirmed once on 2024–25 at 1.96 SE | **Failed** | Δslope +0.059 ± 0.033 = 1.80 SE (bar 1.96); ATS 3+ open 53.11 vs 52.98% (n=883, ±3.3); spread miss 12.562 vs 12.620. |
| T7 | 11-13 | Weather for totals: forecasts in the test season, observed weather in training; judged at the close | **Rejected** | Total slope at close Δ +0.014 ± 0.015 (0.97 SE). O/U 3+ at close 49.98 vs 50.02% (n≈2,110). Total miss 12.965 vs 12.971. Spread no-harm check also failed, by a trivial amount (−0.0006 ± 0.0003). Learned effects: rain −2.5 pts per team per inch; wind −0.14 per mph. |
| C | 11-16 | Per-metric ridge shrinkage (alphas from 2017–19 next-game error: EPA 2, SR 2, explosiveness 8, pass/rush EPA 4, plays 4, points 2) | **Rejected** | Bovada open 2021–25 (n=4,169): Δslope −0.002 ± 0.007 (−0.36 SE; bar 2.24). ATS 3+ 52.41 → 52.42%. CLV pts 0.562 → 0.508 (−3.5 paired SE). Spread MAE 12.826 → 12.891, worse in all 5 seasons. Weeks-played 5+ Δslope −0.006. Ratings predict next-game metrics 1–9% better, but the points model gets worse. |
| F | 11-16 | DraftKings lookahead: v5 with ratings one week staler, at the DK open 2023–25 | **Supported** (tag and track in 2027; no betting on this alone) | n=2,150. Slope +0.175 ± 0.063 (2.77 SE; bar 2.24); by season +0.15/+0.28/+0.09. Bovada Sunday open moved toward us by +0.73 ± 0.09 pts on 3+ gaps (n=1,124). Info: ATS 3+ at the DK open 53.5% (604–525, ±2.9) vs 55.4% for normal v5, whose slope +0.225 is inflated by lookahead. Caveat: some DK opens are older than one week, which flatters this. |

### Slope metric (added 2026-11-13; information only for past decisions)
**What it measures.** The slope is a continuous measure of edge that uses every game, not just the 3+ ones.
- g = our line − the market line (how much we disagree)
- r = the result − the market line (where the game actually landed)
- Regress r on g. The slope says how far, on average, the game lands our way per point of disagreement.
  - 0 = we add nothing beyond the market line.
  - 0.10 = a 6-point disagreement is worth about 0.6 pts our way.
- SEs are a bootstrap over games (2,000 resamples). By-season SEs are OLS.

| Model | Slope at open, 2021–25 (n=4,256) | Slope at close, 2018–25 (n=6,153) | Paired Δ vs reference, at open |
|---|---|---|---|
| v1 | +0.049 ± 0.042 | −0.012 ± 0.032 | |
| v3 | +0.057 ± 0.050 | −0.001 ± 0.037 | |
| v4 | +0.095 ± 0.047 | +0.010 ± 0.035 | |
| **v5** | **+0.104 ± 0.048** | +0.015 ± 0.037 | vs v4: +0.009 ± 0.008 |
| T4 coach career (on v5) | +0.129 ± 0.048 | +0.028 ± 0.036 | vs v5: **+0.026 ± 0.009** |
| R4 drives +start_ytg (on v4) | +0.100 ± 0.047 | +0.012 ± 0.036 | vs its base: +0.010 ± 0.005 |
| R4 drives +all three | +0.099 ± 0.046 | +0.008 ± 0.037 | vs its base: +0.009 ± 0.009 |

v5 at the open, by season: 2021 +0.18, 2022 +0.06, 2023 +0.18, 2024 +0.11, 2025 −0.04 (each ± about 0.10).

**Reading it.**
- At the open, v5's slope is about 2 SEs above zero (95% interval about 0.01 to 0.20). That's the strongest
  evidence so far that we know something the opener doesn't.
- At the close it's about zero. By kickoff the market has priced in what we know, which matches CLV: the line
  moves 0.61 pts toward us on a 6.3-pt average gap, about 0.10 of the gap.
- T4's +0.026 is 2.9 paired SEs, but it was found in hindsight, so it's a hypothesis for the 2026 holdout (A
  below), not a reversal.
- The saved variant rows reproduce stored v3 and v4 exactly. Fumble-luck (T5) rows weren't saved and can be
  rebuilt (about 5 minutes) if wanted.

**Sanity check (open vs close on the same picks).** Take the 2,190 v5 3+-at-open picks from 2021–25:
- Graded at the open they went 52.40%; graded at the close, 50.74%. The gap is 1.67 pts.
- Mean CLV was 0.614 pts.
- A smooth normal (σ ≈ 15.3–16) predicts a gap of 0.614 × 2.5–2.6% per pt ≈ 1.6 pts.
- Using the real density near the close line, which includes key numbers (3.3% per pt within ±1.5), predicts
  2.0 pts.
- The measured 1.67 sits between the two, so the check holds.

The reviewer's version (50.8% + 0.77 × 2.5% ≈ 52.7%) mixes three samples: 50.8% is 3+-at-the-close picks over
2018–25, and 0.77 is 2026's CLV. It still lands near the right answer.

**Don't retry these without new information:** QB-change detection, recent-season weighting, bias
correction, SP+ priors, portal, schedule spots, drive metrics (tested alone in Round 4 and in combination in Test 6:
no contribution either time), returning-production weighting, head-to-head, fumble luck, weather for totals (with
forecasts, Test 7).
**Still open:** coach career as a learned points-model feature. It passed Rule B in combination (T6-A) and
narrowly missed confirmation (T6-C). Confirm it on the 2026 holdout (pre-registration A) before adopting.

### Lessons
- **Information the market already uses** (SP+, schedule, last week's starter) makes us more accurate and
  takes away edge: we agree with the market more.
- **Our edge, if any, comes from the recency-weighted EPA ratings,** and it shows up at the opening line, not
  the close. The slope agrees: about +0.10 at the open (≈2 SE), about 0 at the close. The recency change (v3 → v4)
  added the most (+0.04).
- **Win rate on 3+ gaps is a blunt tool.** It uses half the games and needs 20,000 picks to settle a 1-point
  question. The paired slope uses every game, and two similar models share most of their noise, so differences of
  about 0.015 are detectable.
- **The 1-point gap to the closing line (12.5 vs 11.5) is mostly news:** injuries, QB changes, motivation.
  Overrides and the Check news flag are aimed at that gap, not another model feature.
- **Data checks before multi-call pulls:**
  - CFBD `conference` must be the abbreviation; a full name returns an empty list and still costs a call.
  - Read parameter descriptions, not just the `required` flag.
  - Play-by-play fumble counts are about 25% low in 2021–23, so check each stat by season.

---

## 5. Pre-registrations (written 2026-11-13; NOT run; each needs approval)

### A. Coach career, one-shot 2026 holdout (AMENDED 2026-11-13, before any 2026 run)
**Amendment.** After Test 6, the user switched the holdout from T4's fixed weight (line − (adj_home − adj_away))
to coach career as a **learned points-model feature**, the version that carried Test 6. The change was made before
any 2026 run of either version.

**Second amendment (2026-11-16, before any 2026 run of this idea; no 2026 coach-career result has been seen).**
The opening line for this holdout is **Bovada's `spread_open`**, not the average of books. Reason
(`docs/audit-2026-11-16.md` 1.1): DraftKings' `spread_open` is a lookahead line posted before the previous
week's games, so the average of books is half stale in 2026, where only Bovada and DraftKings have opens.
- **Primary:** every metric below that says "at the open" is graded at the Bovada open. CLV uses Bovada's own
  close. The games are every completed 2026 FBS-involved game with a Bovada open.
- **Reported beside it, not used for the outcome:** the same metrics at the mixed open (average of books), as
  first written.
- **Small sample.** One season at one book: about 750 games and about 370 3+ picks (±5.1 on a win rate). The
  one-season paired SE of Δslope is about 0.02, so power for an effect of +0.03 to +0.04 is still only 40–60%.
  "Consistent" is the most likely outcome even if the effect is real.
- **Bar raised to 2.24 × paired SE** (user decision 2026-11-16, before any 2026 result): "Confirmed" below now
  needs Δslope ≥ 2.24 × paired SE instead of 1.645. This only makes the holdout harder to pass; with a
  one-season paired SE of about 0.02 it needs Δslope of about +0.045, so "Confirmed" is unlikely and
  "Consistent" (track in 2027) is the expected outcome even for a real effect.

**Clean check.** 2026 hasn't been looked at for this idea.
- `coach_test.py`, `slope.py` and `t6.py` all stop at 2025.
- The 2026 analysis (`season2026.py`) scored plain v5 with no coach input.
- The v5 2026 baseline is known, but the coach-career *difference* on 2026 is not.

**Variant, nothing tuned:**
- **Models:** v5 features + `coach_career` + `opp_coach_career`, exactly as defined in Test 6. The shrunk coach
  residual vs v5 uses K = 100 and only seasons before the game's season (for 2026: the v5 walk-forward games
  2018–25, 2020 excluded).
- **Fit:** Ridge(alpha = 1) on standardized features, trained on every 2017–25 row with a final score.
- **Baseline:** the same fit with v5 features only. Both use v5 walk-forward rows for 2026 (`season2026.py`
  ratings).
- **Coach identity for 2026:** the cached 2026 `/coaches` (one coach per team) plus any `coach_changes` rows.
  None are entered for 2026; the user knows of no major mid-season changes.

**Games:** every completed 2026 FBS-involved game with an opening line, with no other filter. Run **once**, on or
after 2026-12-07, after conference championship weekend. Expect about 750 games, with about 400 3+ picks at open.

**Main metric:** paired Δslope at the open (coach-career model − baseline). One-season paired SE is about 0.02,
so detecting an in-sample-sized effect (+0.03 to +0.04) has roughly 40–60% power.

**Outcomes, decided now:**
- **Confirmed:** Δslope ≥ 2.24 × paired SE (was 1.645; raised 2026-11-16), AND spread MAE better, AND ATS 3+ at open not down by more than
  2 pp, AND CLV points not down by more than 2 paired SEs.
- **Consistent:** Δslope > 0, and the other checks as above. In this case, track it in 2027 frozen; there's no
  adoption on this alone.
- **Rejected:** Δslope ≤ 0 or MAE worse. Drop the idea, with no variants afterward.

### B. Combined-feature model (waits for approval of the Part 4 candidate list)
**Setup:**
- Start from v5 and add every approved candidate at once.
- Same points model as v5: plain linear regression, which with 10,000+ rows per training set and few features
  barely needs regularization. If you'd rather use ridge, fix alpha now, on standardized features, and use it for
  the baseline too.
- Walk-forward, trained on seasons < S. No dropping features after seeing results, and no hand-set constants.

**Judged by:** Rule B (Δslope at open 2021–25 ≥ 1.645 paired SE, plus the supporting checks). If Rule B isn't
approved, use Rule A.

**Interactions:** none named, so none tested.

**Clean evidence:** only the 2027 season with the model frozen, and `pick_log`. 2026 isn't clean for this,
because Round 4 already looked at 2026 drive metrics.

### C. Live-betting stopping rule (written now, applied after the 2027 season)
**Inputs:**
- `pick_log` first pick before kickoff, so we're grading early bets.
- Slope at the open over **all** 2027 games with an opening snapshot. One season's SE is about ±0.10.
- ATS of recorded Plays at the price logged.
- Mean CLV points on Plays. With an SD of about 2.2 per pick, SE ≈ 0.11 at 400 Plays.
- **Real ROI from the bet log at the prices actually taken.** The bet log has to exist before 2027 week 0.

**Circuit breaker (mid-season):** after 200 Plays, if mean CLV points ≤ 0, stop. The backtest's 0.61 is about
4 SEs above 0 at that n, so CLV points is the fast signal.

**After 2027:**
- **Continue** (same stakes): slope ≥ +0.05, AND CLV points ≥ +0.30, AND ATS at open ≥ 50%, AND real ROI ≥ −5%.
- **Stop:** slope ≤ 0 AND CLV points ≤ +0.20; OR real ROI ≤ −8% with ATS at open < 50%; OR the slope's 95% upper
  bound < +0.05.
- **Scale back** (half stakes, one more season, then apply the same rule to the two seasons pooled): anything else.

## 6. Combined-test candidates (approved 2026-11-13; run as Test 6, plan in scratch `combined_test_plan.md`; results in section 4)
Only features that failed for **lack of power**, not for **direction**:

| Feature | Include? | Reason |
|---|---|---|
| T4 coach career residual (K=100) | **Yes** | MAE better in all 5 seasons, ATS +0.46, CLV up, Δslope +0.026 (2.9 SE). Failed only on season count. |
| R4 drive metrics: ppo, opp_rate, start_ytg (all three, as originally built) | **Yes** | CLV up in 5 of 6 seasons, MAE slightly better, Δslope +0.009 (1 SE). Use all three rather than start_ytg alone (+0.010, 2.0 SE), which was the best of 4 sub-variants; picking it would add more selection bias. |
| Weather (wind, rain) | **No** | Moves totals, not spreads, so Rule B can't judge it. The backtest used *observed* weather, but live would use *forecasts*. Keep it as a totals hypothesis using the forecast log. |
| QB change from box scores | No | No accuracy change at all; the market already knows last week's starter. |
| Recent-season weighting (R2) | No | ATS and CLV went the wrong way. |
| Current-season bias correction | No | Wrong direction (CLV down, totals worse). |
| SP+ priors, schedule spots | No | Make us agree with the market more. |
| Transfer portal, fumble luck | No | Noise-level or wrong-signed coefficients. |
| Returning-production weighting (T2) | No | Can't move early-season accuracy by design (weight 0.25, gone by week 6). |
| Head-to-head (team or coach) | No | Worse on every measure. |
| Mid-season coach change | Already in v5 | |

**Bias from choosing this list.** Both candidates were picked because they looked good on 2021–25, the same data
the test uses. Picking the best few of about 30 tries overstates their effect, typically by 1–2 SEs. A pass on
2021–25 would therefore be weak evidence. Only 2027 (frozen) and `pick_log` count as clean. The 2026 holdout
(A) is clean for T4 alone, not for the combination.

## 7. What's left
- **Open hypotheses (tracked, not in the model):**
  - weeknight G5 games (Test 1)
  - weather extremes, with a forecast log kept for a future honest test
  - the Test 4 coach-career idea as a one-shot 2026 holdout (only if pre-registered)
- **Next real evidence:**
  - v5's live record in `pick_log`
  - 2027 with the model frozen
- **Ideas not yet tested:**
  - a win-probability-based garbage-time filter (play-by-play)
  - CPOE / passing detail
  - moneyline / win probability
  - comparison with outside ratings

## 8. Tests approved 2026-11-16 (from `docs/audit-2026-11-16.md`; none run yet)
All at the Bovada open, 2021–25, bar 2.24 × paired SE, no variants after results. A pass makes a candidate for a
frozen 2027 holdout only. Three model runs (A, C, F): chance that at least one passes by luck is about 4%.
**Status 2026-11-16:** C rejected, F supported (results in section 4). A and B wait for Dec 6–7.

| # | Test | Models | Rule (written before any result) |
|---|---|---|---|
| A | Holdout 5A, as amended in section 5 | 1 | Section 5A outcomes, Confirmed at 2.24 SE |
| B | Season-phase rule: no bets until weeks-played ≥ 5 | 0 | On 2026 games through Dec 6 at the Bovada open: *supported* if slope(weeks-played ≥ 5) − slope(0–4) > 0 AND ATS 3+ is higher for ≥ 5 than for 0–4. Not supported → drop. Supported → apply in 2027; pre-registration C judges it. Discovery (2021–25, FBS vs FBS): 0–4 47.6% (n=693), 5+ 54.1% (n=1,226); hindsight cut. 2026 by month has been seen at the mixed open (Sept 52.6%, Oct 52.6%). |
| C | Per-metric shrinkage: each metric's ridge alpha set from 2017–19 data only, by how well the rating predicts the team's next game (no lines used) | 1 | Δslope ≥ 2.24 paired SE; ATS 3+ not down > 1.0 pp; CLV points not down > 2 paired SE; spread MAE not worse; **Δslope in weeks-played 5+ alone not negative** |
| F | DraftKings lookahead: v5 unchanged, ratings cut off one week earlier, graded at the DraftKings open 2023–25 | 1 | *Supported* if slope at the DraftKings open ≥ 2.24 bootstrap SE above zero AND the Bovada Sunday open moved toward us on 3+ picks (mean > 0). Supported → tag and track lookahead picks in 2027, no betting on this alone. Weakness: CFBD gives no posting time, so some opens are older than one week. |

**Dropped:** D (FCS-vs-FCS games change the scoring level by ≤ 0.05 pts/team; the totals bias comes from the model
double-counting the league-wide scoring decline, which cancels in the spread: a totals-only fix, parked) and
E (QB prior: its effect falls in weeks 0–4, which the free pass rule B would skip).

### Run details for C and F (written 2026-11-16, before either was run)
**C, per-metric shrinkage.**
- Alpha grid, fixed now: 0.25, 0.5, 1, 2, 4, 8, 16, 32. If the best is at an edge, the edge is used (the grid is not
  extended).
- Choosing alpha (2017–19 only, no lines): for every week group of those seasons, fit each metric's ratings exactly as
  `ratings_as_of` does (same recency and last-season weights, same columns), predict that metric for every team-game in
  the week, and score the squared error weighted by plays. Each metric gets the alpha with the lowest total error.
- Model: v5 with those alphas; nothing else changes (LinearRegression points model, walk-forward, trained on seasons < S).
- Baseline: v5 rebuilt the same way in the same run (checked against the stored v5 predictions).
- Judged on 2021–25 FBS-involved games: slope and ATS at the Bovada open, CLV = Bovada open → Bovada close, MAE on all
  games with a closing line. Paired bootstrap, 2,000 resamples of games. Rule as in the table above.

**F, DraftKings lookahead.**
- "Ratings cut off one week earlier": each week group uses ratings as of the previous week group's first kickoff (by
  time order), so last week's games are left out. The season's first group has nothing earlier and uses its own cutoff.
- The points model is v5 as trained on normal rows from seasons < S, applied to these lagged rows (what a live
  lookahead pick would have used).
- Games: 2023–25 FBS-involved with a DraftKings `spread_open`. Slope of (result − DK open) on (lagged line − DK open),
  bootstrap SE over games (2,000). "Moved toward us" = mean over 3+ gaps of sign(gap) × (Bovada open − DK open), on games
  with both opens.
- Reported as information only: ATS 3+ at the DK open, and normal (not lagged) v5's slope at the DK open.

## 9. NFL (pre-registered 2026-11-16, approved by the user before any NFL model result was seen)
No NFL opening lines exist in our data (nflverse gives closing lines only), so every NFL test is judged for
**accuracy at the close**, not edge. Research behind these choices: R1/R2 in `CLAUDE.md` (player data only).

### nfl-v1: team ratings only (the baseline for every NFL test)
- Same structure as college v5: opponent-adjusted ridge ratings (α = 1) on the seven metrics, then a linear points
  model per team (line = home − away, total = home + away). Features: offense and opposing-defense ratings, home
  (0 at neutral sites). No college-only inputs (FCS, recruiting, returning production, coach changes).
- **Settings grid (36 combinations):** recency half-life 4 / 6 / 8 / 12 weeks × last season's weight 0.25 / 0.5 /
  0.75 × fade over 4 / 8 / 12 weeks.
- **Chosen on 2017–19 only:** the combination with the lowest spread MAE over all 2017–19 games (walk-forward, points
  model trained on earlier seasons; no lines used). Ties go to the longer half-life. Then frozen.
- **2020:** its games feed the ratings, but its rows don't train the points model (no crowds, home field ≈ 0), and it
  is never evaluated.
- **Reported, not judged:** 2021–25 spread and total MAE vs the nflverse closing line, slope at the close, by season.
- **Result of the search (run 2026-11-16, 294 s): half-life 6, last-season weight 0.5, fade over 12 weeks**
  (2017–19 spread miss 10.460). Frozen. All 36 settings fell within 10.460–10.530, so the choice matters little; the
  longest fade (12) was best at every half-life and is the edge of the grid (not extended, as registered).
- **nfl-v1 backtest (2026-11-16), 2021–25, n=1,424, vs the nflverse close:** spread miss 10.220 vs 9.762; total miss
  10.644 vs 10.313; slope at the close −0.089 ± 0.092; ATS 3+ at close 51.3% ±4.2 (n=540, info). Behind the close in
  every season (0.09–0.65). Weeks 0–1 within 0.1–0.2 of the close. **Our line is too flat:** SD 4.0 vs 6.1 for the
  close, result-on-our-line slope 1.28 (close 1.05), correlation with the close 0.82.

### T-QB: starting-QB adjustment (vs nfl-v1)
- Starter = nflverse schedule `home_qb_id` / `away_qb_id` (the actual starter: a small, stated optimism, since late
  scratches are known only near kickoff).
- QB value = EPA per dropback above that season's replacement level (QBs outside the top 32 by dropbacks), shrunk
  with K = 410 dropbacks, from all his earlier games on any team (no games on or after the predicted game).
- Feature `qb_adj` = starter's value − the dropback-weighted value of the QBs in the team's games that feed its
  current ratings, using the same recency weights. `opp_qb_adj` likewise. The points model learns the weights.

### T-skill: skill-player absences (vs nfl-v1 + T-QB)
- Regular = mean share over his last 3 games for the team: RB ≥ 15% of carries + targets, WR/TE ≥ 12% of targets.
  Absent = flagged before game day: roster status `RES`, injury report Out/Doubtful, or off the team's roster.
  Game-day inactives (`INA`) are **not** used.
- Player value = shrunk EPA per game above replacement (RB per opportunity K = 640; WR K = 400; TE K = 205; replacement
  = outside the top 48 RB / 96 WR / 48 TE by volume), from earlier games only.
- Features: sum of absent regulars' values split by game of the absence (1st; 2nd–3rd; 4th+), and `returning` =
  value of regulars back after 3+ games out; each also for the opponent. The points model learns each weight.
- Diagnostic (not part of the rule): a 1st-game weight above 1.0 means an absence costs more than the player's own
  plays (the offense is built around him); weights falling toward 0 by the 4th+ game mean the ratings absorb it.

### Rule for T-QB and T-skill (accuracy adoption)
On 2021–25 (2020 excluded), against the nflverse closing line:
1. Spread MAE better pooled and in at least 4 of 5 seasons.
2. Slope at the close not down by more than 1 paired SE (paired bootstrap, 2,000 resamples of games).
3. Total MAE not worse pooled.
No variants after results. Two test models; adoption is "for accuracy" and never quoted as edge evidence.

### T-QB result (run 2026-11-16, scratch `t_qb.py`): **passed the accuracy rule**
2021–25, n=1,424, vs the nflverse close. Baseline reproduced stored nfl-v1 (mean |diff| 0.0025).
- Spread miss 10.220 → 10.141 (close 9.762); better in 4 of 5 seasons (2021 −0.21, 2022 +0.18, 2023 −0.03, 2024 −0.12,
  2025 −0.21). Total miss 10.644 → 10.568. Slope at the close −0.089 → −0.063 (Δ +0.026 ± 0.068).
- Games with a big QB difference (|qb_adj| > 0.1 either side, n=203): 10.77 → 10.35 (close 10.00).
- Line less flat: SD 4.03 → 4.79 (close 6.07); calibration slope 1.28 → 1.14.
- Learned weight (2025 training): 26.4 pts per 1.0 EPA/dropback of qb_adj (0.1 ≈ 2.6 pts); opponent's −5.8.
- Detail fixed before the run: replacement level for each season = the previous season's (no lookahead); a starter with
  no NFL dropbacks since 2016 = replacement level (0). Adopted for accuracy only; T-skill is judged against v1 + QB.

### T-skill result (run 2026-11-16, scratch `t_skill.py`): **rejected**
2021–25, n=1,424, baseline = nfl-v1 + T-QB (reproduced: 10.1405).
- Spread miss 10.141 → 10.249, better in 2 of 5 seasons (2021 +0.46, 2022 +0.08, 2023 −0.06, 2024 +0.09, 2025 −0.04).
  Total miss 10.568 → 10.598. Slope at the close −0.063 → −0.109 (Δ −0.046 ± 0.049). Fails 3 of 4 conditions.
- Data: 31,929 regular slots, 7,131 flagged absent, 1,000 returning; absent players' value mean 0.25, max 4.3 pts/game.
- Diagnostic weights (2025 training, points per 1 pt of the player's EPA/game): 1st game −0.63, 2nd–3rd −0.62,
  4th+ +0.03, returning −1.02 (wrong sign), opponent terms −0.4 to +0.3. **An absence costs about 0.6 of the player's
  own EPA, not more**, and nothing by the 4th game (the ratings have absorbed it). No support for "the offense is
  built around him" beyond his own plays. Detail fixed before the run: "returning" = his first 3 games back.
- Use: suggested override sizes only (≈ 0.6 × the player's EPA/game for the first 3 games out). No variants.

### T-CAL: stretch the NFL spread (pre-registered 2026-11-16, approved before running)
- Problem: nfl-v2's line is too flat (2021–25: SD 4.8 vs 6.1 for the close; result-on-ours slope 1.14).
- Model: spread × k, where k for season S = slope through the origin of the actual margin on nfl-v2's walk-forward
  spread over 2017 … S−1 (2020 excluded). Totals unchanged. One model, no hand-set constant, no by-week variant.
- Honesty note: the flatness was noticed on 2021–25, the judging seasons. Clean check: 2026 weeks 1–10 (≈149 games,
  never looked at for the NFL), replayed walk-forward with k from 2017–25, not saved.
- Rule (accuracy adoption), 2021–25 vs the nflverse close: (1) spread MAE better pooled and in ≥ 4 of 5 seasons;
  (2) slope at the close not down > 1 paired SE (2,000-game paired bootstrap); (3) 2026: paired change in spread MAE
  not worse than +1 paired SE. Info only: k by season, calibration slope and SD before/after, winner %, share of games
  under 3, Play-tier record at the close. Pass → nfl-v3 = nfl-v2 × k (accuracy only). Fail → no variants.
- Expected before the run: k ≈ 1.1–1.25, MAE gain of a few hundredths to ~0.1.
- **Result (run 2026-11-16, scratch `t_cal.py`): rejected.** k learned from earlier seasons came out **below 1**,
  not above: 0.92 (2021), 0.96, 0.94, 0.98, 1.02 (2025), 1.04 (2026). So the stretch mostly shrank the line further.
  2021–25 (n=1,424): spread miss 10.140 → 10.144, better in 2 of 5 seasons; slope at the close −0.063 → −0.058
  (Δ +0.005 ± 0.009); calibration slope 1.14 → 1.18, SD 4.79 → 4.61; winner % 62.3 = 62.3; Play tier 50.9% → 51.2%.
  2026 clean check (n=149): miss 9.683 → 9.688 (paired +0.005 ± 0.015; close 9.58); 2026 calibration slope 1.35.
  Fails (1); passes (2) and (3). No variants.
- What it shows (information, not a result to act on): the line wasn't too flat in the early backtest seasons
  (2017–20 predictions, made from 1–4 seasons of training data, were if anything too steep), and is too flat from
  2021 on (calibration 1.14; 2026 1.35). Flatness isn't stable over time, so a k learned from the past can't fix it.
  The cause is more likely in how the ratings or points model behave as training data grows (or the 17-game era).
  Next candidate if pursued: find that cause first (descriptive, no lines), then pre-register a fix.

### Why the NFL line is flat: descriptive look (2026-11-16, scratch `flat_cause.py`; our predictions vs results, no lines)
Calibration = slope of the actual margin on our spread (1.0 = right; above 1 = too flat).
- **Per season it's noisy:** walk-forward 0.79 (2017, trained on 1 season), 1.14, 1.18, 1.10, 1.14, 0.78 (2022), 1.21,
  1.44, 1.15, 1.35 (2026). One season's SE is about ±0.16, so most of the swing is noise around ≈ 1.15.
- **More training history → flatter:** the same 2021–25 games, predicted by points models trained on 2016–17 / –19 /
  –22 / –25: calibration 0.85 / 1.05 / 1.21 / 1.19, spread SD 5.6 / 5.1 / 4.7 / 4.8. The early backtest seasons looked
  steep because their points models were fitted on 1–3 seasons (overfit); with more data the real flatness shows.
- **Too flat even in-sample:** one model fitted on all of 2016–26 still has calibration 1.16–1.37 in 10 of 11 seasons
  (2022: 0.89). So it isn't the 17-game era or a change over time: the per-team points model under-states margins by
  design. Likely reason: each row uses only the team's offense and the opponent's defense, but good teams are good at
  everything; the team's own defense and the opponent's offense (field position, possessions) also drive its points
  (T-QB's learned opponent-QB weight, −5.8, is one sign of that). The margin is the difference of two rows that each
  miss half the matchup.
- **Too steep early, too flat late:** walk-forward by weeks of data, 2021–26: 0–2 weeks 0.89, 3–5 0.95, 6–9 1.17, 10+
  1.34 (2017–20: 0.64 / 0.80 / 1.27 / 1.20). One set of weights for the whole season averages a noisy early rating and
  a reliable late one.
- **The ratings themselves aren't the problem:** late-season SD of the points rating / SD of actual points per game is
  0.77–0.90 in every season, with no break at 2021.
- **Candidates to pre-register (not run):** (1) full matchup rows: add the team's own defense and the opponent's
  offense ratings to each row; (2) let the rating weights change with weeks played (an interaction with season
  progress). (1) addresses the in-sample flatness, (2) the early/late pattern.

### T-MATCH: full matchup rows (pre-registered 2026-11-16, approved before running)
- Baseline nfl-v2. Variant: + the team's own defense ratings (7 metrics) and the opponent's offense ratings (7), from
  the same weekly ratings; no new data, 0 calls. Same frozen settings, LinearRegression, walk-forward, 2020 out.
  All 14 inputs kept regardless of correlation (pairs |r| ≥ 0.95 reported, never dropped).
- Rule (accuracy), 2021–25 vs the nflverse close: (1) spread MAE better pooled and in ≥ 4 of 5 seasons; (2) slope at
  the close not down > 1 paired SE; (3) total MAE not worse pooled; (4) 2026 weeks 1–10 paired spread-MAE change not
  worse than +1 paired SE. Info: calibration and SD before/after, in-sample calibration (fit on 2016–25), calibration
  by weeks of data, winner %, under-3 share, Play-tier record at the close, learned weights.
- Expected before the run: in-sample calibration ≈ 1.2 → toward 1.0; spread SD 4.8 → toward 5.5; MAE −0.05 to −0.15;
  early-steep / late-flat not fixed. Pass → nfl-v3 (accuracy only); fail → no variants. 4th NFL model test.
- **Result (run 2026-11-16, scratch `t_match.py`): rejected on the season count (3 of 5).** No input pairs ≥ 0.95.
  2021–25 (n=1,424): spread miss 10.141 → 10.088 (2021 −0.16, 2022 +0.05, 2023 +0.02, 2024 −0.12, 2025 −0.06); total
  miss 10.568 → 10.549; slope at the close −0.063 → +0.003 (Δ +0.066 ± 0.060). 2026 check (n=149): 9.683 → 9.704
  (paired +0.02 ± 0.14), passes. Fails only (1b), 4 of 5 seasons.
- Info: **the diagnosis was right**: in-sample calibration 1.22 → 1.00; walk-forward 1.14 → 0.92 (now slightly steep);
  line SD 4.79 → 6.01 (close 6.07); winner % 62.4 → 64.2; games under 3 pts 42% → 35%; Play tier at the close
  51.0% → 50.7%; 2026 calibration 1.35 → 1.05. By weeks of data the new line is too steep early (0–2: 0.71, 3–5: 0.82,
  6–9: 0.84) and about right late (10+: 1.05), so the remaining problem is now the early-season one.
  Learned weights mix signs across related metrics (e.g. own defense EPA −15.8 and success rate +18.8), as expected
  with correlated inputs.
- **User decision (2026-11-16): keep the rule.** nfl-v2 stays; the weeks-played test is registered against nfl-v2.
  Any later combination of the two ideas is judged on the clean seasons (2026 on), not 2021–25.

### T-WEEK: rating weights that change through the season (pre-registered 2026-11-16, approved before running)
- Baseline nfl-v2. Variant: + p = min(weeks played, 17) / 17, and p × each of the 14 rating inputs (team offense 7,
  opponent defense 7); not for QB adjustments or home. Same frozen settings, LinearRegression, walk-forward, 2020 out.
  All 15 inputs kept (pairs |r| ≥ 0.95 reported only). 0 calls, nothing saved.
- Rule (accuracy), same as T-MATCH: (1) spread MAE better pooled and in ≥ 4 of 5 seasons; (2) slope at the close not
  down > 1 paired SE; (3) total MAE not worse pooled; (4) 2026 weeks 1–10 paired change not worse than +1 paired SE.
  Info: calibration by weeks of data before/after (the point of the test), overall and in-sample calibration, SD,
  winner %, under-3 share, Play tier at the close, learned early/late weights on the points ratings.
- Expected before the run: 10+ weeks calibration 1.34 → ≈ 1.1; early stays ≈ 0.9–1.0; SD 4.8 → ≈ 5.2; MAE −0.02 to
  −0.08; in-sample flatness mostly unfixed. Pass → nfl-v3 (accuracy only); fail → no variants. 5th NFL model test.
- **Result (run 2026-11-16, scratch `t_week.py`): rejected.** 2021–25 (n=1,424): spread miss 10.141 → 10.178, better in
  1 of 5 seasons (2021 only); total miss 10.568 → 10.618; slope at the close −0.063 → −0.082 (Δ −0.018 ± 0.028).
  2026 check: 9.683 → 9.813 (paired +0.13 ± 0.05, worse by 2.5 SE). Fails (1), (3) and (4).
- Info: late calibration did move (10+ weeks 1.34 → 1.21; early unchanged 0.87 / 0.96), but accuracy got worse.
  35 input pairs had |r| ≥ 0.95: p × rating is nearly p itself (r ≈ 0.99) because the ratings weren't centred before
  multiplying, so the learned early/late weights were unstable (e.g. opponent defense EPA −3.4 early, −28.3 late).
  That is an explanation, not a licence for a variant: a centred version would be a new idea, judged on 2026 on.

### T-HIST: nfl-v2 on 2006–2016 (run 2026-11-16, scratch `t_hist.py`; replication, not judged)
- Frozen nfl-v2 code and settings, data from 1999 (in memory, nothing loaded into the DB). Replay check on
  2016–25: mean |diff| vs stored nfl-v2 0.0025.
- 2006–2016, n=2,937, vs the nflverse close: spread miss 10.737 vs 10.557; slope +0.081 ± 0.089; calibration 1.23;
  line SD 4.76 vs 5.94; ATS 3+ 51.7% ± 3.5 (n=778), 88% on underdogs; total miss 10.723 vs 10.545.
- Expected beforehand: gap to the close 0.3–0.5 (was 0.18: missed), slope within 2 SE of 0 (held), calibration
  > 1.1 (held). The flat line is structural. 2006–2016 are now the clean judging seasons for NFL tests.
- Loader trap: 12 pre-2011 games have duplicate ESPN ids.

### T-MATCH on clean seasons (run 2026-11-16, scratch `t_match_clean.py`): **passed**
- Same inputs as T-MATCH, trained from 1999, judged once on 2006–2016 (n=2,937). Rule from
  `docs/nfl-audit-2026-11-16.md` section 6.
- Calibration 1.234 → 0.994 (gain 0.227 ± 0.063, 3.6 SE; bar 2.24). Spread miss 10.737 → 10.730 (−0.007 ± 0.030).
  Slope at the close +0.081 → +0.196 (Δ +0.115 ± 0.049). Total miss 10.723 → 10.707. All four conditions hold.
- Info: line SD 4.76 → 5.93 (close 5.94); 3+ picks on underdogs 88% → 67%; ATS 3+ 51.7% → 53.2% ± 3.4 (n=827);
  miss better in 6 of 11 seasons; calibration with 0–2 weeks of data 0.75 (too steep), 1.00–1.07 after.
- Candidate nfl-v3, for accuracy and calibration only. The slope is at the close and was not the test.

### T-QB2: QB value from full careers (run 2026-11-16, scratch `t_qb2.py`): **rejected**
- Careers from 1999, dropbacks faded by seasons old, draft-bucket prior under 300 dropbacks, starter from
  play-by-play. H = 2 seasons and K = 200 chosen on 2003–2010 by next-game error (K at the grid edge, not extended).
- 2011–2025 without 2020 (n=3,827), baseline nfl-v2 trained from 1999: spread miss 10.268 → 10.268 (+0.0005 ± 0.012);
  slope at the close +0.025 → +0.021; total miss 10.748 → 10.757; halves −0.002 (2011–19) and +0.005 (2021–25).
  Fails 3 of 4 conditions. Better in 7 of 14 seasons. No variants.
- Info: play-by-play and nflverse starters differ in 112 team-games since 1999. Rookie priors: round 1 about +0.08
  to +0.14 EPA/dropback above replacement, later picks about +0.03.

### T-OPEN (free data): nfl-v3 at the Monday line (DRAFT 2026-11-17, NOT approved, NOT run)
Replaces the paid version in `docs/nfl-audit-2026-11-16.md` section 6, test 1. Same question: does the NFL model know
anything the Monday market doesn't? No NFL model has been graded at any line other than roughly the close, so these
results are unseen. Seen so far: only how the Monday lines compare with the close (no model involved).

**Lines (fixed now).**
- *Bet time* = Monday 8:00 AM Eastern of game week (our 6:00 AM Mountain `odds_daily` snapshot, so live tracking can
  copy the rule exactly).
- *2018, 2019, 2021, 2022:* the last `line_history.csv` (TeamRankings consensus) spread quote at or before bet time. It must
  be timestamped after 7:00 PM Eastern on the previous Sunday (week 1: no such check). Otherwise it's a stale lookahead
  quote and the game is dropped.
- *2023–2025:* `nfl_line_moves` source `picksfootball`, snapshot `mon`. Its time of day is unknown. If the Monday cell
  is off the board or missing, the game is dropped (no Tuesday fallback; the fallback is reported as information).
- *Close (for line movement):* from the same source as the Monday line, to avoid mixing sources: the last
  `line_history` quote before kickoff, or picksfootball `gameday`. The nflverse close is reported beside it.
- Regular season only. 2020 out. Playoffs and 2026 weeks 1–10 are reported, not judged.
- Expected n: about 7 × 267, minus drops ≈ 1,800 games; about 450–550 3+ gaps.

**Model (fixed now).**
- nfl-v3 code and settings unchanged. Trained from 1999 in memory, as in T-HIST/T-MATCH clean; nothing is loaded into the DB.
- Ratings rebuilt for each game with only games that kicked off before bet time. That leaves out last week's Monday
  night game for the two teams that played in it.
- *Starter (no lookahead):* the team's starter in its previous game. Exception: if he is on IR (`RES`) in a roster week
  before this game, use the QB with the most dropbacks in that previous game other than him. Week 1 uses the previous
  season's last starter, under the same IR rule. The actual-starter version is reported as information only.

**Supported if both hold**, on 2018–25 without 2020. Paired bootstrap of games, 2,000 resamples.
1. The mean line move toward us from the Monday line to the same-source close, on gaps of 3+ at the Monday line, is at
   least 2.24 bootstrap SE above zero.
2. The slope at the Monday line, (result − Monday line) on (our line − Monday line) over all games, is above zero.

**Reported:**
- slope ± SE at the Monday line and at the close
- ATS 3+ and 5+ at the Monday line, at −110 since there are no prices; pushes excluded
- share of picks on underdogs, and results by line on/off 3 and 7
- everything split by era: line_history (2018–22) vs picksfootball (2023–25). If the two eras disagree in sign on
  measure 1, the result is flagged and does not pass.
- the actual-starter version, the nflverse close, playoffs, and 2026 weeks 1–10

**Then:**
- *Supported:* paper-track NFL picks at the live Monday 6:00 AM MT snapshot through 2027, under the college stopping rule
  (section 5C). No real bets on the NFL until that record exists.
- *Not supported:* the NFL tab drops tiers for good. The model stays a display and override tool.
- No variants after the result, including other bet times, other starter rules, other gap sizes or other seasons.

**Power (stated now).** About 1,800 games give a slope SE near 0.085, so the slope can't carry the test by itself.
Measure 1 has the power: in college it was about 0.56 pts at about 8 SE.

**Known weaknesses (accepted now):**
- The two eras use different sources: a consensus with a known time, then one site without a known time of day.
- The Monday line can't be bet at a known price.
- picksfootball's Monday value may sometimes come from later in the day than 8:00 AM.
- If supported, the 2027 paper record is the real test.

**Count.** One judged run. NFL models judged so far: the grid plus T-QB, T-skill, T-CAL, T-MATCH, T-WEEK, T-MATCH
clean, T-QB2. T-LOOK stays parked: its lookahead lines (sbro open 2016–21, picksfootball `open` 2023–26) have no
posting time.

### T-OPEN result (run 2026-11-17, scratch `topen/t_open.py`, 226 s, nothing written to the DB): **supported by the rule; no betting value shown**
Details fixed before the run:
- The points model is trained on the standard nfl-v3 rows (kickoff cutoff, actual starters) from 1999.
- Only the predicted games use bet-time ratings, bet-time QB values and the starter rule.
- IR check = status `RES` in the team's previous roster week.

Judged, 2018–25 regular season without 2020 (n = 1,750 games; 132 line_history games dropped: 84 stale quotes,
48 with no quote before bet time):

| Measure | Result | Bar | Pass |
|---|---|---|---|
| 1. Line move toward us, Monday → same-source close, 3+ gaps (n = 477) | **+0.388 ± 0.073 pts (5.3 SE)** | ≥ 2.24 SE | yes |
| 2. Slope at the Monday line | **+0.040 ± 0.101** | > 0 | yes (0.4 SE) |
| Eras agree in sign on measure 1 | line_history +0.466 ± 0.112, picksfootball +0.314 ± 0.098 | same sign | yes |

Reported (information only):
- **At the Monday line, the results don't follow the line move:**
  - ATS 3+ 50.0% ± 4.5 (n = 466); 5+ 47.2% ± 7.7 (n = 161); 66% of 3+ picks on underdogs.
  - The line moved toward us on 48% of 3+ gaps and away on 30%.
  - Slope by era: +0.086 ± 0.148 (line_history), −0.037 ± 0.142 (picksfootball).
- **By season**, measure 1 was positive in all 7 seasons (+0.25 to +0.55). The slope was negative in 5 of 7.
  ATS 3+ by season: 50.0 / 50.0 / 47.8 / 55.6 / 43.4 / 47.9 / 53.8%.
- **Accuracy 2018–25:** spread miss ours 10.216, Monday line 9.897, close 9.819. Our line SD is 5.78 against 5.83
  for the Monday line, so the line is no longer flat.
- **Starter rule:** it differs from the actual starter in 619 of 4,754 team-games (13%).
  - The actual-starter version (lookahead) gives move +0.673 (9.1 SE), slope +0.249 ± 0.113, ATS 3+ 53.0% ± 4.7.
  - The kickoff-time model gives +0.716, slope +0.275, 53.7%.
  - So most of the lookahead model's apparent value is QB news that becomes known during the week.
- **Other cuts:**
  - nflverse close instead of the same-source close: move +0.368 (4.6 SE).
  - Slope at the same-source close: −0.059.
  - Monday line on 3 or 7: move +0.256, ATS 42.3% (n = 78). Off 3 and 7: +0.416, 51.5% (n = 388).
  - With the Tuesday fallback: move +0.386, slope +0.006.
  - Playoffs 2018–25: n = 65, move +0.06.
  - 2026 weeks 1–10: n = 150, move +0.511 ± 0.215, slope +0.515 ± 0.339, ATS 3+ 56.8% (n = 44).

**Reading.**
- The rule is met, so by the registration nfl-v3 goes to a paper record at the live Monday snapshot through 2027,
  with no real NFL bets.
- The pass rests entirely on measure 1. Results at the Monday line show no edge: slope +0.04 ± 0.10, ATS 50.0%.
  That's the same pattern as college 2026 (CLV positive, ATS 50% at the open).
- **Caveat (after the fact, so it can't change the verdict):** measure 1 can be inflated by noise in the Monday line
  itself. A stale or one-off Monday number corrects toward the true line by the close, and any reasonable independent
  number sits nearer the true line than the noise does. It needs a benchmark before it's read as information the market
  lacked. Candidate follow-up, to be registered before running: the same measure for a no-skill benchmark (e.g. last
  week's close for the same matchup, adjusted for home field) on the same games.

### T-OPEN-B: is the line move more than Monday-line noise? (DRAFT 2026-11-17, NOT approved, NOT run)
**Question.** T-OPEN found the line moves +0.39 pts toward nfl-v3 between Monday and the close, but results at the
Monday line show nothing. If the Monday number is noisy (a stale consensus quote, or a single site's value at an
unknown hour), any sensible line built without that noise will appear to "see the line move toward it". This test
asks whether nfl-v3 knows anything about the move beyond what the market itself said before Monday.

**Benchmark (fixed now): B1, a market-implied line.** It has no football information beyond earlier closing lines.
- *Fit:* least squares of earlier nflverse closing spreads on team ratings plus a home-field term:
  close = R_away − R_home − H·(not neutral). Ridge α = 1, as in `cfb/ratings.py`.
- *Games used:* only games that kicked off before bet time.
- *Weights:* exactly as nfl-v3's ratings (`SETTINGS`: half-life 6 weeks, last season's games at weight 0.5^(age/6)
  with age from `rating_args`, fading to 0 over 12 weeks played). Week 1 uses last season only.
- *Prediction:* B1's spread for the game = R_away − R_home − H (H = 0 at neutral sites).
- B1 never sees our model, the Monday line, results or anything after bet time.

**Games and lines.** Exactly T-OPEN's judged set: the same 1,750 games, Monday lines and same-source closes, 2018–25
regular season without 2020. No new data.

**Main test.** One regression over all 1,750 games, with move = close − Monday line:

  move = a · (ours − Monday) + b · (B1 − Monday) + c

Supported if **a ≥ 2.24 bootstrap SE above zero**. Paired bootstrap of games, 2,000 resamples. That means nfl-v3's
disagreement with Monday predicts the move even after allowing for the market's own earlier view.

**Reported:**
- B1's own measure 1 (move toward B1 on its 3+ gaps), beside nfl-v3's +0.388.
- The same two-gap regression with result − Monday as the outcome (does our gap predict results once B1 is in?).
- Both eras separately; how often B1 and nfl-v3 are on the same side.
- B1's accuracy against the Monday line and the close.

**Expectation, written now.** If Monday-line noise drives T-OPEN, B1's measure 1 will be similar to ours (0.3–0.5)
and *a* will be small. If nfl-v3 adds information, *a* stays clearly positive with B1 in the regression.

**Then (proposed; needs your agreement because it changes what T-OPEN's pass leads to):**
- *Supported:* build NFL paper-tracking at the live Monday snapshot for 2027, as T-OPEN's rule says.
- *Not supported:* don't build it. The NFL tab drops tiers for good, and the model stays a display and override tool.
  T-OPEN's line-move result is recorded as explained by Monday-line noise.
- No variants afterwards: no other benchmarks, weights, seasons or gap sizes.

**Count.** One judged run. NFL judged tests after this: nine.

### T-OPEN-B result (run 2026-11-17, scratch `topen/t_open_b.py`, nothing written to the DB): **supported**
- *Replication first:* the rebuilt game set and lines reproduce T-OPEN exactly (n = 1,750, measure 1 +0.388).
- **Main test:** move = a·(ours − Monday) + b·(B1 − Monday) + c gives **a = +0.087 ± 0.014 (6.1 SE; bar 2.24)**,
  b = −0.020 ± 0.012. Both eras are positive: line_history +0.112 ± 0.021 (5.4 SE), picksfootball +0.061 ± 0.020 (3.1 SE).
- **B1's own measure 1:** +0.103 ± 0.061 (n = 588 3+ gaps), against nfl-v3's +0.388. By era: +0.055 and +0.160.
  The expectation written for the noise explanation (B1 about 0.3–0.5, *a* small) did not happen.
- **Results:** with result − Monday as the outcome, a = +0.032 ± 0.111 and b = +0.015 ± 0.104. Our gap still
  doesn't predict results at the Monday line, but that SE is too large to rule out a modest effect.
- **Other information:**
  - B1 and nfl-v3 pick the same side of the Monday line in 63% of games (72% on our 3+ gaps), with gap correlation 0.45.
  - Spread miss: ours 10.216, B1 10.224, Monday 9.897, close 9.819.

**Reading.** The Monday-to-kickoff move toward nfl-v3 is not Monday-line noise. The market's own earlier view
explains none of it (b ≈ 0), so nfl-v3 anticipates where the market goes during the week, at about 9% of its gap.
What isn't shown is that this turns into wins at the Monday price (slope +0.04 ± 0.10, ATS 50.0%). Per the agreed
consequence, NFL paper-tracking at the live Monday snapshot is built for 2027. The paper record, not these
backtests, decides whether NFL picks are ever bet.
