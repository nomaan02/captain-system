# Captain Function — ORB Session Replay Report

**Date:** Monday, March 30 2026
**Type:** Historical Simulation (READ-ONLY — no real trades placed)
**Data Source:** TopstepX REST API (1-minute OHLCV bars)
**Engine:** Captain Function ORB with Kelly Criterion sizing

**Note:** The live system detected the session, ran the full pipeline (B1-B6), and generated correct signals at 09:35 ET. A direction-format bug in the Command auto-execute layer (`-1` integer vs `"SELL"` string) prevented order placement. The bug has been fixed and deployed for tomorrow's session.

---

## System Configuration

| Parameter | Value |
|-----------|-------|
| Account | TopstepX 150K Trading Combine (20319811) — PRACTICE |
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
1. MARKET DATA        TopstepX MarketStream (live WebSocket quotes, 10 contracts)

2. OR FORMATION       First 5 minutes of session (09:30:00–09:34:59 ET for NY)
                      OR High = max of all quote highs during window
                      OR Low  = min of all quote lows during window

3. BREAKOUT           After 09:35:00 ET, first quote that crosses:
                      Price > OR High  →  LONG breakout (entry = OR High)
                      Price < OR Low   →  SHORT breakout (entry = OR Low)

4. TP / SL            TP = entry ∓ (0.70 × OR range)    (take profit)
                      SL = entry ± (0.35 × OR range)    (stop loss)
                      Reward:Risk = 2:1

5. KELLY SIZING       Regime-blended Kelly × shrinkage × PASS_EVAL(0.7x)
                      Risk/contract from EWMA avg_loss (dollars)
                      4-way min: Kelly raw, MDD cap, daily cap, TSM max

6. RISK GATES         MDD daily budget ($225), daily loss limit ($2,250),
                      max 15 contracts, max 5 positions, correlation filter
```

---

## Asset Universe

| Asset | Name | Session | OR Window (ET) | Point Value | Tick Size |
|-------|------|---------|----------------|-------------|-----------|
| ES | E-mini S&P 500 | NY | 09:30–09:35 | $50.00 | 0.25 |
| MES | Micro E-mini S&P 500 | NY | 09:30–09:35 | $5.00 | 0.25 |
| NQ | E-mini Nasdaq-100 | NY | 09:30–09:35 | $20.00 | 0.25 |
| MNQ | Micro E-mini Nasdaq-100 | NY | 09:30–09:35 | $2.00 | 0.25 |
| M2K | Micro E-mini Russell 2000 | NY | 09:30–09:35 | $5.00 | 0.10 |
| MYM | Micro E-mini Dow Jones | NY | 09:30–09:35 | $0.50 | 1.00 |
| NKD | Nikkei 225 | APAC | 18:00–18:05 | $5.00 | 5.00 |
| MGC | Micro Gold | London | 03:00–03:05 | $10.00 | 0.10 |
| ZB | 30-Year Treasury | NY Pre | 06:00–06:05 | $1,000.00 | 0.03125 |
| ZN | 10-Year Treasury | NY Pre | 06:00–06:05 | $1,000.00 | 0.015625 |

---

## Live Pipeline Confirmation

The following was captured from the live system logs at session time:

```
09:28:00  Session NY (1) opening — beginning evaluation
09:28:06  ON-B1: 9 assets eligible, 124 features computed
09:28:06  ON-B2: Regime probabilities computed for 9 assets (9 neutral)
09:28:06  ON-B3: AIM aggregation complete for 9 assets (9 with active AIMs)
09:28:06  ON-B4: Kelly sizing for user primary_user (1 accounts, 9 assets)
09:28:06  ON-B5: Trade selection: 5/9 assets selected
09:28:06  ON-B5B: Quality gate: 5 recommended, 0 below threshold
09:28:06  Phase A complete — 9 assets registered for OR tracking

09:30:00  OR FORMING: ES (6467.75), MES (6467.75), NQ (23509.75),
          MNQ (23509.75), M2K (2485.90), MYM (45828.00)

