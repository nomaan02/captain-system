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
