# Concurrency Audit Report — Captain System

**Auditor:** ln-628-concurrency-auditor  
**Date:** 2026-04-09  
**Category:** Concurrency  
**Score:** 5.3 / 10  
**Issues:** 14 confirmed (C:1 H:1 M:5 L:7)

---

## Scope

Full codebase audit across 3 Docker processes (captain-online, captain-offline, captain-command) plus shared libraries. 7 concurrency checks with two-layer detection (grep candidates -> contextual code review).

**Tech stack:** Python 3, threading, asyncio (FastAPI/uvicorn), psycopg2 (QuestDB), redis-py, pysignalr.

**Exclusions:** test files, scripts in `scripts/` (except where they share runtime modules).

---

## Executive Summary

The codebase has **solid locking patterns** in its core shared libraries (`topstep_client.py`, `redis_client.py`, `or_tracker.py`, `topstep_stream.py` UserStream). However, it has **one critical race** in the Offline orchestrator that can silently corrupt AIM meta-weights (D02) used for live position sizing, plus several medium-severity thread-safety gaps in the Command API layer where background threads share globals with the FastAPI async event loop without synchronization.

No TOCTOU vulnerabilities were found. No deadlocks in the classical two-lock sense exist, but one lock is held during blocking network I/O creating a starvation risk.

---

## Check 1: Async/Event-Loop Races (CWE-362)

### AR-01 — Telegram Bot Mute/Rate State Race | MEDIUM | Effort: S

**File:** `captain-command/captain_command/blocks/telegram_bot.py:39,246`  
**Status:** CONFIRMED

`_rate_window` (defaultdict) and `_mute_until` (dict) are module-level mutable state accessed from two different threads without synchronization:
- **Thread A:** `cmd-orchestrator` / `cmd-signals` threads call `send_message()` -> `_check_rate_limit()` reads/writes `_rate_window`
- **Thread B:** `telegram-bot` async loop calls `cmd_mute` handler -> `_set_mute()` / `_is_muted()` reads/writes/deletes from `_mute_until`

The list reassignment + append in `_check_rate_limit` is not atomic. A concurrent `del _mute_until[key]` from two threads on the same key raises `KeyError`.

**Recommendation:** Add a `threading.Lock()` guarding `_rate_window` and `_mute_until`. 3 call sites to wrap.

---

### AR-02 — TopstepStream State/Failure Counter Race | LOW | Effort: M

**File:** `shared/topstep_stream.py` — `_state`, `_rapid_failures`, `_last_open_time`

`_state` is written by `stop()` (main thread) and `_async_on_close()` (stream event loop thread) with no lock. `_rapid_failures += 1` in `_async_on_close` is a non-atomic LOAD+ADD+STORE under CPython. If `update_token()` resets `_rapid_failures = 0` concurrently with an increment, the counter may hold a stale value.

Consequence is benign (at most one extra reconnect attempt), not a financial correctness issue.

**Recommendation:** Use `threading.Lock` for `_state` and `_rapid_failures` writes, or funnel all mutations through `loop.call_soon_threadsafe`.

---

## Check 2: Thread Safety (CWE-366)

### TS-01 — `_api_connections` Unguarded Cross-Thread Access | MEDIUM | Effort: S

**File:** `captain-command/captain_command/api.py:476`

Module-level dict `_api_connections` is written by `update_api_connections()` from the `cmd-orchestrator` background thread and read by `health()` / `status()` on the FastAPI async event loop. No lock guards access. While CPython's GIL makes the reference swap practically safe, the pattern is fragile and non-portable.

**Recommendation:** Add a `threading.Lock()` covering `_api_connections` and `_last_signal_time` (see TS-02). One lock, 4 call sites.

---

### TS-02 — `_last_signal_time` Unguarded Cross-Thread Access | LOW | Effort: S

**File:** `captain-command/captain_command/api.py:482`

Module-level `str | None` written from `cmd-signals` thread, read from async `health()`. Scalar reassignment is GIL-atomic in CPython but unsynchronized.

**Recommendation:** Same lock as TS-01.

---

### TS-03 — `_pipeline_stage` Unguarded Cross-Thread Access | LOW | Effort: S

**File:** `captain-command/captain_command/blocks/b2_gui_data_server.py:65`

