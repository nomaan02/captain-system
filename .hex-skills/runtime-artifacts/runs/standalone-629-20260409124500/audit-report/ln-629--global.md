# Lifecycle Audit Report

<!-- AUDIT-META
worker: ln-629
category: Lifecycle
domain: global
scan_path: .
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
| bootstrap_order | Bootstrap Initialization Order | passed | All 3 processes follow correct order: config → QuestDB → Redis → consumer groups → orchestrator |
| graceful_shutdown | Graceful Shutdown | failed | captain-command signal handlers are overridden by uvicorn before they can fire |
| resource_cleanup | Resource Cleanup on Exit | failed | online orchestrator stop() does not join background thread; command orchestrator runs as daemon |
| signal_handling | Signal Handling | warning | SIGTERM + SIGINT handled in all 3 processes; SIGHUP not handled; command handler overridden by uvicorn |
| probes | Liveness / Readiness Probes | warning | captain-offline + captain-online HEALTHCHECK polls QuestDB, not the process itself |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | captain-command/captain_command/main.py:363-369 | `signal.signal(SIGTERM/SIGINT, shutdown_handler)` is called before `uvicorn.run()`, but uvicorn installs its own async event-loop signal handlers on startup, overriding the custom handler. `orchestrator.stop()` and `telegram_bot.stop()` are never called on container shutdown. | Graceful Shutdown / Signal Override | Use uvicorn's lifespan API: define an `@asynccontextmanager` lifespan function that calls `orchestrator.stop()` and `telegram_bot.stop()` on exit, then pass `app = FastAPI(lifespan=lifespan)`. Alternatively pass `install_signal_handlers=False` to `uvicorn.run()` and manage signals manually outside the uvicorn lifecycle. | M |
| MEDIUM | captain-command/captain_command/main.py:337-341 | `CommandOrchestrator` runs in a `daemon=True` thread (`cmd-orchestrator`). Daemon threads are killed immediately when the main thread (uvicorn) exits — `stop()` cannot execute. Even after fixing the signal-handler override above, any residual exit path that bypasses the shutdown handler will silently kill the orchestrator mid-operation. | Resource Cleanup / Daemon Thread | Change `daemon=False` and add `orch_thread.join(timeout=10)` inside the shutdown handler after `orchestrator.stop()`. | S |
| MEDIUM | captain-offline/Dockerfile + captain-online/Dockerfile (HEALTHCHECK lines) | The Docker HEALTHCHECK for both `captain-offline` and `captain-online` containers pings QuestDB (`http://questdb:9000/exec?query=SELECT%201`), not the container's own process. If the offline or online process crashes while QuestDB stays up, Docker reports the container as **healthy** and never restarts it. | Liveness Probes / Process Health | Add a lightweight health-signal mechanism to offline/online: write a timestamp heartbeat to a temp file (or Redis key) every N seconds in the scheduler loop. Update the HEALTHCHECK to verify this file/key is fresh (e.g., `test: ["CMD", "python", "-c", "import os,time; s=os.stat('/tmp/heartbeat'); assert time.time()-s.st_mtime<90"]`). | M |
| MEDIUM | captain-online/captain_online/blocks/orchestrator.py:86-88 | `OnlineOrchestrator.stop()` sets `self.running = False` but does not join the background `_command_listener` thread (compare: `OfflineOrchestrator.stop()` correctly joins `_redis_thread` with a 5-second timeout). In-flight command processing in online may be aborted without acknowledgement on clean shutdown. | Resource Cleanup / Thread Lifecycle | Mirror the offline pattern: store the thread reference, then in `stop()` call `self._thread.join(timeout=5.0)` and log a warning if it does not exit. | S |
| LOW | captain-offline/captain_offline/main.py:1, captain-online/captain_online/main.py:1, captain-command/captain_command/main.py:1 | None of the three entry points register a `SIGHUP` handler. On long-running daemons, SIGHUP is the standard signal for config reload without full restart. The system currently requires a container restart to pick up env-var changes. | Signal Handling / SIGHUP | Add `signal.signal(signal.SIGHUP, reload_handler)` where `reload_handler` triggers re-reading of env vars or reloading of non-frozen config files. | S |
| LOW | captain-offline/captain_offline/main.py:130-133, captain-online/captain_online/main.py:108-110, captain-command/captain_command/main.py (verify_connections) | `get_last_checkpoint(ROLE)` is called at bootstrap and the result is logged, but no recovery branch acts on it. The SQLite WAL journal was designed to enable crash-resume (e.g., skip re-seeding, skip already-loaded TSM files), but the checkpoint value is never used to alter the boot sequence. | Bootstrap Initialization / Crash Recovery | Wire the checkpoint into the startup flow: check `last["checkpoint"]` and skip already-completed phases (e.g., skip `_seed_aim_states()` if checkpoint is `AIMS_SEEDED`). This matches the documented intent of the journal. | M |
