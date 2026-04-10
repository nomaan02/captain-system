<!--
AUDIT-META
worker: ln-641-pattern-analyzer
category: architecture-patterns
domain: full-codebase
scan_path: /home/nomaan/captain-system
score: 3.8/10
score_compliance: 68
score_completeness: 55
score_quality: 70
score_implementation: 72
issues_total: 97
issues_critical: 7
issues_high: 31
issues_medium: 40
issues_low: 19
status: completed
-->

# Full Codebase Pattern Analysis — Captain System

**Run ID:** standalone-641-20260409120800
**Date:** 2026-04-09
**Scope:** 10 architectural patterns across 45+ files in 3 processes + shared library
**Overall Score: 3.8/10** (C:68 K:55 Q:70 I:72)

---

## Architecture Health Dashboard

| # | Pattern | Score | C | K | Q | I | Critical | High | Medium | Low |
|---|---------|-------|---|---|---|---|----------|------|--------|-----|
| 1 | Pub/Sub / Event-Driven | 0.3/10 | 75 | 55 | 65 | 80 | 1 | 5 | 11 | 6 |
| 2 | Pipeline / Chain of Responsibility | 0.2/10 | 80 | 60 | 60 | 85 | 1 | 7 | 8 | 4 |
| 3 | Repository / Data Access | 0.0/10 | 55 | 50 | 60 | 70 | 3 | 4 | 6 | 3 |
| 4 | Strategy Pattern (AIM dispatch) | 7.0/10 | 90 | 70 | 80 | 80 | 0 | 2 | 2 | 0 |
| 5 | State Machine (account lifecycle) | 7.3/10 | 70 | 60 | 80 | 50 | 0 | 1 | 3 | 1 |
| 6 | State Machine (AIM lifecycle) | 3.1/10 | 30 | 50 | 50 | 60 | 2 | 2 | 1 | 2 |
| 7 | Circuit Breaker | 6.8/10 | 85 | 75 | 80 | 85 | 0 | 2 | 2 | 1 |
| 8 | Encryption / Vault | 6.8/10 | 90 | 60 | 85 | 70 | 0 | 2 | 2 | 1 |
| 9 | WebSocket Streaming | 6.1/10 | 85 | 75 | 75 | 70 | 0 | 2 | 3 | 2 |
| 10 | Config + Crash Recovery | 0.7/10 | 55 | 45 | 70 | 50 | 1 | 4 | 5 | 4 |
| | **TOTAL** | **3.8** | **68** | **55** | **70** | **72** | **7** | **31** | **40** | **19** |

**Legend:** C=Compliance, K=Completeness, Q=Quality, I=Implementation. Scores 0-100. Penalty formula: `score = max(0, 10 - (CRIT*2 + HIGH*1 + MED*0.5 + LOW*0.2))`

---

## Severity Distribution

```
CRITICAL ████████ 7    (14.0 penalty points)
HIGH     ████████████████████████████████ 31   (31.0 penalty points)
MEDIUM   █████████████████████████████████████████ 40   (20.0 penalty points)
LOW      ████████████████████ 19   ( 3.8 penalty points)
                                        TOTAL: 68.8 penalty points
```

---

## CRITICAL Findings (7)

These demand immediate attention. Each represents a runtime bug, security gap, or data integrity risk.

| ID | Pattern | File | Line | Finding | Effort |
|----|---------|------|------|---------|--------|
| C-01 | Pub/Sub | `captain-command/.../b1_core_routing.py` | 199-206 | **Command type mismatch:** Publishes `ADOPT_STRATEGY`/`REJECT_STRATEGY`/`PARALLEL_TRACK` to `STREAM_COMMANDS`, but offline handler only matches `ADOPTION_DECISION`. Strategy adoption commands from GUI are silently consumed and discarded. | S |
| C-02 | Data Access | `shared/questdb_client.py` | 23-29 | **No connection timeout:** `psycopg2.connect()` has no `connect_timeout`. If QuestDB is unreachable, all three processes hang indefinitely with no escape. | S |
| C-03 | Data Access | `captain-command/.../b7_notifications.py` | 433-437 | **Wrong SQL placeholder syntax:** Uses `$1,$2,...` (asyncpg/native PG style) but the driver is psycopg2 which requires `%s`. Will raise `SyntaxError` on role-based user lookup. Untested code path. | S |
| C-04 | Data Access | `shared/questdb_client.py` | 32-41 | **No retry on transient failures:** Every `get_cursor()` is a single-shot TCP connection. A transient QuestDB blip during `b1_dma_update` or `b8_kelly_update` silently skips the learning update, leaving model weights stale until the next trade. Redis and TopstepX clients both have retry logic; QuestDB does not. | S |
| C-05 | AIM Lifecycle | `captain-offline/.../b1_aim_lifecycle.py` | 88-96 | **No status validation:** `_update_aim_status()` accepts any arbitrary string and writes it to D01. GUI can bypass all lifecycle gates (feature gate, learning gate, user activation) and force any AIM to `ACTIVE` from `INSTALLED`. | S |
| C-06 | AIM Lifecycle | `captain-offline/.../b1_aim_lifecycle.py` | 233-305 | **String-literal state comparisons:** States are compared as bare strings (`== "INSTALLED"`) with no enum type safety. An invalid status written to D01 (see C-05) silently falls through all `elif` branches with no error. | L |
| C-07 | Config | `.env.template` + `captain-command/.../api.py` | 67-76 | **Auth secrets missing from template:** `JWT_SECRET_KEY` defaults to ephemeral `secrets.token_hex(32)` (all GUI sessions invalidated on restart). `API_SECRET_KEY` defaults to empty string (disables `/auth/token` login). Neither appears in `.env.template`. Fresh deployments get broken auth silently. | S |

