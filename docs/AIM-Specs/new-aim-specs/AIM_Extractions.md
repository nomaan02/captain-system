# AIM Full Paper Extractions — Detailed Findings

**Created:** 2026-03-01
**Status:** Living document — filled in AIM by AIM during Phase 3 (Full Extraction)
**Purpose:** Detailed research findings from each paper's full extraction. Design conclusions and open questions remain in `AIM_Research_Notes.md`.
**Companion:** `AIM_Research_Notes.md` (screening + conclusions), `AIMRegistry.md` (module specs), `CaptainNotes.md` (system design)

---

# EXTRACTION PROTOCOL

For each paper:
1. **What it proves** — core findings relevant to MOST/Captain
2. **Methodology** — how they did it (data, statistical tests, validation)
3. **Quantitative results** — specific numbers, effect sizes, significance levels
4. **What we take** — concrete design decisions for our AIM/system component
5. **What we leave** — aspects not relevant or not applicable to our setup
6. **Cross-references** — connections to other AIMs or system components

---

# AIM-01: Volatility Risk Premium Monitor

## Paper 34 — Kang & Pan (2015): Commodity Variance Risk Premia and Expected Futures Returns

**What it proves:**
- VRP in crude oil is persistently negative: mean -2.16% (1mo), -5.29% (3mo), -6.63% (6mo), all significant at 1% level
- VRP negatively predicts CL futures returns even after controlling for basis, CFTC positioning, open interest growth, momentum, and storage
- 1σ increase in VRP decreases subsequent 2-month/4-month/6-month returns by 2.86%/3.17%/4.95%
- Adding VRP to prediction model: adj. R² jumps from 1.23% to 6.08% for 2-month returns
- OOS models with VRP always outperform in realized economic profits

**Methodology:**
- Data: CL futures tick data (TickData) + daily CME options, January 1992 – December 2012
- RV: 5-minute average RV (Andersen, Bollerslev & Meddahi 2011) — robust to microstructure noise
- IV: Model-free implied variance from OTM puts + calls (Bakshi-Kapadia-Madan method)
- Expected RV: HAR regression (daily, weekly, monthly RV as predictors) on 250-day rolling window
- VRP = E^P[RV] - IV (forward-looking, no look-ahead bias)
- Tested 1-month, 3-month, 6-month horizons; VRP3 recommended as balance of signal quality and liquidity

**Quantitative results:**
- VRP autocorrelation > 0.59 (highly persistent)
- Oil VRP positively correlated with equity VRP, negatively with Chicago Fed Index
- Lower oil storage → more negative VRP (option writers demand more premium in tight markets)
- VRP magnitude increased post-1996 as markets became more liquid
- Oil market more volatile than equity market; correlation between oil/equity VRP increased post-2008 crisis

**What we take:**
- VRP computation method: HAR-predicted RV minus model-free IV
- VRP3 as recommended horizon for CL; VRP1 for shorter-term ES/NQ signals
- VRP negatively predicts returns → when VRP is more negative (uncertainty high), size down
- Cross-market VRP co-movement suggests global risk sentiment channel

**What we leave:**
- Mean-variance equilibrium model (theoretical derivation) — we only need the empirical VRP measure
- CFTC position as predictor (covered by AIM-07 COT)
- 6-month horizon (too long for intraday strategy)

---

## Paper 35 — Papagelis & Dotsis (2025): The Variance Risk Premium Over Trading and Nontrading Periods

**What it proves:**
- The negative VRP is driven ENTIRELY by the overnight (close-to-open) component
- Overnight variance swap returns: persistently negative and significant across ALL 14 indices globally
- Intraday (open-to-close) variance swap returns: positive in 10/14 cases, significant in 6
- Pattern is universal: US (S&P500, Nasdaq100, Russell2000), Europe (DAX, VSTOXX, SMI, EUROSTOXX), Asia (Nikkei, KOSPI, HSI), individual stocks (AAPL, GS, GOOGL, IBM, AMZN)
- Intraday VRP component predicts returns better at SHORT horizons (1-3 months)
- Overnight VRP component predicts returns better at LONGER horizons

**Methodology:**
- Data: Model-free IV indices (VIX, VXN, RVX, VSMI, VDAX-NEW, VSTOXX, VNK, VKOSPI, VHSI, stock VIX indices), 30/01/2012 – 30/09/2022
- Variance swap P&L decomposition: daily mark-to-market of hypothetical 30-day variance swap into close-to-open and open-to-close components
- The factor tr% accounts for different trading hours (US 6.5h, Europe 8.5h, Japan 6h)
- Newey-West corrected t-statistics for autocorrelation

**Quantitative results (Table 2 — IV changes):**
- VIX: overnight +0.130***, intraday -0.125***, difference 0.255*** (all in vol points)
- VXN: overnight +0.103***, intraday -0.096***
- Pattern consistent across all 14 indices (all differences significant at 1%)
- "Trading resolves uncertainty that accumulates during nontrading hours"

**Quantitative results (Table 3 — Variance swap P&L):**
- VIX: daily P&L -3.254, overnight P&L -6.149***, intraday P&L +2.894
- Day-of-week: Monday VRP most negative in almost all cases (weekend uncertainty)
- Friday: only US indices show significant negative VRP
- Expiration days: no significantly different behavior from monthly average

**What we take:**
- CRITICAL for Captain (Online): overnight VRP is the relevant signal for pre-open decision-making
- When overnight VRP is MORE negative than baseline → elevated uncertainty → size down
- When overnight VRP is LESS negative than baseline → reduced uncertainty → maintain/increase
- Monday effect: extra caution on Monday mornings (weekend uncertainty accumulation)
- Compute as: VRP_overnight = variance swap close-to-open P&L
- Z-score against trailing 60-day window for relative positioning

**What we leave:**
- Individual stock VIX indices (we trade futures, not equities)
- Long-horizon predictive regressions (our trades are intraday)

**Cross-references:** AIM-04 (Pre-Market/Overnight) — overnight VRP decomposition directly feeds both

---

## Paper 40 — Andersen, Fusari & Todorov (2017): Short-Term Market Risks Implied by Weekly Options

**What it proves:**
- Weekly ("short-maturity") S&P 500 options isolate short-term jump and volatility risks that longer-dated options cannot
- Negative jump tail risk varies INDEPENDENTLY of market volatility — not spanned by vol
- Periods of heightened tail concerns are NOT always signaled by elevated VIX
- Tail risk measure from weekly options predicts future equity returns, outperforming VIX and other standard metrics
- FOMC announcements create visible isolated shifts in left tail pricing — detectable in weeklies but NOT in monthly options

**Methodology:**
- Data: S&P 500 options (SPX, SPXQ, SPXW), January 2011 – August 2015, end-of-day quotes via OptionMetrics
- Seminonparametric structural calibration: estimate spot volatility, jump intensity, and jump size distribution daily
- Separate estimation of short-maturity sample (tenor ≤ 9 days) vs. regular sample (9–180+ days)
- Moneyness: m = ln(K/F_τ) / (√τ · IV_ATM,τ)
- Weeklies share of SPX volume: grew from ~10% (2011) to ~50% (2015)

**Quantitative results:**
- Short-dated OTM puts provide strike coverage to m = -6 to -8 consistently
- Deep OTM put coverage for weeklies has LOWER bid-ask spreads than comparable monthly OTMs
- Isolated left tail shifts identified empirically: e.g., September 20, 2012 — deep OTM puts elevated while ATM stable
- FOMC events: short-dated options show clear tail shift patterns invisible in monthly options
- Tail risk factor has significant forecast power for equity premium independent of vol

**What we take:**
- Weekly options (especially OTM puts) provide the purest measure of short-term tail risk
- VIX alone is insufficient — it mixes diffusive vol and jump risk
- If weekly options data is available for ES/NQ, compute the tail risk component separately
- Tail risk elevated + vol stable = still reduce sizing (the situation VIX misses)
- Weekly options are now dominant (>50% of volume) — liquid enough for real-time monitoring

**What we leave:**
- Full seminonparametric estimation procedure (too complex for AIM; use simplified proxies instead)
- Strike-by-strike option surface fitting (we compute aggregate measures)

---

## Paper 39 — Andersen, Fusari & Todorov (2020): The Pricing of Tail Risk and the Equity Premium (International)

**What it proves:**
- THE critical finding: the negative jump risk premium (tail risk premium) is the PRIMARY driver of the equity premium
- Diffusive VRP alone does NOT predict future equity returns once the tail component is stripped out
- VRP's predictive power for returns comes ENTIRELY from the embedded jump tail factor
- Tail factor remains elevated after crises long after volatility subsides to pre-crisis levels
- This pattern holds across ALL 7 international equity markets tested
- Strong global commonality in negative jump risk premiums (highly correlated across countries)

**Methodology:**
- Data: Daily option surfaces for S&P 500, ESTOXX, DAX, SMI, FTSE 100, MIB, IBEX 35, 2007-2014
- Two-factor model (2FU): spot variance (V) + negative jump intensity (U)
- U (jump intensity) evolves partly independently from V (volatility)
- HAR model for P-measure expectations; model-free for Q-measure
- Country-by-country estimation and cross-country analysis

**Quantitative results:**
- UK volatility correlation with S&P 500: ~98%; Swiss: ~95%
- Post-crisis: tail factor elevated for months/years after vol normalizes
- Decomposition: VRP = diffusive variance premium + negative jump risk premium
- Only the jump risk premium component predicts returns; diffusive component does not
- Southern European indices (Spain, Italy) show distinct tail dynamics during sovereign debt crisis

**What we take:**
- FUNDAMENTAL: VRP as a monolithic signal is noisy. The JUMP TAIL COMPONENT is what matters
- Practical implication: if we can only compute total VRP (IV - RV), it still works because tail component is embedded. But if we can separate them (using weekly options), the tail-only measure is superior
- Post-crisis: keep sizing reduced even after VIX normalizes if tail risk remains elevated
- Global tail correlation: VRP signals from ES can inform CL sizing and vice versa

**What we leave:**
- Parametric model specification details (we use the conclusion, not the model)
- Southern European-specific dynamics (not in our asset universe)

---

## Paper 36 — Johannes, Kaeck & Seeger (2024): FOMC Event Risk (Cross-filed to AIM-06)

**What it proves:**
- FOMC event risk is economically large: average event volatility 0.88%, range 0.29%–1.87% (5th-95th percentile)
- Event risk is highly TIME-VARYING — variation factor of ~6x vs. ~3x for VIX overall
- Option-implied FOMC event risk predicts realized event volatility with R² > 50%
- Evidence for early uncertainty resolution in hours/days BEFORE FOMC announcements
- Economically large FOMC event risk volatility risk premia exist
- S&P 500 FOMC event risk also predicts realized bond market volatility (Treasury futures)

**What we take for AIM-01:**
- FOMC events create VRP spikes detectable in short-dated options — validates using VRP as a risk signal
- Event risk is separately identifiable from stochastic volatility and crash risk
- VIX only captures ~50% correlation with FOMC event risk → VIX underestimates event-specific uncertainty
- Pre-FOMC uncertainty resolution = potentially useful timing signal (reduce uncertainty premium before announcement)

**Primary home:** AIM-06 (Economic Calendar Impact Model)

---

### AIM-01 Design Conclusions

**1. Core Signal: VRP = E[RV] - IV**
- Compute daily using HAR-predicted RV (from 5-min intraday data) minus model-free IV (VIX/OVX)
- For ES/NQ: use VIX (S&P 500) or VXN (Nasdaq 100)
- For CL: use OVX (CBOE crude oil volatility index)
- VRP is persistently negative; MORE negative = higher uncertainty

**2. Critical Refinement: Overnight vs. Intraday Decomposition**
- Captain (Online) runs pre-open → the overnight VRP is the operationally relevant signal
- Decompose daily VRP into close-to-open and open-to-close components (Paper 35 methodology)
- Overnight VRP drives the negative premium; intraday VRP is often positive
- Monday mornings: extra uncertainty from weekend accumulation → additional caution factor

**3. Advanced Signal (if weekly options data available): Jump Tail Component**
- Papers 39/40 prove that the JUMP TAIL premium, not diffusive vol, drives return predictability
- VIX alone misses periods where tail risk is elevated but vol is stable
- If feasible: compute deep OTM put relative pricing from weekly options as supplementary tail indicator
- Practical simplification: VRP itself embeds the tail component, so it works even without decomposition

**4. Modifier Construction:**
```
VRP_signal = VRP_overnight (close-to-open variance swap P&L proxy)
z_score = (VRP_signal - mean_60d) / std_60d

if z_score > +1.5:     modifier = 0.7  (high uncertainty, reduce sizing)
elif z_score > +0.5:   modifier = 0.85
elif z_score < -1.0:   modifier = 1.1  (low uncertainty, slight increase)
else:                   modifier = 1.0  (neutral)

Monday adjustment: modifier *= 0.95 on Monday mornings
```

**5. Warm-up:** 120 trading days for z-score baseline (HAR regression needs 250 days of RV, but VIX-based proxy available from day 1)

**6. Data Sources:**
- VIX, VXN, OVX: free, CBOE, daily close + open prices
- Intraday futures data: for RV computation (5-min bars minimum)
- Weekly options chain (if available): for tail risk decomposition

**7. Cross-references:**
- AIM-04 (Pre-Market/Overnight): overnight VRP decomposition feeds both modules
- AIM-06 (Economic Calendar): FOMC event risk creates VRP spikes (Paper 36)
- AIM-11 (Regime Warning): VRP regime (elevated vs. normal) is a leading indicator

---

# AIM-02: Options Skew & Positioning Analyzer

## Paper 47 — Pan & Poteshman (2006): The Information in Option Volume for Future Stock Prices

**What it proves:**
- THE seminal paper on options-based return prediction. Buyer-initiated open-position put-call ratio (PCR) predicts next-day stock returns by 40bp and next-week returns by >1% (risk-adjusted, quintile spread)
- The economic source is NONPUBLIC information (private signal), not market inefficiency
- Publicly observable PCR (Lee-Ready inferred) has much weaker, shorter-lived predictability that reverses — suggesting price pressure not information
- Higher predictability for stocks with higher PIN (concentration of informed traders)
- Full-service brokerage signals (which include hedge funds) provide much stronger predictability than discount brokerage
- Firm proprietary traders contain NO information about future prices — they are uninformed hedgers
- Deep OTM options (highest leverage) have the GREATEST predictability

**Methodology:**
- Data: UNIQUE CBOE dataset recording whether initiator is buyer/seller, opening/closing, and investor class (1990–2001)
- PCR = P / (P + C) where P, C are put/call contracts purchased by non-market-makers to open new positions
- Daily cross-sectional predictive regressions with 4-factor risk adjustment (market, size, value, momentum)
- Horizon analysis: τ = 1, 2, ..., 20 trading days
- PIN variable from Easley, Kiefer & O'Hara as proxy for informed trader concentration

**Quantitative results:**
- Lowest quintile PCR (bullish signal) outperforms highest quintile by >40bp next day, >1% next week (risk-adjusted)
- Predictability gradually dies out over several weeks — information eventually incorporated
- Non-public signal: persistent information-based predictability
- Public signal: 1-2 day predictability only, then reversal (price pressure)
- Bivariate test: non-public signal retains predictability; public signal loses ALL predictability
- Deep OTM options: highest predictability; ATM: moderate; ITM: lowest

**What we take:**
- PCR (specifically open-buy) is a validated directional signal for next-day returns
- For index options (ES/NQ), aggregate PCR across strikes weighted by OI is the practical proxy
- Deep OTM put/call activity carries more information than ATM
- The predictability is about informed trader positioning, not arbitrage opportunities
- Publicly available PCR is weaker but still usable as a conditioning signal

**What we leave:**
- Individual stock PCR construction (we trade indices/futures)
- Investor class decomposition (CBOE data not available to us)

---

## Paper 46 — Kaeck, van Kervel & Seeger (WP): Informed Trading in the Index Option Market

**What it proves:**
- Structural VAR decomposing SPX option order flow into delta exposure (directional) and vega exposure (volatility)
- 1σ vega order flow shock → volatility increases 0.07pp (14% of hourly volatility std deviation)
- Delta + vega order flows together explain 25% of volatility variation
- Option order flow is informative about BOTH underlying price direction AND volatility
- Cross-option strategies account for >75% of option volume — must aggregate across strikes/maturities

**Methodology:**
- 5-equation VAR: delta order flow, vega order flow, underlying return, VIX change, SPY order flow
- Data: SPX option trade/quote data + SPY + VIX (constructed at high frequency), 2014, hourly frequency
- Delta order flow = Σ(net order flow × option delta); Vega order flow = Σ(net order flow × option vega)
- Links structural option pricing model to model-free VIX framework

**What we take:**
- Decomposing option flow into delta (directional bet) and vega (volatility bet) components is the correct framework
- Net vega order flow direction reveals volatility expectations — complements AIM-01 VRP
- 25% of vol variation explained by option order flow = substantial information channel
- For practical implementation: compute aggregate delta-weighted and vega-weighted net volume daily

**What we leave:**
- Full 5-equation VAR implementation (too complex for AIM; use simplified aggregate measures)

---

## Paper 49 — Doran, Peterson & Tarrant (2007): Is There Information in the Volatility Skew?

**What it proves:**
- The SHAPE of the IV skew can predict market crashes and spikes with significant probability
- Short-term OTM puts provide the STRONGEST crash prediction signal
- DOTM put IV - OTM put IV spread (Δσ^P_do,o) is the key predictor variable
- Predictive power DECREASES with maturity: 10-30 day options >> 31-60 days >> 61-90 days
- Crash prediction is statistically significant; spike prediction is NOT economically significant
- Uses S&P 100 options, January 1984 – April 2006

**Methodology:**
- Options sorted by moneyness bins: DOTM (.875-.925), OTM (.925-.975), ATM (.975-1.025), ITM (1.025-1.075)
- Three maturity buckets: 10-30 days, 31-60 days, 61-90 days
- Skew variables: Δσ_do,o = DOTM IV - OTM IV; Δσ_do,a = DOTM IV - ATM IV; Δσ_do,i = DOTM IV - ITM IV
- Also uses Bakshi-Kapadia-Madan (2003) risk-neutral skewness measure
- Probit model for crash/spike prediction (crash = return ≤ -2.73%, spike = return ≥ +2.93%)
- Controls: term structure (10Y-1Y), ATM IV, bid-ask spread, OI, volume

**Quantitative results:**
- Crash thresholds: -1.65% (top 5% of negative returns), -2.73% (top 1%)
- 62 crash days identified over sample period; jumps cluster during high-vol periods
- DOTM-OTM put spread (short-term, 10-30 days) is significant crash predictor
- Put skew steepening (more negative) → higher crash probability
- Call skew provides weak and economically insignificant spike prediction
- Lee-Mykland jump test: 13 negative jump days, only 4 positive (too few for upside)

**What we take:**
- Monitor the put skew steepness (DOTM - OTM put IV spread) for short-term crash warning
- Use 10-30 day maturity bucket for maximum signal strength
- Steepening put skew → reduce sizing (crash risk elevated)
- Flat or normalising put skew → maintain/increase sizing
- One-sided: put skew is informative for downside; call skew is NOT useful for upside prediction

**What we leave:**
- S&P 100 specific analysis (we use S&P 500 / E-mini options)
- Full probit model implementation (we use skew as a continuous modifier, not binary crash/no-crash)

---

## Paper 48 — Saba, Bhuyan & Çetin (2025): Predicting Short-term Stock Returns with Weekly Options Indicators

**What it proves:**
- Weekly options OI and volume predict short-term returns for high-volume stocks and SPY
- Lagged OI call (OIC), OI put (OIP), volume call (VC), volume put (VP) ALL statistically significant after Fama-French + Amihud controls
- Both in-sample (2013-2022) and out-of-sample (Jan-Aug 2023) confirm robustness
- Non-price indicators showed ENHANCED predictive power during COVID-19 crisis (more effective than normal conditions)
- Portfolios based on predictions consistently outperform S&P 500 and NASDAQ 100 active trading strategies
- Moneyness filter (0.88-1.12) captures both informed and uninformed trading behaviour

**Methodology:**
- Data: OptionMetrics daily, weekly options on Magnificent 7 + SPY, 2013-2022 (IS), Jan-Aug 2023 (OOS)
- Weekly returns forecasted from lagged weekly option OI and volume
- GARCH modeling for return volatility forecasting using option predictors
- Fama-French (2012, 2015) + Amihud-Mendelson (1980) controls
- Comparison vs. S&P 500 and NASDAQ 100 active trading strategies

**What we take:**
- Weekly options OI + volume data are powerful SHORT-TERM return predictors
- The signal works for indices (SPY, QQQ) not just individual stocks
- Enhanced predictive power during high-volatility periods (COVID-19) — when Captain needs it most
- Practical: use lagged weekly OI and volume as input features

**What we leave:**
- Individual stock-level analysis (Magnificent 7) — we focus on index futures
- Specific portfolio construction methodology

---

## Paper 50 — Muravyev (2016): Order Flow and Expected Option Returns

**What it proves:**
- Option market-maker INVENTORY RISK has a first-order effect on option prices — larger than asymmetric information
- 1σ order imbalance increase → 1% higher next-day option return
- Inventory risk component is 5x LARGER than previously thought (IV approach vs. OLS: 3.7% vs. ~0.7%)
- Past order imbalances have greater predictive power than ANY of 50+ commonly used option return predictors
- Market-wide order imbalance has particularly large effect (portfolio-level inventory management)

**What we take:**
- Option order imbalance (buy pressure vs. sell pressure) is the DOMINANT predictor of short-term option returns
- Inventory risk drives pricing more than information asymmetry — understand this mechanism for interpreting signals
- Aggregate (market-wide) order imbalance carries the strongest signal
- Cross-ref AIM-03 (GEX): inventory/hedging flows are the core mechanism

**What we leave:**
- Option return prediction per se (we predict underlying returns, not option returns)

---

## Paper 41 — Ryu & Yang (2018): Directional Information Content of Options Volumes

**What it proves:**
- In KOSPI 200 index options: foreign investment firms' open-buy trades significantly predict next-day spot returns
- Domestic firms' trades do NOT predict
- Effect strongest for: OTM options, large trades, short-horizon options
- Confirmed during short-sale restriction period (options = alternative channel for informed trading)

**What we take:**
- Confirms Pan & Poteshman (2006) finding internationally (Korean market)
- OTM and large trades carry the most information — consistent across markets
- Open-buy classification is critical for signal quality
- Institutional (not retail) flow is the informative component

---

## Paper 44 — Houlihan & Creamer (2019): Leveraging a Call-Put Ratio as a Trading Signal

**What it proves:**
- Put-call ratio from specific market participants predicts asset price movements (March 2005 – December 2012)
- Portfolios based on PCR exhibit abnormal excess returns AFTER Carhart 4-factor adjustment AND transaction costs
- Confirms Pan & Poteshman (2006) signal survives real-world implementation costs

**What we take:**
- PCR signal is implementable in practice with actual transaction costs
- Cross-validates Pan & Poteshman's finding in a different sample period and with practical constraints

---

## Paper 45 — Fodor, Krieger & Doran (2011): Do Option Open-Interest Changes Foreshadow Future Equity Returns?

**What it proves:**
- Large call OI increases → significantly higher subsequent equity returns
- Put OI increases → weaker future returns (less pronounced with controls)
- Call-to-put OI RATIO has predictive power for equity returns over the following WEEK
- Supports Black's (1975) conjecture: information is first revealed in option markets

**What we take:**
- Weekly OI ratio changes are a validated weekly-horizon predictor
- Call OI increases more informative than put OI increases
- Complements Paper 47's daily PCR signal with a weekly-horizon OI signal

---

### AIM-02 Design Conclusions

**1. Primary Signal: Put-Call Ratio (PCR)**
- Compute daily aggregate PCR from options on ES/NQ (SPX options)
- Ideally: buyer-initiated open-position volume (if available from data provider)
- Practical proxy: total put volume / total call volume, weighted toward OTM strikes
- Low PCR (call-heavy) → bullish → modifier ≥ 1.0
- High PCR (put-heavy) → bearish/cautious → modifier < 1.0
- Deep OTM activity carries the most informative signal (Paper 47)

**2. Secondary Signal: Volatility Skew Shape**
- Compute DOTM-OTM put IV spread (Paper 49 methodology)
- Use 10-30 day maturity options for maximum signal strength
- Steepening put skew → crash risk elevated → reduce sizing
- Call skew is NOT useful for upside prediction — one-sided signal
- 25-delta risk reversal (RR) is a practical daily proxy: RR = IV_25δ_call - IV_25δ_put

**3. Supporting: Open Interest Changes (Weekly)**
- Large call OI increases → bullish (Paper 45)
- Rising put-to-call OI ratio → cautious (Papers 45, 48)
- Weekly options OI + volume enhanced during high-vol periods (Paper 48)

**4. Supporting: Order Flow Decomposition**
- Net delta order flow = directional information (Paper 46)
- Net vega order flow = volatility information (Paper 46)
- Inventory risk drives short-term option pricing more than information asymmetry (Paper 50)

