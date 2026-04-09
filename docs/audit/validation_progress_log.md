# Validation Progress Log

Agent B (Validator) — tracking all validation cycles.

---

## Cycle 03 — Session 03 Findings (2026-04-09 03:14 GMT+1)

### G-011 | Level 2 Debounce | ALIGNED
- **Spec:** §6 CB — Level 2 triggers once per changepoint event; debounced
- **Verified:** `_level2_active` dict at line 41-44 tracks per-asset state. Set True on first `cp_prob > 0.8` (line 201), cleared when cp_prob drops below threshold (line 205). CUSUM handled separately at line 208 (self-resetting per PG-06).
- **Control flow:** BOCPD debounce at lines 199-205; CUSUM fires independently at lines 207-209.
- **Regressions:** None. No Level 1/Level 4 logic in this block.
- **Verdict:** ALIGNED -> VERIFIED

### G-012 | Level 2/3 Mutual Exclusivity | ALIGNED
- **Spec:** §6 CB — Level 2 and Level 3 are mutually exclusive escalation tiers
- **Verified:** Level 3 check at lines 190-196 runs FIRST. On trigger: calls `trigger_level3()`, clears Level 2 debounce state, returns early (line 196). Level 2 checks at lines 198-209 are unreachable when Level 3 fires.
- **Regressions:** None. Housekeeping clears `_level2_active` on Level 3 trigger (line 195).
- **Verdict:** ALIGNED -> VERIFIED

### G-028 | Redis Publish Retry | ALIGNED
- **Spec:** §11 Feedback Loop 1 — trade outcome must reliably reach Offline via Redis
- **Verified:** `_publish_trade_outcome` (lines 338-380) has 3-attempt retry loop (line 365: `max_attempts = 3`). Exponential backoff at line 373: `0.5 * (2 ** (attempt - 1))` yields 0.5s, 1s, 2s. Success logged at INFO, retries at WARNING, final failure at ERROR with trade_id context.
- **Note:** G-NEW-007 interaction — retry sleeps execute while `_position_lock` is held (up to 3.5s worst case). Acknowledged in session 03 passover as known follow-up, not a spec divergence.
- **Regressions:** None to core publish reliability.
- **Verdict:** ALIGNED -> VERIFIED

### G-006 | Thread Lock for Position Lists | ALIGNED
- **Spec:** §2 B7, §11 Loop 1 — correct trade outcome delivery; no race conditions
- **Verified:** `_position_lock = threading.Lock()` created at line 64. Guards:
  - `_run_position_monitor` (lines 597-603): all mutations protected
  - `_run_shadow_monitor` (lines 608-614): all mutations protected
  - `_handle_taken_skipped` (lines 766-773): append + shadow removal protected
  - `_run_b6_for_user` (lines 574-575): shadow append protected
- **Known follow-ups (already tracked as new findings):**
  - G-NEW-008: Unguarded truthiness checks at lines 120, 127 — benign TOCTOU, worst case one cycle delay (1s).
  - G-NEW-007: Blocking I/O (QuestDB writes, Redis publishes) under lock in `_run_position_monitor`. Lock scope wider than minimum necessary.
- **Regressions:** None to core race condition fix. All mutations guarded.
- **Verdict:** ALIGNED -> VERIFIED (with G-NEW-007/G-NEW-008 tracked for future sessions)

### G-044 | Redis Thread Join on Shutdown | ALIGNED
- **Spec:** §12 Lifecycle — graceful shutdown joins all threads
- **Verified:** `_redis_thread = None` initialized in `__init__` (line 47-51). Assigned with `daemon=True` in `start()` (line 64). `stop()` (lines 69-77) calls `_redis_thread.join(timeout=5.0)` at line 74, warns if thread still alive at line 76. Signal handlers in `main.py` (lines 120-127) call `stop()` then `sys.exit(0)`.
- **Known follow-ups (already tracked as new findings):**
  - G-NEW-010: 5s timeout marginal given 2.5s combined block wait per stream iteration.
  - G-NEW-011: `stop()` assumes caller calls `sys.exit(0)` — satisfied by `main.py` but not enforced.
- **Regressions:** None. daemon=True prevents hung process on exit.
- **Verdict:** ALIGNED -> VERIFIED

### G-014 | SEED=42 Removal | ALIGNED
- **Spec:** §4 B6 — stochastic GA exploration; §4 B7 — stochastic MC simulation
- **Verified:** No `SEED` constant, `random.seed()`, or `np.random.seed()` in either file. Both files still import `random` and `numpy` (actively used). Comments at lines 229 (b6) and 117 (b7) document intent. Codebase-wide grep of `captain-offline/` confirms zero remaining seed patterns.
- **Regressions:** No test dependencies on deterministic output found.
- **Verdict:** ALIGNED -> VERIFIED