---

## HIGH Findings (31)

### Pub/Sub / Event-Driven (5)

| ID | File | Line | Finding | Effort |
|----|------|------|---------|--------|
| H-01 | `shared/redis_client.py` | 102-129 | **No PEL recovery system-wide.** `read_stream` always uses `">"`. After a crash, messages delivered but not ACKed sit in the pending entries list forever. No `xautoclaim`/`xpending`+`xclaim` anywhere. Especially dangerous for offline's trade outcome learning loop. | M |
| H-02 | `captain-command/.../orchestrator.py` | 138-142 | **`stop()` does not join background threads.** Only sets `self.running = False`. In-flight signal processing can be abandoned mid-execution after stream pop but before ACK. Offline correctly joins with 5s timeout; command and online do not. | S |
| H-03 | `captain-online/.../orchestrator.py` | 732-734 | **MANUAL_HALT is a no-op in the online command listener.** Comment says "Stored in D17 by Command process" but no in-process flag is set. Online must poll D17 separately; if poll interval is too long, sessions execute after halt is issued. | M |
| H-04 | `captain-offline/captain_offline/main.py` | 121-122 | **`STREAM_SIGNAL_OUTCOMES` consumer group not registered at startup.** Only `STREAM_TRADE_OUTCOMES` and `STREAM_COMMANDS` are ensured in `main.py`. The group is created lazily inside the reconnect loop, creating a startup race window. | S |
| H-05 | All three orchestrators | — | **No pending message recovery at startup.** All three orchestrators create the consumer group and immediately start reading `">"`. Crashed-before-ACK messages are permanently lost. In offline, this means trade outcomes produce zero learning updates. | M |

### Pipeline / Chain of Responsibility (7)

| ID | File | Line | Finding | Effort |
|----|------|------|---------|--------|
| H-06 | `captain-online/.../orchestrator.py` | 120-128 | **TOCTOU race on position list.** `if self.open_positions:` is a bare read outside `_position_lock`. The `_command_listener` thread can modify both lists between the check and the subsequent lock acquisition. GIL-safe in CPython but formally undefined. | S |
| H-07 | `captain-online/.../orchestrator.py` | 146-281 | **`_run_session` is a 135-line god method** with 6 responsibilities: OR registration, B1-B3, per-user loop, OR tracker state, B8/B9 post-loop, checkpoints. Two distinct code paths (OR tracker vs legacy) are inline. | M |
| H-08 | `captain-online/.../orchestrator.py` | 282-375 | **No checkpoint on per-user B6 failure in Phase B.** If B6 fails for one user in a multi-user session, only `logger.error` is emitted. No `write_checkpoint`, no incident. | S |
| H-09 | `captain-online/.../orchestrator.py` | 260-280 | **Legacy path skips B8/B9 on exception.** In the non-OR-tracker path, B8 (concentration monitor) and B9 (capacity evaluation) are inside the same `try` block as the per-user loop. If any user processing throws, B8/B9 are silently skipped. | S |
| H-10 | `captain-offline/.../orchestrator.py` | 611-683 | **No `write_checkpoint` in weekly/monthly/quarterly tasks.** `_run_daily` has checkpoints at start and end. The other three scheduled tasks have only `logger.info`. A stalled monthly retrain leaves no journal record. | S |
| H-11 | `captain-offline/.../orchestrator.py` | 574 vs 624/648 | **WARM_UP assets excluded from weekly/monthly AIM retrains.** Daily queries include `WARM_UP`; weekly/monthly exclude it. Warm-up assets get drift detection daily but never receive Tier 1 retrain. | S |
| H-12 | `captain-command/.../orchestrator.py` | 104,242,315,540,545,556 | **Six naive `datetime.now()` calls** in a timezone-sensitive context. The `_check_reconciliation_trigger` fallback uses `datetime.now()` (UTC), causing reconciliation to fire at 19:00 UTC instead of 19:00 ET if `zoneinfo` import fails. | S |

