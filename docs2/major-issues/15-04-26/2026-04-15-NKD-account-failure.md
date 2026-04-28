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

## Live Observation: Same Bugs Reproduced on Practice Account

**Time:** ~15:32 ET, 2026-04-15 (practice account 20319811)

The GUI is now showing an active NKD position with multiple anomalies that confirm the feedback loop is still broken:

### GUI Data

| Field | Value | Expected |
|-------|-------|----------|
| Direction | LONG | — |
| Asset | NKD | — |
| Contracts | 1 | — |
| Signal ID | SIG-C727DF4F5FF0 | — |
| Entry Price | **— (MISSING)** | Should show fill price from brokerage |
| Current Price | 58,355.00 | — |
| P&L | **+$0.00 (+0 ticks)** | Should show unrealized loss |
| SL | 58,855.75 | Should be below entry for a LONG |
| TP | 58,913.50 | Should be above entry for a LONG |
| Fill Reference | SIG-C727DF4F5FF0 | Should be a brokerage order/fill ID |

### Anomalies Identified

1. **Entry price is missing ("—")** — The brokerage fill price was never captured. B7 needs entry price to calculate P&L and detect TP/SL hits. Without it, `_write_trade_outcome()` cannot compute `gross_pnl = (exit - entry) * direction * contracts * point_value`.

2. **P&L stuck at $0.00** — Direct consequence of missing entry price. The system cannot compute unrealized P&L.

3. **Current price (58,355.00) is ~500 points BELOW the SL (58,855.75)** — The stop loss should have triggered when price passed through 58,855.75. At $5/point for NKD, this is approximately **-$2,500 unrealized loss on 1 contract** that is neither detected nor reported.

4. **SL/TP both above current price** — For a LONG position, entry should be between SL and TP (i.e., SL < entry < TP). The entry was likely ~58,870-58,890. Current price has blown through the SL by 500+ points.

5. **Fill reference is the signal ID, not a brokerage fill ID** — Suggests the actual fill confirmation from TopstepX was never received or mapped back to the position.

### What This Confirms

- **B7 position monitor is NOT detecting SL breaches** — the position should have been resolved when price dropped below 58,855.75
- **The feedback loop failure is reproducible on the practice account** — this is not a one-off from the overlayfs crash
- **Entry price capture is broken** — either the fill response from `place_market_order()` doesn't return a fill price, or it's not being passed through to the position tracking
- **The same vulnerability that caused the $5K loss on account 20260837 is active right now**

---

## API Cross-Check: Critical Implementation Discrepancies

**Time:** ~14:30 GMT+1, 2026-04-15

Cross-referenced `shared/topstep_client.py`, `captain-command/.../b3_api_adapter.py`, and `shared/topstep_stream.py` against the official TopstepX/ProjectX API documentation (`docs/official_topstep_api_docs/`). Found 5 discrepancies, 3 of which are critical and directly explain the account failure.

### CRITICAL 1: Native Bracket Orders Not Used

The TopstepX API supports **atomic bracket orders** — a single `/Order/place` call that creates entry + SL + TP together:

```json
{
    "accountId": 465,
    "contractId": "CON.F.US.NKD.U25",
    "type": 2, "side": 0, "size": 1,
    "stopLossBracket": {"ticks": 10, "type": 4},
    "takeProfitBracket": {"ticks": 20, "type": 1}
}
```

**Our code places 3 SEPARATE API calls instead** (`b3_api_adapter.py` `send_signal()`):
1. `place_market_order()` → entry
2. `place_stop_order()` → SL (can fail independently)
3. `place_limit_order()` → TP (can fail independently)

Our `place_order()` in `topstep_client.py` doesn't even accept `stopLossBracket`/`takeProfitBracket` parameters — the fields are missing from the payload.

**Impact:** If the system crashes between call 1 and call 2 (overlayfs crash scenario), the position exists at the brokerage with **no stop loss**. With native brackets, the exchange manages TP/SL atomically — no software monitoring required.

### CRITICAL 2: Wrong Position Endpoint

| | Our Code | Official API |
|---|----------|-------------|
| Endpoint | `/Position/search` | `/Position/searchOpen` |
| File | `topstep_client.py` `search_positions()` | Official docs |

