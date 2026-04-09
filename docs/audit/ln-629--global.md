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
| C1 | Bootstrap Initialization Order | passed | All 3 processes verify QuestDB/Redis before use; `ORTracker` module-level instantiation is purely structural (no I/O) |
| C2 | Graceful Shutdown | failed | captain-command: `uvicorn.run()` installs its own SIGTERM/SIGINT handlers, overriding the custom `shutdown_handler` registered at L363-364; `orchestrator.stop()` is never called on Docker SIGTERM |
| C3 | Resource Cleanup on Exit | warning | Redis connection pool not explicitly closed in any shutdown handler; captain-command `shutdown_handler` missing `write_checkpoint` call |
| C4 | Signal Handling | warning | SIGTERM/SIGINT correctly handled in captain-online and captain-offline; captain-command handlers silently overridden by uvicorn |
| C5 | Liveness/Readiness Probes | warning | Docker HEALTHCHECK present on all 3 containers; captain-online/offline health checks probe QuestDB connectivity only, not process liveness |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | `captain-command/captain_command/main.py:363-371` | `uvicorn.run()` installs its own SIGTERM/SIGINT handlers, overriding the custom `shutdown_handler` registered at L363–364. On Docker SIGTERM: `orchestrator.stop()` is never called, `telegram_bot.stop()` is never called, the orchestrator daemon thread is killed mid-flight | Graceful Shutdown / Signal Handling | Use FastAPI's `lifespan` context manager in `api.py` to hook `orchestrator.stop()` and `telegram_bot.stop()` on shutdown, or construct `uvicorn.Server(config)` directly with `server.install_signal_handlers = False` and implement custom handling | M |
| MEDIUM | `captain-online/captain_online/main.py:120-126`; `captain-offline/captain_offline/main.py:142-146`; `captain-command/captain_command/main.py:356-361` | Shutdown handlers call `sys.exit(0)` without explicitly closing the Redis singleton connection pool (`shared/redis_client.py`). In-flight pub/sub subscriptions or pending `XACK` calls are dropped silently | Resource Cleanup | Call `get_redis_client().close()` before `sys.exit(0)` in all three shutdown handlers | S |
| MEDIUM | `captain-online/Dockerfile:32-33`; `captain-offline/Dockerfile:32-33` | `HEALTHCHECK` queries QuestDB (`http://questdb:9000/exec?query=SELECT%201`), not the captain process itself. A crashed or hung Python process passes health checks indefinitely as long as QuestDB is alive; Docker will not trigger a container restart | Liveness Probes | Write a periodic heartbeat sentinel file from each orchestrator's main loop; change `HEALTHCHECK` to verify the file was touched within 2× the loop interval (e.g., `find /tmp/captain_online_heartbeat -mmin -2 \|\| exit 1`) | S-M |
| MEDIUM | `captain-command/captain_command/main.py:356-361` | captain-command `shutdown_handler` does not call `write_checkpoint(ROLE, "SHUTDOWN", ...)`. captain-online (L125) and captain-offline (L145) both write a shutdown checkpoint; captain-command is the only process that goes dark without a recovery marker | Graceful Shutdown | Add `write_checkpoint(ROLE, "SHUTDOWN", "running", "shutdown")` before `sys.exit(0)` in captain-command's `shutdown_handler` | S |
| LOW | `captain-command/captain_command/main.py:348-350` | Orchestrator thread is `daemon=True`. When uvicorn exits, Python exits immediately without joining the thread; in-flight `XREADGROUP` results being processed are silently dropped | Resource Cleanup | After the uvicorn lifespan fix (HIGH finding above), set `daemon=False` and join the thread with a timeout after calling `orchestrator.stop()` | S |