Written by `cmd-redis` thread via `set_pipeline_stage()`, read by `build_dashboard_snapshot()` on the event loop. Worst case: dashboard shows a one-iteration-stale pipeline stage.

**Recommendation:** Add a lock in `b2_gui_data_server.py` or push via `asyncio.run_coroutine_threadsafe`.

---

### TS-04 — Telegram Bot Rate/Mute Dict Race | MEDIUM | Effort: S

*Same finding as AR-01 — cross-referenced. See Check 1.*

---

### TS-05 — VIX Provider Mtime Check Outside Lock | LOW | Effort: S

**File:** `shared/vix_provider.py:41-55`

`_ensure_loaded()` checks file mtime outside the lock, then enters `with _lock: _load_all()` without rechecking. At worst, VIX data is reloaded twice concurrently (wasteful but not corrupting, since `_load_all()` runs under lock).

**Recommendation:** Move the mtime check inside the lock.

---

### TS-06 — Contract Resolver Benign Cache Race | LOW | Effort: S

**File:** `shared/contract_resolver.py:24-60`

`resolve_contract_id` reads cache outside lock as optimization. Two threads missing simultaneously produce redundant API lookups but identical results. Idempotent write under lock.

**Recommendation:** Document the intentional benign race via code comment. No code change needed.

---

## Check 3: TOCTOU (CWE-367)

**All 8 candidates classified as FALSE POSITIVE.**

All `os.path.exists()` sites are either:
- Read-only config files at startup (vault.py, compliance_gate.json, TSM configs)
- Diagnostic/validation paths with safe defaults on failure
- Script-only paths not reachable from running services

No TOCTOU vulnerabilities found.

| File | Reason for FP |
|------|---------------|
| `shared/vault.py:48` | Bootstrap-only, exception caught on open |
| `b2_gui_data_server.py:911` | Static config, safe fallback to MANUAL mode |
| `b3_api_adapter.py:488` | Static config, safe fallback to allowed=False |
| `b4_tsm_manager.py:195` | Error log guard, exception caught |
| `b10_data_validation.py:163-183` | Diagnostic only, not control flow |
| `shared/bar_cache.py:122` | `__main__` block, not reachable at runtime |
| `shared/replay_engine.py:245` | Startup config lookup, immediate open |
| `scripts/init_all.py:87` | Script-only, not a running service |

---

## Check 4: Deadlock Potential (CWE-833)

### DL-01 — Position Lock Held During Blocking Network I/O | MEDIUM | Effort: S

**File:** `captain-online/captain_online/blocks/orchestrator.py:608,766`

`_position_lock` is held while `monitor_positions()` and `monitor_shadow_positions()` call `resolve_position()`, which executes up to 3 synchronous network round-trips:
1. QuestDB INSERT (`_write_trade_outcome`)
2. Redis XADD (`_publish_trade_outcome`)
3. QuestDB INSERT (`_update_capital_silo`)

While the lock is held, the `_command_listener` thread is blocked from acquiring the same lock to register TAKEN/SKIPPED signals. Under QuestDB or Redis latency spikes, the TAKEN confirmation can be delayed by several seconds.

Not a classical deadlock (single lock, no nesting), but a **lock starvation** / **priority inversion** issue on the critical TAKEN signal path.

**Recommendation:** Snapshot-then-release pattern:
```python
with self._position_lock:
    snapshot = list(self.open_positions)
resolved = monitor_positions(snapshot, ...)  # I/O outside lock
with self._position_lock:
    for pos in resolved:
        self.open_positions.remove(pos)
```

---

### False Positives (4)

| File | Lock(s) | Reason |
|------|---------|--------|
| `b11_replay_runner.py:207` | Single `_lock` | No nesting, no I/O under lock |
| `or_tracker.py:220` | Single `_lock` | All acquisitions are brief dict ops |
| `topstep_stream.py:79,171,495` | 3 independent instance locks | Never simultaneously held |
| `topstep_client.py:98,405` | Instance + module lock | Different concerns, never nested |

---

## Check 5: Blocking I/O in Async Context (CWE-400)

### BIO-01 — Sync QuestDB Write Blocks Event Loop | MEDIUM | Effort: S

**File:** `captain-command/captain_command/api.py:252`

