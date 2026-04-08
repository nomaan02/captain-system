# EXEC-06: Cross-Cutting Audit -- Shared Library, Config, Build, Aggregation

**Auditor:** Claude Opus 4.6 (Session 6 of 8 -- FINAL)
**Date:** 2026-04-08
**Scope:** shared/ (18 files), config/ (3 files), Dockerfiles (3), requirements.txt (3), init_questdb.py, cross-service aggregation

---

## Part 1: Shared Library Audit

### 1. shared/questdb_client.py (107 lines)

**Purpose:** QuestDB connection helper using psycopg2 (PostgreSQL wire protocol).

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `get_connection()` | L21 | Raw psycopg2 connection to QuestDB |
| `get_cursor()` | L33 | Context manager yielding cursor with auto-commit |
| `read_d00_row()` | L58 | Read latest D00 row for asset |
| `update_d00_fields()` | L81 | Read-then-reinsert D00 helper (append-only) |

**Imported by:** ALL services (Online, Offline, Command)

**Security:** Credentials from env vars (QUESTDB_HOST/PORT/USER/PASSWORD/DB). Defaults: admin/quest on port 8812. No TLS support for the PG wire connection.

**Error handling:** No connection pooling -- each `get_cursor()` call creates a new connection. No retry logic. No timeout configured on psycopg2.connect(). Connection closed in `finally` block (correct).

**Notable findings:**
- FINDING-S01: **No connection pooling.** Every query opens and closes a fresh TCP connection. Under high load (Online processing 10 assets simultaneously), this could exhaust file descriptors or cause latency spikes. Consider psycopg2.pool.ThreadedConnectionPool.
- FINDING-S02: **Default credentials hardcoded.** admin/quest is the QuestDB default. Not a security issue in Docker-internal networking but would be if port 8812 were exposed externally.
- FINDING-S03: **No query timeout.** A slow QuestDB query could block the calling thread indefinitely. No `connect_timeout` or `options='-c statement_timeout=...'` set.

---

### 2. shared/redis_client.py (132 lines)

**Purpose:** Redis connection singleton with pub/sub channels and durable stream helpers.

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `get_redis_client()` | L36 | Singleton Redis client with connection pool |
| `get_redis_pubsub()` | L54 | PubSub instance from singleton |
| `signals_channel()` | L59 | Per-user signal channel name |
| `publish_to_stream()` | L82 | XADD with maxlen=1000 |
| `ensure_consumer_group()` | L94 | Idempotent XGROUP CREATE |
| `read_stream()` | L106 | XREADGROUP with blocking |
| `ack_message()` | L130 | XACK for processed messages |

**Channel constants (L25-30):**
| Constant | Value | Purpose |
|----------|-------|---------|
| CH_SIGNALS | `captain:signals:{user_id}` | Legacy pub/sub (per-user) |
| CH_TRADE_OUTCOMES | `captain:trade_outcomes` | Legacy pub/sub |
| CH_COMMANDS | `captain:commands` | Command routing |
| CH_ALERTS | `captain:alerts` | Alert broadcast |
| CH_STATUS | `captain:status` | Heartbeat |

**Stream constants (L69-79):**
| Constant | Value | Purpose |
|----------|-------|---------|
| STREAM_SIGNALS | `stream:signals` | Durable signal delivery |
| STREAM_TRADE_OUTCOMES | `stream:trade_outcomes` | Durable outcome delivery |
| STREAM_COMMANDS | `stream:commands` | Durable command delivery |
| STREAM_SIGNAL_OUTCOMES | `stream:signal_outcomes` | Theoretical outcomes (shadow) |

**Consumer groups (L75-79):**
| Constant | Value |
|----------|-------|
| GROUP_COMMAND_SIGNALS | `command_signals` |
| GROUP_OFFLINE_OUTCOMES | `offline_outcomes` |
| GROUP_OFFLINE_COMMANDS | `offline_commands` |
| GROUP_ONLINE_COMMANDS | `online_commands` |
| GROUP_OFFLINE_SIGNAL_OUTCOMES | `offline_signal_outcomes` |

**Imported by:** ALL services

**Security:** No Redis AUTH configured. No TLS. Acceptable for Docker-internal network only.

**Error handling:** Socket timeout 5s, connect timeout 5s, retry_on_error for TimeoutError, health_check_interval=30s. Good. Thread-safe singleton via double-checked locking.

**Notable findings:**
- FINDING-S04: **Dual messaging (pub/sub + streams).** The system uses BOTH Redis pub/sub channels (CH_SIGNALS etc.) AND Redis Streams (STREAM_SIGNALS etc.) for overlapping purposes. Signals moved to streams for durability, but commands/alerts/status still use pub/sub (fire-and-forget). This is intentional but creates two mental models.
- FINDING-S05: **Stream maxlen=1000.** Each stream is capped at 1000 messages. At high signal volumes this could cause undelivered messages if a consumer falls behind by >1000 messages. In practice unlikely (signals are per-session, a few per day).

---

### 3. shared/topstep_client.py (415 lines)

**Purpose:** REST API client for TopstepX brokerage (18 endpoints: auth, orders, positions, bars, trades).

