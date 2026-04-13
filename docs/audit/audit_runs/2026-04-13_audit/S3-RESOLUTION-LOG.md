# Session 3 Resolution Log — 2026-04-13

**Session**: S3 — Docker Infrastructure + Medium Issues
**Issues**: H4, M1-M8
**Date**: 2026-04-13
**Status**: COMPLETE

---

## Fix H4 — Redis Healthcheck Variable Expansion

**Severity**: HIGH
**Root cause**: Redis healthcheck used `["CMD", "sh", "-c", "redis-cli -a $REDIS_PASSWORD ping"]`. While `sh -c` would expand the variable, the `CMD` exec form in Docker Compose can behave inconsistently with variable expansion depending on the shell context. Raw `docker compose up` would hang for 180s waiting for the healthcheck.

**Changes**:
| File | Line | Old | New |
|------|------|-----|-----|
| `docker-compose.yml` | 40 | `["CMD", "sh", "-c", "redis-cli -a $REDIS_PASSWORD ping"]` | `["CMD-SHELL", "redis-cli -a $$REDIS_PASSWORD ping \| grep PONG"]` |

`CMD-SHELL` invokes `/bin/sh -c` reliably. `$$` escapes to `$` in Compose interpolation, so the container sees `$REDIS_PASSWORD`. The `| grep PONG` ensures the healthcheck only passes on a real PONG response (not an auth error message).

**Verification**: YAML validation passes. `CMD-SHELL` confirmed at line 40.

---

## Fix M1 — Zero-Contract Signal Guard

**Severity**: MEDIUM
**Root cause**: B6 `run_signal_output()` created signal dicts with `size=0` when Kelly sizing returned zero contracts. Command B1 filtered these (line 90), but they created unnecessary log noise and wasted Redis bandwidth.

**Changes**:
| File | Lines | Change |
|------|-------|--------|
| `captain-online/.../b6_signal_output.py` | 101-103 | Added `if total_size <= 0: logger.debug(...); continue` after `total_size` aggregation |

Guard placed between `total_size = sum(...)` (line 98) and `signal = {` (now line 105). Uses `logger.debug` (appropriate — zero contracts is a normal sizing outcome, not a warning). Uses `continue` to skip to next asset in the loop.

**Verification**: grep confirms guard at lines 101-103. No downstream code depends on receiving zero-size signals.

---

## Fix M2 — VIX Provider None Logging

**Severity**: MEDIUM
**Root cause**: `_layer5_session_halt()` in the circuit breaker called `_get_current_vix()` which returns `None` when VIX CSV data is unavailable (weekends, holidays, pre-market). The existing `if vix is not None` guard was safe, but the None case was completely silent — no way to tell from logs whether Layer 5 VIX check ran or was skipped.

**Changes**:
| File | Lines | Change |
|------|-------|--------|
| `captain-online/.../b5c_circuit_breaker.py` | 417-418 | Added `if vix is None: logger.info("ON-B5C: VIX unavailable — Layer 5 VIX check skipped")` |

Placed after `vix = _get_current_vix()` (line 416) and before the existing threshold check (line 419). Uses `logger.info` — VIX unavailability is expected outside market hours and shouldn't trigger warning-level alerts.

**Verification**: grep confirms log at line 418. `logger` already defined at line 41. No functional change to circuit breaker logic.

---

## Fix M3 — journal.sqlite Volume Mount Documentation

**Severity**: MEDIUM
**Root cause**: Docker creates a directory (not a file) when a bind-mount target doesn't exist. If `journal.sqlite` files aren't pre-created, SQLite fails to open them. `captain-start.sh` handles this automatically, but manual `docker compose up` doesn't.

**Changes**:
| File | Lines | Change |
|------|-------|--------|
| `docker-compose.yml` | 59-60 | Comment above captain-offline journal.sqlite mount |
| `docker-compose.yml` | 96-97 | Comment above captain-online journal.sqlite mount |
| `docker-compose.yml` | 143-144 | Comment above captain-command journal.sqlite mount |

Each comment reads:
```yaml
      # REQUIRES: touch <process>/journal.sqlite before first run
      # captain-start.sh creates this automatically; manual docker compose does not
```

**Verification**: All 3 mounts have the comment. Documentation only — no functional change.

---

## Fix M4 — Bootstrap Variables in .env.template

**Severity**: MEDIUM
**Root cause**: `scripts/bootstrap_production.py` reads 5 `BOOTSTRAP_*` environment variables (lines 72-76) with sensible defaults, but these were undocumented in `.env.template`. New deployments (especially multi-instance) had to read the script source to find them.

**Changes**:
| File | Lines | Change |
|------|-------|--------|
| `.env.template` | 56-63 | Added `BOOTSTRAP CONFIGURATION` section with 5 commented-out variables |

Variables added (all commented out since defaults exist in the script):
- `BOOTSTRAP_ACCOUNT_ID=20319811`
- `BOOTSTRAP_USER_ID=primary_user`
- `BOOTSTRAP_STARTING_CAPITAL=150000`
- `BOOTSTRAP_MAX_POSITIONS=5`
- `BOOTSTRAP_MAX_CONTRACTS=15`

**Verification**: grep confirms all 5 variables present. Values match `bootstrap_production.py` defaults exactly.

---

## Fix M5 — Memory Limits Warning Comment

