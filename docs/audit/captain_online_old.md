# Captain Online Audit

## Part 1: Core & Ingestion

**Audit date:** 2026-04-08
**Files audited:** 5 (main.py, orchestrator.py, or_tracker.py, b1_data_ingestion.py, b1_features.py)
**Total lines:** ~3,500

---

### File 1: `captain-online/captain_online/main.py` (137 lines)

**Purpose:** Process entry point — verifies infrastructure, starts MarketStream, launches orchestrator.

**Key functions/classes:**
| Function | Line | Role |
|----------|------|------|
| `or_tracker` (module-level) | 33 | ORTracker shared between MarketStream writer and orchestrator reader |
| `_start_market_streams()` | 42 | Authenticates TopstepX, starts multi-contract MarketStream |
| `main()` | 80 | Entry point: infra check -> streams -> orchestrator |
| `shutdown_handler()` | 120 | SIGTERM/SIGINT handler |

**Session/schedule references:** None direct — delegates to orchestrator.

**QuestDB interactions:**
| Table | Op | Line | Purpose |
|-------|----|------|---------|
| _(none)_ | `get_connection()` | 85 | Health check only |

**Redis interactions:**
| Channel/Stream | Pub/Sub | Line | Purpose |
|----------------|---------|------|---------|
| `STREAM_COMMANDS` | consumer group setup | 101 | `ensure_consumer_group(STREAM_COMMANDS, GROUP_ONLINE_COMMANDS)` |

**Async patterns:**
- Synchronous main flow. MarketStream.start() runs in its own thread internally.
- `orchestrator.start()` at line 132 **blocks** — runs the 24/7 session loop.

**Startup/shutdown:**
- **Startup order:** QuestDB ping -> Redis ping -> consumer group -> journal checkpoint -> MarketStream -> orchestrator
- **Shutdown:** SIGTERM/SIGINT (lines 128-129) calls `orchestrator.stop()`, `market_stream.stop()`, writes checkpoint, `sys.exit(0)`

**Stubs/TODOs:** None.

**Notable findings:**

| # | Severity | Line | Finding |
|---|----------|------|---------|
| F01 | HIGH | 120-129 | **No graceful position drain on shutdown.** `shutdown_handler` stops orchestrator and market stream but does not wait for open positions to resolve or publish outcomes. TSM state in QuestDB may become stale. |
| F02 | LOW | 3-5 | **QuantConnect compatibility shim** (`from AlgorithmImports import *` wrapped in try/except). Dead code in Docker deployment, harmless but present in all 5 files. |
| F03 | LOW | 88-98 | **`sys.exit(1)` on infra failure without alert.** No journal entry or Redis alert published before exit. Docker will restart the container, but no telemetry is captured for the failure. |

---

### File 2: `captain-online/captain_online/blocks/orchestrator.py` (776 lines)

**Purpose:** 24/7 session loop — evaluates at session opens (NY/LON/APAC), manages Phase A/B OR breakout pipeline, monitors positions.

**Key functions/classes:**
| Function/Class | Line | Role |
|----------------|------|------|
| `OnlineOrchestrator.__init__()` | 60 | Initializes state: positions, pending sessions, session tracker |
| `start()` | 71 | Writes checkpoint, starts command listener thread, enters session loop |
| `stop()` | 86 | Sets `self.running = False` |
| `_session_loop()` | 102 | Main loop: session check -> OR breakouts -> B7 monitor -> sleep(1) |
| `_is_session_opening()` | 135 | +/- 2 min window detection for session open |
| `_run_session()` | 145 | Full pipeline: CB -> B1 -> B2 -> B3 -> user loop (B4-B5C) -> OR defer |
| `_check_or_breakouts()` | 277 | Polls OR state, runs Phase B (B6) for resolved assets |
| `_recompute_aim15_volume()` | 371 | AIM-15 Phase B: recompute volume ratio with actual first-m-min data |
| `_process_user_sizing()` | 431 | Phase A per user: B4 -> B5 -> B5B -> B5C |
| `_run_b6_for_user()` | 524 | Phase B per user: B6 signal output |
| `_process_user()` | 582 | Legacy path: full B4-B6 (no OR tracker) |
| `_run_position_monitor()` | 590 | B7 position monitoring |
| `_run_shadow_monitor()` | 602 | B7 shadow (theoretical) outcome tracking |
| `_circuit_breaker_check()` | 612 | DATA_HOLD >= 3, VIX > 50, manual halt |
| `_is_manual_halt()` | 633 | Reads `manual_halt_all` from P3-D17 |
| `_get_active_users()` | 647 | Loads users from P3-D15 |
| `_load_user_silo()` | 666 | Loads capital silo from P3-D16 |
| `_command_listener()` | 695 | Background thread: Redis stream consumer with exponential backoff |
| `_handle_command()` | 722 | Command dispatch (MANUAL_HALT, TAKEN_SKIPPED) |
| `_handle_taken_skipped()` | 733 | Creates open position (TAKEN) or logs skip |

