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
repeats it for the backtest rates, so change both together.

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
- **Confirmed:** Δslope ≥ 1.645 × paired SE, AND spread MAE better, AND ATS 3+ at open not down by more than
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