### Data Access (4)

| ID | File | Line | Finding | Effort |
|----|------|------|---------|--------|
| H-13 | `captain-offline/.../b8_kelly_update.py` | 130-205 | **N+1 connection explosion:** 17 separate TCP connections per trade outcome (1 per cursor per sub-function). Each incurs full TCP handshake + close to QuestDB. | M |
| H-14 | `captain-online/.../b1_data_ingestion.py` | 49-295 | **7 loader functions use ORDER BY + Python dedup instead of QuestDB `LATEST ON`.** Fetches every historical row and sorts full table before dedup in Python. `LATEST ON` is used correctly elsewhere (`b1_dma_update`, `b8_kelly_update`). Inconsistent. | M |
| H-15 | `shared/questdb_client.py` | 38 | **Cursor not closed before connection close.** `get_cursor()` context manager closes `conn` in `finally` but never calls `cur.close()`. Under exceptions, cursor may hold server-side resources until GC. | S |
| H-16 | `shared/questdb_client.py` | 21-29 | **No connection pooling.** Every `get_cursor()` call creates a new `psycopg2.connect()`. With 25+ block files each calling multiple times per session, and GUI polling, hundreds of connections per cycle without any pool. QuestDB default limit is 64. | M |

### Strategy + State Machines (5)

| ID | File | Line | Finding | Effort |
|----|------|------|---------|--------|
| H-17 | `shared/aim_compute.py` | 637-649 | **Dead code: `_aim16_hmm()` is fully implemented but never registered in dispatch and never called.** DEC-06 removed AIM-16 from dispatch but left the function body. | S |
| H-18 | `shared/aim_compute.py` | 79-84 | **No null guard on `aim_states` parameter.** If `None` is passed, `aim_states.get("by_asset_aim", {})` raises `AttributeError`. Other dict params have same gap. | S |
| H-19 | `shared/account_lifecycle.py` | 307-358 | **LIVE stage has no failure path.** Module docstring says "Failure at any stage: $226.60 fee, revert to fresh EVAL" but `end_of_day()` only checks MLL for EVAL and XFA, not LIVE. A LIVE account with catastrophic loss stays in LIVE forever. | M |
| H-20 | `captain-offline/.../b1_aim_lifecycle.py` | 375-392 | **Suppression recovery shortcut.** `_load_meta_weight_history()` derives `consecutive_above = 0 if days_below > 0 else 10`. A single positive-weight trade after long suppression immediately satisfies the 10-trade recovery threshold. The comment explicitly says "simplified." | M |
| H-21 | `captain-offline/.../b1_aim_lifecycle.py` | (entire file) | **Zero unit tests.** No `test_b1_aim_lifecycle.py` exists. All state transitions, dual-gate logic, suppression/recovery, and tier retrain are entirely untested. | L |

### Circuit Breaker + Vault + Streaming (6)

| ID | File | Line | Finding | Effort |
|----|------|------|---------|--------|
| H-22 | `captain-online/.../b5c_circuit_breaker.py` | 154-155 | **CB trips only log at INFO, no Redis alert.** Spec blocks B7 and B6 use Redis alerts for CRITICAL events. A CB trip is operationally significant — especially Layer 1 (account survival halt) — but triggers no alert. | S |
| H-23 | `captain-online/.../b5c_circuit_breaker.py` | 574-576 | **Layer 6 manual halt is a hardcoded `return False` stub.** L6 never fires. No query to D17 `system_parameters` for a halt flag. | S |
| H-24 | `shared/vault.py` | 57 | **`aesgcm.decrypt()` raises `InvalidTag` on vault corruption/tamper — unhandled in all callers.** A corrupted vault crashes `captain-command` on startup with an unhandled `cryptography.exceptions.InvalidTag`. | S |
| H-25 | `shared/vault.py` | 78-82 | **`store_api_key` is non-atomic read-modify-write.** `load_vault()` → modify dict → `save_vault()` without file lock. Concurrent callers can overwrite each other. | S |
| H-26 | `shared/topstep_stream.py` | 378-379,645-646 | **`GatewayLogout` only logs — no state change, no alert, no re-auth.** Server-forced disconnection leaves the system believing it is still connected. | S |
| H-27 | `shared/topstep_stream.py` | 35 | **`TOKEN_REFRESH_INTERVAL_S = 20h` defined but never wired to any timer.** Tokens expire silently. No automatic refresh. The stream dies overnight without operator intervention. | M |

### Config + Crash Recovery (4)

