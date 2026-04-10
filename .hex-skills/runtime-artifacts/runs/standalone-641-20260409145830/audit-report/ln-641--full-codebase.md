# Pattern Analyzer — Full Codebase Audit Report

<!-- AUDIT-META
worker: ln-641
category: Pattern Analysis
domain: global
scan_path: .
score: 4.5
total_issues: 88
critical: 9
high: 34
medium: 32
low: 13
status: completed
patterns_analyzed: 14
architecture_health: 61.6
-->

## Summary

14 architectural patterns identified and scored across the Captain System codebase (3 processes, shared layer, config).

**Architecture Health Score: 61.6 / 100** (weighted average of all pattern diagnostic scores)

| Pattern | Score | C | K | Q | I | Issues | Risk Level |
|---------|-------|---|---|---|---|--------|------------|
| Crash Recovery / WAL Journal | 1.3/10 | 62 | 38 | 58 | 52 | 2C 3H 3M 1L | CRITICAL |
| Event-Driven (Pub/Sub) | 0.6/10 | 78 | 42 | 66 | 80 | 2C 3H 4M 2L | CRITICAL |
| Health Check / Heartbeat | 2.8/10 | 62 | 47 | 70 | 51 | 2C 2H 2M 1L | CRITICAL |
| Repository / Data Access | 4.1/10 | 58 | 42 | 60 | 68 | 0C 4H 3M 2L | SIGNIFICANT |
| Orchestrator | 4.5/10 | 72 | 68 | 71 | 75 | 0C 4H 3M 0L | SIGNIFICANT |
| State Machine | 4.6/10 | 67 | 72 | 73 | 76 | 1C 2H 2M 2L | SIGNIFICANT |
| Middleware / Decorator | 4.9/10 | 72 | 65 | 68 | 72 | 0C 3H 3M 3L | SIGNIFICANT |
| Circuit Breaker / Resilience | 5.3/10 | 62 | 63 | 72 | 76 | 0C 2H 5M 1L | MODERATE |
| Job Processing / Scheduling | 5.3/10 | 68 | 55 | 64 | 62 | 0C 3H 3M 1L | MODERATE |
| Pipeline / Chain | 5.6/10 | 77 | 68 | 74 | 83 | 0C 2H 4M 2L | MODERATE |
| Singleton | 6.1/10 | 72 | 65 | 63 | 78 | 0C 2H 3M 2L | MODERATE |
| Strategy | 6.6/10 | 62 | 71 | 60 | 74 | 0C 2H 2M 2L | MODERATE |
| Observer / Notification | 6.6/10 | 72 | 68 | 70 | 75 | 0C 2H 2M 2L | MODERATE |
| Configuration Management | 6.6/10 | 73 | 65 | 71 | 72 | 0C 2H 2M 2L | MODERATE |

**Legend:** C=Compliance, K=Completeness, Q=Quality, I=Implementation (0-100 each). Score is penalty-based (10 - weighted issues).

---

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| compliance_check | Industry standards, naming, anti-patterns | WARN | Avg 68/100 — 6 patterns below 70 |
| completeness_check | Required components, error handling, tests | FAIL | Avg 59/100 — Event-Driven 42, Repository 42, Crash Recovery 38 |
| quality_check | Readability, maintainability, SOLID, smells | WARN | Avg 67/100 — 3 patterns below 65 |
| implementation_check | Production use, integration, monitoring | WARN | Avg 71/100 — Crash Recovery 52, Health Check 51 |

---

## CRITICAL Findings (9)

