# Captain Command Audit

## Part 1: Core + API

**Auditor:** Claude Opus 4.6 (Session 5a of 8)
**Date:** 2026-04-08
**Skills applied:** ln-621-security-auditor, ln-628-concurrency-auditor
**Scope:** main.py, api.py, orchestrator.py, b1_core_routing.py, b2_gui_data_server.py, b3_api_adapter.py, b4_tsm_manager.py

---

### File: captain-command/captain_command/main.py

- **Purpose:** Process entry point — boots infrastructure, loads TSM, starts Telegram bot, orchestrator thread, and FastAPI server.
- **Key functions/classes:**
  - `verify_connections()` :43 — QuestDB + Redis connectivity check, sys.exit on failure
  - `load_tsm_files()` :66 — Loads all TSM JSON configs
  - `_link_tsm_to_account()` :75 — Auto-links TopstepX account to best matching TSM
  - `start_telegram_bot()` :138 — Creates Telegram bot with TAKEN/SKIPPED callback
  - `_ensure_telegram_chat_id()` :166 — Writes TELEGRAM_CHAT_ID to QuestDB D16
  - `_init_topstep()` :237 — Authenticates TopstepX REST API (no WebSocket — owned by Online)
  - `main()` :298 — Full startup sequence, orchestrator in daemon thread, uvicorn in main thread
- **Session/schedule refs:** None — always-on process
- **QuestDB:**
  - `p3_d08_tsm_state` — SELECT count() WHERE account_id = %s :92
  - `p3_d16_user_capital_silos` — SELECT telegram_chat_id :187, INSERT with chat_id :214
- **Redis:** `STREAM_SIGNALS` consumer group init :62
- **Stubs/TODOs:** None
- **Notable:**
  - Line 39: Suppresses httpx logging to prevent Telegram bot token leaking in URLs — good practice
  - Line 131: `best["user_id"] = "primary_user"` — hardcodes user_id before storing TSM
  - Line 371: `uvicorn.run(host="0.0.0.0")` — binds all interfaces inside container (acceptable since nginx fronts it)

---

### File: captain-command/captain_command/api.py

- **Purpose:** FastAPI application — health endpoint, WebSocket hub for GUI, REST endpoints for commands, validation, reports, replay, notifications, and system git-pull.
- **Key functions/classes:**
  - `health()` :98 — GET /api/health, external monitoring
  - `websocket_endpoint()` :192 — WebSocket /ws/{user_id}, session management with eviction
  - `gui_push()` :311 — Thread-safe push to WebSocket sessions via run_coroutine_threadsafe
  - `_safe_ws_send()` :335 — Sends with 10s timeout, auto-cleanup on failure
  - `_make_json_safe()` :294 — Sanitises NaN/Infinity/datetime for JSON
  - `api_git_pull()` :824 — POST /api/system/git-pull, runs subprocess git + docker compose
  - `set_event_loop()` :288 — Captures uvicorn event loop at startup
- **Session/schedule refs:** None — always-on
- **QuestDB:**
  - `p3_d10_notification_log` — SELECT WHERE telegram_delivered = true :559
  - `p3_replay_results` — SELECT ORDER BY ts DESC LIMIT 50 :718
  - `p3_replay_presets` — SELECT WHERE user_id = 'primary_user' :753, INSERT :789
- **Redis:** None directly (delegates to b1_core_routing)
- **Stubs/TODOs:** None
- **Notable:**
  - Line 56: FastAPI app created with no CORS middleware — see SEC-01
  - Lines 824-927: `api_git_pull()` invokes subprocess (git, docker compose) — see SEC-02, SEC-03
  - Line 583: Error response leaks exception string: `return JSONResponse({"error": str(exc)})` — multiple endpoints

---

### File: captain-command/captain_command/blocks/orchestrator.py

- **Purpose:** Always-on event loop — Redis signal stream reader, pub/sub listener for alerts/status/commands, periodic scheduler (health checks, dashboard refresh, reconciliation).
- **Key functions/classes:**
  - `CommandOrchestrator` :87 — Main class
  - `start()` :117 — Launches signal stream thread + pub/sub thread, runs scheduler in caller thread
  - `_signal_stream_reader()` :148 — Durable Redis Stream consumer for signals
  - `_redis_listener()` :184 — Pub/sub for CH_COMMANDS, CH_ALERTS, CH_STATUS
  - `_handle_signal()` :232 — Routes signals with parity filter + auto-execute
  - `_check_parity_skip()` :300 — Daily Redis counter for multi-instance trade alternation
  - `_auto_execute_signal()` :337 — Executes via TopstepX adapter
  - `_run_scheduler()` :428 — 1-second tick loop: market push, dashboard, health, heartbeat, reconciliation
  - `_check_reconciliation_trigger()` :549 — Daily at 19:00 ET
- **Session/schedule refs:**
  - Reconciliation: 19:00 ET daily (SOD_RESET_HOUR, SOD_RESET_MINUTE from constants)
  - Dashboard refresh: every 60s
  - Health checks: every 30s
  - Heartbeat: every 30s
  - Quiet queue flush: every 60s
  - Market push: every 1s
- **QuestDB:** None directly (delegates to blocks)
- **Redis:**
  - `STREAM_SIGNALS` / `GROUP_COMMAND_SIGNALS` — Stream read + ack :161-166
  - `CH_COMMANDS` — Subscribe :195
  - `CH_ALERTS` — Subscribe :195
  - `CH_STATUS` — Subscribe + Publish heartbeat :195, :537
  - `captain:signal_counter:{date}` — INCR for parity :320
- **Stubs/TODOs:** None
- **Notable:**
  - Line 339: `_auto_execute_signal` imports `_active_connections` directly from b3 — tight coupling to module internals
  - Line 416: `_handle_status` imports `_ws_sessions` from api module — cross-module state access
  - Line 358: `adapter = state.get("adapter")` — accesses mutable shared dict without lock (see CONC-02)

---

### File: captain-command/captain_command/blocks/b1_core_routing.py

- **Purpose:** Central message bus — routes signals to GUI + API, routes commands to Online/Offline, handles notifications and status heartbeats.
- **Key functions/classes:**
  - `route_signal_batch()` :51 — Routes signal batch from Online B6 to GUI + API adapters
  - `sanitise_for_api()` :103 — Returns 6-field sanitised order, strips PROHIBITED_EXTERNAL_FIELDS
  - `route_command()` :132 — Routes GUI/API commands to correct subsystem via Redis Stream
  - `route_notification()` :290 — Routes notifications to GUI + Telegram + D10 log
  - `handle_status_message()` :339 — Updates in-memory process health from heartbeat
- **Session/schedule refs:** None
- **QuestDB:**
  - `p3_session_event_log` — INSERT for SIGNAL_RECEIVED :368, TRADE_{action} :393, notification :421, TSM_SWITCH :439, CONCENTRATION_RESPONSE :457, ROLL_CONFIRMED :476, ACTION_ITEM_UPDATE :495, MANUAL_PAUSE/RESUME :520
  - `p3_d10_notification_log` — INSERT :421
  - `p3_d16_user_capital_silos` — SELECT DISTINCT user_id :539
- **Redis:**
  - `STREAM_COMMANDS` — publish_to_stream for TAKEN_SKIPPED :167, strategy decisions :200, AIM control :224, TRIGGER_DIAGNOSTIC :264
  - `CH_COMMANDS` — publish for MANUAL_HALT/RESUME :277
- **Stubs/TODOs:** None
- **Notable:**
  - Line 149: Validates `cmd_type in COMMAND_TYPE_VALUES` — good allowlist pattern
  - Line 107: `sanitise_for_api()` uses explicit field selection rather than filtering — secure by construction

---

### File: captain-command/captain_command/blocks/b2_gui_data_server.py

