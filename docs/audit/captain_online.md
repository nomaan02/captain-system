# Captain Online Audit

## Part 1: Core & Ingestion

**Auditor:** Claude Opus 4.6
**Date:** 2026-04-08
**Skills applied:** ln-629 Lifecycle Auditor, ln-628 Concurrency Auditor
**Scope:** Startup, session management, data ingestion, bar aggregation, WebSocket handling, Opening Range tracking.

---

## File Inventory

### File: captain-online/captain_online/main.py

- **Purpose:** Process entry point — infrastructure verification, stream startup, orchestrator launch.
- **Key functions/classes:**
  - `_start_market_streams()` — l42: TopstepX auth + multi-contract MarketStream start
  - `main()` — l80: full startup sequence
  - `shutdown_handler()` — l120: SIGTERM/SIGINT handler (inline closure)
- **Session/schedule refs:** None directly; delegates to `OnlineOrchestrator`.
- **QuestDB:** Via `get_connection()` (l85) — ping-only health check at startup.
- **Redis:** Via `get_redis_client()` (l93) — ping-only health check; `ensure_consumer_group(STREAM_COMMANDS, GROUP_ONLINE_COMMANDS)` (l101).
- **Stubs/TODOs:** None.
- **Notable:**
  - Module-level `or_tracker = ORTracker()` (l33) is created before `main()` runs — before QuestDB/Redis health checks. Safe only because ORTracker has no DB/Redis deps at init time.
  - `shutdown_handler` calls `sys.exit(0)` from inside a signal handler (l126). Technically unsafe in CPython if the signal is delivered mid-QuestDB query (though rare in practice).
  - No readiness/liveness HTTP endpoint despite being Docker-deployed.

---

### File: captain-online/captain_online/blocks/orchestrator.py

- **Purpose:** 24/7 session loop — evaluates NY/LON/APAC opens, orchestrates Phase A (B1–B5C) and Phase B (B6 after OR breakout), monitors positions.
- **Key functions/classes:**
  - `OnlineOrchestrator` — l57: main class
  - `start()` — l71: spawns command listener thread, calls `_session_loop()`
  - `_session_loop()` — l102: main while loop (1-second tick), calls session/OR/position checks
  - `_run_session()` — l145: full pipeline execution per session
  - `_check_or_breakouts()` — l277: Phase B dispatch on OR resolution
  - `_handle_taken_skipped()` — l733: mutates `open_positions` and `shadow_positions` from command thread
  - `_command_listener()` — l695: background thread, exponential backoff reconnect
- **Session/schedule refs:**
  - `SESSION_OPEN_TIMES` (l47): `{1: (9,30), 2: (3,0), 3: (20,0)}` — NY/LON/APAC in ET.
  - `SESSION_WINDOW_MINUTES = 2` (l54): ±2 min tolerance window.
  - `_session_evaluated_today` (l64): prevents double-eval per calendar date.
- **QuestDB:**
  - `p3_d00_asset_universe` — SELECT ACTIVE assets for OR registration (l170)
  - `p3_d15_user_session_data` — SELECT active users (l651)
  - `p3_d16_user_capital_silos` — SELECT user silo (l670)
  - `p3_d17_system_monitor_state` — SELECT manual_halt_all (l637)
- **Redis:**
  - `CH_STATUS` — publish pipeline stage (l93): `{role, type, stage, timestamp}`
  - `STREAM_COMMANDS` / `GROUP_ONLINE_COMMANDS` — read via `read_stream()` (l708), ack via `ack_message()` (l713)
- **Stubs/TODOs:** None explicit.
- **Notable:**
  - `open_positions` and `shadow_positions` are plain `list` objects mutated from **two threads** with no lock (see Concurrency section).
  - `_all_signals = []` is reset in `_run_session()` (l211) mid-session on the main thread. Fine only because `_run_b6_for_user()` also runs on main thread — but fragile if that changes.
  - `_pending_sessions` stores raw `data` dict references from B1 output; `_check_or_breakouts()` mutates `data["features"]` in-place (l312–314) after Phase A. This means feature dicts are mutable across the ~30min OR window.
  - Lazy imports scattered throughout methods (l189, l196, l202, l446, l465, etc.) — non-standard but thread-safe.

---

### File: captain-online/captain_online/blocks/or_tracker.py

- **Purpose:** Thread-safe OR (Opening Range) state machine — tracks high/low during OR window from live quote ticks, detects breakout/expiry.
- **Key functions/classes:**
  - `ORState` (Enum) — l39: WAITING/FORMING/COMPLETE/BREAKOUT_LONG/BREAKOUT_SHORT/EXPIRED
  - `AssetORSession` — l49: per-asset OR state (`__slots__` for efficiency)
  - `ORTracker` — l205: main tracker with `threading.Lock()`
  - `on_quote()` — l255: called from MarketStream thread on every tick
  - `register_asset()` — l223: called from orchestrator main thread at session open
  - `check_expirations()` — l289: called from main thread every ~1s
  - `_load_session_registry()` — l119: lazy-cached JSON load
  - `_load_contract_to_asset()` — l170: lazy-cached JSON load
- **Session/schedule refs:**
  - `session_registry.json` — OR window times per session type (NY/LON/APAC).
  - `get_asset_session_type()` (l146), `get_or_times()` (l152).
- **QuestDB:** None.
- **Redis:** None.
- **Stubs/TODOs:** None.
- **Notable:**
  - `get_state()` (l245) returns the live `AssetORSession` object — **not a copy** — despite the docstring saying "snapshot". The calling code in `_check_or_breakouts()` reads `state.is_resolved`, `state.state`, `state.or_range`, `state.entry_price`, `state.direction` without holding the lock (see Concurrency section).
  - `_registry_cache` and `_contract_to_asset` (l116, l167) are module-level mutable dicts with non-atomic lazy init — no lock guards the check-then-set pattern. Low risk due to idempotence but technically racy.
  - `cutoff` is stored as `timetz()` (l74), which is correct for within-day comparisons but timezone-aware comparison requires both sides to use the same tzinfo.
  - `ORTracker.clear()` (l318) exists but is **never called** — stale sessions accumulate across days. Harmless because `register_asset()` overwrites, but state from yesterday could be read in the ~1s window between process wake-up and the first `register_asset()` call.

---

### File: captain-online/captain_online/blocks/b1_data_ingestion.py

- **Purpose:** Pre-session data ingestion — loads all QuestDB state tables, validates data quality, runs Data Moderator checks, computes features via b1_features.
- **Key functions/classes:**
  - `run_data_ingestion()` — l695: main entry point, returns full data dict or None
  - `_load_active_assets()` — l46
  - `_load_aim_states()` — l97
  - `_load_aim_weights()` — l134
  - `_load_ewma_states()` — l162
  - `_load_kelly_params()` — l191
  - `_load_tsm_configs()` — l224
  - `_run_data_moderator()` — l352: validates price bounds, volume, missing sources, timestamps
  - `_check_roll_calendar()` — l431
  - `_get_latest_price()` — l485: stream cache → REST fallback
  - `_get_prior_close()` — l511: TopstepX daily bars
- **Session/schedule refs:**
  - `SESSION_IDS` constant used to map `session_id` to name (l62, l703).
  - `session_match()` (l668): checks `session_hours` JSON from P3-D00.
- **QuestDB reads:**
  - `p3_d00_asset_universe` (l49): assets, locked_strategy, roll_calendar
  - `p3_d01_aim_model_states` (l100): AIM states
  - `p3_d02_aim_meta_weights` (l137): DMA weights
  - `p3_d05_ewma_states` (l165): EWMA win/loss stats
  - `p3_d08_tsm_state` (l227): TSM configurations
  - `p3_d12_kelly_parameters` (l194): Kelly params
  - `p3_d17_system_monitor_state` (l333): system params
- **QuestDB writes:**
  - `p3_d00_asset_universe` (l590): `captain_status`, `data_quality_flag` on DATA_HOLD
  - `p3_d17_system_monitor_state` (l621): data quality log
  - `p3_d21_incident_log` (l603): new incidents on quality failures
- **Redis:** `CH_ALERTS` publish on roll calendar events (l631).
- **Stubs/TODOs:**
  - `_check_data_source_for_feature()` — l574: always returns `True` (stub)
  - `_has_valid_timestamp()` — l578: always returns `True` (stub)
- **Notable:**
  - `_publish_alert()` uses `datetime.now().isoformat()` (l642) without timezone — inconsistent with system-wide ET standard.
  - `_check_roll_calendar()` uses `datetime.now().date()` (l436) without timezone — could give wrong date near midnight UTC vs ET boundary.
  - All data loads (`_load_aim_states` etc.) use `ORDER BY last_updated DESC` without `LATEST ON` — correct dedup pattern but potentially slow on large tables.
  - `_get_avg_session_volume_20d()` makes a REST API call to TopstepX for 20-day data at every session open (l547–558). No caching — repeated REST roundtrips per asset.

---

### File: captain-online/captain_online/blocks/b1_features.py

- **Purpose:** 17 feature computation functions (Appendix A) + data access utilities. Computes VRP, PCR, GEX, IVTS, calendar, COT, correlation, momentum, spread, opening volume per asset.
- **Key functions/classes:**
  - `compute_all_features()` — l537: master entry, iterates assets, delegates to per-AIM functions
  - `compute_vrp()`, `compute_overnight_vrp()` — l46, l61: AIM-01
  - `compute_put_call_ratio()`, `compute_dotm_otm_put_spread()` — l76, l87: AIM-02
  - `compute_dealer_net_gamma()` — l105: AIM-03
  - `check_economic_calendar()` — l138: AIM-06
  - `rolling_20d_correlation()` — l233: AIM-08
  - `compute_cross_asset_momentum()` — l248: AIM-09
  - `volume_first_N_min()` — l337: AIM-15
  - `store_opening_volume()` — l1146: write to P3-D29 (called post-OR)
  - `store_opening_volatility()` — l1170: write to P3-D33 (called post-OR)
  - `store_daily_ohlcv()` — l1196: write to P3-D30 (called post-OR)
- **Session/schedule refs:** `_get_session_open_time()` (l1073) hardcodes 9:30 ET for all assets regardless of session type.
- **QuestDB reads:**
  - `p3_d31_implied_vol` — ATM IV, realized vol (l826, l844)
  - `p3_d30_daily_ohlcv` — daily OHLCV for returns/baselines (l1050)
  - `p3_d32_options_skew` — skew spread proxy (l933)
  - `p3_d29_opening_volumes` — historical opening volumes (l1133)
  - `p3_d33_opening_volatility` — trailing 5-min vol (l1327)
  - `p3_spread_history` — trailing spreads (l1270) [**undocumented table**]
  - `p3_d17_system_monitor_state` — last known feature values (l426)
  - `p3_d00_asset_universe` — all universe assets (l1067)
- **QuestDB writes:**
  - `p3_spread_history` — current spread (l700) [**undocumented table**]
  - `p3_d29_opening_volumes` (l1158), `p3_d33_opening_volatility` (l1186), `p3_d30_daily_ohlcv` (l1222)
- **Redis:** None.
- **Stubs/TODOs:**
  - `_get_overnight_range()` — l859: returns `None` (stub)
  - `_get_options_volume()` — l946: returns `None` (stub)
  - `_get_put_iv()` — l949: returns `None` (stub)
  - `_get_option_chain()` — l952: returns `None` (stub)
  - `_get_trailing_pcr()` — l919: returns `None` (stub)
  - `_load_latest_cot()` — l1008: returns `None` (stub)
  - `_load_cot_history()` — l1011: returns `[]` (stub)
  - `_get_cl_spot()` — l1259: returns `None` (stub)
  - `_get_cl_front_futures()` — l1262: returns `None` (stub)
  - **Total stubs: 9** (AIM-01 overnight, AIM-02 options vol, AIM-03 option chain, AIM-07 COT ×2, AIM-11 CL basis ×2)