**Session/schedule references:**
- `SESSION_OPEN_TIMES` (line 47): `{1: (9,30), 2: (3,0), 3: (20,0)}` — all in ET
- `SESSION_WINDOW_MINUTES = 2` (line 54)
- `_session_evaluated_today` dict prevents double evaluation per day

**QuestDB interactions:**
| Table | Op | Line | Purpose |
|-------|----|------|---------|
| `p3_d00_asset_universe` | SELECT | 170-176 | Early OR registration (active assets) |
| `p3_d17_system_monitor_state` | SELECT | 637-643 | Manual halt check |
| `p3_d15_user_session_data` | SELECT | 651-654 | Active users |
| `p3_d16_user_capital_silos` | SELECT | 670-679 | User capital silo |

**Redis interactions:**
| Channel/Stream | Pub/Sub | Line | Payload |
|----------------|---------|------|---------|
| `CH_STATUS` | PUB | 92-98 | `{role, type:"pipeline_stage", stage, timestamp}` |
| `STREAM_COMMANDS` / `GROUP_ONLINE_COMMANDS` | SUB (stream) | 708-713 | Commands: MANUAL_HALT, TAKEN_SKIPPED |

**Async patterns:**
- `threading.Thread(target=_command_listener, daemon=True)` (line 79)
- `time.sleep(1)` main loop cadence (line 133)
- `self.open_positions` and `self.shadow_positions` are plain lists shared between threads

**Startup/shutdown:**
- `start()`: checkpoint -> publish WAITING -> start command listener -> `_session_loop()` (blocking)
- `stop()`: `self.running = False` (loop exits on next iteration, ~1s)

**Stubs/TODOs:** None.

**Notable findings:**

| # | Severity | Line | Finding |
|---|----------|------|---------|
| F04 | **CRITICAL** | 119, 762 | **Thread-unsafe `self.open_positions`.** Main thread reads/removes in `_run_position_monitor()` (line 595-600), command listener thread appends in `_handle_taken_skipped()` (line 762). Python GIL protects simple appends but `list.remove()` during concurrent append is unsafe. Needs a `threading.Lock`. |
| F05 | HIGH | 769-771 | **TOCTOU on `self.shadow_positions`.** List comprehension replacement in `_handle_taken_skipped` (command thread) while `_run_shadow_monitor` (main thread) may be iterating the old reference. Creates new list object (safer than mutation) but there's a window where the main thread iterates a stale copy. |
| F06 | MEDIUM | 143 | **Midnight wraparound bug in session detection.** `abs(current_minute - target_minute)` doesn't handle day boundary. APAC at 23:59 vs 00:01 = 1438, not 2. Currently safe (APAC=20:00) but fragile for future schedule changes. |
| F07 | MEDIUM | 622 | **Hardcoded VIX threshold** `vix > 50.0`. Should reference a config parameter or P3-D17 value. |
| F08 | MEDIUM | 86-87 | **`stop()` doesn't drain open positions.** No outcome published for positions open at shutdown. Offline learning receives no feedback for these trades. |
| F09 | LOW | 664 | **Hardcoded fallback user.** `_get_active_users()` returns `[{"user_id": "primary_user", "role": "ADMIN"}]` when QuestDB returns no rows. Intentional bootstrap behavior but could mask DB failures. |

---

### File 3: `captain-online/captain_online/blocks/or_tracker.py` (395 lines)