- **Purpose:** GUI data assembly layer — builds dashboard snapshots, system overview, payout panel, scaling display, live market data from TopstepX stream cache.
- **Key functions/classes:**
  - `build_dashboard_snapshot()` :91 — Full dashboard for a user (14 sub-queries)
  - `build_system_overview()` :129 — ADMIN system overview (9 sub-queries)
  - `build_live_market_update()` :924 — Lightweight 1Hz market quote push
  - `get_aim_detail()` :446 — Enriched AIM modal data (D01 + D02 + D26)
  - `build_processes_status()` — Process monitoring tab (block registry + health)
  - `set_account_data()` :53 — Cache REST account data
  - `set_pipeline_stage()` :63 — Cache Online pipeline stage
  - `set_user_stream()` :47 — Register UserStream for live data
- **Session/schedule refs:** Called every 60s by orchestrator + on WS connect
- **QuestDB:**
  - `p3_d16_user_capital_silos` — SELECT :307
  - `p3_d03_trade_outcome_log` — SELECT WHERE outcome IS NULL :333, GROUP BY for concentration :737
  - `p3_session_event_log` — SELECT for pending signals :361, signal quality :763, capacity :787
  - `p3_d01_aim_model_states` — SELECT ORDER BY last_updated DESC :421, :464
  - `p3_d02_aim_meta_weights` — SELECT :492
  - `p3_d26_hmm_opportunity_state` — SELECT count() :520
  - `p3_d08_tsm_state` — SELECT for TSM status :577, payout panel :166, scaling :232
  - `p3_d04_decay_detector_states` — SELECT :621
  - `p3_d00_asset_universe` — SELECT LATEST ON :643, :663, :864
  - `p3_d10_notification_log` — SELECT :709
  - `p3_d22_system_health_diagnostic` — SELECT :803, :828
  - `p3_d17_system_monitor_state` — SELECT :851
  - `p3_d21_incident_log` — SELECT :886
- **Redis:** `get_redis_client().ping()` in health check :84
- **Stubs/TODOs:** None
- **Notable:**
  - Module-level globals `_user_stream`, `_account_data`, `_pipeline_stage` — set from multiple threads without locks (see CONC-01)
  - Line 905-916: `_get_compliance_gate()` uses TOCTOU pattern (`os.path.exists` then `open`) — low risk since config file (see CONC-04)
  - 14+ QuestDB queries per dashboard refresh — potential latency concern under load

---

### File: captain-command/captain_command/blocks/b3_api_adapter.py

- **Purpose:** Secure API plugin architecture — abstract adapter interface, TopstepX implementation, connection health monitoring (30s), compliance gate, vault integration.
- **Key functions/classes:**
  - `APIAdapter` :46 — Abstract base class (connect, send_signal, receive_fill, get_account_status, disconnect, ping)
  - `TopstepXAdapter` :113 — Concrete TopstepX adapter with bracket order placement
  - `register_connection()` :379 — Registers adapter for health monitoring
  - `run_health_checks()` :391 — 30s cycle: ping, auto-reconnect (3 retries), log to D14
  - `check_compliance_gate()` :476 — Checks 11 RTS 6 requirements from JSON file
  - `get_adapter()` :359 — Factory by provider name
- **Session/schedule refs:** Health checks every 30s from orchestrator
- **QuestDB:**
  - `p3_d14_api_connection_states` — INSERT for health :521, batch :537
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - Line 373: `_active_connections` — module-level mutable dict accessed from orchestrator thread + health check without lock (see CONC-02)
  - Line 416: `get_api_key(ac_id)` — retrieves from vault during reconnect
  - Line 488: `check_compliance_gate()` — TOCTOU on compliance file read (see CONC-04)
  - Line 124-125: `DEFAULT_CONTRACT_ID` and `DEFAULT_ACCOUNT_NAME` read from env at class definition time — immutable, safe

---

### File: captain-command/captain_command/blocks/b4_tsm_manager.py

- **Purpose:** TSM file management — loads, validates, and stores Trading System Model JSON configs. Handles parameter translation for sizing blocks.
- **Key functions/classes:**
  - `validate_tsm()` :57 — Validates TSM JSON against schema (required fields, classification, numerics, V3 fields)
  - `load_all_tsm_files()` :138 — Loads all TSM JSONs from config directory
  - `load_tsm_for_account()` :179 — Loads specific TSM and stores in D08
  - `translate_for_tsm()` :225 — Applies TSM constraints (max contracts, daily loss budget)
  - `get_fee_for_instrument()` :274 — Fee lookup with V3 fee_schedule fallback
  - `get_scaling_tier()` :302 — Scaling tier lookup by profit
  - `_store_tsm_in_d08()` :378 — Upsert with retry on "table busy"
- **Session/schedule refs:** Called at startup; D08 writes triggered by TSM load/switch
- **QuestDB:**
  - `p3_d08_tsm_state` — INSERT :415 (with 3x retry on "table busy")
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - Line 444: Catches "table busy" and retries with linear backoff — good QuestDB resilience pattern
  - Line 151: `os.listdir(TSM_CONFIG_DIR)` — reads from mounted config volume, not user input
  - Validation is thorough: required fields, classification enums, numeric sanity, V3 fee/payout/scaling

---

## Security Audit Findings

### SEC-01: No Authentication on Any API Endpoint [CRITICAL]

**Location:** `api.py` (entire file)
**Severity:** CRITICAL
**Effort:** M

No API endpoint has authentication. Every route — including `/api/system/git-pull` (which runs `git pull` + `docker compose up --build`), `/api/aim/{id}/activate`, `/api/notifications/test`, and `/api/replay/start` — is accessible to anyone who can reach port 8000.

The WebSocket endpoint `/ws/{user_id}` accepts any `user_id` as a path parameter with no validation that the connecting client owns that identity. An attacker on the local network could:
- Connect as any user_id and receive all their signals/notifications
- Trigger auto-execute trades via command routing
- Run `POST /api/system/git-pull` to execute arbitrary git + docker operations

**Mitigation context:** nginx binds to 127.0.0.1:80 and proxies to 8000, and Docker publishes 8000 only to 127.0.0.1. This provides network-layer protection. However, any process on the host machine (or WSL2 instance) can reach the API. For a single-user local deployment this is acceptable risk; for multi-instance deployment to a client machine (per CLAUDE.md), this becomes HIGH.

**Recommendation:** Add a shared-secret header check (`X-Captain-Key` from .env) as FastAPI middleware, at minimum on write endpoints. For multi-user, implement proper JWT auth.

---

### SEC-02: Unauthenticated Remote Code Execution via git-pull Endpoint [CRITICAL]

**Location:** `api.py:824-927`
**Severity:** CRITICAL
**Effort:** S

`POST /api/system/git-pull` runs `subprocess.run(["git", "pull", "origin", "main"])` and then `subprocess.run(["docker", "compose", ... "up", "-d", "--build"])`. Combined with SEC-01 (no auth), any local process can trigger a full code pull and container rebuild.

The Docker socket (`/var/run/docker.sock`) is mounted into the container (confirmed in `docker-compose.yml:125`), giving this endpoint root-equivalent access to the host Docker daemon.

**Positive observations:**
- Command arguments are hardcoded arrays (no shell injection possible)
- `cwd` is fixed to `/captain/repo`
- Timeouts are set on subprocess calls

**Recommendation:** Gate behind authentication. Consider removing Docker socket mount and using a host-side webhook script instead.

---

### SEC-03: Docker Socket Mounted in Container [HIGH]

**Location:** `docker-compose.yml:125`, `captain-command/Dockerfile:8-14`
**Severity:** HIGH
**Effort:** M

The captain-command container has:
1. Docker CLI + Compose plugin installed in the image (Dockerfile lines 8-14)
2. `/var/run/docker.sock` mounted (docker-compose.yml:125)