- **Notable:**
  - `compute_all_features()` uses `datetime.now()` (l546, no timezone) for `today`. Used in AIM-10 OPEX window, AIM-06 calendar, AIM-04 EIA Wednesday — incorrect near midnight UTC vs ET boundary.
  - `store_opening_volatility()` and `store_opening_volume()` use `pytz` (l1153, l1181) while the rest of the codebase uses `zoneinfo`. Inconsistent.
  - `store_opening_volatility()` inserts into `p3_d33_opening_volatility` without a `ts` column (l1185–1190) — depends on table having a default timestamp.
  - `p3_spread_history` (l700, l1270) is written and read by this file but is not in the documented 29-table schema. Orphaned/undocumented table.
  - `_get_contract_multiplier()` (l955) always returns 50.0 (ES default) regardless of asset — incorrect for MES (5.0), NQ (20.0), etc. Will produce wrong GEX values.

---

## Startup / Shutdown Sequence

```
main() entry
  ├─ 1. QuestDB ping (sys.exit on failure)
  ├─ 2. Redis ping (sys.exit on failure)
  ├─ 3. ensure_consumer_group(STREAM_COMMANDS, GROUP_ONLINE_COMMANDS)
  ├─ 4. get_last_checkpoint / write_checkpoint("STARTUP")
  ├─ 5. _start_market_streams()
  │     ├─ TopstepX authenticate
  │     ├─ preload_contracts
  │     ├─ MarketStream(on_quote=or_tracker.on_quote).start()  ← spawns thread
  │     └─ returns stream handle (or None on failure)
  ├─ 6. write_checkpoint("STREAMS_STARTED")
  ├─ 7. OnlineOrchestrator(or_tracker=or_tracker)
  ├─ 8. signal.signal(SIGTERM, shutdown_handler)
  ├─ 9. signal.signal(SIGINT, shutdown_handler)
  └─ 10. orchestrator.start()  ← BLOCKS
         ├─ spawn _command_listener thread (daemon)
         └─ _session_loop() — while self.running: (1s tick)

shutdown_handler(signum, frame):
  orchestrator.stop()         # sets self.running = False
  market_stream.stop()        # stops WebSocket thread
  write_checkpoint("SHUTDOWN")
  sys.exit(0)
```

**Order is sound.** Infrastructure verified before streams; streams before orchestrator; signal handlers before the blocking call.

---

## Async Patterns

The system is **synchronous + threading** (not asyncio). Key threads:

| Thread | Owner | Start | Shared State |
|--------|-------|-------|-------------|
| Main (session loop) | `orchestrator._session_loop()` | `orchestrator.start()` | `open_positions`, `shadow_positions`, `_pending_sessions` |
| Command listener | `orchestrator._command_listener()` | `orchestrator.start()` | `open_positions`, `shadow_positions` (WRITE) |
| MarketStream | `MarketStream.start()` | `_start_market_streams()` | `or_tracker._sessions` (via `on_quote`) |

No `asyncio.create_task` or `await` in these files.

---

## WebSocket Lifecycle

- `MarketStream` is created in `_start_market_streams()` and started with `.start()`.
- Reconnection logic is **inside `MarketStream`** (not visible in these files; defined in `shared/topstep_stream.py`).
- If stream fails silently (no exception), `on_quote` callbacks stop firing → ORTracker receives no ticks → assets go `FORMING → EXPIRED` via `check_expirations()` (or_tracker.py l289–315). This is a reasonable fallback.
- `market_stream` can be `None` if `_start_market_streams()` fails (l112–113). Shutdown handler guards for this (l123: `if market_stream:`). Session loop continues without live prices — Data Moderator checks should catch stale data, but this path is not fully exercised.

---

## Data Flow: Market Open → Signals

```
MarketStream.on_quote (thread)
  └─ or_tracker.on_quote(data)
       └─ resolves contract_id → asset_id
       └─ _update_state(): WAITING → FORMING → COMPLETE → BREAKOUT/EXPIRED

_session_loop (1s tick, main thread)
  ├─ _is_session_opening(): NY/LON/APAC window check
  │    └─ _run_session(session_id):
  │         ├─ _circuit_breaker_check()
  │         ├─ early OR registration: register_asset() per active asset
  │         ├─ Phase A:
  │         │    B1 run_data_ingestion()    ← QuestDB reads + REST calls
  │         │    B2 run_regime_probability()
  │         │    B3 run_aim_aggregation()
  │         │    B4 run_kelly_sizing()      ┐
  │         │    B5 run_trade_selection()   ├ per-user loop
  │         │    B5B run_quality_gate()     │
  │         │    B5C run_circuit_breaker()  ┘
  │         └─ store _pending_sessions[session_id]
  │
  └─ _check_or_breakouts() [if pending_sessions]:
       ├─ check_expirations()
       ├─ for each resolved asset:
       │    inject or_range, entry_price, direction into features
       │    _recompute_aim15_volume()
       │    store_daily_ohlcv(), store_opening_volatility()
       └─ Phase B:
            B6 run_signal_output() per user per asset
            register_shadow_position()
```

---

## Opening Range Tracking

**Definition:** OR window = `or_start` to `or_end` from `session_registry.json`. For NY: 09:30–09:35 (5 min default). Each asset can have its own `OR_window_minutes` from `locked_strategy.strategy_params`.

**State machine per asset:**
```
WAITING → (first tick ≥ or_start) → FORMING → (tick ≥ or_end) → COMPLETE
  COMPLETE + price > or_high → BREAKOUT_LONG
  COMPLETE + price < or_low  → BREAKOUT_SHORT
  COMPLETE/FORMING + now ≥ cutoff → EXPIRED (check_expirations)
```

**Cutoff:** `or_end + DEFAULT_BREAKOUT_CUTOFF_MINUTES (30)`. So breakout must happen within 30 minutes of OR close.

**Two-phase design:** Orchestrator registers assets BEFORE Phase A (l166–183) so ticks are captured during the ~1–2 min Phase A pipeline run.

---

## Lifecycle Audit (ln-629)

### LCA-01 — Bootstrap Order
**Severity:** PASS
Initialization sequence: config → QuestDB → Redis → streams → orchestrator → signal handlers → blocking run. No dependency used before initialization. **Score contribution: PASS**

### LCA-02 — Graceful Shutdown
**Severity:** MEDIUM
`shutdown_handler()` (main.py l120) handles SIGTERM and SIGINT. It calls `orchestrator.stop()` and `market_stream.stop()`. However, `sys.exit(0)` is called inside the signal handler (l126). If the signal arrives mid-QuestDB query (e.g., during `_run_session()` in the main thread), the query may be interrupted abruptly. A cleaner approach is to set a flag and let the main loop exit cleanly.

**Recommendation:** Replace `sys.exit(0)` with a flag. Let `_session_loop()` exit when `self.running` is False instead of forcing process termination.
**Effort:** S

### LCA-03 — Resource Cleanup on Exit
**Severity:** LOW
QuestDB connections (psycopg2) and Redis connections are **not explicitly closed** in the shutdown handler. They will be garbage-collected, but open TCP connections may linger until OS timeout. For a Docker container with a PID 1 process, this is acceptable but not ideal.

**Recommendation:** Add `get_connection().close()` or connection pool shutdown in the shutdown handler.
**Effort:** S

### LCA-04 — Signal Handling
**Severity:** PASS
Both SIGTERM (Docker stop signal) and SIGINT (Ctrl-C) are handled. Daemon thread (`_command_listener`) will auto-terminate when main thread exits.

### LCA-05 — Liveness/Readiness Probes
**Severity:** MEDIUM
Captain Online runs in Docker but has **no liveness or readiness HTTP endpoint**. Docker can only detect process death, not logical hangs (e.g., stuck in a QuestDB query). If `_session_loop()` deadlocks, the container stays "healthy" indefinitely.

**Recommendation:** Add a `/health` endpoint (or file-based probe) that verifies the last `_session_loop` iteration was within the last 30 seconds.
**Effort:** M

**Lifecycle Score: 6.5/10**
Issues: 2 MEDIUM (shutdown sys.exit, no probes), 1 LOW (resource cleanup)

---

## Concurrency Audit (ln-628)

### CA-01 — Thread Safety: `open_positions` and `shadow_positions` (HIGH)
**Location:** `orchestrator.py` l61–62 (declaration), l762/l769 (written by command thread), l591–600/l602–610 (read+written by main thread)

**Finding:** Two shared `list` objects (`open_positions`, `shadow_positions`) are mutated from two different threads with **no lock**:

- **Main thread** (session loop): `_run_position_monitor()` calls `self.open_positions.remove(pos)` (l598); `_run_shadow_monitor()` calls `self.shadow_positions.remove(shadow)` (l608).
- **Command listener thread**: `_handle_taken_skipped()` calls `self.open_positions.append(position)` (l762) and rewrites `self.shadow_positions` (l769: full list replacement).

`list.append()` is atomic in CPython (GIL-protected) but `list.remove()` and list replacement are not atomic with respect to concurrent `append()`. Race scenario: main thread iterates `open_positions` in `_run_position_monitor()` while command thread appends a new position — `list.remove()` on a concurrently-growing list is safe, but the list-comprehension replacement at l769 (`self.shadow_positions = [...]`) is **not atomic** with the main thread's `_run_b6_for_user()` appending to shadow_positions.

**Severity:** HIGH — could silently drop shadow positions or cause `ValueError` on remove.

**Recommendation:** Guard `open_positions` and `shadow_positions` with a `threading.Lock()`. Acquire in `_handle_taken_skipped`, `_run_position_monitor`, `_run_shadow_monitor`, and `_run_b6_for_user`.
**Effort:** M

### CA-02 — ORTracker `get_state()` Returns Live Object (MEDIUM)
**Location:** `or_tracker.py` l245–248 (`get_state()`), `orchestrator.py` l301–315 (caller reads without lock)

**Finding:** `get_state()` returns the live `AssetORSession` object. The calling code in `_check_or_breakouts()` reads `state.is_resolved`, `state.state`, `state.or_range`, `state.entry_price`, `state.direction` (l301–315) without holding `_lock`. Meanwhile, `on_quote()` (MarketStream thread) modifies the same object under `_lock`. CPython's GIL makes individual attribute reads atomic, but reading multiple fields gives no atomicity guarantee — the caller could observe `state.state = COMPLETE` but `state.or_high = None` if a tick arrives between the two reads.

**Severity:** MEDIUM — unlikely in practice (OR window closes in 5 min with stable prices) but represents a logical race that could produce `None` entry prices.

**Recommendation:** Change `get_state()` to return `session.to_dict()` (a plain dict snapshot) rather than the live object. Or wrap the multi-field read in orchestrator with the tracker's lock via a new `get_resolved_state(asset_id)` method.
**Effort:** S

### CA-03 — Module-Level Cache Race in or_tracker.py (LOW)
**Location:** `or_tracker.py` l116–143 (`_registry_cache`), l167–198 (`_contract_to_asset`)

**Finding:** Both lazy-initialized module-level dicts use an unguarded check-then-set pattern:
```python
if _registry_cache is not None:
    return _registry_cache
# ... load from file ...
_registry_cache = json.load(...)
```
These are called from both the MarketStream thread (`on_quote` → `_load_contract_to_asset`) and the main orchestrator thread (`register_asset` → `_load_session_registry`). Without a lock, both threads could execute the load simultaneously. Since the operation is idempotent (same file), the only consequence is redundant file I/O.

**Severity:** LOW — no data corruption risk, just potential double-load at startup.

**Recommendation:** Use `functools.lru_cache` (thread-safe in CPython 3.12+) or a module-level `threading.Lock()` for the lazy init.
**Effort:** S

### CA-04 — `_all_signals` Reset Race (LOW)
**Location:** `orchestrator.py` l211 (`self._all_signals = []`), l344 (`.extend()`)

**Finding:** `_all_signals` is reset to `[]` at the start of `_run_session()` (main thread) and extended in `_check_or_breakouts()` (also main thread). Both paths are on the main thread, so no race. However, if a future change moves OR breakout handling to a thread pool, this becomes racy.

**Severity:** LOW — not currently unsafe, but fragile design.

### CA-05 — Blocking I/O in Session Loop (INFORMATIONAL)
**Location:** `b1_data_ingestion.py` l497–507 (`_get_latest_price` REST fallback), l520–526 (`_get_prior_close`), l547–558 (`_get_avg_session_volume_20d`)

