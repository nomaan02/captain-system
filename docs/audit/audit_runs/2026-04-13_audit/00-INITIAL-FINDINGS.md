# Captain System Pre-Market Readiness Audit — Initial Findings

**Date**: 2026-04-13
**Triggered by**: Circuit breaker table name mismatch (`b5c_circuit_breaker.py:507`) blocked NY open
**Scope**: Full signal-to-trade pipeline, Docker infrastructure, config consistency
**Method**: 6 parallel deep-search agents across entire codebase
**Status**: FINDINGS CAPTURED — fixes pending

---

## Audit Agents Executed

| Agent | Scope | Duration | Result |
|-------|-------|----------|--------|
| QuestDB Table Names | 383 SQL queries vs init_questdb.py schema | ~4 min | CLEAN |
| Redis Channels | All pub/sub and stream references | ~2.5 min | 5 ISSUES |
| Imports & Modules | 60+ Python files, all import chains | ~3.8 min | CLEAN |
| Signal Pipeline E2E | B1→B7 data flow, field names, gates | ~5.8 min | 1 CRITICAL, 1 MEDIUM |
| Config & Env Vars | .env.template vs code vs docker-compose | ~2.6 min | 3 CRITICAL, 2 HIGH |
| Docker Health/Startup | Compose deps, healthchecks, race conditions | ~2.2 min | 4 CRITICAL, 3 HIGH |

---

## Finding Registry

### CRITICAL — Would Block or Silently Lose Trades

| ID | Title | Location | Description |
|----|-------|----------|-------------|
| C1 | Redis Signal Publication Silent Loss | `captain-online/.../b6_signal_output.py:287` | `publish_to_stream()` exception caught and logged but B6 returns signals as if published. Command never receives them. No retry, no alert. |
| C2 | TopstepX Auth Failure — Blind Operation | `captain-online/captain_online/main.py:43-77` | If TopstepX auth fails, `_start_market_streams()` returns None. Main logs warning and starts orchestrator anyway. B1 gets no quotes. System runs blind. |
| C3 | Contract ID Default H26 (Expired) vs M26 | `captain-command/.../b2_gui_data_server.py:39`, `b3_api_adapter.py:127` | GUI/API defaults to `CON.F.US.EP.H26` (March 2026 — expired). Scripts use M26 (June). TopstepX rejects orders on expired contracts. |
| C4 | B5 Injection Decisions Never Reach Offline | `captain-command/.../b5_injection_flow.py:176` | Publishes ADOPT_STRATEGY/PARALLEL_TRACK/REJECT_STRATEGY to pub/sub `CH_COMMANDS`. Offline reads from `STREAM_COMMANDS` (Redis Stream). Injection decisions silently lost. |
| C5 | Duplicate HALT/RESUME — Inconsistent State | `captain-command/.../b1_core_routing.py:211` + `:288` | Same command published to BOTH `STREAM_COMMANDS` and `CH_COMMANDS`. If one path fails, processes disagree on halt state. |

### HIGH — Could Block Trades Under Specific Conditions

| ID | Title | Location | Description |
|----|-------|----------|-------------|
| H1 | Command Orchestrator on Pub/Sub Not Streams | `captain-command/.../orchestrator.py:222` | Online/Offline read from `STREAM_COMMANDS` (durable). Command reads from `CH_COMMANDS` pub/sub (non-durable). Misses commands on reconnect. |
| H2 | QuestDB Connection — No Retry | `captain-online/captain_online/main.py:95-99` (all 3) | Single connection attempt. 1-second QuestDB delay = process exit. captain-start.sh works around it. |
| H3 | SESSION_WINDOW_MINUTES — 2 vs 5 | `captain-online/.../b9_session_controller.py:29` vs `config/session_registry.json` | Code defaults to 2 min. Config defines 5 min. Wrong window = missed session opens. |
| H4 | Redis Healthcheck Variable Not Expanded | `docker-compose.yml:38` | `$REDIS_PASSWORD` in CMD array not evaluated. Raw `docker compose up` hangs 180s. captain-start.sh workaround exists. |

### MEDIUM — Degraded But Won't Block Trades

| ID | Title | Location | Description |
|----|-------|----------|-------------|
| M1 | Zero-Contract Signals Published | `captain-online/.../b6_signal_output.py:70` | B6 creates signals with size=0. Command filters them (line 90) but creates log noise. |
| M2 | VIX Provider Returns None | `captain-online/.../b5c_circuit_breaker.py:417` | Layer 5 skips check safely when VIX unavailable. Missed spike detection risk. |
| M3 | journal.sqlite Volume Mount Risk | `docker-compose.yml:54,87,130` | Docker creates directory instead of file if sqlite doesn't exist. captain-start.sh pre-creates. |
| M4 | Bootstrap Vars Missing from .env.template | `scripts/bootstrap_production.py:72-76` | 5 BOOTSTRAP_* variables undocumented in template. |
| M5 | Memory Limits Low for Production | `docker-compose.local.yml` | 2GB online / 1.5GB offline may OOM under heavy market load. |
| M6 | No Explicit Docker Network | `docker-compose.yml` | Relies on default network. Project rename breaks hostname resolution. |
| M7 | Unused Table p3_d28_account_lifecycle | `scripts/init_questdb.py:628` | Defined in schema, never referenced in code. Dead schema. |
| M8 | No Startup Health Gate for API | `captain-command/captain_command/main.py:340+` | `/api/health` returns 200 before orchestrator ready. |

---

## Already Fixed (Verified)

| ID | Title | Commit | Status |
|----|-------|--------|--------|
| F1 | Circuit breaker table name mismatch | `71996db` (Apr 13) | VERIFIED — correct table names in b5c |
| F2 | QuestDB credential env var mismatch | `2d393ce` + `155bd47` (Apr 13) | VERIFIED — all references use correct vars |
| F3 | Manual halt QuestDB query syntax | Apr 9 commit | VERIFIED |
| F4 | Redis health check non-fatal | `6fc670b` (Apr 13) | VERIFIED |

---

## Audit Matrix Template

Each fix session will fill in its row upon completion:

| ID | Session | Fix Applied | Files Changed | Test Method | Verified By | Status |
|----|---------|-------------|---------------|-------------|-------------|--------|
| C1 | S1 | | | | | PENDING |
| C2 | S2 | | | | | PENDING |
| C3 | S1 | | | | | PENDING |
| C4 | S1 | | | | | PENDING |
| C5 | S1 | | | | | PENDING |
| H1 | S1 | | | | | PENDING |
| H2 | S2 | | | | | PENDING |
| H3 | S1 | | | | | PENDING |
| H4 | S3 | | | | | PENDING |
| M1 | S3 | | | | | PENDING |
| M2 | S3 | | | | | PENDING |
| M3 | S3 | | | | | PENDING |
| M4 | S3 | | | | | PENDING |
| M5 | S3 | | | | | PENDING |
| M6 | S3 | | | | | PENDING |
| M7 | S3 | | | | | PENDING |
| M8 | S3 | | | | | PENDING |