| # | Pattern | Location | Issue | Recommendation | Effort |
|---|---------|----------|-------|----------------|--------|
| F-01 | Crash Recovery | `main.py` (all 3 processes) | `get_last_checkpoint()` result is logged but **never used to alter startup behavior**. Crash recovery is a no-op — the system behaves identically whether the journal exists or not. | Branch on `last["next_action"]` to skip completed startup phases or restore state context on restart. | M |
| F-02 | Crash Recovery | `shared/journal.py` | No try/except around any SQLite operation. Journal failure propagates as unhandled exception, crashing the caller. | Wrap all DB operations with try/except + logger.error; degrade gracefully. | S |
| F-03 | Event-Driven | `captain-online/blocks/b7_position_monitor.py:361-403` | Trade outcome publish has 3-retry backoff but **no DLQ**. Failed outcomes are silently dropped, permanently breaking the Offline learning feedback loop. | Write failed outcomes to SQLite journal as recoverable records; replay on next successful Redis connection. | M |
| F-04 | Event-Driven | All orchestrator stream readers | `read_stream` uses `">"` exclusively — **pending messages (PEL) from pre-crash in-flight are never reclaimed** after restart. Unacknowledged messages sit in PEL forever. | Add startup `XPENDING` + `XCLAIM` sweep in each orchestrator to reclaim stale messages. | M |
| F-05 | Health Check | `captain-online/blocks/orchestrator.py` | Online process **never publishes heartbeat** to `captain:status`. `_process_health["ONLINE"]` always shows "unknown". Health endpoint perpetually reports DEGRADED. | Add `_publish_heartbeat()` called every 30s from `_session_loop`. | S |
| F-06 | Health Check | `captain-offline/blocks/orchestrator.py` | Offline process **never publishes heartbeat** to `captain:status`. Same impact as F-05. | Add `_publish_heartbeat()` to `_run_scheduler` loop every 30s. | S |
| F-07 | State Machine | `shared/account_lifecycle.py:320-332` | `end_of_day()` MLL check gated to EVAL/XFA only. A **LIVE account with zero or negative balance continues operating** with no failure detection. | Add LIVE balance-depletion check: `if self.tradable_balance <= 0: handle_failure(day, "LIVE_BALANCE_DEPLETED")`. | S |
| F-08 | Health Check | `captain-command/api.py` `/api/health` | No readiness probe. Health endpoint does not actively query QuestDB or Redis. A **DB outage is invisible** until cached state expires. | Add `GET /api/ready` that pings QuestDB and Redis; return 503 if either fails. | S |
| F-09 | Health Check | `captain-command/api.py` `/api/health` | Liveness and readiness mixed in one endpoint. K8s-style deployment cannot distinguish "alive but not ready" from "dead". | Separate into `/api/health` (liveness) and `/api/ready` (readiness). | S |

---

## HIGH Findings (34)