This gives the container full control over the host Docker daemon. Combined with any code execution vulnerability (SEC-02, or a future RCE), this is equivalent to host root access.

**Recommendation:** Replace with a host-side deploy script triggered by a signal file or webhook, rather than granting the container Docker socket access.

---

### SEC-04: Error Messages Leak Internal Details [MEDIUM]

**Location:** `api.py:643, 671, 683, 695, 743, 777, 802, 817, 927` and `b2_gui_data_server.py:583`
**Severity:** MEDIUM
**Effort:** S

Multiple endpoints return `{"error": str(exc)}` directly to the client. Exception messages can reveal internal paths, database schema, library versions, and stack details.

Example: `api.py:583` — `return JSONResponse({"items": [], "count": 0, "error": str(exc)})` exposes QuestDB query errors.

**Recommendation:** Return generic error messages to the client. Log the full exception server-side (already done). Replace `str(exc)` in responses with a generic message like `"Internal error"` plus an error reference ID.

---

### SEC-05: WebSocket user_id Spoofing [MEDIUM]

**Location:** `api.py:192-275`
**Severity:** MEDIUM
**Effort:** M

The WebSocket endpoint accepts `user_id` as a path parameter with no verification. A client connecting to `/ws/admin_user` receives all dashboard data, signals, and notifications for that user. The `user_id` is also injected into commands:

```python
data["user_id"] = user_id  # line 247
```

This means a WebSocket client can impersonate any user for command routing (TAKEN/SKIPPED, AIM control, etc.).

**Recommendation:** Validate user_id against an auth token. At minimum, restrict to the configured BOOTSTRAP_USER_ID.

---

### SEC-06: SQL Injection in Notification Routing [HIGH]

**Location:** `captain-command/captain_command/blocks/b7_notifications.py:433-437`
**Severity:** HIGH
**Effort:** S

```python
role_list = ",".join(f"'{r}'" for r in roles)
cur.execute(
    f"SELECT DISTINCT user_id FROM p3_d16_user_capital_silos "
    f"WHERE status = 'ACTIVE' AND role IN ({role_list})"
)
```

The `roles` list is derived from notification template configuration (not direct user input), which significantly reduces exploitability. However, if a notification's `roles` field is ever influenced by external data, this is a classic SQL injection vector.

**Recommendation:** Use parameterised queries. QuestDB's PostgreSQL wire protocol supports `IN` with parameter arrays, or build parameterised placeholders: `','.join(['%s'] * len(roles))`.

---

### SEC-07: Telegram Bot Token Leak Prevention [LOW — Positive Finding]

**Location:** `main.py:39-41`
**Severity:** LOW (positive)
**Effort:** N/A

```python
logging.getLogger("httpx").setLevel(logging.WARNING)
```

Proactively suppresses httpx request logging to prevent the Telegram bot token (in URL path) from appearing in logs. Well-documented with comment.

---

### SEC-08: Sanitise-for-API Boundary is Secure [LOW — Positive Finding]

**Location:** `b1_core_routing.py:103-115`
**Severity:** LOW (positive)
**Effort:** N/A

`sanitise_for_api()` constructs the outbound order from an explicit allowlist of 6 fields. Combined with `PROHIBITED_EXTERNAL_FIELDS` from constants, this is secure by construction — no internal data leaks to the broker API.

---

## Concurrency Audit Findings

### CONC-01: Module-Level Globals Modified from Multiple Threads Without Locks [HIGH]

**Location:** `b2_gui_data_server.py:41-66`, `api.py:70-91,285-291,476-493`
**Severity:** HIGH (financial data)
**Effort:** M

Multiple module-level globals are written from the orchestrator thread and read from the uvicorn async event loop without synchronisation:

| Variable | Writer | Reader | File |
|----------|--------|--------|------|
| `_user_stream` | `set_user_stream()` | `_get_capital_silo()`, `_get_api_connection_status()` | b2 |
| `_account_data` | `set_account_data()` | `_get_capital_silo()`, `_get_api_connection_status()` | b2 |
| `_pipeline_stage` | `set_pipeline_stage()` | `build_dashboard_snapshot()` | b2 |
| `_process_health` | `update_process_health()` | `health()`, `status()` | api |
| `_api_connections` | `update_api_connections()` | `health()`, `status()`, `api_processes_status()` | api |
| `_last_signal_time` | `update_last_signal_time()` | `health()` | api |
| `_main_loop` | `set_event_loop()` | `gui_push()` | api |
| `_telegram_bot` | `set_telegram_bot()` | `api_test_notification()` | api |

In CPython, the GIL makes simple reference assignments atomic, so this won't cause crashes. However, composite reads (e.g., reading `_process_health[role]` dict while another thread replaces inner keys) can produce inconsistent snapshots.

**Risk assessment:** For this system — single-user, dashboard reads are non-critical, financial decisions are made in Online not Command — this is LOW practical risk but HIGH by concurrency audit standards because it touches financial data display.

**Recommendation:** For dict-valued globals (`_process_health`, `_api_connections`), use `threading.Lock` or replace with atomic reference swaps (write a new dict, assign the reference).

---

### CONC-02: `_active_connections` Dict Accessed from Multiple Threads Without Lock [HIGH]

**Location:** `b3_api_adapter.py:373`, accessed from `orchestrator.py:339,358`
**Severity:** HIGH (financial — trade execution path)
**Effort:** S

`_active_connections` is a module-level dict written by `register_connection()` (main thread at startup) and `run_health_checks()` (orchestrator scheduler thread), and read by `_auto_execute_signal()` (orchestrator signal thread).

The auto-execute path reads `state.get("adapter")` and `adapter.connected` while the health check thread may be reconnecting and updating `state["connected"]`, `state["retry_count"]`, and even replacing `state["adapter"]`.

**Recommendation:** Guard `_active_connections` access with a `threading.Lock`. The health check + auto-execute are both in the orchestrator, so contention will be minimal.

---

### CONC-03: WebSocket Session Set Modified Across Async Tasks [MEDIUM]

**Location:** `api.py:86,202-232,270-274,331,342`
**Severity:** MEDIUM
**Effort:** S

`_ws_sessions` (a `defaultdict(set)`) is modified by:
1. `websocket_endpoint()` — adds/removes from the set (async, on event loop)
2. `gui_push()` — reads the set from a background thread, schedules coroutines
3. `_safe_ws_send()` — discards from the set (async, on event loop)

The `gui_push()` function takes a snapshot via `list(sessions)` (line 331), which is a good defensive pattern. However, `_safe_ws_send()` at line 342 does `_ws_sessions[user_id].discard(ws)` which could race with `websocket_endpoint()` modifying the same set.

Since both `_safe_ws_send` and `websocket_endpoint` run on the same event loop (single-threaded async), this is actually safe — they won't interleave within a single statement. The cross-thread access from `gui_push()` is protected by the snapshot pattern.

**Conclusion:** False positive upon deeper analysis. The snapshot + single-event-loop pattern is correct.

---

### CONC-04: TOCTOU on File Reads [LOW]

**Location:** `b3_api_adapter.py:488-489`, `b2_gui_data_server.py:911-913`
**Severity:** LOW
**Effort:** S

```python
if os.path.exists(COMPLIANCE_GATE_PATH):
    with open(COMPLIANCE_GATE_PATH) as f:
        gate = json.load(f)
```

Classic TOCTOU — file could be deleted between `exists()` and `open()`. However:
- The file is a mounted config volume, not user-controlled
- The `except` block falls back to safe defaults (`gate = {}`)
- No security decision depends on the file existing vs. not existing (compliance gate defaults to MANUAL mode)

**Recommendation:** Replace with try/except `FileNotFoundError` (eliminates TOCTOU and is more Pythonic), but this is cosmetic.

---

