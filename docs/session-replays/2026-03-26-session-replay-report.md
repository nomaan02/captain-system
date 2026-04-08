# Captain Function — ORB Session Replay Report

**Date:** Thursday, March 26 2026
**Type:** Historical Simulation (READ-ONLY — no real trades placed)
**Data Source:** TopstepX REST API (1-minute OHLCV bars)
**Engine:** Captain Function ORB with Kelly Criterion sizing

---

## System Configuration

| Parameter | Value |
|-----------|-------|
| Account | TopstepX 150K Trading Combine (20319811) |
| Capital | $150,000 |
| Max Drawdown Limit | $4,500 |
| Daily Loss Limit | $2,250 |
| MDD Daily Budget | $225/day ($4,500 / 20-day divisor) |
| Position Limit | 5 simultaneous |
| Max Contracts (TSM) | 15 per asset |
| Strategy | Opening Range Breakout (5-min OR) |
| TP Multiple | 0.70x OR range (2:1 reward:risk) |
| SL Multiple | 0.35x OR range |
| Sizing | Kelly Criterion, regime-blended, shrinkage-adjusted |
| Risk Goal | PASS_EVAL (0.7x Kelly reduction) |

---

## Pipeline Flow

```
1. MARKET DATA        TopstepX 1-min bars fetched via REST API for 10 futures contracts
                      across 4 session types (NY, London, APAC, NY Pre-Market)

2. OR FORMATION       First 5 minutes of each session define the Opening Range
                      OR High = max(highs), OR Low = min(lows) of those 5 bars

3. BREAKOUT           After OR closes, scan bars for first break:
                      Price > OR High  -->  LONG breakout (entry = OR High)
                      Price < OR Low   -->  SHORT breakout (entry = OR Low)

4. TP / SL            TP = entry +/- (0.70 x OR range)    (take profit)
                      SL = entry -/+ (0.35 x OR range)    (stop loss)
                      Reward:Risk ratio = 2:1

5. KELLY SIZING       For each asset:
                      a. Blend Kelly fractions across LOW_VOL and HIGH_VOL regimes
                         (equal 0.5/0.5 weighting for REGIME_NEUTRAL assets)
                      b. Apply shrinkage factor (~0.97, from estimation uncertainty)
                      c. Apply PASS_EVAL risk goal multiplier (0.7x)
                      d. Compute raw contracts = Kelly x Capital / Risk-per-contract
                      e. Risk-per-contract from EWMA avg_loss (in dollars)

6. RISK GATES         4-way minimum applied to each asset:
                      a. Raw Kelly contracts
                      b. MDD daily budget cap = floor($225 / SL-risk-per-contract)
                      c. Daily loss cap = floor($2,250 / SL-risk-per-contract)
                      d. TSM max contracts (15)
                      Final = min(a, b, c, d), then max 5 positions total
```

---

## Asset Universe

| Asset | Name | Session | OR Window (ET) | Point Value | Tick Size |
|-------|------|---------|----------------|-------------|-----------|
| ES | E-mini S&P 500 | NY | 09:30-09:35 | $50.00 | 0.25 |
| MES | Micro E-mini S&P 500 | NY | 09:30-09:35 | $5.00 | 0.25 |
| NQ | E-mini Nasdaq-100 | NY | 09:30-09:35 | $20.00 | 0.25 |
| MNQ | Micro E-mini Nasdaq-100 | NY | 09:30-09:35 | $2.00 | 0.25 |
| M2K | Micro E-mini Russell 2000 | NY | 09:30-09:35 | $5.00 | 0.10 |
| MYM | Micro E-mini Dow Jones | NY | 09:30-09:35 | $0.50 | 1.00 |
| NKD | Nikkei 225 | APAC | 18:00-18:05 | $5.00 | 5.00 |
| MGC | Micro Gold | London | 03:00-03:05 | $10.00 | 0.10 |
| ZB | 30-Year Treasury | NY Pre | 06:00-06:05 | $1,000.00 | 0.03125 |
| ZN | 10-Year Treasury | NY Pre | 06:00-06:05 | $1,000.00 | 0.015625 |

---

## Session Results — Trades Executed

### MGC (Micro Gold) — London Session, 03:00 ET