**Purpose:** Thread-safe OR state machine — tracks OR high/low from live quotes, detects breakouts, provides direction/range to B6.

**Key functions/classes:**
| Function/Class | Line | Role |
|----------------|------|------|
| `ORState` (enum) | 39 | WAITING -> FORMING -> COMPLETE -> BREAKOUT_LONG/SHORT or EXPIRED |
| `AssetORSession` | 49 | State for one (asset, date) pair; `__slots__` for memory efficiency |
| `ORTracker` | 205 | Thread-safe tracker with `threading.Lock` |
| `ORTracker.register_asset()` | 223 | Start tracking for an asset |
| `ORTracker.on_quote()` | 255 | MarketStream callback — resolves contract -> updates state |
| `ORTracker.check_expirations()` | 289 | Expire stale COMPLETE/FORMING sessions |
| `ORTracker._update_state()` | 325 | State machine transitions (caller holds lock) |
| `ORTracker._check_breakout()` | 360 | Breakout detection logic |
| `_load_session_registry()` | 119 | Loads session_registry.json (cached) |
| `get_asset_session_type()` | 146 | Asset -> session type mapping |
| `get_or_times()` | 152 | Session type -> (or_start, or_end) |
| `_load_contract_to_asset()` | 170 | Reverse map: contract_id -> asset_id |

**Session/schedule references:**
- `session_registry.json` (line 125-128) defines OR start/end per session type
- Default fallback: NY OR = 09:30-09:35 (5 min)
- `DEFAULT_BREAKOUT_CUTOFF_MINUTES = 30` (line 37)

**QuestDB interactions:** None. Purely in-memory state.

**Redis interactions:** None.

**Async patterns:**
- `threading.Lock()` (line 220) guards all `_sessions` mutations
- `on_quote()` called from MarketStream thread (WebSocket callback thread)
- `check_expirations()` called from orchestrator main thread

**Startup/shutdown:**
- `clear()` method (line 318) exists but **never called** from orchestrator

**Stubs/TODOs:** None.

**Notable findings:**

| # | Severity | Line | Finding |
|---|----------|------|---------|
| F10 | **CRITICAL** | 246-248 | **`get_state()` returns live mutable object, not a snapshot.** Docstring says "snapshot" but returns `self._sessions.get(asset_id)` — the actual object. Callers read `.is_resolved`, `.state`, `.entry_price` without holding the lock while `on_quote()` may be mutating the same object from the MarketStream thread. Race condition on state transitions. |
| F11 | MEDIUM | 30 | **pytz vs zoneinfo inconsistency.** or_tracker uses `from pytz import timezone`, orchestrator uses `from zoneinfo import ZoneInfo`. Both produce correct ET results but mixing libraries is a maintenance hazard (pytz requires `.localize()` while ZoneInfo works with `datetime` natively). |
| F12 | LOW | 116 | **Module-level cache not thread-safe on first load.** `_registry_cache` could race if two threads call `_load_session_registry()` simultaneously during startup. In practice safe because first call happens under ORTracker lock, but the function itself doesn't enforce this. |
| F13 | LOW | 318 | **`clear()` never called.** Stale OR sessions from prior days persist in memory. Harmless because `register_asset()` overwrites per asset_id, but wastes memory. |

---

### File 4: `captain-online/captain_online/blocks/b1_data_ingestion.py` (771 lines)

**Purpose:** Pre-session data ingestion (B1) — loads QuestDB state, runs data quality checks, returns data bundle for B2-B6.

