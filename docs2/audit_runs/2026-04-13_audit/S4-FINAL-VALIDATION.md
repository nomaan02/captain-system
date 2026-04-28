# Final Pre-Market Validation — 2026-04-13

**Scope**: Deep codebase-wide check for any remaining issues that could prevent live trading at next NY market open (09:30 ET Monday).
**Date**: 2026-04-13 (Sunday)
**Verdict**: **9/10 ASSETS READY** — MGC requires config decision; 2 schema bugs need fix for full feature quality.

---

## Executive Summary

Five parallel deep-dive audits were run across the entire Captain System codebase:

1. **Signal-to-trade critical path trace** (Online B1→B6 → Command B1→B3 → B7 monitoring)
2. **Configuration & environment consistency** (contract IDs, env vars, session registry, QuestDB schemas)
3. **Redis IPC consistency** (channels, streams, consumer groups, pub/sub migration)
4. **Import & syntax validation** (72 Python files, all block imports, cross-import consistency)
5. **Error handling on critical path** (8 failure scenarios traced through code)

### Result Matrix

| Audit Area | Verdict | Blockers | Warnings |
|------------|---------|----------|----------|
| Signal-to-trade path | READY (9/10 assets) | 0 | 1 (MGC session) |
| Config & environment | READY (with caveats) | 0 | 2 (D33/D22 schema) |
| Redis IPC | READY | 0 | 4 |
| Imports & syntax | READY | 0 | 0 |
| Error handling | READY | 0 | 3 |
| **TOTAL** | **READY** | **0** | **10** |

---

## Issues Requiring Action Before Market Open

### ISSUE 1 (HIGH): MGC Session Registry Inconsistency

**Files**:
- `config/session_registry.json:59` — assigns MGC to `"LON"` (03:00 ET)
- `scripts/bootstrap_production.py:62` — seeds D00 with `sessions: ["NY"]`
- `CLAUDE.md` locked strategies table — says MGC = `"NY"`

**Impact**: The OR tracker reads `session_registry.json` to determine OR window times for MGC. It will use LON timing (03:00-03:05 ET). But B1 loads MGC at NY open (09:30 ET) because D00 says NY. The OR range will be from 6.5 hours ago or missing entirely. MGC will likely produce no valid signal.

**Other 9 assets are unaffected** — 8 NY assets and NKD (APAC) have consistent session mappings.

**Action required**: Nomaan must decide: is MGC a LON or NY asset? Then fix whichever source is wrong.

### ISSUE 2 (HIGH): D33 `vol_5min` Column Does Not Exist

**Files**:
- `captain-online/.../b1_features.py:1257` — `INSERT INTO p3_d33_opening_volatility (asset_id, session_date, vol_5min)`
- `captain-online/.../b1_features.py:1397` — `SELECT vol_5min FROM p3_d33_opening_volatility`
- `scripts/init_questdb.py:766` — schema has `opening_range_pct DOUBLE`, NOT `vol_5min`

**Impact**: Both queries fail silently (caught by try/except). `store_opening_volatility()` does not store today's data. `_get_trailing_open_vol()` returns None. However, the AIM feature loader (`shared/aim_feature_loader.py:317`) correctly uses `opening_range_pct`, so bootstrapped historical data IS accessible for AIM-12 vol_z scoring. **First live session will work with historical data. Long-term: vol_z data goes stale because new sessions can't write.**

**Fix**: Rename `vol_5min` to `opening_range_pct` at b1_features.py lines 1257 and 1397.

### ISSUE 3 (MEDIUM): D22 GUI Health Diagnostic Column Mismatch

**Files**:
- `captain-command/.../b2_gui_data_server.py:821` — `SELECT dimension, score, status, details, timestamp`
- `scripts/init_questdb.py:511` — schema has `mode, scores, overall_health, ...action_queue, ts`

**Impact**: GUI system health diagnostic panel returns empty data. Query fails silently (caught by try/except). **Zero impact on trading pipeline** — this is display-only.

**Fix**: Align query column names to match actual schema, or align schema to match queries.

---

## Warnings (Non-Blocking, Fix Post-Launch)

### W-01: Verify `AUTO_EXECUTE=true` in `.env`

