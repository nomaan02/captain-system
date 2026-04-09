# Concurrency Audit Report

<!--AUDIT-META
worker: ln-628-concurrency-auditor
category: Concurrency
domain: global
scan_path: /home/nomaan/captain-system
score: 4.4
total_issues: 8
critical: 1
high: 2
medium: 2
low: 3
status: completed
run_id: standalone-628-20260409134040
produced_at: 2026-04-09T14:40:40Z
-->

**Auditor:** ln-628-concurrency-auditor
**Date:** 2026-04-09
**Category:** Concurrency
**Scope:** Full codebase — all 3 processes + shared + scripts
**Score:** 4.4 / 10
**Issues:** 8 confirmed (C:1 H:2 M:2 L:3)

---

## Scope

Full-codebase concurrency audit across all Captain System source files:

- `shared/` (9 modules — redis_client, topstep_stream, topstep_client, questdb_client, vault, contract_resolver, vix_provider, journal, trade_source)
- `captain-command/` (api.py, main.py, orchestrator, b2_gui_data_server, b4_tsm_manager, b8_reconciliation, b11_replay_runner, telegram_bot)
- `captain-online/` (main.py, orchestrator, b1_data_ingestion, b7_position_monitor, b7_shadow_monitor, or_tracker)
- `captain-offline/` (main.py, orchestrator, b2_level_escalation, b7_tsm_simulation, b8_cb_params, b8_kelly_update)

7 concurrency checks with two-layer detection (grep candidates -> contextual code review).

**Tech stack:** Python 3.11, threading.Lock, asyncio (FastAPI/uvicorn), psycopg2 (QuestDB PG wire), redis-py, pysignalr (SignalR WebSocket), concurrent.futures.ThreadPoolExecutor.

**Concurrency model:** 3 Docker processes (Offline, Online, Command) sharing QuestDB + Redis. Each process uses background threads for Redis stream reading, WebSocket streaming, and command listening. Command process additionally runs FastAPI/uvicorn async event loop.

---

## Executive Summary

The codebase has **strong locking discipline in recently-added patterns** — `_ws_lock` (WebSocket sessions), `_state_lock` (GUI data server), `QuoteCache._lock`, `TopstepClient._lock`, and all singleton double-checked locks are correctly implemented.

However, **8 confirmed gaps remain** across three categories:

1. **One CRITICAL race** on the API key vault (`store_api_key` does read-modify-write with no lock across Docker-mounted shared volume)
2. **Two HIGH thread-safety gaps** — unguarded module-level globals in api.py, and a read-modify-write on D00 asset universe without cross-process synchronization
3. **Five lower-severity issues** — sync blocking in async handler, unguarded dict iteration, and GIL-dependent truthiness checks

---

## Checks Summary

| # | Check | Status | Findings |
|---|-------|--------|----------|
| 1 | Async/Event-Loop Races | PASS | 0 confirmed |
| 2 | Thread Safety | FAIL | 3 confirmed (H, H→ carried to TOCTOU, L, L) |
| 3 | TOCTOU | FAIL | 3 confirmed (C, H, L) |
| 4 | Deadlock Potential | PASS | 0 confirmed |
| 5 | Blocking I/O in Async | WARN | 1 confirmed (M) |
| 6 | Resource Contention | WARN | 1 confirmed (M) |
| 7 | Cross-Process Races | PASS | 0 confirmed (vault race covered by Check 3) |

---

## Check 1: Async/Event-Loop Races (CWE-362)

**Layer 1 candidates:** 0
**Confirmed:** 0

No read-modify-write patterns across `await` boundaries. The async FastAPI handlers in `api.py` read module-level Python dicts (GIL-atomic per access) and do not modify shared state across await points. WebSocket handler mutates `_ws_sessions` under `_ws_lock`.

---

## Check 2: Thread Safety (CWE-366)

**Layer 1 candidates:** 14
**Confirmed:** 3 (after false-positive filtering)
**False positives filtered:** 11 (properly locked singletons, GIL-atomic simple assignments, write-once-at-startup patterns in locked modules)

### F-002 — Unguarded Module-Level Globals in api.py | HIGH | Effort: S

