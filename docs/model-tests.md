# Model tests and rules

Every model change we've tried, the rules each one was judged by, and the result. Most entries are summaries
of `CLAUDE.md` (Model and Backtest sections), which stays the working record. Updated 2026-11-13.

**Contents:** 1. Rules · 2. Current model · 3. Season to date · 4. Tests in order · 5. What's left

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
| Telling 53.4% from 52.4% | ≈ 8,000 needed | |

### The acceptance rule (Tests 4–5; write it down before every test)
Baseline is the current model, 2021–25, 3+ gaps at the **opening** line. A change is accepted only if **all four** hold:
1. Pooled ATS 3+ at open is higher than the baseline.
2. It is at or above the baseline in **at least 4 of 5 seasons**.
3. CLV (3+) pooled is not down by more than 1.0 pt.
4. Spread MAE is not worse.

Write the rule before seeing any result, and never loosen it afterwards. If the main variant fails, don't try
other variants.

### Holdouts and multiple testing
- About 30 variants have been tried (Rounds 1–5, v1–v5, Tests 1–5).
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
  - Per-play efficiency: EPA/play split pass and rush, success rate, explosiveness, points per opportunity,
    garbage time excluded.
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

### v5 backtest by season (3+ gaps)
| Season | ATS at close (n) | ATS at open (n) | Total bias (actual − ours) | Total miss, ours / close | O/U 3+ at close |
|---|---|---|---|---|---|
| 2018 | 50.2% (480) | – | +0.35 | 13.53 / 12.94 | 49.4% |
| 2019 | 53.9% (440) | – | −0.90 | 13.51 / 12.87 | 47.8% |
| 2021 | 49.2% (419) | 52.6% (411) | −0.18 | 13.15 / 12.50 | 48.8% |
| 2022 | 51.5% (487) | 52.2% (433) | +0.67 | 12.76 / 12.17 | 50.1% |
| 2023 | 48.9% (427) | 51.2% (451) | +2.04 | 13.10 / 12.62 | 49.3% |
| 2024 | 51.2% (447) | 54.3% (441) | +1.36 | 13.06 / 12.64 | 51.7% |
| 2025 | 50.4% (448) | 51.7% (454) | +0.74 | 12.80 / 12.42 | 50.1% |
| **All** | **50.8% (3,149)** | **52.4% (2,191)** | +0.62 | 13.13 / 12.60 | **49.6% (2,989)** |

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
| September | 116 | 52.6% | 46.0% |
| October | 137 | 52.6% | 45.8% |
| November | 26 | 42.3% | 37.0% |

**Reading it:** the market moves toward us, but only part of the way. A gap still there at kickoff loses, and
5+ gaps are worst, usually because of news the model doesn't have.

**Fading the model** (betting the other side) at close: 49.2% over 2018–25 (n=3,149), so it loses money. Only
2026 looks better (55.6%, ±5.2), and 2026 is used up. Not a strategy.

**Live record (`pick_log`, from 2026-11-12):** Plays 0–1 (USF +4 vs Memphis, Nov 12).

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
| Rev | 11-12 | Outside review (0 calls) | Findings | Our miss SD 16.3 vs market 15.5. Gaps 3+ at close: 50.3% (−2.9% ROI). Bowls 53.6% (n=97); CFP 46% (n=13). Key numbers: 3 = 9.4%, 7 = 7.9% of margins. |
| T1 | 11-12 | Weeknight MAC/SBC/C-USA, 3+ at open | **Kept as a hypothesis** (tag and track) | 2021–25 74–44; 2026 11–9; pooled 61.6% (lower bound 53.5%). |
| T1 | 11-12 | FCS opponents | **Rejected** | 2021–25 131–95, 2026 37–45 (45.1%). |
| T2 | 11-12 | Weight last season's games by returning production | **Rejected** | Weeks 0–5 miss moved ≤ 0.006; ATS 52.29–52.51%; not lower in only 2 of 5 seasons. Test 3 was skipped because its precondition failed. |
| T4 | 11-13 | Coach career record vs our line (K=100) | **Rejected** | ATS 52.40 → 52.86% (n=2,079), but at or above baseline in only 3 of 5 seasons (+0.7/−0.9/−0.4/+0.4/+2.3). CLV 61.1 → 61.8. Spread miss 12.77 → 12.70, better in all 5 seasons. |
| T4 | 11-13 | Team vs same opponent (K=5) | **Rejected** | 52.43%, 2 of 5 seasons, CLV −1.7, miss worse. |
| T4 | 11-13 | Coach vs same opposing coach (K=5) | **Rejected** | 51.93%. |
| T5 | 11-13 | Fumble-recovery luck (play-by-play) | **Rejected** | ATS 52.43 → 52.25%, 1 of 5 seasons, CLV 61.2 → 60.8, miss 12.83 unchanged. Coefficients tiny and wrong-signed. |

**Don't retry these without new information:** QB-change detection, recent-season weighting, bias
correction, SP+ priors, portal, schedule spots, drive metrics, returning-production weighting, head-to-head,
fumble luck.

### Lessons
- **Information the market already uses** (SP+, schedule, last week's starter) makes us more accurate and
  takes away edge: we agree with the market more.
- **Our edge, if any, comes from the recency-weighted EPA ratings,** and it shows up at the opening line, not
  the close.
- **The 1-point gap to the closing line (12.5 vs 11.5) is mostly news:** injuries, QB changes, motivation.
  Overrides and the Check news flag are aimed at that gap, not another model feature.
- **Data checks before multi-call pulls:**
  - CFBD `conference` must be the abbreviation; a full name returns an empty list and still costs a call.
  - Read parameter descriptions, not just the `required` flag.
  - Play-by-play fumble counts are about 25% low in 2021–23, so check each stat by season.

---

## 5. What's left
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