| ID | File | Line | Finding | Effort |
|----|------|------|---------|--------|
| H-28 | `.env.template` | all | **19 env vars consumed by code have no documentation in template.** Template documents 9; code consumes 33. Missing: `QUESTDB_*`, `REDIS_*`, `VAULT_KEY_PATH`, `TSM_CONFIG_DIR`, `CAPTAIN_JOURNAL_PATH`, `BAR_CACHE_PATH`, `JWT_EXPIRY_HOURS`, `CAPTAIN_ROLE`, `TZ`. | M |
| H-29 | `docker-compose.yml` | 41-68 | **`captain-offline` missing `env_file: .env` injection.** Online and command both have it. Offline does not. Latent config landmine for future blocks that may need env vars. | S |
| H-30 | All three `main.py` | 104-108, 126-129, 303-306 | **`get_last_checkpoint()` output is logged but never acted upon.** All processes call it on startup and log "Resuming from: ..." but the returned dict is never used to alter startup behavior. The journal provides observability but not actual recovery. | M |
| H-31 | `shared/journal.py` + `shared/bar_cache.py` | 70; 93,103 | **Naive `datetime.now()` in journal timestamps.** Violates the project-wide "always America/New_York" rule. The `now_et()` helper exists in `constants.py` but is not used here. | S |

---

## MEDIUM Findings (40)

### Pub/Sub (11)

| ID | Finding | File | Effort |
|----|---------|------|--------|
| M-01 | No dead-letter queue — malformed messages are ACKed and silently dropped as `{}` | `shared/redis_client.py:123-125` | S |
| M-02 | `CH_TRADE_OUTCOMES` imported but unused (legacy dead import) | `captain-command/.../orchestrator.py:33` | S |
| M-03 | No pending message recovery at command orchestrator startup | `captain-command/.../orchestrator.py:154-167` | M |
| M-04 | Inconsistent incident creation between `_signal_stream_reader` and `_redis_listener` | `captain-command/.../orchestrator.py:172-227` | S |
| M-05 | No pending message recovery at online orchestrator startup | `captain-online/.../orchestrator.py:703-727` | M |
| M-06 | Online `stop()` does not store or join command listener thread | `captain-online/.../orchestrator.py:74-88` | S |
| M-07 | Implicit priority ordering: trade_outcomes -> signal_outcomes -> commands (undocumented) | `captain-offline/.../orchestrator.py:94-117` | M |
| M-08 | Single broad `except` in `_handle_trade_outcome` — CUSUM failure skips Kelly/EWMA for that trade | `captain-offline/.../orchestrator.py:141-178` | M |
| M-09 | No stream lag / consumer health metrics anywhere in system | All orchestrators | M |
| M-10 | Three-part reconnect loop pattern duplicated 3x across orchestrators (~30 lines each) | All three orchestrators | L |
| M-11 | Single-stream `STREAM_COMMANDS` fans out to both online+offline with no routing documentation | `b1_core_routing.py` + both orchestrators | S |

### Pipeline (8)

| ID | Finding | File | Effort |
|----|---------|------|--------|
| M-12 | `_process_user_sizing` returns `None` for both "blocked" and "exception" — no distinction | `captain-online/.../orchestrator.py:436-528` | M |
| M-13 | Session re-fires on crash before `_session_evaluated_today` is set | `captain-online/.../orchestrator.py:136-281` | S |
| M-14 | Single broad `except` in offline `_handle_trade_outcome` masks per-step failures | `captain-offline/.../orchestrator.py:141-178` | M |
| M-15 | `_handle_signal_outcome` duplicates 5 of 7 steps from `_handle_trade_outcome` (DRY) | `captain-offline/.../orchestrator.py:180-236` | M |
| M-16 | Scheduler `sleep(60)` + no persistence of last-run dates across restarts | `captain-offline/.../orchestrator.py:527-558` | M |
| M-17 | 60-second reconciliation window with no retry if scheduler is blocked | `captain-command/.../orchestrator.py:549-571` | S |
| M-18 | `_tg_send` closure redefined on every loop iteration in `_flush_quiet_queues` | `captain-command/.../orchestrator.py:505-516` | S |
| M-19 | Double GUI push for parity-skipped signals (batch + per-signal) | `captain-command/.../orchestrator.py:263-279` | S |

### Data Access (6)

| ID | Finding | File | Effort |
|----|---------|------|--------|
| M-20 | f-string SQL in `trade_source.py` — fragile pattern (currently safe, future-risk) | `shared/trade_source.py:227-231` | S |
| M-21 | f-string used in `update_d00_fields` INSERT — safe but undocumented | `shared/questdb_client.py:97-101` | S |
| M-22 | `bar_cache._initialized` global flag is not thread-safe (TOCTOU with ThreadPoolExecutor) | `shared/bar_cache.py:29,38-59` | S |
| M-23 | No read-after-write consistency handling between offline writes and online reads | Cross-process boundary | M |
| M-24 | Connection parameters evaluated at module load — no runtime re-read possible | `shared/questdb_client.py:14-18` | S |
| M-25 | Duplicate table read for `locked_strategy` in `b1_data_ingestion` (same table queried 3x) | `captain-online/.../b1_data_ingestion.py:283-319` | S |