**File:** `captain-command/captain_command/api.py:135-148, 607-621`
**Status:** CONFIRMED — open since prior focused audit

Three module-level globals written by background threads, read by async endpoints, **no lock:**

| Global | Writer Thread | Reader (async) | Write Line | Read Lines |
|--------|--------------|----------------|-----------|------------|
| `_process_health` | `cmd-orchestrator` via `update_process_health()` | `health()`, `status()`, `processes_status()` | 609 | 176-184, 244, 574 |
| `_api_connections` | `cmd-orchestrator` via `update_api_connections()` | `health()`, `status()`, `processes_status()` | 614-615 | 175-179, 249, 574 |
| `_last_signal_time` | `cmd-signals` via `update_last_signal_time()` | `health()` | 620-621 | 203 |

**Layer 2 reasoning:** `_process_health[role] = info` (line 609) mutates a dict while `health()` may iterate `.items()` / `.values()` — can raise `RuntimeError: dictionary changed size during iteration`. The `_api_connections` swap (line 614) is a reference replacement (GIL-atomic), but `health()` reads 3 separate globals across multiple statements without atomicity. The composite snapshot can be internally inconsistent.

**Escalation check:** Drives health endpoint HALTED detection and circuit breaker status reporting. Classified HIGH (not CRITICAL) because CB logic itself lives in Offline, not here.

**Recommendation:** Add `_api_state_lock = threading.Lock()` covering all three globals. Snapshot atomically in readers.

---

### F-006 — Position List Truthiness Check Without Lock | LOW | Effort: S

**File:** `captain-online/captain_online/blocks/orchestrator.py:120, 127`
**Status:** CONFIRMED — low practical risk under CPython

Main loop reads `self.open_positions` and `self.shadow_positions` without `_position_lock`:

```python
# Line 120 — no lock
if self.open_positions:
    self._run_position_monitor()  # acquires lock internally at line 601

# Line 127 — no lock
if self.shadow_positions:
    self._run_shadow_monitor()   # acquires lock internally at line 612
```

Background command listener thread mutates both lists under `_position_lock` at lines 770-777.

**Layer 2 reasoning:** CPython's GIL makes `bool(list)` atomic. The monitor methods acquire the lock internally, so the worst case is: (a) check sees non-empty, monitor acquires lock and finds empty → no-op, or (b) check sees empty, new position added by background thread → caught next iteration (~1s delay). Neither case causes data corruption.

**Severity:** LOW (GIL-safe in CPython, no data corruption possible, max 1-iteration delay on financial data path).

**Recommendation:** Wrap truthiness check in lock for spec-correctness and non-CPython portability.

---

### F-007 — Write-Once Globals Without Lock | LOW | Effort: S

**File:** `captain-command/captain_command/api.py:419-425`
**Status:** CONFIRMED — negligible risk

`set_event_loop()` and `set_telegram_bot()` assign module-level globals via `global` keyword with no lock. Both are called exactly once at startup before any reader thread runs.

**Recommendation:** No fix needed. Add comment documenting write-once-at-startup invariant.

---

## Check 3: TOCTOU — Time-of-Check Time-of-Use (CWE-367)

**Layer 1 candidates:** 4
**Confirmed:** 3

### F-001 — Vault store_api_key Read-Modify-Write Race | CRITICAL | Effort: M

**File:** `shared/vault.py:78-82`
**Status:** CONFIRMED

```python
def store_api_key(account_id: str, api_key: str):
    vault = load_vault()        # t=0: READ file → decrypt → dict
    vault[account_id] = api_key # t=1: MODIFY in memory
    save_vault(vault)           # t=2: WRITE encrypt → file
```

No file lock, no threading lock, no atomic operation. The vault file lives at a Docker-mounted path (`/captain/vault/keys.vault`) accessible by all 3 containers.

**Layer 2 reasoning:** If process A calls `store_api_key("acct_1", key_1)` and process B calls `store_api_key("acct_2", key_2)` concurrently:
1. A reads vault: `{}`
2. B reads vault: `{}`
3. A writes: `{"acct_1": key_1}`
4. B writes: `{"acct_2": key_2}` — **acct_1 key is lost**

**Escalation:** This is authentication/security code (API key storage) → CRITICAL per unified escalation rule.