**Key classes/functions:**
| Item | Line | Description |
|------|------|-------------|
| `TopstepXClient` | L88 | Thread-safe REST client |
| `authenticate()` | L103 | Initial auth via /Auth/loginKey |
| `validate_token()` | L123 | Token refresh via /Auth/validate |
| `get_accounts()` | L164 | List accounts |
| `place_order()` | L211 | Place order (all types) |
| `place_market_order()` | L229 | Convenience market order |
| `search_positions()` | L297 | Current positions |
| `close_position()` | L302 | Close position |
| `get_bars()` | L193 | Historical OHLCV bars |
| `get_topstep_client()` | L408 | Module-level singleton |

**Imported by:** Online (B7 position monitor, B1 data), Command (B3 API adapter, B2 GUI)

**Security:** API key from env var (TOPSTEP_API_KEY). Token stored in-memory only. Token auto-refresh at 20h (24h expiry). Session object reused for HTTP connection pooling. No secrets logged.

**Error handling:** Auto token refresh via `_ensure_token()`. HTTP errors parsed via `_parse_response()`. Custom exception hierarchy (TopstepXClientError -> AuthenticationError, APIError). Thread lock on token refresh.

**Notable findings:**
- FINDING-S06: **No rate limiting.** No throttling between API calls. TopstepX could reject rapid requests. No retry-with-backoff on 429/5xx responses.
- FINDING-S07: **No request timeout.** `requests.post()` calls have no explicit timeout parameter. A hung API server would block the thread indefinitely.
- FINDING-S08: **Duplicate import.** `from datetime import timedelta` appears at both L7 (via AlgorithmImports) and L282 (inline). Minor but indicates code that was patched incrementally.

---

### 4. shared/topstep_stream.py (716 lines)

**Purpose:** WebSocket streaming via pysignalr for live market data (MarketStream) and user events (UserStream).

**Key classes:**
| Class | Line | Description |
|-------|------|-------------|
| `QuoteCache` | L70 | Thread-safe quote storage |
| `MarketStream` | L117 | Market data hub (quotes, trades, depth) |
| `UserStream` | L465 | User event hub (account, orders, positions, trades) |
| `StreamState` | L57 | Enum: DISCONNECTED/CONNECTING/CONNECTED/RECONNECTING/ERROR/STOPPED |

**Imported by:** Online (B1 data ingestion, B7 monitor), Command (B2 GUI data server, B3 API adapter)

**Security:** Token passed at connection time. No token logged. Token refresh via `update_token()` method (reconnects).

**Error handling:** Rapid-failure detection in `_async_on_close()` -- counts consecutive fast disconnects (< 30s), stops reconnect after 5 rapid failures. pysignalr handles internal reconnection. GatewayLogout event handled (stops stream).

**Notable findings:**
- FINDING-S09: **No import of shared modules.** topstep_stream.py does NOT import from shared/ (no questdb_client, no redis_client). It is truly standalone -- good separation.
- Symbol map built from `config/contract_ids.json` at startup (L178-218). Falls back gracefully if JSON not found.

---

### 5. shared/constants.py (112 lines)

**Purpose:** Code-level enum enforcement for QuestDB (which has no native enums).

**Key constants:**
| Constant | Values | Used By |
|----------|--------|---------|
| CAPTAIN_STATUS_VALUES | ACTIVE, WARM_UP, TRAINING_ONLY, INACTIVE, DATA_HOLD, ROLL_PENDING, PAUSED, DECAYED | D00 status validation |
| AIM_STATUS_VALUES | INSTALLED...ACTIVE, SUPPRESSED | D01 lifecycle |
| TRADE_OUTCOME_VALUES | TP_HIT, SL_HIT, MANUAL_CLOSE, TIME_EXIT | D03 outcomes |
| SESSION_IDS | {1: NY, 2: LON, 3: APAC} | Session identification |
| REGIME_VALUES | LOW_VOL, HIGH_VOL | Regime labels |
| COMMAND_TYPE_VALUES | 14 command types | B1 routing |
| SANITISED_SIGNAL_FIELDS | 6 fields | External API safety |
| PROHIBITED_EXTERNAL_FIELDS | 9 fields | Never sent externally |
| SOD_RESET_HOUR/MINUTE | 19:00 | Circuit breaker daily reset |
| SYSTEM_TIMEZONE | America/New_York | System-wide TZ |

**Imported by:** ALL services

**Notable findings:**
- FINDING-S10: **SESSION_IDS mismatch with session_registry.json.** constants.py defines {1: NY, 2: LON, 3: APAC} but session_registry.json defines sessions as {NY, LONDON, NY_PRE, APAC}. "LON" vs "LONDON" and "NY_PRE" is not in SESSION_IDS at all. This could cause session matching failures for ZN, ZB, MGC assets.

---

### 6. shared/vault.py (82 lines)

**Purpose:** AES-256-GCM encrypted API key vault.

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `_derive_key()` | L27 | PBKDF2-SHA256 key derivation (600K iterations) |
| `load_vault()` | L46 | Decrypt and parse vault file |
| `save_vault()` | L61 | Encrypt and write vault file |
| `get_api_key()` | L72 | Retrieve key for account |
| `store_api_key()` | L78 | Store key for account |

**Imported by:** Command (B3 API adapter)

