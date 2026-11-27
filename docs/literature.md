# Betting-market efficiency: literature review and 2027 challenger candidates

Stage 1, research and planning only (2026-11-26). No model runs, no tests on historical data, no CFBD or FTN calls,
nothing written to the DB. The only number computed from our data is one standard deviation used for a power estimate
(NFL Monday → game-day total move, picksfootball 2023–26: SD 1.46 pts, n = 955), as section 8.1 of plan-2027.md did.
The shortlist built from this review is in plan-2027.md section 9 (proposed, not registered).

## How to read the entries

- **Access** says what was read. **FT** = full text read (extracted from the PDF). **AB** = abstract or index page only.
  **SS** = secondary summary only (press release, citing paper, thesis). AB and SS entries carry lower confidence. Most
  journal papers here are paywalled (SAGE, Taylor & Francis, Springer, Elsevier, Emerald all refused or redirected to a
  login), so most entries are AB. Where an exact rule or sample size is missing, the entry says so. Nothing is filled in
  from memory.
- **Beat vig?** refers to the paper's own results, against the usual 52.4% break-even at −110 for spreads and totals.
- **Market inputs?** If the signal uses a betting line, it can only be a rule-based challenger (kind b, like B1), never
  a feature of v6 or nfl-v3. The no-market-inputs rule is unchanged.
- **What our models already use.** v6 = v5 + T1 + T-OCDC: opponent-adjusted per-play efficiency (EPA/play, pass and rush
  EPA, success rate, explosiveness, plays, points) with 4-week recency weighting, last season at 0.25 × fade, talent /
  returning production / new head coach / new OC-DC as faded priors, mid-season head-coach change, FCS flags, home
  field. No weather, travel, rest, TV, poll or market input. nfl-v3: the same per-play ratings (nflverse EPA), starting-QB
  adjustment, matchup rows, home field. No weather, rest, bye, division, travel or market input.
- **Data we hold:** CFBD (cached responses for 16 endpoints, incl. `/lines` 2016–26 with open/close for 2021+, `/venues`,
  `/coaches`, `/player/portal`, `/player/returning`), our Odds API snapshots (spreads/totals from Nov 2026, moneylines from
  2026-11-18, timestamped), nflverse (free re-download: schedules with `div_game`, rest days, roof, observed
  temperature/wind, closing lines; play-by-play; injuries; FTN charting 2022+), picksfootball / sbro NFL line histories,
  and our own weather forecast log (college from 2026-11-11, NFL from 2026-11-23, both timestamped).

---

## 1. College football

