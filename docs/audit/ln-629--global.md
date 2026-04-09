# Lifecycle Audit Report

<!-- AUDIT-META
worker: ln-629
category: Lifecycle
domain: global
scan_path: .
score: 7.3
total_issues: 5
critical: 0
high: 1
medium: 3
low: 1
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| bootstrap_order | Bootstrap Initialization Order | passed | All 3 processes init infrastructure (QuestDB → Redis → consumer groups) before business logic |
| graceful_shutdown | Graceful Shutdown | failed | captain-command signal handlers overridden by uvicorn at startup |
| resource_cleanup | Resource Cleanup on Exit | warning | Redis pool never closed explicitly; offline/online missing stop_grace_period |
| signal_handling | Signal Handling | warning | SIGTERM+SIGINT handled in all 3 processes; SIGHUP unhandled; uvicorn override breaks command |
| probes | Liveness/Readiness Probes | warning | offline+online health checks probe QuestDB externally, not the process itself |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | captain-command/captain_command/main.py:355-364 | `signal.signal()` is registered before `uvicorn.run()`. Uvicorn overrides SIGTERM/SIGINT handlers when it starts its event loop, so `orchestrator.stop()` and `telegram_bot.stop()` are never called on Docker SIGTERM. | Signal Handling / Graceful Shutdown | Register a FastAPI lifespan shutdown handler (`@asynccontextmanager` lifespan) or use uvicorn's `on_shutdown` hook to call `orchestrator.stop()` and `telegram_bot.stop()` instead of a raw `signal.signal()`. | M |
| MEDIUM | captain-offline/Dockerfile, captain-online/Dockerfile | captain-offline and captain-online have no `stop_grace_period` in docker-compose.yml (only captain-command has 30s). Docker default is 10s. If the orchestrator is mid-session when SIGTERM arrives, the 10s window may be tight — especially if the Redis thread join times out near 5s (offline). | Resource Cleanup / Graceful Shutdown | Add `stop_grace_period: 30s` to captain-offline and captain-online in docker-compose.yml to match captain-command. | S |
| MEDIUM | captain-offline/Dockerfile:HEALTHCHECK, captain-online/Dockerfile:HEALTHCHECK | The health check for captain-offline and captain-online probes an external service (`http://questdb:9000/exec?query=SELECT%201`) rather than the process itself. A crashed orchestrator (e.g., unhandled exception in `_session_loop` or `_redis_listener`) would still be marked healthy as long as QuestDB is reachable. Docker would not restart it. | Probes / Liveness | Add a lightweight HTTP health endpoint to captain-offline and captain-online (e.g., a single-file aiohttp or Flask server writing a heartbeat flag, or a file-based heartbeat the health check reads). The orchestrator writes a timestamp file every scheduler tick; the health check verifies it is recent. | M |
| MEDIUM | captain-online/captain_online/main.py:122-126, captain-offline/captain_offline/main.py:140-146, captain-command/captain_command/main.py:355-364 | SIGHUP is not handled in any of the 3 processes. Standard Linux practice for long-running daemons is to reload config or rotate logs on SIGHUP. Without a handler, the default Python behaviour is to terminate the process. In a trading system running 24/7, an accidental SIGHUP from a script or logrotate would kill the process uncleanly. | Signal Handling / Signal Propagation | Add `signal.signal(signal.SIGHUP, signal.SIG_IGN)` at minimum to prevent accidental kills, or implement a config-reload/log-flush handler. | S |
| LOW | captain-online/captain_online/blocks/orchestrator.py:86-88 | `stop()` sets `running=False` but does not join the `_command_listener` daemon thread started in `start()`. The thread is daemon=True so it dies with the process, but mid-iteration work (ACK messages, Redis writes) is interrupted without a join. This contrasts with captain-offline which joins its Redis thread (5s timeout). | Resource Cleanup / Shutdown | Mirror captain-offline's pattern: store the `_command_listener` thread reference and join it with a timeout in `stop()`. | S |

## Evidence Notes

### Check 1 — Bootstrap Initialization Order (PASSED)

All three processes follow the correct initialization sequence:

**captain-offline** (`main.py:93-151`):
1. Logging setup
2. QuestDB verify (`get_connection()` + close)
3. Redis verify (`get_redis_client().ping()`)
4. Consumer group init (`ensure_consumer_group`)
5. Crash recovery checkpoint read
6. AIM state seed (DB idempotent operation)
7. `OfflineOrchestrator()` instantiated
8. Signal handlers registered
9. `orchestrator.start()` — blocks