**5. Modifier Construction:**
```
PCR_signal = z_score(PCR_today, trailing_30d)
skew_signal = z_score(DOTM_OTM_put_spread, trailing_60d)

combined = 0.6 × PCR_signal + 0.4 × skew_signal

if combined > +1.5:    modifier = 0.75  (heavy put buying + steep skew = high fear)
elif combined > +0.5:  modifier = 0.90
elif combined < -1.0:  modifier = 1.10  (call-heavy + flat skew = bullish)
else:                  modifier = 1.0
```

**6. Warm-up:** 60 trading days for PCR and skew z-score baselines

**7. Data Sources:**
- SPX/ES options chain: strikes, volumes, OI (OptionMetrics, CBOE, or broker feed)
- VIX skew / 25-delta risk reversal: Bloomberg or CBOE
- For CL: OVX-derived skew + CL options OI/volume (CME)

**8. Cross-references:**
- AIM-01 (VRP): put skew steepness ≈ proxy for tail risk premium
- AIM-03 (GEX): option OI drives dealer hedging flows — the inventory risk mechanism (Paper 50)
- AIM-04 (Pre-Market): PCR changes overnight may signal informed positioning before open
- AIM-06 (Economic Calendar): PCR spikes pre-event (Paper 47 shows predictability around events)

---

# AIM-03: Gamma Exposure (GEX) Estimator

## Paper 52 — Barbon & Buraschi (2020): Gamma Fragility — FOUNDATIONAL

**What it proves:**
- Large aggregate dealer GAMMA IMBALANCE in illiquid markets drives intraday momentum/reversal and market fragility
- NEGATIVE gamma imbalance → intraday momentum (positive autocorrelation) + HIGHER volatility + more/larger flash crashes
- POSITIVE gamma imbalance → intraday reversal (negative autocorrelation) + LOWER volatility
- Effect is DISTINCT from information frictions (VPIN/adverse selection) and funding liquidity frictions (margins)
- Effect strongest for LEAST liquid underlying securities
- Gamma imbalance retains significance even after controlling for VPIN

**Methodology:**
- Data: IvyDB OptionMetrics (OI + greeks) + TAQ (intraday returns/volume), 1996-2017, panel of 276 US equities + index
- Gamma imbalance = aggregate dollar value of all dealer outstanding gamma, computed from OI × option gamma across strikes/maturities
- Autocorrelation ρ of 5-min returns over 60-min windows (12 observations per window); 6,039,248 hourly observations
- Panel regressions: |return| on lagged gamma imbalance; autocorrelation on gamma imbalance
- Flash crash detection: Christensen, Oomen & Renò (2018) drift-burst methodology

**Quantitative results:**
- 34% of the time, |ρ| > 0.30 in 5-minute returns (strongly rejects random walk at intraday frequency)
- Negative gamma days → statistically significant increase in daily volatility; effect is TRANSITORY (gone after 2 days)
- Peak autocorrelation effect at h = 30 minute frequency (consistent with dealer rebalancing cadence)
- Flash crashes: conditional on negative ex-ante gamma, flash crashes are more likely AND larger in magnitude
- Flash crash effect becomes less relevant post-2010 (circuit breaker introduction)
- Cross-sectional: effect STRONGER for least liquid stocks

**What we take:**
- GEX sign determines the intraday volatility regime: NEGATIVE = amplification, POSITIVE = dampening
- For ORB strategy: negative gamma days → wider opening ranges, more momentum → larger potential moves BUT more volatile outcomes
- Positive gamma days → tighter ranges, mean-reversion → smaller moves BUT more predictable
- The 30-minute rebalancing cadence means gamma hedging pressure arrives DURING the ORB holding period
- Transitory (2-day) nature means GEX must be recomputed daily

**What we leave:**
- Individual stock-level analysis (we focus on index/futures)
- Full panel regression specification

---

## Paper 57 — Adams, Dim, Eraker et al. (2025): Do S&P500 Options Increase Market Volatility? Evidence from 0DTEs

**What it proves:**
- 0DTE trading DAMPENS S&P500 volatility by 60 annualized basis points on average (CAUSAL evidence)
- The dampening is NOT from intraday 0DTE trading but from PRE-EXISTING positions in longer-dated options that become 0DTEs
- Market makers' net gamma is a robust predictor of S&P500 intraday realized volatility
- 1σ increase in 0DTE net gamma → 25bp LOWER predicted S&P500 realized vol in next 10-minute interval
- Hedging needs multiplier: 1bp increase in hedging needs → 4bp DECREASE in realized vol
- Market makers' net gamma predicts ORDER FLOW REVERSALS and LOWER MOMENTUM returns intraday

**Methodology:**
- Data: OPRA intraday trades/quotes for SPX options, E-mini futures (DTN IQFeed), Cboe Open-Close Summary, 2018-2024
- Identification: exogenous variation in 0DTE presence on Tue/Thu before May 2022 (calendar-based rules)
- Diff-in-diff: before vs. after regular Tue/Thu 0DTE introduction in 2022
- 10-minute intervals; realized vol = √(sum of squared 1-min log returns) annualized
- Hedging needs = fraction of S&P500 shares market makers would buy/sell for 1% index move

**Quantitative results:**
- Treatment effect: -61 annualized bp on days with 0DTE trading (baseline regression with fixed effects)
- Pre-existing positions contribute 24bp hedging needs vs. only 3bp from new 0DTE positions on expiration day
- Non-0DTE hedging needs even DECREASE when 0DTEs are present
- Predictive: elevated 0DTE net gamma → stronger order flow reversals, lower momentum, lower vol (persists ~1 hour)
- 0DTE volume now accounts for nearly half of total SPX options volume (2024: >3M contracts/day)
- Effect persists in robustness checks (SPY, cash index, different fixed effects)

**What we take:**
- CRITICAL CONTEXT: the growing 0DTE market is currently a STABILISING force for S&P500
- Market makers' net gamma (including 0DTE) predicts 10-minute ahead volatility and order flow direction
- For Captain (Online): compute aggregate dealer gamma including 0DTE positions for the day
- Higher net gamma → expect lower intraday vol and mean-reversion → more predictable ORB environment
- E-mini futures is THE hedging instrument — hedging flows show up in ES order flow

**What we leave:**
- Identification strategy details (we use the conclusion, not the diff-in-diff setup)
- Debate about whether 0DTEs increase or decrease vol (resolved: they dampen on average)

---

## Paper 58 — Egebjerg & Kokholm: A Model for the Hedging Impact of Option Market Makers

**What it proves:**
- Delta hedging decomposes into TWO channels: gamma effect (from underlying price changes) + inventory effect (from new option trades)
- BOTH components are statistically significant and both predict SPX futures returns
- When both channels act in SAME direction → total impact is UNDERESTIMATED by gamma-only analysis
- When they act in OPPOSITE directions → gamma-only analysis OVERESTIMATES impact
- OMMs commonly hold net short positions → negative gamma exposure → trade in same direction as market moves
- End-of-day (last 30 min) delta hedge is a significant predictor of SPX futures return

**Methodology:**
- High-frequency SPX option trade data with novel trade classification algorithm (Grauer et al. 2023)
- Infer net option position of market makers from classified trades
- Decompose net delta change = gamma effect + inventory effect
- End-of-day analysis (last 30 min) + 5-minute intraday analysis
- Controls for various market factors

**Quantitative results:**
- Net delta change significantly predicts end-of-day SPX futures returns
- Intraday (5-min): largest absolute delta changes followed by SPX futures return in hedging direction
- Intraday hedging driven primarily by large option inventory changes, not underlying price fluctuations
- Triple witching days: effects are particularly pronounced
- Results robust to inclusion of control factors

**What we take:**
- Gamma effect alone underestimates total hedging impact — must consider option inventory changes too
- End-of-day hedging in last 30 min is predictable from delta position → relevant for intraday exit timing
- Large option inventory changes trigger immediate intraday hedging → sharp futures moves
- For ORB: if large option trades occur near the open (e.g., block trades), expect immediate hedging flow

**What we leave:**
- Full model specification (constant drift/vol with linear price impact framework)
- Trade classification algorithm details

---

## Paper 60 — Golez & Jackwerth (2012): Pinning in the S&P 500 Futures

**What it proves:**
- S&P 500 futures are PULLED TOWARD ATM strike on serial option expiration days (PINNING)
- Futures are PUSHED AWAY from cost-of-carry adjusted ATM strike right before index option expiration (ANTI-CROSS-PINNING)
- Driven by market makers' delta hedge rebalancing from: (1) time decay of hedges, (2) reselling of ITM options by retail investors, (3) early exercise
- Associated shift: at least $115M per expiration day (recent period: $240M)
- Net effect: reselling + exercise OVERCOME anti-pinning from time decay → net pinning

**Methodology:**
- Data: S&P 500 futures, November 1992 – November 2009
- Serial expirations (non-quarterly months) where SP options expire but futures continue trading
- Ni et al. (2005) methodology for pinning detection
- Logistic regressions explaining pinning vs. anti-pinning from volume, OI, early exercise

**What we take:**
- On option expiration days: expect range compression near high-OI strikes → ORB signal may be distorted
- Expiration day adjustment: reduce confidence in ORB signal (pinning pulls price toward strike, dampening breakout)
- Anti-cross-pinning on quarterly SPX expiration (AM-settled) → different dynamic than serial
- $240M notional shift = economically meaningful distortion even in the most liquid market

**What we leave:**
- Detailed pinning/anti-pinning distinction by expiration type (we apply a blanket expiration-day caution)

---

## Paper 53 — Barbon, Beckmeyer, Buraschi & Moerke (2022): Liquidity Provision to LETFs and Equity Options Rebalancing Flows

**What it proves:**
- Delta-hedging of equity options AND leveraged ETF (LETF) rebalancing BOTH induce end-of-day momentum and mean-reversion
- Positive gamma → end-of-day REVERSAL; Negative gamma → end-of-day MOMENTUM
- Gamma effects are PERSISTENT throughout sample; LETF effects have DECREASED over time
- Intermediaries strategically choose timing of delta-hedging → less predictable flows than LETF
- LETF flows attract more liquidity provision (publicly disclosed) → effects absorbed faster

**Quantitative results:**
- Tesla example (13 Dec 2012): positive gamma, -6.62% intraday → hedging demand = 102.11% of avg last-30-min dollar volume → STRONG price reversal
- Apple example (24 Oct 2018): gamma ≈ 0, LETF rebalancing = 8.85% of avg volume → -1.22% further decline
- Amazon example (23 Jun 2016): positive gamma, -4% intraday → hedging demand ≈ 50% of avg volume → partial mean reversion

**What we take:**
- End-of-day dynamics (last 30 min) are predictable from gamma + LETF data
- For ORB exit timing: if holding through end of day, gamma sign predicts whether trend continues (negative gamma) or reverses (positive gamma)
- LETF rebalancing is a SEPARATE channel from gamma hedging — both matter for end-of-day
- Cross-ref AIM-10 (Calendar): LETF rebalancing amplified on high-volume/high-move days

---

### AIM-03 Design Conclusions

**1. Core Signal: Net Dealer Gamma Exposure (GEX)**
- Compute daily from prior day's option OI data: GEX = Σ (dealer_net_OI × option_gamma × contract_multiplier × spot²) across all strikes/maturities
- Dealers are typically net short index options → negative gamma is the default state
- Sign determines intraday regime:
  - **Negative GEX** → amplification: intraday momentum, higher vol, flash crash risk
  - **Positive GEX** → dampening: mean-reversion, lower vol, more predictable

**2. For ORB Strategy:**
- Negative gamma days → wider opening ranges, more momentum potential BUT more volatile, less predictable outcomes
- Positive gamma days → tighter ranges, mean-reversion tendency → smaller ORB moves BUT higher hit rate
- The 30-minute dealer rebalancing cadence (Paper 52) means hedging flows arrive DURING the ORB holding window
- 0DTE-era context: net GEX often elevated due to accumulated positions turning 0DTE → currently stabilising (Paper 57)

**3. Expiration Day Effect:**
- Pinning pulls prices toward high-OI strikes → reduces breakout probability → ORB signal reliability lower (Paper 60)
- End-of-day momentum/reversal predictable from gamma sign (Paper 53)
- Triple witching days: effects particularly pronounced (Paper 58)

**4. Modifier Construction:**
```
GEX_today = aggregate_dealer_gamma (from prior day OI data)
GEX_z = z_score(GEX_today, trailing_60d)

if GEX_z < -1.0:     modifier = 0.85  (amplification regime, more risk)
elif GEX_z > +1.0:   modifier = 1.10  (dampening regime, more stable)
else:                 modifier = 1.0

Expiration day: modifier *= 0.95 (pinning risk)
Triple witching: modifier *= 0.90
```

**5. Warm-up:** 60 trading days to establish GEX distribution for z-score thresholds

**6. Data Sources:**
- Option OI by strike/maturity: CBOE (SPX/SPXW), CME (ES options, CL options)
- Option greeks: compute from Black-Scholes using prior day's IV surface, or from OptionMetrics/data provider
- LETF data: publicly available AUM/leverage ratios for QLD, TQQQ, UPRO, etc.

**7. Cross-references:**
- AIM-01 (VRP): negative gamma amplifies VRP effects; both signal risk
- AIM-02 (Skew/Positioning): PCR shifts feed dealer inventory → change gamma exposure
- AIM-10 (Calendar): expiration pinning, LETF rebalancing effects
- AIM-12 (Costs): gamma regime affects slippage (amplification → wider spreads)

---

# AIM-04: Pre-Market & Overnight Session Analyzer

## Paper 61 — Liu & Tse (2017): Overnight Returns of Stock Indexes: Evidence from ETFs and Futures

**What it proves:**
- Overnight returns (close-to-open) of US ETFs and MOST international index futures are significantly POSITIVE
- Trading-hour returns (open-to-close) are insignificant or NEGATIVE
- Overnight VOLATILITY is substantially LOWER than trading-hour volatility
- Tail risk (VaR, ES): overnight component contributes LESS than daytime — overnight is less risky
- Overnight returns PREDICT: first-30-min returns (NEGATIVE relation) and last-30-min returns (POSITIVE relation)
- Middle-of-day returns are NOT predictable from overnight
- Both in-sample and out-of-sample predictability confirmed

**Methodology:**
- Data: SPY + 9 sector ETFs (TAQ), E-mini S&P 500 futures (TickData), 12 international index futures (CSI), 1999-2014
- EVT (Extreme Value Theory) for tail risk
- Copula function for joint distribution of overnight and daytime returns → decompose VaR and ES
- Clark-West (2007) OOS test for nested models

**Quantitative results:**
- All US ETFs and most international futures: overnight returns significantly positive
- Overnight VaR/ES contribution substantially lower than daytime
- Overnight return → first-30-min return: NEGATIVE coefficient (gap reversal tendency)
- Overnight return → last-30-min return: POSITIVE coefficient (intraday momentum)
- First-30-min returns CANNOT predict last-30-min returns (these are independent signals)

**What we take:**
- Overnight return is a pre-open signal with TWO effects: initial gap reversal (first 30 min) then continuation (last 30 min)
- For ORB (market open entry): the GAP REVERSAL tendency in first 30 min is directly relevant — large overnight moves may mean-revert initially
- Low overnight volatility + high overnight return = attractive holding period anomaly (context for overnight strategies)
- Cross-market: pattern holds internationally across electronic futures markets

---

## Paper 67 — Donninger (2014): An Investigation of Simple Intraday Trading Strategies — CRITICAL FOR MOST

**What it proves:**
- Tests ORB and gap trading strategies on E-mini S&P 500 futures with REALISTIC transaction costs
- Simple ORB strategy LOSES attractiveness when including round-trip costs of $25/trade
- THE key finding: IVTS (Implied Volatility Term Structure) = VIX/VXV is the BEST regime classifier for intraday strategies
- ORB works only in specific IVTS regimes: [0.93, 1.0] = "medium excited" market → best performance
- IVTS > 1.0 = market turmoil → avoid ORB (and all intraday long strategies)
- IVTS ≤ 0.93 = quiet market → trading costs eat gains
- Gap trading: S&P keeps overnight direction for ~5 minutes after open then reverses. Turnaround time has shortened.

**Methodology:**
- Data: ES E-mini, 1-min HF data (IQFeed), 2010-08-24 to 2014-08-24
- ORB: buy at +0.15% above open (before 15:30), SL 1.8%, TP 0.8%, exit at 16:00
- Transaction costs: 12.5$ per trade per future (1 tick = bid-ask spread estimate)
- IVTS = VIX(t)/VXV(t) as regime filter

**Quantitative results:**
- ORB without costs: +139.8%, Sharpe 1.012 vs. SPY +105.2%, Sharpe 1.025
- ORB with costs ($25 round-trip): +35.4%, Sharpe 0.469 — mostly eaten by costs
- ORB with IVTS [0.93, 1.0] filter + costs: +43.5%, Sharpe 0.812 (with 3x leverage: +171.3%, Sharpe 0.764)
- Short side ORB does NOT work (headwind from bull market)
- Gap: overnight direction continues ~5 min, then reverses (too short to capture after costs for non-HFT)

**What we take:**
- IVTS (VIX/VXV) is a VALIDATED regime filter for ORB strategies on ES — DIRECTLY feeds Captain (Online)
- IVTS ≤ 0.93: quiet, costs dominate → reduce sizing or skip
- IVTS [0.93, 1.0]: medium excitement → optimal regime for ORB → full sizing
- IVTS > 1.0: turmoil → avoid intraday long entries
- Gap reversal timing: ~5 min after open (useful for entry timing)
- Transaction costs are the BINDING constraint — any strategy must account for them

**Cross-references:** AIM-01 (VRP relates to IVTS), AIM-12 (cost estimation critical)

---

## Paper 65 — Rosa (2022): Understanding Intraday Momentum Strategies

**What it proves:**
- Intraday momentum (overnight return → last-30-min return) DISAPPEARS in OOS period post-2013
- BUT: Markov-switching model identifies TWO regimes — low and high predictability
- High predictability state occurred only during COVID-19 crisis (March-December 2020) in post-publication sample
- THRESHOLD-based strategy (trade only when |overnight return| > threshold) → HIGHER success rate, average return, and Sharpe ratio
- Optimal threshold > 0 (intermittent strategy outperforms always-active strategy)
- Significant risk-adjusted alpha; very low factor loadings to Fama-French factors (diversification value)

**Methodology:**
- Data: E-mini S&P 500, 5-min prices, September 1997 – December 2020
- McLean-Pontiff (2016) approach: in-sample, post-sample, post-publication splits
- Markov-switching model for regime identification
- Overnight return = close_{t-1} to open_t; Last 30-min return = close_t to close_t-30min