**Recommendation:** Add `fcntl.flock()` (or `filelock` library) around the read-modify-write cycle:

```python
import fcntl

def store_api_key(account_id: str, api_key: str):
    lock_path = VAULT_PATH + ".lock"
    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        vault = load_vault()
        vault[account_id] = api_key
        save_vault(vault)
```

---

### F-003 — D00 update_d00_fields Read-Modify-Write | HIGH | Effort: M

**File:** `shared/questdb_client.py:81-99`
**Status:** CONFIRMED

```python
def update_d00_fields(asset_id: str, updates: dict, cur=None) -> None:
    current = read_d00_row(asset_id, cur=c)   # READ latest D00 row
    current.update(updates)                     # MODIFY in memory
    # ... INSERT INTO p3_d00_asset_universe ... # WRITE new row
```

QuestDB has no row-level locking. Multiple processes (Offline updating AIM state, bootstrap scripts) could call this on the same asset_id. Since QuestDB is append-only with "latest row wins" semantics (`ORDER BY last_updated DESC LIMIT 1`), concurrent writes cause last-writer-wins with potential data loss of the first writer's changes.

**Layer 2 reasoning:** In practice, concurrent calls on the same asset are rare — Offline updates AIM fields during scheduled runs, and bootstrap runs once. But the function has no structural protection, and the risk increases if usage expands.

**Recommendation:** Add Redis advisory lock keyed on `d00:{asset_id}`:

```python
def update_d00_fields(asset_id: str, updates: dict) -> None:
    lock_key = f"lock:d00:{asset_id}"
    r = get_redis_client()
    if r.set(lock_key, "1", nx=True, ex=5):
        try:
            # ... existing read-modify-write ...
        finally:
            r.delete(lock_key)
```

---

### F-008 — Vault TOCTOU on File Existence Check | LOW | Effort: S

**File:** `shared/vault.py:48-50`
**Status:** CONFIRMED — minimal practical risk

```python
def load_vault() -> dict:
    if not os.path.exists(VAULT_PATH):  # CHECK
        return {}
    with open(VAULT_PATH, "rb") as f:   # USE — file could vanish between check and open
        raw = f.read()
```

**Layer 2 reasoning:** The vault file is in a Docker volume, not a world-writable temp directory. No attacker symlink risk. The race window is negligible. However, the pattern is non-idiomatic.

**Recommendation:** Replace with try/except:
```python
def load_vault() -> dict:
    try:
        with open(VAULT_PATH, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return {}
```

---

## Check 4: Deadlock Potential (CWE-833)

**Layer 1 candidates:** 6 (files with multiple lock acquisitions)
**Confirmed:** 0

All lock patterns across the codebase use single locks with `with` context managers — **no nested locking observed**:

| Lock | File | Protects | Nesting? |
|------|------|----------|----------|
| `_ws_lock` | api.py | `_ws_sessions` | No |
| `_state_lock` | b2_gui_data_server.py | 3 GUI globals | No |
| `_position_lock` | online/orchestrator.py | open/shadow positions | No |
| `QuoteCache._lock` | topstep_stream.py | quote cache dict | No |
| `UserStream._lock` | topstep_stream.py | account/position caches | No |
| `TopstepClient._lock` | topstep_client.py | auth token | No |
| `_client_lock` | redis_client.py | Redis singleton | No |
| `_cache_lock` | contract_resolver.py | contract ID cache | No |
| `ORTracker._lock` | or_tracker.py | OR session dict | No |

No lock holds I/O or external calls. All lock scopes are brief (dict read/write, set add/discard).

---

## Check 5: Blocking I/O in Async Context (CWE-400)

**Layer 1 candidates:** 8 (`time.sleep` calls across codebase)
**Confirmed:** 1
**False positives filtered:** 7 (all in synchronous background threads, not async context)

### F-004 — route_command() Sync in Async WebSocket Handler | MEDIUM | Effort: S

**File:** `captain-command/captain_command/api.py:385`
**Status:** CONFIRMED — open since prior focused audit

`route_command(data, gui_push_fn=gui_push)` is called synchronously inside `async def websocket_endpoint()`. For trade confirmation commands, `route_command` performs a blocking psycopg2 INSERT into QuestDB. This blocks the uvicorn event loop for ~5-50ms per command, stalling all concurrent WebSocket sends and HTTP responses.