### C1. Salaga & Howley (2024): weather and NCAA football totals
- **Citation:** Salaga, S. & Howley, (first name not captured). "The impact of weather on betting outcomes and market behaviour
  in the NCAA football totals market." *Applied Economics Letters* 31(8), 779–782 (online 2022).
  [IDEAS](https://ideas.repec.org/a/taf/apeclt/v31y2024i8p779-782.html). **Access:** AB (T&F 403).
- **Claim:** Weather variables significantly predict totals results relative to the market total, but they do **not**
  predict how much the total moves. The authors take this to mean the market under-uses weather, and they show that
  simple strategies built on three weather variables profit.
- **League / years / n / market:** college; years and n not in the abstract; totals.
- **Beat vig?** Yes per the abstract ("illustrate the ability to profit"); rates not given.
- **Decay?** Too recent for a retest. Our own Test 7 (2021–25 archived forecasts, in the model) found nothing: total slope
  +0.97 SE, O/U 3+ 50.0%. The 2026-11-11 research found unders winning only in extremes (gusts 30+ mph: 57.8%, n = 205;
  rain 0.1–0.3 in: 55.5%, n = 183), using observed weather, so those figures are optimistic.
- **Market inputs?** The rule bets the total, so the outcome is judged against the line. The signal itself (weather) is
  not a market input.
- **Testable with our data?** Live only, from our forecast log (point-in-time, since 2026-11-11). Historical forecasts
  for 2021–25 were already used by Test 7, so re-running on those seasons isn't allowed (plan-2027 §7.6). Cost 0.
- **Overlap:** v6 has no weather. The page shows a forecast ⚠ flag (display only). The paper's version is "a few weather
  variables against the market", the same idea as our H-WX draft. The new part is the claim that the line doesn't move on
  weather, which our odds snapshots plus forecast log can check directly.
- **Verdict: candidate challenger** (→ C-WX). The prior is a recent peer-reviewed claim, our data is point-in-time, and
  the cost is 0. Our own in-model test was negative, so expect small effects.

### C2. Bennett (2019): holdover bias in season openers
- **Citation:** Bennett, R. W. "Holdover Bias in the College Football Betting Market." *Atlantic Economic Journal* 47(1),
  103–110. [IDEAS](https://ideas.repec.org/a/kap/atlecj/v47y2019i1d10.1007_s11293-019-09611-y.html). **Access:** AB.
- **Claim:** In their next season's first game, last season's final AP top 10 are overvalued. Betting against them
  (especially against non-Power 5 opponents) wins significantly more than 52.4%. Teams ranked 11–25 are priced
  efficiently.
- **League / years / n / market:** college; 2008–2016 (per a citing summary); the top-10 n is not in the abstract (about
  10 games a season at most); spreads.
- **Beat vig?** Yes (in-sample; no out-of-sample test mentioned).
- **Decay?** No retest found. It builds on Fodor et al. (2013), who found NFL holdover bias (N20).
- **Market inputs?** No: the signal is last season's poll. The bet is ATS.
- **Testable?** Needs the AP poll: CFBD `/rankings?year=` is not cached. 1 call per season (11 calls for 2016–26, or 1 call
  for the 2026 final poll before 2027 week 0). No point-in-time issue (the final poll is fixed in January).
- **Overlap:** strong. v6 starts each team from last season's games (0.25 × fade), talent and returning production,
  and never sees the poll. If the market over-weights the poll, v6 should already disagree with it in these games.
- **Verdict: diagnostic only.** About 10 games a season can't be judged. Tag them and report v6's gap direction and
  result (→ C-HOLD, reported).

### C3. Arscott (2023): censoring bias in college totals
- **Citation:** Arscott, R. "Market Efficiency and Censoring Bias in College Football Gambling." *Journal of Sports
  Economics* 24(5), 664–689. [IDEAS](https://ideas.repec.org/a/sae/jospec/v24y2023i5p664-689.html); SSRN 4197428
  (working paper dated 2022-08-22; the user's copy is `docs/ssrn-4197428.pdf`). **Access:** FT (SSRN version; the
  journal version wasn't compared).
- **Claim:** the spread and the game total together imply each team's expected points. Those expectations are unbiased
  once you allow for scores being censored at zero, but the market's totals don't account for that censoring. For a
  team expected to score little, the error distribution is skewed right, so the game total runs low exactly where the
  underdog's implied score is near zero. Bet the **over** there. (The paper's "team totals line" means the game
  over/under, not posted team-total markets.)
- **The rule, exactly:**
  - S = |closing spread|, T = closing total.
  - Implied underdog points d = (T − S) / 2 and favourite points f = d + S (Eqs. 6–7).
  - bias(μ, σ) = σ·φ(μ/σ) − μ·Φ(−μ/σ), with σ_dog = 11.280 and σ_fav = 11.941 (Tobit, Table 3).
  - biasTotals = bias(f, σ_fav) + bias(d, σ_dog) (Eq. 13).
  - **Bet the over when biasTotals > 1.00** (stricter cut: > 1.75).
  - In practice biasTotals > 1 means d ≲ 11 points when the spread is large (d = 10.5 with a 30-point spread gives 1.07).
- **League / years / n / market:**
  - College, The Goldsheet closing lines: spreads 1992–2017, totals from 1996, 13,276 games with both lines (underdog
    perspective).
  - About 5.2% of games qualify (~43 a season at 850 games). Totals only.
  - The same model on spreads finds nothing (biasSpread coefficient 0.002 ± 0.027).
- **Beat vig?** In-sample, yes:
  - bias > 1.00: 691 bets, **55.72%**, unit return +6.37%; vs 52.38%, p = 0.079.
  - bias > 1.75: 223 qualifying games, 59.19%, +13.0%.
  - 5-fold cross-validation, **random folds, not time-ordered**: 51.68%, 56.41%, 55.83%, 54.11%, 58.14% (117–163 bets per
    fold). σ and the probit slope are stable across folds.
  - There is no test on later seasons.
- **Decay?** No retest. The sample ends in 2017, so **2018–2025 are clean post-sample seasons** for us, and the paper
  appeared in 2022–23. College totals have risen since (median ~51–54 in the paper's years), so fewer games qualify now.
- **Market inputs?** **Yes, only market inputs.** Rule-based challenger only (kind b).
- **Testable?** Yes, at 0 cost: CFBD `/lines` (closing spread and total, 2018–25 cached; open too for 2021+) and our
  snapshots (2026+). **No posted team totals are needed.**
- **Overlap:** none. v6 can't use lines. v6's own total in these games is a natural side report (v6 under-predicted
  2026 totals by ~2 points).
- **Verdict: candidate challenger** (→ C-CENS). It is the strongest recent claim in the college literature, with an
  exact rule and 0 cost. Its weaknesses: in-sample only (random-fold CV isn't out-of-time), and p = 0.079 against
  break-even even in-sample.

### C4–C6. The totals "over" bias and its decay (worked example)
- **C4 Paul & Weinbach (2005):** "Bettor preferences and market efficiency in football totals markets." *Journal of
  Economics and Finance* 29(3), 409–415. [IDEAS](https://ideas.repec.org/a/spr/jecfin/v29y2005i3p409-415.html).
  **Access:** AB. **Claim:** overs are over-bet in college (and arena) football totals. The authors tie the size of the
  bias to the mix of informed and uninformed bettors and to bet limits, and they expected it to fade as information
  spread. College; years not in the abstract; totals; the abstract reports the bias as profitable.
- **C5 Weinbach & Paul (2009):** *International Gambling Studies* 9(1), 55–66 (title not captured).
  [IDEAS](https://ideas.repec.org/a/taf/intgms/v9y2009i1p55-66.html). **Access:** SS. Split by TV coverage: a slight,
  non-significant over bias overall, significant only for nationally televised games. This was the first sign of decay.
- **C6 Francisco & Moore (2018):** comment on C4, *Journal of Economics and Finance* 42(4).
  [Springer](https://link.springer.com/10.1007/s12197-018-9437-y). **Access:** AB. **Claim:** college totals
  2003–2015 are efficient: neither "always over" nor "always under" is profitable, and "the market has largely
  corrected itself." A University of West Georgia newsletter shows the over at about 50% in 2003–05
  ([PDF](https://www.westga.edu/~bquest/2008/football08.pdf), SS).
- **What the pair teaches:**
  1. A naive bias published from 1990s–early-2000s data was gone, or never pooled-significant, in the next decade.
  2. Where it survived (national TV), it survived in the slice that recreational money reaches most.
  3. The retest's sample (2003–15) overlaps the original's era, so "decay after publication" and "never robust" can't be
     told apart.

  Each later candidate is treated the same way: assume half or less of the published effect, prefer post-publication
  seasons, and never judge on the paper's own years.
- **Our data:** 2026 totals ran *over* the market (+1.07), and 2023 too (+1.28): the opposite of the 2005 bias.
- **Market inputs?** yes (the total itself). **Overlap:** none. **Verdict: not usable** (decayed). As a reported
  diagnostic, the naive over rate at the bettable close already falls out of `report_2027.py`.

### C7. Sinkey & Logan (2010): favorites overpriced, lines remember covers
- **Citation:** Sinkey, M. & Logan, T. D. "Betting Markets and Market Efficiency: Evidence from College Football."
  AEA 2010 meetings paper (Dec 2009). [PDF](https://www.aeaweb.org/conference/2010/retrieve.php?pdfid=406).
  **Access:** FT.
- **Claim:**
  - Favorites are systematically overpriced, and home teams are underpriced (home teams beat the line 2.05 points of
    probability more often).
  - Strong-tradition favorites are 6.38 points of probability less likely to cover.
  - Books add over 2 points to a team's line after it beats the spread, and over 7.5 points after three straight covers.
    The authors read this as shading against bettors' "hot hand" beliefs.
  - $1,000 bet on underdogs in prominent games returns $1,116.99 in expectation before the vig.
- **League / years / n / market:** college, 1985–2003, >11,000 games, spreads.
- **Beat vig?** They report "economic inefficiency" and profitable conditional strategies (fading strong-tradition
  favorites, backing teams vs weak opponents). Exact post-vig rates are not stated in the parts read.
- **Decay?**
  - Their 2014 follow-up (C8) extends the data to 2008.
  - Salaga & Brown (2018, C11) find no across-game momentum overreaction in the line.
  - Bennett (2021, C10) finds momentum *continuation* only in non-Power 5 games.
  - This is mixed evidence, and the sample ends 20+ years ago.
- **Market inputs?** Yes: favorite / underdog status and past ATS results. Rule-based only.
- **Testable?** Yes from CFBD `/lines` + `/games` (cached, 0 calls). The "strong tradition" list is the authors' own.
- **Overlap:** v6's ratings use results (EPA), not ATS margins. A team that covered three straight has better ratings
  in v6 anyway, so part of the "line memory" is real form.
- **Verdict: diagnostic only.** The pre-2004 era and the hot-hand claim overlap C10 and our Test L.

### C8. Sinkey & Logan (2014): does the hot hand drive the market?
- **Citation:** *Eastern Economic Journal* 40(4), 583–603.
  [IDEAS](https://ideas.repec.org/a/pal/easeco/v40y2014i4p583-603.html). **Access:** SS.
- **Claim:** extends C7 to >14,000 games, 1985–2008. Hot-hand beliefs shape line setting.
- **Market inputs?** yes. **Testable?** yes (0 calls). **Overlap / verdict:** as C7. **Diagnostic only.**

### C9. Coleman (2017): team travel effects
- **Citation:** Coleman, B. J. "Team Travel Effects and the College Football Betting Market." *Journal of Sports
  Economics* 18(4), 388–425. [IDEAS](https://ideas.repec.org/a/sae/jospec/v18y2017i4p388-425.html). **Access:** AB.
- **Claim:** spreads and totals are "an inaccurate and inefficient processor" of travel. The variables are time zones
  crossed, direction, distance, and changes in temperature, elevation and aridity. The most consistent case is a
  late-season underdog with a one-hour time-zone deficit against its opponent.
- **League / years / n / market:** college; years and n not in the abstract; spreads and totals.
- **Beat vig?** Implied for the late-season underdog cut; rate not given.
- **Decay?** No retest found.
- **Market inputs?** The headline cut uses underdog status (a line). Travel itself is not a market input.
- **Testable?** Yes at 0 calls: stadium coordinates are in cached `/teams` and `/venues`, and time zones can be derived
  offline.
- **Overlap:** our Round 3(c) put schedule spots into the model (travel km, time zones, short week, second straight road
  game). Accuracy rose, ATS and CLV fell: priced in. The paper's cut (late season × underdog × one zone) is narrower than
  what we tested.
- **Verdict: diagnostic only.** Already tested in-model and rejected. The narrow cut is ~20–40 games a season: tag only.

### C10. Bennett (2021): next-game reaction to mispriced lines
- **Citation:** Bennett, R. W. "Next game reaction to mispriced betting lines in college football." *Applied Economics
  Letters* 28(12), 1006–1009. [EconPapers](https://econpapers.repec.org/RePEc:taf:apeclt:v:28:y:2021:i:12:p:1006-1009).
  **Access:** AB.
- **Claim:** backing teams that greatly beat the spread last game, and fading teams that badly failed to cover, wins
  significantly more than half the time overall. The effect is concentrated in games between two non-Power 5 teams
  (54.23%) and absent in Power 5 games. Bennett reads this as an information gap: news reaches lines more slowly for
  less-watched teams.
- **League / years / n / market:** college, 2006–2018 (citing summary), n not in the abstract, spreads.
- **Beat vig?** Yes in the non-Power 5 slice (54.23% > 52.4%).
- **Decay?** No retest found.
- **Market inputs?** **Yes** (last game's ATS margin). Rule-based only.
- **Testable?** Yes, 0 calls (CFBD lines + scores; our snapshots for 2026+).
- **Overlap:**
  - It points the opposite way from our **Test L** (supported 2026-11-18): the opener *over*-reacts to last week's luck
    (actual − deserved margin), and the line corrects toward us by the close.
  - Bennett says big ATS winners *keep* winning ATS (the market under-reacts) in G5-vs-G5 games.
  - The two can both hold: an ATS margin mixes luck (which Test L says is over-priced) with real form (which the market
    may under-price when attention is low).
  - It also connects to Test 1 (weeknight MAC / Sun Belt / C-USA, kept as a hypothesis).
- **Verdict: candidate, reported only** (→ C-G5ATS). One season can't judge it, but it should be logged beside
  Test L's X.

### C11. Salaga & Brown (2018): momentum and its perception
- **Citation:** "Momentum and betting market perceptions of momentum in college football." *Applied Economics Letters*
  25(19), 1383–1388. [IDEAS](https://ideas.repec.org/a/taf/apeclt/v25y2018i19p1383-1388.html). **Access:** AB.
- **Claim:** no profitable momentum betting, and the line does not systematically over-react to streaks.
- **Years / n:** not in the abstract; regular season; spreads. **Beat vig?** no.
- **Market inputs?** yes (ATS streaks). **Overlap:** as C7 / C10. **Verdict: diagnostic only.** It is the counterweight
  to C7, C8 and C10.

### C12. Cox, Schwartz, Van Ness & Van Ness (2021): momentum in bowls
- **Citation:** *Journal of Sports Economics* 22(3), 251–273.
  [IDEAS](https://ideas.repec.org/a/sae/jospec/v22y2021i3p251-273.html). **Access:** AB.
- **Claim:** regular-season vs bowl spreads. The market is mostly efficient on covers, but it processes momentum badly,
  especially negative momentum, by more than transaction costs.
- **Years / n:** not captured. **Market inputs?** yes.
- **Overlap:** v5 / v6 exclude bowls from the coach-change term. Our bowls ran 53.6% (n = 97), CFP 46% (n = 13): too
  few to judge.
- **Verdict: diagnostic only** (bowls are ~40 games a season).

### C13. Fair & Oster (2007): ranking systems vs the line
- **Citation:** "College Football Rankings and Market Efficiency." *Journal of Sports Economics* 8(1), 3–18 (Cowles
  DP 1381). [IDEAS](https://ideas.repec.org/a/sae/jospec/v8y2007i1p3-18.html). **Access:** AB.
- **Claim:** an optimal blend of computer and poll rankings predicts better than any single system, but adds no
  information beyond the closing Las Vegas spread.
- **Market inputs?** no (rankings), judged against the close. **Overlap:** v6 is a ranking system of this kind.
- **Verdict: diagnostic only.** It is background for our finding that nothing is left at the close (v5 slope at close
  +0.015 ± 0.037).

### C14. Durham & Perry (2008): sentiment and college point spreads
- **Citation:** "The Impact of Sentiment on Point Spreads in the College Football Wagering Market." *Journal of
  Prediction Markets* 2(1), 1–27. [IDEAS](https://ideas.repec.org/a/buc/jpredm/v2y2008i1p1-27.html). **Access:** AB/SS.
- **Claim:**
  - Uninformative expert picks still move spreads during the week.
  - So do recent ATS form, major-conference status and fan avidity.
  - The distortion is too small for a profitable strategy.
- **Market inputs?** the moves are market data. **Overlap:** our line-move slope measures the same intra-week path.
- **Verdict: diagnostic only.** It supports keeping line-move (CLV) and result scorecards separate (section 3.2).

### C15. Paul and co-authors (2026): betting volume and TV ratings
- **Citation:** Syracuse / Coastal Carolina study with R. Paul as co-author, reported by
  [Covers, 2026-08-21](https://www.covers.com/industry/syracuse-university-researchers-find-strong-link-between-college-football-betting-tv-ratings-aug-21-2026).
  **Access:** SS (industry news). Venue unknown, low confidence.
- **Claim:** pre-game betting volume is strongly related to viewership, and the network carrying the game affects both.
- **Use:** it supports **TV network as a low-attention proxy** for college (paired with Krieger & Davis for the NFL, N15).
- **Verdict: diagnostic only.** Start collecting broadcast networks (section 4).

### C16. Topics the user named that have no peer-reviewed work
- **Transfer portal / returning production:** only practitioner pieces (Action Network's TARP, Connelly's returning
  production). Our Round 3(b) portal test was noise (~0.1 pt/SD, CLV flat or down). Returning production is already a v6
  prior. **Not usable** beyond what we have.
- **Interim / fired coaches:** only media ATS counts (e.g. bowl interims 29–31–1). Our v5 coach-change feature is
  better evidence than anything published.
- **Pace / tempo and totals:** practitioner only. v6 already rates `plays` (pace).
- **Late kickoffs ("after dark"), weekday MACtion:** nothing peer-reviewed beyond C5 / C15 (TV exposure) and Sinkey &
  Logan's media-market argument. Our Test 1 (weeknight G5) is the only test.
- **Early season in general:** C2 (holdover) is the only peer-reviewed item. Our Test 2, Round 3(a) and EARLY-1 already
  cover early-season pricing.

---

## 2. NFL

**Since-2015 NFL literature is thin.**
- Peer-reviewed papers whose samples reach past 2015 are few: Shank 2018 / 2019 (to 2016), Tuttle et al. 2024 (to 2016),
  Krieger & Davis 2024 (to 2021), Lopez & Bliss 2024 (to 2023), Paul & Weinbach 2021 (2020 only) and Nofsinger & Shank 2023.
- Most of what covers 2015–2025 is **student theses**: Nuutinen 2025, Skinner 2022, Oswald 2022, Claremont theses.
  They broadly find spreads efficient.
- Weather, key numbers, injuries and international games since 2015 have **no peer-reviewed betting-market study**
  that I found.

### N1. Gray & Gray (1997): NFL efficiency with a probit, momentum effects
- **Citation:** "Testing Market Efficiency: Evidence from the NFL Sports Betting Market." *Journal of Finance* 52(4),
  1725–1737. [IDEAS](https://ideas.repec.org/a/bla/jfinan/v52y1997i4p1725-37.html). **Access:** AB / SS.
- **Claim:**
  - Probit models of cover probability on home-underdog status and recent vs long-run form gave significant in-sample
    profits, with mixed out-of-sample results.
  - The documented inefficiencies "tend to dissipate over time."
- **League / years / n / market:** NFL, 1976–1994, spreads.
- **Beat vig?** In-sample yes; out-of-sample inconsistent.
- **Decay?** Yes:
  - Vergin & Sosik (1999, 1981–96) and a Sacramento State paper find the home-underdog bias gone in the regular season.
  - Dare & Holland (2004) find no momentum effect and a weaker home-underdog effect.
- **Market inputs?** yes. **Testable?** yes (nflverse closes, spreadspoke 1966+; 0 cost).
- **Overlap:** our NFL situations scan (2026-11-16) covered similar ground.
- **Verdict: not usable.** Decayed.

### N2. Levitt (2004): bookmakers shade lines toward bettor biases
- **Citation:** "Why are gambling markets organised so differently from financial markets?" *Economic Journal*
  114(495), 223–246. [PDF](https://www.stat.berkeley.edu/users/aldous/157/Papers/Levitt_Gambling_2004.pdf).
  **Access:** FT.
- **Claim:** bookmakers don't balance action. They set prices that exploit bettors' preference for favourites (and,
  less, visiting teams), raising gross margins 20–30%.
  - In the 2001–02 contest data (~20,000 wagers, 285 bettors, 236 games), visiting favourites covered 47.8%, home
    favourites 49.1%, and **home underdogs 57.7%**.
  - Over 1980–2001 (~5,000 games) favourites cover under 50% (rejected at about the 1% level).
  - Lines are distorted "as much as possible without allowing a simple strategy of always betting on underdogs to become
    profitable": bettors win 49.45% under the observed spreads.
- **Beat vig?** Only home underdogs in the one contest season. Blind underdogs don't beat the vig by design.
- **Decay?** Home underdogs: see N1 (gone by the late 1990s in most retests). The "shade toward the popular side" idea
  is still supported by Humphreys et al. (N3) and Paul & Weinbach (N4, N5).
- **Market inputs?** yes (side of the line).
- **Relevance:** which side is mispriced. If books shade toward favourites, a model gap on the underdog side is partly
  that shade. Our NFL audit found nfl-v2's 3+ gaps were 87% underdogs (50.9% vs 51.0% for every underdog, blind).
- **Verdict: diagnostic only.** Keep reporting our picks against the blind same-side baseline (dog/fav × home/away).

### N3. Humphreys, Paul & Weinbach (2013): bettor biases and the home-underdog bias
- **Citation:** "Bettor Biases and the 'Home-Underdog' Bias in the NFL." *International Journal of Sport Finance* 8(4),
  294–311. [IDEAS](https://ideas.repec.org/a/jsf/intjsf/v8y2013i4p294-311.html). **Access:** AB.
- **Claim:** with actual betting-percentage data, bettors predictably back the best teams, and books do not follow the
  balanced-book model. This is a different cause for the home-underdog bias than Dare & Dennis's scoring explanation,
  which a newer sample contradicts.
- **Market inputs?** yes (betting shares). **Testable?** no: we have no betting-percentage data (paid feeds only;
  no point-in-time history).
- **Verdict: diagnostic only.**

### N4. Paul & Weinbach (2011): betting against public sentiment
- **Citation:** *Applied Economics Letters* 18(2), 193–197 (Levitt-hypothesis tests; title per IDEAS listing).
  [EconPapers](https://econpapers.repec.org/RePEc:taf:apeclt:v:18:y:2011:i:2:p:193-197). **Access:** SS.
- **Claim:** fading the side with most of the bets was profitable for NFL spreads, not totals.
- **Testable?** no (no betting-share data). **Verdict: not usable.**

### N5. Paul & Weinbach (2021): the 2020 season
- **Citation:** *Journal of Prediction Markets* (2021), "Revisiting the Balanced Book Hypothesis – Bettor Preferences and
  Results in the NFL." **Access:** SS.
- **Claim:** balanced books rejected for 2020. Bettors preferred road favourites, big favourites, and the over at the
  highest totals.
- **Testable?** no (betting shares). **Verdict: not usable.** It confirms that the Levitt pattern persists in a recent
  season.

### N6. Borghesi (2007): home-team weather advantage
- **Citation:** "The home team weather advantage and biases in the NFL betting market." *Journal of Economics and
  Business* 59(4), 340–354. [IDEAS](https://ideas.repec.org/a/eee/jebusi/v59y2007i4p340-354.html).
  **Access:** SS (a University of Florida press account only; no abstract on IDEAS).
- **Claim (press):** when game-day temperature is far below what the visitor is used to, home advantage is 1–4 points
  larger than expected. Bettors under-value this, so home underdogs in those games profit.
- **League / years / n:** NFL, years not captured; spreads.
- **Decay?** No retest found. Borghesi's own 2007 *Applied Economics* paper ties the home-underdog effect to late season.
- **Market inputs?** The rule uses underdog status. Temperature itself is not a market input.
- **Testable?** yes. nflverse has observed temperature; our forecast log covers 2026-11-23+ only.
- **Overlap:** nfl-v3 has no weather and one home-field coefficient.
- **Verdict: diagnostic only.** Late-season cold-weather home dogs are a handful of games a season.

### N7. Borghesi (2008): weather biases in NFL totals
- **Citation:** "Weather biases in the NFL totals market." *Applied Financial Economics* 18(12), 947–953.
  [IDEAS](https://ideas.repec.org/a/taf/apfiec/v18y2008i12p947-953.html). **Access:** AB.
- **Claim:** heat, wind and rain cut scoring and bettors under-estimate it. A strategy on expected weather has an
  out-of-sample win rate significantly above 52.38%.
- **League / years / n / market:** NFL, 1984–2004, n not in the abstract, totals.
- **Beat vig?** yes (out-of-sample).
- **Decay?** No peer-reviewed retest after 2004 found. N8 points the same way. Practitioner pieces say wind is now priced
  quickly (unverified).
- **Market inputs?** no for the signal; the bet is on the total.
- **Testable?**
  - Live: our NFL forecast log, but it starts on the **Tuesday** of game week, so there is no forecast at the Monday
    6 AM bet time (a gap to close, section 4).
  - Historical: nflverse observed temp/wind (hindsight weather, like the 2026-11-11 college research).
  - Cost 0.
- **Overlap:** nfl-v3 has no weather.
- **Verdict: candidate challenger** (→ N-WX, judged on line movement, which passes the power check; section 9.3 of
  plan-2027).

### N8. "The Impact of Atmospheric Conditions on Actual and Expected Scoring in the NFL"
- **Citation:** authors and venue not confirmed (likely *International Journal of Sport Finance*;
  [ResearchGate](https://www.researchgate.net/publication/317218823_The_impact_of_atmospheric_conditions_on_actual_and_expected_scoring_in_the_NFL)).
  **Access:** AB (publisher page 404).
- **Claim:** humidity significantly explains actual minus market total. Simple humidity and wind strategies reject
  efficiency. High humidity is linked to more scoring than expected (through the run game).
- **Testable?** humidity is not in nflverse. Open-Meteo archive (free, hourly) can supply it.
- **Verdict: diagnostic only.** The citation is unverified, and humidity is a novel, unreplicated variable.

### N9. Paul & Weinbach (2002): NFL totals 1979–2000
- **Citation:** *Journal of Sports Economics* 3(3), 256–263.
  [IDEAS](https://ideas.repec.org/a/sae/jospec/v3y2002i3p256-263.html). **Access:** SS.
- **Claim:** the under wins more than half the time, but a fair bet can't be rejected overall. Some high-total cuts do
  better.
- **Verdict: not usable** (old, totals bias not robust). Context for N10.

### N10. Shank (2018): "Is the NFL betting market still inefficient?"
- **Citation:** *Journal of Economics and Finance* 42(4), 818–827.
  [IDEAS](https://ideas.repec.org/a/spr/jecfin/v42y2018i4d10.1007_s12197-018-9431-4.html).
  **Access:** none (Springer login, CORE 403). The claims below come **only from the user's brief** and are unverified.
- **Claim (brief):** overs win when the closing total is very small or very large, and so do home teams that went over in
  previous games.
- **Market inputs?** yes (closing total, past O/U results). Rule-based only.
- **Testable?** yes (nflverse closes + scores; picksfootball Monday totals 2023+).
- **Power:** extreme-total cuts are ~15–20% of games (~45 a season): one-season SE ≈ 7.5 pp.
- **Verdict: diagnostic only.** Unread, and the cut is too small to judge in one season.

### N11. Shank (2019): divisional rivals
- **Citation:** "NFL betting market efficiency, divisional rivals, and profitable strategies." *Studies in Economics
  and Finance* 36(4), 567–580. [IDEAS](https://ideas.repec.org/a/eme/sefpps/sef-11-2018-0354.html). **Access:** AB.
- **Claim:** home teams facing division rivals cover less, and division games go under more often (books under-price
  familiarity). Combined with older inefficiencies, an out-of-sample model won nearly 57% on spreads and totals.
- **League / years / market:** NFL, 2003–2016, spreads and totals.
- **Beat vig?** yes (out-of-sample, combined model).
- **Decay?** Our own scan (2026-11-16, 1999–2025 closes): division underdogs 52.0% ± 1.9 (n = 2,611) but not steady by
  era (50.1% in 2010–19); division unders 51.7%. The user parked division games for that reason.
- **Market inputs?** home / underdog side, yes. `div_game` itself is not a market input.
- **Testable?** yes (nflverse `div_game`, free).
- **Power:** ~96 division games a season → SE ≈ 5.1 pp; plausible effect ≤ 2 pp.
- **Verdict: not usable for 2027.** Our 1999–2025 look already used the history, and it fails the power check
  (→ "judge with more seasons" only if the user un-parks it).

### N12. Nofsinger & Shank (2023): momentum trading in NFL totals
- **Citation:** "Momentum Trading in the NFL Gambling Market." *Finance Research Letters* 55(PB), 104006.
  [IDEAS](https://ideas.repec.org/a/eee/finlet/v55y2023ipbs1544612323003781.html). **Access:** AB.
- **Claim:** at the aggregate weekly level, bettors chase totals momentum. Backing the over after momentum loses, and
  the under is profitable.
- **Market inputs?** yes (past O/U results). **Overlap:** N10.
- **Verdict: diagnostic only.**

### N13. Miller & Rapach (2013): intra-week evolution of NFL lines
- **Citation:** "An intra-week efficiency analysis of bookie-quoted NFL betting lines in NYC." *Journal of Empirical
  Finance* 24, 10–23. [IDEAS](https://ideas.repec.org/a/eee/empfin/v24y2013icp10-23.html). **Access:** AB (title only).
  The results on outlaw / open / close efficiency were **not readable**.
- **Relevance:** the study design is ours: the same game priced at several points in the week. It supports measuring
  Monday → close separately from close → result.
- **Market inputs?** yes. **Verdict: diagnostic only** (method background, section 3).

### N14. Tuttle, Pion & Bumpass (2024): NFL moneylines 2007–2016
- **Citation:** "An Examination of the Money Line Market for National Football League Games." *Journal of Economic
  Insight* 50(2), 87–117. [Journal page](https://journalofeconomicinsight.com/index.php/joei/article/view/1335).
  **Access:** AB.
- **Claim:**
  - Opening and closing moneylines are both inefficient, and the close fails to remove it.
  - There is a reverse favourite-longshot bias: favourites over-bet, underdogs under-bet.
  - The inefficiencies are "unpredictable and vary by season."
  - Precipitation games favour betting the favourite.
- **Beat vig?** Not shown for a bettor strategy in general.
- **Market inputs?** yes.
- **Testable?** Our moneylines run from 2026-11-18 only. picksfootball and sbro have moneylines for some seasons.
- **Power:** ML returns on underdogs have SD ≈ 1.2 units per bet; ~100 qualifying dogs → SE ≈ 0.12 units (12% ROI).
- **Verdict: diagnostic only.** "Varies by season", and it fails power.

### N15. Krieger & Davis (2024): visibility and line movement
- **Citation:** "Examining the impact of visibility on market efficiency: lessons from movement in NFL betting lines."
  *Journal of Economics and Finance* 48(2), 263–279.
  [IDEAS](https://ideas.repec.org/a/spr/jecfin/v48y2024i2d10.1007_s12197-023-09656-5.html). **Access:** AB.
- **Claim:** less-visible games (smaller TV audiences, shared kickoff windows, smaller fan bases) have more frequent and
  larger line moves. The reading is that oddsmakers' attention goes to visible games, so openers in low-visibility games
  are noisier.
- **League / years / n:** NFL, 2007–2021, 3,756 games (regular + post); spreads.
- **Beat vig?** not a betting test.
- **Decay?** recent; none.
- **Market inputs?** The outcome is a market move. Visibility proxies are not market inputs.
- **Testable?** partly:
  - Kickoff window from `start_time` (stored).
  - Network from ESPN's scoreboard `broadcasts` (free, not stored).
  - TV audience: Nielsen is not free.
  - Fan base: no clean source.
- **Overlap:** it bears directly on T-OPEN / N-TOT-B1 (our gap predicts the Monday → close move). If low-visibility
  openers are noisier, our move slope should be larger there, and some of the "move toward us" could be opener noise.
- **Power:** splitting one season's line-move slope into two groups gives a difference SE ≈ 0.07 vs a plausible
  difference of 0.03–0.05.
- **Verdict: diagnostic only for 2027.** Collect the network and kickoff window now (section 4), and judge the
  interaction over several seasons.

### N16. Lopez & Bliss (2024): the bye advantage disappeared, the market didn't notice
- **Citation:** "Bye-bye, bye advantage." *Frontiers in Behavioral Economics* (Oct 2024); [arXiv 2408.10867](https://arxiv.org/abs/2408.10867).
  **Access:** FT. The authors work for the NFL.
- **Claim:** state-space models of point differential and of the point spread, 2002–2023.
  - Before the 2011 CBA the bye was worth +2.2 points; after it +0.31 (95% CI −1.01 to 1.64). Practice time, not rest,
    drove it.
  - The market moved the other way: it priced the bye at +0.39 before 2011 and **+0.97 after** (CI 0.65 to 1.28).
  - The mini-bye gives nothing. The market gives a small edge to teams facing an opponent who played the previous
    Monday night.
- **Beat vig?** Not a betting paper. A secondary write-up says backing the bye-disadvantaged team won ~52% since 2011,
  under the vig.
- **Decay?** None yet (2024).
- **Market inputs?** the spread model is a description of the market. The signal (rest days) is not a market input.
- **Testable?** yes, nflverse `away_rest` / `home_rest`, free.
- **Overlap:** nfl-v3 has **no rest term**, so in bye games nfl-v3 already sits ~0.66 pts closer to the true value than
  the market: the effect, if real, is already inside nfl-v3's gap.
- **Power:** ~27 bye-advantage games a season, a 0.66-pt effect is ≈ 2 pp of cover rate vs a one-season SE of ~9.6 pp.
- **Verdict: diagnostic only.** Report nfl-v3's record in bye-differential games. Fails power by a factor of ~10.

### N17. Nichols (2014): visiting-team travel
- **Citation:** "The Impact of Visiting Team Travel on Game Outcome and Biases in NFL Betting Markets." *Journal of Sports
  Economics* 15(1), 78–96 (online 2012). [IDEAS](https://ideas.repec.org/a/sae/jospec/v15y2014i1p78-96.html).
  **Access:** AB.
- **Claim:** west-to-east travel across one or more time zones raises the home team's win probability, growing with
  distance at a decreasing rate. Bettors under-estimate the home score in those games, but the bias is too small to
  exploit out of sample.
- **League / years:** NFL, 1981–2004, regular season.
- **Beat vig?** no.
- **Verdict: not usable** (the author found it unexploitable).

### N18. Smith et al. (1997, 2013, *SLEEP*): West Coast teams in night games
- **Citation:** 2013 SLEEP abstract (Harvard / Stanford). Press:
  [Medical Xpress](https://medicalxpress.com/news/2013-11-circadian-edge-west-coast-nfl.pdf),
  [Stanford](https://stanfordhealthcare.org/publications/165/165409.html) (1997 MNF paper). **Access:** SS.
- **Claim:** 1970–2011 games starting after 8 PM ET between East and West Coast teams: West Coast teams beat the spread
  66% of the time, by 5.26 pts on average (106 night games; 293 day games show nothing).
- **Beat vig?** yes, on a small sample.
- **Decay?** No peer-reviewed retest after 2013. The effect has been widely publicised since 1997, so the market has had
  time to adjust.
- **Testable?** yes (nflverse kickoff times, team locations, closes).
- **Power:** ~5–8 games a season.
- **Verdict: not usable** (sample far too small to judge, likely priced after publication).

### N19. Gregory-Smith (2021): injuries and the market
- **Citation:** "Wages and labor productivity: evidence from injuries in the NFL." *Economic Inquiry*
  ([Wiley](https://onlinelibrary.wiley.com/doi/full/10.1111/ecin.12960)). **Access:** SS.
- **Claim:** the spread doesn't anticipate in-game injuries (as expected) and stays the best predictor of outcomes.
  There is no evidence on how well markets price a pre-announced backup QB.
- **Overlap:** nfl-v3's QB adjustment (T-QB) is our own evidence. The QB-out suggestion on the overrides page uses it.
- **Verdict: not usable** (no betting test). **No peer-reviewed study of backup-QB pricing was found.**

### N20. Fodor et al. (2013): NFL holdover bias
- **Citation:** cited by Bennett (2019) as finding holdover bias and sticky preferences in the NFL
  ([ResearchGate](https://www.researchgate.net/publication/263080729_Inefficient_pricing_from_holdover_bias_in_NFL_point_spread_markets)).
  **Access:** not read.
- **Claim:** early-season lines over-weight last season.
- **Overlap:** nfl-v3 weights last season at 0.5, fading over 12 weeks, and is too steep in weeks 0–2 (calibration 0.75).
- **Verdict: diagnostic only.** nfl-v3-wk already addresses early-season weighting.

### N21. Theses on NFL efficiency since 2015
- Nuutinen (2025, Hanken) — 2015–2022 in-sample, 2023–24 out-of-sample, spreads
  ([PDF](https://helda.helsinki.fi/server/api/core/bitstreams/db1e1612-b57e-4d2b-84d2-4c2c68962e29/content); text not
  extractable).
- Skinner (2022, Princeton) — 2010–2021, OLS fails to reject efficiency
  ([slides](https://gceps.princeton.edu/wp-content/uploads/2022/09/2022_slides_Skinner-thesis.pdf)).
- Oswald (2022, UNI) — 2007–2021/22, spreads, totals, moneylines
  ([PDF](https://scholarworks.uni.edu/cgi/viewcontent.cgi?article=1538&context=hpt)).
- Claremont theses on moneylines (2020–24) and spreads (1992–2012)
  ([moneylines](https://scholarship.claremont.edu/cgi/viewcontent.cgi?article=5145&context=cmc_theses)).
- **Access:** SS.
- **Overall:** spreads look efficient in aggregate, with small pockets that don't replicate across theses.
- **Verdict: diagnostic only.**

### N22. Key numbers (3, 7)
- **Peer-reviewed work:** none found. Practitioner data, e.g. 1999–2025: 3 = 15.1%, 7 = 9.0% of margins (blog); 7
  weakening since the 2015 extra-point change. Our audit: 3 = 14.7%, 7 = 8.5%; +3.5 instead of +3 is worth ~5 points of
  win rate.
- **Use:** betting execution (which number to take), not a model. `pick_results_bettable` already grades at the best
  bettable number.
- **Verdict: diagnostic only.** Report how often a Play's number sits on or off 3 / 7 and the value of the half point
  taken.

### N23. Home field without crowds (2020) and its trend
- **Sources:** NFL Football Operations analytics (home edge ≈ 1.3 pts in 2020 vs 3.3 in 2006)
  ([NFL Ops](https://operations.nfl.com/gameday/analytics/stats-articles/what-does-the-nfl-s-home-field-advantage-look-like-in-2020));
  press reports that books cut home field to ~0.5–1 pt during the 2020 season. **Access:** SS.
  **No betting-market study found.**
- **Overlap:** nfl-v3 already excludes 2020 from points-model training (`NO_CROWD_SEASONS`) and refits home field.
- **Verdict: not usable** (one-off season).

---

## 3. Both leagues and method

### B1. Moskowitz (2021): momentum and value move lines from open to close, then the outcome reverses them
- **Citation:** "Asset Pricing and Sports Betting." *Journal of Finance* 76(6), 3153–3209.
  [NBER conference PDF](https://conference.nber.org/conf_papers/f92072/f92072.pdf). **Access:** FT.
- **Claim:**
  - Over 100,000+ contracts (NFL 1985–2013, NBA 1999–2013, NHL 1995–2013, MLB 2004–2013; Covers/SportsDirect and
    SportsInsights; spread, moneyline and total), price moves from open to close follow momentum (past wins, point
    differential and ATS/point returns over the last 1–8 games) and, more weakly, value. The outcome then **fully
    reverses** those moves.
  - Regressing close → outcome returns on open → close returns gives a coefficient of **about −0.50** for NBA and NFL
    spreads and totals. That rejects the "moves are information" hypothesis (0) and the "moves are pure noise"
    hypothesis (−1): about half of a typical move is reversed.
  - The effects are about one-fifth to one-sixth as large as in equities. Gross returns are a few tens of basis points a
    year (NBA momentum 60 bp open → close; multi-strategy 256 bp close → end), and the ~10% vig wipes them out.
- **Beat vig?** No.
- **Market inputs?** Yes: the signals are past performance and line moves.
- **Testable?** yes, our snapshots and lines (0 cost).
- **Overlap:** our edge so far is mostly in predicting the move (line-move slope, CLV), so this is the most relevant
  paper for how we judge. See 3.2.
- **Verdict: diagnostic only.** It is a measurement rule, not a challenger (3.2).

### B2. Avery & Chevalier (1999): sentiment in price paths
- **Citation:** "Identifying Investor Sentiment from Price Paths: The Case of Football Betting." *Journal of Business*
  72(4), 493–521. [IDEAS](https://ideas.repec.org/a/ucp/jnlbus/v72y1999i4p493-521.html). **Access:** AB.
- **Claim:** sentiment proxies (expert picks, hot hand, team prestige) predict the direction NFL spreads move during the
  week. Some of that movement responds to sentiment rather than information.
- **Verdict: diagnostic only.** It is the original basis for B1 and C14.

### B3. Gandar, Zuber, O'Brien & Russo (1988): statistical vs economic tests
- **Citation:** "Testing Rationality in the Point Spread Betting Market." *Journal of Finance* 43(4), 995–1007/8
  (page range differs between sources). **Access:** AB.
- **Claim:** NFL point spreads pass statistical rationality tests and fail economic (betting-rule) tests.
- **Verdict: diagnostic only.** It is why we judge on betting-relevant slopes, not on regression R².

### B4. Durham, Hertzel & Martin (2005): trends and sequences
- **Citation:** "The Market Impact of Trends and Sequences in Performance: New Evidence." *Journal of Finance* 60(5),
  2551–2569. [IDEAS](https://ideas.repec.org/a/bla/jfinan/v60y2005i5p2551-2569.html). **Access:** AB.
- **Claim:** football betting markets show scant evidence of the Barberis–Shleifer–Vishny trend / regime behaviour.
  (Which leagues isn't confirmed from the abstract.)
- **Verdict: diagnostic only.**

### B5. Glickman & Stern (1998, 2016): state-space ratings
- **Citation:** Glickman, M. E. & Stern, H. S. "A state-space model for National Football League scores." *JASA* 93
  (1998); reprinted in *Anthology of Statistics in Sports* (SIAM 2005, ch. 5). Plus their 2016 chapter "Estimating team
  strength in the NFL" ([PDF](http://www.glicko.net/research/nfl-chapter.pdf)).
  **Access:** 1998 AB / SS; 2016 FT.
- **Claim:**
  - Team strength follows an AR(1) process across weeks and across seasons, with a team-specific home advantage, fit by
    MCMC on 1988–1993 NFL scores.
  - It "appears to outperform the Las Vegas line" on a small test set of late-1993 games.
  - In the 2016 chapter, season-to-season regression pulls strengths toward the mean and narrows the spread of
    estimated strengths compared with least squares (e.g. the 2014 Saints differ by ~3 pts between the two fits). Their
    suggested extension is week-to-week variation for injuries.
- **Market inputs?** no (scores only).
- **Overlap:** this is the family of college T2(b) (rejected on betting checks, biggest accuracy gain; 2027 paper model
  `v6-ht2b`) and NFL `nfl-v3-ss` (registered 2026-11-25).
- **Verdict:** background for v6-ht2b / nfl-v3-ss, **not a new challenger**.

### B6. Lopez, Matthews & Baumer (2018): randomness by sport
- **Citation:** "How Often Does the Best Team Win? A Unified Approach to Understanding Randomness in North American
  Sport." *Annals of Applied Statistics* 12(4), 2483–2516. [arXiv 1701.05976](https://arxiv.org/abs/1701.05976).
  **Access:** FT (arXiv HTML). The NFL parameter values come from an extracted summary of the HTML: treat them as
  approximate.
- **Claim:**
  - A Bayesian state-space model on vig-free **moneyline probabilities**, 2006–2016, four leagues (NFL n = 2,560 games;
    lines for 99.3%).
  - NFL estimates: week-to-week autocorrelation of strength γ_week ≈ 0.978; season-to-season γ_season ≈ 0.69 (95%
    0.61–0.77); game-level noise σ_game ≈ 0.23 vs between-team spread σ_season ≈ 0.33 (logit scale).
  - The median probability that the better team wins a neutral NFL game is ≈ 64%. The NBA has the widest talent spread,
    and MLB and the NHL are closest to coin flips.
- **Market inputs?** **yes** (strengths are estimated from betting odds). Usable only as a description, never as a
  model feature.
- **What it means for us:**
  1. NFL strength barely moves week to week (0.978), so most of a season's information comes from accumulating noisy
     games, not from tracking change. That is consistent with nfl-v3's half-life of 6 and with T-WEEK / T-CAL finding
     little to fix.
  2. About 31% regression between seasons agrees with our last-season weight 0.5 fading over 12 weeks.
  3. With σ_game comparable to the talent spread, one NFL season (~270 games) can only separate models whose lines
     differ substantially. This is the power problem in plan-2027 §8.3 and §9.3.
- **Verdict:** background, **not a challenger**.

### 3.2 What B1 (Moskowitz) means for keeping CLV and ATS as separate scorecards

1. **A move toward us is not, by itself, value.** In Moskowitz's NFL data about half of an average open → close move is
   reversed by the outcome. A model that predicts line moves could be predicting the *noise* half (bettor momentum).
   It would then show strong CLV and no ATS edge, which is roughly the 2026 college pattern (CLV 64.8%, ATS 3+ at the
   open 50.0%).
2. **The test that separates the two is the result slope at the close.**
   - If our gap still predicts results *after* the move (positive slope), part of our information hasn't reached the
     close.
   - If it predicts nothing (≈ 0), the move absorbed our information.
   - If it predicts *negatively*, we are predicting sentiment that reverses.

   College v5: +0.015 ± 0.037 at the close (2018–25), i.e. ≈ 0, not negative. That is consistent with our moves being
   information that gets fully priced, not the reversing kind. NFL: T-OPEN's result slope at Monday +0.04 ± 0.10 can't
   yet tell these apart.
3. **So keep three scorecards per league, never merged:**
   - (i) **line move**: line-move slope and CLV in points;
   - (ii) **result at bet time**: result slope and ATS at the bettable number (the only one that pays);
   - (iii) **reversal check**: the result slope at the close on all games, plus Moskowitz's regression on our 3+ picks
     (close → result return on open → close return; ≈ −0.5 means our moves are typical market moves, ≈ 0 means they
     are information).

   Scorecard (i) can pass while (ii) fails. A CLV-only "pass" never promotes a model to betting. This is already our
   practice (H-TOT, N-TOT-B1 and T-OPEN are judged on movement and labelled "no betting value shown"). The proposal makes
   the reversal check an explicit reported measure in both leagues (plan-2027 §9.1).
4. **Momentum signals belong in (iii), not in the model.** Our features are per-play efficiency, not past ATS results.
   Where we do use a market-derived quantity (Test L's luck variable, C-G5ATS), it is a selection-layer tag judged at bet
   time.

---

## 4. Summary tables

### College

| # | Paper | Years / market | Access | Beat vig (own) | Decayed? | Market inputs | Our data / cost | Verdict |
|---|---|---|---|---|---|---|---|---|
| C1 | Salaga & Howley 2024 | ?, totals | AB | yes (abstract) | too new; our Test 7 negative | no (signal) | forecast log since 11-11, 0 | **candidate (C-WX)** |
| C2 | Bennett 2019 holdover | 2008–16, spreads | AB | yes | no retest | no | `/rankings` 1 call/season | diagnostic (C-HOLD tag) |
| C3 | Arscott 2023 censoring | 1996–2017 closes, totals (n = 13,276; 691 bets) | FT | in-sample 55.72% (p = 0.079 vs 52.38%) | none; 2018–25 post-sample | **yes, only** | CFBD lines 2018–25, 0 | **candidate (C-CENS)** |
| C4–6 | Paul & Weinbach 2005 → Weinbach & Paul 2009 → Francisco & Moore 2018 | to 2015, totals | AB/SS | 2005 yes | **yes, corrected** | yes | 0 | not usable (worked decay example) |
| C7 | Sinkey & Logan 2010 | 1985–2003, spreads | FT | yes | mixed | yes | 0 | diagnostic |
| C8 | Sinkey & Logan 2014 | 1985–2008 | SS | — | mixed | yes | 0 | diagnostic |
| C9 | Coleman 2017 travel | ?, spreads + totals | AB | implied | none | partly | 0 | diagnostic (Round 3 rejected) |
| C10 | Bennett 2021 next game | 2006–18, spreads | AB | yes (G5 54.2%) | none | yes | 0 | reported (C-G5ATS) |
| C11 | Salaga & Brown 2018 | ?, spreads | AB | no | — | yes | 0 | diagnostic |
| C12 | Cox et al. 2021 bowls | ?, spreads | AB | yes (momentum) | — | yes | 0 | diagnostic |
| C13 | Fair & Oster 2007 | ?, spreads | AB | no | — | no | 0 | diagnostic |
| C14 | Durham & Perry 2008 | ?, spreads | AB/SS | no | — | yes | 0 | diagnostic |
| C15 | Paul et al. 2026 TV | ?, volume | SS | — | — | no | ESPN broadcasts, free | collect TV network |
| C16 | portal, interims, pace, late kickoffs | — | — | — | — | — | — | no literature |

### NFL

| # | Paper | Years / market | Access | Beat vig (own) | Decayed? | Market inputs | Our data / cost | Verdict |
|---|---|---|---|---|---|---|---|---|
| N1 | Gray & Gray 1997 | 1976–94, spreads | AB/SS | in-sample | **yes** | yes | 0 | not usable |
| N2 | Levitt 2004 | 2001–02 + 1980–2001 | FT | home dogs 57.7% (1 season) | home dogs gone | yes | 0 | diagnostic (side baselines) |
| N3 | Humphreys, Paul & Weinbach 2013 | ?, spreads | AB | — | — | yes (bet shares) | no data | diagnostic |
| N4 | Paul & Weinbach 2011 | ?, spreads/totals | SS | spreads yes | — | yes (bet shares) | no data | not usable |
| N5 | Paul & Weinbach 2021 | 2020 | SS | — | — | yes | no data | not usable |
| N6 | Borghesi 2007 home weather | ?, spreads | SS | yes (press) | none | partly | nflverse temp, 0 | diagnostic |
| N7 | Borghesi 2008 weather totals | 1984–2004, totals | AB | yes (OOS) | no retest | no (signal) | forecast log (from Tue), 0 | **candidate (N-WX)** |
| N8 | atmospheric conditions | ?, totals | AB | yes | none | no | Open-Meteo, free | diagnostic |
| N9 | Paul & Weinbach 2002 | 1979–2000, totals | SS | no | — | yes | 0 | not usable |
| N10 | Shank 2018 | ?, totals | none | (brief) | — | yes | 0 | diagnostic (fails power) |
| N11 | Shank 2019 division | 2003–16 | AB | yes (~57% OOS) | our scan: unsteady | partly | 0 | not usable for 2027 (fails power) |
| N12 | Nofsinger & Shank 2023 | ?, totals | AB | unders yes | — | yes | 0 | diagnostic |
| N13 | Miller & Rapach 2013 | NYC bookies | AB | ? | — | yes | — | method background |
| N14 | Tuttle et al. 2024 | 2007–16, moneylines | AB | no (books do) | "varies by season" | yes | h2h since 11-18 | diagnostic (fails power) |
| N15 | Krieger & Davis 2024 | 2007–21, n = 3,756 | AB | — | — | no (proxies) | kickoff slot yes; network free | collect; diagnostic |
| N16 | Lopez & Bliss 2024 bye | 2002–23 | FT | ~52% (secondary) | — | no | nflverse rest, 0 | diagnostic (fails power ~10×) |
| N17 | Nichols 2014 travel | 1981–2004 | AB | no | — | no | 0 | not usable |
| N18 | Smith et al. 2013 circadian | 1970–2011, n = 106 | SS | 66% ATS | likely priced | partly | 0 | not usable |
| N19 | Gregory-Smith 2021 injuries | — | SS | — | — | — | — | not usable |
| N20 | Fodor et al. 2013 holdover | ? | not read | ? | — | no | 0 | diagnostic (nfl-v3-wk covers) |
| N21 | theses since 2015 | 2007–2024 | SS | mostly efficient | — | yes | — | diagnostic |
| N22 | key numbers | practitioner | — | — | 7 weakening | — | stored | diagnostic (execution) |
| N23 | 2020 home field | 2020 | SS | — | — | — | — | not usable |

### Both / method

| # | Paper | Access | Verdict |
|---|---|---|---|
| B1 | Moskowitz 2021 (NFL 1985–2013, −0.50 reversal of open → close moves) | FT | measurement rule: three separate scorecards (3.2) |
| B2 | Avery & Chevalier 1999 | AB | diagnostic |
| B3 | Gandar et al. 1988 | AB | diagnostic |
| B4 | Durham, Hertzel & Martin 2005 | AB | diagnostic |
| B5 | Glickman & Stern 1998 / 2016 | AB / FT | background for v6-ht2b, nfl-v3-ss |
| B6 | Lopez, Matthews & Baumer 2018 | FT | background (NFL signal per season) |

**Coverage against the 15–25-per-league aim:** college 16 entries (14 papers plus the decay pair and a gap note), NFL
23, method 6. The college count is at the bottom of the range because the peer-reviewed college literature on these
topics is small. Every topic searched and not found is listed in C16.

### Data to start collecting now (with `as_of` timestamps), even if judged only in 2028+
- **College:**
  1. Final AP poll each January (CFBD `/rankings`, 1 call, for C-HOLD).
  2. TV network per game (ESPN scoreboard `broadcasts`, free, each poll; CFBD `/games/media` 1 call/season for history
     if wanted).
- **NFL:**
  1. Forecasts at the Monday 6 AM bet time (today the NFL weather job starts on Tuesday; forecast the next week's games
     from the nflverse schedule and stored venues on Monday).
  2. TV network and standalone / shared kickoff window per game (ESPN `broadcasts`, free).
  3. nflverse schedule columns we don't store (`div_game`, `away_rest` / `home_rest`, `roof`, `surface`, observed
     `temp` / `wind`), free. History can be re-downloaded, but the live values (rest after flex scheduling, roof decisions)
     should be stored as known before kickoff.