**Finding:** Multiple synchronous REST API calls to TopstepX are made during `run_data_ingestion()` on the main thread. Each call can take 0.5–3 seconds. For 10 assets × 3 REST calls = up to 90 seconds of blocking. This is acceptable in a synchronous design but violates the B1 latency target of `<5 seconds` stated in the module docstring.

**Severity:** MEDIUM (latency / spec violation) — not a concurrency safety issue but session timing-critical.

**Recommendation:** Cache daily bars (prior close, 20-day volumes) with a TTL, or pre-fetch in parallel using `concurrent.futures.ThreadPoolExecutor`.
**Effort:** M

**Concurrency Score: 5.5/10**
Issues: 1 HIGH (list mutation race), 1 MEDIUM (live object race), 1 MEDIUM (blocking I/O latency), 1 LOW (cache race), 1 LOW (fragile reset)

---

## Cross-Cutting Findings

### CCF-01 — `p3_spread_history` Undocumented Table (MEDIUM)
**Location:** `b1_features.py` l700–706 (write), l1270 (read)

`p3_spread_history` is written and read by `compute_all_features()` but does not appear in the 29-table schema documented in `CLAUDE.md` or the spec files. If the table does not exist, the `INSERT` at l700 will silently fail (wrapped in `except: pass`), but feature computation continues. The z-score will be `None` for AIM-12 spread_z on first run.

**Recommendation:** Either document and init this table in `scripts/init_questdb.py`, or rename it to match the P3 schema (e.g., `p3_d34_spread_history`).

### CCF-02 — `_get_contract_multiplier()` Returns ES Default for All Assets (HIGH)
**Location:** `b1_features.py` l955–956

```python
def _get_contract_multiplier(asset_id: str) -> float:
    return 50.0  # ES default
```

This is used by `compute_dealer_net_gamma()` (AIM-03 GEX). For MES (multiplier=5), NQ (20), MNQ (2), ZB (1000), ZN (1000), MGC (100) — GEX values will be wrong by factors of 10–200×. This makes AIM-03 outputs meaningless for all non-ES assets.

**Recommendation:** Look up multiplier from `assets_detail` dict (available from B1 data) or from P3-D00 `point_value` field.

### CCF-03 — Naive `datetime.now()` Without Timezone (MEDIUM)
**Locations:**
- `b1_data_ingestion.py` l436 (`_check_roll_calendar`)
- `b1_data_ingestion.py` l642 (`_publish_alert` timestamp)
- `b1_features.py` l546 (`compute_all_features` `today`)

System-wide rule: all timestamps must use `America/New_York`. These calls use naive local time. Near midnight ET, `datetime.now().date()` could give the wrong trading date (off by one day).

**Recommendation:** Replace all `datetime.now()` with `datetime.now(_ET)` where `_ET = ZoneInfo("America/New_York")`.

### CCF-04 — `_get_session_open_time()` Hardcodes NY Times (LOW)
**Location:** `b1_features.py` l1073–1082

Returns 9:30 ET for all assets regardless of session type. LON/APAC assets will get wrong `event_proximity` calculations for AIM-06.

**Recommendation:** Accept `session_type` parameter and look up from `session_registry.json`.

### CCF-05 — Two Stubs in Data Moderator (MEDIUM)
**Location:** `b1_data_ingestion.py` l574 (`_check_data_source_for_feature`), l578 (`_has_valid_timestamp`)

Both return `True` unconditionally. The Data Moderator's `STALE_FEATURE` detection (l398–404) and timestamp rejection path (l408–413) are effectively disabled. If a real data source goes stale or returns bad timestamps, the system will proceed without flagging it.

**Recommendation:** Implement `_has_valid_timestamp()` to check that the most recent quote in `quote_cache` has a timestamp within the last N minutes.

---

## Session 1 Summary

- **Files audited:** 5
- **Key findings:** 13
  - HIGH: `open_positions`/`shadow_positions` list mutation race between command thread and main thread; `_get_contract_multiplier()` returns ES-only constant for all assets
  - MEDIUM: `get_state()` returns live ORTracker object (lock escape); `sys.exit()` in signal handler; no Docker health/readiness probes; blocking REST I/O in B1 (latency vs <5s target); `p3_spread_history` undocumented table; naive `datetime.now()` in 3 locations; Data Moderator stubs disabled
  - LOW: module-level cache double-init race; `_all_signals` fragile reset; `ORTracker.clear()` never called; `_get_session_open_time()` hardcoded NY
- **Stub count:** 11 total (9 in b1_features.py: AIM-01 overnight range, AIM-02 options vol ×2, AIM-03 option chain, AIM-07 COT ×2, AIM-11 CL basis ×2; 2 in b1_data_ingestion.py: `_check_data_source_for_feature`, `_has_valid_timestamp`)
- **Cross-service deps discovered:**
  - Redis channels: `captain:status` (CH_STATUS), `captain:commands` (STREAM_COMMANDS/GROUP_ONLINE_COMMANDS), `captain:alerts` (CH_ALERTS)
  - QuestDB tables: p3_d00, p3_d01, p3_d02, p3_d05, p3_d08, p3_d12, p3_d15, p3_d16, p3_d17, p3_d21, p3_d29, p3_d30, p3_d31, p3_d32, p3_d33, **p3_spread_history** (undocumented)
  - Shared modules: `topstep_client`, `topstep_stream` (quote_cache), `contract_resolver`, `redis_client`, `questdb_client`, `journal`, `constants`, `vix_provider`
  - Config files: `config/session_registry.json`, `config/contract_ids.json`, `config/economic_calendar_2026.json`

---

## Part 2: AIMs & Regime

**Auditor:** Claude Opus 4.6
**Date:** 2026-04-08
**Skills applied:** ln-624 Code Quality Auditor, ln-626 Dead Code Auditor
**Scope:** Regime probability classification, AIM modifier computation, MoE/DMA aggregation, replay feature loading (Blocks 2-3).

---

## File Inventory

### File: captain-online/captain_online/blocks/b2_regime_probability.py

- **Purpose:** Classify market regime (HIGH_VOL / LOW_VOL) per asset via Pettersson binary rule (C4) or XGBoost classifier (C1-C3).
- **Key functions/classes:**
  - `run_regime_probability()` — l30: main entry, iterates assets, dispatches to binary or classifier path
  - `_binary_regime()` — l95: C4 Pettersson binary — sigma_t vs phi threshold
  - `_compute_realised_vol()` — l119: 20-day annualised RV from daily returns
  - `_classifier_regime()` — l144: C1-C3 XGBoost classifier with serialised model object
  - `argmax_regime()` — l189: utility — returns regime with highest probability
- **Session/schedule refs:** None (pure computation, called by orchestrator per session).
- **QuestDB:** None direct (consumes features dict from B1).
- **Redis:** None.
- **Stubs/TODOs:**
  - `_compute_realised_vol()` l132-139: VRP fallback branch is dead — `pass` statement, always falls through to `return None`.
  - `_classifier_regime()` l168: classifier_object fallback — if no serialised model, uses regime_label as hard label. Not a stub, but graceful degradation.
- **Notable:**
  - **Duplicate assignment bug** at l75 and l83: `regime_probs[asset_id] = probs` is set inside the `else` branch (l75) AND unconditionally after the if/else (l83). The l75 assignment is always overwritten. Functionally harmless but indicates copy-paste sloppiness.
  - Lazy imports inside `_compute_realised_vol()` (l125-126: `from captain_online.blocks.b1_features import _get_daily_returns` + `import numpy as np`) and `_classifier_regime()` (l157: `extract_classifier_features`). Cross-container import at runtime — works because we're in the same Docker process, but couples B2 to B1 internals.
  - Regime classifier: **HYBRID** method. Binary rule for C4 (Pettersson threshold from P2-D07), XGBoost for C1-C3 (serialised model in `classifier_object` field). In practice, most assets likely use `REGIME_NEUTRAL` fallback (50/50) because classifier objects may not be bootstrapped.
  - Output states: `{HIGH_VOL: float, LOW_VOL: float}` per asset. Uncertainty flag: `max_prob < 0.6` → robust Kelly downstream.

---

### File: captain-online/captain_online/blocks/b3_aim_aggregation.py

- **Purpose:** Re-export shim — delegates all logic to `shared/aim_compute.py` for shared use by live and replay paths.
- **Key functions/classes:** None original. Re-exports: `MODIFIER_FLOOR`, `MODIFIER_CEILING`, `run_aim_aggregation`, `compute_aim_modifier`.
- **Session/schedule refs:** None.
- **QuestDB:** None.
- **Redis:** None.
- **Stubs/TODOs:** None.
- **Notable:**
  - **Legacy shim pattern.** Docstring says "re-exports for backward compatibility with existing imports." Two active callers remain: `orchestrator.py:201` (Phase A) and `scripts/replay_full_pipeline.py:150`. Tests and replay_engine already import directly from `shared.aim_compute`. The shim is still needed but should be consolidated.
  - QuantConnect import guard (l1-5) — dead in Docker.

---

### File: shared/aim_compute.py

- **Purpose:** Single source of truth for AIM modifier computation — MoE/DMA aggregation orchestrator + 14 individual AIM handler functions.
- **Key functions/classes:**
  - `z_score()` — l50: pure-Python z-score (intentional duplicate of b1_features version, avoids numpy dependency in shared/)
  - `_clamp()` — l70: value clamping utility
  - `run_aim_aggregation()` — l79: MoE orchestrator — checks status/weight, dispatches, aggregates
  - `compute_aim_modifier()` — l185: dispatch table routing to individual AIM handlers
  - `_aim01_vrp()` — l227: VRP z-score → modifier (with Monday adjustment)
  - `_aim02_skew()` — l268: PCR/skew weighted combination
  - `_aim03_gex()` — l306: dealer gamma sign → dampen/amplify
  - `_aim04_ivts()` — l319: 5-zone IVTS (CRITICAL regime filter) + overnight gap + EIA overlay
  - `_aim06_calendar()` — l380: economic calendar tier/proximity
  - `_aim07_cot()` — l413: COT SMI polarity + extreme positioning overlay
  - `_aim08_correlation()` — l453: cross-asset correlation z-score → 4 tiers
  - `_aim09_momentum()` — l477: cross-asset MACD alignment
  - `_aim10_calendar_effects()` — l493: OPEX window only (DOW removed per DEC-04)
  - `_aim11_regime_warning()` — l507: VIX z-score + VIX change spike + CL basis overlay
  - `_aim12_costs()` — l553: spread_z OR vol_z → cost adjustment + VIX overlay
  - `_aim13_sensitivity()` — l596: passthrough from Offline B5 state (FRAGILE → 0.85)
  - `_aim14_expansion()` — l608: always 1.0 (informational placeholder)
  - `_aim15_volume()` — l613: opening volume ratio → 4 tiers
  - `_aim16_hmm()` — l637: **DEAD CODE** — not in dispatch table (removed per DEC-06)
- **Session/schedule refs:** None (pure computation).
- **QuestDB:** None direct (consumes pre-loaded features, aim_states, aim_weights dicts).
- **Redis:** None.
- **Stubs/TODOs:**
  - AIM-05: DEFERRED (no handler, slot reserved in `_AIM_NAMES` dict).
- **Notable:**
  - **`_aim16_hmm()` is dead code** (l637-649). Removed from dispatch per DEC-06; now handled by Block 5 `apply_hmm_session_allocation()`. Function body remains — should be deleted.
  - `_AIM_NAMES` dict (l102-107) is defined inside `run_aim_aggregation()` — recreated on every call. Should be a module-level constant.
  - Duplicate `z_score()` (l50) vs `b1_features.z_score()` (l357). Docstring at l51 explains: "Pure-Python implementation so shared/ stays dependency-light." Intentional architectural choice.
  - All threshold magic numbers are spec-driven (DEC-01 authoritative), documented in each handler's docstring.

---

### File: shared/aim_feature_loader.py