**Security:**
- AES-256-GCM with 12-byte random nonce per save
- PBKDF2 with 600,000 iterations (current best practice)
- Master key from VAULT_MASTER_KEY env var
- Fixed salt `captain-vault-salt-v1` -- acceptable since uniqueness comes from master key
- Vault path: `/captain/vault/keys.vault`

**Error handling:** Raises RuntimeError if VAULT_MASTER_KEY not set. Returns empty dict if vault file doesn't exist.

**Notable findings:**
- FINDING-S11: **Race condition in save_vault().** Two concurrent save_vault() calls could corrupt the vault file (no file locking). In practice only Command B3 uses vault, so single-writer. But worth noting.
- FINDING-S12: **No vault backup.** If the vault file is corrupted, API keys are lost. No backup mechanism.

---

### 7. shared/journal.py (103 lines)

**Purpose:** SQLite WAL crash recovery journal (P3-D20).

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `get_journal_connection()` | L22 | Auto-initializing SQLite connection |
| `write_checkpoint()` | L54 | Write recovery checkpoint |
| `get_last_checkpoint()` | L83 | Read latest checkpoint for component |

**Imported by:** ALL services (heavily by Command for audit trail)

**Error handling:** Auto-creates directory, database file, and table on first access. WAL mode enabled for concurrent reads during writes.

**Notable findings:**
- FINDING-S13: **Connection opened and closed on every call.** Both write_checkpoint() and get_last_checkpoint() open a new connection, do one operation, then close. Not a performance issue for SQLite but slightly inefficient.

---

### 8. shared/account_lifecycle.py (640 lines)

**Purpose:** TopstepX account lifecycle state machine: EVAL -> XFA -> LIVE with automatic transitions.

**Key classes:**
| Class | Line | Description |
|-------|------|-------------|
| `TopstepStage` | L51 | Enum: EVAL, XFA, LIVE |
| `TopstepEvalAccount` | L63 | EVAL rules ($4500 MLL, $9K target) |
| `TopstepXFAAccount` | L88 | XFA rules (scaling plan, 5 payouts max) |
| `TopstepLiveAccount` | L127 | LIVE rules (daily drawdown, capital unlock) |
| `MultiStageTopstepAccount` | L185 | Full lifecycle state machine |

**Constants:** EVAL_STARTING_BALANCE=150K, EVAL_MLL=4500, EVAL_PROFIT_TARGET=9000, XFA_MAX_PAYOUTS=5, LIVE_DAILY_DRAWDOWN=4500, LIVE_TRADABLE_CAP=30K

**Imported by:** Offline (B3 pseudotrader)

**Error handling:** Comprehensive stage validation. Failure at any stage reverts to fresh EVAL with $226.60 fee.

**Notable findings:** Well-structured state machine with proper lifecycle events. No external dependencies (pure logic).

---

### 9. shared/contract_resolver.py (150 lines)

**Purpose:** Maps asset IDs to TopstepX contract IDs with 4-tier resolution: cache -> config JSON -> D00 roll_calendar -> API search.

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `resolve_contract_id()` | L32 | Main resolver (4-tier fallback) |
| `preload_contracts()` | L65 | Startup preload |
| `invalidate()` | L90 | Cache clear (contract roll) |

**Imported by:** Online (B1 data, B1 features, B7 shadow), Command (B2 GUI, B3 API)

**Error handling:** Thread-safe cache with lock. Graceful fallback on each tier. Returns None if unresolvable (caller must handle). Debug-level logging on failures (appropriate -- resolution failures are expected for unused assets).

---

### 10. shared/bar_cache.py (127 lines)

**Purpose:** SQLite WAL cache for TopstepX historical 1-min bars. Avoids re-fetching for same date/asset/session.

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `get_cached_bars()` | L63 | Retrieve cached bars |
| `cache_bars()` | L80 | Store bars (INSERT OR REPLACE) |
| `prune_cache()` | L101 | Delete entries older than N days |

**Imported by:** Replay engine (shared/replay_engine.py)

**Error handling:** Auto-creates database and table on first access. Primary key enforces uniqueness.

---

### 11. shared/statistics.py (146 lines)

**Purpose:** Anti-overfitting validation functions (PBO and DSR from academic papers).

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `compute_pbo()` | L29 | Probability of Backtest Overfitting via CSCV (Paper 152) |
| `compute_dsr()` | L111 | Deflated Sharpe Ratio (Paper 150) |

**Imported by:** Offline (B3 pseudotrader, B5 sensitivity, B6 auto-expansion)

**Dependencies:** numpy, scipy.stats

**Notable findings:** Well-documented with paper references. Handles edge cases (insufficient data, zero variance). Subsamples at >50K combinations to keep computation tractable.

---

### 12. shared/vix_provider.py (190 lines)

**Purpose:** VIX/VXV daily close data provider from bundled CSV files.

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `get_latest_vix_close()` | L107 | Most recent VIX close |
| `get_trailing_vix_closes()` | L126 | Last N VIX closes |
| `get_trailing_vix_daily_changes()` | L139 | Last N absolute daily changes |
| `get_latest_vxv_close()` | L168 | Most recent VXV close |
| `reload()` | L183 | Force CSV reload |

**Imported by:** Online (B1 features, B5C circuit breaker)

**Error handling:** Lazy loading with thread-safe lock. Auto-reload if CSV modified (mtime check). Graceful degradation if CSV not found (returns None). Good.