**Severity**: MEDIUM
**Root cause**: `docker-compose.local.yml` memory limits (2G online, 1.5G offline, 768M command) are sized for WSL 2 dev environments. Production workloads under heavy market conditions could OOM.

**Changes**:
| File | Lines | Change |
|------|-------|--------|
| `docker-compose.local.yml` | 10-11 | Added 2-line warning comment in file header |

Comment reads:
```yaml
#   - WARNING: Memory limits are WSL 2 dev-sized. Production needs 4G/2G minimum.
#     Monitor with: docker stats --no-stream
```

**Decision**: Actual limit values NOT changed. This is a production config decision for Nomaan. The comment documents the risk for future reference.

**Escalation note (M5)**: The orchestrator plan flagged asking whether to increase limits now. Decision: deferred — the current limits have been stable for WSL 2 development and the system hasn't exhibited OOM issues. Increasing limits is a production deployment concern, not a pre-market readiness blocker.

---

## Fix M6 — Explicit Docker Network

**Severity**: MEDIUM
**Root cause**: Docker Compose creates a default network named `{project}_default`. If the project directory is renamed (e.g., `captain-system` → `captain-v2`), the default network name changes and inter-container hostname resolution breaks silently.

**Changes**:
| File | Lines | Change |
|------|-------|--------|
| `docker-compose.yml` | 208-210 | Added top-level `networks: captain: driver: bridge` block |
| `docker-compose.yml` | 7 services | Added `networks: - captain` to all services |

All 7 services (questdb, redis, captain-offline, captain-online, captain-command, captain-gui, nginx) now use the explicit `captain` bridge network. Inter-container DNS resolution is stable regardless of project directory name.

**Verification**: Python YAML validation confirms all 7 services have `networks: ['captain']` and the top-level network block exists. Total `networks:` references = 8 (7 services + 1 definition).

---

## Fix M7 — Unused Table Documentation

**Severity**: MEDIUM
**Root cause**: `p3_d28_account_lifecycle` table is defined in `scripts/init_questdb.py` but no block references it. The table was designed for future `account_lifecycle.py` integration but is currently dead schema.

**Changes**:
| File | Lines | Change |
|------|-------|--------|
| `scripts/init_questdb.py` | 626-627 | Added 2-line NOTE inside the P3-D28 comment block |

Comment reads:
```python
    # NOTE: Table defined for future account_lifecycle.py integration.
    #       Not currently referenced by any block. See 2026-04-13 audit.
```

Table NOT deleted — it's reserved for planned future integration. Comment documents the status.

**Verification**: grep confirms NOTE at line 626. No code references this table (confirmed by QuestDB table name audit in initial findings).

---

## Fix M8 — API Startup Health Gate

**Severity**: MEDIUM
**Root cause**: `/api/health` returned HTTP 200 immediately when the FastAPI server started, before the CommandOrchestrator's daemon threads were initialized. Docker's healthcheck (which polls `/api/health` every 30s) would report the container as healthy prematurely. External monitoring could route traffic before the system was ready.

**Changes**:
| File | Lines | Change |
|------|-------|--------|
| `captain-command/.../api.py` | 74-77 | Added `set_orchestrator_ready()` function |
| `captain-command/.../api.py` | 176 | Added `_orchestrator_ready = False` flag |
| `captain-command/.../api.py` | 208-212 | Added 503 early-return guard in `health()` |
| `captain-command/.../blocks/orchestrator.py` | 154-157 | Added `set_orchestrator_ready()` call after thread starts |

**Startup sequence**:
1. `main.py` starts FastAPI via uvicorn → `/api/health` returns 503 ("STARTING")
2. Orchestrator `start()` launches 4 daemon threads (signal reader, command stream, redis listener, process log forwarder)
3. After all threads start, `set_orchestrator_ready()` sets `_orchestrator_ready = True`
4. `/api/health` now returns 200 with normal status payload
5. `_run_scheduler()` (blocking main loop) begins

**Thread safety**: `_orchestrator_ready` is a write-once boolean (False→True). GIL makes this atomic. No read-modify-write pattern.

**Import safety**: `from captain_command.api import set_orchestrator_ready` is a lazy import inside `start()`, not at module level. No circular import risk (confirmed: `api.py` does not import from `orchestrator` at module level).

**Verification**: grep confirms flag, setter, and 503 guard in api.py. grep confirms readiness call in orchestrator.py at line 155, positioned after all 4 thread starts and before `_run_scheduler()`.

---

## Test Results

**148 tests passed** in 0.71s (all unit tests excluding integration/stress/lifecycle). Zero failures.

## Docker Compose Validation

Both `docker-compose.yml` and `docker-compose.local.yml` parse as valid YAML with correct structure. All 7 services on the `captain` network. Volume and dependency references intact.

## Files Modified (8 total)

1. `docker-compose.yml` (H4, M3, M6)
2. `docker-compose.local.yml` (M5)
3. `captain-online/captain_online/blocks/b6_signal_output.py` (M1)
4. `captain-online/captain_online/blocks/b5c_circuit_breaker.py` (M2)
5. `.env.template` (M4)
6. `scripts/init_questdb.py` (M7)
7. `captain-command/captain_command/api.py` (M8)
8. `captain-command/captain_command/blocks/orchestrator.py` (M8)