09:35:00  OR COMPLETE: all 6 NY assets (thousands of ticks each)
09:35:00  BREAKOUT SHORT: M2K, MES, NQ, ES, MNQ, MYM (all within 5 seconds)
09:35:00  Phase B: B6 signals generated and published to Redis
```

---

## Session Results — Trades Executed

### ES (E-mini S&P 500) — NY Session, 09:30 ET

| Step | Detail |
|------|--------|
| OR Window | 6454.75 — 6471.25 (range = 16.50 pts) |
| OR Ticks | 3,544 quotes during 5-min window |
| Breakout | **SHORT** at 09:35 ET |
| Entry Price | 6454.75 (OR Low) |
| TP Target | 6443.20 (entry − 0.70 × 16.50 = entry − 11.55) |
| SL Target | 6460.53 (entry + 0.35 × 16.50 = entry + 5.78) |
| Exit | **TP HIT** at 09:40 ET @ 6443.20 |
| Kelly Fraction | 0.0332 |
| Risk/Contract | $192.17 (EWMA avg_loss) |
| MDD Cap | 1 contract (floor($225 / $200)) |
| **Contracts** | **1** |
| **PnL** | **1 × +$577.50 = +$577.50** |

---

### MES (Micro E-mini S&P 500) — NY Session, 09:30 ET

| Step | Detail |
|------|--------|
| OR Window | 6455.00 — 6471.00 (range = 16.00 pts) |
| OR Ticks | 3,679 quotes during 5-min window |
| Breakout | **SHORT** at 09:35 ET |
| Entry Price | 6455.00 (OR Low) |
| TP Target | 6443.80 (entry − 0.70 × 16.00 = entry − 11.20) |
| SL Target | 6460.60 (entry + 0.35 × 16.00 = entry + 5.60) |
| Exit | **TP HIT** at 09:40 ET @ 6443.80 |
| Kelly Fraction | 0.1015 |
| Risk/Contract | $19.02 (EWMA avg_loss) |
| MDD Cap | 11 contracts (floor($225 / $20)) |
| **Contracts** | **11** |
| **PnL** | **11 × +$56.00 = +$616.00** |

---

### MNQ (Micro E-mini Nasdaq-100) — NY Session, 09:30 ET

| Step | Detail |
|------|--------|
| OR Window | 23457.00 — 23538.00 (range = 81.00 pts) |
| OR Ticks | 5,040 quotes during 5-min window |
| Breakout | **SHORT** at 09:35 ET |
| Entry Price | 23457.00 (OR Low) |
| TP Target | 23400.30 (entry − 0.70 × 81.00 = entry − 56.70) |
| SL Target | 23485.35 (entry + 0.35 × 81.00 = entry + 28.35) |
| Exit | **TP HIT** at 09:40 ET @ 23400.30 |
| Kelly Fraction | 0.0567 |
| Risk/Contract | $29.72 (EWMA avg_loss) |
| MDD Cap | 5 contracts (floor($225 / $30)) |
| **Contracts** | **5** |
| **PnL** | **5 × +$113.40 = +$567.00** |

---

### M2K (Micro E-mini Russell 2000) — NY Session, 09:30 ET

| Step | Detail |
|------|--------|
| OR Window | 2474.50 — 2486.00 (range = 11.50 pts) |
| OR Ticks | 1,552 quotes during 5-min window |
| Breakout | **SHORT** at 09:35 ET |
| Entry Price | 2474.50 (OR Low) |
| TP Target | 2466.45 (entry − 0.70 × 11.50 = entry − 8.05) |
| SL Target | 2478.53 (entry + 0.35 × 11.50 = entry + 4.03) |
| Exit | **TP HIT** at 09:40 ET @ 2466.45 |
| Kelly Fraction | 0.0875 |
| Risk/Contract | $34.23 (EWMA avg_loss) |
| MDD Cap | 9 contracts (floor($225 / $25)) |
| **Contracts** | **9** |
| **PnL** | **9 × +$40.25 = +$362.25** |

---

### MYM (Micro E-mini Dow Jones) — NY Session, 09:30 ET

| Step | Detail |
|------|--------|
| OR Window | 45756.00 — 45871.00 (range = 115.00 pts) |
| OR Ticks | 2,108 quotes during 5-min window |
| Breakout | **SHORT** at 09:35 ET |
| Entry Price | 45756.00 (OR Low) |
| TP Target | 45675.50 (entry − 0.70 × 115.00 = entry − 80.50) |
| SL Target | 45796.25 (entry + 0.35 × 115.00 = entry + 40.25) |
| Exit | **TP HIT** at 09:41 ET @ 45675.50 |
| Kelly Fraction | 0.0850 |
| Risk/Contract | $49.83 (EWMA avg_loss) |
| MDD Cap | 4 contracts (floor($225 / $50)) |
| **Contracts** | **4** |
| **PnL** | **4 × +$40.25 = +$161.00** |

---

## Assets Blocked by Risk Gates

| Asset | Session | OR Range | Direction | Risk/Contract | MDD Cap | Reason |
|-------|---------|----------|-----------|---------------|---------|--------|
| NQ | NY | 80.75 pts | SHORT | $293.92 | 0 | Risk/ct > daily budget |
| NKD | APAC | 270.00 pts | SHORT | $510.79 | 0 | Risk/ct > daily budget |
| ZB | NY Pre | 0.0312 pts | SHORT | $355.87 | 0 | Risk/ct > daily budget |
| ZN | NY Pre | 0.0156 pts | SHORT | $118.71 | 0 | Risk/ct > daily budget |
| MGC | London | 4.80 pts | SHORT | $50.73 | 4 | Excluded by position limit (max 5) |

---

## PnL Summary

| Asset | Direction | Entry | Exit | Reason | Contracts | PnL |
|-------|-----------|-------|------|--------|-----------|-----|
| MES | SHORT | 6,455.00 | 6,443.80 | TP HIT | 11 | +$616.00 |
| ES | SHORT | 6,454.75 | 6,443.20 | TP HIT | 1 | +$577.50 |
| MNQ | SHORT | 23,457.00 | 23,400.30 | TP HIT | 5 | +$567.00 |
| M2K | SHORT | 2,474.50 | 2,466.45 | TP HIT | 9 | +$362.25 |
| MYM | SHORT | 45,756.00 | 45,675.50 | TP HIT | 4 | +$161.00 |
| **TOTAL** | | | | **5 trades, 30 contracts** | | **+$2,283.75** |

---

## Session Statistics

| Metric | Value |
|--------|-------|
| Trades Executed | 5 |
| Wins | 5 |
| Losses | 0 |
| Win Rate | 100% |
| Gross Profit | +$2,283.75 |
| Gross Loss | $0.00 |
| Net PnL | **+$2,283.75** |
| Return on Capital | +1.52% |
| Capital at Risk | $0 realised loss |
| Max Drawdown Used | $0 of $4,500 (0%) |
| Daily Loss Used | $0 of $2,250 (0%) |
| Account Status | WITHIN ALL LIMITS |

---

## Market Context

All 6 NY-session assets broke SHORT immediately at 09:35:00 ET (OR window close) and dropped cleanly through their take-profit levels within 5-6 minutes. This was a high-conviction directional open — strong selling pressure from the first tick of the regular session, consistent across all equity index futures (S&P, Nasdaq, Russell, Dow).

Every trade hit its 0.70x OR-range take-profit target:
- ES dropped 16.50 pts in the OR, then another 11.55 pts to TP (5 mins)
- NQ dropped 80.75 pts in the OR, then another 56.53 pts to TP (5 mins)
- M2K dropped 11.50 pts in the OR, then another 8.05 pts to TP (5 mins)

The 2:1 reward:risk structure (0.70x TP vs 0.35x SL) captured the full downside move while keeping stop-losses tight enough to limit exposure.

---

## Kelly Sizing Detail

| Asset | LOW_VOL Kelly | HIGH_VOL Kelly | Blended | Shrinkage | After PASS_EVAL | Risk/Ct | Raw Cts | MDD Cap | Final |
|-------|---------------|----------------|---------|-----------|-----------------|---------|---------|---------|-------|
| ES | 0.0593 | 0.0380 | 0.0487 | ×0.974 | 0.0332 | $192.17 | 25 | 1 | **1** |
| MES | 0.1449 | 0.0479 | 0.0964 | ×0.973 | 0.1015 | $19.02 | 800 | 11 | **11** |
| MNQ | 0.1058 | 0.0503 | 0.0781 | ×0.975 | 0.0567 | $29.72 | 286 | 5 | **5** |
| M2K | 0.0682 | 0.0568 | 0.0625 | ×0.971 | 0.0875 | $34.23 | 383 | 9 | **9** |
| MYM | 0.0696 | 0.0517 | 0.0607 | ×0.972 | 0.0850 | $49.83 | 255 | 4 | **4** |

*MDD daily budget ($225) was the binding constraint for all assets.*

---

## Simulation Caveats

This replay simulates the core ORB pipeline. The following live pipeline steps were not included:

| Skipped Step | Pipeline Block | Effect |
|--------------|---------------|--------|
| VIX circuit breaker | Orchestrator | Halts all trading if VIX > 50 |
| Data Moderator | B1 | Price/volume validation, staleness checks |
| Regime classification | B2 | Dynamic LOW_VOL/HIGH_VOL (sim uses equal 50/50) |
| AIM aggregation | B3 | 6 adaptive modifiers (sim uses neutral 1.0) |
| Correlation filtering | B5 | Would block ES+MES simultaneously (~99% correlated) |
| Quality gate | B5B | Minimum conviction threshold |
| Circuit breaker L0-L6 | B5C | 7-layer safety checks |
| Portfolio risk cap | B4 | Total risk capped at 10% of capital |

**Note:** With correlation filtering active, MES would have been excluded (same underlying as ES). This would reduce total PnL by $616.00 to **+$1,667.75**.

---

*Report generated by Captain Function Session Replay Engine*
*Data: TopstepX REST API | Sizing: QuestDB (D05 EWMA, D12 Kelly, D08 TSM, D16 Capital Silo)*