**Notable findings:**
- FINDING-S14: **Static CSV data requires manual updates.** VIX/VXV CSVs must be manually updated for live trading. No automated daily fetch mechanism.

---

### 13. shared/replay_engine.py (2065 lines)

**Purpose:** Full session replay engine -- replays the entire Online pipeline (data fetch -> regime -> AIM -> sizing -> signal -> outcome) against historical data.

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `load_replay_config()` | L59 | Loads config from QuestDB + overrides |
| `fetch_session_bars()` | L508 | Fetches bars from API with caching |
| `simulate_orb()` | L556 | Simulates ORB trade entry/exit |
| `compute_contracts()` | L889 | Full Kelly+AIM+CB contract sizing |
| `run_replay()` | L1479 | Main replay orchestrator |
| `run_whatif()` | L1880 | What-if comparison (current vs proposed) |

**QuestDB tables read:** D00, D05, D07, D08, D12, D16, D25, D26, D03

**Imported by:** Command (B11 replay runner)

**Dependencies:** shared.questdb_client, shared.bar_cache, shared.topstep_client, shared.aim_compute, shared.aim_feature_loader, requests, zoneinfo

**Notable findings:**
- FINDING-S15 (CRITICAL): **Wrong table name `p3_d25_circuit_breaker`.** Line 289 queries `p3_d25_circuit_breaker` but the actual table is `p3_d25_circuit_breaker_params`. This will silently fail (empty result) and disable circuit breaker modifiers in replay.
- Complex 2065-line file that reimplements the Online pipeline. Any changes to Online blocks must be manually mirrored here -- high drift risk.

---

### 14. shared/trade_source.py (320 lines)

**Purpose:** Trade data abstraction: loads from synthetic P1 backtest logs or live D03 QuestDB table.

**Key functions:**
| Function | Line | Description |
|----------|------|-------------|
| `load_trades()` | L38 | Main dispatcher (synthetic or questdb) |
| `_load_synthetic()` | L75 | P1 d22 trade log converter |
| `_load_from_d03()` | L196 | Live trade reader from QuestDB |
| `seed_d03_from_synthetic()` | L272 | Seed D03 with synthetic data |

**Imported by:** Offline (via signal_replay), shared/signal_replay.py

**Notable findings:**
- FINDING-S16: **Duplicate import.** Line 6 has `from shared.questdb_client import get_cursor` imported twice (lines 6 and 7). Harmless but indicates copy-paste error.

---

### 15. shared/signal_replay.py (517 lines)

**Purpose:** Offline signal pipeline replay (sizing_replay and strategy_replay) for pseudotrader/sensitivity/expansion.

**Key classes:**
| Class | Line | Description |
|-------|------|-------------|
| `SignalReplayEngine` | L68 | Replays B2-B5 pipeline with configurable params |
| `.sizing_replay()` | L84 | Same trades, different AIM/Kelly sizing |
| `.strategy_replay()` | L213 | Different SL/TP/threshold + sizing |
| `.load_replay_context()` | L434 | Static data loader helper |

**Imported by:** Offline (B3 pseudotrader, B5 sensitivity, B6 auto-expansion)

**Notable findings:** Pure computation -- no side effects on Redis/QuestDB. Clean separation of concerns. Two calling conventions (direct and config-dict) for flexibility.

---

### 16. shared/aim_compute.py (649 lines) -- PREVIOUSLY AUDITED (EXEC-02)

**Purpose:** AIM modifier computation for all 16 AIM types. Already covered in EXEC-02.

### 17. shared/aim_feature_loader.py (409 lines) -- PREVIOUSLY AUDITED (EXEC-02)

**Purpose:** Loads AIM feature data from QuestDB tables (D29-D33). Already covered in EXEC-02.

---

## Part 2: Config & Build File Audit

### 18. config/session_registry.json (66 lines)

**Purpose:** Session timing definitions (OR start/end, EOD times, filters) and asset-to-session mapping.

**Sessions defined:** NY, LONDON, NY_PRE, APAC
**Asset mapping:** 19 assets across 4 sessions

**Notable findings:**
- FINDING-C01: **Session name mismatch.** `LONDON` in JSON vs `LON` in constants.py SESSION_IDS. `NY_PRE` exists in JSON but not in SESSION_IDS at all.
- FINDING-C02: **ZN/ZB mapped to NY_PRE, not NY.** CLAUDE.md says both are "NY" session, but session_registry.json maps them to NY_PRE (06:00 ET open). This may be intentional (treasuries trade earlier) but conflicts with the locked strategy table in CLAUDE.md.

---

### 19. config/compliance_gate.json (14 lines)

**Purpose:** RTS-6 compliance gate flags. All 11 checks enabled.

**Notable findings:** All gates enabled (true). This is a configuration file only -- the actual enforcement logic lives in Command blocks. No code references were found that read this file, suggesting the compliance checks may be hardcoded rather than driven by this config.

---

### 20. config/contract_ids.json (76 lines)

**Purpose:** Verified TopstepX contract ID mappings for all 10 active assets.

**Assets mapped:** ES, MES, NQ, MNQ, M2K, MYM, NKD, MGC, ZB, ZN
**Expiry:** All June 2026 (M26) except MGC (April J26)
**Note:** MGC April expiry will need a roll before April expiry.

---

### 21-23. Dockerfiles