Our code calls an endpoint that **does not exist** in the official documentation. The correct endpoint `/Position/searchOpen` returns open positions with an `averagePrice` field — the **entry/fill price** the system needs.

### CRITICAL 3: WebSocket Fill Callbacks Never Wired

`shared/topstep_stream.py` `UserStream` subscribes to all User Hub events and has handlers for:

| Event | Data Available | Wired in Production? |
|-------|---------------|---------------------|
| `GatewayUserOrder` | `filledPrice`, `fillVolume`, `status` | **NO** — callback never set |
| `GatewayUserPosition` | `averagePrice` (entry price) | **NO** — cached but callback never set |
| `GatewayUserTrade` | `price`, `profitAndLoss`, `fees` | **NO** — callback never set |
| `GatewayUserAccount` | `balance`, `canTrade` | **NO** — callback never set |

The brokerage IS sending fill data in real-time via WebSocket. **Nobody is listening.** The `_positions_cache` stores `averagePrice` internally but no code reads it.

Meanwhile `b3_api_adapter.py` has a `receive_fill(order_id)` method that queries `/Order/search` for `filledPrice`, but there's no evidence the orchestrator ever calls it after order placement.

### MEDIUM: Non-Existent OrderType Enum Value

| Value | Our Code | Official API |
|-------|----------|-------------|
| 3 | `STOP_LIMIT` | **Does not exist** (API enum jumps 2→4) |

In `topstep_client.py` `OrderType.STOP_LIMIT = 3`. Not used in the bracket flow currently, but could cause API rejection if ever called.

### CRITICAL 4: TP/SL Prices Not Aligned to Tick Size — ALL Orders Rejected

**Discovered:** ~14:50 GMT+1, 2026-04-15 via TopstepX native dashboard order log

B6 computes TP/SL using floating-point arithmetic on OR ranges and multipliers, producing fractional tick values. The TopstepX API requires prices to be **exact multiples of the instrument's tick size**. Every SL and TP order is rejected.

Evidence from practice account orders export (`orders_export.csv`):

| Asset | Tick Size | SL Price Sent | TP Price Sent | Result |
|-------|-----------|--------------|--------------|--------|
| MES (x11) | 0.25 | 7017.**5375** | 7025.**675** | **Both REJECTED** |
| ES (x1) | 0.25 | 7017.**5375** | 7025.**675** | **Both REJECTED** |
| MNQ (x5) | 0.25 | 26025.**175** | 26071.**9** | **Both REJECTED** |

Rejection message: `"Invalid stop price. Price is not aligned to tick size."` / `"Invalid limit price. Price is not aligned to tick size."`

