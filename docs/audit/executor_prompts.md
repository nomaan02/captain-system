# Captain System — Audit Executor Prompts

Paste each prompt into a fresh Claude Code session. Each session writes its findings to a file in `docs/audit/`.

---

## EXEC-01: Captain Online — Core & Ingestion

```
You are auditing the Captain trading system. Session 1 of 8.

## Context
Captain System is a 3-process Docker pipeline (Online/Offline/Command) trading futures via TopstepX.
Captain Online is the signal engine — it runs at session open (NY/LON/APAC), ingests market data,
computes regime + AIM scores, sizes via Kelly, and publishes signals to Redis.

## Skills
Invoke: `ln-629-lifecycle-auditor` (startup/shutdown/session state machines), `ln-628-concurrency-auditor` (asyncio, WebSocket, shared state)

## Files to Read
1. captain-online/captain_online/main.py
2. captain-online/captain_online/blocks/orchestrator.py (775 lines)
3. captain-online/captain_online/blocks/or_tracker.py
4. captain-online/captain_online/blocks/b1_data_ingestion.py (770 lines)
5. captain-online/captain_online/blocks/b1_features.py (1,368 lines)

## Extract Per File
For each file, report:
- **Purpose** (one line)
- **Key functions/classes** (with line numbers)
- **Session/schedule references** — how does it know when a session opens? What triggers block execution?
- **QuestDB interactions** — table name, operation (SELECT/INSERT/UPDATE), key fields, line number
- **Redis interactions** — channel name, pub or sub, payload shape, line number
- **Async patterns** — asyncio.create_task, await, locks, shared mutable state, WebSocket connections
- **Startup/shutdown** — initialization order, cleanup, graceful shutdown handling
- **Stubs/TODOs** — with line numbers
- **Notable findings** — anything surprising, risky, or smell-worthy

## Output
Write findings to: `docs/audit/captain_online.md` — under heading `## Part 1: Core & Ingestion`

## Passover
End with a summary block for the next session:
- Files audited + key findings count
- Stub count
- Cross-service dependencies discovered (Redis channels, QuestDB tables, shared modules)
- Open questions for next session (AIMs & Regime)
```

---

## EXEC-02: Captain Online — AIMs & Regime

```
You are auditing the Captain trading system. Session 2 of 8.

## Previous Session Summary (EXEC-01)
[Paste the passover block from EXEC-01 here]

## Context
Captain Online Blocks 2-3: After data ingestion and feature computation (covered in EXEC-01),
the pipeline classifies market regime (trending/mean-reverting/volatile) and aggregates
AIM (Adaptive Intelligence Module) scores using DMA (Dynamic Model Averaging) weights.
AIM scores feed into Kelly sizing in the next stage.

## Skills
Invoke: `ln-624-code-quality-auditor` (complexity, magic numbers, O(n²)), `ln-626-dead-code-auditor` (unused code, stubs)

## Files to Read
1. captain-online/captain_online/blocks/b2_regime_probability.py
2. captain-online/captain_online/blocks/b3_aim_aggregation.py
3. shared/aim_compute.py (649 lines)
4. shared/aim_feature_loader.py

## Extract Per File
For each file, report:
- **Purpose** (one line)
- **Key functions/classes** (with line numbers)
- **AIM inventory** — which AIMs are implemented vs stubbed? List each AIM ID, name, status
- **Feature computation** — what features are calculated, from which data sources?
- **Regime classifier** — what method? (HMM, threshold, rule-based?) Input features? Output states?
- **MoE/DMA aggregation** — how are AIM weights loaded and applied? Forgetting factor?
- **QuestDB interactions** — table, operation, fields, line
- **Redis interactions** — channel, pub/sub, line
- **Code quality** — cyclomatic complexity hotspots, magic numbers, deeply nested logic
- **Dead code** — unused imports, unreachable branches, commented-out blocks
- **Stubs/TODOs** — with line numbers
- **Notable findings**

## Output
Append to: `docs/audit/captain_online.md` — under heading `## Part 2: AIMs & Regime`

## Passover
End with summary block:
- Files audited, key findings, stub count
- Complete AIM inventory (ID → status)
- QuestDB tables touched (for cross-ref in EXEC-03 and EXEC-06)
- What feeds into Kelly sizing (the input contract for EXEC-03)
```

---

## EXEC-03: Captain Online — Kelly → Signal Output

```
You are auditing the Captain trading system. Session 3 of 8.