- **Purpose:** Historical AIM feature loader for session replay — builds features dict, aim_states, and aim_weights from QuestDB tables + VIX CSVs.
- **Key functions/classes:**
  - `load_replay_features()` — l29: main entry, returns (features, aim_states, aim_weights) tuple
  - `_load_vix_features()` — l60: VIX/VXV → ivts, vix_z, vix_daily_change_z
  - `_load_ohlcv_features()` — l108: OHLCV → overnight_return_z, cross_momentum, correlation_z
  - `_load_iv_rv_features()` — l205: implied vol → vrp_overnight_z (ES only)
  - `_load_skew_features()` — l234: options skew → skew_z (ES only)
  - `_load_volume_features()` — l259: vol_z from opening volatility, opening_volume_ratio from volumes
  - `_load_calendar_features()` — l296: date-derived features (day_of_week, is_opex_window, is_eia_wednesday)
  - `_load_aim_states_and_weights()` — l320: D01/D02 from QuestDB with dedup via ORDER BY last_updated DESC
  - `_third_friday()` — l385: OPEX date utility
  - `_pearson()` — l396: pure-Python Pearson correlation
- **Session/schedule refs:** None (replay operates on historical dates).
- **QuestDB reads:**
  - `p3_d30_daily_ohlcv` (l118, l161): trailing closes/opens for returns, correlation
  - `p3_d31_implied_vol` (l209): ATM IV + realised vol for VRP (ES only)
  - `p3_d32_options_skew` (l238): CBOE skew for skew_z (ES only)
  - `p3_d33_opening_volatility` (l264): opening range pct for vol_z
  - `p3_d29_opening_volumes` (l276): volume_first_m_min for opening_volume_ratio
  - `p3_d01_aim_model_states` (l331): AIM status + current_modifier (with ORDER BY dedup)
  - `p3_d02_aim_meta_weights` (l359): DMA weights (with ORDER BY dedup)
- **Redis:** None.
- **Stubs/TODOs:** None (code stubs). But 7 feature data gaps — features that handlers expect but replay cannot provide:
  - `pcr_z` — no PCR data source (l251, comment)
  - `gex` — no options chain data
  - `cot_smi`, `cot_speculator_z` — no COT data
  - `event_proximity`, `events_today` — no calendar feed in replay (l310-311)
  - `spread_z` — no spread history data
  - `cl_basis` — no CL spot/futures data
- **Notable:**
  - **Private attribute access** at l67-71: `vix_provider._vix_data`, `vix_provider._vxv_data`, `vix_provider._ensure_loaded()` — reaches into private internals. Dead assignment at l67 (overwritten at l69 after `_ensure_loaded()`).
  - **`correlation_z` is NOT a z-score** (l193): comment says "Simplified: use the correlation value directly as proxy z-score." Raw Pearson correlation is in [-1, 1]. AIM-08 thresholds expect z-scored input where >1.5 triggers CORR_STRESS. With raw correlation, CORR_STRESS is **unreachable in replay**.
  - **ORDER BY mismatch** at l279: `WHERE session_date <= %s ORDER BY ts DESC LIMIT 30`. WHERE filters by `session_date` (STRING) but ORDER BY uses `ts` (TIMESTAMP, designated). If data was backfilled out of chronological order, LIMIT 30 may return wrong rows.
  - **N+1 query pattern** in `load_replay_features()` (l41-49): 4-5 SQL queries per asset × 10 assets = 40-50 queries plus 2 for states/weights. Acceptable for batch replay.
  - SQL injection safe — all queries use parameterised `%s` placeholders.

---

## Regime Classifier Detail

**Method:** Hybrid — two paths based on asset category.

| Path | Assets | Method | Inputs | Thresholds |
|------|--------|--------|--------|------------|
| Binary (Pettersson) | C4 | sigma_t vs phi | 20-day realised vol (annualised) | phi from P2-D07 `pettersson_threshold` |
| XGBoost Classifier | C1-C3 | `predict_proba()` | Feature vector from B1 (`extract_classifier_features`) | Class ordering: [LOW_VOL, HIGH_VOL] |
| Fallback | Any | REGIME_NEUTRAL | None | 50/50 split |

**Uncertainty gate:** If `max_prob < 0.6` → `regime_uncertain[asset_id] = True` → downstream uses robust Kelly sizing.

**Current production reality:** Most assets likely fall through to REGIME_NEUTRAL (50/50) because:
1. `classifier_object` in P2-D07 may not be populated for most assets
2. `REGIME_NEUTRAL` label triggers 50/50 return without classifier invocation
3. Binary path requires `pettersson_threshold` which may only exist for C4 assets

---

## MoE/DMA Aggregation Detail

**Gating logic (per asset × AIM):**
1. AIM state must exist in `aim_states["by_asset_aim"][(asset_id, aim_id)]`
2. State `status` must be `"ACTIVE"`
3. DMA weight must exist in `aim_weights[(asset_id, aim_id)]`
4. `inclusion_flag` must be `True` (DMA can exclude underperforming AIMs)

**Aggregation formula:**
```
combined_modifier = Σ(modifier_i × w_i) / Σ(w_i)
where w_i = inclusion_probability from D02
```

**Clamping:** `combined_modifier ∈ [0.5, 1.5]` (MODIFIER_FLOOR / MODIFIER_CEILING).

**Forgetting factor:** Lambda (λ) is NOT applied at aggregation time. DMA weight updates happen in Offline process (D02 meta-weight update cycle). Aggregation simply reads the current weights.

**If no active AIMs:** `combined_modifier = 1.0` (neutral, no sizing adjustment).

---

## AIM Inventory

| AIM ID | Name | Handler | In Dispatch | Upstream Data Status | Effective in Production |
|--------|------|---------|-------------|---------------------|------------------------|
| 01 | VRP | `_aim01_vrp` | YES | PARTIAL — `vrp_overnight_z` needs p3_d31 (ES only, 122 days) | ES only |
| 02 | Skew | `_aim02_skew` | YES | PARTIAL — `pcr_z` stub; `skew_z` needs p3_d32 (ES only, 81 days) | ES only (skew half) |
| 03 | GEX | `_aim03_gex` | YES | DEAD-ON-ARRIVAL — `gex` depends on stub `_get_option_chain()` in b1_features | Never fires |
| 04 | IVTS | `_aim04_ivts` | YES | FUNCTIONAL — `ivts` from vix_provider VIX/VXV CSVs (9155+ rows) | All assets |
| 05 | — | — | NO | DEFERRED by spec | — |
| 06 | EconCal | `_aim06_calendar` | YES | FUNCTIONAL — `economic_calendar_2026.json` loaded by B1 | All assets |
| 07 | COT | `_aim07_cot` | YES | DEAD-ON-ARRIVAL — `cot_smi`/`cot_speculator_z` stubs in b1_features | Never fires |
| 08 | CrossCorr | `_aim08_correlation` | YES | FUNCTIONAL — `correlation_z` from p3_d30 OHLCV | All non-ES assets |
| 09 | CrossMom | `_aim09_momentum` | YES | FUNCTIONAL — `cross_momentum` from p3_d30 OHLCV | All assets |
| 10 | Calendar | `_aim10_calendar_effects` | YES | FUNCTIONAL — date-derived (`is_opex_window`) | All assets |
| 11 | RegimeWarn | `_aim11_regime_warning` | YES | FUNCTIONAL — `vix_z` from vix_provider | All assets |
| 12 | DynCosts | `_aim12_costs` | YES | PARTIAL — `spread_z` needs undocumented p3_spread_history; `vol_z` from p3_d33 | vol_z half only |
| 13 | Sensitivity | `_aim13_sensitivity` | YES | DEPENDS — reads `current_modifier` from Offline B5 AIM state | If Offline runs |
| 14 | AutoExpand | `_aim14_expansion` | YES | N/A — always returns 1.0 | Informational only |
| 15 | OpenVol | `_aim15_volume` | YES | FUNCTIONAL — `opening_volume_ratio` from live stream + p3_d29 | All assets |
| 16 | HMM | `_aim16_hmm` | **NO** (dead) | Moved to Block 5 per DEC-06 | Handler is dead code |

**Summary:** 13 in dispatch. Of those: **7 FUNCTIONAL** (04, 06, 08, 09, 10, 11, 15), **3 PARTIAL** (01, 02, 12), **2 DEAD-ON-ARRIVAL** (03, 07), **1 DEPENDS** (13).

---

## Code Quality Audit (ln-624)

### CQ-01 — `_AIM_NAMES` Dict Recreated Per Call
**Severity:** LOW
**Location:** `shared/aim_compute.py:102-107`

`_AIM_NAMES` is a 16-entry dict literal defined inside `run_aim_aggregation()`. It is recreated on every call for every asset iteration. This is a module-level constant that should be defined once.

**Recommendation:** Move `_AIM_NAMES` to module level.
**Effort:** S

### CQ-02 — Private Attribute Access Across Module Boundary
**Severity:** MEDIUM
**Location:** `shared/aim_feature_loader.py:67-71`

`_load_vix_features()` accesses `vix_provider._vix_data`, `vix_provider._vxv_data`, and `vix_provider._ensure_loaded()` — all private members prefixed with `_`. This creates tight coupling to vix_provider internals. If the internal data structure changes, aim_feature_loader breaks silently.

**Recommendation:** Add public accessor methods to vix_provider (e.g., `get_vix_series(up_to_date)`) and use those.
**Effort:** M

### CQ-03 — `correlation_z` Uses Raw Pearson as Z-Score Proxy in Replay
**Severity:** MEDIUM
**Location:** `shared/aim_feature_loader.py:193`

Comment says: "Simplified: use the correlation value directly as proxy z-score since we don't have a long history of rolling correlations." Raw Pearson correlation is bounded to [-1, 1]. AIM-08 thresholds at `aim_compute.py:467` expect z-scored input where `corr_z > 1.5` triggers `CORR_STRESS`. **This tier is mathematically unreachable in replay**, making AIM-08 replay fidelity lower than live.

**Recommendation:** Compute rolling correlations over a trailing window and z-score the latest value against that window.
**Effort:** M

### CQ-04 — Inconsistent Import Paths for aim_compute
**Severity:** MEDIUM
**Location:** `orchestrator.py:201` vs `orchestrator.py:383`

Same file uses two different import paths for the same module:
- Phase A (l201): `from captain_online.blocks.b3_aim_aggregation import run_aim_aggregation` (via re-export shim)
- Phase B AIM-15 recompute (l383): `from shared.aim_compute import (_aim15_volume, MODIFIER_FLOOR, MODIFIER_CEILING, _clamp)`

Inconsistent and confusing. Also, Phase B imports private functions (`_aim15_volume`, `_clamp`) directly.

**Recommendation:** Standardise all imports to `shared.aim_compute`. If private functions are needed externally, make them public or provide a public wrapper.
**Effort:** S

### CQ-05 — ORDER BY / WHERE Column Mismatch in Volume Query
**Severity:** MEDIUM
**Location:** `shared/aim_feature_loader.py:276-279`

```sql
WHERE asset_id = %s AND session_date <= %s ORDER BY ts DESC LIMIT 30
```

WHERE filters by `session_date` (STRING) but ORDER BY uses `ts` (TIMESTAMP, designated). If data was backfilled with `ts` values that don't align with `session_date` chronologically, `LIMIT 30` could return an unexpected subset of rows.

**Recommendation:** Use `ORDER BY session_date DESC` to match the WHERE filter, or use `LATEST ON` if dedup is needed.
**Effort:** S

### CQ-06 — Duplicate z_score() Implementations
**Severity:** LOW
**Location:** `shared/aim_compute.py:50-67` vs `captain-online/captain_online/blocks/b1_features.py:357-369`

Two implementations: aim_compute uses pure Python; b1_features uses numpy. Both produce the same result. The aim_compute docstring explains: "Pure-Python implementation so shared/ stays dependency-light." **Intentional architectural decision — not a defect.** However, if one is updated without the other, they could diverge.

**Recommendation:** Add a comment in b1_features.z_score referencing the shared version. Consider a shared test that verifies both produce identical output.
**Effort:** S