**captain-online** (`main.py:78-132`):
1. Logging setup
2. QuestDB verify
3. Redis verify
4. Consumer group init
5. Crash recovery checkpoint read
6. `_start_market_streams()` — TopstepX auth + MarketStream
7. `OnlineOrchestrator()` instantiated
8. Signal handlers registered
9. `orchestrator.start()` — blocks

**captain-command** (`main.py:295-395`):
1. Logging setup
2. `verify_connections()` — QuestDB + Redis + consumer group
3. Crash recovery checkpoint read
4. `load_tsm_files()` — TSM config
5. `start_telegram_bot()` — Telegram bot
6. `_ensure_telegram_chat_id()` — D16 write
7. `_init_topstep()` — TopstepX REST auth (no WebSocket)
8. `_link_tsm_to_account()` — D08 write
9. `CommandOrchestrator()` in background daemon thread
10. Signal handlers registered ← **BEFORE uvicorn**
11. `uvicorn.run()` — **overrides signal handlers**

### Check 2 — Graceful Shutdown (FAILED — captain-command)

```python
# main.py:355-364 — registered BEFORE uvicorn.run()
def shutdown_handler(signum, frame):
    logger.info("Shutdown signal received")
    orchestrator.stop()         # ← never called
    if telegram_bot:
        telegram_bot.stop()     # ← never called
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)   # overridden by uvicorn
signal.signal(signal.SIGINT, shutdown_handler)    # overridden by uvicorn

uvicorn.run(app, host="0.0.0.0", port=8000, ...)  # installs own handlers
```

Uvicorn installs its own signal loop handlers via `asyncio`'s `add_signal_handler()`. This replaces the `signal.signal()` registrations above. On SIGTERM, uvicorn drains in-flight HTTP requests then exits. Daemon threads (orchestrator, signal stream reader, redis listener) are killed by the OS without `stop()` being called.

**captain-offline** shutdown is CORRECT — joins Redis thread:
```python
# orchestrator.py:69-76
def stop(self):
    self.running = False
    if self._redis_thread and self._redis_thread.is_alive():
        self._redis_thread.join(timeout=5.0)
```

**captain-online** shutdown sets flag only — no join:
```python
# orchestrator.py:86-88
def stop(self):
    self.running = False
    logger.info("Online orchestrator stopping...")
```

### Check 3 — Resource Cleanup (PARTIAL)

- **QuestDB**: `get_cursor()` is a context manager that opens and closes a connection per query. No persistent connection leak. ✓
- **Redis**: `get_redis_client()` returns a singleton with an internal connection pool (redis-py). Pool is never explicitly closed on shutdown. OS cleans up sockets after `sys.exit(0)`, but no clean `CLIENT QUIT` is sent to Redis.
- **MarketStream**: Explicitly stopped in captain-online shutdown handler (`market_stream.stop()`). ✓
- **Telegram bot**: Not stopped in captain-command (handler overridden by uvicorn).

### Check 4 — Signal Handling

| Process | SIGTERM | SIGINT | SIGHUP |
|---------|---------|--------|--------|
| captain-offline | ✓ custom handler | ✓ custom handler | ✗ default (terminates) |
| captain-online | ✓ custom handler | ✓ custom handler | ✗ default (terminates) |
| captain-command | ✗ overridden by uvicorn | ✗ overridden by uvicorn | ✗ default (terminates) |

### Check 5 — Liveness/Readiness Probes

| Container | Health Check | Verifies Process? |
|-----------|-------------|-------------------|
| questdb | `curl http://localhost:9000/exec?query=SELECT%201` | ✓ native |
| redis | `redis-cli ping` | ✓ native |
| captain-offline | `curl http://questdb:9000/exec?query=SELECT%201` | ✗ external |
| captain-online | `curl http://questdb:9000/exec?query=SELECT%201` | ✗ external |
| captain-command | `curl http://localhost:8000/api/health` | ✓ own endpoint |
| nginx | `wget http://127.0.0.1:80/` | ✓ own service |

captain-command's `/api/health` checks Redis, QuestDB, and API connection state — excellent. The same pattern is missing from the other two Python processes.

---

**Score: 7.3/10** | Issues: 5 (C:0 H:1 M:3 L:1)