## Previous Session Summary (EXEC-02)
[Paste the passover block from EXEC-02 here]

## Context
Captain Online Blocks 4-9: After regime + AIM aggregation, the pipeline sizes positions
via Kelly criterion (7 layers), applies trade selection filters, quality gate, circuit breaker
(4 layers), then outputs signals to Redis. B7 monitors open positions for TP/SL.
B8 monitors portfolio concentration. B9 evaluates capacity constraints.

## Skills
Invoke: `ln-623-code-principles-auditor` (DRY/KISS/YAGNI, error handling), `ln-627-observability-auditor` (logging, QuestDB writes, Redis pub/sub, health)

## Files to Read
1. captain-online/captain_online/blocks/b4_kelly_sizing.py
2. captain-online/captain_online/blocks/b5_trade_selection.py
3. captain-online/captain_online/blocks/b5b_quality_gate.py
4. captain-online/captain_online/blocks/b5c_circuit_breaker.py (587 lines)
5. captain-online/captain_online/blocks/b6_signal_output.py
6. captain-online/captain_online/blocks/b7_position_monitor.py
7. captain-online/captain_online/blocks/b7_shadow_monitor.py
8. captain-online/captain_online/blocks/b8_concentration_monitor.py
9. captain-online/captain_online/blocks/b9_capacity_evaluation.py

## Extract Per File
For each file, report:
- **Purpose** (one line)
- **Key functions/classes** (with line numbers)
- **Kelly layers** — enumerate all 7 steps (raw Kelly → shrinkage → robust → ...). Are all implemented?
- **Circuit breaker layers** — enumerate all 4 layers (L1-L4). Trigger conditions? Recovery logic?
- **Signal output fields** — exact Redis payload structure published to `captain:signals:{user_id}`
- **Position monitoring** — how does B7 track TP/SL? WebSocket or polling? What triggers close?
- **Shadow monitoring** — how does B7_shadow track theoretical outcomes for parity-skipped signals?
- **QuestDB interactions** — table, operation, fields, line
- **Redis interactions** — channel, pub/sub, payload shape, line
- **DRY violations** — repeated logic across blocks (especially between B5/B5b/B5c)
- **Observability** — structured logging? Log levels? Health metrics?
- **Stubs/TODOs** — with line numbers
- **Notable findings**

## Output
Append to: `docs/audit/captain_online.md` — under heading `## Part 3: Kelly → Signal Output`

## Passover
End with summary block:
- Files audited, key findings, stub count
- Complete Kelly layer inventory (step → status)
- Complete CB layer inventory (L1-L4 → status)
- All Redis channels used by Online (for EXEC-06 cross-ref)
- All QuestDB tables used by Online (for EXEC-06 cross-ref)
- Signal output contract (fields published to Redis)
```

---

## EXEC-04a: Captain Offline — Orchestrator + B1-B2

```
You are auditing the Captain trading system. Session 4a of 8.

## Context
Captain Offline is the "strategic brain" — it runs event-driven and scheduled tasks:
AIM lifecycle management, DMA weight updates, BOCPD changepoint detection, drift detection,
pseudotrading, Kelly parameter updates, and circuit breaker recalibration.
It subscribes to trade outcomes from Redis and updates QuestDB state tables.

This session covers the orchestrator, bootstrap, and Blocks 1-2 (AIM + decay detection).

## Skills
Invoke: `ln-629-lifecycle-auditor` (startup, scheduled tasks, event handling), `ln-626-dead-code-auditor`

## Files to Read
1. captain-offline/captain_offline/main.py
2. captain-offline/captain_offline/blocks/orchestrator.py (684 lines)
3. captain-offline/captain_offline/blocks/bootstrap.py
4. captain-offline/captain_offline/blocks/version_snapshot.py
5. captain-offline/captain_offline/blocks/b1_aim_lifecycle.py
6. captain-offline/captain_offline/blocks/b1_aim16_hmm.py
7. captain-offline/captain_offline/blocks/b1_dma_update.py
8. captain-offline/captain_offline/blocks/b1_drift_detection.py
9. captain-offline/captain_offline/blocks/b1_hdwm_diversity.py
10. captain-offline/captain_offline/blocks/b2_bocpd.py
11. captain-offline/captain_offline/blocks/b2_cusum.py
12. captain-offline/captain_offline/blocks/b2_level_escalation.py

