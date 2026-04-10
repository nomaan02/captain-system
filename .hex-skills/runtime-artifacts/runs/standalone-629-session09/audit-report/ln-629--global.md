# Lifecycle Audit Report

<!-- AUDIT-META
worker: ln-629
category: Lifecycle
domain: global
scan_path: captain-command/captain_command
score: 7.1
total_issues: 6
critical: 0
high: 1
medium: 3
low: 2
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| bootstrap_order | Bootstrap Initialization Order | passed | config → QuestDB → Redis → consumer groups → TSM → Telegram → TopstepX → Orchestrator → uvicorn; correct dependency order |
| graceful_shutdown | Graceful Shutdown | failed | SIGTERM/SIGINT handlers registered before uvicorn.run(); uvicorn overrides them with asyncio handlers — shutdown_handler never executes |
| resource_cleanup | Resource Cleanup on Exit | failed | Orchestrator daemon threads not joined on stop(); Redis singleton pool never explicitly closed |
| signal_handling | Signal Handling | warning | SIGTERM/SIGINT registered but overridden by uvicorn; SIGHUP not handled |
| probes | Liveness/Readiness Probes | warning | Single /api/health endpoint serves both liveness and readiness; no separate /ready probe; Dockerfile + docker-compose healthcheck present and correct |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | `captain-command/captain_command/main.py:363-364` | `signal.signal(SIGTERM/SIGINT)` registered before `uvicorn.run()` — uvicorn installs its own asyncio signal handlers at startup, completely overriding the application handlers. `orchestrator.stop()` and `telegram_bot.stop()` are never called on container shutdown. | Graceful Shutdown / Signal Override | Migrate to FastAPI lifespan `@asynccontextmanager` or uvicorn `on_shutdown` hook; call `orchestrator.stop()` and `telegram_bot.stop()` from there instead of a signal handler | M |
| MEDIUM | `captain-command/captain_command/main.py:350` | `orchestrator` thread created with `daemon=True` — Python kills daemon threads immediately when the main thread exits, so even if the signal handler were fixed, `stop()` cannot complete before the thread is terminated | Resource Cleanup / Thread Lifecycle | Change to `daemon=False` and call `orch_thread.join(timeout=10)` in the lifespan shutdown hook after `orchestrator.stop()` | S |
| MEDIUM | `shared/redis_client.py:37-50` | Redis singleton connection pool is never explicitly closed during shutdown — `get_redis_client()` creates a module-level `_client` that is never `close()`-d, leaving socket FIN in OS TIME_WAIT for the pool's max connections | Resource Cleanup / Connection Leak | Call `get_redis_client().close()` (or `connection_pool.disconnect()`) in the lifespan shutdown hook | S |
| MEDIUM | `captain-command/captain_command/main.py:363-364` | SIGHUP not handled in any captain process — default SIGHUP disposition terminates the process, preventing config-file reload without full container restart | Signal Handling / SIGHUP | Register `signal.signal(signal.SIGHUP, lambda s,f: reload_config())` or at minimum `signal.SIG_IGN` to prevent unclean termination | S |
| LOW | `captain-command/captain_command/main.py:303-306` | `get_last_checkpoint()` called at startup and logged but return value never used — a process that crashed mid-boot (e.g. after `TOPSTEP_CONNECTED`) restarts identically to cold start, re-executing already-completed phases | Bootstrap Order / Crash Recovery | Act on `last["next_action"]` to skip completed boot phases; at minimum log a WARNING when resuming mid-sequence to alert operators | M |
| LOW | `captain-command/Dockerfile:31` + `docker-compose.yml:104-109` | Single `/api/health` endpoint used for both liveness and readiness — Kubernetes (and future orchestrators) need separate probes: liveness (is the process alive?) vs. readiness (is it ready to serve traffic, i.e., Redis+QuestDB connected?) | Probes / Probe Separation | Add `/api/ready` endpoint that checks Redis+QuestDB; keep `/api/health` as the composite status; configure separate liveness and readiness probes | S |

## Score

```
penalty = (0 × 2.0) + (1 × 1.0) + (3 × 0.5) + (2 × 0.2)
        = 0 + 1.0 + 1.5 + 0.4
        = 2.9
score   = max(0, 10 - 2.9) = 7.1
```

**7.1 / 10** — Moderate issues. Address graceful shutdown (HIGH) before production deployment; resource cleanup and SIGHUP (MEDIUM) in next sprint.

---
*Audit session: standalone-629-session09 | Scanned: 2026-04-09 | Worker: ln-629 v3.0.0*