All three Dockerfiles follow the same pattern:

| Property | Online | Offline | Command |
|----------|--------|---------|---------|
| Base image | python:3.12-slim | python:3.12-slim | python:3.12-slim |
| Multi-stage | No | No | No |
| System deps | tzdata, curl | tzdata, curl | tzdata, curl, git, docker CLI + compose |
| Runs as | root (default) | root (default) | root (default) |
| Timezone | America/New_York | America/New_York | America/New_York |
| Health check | curl QuestDB HTTP | curl QuestDB HTTP | curl localhost:8000/api/health |
| Config bake | COPY _config/ /captain/config/ | COPY _config/ /captain/config/ | COPY _config/ /captain/config/ |

**Notable findings:**
- FINDING-C03: **All containers run as root.** No USER directive. Standard practice for dev but a security hardening gap for production. A compromised container has full filesystem access.
- FINDING-C04: **Command Dockerfile installs Docker CLI + Compose (172 MB).** Lines 9-14 install docker-27.5.1 and compose-v2.35.1 for the git-pull rebuild feature. This significantly increases image size and attack surface. Only Command needs this.
- FINDING-C05: **No .dockerignore audit.** If large files (data/, logs/, .git/) are not ignored, COPY . will bloat the image.
- Layer caching is good: requirements.txt copied and installed before application code.

---

### 24-26. requirements.txt

| Package | Online | Offline | Command | Notes |
|---------|--------|---------|---------|-------|
| psycopg2-binary | >=2.9 | >=2.9 | >=2.9 | All three |
| redis | >=5.0 | >=5.0 | >=5.0 | All three |
| numpy | >=1.24 | >=1.24 | >=1.24 | All three |
| scipy | >=1.10 | >=1.10 | - | Online+Offline |
| scikit-learn | >=1.3 | >=1.3 | - | Online+Offline |
| pydantic | >=2.0 | >=2.0 | >=2.0 | All three |
| pysignalr | >=1.0 | - | >=1.0 | Online+Command |
| requests | >=2.25.0 | - | >=2.25.0* | Online+Command |
| tenacity | >=8.0 | - | >=8.0 | Online+Command |
| hmmlearn | - | >=0.3 | - | Offline only |
| xgboost | ==2.0.3 | - | - | Online only (pinned!) |
| fastapi | - | - | >=0.104 | Command only |
| uvicorn | - | - | >=0.24 | Command only |
| websockets | - | - | >=12.0 | Command only |
| cryptography | - | - | >=41.0 | Command only (vault) |
| httpx | - | - | >=0.25 | Command only |
| python-telegram-bot | - | - | >=21.0 | Command only |
| pytz | >=2024.1 | - | - | Online only |

**Notable findings:**
- FINDING-C06: **Mostly unpinned versions.** Only xgboost is pinned (==2.0.3). All other deps use >= ranges. A `pip install` could pull breaking changes. Recommend pinning all versions or using a lock file.
- FINDING-C07: **scikit-learn in Online but unused.** Per EXEC-03 passover, scikit-learn was flagged as unused in Online. It adds ~200MB to the image.
- FINDING-C08: **Command needs requests but it is not listed.** Command uses `shared/topstep_client.py` which imports requests, and `shared/replay_engine.py` which imports requests. Command's requirements.txt does not list requests. It may be pulled in as a transitive dependency of httpx, but this is fragile.
- FINDING-C09: **numpy in Command requirements.** Command does not directly use numpy, but `shared/replay_engine.py` (imported by B11) uses it implicitly through aim_compute. The dependency is correct but non-obvious.

---

### 27. scripts/init_questdb.py (798 lines)

**Purpose:** Creates all QuestDB tables. Claims "30 tables" in header but actually defines **36 CREATE TABLE statements** (see Table 1 below).

---

## Part 3: Aggregation Tables

### Table 1: QuestDB Table Registry