## Extract Per File
For each file, report:
- **Purpose** (one line)
- **Key functions/classes** (with line numbers)
- **Scheduled tasks** — what runs on schedule? Cron expression or interval? What triggers it?
- **Event handlers** — what Redis messages trigger what actions?
- **Category A vs B learning** — does this block learn from ALL signals (Category A) or own trades only (Category B)?
- **QuestDB interactions** — table, operation, fields, line
- **Redis interactions** — channel, pub/sub, line
- **Startup sequence** — initialization order, dependencies, health checks
- **Dead code** — unused functions, unreachable branches, commented-out blocks
- **Stubs/TODOs** — with line numbers
- **Notable findings**

## Output
Write to: `docs/audit/captain_offline.md` — under heading `## Part 1: Orchestrator + B1-B2`

## Passover
End with summary block:
- Files audited, key findings, stub count
- All scheduled tasks with timing
- All event handlers with trigger channels
- QuestDB tables touched
- Open questions for B3-B9
```

---

## EXEC-04b: Captain Offline — B3-B9

```
You are auditing the Captain trading system. Session 4b of 8.

## Previous Session Summary (EXEC-04a)
[Paste the passover block from EXEC-04a here]

## Context
Captain Offline Blocks 3-9: Pseudotrader (B3) simulates trades for backtesting.
Injection (B4) handles AIM injection flows. Sensitivity (B5) runs parameter sensitivity.
Auto-expansion (B6) manages asset universe growth. TSM simulation (B7) models account state.
CB params (B8a) and Kelly update (B8b) recalibrate risk parameters.
Diagnostic (B9) runs system health checks.

## Skills
Invoke: `ln-625-dependencies-auditor` (external deps, unused packages), `ln-624-code-quality-auditor` (complexity, patterns)

## Files to Read
1. captain-offline/captain_offline/blocks/b3_pseudotrader.py (1,431 lines — LARGE)
2. captain-offline/captain_offline/blocks/b4_injection.py
3. captain-offline/captain_offline/blocks/b5_sensitivity.py
4. captain-offline/captain_offline/blocks/b6_auto_expansion.py
5. captain-offline/captain_offline/blocks/b7_tsm_simulation.py
6. captain-offline/captain_offline/blocks/b8_cb_params.py
7. captain-offline/captain_offline/blocks/b8_kelly_update.py
8. captain-offline/captain_offline/blocks/b9_diagnostic.py (888 lines)

## Extract Per File
For each file, report:
- **Purpose** (one line)
- **Key functions/classes** (with line numbers)
- **Pseudotrader** — how does B3 simulate trades? What data does it use? How does it report outcomes?
- **Kelly update** — which of the 7 Kelly steps are recalibrated? From what data?
- **CB params** — which CB layers get updated? What's the beta_b recalibration logic?
- **QuestDB interactions** — table, operation, fields, line
- **Redis interactions** — channel, pub/sub, line
- **Code quality** — complexity hotspots, god functions, magic numbers
- **External dependencies** — numpy, scipy, pandas usage; any heavy imports?
- **Stubs/TODOs** — with line numbers
- **Notable findings**

## Output
Append to: `docs/audit/captain_offline.md` — under heading `## Part 2: B3-B9`

## Passover
End with summary block:
- Files audited, key findings, stub count
- All QuestDB tables used by Offline (complete list)
- All Redis channels used by Offline (complete list)
- External dependency inventory
- Cross-service dependencies (what does Offline expect from Online/Command?)
```

---

## EXEC-05a: Captain Command — Core + API

```
You are auditing the Captain trading system. Session 5a of 8.

## Context
Captain Command is the "linking layer" — always-on FastAPI service that:
- Routes signals from Redis to GUI and TopstepX
- Serves WebSocket to GUI for real-time updates
- Exposes REST API for manual control
- Manages TSM (Trade State Machine) for account lifecycle
- Has Docker socket access for self-update

