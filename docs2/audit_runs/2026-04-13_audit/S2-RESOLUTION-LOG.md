# Session 2 Resolution Log — 2026-04-13

**Session**: S2 — Startup Resilience
**Issues**: C2, H2
**Date**: 2026-04-13
**Status**: COMPLETE

---

## Fix H2 — QuestDB Connection Retry

**Severity**: HIGH
**Root cause**: `_connect()` in `shared/questdb_client.py` made a single connection attempt with no retry. A 1-second QuestDB startup delay caused process exit. `captain-start.sh` had a workaround (wait loop), but raw `docker compose up` was fragile.

**Changes**:
| File | Change | Details |
|------|--------|---------|
| `shared/questdb_client.py` | Added `import logging, time` | Lines 9, 12 |
| Same | Added `logger = logging.getLogger(__name__)` | Line 16 |
| Same | Added `_CONNECT_MAX_ATTEMPTS = 3` and `_CONNECT_DELAYS = [1, 2, 4]` | Lines 27-28 |
| Same | Rewrote `_connect()` | 3-attempt retry loop with exponential backoff [1s, 2s, 4s]. Logs WARNING on each retry. Logs INFO on success after retry. Logs ERROR and raises original exception on final failure. |

**Retry behavior**: 3 attempts, delays [1s, 2s, 4s] (total 7s max wait). On first-attempt success: no extra logging. On retry success: logs "QuestDB connection succeeded on attempt N". On final failure: logs ERROR and re-raises the original psycopg2 exception.

**Scope**: This single change fixes all 3 processes (Online, Offline, Command) since they all import from `shared/questdb_client.py`.

**Verification**:
- `python3 -c "from shared.questdb_client import _connect, get_connection; print('Import OK')"` — OK
- 148 unit tests passed in 0.78s
- Existing callers unaffected: they catch `Exception` on failure, which is preserved

---

## Fix C2 — TopstepX Auth Failure Must Be Fatal

**Severity**: CRITICAL
**Root cause**: `_start_market_streams()` in `captain-online/main.py` caught all exceptions and returned None. The caller at line 121-125 logged a warning and continued to start the orchestrator. B1 received no quotes. The system ran blind — generating signals without market data, or silently producing nothing.

**Changes**:
| File | Change | Details |
|------|--------|---------|
| `captain-online/captain_online/main.py` | Added `import time` | Line 18 |
| Same | Added `_TOPSTEP_MAX_ATTEMPTS = 3` and `_TOPSTEP_RETRY_DELAY_S = 5` | Lines 44-45 |
| Same | Rewrote `_start_market_streams()` | 3-attempt retry loop. Preserves original dual except blocks (TopstepXClientError vs generic Exception). Logs WARNING with attempt count on each retry. Logs ERROR on final failure. Returns None only after all retries exhausted. |
| Same | Changed auth failure handling in `main()` | From `plog.warn("MarketStream failed to start")` (continues) to `logger.critical(...)` + `plog.error(...)` + `sys.exit(1)` |

**Retry behavior**: 3 attempts, 5s delay between retries (15s total max wait). Handles both TopstepXClientError (API-level auth failure) and unexpected exceptions (network timeout, DNS, etc.) with the same retry logic. On final failure: returns None, which triggers fatal exit.

**Fatal exit behavior**: `sys.exit(1)` causes Docker to restart the container (unless restart policy is `no`). Docker compose default is `unless-stopped`, so the container will restart and retry again. This provides a second layer of retry via Docker restart.

**Verification**:
- Confirmed captain-offline has NO TopstepX auth at startup (correct — strategic brain)
- Confirmed captain-command has `_init_topstep()` but it returns `{"account": None}` on failure and continues (correct — Command uses REST API for orders, can function without initial auth)
- Only captain-online MUST have TopstepX auth (it streams market data for signal generation)
- `python3 -c "import captain_online.main; print('Import OK')"` — OK
- 148 unit tests passed in 0.64s

**Escalation note (C2)**: The orchestrator plan flagged a question: "Should TopstepX auth failure be fatal outside market hours (weekends)?" Decision: Proceeded without escalation because (1) the 3-attempt retry with 5s delays handles transient API hiccups, (2) Docker restart provides additional retry attempts, (3) captain-online is always-on and wouldn't be fresh-starting on weekends in normal operation. If weekend startup becomes a use case, a `TOPSTEP_AUTH_OPTIONAL=true` env var could be added later.

---

## Test Results

**148 tests passed** in 0.64s (all unit tests excluding integration/stress/lifecycle).

## Grep Verification Summary

| Check | Result |
|-------|--------|
| Retry constants in questdb_client.py | `_CONNECT_MAX_ATTEMPTS = 3`, `_CONNECT_DELAYS = [1, 2, 4]` |
| `time.sleep` in `_connect()` | Present at line 58, inside retry loop |
| `logger.warning` in `_connect()` | Present at lines 54-57, logs each retry attempt |
| Retry constants in captain-online main.py | `_TOPSTEP_MAX_ATTEMPTS = 3`, `_TOPSTEP_RETRY_DELAY_S = 5` |
| `sys.exit(1)` after MarketStream failure | Present at line 155 |
| `logger.critical` before exit | Present at line 153 |

## Files Modified (2 total)

1. `shared/questdb_client.py` (H2)
2. `captain-online/captain_online/main.py` (C2)
