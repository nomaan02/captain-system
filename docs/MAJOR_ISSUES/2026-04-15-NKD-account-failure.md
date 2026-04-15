# MAJOR ISSUE: NKD APAC Session Loss — Account Failure

**Date:** 2026-04-15
**Severity:** CRITICAL
**Account:** 20260837 (150KTC-V2-551001-19064435)
**Status:** Account failed — max drawdown exceeded

---

## Summary

Overnight on 2026-04-14/15, NKD (Nikkei 225 futures) took a loss exceeding $5,000 during the APAC trading session, breaching the $4,500 max drawdown limit on the TopstepX 150K Trading Combine account (20260837). The account is now failed with `canTrade=False` and a remaining balance of $144,716.26 ($5,283.74 below starting capital).

The system had **zero functioning safety nets** — the feedback loop that should record trade outcomes, update the circuit breaker, and track capital was completely dead. No trade was ever recorded in the outcome log, meaning the system was executing live trades with no learning, no risk adaptation, and no loss-prevention feedback of any kind.

---

## Root Cause Analysis

### 1. Feedback Loop Completely Dead

The core feedback loop (`Online -> signal -> Command -> execute -> outcome -> Offline -> learn`) was broken at the outcome recording step. Evidence:

| Component | Expected State | Actual State |
|-----------|---------------|--------------|
| D03 (trade_outcome_log) | Records every trade entry/exit with P&L | **0 rows — completely empty** |
| D25 (circuit_breaker_params) | Calibrates from trade observations | **cold_start=true, n_observations=0, beta_b=0.0** |
| D16 (user_capital_silos) | Tracks real P&L, updates total_capital | **total_capital still $150,000, capital_history shows only initial_bootstrap** |
| D12 (kelly_parameters) | Updates from EWMA win rate / avg loss | **Never received trade data to update from** |

**Impact:** The system was executing live trades but never recording outcomes. This means:
- Circuit breaker layers 3-4 were permanently disabled (cold start, no data)
- Kelly sizing never adapted to real performance
- EWMA states never updated from actual wins/losses
- No capital tracking — system believed it still had $150,000

### 2. NKD Strategy Parameters

NKD has the tightest strategy parameters of all 10 assets:

| Parameter | Value | Note |
|-----------|-------|------|
| m (lookback) | 6 | |
| k (threshold) | 6 | **Tightest k of all assets** — most aggressive breakout trigger |
| OO (out-of-sample) | 0.8533 | |
| Session | APAC | Only asset in the APAC session — trades alone overnight |

The extremely tight k=6 means NKD triggers breakout signals on very small moves. Combined with no circuit breaker protection, a bad signal during a volatile APAC session could result in an outsized loss.

### 3. Overlayfs Crash Context

The tower experienced an `overlayfs: cleanup of 'work/work' failed (-30)` error overnight, traced to Docker I/O pressure on the overlay filesystem. This may have:
- Caused a system reboot mid-trade, leaving a position open without monitoring
- Prevented the B7 position monitor from detecting stop-loss hits
- Corrupted container state, preventing clean shutdown and position flattening

The timeline suggests the crash occurred during or shortly after the APAC session when NKD was actively trading.

### 4. Captain-Command OOM Crash Loop

After the system came back up, captain-command entered a crash loop with exit code 137 (SIGKILL — OOM kill). The container had a 768MB memory limit which was insufficient. This meant:
- The GUI could not connect (API, WebSocket, Redis, QuestDB all route through captain-command)
- No manual intervention was possible through the GUI
- The system appeared completely unresponsive

**Fix applied:** Memory limit increased from 768MB to 1280MB in `docker-compose.local.yml`.

---

## What We Still Don't Know

1. **The exact trade(s):** D03 is empty — we have no record of what NKD traded, at what size, what direction, or what the entry/exit prices were. The TopstepX API trade history on account 20260837 has not yet been pulled.

2. **Whether stop losses were set:** If B6 generated a signal with TP/SL levels, did the order actually include the stop loss? If the system crashed mid-execution, the stop might never have been placed.

3. **Whether it was one trade or multiple:** A single $5K loss or accumulated losses across the APAC session.

4. **Why D03 is empty:** The trade outcome recording mechanism has never worked on this deployment. This could be:
   - B7 (position monitor) not detecting exits
   - The trade outcome Redis channel not publishing
   - The Offline orchestrator not consuming outcomes
   - A code bug in the outcome recording path

5. **Whether the overlayfs crash happened before, during, or after the NKD trade(s).**

---

## Immediate Actions Taken

| Action | Status |
|--------|--------|
| Switched to practice account (20319811, PRAC-V2-551001-43861321) | Done |
| Fixed captain-command OOM (768MB -> 1280MB) | Done |
| Updated BOOTSTRAP_ACCOUNT_ID to 20319811 | Done |
| System verified healthy on practice account (canTrade=True, balance=$149,997.51) | Done |

---

## Required Investigation (Before Any Non-Practice Trading)

1. **Pull TopstepX trade history** from account 20260837 via the API to get the actual NKD trade details
2. **Root-cause why D03 is empty** — trace the entire feedback loop from trade execution through outcome recording
3. **Verify B7 position monitor** is actually detecting trade exits and publishing to `captain:trade_outcomes`
4. **Verify Offline orchestrator** is consuming trade outcomes and updating D02/D04/D05/D12/D25
5. **Verify D16 capital tracking** updates after trades
6. **Stress test the feedback loop** on the practice account — execute a trade and verify the full cycle: signal -> execution -> outcome recorded -> offline learning -> updated state
7. **Investigate QuestDB D01 bloat** — 4.3 million rows (expected ~270) indicates append-only table growing unbounded, likely contributing to OOM
8. **Fix TSM file** — `topstep_150k_live.json` is missing `starting_balance` and `max_drawdown_limit` fields (3/4 valid)

---

## Key Lesson

The system was deployed to a live-funded account with `AUTO_EXECUTE=true` but the feedback loop — the single most critical safety mechanism — was never verified to be working end-to-end. The circuit breaker, Kelly adaptation, and capital tracking all depend on trade outcomes being recorded, and none of them received a single data point. The system was effectively trading blind.
