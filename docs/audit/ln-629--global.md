# Lifecycle Audit Report

<!-- AUDIT-META
worker: ln-629
category: Lifecycle
domain: global
scan_path: .
score: 6.2
total_issues: 9
critical: 0
high: 1
medium: 4
low: 4
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| bootstrap_order | Bootstrap Initialization Order | passed | All 3 processes init infrastructure (QuestDB → Redis → consumer groups) before business logic; b9 SESSION_OPEN_TIMES computed safely inside lazy orchestrator import |
| graceful_shutdown | Graceful Shutdown | failed | captain-command signal handlers overridden by uvicorn at startup |
| resource_cleanup | Resource Cleanup on Exit | warning | Redis pool never closed explicitly; offline/online missing stop_grace_period; or_tracker not cleared on shutdown |
| signal_handling | Signal Handling | warning | SIGTERM+SIGINT handled in all 3 processes; SIGHUP unhandled; uvicorn override breaks command |
| probes | Liveness/Readiness Probes | warning | offline+online health checks probe QuestDB externally, not the process itself |
| block_naming | Block Naming Conventions | failed | b8_ and b9_ prefixes each used by two files — collides with spec-defined B8/B9 block numbers |
| b9_bootstrap | b9_session_controller Bootstrap Safety | passed | Pure utility module; no I/O at class or function definition; SESSION_OPEN_TIMES evaluated lazily inside main() via deferred orchestrator import |
| b9_cleanup | b9_session_controller Graceful Shutdown | passed | No threads, sockets, or file handles held open; module-level cache requires no teardown |
| b8_cleanup | b8_or_tracker Graceful Shutdown | warning | ORTracker holds a threading.Lock and an in-memory sessions dict; or_tracker.clear() is not called in shutdown_handler — minor, but sessions dict grows across day if clear() is skipped |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | captain-command/captain_command/main.py:355-364 | `signal.signal()` is registered before `uvicorn.run()`. Uvicorn overrides SIGTERM/SIGINT handlers when it starts its event loop, so `orchestrator.stop()` and `telegram_bot.stop()` are never called on Docker SIGTERM. | Signal Handling / Graceful Shutdown | Register a FastAPI lifespan shutdown handler (`@asynccontextmanager` lifespan) or use uvicorn's `on_shutdown` hook to call `orchestrator.stop()` and `telegram_bot.stop()` instead of a raw `signal.signal()`. | M |
| MEDIUM | captain-online/captain_online/blocks/ | Two files use the `b8_` prefix (`b8_concentration_monitor.py` = spec B8, `b8_or_tracker.py` = renamed) and two use `b9_` (`b9_capacity_evaluation.py` = spec B9, `b9_session_controller.py` = new). The prefix collides with the spec-canonical block numbers, creating maintainability ambiguity and index confusion in audit tooling. | Block Naming / Naming Conventions | Rename `b8_or_tracker.py` to `or_tracker.py` (no block prefix — it is a support utility, not a numbered pipeline stage) and `b9_session_controller.py` to `session_controller.py` for the same reason. Alternatively, assign them distinct non-conflicting numbers (e.g. `b8b_or_tracker.py`, `b9b_session_controller.py`). Update all import sites. | M |
| MEDIUM | captain-offline/Dockerfile, captain-online/Dockerfile | captain-offline and captain-online have no `stop_grace_period` in docker-compose.yml (only captain-command has 30s). Docker default is 10s. If the orchestrator is mid-session when SIGTERM arrives, the 10s window may be tight — especially if the Redis thread join times out near 5s (offline). | Resource Cleanup / Graceful Shutdown | Add `stop_grace_period: 30s` to captain-offline and captain-online in docker-compose.yml to match captain-command. | S |
| MEDIUM | captain-offline/Dockerfile:HEALTHCHECK, captain-online/Dockerfile:HEALTHCHECK | The health check for captain-offline and captain-online probes an external service (`http://questdb:9000/exec?query=SELECT%201`) rather than the process itself. A crashed orchestrator (e.g., unhandled exception in `_session_loop` or `_redis_listener`) would still be marked healthy as long as QuestDB is reachable. Docker would not restart it. | Probes / Liveness | Add a lightweight HTTP health endpoint to captain-offline and captain-online (e.g., a single-file aiohttp or Flask server writing a heartbeat flag, or a file-based heartbeat the health check reads). The orchestrator writes a timestamp file every scheduler tick; the health check verifies it is recent. | M |
| MEDIUM | captain-online/captain_online/main.py:122-126, captain-offline/captain_offline/main.py:140-146, captain-command/captain_command/main.py:355-364 | SIGHUP is not handled in any of the 3 processes. Standard Linux practice for long-running daemons is to reload config or rotate logs on SIGHUP. Without a handler, the default Python behaviour is to terminate the process. In a trading system running 24/7, an accidental SIGHUP from a script or logrotate would kill the process uncleanly. | Signal Handling / Signal Propagation | Add `signal.signal(signal.SIGHUP, signal.SIG_IGN)` at minimum to prevent accidental kills, or implement a config-reload/log-flush handler. | S |
| LOW | captain-online/captain_online/blocks/orchestrator.py:86-88 | `stop()` sets `running=False` but does not join the `_command_listener` daemon thread started in `start()`. The thread is daemon=True so it dies with the process, but mid-iteration work (ACK messages, Redis writes) is interrupted without a join. This contrasts with captain-offline which joins its Redis thread (5s timeout). | Resource Cleanup / Shutdown | Mirror captain-offline's pattern: store the `_command_listener` thread reference and join it with a timeout in `stop()`. | S |
| LOW | captain-online/captain_online/blocks/b8_or_tracker.py:29, captain-online/captain_online/blocks/b9_session_controller.py:21 | `b8_or_tracker` uses `pytz.timezone()` while `b9_session_controller` and the rest of the system use `zoneinfo.ZoneInfo`. Both work correctly but represent an inconsistency — `pytz` is a legacy dependency (`tzinfo.localize()` semantics differ from `zoneinfo`). | Code Quality / Consistency | Replace `from pytz import timezone` + `_ET = timezone("America/New_York")` in `b8_or_tracker.py` with `from zoneinfo import ZoneInfo` + `_ET = ZoneInfo("America/New_York")`. Replace `datetime.now(_ET)` calls accordingly (already use the right form). | S |
| LOW | captain-online/captain_online/blocks/b8_or_tracker.py:116, captain-online/captain_online/blocks/b9_session_controller.py:35 | Both modules define a `_registry_cache: dict | None = None` module-level global and each independently loads `config/session_registry.json` on first call. This results in two separate cached copies of the same file in memory and two file-open calls at startup. | DRY / Resource | Move `_load_session_registry()` (or a renamed `_load_registry()`) into a shared module (e.g., `shared/session_registry.py`) and import it from both `b8_or_tracker` and `b9_session_controller`. | M |
| LOW | captain-online/captain_online/blocks/b9_session_controller.py:72-77 | The `_DEFAULT_OPEN_TIMES` fallback defines APAC open time as `(20, 0)` (20:00 ET), but `config/session_registry.json` defines `APAC.or_start` as `"18:00"`. If the registry file is missing (e.g., misconfigured Docker volume mount), the fallback silently uses the wrong time for APAC sessions (2-hour discrepancy). | Bootstrap Safety / Fallback Correctness | Correct the fallback to `3: (18, 0)` to match the registry, or raise a hard startup error (`sys.exit(1)`) if the registry cannot be found, since running without it yields wrong session schedules. | S |