### Fact-Check Results
- QuestDB table names: 12 references across 6 files — all match `scripts/init_questdb.py`
- Redis channels: All references match `shared/redis_client.py` canonical definitions
- Threshold constants: All values reasonable (LEVEL2=0.8, LEVEL3=0.9, PBO=0.5, DSR=0.5)

### Cycle 03 Summary
- **Findings validated:** 6
- **ALIGNED:** 6
- **PARTIAL:** 0
- **DIVERGENT:** 0
- **Cumulative:** 18 / 67 total (all 18 FIXED -> VERIFIED)
- **Open concerns:** G-NEW-007 through G-NEW-011 tracked as new findings for future sessions

---

## Cycle 06 — Session 06 Findings (2026-04-09 12:02 GMT+1)

### G-023 | Concurrent Market Data Prefetch | ALIGNED
- **Spec:** §1 — B1 latency budget <9s; parallel asset data fetch via ThreadPoolExecutor
- **Verified:** `_prefetch_market_data()` at b1_data_ingestion.py:353-381 uses `ThreadPoolExecutor(max_workers=min(len(assets), 10))`. Results keyed by asset_id. `as_completed` loop with per-task exception handling. Integration at lines 809-812 feeds into `_run_data_moderator`.
- **Regressions:** None.
- **Verdict:** ALIGNED -> VERIFIED

### G-018 | Rate Limit Retry with Exponential Backoff | ALIGNED
- **Spec:** §10 — TopstepX REST handles rate limiting and timeout gracefully
- **Verified:** Constants at topstep_client.py:28-29. `_post()` (lines 345-380): `timeout=10`, 429 retry with backoff 1s/2s/4s, `Retry-After` header respected. `authenticate()` (line 111): `timeout=10`.
- **Regressions:** None.
- **Verdict:** ALIGNED -> VERIFIED

### G-030 | VIX Spike / Regime Shift / Commission Stubs | PARTIAL
- **Spec:** §2 B7 — "VIX z-score > 2.0 (vs 60d trailing) -> HIGH alert"; regime shift -> CRITICAL; commission chain with fallback
- **Regime shift:** ALIGNED. `_regime_shift_detected()` (line 502) reads `_regime_cache`, called from orchestrator.
- **Commission:** ALIGNED in structure. `_get_api_commission()` (line 454) wired to `get_expected_fee`.
- **VIX spike — PARTIAL:** `_check_vix_spike()` (line 476) uses flat `vix >= threshold` (default 50.0). Spec requires z-score > 2.0 vs 60d trailing.
- **Regression — wrong table:** Lines 462, 487 query `system_params` (should be `p3_d17_system_monitor_state`) with wrong columns `value`/`key` (should be `param_value`/`param_key`). Runtime failure.
- **Regression — dead code:** `resolve_commission` calls `_get_api_commission(account_id)` without `asset_id`/`tsm`.
- **Verdict:** PARTIAL -> stays FIXED.

### G-031 | point_value Query in Shadow Monitor | PARTIAL
- **Spec:** §2 B7 — point_value from P3-D00 (asset_universe)
- **Verified:** `_get_point_value()` at b7_shadow_monitor.py:217-230 uses LATEST ON with parameterized $1. Fallback 50.0.
- **Regression — wrong table:** Line 222 queries `asset_universe` (should be `p3_d00_asset_universe`). Runtime failure.
- **Verdict:** PARTIAL -> stays FIXED.

### G-032 | Expired Shadow Position Resolution | ALIGNED
- **Spec:** §2 B7 Phase 5 — shadow outcomes feed Category A learning
- **Verified:** b7_shadow_monitor.py:88-95 calls `_resolve_shadow(shadow, "TIMEOUT", exit_price)`. Publishes `theoretical=True` outcome to `STREAM_SIGNAL_OUTCOMES`.
- **Known follow-ups:** G-NEW-019 (datetime.now naive), G-NEW-020 (no retry on publish).
- **Verdict:** ALIGNED -> VERIFIED

### G-033 | Atomic Capital + CB Update | ALIGNED
- **Spec:** §11 Loop 5 — atomic D23 L_t += pnl, n_t++ with D16 capital update
- **Verified:** `_update_capital_and_cb()` uses single `with get_cursor() as cur:` for D16+D23. Old separate methods removed.
- **Verdict:** ALIGNED -> VERIFIED

### Audit Skills
- **ln-641:** 2H (datetime.now in b7_pos_monitor; commission dead code), 4M, 8L across 4 files.
- **ln-614:** 2 wrong table names (`system_params`, `asset_universe`). 10/12 claims verified.

### Cycle 06 Summary
- **Findings validated:** 6
- **ALIGNED:** 4 (G-023, G-018, G-032, G-033)
- **PARTIAL:** 2 (G-030, G-031)
- **DIVERGENT:** 0
- **Cumulative:** 22 / 67 total (4 new VERIFIED; 2 stay FIXED with notes)
- **Open concerns:** G-030 VIX z-score + table bugs; G-031 table name; G-NEW-015 through G-NEW-021 tracked