**Layer 2 reasoning:** Trade confirmations are the hot path — when a signal fires and the user clicks TAKEN, this blocks. Under normal load (1-2 concurrent users), impact is minor. Under batch signal processing (10 assets × 3 sessions), blocking could stack.

**Recommendation:**
```python
await asyncio.to_thread(route_command, data, gui_push_fn=gui_push)
```

**False positives filtered (not in async context):**
- `topstep_stream.py:300,568` — `time.sleep(1)` in sync `update_token()` method
- `b4_tsm_manager.py:447` — `time.sleep(attempt+1)` in sync retry loop
- `captain-command/orchestrator.py:181,225` — `time.sleep(backoff)` in daemon threads
- `captain-online/orchestrator.py:727` — `time.sleep(backoff)` in daemon thread
- `b11_replay_runner.py:510` — `time.sleep()` in replay tick simulation thread

---

## Check 6: Resource Contention (CWE-362)

**Layer 1 candidates:** 5
**Confirmed:** 1
**False positives filtered:** 4 (QuestDB WAL handles concurrent appends; Redis Streams use consumer groups correctly)

### F-005 — _ws_sessions Iteration Without Lock in status() | MEDIUM | Effort: S

**File:** `captain-command/captain_command/api.py:246-248`
**Status:** CONFIRMED — open since prior focused audit

```python
async def status():
    return JSONResponse({
        ...
        "active_ws_sessions": {
            uid: len(sockets) for uid, sockets in _ws_sessions.items()  # NO LOCK
        },
```

`gui_push()` (line 455), `websocket_endpoint()` (lines 331, 362, 403), and `_safe_ws_send()` (line 479) all mutate `_ws_sessions` under `_ws_lock`. The `status()` endpoint skips the lock → potential `RuntimeError: dictionary changed size during iteration`.

**Recommendation:** Snapshot under lock:
```python
with _ws_lock:
    ws_snapshot = {uid: len(s) for uid, s in _ws_sessions.items()}
```

**False positives filtered (not contention bugs):**
- D03 `p3_d03_trade_outcome_log` concurrent inserts from Online B7 + Command — QuestDB WAL handles append-only writes; no "table busy" errors observed on D03
- D08 `p3_d08_tsm_state` concurrent inserts — retry mechanism at `b4_tsm_manager.py:444` correctly handles QuestDB WAL commit contention
- Redis Stream consumer groups — `xreadgroup` + `ack_message` pattern correctly ensures each message processed by exactly one consumer per group
- ThreadPoolExecutor in `b1_data_ingestion.py:365` — pool-scoped, not shared; each task fetches independent asset data

---

## Check 7: Cross-Process & Invisible Side Effects (CWE-362, CWE-421)

**Layer 1 candidates:** 3
**Confirmed:** 0 (vault cross-process race already covered by F-001 in Check 3)

**Resource Inventory:**

| Resource | Exclusive? | Process A | Process B | Process C | Sync? |
|----------|-----------|-----------|-----------|-----------|-------|
| QuestDB tables | No (WAL) | Offline writes D02,D04,D05,D12,D25 | Online writes D03 | Command writes D08,D16 | WAL handles |
| Redis Streams | No (consumer groups) | Offline reads outcomes/commands | Online reads commands | Command reads signals | Consumer groups |
| Redis Pub/Sub | No (broadcast) | Offline publishes status | Online publishes signals/status | Command publishes commands | By design |
| Vault file | YES | Reads keys | Reads keys | Reads/writes keys | **NO SYNC** (F-001) |
| SQLite journals | No (1 per process) | Own journal | Own journal | Own journal | Process-isolated |

The vault file is the only exclusive cross-process resource without synchronization. This is fully covered by F-001 above.

Redis Streams use consumer groups with message acknowledgment — properly designed for multi-process consumption. QuestDB WAL mode handles concurrent writers at the storage layer. SQLite journals are process-isolated (one per container).

---

## Correctly Implemented Patterns