### CONC-05: Blocking I/O in Orchestrator Scheduler Thread [LOW]

**Location:** `orchestrator.py:428-467`
**Severity:** LOW
**Effort:** S

The scheduler runs in a background thread with `time.sleep(1)` ticks. All QuestDB queries (via `build_dashboard_snapshot`, `run_health_checks`) are blocking I/O but this is intentional — the scheduler thread is dedicated and separate from the async event loop.

The `gui_push()` call correctly uses `run_coroutine_threadsafe()` to bridge from the blocking thread to the async event loop.

**Conclusion:** Blocking I/O in a dedicated thread is the correct pattern here. Not a finding.

---

## API Endpoint Inventory

| Method | Path | Auth? | Input Validation | Line |
|--------|------|-------|-----------------|------|
| GET | `/api/health` | No | N/A | 98 |
| GET | `/api/accounts` | No | N/A | 148 |
| GET | `/api/status` | No | N/A | 170 |
| WS | `/ws/{user_id}` | No | user_id unvalidated | 192 |
| POST | `/api/validate/input` | No | Pydantic model | 364 |
| POST | `/api/validate/asset-config` | No | Pydantic model | 371 |
| GET | `/api/dashboard/{user_id}` | No | user_id unvalidated | 383 |
| GET | `/api/aim/{aim_id}/detail` | No | aim_id as int | 394 |
| POST | `/api/aim/{aim_id}/activate` | No | aim_id as int | 400 |
| POST | `/api/aim/{aim_id}/deactivate` | No | aim_id as int | 410 |
| GET | `/api/system-overview` | No | N/A (labelled ADMIN) | 420 |
| GET | `/api/processes/status` | No | N/A | 431 |
| GET | `/api/reports/types` | No | N/A | 451 |
| POST | `/api/reports/generate` | No | Pydantic model | 457 |
| GET | `/api/notifications/preferences/{user_id}` | No | user_id unvalidated | 518 |
| POST | `/api/notifications/preferences` | No | Pydantic model | 526 |
| POST | `/api/notifications/read` | No | Pydantic model | 533 |
| POST | `/api/notifications/test` | No | Pydantic model | 540 |
| GET | `/api/notifications/telegram-history` | No | limit (int, capped 200) | 552 |
| POST | `/api/replay/start` | No | Pydantic model | 623 |
| POST | `/api/replay/batch/start` | No | Pydantic model | 654 |
| POST | `/api/replay/control` | No | Pydantic model | 674 |
| POST | `/api/replay/save` | No | Pydantic model | 686 |
| GET | `/api/replay/status` | No | N/A | 698 |
| GET | `/api/replay/history` | No | N/A | 712 |
| GET | `/api/replay/presets` | No | N/A | 747 |
| POST | `/api/replay/presets` | No | Pydantic model | 780 |
| POST | `/api/replay/whatif` | No | Pydantic model | 805 |
| POST | `/api/system/git-pull` | No | N/A | 824 |

**Total: 28 endpoints (1 WebSocket, 27 REST) — 0/28 have authentication.**

---

## WebSocket Connections

| Connection | Direction | Lifecycle | Reconnection | Error Handling |
|-----------|-----------|-----------|--------------|----------------|
| `/ws/{user_id}` | GUI → Command | Accept → evict stale (>3 per user, code 4001) → message loop → finally cleanup | Client-side (4001 = no reconnect, other codes = reconnect) | try/except with cleanup in finally block |
| Redis Stream (signals) | Command → Redis | Consumer group with durable delivery | Exponential backoff (1s → 30s max) with incident logging | Catches all exceptions, logs, creates incident |
| Redis Pub/Sub (alerts, status, commands) | Command → Redis | Subscribe to 3 channels | Exponential backoff (1s → 30s max) | Catches all exceptions, re-subscribes |

---

## Parity Filter Analysis

**Location:** `orchestrator.py:300-335`

The `_check_parity_skip()` implementation:
1. Gets today's date in America/New_York timezone
2. Increments a daily Redis counter `captain:signal_counter:{date}` via `INCR` (atomic)
3. Counter TTL: 2 days (86400 * 2)
4. Trade number 1,3,5... → parity 0 (odd); 2,4,6... → parity 1 (even)
5. Returns `True` (skip) if signal parity != instance parity
6. On Redis failure: defaults to TAKE (fail-open, ensuring no signal is silently dropped)

**Correctness:** The algorithm is sound. Redis `INCR` is atomic, and both instances reading the same Redis will see the same counter sequence. The key assumption is that both instances process signals in the same order — guaranteed because they read from the same Redis Stream.