### Strategy + State Machines (6)

| ID | Finding | File | Effort |
|----|---------|------|--------|
| M-26 | Individual `_aim*` handler functions have zero direct unit tests — test file mocks the dispatch | `shared/aim_compute.py` + `tests/test_b3_aim.py` | M |
| M-27 | `_aim03_gex()` uses binary sign check only — inconsistent with multi-tier z-score pattern | `shared/aim_compute.py:306-316` | S |
| M-28 | `_transition_to()` accepts any `TopstepStage` with no legal-transition validation | `shared/account_lifecycle.py:362-405` | S |
| M-29 | `halted_until_19est` is an implicit, untracked sub-state within LIVE | `shared/account_lifecycle.py:212,568-572` | M |
| M-30 | `process_payout()` unreachable branch at line 520 — dead code | `shared/account_lifecycle.py:499-520` | S |
| M-31 | `run_aim_lifecycle()` called without `user_activated_aims` in daily orchestrator — ELIGIBLE->ACTIVE can never trigger from scheduler | `captain-offline/.../orchestrator.py:576` | S |

### Circuit Breaker + Vault + Streaming (7)

| ID | Finding | File | Effort |
|----|---------|------|--------|
| M-32 | `_parse_json` duplicated across multiple blocks (DRY) | `b5c_circuit_breaker.py:579-586` | S |
| M-33 | `model_m=None` silently uses `l_b=0.0`, making L3/L4 ineffective for multi-basket | `b5c_circuit_breaker.py:357-358,409-410` | S |
| M-34 | No vault access audit logging — `get_api_key` calls are silent | `shared/vault.py` | S |
| M-35 | `vault-backup` Docker volume exists but vault.py never writes to it | `shared/vault.py` + `docker-compose.yml:172` | S |
| M-36 | `client._transport._skip_negotiation = True` accesses private pysignalr API | `shared/topstep_stream.py:457,715` | S |
| M-37 | Event loop never closed after `stop()` — leaks loop, triggers ResourceWarning | `shared/topstep_stream.py:254-265,547-557` | S |
| M-38 | `_create_client` is identical in both `MarketStream` and `UserStream` (DRY) | `shared/topstep_stream.py:444-458 vs 702-716` | S |

### Config + Crash Recovery (5)

| ID | Finding | File | Effort |
|----|---------|------|--------|
| M-39 | `TOPSTEP_CONTRACT_ID` defaults to expired H26 contract (March 2026 ES) | `b2_gui_data_server.py:38`, `b3_api_adapter.py:124` | M |
| M-40 | `SESSION_ID_MAP` duplicated with conflicting NY_PRE mapping (4 in constants vs 1 in replay) | `shared/replay_engine.py:52` vs `shared/constants.py:67-72` | S |
| M-41 | Journal has no pruning — unbounded row growth (5,000+ rows/year) | `shared/journal.py` | S |
| M-42 | Module-level `_initialized` flag is not thread-safe in journal.py and bar_cache.py | `shared/journal.py:19-50`, `shared/bar_cache.py:29-59` | S |
| M-43 | Journal connection-per-call sets `PRAGMA journal_mode=WAL` redundantly on every open | `shared/journal.py:63-92` | S |

---

## LOW Findings (19)