| Pattern | Location | Assessment |
|---------|----------|------------|
| `_state_lock` atomic snapshot | b2_gui_data_server.py:112-115 | Correct — reads 3 globals under one lock |
| `_ws_lock` full lifecycle | api.py:331,362,403,455,479 | Correct — all mutations guarded |
| `QuoteCache._lock` | topstep_stream.py:82,92,98,105 | Correct — defensive copies returned |
| `UserStream._lock` | topstep_stream.py:508,513,673,687 | Correct — account/position caches protected |
| `TopstepClient._lock` | topstep_client.py:118,132,147 | Correct — token lifecycle protected |
| Double-checked locking | redis_client.py:39-43, topstep_client.py:427-430 | Correct — singleton with lock |
| `_position_lock` write path | online/orchestrator.py:578,601,612,770 | Correct — all mutations locked |
| `ORTracker._lock` | or_tracker.py:232,247,252,282,302,320 | Correct — all session mutations locked |
| `_cache_lock` | contract_resolver.py:46,53,60,92 | Correct — cache updates locked |
| Redis consumer groups | redis_client.py:94-127 | Correct — `xreadgroup` + `ack_message` |
| ThreadPoolExecutor scoping | b1_data_ingestion.py:365-379 | Correct — pool-scoped, independent tasks |
| Daemon thread lifecycle | all orchestrators | Correct — `self.running` flag + `join(timeout)` |

---

## Scoring Breakdown

| Severity | Count | Weight | Subtotal |
|----------|-------|--------|----------|
| CRITICAL | 1 | 2.0 | 2.0 |
| HIGH | 2 | 1.0 | 2.0 |
| MEDIUM | 2 | 0.5 | 1.0 |
| LOW | 3 | 0.2 | 0.6 |
| **Penalty** | | | **5.6** |
| **Score** | | | **4.4 / 10** |

---

## Findings Summary

| Sev | ID | Check | Location | Issue | Effort |
|-----|-----|-------|----------|-------|--------|
| CRITICAL | F-001 | TOCTOU | shared/vault.py:78-82 | store_api_key read-modify-write race — API key loss possible across Docker containers | M |
| HIGH | F-002 | Thread Safety | captain-command/.../api.py:607-621 | _process_health/_api_connections/_last_signal_time written by bg threads without lock | S |
| HIGH | F-003 | TOCTOU | shared/questdb_client.py:81-99 | update_d00_fields read-modify-write on D00 without cross-process sync | M |
| MEDIUM | F-004 | Blocking I/O | captain-command/.../api.py:385 | route_command() sync psycopg2 call inside async WebSocket handler | S |
| MEDIUM | F-005 | Contention | captain-command/.../api.py:246-248 | _ws_sessions.items() iteration without _ws_lock in status() | S |
| LOW | F-006 | Thread Safety | captain-online/.../orchestrator.py:120,127 | Position list truthiness check without lock (GIL-safe in CPython) | S |
| LOW | F-007 | Thread Safety | captain-command/.../api.py:419-425 | Write-once globals without lock (startup only) | S |
| LOW | F-008 | TOCTOU | shared/vault.py:48-50 | os.path.exists check before open (non-idiomatic) | S |

---

## Prioritized Fix Plan

| Priority | ID | Severity | Fix | Effort |
|----------|----|----------|-----|--------|
| 1 | F-001 | CRITICAL | Add `fcntl.flock()` around vault read-modify-write cycle | M |
| 2 | F-002 | HIGH | Add `_api_state_lock` for 3 unguarded globals; snapshot atomically in readers | S |
| 3 | F-003 | HIGH | Add Redis advisory lock `lock:d00:{asset_id}` around read-modify-write | M |
| 4 | F-004 | MEDIUM | `await asyncio.to_thread(route_command, ...)` | S |
| 5 | F-005 | MEDIUM | Snapshot `_ws_sessions` under `_ws_lock` in `status()` | S |
| 6 | F-006 | LOW | Wrap truthiness check in `_position_lock` | S |
| 7 | F-008 | LOW | Replace `os.path.exists` → try/except `FileNotFoundError` | S |
| 8 | F-007 | LOW | Add comment documenting write-once invariant | S |

**Total estimated effort:** ~4-6 hours for all 8 fixes (priorities 1-3 require careful testing).
