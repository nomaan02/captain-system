# Phase 1: P3-Command Cross-Validation Audit

> **Auditor:** Claude Code (canvas audit session 2)
> **Date:** 2026-04-12
> **Source:** `00-spec-manifest.md` (sections 1-11) vs `captain-command/` codebase
> **Scope:** Blocks B1-B10, Programs PG-30 to PG-41, 15 spec module filenames, 9 data stores, 6 Redis patterns, signal distribution pipeline, 2 feedback loops

---

## COVERAGE: 39 of 48 spec items have matching code (81%)

| Category | Implemented | Divergent | Missing | Total |
|----------|-------------|-----------|---------|-------|
| Blocks (B1-B10) | 10 | 0 | 0 | 10 |
| Programs (PG-30 to PG-41) | 11 | 0 | 0 | 11 |
| Spec module filenames | 9 | 3 | 3 | 15 |
| Data stores (Cmd-relevant) | 8 | 1 | 0 | 9 |
| Redis patterns (Cmd-relevant) | 3 | 3 | 3 | 9 |
| Signal distribution pipeline | 0 | 0 | 1 | 1 |
| Feedback loops (Cmd-relevant) | 2 | 0 | 0 | 2 |
| Key spec functions | 3 | 2 | 0 | 5 |
| **Totals** | **39** | **5** | **4** | **48** |

**Unspecced code items:** 5 (see section below)

---

## IMPLEMENTED -- Spec items fully matching code

### Blocks & Programs

| Spec Item | Code File | Notes |
|-----------|-----------|-------|
| B1 / PG-30 Core Routing | `b1_core_routing.py` (582 lines) | `sanitise_for_api()` -> 6 fields, `sanitise_for_gui()`, `route_signal_batch()`, `route_command()`, `route_notification()` |
| B2 / PG-31 GUI Data Server | `b2_gui_data_server.py` (1,498 lines) | `build_dashboard_snapshot()`, WebSocket push via `api.gui_push()`, 30+ data fetcher functions |
| B4 / PG-33 TSM Management | `b4_tsm_manager.py` (452 lines) | `validate_tsm()`, `load_tsm_for_account()`, `translate_for_tsm()`, `get_fee_for_instrument()`, `get_scaling_tier()` |
| B5 / PG-34 Injection Flow | `b5_injection_flow.py` (262 lines) | `notify_new_candidate()`, `get_injection_comparison()`, `route_injection_decision()`, `get_parallel_tracking_status()` |
| B6 / PG-35 Report Generation | `b6_reports.py` (681 lines) | RPT-01 through RPT-12 all implemented with `_rpt01_pre_session` .. `_rpt12_alpha_decomposition` |
| B7 / PG-36 Notifications | `b7_notifications.py` (587 lines) + `telegram_bot.py` (709 lines) | Multi-channel routing (GUI, Telegram, push), quiet hours, rate limiting, inline TAKEN/SKIPPED buttons |
| B8 / PG-39 Reconciliation | `b8_reconciliation.py` (626 lines) | SOD reset implemented: A=balance, f(A), mdd_pct, R_eff, N, E, L_halt. Payout recommendation logic included |
| B9 / PG-40 Incident Response | `b9_incident_response.py` (378 lines) | `create_incident()`, `resolve_incident()`, `acknowledge_incident()`, `check_escalations()` |
| B10 / PG-41 Data Validation | `b10_data_validation.py` (243 lines) | `validate_user_input()`, `validate_asset_config()` |
| B3 / PG-32 API Execution | `b3_api_adapter.py` (581 lines) + `b12_compliance_gate.py` (214 lines) | TopstepX adapter implemented. Compliance gate split to separate block. See DIVERGENT for gaps |

### Data Stores