| ID | Finding | File | Effort |
|----|---------|------|--------|
| L-01 | `maxlen=1000` hard trim on streams — burst load could trim before consumer reads | `shared/redis_client.py:89` | S |
| L-02 | No stream health utility (pending count, lag, `xinfo`) exposed | `shared/redis_client.py` | M |
| L-03 | Hardcoded consumer names `command_1`/`online_1`/`offline_1` prevent multi-replica safety | All three orchestrators | S |
| L-04 | Inconsistent thread management: offline joins, command/online don't | All three orchestrators | S |
| L-05 | `_all_signals` accumulation across OR resolution not documented | `captain-online/.../orchestrator.py:347` | S |
| L-06 | `_run_tsm_for_account` has unbounded D03 query on every trade (no LIMIT) | `captain-offline/.../orchestrator.py:473-526` | S |
| L-07 | B5 (injection_flow) imported at top level but never called from command orchestrator | `captain-command/.../orchestrator.py:60-63` | S |
| L-08 | No query timing / slow-query logging anywhere in 107 call sites | `shared/questdb_client.py` | S |
| L-09 | `bar_cache.prune_cache()` exists but is never called from production code | `shared/bar_cache.py:101-114` | S |
| L-10 | `self.winning_days` accumulates in account_lifecycle but is never read or exported | `shared/account_lifecycle.py:344-345` | S |
| L-11 | N+1 query pattern in `run_tier_retrain()` — one SELECT per AIM_ID per asset | `b1_aim_lifecycle.py:329-361` | S |
| L-12 | `warmup_required()` deprecated alias raises no deprecation warning | `b1_aim_lifecycle.py:200-202` | S |
| L-13 | `_load_cb_params` fetches all accounts/rows then filters in Python | `b5c_circuit_breaker.py:470-486` | S |
| L-14 | Vault key rotation not implemented (90-day rotation mentioned in docstring but no code) | `shared/vault.py` | M |
| L-15 | `time.sleep(1)` in `update_token()` blocks the calling thread | `shared/topstep_stream.py:300,568` | S |
| L-16 | `_state` written without lock in both stream classes (GIL-safe but formally racy) | `shared/topstep_stream.py:231,258,330,354,365` | S |
| L-17 | `now_et()` uses lazy imports inside function body (unconventional, slightly wasteful) | `shared/constants.py:83-87` | S |
| L-18 | Journal `get_last_checkpoint` sorts by ISO string, not rowid | `shared/journal.py:88` | S |
| L-19 | `journal.py` has no `__main__` admin block (unlike `bar_cache.py`) | `shared/journal.py` | S |

---

## Per-Pattern Deep Analysis

### 1. Pub/Sub / Event-Driven — 0.3/10

**Architecture:** Dual-tier messaging — Redis Streams with consumer groups for durable signals/outcomes, pub/sub for non-critical alerts/status. Five channels + four streams + five consumer groups.

**What works well:**
- `ensure_consumer_group` correctly handles `BUSYGROUP` with `mkstream=True` (idempotent)
- ACK-after-process ordering in all three orchestrators (correct at-least-once semantics)
- Exponential backoff on reconnect (1s -> 30s cap)
- Offline correctly joins Redis thread with 5s timeout

**Systemic gap:** No pending entry list (PEL) recovery anywhere. After any crash, messages in flight are permanently lost. The `xautoclaim`/`xpending`+`xclaim` pattern is absent from the entire codebase. For a 24/7 trading system with `AUTO_EXECUTE=true`, this is the single highest-risk architectural gap.

---

### 2. Pipeline / Chain of Responsibility — 0.2/10

**Architecture:** Three orchestrators implementing different pipeline variants:
- **Online:** Two-phase split-chain (Phase A: B1-B5C at session open, Phase B: B6 on OR breakout)
- **Offline:** Event-driven + scheduler hybrid (7-step trade outcome chain + daily/weekly/monthly/quarterly)
- **Command:** Three-thread concurrent (signal stream, pub/sub listener, main scheduler)

**What works well:**
- Block execution order is strictly enforced via data dependencies
- Each block is a standalone module with single `run_*` entry point
- OR-tracker Phase A/B split is architecturally sound and well-commented
- All blocks are reachable and wired (B3_pseudotrader correctly invoked via B4_injection only)

**Systemic gap:** Error handling is monolithic. The offline `_handle_trade_outcome` runs 7 sequential steps (DMA -> BOCPD -> CUSUM -> level_escalation -> Kelly -> CB_params -> TSM) inside a single `try/except`. Any mid-chain failure silently abandons all downstream learning. Kelly and EWMA — the most critical feedback loop parameters — are skipped if CUSUM throws.

---

### 3. Repository / Data Access — 0.0/10

**Architecture:** `shared/questdb_client.py` provides `get_connection()` factory and `get_cursor()` context manager over psycopg2. All 25+ block files call `get_cursor()` directly. No repository class, no abstraction layer. Two higher-level helpers: `read_d00_row()` and `update_d00_fields()`.

**What works well:**
- All queries use `%s` parameterization — no SQL injection found
- `autocommit=True` is correctly set (QuestDB has no multi-statement transactions)
- Connection parameters externalized via env vars
- `LATEST ON` used correctly in `b1_dma_update` and `b8_kelly_update`

**Systemic gap:** No connection pooling, no connection timeout, no retry. The system creates hundreds of ephemeral TCP connections per session cycle against a database with a default 64-connection limit. `b8_kelly_update` alone opens 17 connections per trade. The entire data access layer has zero resilience to transient failures.

---

### 4. Strategy Pattern (AIM dispatch) — 7.0/10