**Key functions/classes:**
| Function | Line | Role |
|----------|------|------|
| `run_data_ingestion(session_id)` | 695 | Main entry: load assets -> data moderator -> roll check -> load offline outputs -> compute features |
| `_load_active_assets()` | 46 | P3-D00 SELECT + session filter + dedup |
| `_load_aim_states()` | 97 | P3-D01 SELECT + dedup |
| `_load_aim_weights()` | 134 | P3-D02 SELECT + dedup |
| `_load_ewma_states()` | 162 | P3-D05 SELECT + dedup |
| `_load_kelly_params()` | 191 | P3-D12 SELECT + dedup + sizing overrides |
| `_load_tsm_configs()` | 224 | P3-D08 SELECT + dedup |
| `_load_locked_strategies()` | 282 | P3-D00.locked_strategy SELECT + dedup |
| `_load_regime_models()` | 308 | Derived from locked strategies |
| `_run_data_moderator()` | 352 | Price bounds, volume, data source, timestamp validation |
| `_check_roll_calendar()` | 431 | Contract roll date check + CRITICAL alert |
| `_get_latest_price()` | 485 | Stream cache -> REST fallback |
| `_get_prior_close()` | 511 | TopstepX REST daily bars |
| `_get_avg_session_volume_20d()` | 542 | TopstepX REST daily bars |
| `_create_incident()` | 599 | INSERT into P3-D21 incident log |
| `_publish_alert()` | 630 | Redis CH_ALERTS publish |
| `session_match()` | 668 | Asset-session eligibility check |

**Session/schedule references:**
- `session_match()` (line 668) checks `session_hours` config from P3-D00
- Uses `SESSION_IDS` from `shared.constants`

**QuestDB interactions:**
| Table | Op | Line | Key Fields |
|-------|----|------|------------|
| `p3_d00_asset_universe` | SELECT | 49-57 | 13 columns, ORDER BY last_updated DESC |
| `p3_d01_aim_model_states` | SELECT | 100-106 | aim_id, asset_id, status, model_object, etc. |
| `p3_d02_aim_meta_weights` | SELECT | 137-142 | aim_id, asset_id, inclusion_probability |
| `p3_d05_ewma_states` | SELECT | 165-170 | asset_id, regime, session, win_rate, etc. |
| `p3_d12_kelly_parameters` | SELECT | 194-199 | asset_id, regime, session, kelly_full, shrinkage |
| `p3_d08_tsm_state` | SELECT | 227-241 | 27 columns (full TSM config) |
| `p3_d00_asset_universe` | SELECT | 288-293 | asset_id, locked_strategy (2nd query to same table) |
| `p3_d17_system_monitor_state` | SELECT | 333-339 | param_key, param_value |
| `p3_d21_incident_log` | INSERT | 603-608 | incident_id, type, severity, details |
| `p3_d17_system_monitor_state` | INSERT | 622-627 | data_quality_log_{session_id} |

**Redis interactions:**
| Channel | Pub/Sub | Line | Payload |
|---------|---------|------|---------|
| `CH_ALERTS` | PUB | 636-643 | `{priority, message, action_required, source, timestamp}` |

**Async patterns:** None. Synchronous function calls.

**Stubs/TODOs:**
| Line | Function | Status |
|------|----------|--------|
| 574-575 | `_check_data_source_for_feature()` | Always returns `True` — "Stub for V1" |
| 578-580 | `_has_valid_timestamp()` | Always returns `True` — "Stub for V1" |

**Notable findings:**

| # | Severity | Line | Finding |
|---|----------|------|---------|
| F14 | MEDIUM | 437 | **Naive `datetime.now().date()` in roll calendar check.** Should be `datetime.now(_ET).date()`. Around midnight UTC (7-8 PM ET), this could evaluate the wrong day. |
| F15 | MEDIUM | 640 | **Naive `datetime.now().isoformat()` in `_publish_alert`.** Alert timestamps lack timezone info. Downstream consumers may misinterpret. |
| F16 | MEDIUM | 282-327 | **Triple query to `p3_d00_asset_universe`.** `_load_active_assets()` (line 49), `_load_locked_strategies()` (line 288), and `_load_regime_models()` -> `_load_locked_strategies()` each query D00 independently. Could be consolidated into a single load. |
| F17 | LOW | 574-580 | **Data moderator stubs.** Timestamp validation and data source checks always pass. Price/volume checks are functional but these two gaps weaken pre-trade data quality assurance. |

---

### File 5: `captain-online/captain_online/blocks/b1_features.py` (1,368 lines)

**Purpose:** Feature computation for 17 AIMs (Appendix A) + 11 data access utilities (Appendix B). Pure math + data adapters.