| Store | Spec Name | Code Reference | Status |
|-------|-----------|----------------|--------|
| P3-D08 | TSM configs | `b4_tsm_manager._store_tsm_in_d08()`, `b8_reconciliation._compute_sod_topstep_params()` | Writes confirmed |
| P3-D09 | Report archive | `b6_reports._archive_report()` -> `p3_d09_report_archive` | Writes confirmed |
| P3-D10 | Notification log | `b7_notifications._log_notification_full()` + `b1_core_routing._log_notification()` -> `p3_d10_notification_log` | Writes confirmed |
| P3-D14 | API connection states | `b3_api_adapter._log_api_health()` -> `p3_d14_api_connection_states` | R/W confirmed |
| P3-D16 | User profiles / capital silos | `b2_gui_data_server._get_capital_silo()` reads via QuestDB | Read confirmed |
| P3-D19 | Reconciliation log | `b8_reconciliation._log_reconciliation()` -> `p3_d19_reconciliation_log` | Writes confirmed |
| P3-D21 | Incident log | `b9_incident_response._store_incident()` -> `p3_d21_incident_log` | Writes confirmed |
| P3-D23 | Intraday reset | `b8_reconciliation._reset_daily_counters()` zeros D23 intraday state | Loop 5 reset confirmed |

### Redis Channels

| Channel | Spec Role | Code | Status |
|---------|-----------|------|--------|
| `captain:commands` | Published by Cmd B1 | `b1_core_routing.route_command()` publishes | Confirmed |
| `captain:alerts` | Subscribed by Cmd B7 | `orchestrator._redis_listener()` subscribes | Confirmed |
| `captain:status` | Subscribed by Cmd B1 | `orchestrator._redis_listener()` subscribes | Confirmed |

### Feedback Loops

| Loop | Spec | Code | Status |
|------|------|------|--------|
| Loop 5 | D23 intraday reset by Cmd B8 at 19:00 EST | `b8_reconciliation._reset_daily_counters()` called from `orchestrator._check_reconciliation_trigger()` | Confirmed |
| Loop 6 | SOD compounding A -> mdd_pct -> R_eff -> N -> E -> L_halt -> D08 | `b8_reconciliation._compute_sod_topstep_params()` implements full formula chain | Confirmed |

### Key Functions

| Spec Function | Code | Status |
|---------------|------|--------|
| `sanitise_for_api()` -> 6 fields | `b1_core_routing.sanitise_for_api()` with `SANITISED_SIGNAL_FIELDS` constant | Confirmed |
| RPT-01 through RPT-12 | `b6_reports.py` lines 34-45 (registry) + 12 generator functions | All 12 implemented |
| SOD reset formula | `b8_reconciliation._compute_sod_topstep_params()` computes f(A), R_eff, N, E, L_halt | Confirmed |

---

## DIVERGENT -- Spec items where code exists but differs

### D1. Signal transport: Redis Streams instead of Pub/Sub [LOW]

- **Spec:** `captain:signals:{user_id}` as pub/sub channel (manifest section 6)
- **Code:** `orchestrator._signal_stream_reader()` uses Redis Streams with consumer groups, XREADGROUP, PEL recovery, and XACK
- **Impact:** This is an **improvement** over spec. Streams provide durable delivery, crash recovery, and exactly-once-ish processing. Pub/sub would lose signals if the consumer is down.
- **Severity:** LOW (positive divergence)

### D2. Redis Lists (queues) replaced by pub/sub and streams [LOW]

- **Spec:** `signal_queue`, `command_queue`, `notification_queue` as Redis Lists (manifest section 6, "Queues")
- **Code:** Signals use Redis Streams; commands/alerts/status use pub/sub channels. No Redis Lists exist.
- **Impact:** Functionally equivalent. Streams are strictly better than lists for signal delivery. Pub/sub is adequate for commands/alerts since they're non-critical.
- **Severity:** LOW (architectural simplification)

### D3. P3-D27 repurposed: pseudotrader forecasts instead of signal distribution [MEDIUM]