## Evidence Notes

### Check 1 — Bootstrap Initialization Order

**New b9_session_controller analysis (PASSED):**

`b9_session_controller.py` is a pure utility module with no class instantiation. At module level it only defines:
- A `_registry_cache` global (initialized to `None`)
- A `SESSION_WINDOW_MINUTES` constant from env var
- Module-level `_ET = ZoneInfo(SYSTEM_TIMEZONE)` and `logger`
- `_DEFAULT_OPEN_TIMES` dict

No I/O occurs until a function is called. `orchestrator.py` calls `get_session_open_times()` at its own module level (line 51), but the orchestrator is imported lazily inside `main()` (line 117 of `main.py`) — after `logging.basicConfig()` is configured and infrastructure has been verified. The chain is safe:

```
main() called
  → QuestDB/Redis verified
  → _start_market_streams()
  → from captain_online.blocks.orchestrator import OnlineOrchestrator  ← lazy import
       → b9_session_controller imported
       → SESSION_OPEN_TIMES = get_session_open_times()  ← file read here, logging ready
```

**New b8_or_tracker analysis (PASSED):**

`or_tracker = ORTracker()` at line 33 of `main.py` is a module-level instantiation (not lazy). `ORTracker.__init__` only creates a `dict` and a `threading.Lock` — no I/O, no network, no file access. Safe at any import time.