**Architecture:** `shared/aim_compute.py` implements a dispatch-table Strategy pattern. 14 active handlers share uniform signature `(f: dict, state: dict) -> dict` returning `{modifier, confidence, reason_tag}`. The MoE (Mixture of Experts) orchestration in `run_aim_aggregation()` is cleanly separated from individual modifier computations.

**What works well:**
- Textbook dispatch-table variant with uniform interface
- Safe-neutral fallback (`modifier=1.0`) for unknown IDs and exceptions
- `_clamp` applied uniformly outside handlers
- Clean separation between dispatch, orchestration, and individual strategies

**Gaps:** Dead `_aim16_hmm` function body (DEC-06 removal incomplete). No null guard on entry parameters. Individual handler functions have zero direct unit tests — `test_b3_aim.py` mocks the very dispatch it should test.

---

### 5. State Machine — Account Lifecycle — 7.3/10

**Architecture:** `shared/account_lifecycle.py` implements EVAL -> XFA -> LIVE progression with `TopstepStage` enum. Transitions guarded through `_transition_to()` and `handle_failure()`. Full audit trail via `LifecycleEvent` dataclass with UUID per event.

**What works well:**
- `TopstepStage` uses `str, Enum` with all comparisons against enum members
- No direct mutation of `self.current_stage` outside guarded methods
- `get_state_snapshot()` and `to_tsm_dict()` for state export
- Comprehensive test coverage (`test_account_lifecycle.py`) including full journeys

**Gaps:** `_transition_to()` has no legal-transition guard matrix (EVAL->LIVE is accepted). LIVE stage has no failure path despite docstring claiming "failure at any stage." State machine is used only in simulation/pseudotrader, not persisted to D28 during live trading.

---

### 6. State Machine — AIM Lifecycle — 3.1/10

**Architecture:** `captain-offline/.../b1_aim_lifecycle.py` manages INSTALLED -> COLLECTING -> WARM_UP -> ELIGIBLE -> ACTIVE <-> SUPPRESSED lifecycle per AIM per asset. Feature gate + learning gate (DEC-05 dual-gate) guard progression.

**What works well:**
- All seven states are reachable in normal flow
- DEC-05 dual-gate logic (feature gate + learning gate) is conceptually sound
- `snapshot_before_update()` at ELIGIBLE->ACTIVE transition

**Systemic gaps:** States are string literals with no type safety or enum. `_update_aim_status()` has no validation — accepts any string. Suppression recovery uses a dangerous shortcut (`consecutive_above = 0 if days_below > 0 else 10`) that allows instant recovery. Zero unit tests for the entire module.

---

### 7. Circuit Breaker — 6.8/10

**Architecture:** `b5c_circuit_breaker.py` implements a 7-layer composite filter. Each layer is an independent guard function. Pure-filter (read-only) positioned at B5C in the online pipeline.

**What works well:**
- All 7 layers present with correct mathematical formulas from spec
- Cold-start handling: L3/L4 pass-through when `n_obs=0` or `beta_b=0`
- Pure-filter design (no side effects, no state writes)
- Good test coverage across `test_b5c_circuit.py`, `test_pipeline_e2e.py`, `test_stress.py`

**Gaps:** L6 manual halt is a dead stub (`return False`). CB trips emit no Redis alert. Both are operational gaps for a 24/7 system.

---

### 8. Encryption / Vault — 6.8/10

**Architecture:** `shared/vault.py` provides AES-256-GCM encryption with PBKDF2-HMAC-SHA256 key derivation (600K iterations). 12-byte random nonce per write. Used by `b3_api_adapter.py` and `telegram_bot.py`.

**What works well:**
- Correct AES-256-GCM implementation via `cryptography` library
- PBKDF2 iteration count meets NIST SP 800-132
- No hardcoded secrets; master key from env var
- Clean 4-function API

**Gaps:** `InvalidTag` exception from corrupted vault is unhandled in all callers. `store_api_key` is non-atomic read-modify-write (concurrent callers can lose writes). No key rotation. No access logging. Backup volume exists but is never written to.

---

### 9. WebSocket Streaming — 6.1/10

**Architecture:** `shared/topstep_stream.py` provides `MarketStream` and `UserStream` classes built on pysignalr's `SignalRClient`. Each runs in a dedicated daemon thread with its own asyncio event loop. Thread-safe `QuoteCache` singleton.

**What works well:**
- Correct async-in-thread bridge pattern
- Rapid-failure detection (5 failures in 10s -> stop reconnecting)
- Thread-safe `QuoteCache` with proper lock usage
- Re-subscription on every `_async_on_open` (standard SignalR pattern)

**Gaps:** `TOKEN_REFRESH_INTERVAL_S = 20h` is defined but never wired to any timer — tokens expire silently. `GatewayLogout` only logs without state change or alert. `_create_client` accesses private pysignalr API (`_transport._skip_negotiation`).

---