| # | Table Name | Schema Line | Owner (writes) | Readers | Partition | Key Columns |
|---|-----------|-------------|----------------|---------|-----------|-------------|
| 1 | p3_d00_asset_universe | L42 | Command, Online B1 | All | by last_updated | asset_id(S), captain_status, locked_strategy, roll_calendar |
| 2 | p3_d01_aim_model_states | L71 | Offline B1 | Online B3, Command B2 | by last_updated | aim_id, asset_id(S), status, current_modifier |
| 3 | p3_d02_aim_meta_weights | L89 | Offline B1 | Online B3, Command B2 | by last_updated | aim_id, asset_id(S), inclusion_probability, inclusion_flag |
| 4 | p3_d03_trade_outcome_log | L105 | Online B7 | Offline, Command B6 | DAY | trade_id, asset(S), pnl, direction, outcome |
| 5 | p3_d04_decay_detector_states | L136 | Offline B2 | Command B6 | by last_updated | asset_id(S), bocpd_cp_probability |
| 6 | p3_d05_ewma_states | L159 | Offline B8 | Online B4, Replay | by last_updated | asset_id(S), regime, win_rate, avg_win, avg_loss |
| 7 | p3_d06_injection_history | L176 | Offline B4 | Command B5, B6 | MONTH | asset(S), recommendation, status |
| 8 | p3_d06b_active_transitions | L197 | Offline B4 | Command | by last_updated | asset_id(S), mode, completed |
| 9 | p3_d07_correlation_model_states | L215 | Offline | Online B5, Replay | by last_updated | correlation_matrix(JSON) |
| 10 | p3_d08_tsm_state | L229 | Command B4 | Online B4, B8, Replay | by last_updated | account_id(S), user_id(S), current_balance, max_contracts |
| 11 | p3_d09_report_archive | L270 | Command B6 | Command B2 | MONTH | report_id, report_type, content(JSON) |
| 12 | p3_d10_notification_log | L285 | Command B1, B7 | Command B2 | DAY | user_id(S), priority, event_type |
| 13 | p3_d11_pseudotrader_results | L310 | Offline B3 | Command B5 | MONTH | recommendation, sharpe_improvement, pbo, dsr |
| 14 | p3_d12_kelly_parameters | L329 | Offline B8 | Online B1/B4, Replay | by last_updated | asset_id(S), regime, kelly_full, shrinkage_factor |
| 15 | p3_d13_sensitivity_scan_results | L345 | Offline B5 | Command | by scan_date | asset_id(S), robustness_status |
| 16 | p3_d14_api_connection_states | L363 | Command B3 | Command B2 | by last_updated | account_id(S), connection_status, latency_ms |
| 17 | p3_d15_user_session_data | L379 | Command | Command | by last_active | user_id(S), auth_token, role |
| 18 | p3_d16_user_capital_silos | L397 | Command | Online B4, Replay | by last_updated | user_id(S), total_capital, accounts(JSON) |
| 19 | p3_d17_system_monitor_state | L420 | Online/Command | Command B2 | by last_updated | param_key, param_value |
| 20 | p3_d18_version_history | L433 | Offline | -- | MONTH | version_id, component, trigger |
| 21 | p3_offline_job_queue | L449 | Offline orch | Offline | by last_updated | job_id, job_type, asset_id(S), status |
| 22 | p3_d19_reconciliation_log | L470 | Command B8 | -- | MONTH | account_id(S), mismatches, corrected |
| 23 | p3_d21_incident_log | L489 | Command B9 | Command B2 | MONTH | incident_id, severity, status |
| 24 | p3_d22_system_health_diagnostic | L511 | Offline B9 | Command B2 | MONTH | overall_health, action_queue(JSON) |
| 25 | p3_d23_circuit_breaker_intraday | L535 | Online B7B, Command B8 | Online B5C | by last_updated | account_id(S), l_t, n_t |
| 26 | p3_d25_circuit_breaker_params | L550 | Offline B8 | Online B5C, Replay | by last_updated | account_id(S), beta_b, sigma |
| 27 | p3_d26_hmm_opportunity_state | L568 | Offline B1 | Online B5, Replay | by last_updated | hmm_params, opportunity_weights |
| 28 | p3_session_event_log | L588 | Command B1/B5/B7/B8 | -- | DAY | user_id(S), event_type, asset(S) |
| 29 | p3_d27_pseudotrader_forecasts | L605 | Offline B3 | Command | MONTH | forecast_type, account_id(S) |
| 30 | p3_d28_account_lifecycle | L626 | Offline B3, Command B8 | -- | MONTH | account_id(S), event_type, from_stage, to_stage |
| 31 | p3_spread_history | L651 | Online B1 | -- | MONTH | asset_id(S), spread |
| 32 | p3_d29_opening_volumes | L665 | Online | Replay (aim_feature_loader) | MONTH | asset_id(S), volume_first_m_min |
| 33 | p3_d30_daily_ohlcv | L681 | Online | Replay (aim_feature_loader) | YEAR | asset_id(S), trade_date, open/high/low/close |
| 34 | p3_replay_results | L698 | Command B11 | Command B2 | MONTH | replay_id, session_type(S) |
| 35 | p3_replay_presets | L717 | Command B11 | Command B2 | YEAR | preset_id, user_id(S) |
| 36 | p3_d31_implied_vol | L731 | Bootstrap | Online B1, aim_feature_loader | MONTH | asset_id(S), atm_iv_30d, vrp |
| 37 | p3_d32_options_skew | L747 | Bootstrap | Online B1, aim_feature_loader | MONTH | asset_id(S), cboe_skew |
| 38 | p3_d33_opening_volatility | L762 | Online orch | aim_feature_loader | MONTH | asset_id(S), opening_range_pct |

**Total: 38 tables** (init_questdb.py header says "30" -- outdated by 8).

---

### Table 2: Redis Channel Registry

| Channel/Stream | Type | Publisher | Subscriber(s) | Payload Shape | Purpose |
|----------------|------|-----------|---------------|---------------|---------|
| captain:signals:{user_id} | pub/sub | (legacy) | (legacy) | Signal batch | Legacy signals -- replaced by stream:signals |
| captain:trade_outcomes | pub/sub | (legacy) | (legacy) | Trade outcome | Legacy -- replaced by stream:trade_outcomes |
| captain:commands | pub/sub | Command B1, B5 | Command orch, Online orch, Offline orch | {type, ...} | Command broadcast (fire-and-forget) |
| captain:alerts | pub/sub | Online B4/B7/B8, Any | Command orch | {priority, message} | Alert broadcast |
| captain:status | pub/sub | All orchestrators | Command orch | {process, status, ts} | Heartbeat/health |
| stream:signals | stream | Online B6 | Command orch (GROUP_COMMAND_SIGNALS) | Full signal batch | Durable signal delivery |
| stream:trade_outcomes | stream | Online B7 | Offline orch (GROUP_OFFLINE_OUTCOMES) | Trade outcome | Critical feedback loop |
| stream:commands | stream | Command B1 | Online (GROUP_ONLINE_COMMANDS), Offline (GROUP_OFFLINE_COMMANDS) | Command payload | Durable command delivery |
| stream:signal_outcomes | stream | Online B7 shadow | Offline orch (GROUP_OFFLINE_SIGNAL_OUTCOMES) | Theoretical outcome | Category A learning |
| captain:signal_counter:{date} | key | Command orch | Command orch | Integer counter | Parity-based trade splitting |