| # | Pattern | Location | Issue | Effort |
|---|---------|----------|-------|--------|
| F-10 | Event-Driven | All event payloads | No event schema versioning — breaking payload changes undetectable by consumers. | S |
| F-11 | Event-Driven | All consumer handlers | No idempotency guard — duplicate delivery causes double P&L writes, double EWMA/Kelly updates. | M |
| F-12 | Event-Driven | `b6_signal_output.py:264-274` | `_publish_signals` has no retry — transient Redis error drops signal batch permanently. | S |
| F-13 | Crash Recovery | `shared/journal.py:19,35` | `_initialized` global flag has no threading lock — race condition on concurrent access. | S |
| F-14 | Crash Recovery | `journal.py` vs `init_sqlite.py` | Schema divergence: `init_sqlite.py` creates `idx_journal_checkpoint`; `journal.py` auto-init does not. | S |
| F-15 | Crash Recovery | All checkpoint callers | `state_hash` field exists in schema but is never populated in production. State corruption undetectable on recovery. | M |
| F-16 | Orchestrator | `captain-offline/blocks/orchestrator.py:130-175` | Single `except Exception` wraps 7 steps in `_handle_trade_outcome`. Step 1 failure silently skips steps 2-7. | S |
| F-17 | Orchestrator | `captain-online/main.py` shutdown | `stop()` doesn't join `_command_listener` thread. In-flight Redis ack lost on SIGTERM. | S |
| F-18 | Orchestrator | Online + Offline orchestrators | Neither publishes periodic heartbeats (same root as F-05/F-06 but Orchestrator-scoped). | S |
| F-19 | Repository | `shared/questdb_client.py:21-29` | **No connection pooling** — new TCP connection per `get_cursor()` call. `b1_features.py` makes 31 calls per session. | M |
| F-20 | Repository | `shared/questdb_client.py:32-41` | No error handling in `get_cursor()` — psycopg2 failures propagate raw with no timeout. | S |
| F-21 | Repository | `shared/questdb_client.py:81-106` | `update_d00_fields` read-then-reinsert is **not atomic** — crash between read and INSERT creates inconsistency. | S |
| F-22 | Repository | `shared/bar_cache.py:29,38-59` | `_initialized` flag has TOCTOU race — two threads can run `executescript` concurrently. | S |
| F-23 | State Machine | `shared/account_lifecycle.py:362` | `_transition_to()` has **no transition guard** — illegal sequences (EVAL→LIVE) silently succeed. | S |
| F-24 | State Machine | `shared/constants.py:13-33` | `AIM_STATUS_VALUES` and `CAPTAIN_STATUS_VALUES` are plain sets, not enums — typos undetectable at compile time. | M |
| F-25 | Singleton | `shared/vault.py:27-43` | `_derive_key()` runs **600,000-iteration PBKDF2 on every API key lookup** — no key caching. | S |
| F-26 | Singleton | `shared/vault.py:72-82` | `store_api_key()` not atomic — concurrent calls create last-writer-wins vault corruption. | S |
| F-27 | Circuit Breaker | `b5c_circuit_breaker.py:456,578` | Layer 6 manual override is a **permanent stub** (`return False`). ADMIN halt mechanism non-functional. | S |
| F-28 | Circuit Breaker | `b5c_circuit_breaker.py:48` | No Redis alert published when any CB layer trips. Operators have no real-time visibility into CB activity. | S |
| F-29 | Job Processing | Offline `_dispatch_pending_jobs` | **No DLQ**: failed jobs marked FAILED but never retried, never alerted. | M |
| F-30 | Job Processing | Offline `_run_scheduler` | Orphaned `RUNNING` jobs after restart are **never recovered** — stay RUNNING forever. | S |
| F-31 | Job Processing | Offline `_run_scheduler` | `_dispatch_pending_jobs` only called from `_run_daily` — jobs queued at 10am wait until 16:00 ET. | S |
| F-32 | Strategy | `b1_aim_lifecycle.py:350-354` | AIM trainer registry is a **commented stub** — models are never actually retrained in production. | S |
| F-33 | Strategy | `b4_kelly_sizing.py`, `b5_trade_selection.py` | No formal Strategy interface (ABC/Protocol). Open/Closed violated — adding risk goal requires editing function body. | M |
| F-34 | Observer | `b7_notifications.py` | **No retry or dead letter** for failed Telegram delivery. CRITICAL notifications can be silently dropped. | M |
| F-35 | Observer | `b7_notifications.py:168-265` | No formal Observer interface — adding a new channel requires editing `route_notification()`. | M |
| F-36 | Config | `b9_session_controller.py`, `b12_compliance_gate.py` | **No config schema validation** on load. Malformed JSON produces silent misbehavior. | S |
| F-37 | Config | `shared/vault.py:get_api_key()` | Vault loads entire keystore + runs PBKDF2 on every single API key lookup (same root as F-25). | S |
| F-38 | Middleware | `_JWTAuthMiddleware.dispatch` | Auth failures (401s) are **not logged**. Unauthorized access attempts leave no audit trail. | S |
| F-39 | Middleware | `_JWTAuthMiddleware.dispatch` | No exception handler around `call_next`. Downstream handler exceptions propagate uncaught. | S |
| F-40 | Middleware | `api.py:542,552,771,798` | `user_id` hardcoded to `"primary_user"` in 4+ REST endpoints — bypasses JWT middleware identity. | S |
| F-41 | Pipeline | `captain-offline/blocks/orchestrator.py:138-176` | All 7 offline feedback steps in single `try/except` — DMA failure silently skips BOCPD, Kelly, CB, TSM. | S |
| F-42 | Pipeline | `captain-online/blocks/orchestrator.py:185-274` | Entire Phase A pipeline in one `try/except`. B2 failure prevents B3-B6 for all users; session marked evaluated (no retry). | M |
| F-43 | Orchestrator | `captain-offline/main.py:121-122` | `STREAM_SIGNAL_OUTCOMES` consumer group registered at runtime in `_redis_listener`, not at startup. | S |

---

## MEDIUM Findings (32)