`route_command(data, gui_push_fn=gui_push)` is called synchronously inside `async def websocket_endpoint`. For `TAKEN_SKIPPED` commands, this calls `_log_trade_confirmation` which executes a psycopg2 INSERT (~5-50ms). This blocks the uvicorn event loop for every command-type WebSocket message.

**Recommendation:**
```python
await asyncio.to_thread(route_command, data, gui_push_fn=gui_push)
```

---

### BIO-02 — Telegram urllib Blocking (Future Risk) | LOW | Effort: S

**File:** `captain-command/captain_command/blocks/telegram_bot.py:608`

`urllib.request.urlopen(req, timeout=10)` is synchronous with a 10-second timeout. Currently called only from the `cmd-orchestrator` daemon thread (safe). Flagged as LOW because any future call from async context would block the event loop for up to 10 seconds.

**Recommendation:** Replace with `httpx.AsyncClient` if Telegram sends ever move to async context.

---

### False Positives (9)

All `time.sleep()` calls in orchestrators and stream modules run in dedicated daemon threads, not the asyncio event loop. The subprocess calls in `api_git_pull` run in FastAPI's sync threadpool (endpoint is `def`, not `async def`).

---

## Check 6: Resource Contention (CWE-362)

### RC-01 — QuestDB No Connection Pool | MEDIUM | Effort: S

**File:** `shared/questdb_client.py`

`get_cursor()` creates a new psycopg2 TCP connection per call with no pooling. During busy sessions (10 assets, session open), this creates connection storms on port 8812 and adds 5-20ms per write from TCP handshake overhead. Connection count is unbounded.

**Recommendation:** Use `psycopg2.pool.ThreadedConnectionPool(minconn=2, maxconn=10)`. Transparent to callers — `get_cursor()` API unchanged.

---

### RC-02 — Vault Non-Atomic Read-Modify-Write | LOW | Effort: S

**File:** `shared/vault.py:61-78`

`store_api_key()` does load -> mutate -> save without a lock. Two concurrent callers would race, last-writer-wins. In practice this is a bootstrap-only operation with sequential callers.

**Recommendation:** Add a module-level `threading.Lock()` around the load/save pair.

---

### False Positives (2)

| File | Reason |
|------|--------|
| `b7_notifications.py:115` | `_quiet_queue_lock` correctly guards all access; flushes outside lock |
| `shared/redis_client.py` | redis-py's internal `ConnectionPool` is thread-safe by design |

---

## Check 7: Cross-Process & Invisible Side Effects (CWE-362, CWE-421)

### CP-01 — D02 AIM Meta-Weights Write Race (Offline) | CRITICAL | Effort: S

**File:** `captain-offline/captain_offline/blocks/orchestrator.py:63,526`

**THIS IS THE MOST IMPORTANT FINDING IN THIS AUDIT.**

The Offline orchestrator runs two threads that both write to `p3_d02_aim_meta_weights` with **zero coordination**:

| Thread | Trigger | Write Path |
|--------|---------|------------|
| `_redis_thread` | Every trade/signal outcome | `_handle_trade_outcome` -> `run_dma_update()` -> INSERT D02 |
| Main/scheduler | Daily 16:00 ET | `_run_daily` -> `run_aim_lifecycle()` -> `run_drift_detection()` -> INSERT D02 |

Both use independent `get_cursor()` calls (separate connections). QuestDB is append-only — both rows land. The "latest" row is determined by `LATEST ON last_updated PARTITION BY aim_id, asset_id`. If the scheduler writes a stale `inclusion_probability` **after** the DMA update wrote the fresh value, the stale value wins. The next session reads wrong AIM weights for Kelly sizing and trade direction.

The race window is narrow (daily close at 16:00 ET when late trade outcomes may still be arriving) but the consequence is **silent financial data corruption**.

**Recommendation:** Add `self._d02_write_lock = threading.RLock()` in `__init__`. Acquire around `run_dma_update()` in both `_handle_trade_outcome` and `_handle_signal_outcome`, and around `run_aim_lifecycle()` + `run_drift_detection()` in `_run_daily`.

---

### CP-02 — Git Pull/Rebuild No Concurrency Guard | HIGH | Effort: S

**File:** `captain-command/captain_command/api.py:825`