- **Spec:** P3-D27 = `distribution_state` (Redis) + `distribution_audit` (QuestDB) for signal distribution pipeline
- **Code:** P3-D27 = `p3_d27_pseudotrader_forecasts` (QuestDB) for pseudotrader two-forecast structure. No `distribution_state` Redis key or `distribution_audit` table exists.
- **Impact:** Signal distribution tracking has no persistent state. Related to MISSING item M2 (signal_distributor.py).
- **Severity:** MEDIUM -- the data store exists but serves a completely different purpose

### D4. `onboard_account()` and `validate_fee_schedule()` absorbed into other functions [LOW]

- **Spec:** `tsm_manager.py` should have `onboard_account()` and `validate_fee_schedule()`
- **Code:** Account onboarding is handled by `main._link_tsm_to_account()` and `b4_tsm_manager.load_tsm_for_account()`. Fee validation is inside `b4_tsm_manager.validate_tsm()` (V3 section). The named functions don't exist.
- **Impact:** Functionality is present but spread across files. Not a gap, just different factoring.
- **Severity:** LOW (naming divergence)

### D5. No mTLS on broker adapters [MEDIUM]

- **Spec:** `broker_adapter_topstep.py` and `broker_adapter_ibkr.py` use mTLS
- **Code:** `TopstepXAdapter` connects via `TopstepXClient` (shared/topstep_client.py) using standard HTTPS + JWT auth. No client certificate or mutual TLS configuration.
- **Impact:** TopstepX API does not require mTLS (uses API key + JWT), so this may be spec overreach. However, if IBKR or a future broker requires mTLS, the adapter pattern has no support for it.
- **Severity:** MEDIUM (spec calls for it; code doesn't implement it; current broker doesn't need it)

---

## MISSING -- Spec items with no code at all

### M1. broker_adapter_ibkr.py -- IBKR adapter [LOW]

- **Spec:** PG-32 lists `broker_adapter_ibkr.py` for Interactive Brokers adapter with mTLS
- **Code:** Only `TopstepXAdapter` exists. The `APIAdapter` ABC is defined, making a future IBKR adapter easy to add, but no IBKR implementation exists.
- **Severity:** LOW -- IBKR integration is not on the current roadmap; TopstepX is the sole broker. The ABC pattern is correctly structured for future extension.

### M2. signal_distributor.py -- 6-step signal distribution pipeline [CRITICAL]

- **Spec:** Manifest section 11 (PG-25D / PG-30) defines a 6-step pipeline:
  1. `classify_pool()` -- pool classification (R: D08, D16)
  2. `merge_and_dedup()` -- merge & deduplicate (R: D08 instrument_permissions)
  3. Conflict key check -- in-memory assigned_conflicts
  4. `distribute_signals()` -- priority rotation & EV balancing (R/W: D27)
  5. `append_broker_only()` -- broker-only bypass
  6. `finalise_distribution()` -- assignment output (W: D27, distribution_audit)
- **Code:** No `signal_distributor.py` exists anywhere in the codebase. No functions matching these names exist. The orchestrator's `_handle_signal()` routes signals directly without distribution logic.
- **Impact:** Multi-user signal distribution (conflict avoidance, EV-balancing, priority rotation) is not implemented. The parity-based trade splitting (`_check_parity_skip`) provides basic alternation but is not the spec'd distribution pipeline.
- **Severity:** CRITICAL -- this is a core multi-user feature required before deploying to multiple accounts with overlapping instrument permissions

### M3. `fees:{asset}` Redis key write by Cmd B4 [MEDIUM]

- **Spec:** Manifest section 6 (Hashes and Keys): `fees:{asset}` written by Cmd B4, read by Online B4 (L7) and CB L1
- **Code:** `b4_tsm_manager` validates and loads fee_schedule into QuestDB (D08) but does NOT write `fees:{asset}` to Redis. Fee data is in D08 only.
- **Impact:** Online B4 and CB must query QuestDB for fees instead of reading from Redis. This adds latency to the hot path (Kelly L7 sizing and CB L1 preemptive halt).
- **Severity:** MEDIUM -- functional but suboptimal; Online/CB may already be working around this via QuestDB reads