---

### Table 3: Session/Trigger Registry

| Trigger | Type | Service | Handler | Timing |
|---------|------|---------|---------|--------|
| Session open (NY) | time-based | Online orch | `_is_session_opening()` | 09:30 ET |
| Session open (LONDON) | time-based | Online orch | `_is_session_opening()` | 03:00 ET |
| Session open (APAC) | time-based | Online orch | `_is_session_opening()` | 18:00 ET |
| Session open (NY_PRE) | time-based | Online orch | `_is_session_opening()` | 06:00 ET |
| SOD reset | time-based | Command orch | `_run_scheduler()` | 19:00 ET |
| Reconciliation | time-based | Command orch | `_check_reconciliation_trigger()` | Per scheduler cycle |
| Dashboard refresh | periodic | Command orch | `_run_scheduler()` | Every 1s cycle |
| Heartbeat | periodic | All orchestrators | `_publish_heartbeat()` | ~30s intervals |
| Signal received | event | Command orch | `_signal_stream_reader()` | On stream:signals message |
| Trade outcome | event | Offline orch | `_handle_signal_outcome()` | On stream:trade_outcomes |
| Command received | event | Online/Offline orch | Redis stream reader | On stream:commands |
| Alert received | event | Command orch | `_redis_listener()` | On captain:alerts |
| Daily schedule | time-based | Offline orch | `_run_scheduler()` | After 19:00 ET |
| Weekly schedule | time-based | Offline orch | `_run_scheduler()` | HDWM diversity, diagnostic |
| Monthly schedule | time-based | Offline orch | `_run_scheduler()` | Sensitivity scan, diagnostic |
| Quarterly schedule | time-based | Offline orch | `_run_scheduler()` | CUSUM recalibration |
| Level 3 trigger | event | Offline orch | Decay escalation | On BOCPD changepoint detection |

---

### Table 4: External Integration Registry

| Integration | Service | Auth Method | Endpoints Used | Rate Limiting |
|-------------|---------|-------------|----------------|---------------|
| TopstepX REST API | Online (B1, B7), Command (B3, B2) | API key + JWT token (24h expiry, auto-refresh at 20h) | Auth (login, validate, logout), Orders (place, modify, cancel, search), Positions (search, close), Trades (search), Contracts (search, getById), Bars (historical) | **None implemented** |
| TopstepX MarketStream (SignalR) | Online (B1) | JWT token | Market hub: quotes, trades, depth | N/A (push-based) |
| TopstepX UserStream (SignalR) | Online (B7), Command (B2) | JWT token + account_id | User hub: account, orders, positions, trades | N/A (push-based) |
| Telegram Bot API | Command (B7 notifications, telegram_bot.py) | Bot token (env var) | sendMessage, setWebhook | python-telegram-bot handles internally |
| QuestDB (PG wire) | ALL | admin/quest (env vars) | SQL queries via psycopg2 | **None** |
| Redis | ALL | No auth | pub/sub, streams, keys | **None** |
| VIX/VXV CSV files | Online (B1 features, B5C) | N/A (local filesystem) | File read | N/A |

---

### Table 5: Cross-Service Consistency Check

#### CRITICAL: Table Name Mismatches

| Location | Uses | Correct Name | Severity |
|----------|------|--------------|----------|
| telegram_bot.py L102 | `p3_d00_asset_registry` | `p3_d00_asset_universe` | **CRITICAL** -- query will fail, /status command broken |
| telegram_bot.py L112, L162 | `p3_d03_trade_outcomes` | `p3_d03_trade_outcome_log` | **CRITICAL** -- queries will fail, trade summary broken |
| replay_engine.py L289 | `p3_d25_circuit_breaker` | `p3_d25_circuit_breaker_params` | **HIGH** -- CB modifiers missing in replay |

#### Session Name Inconsistency

| Source | NY | London | Pre-market | Asia-Pacific |
|--------|-----|--------|------------|--------------|
| constants.py SESSION_IDS | NY (id=1) | LON (id=2) | -- | APAC (id=3) |
| session_registry.json | NY | LONDON | NY_PRE | APAC |
| D05/D12 schema (session column) | INT (1/2/3) | INT | INT | INT |

**Impact:** Code using SESSION_IDS keys ("LON") won't match session_registry.json keys ("LONDON"). NY_PRE session (for ZN, ZB, MCL) has no ID in SESSION_IDS.

#### Table Count Drift

| Source | Claims | Actual |
|--------|--------|--------|
| init_questdb.py header | "30 tables" | 38 CREATE TABLE statements |
| init_questdb.py __main__ | "30 tables" | 38 |
| CLAUDE.md | "29 tables" | 38 |