**Key functions/classes:**
| Function | Line | AIM | Role |
|----------|------|-----|------|
| `compute_all_features()` | 537 | ALL | Master entry: iterates assets, computes active AIM features |
| `compute_vrp()` | 46 | AIM-01 | VRP = realised vol - implied vol |
| `compute_overnight_vrp()` | 61 | AIM-01 | Overnight VRP |
| `compute_put_call_ratio()` | 76 | AIM-02 | PCR from options volume |
| `compute_dotm_otm_put_spread()` | 87 | AIM-02 | DOTM-OTM put IV spread |
| `compute_dealer_net_gamma()` | 105 | AIM-03 | Dealer GEX from option chain |
| `check_economic_calendar()` | 138 | AIM-06 | Events for date + asset |
| `min_distance_to_event()` | 158 | AIM-06 | Minutes to nearest event |
| `latest_smi_polarity()` | 190 | AIM-07 | Smart Money Index from COT |
| `speculator_z_score()` | 212 | AIM-07 | Large speculator z-score |
| `rolling_20d_correlation()` | 233 | AIM-08 | 20-day Pearson correlation |
| `compute_cross_asset_momentum()` | 248 | AIM-09 | Aggregate MACD momentum |
| `is_within_opex_window()` | 279 | AIM-10 | OPEX +/- 2 trading days |
| `get_live_spread()` | 322 | AIM-12 | Current bid-ask spread |
| `volume_first_N_min()` | 337 | AIM-15 | First N-min volume |
| `store_opening_volume()` | 1146 | AIM-15 | Persist to P3-D29 |
| `store_opening_volatility()` | 1170 | AIM-12 | Persist to P3-D33 |
| `store_daily_ohlcv()` | 1196 | Common | Persist to P3-D30 |
| `z_score()` | 357 | Util | Standard z-score |
| `ema()` | 372 | Util | Exponential moving average |
| `get_return_bounds()` | 450 | Kelly | Distributional robust Kelly bounds |
| `compute_robust_kelly()` | 467 | Kelly | Min-max robust Kelly fraction |
| `get_or_window_minutes()` | 483 | OR | OR window from locked_strategy |

**Session/schedule references:**
- `_get_session_open_time()` (line 1073): **Hardcoded 9:30 ET for ALL assets** regardless of session type
- `_get_recent_5min_vol()` (line 1297-1298): **Hardcoded 9:30 open** for vol computation

**QuestDB interactions:**
| Table | Op | Line | Purpose |
|-------|----|------|---------|
| `p3_d17_system_monitor_state` | SELECT | 425-430 | Last known feature fallback |
| `p3_spread_history` | INSERT | 700-705 | Persist current spread |
| `p3_d31_implied_vol` | SELECT | 826-837 | ATM IV 30d |
| `p3_d31_implied_vol` | SELECT | 844-856 | Realised vol 20d |
| `p3_d31_implied_vol` | SELECT | 869-886 | Trailing VRP (60d) |
| `p3_d30_daily_ohlcv` | SELECT | 895-917 | Trailing overnight returns (60d) |
| `p3_d32_options_skew` | SELECT | 930-944 | Trailing skew (60d) |
| `p3_d30_daily_ohlcv` | SELECT | 1048-1061 | Daily closes (up to 280d) |
| `p3_d00_asset_universe` | SELECT | 1067-1071 | All universe assets (DISTINCT) |
| `p3_d29_opening_volumes` | SELECT | 1132-1143 | Historical opening volumes |
| `p3_d29_opening_volumes` | INSERT | 1157-1168 | Store today's opening volume |
| `p3_d33_opening_volatility` | INSERT | 1185-1193 | Store today's opening vol |
| `p3_d30_daily_ohlcv` | INSERT | 1220-1228 | Store today's daily OHLCV |
| `p3_spread_history` | SELECT | 1270-1281 | Trailing spreads (60d) |
| `p3_d33_opening_volatility` | SELECT | 1327-1338 | Trailing opening vol (60d) |

**Redis interactions:** None.

**Async patterns:** None. Synchronous.