| # | Pattern | Location | Issue | Effort |
|---|---------|----------|-------|--------|
| F-44 | Event-Driven | `shared/redis_client.py:27` | `CH_TRADE_OUTCOMES` pub/sub constant defined but never used (vestigial). | S |
| F-45 | Event-Driven | `b7_position_monitor.py:477-501` | `_check_vix_spike` opens fresh DB cursor every 10s per open position for daily-changing value. | S |
| F-46 | Event-Driven | `b7:272`, `b6:34` | `_write_trade_outcome` (16 params) and `run_signal_output` (17 params) — far exceed 5-param threshold. | M |
| F-47 | Event-Driven | `b6:99`, `b7:134,386,418,519`, cmd orch | Multiple `datetime.now()` (naive, no timezone) in event timestamps. Violates system-wide ET rule. | S |
| F-48 | State Machine | `account_lifecycle.py:182`, `b4_tsm_manager.py:412` | Naive `datetime.now().isoformat()` without timezone — violates system-wide ET rule. | S |
| F-49 | State Machine | `account_lifecycle.py`, `_transition_to` | In-memory state not auto-persisted on transitions. Crash loses lifecycle events. | M |
| F-50 | Repository | `b1_features.py` | 31 inline `get_cursor()` calls with raw SQL spanning 8+ tables — bypasses query abstraction. | L |
| F-51 | Repository | `questdb_client.py:41` | `cur.close()` never called before `conn.close()` — relies on GC for cursor cleanup. | S |
| F-52 | Repository | `questdb_client.py:49-55` | `D00_COLUMNS` hardcoded — schema drift risk on any column change. | S |
| F-53 | Singleton | `vix_provider.py:42-53` | `os.path.getmtime()` syscall on every accessor invocation — hot path overhead. | S |
| F-54 | Singleton | `redis_client.py:36-51` | No `reset_for_testing()` function — test isolation requires fragile monkeypatching. | S |
| F-55 | Singleton | `contract_resolver.py:39` | Cache read outside lock — safe under CPython GIL but formally incorrect. | S |
| F-56 | Singleton | `vix_provider.py:183-190` | `reload()` sets `_loaded=False` then calls `_ensure_loaded()` outside lock — race window. | S |
| F-57 | Circuit Breaker | `b5c_circuit_breaker.py:273,303,428` | `topstep_params = parse_json(...)` duplicated in 3 layer functions — DRY violation. | S |
| F-58 | Circuit Breaker | `b5c_circuit_breaker.py:440` | `DEFAULT_VIX_CB_THRESHOLD=50.0` hardcoded — not readable from TSM or D17 at runtime. | S |
| F-59 | Circuit Breaker | `b5c:462,512` | `_load_cb_params` and `_load_intraday_state` fetch entire D23/D25 tables without WHERE filter. | S |
| F-60 | Circuit Breaker | `b5c_circuit_breaker.py` (582 lines); line 308 | File exceeds 500-line limit; magic number `4500.0` as MDD fallback. | S |
| F-61 | Circuit Breaker | `b5c:layers 3-4`, `bootstrap_production.py:276` | Bootstrap seeds only `model_m=0` but system uses per-asset m values. Extended cold-start period. | S |
| F-62 | Job Processing | Offline `_run_scheduler:538-549` | Magic numbers for schedule triggers (`hour>=16`, `weekday()==0`, `day==1`). No named constants. | S |
| F-63 | Job Processing | Offline `_run_scheduler` | No catch-up for missed daily tasks if process was down during 16:00 window. | M |
| F-64 | Job Processing | Offline `_dispatch_pending_jobs:462` | `len(returns) < 60` — magic number with no named constant. | S |
| F-65 | Strategy | `b1_aim_lifecycle.py` throughout | AIM state machine uses raw string literals — `AIM_STATUS_VALUES` set never used for validation. | S |
| F-66 | Strategy | `b4_kelly_sizing.py:43-268` | `run_kelly_sizing()` is a 200-line monolith — 12 steps inlined, untestable at step level. | M |
| F-67 | Observer | `b9_incident_response.py:~95` | `create_incident()` calls `notify_fn` directly, **bypassing** `route_notification()` — skips quiet hours, prefs, logging. | S |
| F-68 | Observer | `b7_notifications.py:358-366` | SQL placeholder uses `$N` style — inconsistent with codebase `%s` convention, likely broken at runtime. | S |
| F-69 | Observer | `telegram_bot.py:send_message()` | HTTP GET with URL-encoded body — fragile for long messages exceeding URL limits. | S |
| F-70 | Config | `shared/vault.py:24` | Fixed PBKDF2 salt `b"captain-vault-salt-v1"` — two instances with same master key share derived key. | M |
| F-71 | Config | `b9_session_controller.py:_registry_cache` | No config hot-reload — session registry changes require container restart. | S |
| F-72 | Middleware | `/auth/token` endpoint | No rate limiting on token issuance. Brute-force unlimited. | M |
| F-73 | Middleware | `_JWTAuthMiddleware` | `BaseHTTPMiddleware` buffers entire response body — overhead for large responses. | M |
| F-74 | Middleware | `questdb_client.get_cursor` | No error logging inside context manager — DB failures propagate with zero context. | S |
| F-75 | Crash Recovery | `journal.py` | No journal pruning. 260K+ rows/year per process with no cleanup. | S |