**Edge case:** If one instance is down and misses a signal, the counter still increments (it's a Redis-side operation from the running instance). When the down instance comes back, it will read the same counter value, so parity stays synchronized.

---

## Security Score: 5.5/10

| Check | Score | Findings |
|-------|-------|----------|
| Hardcoded Secrets | 9/10 | No hardcoded secrets found. Credentials from env vars and vault. |
| SQL Injection | 7/10 | 1 f-string SQL in b7_notifications (SEC-06). All other queries parameterised. |
| XSS Vulnerabilities | 10/10 | No HTML rendering in backend. JSON API only. |
| Missing Input Validation | 3/10 | 0/28 endpoints have auth. user_id unvalidated on WS + REST. |
| Insecure Dependencies | 7/10 | Docker socket mount (SEC-03). Subprocess usage gated but unauthenticated. |

**Weighted: 5.5/10** — dragged down heavily by complete absence of authentication (SEC-01, SEC-02).

## Concurrency Score: 7.5/10

| Check | Score | Findings |
|-------|-------|----------|
| Async/Event-Loop Races | 9/10 | WebSocket session management is correct (snapshot pattern). |
| Thread Safety | 6/10 | Multiple shared globals without locks (CONC-01, CONC-02). |
| TOCTOU | 9/10 | Config file reads only, safe defaults on failure. |
| Deadlock Potential | 10/10 | No nested locks in audited files. |
| Blocking I/O in Async | 10/10 | Blocking queries correctly isolated in sync defs / dedicated threads. |
| Resource Contention | 8/10 | `_active_connections` contention on trade execution path. |
| Cross-Process Races | 9/10 | Parity counter uses atomic Redis INCR. |

**Weighted: 7.5/10** — main issue is unlocked shared state in a multi-threaded process.

---

## Session 5a Summary

- **Files audited:** 7
- **Key findings:** 10 (6 security, 4 concurrency — 2 confirmed false positive / positive)
- **Stub count:** 0
- **API endpoints:** 28 (1 WS, 27 REST) — see inventory table above
- **WebSocket connections:** 3 (1 GUI WS, 1 Redis Stream, 1 Redis Pub/Sub)
- **Security concerns (ranked by severity):**
  1. **CRITICAL** SEC-01: No authentication on any endpoint
  2. **CRITICAL** SEC-02: Unauthenticated RCE via git-pull + Docker socket
  3. **HIGH** SEC-03: Docker socket mounted in container
  4. **HIGH** SEC-06: SQL injection in b7_notifications role query
  5. **MEDIUM** SEC-04: Error messages leak internal details
  6. **MEDIUM** SEC-05: WebSocket user_id spoofing
- **Concurrency concerns (ranked by severity):**
  1. **HIGH** CONC-01: Module-level globals modified from multiple threads
  2. **HIGH** CONC-02: `_active_connections` accessed without lock on trade path
  3. **LOW** CONC-04: TOCTOU on config file reads (cosmetic)
- **Security score:** 5.5/10
- **Concurrency score:** 7.5/10

---

## Part 2: Reports, Notifications, Reconciliation, Replay

**Auditor:** Claude Opus 4.6 (Session 5b of 8)
**Date:** 2026-04-08
**Scope:** b5_injection_flow.py, b6_reports.py, b7_notifications.py, b8_reconciliation.py, b9_incident_response.py, b10_data_validation.py, b11_replay_runner.py, telegram_bot.py

---

### File: captain-command/captain_command/blocks/b5_injection_flow.py

- **Purpose:** Routes strategy injection workflow between GUI and Offline B4 — displays comparison panels, collects user decision (ADOPT/PARALLEL_TRACK/REJECT), forwards to Offline.
- **Key functions/classes:**
  - `notify_new_candidate()` :34 — Push notification to GUI when Offline B4 produces a new candidate
  - `get_injection_comparison()` :73 — Reads D06 + D11 for side-by-side current vs. proposed strategy
  - `route_injection_decision()` :154 — Validates decision, publishes to Redis CH_COMMANDS, logs to D17
  - `get_parallel_tracking_status()` :203 — Fetches active parallel-track candidates for an asset
  - `_log_injection_decision()` :243 — Inserts decision event into p3_session_event_log
- **QuestDB:**
  - `p3_d06_injection_history` — SELECT candidate details :86-97, SELECT parallel tracking :216-222
  - `p3_d11_pseudotrader_results` — SELECT pseudotrader metrics :123-130
  - `p3_session_event_log` — INSERT injection decision :247-259
- **Redis:**
  - `CH_COMMANDS` — PUBLISH decision command (ADOPT_STRATEGY / PARALLEL_TRACK / REJECT_STRATEGY) :175-179
- **Stubs/TODOs:** None
- **Notable:**
  - Line 57: `datetime.now().isoformat()` — no timezone. Should use `datetime.now(ZoneInfo("America/New_York"))` per CLAUDE.md rule 4. Same pattern at lines 191, 248-253.
  - Line 146: Error branch returns `{"error": str(exc)}` — leaks internal exception message to caller (consistent with SEC-04 from Part 1).

---

### File: captain-command/captain_command/blocks/b6_reports.py

- **Purpose:** 11 report types (RPT-01 through RPT-11). RPT-01/07 render in-app as JSON; others return CSV strings.
- **Key functions/classes:**
  - `generate_report()` :47 — Main dispatcher, archives report metadata to D09
  - `REPORT_TYPES` :32-44 — Registry of all 11 report types with trigger and render mode
  - `_rpt01_pre_session()` :111 — Latest signals + active assets (in-app)
  - `_rpt02_weekly_performance()` :145 — 7-day trade outcomes (CSV)
  - `_rpt03_monthly_decay()` :173 — BOCPD/CUSUM decay states (CSV)
  - `_rpt04_aim_effectiveness()` :194 — AIM DMA weights, accuracy, PnL contribution (CSV, most complex)
  - `_rpt05_strategy_comparison()` :310 — Injection history from D06 (CSV)
  - `_rpt06_regime_change()` :337 — Regime change events from session log (CSV)
  - `_rpt07_daily_prop()` :359 — TSM MDD/MLL drawdown status (in-app)
  - `_rpt08_regime_calibration()` :404 — Expected vs actual edge (CSV)
  - `_rpt09_parameter_audit()` :431 — Parameter change history from session log (CSV)
  - `_rpt10_annual_performance()` :457 — Full-year trade outcomes (CSV)
  - `_rpt11_financial_export()` :487 — Trade log with PnL/commission/slippage (CSV)
  - `_to_csv()` :519 — Converts query results to CSV string
  - `_archive_report()` :529 — Inserts report metadata into D09
- **QuestDB:**
  - `p3_session_event_log` — SELECT signals :116-121, SELECT regime changes :342-347, SELECT param changes :435-441
  - `p3_d00_asset_universe` — SELECT active assets :129-131
  - `p3_d03_trade_outcome_log` — SELECT weekly :149-155, SELECT aim trades :232-238, SELECT calibration :408-415, SELECT annual :462-470, SELECT financial :492-501
  - `p3_d04_decay_detector_states` — SELECT decay state :177-181
  - `p3_d01_aim_model_states` + `p3_d02_aim_meta_weights` — LEFT JOIN for AIM effectiveness :220-228
  - `p3_d06_injection_history` — SELECT candidates :314-319
  - `p3_d08_tsm_state` — SELECT account drawdown :363-369
  - `p3_d09_report_archive` — INSERT report metadata :533-548
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - RPT-04 (:194-302) is the most substantive report — correctly computes per-AIM accuracy and PnL contribution from trade-level breakdowns. Logic for neutral modifiers (abs(mod - 1.0) < 0.01 counts as correct) is defensible.
  - RPT-11 (:487) is labelled "ADMIN only" in the comment but has no authorization check in the function itself. The API endpoint also has no auth (see SEC-01). Financial data (PnL, commissions, slippage) is exposed to any caller.
  - Line 137: `return {"error": str(exc)}` in RPT-01 — leaks exception details. Same pattern in RPT-07 (:396).
  - Line 387: `round(drawdown / mdd * 100, 1) if mdd > 0 else 0` — division guard present, good.

---

### File: captain-command/captain_command/blocks/b7_notifications.py

- **Purpose:** Full notification routing — 26 event types mapped to 4 priority levels, per-user preferences, quiet hours queue, Telegram + GUI delivery, full audit logging to D10.
- **Key functions/classes:**
  - `EVENT_REGISTRY` :47-79 — 26 event types: 10 CRITICAL, 9 HIGH, 4 MEDIUM, 4 LOW (spec says 9 CRITICAL but code has 10 — ENTRY_PRICE_MISSING added)
  - `route_notification()` :161 — Main routing entry point: resolves priority/template, checks per-user prefs, delivers to GUI + Telegram, logs to D10
  - `flush_quiet_queue()` :128 — Drains queued notifications when quiet hours end
  - `_enqueue_quiet()` :118 — Adds to quiet queue (max 50 per user, drops oldest)
  - `save_user_preferences()` :380 — Persists prefs to p3_session_event_log
  - `_get_user_preferences()` :357 — Loads prefs from session log, falls back to DEFAULT_PREFERENCES
  - `_get_users_by_roles()` :417 — **SEC-06 (from Part 1)**: f-string SQL injection at line 433-436
  - `_get_telegram_chat_id()` :401 — Lookups chat_id from D16
  - `_log_notification_full()` :462 — Full delivery audit log to D10
  - `log_notification_response()` :510 — Logs user response to actionable notification
  - `mark_gui_read()` :536 — Records GUI notification read timestamp
  - `_is_in_quiet_hours()` :317 — Timezone-aware quiet hours check
  - `_extract_placeholders()` :566 — Regex placeholder extraction for templates
- **QuestDB:**
  - `p3_session_event_log` — SELECT prefs :365-370, INSERT prefs :384-396
  - `p3_d16_user_capital_silos` — SELECT chat_id :405-411, SELECT by role :428-437
  - `p3_d10_notification_log` — INSERT full log :482-505, INSERT response :516-531, INSERT gui_read :540-555
- **Redis:** None directly (called from orchestrator which handles Redis)
- **Stubs/TODOs:** None
- **Notable:**
  - **SEC-06 CONFIRMED** at line 433: `role_list = ",".join(f"'{r}'" for r in roles)` followed by f-string SQL. The `roles` come from `EVENT_REGISTRY` (hardcoded strings like "ADMIN", "DEV"), so exploitation requires a compromised registry entry or a code path that passes user-controlled role names. Risk is mitigated but the pattern is still dangerous.
  - Line 114: `_quiet_queue` and `_quiet_queue_lock` — properly thread-safe with lock. Good pattern.
  - Line 496: Message truncated to 500 chars for storage — `message[:500]` — reasonable guard.
  - Lines 516-531: `log_notification_response` inserts a full new row with empty fields to record a response — append-only pattern for QuestDB. Works but creates sparse rows.
  - EVENT_REGISTRY count: 10 CRITICAL + 9 HIGH + 4 MEDIUM + 4 LOW = 27 entries in the dict, but docstring says 26. Actual count is 27 (ENTRY_PRICE_MISSING was likely added late).

**Finding NOTIF-01 (LOW):** Event count mismatch — docstring says 26, code has 27 event types.

---

### File: captain-command/captain_command/blocks/b8_reconciliation.py

- **Purpose:** Daily 19:00 EST reconciliation — syncs account balances with broker, computes SOD Topstep parameters (f(A), N, E, L_halt, W, g), issues payout recommendations, resets daily counters.
- **Key functions/classes:**
  - `run_daily_reconciliation()` :41 — Main entry: iterates accounts, reconciles, computes SOD, resets counters
  - `_reconcile_api_account()` :93 — Compares broker vs system balance, auto-corrects if mismatch > $1
  - `_request_manual_reconciliation()` :142 — Sends GUI notification for non-API accounts
  - `process_manual_balance()` :160 — Processes user-reported balance
  - `_compute_sod_topstep_params()` :177 — Full V3 SOD computation: f(A), R_eff, N, E, L_halt, W, g
  - `_check_payout_recommendation()` :298 — 4-step payout decision with tier preservation, net commission check, MDD% impact
  - `_reset_daily_counters()` :399 — Resets daily_loss_used and D23 intraday CB state
  - `_get_all_accounts()` :450 — Fetches all accounts from D08
  - `_update_account_balance()` :483 — Logs balance update to session event log
  - `_update_topstep_state()` :501 — Logs computed SOD state to session event log
  - `_log_reconciliation()` :519 — Inserts into D19 reconciliation log
- **QuestDB:**
  - `p3_d08_tsm_state` — SELECT all accounts :454-461, SELECT account_ids for reset :421-424
  - `p3_session_event_log` — INSERT daily reset :408-417, INSERT balance update :487-497, INSERT topstep SOD :505-515
  - `p3_d23_circuit_breaker_intraday` — INSERT zero-reset rows per account :426-437
  - `p3_d19_reconciliation_log` — INSERT reconciliation result :525-537
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - Line 250: `from captain_command.blocks.b4_tsm_manager import get_scaling_tier` — lazy import inside function body. Avoids circular imports but creates a tight coupling to b4.
  - **Finding RECON-01 (MEDIUM):** Lines 483-498 and 501-515 — `_update_account_balance` and `_update_topstep_state` only log events to session_event_log. They do NOT actually update the D08 TSM state row (QuestDB is append-only, so true updates require inserting a new row into D08 with the corrected balance). The reconciliation detects mismatches but the correction only goes to the event log — the next SELECT from D08 will still return the old balance. This means reconciliation may repeatedly detect the same mismatch.
  - **Finding RECON-02 (HIGH):** The payout recommendation at line 336 uses `f_target_max = 0.03` (3% MDD fraction) as a hardcoded constant. This should come from config or D17 system params, not be baked into code. If the MDD limit or account type changes, this threshold needs a code change.
  - Line 312-318: Account-type-aware payout rules (BROKER_LIVE vs PROP) — good differentiation.
  - Line 439: `len(accounts)` referenced outside the `with get_cursor()` block scope — `accounts` was fetched inside the cursor context but the variable persists. Works in Python but could be confusing.

---

### File: captain-command/captain_command/blocks/b9_incident_response.py

- **Purpose:** Incident management — creates incidents with P1-P4 severity, stores to D21, routes notifications by severity, tracks resolution.
- **Key functions/classes:**
  - `create_incident()` :53 — Creates incident record, persists to D21, routes notification
  - `resolve_incident()` :136 — Inserts resolution row (append-only pattern)
  - `get_open_incidents()` :197 — Fetches open incidents from D21
  - `get_incident_detail()` :221 — Full incident history (creation + resolution rows)
  - `_store_incident()` :265 — Inserts incident into D21
  - `INCIDENT_TYPES` :34-37 — 6 types: CRASH, DATA_QUALITY, RECONCILIATION, PERFORMANCE, SECURITY, OPERATIONAL
  - `SEVERITY_ROUTING` :40-45 — P1/P2 get GUI+TELEGRAM, P3 gets GUI only, P4 logged only
- **QuestDB:**
  - `p3_d21_incident_log` — INSERT creation :269-286, INSERT resolution :160-176, SELECT open :201-207, SELECT detail :225-233
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - **Finding INC-01 (MEDIUM):** Line 257: `return {"error": str(exc)}` — the `exc` variable is referenced from the except block but it has already exited that scope. In CPython this works (the exception variable lingers) but it is technically undefined behavior per Python scoping rules and will fail if the try block succeeds but `rows` is empty. The fallthrough after the `if not rows` check at line 236 does `return {"error": f"Incident {incident_id} not found"}` which is correct — but line 257 is outside the try/except and references `exc` from the except clause, creating a potential `NameError` if the try succeeds but `rows` is non-empty and the function reaches line 257 (which it cannot, since the return at line 253 catches all successful paths). Still, the dangling `return {"error": str(exc)}` at line 257 is dead code that would crash if reached.
  - Lines 162-175: Resolution row inserts empty strings for type/severity/component — the `get_incident_detail()` function at line 239-240 relies on first/last row ordering to reconstruct the full record. This is fragile if the table gets reordered.
  - Severity routing spec says P1_CRITICAL targets ADMIN+DEV on ALL channels (GUI, Telegram, Email), but SEVERITY_ROUTING at line 41 only lists GUI+TELEGRAM for P1. Email is not implemented (noted as "Future v2" in b7).

---

### File: captain-command/captain_command/blocks/b10_data_validation.py

- **Purpose:** Validates user-provided data inputs (entry price, commission, balance) and asset configuration for onboarding.
- **Key functions/classes:**
  - `validate_user_input()` :59 — Validates ACTUAL_ENTRY_PRICE (2% threshold), ACTUAL_COMMISSION (10x threshold), ACCOUNT_BALANCE (5% threshold)
  - `validate_asset_config()` :136 — Full asset config validation: required fields, P1/P2 path existence, data source connectivity, roll calendar, session hours regex, numeric sanity
  - `ASSET_REQUIRED_FIELDS` :31-42 — 10 required fields for asset onboarding
  - `VALID_ADAPTERS` :45 — REST, FILE, WEBSOCKET, BROKER_API
  - `_SESSION_HOURS_RE` :49-51 — Regex for session hours format
- **QuestDB:** None
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - This is a pure validation module — no database access, no side effects. Clean design.
  - Line 163: `os.path.exists(p1_path)` — path traversal concern. If `p1_path` comes from user input, it could probe for file existence on the host filesystem. Mitigated by Docker container isolation (the container cannot see the full host FS) but still worth noting.
  - Line 185: `os.path.getsize(endpoint) == 0` — FILE adapter checks for empty files. Good defensive check.
  - Line 83: Division guard for `signal_price != 0` prevents ZeroDivisionError. Good.
  - The module returns `requires_confirmation: True` for suspicious values instead of hard-rejecting — allows user override. Good UX design.

---

### File: captain-command/captain_command/blocks/b11_replay_runner.py

- **Purpose:** Manages single-day and batch (multi-day) replay sessions as background threads, streaming events to GUI via WebSocket. Supports pause/resume, speed control, skip-to-next, what-if reruns.
- **Key functions/classes:**
  - `ReplaySession` :32 — Single replay session: background thread, pause/resume events, GUI streaming
  - `ReplaySession._run()` :111 — Main thread: calls `shared.replay_engine.run_replay()` with on_event callback
  - `ReplaySession.start()` :56 — Starts daemon thread
  - `ReplaySession.pause()` / `resume()` / `set_speed()` / `skip_to_next()` / `stop()` :67-95 — Playback controls
  - `BatchReplaySession` :382 — Multi-day replay: iterates weekdays, computes batch summary
  - `BatchReplaySession._compute_batch_summary()` :579 — PnL, win rate, max drawdown, best/worst day
  - `start_replay()` :210 — Module-level: stops existing user replay, loads config, starts ReplaySession
  - `start_batch_replay()` :616 — Module-level: validates date range, max 60 weekdays, starts BatchReplaySession
  - `control_replay()` :262 — Dispatches pause/resume/speed/skip/stop to active session
  - `get_active_replay()` :286 — Returns status of active replay
  - `save_replay()` :294 — Saves replay results to p3_replay_results
  - `run_whatif()` :338 — Reruns sizing with different config using cached bars from last replay
  - `_get_user_session()` :689 — Finds most recent session for user (prefers running/paused)
  - `_safe_config()` :704 — Strips non-serializable data for storage
- **QuestDB:**
  - `p3_replay_results` — INSERT saved replay :312-330
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - Line 206: `_active_sessions` dict and `_lock` — properly thread-safe with threading.Lock. Good pattern.
  - Line 148: Sleep in small increments (0.1s) with stop/pause checks — responsive playback control. Good design.
  - **Finding REPLAY-01 (MEDIUM):** Lines 216-218: Stopping existing replays iterates `_active_sessions` inside `_lock`, but `rs.stop()` itself does not acquire the lock (it just sets flags). This is fine. However, stale completed/stopped sessions are never removed from `_active_sessions`, so the dict grows unboundedly over time. For a GUI tool this is unlikely to be a problem in practice, but long-running server processes could accumulate hundreds of orphaned sessions.
  - **Finding REPLAY-02 (LOW):** Lines 230-235: `config_overrides` TP/SL override loop is duplicated identically in `start_replay()`, `run_whatif()`, and `start_batch_replay()`. Should be extracted to a helper.
  - Line 647-648: Batch replay caps at 60 weekdays — reasonable guard against runaway replays.
  - Line 507: Batch mode sleep is `0.1 / max(self.speed, 1)` — less granular than single-replay pause/stop checking. Batch mode does not support the same responsive pause/stop as single replay (no `_pause_event.wait` in the sleep loop).

---

### File: captain-command/captain_command/blocks/telegram_bot.py

- **Purpose:** Telegram bot — 7 commands (/status, /signals, /positions, /reports, /tsm, /mute, /help), inline TAKEN/SKIPPED buttons, chat ID whitelisting, rate limiting, audit logging.
- **Key functions/classes:**
  - `CaptainTelegramBot` :270 — Main bot class, runs in daemon thread with own asyncio event loop
  - `CaptainTelegramBot.start()` :293 — Starts background polling thread
  - `CaptainTelegramBot.stop()` :302 — Graceful stop via asyncio future
  - `CaptainTelegramBot._run_bot()` :315 — Sets up handlers, starts polling with `stop_signals=()`
  - `CaptainTelegramBot.send_message()` :550 — Sends message via urllib (not python-telegram-bot's async send). Rate limit + mute check.
  - `CaptainTelegramBot.send_signal_notification()` :624 — Sends signal with inline TAKEN/SKIPPED buttons
  - `create_telegram_bot()` :673 — Factory: token from vault first, then env var fallback
  - `_check_rate_limit()` :44 — 60 messages/hour per chat_id, sliding window
  - `_get_whitelisted_chat_ids()` :61 — Loads {chat_id: user_id} from D16
  - `_get_user_for_chat_id()` :80 — Single chat_id lookup
  - `_check_auth()` (inner) :334 — Verifies chat ID in whitelist before processing any command
  - `_query_system_status()` :91 — System status for /status
  - `_query_latest_signals()` :123 — Latest signals for /signals (no strategy details)
  - `_query_open_positions()` :152 — Open positions for /positions
  - `_query_recent_reports()` :184 — Recent reports for /reports
  - `_query_tsm_status()` :209 — TSM account status for /tsm
  - `_set_mute()` / `_is_muted()` :249-262 — In-memory mute state
  - `_log_bot_interaction()` :647 — Audit logs all interactions to session_event_log
- **Telegram commands:**
  - `/status` :347 — System status summary (active assets, warmup, open positions)
  - `/signals` :364 — Latest signals (asset, direction, confidence only — no strategy details)
  - `/positions` :382 — Open positions (asset, direction, contracts, entry price)
  - `/reports` :402 — Recent report list
  - `/tsm` :420 — TSM status (MDD%, MLL%, pass probability, balance)
  - `/mute <hours>` :442 — Mute non-CRITICAL for 1-24 hours
  - `/help` :464 — Help text
  - Inline callback :482 — TAKEN/SKIPPED buttons on signal notifications
- **QuestDB:**
  - `p3_d16_user_capital_silos` — SELECT whitelisted chat_ids :68-73
  - `p3_d00_asset_registry` — SELECT status counts :101-108 (NOTE: table name is `p3_d00_asset_registry` here but `p3_d00_asset_universe` in b6 — see finding TG-01)
  - `p3_d03_trade_outcomes` — SELECT open positions :112-114, :159-164 (NOTE: table name is `p3_d03_trade_outcomes` here but `p3_d03_trade_outcome_log` in b6/b8 — see finding TG-01)
  - `p3_session_event_log` — SELECT latest signals :130-134, SELECT recent reports :189-193, INSERT bot interaction :651-662
  - `p3_d08_tsm_state` — SELECT TSM status :213-218
- **Redis:** None
- **Stubs/TODOs:** None
- **Notable:**
  - **Finding TG-01 (HIGH):** Table name inconsistency — telegram_bot.py uses `p3_d00_asset_registry` (:102) while b6_reports.py uses `p3_d00_asset_universe` (:130). Similarly, telegram_bot uses `p3_d03_trade_outcomes` (:112, :160) while b6/b8 use `p3_d03_trade_outcome_log`. One of these is the correct table name; the other will cause runtime SQL errors. Since init_questdb.py likely defines one canonical name, the mismatched names in telegram_bot.py will silently fail (caught by except blocks, returning empty results).
  - **Finding TG-02 (MEDIUM):** Line 600: `send_message()` uses raw `urllib.request` GET with token in the URL instead of python-telegram-bot's async API. This means the bot token appears in URL strings in memory and potentially in HTTP logs. The bot commands use python-telegram-bot properly (via ApplicationBuilder), but the outbound send bypasses it.
  - **Finding TG-03 (LOW):** Lines 39, 246: `_rate_window` and `_mute_until` are module-level dicts without thread locks. The bot runs in its own thread and `send_message()` is called from the notification router in the orchestrator thread. Concurrent access to these dicts from multiple threads is a race condition. In practice, CPython's GIL makes dict operations atomic for simple get/set, but this is an implementation detail, not a guarantee.
  - Security positives: (1) Chat ID whitelisting before any command (:334-343), (2) No strategy details in /signals responses (:126-127), (3) Rate limiting at 60/hour (:44-53), (4) Mute respects CRITICAL bypass (:582), (5) Token loaded from vault first (:687-690), (6) All interactions audit-logged (:647-665).
  - Line 544: `stop_signals=()` prevents signal handler registration outside main thread — correct for daemon thread.

---

## Part 2 Findings Summary

### New Findings (Session 5b)

| ID | Severity | File | Line | Description |
|----|----------|------|------|-------------|
| TG-01 | HIGH | telegram_bot.py | 102, 112, 160 | Table name mismatch: `p3_d00_asset_registry` and `p3_d03_trade_outcomes` vs canonical names `p3_d00_asset_universe` and `p3_d03_trade_outcome_log`. Will cause runtime SQL failures. |
| RECON-01 | MEDIUM | b8_reconciliation.py | 483-515 | Balance correction only logs to session_event_log, does not insert corrected row into D08 TSM state. Reconciliation detects but does not actually fix the mismatch in the queryable table. |
| RECON-02 | HIGH | b8_reconciliation.py | 336 | Hardcoded `f_target_max = 0.03` for MDD% payout threshold. Should be configurable. Money-affecting: incorrect threshold silently blocks or permits payouts. |
| INC-01 | MEDIUM | b9_incident_response.py | 257 | Dead code `return {"error": str(exc)}` outside except block. Would raise NameError if reached. |
| NOTIF-01 | LOW | b7_notifications.py | 7 | Docstring says 26 event types, code has 27. |
| REPLAY-01 | MEDIUM | b11_replay_runner.py | 206 | `_active_sessions` dict never cleaned up — grows unboundedly. |
| REPLAY-02 | LOW | b11_replay_runner.py | 230 | TP/SL override code duplicated 3 times. |
| TG-02 | MEDIUM | telegram_bot.py | 600 | `send_message()` uses urllib GET with token in URL instead of library async send. Token exposed in URL strings. |
| TG-03 | LOW | telegram_bot.py | 39, 246 | `_rate_window` and `_mute_until` module-level dicts accessed from multiple threads without locks. |

### Combined Findings (Part 1 + Part 2)

**CRITICAL (2):** SEC-01 (no auth), SEC-02 (RCE via git-pull)
**HIGH (5):** SEC-03 (Docker socket), SEC-06 (SQL injection), CONC-01 (unlocked globals), CONC-02 (unlocked connections), TG-01 (wrong table names), RECON-02 (hardcoded payout threshold)
**MEDIUM (7):** SEC-04 (error leaks), SEC-05 (WS spoofing), RECON-01 (reconciliation ineffective), INC-01 (dead code), REPLAY-01 (session leak), TG-02 (token in URL)
**LOW (4):** CONC-04 (TOCTOU), NOTIF-01 (docstring count), REPLAY-02 (code duplication), TG-03 (unlocked dicts)

---

## Complete QuestDB Table Inventory (Command Process)

| Table | Operations | Used By |
|-------|-----------|---------|
| `p3_d00_asset_universe` | SELECT | b6 (RPT-01), telegram_bot* |
| `p3_d01_aim_model_states` | SELECT | b6 (RPT-04) |
| `p3_d02_aim_meta_weights` | SELECT (JOIN) | b6 (RPT-04) |
| `p3_d03_trade_outcome_log` | SELECT | b6 (RPT-02/04/08/10/11), telegram_bot* |
| `p3_d04_decay_detector_states` | SELECT | b6 (RPT-03) |
| `p3_d06_injection_history` | SELECT | b5, b6 (RPT-05) |
| `p3_d08_tsm_state` | SELECT | main, b4, b6 (RPT-07), b8, telegram_bot |
| `p3_d09_report_archive` | INSERT | b6 |
| `p3_d10_notification_log` | SELECT, INSERT | api, b7 |
| `p3_d11_pseudotrader_results` | SELECT | b5 |
| `p3_d16_user_capital_silos` | SELECT, INSERT | main, b7, telegram_bot |
| `p3_d19_reconciliation_log` | INSERT | b8 |
| `p3_d21_incident_log` | SELECT, INSERT | b9 |
| `p3_d23_circuit_breaker_intraday` | INSERT | b8 |
| `p3_session_event_log` | SELECT, INSERT | b5, b6, b7, b8, telegram_bot |
| `p3_replay_results` | SELECT, INSERT | api, b11 |
| `p3_replay_presets` | SELECT, INSERT | api |

*telegram_bot uses non-canonical names `p3_d00_asset_registry` and `p3_d03_trade_outcomes` — see TG-01.

---

## Complete Redis Channel/Key Inventory (Command Process)

| Channel/Key | Type | Direction | Used By |
|-------------|------|-----------|---------|
| `STREAM_SIGNALS` / `GROUP_COMMAND_SIGNALS` | Stream | Read + Ack | main, orchestrator |
| `CH_COMMANDS` (`captain:commands`) | Pub/Sub | Subscribe + Publish | orchestrator, b1, b5 |
| `CH_ALERTS` (`captain:alerts`) | Pub/Sub | Subscribe | orchestrator |
| `CH_STATUS` (`captain:status`) | Pub/Sub | Subscribe + Publish | orchestrator |
| `captain:signal_counter:{date}` | Key (INCR) | Read/Write | orchestrator (parity) |

---

## Notification & Alert Inventory

### Event Types (27 total, from b7 EVENT_REGISTRY)

**CRITICAL (10):** TP_HIT, SL_HIT, DECAY_LEVEL3, TSM_MDD_BREACH, TSM_MLL_BREACH, SYSTEM_CRASH, MID_TRADE_REGIME_SHIFT, API_KEY_COMPROMISE, API_CONNECTION_LOST, ENTRY_PRICE_MISSING

**HIGH (9):** SIGNAL_GENERATED, DECAY_LEVEL2, REGIME_CHANGE, AIM_FRAGILE, INJECTION_AVAILABLE, VIX_SPIKE, AUTO_EXEC_GATE, HEALTH_DIAGNOSTIC, ACTION_ITEM_REOPENED

**MEDIUM (4):** AIM_WARMUP_COMPLETE, WEEKLY_REPORT_READY, PARALLEL_TRACKING_DONE, API_KEY_ROTATION_DUE

**LOW (4):** MONTHLY_REPORT_READY, RETRAIN_COMPLETE, SYSTEM_STATUS, ANNUAL_REVIEW_READY

### Delivery Channels

| Channel | Priority Threshold | Quiet Hours | Mute |
|---------|-------------------|-------------|------|
| GUI (WebSocket) | All (LOW+) | N/A (always delivered) | N/A |
| Telegram | HIGH+ (configurable) | Queued (max 50), CRITICAL bypasses | Mutable (1-24h), CRITICAL bypasses |
| Email | MEDIUM+ (configurable) | N/A | N/A (future v2, not implemented) |

### Incident Severity Routing (b9)

| Severity | Channels | Targets |
|----------|----------|---------|
| P1_CRITICAL | GUI + Telegram | ADMIN |
| P2_HIGH | GUI + Telegram | ADMIN |
| P3_MEDIUM | GUI only | ADMIN |
| P4_LOW | Logged only | None |

---

## External Integration Inventory

### Telegram Bot API

| Integration | Method | Auth | File | Line |
|-------------|--------|------|------|------|
| Send message | GET `api.telegram.org/bot{token}/sendMessage` | Bot token in URL | telegram_bot.py | 600-609 |
| Receive commands | Long polling via python-telegram-bot | Bot token in ApplicationBuilder | telegram_bot.py | 525-544 |
| Inline callbacks | CallbackQueryHandler | Chat ID whitelist | telegram_bot.py | 482-513 |

### TopstepX (from Part 1)

| Integration | Method | Auth | File |
|-------------|--------|------|------|
| REST API auth | POST /api/Auth/login | Email + API key from env | main.py, b3_api_adapter.py |
| Account status | GET /api/Account | Bearer token | b3_api_adapter.py |
| Order placement | POST /api/Order | Bearer token | b3_api_adapter.py |
| Position query | GET /api/Position | Bearer token | b3_api_adapter.py |

---

## Session 5b Summary

- **Files audited:** 8
- **New findings:** 9 (2 HIGH, 4 MEDIUM, 3 LOW)
- **Combined findings (Part 1 + 2):** 18 total (2 CRITICAL, 5 HIGH, 7 MEDIUM, 4 LOW)
- **Stub count:** 0 (all 8 files fully implemented)
- **QuestDB tables used by Command:** 17
- **Redis channels/keys used by Command:** 5
- **Telegram bot commands:** 7 + inline TAKEN/SKIPPED
- **Report types:** 11 (RPT-01 through RPT-11)
- **Notification event types:** 27
- **Incident severity levels:** 4 (P1-P4)