**Every entry order fills successfully** (Market orders don't need tick alignment), but **every protective SL/TP order is rejected**. Result: all positions sit at the brokerage completely naked.

For the NKD failure: NKD tick size = 5. If B6 computed an SL like 58,855.75, that's not a multiple of 5 — rejected. The position sat open with no stop loss during the entire APAC session.

Trades export (`trades_export.csv`) confirms all today's positions were closed manually from the TopstepX dashboard, not by the system:

| Asset | Entry | Exit | P&L | Closed By |
|-------|-------|------|-----|-----------|
| MES x11 | 7019.75 | 7010.75 | -$495.00 | Manual (ClosePosition) |
| ES x1 | 7019.75 | 7011.00 | -$437.50 | Manual (ClosePosition) |
| MNQ x5 | 26044.25 | 26048.00 | +$37.50 | Manual (ClosePosition) |

### How These Discrepancies Caused the Account Failure

```
What Should Happen                    What Actually Happens
──────────────────                    ─────────────────────
TP/SL prices:     Tick-aligned        Sub-tick decimals → ALL SL/TP REJECTED by API
Order placement:  Atomic bracket      3 separate calls (crash-vulnerable)
SL enforcement:   Exchange-managed    Software-only (requires B7 running)
                                      AND rejected at API level → zero protection
Entry price:      From fill callback  Never captured (callbacks not wired)
B7 monitoring:    Check vs entry+SL   Has no entry price → can't detect SL breach
Trade outcomes:   Written to D03      Never written (no exit detection possible)
Feedback loop:    Updates all params   All permanently stale (cold start forever)
```

**The system has ZERO layers of stop-loss protection:**
1. Exchange-level brackets → not implemented (3 separate orders instead)
2. API-level SL orders → REJECTED (tick alignment)
3. Software-level B7 monitoring → broken (no entry price, in-memory state lost on crash)

The system relies **entirely on software-level TP/SL monitoring** (B7) instead of **exchange-level bracket orders**. When B7 can't function (missing entry price, process crash, in-memory state lost), there is zero protection on the position.

---

## Consolidated Issues & Proposed Fixes

All issues discovered during this investigation, organized by severity and independence. Two independent failure chains were identified — both must be fixed before any non-practice trading.

### CHAIN 1: No Exchange-Level Protection (Positions Are Naked)

These issues mean no TP/SL orders exist at the brokerage. Positions sit completely unprotected.

#### Issue 1A: TP/SL Prices Not Tick-Aligned (CRITICAL — Immediate Fix)

- **Problem:** B6 (`captain-online/.../b6_signal_output.py`) computes TP/SL via floating-point arithmetic on OR ranges (`_compute_tp()`, `_compute_sl()`), producing sub-tick precision values (e.g., 7017.5375 for a 0.25-tick instrument). TopstepX API rejects these: `"Invalid stop price. Price is not aligned to tick size."`
- **Evidence:** `docs/MAJOR_ISSUES/orders_export.csv` — every SL and TP order on 2026-04-15 was REJECTED across MES, ES, and MNQ. All entry (Market) orders filled successfully.
- **Proposed Fix:** Round TP/SL to nearest tick before publishing: `rounded = round(price / tick_size) * tick_size`. Tick sizes are available from the contract data (e.g., `/Contract/available` response or `shared/contract_resolver.py`). For safety: round SL toward entry (tighter stop), round TP toward entry (earlier exit).
- **Files:** `captain-online/captain_online/blocks/b6_signal_output.py` (`_compute_tp()`, `_compute_sl()`), possibly `shared/contract_resolver.py` (needs to expose tick sizes)

#### Issue 1B: Native Bracket Orders Not Used (CRITICAL — Architectural)

- **Problem:** TopstepX API supports atomic bracket orders via `stopLossBracket` and `takeProfitBracket` parameters on `/Order/place`. Our code places 3 SEPARATE API calls (entry → SL → TP) in `b3_api_adapter.py` `send_signal()`. If the system crashes between entry and SL placement, the position has no stop loss.
- **Evidence:** The overlayfs crash on 2026-04-14/15 likely hit during this window. `shared/topstep_client.py` `place_order()` doesn't accept bracket parameters at all.
- **Proposed Fix:** Add `stopLossBracket`/`takeProfitBracket` support to `place_order()` in `topstep_client.py`. Modify `send_signal()` in `b3_api_adapter.py` to send a single API call with bracket parameters. Bracket uses `ticks` (integer tick count distance from fill), not absolute prices — requires converting price-level distances to tick counts. Keep the 3-order fallback as a safety net if bracket placement fails.
- **Files:** `shared/topstep_client.py` (`place_order()`), `captain-command/captain_command/blocks/b3_api_adapter.py` (`send_signal()`)
- **Note:** Native brackets use `ticks` (integer) not price levels. Formula: `ticks = int(abs(entry_price - sl_price) / tick_size)`. This requires knowing the fill price at bracket submission time — for market orders, the fill price isn't known until after execution. Evaluate whether the API resolves bracket ticks relative to fill or whether absolute-price separate orders remain necessary as a primary approach with tick-alignment fix.

#### Issue 1C: No Automatic Flatten on SL Failure (HIGH)

- **Problem:** In `b3_api_adapter.py` `send_signal()`, if the SL order fails after entry fills, a CRITICAL alert is published but the entry is NOT cancelled and the position is NOT flattened. The position sits open and unprotected.
- **Proposed Fix:** If SL placement fails, immediately call `/Position/closeContract` to flatten the position. Better to exit at market than hold naked.
- **Files:** `captain-command/captain_command/blocks/b3_api_adapter.py` (`send_signal()`)

---

### CHAIN 2: No Software-Level Monitoring (Feedback Loop Dead)

These issues mean B7 can't track positions, outcomes are never recorded, and the learning loop never fires.

#### Issue 2A: Entry Price Never Captured (CRITICAL)

- **Problem:** When an order fills, the `filledPrice` is available from the API (via `/Order/search` response or `GatewayUserOrder` WebSocket event). But this price never flows back to captain-online's `open_positions` list. The TAKEN command published by captain-command doesn't include the fill price. B7 sees entry_price as `None` → can't compute P&L or detect TP/SL hits.
- **Evidence:** GUI shows entry price as "—" for the active NKD position.
- **Proposed Fix:** After order placement in `_auto_execute_signal()`, call `receive_fill(order_id)` (which already exists in `b3_api_adapter.py`) to get `filledPrice`. Include it in the TAKEN command published to `stream:commands`. In captain-online's `_handle_taken_skipped()`, extract it into the position dict.
- **Files:** `captain-command/captain_command/blocks/orchestrator.py` (`_auto_execute_signal()`), `captain-command/captain_command/blocks/b3_api_adapter.py` (`receive_fill()`), `captain-online/captain_online/blocks/orchestrator.py` (`_handle_taken_skipped()`)

#### Issue 2B: WebSocket Fill Callbacks Not Wired (CRITICAL)

- **Problem:** `shared/topstep_stream.py` `UserStream` subscribes to `GatewayUserOrder`, `GatewayUserPosition`, `GatewayUserTrade` events. Handlers exist. But NO production code wires the callbacks — `on_order_update`, `on_position_update`, `on_trade_update` are never set. Fill data (`filledPrice`, `averagePrice`, trade `price`/`profitAndLoss`/`fees`) arrives from TopstepX and is silently dropped.
- **Proposed Fix:** Wire UserStream callbacks in captain-command's `main.py` during TopstepX initialization. At minimum, use `GatewayUserPosition` (`averagePrice`) to update position tracking, and `GatewayUserTrade` (`profitAndLoss`, `fees`) for real-time outcome capture.
- **Files:** `shared/topstep_stream.py` (callback infrastructure exists), `captain-command/captain_command/main.py` (needs to wire callbacks during `_init_topstep()`)
- **Note:** TopstepX allows only ONE concurrent WebSocket per account. Currently captain-online owns the WebSocket for market data. Evaluate whether captain-command can share or if UserStream events should route through captain-online.

#### Issue 2C: `open_positions` Is In-Memory Only (CRITICAL)

- **Problem:** The Online orchestrator's `self.open_positions` list is never persisted. If captain-online restarts (crash, OOM, overlayfs error), all tracked positions are lost permanently. B7 stops monitoring. No reconciliation with the brokerage occurs on startup.
- **Evidence:** The overlayfs crash would have wiped this list. After restart, B7 had nothing to monitor, even if positions existed at the brokerage.
- **Proposed Fix:** On startup, query `/Position/searchOpen` to discover brokerage positions and reconstruct `open_positions`. Alternatively, persist position state to QuestDB or Redis so it survives restarts.
- **Files:** `captain-online/captain_online/blocks/orchestrator.py` (add startup reconciliation), `shared/topstep_client.py` (fix endpoint — see Issue 2E)

#### Issue 2D: D03 Empty → Entire Offline Pipeline Dead (CRITICAL)

- **Problem:** Because B7 never resolves positions (no entry price), `_write_trade_outcome()` never fires, D03 stays empty. This means the entire Offline learning pipeline never triggers:
  - D02 AIM weights never update (`b1_dma_update.py`)
  - D04 decay detection never runs (`b2_bocpd.py`, `b2_cusum.py`)
  - D05 EWMA states never update (`b8_kelly_update.py`)
  - D12 Kelly fractions never adapt (`b8_kelly_update.py`)
  - D25 circuit breaker stays cold_start=true (`b8_cb_params.py`) → Layers 3-4 permanently disabled
  - D16 capital stuck at bootstrap $150K (`b7_position_monitor.py` `_update_capital_and_cb()`)
- **Proposed Fix:** This resolves automatically once Issues 2A-2C are fixed. B7 will be able to detect exits → write D03 → publish to Redis → Offline consumes and updates all tables. Verify end-to-end on practice account after fixes.
- **Files:** All Offline blocks (indirect — depend on upstream fixes)

#### Issue 2E: Wrong Position Endpoint (HIGH)

- **Problem:** `shared/topstep_client.py` `search_positions()` calls `/Position/search` which does not exist in the official API. The correct endpoint is `/Position/searchOpen`.
- **Proposed Fix:** Change endpoint from `/Position/search` to `/Position/searchOpen`.
- **Files:** `shared/topstep_client.py` (`search_positions()`)

#### Issue 2F: Non-Existent OrderType Enum (LOW)

- **Problem:** `shared/topstep_client.py` defines `OrderType.STOP_LIMIT = 3` which does not exist in the official API (enum jumps 2→4). Not currently used in the bracket flow but could cause rejection if ever called.
- **Proposed Fix:** Remove or comment out `STOP_LIMIT = 3`.
- **Files:** `shared/topstep_client.py` (`OrderType` class)

---

### OTHER ISSUES (From Original Investigation)

#### Issue 3A: QuestDB D01 Bloat (MEDIUM)

- **Problem:** `p3_d01_aim_model_states` has 4.3 million rows (expected ~270). Append-only table growing unbounded, likely contributing to captain-command OOM (768MB limit).
- **Proposed Fix:** Add table compaction or deduplication. OOM fix already applied (768MB → 1280MB) but bloat should be addressed.

#### Issue 3B: TSM Config Missing Fields (MEDIUM)

- **Problem:** `topstep_150k_live.json` is missing `starting_balance` and `max_drawdown_limit` fields (3/4 valid).
- **Proposed Fix:** Add missing fields to the TSM config file.

#### Issue 3C: Docker Restart Policy & Overlayfs (MEDIUM)

- **Problem:** `overlayfs: cleanup of 'work/work' failed (-30)` error traced to Docker I/O pressure on Ubuntu 24.04. Container restart behavior can cause in-memory state loss (Issue 2C).
- **Proposed Fix:** Standardized Docker maintenance with local logging driver and systemd timers (already decided). Issue 2C (position persistence) is the real fix for the data-loss aspect.

---

### Fix Priority Order

| Priority | Issue | Impact | Complexity |
|----------|-------|--------|------------|
| **P0** | 1A: Tick-align TP/SL | Positions get exchange-level SL/TP protection | Low — single rounding function |
| **P0** | 2E: Fix position endpoint | Position queries work correctly | Low — one string change |
| **P0** | 2F: Remove bad enum | Prevents future API rejection | Low — one line |
| **P1** | 1C: Flatten on SL failure | No naked positions if SL order fails | Low — add flatten call |
| **P1** | 2A: Capture entry price | B7 can track positions and detect exits | Medium — wire fill price through TAKEN command |
| **P1** | 2C: Persist/reconcile positions | Positions survive restarts | Medium — startup reconciliation query |
| **P2** | 1B: Native bracket orders | Atomic SL/TP at exchange level | Medium — API change + tick conversion |
| **P2** | 2B: Wire WebSocket callbacks | Real-time fill + position data | Medium — evaluate WebSocket ownership |
| **P3** | 3A: D01 bloat | Reduce memory pressure | Medium — compaction script |
| **P3** | 3B: TSM config | Correct risk parameters | Low — add fields |

**Minimum viable safety:** P0 + P1 issues fixed = exchange-level SL/TP protection + software-level B7 monitoring + position crash recovery. Verify end-to-end on practice account before any live trading.

---

## Key Lesson

The system was deployed to a live-funded account with `AUTO_EXECUTE=true` but:

1. **TP/SL orders were silently rejected by the brokerage** — every position since deployment had zero stop-loss protection. The rejection errors were never surfaced or checked.
2. **The feedback loop was never verified end-to-end** — the circuit breaker, Kelly adaptation, and capital tracking all depend on trade outcomes being recorded, and none received a single data point.
3. **No defense-in-depth** — the system relied on a single layer of software monitoring (B7) that itself depended on fill data that was never captured. When B7 couldn't function, there was zero fallback.

The system was effectively placing market orders into a brokerage with no stop losses, no exit monitoring, no outcome recording, and no learning — while believing it had all of these.