**Stubs (12 functions returning None):**
| Line | Function | AIM Affected | Impact |
|------|----------|-------------|--------|
| 858-859 | `_get_overnight_range()` | AIM-01 | Overnight VRP always None |
| 919-921 | `_get_trailing_pcr()` | AIM-02 | PCR z-score always None |
| 946-947 | `_get_options_volume()` | AIM-02 | PCR always None |
| 949-950 | `_get_put_iv()` | AIM-02 | Put skew always None |
| 952-953 | `_get_option_chain()` | AIM-03 | GEX always None |
| 955-956 | `_get_contract_multiplier()` | AIM-03 | Hardcoded 50.0 (ES only) |
| 957-958 | `_get_risk_free_rate()` | AIM-03 | Hardcoded 0.05 |
| 1008-1009 | `_load_latest_cot()` | AIM-07 | SMI always None |
| 1011-1012 | `_load_cot_history()` | AIM-07 | Speculator z always None |
| 1259-1260 | `_get_cl_spot()` | AIM-11 | CL basis always None |
| 1261-1262 | `_get_cl_front_futures()` | AIM-11 | CL basis always None |

**Notable findings:**

| # | Severity | Line | Finding |
|---|----------|------|---------|
| F18 | HIGH | all stubs | **12 stub data adapters.** AIM-02 (Options Skew), AIM-03 (GEX), AIM-07 (COT), AIM-11 CL-specific, and AIM-01 overnight range are fully stubbed. These AIMs will always produce neutral/missing modifiers. ~5 of 15 live AIMs are non-functional. |
| F19 | HIGH | 546 | **Naive `datetime.now()` in master feature computation.** Used for `overnight_return`, `day_of_week`, AIM conditionals. Near midnight UTC (~7-8 PM ET), `day_of_week` evaluates the wrong day. Must be `datetime.now(ET)`. |
| F20 | HIGH | 1073-1082 | **`_get_session_open_time()` hardcodes 9:30 ET.** APAC and LON assets get wrong session open time. Affects AIM-06 `event_proximity` and AIM-12 `_get_recent_5min_vol()` (line 1298). |
| F21 | MEDIUM | 479 | **Possible math error in `compute_robust_kelly()`.** `robust_f = lower / (upper * lower)` simplifies to `1/upper` when `lower != 0`. Paper 218 min-max robust Kelly is typically `(p*b - q) / b` or similar. This may produce incorrect fractions. |
| F22 | MEDIUM | 735 | **Duplicate `_get_latest_price()`.** Nearly identical implementations in both b1_data_ingestion.py (line 485) and b1_features.py (line 735). Should reference a shared utility. |
| F23 | LOW | 956 | **Hardcoded contract multiplier 50.0.** Only correct for ES/MES. Other assets (NQ=20, ZB=1000, MGC=10, etc.) would get wrong GEX if AIM-03 were ever wired up. |

---

## Findings Summary

### By Severity

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 2 | F04, F10 |
| HIGH | 5 | F01, F05, F18, F19, F20 |
| MEDIUM | 7 | F06, F07, F08, F11, F14-F16, F21-F22 |
| LOW | 6 | F02, F03, F09, F12, F13, F17, F23 |
| **Total** | **23** | |

### Critical Findings Detail

**F04 — Thread-unsafe `self.open_positions` (orchestrator.py:119,762)**
The main thread calls `_run_position_monitor()` which does `self.open_positions.remove(pos)`, while the command listener thread appends to `self.open_positions` in `_handle_taken_skipped()`. Python's GIL prevents data corruption but not logical races. A position could be appended between the monitor iterating the list and removing from it, causing missed monitoring cycles or ValueError exceptions. **Fix:** Add a `threading.Lock` around all open_positions access.

**F10 — `get_state()` returns live mutable object (or_tracker.py:246-248)**
The docstring claims "snapshot" but the actual `AssetORSession` object is returned. Callers (orchestrator) read `.is_resolved`, `.direction`, `.entry_price` without holding the lock, while `on_quote()` from the MarketStream thread mutates the same object. A state could transition from FORMING to BREAKOUT between the orchestrator checking `is_resolved` and reading `direction`. **Fix:** Return a copy or a frozen dataclass snapshot.

### Stub Count: 14 total
- b1_data_ingestion.py: 2 stubs (data source check, timestamp validation)
- b1_features.py: 12 stubs (options, COT, CL data, contract multiplier, risk-free rate)

---