| Step | Detail |
|------|--------|
| OR Window | 4447.30 — 4456.70 (range = 9.40 pts) |
| OR Bars | 5 bars, 03:00-03:04 ET |
| Breakout | SHORT at 03:05 ET |
| Entry Price | 4447.30 (OR Low) |
| TP Target | 4440.72 (entry - 0.70 x 9.40 = entry - 6.58) |
| SL Target | 4450.59 (entry + 0.35 x 9.40 = entry + 3.29) |
| Exit | **TP HIT** at 03:08 ET @ 4440.72 |
| Kelly Fraction | 0.0637 |
| Risk/Contract | $50.73 (EWMA avg_loss) |
| MDD Cap | 4 contracts (floor($225 / $50)) |
| **Contracts** | **4** |
| **PnL** | **4 x +$65.80 = +$263.20** |

---

### M2K (Micro E-mini Russell 2000) — NY Session, 09:30 ET

| Step | Detail |
|------|--------|
| OR Window | 2521.10 — 2529.10 (range = 8.00 pts) |
| OR Bars | 5 bars, 09:30-09:34 ET |
| Breakout | LONG at 09:43 ET |
| Entry Price | 2529.10 (OR High) |
| TP Target | 2534.70 (entry + 0.70 x 8.00 = entry + 5.60) |
| SL Target | 2526.30 (entry - 0.35 x 8.00 = entry - 2.80) |
| Exit | **TP HIT** at 09:44 ET @ 2534.70 |
| Kelly Fraction | 0.0875 |
| Risk/Contract | $34.23 (EWMA avg_loss) |
| MDD Cap | 9 contracts (floor($225 / $25)) |
| **Contracts** | **9** |
| **PnL** | **9 x +$28.00 = +$252.00** |

---

### MYM (Micro E-mini Dow Jones) — NY Session, 09:30 ET

| Step | Detail |
|------|--------|
| OR Window | 46425.00 — 46544.00 (range = 119.00 pts) |
| OR Bars | 5 bars, 09:30-09:34 ET |
| Breakout | LONG at 09:42 ET |
| Entry Price | 46544.00 (OR High) |
| TP Target | 46627.30 (entry + 0.70 x 119.00 = entry + 83.30) |
| SL Target | 46502.35 (entry - 0.35 x 119.00 = entry - 41.65) |
| Exit | **TP HIT** at 09:44 ET @ 46627.30 |
| Kelly Fraction | 0.0850 |
| Risk/Contract | $49.83 (EWMA avg_loss) |
| MDD Cap | 4 contracts (floor($225 / $50)) |
| **Contracts** | **4** |
| **PnL** | **4 x +$41.65 = +$166.60** |

---

### ES (E-mini S&P 500) — NY Session, 09:30 ET

| Step | Detail |
|------|--------|
| OR Window | 6582.75 — 6594.00 (range = 11.25 pts) |
| OR Bars | 5 bars, 09:30-09:34 ET |
| Breakout | SHORT at 09:39 ET |
| Entry Price | 6582.75 (OR Low) |
| TP Target | 6574.88 (entry - 0.70 x 11.25 = entry - 7.88) |
| SL Target | 6586.69 (entry + 0.35 x 11.25 = entry + 3.94) |
| Exit | **SL HIT** at 09:40 ET @ 6586.69 |
| Kelly Fraction | 0.0332 |
| Risk/Contract | $192.17 (EWMA avg_loss) |
| MDD Cap | 1 contract (floor($225 / $200)) |
| **Contracts** | **1** |
| **PnL** | **1 x -$196.88 = -$196.88** |

---

### MNQ (Micro E-mini Nasdaq-100) — NY Session, 09:30 ET

| Step | Detail |
|------|--------|
| OR Window | 24087.50 — 24156.50 (range = 69.00 pts) |
| OR Bars | 5 bars, 09:30-09:34 ET |
| Breakout | SHORT at 09:38 ET |
| Entry Price | 24087.50 (OR Low) |
| TP Target | 24039.20 (entry - 0.70 x 69.00 = entry - 48.30) |
| SL Target | 24111.65 (entry + 0.35 x 69.00 = entry + 24.15) |
| Exit | **SL HIT** at 09:43 ET @ 24111.65 |
| Kelly Fraction | 0.0567 |
| Risk/Contract | $29.72 (EWMA avg_loss) |
| MDD Cap | 5 contracts (floor($225 / $30)) |
| **Contracts** | **5** |
| **PnL** | **5 x -$48.30 = -$241.50** |

---

## Assets Blocked by Risk Gates

These assets detected valid breakouts but were blocked because the MDD daily budget ($225) could not afford even 1 contract at their risk level.