This session covers the core: main, API, orchestrator, routing, GUI server, API adapter, TSM.

## Skills
Invoke: `ln-621-security-auditor` (API endpoints, Docker socket, vault access, auth), `ln-628-concurrency-auditor` (WebSocket, async, shared state)

## Files to Read
1. captain-command/captain_command/main.py
2. captain-command/captain_command/api.py (927 lines)
3. captain-command/captain_command/blocks/orchestrator.py (571 lines)
4. captain-command/captain_command/blocks/b1_core_routing.py (545 lines)
5. captain-command/captain_command/blocks/b2_gui_data_server.py (1,484 lines — LARGE)
6. captain-command/captain_command/blocks/b3_api_adapter.py (545 lines)
7. captain-command/captain_command/blocks/b4_tsm_manager.py

## Extract Per File
For each file, report:
- **Purpose** (one line)
- **Key functions/classes** (with line numbers)
- **API endpoints** — method, path, auth required?, input validation?, line
- **WebSocket connections** — to GUI, from Redis, connection lifecycle, reconnection logic
- **Security concerns** — Docker socket usage, vault access, input sanitization, CORS, auth
- **Parity filter** — where is `_check_parity_skip` implemented? How does the daily counter work?
- **QuestDB interactions** — table, operation, fields, line
- **Redis interactions** — channel, pub/sub, line
- **Async patterns** — concurrent access to shared state, lock usage, race conditions
- **Stubs/TODOs** — with line numbers
- **Notable findings**

## Output
Write to: `docs/audit/captain_command.md` — under heading `## Part 1: Core + API`

## Passover
End with summary block:
- Files audited, key findings, stub count
- Complete API endpoint inventory
- WebSocket connection inventory
- Security concerns ranked by severity
- Open questions for B5-B11
```

---

## EXEC-05b: Captain Command — Reports → Replay

```
You are auditing the Captain trading system. Session 5b of 8.

## Previous Session Summary (EXEC-05a)
[Paste the passover block from EXEC-05a here]

## Context
Captain Command Blocks 5-11: Injection flow (B5) handles AIM injection from GUI.
Reports (B6) generates trading reports. Notifications (B7) sends Telegram alerts.
Reconciliation (B8) verifies trade execution vs signals. Incident response (B9) handles
system failures. Data validation (B10) checks data integrity. Replay (B11) runs
session replay for debugging. Telegram bot provides remote control.

## Skills
Invoke: `ln-621-security-auditor` (Telegram bot, external API calls), `ln-627-observability-auditor` (logging, alerts, health)

## Files to Read
1. captain-command/captain_command/blocks/b5_injection_flow.py
2. captain-command/captain_command/blocks/b6_reports.py (549 lines)
3. captain-command/captain_command/blocks/b7_notifications.py (569 lines)
4. captain-command/captain_command/blocks/b8_reconciliation.py (539 lines)
5. captain-command/captain_command/blocks/b9_incident_response.py
6. captain-command/captain_command/blocks/b10_data_validation.py
7. captain-command/captain_command/blocks/b11_replay_runner.py (716 lines)
8. captain-command/captain_command/blocks/telegram_bot.py (708 lines)

## Extract Per File
For each file, report:
- **Purpose** (one line)
- **Key functions/classes** (with line numbers)
- **Telegram bot** — commands exposed, auth checks, rate limiting, sensitive data in messages?
- **Notification channels** — what triggers alerts? Priority levels? Delivery guarantees?
- **Reconciliation** — what does it compare? Signal vs execution? How often? What on mismatch?
- **Replay engine** — how does B11 invoke shared/replay_engine.py? What inputs/outputs?
- **QuestDB interactions** — table, operation, fields, line
- **Redis interactions** — channel, pub/sub, line
- **Observability** — structured logging, log levels, health metrics, alert thresholds
- **Security** — Telegram token handling, external API auth, injection vectors
- **Stubs/TODOs** — with line numbers
- **Notable findings**

## Output
Append to: `docs/audit/captain_command.md` — under heading `## Part 2: Reports → Replay`

## Passover
End with summary block:
- Files audited, key findings, stub count
- All QuestDB tables used by Command (complete list)
- All Redis channels used by Command (complete list)
- All external integrations (Telegram, TopstepX endpoints used)
- Notification/alert inventory
```

---

## EXEC-06: Cross-Cutting — Shared, Config, Triggers

```
You are auditing the Captain trading system. Session 6 of 8 (FINAL).