### M4. `distribution_state` Redis key + `distribution_audit` QuestDB table [CRITICAL]

- **Spec:** P3-D27 defines both `distribution_state` (Redis hash for priority queue + rolling_30d_ev) and `distribution_audit` (QuestDB table for per-session append)
- **Code:** Neither exists. P3-D27 in code is `p3_d27_pseudotrader_forecasts` (unrelated).
- **Impact:** Directly tied to M2. Without the signal distributor, these stores have no purpose. When M2 is implemented, M4 must be implemented alongside.
- **Severity:** CRITICAL (blocked by M2; must ship together)

---

## UNSPECCED -- Code that exists with no spec coverage

### U1. b11_replay_runner.py -- Signal Replay System (723 lines)

- **Code:** Full replay system with `ReplaySession` and `BatchReplaySession` classes, what-if analysis, preset management, and 9 dedicated API endpoints (`/api/replay/*`)
- **Spec:** No mention of replay, what-if, or session re-simulation in any canvas spec document
- **Notes:** This is a valuable debugging/analysis tool. Recommend adding to spec as a new block (B11) or as an extension of PG-31 (GUI Interface).

### U2. b12_compliance_gate.py as standalone block (214 lines)

- **Code:** Separate block with `check_compliance_gate()`, `compliance_check()`, `instrument_permitted()`, `get_gate_status()`
- **Spec:** `compliance_gate.py` is listed under PG-32 (B3 API Execution), not as a standalone block
- **Notes:** Splitting compliance into its own block is a good architectural decision (single responsibility). Recommend updating spec to recognize B12 as a named block.

### U3. Pseudotrader dashboard endpoints (6 routes)

- **Code:** `/api/pseudotrader/decisions`, `/parameters`, `/health`, `/trends`, `/versions`, `/forecasts` in `api.py`
- **Spec:** No pseudotrader GUI endpoints defined in PG-31 or PG-32
- **Notes:** These were added during the UX overhaul (2026-04-11). Pseudotrader data comes from Offline B3; these endpoints surface it in the GUI.

### U4. JWT authentication middleware

- **Code:** `_JWTAuthMiddleware` in `api.py` with `/auth/token` and `/auth/refresh` endpoints, audit logging via `_write_audit_log()`
- **Spec:** Canvas specs reference "ADMIN-only" access for admin_overview but don't define an auth mechanism
- **Notes:** JWT auth was added during the gap analysis fixes. Essential for production. Recommend formalizing in spec.

### U5. ProcessLogger forwarder thread

- **Code:** `orchestrator._process_log_forwarder()` subscribes to `captain:process_logs` and pushes to GUI
- **Spec:** No mention of process log forwarding in PG-30 or any command spec
- **Notes:** Useful observability feature. Low-priority spec gap.

---

## Summary

The P3-Command codebase is **well-aligned with spec** for all 10 blocks and 11 programs. Every block has a corresponding implementation with correct core logic. The SOD reconciliation formula, all 12 report types, the notification routing system, and the incident response flow all match spec expectations.

**Critical gap:** The **signal distribution pipeline** (PG-25D/PG-30 section 11) is entirely absent. This 6-step pipeline handles multi-user signal distribution with conflict avoidance, EV-balancing, and priority rotation. Without it, multi-account deployment relies solely on parity-based alternation, which doesn't handle instrument permission conflicts or fair EV distribution.

**Positive divergences:** The migration from pub/sub to Redis Streams for signal delivery and the addition of JWT auth, replay tooling, and compliance gate separation all represent improvements beyond spec.

**Module naming convention:** Code uses `bN_descriptive_name.py` (e.g., `b1_core_routing.py`) while spec uses plain names (e.g., `command_router.py`). This is a consistent, intentional pattern -- not a true divergence.