#### Schema Consistency: Code vs init_questdb.py

All code-referenced table names match init_questdb.py definitions **except** the three mismatches listed above.

The `p3_d12_kelly_parameters` name is consistent everywhere (init_questdb.py, Online B1, Offline B8, replay_engine). CLAUDE.md refers to it as "D12 (kelly_params)" informally but code uses the full name.

---

## Part 4: Final Summary

### Files Audited Across All Sessions

| Session | Focus | Files |
|---------|-------|-------|
| EXEC-01 | Online B1-B3 (Data to AIM) | 5 |
| EXEC-02 | Online B3-B5 (AIM to Sizing) | 4 |
| EXEC-03 | Online B4-B8 (Kelly to Signal) | 9 |
| EXEC-04a | Offline B1-B2 (AIM lifecycle, Decay) | 12 |
| EXEC-04b | Offline B3-B9 (Pseudotrader to Health) | 8 |
| EXEC-05a | Command B1-B5 (Routing to Injection) | 7 |
| EXEC-05b | Command B6-B11 (Reports to Replay) | 8 |
| EXEC-06 | Shared, Config, Build, Aggregation | 28 |
| **TOTAL** | | **81 files** |

### Stubs/TODOs Found

| Service | Count | Notes |
|---------|-------|-------|
| Online | 11 | Per EXEC-03 passover |
| Offline | 0 | Per EXEC-04b passover |
| Command | 0 | No TODO/FIXME/STUB found in any command block |
| Shared | 0 | No TODO/FIXME/STUB found in any shared file |
| **TOTAL** | **11** | All in Online service |

### Top 10 Findings Ranked by Severity

| # | ID | Severity | Location | Description |
|---|-----|----------|----------|-------------|
| 1 | CRITICAL | **P1** | telegram_bot.py L102 | Wrong table name `p3_d00_asset_registry` (should be `p3_d00_asset_universe`). Telegram /status command will crash. |
| 2 | CRITICAL | **P1** | telegram_bot.py L112, L162 | Wrong table name `p3_d03_trade_outcomes` (should be `p3_d03_trade_outcome_log`). Telegram /status and /trades commands will crash. |
| 3 | HIGH | **P2** | replay_engine.py L289 | Wrong table name `p3_d25_circuit_breaker` (should be `p3_d25_circuit_breaker_params`). Circuit breaker data missing from all replay runs. |
| 4 | HIGH | **P2** | constants.py / session_registry.json | Session name mismatch: LON vs LONDON, NY_PRE missing from SESSION_IDS. Assets mapped to NY_PRE (ZN, ZB, MCL, MGC) may not trigger correctly. |
| 5 | HIGH | **P2** | topstep_client.py | No rate limiting or request timeout on REST API calls. A slow/hung API will block the calling thread indefinitely. |
| 6 | MEDIUM | **P3** | All Dockerfiles | All containers run as root. No USER directive for privilege dropping. |
| 7 | MEDIUM | **P3** | All requirements.txt | Unpinned dependency versions (except xgboost). Builds are not reproducible. |
| 8 | MEDIUM | **P3** | questdb_client.py | No connection pooling. Each query opens a new TCP connection. Performance risk under load. |
| 9 | MEDIUM | **P3** | vix_provider.py | Static CSV data requires manual updates. No automated daily VIX fetch. |
| 10 | LOW | **P4** | init_questdb.py header | Table count claims "30" but actual count is 38. Documentation drift. |

### Recommended Priority Fixes (Ordered)

1. **FIX telegram_bot.py table names** (5 minutes). Change `p3_d00_asset_registry` to `p3_d00_asset_universe` and `p3_d03_trade_outcomes` to `p3_d03_trade_outcome_log`. These are runtime SQL errors that will crash Telegram commands.

2. **FIX replay_engine.py L289 table name** (2 minutes). Change `p3_d25_circuit_breaker` to `p3_d25_circuit_breaker_params`. Circuit breaker modifiers are silently missing from all replay analysis.

3. **Resolve session name inconsistency** (30 minutes). Either update constants.py SESSION_IDS to include "LONDON" and "NY_PRE" mappings, or update session_registry.json to use "LON". Audit all code that matches session names to determine which convention wins.

4. **Add request timeouts to topstep_client.py** (15 minutes). Add `timeout=30` to all requests.post() calls. Add retry-with-backoff for 429/5xx.

5. **Pin dependency versions** (20 minutes). Run `pip freeze` inside each container and create pinned requirements.txt files for reproducible builds.

6. **Add QuestDB connection pooling** (1 hour). Replace per-query connections with psycopg2.pool.ThreadedConnectionPool in questdb_client.py.

7. **Add non-root USER to Dockerfiles** (10 minutes per Dockerfile). Add `RUN useradd -r captain && USER captain` before CMD.

8. **Update init_questdb.py table count** (2 minutes). Change "30 tables" to "38 tables" in header and __main__ block.

9. **Automate VIX data updates** (2-4 hours). Add a daily fetch mechanism for VIX/VXV closes, or pull from QuestDB seed data.

10. **Remove unused scikit-learn from Online requirements.txt** (2 minutes). Unless a specific block imports it (none found in audit).