**Quantitative results:**
- In-sample (1997-2013): significant predictability
- Post-publication (2014-2020): predictability disappears in calendar time
- Markov-switching: high predictability regime = March-December 2020 ONLY
- Threshold strategy: success rate, avg return per trade, and Sharpe ALL increase with threshold
- Total return: hump-shaped vs. threshold (there's an optimal threshold, not too aggressive)
- Risk-adjusted: significant alpha, near-zero factor loadings

**What we take:**
- CRITICAL: intraday momentum is NOT a reliable standalone signal — it is REGIME-DEPENDENT
- Only works during HIGH VOLATILITY periods (COVID-19 type)
- Threshold-based filtering is essential: trade only when overnight return is large enough
- For Captain (Online): compute |overnight return|, only generate momentum signal when above threshold
- Confirms AIM-01/Paper 67: regime conditioning is THE key to intraday strategy viability
- Very low correlation with standard risk factors → genuine diversification

---

## Paper 62 — Wen, Indriawan, Lien & Xu (2023): Intraday Return Predictability in the Crude Oil Market: The Role of EIA Announcements

**What it proves:**
- EIA inventory announcements (Wed 10:30 ET) SHIFT the intraday momentum pattern for crude oil
- On EIA days: 3rd half-hour returns (10:30-11:00) significantly predict last-30-min returns (NOT the 1st half-hour)
- On NON-EIA days: 1st half-hour returns predict last-30-min returns (standard pattern)
- Dominant source on non-EIA days: overnight component of 1st half-hour return
- EIA announcement effect stronger during: high volatility, high adverse selection costs, lower liquidity, larger trades
- Informed traders process EIA information → momentum builds post-announcement

**Methodology:**
- Data: USO ETF, 5-min prices, April 2006 – July 2019
- Split by EIA vs. non-EIA days; predictive regressions; HAC standard errors

**What we take:**
- For CL: on EIA announcement Wednesdays, the information signal SHIFTS to post-10:30 ET
- Standard overnight-based ORB timing may be LESS effective on EIA days for CL
- Captain (Online) should flag EIA days and either: (a) delay CL signal to post-10:30, or (b) reduce CL sizing pre-10:30
- Cross-ref AIM-06 (Economic Calendar): EIA is a scheduled event that changes intraday dynamics

---

## Paper 68 — Ma, Wahab, Chevallier & Li (2023): Oil Futures Overnight vs Intraday Information for US Stock Vol

**What it proves:**
- Oil futures OVERNIGHT RV predicts US stock market (S&P 500) volatility (CROSS-MARKET effect)
- High overnight oil RV → high S&P 500 RV next day
- NEGATIVE overnight oil returns are more powerful predictors than positive (leverage effect)
- Decompositions based on signed intraday returns significantly improve predictive ability (OOS)
- Effect strongest during: high US stock market fluctuations AND high/low EPU states

**What we take:**
- CROSS-ASSET signal: overnight CL volatility predicts next-day ES volatility
- Captain (Online) can use overnight CL RV as a conditioning variable for ES sizing
- Negative overnight CL returns = elevated ES risk → reduce ES sizing
- Cross-ref AIM-08/09 (Cross-Asset): overnight CL → ES transmission channel

---

## Paper 66 — Grant, Wolf & Yu (2005): Intraday Price Reversals in US Stock Index Futures (15-year study)

**What it proves:**
- Highly significant intraday price reversals in S&P 500 futures following large price changes at market open
- Consistent over 15 years (Nov 1987 – Sep 2002) and across day-of-week
- Stronger reversals after large POSITIVE openings than negative
- BUT: after adjusting for bid-ask proxy → significance SHARPLY reduced
- Market efficiency likely holds after transaction costs

**What we take:**
- Large opening gaps tend to reverse intraday — confirms Paper 61's finding
- For ORB: a very large gap at open = higher probability of reversal rather than continuation
- Gap DIRECTION asymmetry: positive gaps reverse more reliably
- Transaction costs again the binding constraint — gap fading only works at very low cost

---

## Paper 69 — Janse van Rensburg & Van Zyl (2025): Price Gaps and Volatility: Do Weekend Gaps Tend to Close?

**What it proves:**
- Weekend gaps do NOT reliably close at short distances across DJIA, NASDAQ, DAX
- At medium-to-large distances: significant directional patterns (gap CONTINUATION), especially in DAX
- Larger gaps → HIGHER subsequent volatility
- Gap anomalies VARY by market structure and geography (DAX behaves differently from US)

**What we take:**
- Monday opens: do NOT assume weekend gaps will fill — they may extend
- Larger gaps = elevated volatility signal → adjust sizing
- Confirms Paper 65: regime matters (gap behaviour varies by market conditions)
- Cross-ref AIM-01 (VRP): Monday weekend uncertainty premium + gap volatility

---

## Paper 70 — Aleti, Bollerslev & Siggaard (2024): Intraday Market Return Predictability Culled from the Factor Zoo

**What it proves:**
- Intraday market return IS predictable using ML on 200+ cross-sectional factor returns
- OOS Sharpe ratio: 1.37 for SPY (vs. 0.09 buy-and-hold intraday)
- Abnormal returns concentrated in HIGH ECONOMIC UNCERTAINTY periods
- Key predictive factors: tail risk and LIQUIDITY measures
- Most overall market return accrues during OVERNIGHT period (not intraday)
- Continuous (smooth) returns are predictable; jump returns are NOT → filter out jumps before prediction

**What we take:**
- Intraday predictability CONCENTRATES in high-uncertainty periods — confirms regime-dependence finding
- Tail risk and liquidity factors drive intraday predictability → cross-ref AIM-01, AIM-05
- For Captain (Online): aggregate factor returns from prior interval could enhance ORB signal
- Overnight period captures most TOTAL return → holding overnight has higher return expectation

---

### AIM-04 Design Conclusions

**1. Overnight Return as Primary Pre-Open Signal:**
- Compute overnight return (close_{t-1} to pre-open/open_t) for each asset
- Large overnight return = TWO effects: (a) initial gap reversal in first 30 min, (b) last-30-min continuation
- For ORB (entry at/near open): LARGE overnight moves may mean-revert initially → factor into entry timing
- Threshold filtering essential: only generate strong directional signal when |overnight return| exceeds threshold (Paper 65)

**2. IVTS (VIX/VXV) as Regime Filter — DIRECTLY FOR MOST:**
- IVTS = VIX/VXV, computed daily from CBOE
- IVTS ≤ 0.93: quiet market → costs dominate, ORB marginal → modifier 0.80
- IVTS [0.93, 1.0]: medium excitement → OPTIMAL for ORB → modifier 1.10
- IVTS > 1.0: turmoil → avoid intraday longs → modifier 0.65
- This is a VALIDATED regime classifier for ORB on ES (Paper 67)

**3. CL-Specific: EIA Announcement Days:**
- Wednesday 10:30 ET EIA releases SHIFT the intraday momentum signal for crude oil
- On EIA days: standard overnight-based ORB signal is weaker; post-10:30 signal stronger
- Captain (Online) should flag EIA Wednesdays and adjust CL entry timing or sizing

**4. Cross-Market Overnight Signals:**
- CL overnight RV predicts next-day ES volatility (cross-market transmission)
- Negative overnight CL returns → elevated ES risk → condition ES sizing downward

**5. Gap Behaviour:**
- Large positive gaps reverse more reliably than negative gaps (Paper 66)
- Weekend gaps do NOT reliably close — may extend (Paper 69)
- Larger gaps = higher subsequent volatility → size adjustment needed
- Monday morning: combine gap signal with weekend VRP uncertainty from AIM-01

**6. Modifier Construction:**
```
overnight_return = close_{t-1} to open_t
IVTS = VIX / VXV

# IVTS regime filter (primary)
if IVTS > 1.0:        ivts_mod = 0.65  (turmoil)
elif IVTS >= 0.93:     ivts_mod = 1.10  (optimal)
else:                  ivts_mod = 0.80  (quiet)

# Overnight return signal (secondary)
overnight_z = z_score(|overnight_return|, trailing_60d)
if overnight_z > 2.0:   gap_mod = 0.85  (extreme gap, expect reversal/volatility)
elif overnight_z > 1.0: gap_mod = 0.95
else:                    gap_mod = 1.0

modifier = ivts_mod × gap_mod

# CL on EIA Wednesday: modifier *= 0.90
```

**7. Warm-up:** 60 trading days for overnight return z-score; IVTS available from day 1

**8. Data Sources:**
- VIX, VXV: CBOE, daily (free)
- Overnight returns: close/open prices from futures data feed
- EIA calendar: publicly available, fixed schedule (Wednesdays 10:30 ET)

**9. Cross-references:**
- AIM-01 (VRP): overnight VRP decomposition feeds here; Monday VRP compound effect
- AIM-06 (Economic Calendar): EIA announcements shift CL intraday dynamics
- AIM-08/09 (Cross-Asset): overnight CL → ES volatility transmission
- AIM-12 (Costs): transaction costs are THE binding constraint for intraday strategies

---

# AIM-05: Order Book Depth/Imbalance at Open — DEFERRED (L2 data cost)

## Paper 78 — Lipton, Pesavento & Sotiropoulos (2014): Trading Strategies via Book Imbalance (Risk magazine)

**What it proves:**
- Book imbalance I = (q_bid - q_ask)/(q_bid + q_ask) is a good predictor of mid-price movements
- Price change is well approximated as a LINEAR function of imbalance
- High imbalance → shorter waiting time until next price change
- BUT: price change is typically well BELOW the bid-ask spread → no straightforward statistical arbitrage
- Stochastic model: 3D diffusion with Fourier-Laplace expansion, semi-analytical solution

**What we take:**
- Book imbalance is the simplest and most validated microstructure signal
- Linear relationship: heavier bid side → next move likely up, and vice versa
- For ORB entry: if available, check book imbalance direction at open to confirm ORB signal
- Sub-spread moves → useful for entry TIMING and CONFIRMATION, not standalone direction

---

## Paper 80 — Cont, Cucuringu & Zhang (2023): Cross-Impact of Order Flow Imbalance in Equity Markets

**What it proves:**
- Multi-level OFI (integrating top 5-10 LOB levels) explains price impact BETTER than best-level OFI alone
- Contemporaneous: once multi-level OFI is integrated, cross-asset OFI adds NO additional explanatory power
- LAGGED cross-asset OFIs DO improve FORECASTING of future returns — but decays RAPIDLY (short-term only)
- Sparse single-asset model sufficient for contemporaneous impact; cross-asset only for prediction

**Methodology:**
- Data: Equity markets (LOB data), multi-level OFI construction
- Single-asset vs. multi-asset regression; in-sample vs. OOS forecasting
- 10,793 article views, 16 citing articles

**What we take:**
- If L2 data available: compute multi-level OFI by integrating across LOB depth, not just top-of-book
- Cross-asset OFI lagged signals decay within minutes — only useful for very short-term positioning
- For ORB: multi-level OFI at the open captures aggregate buying/selling pressure beyond just bid-ask
- Cross-ref AIM-08/09: cross-asset OFI confirms the cross-market transmission at microstructure level

---

## Paper 74 — Hu & Zhang (2025): Stochastic Price Dynamics from OFI (CSI 300 Index Futures)

**What it proves:**
- OFI is analogous to a SHOCK to the market — modeled as Ornstein-Uhlenbeck process with memory and mean-reversion
- Driven by jump-type Lévy process (heavy-tailed), NOT Gaussian
- Horizon-dependent heterogeneity: conventional metrics interact DIFFERENTLY at different forecast horizons
- REGIME-DEPENDENT dynamics in OFI memory and forecasting power
- Quasi-Sharpe ratio (response ratio) provides risk-adjusted performance measure by forecast horizon

**What we take:**
- OFI signals have OPTIMAL forecast horizons that vary by regime — cannot use one fixed horizon
- Heavy-tailed OFI distribution means extreme imbalances are more common than Gaussian would predict
- Regime conditioning (from Program 2 or AIM-11) should determine which OFI forecast horizon to use
- Mean-reverting nature: large OFI signals decay — must act quickly

---

## Paper 71 — Wang (2025): Order Book Curvature as Liquidity Measure (CL Futures)

**What it proves:**
- LOB curvature (power-law relation between price distance and cumulative depth) is a new liquidity measure
- Curvature shocks → reduce depth, widen spreads
- Curvature significantly IMPROVES volatility forecasts beyond traditional liquidity measures (spread, depth)
- CL-specific: CME crude oil futures, high-frequency data
- EIA news effect is INSIGNIFICANT after controlling for intraday seasonality → liquidity dynamics are endogenous
- VAR with impulse-response analysis; TSRV for volatility estimation

**What we take:**
- For CL: LOB curvature is a superior liquidity measure for volatility prediction
- If L2 CL data available: compute curvature, use for volatility conditioning (complements AIM-01 VRP)
- Confirms Paper 62 (AIM-04): EIA effect is endogenous within liquidity dynamics

---

## Paper 72 — Andersen & Bondarenko (2015): Assessing VPIN — CRITICAL METHODOLOGICAL LESSON

**What it proves:**
- VPIN (Volume-synchronized Probability of Informed Trading) is methodologically FLAWED
- BVC (Bulk Volume Classification) used by VPIN is INFERIOR to standard tick rule for trade classification
- VPIN predicts volatility ONLY because increasing volatility induces SYSTEMATIC CLASSIFICATION ERRORS in BVC
- Once errors are corrected, VPIN has NO genuine predictive power for toxicity or market turbulence
- Uses E-mini S&P 500 futures with accurate trade classification from quotes + trade data

**What we take:**
- DO NOT USE VPIN as implemented by Easley et al. for order flow toxicity measurement
- Trade classification methodology MATTERS — BVC is flawed; use tick rule or quote-based classification
- Any microstructure signal must be validated against proper classification benchmarks
- Spurious predictive power from data processing artifacts is a REAL risk — applies to all AIM-05 signals

---

## Paper 77 — Easley, López de Prado & O'Hara (2012): Flow Toxicity and Liquidity (VPIN) — Original

**What it proves (claimed):**
- VPIN = volume-synchronized probability of informed trading, updated in volume time
- Order flow toxicity = adverse selection of market makers providing liquidity at a loss
- Volume bucketing reduces volatility clustering impact
- Claims VPIN is useful indicator of short-term toxicity-induced volatility

**What we take:**
- The CONCEPT of flow toxicity is valuable — when informed order flow adversely selects market makers, liquidity withdraws
- The IMPLEMENTATION (VPIN with BVC) is flawed (Paper 72). Use the concept with better classification.
- Volume time (bucketing) is still a useful idea for standardising microstructure analysis

---

## Paper 75 — Tsantekidis et al. (2020): DL for Price Prediction from Stationary LOB Features

**What it proves:**
- Stationarity transformation of LOB features enables effective deep learning application
- Combined CNN+LSTM model outperforms individual CNN and LSTM for mid-price prediction
- Key: raw LOB data is non-stationary; must transform before ML application

**What we take:**
- If building an ML-based OFI model in future: use stationarity transformations (normalisation, differencing)
- CNN (spatial structure across levels) + LSTM (temporal dynamics) is the right architecture for LOB data
- Reference implementation for future AIM-05 activation

---

## Paper 79 — Paddrik et al. (2017): LOB Information Level and Market Stability Metrics

**What it proves:**
- Higher-fidelity microstructure data (Level 6 with trader IDs) → BETTER flash crash prediction
- Can signal flash crash ~1 MINUTE in advance
- Validated on May 6, 2010 Flash Crash (ES) and Sep 17, 2012 mini flash crash (CL)
- Agent-based model simulation + actual CME/NYMEX data
- Publicly available Level 2 data is helpful but Level 6 (regulatory) is significantly better

**What we take:**
- Flash crash early warning with ~1 min lead time IS feasible with detailed microstructure data
- For AIM-05 activation: even Level 2 data provides useful stability signals, but expectations should be managed
- Cross-ref AIM-03 (GEX): flash crash risk also linked to negative dealer gamma

---

### AIM-05 Design Conclusions — FOR FUTURE ACTIVATION (currently DEFERRED due to L2 data cost)

**1. Primary Signal: Book Imbalance at Open**
- I = (q_bid - q_ask) / (q_bid + q_ask) at best bid/ask levels
- Linear predictor of next mid-price tick direction (Paper 78)
- Heavier bid → expect up move; heavier ask → expect down move
- Sub-spread signal → entry CONFIRMATION and TIMING, not standalone direction

**2. Enhanced Signal: Multi-Level OFI**
- Integrate OFI across top 5-10 LOB levels, not just top-of-book (Paper 80)
- Multi-level OFI captures aggregate buying/selling pressure more accurately
- Cross-asset lagged OFI adds predictive power but decays within minutes

**3. CL-Specific: LOB Curvature**
- Power-law curvature measure improves volatility forecasts for CL beyond spread/depth (Paper 71)
- If CL L2 data available: compute curvature as supplementary volatility conditioning signal

**4. Regime Conditioning:**
- OFI dynamics are regime-dependent with horizon-dependent heterogeneity (Paper 74)
- Must select appropriate forecast horizon per regime — no universal fixed horizon

**5. Methodological Warnings:**
- VPIN is flawed — do NOT use BVC for trade classification (Paper 72 vs. 77)
- Use tick rule or quote-based classification instead
- Stationarity transformation required before any ML application on LOB data (Paper 75)

**6. Flash Crash Early Warning:**
- Feasible with ~1 min lead time from detailed microstructure data (Paper 79)
- Cross-refs AIM-03 (GEX negative gamma) for complementary flash crash risk signal

**7. Activation Requirements:**
- L2 order book data feed (CME for ES/NQ/CL)
- Estimated cost: $500-2000/month depending on depth and vendor
- When activated: compute book imbalance + multi-level OFI at open as modifier for ORB direction confidence

**8. Modifier Construction (when activated):**
```
book_imbalance = (q_bid - q_ask) / (q_bid + q_ask) at open
OFI_multilevel = weighted sum of OFI across top 5 levels

if book_imbalance aligns with ORB direction:   modifier = 1.10  (confirmation)
elif book_imbalance opposes ORB direction:     modifier = 0.85  (contradiction)
else:                                          modifier = 1.0

# Curvature overlay for CL:
if curvature_z > 1.5:  modifier *= 0.90  (low liquidity, wider expected slippage)
```

**9. Warm-up:** 20 trading days to establish OFI distribution baselines (fast warm-up due to HF data)

**10. Cross-references:**
- AIM-03 (GEX): dealer gamma + OFI = comprehensive microstructure picture
- AIM-08/09 (Cross-Asset): cross-asset OFI lag confirms transmission channel
- AIM-12 (Costs): LOB curvature directly informs slippage estimation

---

# AIM-06: Economic Calendar Impact Model

## Paper 82 — Miao, Ramchander & Zumwalt (2014): S&P 500 Index-Futures Price Jumps and Macroeconomic News

**What it proves:**
- Over 3/4 of S&P 500 futures price jumps at 8:30 AM and over 3/5 at 10:00 AM are related to scheduled macro news
- NON-FARM PAYROLL and CONSUMER CONFIDENCE are the strongest jump-causing announcements
- Price adjustment is rapid: most jumps complete within 5 minutes of release
- Speed differs by announcement type and by trading platform (electronic Globex faster than pit)
- Jump detection: Lee-Mykland (2008) methodology identifies precise intraday timing

**Methodology:** S&P 500 futures (full-size SP + E-mini ES), 2001-2010, intraday tick data

**What we take:**
- NFP (first Friday, 8:30 ET) and Consumer Confidence are THE highest-impact events for ES
- 8:30 AM and 10:00 AM are the critical news windows → if ORB entry overlaps, expect jumps
- Most price adjustment within 5 minutes → ORB signal may be overwhelmed by news reaction
- Captain (Online) should identify if open overlaps with 8:30 release and adjust accordingly

---

## Paper 88 — Laarits (2024): Pre-Announcement Risk (Pre-FOMC Drift)

**What it proves:**
- Pre-FOMC drift = 162 bps/YEAR from holding equity market during intraday pre-announcement trading (8 FOMC days)
- Post-announcement: -24 bps/year (zero or slightly negative)
- This is a RISK PREMIUM, not information leakage — investors earn compensation for bearing interpretation uncertainty
- Key mechanism: recent news determines how FOMC action is INTERPRETED
  - Good recent news → Fed action = growth signal (informational channel) → negative stock-bond covariance
  - Bad recent news → Fed action = policy stance signal (traditional channel) → positive stock-bond covariance
- Market return PRE-announcement predicts interpretation type
- Calibration: 19bp pre-announcement return matches 20bp empirical value

**What we take:**
- FOMC days: expect elevated returns BEFORE announcement, zero/negative AFTER
- For ORB: if FOMC is at 2 PM and ORB is at open, the morning session may carry a risk premium
- Recent market performance predicts FOMC interpretation → Captain can condition on recent 5-day return
- Pre-FOMC drift is genuine compensation for risk, not an arbitrage opportunity

---

## Paper 90 — Kurov, Sancetta, Strasser & Wolfe (2015): Price Drift Before US Macroeconomic News

**What it proves:**
- 7 out of 18 market-moving announcements show evidence of INFORMED TRADING before official release
- Prices drift in the "correct" direction starting ~30 MINUTES before announcement
- Pre-announcement drift accounts for MORE THAN HALF of the total price adjustment
- Post-announcement returns alone SUBSTANTIALLY UNDERSTATE the true news impact
- Private organisations' releases have STRONGER drifts (information leakage + superior forecasting)
- Two explanations: (1) information leakage, (2) superior forecasting from public data reprocessing

**Methodology:** E-mini S&P 500 + 10-year Treasury futures, second-by-second data, Jan 2008 - Mar 2014

**What we take:**
- For 7 key announcements: prices already move 30 min BEFORE release → ORB signal at open may already reflect upcoming news
- Post-announcement returns understate total impact → looking only at post-news reaction gives incomplete picture
- Captain (Online) should weight pre-announcement drift into expected return calculations
- Private-source data (e.g., ISM, Consumer Confidence) may have MORE leakage than government data (e.g., NFP)

---

## Paper 81 — Cai, Ahmed, Jiang & Liu (2020): US Macro News Impact on Chinese Commodity Futures

**What it proves:**
- US macro news SURPRISE components significantly affect returns, volume, and volatility of Chinese commodity futures
- Gold and silver futures most sensitive; base metals and agricultural less so
- Asymmetric effect: positive and negative surprises have different magnitudes
- Cross-border information transmission confirmed (US → China channel)
- After introduction of night trading in China: stronger linkage

**What we take:**
- US macro events affect global commodity markets, not just US — relevant for CL if trading globally
- Gold/silver most responsive → if expanding to metals futures, macro calendar even more critical
- Cross-ref AIM-08/09: US macro news as a cross-market transmission mechanism

---

## Paper 83 — Boucher, Gagnon & Power (2026): Speculative Trading in Energy Markets and Macro Surprises

**What it proves:**
- Increased speculative trading LESSENS the impact of macro surprises on energy futures (CL, NG)
- Speculators IMPROVE liquidity and price discovery, REDUCE volatility around announcements
- Damping effect STRONGER for procyclical commodities (CL, NG) than safe havens (gold)
- Money managers (not swap dealers) drive the positive effects
- 26 macro announcement types examined

**What we take:**
- More speculative activity = better execution quality around macro events for CL
- In periods of HIGH speculative activity: macro impact is dampened → ORB signal may be MORE reliable
- In periods of LOW speculative activity: macro impact is amplified → reduce sizing
- Cross-ref AIM-07 (COT): speculator positioning data can proxy for speculative activity level

---

## Paper 87 — Erenburg, Kurov & Lasser (2006): Trading Around Macro Announcements

**What it proves:**
- Exchange locals react FASTER than off-exchange traders to macro news (first 20 seconds)
- Locals are net buyers (sellers) during good (bad) news; off-exchange traders are net sellers (buyers) — opposite
- Locals' strategy is PROFITABLE; off-exchange traders make LOSING trades in first 20 seconds
- Large surge in trading volume immediately after announcement
- Speed of price reaction VARIES ACROSS announcement types
- 10 announcement types significantly affect S&P 500 futures prices

**What we take:**
- In the first seconds post-announcement: "smart money" (locals/HFT) already positioned correctly
- For manual ORB execution: DO NOT try to trade the immediate post-announcement reaction (too fast)
- Wait for initial price adjustment to complete (1-5 min) before acting on news signal
- Cross-ref AIM-12 (Costs): slippage elevated in first seconds post-announcement

---

## Paper 89 — Kurov, Olson & Wolfe (2024): Causal Effects Between Equities, Oil, and Monetary Policy

**What it proves:**
- Since 2008: stock returns CAUSE crude oil returns (not just the reverse — bidirectional)
- Structural change: associated with ZLB (zero lower bound) and increased oil-business cycle synchronisation
- FOMC announcements affect BOTH stocks and crude oil simultaneously
- Time-varying coefficients: the stock→oil causality was absent before 2008 but strong after
- Uses exogenous intraday volatility shifts for identification (stock market open, WPSR, FOMC)

**What we take:**
- Stock returns → oil returns causality: ES moves drive CL in the same direction (post-2008)
- On FOMC days: BOTH ES and CL react to the same announcement → cross-asset sizing consideration
- For Captain (Online): if holding both ES and CL positions on FOMC day, correlation is HIGH → reduce combined exposure
- Cross-ref AIM-08/09: stock-oil bidirectional causality confirms cross-asset signal relevance

---

### AIM-06 Design Conclusions

**1. Event Hierarchy by Impact:**
| Tier | Events | Typical Time | Asset Most Affected |
|------|--------|--------------|---------------------|
| Tier 1 (Highest) | NFP, FOMC | 8:30 ET / 2:00 PM ET | ES, NQ, CL |
| Tier 2 (High) | CPI, GDP, Consumer Confidence | 8:30 ET / 10:00 ET | ES, NQ |
| Tier 3 (Moderate) | EIA Petroleum, ISM, Retail Sales | 10:30 ET / 10:00 ET | CL (EIA), ES (ISM) |
| Tier 4 (Lower) | Housing, Durable Goods, PPI | Various | Moderate |

**2. Pre-Announcement Drift (30 min before):**
- 7/18 announcements show drift accounting for >50% of total price impact (Paper 90)
- ORB signal at open may already reflect upcoming 8:30 news (drift starts at ~8:00)
- Captain should flag if open is within 30 min of Tier 1/2 announcement

**3. Pre-FOMC Risk Premium:**
- 162 bps/year from 8 FOMC days — genuine risk premium (Paper 88)
- Morning session on FOMC day carries elevated expected return but also elevated risk
- Recent 5-day market return predicts FOMC interpretation type

**4. Post-Announcement Speed:**
- Most adjustment within 1-5 minutes; locals positioned in <20 seconds (Papers 82, 87)
- Manual trading: wait for initial adjustment to complete before acting on news
- Don't trade the immediate reaction — wait for settlement

**5. Cross-Asset on Event Days:**
- FOMC affects BOTH ES and CL simultaneously → high correlation → reduce combined exposure (Paper 89)
- Stock returns cause oil returns since 2008 (bidirectional) → cross-asset risk elevated on event days

**6. Energy-Specific:**
- Speculative activity dampens macro impact on CL → better execution in high-speculator periods (Paper 83)
- EIA Wednesday 10:30 shifts CL intraday dynamics (cross-ref AIM-04, Paper 62)

**7. Modifier Construction:**
```
events_today = check_economic_calendar()

if Tier_1_event within ±30min of ORB entry:
    modifier = 0.70  (high vol, rapid adjustment, potential jump)
elif Tier_1_event later in day (e.g., FOMC at 2PM):
    modifier = 1.05  (pre-announcement risk premium)
elif Tier_2_event within ±30min of ORB entry:
    modifier = 0.85
elif Tier_3_event (EIA for CL):
    modifier = 0.90 for CL, 1.0 for ES
elif event_free_day:
    modifier = 1.0

# FOMC day cross-asset: if holding both ES + CL, reduce combined exposure by 0.85
```

**8. Warm-up:** None required — calendar is deterministic. Load event schedule at system start.

**9. Data Sources:**
- Economic calendar: Bloomberg, Investing.com, or free API (e.g., FRED release calendar)
- VIX/VXV for IVTS context on event days (cross-ref AIM-04)
- Paper 36 (cross-filed from AIM-01): FOMC event risk from options — can enhance FOMC-day modifier

**10. Cross-references:**
- AIM-01 (VRP): FOMC events create VRP spikes (Paper 36)
- AIM-04 (Pre-Market): IVTS regime filter interacts with event days; EIA shifts CL dynamics
- AIM-07 (COT): speculative positioning level affects macro impact magnitude (Paper 83)
- AIM-08/09 (Cross-Asset): stock→oil causality elevated on macro event days (Paper 89)

---

# AIM-07: Commitments of Traders (COT) Positioning

## Paper 95 — Wang (2003): Investor Sentiment, Market Timing, and Futures Returns — SEMINAL

**What it proves:**
- Large SPECULATOR sentiment = PRICE CONTINUATION indicator (follow their positioning)
- Large HEDGER sentiment = CONTRARY indicator (fade their positioning)
- Small trader sentiment = NO predictive power (ignore completely)
- EXTREME sentiments provide MORE reliable forecasts than moderate levels
- COMBINATION of extreme large trader sentiments = best timing signal
- Findings suggest large speculators possess superior timing ability; hedgers act as portfolio insurers

**Methodology:** S&P 500 index futures, COT data, sentiment index based on net positions by trader type

**Quantitative results:**
- Buy-and-hold or past-return-based rules cannot match sentiment-conditional strategies
- Extreme speculator bullishness → future price continuation
- Extreme hedger bullishness → future price REVERSAL (contrarian)
- S&P 500 futures returns exhibit weak mean reversion → hedger contrarian signal works because portfolio insurance drives hedger positioning

**What we take:**
- PRIMARY rule: follow large speculator sentiment, fade large hedger sentiment, ignore small traders
- EXTREME positioning levels (historical top/bottom) are the most reliable signals
- For Captain (Online): compute COT sentiment index, flag extreme readings as alerts
- Weekly frequency → not for intraday timing, but for position sizing conditioning

---

## Paper 98 — Micaletti: Smart Money Indicator (SMI) from COT — STRONGEST IMPLEMENTATION

**What it proves:**
- Cross-asset, positions-based RELATIVE sentiment indicator (institutional vs. individual) is HIGHLY significant
- When SMI positive (institutions relatively bullish equities): annualized returns ~20pp HIGHER than when negative
- SMI renders time-series MOMENTUM UNINFORMATIVE — it dominates momentum as a predictor
- During NEGATIVE momentum + SMI positive: ~+30% annualized; negative momentum + SMI negative: ~-20% (50pp spread!)
- Also facilitates timing of smart beta equity factors
- Walk-forward TAA strategy outperforms value and momentum benchmarks
- Passes extremely stringent data snooping tests (Bonferroni, Romano-Wolf, Hansen's SPA)

**Methodology:**
- 25+ years of weekly COT data
- Cross-asset: not just equity futures but also positions in closely related non-equity assets
- Parametric, nonparametric, Bayesian, and classical statistical tests
- Walk-forward (not just in-sample) validation

**Quantitative results:**
- SMI positive: 20pp higher annualized returns WITH lower volatility
- During negative equity momentum: SMI positive → ~30%, SMI negative → ~-20%
- Timing significance increases when conditioned on factor momentum state
- Robust to different parameter combinations, data lags, and construction methods

**What we take:**
- THE most powerful COT-based signal: RELATIVE positioning (institutional vs. individual), computed CROSS-ASSET
- Dominates both value and momentum for tactical allocation
- For Captain (Online): compute SMI weekly, use polarity as primary COT conditioning signal
- Especially valuable during negative momentum periods → tells you when to stay in despite negative trend
- Cross-ref AIM-11 (Regime Warning): SMI polarity change could signal regime transition

---

## Paper 91 — Chen & Maher (2013): Predictive Role of Large Futures Trades for S&P500: COT Data — CRITICAL CAVEAT

**What it proves:**
- Hedge funds appear superior in information/trading ability BUT advantage preserved ONLY at HIGH FREQUENCY
- Weekly COT report (with 3-day delay) PREVENTS timely public access → signal unreliable at weekly level
- Commercial firms' net positioning positively correlated with returns but NOT STABLE across time
- STRUCTURAL BREAKS in predictive role: dotcom and subprime crises change relationships fundamentally
- Popular sentiment index (Wang 2003) does NOT produce significant average returns in backtesting
- As trader MIX within categories evolves (e.g., more hedge funds classified as commercial), information role SHIFTS

**Methodology:** S&P500 standard + E-mini futures, consolidated COT + disaggregated COT, structural break analysis

**What we take:**
- CRITICAL WARNING: COT-based signals have structural breaks → must monitor for regime changes in the signal itself
- Weekly frequency + 3-day delay = TOO SLOW for intraday timing → COT is a CONDITIONING variable, not a trigger
- Disaggregated COT (with hedge fund breakdown) is more informative than legacy commercial/noncommercial
- Captain (Offline) should periodically re-evaluate whether COT relationships still hold (decay detection applies to AIM signals too)

---

## Paper 93 — Sanders, Boris & Manfredo (2004): Hedgers, Funds, Small Speculators in Energy Futures

**What it proves:**
- CL, gasoline, heating oil, natural gas: positive correlation between returns and noncommercial (fund) positions; negative for commercial
- Market RETURNS LEAD trader positions (not the other way around) in most energy markets
- Traders' net positions do NOT lead market returns in general
- Extreme positioning provides SOME timing value (contrarian for funds at extremes)
- Detailed examination of COT data collection procedures reveals important classification limitations

**What we take:**
- For CL: returns drive COT positioning, not vice versa → COT is a LAGGING indicator for energy
- Extreme fund positioning in CL may signal reversal (contrarian at extremes) but NOT reliable for direction
- COT data limitations: reporting thresholds vary, classifications change, data is not real-time
- Cross-ref AIM-06 (Econ Calendar): speculator activity level around macro events affects impact

---

## Paper 94 — Smales (2015): Trading Behavior in S&P 500 Index Futures

**What it proves:**
- Speculators + small traders follow POSITIVE FEEDBACK strategies (momentum/trend-following)
- Hedgers DYNAMICALLY ADJUST in response to returns (contrarian/portfolio insurance)
- These strategies REVERSE during the 2008-09 financial crisis (regime-dependent)
- Investor sentiment and market volatility determine net trading position across all trader types
- All trader types are better at foreseeing market UPTURNS than downturns
- OOS: speculators and small traders have SOME predictive ability for short-term returns

**What we take:**
- COT positioning behaviour is REGIME-DEPENDENT — reverses during crises
- Captain (Offline) should detect when positioning-return relationship has shifted
- Sentiment and volatility drive positioning → positioning is partly a function of existing AIM signals (VRP, IVTS)
- Confirms Paper 95: speculators = continuation, hedgers = contrarian, but with crisis-period reversal caveat

---

## Paper 92 — Dreesmann, Herberger & Charifzadeh (2023): COT Report as Trading Signal?

**What it proves:**
- Short-term reversal strategy from COT: long-only significant in 6 individual markets; long-short in only 2
- PORTFOLIO level: CoT strategy UNDERPERFORMS the benchmark (S&P 500 buy-and-hold Sharpe 1.07)
- COT report contributes to efficient derivatives market (information is priced in)
- Monte Carlo simulation confirms: chosen parameters cannot generate excess Sharpe ratios in portfolio

**What we take:**
- COT as a STANDALONE trading strategy does not work in portfolio context
- Confirms it should be used as a CONDITIONING/MODIFIER, not a primary signal
- Individual market-level effects exist but don't aggregate → asset-specific application needed

---

## Paper 99 — Hamilton & Wu (2015): Effects of Index-Fund Investing on Commodity Futures Prices

**What it proves:**
- NO evidence that index trader positions in agricultural contracts predict near futures returns
- Some support for oil futures 2006-2009 but BREAKS DOWN out of sample
- Index-fund investing has little systematic impact on commodity futures prices overall
- Notional positions (not contract counts) should be used if testing for effect

**What we take:**
- Index trader (passive) positioning is NOT informative for price prediction
- Only ACTIVE trader positioning (hedge funds, managed money) carries potential signal
- For CL: use disaggregated COT (managed money category), not legacy commercial/noncommercial

---

## Paper 96 — Keenan (2020): Advanced Positioning, Flow, and Sentiment Analysis (Wiley, 281pp)

**What it proves:** Comprehensive practitioner reference book bridging fundamental and technical analysis via positioning data.

**What we take:** Reference resource for implementation details. Too large for extraction but available as implementation guide when building AIM-07.

---

### AIM-07 Design Conclusions

**1. The COT Signal Hierarchy:**
| Signal | Direction | Reliability | Use |
|--------|-----------|-------------|-----|
| Large speculator sentiment (extreme) | Continuation | Moderate (breaks during crises) | Conditioning |
| Large hedger sentiment (extreme) | Contrarian | Moderate (breaks during crises) | Conditioning |
| Small trader sentiment | None | Unreliable | Ignore |
| Cross-asset SMI (institutional vs. individual) | Follow institutions | HIGH (robust to data snooping) | PRIMARY |
| Index trader positions | None | None | Ignore |

**2. COT is a CONDITIONING Variable, NOT a Trigger:**
- Weekly frequency + 3-day delay = too slow for intraday timing
- Use to condition SIZING, not direction
- Best at EXTREME readings (90th/10th percentile of historical distribution)
- Structural breaks occur → must monitor for regime changes in the signal itself

**3. Best Implementation: Cross-Asset SMI (Paper 98):**
- Compute relative institutional vs. individual positioning across equity and related assets
- SMI positive → 20pp higher annualized returns → increase sizing confidence
- SMI negative → reduce exposure, especially during negative momentum
- Dominates both value and momentum signals

**4. CL-Specific Limitations:**
- In energy futures, returns LEAD positions, not vice versa → COT is lagging for CL (Paper 93)
- Use disaggregated COT (managed money) not legacy categories (Paper 99)
- Extreme managed-money positioning in CL may have contrarian value at extremes only

**5. Modifier Construction:**
```
# Weekly update (Friday COT release, Tuesday data)
COT_speculator_z = z_score(speculator_net_long, trailing_52w)
SMI_polarity = compute_SMI_cross_asset()  # Paper 98 methodology

if SMI_polarity == POSITIVE:
    smi_mod = 1.05  (institutions bullish)
elif SMI_polarity == NEGATIVE:
    smi_mod = 0.90  (institutions bearish)

# Extreme positioning overlay
if |COT_speculator_z| > 1.5:
    if COT_speculator_z > 1.5:   extreme_mod = 0.95  (crowded long, continuation but elevated risk)
    elif COT_speculator_z < -1.5: extreme_mod = 1.10  (extreme bearishness, contrarian opportunity)
else:
    extreme_mod = 1.0

modifier = smi_mod × extreme_mod
```

**6. Update Frequency:** Weekly (COT released Friday, data as of Tuesday)

**7. Warm-up:** 52 weeks (1 year of COT history for z-score and SMI baseline)

**8. Data Sources:**
- CFTC Commitments of Traders reports: free, public, weekly (legacy + disaggregated)
- CFTC Traders in Financial Futures (TFF): for ES/NQ
- CFTC Disaggregated COT: for CL (managed money category)

**9. Cross-references:**
- AIM-04 (Pre-Market/IVTS): IVTS and COT together provide regime + positioning context
- AIM-06 (Economic Calendar): speculator activity level affects macro event impact (Paper 83)
- AIM-11 (Regime Warning): SMI polarity change could signal regime transition
- Captain (Offline): must periodically re-evaluate COT relationship stability (structural break detection)

---

# AIM-08: Dynamic Cross-Asset Correlation Monitor

## Paper 102 — Ang & Bekaert (2004): How Regimes Affect Asset Allocation — SEMINAL

**What it proves:**
- International equity returns are MORE highly correlated in BEAR markets than normal times (asymmetric correlation)
- Two regimes: NORMAL (moderate vol, moderate correlation) + BEAR MARKET (lower returns, much higher vol, higher correlations)
- Regime-switching allocation DOMINATED static strategies in OOS test
- In high-vol regime: optimal to switch primarily to CASH (not just rebalance equities)
- Large market-timing benefits because high-vol regimes coincide with relatively high interest rates
- RS strategy most valuable for CASH/BONDS/EQUITY switching, not just global equity rebalancing

**Methodology:** RS model (Hamilton 1989), 6 international equity markets + cash, in-sample + OOS evaluation

**What we take:**
- Two-regime model (normal + stress) is sufficient and validated for asset allocation
- When bear/stress regime detected: shift toward CASH → Captain should REDUCE sizing, not just rebalance
- Asymmetric correlations: diversification benefits disappear exactly when needed most → must condition on regime
- For Captain (Online): regime probability feeds directly into sizing multiplier

---

## Paper 103 — Bucci & Ciciretti (2022): Market Regime Detection via Realized Covariances

**What it proves:**
- Market regimes can be identified from REALIZED COVARIANCE matrices (not just returns)
- Hierarchical clustering = BEST performing model for regime labeling (beats TVAR, MSVAR, LSTVAR)
- Both abrupt AND smooth regime changes captured
- Covariances embed regime information → regime detection from co-movement structure
- Investment strategy evaluation: regime-switching strategy using detected labels outperforms

**Methodology:** Monthly realized covariances, factor extraction, 4 detection models + unsupervised learning, simulation + empirical

**What we take:**
- REALIZED COVARIANCE (not just correlation) is the right input for regime detection
- Hierarchical clustering is a computationally simple, high-performing approach
- For Captain (Offline): compute realized covariance matrix of ES/NQ/CL, feed factors to clustering algorithm
- Smooth transition detection (LSTVAR) captures gradual regime shifts that abrupt models miss
- Cross-ref Program 2: this provides an alternative/complementary regime classification to Pettersson/MS-HAR

---

## Paper 108 — Bouzguenda & Jarboui (2026): Managing Systemic Risk in Energy and Financial Markets

**What it proves:**
- WTI crude oil = PRINCIPAL CONDUIT of volatility spillovers between energy and equity markets
- DCC-GARCH + Diebold-Yilmaz connectedness: time-varying, intensifies during crises (COVID, Russia-Ukraine)
- Heightened systemic risk during major disruptions → correlations spike
- Five portfolio strategies tested: Min Variance, Min Correlation, Min Connectedness, Min R², Min Decomposed R²
- CONNECTEDNESS-based strategies show SUPERIOR RESILIENCE during crises
- Min Variance delivers robust risk-adjusted returns overall but less adaptive

**Methodology:** Gold, WTI, S&P 500, SSE, daily returns, Jan 2019 – Aug 2025

**What we take:**
- CL is THE key transmitter → when CL volatility spikes, expect ES contagion
- Connectedness metrics (Diebold-Yilmaz) provide dynamic systemic risk measure
- For Captain (Online): monitor ES-CL connectedness; when elevated → reduce combined exposure
- During crises: connectedness-based sizing outperforms variance-based → use correlation regime, not just vol

---

## Paper 105 — Delatte & Lopez (2013): Commodity and Equity Markets — Copula Stylized Facts

**What it proves:**
- Dependence between commodity and stock markets is TIME-VARYING, SYMMETRICAL, and occurs MOST of the time
- NOT just during extreme events (contradicts tail-dependence-only assumptions)
- Not allowing time-varying parameters → BIAS toward false tail dependence evidence
- Growing co-movement since 2003: industrial metals first, then ALL commodity classes post-2008
- Copula approach separates marginals from dependence → more accurate than raw correlations

**Methodology:** Copula analysis (6 dependence structures tested), Jan 1990 – Feb 2012, GSCI + DJ-UBSCI + sub-indices

**What we take:**
- Commodity-equity correlation is PERSISTENT and growing, not just a crisis phenomenon
- Must use TIME-VARYING dependence measures → rolling or DCC, not static
- The correlation between CL and ES has been structurally higher since 2008 → permanent regime shift
- For AIM-08: use DCC-GARCH or rolling window, never assume static correlation

---

## Paper 107 — Bratis, Laopodis & Kouretas (2020): Dynamics Among Global Asset Portfolios

**What it proves:**
- DCC-GARCH: cross-correlations among global equities STRENGTHENED during 2008 crisis → weak diversification
- Financial spillovers strengthened POST-crisis → persistent, not temporary
- Heterogeneous portfolios (multi-asset class) > homogeneous (single class) in ALL periods
- US and EMU crises affected assets DIFFERENTLY → contagion is not uniform
- Risk-offsetting assets (commodities) needed for cyclical/countercyclical portfolio balance

**What we take:**
- Multi-asset approach (ES + CL + potentially bonds/gold) IS the right framework for Captain
- Correlation regime shift post-2008 is PERSISTENT → calibrate baseline to post-2008 data
- Need to include countercyclical assets for crisis resilience → gold/bonds as hedge when both ES and CL are correlated
- Heterogeneous portfolio outperformance confirms value of cross-asset diversification when correlation is managed

---

## Prior Extractions: Papers 14 + 18 (from earlier sessions)

**Paper 14 — Amado & Teräsvirta (2014): TV-GARCH variance decomposition**
- Separate LONG-RUN baseline volatility from SHORT-RUN GARCH component
- Use regime-conditional CONSTANT correlation (within regime, correlation is stable)
- Improves OOS covariance forecasting

**Paper 18 — Soury (2024): RS Copulas for ES/NQ and CL**
- Two persistent regimes: CALM and TURBULENT
- ASYMMETRIC tail dependence: stronger co-movement in down-moves than up-moves
- Regime-conditional correlations differ significantly between calm and turbulent states

---

### AIM-08 Design Conclusions

**1. Core Signal: Dynamic Cross-Asset Correlation**
- Compute 20-day rolling correlation between ES and CL daily returns (or DCC-GARCH for better estimates)
- Z-score against trailing 252-day (1-year) baseline
- Correlation is STRUCTURALLY higher post-2008 → use post-2008 calibration window

**2. Two-Regime Correlation Framework:**
| State | ES-CL Correlation | Implication | Action |
|-------|-------------------|-------------|--------|
| Normal | ~0.3-0.5 | Diversification benefit exists | Hold both, normal sizing |
| Stress | ~0.7-0.9 | Diversification collapses | REDUCE combined exposure |

- Bear markets → higher correlations → diversification fails when most needed (Paper 102)
- CL is the principal volatility transmitter (Paper 108) → CL vol spike = ES contagion warning

**3. Detection Method:**
- Hierarchical clustering on realized covariance factors is the best regime detector (Paper 103)
- Simpler alternative: rolling correlation z-score threshold
- TV-GARCH separates long-run from short-run for better baseline (Paper 14)
- RS copulas capture asymmetric tail dependence (Paper 18)

**4. Modifier Construction:**
```
corr_ES_CL = rolling_20d_correlation(ES_returns, CL_returns)
corr_z = z_score(corr_ES_CL, trailing_252d)

if corr_z > 1.5:     modifier = 0.80  (stress: correlation spike, diversification collapsed)
elif corr_z > 0.5:   modifier = 0.90  (elevated, caution)
elif corr_z < -0.5:  modifier = 1.05  (below average, diversification benefit strong)
else:                 modifier = 1.0

# If holding BOTH ES + CL positions simultaneously:
combined_modifier *= 0.85 when corr_z > 1.0  (reduce combined exposure)
```

**5. Warm-up:** 252 trading days (1 year for correlation baseline and z-score)

**6. Data Sources:**
- ES and CL daily returns: futures data feed (free)
- DCC-GARCH: compute from daily returns (offline estimation, daily update)
- VIX + OVX: supplementary stress indicators

**7. Cross-references:**
- AIM-04 (Pre-Market): overnight CL RV → next-day ES vol (Paper 68 cross-market channel)
- AIM-06 (Economic Calendar): FOMC affects both ES and CL simultaneously (Paper 89)
- AIM-09 (Spatio-Temporal): uses cross-asset correlations as input for signal generation
- AIM-11 (Regime Warning): correlation regime change = leading indicator of broader regime shift
- Program 2: realized covariance regime detection is complementary to Pettersson/MS-HAR methods

---

# AIM-09: Spatio-Temporal Cross-Asset Signal

## Paper 116 — Pu, Roberts, Dong & Zohren (2023): Network Momentum across Asset Classes

**What it proves:**
- Momentum SPILLOVER exists across asset classes — one asset's momentum predicts another's returns
- Graph learning (linear, interpretable, minimal assumptions) reveals the spillover network from PRICING DATA ONLY
- Network momentum strategy: Sharpe 1.5, annual return 22% (vol-scaled), 2000-2022 on 64 continuous futures
- Pioneering: first examination of momentum spillover across multiple asset classes using only pricing data
- Network momentum provides DIVERSIFICATION beyond individual momentum

**Methodology:** 64 futures (commodities, equities, bonds, currencies), graph learning for adjacency matrix, MACD-like momentum features as node signals, 2000-2022

**What we take:**
- Cross-asset momentum spillover IS a real, exploitable phenomenon
- Graph structure (which assets lead which) can be learned from returns alone — no need for fundamental data
- For Captain: CL momentum may predict ES returns (commodity→equity spillover channel)
- Network momentum diversifies individual momentum risk → combine both signals

---

## Paper 111 — Li & Ferreira (2025): Follow the Leader — Network Momentum for Commodity Futures

**What it proves:**
- Combining univariate trend indicators WITH cross-sectional (network) momentum SIGNIFICANTLY improves Sharpe ratio, return skewness, and downside performance
- Two lead-lag detection methods as ENSEMBLE: Lévy area signatures + Dynamic Time Warping (DTW)
- Network momentum indicator from learned lead-lag → novel trend-following signal
- Statistical significance validated on BOOTSTRAPPED price trajectories from real data (not just in-sample)
- Commodity futures focus — directly applicable to CL

**What we take:**
- ENSEMBLE of lead-lag methods outperforms any single method → use multiple detection approaches
- Bootstrapped validation = highest standard of evidence → result is not data mining
- Combining network signal with univariate trend is the right architecture (not replacing, augmenting)
- For ORB: univariate ORB signal + network momentum modifier = enhanced strategy

---

## Paper 115 — Zhang, Cucuringu, Shestopaloff & Zohren (2023): DTW for Lead-Lag Detection

**What it proves:**
- Dynamic Time Warping detects lead-lag relationships in lagged multi-factor models robustly
- Cluster-driven methodology handles non-synchronized time series of varying lengths
- Significant economic benefits when lead-lag signals leveraged in trading strategies
- From Oxford-Man Institute (same group as Paper 19 — validated methodology)

**What we take:**
- DTW is a validated computational method for detecting which assets lead which
- For implementation: compute DTW-based lead-lag scores between ES, NQ, CL daily
- Cluster markets into leaders and followers → followers' positions follow leaders' momentum
- Lead-lag is time-varying → re-estimate periodically (weekly or monthly)

---

## Paper 112 — Wood, Kessler, Roberts & Zohren (2024): X-Trend — Few-Shot Learning for Trend-Following

**What it proves:**
- Few-shot learning enables rapid adaptation to new financial regimes (COVID-19 as case study)
- X-Trend (Cross Attentive Time-Series Trend Network): Sharpe +18.9% over neural forecaster, 10x over TSMOM (2018-2023)
- Recovers 2x faster from COVID drawdown than neural forecaster
- Zero-shot on NOVEL UNSEEN assets: 5x Sharpe improvement — transfers patterns across assets
- Cross-attention mechanism provides INTERPRETABLE explanations of which historical patterns drive forecasts
- Segments regimes using change-point detection → context set per regime

**What we take:**
- REGIME-ADAPTIVE: model selects relevant historical patterns for current regime automatically
- For Captain (Offline): train X-Trend-like architecture on multi-asset futures as a regime-adaptive signal generator
- Cross-attention interpretability → human-readable explanation of WHY a signal was generated (useful for discretionary reports)
- Zero-shot transfer → when adding new assets, model generalises without full retraining

---

## Paper 117 — Pu, Zohren, Roberts & Dong (2023): L2GMOM — Learning to Learn Financial Networks

**What it proves:**
- End-to-end ML: simultaneously LEARNS financial networks AND OPTIMISES trading signals
- Algorithm unrolling → interpretable neural network with forward propagation derived from optimization
- Sharpe ratio 1.74 across 20-year period on 64 futures contracts (HIGHEST of all papers)
- No need for expensive databases or financial expertise — learns from pricing data
- Task-specific graph construction OUTPERFORMS economically-motivated graphs

**What we take:**
- THE advanced implementation path: joint network learning + portfolio optimisation
- 1.74 Sharpe = exceptional performance → this is the ceiling for what AIM-09 could achieve
- Interpretable architecture (unrolled optimisation) = suitable for regulatory/compliance scrutiny
- For Captain (Offline): implement L2GMOM as the AIM-09 model, retrain monthly

---

## Paper 118 — Xu, Li, Singh & Park (2025): Cross-Asset TSM — Industrial Metals Lead Equities

**What it proves:**
- Industrial metals' past returns PREDICT stock market returns (1-month lookback)
- I-XTSM strategy avoids MOMENTUM COLLAPSE during turbulent markets
- Outperforms single-asset TSM and bond-based XTSM
- >50% of industrial metals information reflected in stock prices within 1 month
- GSCI Industrial Metals Index as cross-asset signal: copper, aluminium, zinc, lead
- Jan 1990 – Dec 2023

**What we take:**
- VALIDATED: commodity → equity momentum transmission channel exists
- CL and industrial metals as LEADING indicators for ES/NQ → directly applicable
- 1-month lookback for cross-asset signal is optimal (not 12-month)
- For Captain (Online): compute 1-month industrial metals/CL momentum, use as ES sizing modifier
- Avoids momentum collapse = protective during exactly the periods ORB strategies are vulnerable

---

## Paper 119 — Declerck (2019): Trend-Following and Spillover Effects

**What it proves:**
- Trends SPILL OVER across asset classes: bonds, currencies, equities (29 instruments, developed markets)
- Past trends of one asset help build strategies for OTHER related assets
- Spillover works BETTER with LONGER lookback periods than standard trend-following sweet spot
- Multi-asset trend-following delivers strong returns for short-to-medium lookbacks

**What we take:**
- Cross-asset spillover is a robust, well-documented phenomenon across all major asset classes
- Longer lookback (3-12 months) for spillover signal vs. shorter (1-3 months) for individual momentum
- For Captain: dual-horizon system — short lookback for individual asset, long lookback for cross-asset spillover
- Confirms that CL/bonds can inform ES positioning through trend spillover channel

---

## Prior Extraction: Paper 19 — Tan, Roberts & Zohren (2023): Spatio-Temporal Momentum — ALREADY HELD

**Key finding:** Simple Single-Layer Perceptron (SLP) using cross-asset MACD features OUTPERFORMS complex deep learning for multi-asset signal generation on equity index futures. Provides the architectural framework for AIM-09's cross-asset signal as a sizing modifier.

---

### AIM-09 Design Conclusions

**1. Network/Spatio-Temporal Momentum is Validated and Powerful:**
- Sharpe 1.5-1.74 on multi-asset portfolios over 20+ years (Papers 116, 117)
- Statistically significant improvement over univariate trend-following, validated on bootstrap (Paper 111)
- Works from PRICING DATA ONLY — no fundamental databases needed
- Simple SLP is sufficient; complex DL does not outperform (Paper 19)

**2. Lead-Lag Relationships are the Core Mechanism:**
- CL and industrial metals LEAD equity markets with 1-month lag (Papers 118, 119)
- DTW (Paper 115), Lévy area (Paper 111), graph learning (Papers 116, 117) detect connections
- Relationships are TIME-VARYING → re-estimate monthly
- ENSEMBLE of detection methods outperforms any single method (Paper 111)

**3. Regime-Adaptive:**
- Few-shot learning (X-Trend) adapts to new regimes rapidly (Paper 112)
- Cross-attention provides interpretability
- Network topology shifts when regimes change → re-learn connections

**4. For MOST/Captain Implementation:**
- **Simple path:** Compute 1-month CL/industrial metals momentum → use as ES/NQ conditioning modifier (Paper 118)
- **Intermediate:** SLP on cross-asset MACD features (Paper 19)
- **Advanced:** L2GMOM end-to-end graph learning + portfolio optimisation (Paper 117, Sharpe 1.74)

**5. Modifier Construction:**
```
# Simple implementation (start here):
CL_momentum_1m = (CL_close_today / CL_close_21d_ago) - 1
industrial_metals_mom = GSCI_IND_1m_return

cross_signal = 0.5 * sign(CL_momentum_1m) + 0.5 * sign(industrial_metals_mom)

if cross_signal aligns with ORB direction:   modifier = 1.10  (cross-asset confirmation)
elif cross_signal opposes ORB direction:     modifier = 0.85  (cross-asset contradiction)
else:                                        modifier = 1.0

# Advanced: replace with SLP/L2GMOM continuous signal
```

**6. Warm-up:** 63 trading days (3 months for momentum features + 1 month for lead-lag estimation)

**7. Data Sources:**
- Futures prices: ES, NQ, CL, industrial metals (copper, aluminium via LME or GSCI-IND)
- All freely available from data feeds
- No proprietary data or expensive databases required

**8. Cross-references:**
- AIM-08 (Correlation): correlation regime provides context for cross-asset signal strength
- AIM-04 (IVTS/Pre-Market): overnight CL → ES transmission is the intraday version of this spillover
- AIM-11 (Regime Warning): network topology change = regime transition early warning
- Program 2: cross-asset spillover could enhance regime-conditioned strategy selection

---

# AIM-10: Calendar Effect Model

## Paper 121 — Floros & Salvador (2014): Calendar Anomalies in Cash and Stock Index Futures — Regime-Conditioned

**What it proves:**
- Calendar anomalies (DOW, monthly effects) DIFFER between cash and futures markets (basis risk)
- REGIME-CONDITIONED: low-vol regime → calendar effects tend to be POSITIVE; high-vol regime → effects turn NEGATIVE
- Markov Regime-Switching model (Hamilton 1989) distinguishes high/low volatile periods
- Calendar effects are NOT constant — they REVERSE SIGN depending on market regime

**Methodology:** FTSE100, FTSE/ASE-20, S&P500, Nasdaq100 spot + futures, daily, 2004-2011

**What we take:**
- Calendar effects MUST be conditioned on regime — applying them uniformly will produce wrong signals in high-vol
- For Captain (Online): any calendar-based modifier must be MULTIPLIED by regime state (not added)
- Low-vol + Monday → may be slightly negative (traditional DOW); high-vol + Monday → may reverse
- Validates the regime-first architecture: regime classification (Program 2) must feed into AIM-10

---

## Paper 125 — Holmberg, Lönnbark & Lundström (2013): ORB Strategy Profitability on CL Futures — DIRECTLY RELEVANT

**What it proves:**
- Opening Range Breakout (ORB) on CRUDE OIL futures results in significantly higher returns than zero
- Increased success rate vs. fair game (martingale baseline)
- Contraction-Expansion (C-E) principle: markets alternate between quiet and expansion periods; ORB identifies expansion days
- If price exceeds ORB threshold during the day → long/short position is established → positive expected return
- Uses daily OHLC to infer intraday execution (bootstrap for significance)

**Methodology:** CL futures, daily OHLC, bootstrap test of profitability, ORB threshold = predetermined % from open

**What we take:**
- ORB IS a validated strategy for CL futures — statistical evidence of positive expected returns
- C-E principle = the theoretical basis: non-normal expansion days drive profitability (momentum breakdown of martingale)
- For MOST: this is the FOUNDATIONAL validation paper for our core strategy on CL
- ORB threshold selection matters → too wide misses trades, too narrow gets noise
- Cross-ref AIM-04 Paper 67: ORB on ES requires IVTS regime filter; Paper 125 validates ORB on CL directly

---

## Paper 128 — Ewald et al. (2025): Intraday Seasonality and Abnormal Returns in Brent Crude Oil Futures

**What it proves:**
- Statistically significant INTRADAY seasonal patterns in Brent crude oil futures (ICE London)
- Peaks and bottoms at PARTICULAR times of day, depend on contract maturity
- U-shaped pattern: higher activity/vol at open and close, dip midday
- Long-short strategies based on intraday patterns yield consistent positive CAPM alphas EVEN AFTER realistic transaction costs and margin
- Patterns follow major global markets' office hours (not 24h uniform)

**Methodology:** Tick data, ICE London, Jan 2010 – Oct 2021 (130 GB), 1-minute conversion, CAPM alpha evaluation

**What we take:**
- CL (and Brent) has EXPLOITABLE intraday time-of-day seasonality → specific entry/exit windows are better than others
- For ORB on CL: the OPEN is already a high-activity period (U-shape confirms); the MIDDLE of the session is calmer
- Can potentially time ORB entry to coincide with high-activity windows for better breakout probability
- After-costs profitability confirmed → this is implementable, not just theoretical
- Maturity-dependent: front-month may behave differently than back months

---

## Paper 124 — van Heusden (2020): On the Persistence of Calendar Anomalies (Thesis)

**What it proves:**
- Calendar anomalies (DOW, Turn-of-Month, January effect) have largely DISAPPEARED post-academic-publication
- AEX, S&P500, Nikkei 225, ASX 300, 2000-2019
- No clear re-emergence found (except negative TOM in Australia post-2016)
- "Golden age" of calendar anomalies was mid-1900s
- Markets are increasingly efficient → traditional calendar effects mostly arbitraged away

**What we take:**
- DO NOT rely on traditional DOW or January effects for systematic sizing — they are no longer reliably present
- Any calendar effect used in AIM-10 must be validated on RECENT data (post-2015) and SPECIFICALLY for futures
- The remaining effects are likely those that are regime-conditioned (Paper 121) or asset-specific (Papers 125, 128)
- General equity calendar anomalies are NOT applicable to our futures-based strategy

---

## Paper 127 — Meek & Hoelscher (2023): Day-of-the-Week Effect in Petroleum Products

**What it proves:**
- DOW effect VARIES across energy commodities — not uniform across WTI, Brent, RBOB, Heating Oil, Natural Gas
- For CL specifically: some days show significant return patterns but no universal "worst day" or "best day"
- Multiple GARCH variants (EGARCH, PGARCH, QGARCH, TGARCH) used to control for volatility clustering
- Results may help TIME trade decisions within the week

**What we take:**
- For CL: DOW effects exist but are commodity-specific and model-dependent → use as a WEAK conditioning signal only
- Must be validated with our own CL sample data before incorporating (not strong enough to use off-the-shelf)
- Cross-ref AIM-01 (VRP): Monday VRP effect + DOW return effect compound for Monday-specific adjustment

---

## Paper 129 — Gao, He & Hu (2025): The Monthly Cycle of Option Prices

**What it proves:**
- ~2% monthly IV cycle around the 3rd Friday of each month (standard equity option expiration)
- IV rises BEFORE expiration, falls AFTER → driven by investors' collective rollover demand
- Supply-side frictions (market maker capacity) amplify the cycle
- More pronounced during: high market risk, increased risk aversion, tighter intermediary constraints
- Weekly options WEAKEN the cycle (disperse the concentrated rollover demand)
- Delta-neutral straddle strategy: up to 11.5% return per month

**What we take:**
- MONTHLY OPEX creates a predictable ~2% IV cycle → affects VRP computation (AIM-01) and GEX dynamics (AIM-03)
- Before OPEX: IV elevated → VRP may appear more negative (AIM-01 signal distorted by structural effect)
- After OPEX: IV drops → VRP normalises
- For Captain (Online): flag 3rd Friday ± 2 days as "OPEX window" with adjusted AIM-01/AIM-03 baselines
- Weekly options attenuate this effect → less relevant for assets with active weekly options (SPX)
- Cross-ref AIM-03: option expiration pinning (Paper 60) + this IV cycle = compound OPEX effect

---

### AIM-10 Design Conclusions

**1. Calendar Effects are REGIME-CONDITIONED:**
- Low-vol regime → calendar anomalies tend positive; high-vol → effects REVERSE to negative (Paper 121)
- ANY calendar modifier must be MULTIPLIED by regime state — regime classification from Program 2 feeds in
- Traditional DOW/January/TOM effects have largely disappeared (Paper 124) — do NOT use as standalone signals

**2. ORB is Validated on CL Futures:**
- Significantly positive expected returns from ORB on crude oil (Paper 125) — foundational validation for MOST strategy
- C-E principle provides theoretical basis: non-normal expansion days drive profitability
- Cross-validated with AIM-04 Paper 67 (ORB on ES with IVTS filter)

**3. Intraday Time-of-Day Seasonality in CL is Exploitable:**
- U-shaped activity/vol pattern; specific entry windows better than others (Paper 128)
- After-costs CAPM alpha confirmed → implementable
- Front-month behaviour may differ from back months

**4. Monthly OPEX Cycle:**
- ~2% IV cycle around 3rd Friday → distorts VRP and GEX baselines (Paper 129)
- Flag OPEX window (3rd Friday ± 2 days) for adjusted signal interpretation
- Pinning (AIM-03 Paper 60) + IV cycle compound the effect

**5. DOW in Petroleum:**
- Commodity-specific and model-dependent → weak conditioning signal only for CL (Paper 127)
- Monday caution compound effect: VRP (AIM-01) + DOW (AIM-10) + gap (AIM-04)

**6. Modifier Construction:**
```
# Monthly OPEX window
if trading_day within [3rd_Friday - 2, 3rd_Friday + 1]:
    opex_mod = 0.95  (structural IV distortion, pinning risk)
else:
    opex_mod = 1.0

# Regime-conditioned DOW (weak signal)
regime = current_regime_state  # from Program 2
if regime == LOW_VOL:
    dow_mod = 1.0  # no strong DOW effect; slight positive bias acceptable
elif regime == HIGH_VOL:
    dow_mod = 0.97  # calendar effects reverse; extra caution
else:
    dow_mod = 1.0

# Intraday timing for CL (informational, not modifier)
# Open = high-activity window → good for ORB breakout
# Midday = calmer → potential false breakout risk

modifier = opex_mod × dow_mod
```

**7. Warm-up:** None for calendar (deterministic). OPEX dates known in advance.

**8. Data Sources:** Exchange option expiration calendar (CBOE, CME); OHLC for C-E principle detection

**9. Cross-references:**
- AIM-01 (VRP): Monday VRP + OPEX IV cycle → compound adjustment
- AIM-03 (GEX): pinning + OPEX IV cycle = compound expiration effect
- AIM-04 (IVTS): regime filter determines which calendar effects apply
- Program 2: regime state feeds directly into calendar effect sign

---

# AIM-11: Regime Transition Early Warning

## Paper 139 — Fong & See (2002): Markov Switching of Conditional Volatility of CL Futures — CL-SPECIFIC

**What it proves:**
- CL regime switching: regime shifts DOMINATE GARCH effects → transitions between calm/turbulent matter more than within-state persistence
- Basis-driven TIME-VARYING transition probabilities: negative basis (backwardation) increases high-vol regime PERSISTENCE
- When oil in backwardation with low stocks → high-vol regime more persistent (theory of storage)
- OOS: regime switching model outperforms constant variance AND GARCH(1,1) regardless of evaluation criteria
- Two states with abrupt changes in mean AND variance; all GARCH parameters can switch between regimes
- Volatility regimes correlate well with major supply/demand events (1996-97 backwardation, 1994 shortage)

**Methodology:** WTI crude oil futures, daily, generalised RS model with GARCH + basis-driven TVTP + conditional leptokurtosis

**Quantitative results:**
- Monthly standard deviation 63% above baseline during 1996-97 high-vol regime
- Oil futures exhibit backwardation 71% of the time
- Negative basis → higher probability of staying in high-vol state; positive basis → more likely to transition to low-vol
- High GARCH persistence (α+β ≈ 0.9+) is spurious — driven by structural breaks between regimes (Lamoureux & Lastrapes 1990)

**What we take:**
- For CL: REGIME TRANSITIONS are the primary volatility driver, not GARCH persistence
- Monitor CL futures basis (spot - futures): negative basis in high-vol = regime will PERSIST → stay cautious longer
- Positive basis (contango) = lower regime persistence → earlier recovery possible
- Captain (Offline) regime model for CL should include basis as transition variable
- Cross-ref Program 2: basis-driven TVTP is a validated approach for CL regime classification

---

## Paper 136 — Bansal, Connolly & Stivers (2010): Regime-Switching in Stock Index and Treasury Futures Returns

**What it proves:**
- Bivariate RS model: HIGH-STRESS regime has much higher stock vol, MUCH LOWER stock-bond correlation, higher mean bond return
- Stock variance is 3x+ higher in high-stress vs. low-stress regime (consistent across subperiods)
- Stock-bond correlation 0.5+ LOWER in high-stress → diversification benefit from bonds INCREASES during stress
- Lagged VIX is USEFUL for modeling time-varying transition probabilities:
  - Higher lagged VIX → higher probability of transitioning FROM low-stress TO high-stress
  - Higher lagged VIX → higher probability of STAYING IN high-stress
- Lagged daily VIX variability and price-impact illiquidity also informative about transitions
- VIX averaged 30.5% on high-stress days vs. 19.8% on low-stress days
- Daily absolute VIX change 2x+ higher on high-stress days

**Methodology:** S&P 500 + 10-year T-note daily futures returns, 1997-2005, bivariate RS with means, vols, correlation all regime-dependent

**What we take:**
- VIX is THE primary LEADING INDICATOR for regime transitions → Captain should monitor VIX level and VIX changes
- VIX level trending up → probability of transitioning to high-stress regime increases → reduce sizing PREEMPTIVELY
- VIX daily variability (large absolute daily changes) = transition in progress → immediate caution
- During high-stress: bond diversification benefit INCREASES → if expanding to multi-asset, bonds become more valuable exactly when equities are stressed
- 3x variance ratio between regimes = dramatic sizing adjustment needed when regime shifts

---

## Paper 131 — Wang et al. (2025): Early Warning of Regime Switching via Heteroskedastic Network Model

**What it proves:**
- Heteroskedastic network + HMM + ARMA-GARCH + ML algorithm provides early warning of regime switching
- Maps financial time series into complex network → community structure detects BOTH regime switching AND early warning signals
- Dynamic process perspective captures nonlinearity and uncertainty that single-point features MISS
- Can detect critical switches across various periods: COVID-19, Russia-Ukraine, etc.
- Typical features of early warning signals can be EXTRACTED and characterised
- S&P 500 time series validation

**What we take:**
- Early warning IS feasible — the concept of extracting warning signals BEFORE the actual transition is validated
- Network/community structure approach adds value beyond simple threshold-based detection
- For Captain (Offline): consider implementing network-based early warning as a complement to VIX-based detection
- Dynamic process (sliding window ARMA-GARCH features → network → community detection) provides richer signal than point-in-time indicators
- Cross-ref AIM-08 (Correlation): network topology change from realized covariance (Paper 103) is a related detection mechanism

---

## Paper 134 — Leiss & Nax (2018): Option-Implied Objective Measures of Market Risk

**What it proves:**
- Foster-Hart (FH) bound: option-implied, forward-looking risk measure from S&P 500 RNDs
- SIGNIFICANT predictor of LARGE ahead-return DOWNTURNS
- Captures MORE characteristics of risk-neutral distributions (higher moments, tails) than VaR, ES, or VIX alone
- Predictive consistency across evaluation horizons
- Rigorous variable selection reveals FH as a significant predictor even after controlling for other measures
- Nonparametric RND estimation, 2003-2013

**What we take:**
- Option-implied risk measures predict LARGE downturns — useful as early warning supplement
- FH bound captures tail characteristics that VIX misses → complements AIM-01 VRP and AIM-04 IVTS
- For Captain (Online): if RND estimation is feasible, compute FH-type bound as supplementary risk indicator
- Practical: the full nonparametric RND is complex, but the CONCEPT (option-implied forward-looking risk that captures tails) validates using options-based signals for regime warning
- Cross-ref AIM-01 (VRP jump tail), AIM-02 (skew as crash predictor)

---

## Prior Extractions Held: Papers 4, 10, 11 (in RegimeClassificationMethods.md)
- **Paper 10 (Pettersson 2014):** EWMA vol vs. trailing average — Tier 1 regime classification for Program 2
- **Paper 4 (Qiao et al. 2024):** MS-HAR-GARCH with DJI proxy — Tier 2 (inactive) regime classification
- **Paper 11 (Shu, Yu & Mulvey 2025):** Supervised regime prediction for Program 2 Block 3b classifier

---

### AIM-11 Design Conclusions

**1. VIX is THE Primary Leading Indicator for Regime Transitions:**
- Higher lagged VIX → higher transition probability to high-stress regime (Paper 136)
- VIX 30.5% average on high-stress days vs. 19.8% on low-stress days
- Large absolute daily VIX change → transition in progress
- Z-score VIX level against 252-day baseline; also monitor daily VIX change

**2. For CL: Basis-Driven Transition Dynamics:**
- Negative basis (backwardation) increases high-vol regime PERSISTENCE → stay cautious longer (Paper 139)
- Positive basis (contango) → lower persistence → earlier recovery possible
- Regime shifts dominate GARCH in CL → don't rely on GARCH for CL volatility forecasting
- CL basis as explicit transition variable in Captain's CL regime model

**3. Early Warning IS Feasible:**
- Network/community structure approach detects warning signals BEFORE actual transition (Paper 131)
- Dynamic process features (sliding window) provide richer signals than point-in-time
- Option-implied FH bound predicts large downturns (Paper 134) — forward-looking supplement

**4. High-Stress Regime Characteristics:**
- 3x+ stock variance, 0.5+ lower stock-bond correlation, higher bond return (Paper 136)
- Diversification benefit from bonds INCREASES during stress → multi-asset value proposition

**5. Modifier Construction:**
```
VIX_z = z_score(VIX_close, trailing_252d)
VIX_daily_change_z = z_score(|VIX_change_today|, trailing_60d)

# VIX level warning
if VIX_z > 1.5:      vix_mod = 0.75  (high transition probability to stress)
elif VIX_z > 0.5:    vix_mod = 0.90  (elevated)
elif VIX_z < -0.5:   vix_mod = 1.05  (low stress probability)
else:                 vix_mod = 1.0

# VIX change warning (transition in progress)
if VIX_daily_change_z > 2.0:  transition_mod = 0.85  (regime shift happening NOW)
else:                          transition_mod = 1.0

# CL-specific basis overlay
if asset == CL:
    basis = (CL_spot - CL_front_futures) / CL_spot
    if basis < -0.02 and VIX_z > 0.5:  basis_mod = 0.90  (backwardation + stress = persistent)
    else:                                basis_mod = 1.0
else:
    basis_mod = 1.0

modifier = vix_mod × transition_mod × basis_mod
```

**6. Warm-up:** 252 trading days for VIX z-score baseline

**7. Data Sources:**
- VIX: CBOE, daily (free)
- CL basis: spot vs. front-month futures (data feed)
- VIX daily changes: computed from VIX close prices

**8. Cross-references:**
- AIM-01 (VRP): VRP and VIX are related but not identical — VRP jump tail provides additional information
- AIM-04 (IVTS): IVTS = VIX/VXV is a normalised version of the VIX signal
- AIM-08 (Correlation): correlation regime change is another early warning mechanism
- Program 2: Pettersson Tier 1 (Paper 10) and MS-HAR Tier 2 (Paper 4) provide the core regime labels that AIM-11 supplements with EARLY WARNING

---

# AIM-12: Dynamic Slippage & Cost Estimator

## Paper 140 — Engle, Ferstenberg & Russell (2006): Measuring and Modeling Execution Cost and Risk — FOUNDATIONAL

**What it proves:**
- Execution cost has TWO dimensions: EXPECTED COST and COST RISK (variance) — both must be modeled
- Time induces a risk/cost TRADEOFF: fast execution = higher cost, lower risk; slow execution = lower cost, higher risk
- Frontier of risk/reward tradeoffs (analogous to mean-variance portfolio analysis)
- Cost and risk are CONDITIONED on market state and order characteristics → TIME-VARYING menu of tradeoffs
- Introduces Liquidation Value at Risk (LVAR) — quantifies worst-case execution cost

**Methodology:** 233,913 orders from Morgan Stanley 2004, tracking order submission through all fill transactions

**What we take:**
- Execution cost is NOT fixed — it depends on market state at time of execution
- Captain (Online) should estimate expected slippage BEFORE trade, not assume a constant
- Cost frontier concept: for each market state, there is an optimal execution speed
- For ORB: market order at open has HIGH cost certainty but potentially HIGH cost; limit order near open has lower expected cost but FILL RISK

---

## Paper 142 — Brown, Koch & Powers (2009): Slippage and Choice of Market or Limit Orders in Futures

**What it proves:**
- Slippage on commodity futures market orders is NOT significantly different from zero ON AVERAGE
- BUT: significant cross-sectional VARIATION (wheat: -$112.50 loss to +$87.50 gain per contract)
- Time-to-clear: increases with order size and bid-ask spread; decreases with volatility and depth
- Larger orders → more ADVERSE slippage; greater market depth → MODERATES adverse impact
- Absolute slippage increases with: order size, bid-ask spread, market volatility
- Experienced traders submit LIMIT orders when adverse slippage is likely (larger orders, high vol, low depth)

**Methodology:** 2,400+ CBOT wheat/corn/soybean futures order tickets, 97 retail traders, 3-year span

**What we take:**
- Average slippage ≈ 0 for futures → NOT systematically biased against us
- But VARIANCE is the real cost → some fills much worse than expected
- Slippage determinants to monitor: order size, spread, volatility, market depth
- Adaptive order type: use limit orders when conditions indicate adverse slippage likely
- For Captain (Online): check spread and depth at execution moment → choose market vs. limit order type

---

## Paper 145 — Donnelly (2022): Optimal Execution: A Review (8,611 views)

**What it proves:**
- Comprehensive 20-year review establishing the Almgren-Chriss framework as foundational
- LOB mechanics: temporary impact (reverts) vs. permanent impact (persists)
- Price impact can be linear, nonlinear, or stochastic
- FIFO priority queue determines fill quality → position in queue matters for limit orders
- Dynamic programming and HJB equations solve the optimal execution problem
- Multiple performance criteria possible: risk-adjusted wealth, VWAP benchmarks, etc.

**What we take:**
- Temporary vs. permanent impact distinction is important for ORB: opening impact may be partly temporary → price may revert
- For small orders (1-3 contracts): temporary impact dominates → execution straightforward
- For scaling up: Almgren-Chriss framework applies → need to optimize execution schedule
- Reference resource for future implementation of execution optimization

---

## Paper 146 — Almgren (2003): Optimal Execution with Nonlinear Impact and Trading-Enhanced Risk

**What it proves:**
- Market impact per share follows POWER LAW of trading rate (includes square root law)
- Nonlinear case: "characteristic time" depends on initial portfolio size and DECREASES as execution proceeds
- Trading-enhanced risk: realized price uncertainty INCREASES with demanding rapid execution
- CRITICAL PORTFOLIO SIZE: above this, trading-enhanced risk dominates; below, it can be neglected
- Exact solutions for power law impact functions

**What we take:**
- For MOST (small positions, 1-3 contracts): likely BELOW critical portfolio size → trading-enhanced risk negligible
- Impact follows square root law → doubling order size increases impact by ~41%, not 100%
- When scaling to larger positions: must account for nonlinear impact → split orders or extend execution window
- For Captain: if position size exceeds threshold, use TWAP/VWAP rather than single market order at open

---

## Paper 143 — Tse (1999): Market Microstructure of FTSE 100 Index Futures

**What it proves:**
- Intraday patterns in index futures: spreads stable during day, DECLINE at close, INCREASE during US macro news
- Traders active at OPEN with narrow spreads and large sizes → open is relatively liquid
- Volatility and volume U-shaped (higher at open and close)
- Information asymmetry in INDEX futures is INSIGNIFICANT → diversification reduces private info effect
- Inventory costs SMALL in futures (traders reduce inventory in one trade vs. week for stock specialist)
- Grossman-Miller model confirmed: liquidity = price of demand for immediacy

**What we take:**
- Opening is LIQUID with narrow spreads → good environment for ORB execution
- Macro news times: spreads WIDEN → increase slippage allowance around 8:30 AM releases (cross-ref AIM-06)
- Index futures have LOW adverse selection costs → cost is primarily IMMEDIACY, not information asymmetry
- U-shaped volume confirms: open and close are best execution windows

---

## Paper 147 — Greer, Brorsen & Liu (1992): Slippage Costs for a Public Futures Fund

**What it proves:**
- Slippage for LARGE TECHNICAL TRADERS is about DOUBLE that of average traders ($34 vs. $17 per contract)
- Slippage LARGEST on days with LARGE PRICE MOVEMENTS and for LARGE ORDERS
- Funds trade at times when market moves quickly → brokers have trouble filling at target
- Since funds use SIMILAR SYSTEMS, trading at same time → may increase intraday price movements (crowding)
- Stop orders particularly affected: price moves before broker can fill

**What we take:**
- As a systematic/technical trader, expect HIGHER slippage than average market participant
- On high-vol days: double the slippage assumption (crowding + fast-moving markets)
- Stop-loss execution is especially costly → fixed TP/SL strategy must account for stop slippage being WORSE than entry slippage
- Crowding effect: if many ORB strategies trigger simultaneously, slippage increases for all
- For Captain: include a volatility-adjusted slippage multiplier (not constant slippage)

---

### AIM-12 Design Conclusions

**1. Execution Cost = Expected Cost + Cost Variance:**
- Both dimensions must be modeled (Paper 140)
- Expected cost depends on: order size, spread, volatility, depth, time of day
- Cost variance = the uncertainty around the fill price → this is the real risk

**2. Slippage is Near Zero on Average but HIGHLY Variable:**
- Average slippage in futures ≈ 0 → not systematically biased against traders (Paper 142)
- But variation is LARGE: -$112 to +$87 per contract possible
- Determinants: order size (+), spread (+), volatility (+), depth (-)

**3. Technical/Systematic Traders Face DOUBLE Slippage:**
- $34 vs. $17 per contract for average traders (Paper 147)
- Crowding from similar systems amplifies slippage on high-vol days
- Stop-loss fills are WORSE than entry fills → asymmetric slippage

**4. Market Impact is NONLINEAR:**
- Square root law: doubling order size → ~41% more impact, not 100% (Paper 146)
- Below critical portfolio size: trading-enhanced risk negligible (our 1-3 contracts → likely fine)
- Above: split orders via TWAP/VWAP

**5. Index Futures Open is LIQUID:**
- Narrow spreads + large sizes at open → good for ORB execution (Paper 143)
- Macro news: spreads widen → allow extra slippage
- Low information asymmetry → cost is immediacy, not adverse selection

**6. Modifier Construction:**
```
spread_z = z_score(current_spread, trailing_60d_open_spreads)
vol_z = z_score(recent_5min_vol, trailing_60d_open_vol)

# Estimate expected slippage multiplier
if spread_z > 1.5 or vol_z > 1.5:
    cost_mod = 0.85  (high execution cost environment, reduce sizing)
elif spread_z > 0.5 or vol_z > 0.5:
    cost_mod = 0.95
elif spread_z < -0.5 and vol_z < -0.5:
    cost_mod = 1.05  (low cost environment, slightly increase)
else:
    cost_mod = 1.0

# Technical trader premium (always applied)
slippage_estimate = base_slippage × 2.0  (Paper 147: systematic trader double)

# High-vol day overlay
if VIX_z > 1.0:  cost_mod *= 0.95  (high-vol = worse fills on stops)

modifier = cost_mod
```

**7. Warm-up:** 60 trading days for spread and volume z-score baselines at the open

**8. Data Sources:**
- Real-time bid-ask spread at execution (broker feed)
- 5-minute volume and volatility at open (from intraday data)
- Historical fill quality (own trade records, when available)

**9. Cross-references:**
- AIM-04 (IVTS/Pre-Market): regime filter determines expected market conditions at open
- AIM-06 (Economic Calendar): macro news days widen spreads → adjust slippage expectation
- AIM-05 (Order Book): LOB curvature and depth directly inform cost estimation
- Captain (Command/TSM): prop firm constraints (MDD) make stop slippage particularly costly
- All other AIMs: cost estimation is the BINDING CONSTRAINT on whether any signal's edge is tradeable

---

# AIM-13: Strategy Parameter Sensitivity Scanner

## Paper 152 — Bailey, Borwein, López de Prado & Zhu (2017): The Probability of Backtest Overfitting (PBO) — SEMINAL

**What it proves:**
- Introduces PBO framework and CSCV (Combinatorially Symmetric Cross-Validation)
- Model-free, nonparametric method to assess probability that a backtest-selected strategy is overfit
- Standard holdout is UNRELIABLE for investment backtests (not enough independent samples)
- Even 5 parameters across thousands of securities → BILLIONS of possible backtests → PBO can be disturbingly high
- CSCV: partition data into S subsets, form all C(S, S/2) train-test splits, compute PBO as fraction of splits where IS-best underperforms OOS median

**What we take:**
- MANDATORY for Program 1 validation: before accepting any strategy, compute PBO via CSCV
- If PBO > 0.5 → strategy is MORE LIKELY overfit than genuine → reject or flag for further investigation
- PBO increases with: number of trials, shorter data, more parameters, lower signal-to-noise
- For Captain (Offline) AIM-13 scan: compute PBO on the parameter perturbation grid
- Cross-ref Program 1 Block 5: PBO should be one of the quality metrics weighted into OO score

---

## Paper 150 — Bailey & López de Prado (2014): The Deflated Sharpe Ratio (DSR)

**What it proves:**
- Standard Sharpe ratio is INFLATED by two sources: selection bias (multiple testing) + non-Normal returns
- DSR corrects for BOTH: adjusts expected Sharpe downward based on number of strategies tested, skewness, kurtosis, sample length
- WITHOUT knowing the NUMBER OF TRIALS attempted → a backtest result is WORTHLESS
- Minimum Track Record Length (MinTRL): how many observations needed to trust a given Sharpe ratio at a given confidence level
- Type I Error probability grows multiplicatively with more strategies tested

**What we take:**
- DSR is THE adjusted performance metric for strategy evaluation in Program 1
- Must record and report the NUMBER OF CONFIGURATIONS tested (N_trials) for every strategy evaluation
- DSR formula: adjusts for N_trials, skewness, kurtosis → produces "true" significance level
- MinTRL tells us: how much OOS data do we need before we can trust the strategy is real?
- For Captain (Offline): when evaluating decay or re-evaluation, apply DSR not raw Sharpe

---

## Paper 151 — Wiecki et al. (Quantopian): Comparing Backtest and OOS on 888 Algorithms — EMPIRICAL

**What it proves:**
- EMPIRICAL: backtest Sharpe ratio has ALMOST NO predictive value for OOS performance (R² < 0.025)
- Higher-order moments (volatility, max drawdown) and portfolio construction features (hedging) are BETTER OOS predictors
- More backtesting done by quant → LARGER discrepancy between IS and OOS (direct evidence of overfitting)
- ML classifiers on backtest behavior features → R² = 0.17 for OOS prediction (7x better than Sharpe alone)
- Portfolio constructed from ML predictions OUTPERFORMS portfolio from highest backtest Sharpes
- 888 unique algorithms, Quantopian platform, backtested 2010-2015, min 6 months OOS

**What we take:**
- DO NOT select strategies primarily by backtest Sharpe ratio — it is nearly uninformative
- Instead evaluate: volatility stability, max drawdown characteristics, portfolio structure, parameter sensitivity
- For Program 1: the OO score should weight behavioral features (EIR, SIR, DIR) over raw performance metrics
- More trials/iterations increase overfitting risk → Captain (Offline) must track cumulative testing load per strategy
- ML-based selection outperforms linear — supports the idea of a meta-learning layer in Captain

---

## Paper 154 — Park & Irwin (2010): Reality Check on Technical Trading Rules in US Futures Markets

**What it proves:**
- After White's Bootstrap Reality Check + Hansen's Superior Predictive Ability correction for data snooping:
  ONLY 2 of 17 US futures markets show statistically significant profits from technical trading rules
- Technical trading rules are generally NOT profitable in US futures markets after proper correction
- The FULL UNIVERSE of rules tested must be considered, not just the best performing rule
- 1985-2004 sample period; universe of standard technical rules (moving averages, channel breakouts, etc.)

**What we take:**
- OUR strategy MUST survive White's Reality Check / Hansen's SPA test — not just in-sample significance
- Captain (Offline) AIM-13 monthly scan should include SPA-type test over the perturbation grid
- If only 2/17 futures markets survive → genuine edge is RARE → our edge claim requires extraordinary evidence
- The ORB strategy (validated in Paper 125, AIM-10) with regime conditioning (Paper 67, AIM-04) must pass this bar
- Data snooping correction is NON-NEGOTIABLE for any strategy claim

---

## Paper 157 — Aparicio & López de Prado (2018): How Hard Is It to Pick the Right Model? MCS and Backtest Overfitting

**What it proves:**
- Model Confidence Set (MCS, Hansen et al. 2011) is NOT robust to multiple testing in finance
- Requires very HIGH signal-to-noise ratio to be usable → most financial applications don't have this
- MCS useful for initial SCREENING but NOT sufficient evidence for strategy selection
- Even with sophisticated model selection, overfitting risk remains high when many models tested

**What we take:**
- MCS cannot be relied upon as the sole model selection criterion for Captain
- Use MCS for initial screening (reduce candidate set) but require PBO/DSR for final validation
- High signal-to-noise requirement → in low-SNR environments (most of finance), be extra conservative

---

## Paper 158 — Witzany (2021): Bayesian Approach to Measurement of Backtest Overfitting

**What it proves:**
- Bayesian MCMC approach yields: expected OOS haircut, probability of loss, expected OOS rank, FDR
- Empirical study on technical strategies: naively selected "best" strategy is typically a FALSE DISCOVERY
- Key insight: the IS-selected "best" strategy's expected OOS RANK is often in the middle of the candidate set, not near the top
- Probability of loss can be computed: even for IS-profitable strategies, OOS probability of loss may be >50%
- Haircut: the percentage by which IS performance must be reduced to get realistic OOS expectation

**What we take:**
- Apply Bayesian haircut to ALL strategy performance claims: expected OOS Sharpe = IS Sharpe × (1 - haircut%)
- Compute probability of loss for each strategy before adoption → reject if P(loss) > threshold (e.g., 40%)
- Expected OOS rank metric is a powerful sanity check: if the IS-best is expected to be median OOS → the edge is illusory
- For Captain (Offline): implement Bayesian PBO estimation alongside CSCV-based PBO

---

### AIM-13 Design Conclusions

**1. PBO and DSR are MANDATORY Validation Tools:**
- Before accepting ANY strategy from Program 1/2: compute PBO (via CSCV, Paper 152) and DSR (Paper 150)
- PBO > 0.5 → strategy is MORE LIKELY overfit than genuine → REJECT
- DSR adjusts Sharpe for number of trials tested + non-Normal returns → USE DSR not raw Sharpe
- Must record N_trials for every evaluation (number of parameter configurations tested)

**2. Backtest Sharpe Ratio is NEARLY USELESS for OOS Prediction:**
- R² < 0.025 on 888 algorithms (Paper 151) → Sharpe tells you almost nothing about future performance
- Higher-order features (vol, drawdown, portfolio structure) are 7x more predictive
- ML-based selection outperforms → supports Captain's meta-learning architecture

**3. After Data Snooping Correction, Most Technical Rules FAIL:**
- Only 2/17 US futures markets survive White's Reality Check (Paper 154)
- Our strategy MUST pass this bar → ORB + regime filter + feature selection must be tested as a FAMILY
- Any strategy claim without data snooping correction is INVALID

**4. Bayesian Haircut:**
- Expected OOS Sharpe = IS Sharpe × (1 - haircut%) (Paper 158)
- Compute probability of loss before adoption
- IS-best strategy's expected OOS rank may be MEDIAN, not top

**5. Monthly Sensitivity Scan (AIM-13 Operation):**
```
# Captain (Offline) monthly AIM-13 scan:
for each active strategy (model, feature, threshold):
    perturbation_grid = generate_perturbations(±10%, ±20% on each parameter)
    for each perturbation:
        compute Sharpe, drawdown, win_rate on recent OOS window
    
    # Sensitivity metrics:
    sharpe_stability = std(Sharpe across grid) / mean(Sharpe across grid)  # lower = more robust
    pbo = compute_CSCV(perturbation_grid, recent_data)
    dsr = compute_DSR(best_Sharpe, N_trials=len(grid), skew, kurt, T)
    
    # Flags:
    if sharpe_stability > 0.5:   FLAG "FRAGILE" → parameter-sensitive
    if pbo > 0.5:                FLAG "OVERFIT" → likely data-mined
    if dsr < 0.5:                FLAG "INSIGNIFICANT" → insufficient evidence
    
    # If 2+ flags → trigger Level 2 alert (sizing reduction) or Level 3 (strategy re-evaluation)
```

**6. Warm-up:** Requires sufficient OOS data (MinTRL from DSR, typically 100+ trading days for Sharpe ≈ 1.0)

**7. Data Sources:** Strategy backtest results (internal), parameter grid (generated), OOS trade outcomes (accumulated)

**8. Cross-references:**
- Program 1 Block 5: PBO/DSR should be weighted into OO score
- Captain (Offline): AIM-13 scan triggers Level 2/3 autonomy when flags raised
- AIM-14 (Auto-Expansion): when AIM-13 flags decay, AIM-14 searches for replacements
- System Topic 3 (Sequential Monitoring): SPRT/CUSUM detects performance decay; AIM-13 investigates the CAUSE (parameter sensitivity vs. regime shift)

---

# AIM-14: Model Universe Auto-Expansion Monitor

## Paper 164 — Deep, Deep & Lamptey (2025): Interpretable Hypothesis-Driven Walk-Forward Validation

**What it proves:**
- Rigorous walk-forward validation with 34 INDEPENDENT OOS periods + strict information discipline eliminates lookahead bias
- Honest results: 0.55% annualised, Sharpe 0.33, p-value 0.34 (NOT significant) — this is what GENUINE validation looks like
- BUT: exceptional downside protection (maxDD -2.76% vs. -23.8% SPY), market-neutral (β = 0.058)
- Performance is REGIME-DEPENDENT: high-vol (2020-2024) = +2.4% annualised; stable (2015-2019) = -0.16%
- Framework is AGNOSTIC to hypothesis source → extensible to LLMs, genetic programming, neural nets
- Every trade originates from a human-INTERPRETABLE hypothesis

**What we take:**
- Walk-forward with multiple independent OOS periods is THE gold standard for strategy validation
- Expect MODEST results after rigorous validation — 15-30% published claims are almost always overfit
- Regime-dependent performance is NORMAL — strategies work conditionally, not universally
- Interpretability requirement aligns with our regulatory/audit needs (GUI discretionary reports)
- Open-source template → can adapt for Captain (Offline) AIM-14 candidate evaluation

---

## Paper 163 — Kim, Ahn, Oh & Enke (2017): Intelligent Hybrid Trading System — Rough Sets + GA for Futures

**What it proves:**
- Rough set analysis + genetic algorithm successfully discovers interpretable trading rules for futures
- GA simultaneously solves data discretisation + reduct optimisation (both NP-hard)
- Generated 'If-then' decision rules are TRANSPARENT — investors can understand the reasoning
- Sliding window method validates temporal stability
- Significantly outperforms benchmark on KOSPI 200 futures
- Analysis of training period size and number of rules → both matter for OOS performance

**What we take:**
- THIS is the type of automated rule discovery AIM-14 should implement
- GA + rough sets = interpretable rule generation from technical indicator feature space
- For Captain Level 3: when strategy decays, GA searches feature space for new if-then rules
- Interpretable rules satisfy regulatory/compliance requirements + human audit capability
- Training period size optimisation is a meta-parameter that must be tuned (connects to Paper 161)

---

## Paper 161 — Mroziewicz & Ślepaczuk (2026): Walk-Forward Optimization with Double OOS

**What it proves:**
- Walk-forward window LENGTH itself must be optimised — performance is HIGHLY dependent on it
- Novel "double OOS": optimise on training → select best on validation → test ONCE on final holdout
- 81 combinations of window lengths tested (1-28 days training, various testing windows)
- EMA Crossover on Bitcoin intraday at 6 frequencies over 19-month training + 21-month OOS
- Walk-forward strategy has LOWER drawdown and HIGHER Information Ratio than buy-and-hold
- PORTFOLIO combining buy-and-hold + walk-forward strategy → 50% drawdown REDUCTION, highest performance
- Parameters transfer CROSS-ASSET: Bitcoin-optimised parameters work on Ethereum and Binance Coin
- Break-even cost: 0.4% per transaction → strategy survives realistic costs

**What we take:**
- Window length is a CRITICAL meta-parameter → AIM-14 must optimise it, not fix it
- Double OOS prevents data contamination → Captain must enforce strict OOS discipline for candidate evaluation
- Cross-asset parameter transfer works → feature/threshold discovered for ES may apply to NQ
- Portfolio of strategies outperforms individual → Captain should maintain a PORTFOLIO of validated strategies
- Walk-forward delivers lower drawdown even when raw returns are similar → risk management value

---

## Paper 162 — Lo: Data-Snooping Biases in Financial Analysis — CLASSIC

**What it proves:**
- Data snooping can NEVER be completely eliminated — it is unavoidable in non-experimental inference
- The "Carmichael numbers" example: a completely nonsensical stock selection rule produces stellar backtest results purely by chance
- Given enough time, attempts, and imagination, ALMOST ANY pattern can be teased from data
- Solutions are RARELY statistical → need a FRAMEWORK to limit the search
- Framework should come from: economic theory, psychological theory, or analyst's judgment/experience
- Awareness of the problem is the MOST IMPORTANT step

**What we take:**
- FUNDAMENTAL: AIM-14's search space MUST be constrained by economic/market mechanism theory
- Cannot search over arbitrary feature combinations → must have hypothesis for WHY a feature would work
- Captain (Offline) must log all searches attempted (N_trials) and apply DSR (AIM-13) correction
- The ORB strategy has economic reasoning (momentum, contraction-expansion) → it passes this bar
- Random feature generation without theoretical basis = guaranteed overfitting

---

## Paper 165 — Koshiyama & Firoozye (2019): Avoiding Backtesting Overfitting by Covariance-Penalties

**What it proves:**
- Covariance-Penalty Correction: penalise risk metric proportional to number of parameters and amount of data
- Three approaches categorised: Data Snooping, Overestimated Performance, Cross-Validation
- AIC/BIC-like complexity penalty applied to strategy evaluation → simpler strategies PREFERRED
- Total Least Squares outperforms Ordinary Least Squares
- Tested on 1300+ assets — suitable procedure to avoid backtest overfitting
- Practical: easy to implement alongside existing evaluation

**What we take:**
- SIMPLER strategies with fewer parameters should be PREFERRED → complexity penalty in OO score
- Covariance-penalty provides an automatic mechanism: more parameters → lower adjusted performance
- For AIM-14 candidate ranking: penalise candidates by parameter count
- Complements PBO (AIM-13) — PBO measures overfitting probability, covariance-penalty adjusts the metric

---

### AIM-14 Design Conclusions

**1. Automated Strategy Discovery is Feasible but Requires Extreme Rigour:**
- Walk-forward with multiple independent OOS periods (34 in Paper 164)
- Double OOS: training → validation → final holdout tested ONCE (Paper 161)
- Interpretable rules REQUIRED: if-then, natural language, rough set output (Papers 163, 164)
- Search CONSTRAINED by economic theory — never arbitrary feature search (Paper 162)

**2. AIM-14 Operation (Captain Level 3 Trigger):**
```
# When AIM-13 flags strategy decay → AIM-14 activates:

# Step 1: Generate candidates
candidates = GA_rough_set_search(
    feature_space = Program_1_features,
    constraints = economic_theory_filter,  # Paper 162: theory-bounded search
    max_parameters = 5,  # complexity limit
    population_size = 100,
    generations = 50
)

# Step 2: Walk-forward validate each candidate
for candidate in candidates:
    # Paper 161: optimise window length as meta-parameter
    for window_config in window_grid:
        wf_results = walk_forward_validate(candidate, window_config, training_data)
    
    best_window = select_best_window(wf_results, criterion="robust_sharpe")
    
    # Paper 164: multiple independent OOS windows
    oos_results = multi_window_oos_test(candidate, best_window, holdout_data)

# Step 3: Filter candidates
for candidate in validated_candidates:
    pbo = compute_PBO(candidate)       # AIM-13: Paper 152
    dsr = compute_DSR(candidate)       # AIM-13: Paper 150
    complexity_penalty = covariance_penalty(candidate.n_params)  # Paper 165
    
    adjusted_score = dsr - complexity_penalty
    
    if pbo > 0.5: REJECT
    if adjusted_score < threshold: REJECT

# Step 4: Present surviving candidates to user (tiered autonomy)
# Level 3: requires user approval via GUI before adoption
```

**3. Key Design Principles:**
- Theory-constrained search: every candidate must have an economic hypothesis (Paper 162)
- Simpler is better: complexity penalty → fewer parameters preferred (Paper 165)
- Window length is a meta-parameter: optimise, don't fix (Paper 161)
- Expect modest results from honest validation → 0.55% annualised is realistic (Paper 164)
- Cross-asset transfer: parameters from one asset may work on similar assets (Paper 161)
- Portfolio of strategies > single strategy → maintain multiple validated strategies (Paper 161)

**4. Warm-up:** Requires sufficient data for walk-forward training (minimum 252 days per candidate evaluation)

**5. Data Sources:** Program 1 features + transformations; historical backtest results; feature space definitions

**6. Cross-references:**
- AIM-13 (Sensitivity): decay detection triggers AIM-14 activation; PBO/DSR validate candidates
- Program 1: features and models to search over
- Captain (Offline): Level 3 autonomy → AIM-14 runs automatically but adoption requires human approval
- Captain (Command): GUI presents candidates with interpretable hypotheses for user decision

---

# AIM-15: Opening Session Volume Quality Monitor

## Paper 175 — Mittal & Choudhary: Liquidity-Driven Breakout Reliability — CRITICAL FOR ORB

**What it proves:**
- Breakouts entering LOW-VOLUME price zones have >70% continuation probability (Kaplan-Meier survival)
- Breakouts testing HIGH-VOLUME nodes are approximately RANDOM (no edge)
- Liquidity structure is the OMITTED VARIABLE in breakout analysis — not momentum, not volatility, not information
- Price moves because LIQUIDITY IS ABSENT, not because of aggressive force
- 15,000+ breakout events across equity index futures, FX, commodities, 2022-2024
- Value Area structures and volume-at-price analysis formalise the concept

**What we take:**
- FOR ORB: breakout quality depends on WHETHER price is moving into a liquidity-sparse zone
- If opening range breakout moves into a zone with LOW historical volume → HIGH continuation probability → SIZE UP
- If breakout moves into a zone with HIGH historical volume → likely to stall → REDUCE or skip
- Captain (Online): compute volume profile from prior sessions, identify high/low volume nodes relative to breakout level
- This is potentially the single most impactful enhancement to ORB reliability

---

## Paper 168 — Tsai et al. (2019): Timely Opening Range Breakout (TORB) on Index Futures — DIRECT VALIDATION

**What it proves:**
- TORB using 1-MINUTE intraday data achieves >8% annual returns across ALL 5 index futures markets tested (DJIA, S&P 500, NASDAQ, HSI, TAIEX)
- Best performance: 20.28% annual return in TAIEX (p = 3.1×10⁻⁵%)
- Key innovation: align breakout parameters with UNDERLYING stock market opening hours (active hours)
- Best probing time: SHORT in US markets (few minutes), LONGER in Asian markets
- TORB signals are in the SAME direction as institutional traders (especially foreign investment institutions)
- TORB outperforms TRB (daily data-based range breakout) → higher frequency data = more information
- Results survive sub-period analysis (2003-2007 and 2007-2013) including financial crisis

**What we take:**
- TORB is a VALIDATED ORB variant for index futures with significant returns across multiple markets
- 1-minute data is SUPERIOR to daily data for ORB strategy calibration
- Opening range length matters: 5-minute range produces most significant results for US markets
- For MOST: ORB parameters should be calibrated to the first few minutes of the underlying stock market open
- Institutional trader alignment → ORB captures the same signal that institutions act on
- Cross-ref AIM-04 Paper 67: TORB validates ORB profitability even WITHOUT explicit IVTS regime filter

---

## Paper 176 — Zarattini, Barbon & Aziz (2024): ORB + Stocks in Play — VOLUME QUALITY IS THE KEY

**What it proves:**
- 5-minute ORB on "Stocks in Play" (stocks with higher-than-normal volume due to news): 1,600% total return, Sharpe 2.81, annualised alpha 36% (2016-2023)
- S&P 500 buy-and-hold over same period: only 198%
- KEY INSIGHT: ORB works DRAMATICALLY BETTER when applied to assets with ELEVATED VOLUME/ACTIVITY
- Limiting ORB to Stocks in Play produces significant net returns AFTER transaction costs
- Multiple ORB timeframes: 5-min, 15-min, 30-min, 60-min all tested with stock-level statistics
- 7,000+ US stocks, comprehensive stock-level database

**What we take:**
- VOLUME QUALITY is THE differentiator for ORB profitability — not the strategy itself but WHEN to apply it
- For futures (ES, NQ, CL): the equivalent of "Stocks in Play" is days with ABOVE-AVERAGE opening volume
- Captain (Online): compute opening session volume relative to trailing average → if significantly above → ORB edge is stronger
- This explains why ORB sometimes works and sometimes doesn't — volume quality was the missing variable
- Sharpe 2.81 with proper volume filtering vs. much lower without → volume quality is worth more than any other signal modifier

---

## Paper 177 — Wen, Gong, Ma & Xu (2021): Intraday Momentum in Crude Oil

**What it proves:**
- In CL market: ONLY the first half-hour returns positively predict last half-hour returns
- Different from equity markets where second-to-last half-hour also predicts
- The OVERNIGHT component of the first half-hour contains MORE predictive information than the open half-hour
- Market timing strategy based on this generates substantial profits
- Oil inventory announcements do NOT offer predictability for last half-hour returns (contrasts with AIM-04 Paper 62)
- USO ETF data, 2006-2018

**What we take:**
- For CL: the first half-hour (driven by overnight information) is the ONLY intraday predictor → simplifies signal construction
- Overnight information dominance confirms AIM-04 overnight return signal for CL
- CL has a SIMPLER intraday momentum pattern than equities → fewer complications
- Volume around the open is critical for capturing this first-half-hour predictive power

---

## Paper 170 — Frino, Bjursell, Wang & Lepone (2008): Large Trades and Intraday Futures Price Behavior

**What it proves:**
- Large buyer-initiated trades: larger PERMANENT (information) impact; smaller TEMPORARY (liquidity) impact
- Large seller-initiated trades: larger TEMPORARY impact; smaller PERMANENT impact
- In BEARISH markets: seller information effects > buyer effects; buyer liquidity effects > seller
- In BULLISH markets: buyer information effects > seller; seller liquidity effects > buyer
- Market condition is a KEY DETERMINANT of asymmetric price effects
- S&P 500, NASDAQ-100, Live Cattle, British Pound, Eurodollar (CME)

**What we take:**
- Large trade impact is REGIME-DEPENDENT → confirms regime-first architecture
- In bearish markets: large sells carry more information → downside ORB breakouts may be more informative
- In bullish markets: large buys carry more information → upside ORB breakouts may be more informative
- For AIM-15: opening session trade SIZE distribution (are there large trades?) indicates institutional activity quality
- Cross-ref AIM-11 (Regime Warning): regime determines which side of ORB is more informative

---

## Paper 174 — Rosa (2022): Understanding Intraday Momentum — DUPLICATE

Already fully extracted as Paper 65 in AIM-04. Key finding: intraday momentum is regime-dependent, threshold filtering essential.

---

### AIM-15 Design Conclusions

**1. Volume Quality is THE Key Differentiator for ORB Reliability:**
- ORB on high-volume sessions → Sharpe 2.81 (Paper 176); ORB on normal sessions → much lower
- Breakouts into low-volume price zones → >70% continuation (Paper 175); into high-volume → random
- Volume quality explains WHY ORB sometimes works and sometimes doesn't — the missing variable all along
- This is potentially the single most impactful enhancement to the MOST strategy

**2. Dual Volume Quality Check:**
- (a) TEMPORAL: Is TODAY's opening volume above trailing average? → measures market interest/conviction
- (b) SPATIAL: Is the breakout moving INTO a low-volume price zone? → measures path resistance

**3. TORB Validates ORB Across 5 Index Futures Markets:**
- >8% annual returns using 1-minute data (Paper 168)
- 5-minute range = optimal for US markets
- Aligns with institutional trader direction
- Higher frequency data = more information → use 1-min data for ORB calibration

**4. CL-Specific: First Half-Hour is the Only Predictor:**
- Simpler than equity markets (Paper 177)
- Overnight component dominates → confirms AIM-04 signals
- Opening volume quality critical for capturing this effect

**5. Large Trade Impact is Regime-Dependent:**
- Bearish: seller trades more informative; Bullish: buyer trades more informative (Paper 170)
- Opening session trade SIZE distribution indicates institutional participation quality

**6. Modifier Construction:**
```
# Temporal volume quality (primary)
open_volume_30min = volume in first 30 min of session
avg_open_volume_20d = trailing 20-day average of first-30-min volume

volume_ratio = open_volume_30min / avg_open_volume_20d

if volume_ratio > 1.5:    vol_mod = 1.15  (high conviction, strong ORB environment)
elif volume_ratio > 1.0:  vol_mod = 1.05  (above average, moderate confirmation)
elif volume_ratio < 0.7:  vol_mod = 0.80  (low conviction, ORB signal unreliable)
else:                     vol_mod = 1.0

# Spatial volume quality (if volume profile available)
breakout_zone_volume = volume_at_price(breakout_level ± buffer)
if breakout_zone_volume < 20th_percentile:
    spatial_mod = 1.10  (low liquidity zone → high continuation probability)
elif breakout_zone_volume > 80th_percentile:
    spatial_mod = 0.85  (high liquidity zone → likely to stall)
else:
    spatial_mod = 1.0

modifier = vol_mod × spatial_mod
```

**7. Warm-up:** 20 trading days for volume ratio baseline; volume profile needs 5-10 sessions

**8. Data Sources:**
- Real-time volume at open: from intraday data feed
- Volume profile (volume-at-price): from prior sessions' tick data or from platform tools
- No proprietary data needed — OHLCV sufficient for temporal quality; tick data for spatial quality

**9. Cross-references:**
- AIM-04 (Pre-Market): overnight return signal + volume quality = compound ORB reliability indicator
- AIM-05 (Order Book): LOB depth at open is the microstructure version of volume quality
- AIM-10 (Calendar): ORB validated on CL (Paper 125) + now volume quality explains WHEN it works
- AIM-12 (Costs): high volume = tighter spreads = better execution quality (virtuous cycle)
- All AIMs: volume quality may be the SINGLE MOST IMPORTANT conditioning variable for the entire system

---

# SYSTEM TOPIC EXTRACTIONS

## System 1: Multi-Signal Aggregation and Online Learning

## Paper 184 — Timmermann (2018): Forecasting Methods in Finance (Annual Review of Financial Economics)

**What it proves:**
- Financial forecasting has UNIQUE challenges: low signal-to-noise ratio, persistent predictors, model instability from competitive pressures, data mining concerns
- Competitive pressures → predictable patterns SELF-DESTRUCT as investors exploit them → model instability is FUNDAMENTAL
- Forecast COMBINATION (ensemble) methods are THE approach for dealing with weak predictors and estimation error
- Economic evaluation (certainty equivalent, realized utility from trading) more informative than statistical measures (MSE, R²)
- Methods: filtering, bounds from economic theory (conditional Sharpe ratio), combining forecasts, density forecasting via options

**What we take:**
- THE authoritative statement that ensemble/combination is correct for financial forecasting
- Captain's meta-learning (combining multiple AIM outputs) is the theoretically grounded approach
- Must evaluate AIM signals by ECONOMIC performance (P&L, Sharpe, utility) not just statistical significance
- Model instability is expected → Captain must continuously adapt, not maintain fixed weights
- Filtering methods (Kalman filter / DMA) extract persistent signals from noisy data

---

## Paper 187 — Nonejad (2021): Dynamic Model Averaging (DMA) Techniques — Survey (49pp, 300+ citations)

**What it proves:**
- DMA provides practical, efficient handling of model uncertainty + parameter instability SIMULTANEOUSLY
- The IDENTITY of the best model CHANGES over time → DMA dynamically tracks which model/predictor is currently best
- Uses forgetting factors + Kalman filter → computationally efficient, NO simulation required
- Model probabilities update each period → at each point, different predictors may be relevant
- Output: inclusion probability of each predictor at each time point → tells you which signals matter NOW
- Applications span: equity returns, inflation, commodity prices, volatility, exchange rates → universally useful
- DMA outperforms static BMA, random walk, and autoregressive benchmarks

**What we take:**
- DMA is THE framework for Captain's meta-learning layer / AIM aggregation
- Forgetting factor controls how quickly old observations lose influence → natural mechanism for regime adaptation
- Inclusion probability output → Captain can AUTOMATICALLY determine which AIMs are currently contributing
- Computationally lightweight → feasible for daily Captain (Online) operation
- Each AIM's output becomes a "predictor" in the DMA framework; DMA dynamically weights them
- Cross-ref AIM-13 (Sensitivity): DMA naturally discounts AIMs that have degraded (their inclusion probability drops)

---

## Paper 180 — Li & Hoi (2014): Online Portfolio Selection: A Survey (ACM Computing Surveys, 154 citations)

**What it proves:**
- Comprehensive survey of ONLINE (sequential) portfolio selection algorithms
- Four categories: Follow-the-Winner (asymptotically optimal), Follow-the-Loser (mean reversion), Pattern Matching, Meta-Learning Algorithms (MLAs)
- MLAs combine MULTIPLE strategies automatically → directly applicable to Captain's architecture
- Connection to Capital Growth Theory (Kelly criterion) → theoretical link to System Topic 2
- Online learning: portfolio adjusts period by period using only past information → no lookahead
- MLAs achieve robust performance by not committing to any single strategy

**What we take:**
- Captain doesn't pick ONE strategy — it dynamically COMBINES multiple strategies via MLA framework
- Follow-the-Winner (trend) and Follow-the-Loser (mean reversion) can COEXIST when properly combined
- Kelly criterion / capital growth theory provides the theoretical foundation for sequential sizing
- For Captain (Online): treat each AIM-weighted signal as a "strategy" → MLA-type aggregation combines them
- The online learning paradigm (process data sequentially, adjust) IS the Captain's operational mode

---

## Paper 183 — Khezri, Tanha & Samadi (2023): Ensemble Data Stream Classification in Non-Stationary Environments

**What it proves:**
- Ensemble learning is specifically efficient for NON-STATIONARY data streams with concept drift
- Component-based nature → DYNAMIC UPDATES: add, remove, reweight individual classifiers as data evolves
- Online vs. chunk-based processing: online updates per instance; chunk-based buffers then batch-updates
- Concept DRIFT: underlying distribution changes → model must detect and adapt
- Concept EVOLUTION: entirely new patterns emerge that weren't in training
- Key drift detectors: ADWIN, DDM (Drift Detection Method), DWM (Dynamic Weighted Majority), STEPD
- 24 synthetic non-stationary streams tested; ensemble methods outperform single classifiers under drift

**What we take:**
- Captain's 15 AIMs as ensemble components → can be dynamically added/removed/reweighted as their relevance changes
- ADWIN as drift detector: monitors each AIM's prediction accuracy; when accuracy drops → concept drift detected → reduce AIM weight
- DWM (Dynamic Weighted Majority): dynamically adjusts weights of ensemble members based on recent performance → THIS is the Captain's meta-learning mechanism
- Concept evolution = when a completely new market pattern emerges that no AIM covers → triggers AIM-14 auto-expansion
- Chunk-based (daily batch) vs. online (per-trade) → Captain (Online) processes daily; Captain (Offline) batch-processes for retraining

---

### System 1 Design Conclusions

**1. DMA is THE Framework for Captain's AIM Aggregation:**
- Each AIM output is a "predictor" in the DMA system
- DMA dynamically updates model probabilities → at each point, some AIMs matter more than others
- Forgetting factor controls adaptation speed → set appropriately for daily trading cadence
- Computationally lightweight → feasible for daily Captain (Online) operation
- Output: dynamic inclusion probability for each AIM → automatically weights/suppresses AIMs

**2. Forecast Combination is Theoretically Correct:**
- Low SNR environment → individual predictors are weak → combination improves accuracy
- Competitive pressures destroy patterns → combination adapts as individual signals degrade
- Evaluate by ECONOMIC performance (P&L, Sharpe), not just statistical significance

**3. Captain Architecture Maps to Meta-Learning Algorithm (MLA):**
- 15 AIMs = 15 "strategies" to combine
- MLA dynamically combines them → doesn't commit to any single signal
- Follow-the-Winner (trend AIMs like AIM-09) and Follow-the-Loser (contrarian AIMs like AIM-07 hedger sentiment) coexist
- Kelly criterion provides theoretical foundation for sequential sizing decisions

**4. Ensemble Handles Non-Stationarity:**
- Component-based → add/remove/reweight AIMs as they gain or lose relevance
- ADWIN or DWM as drift detection mechanism for individual AIM performance
- Concept evolution → triggers AIM-14 auto-expansion when new patterns emerge

**5. Implementation Path:**
```
# Captain (Online) daily aggregation using DMA:
for each trading day t:
    # Collect AIM outputs
    aim_outputs = [AIM_1.modifier, AIM_2.modifier, ..., AIM_15.modifier]
    
    # DMA update: compute model probabilities using forgetting factor
    model_probs = DMA_update(aim_outputs, forgetting_factor=0.99, prior_probs=yesterday_probs)
    
    # Weighted aggregation
    combined_modifier = weighted_average(aim_outputs, weights=model_probs)
    
    # Apply to Kelly sizing
    final_size = kelly_fraction × combined_modifier
    
    # Captain (Offline) periodic: monitor inclusion probabilities
    for each AIM:
        if inclusion_probability < threshold:
            FLAG "AIM may be irrelevant" → investigate or reduce
```

**6. Cross-references:**
- System 2 (Kelly): capital growth theory provides the objective function for DMA-weighted decisions
- System 3 (Sequential Monitoring): SPRT/CUSUM detects individual AIM decay; DMA automatically adapts
- System 4a (Concept Drift): ADWIN/DDM detect drift; DMA adapts weights via forgetting factor
- System 4c (Ensemble Meta-Learning): MoE/model averaging provides the theoretical foundation
- AIM-13 (Sensitivity): PBO/DSR validate that the combined signal is genuine, not overfit

---

## System 2: Kelly Criterion with Parameter Uncertainty

## Paper 219 — MacLean & Zhao (2022): Kelly Investing with Downside Risk Control in a Regime-Switching Market — THE SIZING PAPER

**What it proves:**
- Kelly strategy modified for REGIME-SWITCHING markets with DOWNSIDE RISK CONTROL
- Market = Markovian regime process; within each regime, asset prices are lognormal
- Modified Kelly = "BLENDED Kelly": regime-specific Kelly portfolios combined via probability weights
- Multi-asset problem reduces to: (1) determine REGIME WEIGHTS, (2) determine FRACTION allocated to risky assets
- VaR constraint at EACH discrete decision point (not just horizon) → controls shortfall RATE and SIZE
- Shortfalls penalised with CONVEX function → linked to Prospect Theory (loss aversion)
- Estimation risk controlled by regime switching; decision risk controlled by downside threshold
- Single regime → fractional Kelly. Multiple regimes → regime-weighted blended Kelly
- Applied to sector ETFs with demonstrated superiority

**What we take:**
- Captain (Online) sizing = BLENDED KELLY across regime probabilities
- Each regime (from Program 2) has its own optimal Kelly portfolio → blend using regime transition probabilities
- TSM constraints (MDD, MLL) map to the downside wealth threshold → convex shortfall penalty enforces them
- VaR at EACH decision point (each trading day) → not just end-of-period constraint
- The regime-switching structure means sizing AUTOMATICALLY adjusts as regime probabilities change
- This IS the mathematical specification for Captain (Online)'s core sizing algorithm

---

## Paper 217 — Baker & McHale (2013): Optimal Betting Under Parameter Uncertainty — SHRINKAGE

**What it proves:**
- Kelly bet should be SHRUNK when the probability of winning is ESTIMATED (not known with certainty)
- "Parameter risk": out-of-sample optimal decision ≠ in-sample optimal decision → raw Kelly OVERESTIMATES
- Shrinkage factor depends on UNCERTAINTY about the probability estimate
- For logarithmic utility: scaling is ALWAYS shrinkage (never swelling) → always bet LESS than raw Kelly
- "Back of envelope" correction: simple scaling factor for practitioners
- Bootstrap approach to estimate the shrinkage factor from historical prediction accuracy
- Half-Kelly is widely used → this paper provides THEORETICAL JUSTIFICATION for why it works
- Tested on simulation + tennis betting data → shrunken Kelly outperforms raw Kelly OOS

**What we take:**
- Captain MUST shrink Kelly sizing below the raw optimal → parameter uncertainty is unavoidable
- Shrinkage formula: f_adjusted = f_kelly × shrinkage_factor, where shrinkage depends on estimation variance
- Back-of-envelope: if estimation uncertainty is high → shrink more; if low → shrink less
- Half-Kelly (f_adjusted = 0.5 × f_kelly) is a conservative but effective starting point
- As Captain accumulates more data and estimation improves → shrinkage factor can gradually increase toward 1.0
- This provides the BRIDGE between theoretical Kelly and practical implementation

---

## Paper 218 — Sun & Boyd (Stanford): Distributional Robust Kelly Strategy — WORST-CASE GUARANTEE

**What it proves:**
- Distributional robust Kelly: maximise WORST-CASE expected log growth across an UNCERTAINTY SET of distributions
- Extends Breiman's asymptotic optimality theorem: robust Kelly STILL maximises worst-case growth rate even when distributions VARY within the uncertainty set
- Dominates any other essentially different strategy by magnitude in the long run
- Three sources of uncertainty: (1) in-sample/out-of-sample gap (optimizer's curse), (2) distribution shift (non-stationarity), (3) estimation errors in mean and covariance
- Computationally: CONVEX problem, tractable via DCP/CVXPY for finite outcomes with standard uncertainty sets
- Uncertainty sets can be: moment constraints, support constraints, f-divergence balls, Wasserstein balls
- Horse race numerical example shows significant improvement in worst-case wealth growth

**What we take:**
- For Captain: when regime is UNCERTAIN (transition zone, new regime), use robust Kelly as fallback
- The uncertainty set should reflect: regime probability uncertainty + return parameter estimation error + non-stationarity
- Convex → implementable in Captain (Online) using CVXPY or equivalent solver
- Worst-case guarantee = the FLOOR on growth rate is optimised → prevents catastrophic losses from model error
- In practice: during HIGH uncertainty (regime transition, novel market condition) → robust Kelly; during LOW uncertainty (stable regime) → standard blended Kelly
- This provides the SAFETY NET that prevents Captain from over-betting on uncertain estimates

---

### System 2 Design Conclusions

**1. Blended Kelly is THE Sizing Formula:**
- Captain (Online) sizing = regime-weighted blend of regime-specific Kelly portfolios (Paper 219)
- Each regime from Program 2 has its own optimal Kelly fraction → blend using current regime probabilities
- TSM constraints (MDD, MLL, prop firm rules) map to downside wealth threshold + convex shortfall penalty
- VaR at EACH decision point → daily risk control, not just end-of-period

**2. Kelly MUST be Shrunk for Parameter Uncertainty:**
- Raw Kelly systematically OVERESTIMATES optimal bet when probabilities are estimated (Paper 217)
- Shrinkage factor depends on estimation uncertainty → more uncertainty = more shrinkage
- Half-Kelly (50% of raw) is a conservative, effective starting point
- As data accumulates and estimation improves → gradually increase toward full Kelly
- For logarithmic utility: shrinkage is ALWAYS the right direction (never swell)

**3. Robust Kelly for Worst-Case Protection:**
- When regime is uncertain (transition, novel condition) → maximise worst-case log growth (Paper 218)
- Extends Breiman's guarantee to uncertain environments → still asymptotically optimal
- Convex, tractable via standard solvers (CVXPY)
- Provides the safety net preventing over-betting on uncertain estimates

**4. Implementation Architecture:**
```
# Captain (Online) daily sizing:

regime_probs = Program2_regime_probabilities()  # from regime classifier
regime_kelly = {}
for regime in [LOW_VOL, HIGH_VOL]:
    regime_kelly[regime] = compute_kelly_fraction(
        E_return=EWMA_regime_return[regime],
        volatility=regime_vol[regime],
        win_rate=regime_win_rate[regime]
    )

# Step 1: Blended Kelly (Paper 219)
blended_kelly = sum(regime_probs[r] * regime_kelly[r] for r in regimes)

# Step 2: Parameter uncertainty shrinkage (Paper 217)
shrinkage = estimate_shrinkage_factor(estimation_variance, N_observations)
adjusted_kelly = blended_kelly * shrinkage  # always ≤ blended_kelly

# Step 3: Robust fallback during high uncertainty (Paper 218)
if regime_uncertainty > threshold:  # e.g., regime probabilities near 50/50
    robust_kelly = solve_robust_kelly(uncertainty_set, return_bounds)
    final_kelly = min(adjusted_kelly, robust_kelly)  # take the more conservative
else:
    final_kelly = adjusted_kelly

# Step 4: Apply AIM modifiers and TSM constraints
final_size = final_kelly * combined_AIM_modifier
final_size = apply_TSM_constraints(final_size, MDD_remaining, MLL_buffer)
```

**5. Cross-references:**
- System 1 (DMA): DMA weights feed into regime probabilities for blended Kelly
- System 3 (SPRT/CUSUM): detects when Kelly parameters need updating (decay in edge)
- System 4b (Thompson Sampling): TS provides constrained action selection; Kelly provides the sizing magnitude
- AIM-01 through AIM-15: each AIM's modifier adjusts the Kelly fraction up or down
- Captain (Command/TSM): TSM constraints become the downside threshold in Paper 219's framework
- Program 2: regime probabilities are the WEIGHTS in the blended Kelly formula

---

## System 3: Sequential Monitoring for Strategy Decay

## Paper 231 — Adams & MacKay (2007): Bayesian Online Changepoint Detection (BOCPD) — THE ALGORITHM

**What it proves:**
- Online algorithm for EXACT inference of the most recent changepoint in sequential data
- Computes posterior distribution over "run length" r_t (time since last changepoint) at each timestep
- Message-passing algorithm: recursive, O(1) per update (after sufficient statistics), highly MODULAR
- Two calculations per step: (1) prior over r_t given r_{t-1}, (2) predictive distribution given run data
- Run length DROPS TO ZERO when changepoint occurs; GROWS when no change
- Predictive distribution: integrates over run length posterior → automatically adapts predictions after changepoint
- Applicable to ANY data type (Gaussian, Poisson, etc.) via modular likelihood specification
- 3 real-world datasets demonstrated (well log, bee dance, NYSE returns)

**What we take:**
- BOCPD is THE algorithm for Captain (Offline) strategy decay detection
- Monitor trade P&L stream → when run length posterior mass concentrates at 0 → changepoint = strategy decay
- At each trading day: Captain computes P(changepoint today | all past P&L) → when this exceeds threshold → trigger Level 2 (sizing reduction) or Level 3 (strategy re-evaluation)
- Modular: apply SEPARATELY to each AIM's performance stream → detect which specific AIM has degraded
- The run length distribution also provides UNCERTAINTY about whether change has occurred → probabilistic, not binary
- Can monitor MULTIPLE streams simultaneously (trade P&L, AIM accuracy, regime features)

---

## Paper 232 — Chatterjee & Qiu (2009): Distribution-Free CUSUM Control Charts with Bootstrap (Annals of Applied Statistics)

**What it proves:**
- Traditional CUSUM assumes NORMAL distributions → when violated (common in finance!), actual in-control ARL differs DRAMATICALLY from nominal
- Proposed: DISTRIBUTION-FREE CUSUM with SEQUENTIAL control limits estimated by BOOTSTRAP
- Control limits conditioned on "sprint length" T_n (time since last CUSUM reset) → (C_n, T_n) forms Markov process
- Bootstrap calibrates control limits to the ACTUAL in-control distribution → no parametric assumptions needed
- Robust against: multimodal, skewed, heavy-tailed distributions (all characteristics of trade returns)
- When normality is wrong: CUSUM either signals too early (false alarms) or too late (missed decay) → this fixes both
- CUSUM: C_n = max(C_{n-1} + X_n - k, 0); signal when C_n > h(T_n) [sequential limit, not fixed h]

**What we take:**
- Trade returns are NOT Normal (fat tails, skewness) → standard CUSUM will give WRONG false alarm rates
- Bootstrap-based control limits from Captain's own in-control trade data → correctly calibrated ARL
- Sequential limits conditioned on sprint length → more precise than single control limit
- For Captain (Offline): estimate in-control distribution from first N validated trades → bootstrap CUSUM limits
- Complement to BOCPD: CUSUM detects shifts in MEAN (edge decay); BOCPD detects general distributional changes
- Two-sided CUSUM: detect BOTH upward shifts (strategy improves? unlikely) and downward shifts (strategy decays)

---

## Paper 228 — Tsaknaki (PhD Thesis 2024/2025): Advances in BOCPD and Robust Kelly Investing (140pp) — THE BRIDGE

**What it proves:**
- BRIDGES change-point detection (Part I) and Kelly investing under model risk (Part II)

**Part I — BOCPD with Time-Varying Parameters:**
- Standard BOCPD assumes INDEPENDENCE within regimes → VIOLATED in trading data (autocorrelation, heteroskedasticity)
- MBO(q): Bayesian autoregressive online CPD that handles AUTOCORRELATION within regimes
- Score-Driven MBO(1): parameters ADAPT within regimes via score-driven updates → handles time-varying volatility
- Applied to order flow and market impact in financial markets (published Quantitative Finance 2024)
- Can detect order flow regime shifts and predict market impact changes ONLINE

**Part II — Kelly Criterion with Model Risk:**
- KO/UKO strategies: Kelly with OPTIONS for model risk hedging
- Convex combination of strategies under distributional model risk → robust to parameter misspecification
- Dynamic arbitrage strategies in presence of model risk
- When changepoint detected (Part I) → immediately triggers re-evaluation of Kelly parameters (Part II)

**What we take:**
- Standard BOCPD is INSUFFICIENT for trading data → must extend to handle autocorrelation (MBO model)
- Score-driven adaptation within regimes → captures time-varying volatility without declaring a new regime
- THE explicit connection: changepoint detection triggers Kelly re-evaluation → this is EXACTLY Captain's architecture
- Order flow regime detection → directly applicable to AIM-05 activation and AIM-03 GEX monitoring
- Model risk in Kelly → connects to Paper 218 (robust Kelly) and Paper 217 (shrinkage)

---

### System 3 Design Conclusions

**1. BOCPD is THE Primary Decay Detection Algorithm:**
- Online, exact posterior over run length → at each day, Captain knows P(changepoint | history) (Paper 231)
- When P(changepoint) exceeds threshold → trigger Level 2 (sizing reduction + alert) or Level 3 (strategy re-evaluation)
- Apply SEPARATELY to each monitoring stream: trade P&L, individual AIM accuracy, regime features
- Probabilistic output (not binary) → Captain can GRADE the severity of decay

**2. Distribution-Free CUSUM for Non-Normal Returns:**
- Trade returns have fat tails and skewness → standard CUSUM gives wrong false alarm rates (Paper 232)
- Bootstrap-based sequential control limits → calibrated to ACTUAL return distribution
- Sprint length conditioning → more precise than single control limit
- Complementary to BOCPD: CUSUM detects mean shifts (edge decay); BOCPD detects any distributional change

**3. Extended BOCPD for Trading Data:**
- Standard BOCPD assumes independence → trading data has autocorrelation and heteroskedasticity (Paper 228)
- MBO(q) extends BOCPD to autoregressive dynamics within regimes
- Score-driven variant handles time-varying volatility within regime → doesn't false-alarm on vol changes
- Applied to order flow and market impact → validated in financial markets

**4. Bridge to Kelly Re-evaluation:**
- Changepoint detection (System 3) → triggers Kelly parameter re-evaluation (System 2)
- THIS IS Captain's core feedback loop: monitor → detect → re-evaluate → adapt
- Paper 228 makes this connection EXPLICIT in a single framework

**5. Implementation Architecture:**
```
# Captain (Offline) decay monitoring:

# Stream 1: Overall trade P&L
bocpd_pnl = BOCPD_MBO(trade_pnl_stream, autoregressive_order=1)
cusum_pnl = BootstrapCUSUM(trade_pnl_stream, in_control_data=validated_trades)

# Stream 2: Per-AIM accuracy  
for aim in AIMs:
    bocpd_aim[aim] = BOCPD(aim.prediction_accuracy_stream)

# Daily update:
for each new trade outcome:
    bocpd_pnl.update(trade_pnl)
    cusum_pnl.update(trade_pnl)
    
    # Check for decay
    if bocpd_pnl.changepoint_probability > 0.8:
        trigger_level_2("BOCPD: strategy decay detected", severity=bocpd_pnl.cp_prob)
    if cusum_pnl.statistic > cusum_pnl.control_limit:
        trigger_level_2("CUSUM: mean shift detected in P&L")
    
    # Check per-AIM
    for aim in AIMs:
        if bocpd_aim[aim].changepoint_probability > 0.7:
            flag_aim_degradation(aim)
            reduce_aim_weight_via_DMA(aim)  # System 1 connection

# Level 3 trigger: if sustained decay (BOCPD cp_prob > 0.9 for 5+ days):
    trigger_level_3()  # Autonomous Programs 1/2 re-run + AIM-14 search
    recalculate_kelly_parameters()  # System 2 connection
```

**6. Cross-references:**
- System 1 (DMA): when BOCPD flags AIM degradation → DMA automatically reduces AIM weight
- System 2 (Kelly): changepoint triggers Kelly parameter re-evaluation → blended Kelly recomputed
- System 4a (Concept Drift): BOCPD IS a concept drift detector; CUSUM detects mean shifts; both complementary
- AIM-11 (Regime Warning): VIX-based early warning detects regime TRANSITIONS; BOCPD/CUSUM detect strategy DECAY within a regime
- AIM-13 (Sensitivity): PBO/DSR validate that strategies are genuine; BOCPD/CUSUM monitor that genuine strategies haven't degraded
- Captain Tiered Autonomy: Level 1 (retrain schedule) → automatic. Level 2 (sizing reduction + alert) → BOCPD/CUSUM trigger. Level 3 (strategy re-evaluation) → sustained decay trigger.

---

## System 4a: Online Learning and Concept Drift

## Paper 190 — Idrees et al. (2020): HDWM — Heterogeneous Dynamic Weighted Majority (Knowledge-Based Systems)

**What it proves:**
- The BEST TYPE of predictive model CHANGES OVER TIME in non-stationary environments
- HDWM: heterogeneous ensemble that intelligently SWITCHES between different model types as concept drift occurs
- "Seed" learners of different types maintain ensemble DIVERSITY (prevents collapse to homogeneous ensemble)
- Significantly outperforms standard WMA in non-stationary environments
- Outperforms homogeneous DWM especially with RECURRING concept drifts (market regimes recur!)
- Active approaches detect drift explicitly; passive approaches use weighted ensembles → HDWM combines both

**What we take:**
- Captain's 15 AIMs = heterogeneous ensemble. Different AIM "types" (options-based, flow-based, macro-based, etc.)
- HDWM architecture: maintain seed AIMs of each type; dynamically weight; allow best type to change
- Recurring drift handling is critical → market regimes recur (low-vol → high-vol → low-vol)
- The system should never collapse to using only one AIM type — diversity is essential for robustness

---

## Paper 192 — Yu et al. (2024): OBAL — Online Boosting Adaptive Learning for Multistream Classification (AAAI-24)

**What it proves:**
- Handles MULTIPLE data streams with ASYNCHRONOUS concept drift (different streams drift at different times)
- Dual-phase: (1) AdaCOSA initialises ensemble from archived source streams mitigating covariate shift; (2) Online GMM-based weighting for asynchronous drift
- Adaptive re-weighting strategy learns DYNAMIC CORRELATIONS among streams
- Prevents NEGATIVE TRANSFER from irrelevant/degraded sources
- Significantly improves predictive performance and stability of target stream

**What we take:**
- Captain receives 15 AIM "streams" that drift INDEPENDENTLY → OBAL-type architecture handles asynchronous degradation
- When one AIM (say AIM-07 COT) drifts (structural break in COT relationships) while others remain stable, OBAL isolates and down-weights the drifting stream without affecting the rest
- Negative transfer prevention → when an AIM becomes irrelevant, its contribution is automatically suppressed
- GMM-based weighting mechanism → flexible, handles multimodal distributions of AIM output quality

---

## Paper 189 — Malialis et al. (2020): AREBA — Online Learning with Adaptive Rebalancing (IEEE TNNLS)

**What it proves:**
- Addresses the COMBINED challenges of concept drift + class imbalance in ONLINE learning
- AREBA selectively includes a SUBSET of examples, maintaining class balance while adapting to drift
- Significantly outperforms alternatives in BOTH learning speed and learning quality
- One of very few studying online imbalance under EACH drift type independently (sudden, gradual, incremental, recurring)
- Desired properties: learn new knowledge, preserve relevant old knowledge, high performance on both classes, fast operation, fixed storage

**What we take:**
- In trading: class imbalance = rare but important events (crash days, extreme moves, regime transitions)
- AREBA ensures the system doesn't "forget" rare patterns even as common patterns dominate training
- For Captain: the adaptive rebalancing mechanism prevents over-fitting to calm market conditions while losing crash sensitivity
- Each drift type requires different adaptation → Captain must identify WHICH type of drift is occurring

---

## Paper 191 — Bhattacharya (2022): Concept Drift Detection via AutoEncoder + ADWIN (Master thesis)

**What it proves:**
- AutoEncoder-based Drift Detector (AEDD): detects drift WITHOUT access to true labels (unsupervised)
- Combines autoencoder reconstruction error with ADWIN for structural change detection
- Outperforms state-of-the-art alternatives on real-world datasets with induced drift
- Key insight: when the autoencoder's reconstruction error increases, the input distribution has changed → drift detected

**What we take:**
- In trading: "true labels" (whether trade was correct) arrive with DELAY → can't wait for P&L to detect drift
- AutoEncoder reconstruction error provides REAL-TIME, label-free drift detection
- ADWIN monitors reconstruction error stream for structural changes → triggers retraining
- For Captain: train autoencoder on market features during stable period → monitor reconstruction error daily → spike = concept drift in progress

---

## Paper 193 — Palli et al. (2024): Online ML from Non-stationary Streams — Systematic Review (JICT)

**What it proves:**
- Systematic review: 35 core papers from 1,110 studies on concept drift + class imbalance in non-stationary streams
- Concept detection: separate mechanism (drift detector) in parallel with classifier
- Concept adaptation: update classifier or train new one to replace old
- OPEN PROBLEMS: multiple drift types simultaneously, dynamic class imbalance ratio, multi-class imbalance with drift
- Online (instance-by-instance) vs. batch (chunk-based) processing architectures have different design requirements

**What we take:**
- Captain architecture should separate DETECTION (drift detectors per AIM) from ADAPTATION (retraining/reweighting)
- Multiple drift types can co-occur → different AIMs may experience different drift types simultaneously
- Online (daily) processing for AIM weight updates; batch (weekly/monthly) for AIM model retraining
- Class imbalance is an ongoing challenge → rare market events must be over-weighted in training

---

### System 4a Design Conclusions

**1. HDWM is the Architecture Blueprint:**
- Captain's AIMs = heterogeneous ensemble of different model types
- Maintain "seed" AIMs of each type → ensures diversity persists even when some AIMs underperform
- Dynamic weighting allows best AIM types to dominate, changes with regime
- Handles RECURRING drifts (market regimes recur) — critical for trading

**2. Asynchronous Drift Handling (OBAL):**
- 15 AIMs drift independently → one AIM may degrade while others remain valid
- OBAL-type mechanism isolates and down-weights drifting streams
- Prevents negative transfer → degraded AIM doesn't contaminate overall signal
- Dynamic correlation learning → adjusts how AIMs interact as markets evolve

**3. Rare Event Preservation (AREBA):**
- Crash days, extreme moves, regime transitions are the minority class but most important
- Adaptive rebalancing ensures Captain retains sensitivity to rare events
- Without this: system over-fits to calm conditions, fails during stress

**4. Unsupervised Drift Detection:**
- AutoEncoder reconstruction error provides REAL-TIME, label-free drift detection
- Don't wait for trade P&L to know something has changed — detect from feature space
- ADWIN on reconstruction error → automatic structural change detection
- Triggers Captain (Offline) retraining when drift detected

**5. Architecture: Online + Batch Hybrid:**
- Daily (Online): update AIM weights via DMA/HDWM; detect drift via autoencoder/ADWIN; generate trading decisions
- Weekly/Monthly (Offline): retrain degraded AIM models; run AREBA-type rebalancing; update ensemble composition

**6. Cross-references:**
- System 1 (DMA): DMA provides the weighting mechanism; HDWM provides the architecture
- System 3 (SPRT/CUSUM): complementary drift detection; SPRT for performance monitoring, autoencoder for feature monitoring
- AIM-13 (Sensitivity): parameter sensitivity → different mechanism from concept drift, but both trigger retraining
- AIM-11 (Regime Warning): regime transition IS a type of concept drift → same detection/adaptation framework applies

---

## System 4b: RL and Bandit Methods

## Paper 200 — Lam (2025): Ensembling Portfolio Strategies for Long-Term Investments

**What it proves:**
- Distribution-free preference framework: combinatorial strategy EVENTUALLY EXCEEDS wealth of ALL component strategies
- No statistical assumptions on market data needed → robust to ANY market regime
- Works for any scale of component strategies (even INFINITE number)
- Tested over 27 years including major market events (dot-com, GFC, COVID)
- Accelerated variant significantly improves convergence speed
- Small Sharpe ratio tradeoff for guaranteed eventual dominance

**What we take:**
- Captain's ensemble of strategies/AIMs WILL eventually outperform any single component — guaranteed by theory
- The distribution-free nature means this works regardless of regime → no regime-specific tuning needed for the ensemble rule
- For Captain: treat each AIM-weighted strategy as a "component strategy" → apply this framework for long-term capital allocation
- The small Sharpe tradeoff vs. guaranteed dominance is the RIGHT trade for a persistent learning system

---

## Paper 204 — Deb, Ghavamzadeh & Banerjee (2025): Thompson Sampling for Constrained Bandits (RLJ 2025)

**What it proves:**
- Thompson Sampling (TS) extended to TWO constrained bandit frameworks:
  - CBwK (Contextual Bandits with Knapsacks): maximise reward subject to RESOURCE CONSTRAINTS
  - CCB (Conservative Bandits): performance must remain above (1-α) × baseline at ALL times
- TS provides high-probability regret bounds for both constrained settings
- TS often outperforms UCB empirically → now proven to work under constraints too
- Resource constraints: budget limits, consumption vectors
- Conservative constraint: learner never performs much worse than safe baseline

**What we take:**
- Captain DIRECTLY maps to CBwK: maximise cumulative P&L subject to TSM constraints (MDD, MLL, account budget)
- Captain ALSO maps to CCB: performance must remain above baseline (e.g., prop firm minimum return requirements)
- Thompson Sampling = the algorithm for Captain's daily action selection under constraints
- At each decision point: observe context (AIM outputs, regime state) → select action (sizing) → receive reward (P&L) → consume resource (risk budget)
- The conservative constraint ensures Captain NEVER risks the account for exploration — exploration is bounded

---

## Paper 197 — Ackermann, Osa & Sugiyama (2024): Offline RL from Datasets with Structured Non-Stationarity (RLC 2024)

**What it proves:**
- Addresses offline RL where transition/reward functions GRADUALLY CHANGE between episodes but stay constant within
- Uses Contrastive Predictive Coding (CPC) to IDENTIFY non-stationarity in the offline dataset
- Learns a representation of the "hidden parameter" (regime/market state) → predicts it during evaluation
- Achieves oracle performance; outperforms standard offline RL baselines
- Dynamic-Parameter MDP formulation: hidden parameter constant within episode, evolves between episodes

**What we take:**
- Captain's "episodes" = trading days; market parameters (regime, volatility state, correlation structure) evolve between days
- CPC identifies the regime/state from historical trade data → Captain can infer current state without explicit regime classification
- This provides an ALTERNATIVE to the explicit regime classification in Program 2 — learned implicitly from data
- For Captain (Offline): train policy on historical dataset accounting for non-stationarity → deploy online with state prediction
- Complements System 4a: structured non-stationarity is a specific form of concept drift with exploitable structure

---

## Paper 205 — Mania, Guy & Recht (2018): Simple Random Search for RL (UC Berkeley)

**What it proves:**
- Simple random search MATCHES state-of-the-art sample efficiency on RL benchmarks
- Static LINEAR policies achieve competitive performance — no neural networks needed
- Augmented Random Search (ARS): 15x+ more computationally efficient than Evolution Strategies
- Three simple features: reward scaling, state normalisation, direction pruning
- Reproducibility crisis: many RL methods not robust to hyperparameters, random seeds, implementations
- Over 100 random seeds → HIGH VARIABILITY in benchmark performance → common evaluations are inadequate

**What we take:**
- FUNDAMENTAL design principle: START SIMPLE, add complexity only when validated
- Captain should begin with LINEAR combination rules for AIM outputs, not neural networks
- If a simple weighted average of AIM modifiers works (DMA from System 1), don't overcomplicate
- 15x computational efficiency matters for daily operational system → simple methods are preferable
- Reproducibility: evaluate over MANY seeds/scenarios (connects to AIM-13 PBO testing)
- The "complicated RL is always better" belief is FALSE → simple methods are often equally effective

---

### System 4b Design Conclusions

**1. Constrained Bandits for Captain Decision-Making:**
- Captain = CBwK agent: maximise cumulative P&L under resource constraints (TSM: MDD, MLL, risk budget)
- Captain = CCB agent: performance must remain above (1-α) × baseline (prop firm requirements)
- Thompson Sampling is the algorithm of choice (proven regret bounds + empirical superiority)
- Context = AIM outputs + regime state; Action = sizing; Reward = P&L; Resource consumption = risk/drawdown

**2. Distribution-Free Strategy Ensemble:**
- Combinatorial strategy GUARANTEED to eventually exceed all component strategies' wealth
- No market distribution assumptions → works regardless of regime
- Small Sharpe tradeoff for theoretical guarantee is acceptable for a persistent system

**3. Offline RL with Structured Non-Stationarity:**
- Market parameters evolve between days but stable within day → Dynamic-Parameter MDP
- CPC learns regime representation from historical data → alternative to explicit regime classification
- Train offline → deploy online with state prediction

**4. Simplicity Principle:**
- Linear policies match complex RL → START with DMA + linear AIM combination
- Simple methods are 15x+ more computationally efficient
- Add complexity ONLY when simple methods are provably insufficient
- Evaluate over MANY scenarios (AIM-13 PBO requirement)

**5. Implementation Priority:**
```
# Captain decision architecture (simplicity-first):

Level 0: DMA-weighted average of AIM modifiers (System 1) → BASELINE
Level 1: Add Thompson Sampling for action selection under constraints (Paper 204)
Level 2: Add offline RL regime inference (Paper 197) if Level 0-1 insufficient
Level 3: Add full ensemble guarantee (Paper 200) for long-term capital growth

# Don't implement Level N+1 until Level N is exhausted
```

**6. Cross-references:**
- System 1 (DMA): DMA is the "Level 0" simple aggregation method → start here
- System 2 (Kelly): Kelly sizing provides the unconstrained optimum; Thompson Sampling adds constraints
- System 3 (SPRT/CUSUM): detects when the current policy needs updating
- System 4a (Concept Drift): HDWM handles model-type changes; Paper 197 handles structured non-stationarity
- AIM-13 (Sensitivity): reproducibility requirement → evaluate over many seeds (Paper 205)

---

## System 4c: Ensemble Meta-Learning

## Paper 211 — Mu & Lin (2025): Comprehensive Survey of Mixture-of-Experts (MoE)

**What it proves:**
- MoE = "divide and conquer" architecture that dynamically selects and activates MOST RELEVANT sub-models per input
- Basic components: gating functions (which experts to use), expert networks (specialised sub-models), routing mechanisms (how to direct inputs), training strategies, system design
- Covers MoE across ALL relevant ML paradigms: continual learning, meta-learning, multi-task learning, RL, federated learning
- Selective activation: NOT all experts active for every input → efficiency + specialisation
- Switch Transformer achieves 7x pre-training speedup → MoE scales better than dense models
- Expert specialisation: each expert handles different data types or conditions → avoids conflicting knowledge

**What we take:**
- Captain = MoE system. 15 AIMs = 15 "experts." Gating function = meta-learning layer (DMA/HDWM)
- NOT all AIMs are relevant every day → gating function selects which AIMs to activate based on current market conditions
- Each AIM SPECIALISES: AIM-01 (options-vol), AIM-04 (pre-market), AIM-07 (positioning), AIM-09 (cross-asset) → different signal types
- MoE in RL (Section III-D): directly applicable to Captain using RL for sizing decisions under different regimes
- MoE in continual learning (Section III-A): handles the non-stationarity problem where expert relevance changes over time
- Expert routing: "top-k" routing (activate only top-k experts) → Captain activates only the k most relevant AIMs per day

---

## Paper 206 — Gama et al. (2014): A Survey on Concept Drift Adaptation (2488 citations, 17773 downloads) — FOUNDATIONAL

**What it proves:**
- THE definitive survey on concept drift in online learning. 2488 citations.
- Concept drift = the relation between input data and target variable CHANGES OVER TIME
- Drift types: sudden (abrupt change), gradual (smooth transition), incremental (slow), recurring (cyclical), reoccurring (old concepts return)
- Adaptation strategies: (1) instance selection (windowing, weighting), (2) model management (ensemble: add/remove/reweight)
- Active approaches: explicitly DETECT drift → trigger adaptation. Passive approaches: continuously adapt via ensemble weighting
- Evaluation: prequential (test-then-train) error, Kappa statistic for streaming, significance tests adapted for non-i.i.d. data
- Applications: spam filtering, energy management, fraud detection, network intrusion, manufacturing quality

**What we take:**
- TRADING IS CONCEPT DRIFT: the relationship between AIM signals and profitable trades CHANGES with market regimes
- Drift types in trading: sudden (flash crash, policy shock), gradual (regime transition), recurring (seasonal, business cycle)
- Captain architecture = HYBRID: active detection (SPRT/CUSUM from System 3) + passive adaptation (DMA ensemble from System 1)
- Prequential evaluation = trade-by-trade P&L tracking → naturally suited to Captain's daily evaluation
- Recurring drift handling is CRITICAL → market regimes recur → Captain must recognise and recall old concepts (HDWM seed learners from System 4a)

---

## Paper 209 — Dormann et al. (2018): Model Averaging in Ecology — Mathematical Foundations

**What it proves:**
- Mathematical foundations: model-averaged prediction error depends on each model's BIAS, VARIANCE, COVARIANCE between models, and WEIGHT UNCERTAINTY
- Model averaging is MOST useful when: (1) predictive error dominated by VARIANCE (not bias), (2) covariance between models is LOW
- For NOISY data → both conditions typically met → model averaging is beneficial (finance = noisy data!)
- CRITICAL INSIGHT: estimated weights may NOT outperform EQUAL WEIGHTS when model set is reasonable
- When many INADEQUATE models: estimated weights superior. When model set is reasonable: equal weights match
- Weight estimation creates ADDITIONAL uncertainty → the cure can be worse than the disease
- Confidence intervals for model-averaged predictions seldom achieve nominal coverage → don't trust uncertainty estimates too precisely
- Cross-validation is recommended for reliable uncertainty quantification

**What we take:**
- Captain should START with EQUAL AIM weights → DMA learns better weights over time
- The equal-weights startup is NOT lazy — it is THEORETICALLY JUSTIFIED for reasonable model sets
- Finance (noisy, variance-dominated) meets BOTH conditions for model averaging to be beneficial
- Low covariance between AIMs is DESIRABLE → diversified AIM types (options, flow, macro, cross-asset) ensure low correlation
- Weight uncertainty is real → don't over-fit the meta-learning → forgetting factor in DMA provides regularisation
- Cross-validation (expanding window) for Captain's meta-learning evaluation, not just in-sample fit
- Confidence intervals from model averaging are unreliable → don't take Captain's probability estimates as precise

---

### System 4c Design Conclusions

**1. Captain = Mixture-of-Experts Architecture:**
- 15 AIMs = 15 specialised experts (options-vol, pre-market, positioning, cross-asset, calendar, etc.)
- Gating function = DMA-based meta-learning layer that routes inputs to relevant experts
- Selective activation: not all 15 AIMs active every day → gating determines which are relevant
- Expert specialisation prevents conflicting knowledge → each AIM owns its domain
- MoE supports continual learning (regimes change) and RL (sizing under constraints)

**2. Concept Drift is THE Fundamental Challenge:**
- Trading IS concept drift: AIM signal → profitable trade relationship changes with regimes
- Drift types: sudden (flash crash), gradual (regime transition), recurring (seasonal cycles)
- Hybrid detection + adaptation: active (SPRT/CUSUM) + passive (DMA ensemble reweighting)
- Recurring drift = market regimes return → Captain must RECALL old concepts, not just learn new ones

**3. Start with Equal Weights — Theoretically Justified:**
- Equal weights match estimated weights for reasonable model sets (Paper 209)
- Finance (noisy data) meets conditions for model averaging to be beneficial
- Low covariance between AIM types (diversified signals) is CRITICAL → design AIMs to be diverse
- DMA forgetting factor provides regularisation against weight over-fitting
- Don't trust Captain's probability estimates as precise → weight uncertainty is real

**4. The Complete Captain Learning Architecture:**
```
STARTUP:
    Equal weights for all 15 AIMs (theoretically justified)

DAILY (Captain Online):
    1. Collect AIM outputs → each AIM produces modifier ∈ [0.5, 1.5]
    2. MoE gating: DMA determines which AIMs are active (inclusion probability > threshold)
    3. Weighted aggregation: DMA model probabilities × AIM modifiers → combined modifier
    4. Apply to Kelly sizing under TSM constraints (Thompson Sampling from System 4b)
    5. Execute trade

WEEKLY (Captain Offline — light):
    6. Update DMA model probabilities based on trade P&L feedback
    7. Monitor each AIM via ADWIN for concept drift (System 4a)
    8. Update prequential evaluation metrics

MONTHLY (Captain Offline — heavy):
    9. Run AIM-13 sensitivity scan (PBO, DSR)
    10. Check SPRT/CUSUM for strategy decay (System 3)
    11. If decay detected: trigger AIM-14 auto-expansion search (System 4b Level 3)
    12. Retrain individual AIM models as needed (AREBA rebalancing)
    13. Generate discretionary reports (RPT-01 through RPT-10)
```

**5. Cross-references:**
- System 1 (DMA): provides the gating/weighting mechanism
- System 2 (Kelly): provides the unconstrained optimal sizing; constraints from TSM
- System 3 (SPRT/CUSUM): active drift detection for strategy-level decay
- System 4a (HDWM/OBAL/AREBA): handles model-type switching, multistream drift, rare events
- System 4b (Thompson Sampling, ensemble guarantee): constrained action selection, simplicity principle
- AIM-13/14: sensitivity scanning and auto-expansion as maintenance modules
- All 15 AIMs: the specialised experts in the MoE architecture

---

*When all sections are filled, the extraction phase is complete and Program3.md can be built.*