The `.env.template` defaults to `AUTO_EXECUTE=false`. Confirm the actual `.env` has `AUTO_EXECUTE=true` before market open.

### W-02: Missing PEL Recovery in Online and Offline Orchestrators

Command orchestrator correctly drains the Pending Entries List (PEL) on startup using `read_pending_stream()`. Online and Offline orchestrators do NOT — they start reading with `">"` (new messages only). Any messages delivered but not ACKed before a crash become orphaned.

**Risk**: Low — narrow crash window. Should be added for completeness.

### W-03: MarketStream Permanent Death Goes Undetected

If pysignalr's rapid-failure detection triggers (5 drops in <10s each), the stream enters DISCONNECTED state silently. The orchestrator does not check stream state before running sessions. B1 would read stale prices from the quote cache.

**Mitigation**: Reconnection handles transient failures well. Permanent death is unlikely outside of token expiry (which Docker restart + auth retry handles).

### W-04: Missing Catch-All in `_auto_execute_signal`

`captain-command/.../orchestrator.py` — `_auto_execute_signal()` has no top-level try/except. An unexpected exception from `send_signal()` would crash the signal handler thread (though Command process continues).

### W-05: Missing Consumer Group Inits in main.py

- Offline `main.py` missing: `ensure_consumer_group(STREAM_SIGNAL_OUTCOMES, GROUP_OFFLINE_SIGNAL_OUTCOMES)`
- Command `main.py` missing: `ensure_consumer_group(STREAM_COMMANDS, GROUP_COMMAND_COMMANDS)`

**Risk**: Nil — orchestrator loops create groups redundantly. But main.py is the canonical fail-fast location.

### W-06: Test Scripts Use Pub/Sub Instead of Streams

`scripts/paper_trader.py` and `scripts/inject_test_signal.py` still publish signals via pub/sub. Command's stream reader won't receive them. Only affects development/test tooling.

### W-07: Orphaned Position Recovery Not Implemented

If Online crashes while positions are open, the in-memory position list is lost. Brokerage-side bracket orders (SL/TP) protect against unlimited loss, but D03 trade outcome logging breaks — Offline learning misses that trade.

---

## Full Validation Results

### Signal-to-Trade Path (14 files traced)

| Block | File | Status | Notes |
|-------|------|--------|-------|
| Online main.py | captain-online/.../main.py | OK | TopstepX auth 3x retry + fatal exit |
| B1 Data Ingestion | captain-online/.../b1_data_ingestion.py | OK | All table names match schema |
| B2 Regime | captain-online/.../b2_regime_probability.py | OK | Binary + classifier paths with fallback |
| B3 AIM | shared/aim_compute.py | OK | Aggregation with feature loader |
| B4 Kelly Sizing | captain-online/.../b4_kelly_sizing.py | OK | V3 4-way min, risk per contract |
| B5 Selection | captain-online/.../b5_trade_selection.py | OK | Edge calc, correlation filter, HMM |
| B5B Quality Gate | captain-online/.../b5b_quality_gate.py | OK | Cold-start floor at 0.5 |
| B5C Circuit Breaker | captain-online/.../b5c_circuit_breaker.py | OK | 7 layers, L3/L4 cold-start disabled |
| B6 Signal Output | captain-online/.../b6_signal_output.py | OK | 3x retry + CRITICAL alert |
| B7 Position Monitor | captain-online/.../b7_position_monitor.py | OK | TP/SL detection, D03 write, outcome publish |
| B9 Session Controller | captain-online/.../b9_session_controller.py | OK | Window default=5 matches registry |
| Command Orchestrator | captain-command/.../orchestrator.py | OK | Stream reader + PEL recovery |
| B1 Core Routing | captain-command/.../b1_core_routing.py | OK | All 5 publishes use STREAM_COMMANDS |
| B3 API Adapter | captain-command/.../b3_api_adapter.py | OK | Bracket orders, compliance gate, SL alert |

### Contract IDs (10 assets)