---

## LOW Findings (13)

| # | Pattern | Location | Issue | Effort |
|---|---------|----------|-------|--------|
| F-76 | Event-Driven | `cmd/orchestrator.py:505-516` | Closure inside for-loop in `_flush_quiet_queues` — late-binding risk. | S |
| F-77 | Event-Driven | All streams | No stream monitoring metrics (XLEN, XPENDING). Stuck consumer undetectable. | M |
| F-78 | Pipeline | Online orchestrator | No per-stage latency measurement. B1's 5s target undocumented and unenforced. | S |
| F-79 | Pipeline | Online orchestrator `_process_user_sizing` | `proposed_contracts` and `final_contracts` are the same dict object — redundant kwarg. | S |
| F-80 | State Machine | `b7_tsm_simulation.py:147` | 10,000 Monte Carlo paths run synchronously on orchestrator thread — blocks event loop. | M |
| F-81 | State Machine | `b4_tsm_manager.py:415`, `b7_tsm_simulation.py:174` | Raw INSERT (not UPSERT) to D08 — table grows unbounded with duplicates. | S |
| F-82 | Repository | `bar_cache.py:101-114` | `prune_cache()` never called from scheduled task — cache grows indefinitely. | S |
| F-83 | Repository | `questdb_client.py` | Zero logging — no connection events, query failures, or timing. | S |
| F-84 | Singleton | `bar_cache.py:29,44-59` | `_initialized` set without lock (same root as F-22). | S |
| F-85 | Crash Recovery | All callers | Checkpoint names are bare strings (25+ sites) — typos undetectable. | S |
| F-86 | Observer | `telegram_bot.py:_log_bot_interaction()` | Uses `"TG:{chat_id}"` instead of resolved `user_id` — audit trail inconsistent. | S |
| F-87 | Config | `compliance_gate.json:2` | Non-standard `_comment` field in JSON. | S |
| F-88 | Middleware | `api.py` | No CORS middleware configured. No request-level access logging. `request.state.user_id` populated but unused by REST endpoints. | S |

---

## Cross-Cutting Analysis

### Weakest Dimensions (across all 14 patterns)

| Dimension | Average | Worst Pattern | Root Cause |
|-----------|---------|---------------|------------|
| **Completeness** | 59.5 | Crash Recovery (38) | Missing required components: DLQs, connection pooling, schema validation, idempotency guards |
| **Compliance** | 68.3 | Repository (58) | Thin abstractions, god classes >500 lines, missing formal interfaces |
| **Quality** | 66.9 | Crash Recovery (58) | Monolithic functions, magic numbers, missing thread safety |
| **Implementation** | 71.0 | Health Check (51) | Monitoring gaps, dead features (L6 stub, journal recovery) |

### Top 5 Systemic Risks

1. **Crash recovery is instrumentation, not recovery.** The journal writes checkpoints but no process ever branches on them. A crash and restart always produces the same startup sequence. The `state_hash` and `next_action` fields are structural promises never fulfilled.

2. **Event system has no durability guarantees.** No DLQ, no idempotency, no PEL reclaim. A process crash at the wrong moment loses trade outcomes permanently, degrading the adaptive learning loop (Kelly, EWMA, BOCPD). This is the riskiest gap for a live trading system.

3. **Health endpoint is structurally misleading.** Online and Offline never publish heartbeats, so the `/api/health` always reports DEGRADED. Any monitoring system watching this endpoint cannot distinguish "system healthy" from "two of three processes are down."

4. **No QuestDB connection pooling.** 31+ new TCP connections per session in B1 alone. Under multi-user load this will degrade signal generation latency during the critical pre-market window.

5. **Vault PBKDF2 runs 600K iterations per API key lookup.** No key caching, no write locking. Concurrent `store_api_key()` calls can corrupt the vault file.