## Cross-Service Dependencies

### Redis Channels Used
| Channel/Stream | Direction | File | Purpose |
|----------------|-----------|------|---------|
| `CH_STATUS` | PUB | orchestrator.py | Pipeline stage transitions |
| `STREAM_COMMANDS` / `GROUP_ONLINE_COMMANDS` | SUB | orchestrator.py, main.py | Commands (TAKEN/SKIPPED, MANUAL_HALT) |
| `CH_ALERTS` | PUB | b1_data_ingestion.py | Contract roll alerts, data quality alerts |

### QuestDB Tables Accessed
| Table | Read | Write | Files |
|-------|------|-------|-------|
| `p3_d00_asset_universe` | x | x (status/flag) | b1_data_ingestion, orchestrator, b1_features |
| `p3_d01_aim_model_states` | x | | b1_data_ingestion |
| `p3_d02_aim_meta_weights` | x | | b1_data_ingestion |
| `p3_d05_ewma_states` | x | | b1_data_ingestion |
| `p3_d08_tsm_state` | x | | b1_data_ingestion |
| `p3_d12_kelly_parameters` | x | | b1_data_ingestion |
| `p3_d15_user_session_data` | x | | orchestrator |
| `p3_d16_user_capital_silos` | x | | orchestrator |
| `p3_d17_system_monitor_state` | x | x | b1_data_ingestion, orchestrator, b1_features |
| `p3_d21_incident_log` | | x | b1_data_ingestion |
| `p3_d29_opening_volumes` | x | x | b1_features |
| `p3_d30_daily_ohlcv` | x | x | b1_features |
| `p3_d31_implied_vol` | x | | b1_features |
| `p3_d32_options_skew` | x | | b1_features |
| `p3_d33_opening_volatility` | x | x | b1_features |
| `p3_spread_history` | x | x | b1_features |

### Shared Modules Used
| Module | Used By | Purpose |
|--------|---------|---------|
| `shared.questdb_client` | All files | DB connection + cursor |
| `shared.redis_client` | main.py, orchestrator.py, b1_data_ingestion.py | Redis client + pub/sub + streams |
| `shared.contract_resolver` | main.py, b1_data_ingestion.py, b1_features.py, or_tracker.py | Asset -> contract_id mapping |
| `shared.topstep_client` | main.py, b1_data_ingestion.py, b1_features.py | REST API client |
| `shared.topstep_stream` | b1_data_ingestion.py, b1_features.py | `quote_cache` (shared mutable dict) |
| `shared.journal` | main.py, orchestrator.py | SQLite WAL checkpoints |
| `shared.constants` | orchestrator.py, b1_data_ingestion.py | SESSION_IDS, SYSTEM_TIMEZONE |
| `shared.vix_provider` | b1_features.py | VIX/VXV daily data |
| `shared.aim_compute` | orchestrator.py | AIM-15 modifier computation |

---

## Passover Summary for Session 2

**Files audited:** 5
**Key findings:** 23 (2 CRITICAL, 5 HIGH, 7 MEDIUM, 9 LOW)
**Stub count:** 14

**Cross-service dependencies discovered:**
- 3 Redis channels (CH_STATUS pub, STREAM_COMMANDS sub, CH_ALERTS pub)
- 16 QuestDB tables (12 read, 6 write)
- 9 shared modules

**Open questions for Session 2 (AIMs & Regime):**
1. How does B2 (regime probability) handle the case where `regime_models` all return `REGIME_NEUTRAL`? Is the classifier truly locked or does it evaluate features?
2. B3 (AIM aggregation) depends on `aim_states` and `aim_weights` — how does it handle 5 of 15 AIMs being stubbed (always None modifiers)?
3. The `shared.aim_compute` module (used by orchestrator for AIM-15) — what's the full interface? Is `_aim15_volume` the only external caller?
4. Does B5 (trade selection) account for the fact that most AIM features are currently None?
5. B6 (signal output) — what's the full Redis publish payload shape? Need to trace the signal -> Command -> GUI -> TAKEN flow.
6. `shared.topstep_stream.quote_cache` — is this a plain dict or thread-safe? Multiple readers (B1, B1-features, OR tracker, B7) access it.
