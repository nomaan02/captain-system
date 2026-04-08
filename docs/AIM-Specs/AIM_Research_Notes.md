# AIM Research Notes — Paper Findings by Module

**Created:** 2026-03-01
**Status:** Living document — filled in AIM by AIM as papers are extracted
**Purpose:** Permanent record of research findings informing each AIM's design. Survives chat resets.
**Process:** For each AIM — screen papers (titles), select keepers, re-upload for full extraction, save findings here before moving to next AIM.

---

# HOW TO USE THIS DOCUMENT

Each AIM section below follows this structure:
1. **Papers screened** — all papers received from the search, with keep/skip decision
2. **Papers extracted** — full findings from the kept papers
3. **Design conclusions** — what the research tells us about how to build this AIM
4. **Open questions** — anything unresolved that needs further research or a design decision

When starting a new chat, read `CaptainNotes.md`, `AIMRegistry.md`, and this file to restore full context.

---

# SYSTEM PAPERS (Prompts 1, 2, 3, 4a, 4b, 4c)

## System Topic 1: Multi-Signal Aggregation and Online Learning
**Search prompt used:** System Prompt 1
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Focus | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 179 | Hybrid DL Models for Stock Market: Comparative Survey | Mishra, Saxena et al. | 2025 | End-to-end DL pipelines | KEEP | Architecture survey: ingestion → feature store → modelling → XGBoost meta-learner → RL policy. ADWIN drift monitor |
| 180 | Online Portfolio Selection: A Survey | Li & Hoi | 2014 (ACM CS) | Online learning for portfolios | **KEEP — extract** | Foundational survey. Sequential decision framework. Follow-the-Winner/Loser, Pattern-Matching, Meta-Learning. 154 citations |
| 181 | Practical Applications of MAB and Contextual Bandits | Bouneffouf & Rish (IBM) | 2019 | MAB/contextual bandits | KEEP | Exploration vs. exploitation for Captain's strategy/AIM selection. Comprehensive taxonomy incl. finance |
| 182 | Meta-Ensemble for Climate Finance | Kovi | 2025 (preprint) | Meta-ensembles | SKIP | Not peer-reviewed. Climate finance tangential. Concepts better covered by Paper 185 |
| 183 | Ensemble Data Stream Classification in Non-Stationary Environments | Khezri, Tanha & Samadi | 2023 | Ensemble + concept drift | **KEEP — extract** | Ensembles adapting to concept drift (non-stationary markets). Online vs. chunk-based. 24 synthetic streams tested |
| 184 | Forecasting Methods in Finance | Timmermann | 2018 (ARFE) | Financial forecasting review | **KEEP — extract** | Authoritative: low SNR, model instability, competitive pressures, forecast combination and evaluation |
| 185 | Comprehensive Review on Ensemble Deep Learning | Mohammed & Kora | 2023 | Ensemble DL methods | KEEP | Bagging/boosting/stacking/meta-learning fusion. Reference for combining AIM outputs |
| 186 | Personalized Investment Advisory via RL | Kambhampati (Vanguard) | 2025 | RL for advisory | KEEP | Thompson Sampling Sharpe 0.94 vs. 0.78 trad. Contextual bandits, DQN. RL methodology transferable |
| 187 | Dynamic Model Averaging in Time-Series Econometrics | Nonejad | 2021 (JES) | DMA | **KEEP — extract** | Time-varying model weights via forgetting factors + Kalman filter. Handles model uncertainty + parameter instability. Prime Captain meta-learning candidate |
| 188 | Online Learning with (Multiple) Kernels | Diethe & Girolami | 2013 (Neural Comp.) | Online kernel learning | KEEP | MKL parallels combining signal sources. Non-i.i.d. data theory. Foundational |

**Top 3 for full extraction:** 184 (financial forecasting in low-SNR/instability), 187 (DMA with time-varying weights), 180 (online portfolio selection + meta-learning)
**Strong runner-up:** 183 (ensemble methods for concept drift in non-stationary streams)

### Papers Extracted
**All 4 primary papers extracted (180, 183, 184, 187).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions for Captain Meta-Learning
- **DMA is THE framework.** Dynamically updates model probabilities via forgetting factors + Kalman filter. Computationally lightweight, no simulation. Identifies which AIMs matter at each time point. (Paper 187)
- **Forecast combination is theoretically correct** for low-SNR, model-unstable environments. Individual predictors are weak → combination improves. Evaluate by ECONOMIC measures. (Paper 184)
- **MLA (Meta-Learning Algorithm) architecture.** Captain combines 15 AIMs like strategies in an online portfolio. Follow-the-Winner + Follow-the-Loser coexist. Kelly criterion = theoretical foundation. (Paper 180)
- **Ensemble handles non-stationarity.** Add/remove/reweight AIMs dynamically. ADWIN/DWM as drift detectors per AIM. Concept evolution → triggers AIM-14. (Paper 183)

### Open Questions
*(fill in after extraction)*

---