### Patterns Requiring Immediate Attention

| Priority | Pattern | Action |
|----------|---------|--------|
| P0 | Health Check | Add heartbeats from Online + Offline orchestrators. Add `/api/ready`. |
| P0 | Event-Driven | Add PEL reclaim on startup. Add DLQ fallback for trade outcomes. |
| P0 | Crash Recovery | Either implement actual recovery branching or remove the pattern to avoid false confidence. |
| P1 | Repository | Add connection pooling to `questdb_client.py`. Add error handling. |
| P1 | Singleton | Cache vault PBKDF2 derived key. Add write lock to `store_api_key`. |
| P1 | Orchestrator | Isolate per-step errors in `_handle_trade_outcome`. Join threads on stop. |
| P2 | Circuit Breaker | Implement L6 manual halt. Add alert publishing on trip. |
| P2 | Job Processing | Add DLQ. Move job dispatch to scheduler loop. Add orphan recovery. |

---

<!-- DATA-EXTENDED
{
  "patterns": [
    {"name": "Event-Driven", "score": 0.6, "diagnostic": {"C": 78, "K": 42, "Q": 66, "I": 80}, "issues": {"C": 2, "H": 3, "M": 4, "L": 2}},
    {"name": "Pipeline", "score": 5.6, "diagnostic": {"C": 77, "K": 68, "Q": 74, "I": 83}, "issues": {"C": 0, "H": 2, "M": 4, "L": 2}},
    {"name": "Circuit Breaker", "score": 5.3, "diagnostic": {"C": 62, "K": 63, "Q": 72, "I": 76}, "issues": {"C": 0, "H": 2, "M": 5, "L": 1}},
    {"name": "State Machine", "score": 4.6, "diagnostic": {"C": 67, "K": 72, "Q": 73, "I": 76}, "issues": {"C": 1, "H": 2, "M": 2, "L": 2}},
    {"name": "Repository", "score": 4.1, "diagnostic": {"C": 58, "K": 42, "Q": 60, "I": 68}, "issues": {"C": 0, "H": 4, "M": 3, "L": 2}},
    {"name": "Singleton", "score": 6.1, "diagnostic": {"C": 72, "K": 65, "Q": 63, "I": 78}, "issues": {"C": 0, "H": 2, "M": 3, "L": 2}},
    {"name": "Orchestrator", "score": 4.5, "diagnostic": {"C": 72, "K": 68, "Q": 71, "I": 75}, "issues": {"C": 0, "H": 4, "M": 3, "L": 0}},
    {"name": "Job Processing", "score": 5.3, "diagnostic": {"C": 68, "K": 55, "Q": 64, "I": 62}, "issues": {"C": 0, "H": 3, "M": 3, "L": 1}},
    {"name": "Health Check", "score": 2.8, "diagnostic": {"C": 62, "K": 47, "Q": 70, "I": 51}, "issues": {"C": 2, "H": 2, "M": 2, "L": 1}},
    {"name": "Strategy", "score": 6.6, "diagnostic": {"C": 62, "K": 71, "Q": 60, "I": 74}, "issues": {"C": 0, "H": 2, "M": 2, "L": 2}},
    {"name": "Observer", "score": 6.6, "diagnostic": {"C": 72, "K": 68, "Q": 70, "I": 75}, "issues": {"C": 0, "H": 2, "M": 2, "L": 2}},
    {"name": "Configuration", "score": 6.6, "diagnostic": {"C": 73, "K": 65, "Q": 71, "I": 72}, "issues": {"C": 0, "H": 2, "M": 2, "L": 2}},
    {"name": "Crash Recovery", "score": 1.3, "diagnostic": {"C": 62, "K": 38, "Q": 58, "I": 52}, "issues": {"C": 2, "H": 3, "M": 3, "L": 1}},
    {"name": "Middleware", "score": 4.9, "diagnostic": {"C": 72, "K": 65, "Q": 68, "I": 72}, "issues": {"C": 0, "H": 3, "M": 3, "L": 3}}
  ],
  "architecture_health": 61.6,
  "run_id": "standalone-641-20260409145830",
  "codebase_root": "/home/nomaan/captain-system",
  "files_analyzed": 42,
  "scan_date": "2026-04-09T14:58:30Z"
}
-->