### 10. Config + Crash Recovery — 0.7/10

**Architecture:** Config uses 12-factor env vars for infrastructure + `shared/constants.py` for domain enums. Crash recovery uses SQLite WAL journals per process with named checkpoints.

**What works well:**
- Domain constants collected in one module with frozenset-like sets
- `SYSTEM_TIMEZONE = "America/New_York"` centralized correctly
- WAL mode correctly enabled for crash safety
- Per-process journal isolation prevents cross-process contamination

**Systemic gaps:** `.env.template` documents only 9 of 33 consumed env vars — including missing auth secrets. `captain-offline` is not injected with `.env` file. Journal checkpoints are logged but never used for actual recovery on restart. Session ID mapping conflicts between `constants.py` and `replay_engine.py` (NY_PRE = 4 vs 1).

---

## Top 10 Priority Fixes

Ordered by risk to production correctness of the live trading feedback loop.

| Priority | ID | Pattern | Fix | Effort | Impact |
|----------|-----|---------|-----|--------|--------|
| 1 | C-01 | Pub/Sub | Fix command type mismatch: `ADOPT_STRATEGY` -> `ADOPTION_DECISION` in `b1_core_routing.py` | S | Strategy adoption from GUI is currently silently discarded |
| 2 | C-02+C-04 | Data Access | Add `connect_timeout=5` and 3-attempt retry wrapper to `questdb_client.py` | S | All three processes hang or silently lose updates on transient QuestDB blip |
| 3 | H-01+H-05 | Pub/Sub | Add `xautoclaim` recovery at startup in all three orchestrators | M | Crashed-before-ACK trade outcomes permanently skip learning updates |
| 4 | C-03 | Data Access | Fix `$1` -> `%s` placeholder in `b7_notifications.py:433` | S | Runtime crash on role-based user lookup |
| 5 | C-05+C-06 | AIM Lifecycle | Validate status in `_update_aim_status()` + convert states to Enum | S+L | GUI can bypass all lifecycle gates |
| 6 | H-16 | Data Access | Add `ThreadedConnectionPool(min=2, max=10)` to `questdb_client.py` | M | Connection exhaustion under concurrent GUI + session processing |
| 7 | H-27 | Streaming | Wire `TOKEN_REFRESH_INTERVAL_S` to a background timer | M | Streams die silently after ~20h when token expires |
| 8 | C-07 | Config | Add `JWT_SECRET_KEY` and `API_SECRET_KEY` to `.env.template` | S | Fresh deployments get broken auth |
| 9 | H-12 | Pipeline | Replace `datetime.now()` with `now_et()` in command orchestrator | S | Reconciliation fires at wrong time if zoneinfo fails |
| 10 | M-08+M-14 | Pipeline | Wrap each step in offline `_handle_trade_outcome` in its own try/except | M | Single CUSUM failure silently kills Kelly/EWMA learning for that trade |

---

## Positive Findings

These patterns are implemented well and should be preserved:

1. **SQL injection prevention** — 100% parameterized queries across all 25+ block files. The only f-strings embed hardcoded constants.
2. **Redis Streams consumer group setup** — `BUSYGROUP` handling is idempotent and correct everywhere.
3. **ACK-after-process** — All three orchestrators ACK stream messages only after successful handler execution.
4. **AIM dispatch table** — Textbook Strategy pattern with uniform interface, safe fallbacks, and clean separation.
5. **Circuit breaker math** — All 7 layers implement the spec formulas correctly with proper cold-start bypass.
6. **AES-256-GCM** — Correct nonce generation, adequate PBKDF2 iterations, no hardcoded secrets.
7. **Per-process journal isolation** — Each Docker container gets its own SQLite WAL file, avoiding multi-writer conflicts.
8. **Domain constants centralized** — `shared/constants.py` is the single source for all status values, session IDs, and security boundaries.

---

<!--
DATA-EXTENDED
{
  "patterns_analyzed": 10,
  "files_examined": 48,
  "processes_covered": ["captain-offline", "captain-online", "captain-command", "shared"],
  "scoring_method": "penalty-based per audit_scoring.md v2.0.0",
  "top_systemic_risks": [
    "No PEL recovery system-wide — crashed messages are permanently lost",
    "No QuestDB connection resilience — no timeout, no retry, no pool",
    "AIM lifecycle has no type safety and no tests",
    "Journal checkpoints provide observability but zero actual recovery"
  ],
  "architecture_strengths": [
    "Dual-tier messaging (Streams for durable, pub/sub for broadcast) is well-designed",
    "Block-based pipeline with single entry points per block is clean and maintainable",
    "Circuit breaker 7-layer composite with progressive activation is spec-correct",
    "Strategy pattern dispatch table is textbook quality"
  ]
}
-->