## System Topic 2: Kelly Criterion with Parameter Uncertainty
**Search prompt used:** System Prompt 2 (now filed as System Topic 3 in user's folder structure)
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Focus | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 216 | Utility Maximization in Constrained and Unbounded Financial Markets (Regime Switching, BSDEs) | Hu, Liang & Tang | 2024 (arXiv, 101pp) | BSDE-based utility maximisation, regime switching | SKIP | Pure mathematics. Regime-switching chapter exists but impenetrable BSDE theory. Paper 219 covers same topic practically |
| 217 | Optimal Betting Under Parameter Uncertainty: Improving the Kelly Criterion | Baker & McHale | 2013 | Kelly shrinkage under parameter uncertainty | KEEP-extract | Core paper. Kelly bet should be SHRUNK when probability is estimated. Shrinkage factor estimates. "Back of envelope" correction. Simulation + tennis data |
| 218 | Distributional Robust Kelly Strategy: Optimal Strategy under Uncertainty in the Long-Run | Sun & Boyd (Stanford) | preprint | Robust Kelly under distributional uncertainty | KEEP-extract | Worst-case log growth across uncertainty set. Extends Breiman. Convex, tractable. Directly addresses Captain parameter uncertainty |
| 219 | Kelly Investing with Downside Risk Control in a Regime-Switching Market | MacLean & Zhao | 2022 (Quantitative Finance) | Regime-switching Kelly + drawdown control | KEEP-extract | THE paper for Captain (Online). Modified "blended Kelly" with Markov regime weights + downside threshold. Multi-asset sector ETFs |
| 220 | Long-Term Capital Growth: Good and Bad Properties of Kelly and Fractional Kelly | MacLean, Thorp & Ziemba | 2010 (Quantitative Finance) | Kelly theory + fractional Kelly | KEEP | Foundational reference from THE authorities. Multi-asset continuous-time formula. Fractional Kelly as risk control |
| 221 | Understanding the Kelly Criterion | Edward O. Thorp | 2008 (Wilmott) | Practical Kelly wisdom | KEEP | Thorp himself. Opportunity costs, overbetting, estimated vs. true probabilities. Why to bet LESS than full Kelly |
| 222 | Kelly Betting Under Probabilistic Recovery Constraints | Lee | 2025 | Kelly + recovery probability constraint | KEEP | Modified Kelly where recovery probability after loss ≥ threshold. Directly relevant to TSM layer (prop firm MLL/MDD). Short (4pp) but precise |
| 223 | The Kelly Criterion: How Estimation Errors Affect Portfolio Performance | Sælen | 2012 (NHH thesis) | Estimation errors in Kelly | SKIP | Master's thesis. Core findings covered more rigorously by Paper 217 |
| 224 | Optimal Capital Growth with Convex Shortfall Penalties | MacLean, Zhao & Ziemba | 2016 (Quantitative Finance) | Kelly + regime switching + path VaR + shortfall penalties | KEEP | Extends Paper 219. Markov regime-switching + path-level wealth floor with convex penalties. Captain + TSM constraints |
| 225 | Leverage and Uncertainty | Turlakov | — | Kelly in fat-tailed world, Kelly Parity | KEEP | Fractional Kelly derived from fat tails. Multi-asset Kelly Parity ↔ Risk Parity. Practical adaptive framework |

**Top 3 for full extraction:** 219 (regime-switching Kelly + drawdown), 217 (Kelly shrinkage under parameter uncertainty), 218 (distributional robust Kelly)

### Papers Extracted
**All 3 primary papers extracted (217, 218, 219).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions for Captain (Online) Sizing
- **Blended Kelly = THE sizing formula.** Regime-weighted blend of regime-specific Kelly portfolios. TSM constraints = downside threshold + convex shortfall penalty. VaR at each decision point. (Paper 219)
- **Kelly MUST be shrunk.** Raw Kelly overestimates when probabilities estimated. Shrinkage factor depends on estimation uncertainty. Half-Kelly is conservative but effective starting point. Always shrink, never swell (for log utility). (Paper 217)
- **Robust Kelly for worst-case protection.** When regime uncertain → maximise worst-case log growth across uncertainty set. Extends Breiman's guarantee. Convex, tractable via CVXPY. Safety net against model error. (Paper 218)
- **Architecture:** blended_kelly × shrinkage × min(adjusted, robust_fallback) × AIM_modifier × TSM_constraints

### Open Questions
*(fill in after extraction)*

---

## System Topic 3: Sequential Monitoring for Strategy Decay
**Search prompt used:** System Prompt 3 (now filed as System Topic 4 in user's folder structure)
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Focus | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 226 | Control Charts for Time Series | Kramer & Schmid | 1997 (Nonlinear Analysis) | CUSUM/EWMA/Shewhart for autocorrelated data | KEEP | Foundational: CUSUM/EWMA behaviour with autocorrelated data. EWMA/CUSUM better for small shifts, Shewhart for large |
| 227 | Statistical Damage Classification Using SPRT | Sohn, Allen, Worden & Farrar | 2003 (Structural Health Monitoring) | SPRT + extreme value statistics | KEEP | SPRT for degradation detection with extreme value tails. Direct analogy: structure=strategy, damage=decay |
| 228 | Advances in Bayesian Online Change-Point Detection and Robust Investment Strategies | Tsaknaki | 2025 (PhD thesis, 140pp) | BOCPD + time-varying params + Kelly | KEEP-extract | Bridges decay detection and Kelly sizing. BOCPD with score-driven models. Published in Quantitative Finance. Covers order flow + market impact |
| 229 | Modeling and Structural Break Detection Using Nonparametric Methods | Roy | 2025 (PhD thesis, 155pp) | Nonparametric break detection | SKIP | Pure statistics thesis. 155pp without financial application. Too far from Captain's practical needs |
| 230 | Bayesian Online Change Point Detection in Finance | Habibi | 2021 (Financial Internet Quarterly, 8pp) | BOCPD in finance | KEEP | Concise financial BOCPD application. Prior selection, parameter estimation. Practical complement to Paper 231 |
| 231 | Bayesian Online Changepoint Detection | Adams & MacKay | 2007 (Cambridge) | THE foundational BOCPD algorithm | KEEP-extract | THE reference paper. Run-length distribution via message-passing. Modular design. The algorithm Captain (Offline) would implement |
| 232 | Distribution-Free CUSUM Control Charts Using Bootstrap-Based Control Limits | Chatterjee & Qiu | 2009 (Annals of Applied Statistics) | Distribution-free CUSUM with bootstrap | KEEP-extract | Critical: trade returns are non-normal. Bootstrap control limits eliminate normality assumption. Sequential limits conditioned on last reset |
| 233 | Change-Point Detection Using PELT Algorithm | Jia | 2025 (CISAI conference) | PELT = linear-complexity change-point detection | KEEP | Efficient batch alternative. Compares PELT/Binseg/Dynp. Useful for Captain (Offline) periodic batch reprocessing |
| 234 | Bayesian Change-Point Detection in Multiple Financial Time Series | Huang | 2025 (ICEMBDA conference) | BOCPD vs. GLR vs. KS comparison | KEEP | Method comparison: BOCPD outperforms GLR and KS across scenarios. S&P 500 validation 2006-2025 |
| 235 | Bayesian Change Point Detection: Evidence from Hong Kong Stock Market | Yan | 2025 (MLSC conference) | BOCPD on Hang Seng | SKIP | Redundant with Paper 234. Same methodology, less informative (no method comparison) |

**Top 3 for full extraction:** 231 (BOCPD foundational), 232 (distribution-free CUSUM), 228 (BOCPD + Kelly thesis)

### Papers Extracted
**All 3 primary papers extracted (228, 231, 232).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions for SPRT/CUSUM Implementation
- **BOCPD is THE primary decay detection algorithm.** Online exact posterior over run length. P(changepoint | history) at each day. Apply per monitoring stream (P&L, per-AIM, features). Probabilistic, not binary. (Paper 231)
- **Distribution-free CUSUM for non-Normal returns.** Bootstrap-based sequential control limits calibrated to actual distribution. Sprint length conditioning. Complementary to BOCPD: CUSUM detects mean shifts; BOCPD detects distributional changes. (Paper 232)
- **Extended BOCPD for trading data.** Standard BOCPD assumes independence → MBO(q) handles autocorrelation + heteroskedasticity within regimes. Score-driven adaptation for time-varying volatility. Applied to order flow and market impact. (Paper 228)
- **Bridge to Kelly:** Changepoint detection triggers Kelly parameter re-evaluation — Captain's core feedback loop. (Paper 228, Part II)
- **Architecture:** BOCPD on P&L + per-AIM streams; CUSUM as complementary mean-shift detector. cp_prob > 0.8 → Level 2; sustained > 0.9 for 5+ days → Level 3.

### Open Questions
*(fill in after extraction)*

---

## System Topic 4a: Online Learning and Concept Drift
**Search prompt used:** System Prompt 4a (simplified)
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Focus | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 189 | Online Learning with Adaptive Rebalancing in Nonstationary Environments | Malialis, Panayiotou & Polycarpou | 2020 (IEEE TNNLS) | Online learning + class imbalance + drift | **KEEP — extract** | AREBA: handles concept drift AND class imbalance jointly; outperforms baselines on speed and quality |
| 190 | Heterogeneous Online Learning Ensemble for Non-Stationary Environments | Idrees, Minku, Stahl & Badii | 2020 (KBS) | Heterogeneous ensemble + drift | **KEEP — extract** | HDWM: switches between model TYPES via seed learners; handles recurring drifts; directly parallels Captain's AIM selection |
| 191 | Concept Drift Detection and Adaptation for ML | Bhattacharya | 2022 (thesis) | Unsupervised drift detection | KEEP | AEDD: autoencoder-based drift detection WITHOUT true labels via ADWIN; important for delayed trade outcomes |
| 192 | Online Boosting Adaptive Learning for Multistream Classification | Yu, Lu, Zhang & Zhang | 2024 (AAAI) | Multistream concept drift | **KEEP — extract** | OBAL: handles multiple streams drifting asynchronously; AdaCOSA + GMM weighting; Captain processes 15 AIMs independently |
| 193 | Online ML from Non-Stationary Streams: Systematic Review | Palli, Jaafar et al. | 2024 (JICT) | Systematic review | KEEP | Comprehensive review: detection mechanisms, adaptation methods, imbalance handling |
| 194 | Adaptive Ensemble LSTM for Smart Grid Load Forecasting | Azeem, Ismail et al. | 2024 | Smart grid load forecasting | SKIP | Domain-specific (electrical grids); drift methods better covered by 190/192/193 |
| 195 | Adaptive Anomaly Detection: Continual Learning Framework | Ou, Huang et al. | 2025 (preprint) | Anomaly detection + drift | SKIP | Not peer-reviewed; generic anomaly detection; concepts better covered by peer-reviewed papers |

**Top 3 for full extraction:** 190 (HDWM heterogeneous ensemble + model-type switching), 192 (OBAL multistream drift, AAAI), 189 (AREBA joint drift + class imbalance)

### Papers Extracted
**All 5 kept papers extracted (189, 190, 191, 192, 193).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **HDWM architecture:** Different AIM "types" → best type changes with regime. Seed learners maintain diversity. Handles RECURRING drifts (market regimes). (Paper 190)
- **Asynchronous drift handling (OBAL):** 15 AIMs drift independently → isolate and down-weight degraded streams. Prevents negative transfer. Dynamic correlation learning. (Paper 192)
- **Rare event preservation (AREBA):** Class imbalance = rare but important events (crashes). Adaptive rebalancing prevents over-fitting to calm conditions. (Paper 189)
- **Unsupervised drift detection:** AutoEncoder reconstruction error + ADWIN for label-free detection. Don't wait for trade P&L → detect from feature space. (Paper 191)
- **Hybrid processing:** Daily online (AIM weight updates, drift detection) + Weekly/Monthly batch (model retraining, rebalancing). (Paper 193)

### Open Questions
*(fill in after extraction)*

---

## System Topic 4b: Reinforcement Learning and Bandit Methods
**Search prompt used:** System Prompt 4b (simplified)
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Focus | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 196 | Deep RL in Portfolio Allocation | Ijbema | 2025 (thesis) | DDPG/PPO/SAC portfolios | KEEP | Off-policy shows better OOS generalisation; honest about difficulty beating BuyAndHold |
| 197 | Offline RL from Datasets with Structured Non-Stationarity | Ackermann, Osa & Sugiyama | 2024 (RLC) | Offline RL + evolving dynamics | **KEEP — extract** | Contrastive Predictive Coding identifies non-stationarity in offline data; directly applicable to Captain learning from historical data |
| 198 | Portfolio Selection: RL vs. Traditional | Kottas | 2025 (thesis) | RL vs. MVO comparison | SKIP | Duplicates Paper 196 scope with less rigor |
| 199 | RL for Portfolio Management | Filos | 2018 (Imperial, arXiv) | DSRQN + MSM agents | KEEP | Generalisation across assets/markets regardless of training universe; linear scaling; universal trading agent |
| 200 | Ensembling Portfolio Strategies: Distribution-Free Framework | Lam | 2025 (arXiv) | Distribution-free strategy combination | **KEEP — extract** | Combines strategies WITHOUT statistical assumptions; combinatorial construction eventually exceeds best component; parallels Captain multi-AIM |
| 201 | RL for Real-World Non-Stationary Systems: Survey | Padha | 2026 (preprint) | RL survey: partial obs. + non-stationarity | KEEP | Comprehensive survey: model-free/based/offline under partial observability, safety, distribution shift |
| 202 | Systematic Portfolio Optimization via RL | Espiga-Fernández et al. | 2024 (Algorithms) | DQN/DDPG/PPO/SAC on indices | KEEP | CNN features + longer lookback outperform MLP; periodic rebalancing > continuous |
| 203 | Trading Financial Indices with RL Agents | Pendharkar & Cusatis | 2018 (ESWA) | SARSA(λ)/Q(λ)/TD(λ) | KEEP | Adaptive TD(λ) consistently beats single-asset. Classical RL on S&P500+bonds. Peer-reviewed |
| 204 | Thompson Sampling for Constrained Bandits | Deb, Ghavamzadeh & Banerjee | 2025 (RL Journal) | Constrained contextual bandits | **KEEP — extract** | CBwK (resource constraints) + CCB (safe baseline). Thompson Sampling. Maps directly to Captain TSM constraints |
| 205 | Simple Random Search is Competitive with RL | Mania, Guy & Recht (Berkeley) | 2018 | Random search vs. RL | KEEP | Simple methods match RL, 15x faster. CRITICAL cautionary: simple EWMA may suffice before complex RL |

**Top 3 for full extraction:** 200 (distribution-free strategy ensembling), 204 (constrained bandits with TSM-like constraints), 197 (offline RL with structured non-stationarity)
**Key design note:** Paper 205 — establish simple baselines (EWMA) before building complex RL into Captain

### Papers Extracted
**All 4 primary papers extracted (197, 200, 204, 205).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **CBwK/CCB for Captain:** P&L maximisation under TSM constraints (MDD, MLL) = CBwK. Baseline maintenance = CCB. Thompson Sampling is the algorithm. (Paper 204)
- **Distribution-free ensemble:** Guaranteed eventual wealth dominance over all components. No market assumptions. (Paper 200)
- **Offline RL:** Market evolves between days = Dynamic-Parameter MDP. CPC learns regime implicitly. (Paper 197)
- **SIMPLICITY PRINCIPLE:** Linear policies match complex RL. Start DMA, add complexity only when validated. 15x efficiency gain. (Paper 205)
- **Priority: Level 0 (DMA) → Level 1 (TS + constraints) → Level 2 (offline RL) → Level 3 (ensemble guarantee)**
*(fill in after extraction)*

### Open Questions
*(fill in after extraction)*

---

## System Topic 4c: Ensemble Methods and Meta-Learning
**Search prompt used:** System Prompt 4c (simplified)
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Focus | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 206 | A Survey on Concept Drift Adaptation | Gama, Žliobaitė, Bifet, Pechenizkiy & Bouchachia | 2014 (ACM Computing Surveys) | Concept drift adaptation | KEEP-extract | THE foundational concept drift survey. 2488 citations. Characterises adaptive learning, categorises strategies, evaluates methodology |
| 207 | Forecast-Then-Optimize Deep Learning Methods | Jiang, Feng et al. | 2025 | FTO framework: ensembles + meta-learners + uncertainty | KEEP | FTO parallels Captain predict-then-size flow. Operations management focus |
| 208 | Ensemble Data Stream Classification in Non-Stationary Environments | Khezri, Tanha & Samadi | 2023 (preprint) | Ensemble + concept drift | SKIP | Duplicate of Paper 183 (System Topic 1) |
| 209 | Model Averaging in Ecology: Bayesian, Information-Theoretic, and Tactical Approaches | Dormann et al. | 2018 (Ecological Monographs) | Model averaging theory | KEEP-extract | Domain-agnostic model averaging framework. Critical: estimated weights may NOT beat equal weights. Bayesian/AIC/CV weighting |
| 210 | Online ML from Non-Stationary Streams: Systematic Review | Palli, Jaafar et al. | 2024 (JICT) | Systematic review | SKIP | Duplicate of Paper 193 (System Topic 4a) |
| 211 | A Comprehensive Survey of Mixture-of-Experts: Algorithms, Theory, and Applications | Mu & Lin | 2025 | MoE architecture | KEEP-extract | MoE = Captain architecture: 15 AIMs as experts, gating = meta-learner. Covers continual/meta/RL learning, routing, training strategies |
| 212 | Learning in Nonstationary Environments: A Survey | Ditzler, Roveri, Alippi & Polikar | 2015 (IEEE CIM) | Active vs. passive drift adaptation | KEEP | Active (explicit detection) vs. passive (continuous adaptation) — key design choice for Captain learning mode |
| 213 | Scalable and Interpretable MoE Models | Jafar, Gamal & Raheem | 2025 (preprint) | MoE explainability | SKIP | Non-peer-reviewed preprint. Paper 211 covers same content more comprehensively |
| 214 | Information Aggregation and Collective Intelligence Beyond Wisdom of Crowds | — | 2026 (Nature Reviews) | Group decision theory | KEEP | Theoretical foundation for multi-signal combination. Herding/amplification risks as design caution for AIM aggregation |
| 215 | Survey on Ensemble Classification: Sampling and Learning Perspectives | Xue, Han, Li & Ma | 2026 (KAIS) | Ensemble classification (75pp) | KEEP | Comprehensive: meta-learning, transfer learning, incremental/online learning in ensemble context |

**Top 3 for full extraction:** 211 (MoE comprehensive), 206 (concept drift foundational), 209 (model averaging theory)

### Papers Extracted
**All 3 primary papers extracted (206, 209, 211).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions for AIM Aggregation Architecture
- **Captain = MoE.** 15 AIMs = 15 specialised experts. Gating function (DMA) routes inputs to relevant experts. Selective activation: not all AIMs active daily. Expert specialisation prevents conflicting knowledge. (Paper 211)
- **Trading IS concept drift.** AIM signal → profitable trade relationship changes with regimes. Drift types: sudden (crash), gradual (regime transition), recurring (seasonal). Hybrid: active detection (SPRT) + passive adaptation (DMA). (Paper 206 — 2488 citations)
- **Start with EQUAL WEIGHTS.** Equal weights match estimated weights for reasonable model sets. Finance (noisy data) meets conditions where averaging is beneficial. Low covariance between diversified AIMs is critical. Weight uncertainty is real → don't overfit the meta-learning. (Paper 209)
- **Complete architecture:** Startup (equal weights) → Daily (MoE gating + DMA aggregation + TS sizing) → Weekly (DMA update + ADWIN drift monitoring) → Monthly (AIM-13 scan + SPRT decay + AIM-14 expansion + retraining)

### Open Questions
- Optimal forgetting factor for DMA in daily trading cadence (0.99 vs. 0.95 vs. adaptive)
- Top-k routing: how many AIMs should be active simultaneously (all 15 vs. top-5 vs. dynamic)
- Whether MoE gating should be learned end-to-end or remain as DMA-style model averaging

---

# AIM-01: Volatility Risk Premium Monitor

**Search prompt used:** AIM-01 prompt
**Status:** SCREENED — 5 kept, 2 skipped, 1 cross-filed to AIM-06

### Papers Screened

| # | Title | Authors | Year | Decision |
|---|-------|---------|------|----------|
| 34 | Commodity Variance Risk Premia and Expected Futures Returns | Kang & Pan | 2015 | **KEEP — full extract** (VRP predicts CL futures returns, commodity-specific) |
| 35 | The Variance Risk Premium Over Trading and Nontrading Periods | Papagelis & Dotsis | 2025 | **KEEP — full extract** (overnight vs. intraday VRP decomposition, pre-open timing) |
| 36 | FOMC Event Risk | Johannes, Kaeck & Seeger | 2024 | **KEEP — cross-file to AIM-06** (options-implied event risk, better for Economic Calendar) |
| 37 | VRP: Components, Term Structures, Stock Return Predictability | Li & Zinna | 2018 | SKIP (VRP components, academic, covered by 39/40) |
| 38 | Extracting Forward Equity Return Expectations Using Derivatives | Clark, Lu & Tian | 2026 | SKIP (too theoretical, forward return expectations, not intraday conditioning) |
| 39 | The Pricing of Tail Risk and the Equity Premium | Andersen, Fusari & Todorov | 2020 | **KEEP** (jump tail risk premium is the primary return predictor, not diffusive VRP) |
| 40 | Short-Term Market Risks Implied by Weekly Options | Andersen, Fusari & Todorov | 2017 | **KEEP — full extract** (weekly options isolate short-term jump/vol risk, most practical) |

**Top 3 for full extraction:** Papers 34, 35, 40
**Supporting:** Paper 39 (same authors as 40, covers longer horizon — extract if context permits)
**Cross-filed:** Paper 36 → AIM-06

### Papers Extracted
**Papers 34, 35, 36, 39, 40** — full extraction complete. See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **How to compute VRP:** E[RV] (HAR-predicted from 5-min data) minus model-free IV (VIX/OVX). VRP is persistently negative; more negative = higher uncertainty.
- **Critical refinement:** Decompose into overnight (close-to-open) vs. intraday VRP. Overnight VRP drives the negative premium and is the operationally relevant signal for Captain (Online) pre-open decisions. (Paper 35)
- **The actual driver:** Jump tail risk premium, NOT diffusive VRP, predicts equity returns. VRP works because it embeds the tail component. Weekly OTM puts can isolate tail risk. (Papers 39, 40)
- **Modifier construction:** Z-score overnight VRP against 60-day baseline. z > +1.5 → modifier 0.7; z > +0.5 → 0.85; z < -1.0 → 1.1; else 1.0. Monday adjustment: ×0.95. (See `AIM_Extractions.md` for full spec)
- **For CL specifically:** VRP negatively predicts CL returns. VRP3 (3-month) is optimal horizon. 1σ VRP increase → 2.86% decrease in 2-month returns. (Paper 34)
- **Warm-up:** 120 trading days confirmed (for z-score baseline; HAR needs 250 days but VIX proxy available immediately)
- **Data:** VIX/VXN/OVX (free, CBOE), intraday futures for RV, weekly options chain if available

### Open Questions
- Whether to implement the full jump tail decomposition (from weekly options) or use VRP as monolithic proxy — depends on data access and computational cost
- How does Monday adjustment interact with AIM-06 FOMC event risk on FOMC Mondays?
- Whether OVX close/open values are readily available for overnight decomposition on CL

---

# AIM-02: Options Skew & Positioning Analyzer

**Search prompt used:** AIM-02 prompt
**Status:** SCREENED — 8 kept, 2 skipped (1 cross-filed to AIM-01)

### Papers Screened

| # | Title | Authors | Year | Decision |
|---|-------|---------|------|----------|
| 41 | The Directional Information Content of Options Volumes | Ryu & Yang | 2018 | **KEEP** (PCR + investor-type decomposition predicts next-day returns) |
| 42 | Put-Call Ratio Volume vs. Open Interest in Predicting Market Return | Jena, Tiwari & Mitra | 2019 | SKIP (basic methodology, replicated in stronger papers 47/48) |
| 43 | Crash Risk Matters: Option-Implied Expected Market Return | Chen & Song | 2025 | SKIP — cross-file to AIM-01 (risk-neutral crash risk, better for VRP territory) |
| 44 | Leveraging a Call-Put Ratio as a Trading Signal | Houlihan & Creamer | 2019 | **KEEP** (PCR from specific participants → abnormal excess returns after Carhart + costs) |
| 45 | Do Option Open-Interest Changes Foreshadow Future Equity Returns? | Fodor, Krieger & Doran | 2011 | **KEEP** (call OI increases predict higher returns, OI ratio predicts weekly) |
| 46 | Informed Trading in the Index Option Market | Kaeck, van Kervel & Seeger | WP | **KEEP — full extract** (structural VAR decomposing flow into delta + vega exposures on SPX) |
| 47 | The Information in Option Volume for Future Stock Prices | Pan & Poteshman | 2006 | **KEEP — full extract** (seminal: buyer-initiated open-position PCR predicts next-day/week) |
| 48 | Predicting Short-term Stock Returns with Weekly Options Indicators | Saba, Bhuyan & Çetin | 2025 | **KEEP — full extract** (weekly options OI/volume predict short-term returns, OOS 2023) |
| 49 | Is There Information in the Volatility Skew? | Doran, Peterson & Tarrant | 2007 | **KEEP — full extract** (skew shape predicts crashes/spikes, short-term OTM puts strongest) |
| 50 | Order Flow and Expected Option Returns | Muravyev | 2016 | **KEEP** (inventory risk vs. asymmetric info decomposition, order imbalances predict returns) |

**Top 4 for full extraction:** Papers 46, 47, 48, 49
**Supporting (extract if context permits):** Papers 41, 44, 45, 50
**Cross-filed:** Paper 43 → AIM-01

### Papers Extracted
**All 8 kept papers extracted (46, 47, 48, 49, 50, 41, 44, 45).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **Best skew measure:** DOTM-OTM put IV spread (10-30 day maturity); practical proxy = 25-delta risk reversal (RR). Steepening put skew = crash risk elevated. Call skew NOT useful for upside. (Paper 49)
- **Primary signal:** Put-Call Ratio (PCR), ideally buyer-initiated open-position volume. Low PCR = bullish, high PCR = bearish. Deep OTM activity most informative. Predicts next-day returns by 40bp, next-week by >1%. (Paper 47)
- **Directional predictive power:** Validated for S&P 500/100 (Papers 47, 49), SPY (Paper 48), KOSPI 200 (Paper 41). Survives Carhart 4-factor + transaction costs (Paper 44). Weekly OI ratio also predictive (Paper 45).
- **Modifier construction:** Combined signal = 0.6 × PCR z-score + 0.4 × skew z-score. Combined > +1.5 → modifier 0.75; > +0.5 → 0.90; < -1.0 → 1.10; else 1.0. (See `AIM_Extractions.md`)
- **Order flow insight:** Inventory risk dominates asymmetric info in option pricing (Paper 50). Vega order flow explains 14% of hourly vol variation (Paper 46).
- **Enhanced during crises:** Predictive power of OI/volume indicators INCREASED during COVID-19 (Paper 48)
- **Warm-up:** 60 trading days for z-score baselines

### Open Questions
- Whether CBOE-level open/close classification data is available for our implementation (needed for true Pan-Poteshman PCR)
- Best practical proxy for PCR when only aggregate volume is available (total put volume / call volume works but is noisier)
- Whether CL options skew provides the same predictive quality as SPX options skew

---

# AIM-03: Gamma Exposure (GEX) Estimator

**Search prompt used:** AIM-03 prompt
**Status:** SCREENED — 5 kept, 5 skipped (2 subsumed, 1 duplicate, 1 retail, 1 dissertation)

### Papers Screened

| # | Title | Authors | Year | Decision |
|---|-------|---------|------|----------|
| 51 | 0DTEs: Trading, Gamma Risk and Volatility Propagation | Dim, Eraker & Vilkov | 2025 | SKIP — subsumed by Paper 57 |
| 52 | Gamma Fragility | Barbon & Buraschi | 2020 | **KEEP — full extract** (foundational: gamma imbalance → intraday momentum/reversal + flash crashes) |
| 53 | Liquidity Provision to LETFs and Options Rebalancing Flows | Barbon, Beckmeyer, Buraschi & Moerke | 2022 | **KEEP** (EOD momentum/reversion from gamma hedging, persistent effect) |
| 54 | Same as 53 (alt version) | Barbon et al. | — | SKIP — duplicate of 53 |
| 55 | Retail Traders Love 0DTE Options... But Should They? | Beckmeyer, Branger & Gayda | 2024 | SKIP (retail participation focus, not GEX conditioning) |
| 56 | Essays in Derivatives Markets (PhD Dissertation) | Mörike | 2023 | SKIP (335-page thesis, key findings in papers 52/53) |
| 57 | Do S&P500 Options Increase Market Volatility? Evidence from 0DTEs | Adams, Dim, Eraker, Fontaine, Ornthanalai & Vilkov | 2025 | **KEEP — full extract** (comprehensive: 0DTE GEX dampens vol, causal evidence, subsumes 51+59) |
| 58 | A Model for the Hedging Impact of Option Market Makers | Egebjerg & Kokholm | WP | **KEEP — full extract** (math model: gamma + inventory effects, net delta predicts SPX futures) |
| 59 | The Market for 0DTE options: Liquidity Providers in Volatility Attenuation | Adams, Fontaine & Ornthanalai | 2025 | SKIP — subsumed by Paper 57 |
| 60 | Pinning in the S&P 500 Futures | Golez & Jackwerth | 2012 | **KEEP** (pinning near ATM strikes on expiration, MM delta-hedge rebalancing) |

**Top 3 for full extraction:** Papers 52, 57, 58
**Supporting:** Papers 53, 60

### Papers Extracted
**All 5 kept papers extracted (52, 53, 57, 58, 60).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **GEX estimation:** OI-based: GEX = Σ(dealer_net_OI × option_gamma × multiplier × spot²) across strikes/maturities. Dealers typically net short → negative gamma default. Recompute daily from prior day OI. (Papers 52, 57)
- **Intraday regime:** Negative GEX → amplification (momentum, higher vol, flash crash risk). Positive GEX → dampening (reversal, lower vol, more predictable). Peak effect at 30-min frequency. (Paper 52)
- **0DTE context:** 0DTE presence DAMPENS vol by ~60bp on average. Pre-existing positions becoming 0DTEs drive hedging needs, not new 0DTE trading. Net gamma predicts 10-min ahead vol and order flow reversals. (Paper 57)
- **Two hedging channels:** Gamma effect (price-driven) + inventory effect (option trade-driven). Both significant; gamma-only analysis underestimates when both act same direction. (Paper 58)
- **Expiration effects:** Pinning near high-OI strikes on expiration days ($240M notional shift). ORB breakout reliability lower on expiration days. (Paper 60)
- **End-of-day:** Last 30 min return predictable from gamma sign + LETF rebalancing. Persistent throughout sample. (Paper 53)
- **Modifier:** GEX z-score vs. 60-day trailing. z < -1 → modifier 0.85; z > +1 → 1.10; else 1.0. Expiration: ×0.95. Triple witching: ×0.90.
- **Data:** CBOE OI (SPX/SPXW), CME OI (ES/CL options), compute greeks from IV surface. LETF AUM publicly available.
- **Warm-up:** 60 trading days

### Open Questions
*(fill in after extraction)*

---

# AIM-04: Pre-Market & Overnight Session Analyzer

**Search prompt used:** AIM-04 prompt
**Status:** SCREENED — 8 kept, 1 skipped

### Papers Screened

| # | Title | Authors | Year | Decision |
|---|-------|---------|------|----------|
| 61 | Overnight Returns of Stock Indexes: Evidence from ETFs and Futures | Liu & Tse | 2017 | **KEEP — full extract** (overnight returns predict first/last half-hour, ETFs + futures) |
| 62 | Intraday Return Predictability in the Crude Oil Market: EIA Announcements | Wen, Indriawan, Lien & Xu | 2023 | **KEEP** (CL-specific, overnight → intraday momentum, EIA announcement effect) |
| 64 | The Momentum & Trend-Reversal as Temporal Market Anomalies | Basdekidou | 2017 | SKIP (weak methodology, low-quality journal, covered by 61/65) |
| 65 | Understanding Intraday Momentum Strategies | Rosa | 2022 | **KEEP — full extract** (CRITICAL: intraday momentum disappears OOS, Markov-switching regime, thresholds needed) |
| 66 | Intraday Price Reversals in US Stock Index Futures: 15-Year Study | Grant, Wolf & Yu | 2005 | **KEEP** (large opens → reversals, 15 years of S&P 500 futures data) |
| 67 | An Investigation of Simple Intraday Trading Strategies | Donninger | 2014 | **KEEP — full extract** (directly tests ORB on ES, fails without IVTS regime filter, most applicable to MOST) |
| 68 | Oil Futures Overnight vs. Intraday for US Stock Volatility | Ma, Wahab, Chevallier & Li | 2023 | **KEEP** (cross-market: oil overnight RV → S&P 500 vol, cross-ref AIM-08/09) |
| 69 | Price Gaps and Volatility: Do Weekend Gaps Tend to Close? | Janse van Rensburg & Van Zyl | 2025 | **KEEP** (weekend gaps don't universally fill, larger gaps → higher vol) |
| 70 | Intraday Market Return Predictability from the Factor Zoo | Aleti, Bollerslev & Siggaard | 2024 | **KEEP** (ML intraday prediction, Sharpe 1.37 OOS, performance in high-uncertainty periods) |

**Top 3 for full extraction:** Papers 61, 65, 67
**Supporting:** Papers 62, 66, 68, 69, 70
**Note:** Paper 67 directly links AIM-04 to AIM-01 via IVTS (VIX/VXV) as regime filter for ORB

### Papers Extracted
**All 8 kept papers extracted (61, 62, 65, 66, 67, 68, 69, 70).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **IVTS (VIX/VXV) is THE validated regime filter for ORB on ES.** IVTS ≤ 0.93 = quiet (reduce), [0.93, 1.0] = optimal (full), >1.0 = turmoil (avoid). (Paper 67 — CRITICAL for MOST)
- **Overnight return is a dual signal:** (a) first-30-min gap reversal, (b) last-30-min continuation. Large gaps = reversal risk. (Papers 61, 66)
- **Intraday momentum is REGIME-DEPENDENT, NOT reliable standalone.** Disappears OOS post-2013; only works in high-vol periods (COVID). Threshold filtering essential. (Paper 65)
- **CL-specific: EIA Wednesdays shift the momentum signal** from 1st to 3rd half-hour. Captain should flag and adjust. (Paper 62)
- **Cross-market: overnight CL RV predicts next-day ES vol.** Negative oil overnight returns → elevated equity risk. (Paper 68)
- **Weekend gaps don't reliably close** — may extend. Larger gaps = higher vol. (Paper 69)
- **Intraday predictability concentrates in high-uncertainty periods** and is driven by tail risk and liquidity factors. (Paper 70)
- **Transaction costs are THE binding constraint.** Without regime filtering, ORB and gap strategies lose attractiveness after costs. (Papers 66, 67)
- **Modifier:** IVTS regime filter (primary) × overnight gap z-score (secondary). IVTS > 1.0 → 0.65; [0.93, 1.0] → 1.10; < 0.93 → 0.80. Extreme gap z > 2.0 → ×0.85.

### Open Questions
- Whether IVTS regime thresholds from 2010-2014 sample still hold in 2020s (post-0DTE era)
- Optimal overnight return threshold for each asset (ES vs. NQ vs. CL)
- How IVTS interacts with AIM-01 VRP signal (both measure vol state but from different angles)

---

# AIM-05: Order Book Depth/Imbalance at Open

**Search prompt used:** AIM-05 prompt
**Status:** SCREENED — 8 kept, 2 skipped. AIM is DEFERRED (L2 data cost) but research completed for future activation.

### Papers Screened

| # | Title | Authors | Year | Decision |
|---|-------|---------|------|----------|
| 71 | Order Book Curvature as Liquidity Measure: CL Futures | Wang | 2025 | **KEEP** (CL-specific LOB curvature, HF volatility prediction) |
| 72 | Assessing Order Flow Toxicity & Early Warning Signals | Andersen & Bondarenko | 2015 | **KEEP** (critiques VPIN on ES, important methodological lesson) |
| 73 | Major Issues in HF Financial Data Analysis: Survey | Zhang & Hua | 2025 | SKIP (too broad, general survey) |
| 74 | Stochastic Price Dynamics from Order Flow Imbalance: CSI 300 | Hu & Zhang | 2025 | **KEEP — full extract** (OFI as OU process, regime-dependent dynamics, horizon heterogeneity) |
| 75 | DL for Price Prediction from Stationary LOB Features | Tsantekidis et al. | 2020 | **KEEP** (stationary feature construction from LOB for DL) |
| 76 | Assessing Order Flow Toxicity via Perfect Trade Classification | Andersen & Bondarenko | 2013 | SKIP — earlier version of Paper 72 |
| 77 | Flow Toxicity and Liquidity in a HF World (VPIN) | Easley, López de Prado & O'Hara | 2012 | **KEEP** (seminal VPIN paper, conceptual foundation) |
| 78 | Trading Strategies via Book Imbalance | Lipton, Pesavento & Sotiropoulos | Risk | **KEEP — full extract** (directional probability from bid-ask imbalance, semi-analytical solution) |
| 79 | Effects of LOB Information Level on Market Stability | Paddrik, Hayes, Scherer & Beling | 2017 | **KEEP** (LOB depth signals flash crash ~1 min before, CME data) |
| 80 | Cross-impact of Order Flow Imbalance in Equity Markets | Cont, Cucuringu & Zhang | 2023 | **KEEP — full extract** (multi-level OFI integration, lagged cross-asset OFI predicts returns, cross-ref AIM-08/09) |

**Top 3 for full extraction:** Papers 78, 80, 74
**Supporting:** Papers 71, 72, 75, 77, 79
**Cross-filed:** Paper 80 also relevant to AIM-08/09 (cross-asset)

### Papers Extracted
**All 8 kept papers extracted (71, 72, 74, 75, 77, 78, 79, 80).** See `AIM_Extractions.md` for detailed findings. Research completed for future activation.

### Design Conclusions (DEFERRED — for future activation when L2 data acquired)
- **Book imbalance I = (q_bid - q_ask)/(q_bid + q_ask)** linearly predicts next tick direction. Sub-spread signal → entry CONFIRMATION, not standalone. (Paper 78)
- **Multi-level OFI** (top 5-10 LOB levels) superior to top-of-book only. Lagged cross-asset OFI predicts returns but decays rapidly. (Paper 80)
- **OFI dynamics are REGIME-DEPENDENT** with horizon-dependent heterogeneity → must select forecast horizon per regime. Heavy-tailed (Lévy) driving process. (Paper 74)
- **CL-specific: LOB curvature** improves volatility forecasts beyond spread/depth. EIA effect endogenous within liquidity. (Paper 71)
- **VPIN is FLAWED** — predictive power is spurious from BVC classification errors. Do NOT use. (Paper 72 vs. 77)
- **Flash crash warning ~1 min ahead** feasible with microstructure data; validated on ES and CL flash crashes. (Paper 79)
- **DL on LOB:** CNN+LSTM on stationarity-transformed features works for mid-price prediction. (Paper 75)
- **Activation cost:** L2 data feed ~$500-2000/month. When activated: book imbalance + multi-level OFI at open as ORB direction confirmation modifier.

---

# AIM-06: Economic Calendar Impact Model

**Search prompt used:** AIM-06 prompt
**Status:** SCREENED — 7 kept, 3 skipped (1 unreadable, 1 duplicate, 1 wrong market)

### Papers Screened

| # | Title | Authors | Year | Decision |
|---|-------|---------|------|----------|
| 81 | US Macro News Impact on Chinese Commodity Futures | Cai, Ahmed, Jiang & Liu | 2020 | **KEEP** (19 announcements, cross-border commodity transmission) |
| 82 | S&P 500 Futures Price Jumps and Macroeconomic News | Miao, Ramchander & Zumwalt | 2014 | **KEEP — full extract** (75%+ of 8:30am jumps from macro news, NFP/Cons Confidence key) |
| 83 | Speculative Trading in Energy Markets: Macro Surprises | Boucher, Gagnon & Power | 2026 | **KEEP** (26 announcements on CL/NG/metals, speculative trading dampens impact) |
| 84 | The Impact of Economic News on Financial Markets | Parker | 2007 | SKIP (PDF garbled/unreadable) |
| 85 | Intraday Return Predictability in CL: EIA Announcements | Wen et al. | 2023 | SKIP — duplicate (already kept as Paper 62 under AIM-04) |
| 86 | Macro Announcements in Brazilian Futures Markets | Santos, Garcia & Medeiros | 2014 | SKIP (Brazilian markets, not US futures) |
| 87 | Trading Around Macro Announcements: Are All Traders Equal? | Erenburg, Kurov & Lasser | 2006 | **KEEP** (10 announcement types on ES, price adjustment process) |
| 88 | Pre-Announcement Risk | Laarits | 2024 | **KEEP — full extract** (pre-FOMC drift = 162bps/yr, interpretation uncertainty risk premium) |
| 89 | Causal Effects: Equities, Oil, and Monetary Policy Over Time | Kurov, Olson & Halova Wolfe | 2024 | **KEEP** (time-varying causality stocks↔oil↔monetary policy, 2005-2022) |
| 90 | Price Drift before U.S. Macroeconomic News | Kurov, Sancetta, Strasser & Halova Wolfe | 2015 | **KEEP — full extract** (pre-drift ~30 min before 7/18 announcements, >50% of total move in ES) |

**Top 3 for full extraction:** Papers 82, 88, 90
**Supporting:** Papers 81, 83 (CL-specific), 87, 89
**Cross-references:** Paper 36 (from AIM-01 screening, cross-filed here) also covers FOMC event risk via options

### Papers Extracted
**All 7 kept papers extracted (81, 82, 83, 87, 88, 89, 90) + Paper 36 (cross-filed from AIM-01).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **Event hierarchy:** Tier 1 = NFP, FOMC (highest impact); Tier 2 = CPI, GDP, Consumer Confidence; Tier 3 = EIA, ISM; Tier 4 = Housing, Durables, PPI. (Papers 82, 87)
- **Pre-announcement drift:** 7/18 announcements show informed trading ~30 min BEFORE release. Drift accounts for >50% of total price impact. ORB signal at open may already reflect upcoming 8:30 news. (Paper 90)
- **Pre-FOMC risk premium:** 162 bps/year from 8 FOMC days. Not leakage — genuine risk compensation. Recent 5-day return predicts FOMC interpretation. (Paper 88)
- **Post-announcement speed:** Most adjustment in 1-5 min; locals positioned in <20 sec. Manual ORB: wait for initial adjustment before acting. (Papers 82, 87)
- **Cross-asset on event days:** FOMC affects ES + CL simultaneously. Since 2008: stock returns CAUSE oil returns (bidirectional). Reduce combined exposure on event days. (Paper 89)
- **Energy-specific:** Speculative activity DAMPENS macro impact on CL (improves execution). EIA shifts CL dynamics (AIM-04). (Paper 83)
- **Modifier:** Tier 1 within ±30min of ORB → 0.70; Tier 1 later in day → 1.05; Tier 2 near ORB → 0.85; EIA for CL → 0.90; event-free → 1.0. FOMC cross-asset: ×0.85.
- **Warm-up:** None — calendar is deterministic. Cross-ref Paper 36 (AIM-01) for FOMC event risk from options.

### Open Questions
- Whether pre-announcement drift threshold should be used to ENHANCE ORB (trade with drift direction) or REDUCE sizing (uncertainty from news)
- How to weight event-day modifier when multiple events coincide
- Whether to use options-implied event risk (Paper 36) as a continuous modifier vs. binary event flag

---

# AIM-07: Commitments of Traders (COT) Positioning

**Search prompt used:** AIM-07 prompt
**Status:** SCREENED — 8 kept, 1 skipped (duplicate)

### Papers Screened

| # | Title | Authors | Year | Decision |
|---|-------|---------|------|----------|
| 91 | Predictive Role of Large Futures Trades for S&P 500: COT Data | Chen & Maher | 2013 | **KEEP — full extract** (hedge funds superior at HF only, weekly COT too delayed, signal unreliable) |
| 92 | COT Report as Trading Signal? Short-term Reversals | Dreesmann, Herberger & Charifzadeh | 2023 | **KEEP** (COT reversal works in individual markets but not portfolio) |
| 93 | Hedgers, Funds, Small Speculators in Energy Futures: COT | Sanders, Boris & Manfredo | 2004 | **KEEP** (CL/NG/energy COT, positions don't lead returns) |
| 94 | Trading Behavior in S&P 500 Index Futures | Smales | 2015 | **KEEP** (ES COT: speculators positive-feedback, hedgers contrarian, sentiment determines positions) |
| 95 | Investor Sentiment, Market Timing, and Futures Returns | Wang | 2003 | **KEEP — full extract** (seminal: speculator = continuation, hedger = contrarian, extremes most reliable) |
| 96 | Advanced Positioning, Flow, and Sentiment Analysis in Commodity Markets | Keenan | 2020 | **KEEP (reference book)** (281-page Wiley practitioner text, too large for extraction) |
| 97 | Trading Behaviour in Closely Related Markets for S&P 500 | Smales | WP | SKIP — earlier version of Paper 94 |
| 98 | Smart Money: Market & Factor Timing Using Relative Sentiment | Micaletti | WP | **KEEP — full extract** (cross-asset COT relative sentiment, outperforms value/momentum, 25-year robust) |
| 99 | Effects of Index-Fund Investing on Commodity Futures Prices | Hamilton & Wu | 2015 | **KEEP** (important null: index-fund COT positions don't predict returns OOS in oil) |

**Top 3 for full extraction:** Papers 95, 98, 91
**Supporting:** Papers 92, 93 (CL-specific), 94 (ES behaviour), 96 (book reference), 99 (null result caution)

### Papers Extracted
**All 8 kept papers extracted (91, 92, 93, 94, 95, 96, 98, 99).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **Signal hierarchy:** Large speculator = continuation; large hedger = contrarian; small trader = ignore; index traders = ignore. EXTREME readings most reliable. (Paper 95 — seminal)
- **Best implementation: Cross-Asset SMI** (institutional vs. individual relative positioning). When SMI positive: ~20pp higher annual returns. Dominates momentum. 50pp spread during negative momentum. Robust to data snooping 25+ years. (Paper 98)
- **COT is a CONDITIONING variable, NOT a trigger.** Weekly + 3-day delay = too slow for intraday. Structural breaks change relationships across crises. Portfolio-level: doesn't outperform. (Papers 91, 92)
- **CL-specific:** Returns LEAD positions, not vice versa. COT is LAGGING for energy. Use disaggregated COT (managed money). Extremes may have contrarian value only. (Papers 93, 99)
- **Regime-dependent:** Positioning behaviour REVERSES during crises. Must monitor for signal regime changes. (Paper 94)
- **Modifier:** SMI positive → 1.05; SMI negative → 0.90. Extreme speculator z > 1.5 → ×0.95 (crowded); z < -1.5 → ×1.10 (contrarian). Weekly update, 52-week warm-up.
- **Data:** CFTC COT reports (free, weekly): TFF for ES/NQ, Disaggregated for CL.

### Open Questions
*(fill in after extraction)*

---

# AIM-08: Dynamic Cross-Asset Correlation Monitor

**Search prompt used:** AIM-08 prompt (supplementary — Papers 14 and 18 already held)
**Papers already held:** Paper 14 (Amado & Teräsvirta 2014, TV-GARCH), Paper 18 (Soury 2024, RS Copulas)
**Status:** SCREENED — 5 kept, 5 skipped (1 hedging, 1 Chinese, 1 duplicate, 1 covered by Paper 18, 1 encyclopedia)

### Papers Screened

| # | Title | Authors | Year | Decision |
|---|-------|---------|------|----------|
| 100 | Commodity & Stock Hedging with Asymmetric DCC | Alshammari & Obeid | 2023 | SKIP (hedging effectiveness focus, not signal generation) |
| 101 | Dynamic Correlation Chinese Stock & Commodity | Kang & Yoon | — | SKIP (Chinese markets) |
| 102 | How Regimes Affect Asset Allocation | Ang & Bekaert | 2004 | **KEEP — full extract** (foundational: bear-market regimes → higher correlations, RS dominates static OOS) |
| 103 | Market Regime Detection via Realized Covariances | Bucci & Ciciretti | 2022 | **KEEP — full extract** (regime detection FROM covariance matrices, clustering outperforms RS models) |
| 104 | Same as 103 | Bucci & Ciciretti | 2022 | SKIP — duplicate |
| 105 | Commodity & Equity Markets: Copula Stylized Facts | Delatte & Lopez | 2013 | **KEEP** (time-varying equity-commodity dependence, structural shift post-2003/2008) |
| 106 | Copula-Based RS GARCH for Hedging | Lee | 2009 | SKIP (RS copula covered by Paper 18 already extracted) |
| 107 | Dynamics among Global Asset Portfolios | Bratis, Laopodis & Kouretas | 2020 | **KEEP** (cross-correlations spike in crises, heterogeneous portfolios outperform) |
| 108 | Systemic Risk in Energy & Financial Markets: Connectedness | Bouzguenda & Jarboui | 2026 | **KEEP — full extract** (WTI/S&P 500/gold DCC-GARCH + connectedness, our exact assets, most recent) |
| 109 | Portfolio Management with Alternative Investments | Platanakis et al. | 2024 | SKIP (encyclopedia entry, too general) |

**Top 3 for full extraction:** Papers 102, 103, 108
**Supporting:** Papers 105, 107

### Papers Already Extracted
- **Paper 14 (Amado & Teräsvirta 2014):** TV-GARCH variance decomposition. Separates long-run baseline volatility from short-run GARCH. Regime-conditional constant correlation. Used for cross-asset covariance estimation in AIM-08.
- **Paper 18 (Soury 2024):** Regime-switching copula for ES/NQ/CL dependency. Two persistent regimes (calm/turbulent). Asymmetric tail dependence. Informs regime-conditional cross-asset capital allocation.

### Papers Extracted (supplementary)
**All 5 kept papers extracted (102, 103, 105, 107, 108) + Papers 14, 18 held.** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **Core: correlations are regime-dependent.** Higher in bear markets (asymmetric). Two-regime (normal + stress) is sufficient. RS allocation dominated static OOS. In stress: switch to CASH. (Paper 102 — seminal)
- **Detection: hierarchical clustering on realized covariance factors** is the best-performing method. Captures both abrupt and smooth changes. (Paper 103)
- **CL = principal volatility transmitter.** WTI is THE conduit of spillovers to equity. Connectedness-based strategies show superior crisis resilience. (Paper 108)
- **Commodity-equity correlation is persistent and growing** since 2003/2008. Must use TIME-VARYING measures (DCC or rolling). Static correlation is wrong. (Paper 105)
- **Multi-asset portfolios outperform single-class** in all periods. Need risk-offsetting (countercyclical) assets. (Paper 107)
- **Modifier:** Rolling 20d ES-CL correlation, z-scored vs. 252d baseline. z > 1.5 → 0.80 (stress); z > 0.5 → 0.90; z < -0.5 → 1.05. Combined exposure: ×0.85 when corr_z > 1.0.
- **Warm-up:** 252 trading days. Post-2008 calibration recommended.
- **Prior extractions applied:** TV-GARCH for long-run/short-run decomposition (Paper 14). RS copulas for asymmetric tail dependence (Paper 18).

### Open Questions
*(fill in after extraction)*

---

# AIM-09: Spatio-Temporal Cross-Asset Signal

**Search prompt used:** AIM-09 prompt (supplementary — Paper 19 already held)
**Papers already held:** Paper 19 (Tan, Roberts & Zohren 2023, SLP with cross-asset MACD)
**Status:** SCREENED — 8 kept, 2 skipped (1 already extracted as Paper 19, 1 thesis)

### Papers Already Extracted
- **Paper 19 (Tan, Roberts & Zohren 2023):** Single-Layer Perceptron with cross-asset MACD features outperforms complex deep learning for multi-asset signal generation on equity index futures. Architecture framework for cross-asset signal agreement as a sizing modifier.

### Papers Screened (supplementary)

| # | Title | Authors | Year | Decision |
|---|-------|---------|------|----------|
| 110 | Spatio-Temporal Momentum | Tan, Roberts & Zohren | 2023 | SKIP — duplicate of already-extracted Paper 19 |
| 111 | Follow the Leader: Network Momentum for Trend-Following | Li & Ferreira | 2025 | **KEEP — full extract** (network momentum in commodity futures, lead-lag detection) |
| 112 | Few-Shot Learning (X-Trend) for Trend-Following | Wood, Kessler, Roberts & Zohren | 2024 | **KEEP** (few-shot regime adaptation, cross-attention, zero-shot on novel assets) |
| 113 | Multi-asset Financial Markets (DPhil thesis) | Vuletić | 2025 | SKIP (200-page thesis, key findings in published papers) |
| 114 | Optimal Trend Following Portfolios | Valeyre | 2022 | **KEEP** (theoretical cross-asset trend portfolio framework) |
| 115 | DTW for Lead-Lag Detection in Multi-Factor Models | Zhang, Cucuringu et al. | 2023 | **KEEP — full extract** (DTW method for lead-lag, directly for cross-asset spillover network) |
| 116 | Network Momentum across Asset Classes | Pu, Roberts, Dong & Zohren | 2023 | **KEEP — full extract** (graph learning on 64 futures, momentum spillover, Sharpe 1.5, 22% annual) |
| 117 | L2GMOM: Learning Financial Networks for Momentum | Pu, Zohren, Roberts & Dong | 2024 | **KEEP** (end-to-end network + signal optimisation, Sharpe 1.74) |
| 118 | Cross-asset TSM: A New Perspective (I-XTSM) | Xu, Li, Singh & Park | 2025 | **KEEP** (industrial metal signals predict stock returns, avoids momentum collapse) |
| 119 | Trend-Following and Spillover Effects | Declerck | 2019 | **KEEP** (foundational: cross-asset trend spillover across 29 instruments) |

**Top 3 for full extraction:** Papers 116, 111, 115
**Supporting:** Papers 112, 114, 117, 118, 119

### Papers Extracted (supplementary)
**All 7 kept papers extracted (111, 112, 115, 116, 117, 118, 119) + Paper 19 held.** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **Network momentum is validated and powerful.** Sharpe 1.5-1.74 on 64 futures, 20+ years. Works from pricing data only. (Papers 116, 117)
- **Lead-lag = core mechanism.** CL and industrial metals LEAD equity markets with ~1-month lag. DTW + Lévy area as ensemble detection. Time-varying → re-estimate monthly. (Papers 111, 115, 118, 119)
- **Simple → Advanced path:** (a) 1-month CL momentum as ES modifier (Paper 118); (b) SLP on cross-asset MACD (Paper 19); (c) L2GMOM end-to-end (Paper 117, Sharpe 1.74)
- **Regime-adaptive:** X-Trend few-shot adapts rapidly to new regimes; 10x Sharpe over TSMOM 2018-2023; zero-shot transfer to new assets. (Paper 112)
- **Spillover works better with longer lookbacks** (3-12 months) than standard trend sweet spot. Dual-horizon: short for individual, long for cross-asset. (Paper 119)
- **Modifier:** Cross-asset momentum signal agrees with ORB → 1.10; disagrees → 0.85; neutral → 1.0. Warm-up: 63 trading days.
- **Data:** Futures prices only (ES, NQ, CL, industrial metals). Free. No proprietary databases.
- Modifier construction: *(fill in)*

### Open Questions
*(fill in after extraction)*

---

# AIM-10: Calendar Effect Model

**Search prompt used:** AIM-10 prompt
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Asset | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 120 | Momentum & Trend-Reversal as Temporal Anomalies | Basdekidou | 2017 | Leveraged ETFs | SKIP (dup) | Duplicate of Paper 64 (AIM-04), weak methodology |
| 121 | Calendar Anomalies in Cash and Stock Index Futures | Floros & Salvador | 2013 | FTSE100/S&P500/NQ futures | **KEEP — extract** | DOW + monthly in index futures w/ regime-switching; calendar effects positive in low-vol, negative in high-vol |
| 122 | Influence of Holidays on US Stock Yield and Volatility | Tang, Wu & Zhang | 2025 | US stocks | SKIP | Conference proceedings, weak methodology, holiday effect not significant overall |
| 123 | Intraday Return and Volatility Patterns: Futures vs Spot | Finnerty & Park | 1986 | S&P 500 futures | SKIP | Too old (1986); intraday patterns fundamentally changed since electronic trading |
| 124 | On the Persistence of Calendar Anomalies | van Heusden | 2020 | S&P500/AEX/Nikkei/ASX | KEEP | Tests persistence/disappearance of calendar effects post-publication; important design caution |
| 125 | Assessing Profitability of Intraday ORB Strategies | Holmberg, Lönnbark & Lundström | 2013 | CL futures | **KEEP — extract** | Directly tests ORB strategy on crude oil futures; significantly profitable; THE ORB paper |
| 126 | Equity Option Return Predictability and Expiration Days | Garcia-Ares | 2025 | US equity options + SPX | KEEP | 3rd Friday + following Monday systematically different; rollover pressure. Cross-ref AIM-03 |
| 127 | Day-of-the-Week Effect: Petroleum and Petroleum Products | Meek & Hoelscher | 2023 | WTI/Brent/RBOB/HO/NG futures | KEEP | DOW effect varies across energy commodities; CL-specific calendar evidence |
| 128 | Intra-day Seasonality and Abnormal Returns in Brent Crude Oil Futures | Ewald, Haugom et al. | 2025 | Brent crude oil futures | **KEEP — extract** | Tick-level intraday seasonal patterns; peaks/bottoms at specific times; generates CAPM alpha after costs |
| 129 | The Monthly Cycle of Option Prices | Gao, He & Hu | 2025 | US equity options | KEEP | ~2% monthly IV cycle around 3rd Friday rollover; cross-ref AIM-01/02 for IV timing |

**Top 3 for full extraction:** 121 (regime-conditioned calendar anomalies in index futures), 125 (ORB on CL futures), 128 (intraday seasonality in crude oil futures)
**Cross-references:** Paper 126 → AIM-03 (GEX/options expiration). Paper 129 → AIM-01/02 (monthly IV cycle timing)

### Papers Extracted
**All 6 kept papers extracted (121, 124, 125, 127, 128, 129).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **Calendar effects are REGIME-CONDITIONED.** Positive in low-vol, NEGATIVE in high-vol. Must multiply by regime state, not apply uniformly. (Paper 121)
- **ORB is validated on CL futures** with significantly positive expected returns. C-E principle = theoretical basis. THE foundational validation for MOST strategy on CL. (Paper 125)
- **CL intraday seasonality is exploitable** — U-shaped vol, specific time-of-day peaks/bottoms. After-costs CAPM alpha confirmed. (Paper 128)
- **Traditional DOW/January/TOM effects have DISAPPEARED** post-publication in major equity markets. Do NOT rely as standalone. (Paper 124)
- **DOW in petroleum is commodity-specific** — varies across WTI/Brent/RBOB/NG. Weak conditioning signal only. (Paper 127)
- **Monthly OPEX cycle:** ~2% IV swing around 3rd Friday rollover → distorts VRP and GEX baselines. Flag OPEX window. Weekly options attenuate. (Paper 129)
- **Modifier:** OPEX window (3rd Fri ± 2d) → ×0.95; high-vol regime → DOW ×0.97; else 1.0. No warm-up needed.

### Open Questions
- Optimal ORB threshold for CL (Paper 125 validates concept but our sample should determine specific threshold)
- Whether CL intraday timing peaks (Paper 128) apply to WTI as well as Brent
- How weekly/0DTE options era changes the OPEX cycle magnitude (Paper 129 notes attenuation)

---

# AIM-11: Regime Transition Early Warning

**Search prompt used:** AIM-11 prompt (supplementary — Papers 4, 10, 11 already held)
**Papers already held:** Paper 4 (Qiao et al. 2024), Paper 10 (Pettersson 2014), Paper 11 (Shu, Yu & Mulvey 2025)
**Status:** SCREENED

### Papers Already Extracted
- **Paper 10 (Pettersson 2014):** EWMA vol vs. trailing average — Tier 1 regime classification. Basis for AIM-11's current regime state input.
- **Paper 4 (Qiao et al. 2024):** MS-HAR-GARCH — Tier 2 regime classification (inactive). VOV decomposition.
- **Paper 11 (Shu, Yu & Mulvey 2025):** Supervised regime prediction. Program 2 Block 3b classifier basis.

### Papers Screened (supplementary — leading indicators)

| # | Title | Authors | Year | Asset | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 130 | Conditional Volatility of Commodity Index Futures as Regime Switching | Fong & See | 2001 | GSCI commodity futures | KEEP | Basis-driven time-varying transition probabilities; negative basis increases probability of high-variance state |
| 131 | Early Warning of Regime Switching: Heteroskedastic Network Model | Wang, An, Dong et al. | 2025 | S&P 500 | **KEEP — extract** | Explicit early warning signals for regime transitions; HMM + ARMA-GARCH + ML network; extracts critical warning features |
| 132 | Detecting Market Transitions in Energy Futures Using PCA | Borovkova | 2006 | Crude oil/NG/electricity futures | KEEP | PCA indicator (level/slope/curvature of forward curve) detects crude oil market transitions |
| 133 | Realized Jumps on Financial Markets | Tauchen & Zhou | 2011 | Equity, bonds, FX | KEEP | Jump detection via bipower variation; estimated jump intensity/variance; jumps often precede regime changes |
| 134 | Option-Implied Objective Measures of Market Risk | Leiss & Nax | 2018 | S&P 500 options | KEEP | Forward-looking Foster-Hart risk measure from RNDs; significant predictor of large ahead-return downturns. Cross-ref AIM-01/02 |
| 135 | Detecting Regime Shifts in Credit Spreads | Maalaoui Chun, Dionne & François | 2014 | Credit spreads | KEEP | Random regime shift detection: level regime (long-lived, Fed) vs. volatility regime (short-lived, crises). Methodology transferable |
| 136 | Regime-Switching in Stock Index and Treasury Futures Returns | Bansal, Connolly & Stivers | 2010 | S&P 500 + T-Note futures | **KEEP — extract** | Lagged VIX models time-varying transition probabilities. High-stress regime ID. VIX as leading indicator for futures regime shifts |
| 137 | VIX Futures Basis: Evidence and Trading Strategies | Simon & Campasano | 2012 | VIX futures | KEEP | VIX term structure (contango/backwardation) predicts VIX futures returns; term structure shape as regime indicator |
| 138 | Indexing, Cointegration and Equity Market Regimes | Alexander & Dimitriu | 2005 | Equity indices | SKIP | Tangential — equity indexing/tracking focus. Price dispersion as leading indicator is interesting but not core |
| 139 | Markov Switching of Conditional Volatility of Crude Oil Futures | Fong & See | 2002 | Crude oil futures | **KEEP — extract** | Regime switching directly on CL futures. Basis-driven transition probs. Regime shifts dominate GARCH. OOS outperforms non-switching |

**Top 3 for full extraction:** 139 (CL futures regime switching with basis-driven transitions), 136 (VIX as leading indicator for futures regime shifts), 131 (explicit early warning signal extraction)
**Cross-references:** Paper 134 → AIM-01/02 (option-implied risk measures)

### Papers Extracted (supplementary — leading indicators)
**All 4 supplementary papers extracted (131, 134, 136, 139) + Papers 4, 10, 11 held.** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **VIX = THE primary leading indicator** for regime transitions. Higher lagged VIX → higher transition probability to stress. VIX 30.5% avg on high-stress days vs. 19.8% on low-stress. Large daily VIX changes = transition in progress. (Paper 136)
- **CL basis = CL-specific transition variable.** Negative basis (backwardation) → high-vol regime PERSISTS longer. Positive basis → earlier recovery. Regime shifts dominate GARCH in CL. RS model outperforms GARCH OOS. (Paper 139)
- **Early warning is feasible.** Network community structure extracts warning signals BEFORE transitions. Dynamic process features richer than point-in-time. (Paper 131)
- **Option-implied FH bound predicts large downturns** — forward-looking supplement capturing tails beyond VIX. (Paper 134)
- **High-stress characteristics:** 3x+ stock variance, 0.5+ lower stock-bond correlation, higher bond returns. Diversification benefit increases during stress. (Paper 136)
- **Modifier:** VIX z-score > 1.5 → 0.75; > 0.5 → 0.90; < -0.5 → 1.05. VIX daily change z > 2.0 → ×0.85. CL backwardation + stress → ×0.90. Warm-up: 252 days.

### Open Questions
- Optimal VIX z-score thresholds for our specific asset universe and holding period
- How to combine VIX-based early warning with IVTS regime filter from AIM-04 (both use VIX-derived inputs)
- Whether option-implied FH bound is computationally feasible for daily Captain (Online) execution

---

# AIM-12: Dynamic Slippage & Cost Estimator

**Search prompt used:** AIM-12 prompt
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Asset | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 140 | Measuring and Modeling Execution Cost and Risk | Engle, Ferstenberg & Russell | 2006 | Equities (order-level) | **KEEP — extract** | Foundational cost/risk tradeoff model; models expected cost + risk by market state; introduces LVAR |
| 141 | Market Microstructure: A Practitioner's Guide | Madhavan | 2002 | General (survey) | KEEP | Comprehensive practitioner survey of microstructure — price formation, frictions. Background reference |
| 142 | Slippage and the Choice of Market or Limit Orders in Futures Trading | Brown, Koch & Powers | 2009 | CBOT wheat/corn/soybean futures | **KEEP — extract** | Directly quantifies slippage in commodity futures; identifies predictive factors (order size, price movement, volume) |
| 143 | Market Microstructure of FT-SE 100 Index Futures | Tse | 1999 | FTSE 100 index futures | KEEP | Intraday bid-ask spread patterns in index futures; spreads stable intraday, widen with macro news. Time-of-day cost |
| 144 | Handbook of Price Impact Modeling | (textbook, CRC) | 2023 | General | KEEP | Comprehensive textbook reference — market simulator, closed-form strategies, liquidity risk measurement |
| 145 | Optimal Execution: A Review | Donnelly | 2022 | General | **KEEP — extract** | 20-year comprehensive review of optimal execution field; LOB mechanics, cost/risk sources, complex dynamics |
| 146 | Optimal Execution with Nonlinear Impact Functions | Almgren | 2003 | General | KEEP | Foundational paper — power-law (square root) market impact, characteristic time, trading-enhanced risk |
| 147 | Slippage Costs in Order Execution for a Public Futures Fund | Greer, Brorsen & Liu | ~1992 | Commodity futures fund | KEEP | Slippage 2x larger for fund vs. general traders; worst on large-move days and large orders. Directly applicable |
| 148 | Optimal Execution Under Price Impact with Heterogeneous Timescale | Di Giacinto | 2024 | General | KEEP | Generalises Almgren-Chriss with market maker reversion timescales; power-law impact decay |

**Top 3 for full extraction:** 140 (dynamic cost/risk model by market state), 142 (slippage in commodity futures with predictive factors), 145 (comprehensive execution review)
**Supporting:** 146 (Almgren foundational impact model), 147 (futures fund slippage), 143 (intraday spread patterns in index futures)

### Papers Extracted
**All 6 primary papers extracted (140, 142, 143, 145, 146, 147).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **Execution cost = expected cost + cost variance.** Both time-varying, conditioned on market state. LVAR for worst-case. (Paper 140)
- **Slippage ≈ 0 on average for futures BUT variation is large.** Determinants: order size (+), spread (+), vol (+), depth (-). Experienced traders use limits when adverse slippage likely. (Paper 142)
- **Systematic/technical traders face DOUBLE the slippage** ($34 vs $17/contract). Crowding on high-vol days amplifies. Stop-loss fills are WORSE than entries. (Paper 147)
- **Market impact follows power law** (square root): doubling size → ~41% more impact. Below critical size (1-3 contracts) → trading-enhanced risk negligible. Above → split via TWAP. (Paper 146)
- **Index futures open is LIQUID** — narrow spreads, large sizes. Macro news widens spreads. Low information asymmetry → cost is IMMEDIACY. (Paper 143)
- **Modifier:** spread_z > 1.5 or vol_z > 1.5 → 0.85; > 0.5 → 0.95; both < -0.5 → 1.05. Always apply 2x slippage multiplier for systematic trader. High-vol VIX → ×0.95.
- Integration with Kelly formula: *(fill in)*

### Open Questions
*(fill in after extraction)*

---

# AIM-13: Strategy Parameter Sensitivity Scanner

**Search prompt used:** AIM-13 prompt
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Asset | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 149 | *(empty/unreadable — 5 blank pages)* | — | — | — | SKIP | No extractable content |
| 150 | The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality | Bailey & López de Prado | 2014 | General | **KEEP — extract** | DSR corrects Sharpe for multiple testing + non-normality; essential framework for parameter sensitivity |
| 151 | Backtest vs. OOS Performance on 888 Trading Algorithms | Wiecki, Campbell, Lent & Stauth (Quantopian) | 2016 | General (888 algos) | **KEEP — extract** | Sharpe R² < 0.025 for OOS prediction; higher-order moments more predictive; more backtesting → larger IS-OOS gap; ML classifiers R² = 0.17 |
| 152 | The Probability of Backtest Overfitting | Bailey, Borwein, López de Prado & Zhu | 2017 | General | **KEEP — extract** | PBO/CSCV formal framework to quantify overfitting probability; THE mathematical methodology |
| 153 | Evaluation and Optimization of Trading Strategies (book) | Pardo | 2nd ed. | General | KEEP | Comprehensive textbook — walk-forward analysis, optimisation, robustness testing. Reference only (367pp) |
| 154 | Reality Check on Technical Trading Rule Profits in US Futures Markets | Park & Irwin | 2010 | 17 US futures markets | KEEP | White's Reality Check + Hansen's SPA on futures; only 2/17 profitable after data snooping correction |
| 155 | Statistical Overfitting and Backtest Performance | Bailey, Ger, López de Prado et al. | ~2015 | General (simulator) | KEEP | Online simulator demonstrating backtest overfitting on random walks; supports perturbation concept |
| 156 | Evolutionary Bootstrap Method for Selecting Dynamic Trading Strategies | LeBaron | 1998 | FX | KEEP | Bootstrap + evolutionary optimisation for model/strategy selection; cross-validation for OOS estimation |
| 157 | Bayesian Approach to Measurement of Backtest Overfitting | Witzany | 2021 | General (technical) | KEEP | Bayesian MCMC framework for overfitting probability + Sharpe adjustment; complements frequentist DSR |
| 158 | How Hard Is It to Pick the Right Model? MCS and Backtest Overfitting | Aparicio & López de Prado | 2018 | General | KEEP | MCS not robust to multiple testing; important negative result — what NOT to use for model selection |

**Top 3 for full extraction:** 152 (PBO/CSCV overfitting probability), 150 (Deflated Sharpe Ratio), 151 (Quantopian empirical OOS study)
**Supporting:** 154 (futures reality check), 157 (Bayesian PBO alternative), 158 (MCS limitations)

### Papers Extracted
**All 6 papers extracted (150, 151, 152, 154, 157, 158).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **PBO + DSR are MANDATORY.** PBO > 0.5 → REJECT. DSR adjusts for N_trials + non-Normal returns. Must record N_trials. (Papers 150, 152)
- **Backtest Sharpe is USELESS for OOS prediction** — R² < 0.025 on 888 algorithms. Higher-order features (vol, DD, portfolio structure) 7x more predictive. ML-based selection outperforms. (Paper 151)
- **After data snooping correction, most technical rules FAIL** — only 2/17 futures markets survive White's Reality Check. Our strategy must pass this bar. (Paper 154)
- **MCS is insufficient** for strategy selection — useful for screening only, not final validation. (Paper 157)
- **Bayesian haircut:** Expected OOS Sharpe = IS Sharpe × (1 - haircut%). Compute probability of loss before adoption. IS-best expected OOS rank may be median. (Paper 158)
- **Monthly scan:** Perturb parameters ±10-20%, compute sharpe_stability, PBO, DSR. 2+ flags → Level 2/3 alert.
- ROBUST/FRAGILE threshold: *(fill in)*

### Open Questions
*(fill in after extraction)*

---

# AIM-14: Model Universe Auto-Expansion Monitor

**Search prompt used:** AIM-14 prompt
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Asset | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 159 | Crypto Trading via Fractal Market Hypothesis + Symbolic Regression | Blackledge & Blackledge | 2025 | BTC/ETH | SKIP | Crypto-specific, FMH niche; not relevant to auto-expansion for futures |
| 160 | Optimising Supertrend Parameters Using Bayesian Optimisation | Rahman | 2024 (thesis) | Stocks | SKIP | Too narrow — single indicator parameter tuning, not universe expansion |
| 161 | Trading Strategy Parameter Optimization: Double OOS + Walk-Forward | Mroziewicz & Ślepaczuk | 2026 | BTC/BNB/ETH | **KEEP — extract** | Parameterises WF window lengths; double OOS validation; Robust Sharpe Ratio; directly applicable to Captain re-runs |
| 162 | Data-Snooping Biases in Financial Analysis | Lo | classic | General | KEEP | Foundational Andrew Lo paper; framework for limiting search during expansion; solutions require theory/judgment |
| 163 | Intelligent Hybrid Trading System: Rough Sets + GA for Futures | Kim, Ahn, Oh & Enke | 2017 | KOSPI 200 futures | **KEEP — extract** | Automated trading rule discovery in futures via rough sets + GA; sliding window; variable training period |
| 164 | Interpretable Hypothesis-Driven Trading: Rigorous WF Validation | Deep, Deep & Lamptey | 2025 | US equities (100) | **KEEP — extract** | Rigorous WF validation, 34 independent test periods, strict info-set discipline, regime-dependent performance, open-source |
| 165 | Avoiding Backtesting Overfitting by Covariance-Penalties | Koshiyama & Firoozye | 2019 | 1300+ assets | KEEP | Covariance-Penalty correction prevents overfitting during universe expansion; TLS superior |
| 166 | Reality Check on Technical Trading Rules in US Futures | Park & Irwin | 2010 | 17 US futures | SKIP (dup) | Duplicate of Paper 154 (AIM-13) |
| 167 | Portfolio Optimization Efficiency Test + Data Snooping Bias | Kresta & Wang | 2020 | Equities | KEEP | Hypothesis test for strategy efficiency under data snooping; lower priority but useful validation |

**Top 3 for full extraction:** 164 (rigorous WF validation + regime dependence), 163 (automated rule discovery in futures via GA), 161 (parameterised WF + double OOS)
**Supporting:** 162 (Lo foundational data snooping), 165 (covariance penalties for overfitting prevention)

### Papers Extracted
**All 5 papers extracted (161, 162, 163, 164, 165).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **Automated discovery is feasible but requires extreme rigour.** Walk-forward with 34+ independent OOS periods. Double OOS prevents contamination. Interpretable rules REQUIRED. (Papers 161, 164)
- **Search MUST be theory-constrained.** Data snooping cannot be eliminated → limit search by economic theory. Arbitrary feature search = guaranteed overfitting. (Paper 162 — Lo, classic)
- **GA + rough sets for interpretable rule discovery** in futures markets. If-then rules are transparent. Significantly outperforms benchmark. (Paper 163)
- **Window length is a critical meta-parameter** — must optimise, not fix. Cross-asset parameter transfer works. Portfolio of strategies > single strategy. (Paper 161)
- **Simpler strategies preferred.** Covariance-penalty proportional to parameter count. Complements PBO. (Paper 165)
- **Expect modest results** from honest validation (0.55% annualised). Regime-dependent performance is NORMAL. (Paper 164)
- **Operation:** AIM-13 flags decay → AIM-14 generates candidates via GA → walk-forward validate → PBO/DSR filter → present to user for approval (Level 3).
- Search grid bounds per strategy parameter: *(fill in)*

### Open Questions
*(fill in after extraction)*

---

# AIM-15: Opening Session Volume Quality Monitor

**Search prompt used:** AIM-15 prompt
**Status:** SCREENED

### Papers Screened

| # | Title | Authors | Year | Asset | Decision | Reason |
|---|-------|---------|------|-------|----------|--------|
| 168 | Timely Opening Range Breakout on Index Futures | Tsai, Wu, Syu et al. | 2019 | DJIA/S&P500/NQ/HSI/TAIEX futures | **KEEP — extract** | TORB on index futures w/ 1-min data; Per-Minute Mean Volume (PMMV) at open; 8%+ annual returns |
| 169 | Private Information, Excessive Volatility and Intraday Regularities in Spot FX | McGroarty, ap Gwilym & Thomas | 2005 | Spot FX | KEEP | Intraday volume/spread/order flow regularities; random buy/sell variation > private info. Methodology transferable |
| 170 | Large Trades and Intraday Futures Price Behavior | Frino, Bjursell, Wang & Lepone | 2008 | CME futures | KEEP | Price impact of large trades on CME; info vs. liquidity effects differ by bull/bear. Volume quality → open dynamics |
| 171 | QuantAgent: Multi-Agent LLMs for HFT | Xiong, Zhang et al. | 2025 | BTC/NQ futures | SKIP | LLM-based HFT; not about volume quality at open |
| 172 | *(duplicate of 171)* | — | — | — | SKIP (dup) | Same PDF |
| 173 | *(duplicate of 171)* | — | — | — | SKIP (dup) | Same PDF |
| 174 | Understanding Intraday Momentum Strategies | Rosa | 2022 | US equities (SPY) | KEEP | Markov-switching: predictability depends on signal strength; thresholds improve OOS. Signal quality ≈ volume quality |
| 175 | Liquidity-Driven Breakout Reliability | Mittal & Choudhary | 2024 | Index futures/FX/commodities | **KEEP — extract** | 15,000+ breakouts; volume profile + Kaplan-Meier survival; low-vol breakouts >70% continuation vs. ~random at high-vol nodes |
| 176 | Profitable ORB Day Trading Strategy: Stocks in Play | Zarattini, Barbon & Aziz | 2024 | US equities (7,000+) | **KEEP — extract** | 5-min ORB with "Stocks in Play" quality filter (volume+news); top 20: Sharpe 2.81, alpha 36%. Volume filtering = AIM-15 core |
| 177 | Intraday Momentum in Crude Oil Market | Wen, Gong, Ma & Xu | 2019 | Crude oil (USO) | KEEP | First half-hour predicts last half-hour in CL; unique volume pattern from inventory data; first-half-hour dynamics inform AIM-15 |
| 178 | Regime-Based NQ Futures Trading: LSTM vs Transformer | Mähleke | 2025 (thesis) | NQ futures | SKIP | Master's thesis; regime focus better served by Program 2 research |

**Top 3 for full extraction:** 175 (breakout reliability by liquidity structure, survival analysis), 168 (TORB on index futures with PMMV), 176 (ORB with volume quality filter, Sharpe 2.81)
**Supporting:** 170 (large trade impact on CME), 174 (signal strength → predictability), 177 (CL intraday momentum + volume patterns)

### Papers Extracted
**All 6 papers extracted (168, 170, 175, 176, 177; Paper 174 = duplicate of AIM-04 Paper 65).** See `AIM_Extractions.md` for detailed findings.

### Design Conclusions
- **Volume quality is THE key differentiator for ORB.** Sharpe 2.81 with volume filtering vs. much lower without (Paper 176). Breakouts into low-volume zones have >70% continuation; into high-volume ≈ random (Paper 175). THIS is the missing variable.
- **Dual volume check:** (a) TEMPORAL: is today's opening volume above 20-day average? (b) SPATIAL: is breakout moving into low-volume price zone? Both independently predict ORB success.
- **TORB validated across 5 index futures:** >8% annual return using 1-minute data. 5-minute range optimal for US. Aligns with institutional direction. Higher frequency = more information. (Paper 168)
- **CL: first half-hour is the ONLY intraday predictor.** Overnight component dominates. Simpler than equities. (Paper 177)
- **Large trade impact is regime-dependent.** Bearish: sellers more informative. Bullish: buyers more informative. Opening session trade size = institutional participation quality. (Paper 170)
- **Modifier:** volume_ratio > 1.5 → 1.15; > 1.0 → 1.05; < 0.7 → 0.80. Low-volume breakout zone → ×1.10; high-volume zone → ×0.85. Warm-up: 20 days.

### Open Questions
*(fill in after extraction)*

---

# OVERALL STATUS TRACKER

| Module | Search Done | Papers Screened | Papers Extracted | Notes Saved |
|--------|-------------|-----------------|------------------|-------------|
| System 1 (Multi-signal aggregation) | ☑ | ☑ (keep 9, skip 1) Top 3: 184, 187, 180 | ☑ (4 extracted) | ☑ |
| System 2 (Kelly uncertainty) | ☑ | ☑ (keep 8, skip 2) Top 3: 219, 217, 218 | ☑ (3 extracted) | ☑ |
| System 3 (Sequential monitoring) | ☑ | ☑ (keep 8, skip 2) Top 3: 231, 232, 228 | ☑ (3 extracted) | ☑ |
| System 4a (Concept drift) | ☑ | ☑ (keep 5, skip 2) Top 3: 190, 192, 189 | ☑ (5 extracted) | ☑ |
| System 4b (RL / Bandits) | ☑ | ☑ (keep 9, skip 1) Top 3: 200, 204, 197 | ☑ (4 extracted) | ☑ |
| System 4c (Ensemble meta-learning) | ☑ | ☑ (keep 7, skip 3) Top 3: 211, 206, 209 | ☑ (3 extracted) | ☑ |
| AIM-01 IV/RV | ☑ | ☑ (keep 5, skip 2) Top 3: 34, 35, 40 | ☑ (all 5 extracted) | ☑ |
| AIM-02 Options Skew | ☑ | ☑ (keep 8, skip 2) Top 4: 46, 47, 48, 49 | ☑ (all 8 extracted) | ☑ |
| AIM-03 GEX | ☑ | ☑ (keep 5, skip 5) Top 3: 52, 57, 58 | ☑ (all 5 extracted) | ☑ |
| AIM-04 Pre-Market | ☑ | ☑ (keep 8, skip 1) Top 3: 61, 65, 67 | ☑ (all 8 extracted) | ☑ |
| AIM-05 Order Book | ☑ | ☑ (keep 8, skip 2) Top 3: 78, 80, 74 — DEFERRED | ☑ (all 8 extracted) | ☑ |
| AIM-06 Econ Calendar | ☑ | ☑ (keep 7, skip 3) Top 3: 82, 88, 90 | ☑ (all 7 + Paper 36) | ☑ |
| AIM-07 COT | ☑ | ☑ (keep 8, skip 1) Top 3: 95, 98, 91 | ☑ (all 8 extracted) | ☑ |
| AIM-08 Correlation | ☑ | ☑ (keep 5, skip 5) Top 3: 102, 103, 108 + P14+18 | ☑ (all 5+2 extracted) | ☑ |
| AIM-09 Spatio-Temporal | ☑ | ☑ (keep 8, skip 2) Top 3: 116, 111, 115 + P19 | ☑ (all 7+1 extracted) | ☑ |
| AIM-10 Calendar Effects | ☑ | ☑ (keep 7, skip 3) Top 3: 121, 125, 128 | ☑ (6 extracted) | ☑ |
| AIM-11 Regime Warning | ☑ | ☑ (keep 9, skip 1) Top 3: 139, 136, 131 + P4+10+11 | ☑ (4+3 extracted) | ☑ |
| AIM-12 Costs | ☑ | ☑ (keep 9, skip 0) Top 3: 140, 142, 145 | ☑ (6 extracted) | ☑ |
| AIM-13 Sensitivity | ☑ | ☑ (keep 9, skip 1) Top 3: 152, 150, 151 | ☑ (6 extracted) | ☑ |
| AIM-14 Auto-Expansion | ☑ | ☑ (keep 6, skip 3) Top 3: 164, 163, 161 | ☑ (5 extracted) | ☑ |
| AIM-15 Volume Quality | ☑ | ☑ (keep 7, skip 4) Top 3: 175, 168, 176 | ☑ (6 extracted) | ☑ |

---

*Fill in this tracker as each module is completed. When all rows show ✓, the research phase is complete and Program3.md can be built.*