`/api/system/git-pull` has no guard against concurrent calls. Two simultaneous requests can:
1. Both run `git pull` (git's `.git/index.lock` causes one to fail)
2. Both decide `needs_rebuild = True` and launch two `_rebuild` threads
3. Two simultaneous `docker compose up -d --build` calls corrupt the build cache and leave containers in an inconsistent state mid-trade

**Recommendation:** Add `_rebuild_lock = threading.Lock()` with non-blocking `acquire(blocking=False)`. Return error if already held.

---

### False Positives / NEEDS-CONTEXT (2)

| ID | File | Status | Reason |
|----|------|--------|--------|
| CP-03 | `b7_position_monitor.py:284` D16 read-modify-write | NEEDS-CONTEXT (LOW) | Currently serial in main thread; becomes a race only if position concurrency increases |
| CP-04 | Redis Stream ordering | FP | Consumer groups provide strict FIFO; single writer per stream |

---

## Scoring Breakdown

| Check | Score | Findings |
|-------|-------|----------|
| 1. Async Races | 7/10 | 2 confirmed (M, L) |
| 2. Thread Safety | 6/10 | 5 confirmed (2M, 3L) + 1 cross-ref |
| 3. TOCTOU | 10/10 | 0 confirmed |
| 4. Deadlock Potential | 7/10 | 1 confirmed (M) |
| 5. Blocking I/O | 7/10 | 2 confirmed (M, L) |
| 6. Resource Contention | 7/10 | 2 confirmed (M, L) |
| 7. Cross-Process Races | 3/10 | 2 confirmed (C, H) |
| **Weighted Average** | **5.3/10** | **14 total (C:1 H:1 M:5 L:7)** |

---

## Prioritized Fix Plan

| Priority | ID | Severity | File | Fix | Effort |
|----------|----|----------|------|-----|--------|
| 1 | CP-01 | CRITICAL | offline/orchestrator.py | Add `_d02_write_lock` around D02 write paths | S |
| 2 | CP-02 | HIGH | api.py | Add `_rebuild_lock` with non-blocking acquire | S |
| 3 | DL-01 | MEDIUM | online/orchestrator.py | Snapshot positions outside lock, do I/O, re-acquire | S |
| 4 | BIO-01 | MEDIUM | api.py:252 | `await asyncio.to_thread(route_command, ...)` | S |
| 5 | TS-01+02 | MEDIUM+LOW | api.py | Add one lock for `_api_connections` + `_last_signal_time` | S |
| 6 | AR-01/TS-04 | MEDIUM | telegram_bot.py | Add one lock for `_rate_window` + `_mute_until` | S |
| 7 | RC-01 | MEDIUM | questdb_client.py | `psycopg2.pool.ThreadedConnectionPool` | S |
| 8 | TS-03 | LOW | b2_gui_data_server.py | Lock or `run_coroutine_threadsafe` for `_pipeline_stage` | S |
| 9 | AR-02 | LOW | topstep_stream.py | Lock `_state` + `_rapid_failures` mutations | M |
| 10 | TS-05 | LOW | vix_provider.py | Move mtime check inside lock | S |
| 11 | RC-02 | LOW | vault.py | Lock around load/save pair | S |
| 12 | TS-06 | LOW | contract_resolver.py | Document intentional benign race | S |
| 13 | BIO-02 | LOW | telegram_bot.py | Replace urllib with httpx if moved to async | S |

**Total estimated effort:** ~6-8 hours for all 13 fixes. Priorities 1-2 should be fixed before next NY session open.

---

## Correctly Implemented Patterns (Positive Observations)

These areas were audited and found to be **correctly synchronized**:

| Component | Pattern | Assessment |
|-----------|---------|------------|
| `shared/topstep_client.py` | Token refresh double-checked locking | Correct |
| `shared/redis_client.py` | Singleton with `_client_lock` | Correct |
| `shared/topstep_stream.py` UserStream | `_lock` on account/position cache | Correct |
| `captain-online/blocks/or_tracker.py` | `_lock` on all dict ops, no I/O under lock | Correct |
| `captain-command/blocks/b11_replay_runner.py` | `_lock` on session registry, DB outside lock | Correct |
| `captain-command/blocks/b7_notifications.py` | `_quiet_queue_lock` with flush-outside-lock | Correct |
| Redis Streams cross-process | Consumer groups with explicit ack | Correct |
| `api.py gui_push()` | `asyncio.run_coroutine_threadsafe` | Correct |