### CQ-07 — Regime Probability Fallback Produces 50/50 for Most Assets
**Severity:** LOW (informational)
**Location:** `b2_regime_probability.py:150-154`

For C1-C3 assets with `regime_label == "REGIME_NEUTRAL"`, the function immediately returns `{HIGH_VOL: 0.5, LOW_VOL: 0.5}` without invoking any classifier. This means the regime classifier is effectively a no-op for these assets. Not a code quality issue — this is correct V1 behavior — but worth noting as a system-level gap.

### CQ-08 — Magic Numbers in AIM Thresholds (DOWNGRADED)
**Severity:** LOW
**Location:** Throughout `shared/aim_compute.py` (all AIM handlers)

Each AIM handler has hardcoded numeric thresholds (e.g., 1.5, 0.5, -1.0, 0.93, 0.85). These are **spec-driven constants** from DEC-01 and documented in each handler's docstring. Extracting them to a central config would aid tuning but is not required given the spec-locked nature.

**Code Quality Score: 7.0/10**
Issues: 4 MEDIUM (private access, correlation proxy, import paths, ORDER BY mismatch), 4 LOW (_AIM_NAMES per call, duplicate z_score, regime 50/50, threshold magic numbers)

---

## Dead Code Audit (ln-626)

### DC-01 — `_aim16_hmm()` Dead Function
**Severity:** MEDIUM
**Location:** `shared/aim_compute.py:637-649`

Function is defined but **not in the dispatch table** (l192-210). Comment at l208 says: "AIM-16 removed from B3 dispatch per DEC-06; session budget allocator now handled by `apply_hmm_session_allocation()` in Block 5." The function is never called — confirmed by grep (no caller references `_aim16_hmm` in any Python source).

**Recommendation:** Delete `_aim16_hmm()`. Git preserves history.
**Effort:** S

### DC-02 — QuantConnect Import Guards
**Severity:** LOW
**Location:** `b2_regime_probability.py:1-5`, `b3_aim_aggregation.py:1-5`

```python
try:
    from AlgorithmImports import *
except ImportError:
    pass
```

Legacy artifact from QuantConnect Lean environment. Never executes in Docker deployment. Present in both files.

**Recommendation:** Remove from both files.
**Effort:** S

### DC-03 — VRP Fallback Branch in `_compute_realised_vol()`
**Severity:** LOW
**Location:** `b2_regime_probability.py:132-139`

The VRP fallback block contains `pass` and always falls through to `return None`:
```python
if vrp is not None:
    # VRP = rv - iv, so rv = vrp + iv. We don't have iv separately...
    # Without iv, we cannot reconstruct rv exactly — return None
    pass
return None
```

The comment explains why the reconstruction is impossible, but the code block is a no-op.

**Recommendation:** Remove the if-block. Add a comment explaining why VRP cannot be used to reconstruct RV.
**Effort:** S

### DC-04 — Redundant Assignment in `run_regime_probability()`
**Severity:** LOW
**Location:** `b2_regime_probability.py:75` and `b2_regime_probability.py:83`

`regime_probs[asset_id] = probs` is set at l75 (inside `else` branch) and unconditionally at l83 (after the if/else). The l75 assignment is always overwritten by l83.

**Recommendation:** Remove l75.
**Effort:** S

### DC-05 — Dead Assignment in `_load_vix_features()`
**Severity:** LOW
**Location:** `shared/aim_feature_loader.py:67`

```python
vix_data = vix_provider._vix_data  # line 67 — DEAD
vix_provider._ensure_loaded()       # line 68
vix_data = vix_provider._vix_data   # line 69 — overwrites
```

The l67 assignment reads `_vix_data` before `_ensure_loaded()` is called, then l69 re-reads it. The l67 result is never used.

**Recommendation:** Remove l67.
**Effort:** S

### DC-06 — b3_aim_aggregation.py Re-Export Shim
**Severity:** LOW (informational)
**Location:** `captain-online/captain_online/blocks/b3_aim_aggregation.py` (entire file, 28 lines)

The entire module is a re-export shim. Two callers remain:
- `orchestrator.py:201` (Phase A — live pipeline)
- `scripts/replay_full_pipeline.py:150` (legacy replay script)

All tests and the replay engine already import directly from `shared.aim_compute`. This shim adds an indirection layer.

**Recommendation:** Update remaining callers to import from `shared.aim_compute` directly, then delete this file.
**Effort:** S

**Dead Code Score: 8.0/10**
Issues: 1 MEDIUM (_aim16_hmm dead function), 5 LOW (QC guards ×2, VRP pass-block, redundant assignment, dead assignment, re-export shim)

---

## Feature Computation Map

Features computed by B1 and consumed by B2/B3:

| Feature Key | AIM Consumer | Source (Live) | Source (Replay) | Status |
|-------------|-------------|---------------|-----------------|--------|
| `vrp_overnight_z` | AIM-01 | p3_d31 + z_score | p3_d31 + z_score | ES only |
| `day_of_week` | AIM-01 Monday adj | `datetime.weekday()` | `date.weekday()` | OK |
| `pcr_z` | AIM-02 | `_get_trailing_pcr()` **STUB** | Not loaded | Dead |
| `skew_z` | AIM-02 | p3_d32 + z_score | p3_d32 + z_score | ES only |
| `gex` | AIM-03 | `_get_option_chain()` **STUB** | Not loaded | Dead |
| `ivts` | AIM-04 | vix_provider VIX/VXV | vix_provider VIX/VXV | OK |
| `overnight_return_z` | AIM-04 overlay | OHLCV + z_score | p3_d30 + z_score | OK |
| `is_eia_wednesday` | AIM-04 CL overlay | weekday check | weekday check | OK (CL only) |
| `event_proximity` | AIM-06 | economic_calendar JSON | Not loaded | Replay gap |
| `events_today` | AIM-06 | economic_calendar JSON | Not loaded | Replay gap |
| `cot_smi` | AIM-07 | `_load_latest_cot()` **STUB** | Not loaded | Dead |
| `cot_speculator_z` | AIM-07 | `_load_cot_history()` **STUB** | Not loaded | Dead |
| `correlation_z` | AIM-08 | rolling_20d + z_score | raw Pearson (proxy) | Live OK / Replay degraded |
| `cross_momentum` | AIM-09 | 5d vs 20d return alignment | 5d vs 20d return alignment | OK |
| `is_opex_window` | AIM-10 | 3rd Friday ±3 cal days | 3rd Friday ±3 cal days | OK |
| `vix_z` | AIM-11, AIM-12 | vix_provider + z_score | vix_provider + z_score | OK |
| `vix_daily_change_z` | AIM-11 | vix_provider + z_score | vix_provider + z_score | OK |
| `cl_basis` | AIM-11 CL overlay | `_get_cl_spot/futures()` **STUB** | Not loaded | Dead |
| `spread_z` | AIM-12 | p3_spread_history + z_score | Not loaded | Undoc table |
| `vol_z` | AIM-12 | p3_d33 + z_score | p3_d33 + z_score | OK |
| `opening_volume_ratio` | AIM-15 | live stream + p3_d29 | p3_d29 | OK |

---

## Side-Effect Cascade Analysis (ln-624 Rule 10)

| Module | Sinks (0-1) | Shallow Pipes (2) | Deep Pipes (3+) | Sink Ratio |
|--------|-------------|-------------------|-----------------|------------|
| b2_regime_probability.py | 4 (all pure functions) | 0 | 0 | 100% |
| b3_aim_aggregation.py | 1 (re-export only) | 0 | 0 | 100% |
| shared/aim_compute.py | 16 (all pure functions) | 0 | 0 | 100% |
| shared/aim_feature_loader.py | 1 (load_replay_features) | 7 (internal loaders) | 0 | 12.5% |

All B2/B3 computation is pure-functional (no DB writes, no Redis pub/sub, no external side effects). The aim_feature_loader reads from QuestDB and vix_provider but writes nothing. **No cascade depth concerns.**

---

## Cross-Cutting Observations

### XC-01 — 5 of 13 Active AIMs Cannot Fire in Production
AIM-03 (GEX) and AIM-07 (COT) are **dead-on-arrival** — their feature inputs depend on stubs in b1_features.py that always return None. AIM-01 VRP and AIM-02 Skew are ES-only. AIM-12 spread_z relies on an undocumented table. This means **only 7-8 AIMs out of 13 active contribute to the combined modifier** for most assets. The DMA weighted average is computed over a sparser set than the spec intends.

### XC-02 — Replay / Live Feature Parity Gap
Replay cannot reproduce AIM-06 (no calendar feed), AIM-08 (degraded — raw correlation, not z-scored), and inherits all the B1 stub gaps. Replay A/B validation results will diverge from live for these AIMs, limiting replay's usefulness as a validation tool.

### XC-03 — Lazy Imports Create Hidden Coupling
B2's `_compute_realised_vol()` (l125) and `_classifier_regime()` (l157) import private functions from B1 at runtime. This cross-block coupling means B2 cannot be tested in isolation without B1's module being importable. The functions imported (`_get_daily_returns`, `extract_classifier_features`) are prefixed with `_` indicating they were intended as internal to B1.

---

## Session 2 Summary

- **Files audited:** 4
- **Key findings:** 14
  - MEDIUM (5): private vix_provider access in feature loader; correlation_z uses raw Pearson (AIM-08 CORR_STRESS unreachable in replay); inconsistent import paths for aim_compute in orchestrator; ORDER BY/WHERE column mismatch in volume query; `_aim16_hmm()` dead function still in codebase
  - LOW (9): `_AIM_NAMES` per-call recreation; duplicate z_score implementations; regime 50/50 default for most assets; threshold magic numbers (spec-driven); QuantConnect import guards ×2; VRP fallback pass-block; redundant assignment; dead vix_data assignment
- **Stub count:** 0 new stubs in these files (all stubs are upstream in b1_features, catalogued in Session 1)
- **Replay data gaps:** 7 features not loadable in replay (pcr_z, gex, cot_smi, cot_speculator_z, event_proximity, events_today, spread_z, cl_basis)
- **AIM inventory:**
  - AIM-01 VRP → PARTIAL (ES only)
  - AIM-02 Skew → PARTIAL (ES only, pcr_z dead)
  - AIM-03 GEX → DEAD-ON-ARRIVAL (upstream stub)
  - AIM-04 IVTS → FUNCTIONAL
  - AIM-05 → DEFERRED (by spec)
  - AIM-06 EconCal → FUNCTIONAL (live) / GAP (replay)
  - AIM-07 COT → DEAD-ON-ARRIVAL (upstream stub)
  - AIM-08 CrossCorr → FUNCTIONAL (live) / DEGRADED (replay)
  - AIM-09 CrossMom → FUNCTIONAL
  - AIM-10 Calendar → FUNCTIONAL
  - AIM-11 RegimeWarn → FUNCTIONAL
  - AIM-12 DynCosts → PARTIAL (spread_z from undocumented table)
  - AIM-13 Sensitivity → DEPENDS (Offline B5)
  - AIM-14 AutoExpand → ALWAYS 1.0
  - AIM-15 OpenVol → FUNCTIONAL
  - AIM-16 HMM → DEAD CODE (removed from dispatch, handler still in file)
- **Cross-service deps:**
  - QuestDB tables read (replay): p3_d01, p3_d02, p3_d29, p3_d30, p3_d31, p3_d32, p3_d33
  - QuestDB tables read (live, via B1): p3_d00, p3_d01, p3_d02, p3_d05, p3_d12, p3_d29, p3_d30, p3_d31, p3_d32, p3_d33, p3_spread_history
  - Shared modules: `aim_compute`, `aim_feature_loader`, `questdb_client`, `vix_provider`
  - Kelly sizing input contract: `combined_modifier` (float ∈ [0.5, 1.5]) → multiplied into Kelly fraction in B4

---

## Part 3: Kelly to Signal Output

**Auditor:** Claude Opus 4.6
**Date:** 2026-04-08
**Skills applied:** ln-623 Code Principles Auditor, ln-627 Observability Auditor
**Scope:** Kelly sizing (12-step pipeline), trade selection, quality gate, circuit breaker (7 layers), signal output, position monitoring, shadow monitoring, concentration, capacity (Blocks 4–9).