## Previous Session Summaries
[Paste passover blocks from EXEC-03, EXEC-04b, and EXEC-05b — specifically:
- All QuestDB tables per service
- All Redis channels per service
- All external integrations
- All scheduled tasks/triggers]

## Context
This session audits the shared library (used by all 3 processes), configuration files,
and produces cross-service aggregation tables. The shared/ directory is mounted read-only
into all containers. It contains the TopstepX client, QuestDB/Redis helpers, vault,
journal, replay engine, and AIM computation.

## Skills
Invoke: `ln-622-build-auditor` (Dockerfiles, requirements, build health), `ln-627-observability-auditor` (logging, health checks), `ln-621-security-auditor` (vault, API keys, secrets)

## Files to Read — Shared Library
1. shared/questdb_client.py
2. shared/redis_client.py
3. shared/topstep_client.py
4. shared/topstep_stream.py (716 lines)
5. shared/constants.py
6. shared/vault.py
7. shared/journal.py
8. shared/account_lifecycle.py (640 lines)
9. shared/contract_resolver.py
10. shared/bar_cache.py
11. shared/statistics.py
12. shared/vix_provider.py
13. shared/replay_engine.py (2,065 lines — LARGE, skim for structure)
14. shared/trade_source.py
15. shared/signal_replay.py
16. shared/aim_compute.py (already covered in EXEC-02, reference only)
17. shared/aim_feature_loader.py (already covered in EXEC-02, reference only)

## Files to Read — Config & Build
18. scripts/init_questdb.py (798 lines — QuestDB schema definitions)
19. config/session_registry.json
20. config/compliance_gate.json
21. config/contract_ids.json
22. captain-online/Dockerfile
23. captain-offline/Dockerfile
24. captain-command/Dockerfile
25. captain-online/requirements.txt
26. captain-offline/requirements.txt
27. captain-command/requirements.txt

## Extract Per File
For each shared file:
- **Purpose** (one line)
- **Key functions/classes** (with line numbers)
- **Which services import it** — Online, Offline, Command, or all?
- **Security** — secrets handling, encryption, token storage
- **Error handling** — connection retries, timeout handling, failure modes

For config/build files:
- **Dockerfile** — base image, multi-stage?, security (running as root?), layer efficiency
- **requirements.txt** — pinned versions? Known CVE packages?
- **init_questdb.py** — complete table inventory with column definitions

## Aggregation Tables (build from all sessions)

### Table 1: QuestDB Table Registry
| Table Name | Owner (R/W) | Readers | Key Columns | Schema Line (init_questdb.py) |

### Table 2: Redis Channel Registry
| Channel | Publisher | Subscriber(s) | Payload Shape | Purpose |

### Table 3: Session/Trigger Registry
| Trigger | Type (cron/event/startup) | Service | Handler Function | Timing |

### Table 4: External Integration Registry
| Integration | Service | Auth Method | Endpoints Used | Rate Limiting? |

### Table 5: Asset-Session Mapping
| Asset | Sessions | OR Window | Strategy (m,k) |

## Output
Write to: `docs/audit/cross_cutting.md`

## Final Summary
End with:
- Total files audited across all sessions
- Total stubs/TODOs found
- Top 10 findings ranked by severity
- Cross-service consistency issues (e.g., Redis channel name mismatches, QuestDB schema drift)
- Recommended priority fixes
```

---

## Execution Checklist

| Session | Status | Files | Findings | Stubs |
|---------|--------|-------|----------|-------|
| EXEC-01 | [ ] | /5 | | |
| EXEC-02 | [ ] | /4 | | |
| EXEC-03 | [ ] | /9 | | |
| EXEC-04a | [ ] | /12 | | |
| EXEC-04b | [ ] | /8 | | |
| EXEC-05a | [ ] | /7 | | |
| EXEC-05b | [ ] | /8 | | |
| EXEC-06 | [ ] | /27 | | |
| **Total** | | **80** | | |

### Patch Prompts
If a session misses files or has incomplete extraction, create an EXEC-XX-PATCH prompt targeting only the gaps.