**Existing processes (unchanged — PASSED):** All 3 processes init QuestDB → Redis → consumer groups before business logic.

### Check 2 — Graceful Shutdown (FAILED — unchanged)

See Session 07/08 findings. The captain-command uvicorn override remains the primary issue.

**b9_session_controller:** Pure utility module — no threads, no sockets, no persistent resources. Nothing to shut down. PASSED.

**b8_or_tracker (ORTracker):** Holds a `threading.Lock` and a `_sessions` dict. The Lock is a pure memory primitive — no OS resource released on cleanup. The `_sessions` dict grows during a trading day and is meant to be cleared via `clear()` at end-of-day. The `shutdown_handler` in `main.py` does not call `or_tracker.clear()`:

```python
def shutdown_handler(signum, frame):
    logger.info("Shutdown signal received")
    orchestrator.stop()
    if market_stream:
        market_stream.stop()
    write_checkpoint(ROLE, "SHUTDOWN", "running", "shutdown")
    sys.exit(0)
    # ← or_tracker.clear() never called
```

This is not a resource leak (memory is freed on `sys.exit(0)`) but if the process is restarted mid-day without clearing, stale session state persists. Low severity.

### Check 3 — Resource Cleanup

- **b9_session_controller file handles:** `_load_registry()` opens `session_registry.json` with `with open(...) as f:` — context manager guarantees close. No handle leak. ✓
- **b8_or_tracker file handles:** `_load_session_registry()` and `_load_contract_to_asset()` both use `with open(...) as f:`. No handle leak. ✓
- **b8_or_tracker threading.Lock:** Pure memory, no OS resource. No explicit teardown needed. ✓
- **Existing findings unchanged:** Redis pool not closed, telegram bot not stopped on command shutdown.

### Check 4 — Signal Handling (unchanged)

| Process | SIGTERM | SIGINT | SIGHUP |
|---------|---------|--------|--------|
| captain-offline | ✓ custom handler | ✓ custom handler | ✗ default (terminates) |
| captain-online | ✓ custom handler | ✓ custom handler | ✗ default (terminates) |
| captain-command | ✗ overridden by uvicorn | ✗ overridden by uvicorn | ✗ default (terminates) |

b9_session_controller and b8_or_tracker do not register or interact with signal handlers. No new signal handling issues introduced.

### Check 5 — Block Naming Conventions (FAILED — new finding)

The captain-online spec defines B1–B9 as a numbered pipeline. The canonical mapping from `executor_prompts.md` and audit history is:

| Block # | File | Role |
|---------|------|------|
| B1 | b1_data_ingestion.py, b1_features.py | Data ingestion |
| B2 | b2_regime_probability.py | Regime detection |
| B3 | b3_aim_aggregation.py | AIM aggregation |
| B4 | b4_kelly_sizing.py | Kelly sizing |
| B5 | b5_trade_selection.py | Trade selection |
| B5B | b5b_quality_gate.py | Quality gate |
| B5C | b5c_circuit_breaker.py | Circuit breaker |
| B6 | b6_signal_output.py | Signal output |
| B7 | b7_position_monitor.py, b7_shadow_monitor.py | Position monitoring |
| **B8** | **b8_concentration_monitor.py** | Concentration check (spec B8) |
| **B9** | **b9_capacity_evaluation.py** | Capacity evaluation (spec B9) |

The rename of `or_tracker.py` → `b8_or_tracker.py` (G-067 fix) and creation of `b9_session_controller.py` (G-066 fix) create prefix collisions. The orchestrator docstring confirms: "POST-LOOP: B8 (concentration) → B9 (capacity)". The OR tracker and session controller are support utilities — the `b8_` and `b9_` prefixes imply they are pipeline stages, which they are not.

### Check 6 — Liveness/Readiness Probes (unchanged)

See prior findings. No changes from b8/b9 additions.

---

**Score: 6.2/10** | Issues: 9 (C:0 H:1 M:4 L:4)