---

## File Inventory

### File: captain-online/captain_online/blocks/b4_kelly_sizing.py

- **Purpose:** Computes optimal contract sizing per asset per account — 12-step Kelly pipeline with blended regime weights, shrinkage, AIM modifier, TSM constraints, and V3 fee integration.
- **Key functions/classes:**
  - `run_kelly_sizing()` — l40: main entry, 12-step pipeline for one user
  - `_get_kelly_for_regime()` — l271: Kelly fraction lookup with session fallback
  - `_get_shrinkage()` — l284: shrinkage factor lookup (first-match, any session)
  - `_get_ewma_for_regime()` — l292: EWMA state lookup with session fallback
  - `_apply_risk_goal()` — l305: risk-goal-specific Kelly adjustment (PASS_EVAL/PRESERVE/GROW)
  - `_compute_tsm_cap()` — l320: TSM constraint cap (MDD budget, MLL, scaling plan)
  - `_compute_topstep_daily_cap()` — l385: V3 Topstep daily cap (E = e × A)
  - `_compute_scaling_cap()` — l406: V3 scaling cap (XFA micro-equivalent)
  - `_get_expected_fee()` — l422: V3 fee per contract from fee_schedule
  - `_load_system_param()` — l443: D17 system parameter reader
  - `_parse_json()` — l461: safe JSON deserializer
- **Session/schedule refs:** `session_id` parameter passed through for Kelly/EWMA lookup.
- **QuestDB:** p3_d17_system_monitor_state (read, l448-458, via `_load_system_param`).
- **Redis:** captain:alerts (publish, l80, silo drawdown CRITICAL alert).
- **Stubs/TODOs:** None.
- **Notable:**
  - **Lazy import** of `shared.redis_client` inside the silo-drawdown block (l78) — only imported when needed (cold-start path). Acceptable pattern.
  - **Lazy import** of `b1_features.get_return_bounds, compute_robust_kelly` (l134) inside the robust Kelly fallback path. Creates coupling to B1 from B4.
  - `_get_shrinkage()` uses first-match across all sessions (l286-288) — no session_id filtering. Could return wrong shrinkage if multiple sessions have different shrinkage values.
  - V3 4-way min (l203): `min(raw_contracts, tsm_cap, topstep_daily_cap, scaling_cap)` — clean implementation matching spec.

---

### File: captain-online/captain_online/blocks/b5_trade_selection.py

- **Purpose:** Universe-level trade selection — ranks assets by expected edge × contracts, applies correlation filter and max-position limit, plus V3 HMM session-partitioned budget allocation.
- **Key functions/classes:**
  - `run_trade_selection()` — l29: main entry, edge scoring + correlation filter + position limit
  - `apply_hmm_session_allocation()` — l135: V3 HMM session budget (cold start 3-phase ramp)
  - `_get_ewma_for_regime()` — l192: EWMA lookup (duplicate of B4)
  - `_load_correlation_matrix()` — l203: loads D07 correlation matrix
  - `_get_correlation()` — l216: pairwise correlation lookup
  - `_load_hmm_opportunity_state()` — l225: loads D26 HMM state
  - `_parse_json()` — l243: safe JSON deserializer (duplicate)
- **Session/schedule refs:** `session_id` used for EWMA lookup and HMM session mapping ({1:"NY", 2:"LON", 3:"APAC"}).
- **QuestDB:** p3_d07_correlation_model_states (read, l207), p3_d26_hmm_opportunity_state (read, l228).
- **Redis:** None.
- **Stubs/TODOs:** None.
- **Notable:**
  - `apply_hmm_session_allocation()` has `import math` at l175 inside function body — should be at module top.
  - Correlation filter halves contracts for the lower-scoring correlated asset (l84-89) — blunt instrument, no graduated response.
  - HMM cold-start ramp: <20 obs → equal 1/3, 20-59 → blended 50/50, 60+ → full HMM. Floor at 0.05 per session (l171).

---

### File: captain-online/captain_online/blocks/b5b_quality_gate.py

- **Purpose:** Filters selected trades by minimum quality threshold — quality_score = edge × modifier × data_maturity. Below floor → AVAILABLE_NOT_RECOMMENDED. Between floor and ceiling → graduated quality_multiplier.
- **Key functions/classes:**
  - `run_quality_gate()` — l28: main entry, quality scoring and gate logic
  - `_get_trade_count()` — l105: trade count from P3-D03
  - `_load_system_param()` — l116: D17 parameter reader (duplicate)
  - `_log_quality_results()` — l134: writes session log to P3-D17
- **Session/schedule refs:** `session_id` used as log key.
- **QuestDB:** p3_d03_trade_outcome_log (read, l109, trade count), p3_d17_system_monitor_state (read l119 + write l152).
- **Redis:** None.
- **Stubs/TODOs:** None.
- **Notable:**
  - Cold-start data_maturity floor at 0.5 (l54) — prevents quality gate from blocking all trades on fresh system. Full maturity at 50 trades.
  - `_load_system_param` returns `float()` always (l129) — differs from B4's `type(default)()` cast. B4 can return int; B5B always returns float.

---

### File: captain-online/captain_online/blocks/b5c_circuit_breaker.py

- **Purpose:** 7-layer circuit breaker screen (L0–L6) per Topstep_Optimisation_Functions.md. Non-Topstep accounts bypass entirely.
- **Key functions/classes:**
  - `run_circuit_breaker_screen()` — l44: main entry, iterates accounts × assets through all layers
  - `_check_all_layers()` — l165: sequential L0→L6 evaluation, returns first block reason
  - `_layer0_scaling_cap()` — l232: XFA simultaneous open position limit
  - `_layer1_preemptive_halt()` — l259: abs(L_t) + rho_j >= c·e·A
  - `_layer2_budget()` — l292: n_t >= N (total trades today)
  - `_layer3_basket_expectancy()` — l324: mu_b = r_bar + beta_b·L_b ≤ 0 → BLOCKED
  - `_layer4_correlation_sharpe()` — l371: S = mu_b / (σ·√(1+2·n_t·ρ̄)) ≤ λ → BLOCKED
  - `_layer5_session_halt()` — l436: VIX > 50 or DATA_HOLD ≥ 3
  - `_layer6_manual_override()` — l452: admin halt check (stub)
  - `_load_cb_params()` — l464: D25 reader with model_m filter
  - `_load_intraday_state()` — l507: D23 reader
  - `_resolve_fee()` — l532: per-account fee resolution (duplicate logic of B4/B7)
  - `_get_current_vix()` — l554: VIX from shared.vix_provider
  - `_get_data_hold_count()` — l563: count DATA_HOLD assets from D00
  - `_check_manual_halt()` — l574: **stub** — always returns False
  - `_parse_json()` — l579: safe JSON deserializer (duplicate)
- **Session/schedule refs:** `session_id` passed to L5 (not currently used by L5 implementation).
- **QuestDB:** p3_d25_circuit_breaker_params (read, l472-487), p3_d23_circuit_breaker_intraday (read, l510-514), p3_d00_asset_universe (read, l567).
- **Redis:** None direct (L5 uses vix_provider).
- **Stubs/TODOs:**
  - `_check_manual_halt()` l574-576: always returns `False` — L6 manual override is non-functional.
- **Notable:**
  - Cold start safety: L3/L4 skip when `n_obs == 0` (l348, l397). Significance gate: beta_b zeroed when p > 0.05 or n < 100 (l352, l401).
  - `_load_cb_params()` uses ORDER BY + manual seen-set dedup (l489-493) instead of LATEST ON — same pattern as other blocks, but could miss multi-model params.
  - `_layer2_budget` uses MDD from `max_drawdown_limit` OR `max_daily_drawdown` OR hardcoded 4500.0 (l304) — the 4500 fallback is a magic number (TopstepX 150K combine MDD).

---

### File: captain-online/captain_online/blocks/b6_signal_output.py

- **Purpose:** Generates fully specified trading signals per user; publishes to Redis `stream:signals` for Command routing. Includes below-threshold signals for transparency.
- **Key functions/classes:**
  - `run_signal_output()` — l32: main entry, builds signal dicts and publishes
  - `_determine_direction()` — l166: OR breakout direction from features, fallback to strategy default
  - `_compute_tp()` — l181: TP from tp_multiple × or_range
  - `_compute_sl()` — l194: SL from sl_multiple × or_range
  - `_build_per_account()` — l207: per-account trade breakdown for GUI
  - `_classify_confidence()` — l247: HIGH/MEDIUM/LOW confidence tier
  - `_publish_signals()` — l260: Redis stream publisher
  - `_log_signal_output()` — l275: session log to D17
  - `_get_daily_pnl()` — l293: today's cumulative P&L from D03
  - `_get_ewma_for_regime()` — l310: EWMA lookup (3rd duplicate)
  - `_load_system_param()` — l321: D17 reader (duplicate)
  - `_parse_json()` — l338: safe JSON deserializer (duplicate)
- **Session/schedule refs:** `session_id` included in signal payload and log key.
- **QuestDB:** p3_d03_trade_outcome_log (read, l299, daily PnL), p3_d17_system_monitor_state (read l323 + write l285).
- **Redis:** stream:signals (publish, l263, via `publish_to_stream`).
- **Stubs/TODOs:** None.
- **Notable:**
  - Redundant `from shared.questdb_client import get_cursor` at l297 inside `_get_daily_pnl()` — already imported at module level (l28).
  - Signal includes rich context for GUI: aim_breakdown, regime_state, quality_score, confidence_tier, user_daily_pnl, per-account breakdown with remaining_mdd/mll.
  - `_classify_confidence()` logic: edge > ceiling AND modifier > 1.0 → HIGH; edge > floor → MEDIUM; else LOW. The AND condition means even high-edge signals get MEDIUM if AIM modifier ≤ 1.0.

---

### File: captain-online/captain_online/blocks/b7_position_monitor.py

- **Purpose:** Intraday position monitoring (10s poll) — P&L tracking, TP/SL proximity alerts, VIX spike, regime shift, time exit, position resolution → D03 trade outcome → Redis feedback loop to Offline.
- **Key functions/classes:**
  - `monitor_positions()` — l46: single monitoring pass for all open positions
  - `resolve_position()` — l127: position close — D03 write, capital update, D23 CB state, Redis publish
  - `resolve_commission()` — l198: V3 commission resolution (API → fee_schedule → cpc → notify)
  - `get_expected_fee()` — l232: expected fee per contract (exported, duplicate of B4 `_get_expected_fee`)
  - `_write_trade_outcome()` — l252: D03 INSERT
  - `_update_capital_silo()` — l279: D16 read-then-write (not atomic)
  - `_update_intraday_cb_state()` — l299: D23 read-then-write (not atomic)
  - `_publish_trade_outcome()` — l336: CRITICAL Redis stream publish for Offline
  - `_notify()` — l367: Redis alerts publisher
  - `_get_live_price()` — l387: quote_cache + REST fallback
  - `_check_vix_spike()` — l419: **stub** (pass)
  - `_regime_shift_detected()` — l424: **stub** (returns False)
  - `_parse_close_time()` — l429: trading hours parser
  - `_parse_json()` — l442: safe JSON deserializer (duplicate)
- **Session/schedule refs:** Reads session from position dict.
- **QuestDB:** p3_d03_trade_outcome_log (write, l263), p3_d16_user_capital_silos (read+write, l283-296), p3_d23_circuit_breaker_intraday (read+write, l308-333).
- **Redis:** stream:trade_outcomes (publish, l339), captain:alerts (publish, l378).
- **Stubs/TODOs:**
  - `_check_vix_spike()` l419-422: stub (pass) — TODO in comment.
  - `_regime_shift_detected()` l424-427: stub (returns False) — TODO in comment.
  - `_get_api_commission()` l413-414: stub (returns None) — API fill commission not yet wired.