| Asset | Session | OR Range | Direction | Risk/Contract | MDD Cap | Reason |
|-------|---------|----------|-----------|---------------|---------|--------|
| NQ | NY | 67.75 pts | SHORT | $293.92 | 0 | Risk > budget |
| NKD | APAC | 40.00 pts | SHORT | $510.79 | 0 | Risk > budget |
| ZB | NY Pre | 0.0625 pts | LONG | $355.87 | 0 | Risk > budget |
| ZN | NY Pre | 0.0312 pts | LONG | $118.71 | 0 | Risk > budget |
| MES | NY | 11.50 pts | SHORT | $19.02 | 11 | Excluded by position limit (max 5) |

---

## PnL Summary

| Asset | Direction | Entry | Exit | Reason | Contracts | PnL |
|-------|-----------|-------|------|--------|-----------|-----|
| MGC | SHORT | 4,447.30 | 4,440.72 | TP HIT | 4 | +$263.20 |
| M2K | LONG | 2,529.10 | 2,534.70 | TP HIT | 9 | +$252.00 |
| MYM | LONG | 46,544.00 | 46,627.30 | TP HIT | 4 | +$166.60 |
| ES | SHORT | 6,582.75 | 6,586.69 | SL HIT | 1 | -$196.88 |
| MNQ | SHORT | 24,087.50 | 24,111.65 | SL HIT | 5 | -$241.50 |
| **TOTAL** | | | | **5 trades, 23 contracts** | | **+$243.42** |

---

## Session Statistics

| Metric | Value |
|--------|-------|
| Trades Executed | 5 |
| Wins | 3 (MGC, M2K, MYM) |
| Losses | 2 (ES, MNQ) |
| Win Rate | 60% |
| Gross Profit | +$681.80 |
| Gross Loss | -$438.38 |
| Net PnL | **+$243.42** |
| Capital at Risk | $681.80 (0.45% of $150K) |
| Return on Capital | +0.16% |
| Max Drawdown Used | $438.38 of $4,500 (9.7%) |
| Daily Loss Used | $438.38 of $2,250 (19.5%) |
| Account Status | WITHIN ALL LIMITS |

---

## Simulation Caveats

This replay simulates the core ORB pipeline (OR formation, breakout detection, TP/SL, Kelly sizing, MDD/daily loss caps). The following live pipeline steps were **not included** in this simulation:

| Skipped Step | Pipeline Block | Effect |
|--------------|---------------|--------|
| VIX circuit breaker | Orchestrator | Halts all trading if VIX > 50 |
| Data Moderator | B1 | Price/volume validation, staleness checks |
| Regime classification | B2 | Dynamic LOW_VOL/HIGH_VOL probabilities (sim uses equal 50/50) |
| AIM aggregation | B3 | 6 adaptive modifiers per asset (sim uses neutral 1.0) |
| Correlation filtering | B5 | Would block ES+MES trading simultaneously (~99% correlated) |
| Quality gate | B5B | Minimum conviction threshold to trade |
| Circuit breaker L0-L6 | B5C | 7-layer safety checks (scaling, preemptive halt, basket expectancy, Sharpe) |
| Portfolio risk cap | B4 | Total risk across all positions capped at 10% of capital |
| HMM session allocation | B5 | Opportunity-weighted contract allocation across sessions |

With correlation filtering active, MES would have been excluded (same underlying as ES), removing the -$221.32 MES loss from the original 10-asset evaluation and potentially improving results.

---

## Kelly Sizing Detail

| Asset | LOW_VOL Kelly | HIGH_VOL Kelly | Blended | Shrinkage | After PASS_EVAL | Risk/Ct | Raw Cts | Final |
|-------|---------------|----------------|---------|-----------|-----------------|---------|---------|-------|
| MGC | 0.0496 | 0.0723 | 0.0610 | x0.973 | 0.0637 | $50.73 | 188 | **4** |
| M2K | 0.0682 | 0.0568 | 0.0625 | x0.971 | 0.0875 | $34.23 | 383 | **9** |
| MYM | 0.0696 | 0.0517 | 0.0607 | x0.972 | 0.0850 | $49.83 | 255 | **4** |
| ES | 0.0593 | 0.0380 | 0.0487 | x0.974 | 0.0332 | $192.17 | 25 | **1** |
| MNQ | 0.1058 | 0.0503 | 0.0781 | x0.975 | 0.0567 | $29.72 | 286 | **5** |

*"Final" column reflects the binding constraint (MDD cap in all cases except MNQ which hits MDD cap at 5).*

---

*Report generated by Captain Function Session Replay Engine*
*Data: TopstepX REST API | Sizing: QuestDB (D05 EWMA, D12 Kelly, D08 TSM, D16 Capital Silo)*