| Asset | Contract ID | Status |
|-------|------------|--------|
| ES | CON.F.US.EP.M26 | Current (June 2026) |
| MES | CON.F.US.MES.M26 | Current |
| NQ | CON.F.US.ENQ.M26 | Current |
| MNQ | CON.F.US.MNQ.M26 | Current |
| M2K | CON.F.US.M2K.M26 | Current |
| MYM | CON.F.US.MYM.M26 | Current |
| NKD | CON.F.US.NKD.M26 | Current |
| MGC | CON.F.US.MGC.M26 | Current |
| ZB | CON.F.US.USA.M26 | Current |
| ZN | CON.F.US.TYA.M26 | Current |

Zero H26 (expired) references in source code.

### Redis IPC Paths (7 paths traced)

| Path | Mechanism | Publisher → Subscriber | Status |
|------|-----------|----------------------|--------|
| Signals | Stream (durable) | Online B6 → Command orchestrator | PASS |
| Trade outcomes | Stream (durable) | Online B7 → Offline orchestrator | PASS |
| Commands | Stream (durable) | Command B1/B5 → all 3 processes | PASS |
| Signal outcomes | Stream (durable) | Online B7 shadow → Offline orchestrator | PASS |
| Alerts | Pub/sub (fire-and-forget) | Any → Command B7 | PASS (non-critical) |
| Status | Pub/sub (fire-and-forget) | All → Command | PASS (non-critical) |
| Process logs | Pub/sub (fire-and-forget) | All → Command → GUI | PASS (non-critical) |

All critical data flows use durable Redis Streams. Consumer groups unique per process. No shared groups.

### Import & Syntax Validation

| Area | Files | Status |
|------|-------|--------|
| Python syntax (py_compile) | 72 files | ALL PASS |
| Captain Online imports | 16 blocks | ALL OK |
| Captain Offline imports | 20 blocks | ALL OK |
| Captain Command imports | 16 blocks | ALL OK |
| Shared modules | 19 modules | ALL OK |
| Cross-import consistency | CH_COMMANDS migration | CLEAN |

### Error Handling (8 scenarios)

| Scenario | Handling | Severity |
|----------|----------|----------|
| TopstepX auth failure | 3x retry → FATAL exit | ACCEPTABLE |
| Order placement failure | Caught, alerted, system continues | ACCEPTABLE |
| Redis connection loss | 3x retry on signal + outcome publish | ACCEPTABLE |
| QuestDB connection loss | Auto-healing + 3x retry on connect | ACCEPTABLE |
| Market data disconnect | pysignalr auto-reconnect (20s detect) | WARNING (see W-03) |
| Circuit breaker halt | Removes assets from pipeline — no signal = no trade | ACCEPTABLE |
| Orphaned positions | Not recovered, but bracket orders protect | WARNING (see W-07) |
| Crash recovery journal | Passive audit trail, no active recovery | ACCEPTABLE for launch |

---

## Pre-Market Checklist

Before starting Docker containers for Monday market open:

- [ ] **Decide MGC session**: Is MGC a LON or NY asset? Fix `session_registry.json` or `bootstrap_production.py`
- [ ] **Fix D33 column** (optional for first session): Change `vol_5min` to `opening_range_pct` in b1_features.py lines 1257 and 1397
- [ ] **Verify `.env`**: Confirm `AUTO_EXECUTE=true`
- [ ] **Start Docker Desktop**: Enable WSL2 integration
- [ ] **Run**: `bash captain-start.sh --build`
- [ ] **Verify**: All 9 containers healthy (`docker compose ps`)
- [ ] **Verify**: `/api/health` returns 200
- [ ] **Verify**: QuestDB console at `:9000` — `SELECT count() FROM p3_d00_asset_universe` returns 10

---

## Conclusion

The Captain System is **ready for live trading on 9 of 10 assets**. The complete signal-to-trade pipeline — from TopstepX market data through regime detection, AIM scoring, Kelly sizing, circuit breaker screening, signal publication, order execution, and position monitoring — is wired correctly with proper error handling, retry logic, and durable Redis Streams.

The 3 issues found are:
1. **MGC session config inconsistency** — blocks MGC only, needs decision
2. **D33 vol_5min column name** — silent degradation of AIM-12 feature, not a crash
3. **D22 GUI column mismatch** — health panel shows empty, zero trading impact

All S1-S3 audit fixes (17 issues) are verified and holding. No regressions detected. 148/148 unit tests pass. 72/72 Python files compile cleanly. 20/20 static grep checks pass.