- **Notable:**
  - **Non-atomic read-then-write** for D16 capital silo (l283-296) and D23 intraday CB state (l308-333). QuestDB doesn't support UPDATE; new rows are inserted. Concurrent position resolutions could race.
  - **CRITICAL FEEDBACK LOOP**: `resolve_position()` → D03 → Redis stream → Offline learning. If Redis publish fails (l360), trade outcome is logged to D03 but Offline never learns. Error is logged but no retry/dead-letter.
  - `_get_live_price()` has REST fallback (l397-410) — 1-minute bars from TopstepX API. Good resilience pattern.
  - `_update_capital_silo()` reads current total_capital and adds net_pnl (l290) — no check for stale reads or concurrent updates.

---

### File: captain-online/captain_online/blocks/b7_shadow_monitor.py

- **Purpose:** Theoretical position tracker for multi-instance parity mode — monitors ALL signals as shadow positions, resolves theoretical TP/SL outcomes for parity-skipped signals, publishes to `stream:signal_outcomes` for Offline Category A learning.
- **Key functions/classes:**
  - `register_shadow_position()` — l39: creates shadow position dict from B6 signal
  - `monitor_shadow_positions()` — l66: single monitoring pass, checks live prices vs TP/SL
  - `_resolve_shadow()` — l122: resolves shadow, publishes theoretical outcome
  - `_infer_entry()` — l175: infers entry price from features/per_account/TP-SL midpoint
  - `_get_shadow_contracts()` — l204: extracts contract count from signal
  - `_get_point_value()` — l215: **hardcoded POINT_VALUES dict** (l217-221)
  - `_get_live_price()` — l225: quote_cache lookup (no REST fallback, unlike B7)
- **Session/schedule refs:** `session_id` stored in shadow for outcome publishing.
- **QuestDB:** None.
- **Redis:** stream:signal_outcomes (publish, l164, via `publish_to_stream`).
- **Stubs/TODOs:** None.
- **Notable:**
  - **Hardcoded POINT_VALUES** (l217-221) duplicates data that should come from D00 asset_universe or shared/constants.py. If point values change, this dict must be manually updated.
  - Shadow max age: 8 hours (l36). Expired shadows are silently dropped — no outcome published for time-expired shadows (unlike real B7 which has TIME_EXIT).
  - `_get_live_price()` has **no REST fallback** (l225-232), unlike real B7's `_get_live_price()`. Shadow could fail to resolve if WebSocket drops.
  - `_infer_entry()` computes entry from TP/SL as last resort using 1/3 from SL toward TP (l197) — assumes default tp_multiple=0.70, sl_multiple=0.35 ratio. Fragile if strategy changes multiples.
  - No commission in shadow outcomes (`commission: 0`, l151) — correct per spec (Category A learning uses gross P&L).

---

### File: captain-online/captain_online/blocks/b8_concentration_monitor.py

- **Purpose:** Network-level concentration monitor — runs once per session after all user loops. Detects when too many users trade the same asset/direction. Monitoring and alerting only — does NOT modify signals. Skips in V1 (single user).
- **Key functions/classes:**
  - `run_concentration_monitor()` — l30: main entry, aggregates exposure, checks thresholds
  - `_notify_admins()` — l116: Redis CRITICAL alert with action_required flag
  - `_log_concentration_event()` — l131: D17 write
  - `_get_recent_alert_count()` — l142: 30-day alert count from D17
  - `_log_capacity_recommendation()` — l155: D17 recommendation write
  - `_load_param()` — l167: D17 parameter reader (duplicate, different name)
- **Session/schedule refs:** `session_id` in alert payloads.
- **QuestDB:** p3_d17_system_monitor_state (read l170 + write l133, l159).
- **Redis:** captain:alerts (publish, l121).
- **Stubs/TODOs:** None.
- **Notable:**
  - V1 single-user early return (l39) — entire block is effectively a no-op in current deployment.
  - Proactive tracking: fires recommendation if >10 concentration alerts in 30 days (l99-106).
  - Uses `dateadd('d', -%s, now())` in QuestDB query (l149) — QuestDB-specific syntax.

---

### File: captain-online/captain_online/blocks/b9_capacity_evaluation.py

- **Purpose:** Session-end capacity evaluation — tracks signal supply vs. trader demand, identifies constraints (signal shortage, asset concentration, quality rate, user capacity, strategy/asset-class homogeneity), generates recommendations for System Overview GUI.
- **Key functions/classes:**
  - `run_capacity_evaluation()` — l26: main entry, computes metrics and constraints
  - `_load_session_log()` — l160: reads session log from D17
  - `_count_assets_producing_signals()` — l180: counts assets passing quality gate
  - `_load_correlation_matrix()` — l190: loads D07 (duplicate of B5)
  - `_find_high_corr_pairs()` — l205: pairwise correlation filter
  - `_get_strategy_models()` — l223: unique (m,k) pairs from D00
  - `_count_accounts()` — l248: aggregates accounts across users
  - `_load_param()` — l261: D17 reader (duplicate, matches B8 variant)
  - `_save_capacity_state()` — l277: writes capacity state to D17
- **Session/schedule refs:** `session_id` used as save key.
- **QuestDB:** p3_d17_system_monitor_state (read l163 + write l280), p3_d07_correlation_model_states (read, l193), p3_d00_asset_universe (read, l110, l227).
- **Redis:** None.
- **Stubs/TODOs:** None.
- **Notable:**
  - **N+1 query** for asset class check (l108-117): queries D00 per-asset inside a loop instead of a single batch query. Only 10 assets currently, but scales poorly.
  - `_load_session_log()` fetches ALL session_log entries then filters in Python (l172-176) instead of filtering in SQL with session_id parameter. Wastes bandwidth as history grows.
  - `_load_param()` returns `json.loads()` (l271) while B5B/B6 versions return `float()` — inconsistent return type contract.
  - Constraint for ASSET_CLASS_HOMOGENEITY uses `"detail"` key (l124) while others use `"message"` — inconsistent schema.

---

## Cross-Cutting Analysis

### Kelly Pipeline: 12-Step Inventory

| Step | Description | Implementation | Status |
|------|-------------|----------------|--------|
| 0 | Silo drawdown check (>30%) | `run_kelly_sizing` l66-103 | IMPLEMENTED |
| 1 | Blended Kelly across regimes (Paper 219) | l117-123 | IMPLEMENTED |
| 2 | Parameter uncertainty shrinkage (Paper 217) | l126-127 | IMPLEMENTED |
| 3 | Robust Kelly fallback (Paper 218) | l130-138 | IMPLEMENTED |
| 4 | AIM modifier application | l141-142 | IMPLEMENTED |
| 5 | User-level Kelly ceiling | l145 | IMPLEMENTED |
| 6 | Per-account sizing with risk_goal | l147-234 | IMPLEMENTED |
| 6a | Risk-goal adjustment | l172 via `_apply_risk_goal` | IMPLEMENTED |
| 6b | TSM hard constraints (MDD, MLL, margin, contracts, scaling) | l174-182 | IMPLEMENTED |
| 6c | V3 Fee integration (risk_per_contract + expected_fee) | l192-194 | IMPLEMENTED |
| 6d | V3 4-way min (kelly, tsm_cap, topstep_daily_cap, scaling_cap) | l201-204 | IMPLEMENTED |
| 7 | User-level portfolio risk cap | l237-248 | IMPLEMENTED |
| 8 | Level 2 sizing override | l250-257 | IMPLEMENTED |

**Verdict: 12/12 steps implemented.** All Kelly layers functional.

### Circuit Breaker: 7-Layer Inventory

| Layer | Description | Trigger | Recovery | Status |
|-------|-------------|---------|----------|--------|
| L0 | Scaling cap (XFA only) | open + proposed > tier_micros | N/A (capacity-based) | IMPLEMENTED |
| L1 | Preemptive hard halt | abs(L_t) + ρ_j ≥ c·e·A | Next day (L_t resets) | IMPLEMENTED |
| L2 | Budget exhausted | n_t ≥ N = floor((e·A)/(MDD·p+φ)) | Next day (n_t resets) | IMPLEMENTED |
| L3 | Basket expectancy | μ_b = r̄ + β_b·L_b ≤ 0 | L_b recovers (wins improve expectancy) | IMPLEMENTED (cold-start safe) |
| L4 | Correlation Sharpe | S = μ_b/(σ·√(1+2·n_t·ρ̄)) ≤ λ | S rises as mu_b improves | IMPLEMENTED (cold-start safe) |
| L5 | Session halt (VIX/DATA_HOLD) | VIX > 50 or DATA_HOLD ≥ 3 | VIX drops / DATA_HOLD resolves | IMPLEMENTED |
| L6 | Manual override (ADMIN halt) | `_check_manual_halt()` | Admin clears halt | **STUB** (always False) |

**Verdict: 6/7 layers implemented, L6 is a stub.** Cold start: L3/L4 skip when n_obs=0 and zero beta_b when p>0.05 or n<100. Correct per spec ("beta_b=0, layers 3-4 disabled").

### Signal Contract (Redis `stream:signals` Payload)

```json
{
  "user_id": "string",
  "session_id": "int",
  "timestamp": "ISO8601",
  "signals": [{
    "signal_id": "SIG-XXXXXXXXXXXX",
    "user_id": "string",
    "asset": "string",
    "session": "int",
    "timestamp": "ISO8601",
    "direction": "int (1=LONG, -1=SHORT)",
    "tp_level": "float",
    "sl_level": "float",
    "sl_method": "string",
    "entry_conditions": "dict",
    "per_account": {
      "<account_id>": {
        "contracts": "int",
        "recommendation": "TRADE|SKIP|BLOCKED|REDUCED_TO_ZERO",
        "skip_reason": "string|null",
        "account_name": "string",
        "category": "string",
        "risk_goal": "string",
        "remaining_mdd": "float|null",
        "remaining_mll": "float|null",
        "pass_probability": "float|null",
        "risk_budget_pct": "float|null",
        "api_validated": "bool"
      }
    },
    "aim_breakdown": "dict",
    "combined_modifier": "float",
    "regime_state": "string",
    "regime_probs": "dict",
    "expected_edge": "float",
    "win_rate": "float",
    "payoff_ratio": "float",
    "user_total_capital": "float",
    "user_daily_pnl": "float",
    "quality_score": "float",
    "quality_multiplier": "float",
    "data_maturity": "float",
    "confidence_tier": "HIGH|MEDIUM|LOW"
  }],
  "below_threshold": [{
    "asset": "string",
    "quality_score": "float",
    "expected_edge": "float",
    "reason": "string"
  }]
}
```

### Trade Outcome Contract (Redis `stream:trade_outcomes`)

```json
{
  "trade_id": "TRD-XXXXXXXXXXXX",
  "user_id": "string",
  "asset": "string",
  "direction": "int",
  "entry_price": "float",
  "exit_price": "float",
  "contracts": "int",
  "pnl": "float (net)",
  "commission": "float",
  "slippage": "float|null",
  "outcome": "TP_HIT|SL_HIT|TIME_EXIT",
  "regime_at_entry": "string",
  "aim_modifier_at_entry": "float",
  "aim_breakdown_at_entry": "dict",
  "session": "int",
  "account": "string",
  "timestamp": "ISO8601"
}
```

### Shadow Outcome Contract (Redis `stream:signal_outcomes`)

Same schema as trade outcome with additions:
- `theoretical: true` (Category B blocks must ignore)
- `signal_id: "SHADOW-XXXXXXXXXXXX"` prefix
- `commission: 0` (no fee for theoretical trades)

### Position Monitoring: TP/SL Detection

- **Poll interval:** 10 seconds (POLL_INTERVAL_SECONDS, l42)
- **Live price source:** quote_cache (sub-second) → REST bars fallback (1-minute)
- **TP hit:** direction=1 → price ≥ TP; direction=-1 → price ≤ TP
- **SL hit:** direction=1 → price ≤ SL; direction=-1 → price ≥ SL
- **Time exit:** Non-overnight accounts → forced close 5 min before market close
- **Resolution chain:** resolve_position → D03 write → D16 capital update → D23 CB state → Redis publish
- **Alerts:** TP proximity <10% → HIGH; SL proximity <10% → CRITICAL

### Shadow Monitoring: Theoretical Outcomes

- **Tracks:** ALL signals from B6, regardless of TAKEN/SKIPPED/PARITY_SKIPPED status
- **Resolution:** Same TP/SL logic as real B7 (price comparison against levels)
- **Expiry:** 8 hours (SHADOW_MAX_AGE_SECONDS) — expired shadows silently dropped, no TIME_EXIT equivalent
- **Output:** stream:signal_outcomes → Offline Category A learning (DMA, EWMA, Kelly, BOCPD)
- **Exclusion:** Category B (CB params, TSM) ignores theoretical outcomes via `theoretical: true` flag

---

## Findings

### MEDIUM Severity

**M1. DRY: `_parse_json()` duplicated 6× across Online blocks**
- **Files:** b4_kelly_sizing.py:461, b5_trade_selection.py:243, b5b_quality_gate.py (missing — uses json.loads inline), b5c_circuit_breaker.py:579, b6_signal_output.py:338, b7_position_monitor.py:442, b1_data_ingestion.py:679
- **Detail:** Identical 8-line function copied into 6 separate files. Should be in shared/ or a block utility module.
- **Effort:** S
- **pattern_id:** dry_1.1
- **pattern_signature:** util_parse_json

**M2. DRY: `_get_ewma_for_regime()` duplicated 3× across B4/B5/B6**
- **Files:** b4_kelly_sizing.py:292, b5_trade_selection.py:192, b6_signal_output.py:310
- **Detail:** Identical 9-line function (tuple-key lookup with session fallback) copied into 3 files. Should be a shared helper.
- **Effort:** S
- **pattern_id:** dry_1.1
- **pattern_signature:** lookup_ewma_for_regime

**M3. DRY: `_load_system_param()` / `_load_param()` duplicated 6× with variant signatures**
- **Files:** b4_kelly_sizing.py:443 (type(default) cast), b5b_quality_gate.py:116 (float cast), b6_signal_output.py:321 (float cast), b1_data_ingestion.py:330 (default=None), b8_concentration_monitor.py:167 (float cast), b9_capacity_evaluation.py:261 (json.loads)
- **Detail:** Same D17 query pattern with 3 different return-type strategies. B9's version returns json.loads while others return float — inconsistent API contract. Should be a single shared function with explicit type parameter.
- **Effort:** M
- **pattern_id:** dry_1.4
- **pattern_signature:** loader_system_param_d17

**M4. DRY: Fee resolution duplicated 3× across B4/B5C/B7**
- **Files:** b4_kelly_sizing.py:422 (`_get_expected_fee`), b5c_circuit_breaker.py:532 (`_resolve_fee`), b7_position_monitor.py:232 (`get_expected_fee`)
- **Detail:** Three implementations of fee_schedule → commission_per_contract fallback chain. Slightly different signatures but identical core logic. B7's `get_expected_fee()` is public; B4's is private. Should be consolidated in shared/.
- **Effort:** M
- **pattern_id:** dry_1.4
- **pattern_signature:** fee_resolution_schedule

**M5. DRY: `_load_correlation_matrix()` duplicated in B5 and B9**
- **Files:** b5_trade_selection.py:203, b9_capacity_evaluation.py:190
- **Detail:** Identical function (D07 query + JSON parse). Should be shared.
- **Effort:** S
- **pattern_id:** dry_1.5
- **pattern_signature:** loader_correlation_matrix_d07

**M6. Non-atomic read-then-write for D16 and D23 in B7**
- **Files:** b7_position_monitor.py:279-296 (D16), b7_position_monitor.py:299-333 (D23)
- **Detail:** Both `_update_capital_silo()` and `_update_intraday_cb_state()` read current state then insert a new row. QuestDB has no UPDATE or transactions. If two positions resolve within the same 10s poll cycle, the second read may see stale data, causing capital/CB state drift.
- **Risk:** LOW in V1 (single user, few simultaneous positions). MEDIUM if scaled.
- **Effort:** M

**M7. Hardcoded POINT_VALUES dict in B7 shadow monitor**
- **File:** b7_shadow_monitor.py:217-221
- **Detail:** Point values hardcoded in a dict instead of reading from D00 asset_universe or shared/constants.py. If point values change (e.g., adding a new asset), shadow monitor calculates wrong P&L.
- **Effort:** S

**M8. No retry/dead-letter for critical Redis trade outcome publish**
- **File:** b7_position_monitor.py:336-360
- **Detail:** If `publish_to_stream(STREAM_TRADE_OUTCOMES, ...)` fails, trade outcome is logged to D03 but Offline never receives it. Error is logged but no retry mechanism or dead-letter queue. This breaks the critical feedback loop.
- **Effort:** M

### LOW Severity

**L1. QuantConnect import guards — dead in Docker**
- **Files:** All 9 files have `try: from AlgorithmImports import * except ImportError: pass` at lines 1-5.
- **Detail:** QuantConnect compatibility shim. Never executes in Docker. Harmless but noisy.
- **Effort:** S

**L2. Inline `import math` in `apply_hmm_session_allocation()`**
- **File:** b5_trade_selection.py:175
- **Detail:** `import math` inside function body. Should be at module top.
- **Effort:** S

**L3. Redundant import in `_get_daily_pnl()`**
- **File:** b6_signal_output.py:296-297
- **Detail:** `from shared.questdb_client import get_cursor` imported inside function — already imported at module level (l28).
- **Effort:** S

**L4. MDD fallback magic number 4500.0 in L2 budget**
- **File:** b5c_circuit_breaker.py:304
- **Detail:** `mdd = tsm.get("max_drawdown_limit") or tsm.get("max_daily_drawdown") or 4500.0` — the 4500 is the TopstepX 150K combine MDD. Should be a named constant or loaded from D17.
- **Effort:** S

**L5. Shadow monitor _get_live_price has no REST fallback**
- **File:** b7_shadow_monitor.py:225-232
- **Detail:** Unlike real B7's `_get_live_price()` which has REST fallback (b7_position_monitor.py:397-410), shadow version only reads from quote_cache. If WebSocket drops, shadows silently stop resolving.
- **Effort:** S

**L6. Expired shadows produce no outcome**
- **File:** b7_shadow_monitor.py:87-93
- **Detail:** Shadows that exceed SHADOW_MAX_AGE_SECONDS are silently dropped. Real B7 has TIME_EXIT for non-overnight accounts. Expired shadows should publish a TIMEOUT outcome so Offline Category A learning doesn't develop survivorship bias.
- **Effort:** M

**L7. B9 N+1 query for asset class check**
- **File:** b9_capacity_evaluation.py:108-117
- **Detail:** Queries D00 per-asset inside a loop (10 queries). Should be a single batch query. Acceptable at 10 assets but violates O(1)-per-block query discipline.
- **Effort:** S

**L8. B9 `_load_session_log()` fetches all then filters in Python**
- **File:** b9_capacity_evaluation.py:160-177
- **Detail:** Fetches ALL session_log entries from D17 then filters by session_id in Python (l172-176). As history grows, this wastes bandwidth. Should filter in SQL via param_key LIKE pattern or category + session_id.
- **Effort:** S

**L9. B9 constraint schema inconsistency — `detail` vs `message` key**
- **File:** b9_capacity_evaluation.py:124 vs l67/l76/l83
- **Detail:** ASSET_CLASS_HOMOGENEITY constraint uses `"detail"` key while all other constraints use `"message"`. GUI consumer must handle both.
- **Effort:** S

**L10. B7 stubs: VIX spike detection and regime shift detection**
- **Files:** b7_position_monitor.py:419-422 (`_check_vix_spike`), b7_position_monitor.py:424-427 (`_regime_shift_detected`)
- **Detail:** Both are TODO stubs. VIX spike detection is partially covered by B5C L5 (pre-trade), but no mid-trade VIX monitoring. Regime shift detection during open position is absent.
- **Effort:** M (each)

---

## Observability Assessment

### Structured Logging

| File | Logger | Levels Used | Assessment |
|------|--------|-------------|------------|
| b4_kelly_sizing.py | `logging.getLogger(__name__)` | INFO, WARNING, ERROR | Good — logs all sizing decisions with numeric detail |
| b5_trade_selection.py | `logging.getLogger(__name__)` | INFO | Minimal — only final count logged |
| b5b_quality_gate.py | `logging.getLogger(__name__)` | INFO | Good — logs per-asset gate failures |
| b5c_circuit_breaker.py | `logging.getLogger(__name__)` | INFO | Good — logs each CB block with layer detail |
| b6_signal_output.py | `logging.getLogger(__name__)` | INFO, WARNING, DEBUG, ERROR | Best — signal count, per-asset warnings, debug publish |
| b7_position_monitor.py | `logging.getLogger(__name__)` | INFO, WARNING, ERROR | Good — logs resolutions, price fallback warnings |
| b7_shadow_monitor.py | `logging.getLogger(__name__)` | INFO, WARNING, ERROR, DEBUG | Good — debug for expiry, info for resolutions |
| b8_concentration_monitor.py | `logging.getLogger(__name__)` | INFO, ERROR | Adequate for V1 no-op block |
| b9_capacity_evaluation.py | `logging.getLogger(__name__)` | INFO | Minimal — only summary line |

**Verdict:** All blocks use Python stdlib `logging` with `__name__` loggers — consistent and correct. No `print()` or `console.log` equivalents. Log levels are generally appropriate. B4 and B6 have the richest logging with per-asset numeric detail.

### Health Check Endpoints
- **None in these blocks.** Blocks are pure computation called by the orchestrator. Health checks would be at the process level (main.py/orchestrator). Part 1 already flagged missing readiness/liveness HTTP endpoint.

### Metrics Collection
- **No Prometheus/StatsD/CloudWatch instrumentation.** Session data logged to D17 (capacity_state, quality_results, signal_output) serves as a partial metrics substitute but is not queryable by standard monitoring tools.

### Request Tracing / Correlation IDs
- **Partial.** Signal IDs (`SIG-xxx`) and trade IDs (`TRD-xxx`) provide correlation across B6→B7→Offline. Shadow IDs (`SHADOW-xxx`) trace theoretical outcomes. However, no session-level trace ID propagates through B4→B5→B5B→B5C→B6 pipeline — each block logs independently.

### Log Levels
- **Appropriate.** ERROR for publish failures, WARNING for missing data/fallback paths, INFO for decisions, DEBUG for publish confirmations and shadow expiry.

**Observability Score: 6.5/10**
- (+) Consistent structured logging with __name__ loggers
- (+) Per-decision numeric logging in B4/B6
- (+) Signal/trade/shadow IDs for cross-block correlation
- (-) No pipeline-level trace ID (session-level correlation)
- (-) No metrics instrumentation
- (-) No health endpoints (process-level concern)

---

## Code Principles Score

**DRY: 5.5/10** — 5 distinct duplication clusters (M1-M5) totaling ~15 copy-pasted functions. The `_parse_json` and `_load_system_param` duplications span the entire Online process.

**KISS: 8.5/10** — No unnecessary abstractions. Each block is a single function with helpers. No premature factories/patterns.

**YAGNI: 9.0/10** — No dead feature flags or unused extensibility points. B8 concentration monitor is a V1 no-op for single-user but is spec-required for multi-user.

**Error Handling: 7.0/10** — Redis publishes wrapped in try/except. QuestDB queries mostly wrapped. Critical gap: no retry for trade outcome publish (M8). Non-atomic D16/D23 updates (M6).

**Overall Code Principles Score: 7.0/10**

---

## Stub Inventory (B4-B9)

| File | Function | Line | Type | Impact |
|------|----------|------|------|--------|
| b5c_circuit_breaker.py | `_check_manual_halt()` | l574 | Stub (returns False) | L6 manual override non-functional |
| b7_position_monitor.py | `_check_vix_spike()` | l419 | Stub (pass) | No mid-trade VIX monitoring |
| b7_position_monitor.py | `_regime_shift_detected()` | l424 | Stub (returns False) | No mid-trade regime shift detection |
| b7_position_monitor.py | `_get_api_commission()` | l413 | Stub (returns None) | API fill commission not wired |

**Total new stubs: 4** (plus 3 from Part 1, 0 from Part 2 = **7 total Online stubs**)
