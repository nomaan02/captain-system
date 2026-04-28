---
title: Phase 5 Build Plan — BOCPD / CUSUM / Level Escalation
date: 2026-04-27
phase: 5
companion_to:
  - docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md
  - docs2/audits/2026-04-22_offline_spec_vs_code_audit.md
  - docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md
  - docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md
  - docs2/spec-docs-02/offline/kelly_7_layer_pipeline.md
findings_addressed: [F-07, F-19, F-49]
status: READY
authority_chain: decisions log §2 > audit > spec > code
deferred_followups:
  - "Online B4 Kelly cp_prob wiring — separate ticket (canvas claims read; code does not read; out of Phase 5 scope)"
  - "Doc 32 PG-15 amendment — documentation deliverable for Isaac (no code impact)"
---

# Phase 5 — BOCPD / CUSUM / Level Escalation

Scope: bring `b2_bocpd.py`, `b2_cusum.py`, `b2_level_escalation.py`, and the
offline Kelly L1 reader (`b8_kelly_update.py`) into spec compliance with the
resolutions in the Audit Decisions Log §2 Group E (Q-07, Q-29) and §5 Phase 5
row. Three findings: F-07 (HIGH), F-19 (HIGH), F-49 (MEDIUM).

Plan mode: **build plan for Cursor Composer 2 — do not execute code**.

---

## Stage 1 — Audit Pass Recap (read-only, completed)

### F-07 — BOCPD Redis writer missing for `captain:bocpd:{asset}` (HIGH)

Audit: `2026-04-22_offline_spec_vs_code_audit copy.md` lines 203–225.
Decision: Q-07 (decisions log §2 Group E line 74) — Redis is canonical;
`b2_bocpd` adds Redis writer alongside existing D04 write; offline Kelly L1
switches QuestDB → Redis read; Doc 32 PG-15 wording amended (flag for Isaac,
not code).

Current state:
- `b2_bocpd.py:161` computes `cp_probability`, persists to QuestDB at
  `b2_bocpd.py:220-228` (5-column partial INSERT into
  `p3_d04_decay_detector_states`).
- `b8_kelly_update.py:42-52` (`_get_cp_prob`) reads QuestDB
  `current_changepoint_probability` with default 0.1 on miss/null.
- Repo-wide grep for `bocpd:` Redis setters → **zero current writers**, so no
  divergent module to delete.
- Redis key shape **decision: `captain:bocpd:{asset}`** (codebase-consistent
  with `shared/redis_client.py:27-34`; canvas literal `bocpd:{asset}` deviates
  from house convention).

### F-19 — BOCPD Level 2 debouncing skips re-triggers as cp rises (HIGH)

Audit: `2026-04-22_offline_spec_vs_code_audit copy.md` lines 479–501.
Decision: not in decisions log; audit `Needs Isaac: NO`; **fix variant chosen
by Nomaan = material-delta re-fire (Δ ≥ 0.05)**.

Current state: `b2_level_escalation.py:199-206`. `_level2_active[asset_id]`
boolean debounces — first crossing of `LEVEL2_THRESHOLD = 0.8` fires; subsequent
trades with rising cp do NOT re-fire `trigger_level2`, so `P3-D12.sizing_override`
is never refreshed with the stronger `reduction_factor` from PG-08.

### F-49 — CUSUM PG-07 pathwise pooling vs literal nested `j` loop (MEDIUM)

Audit: `2026-04-22_offline_spec_vs_code_audit.md` lines 1113–1122 (only the
non-copy version carries this entry; the copy stops at F-43).
Decision: Q-29 (decisions log §2 Group E line 76) — implement literal nested
`j` loop. Pathwise `max(c_up, c_down)` pooling is **not** an acceptable
approximation. **No NumPy vectorisation, no scipy shortcuts**, even if
mathematically equivalent.

Current state: `b2_cusum.py:100-153` (`calibrate_cusum_limits`). Single pass
through resample appends `max(c_up, c_down)` per step at the naturally-occurring
sprint length. No inner `j` loop. No standalone
`compute_cusum_conditional_on_sprint(resample, j)` helper exists.

### Pending items / soft flags

- **Doc 32 PG-15 amendment** owed to Isaac: line 633 currently says
  `cp_prob = P3-D04[u].current_changepoint_probability`; should read
  `cp_prob = redis.get("captain:bocpd:{u}")`. Surface as a non-blocking
  documentation deliverable.
- **Online B4 Kelly cp_prob wiring** is **deferred** to a separate ticket per
  Nomaan's decision. Canvas L2/L3 annotations claim Online reads
  `bocpd:{asset}`; code does not. Phase 5 only fixes the offline-side reader
  (`b8_kelly_update._get_cp_prob`). Note in batch 2 as a TODO at the call
  site.
- **F-49 runtime cost flag**: literal nested loop is roughly
  `B × MAX_SPRINT × n` vs current `B × n` — order **20–50× slower** on a
  quarterly job. Acceptable per Q-29; surface in batch 4 acceptance criteria
  for one-time profiling.
- §3.2 re-asks: none in this phase's scope.

---

## Stage 2 — Build Plan (5 batches)

### Batch ordering rationale

1. **B1** writes `captain:bocpd:{asset}` to Redis (additive — does not
   change reads). Safe to ship first.
2. **B2** switches `_get_cp_prob` reader to Redis with QuestDB fallback.
   Ordering after B1 ensures no read-before-write window.
3. **B3** material-delta re-fire in level escalation — independent of B1/B2.
4. **B4** CUSUM nested-loop rewrite — independent module, can run in parallel
   with B1–B3 but has the highest test surface.
5. **B5** tests + docs deliverables (Doc 32 PG-15 amendment markdown, ticket
   stub for Online B4 wiring, runtime profile note).

---

## Batch 1 — Add Redis writer for `captain:bocpd:{asset}` in `b2_bocpd`

### 1.1 Spec citation
- Decisions log §2 Group E Q-07 (line 74): "Kelly L1 reads BOCPD `cp_prob`
  from Redis (`bocpd:{asset}` key). … Add a Redis writer in `b2_bocpd`
  alongside the existing D04 write."
- Audit F-07 (`2026-04-22_offline_spec_vs_code_audit copy.md` lines 203–225).
- Spec authority: `Kelly_7_Layer_Pipeline.canvas` L1 SIDE INPUTS column —
  "BOCPD cp_prob (Redis: bocpd:{asset} key)".
- Phase plan delta §5 Phase 5 row: "Adds Redis writer for `bocpd:{asset}`
  (Q-07)."

### 1.2 Pre-flight checks
- `git grep -n 'bocpd' -- '*.py'` returns no Redis setters. Confirm before
  starting.
- `shared/redis_client.py:27-34` defines key prefix `captain:`. Confirm
  `get_redis_client()` is the singleton accessor used elsewhere
  (e.g. `b2_level_escalation.py:99-100`).
- Python redis client `set` API: `client.set(name, value, ex=...)`. Choose TTL
  ≥ longer than the trade cadence (recommend `ex = 7 * 86400` so a quiet asset
  doesn't expire over a weekend; Kelly L1 will fall back to the QuestDB read
  if Redis miss).

### 1.3 Files & line ranges
- **Modify:** `captain-offline/captain_offline/blocks/b2_bocpd.py` lines
  220–228 (the QuestDB write block inside `run_bocpd_update`). Add Redis
  write **after** the QuestDB write succeeds.
- **Modify:** `shared/redis_client.py` lines 27–34. Add a constant for the
  key template alongside the existing `CH_*` channel names.

### 1.4 Change shape — `shared/redis_client.py`

**Before** (lines 27–34):
```python
REDIS_KEY_QUOTES = "captain:quotes"
CH_SIGNALS = "captain:signals:{user_id}"
CH_TRADE_OUTCOMES = "captain:trade_outcomes"
CH_COMMANDS = "captain:commands"
CH_ALERTS = "captain:alerts"
CH_STATUS = "captain:status"
CH_PROCESS_LOGS = "captain:process_logs"
CH_USER_EVENTS = "captain:user_events"
```

**After**:
```python
REDIS_KEY_QUOTES = "captain:quotes"
REDIS_KEY_BOCPD = "captain:bocpd:{asset_id}"  # F-07: canonical cp_prob (Q-07)
CH_SIGNALS = "captain:signals:{user_id}"
CH_TRADE_OUTCOMES = "captain:trade_outcomes"
CH_COMMANDS = "captain:commands"
CH_ALERTS = "captain:alerts"
CH_STATUS = "captain:status"
CH_PROCESS_LOGS = "captain:process_logs"
CH_USER_EVENTS = "captain:user_events"
```

### 1.5 Change shape — `b2_bocpd.py:run_bocpd_update`

**Before** (lines 215–230 approximately):
```python
def run_bocpd_update(asset_id: str, pnl_per_contract: float,
                      detector: BOCPDDetector | None = None) -> tuple[float, BOCPDDetector]:
    if detector is None:
        detector = BOCPDDetector()

    cp_prob = detector.update(pnl_per_contract)

    state = detector.to_dict()
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d04_decay_detector_states
               (asset_id, bocpd_run_length_posterior, bocpd_cp_probability,
                bocpd_cp_history, current_changepoint_probability, last_updated)
               VALUES (%s, %s, %s, %s, %s, now())""",
            (asset_id, json.dumps(state), cp_prob,
             json.dumps(detector.cp_history[-100:]), cp_prob),
        )

    logger.debug("BOCPD %s: cp_prob=%.4f", asset_id, cp_prob)
    return cp_prob, detector
```

**After** — additive Redis mirror after QuestDB write succeeds:
```python
def run_bocpd_update(asset_id: str, pnl_per_contract: float,
                      detector: BOCPDDetector | None = None) -> tuple[float, BOCPDDetector]:
    if detector is None:
        detector = BOCPDDetector()

    cp_prob = detector.update(pnl_per_contract)

    # P3-D04 (audit trail / state restore — full posterior + history JSON)
    state = detector.to_dict()
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d04_decay_detector_states
               (asset_id, bocpd_run_length_posterior, bocpd_cp_probability,
                bocpd_cp_history, current_changepoint_probability, last_updated)
               VALUES (%s, %s, %s, %s, %s, now())""",
            (asset_id, json.dumps(state), cp_prob,
             json.dumps(detector.cp_history[-100:]), cp_prob),
        )

    # F-07 (Q-07): canonical cp_prob mirror to Redis for Kelly L1.
    # QuestDB remains audit/replay; Redis is the live read path.
    try:
        client = get_redis_client()
        client.set(
            REDIS_KEY_BOCPD.format(asset_id=asset_id),
            f"{cp_prob:.6f}",
            ex=7 * 86400,  # 7-day TTL covers weekend gaps; readers fall back to D04
        )
    except Exception as e:
        # Non-fatal: QuestDB write already committed; readers will fall back.
        logger.error("BOCPD %s: Redis mirror failed (non-fatal): %s", asset_id, e)

    logger.debug("BOCPD %s: cp_prob=%.4f", asset_id, cp_prob)
    return cp_prob, detector
```

Add the import at top of `b2_bocpd.py`:
```python
from shared.redis_client import get_redis_client, REDIS_KEY_BOCPD
```

### 1.6 Test additions
- **New file:** `tests/test_b2_bocpd_redis_writer.py`.
- **Assertions:**
  1. After `run_bocpd_update("ES", 12.5, detector)`, the Redis key
     `captain:bocpd:ES` exists with a string value parseable as float.
  2. The float value matches the returned `cp_prob` to 1e-6.
  3. Key TTL is in `(0, 7 * 86400]` range (i.e. set, non-zero).
  4. QuestDB row in `p3_d04_decay_detector_states` for ES carries the same
     `bocpd_cp_probability`.
  5. Redis failure (mock `get_redis_client().set` to raise) does NOT raise
     out of `run_bocpd_update`; QuestDB row still committed; warning logged.
- **Fixture:** Use `fakeredis` or the existing tests/conftest Redis fixture
  if one exists; otherwise mock `shared.redis_client.get_redis_client`.

### 1.7 Exit criteria
- `run_bocpd_update` writes BOTH QuestDB and Redis on success.
- Redis failure does not abort the QuestDB path.
- New test passes; existing `tests/test_stress.py::test_cusum_breach_triggers_level2`
  still passes (unrelated, sanity check).
- `git grep -n 'captain:bocpd' -- '*.py'` returns the constant + the writer
  + the test only.

### 1.8 Rollback
- Revert the two edits (`shared/redis_client.py` constant addition,
  `b2_bocpd.py` Redis mirror block + import).
- Optional: `redis-cli --scan --pattern 'captain:bocpd:*' | xargs redis-cli del`
  to clear stale keys. Not required for correctness — keys expire on TTL.

---

## Batch 2 — Switch offline Kelly L1 reader to Redis (with QuestDB fallback)

### 2.1 Spec citation
- Decisions log §2 Group E Q-07 (line 74): "Reader (Kelly L1) switches from
  QuestDB to Redis."
- Audit F-07 (HIGH).
- Spec authority chain note: doc 32 PG-15 still says QuestDB. Decisions log
  supersedes spec. **Doc 32 amendment is a Phase 5 deliverable for Isaac
  (Batch 5), not a blocker for this batch.**

### 2.2 Pre-flight checks
- Confirm Batch 1 is merged (Redis writer live) before deploying Batch 2.
- `git grep -n '_get_cp_prob' --include='*.py'` should return only
  `b8_kelly_update.py` (the function definition + its caller).
- Confirm `b8_kelly_update.py` import block already imports `get_cursor`;
  add `get_redis_client` and `REDIS_KEY_BOCPD` next to it.

### 2.3 Files & line ranges
- **Modify:** `captain-offline/captain_offline/blocks/b8_kelly_update.py`
  lines 42–52 (the entire `_get_cp_prob` function body).
- **Modify:** `b8_kelly_update.py` import block (top of file) — add
  `get_redis_client`, `REDIS_KEY_BOCPD` from `shared.redis_client`.

### 2.4 Change shape

**Before** (lines 42–52):
```python
def _get_cp_prob(asset_id: str) -> float:
    """Get current BOCPD changepoint probability from P3-D04."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT current_changepoint_probability FROM p3_d04_decay_detector_states
               WHERE asset_id = %s
               LATEST ON last_updated PARTITION BY asset_id""",
            (asset_id,),
        )
        row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0.1  # default low
```

**After**:
```python
def _get_cp_prob(asset_id: str) -> float:
    """Get current BOCPD changepoint probability.

    Per Q-07 (decisions log §2 Group E), Redis `captain:bocpd:{asset_id}`
    is canonical. QuestDB P3-D04 is the audit/replay store and fallback
    when Redis is cold (process restart, key TTL expiry, fakeredis test).

    NOTE: Online B4 Kelly does NOT consume cp_prob today (canvas L2/L3
    annotation claims it should — see deferred ticket).
    """
    # Primary: Redis (canonical per Q-07).
    try:
        client = get_redis_client()
        raw = client.get(REDIS_KEY_BOCPD.format(asset_id=asset_id))
        if raw is not None:
            # redis-py returns bytes by default; handle both.
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            return float(raw)
    except Exception as e:
        logger.warning("Kelly L1 cp_prob: Redis read failed for %s, "
                        "falling back to QuestDB: %s", asset_id, e)

    # Fallback: QuestDB P3-D04 (last-known committed state).
    with get_cursor() as cur:
        cur.execute(
            """SELECT current_changepoint_probability FROM p3_d04_decay_detector_states
               WHERE asset_id = %s
               LATEST ON last_updated PARTITION BY asset_id""",
            (asset_id,),
        )
        row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0.1  # default low
```

Add to imports at top of `b8_kelly_update.py`:
```python
from shared.redis_client import get_redis_client, REDIS_KEY_BOCPD
```

### 2.5 Test additions
- **New file:** `tests/test_b8_kelly_cp_prob_source.py`.
- **Assertions:**
  1. Redis hit (key set to `"0.74"`) → `_get_cp_prob("ES")` returns `0.74`,
     QuestDB is NOT queried (mock `get_cursor` and assert `not_called`).
  2. Redis miss (no key) + QuestDB row with cp=0.62 → returns 0.62.
  3. Redis miss + QuestDB miss → returns default 0.1.
  4. Redis raises → falls back to QuestDB; warning logged.
  5. Redis returns malformed string (`"NaN"` raw) → safe handling: the test
     should encode the desired behaviour. Recommend: log + fall through to
     QuestDB. Implement an extra `except (ValueError, TypeError)` arm in the
     primary block; assert behaviour.

### 2.6 Exit criteria
- Reader prefers Redis; QuestDB fallback exercised on Redis failure.
- All 5 test cases above pass.
- No other module's reader is changed (defer Online B4 wiring per scope
  constraint #4).
- `git grep -n 'current_changepoint_probability' --include='*.py'` shows
  remaining QuestDB readers (orchestrator restore, GUI, reports) untouched.

### 2.7 Rollback
- Revert `_get_cp_prob` to the QuestDB-only implementation.
- Revert the import addition.
- Batch 1's Redis writer can stay running (additive); harmless if no reader.

---

## Batch 3 — F-19 BOCPD Level 2 material-delta re-fire

### 3.1 Spec citation
- Audit F-19 (`2026-04-22_offline_spec_vs_code_audit copy.md` lines 479–501).
- Spec authority: doc 32 PG-05 (line 246) — `IF cp_probability > 0.8: TRIGGER
  Level_2(asset, severity=cp_probability, source="BOCPD")`. PG-08 — sizing
  reduction scales with severity.
- Decisions log: silent on F-19. Audit `Needs Isaac: NO`. **Fix variant
  selected by Nomaan: material-delta re-fire (option 2 of audit's three
  options), Δ ≥ 0.05.**

### 3.2 Pre-flight checks
- Confirm `_level2_active` is currently a module-level `dict[str, bool]` —
  inspect top of `b2_level_escalation.py`. The new state will need to track a
  float (last-fired severity) per asset, not a bool.
- Confirm `LEVEL2_THRESHOLD = 0.8` and `LEVEL3_THRESHOLD`, `LEVEL3_SUSTAINED_WINDOW`
  constants live at module scope.
- Confirm `trigger_level2(asset_id, severity, source)` is the sole entry into
  PG-08's `_set_sizing_override` from the BOCPD path.

### 3.3 Files & line ranges
- **Modify:** `captain-offline/captain_offline/blocks/b2_level_escalation.py`:
  - Module-level constant block (top of file, near `LEVEL2_THRESHOLD`): add
    `LEVEL2_REFIRE_DELTA = 0.05`.
  - `_level2_active` declaration: change `dict[str, bool]` →
    `dict[str, float]` (stores last-fired severity).
  - `check_level_escalation` body — the BOCPD Level 2 block at lines
    199–206.

### 3.4 Change shape

**Before** (lines 199–206):
```python
    # Level 2: BOCPD cp_prob > 0.8 — debounced (once per changepoint event)
    if cp_probability > LEVEL2_THRESHOLD:
        if not _level2_active.get(asset_id):
            _level2_active[asset_id] = True
            trigger_level2(asset_id, cp_probability, "BOCPD")
    else:
        # cp_prob dropped below threshold — reset debounce for next event
        _level2_active.pop(asset_id, None)
```

Module-level state declaration (current):
```python
_level2_active: dict[str, bool] = {}
```

**After** — module-level state and constant:
```python
LEVEL2_REFIRE_DELTA = 0.05  # F-19: re-fire when severity rises by >= delta

# F-19: stores last-fired severity per asset (NOT a bool).
# Absent key → no L2 active. Present key → last severity that fired
# trigger_level2; subsequent triggers gated on (new_severity - last) >= delta.
_level2_active: dict[str, float] = {}
```

**After** — re-fire logic (replaces lines 199–206):
```python
    # Level 2: BOCPD cp_prob > 0.8 — material-delta re-fire (F-19, Δ=0.05).
    # First crossing fires unconditionally; subsequent fires only when
    # cp_probability has risen by >= LEVEL2_REFIRE_DELTA since the last fire.
    # PG-08 sizing reduction therefore tracks worsening cp instead of
    # locking in at first-crossing severity.
    if cp_probability > LEVEL2_THRESHOLD:
        last_fired = _level2_active.get(asset_id)
        if last_fired is None or (cp_probability - last_fired) >= LEVEL2_REFIRE_DELTA:
            _level2_active[asset_id] = cp_probability
            trigger_level2(asset_id, cp_probability, "BOCPD")
    else:
        # cp_prob dropped below threshold — reset for next event.
        _level2_active.pop(asset_id, None)
```

Note: the CUSUM Level 2 block at lines 209–210 (CUSUM "BREACH") is unchanged;
CUSUM resets itself per breach, so its semantics are different from BOCPD's
sustained crossing.

### 3.5 Test additions
- **New file:** `tests/test_b2_level_escalation_refire.py` (or extend
  `tests/test_b5c_circuit.py` if there's already a coverage home — confirm
  by grepping `_level2_active` in `tests/`).
- **Assertions** (each call patches `trigger_level2` to a `MagicMock`):
  1. Single fire on first crossing: cp = 0.81 → `trigger_level2` called once
     with severity=0.81.
  2. No re-fire below delta: cp sequence [0.81, 0.83, 0.85] → only 1 call
     (0.85 − 0.81 = 0.04 < 0.05; 0.83 − 0.81 = 0.02 < 0.05).
  3. Re-fire at delta: cp sequence [0.81, 0.86] → 2 calls (severities 0.81,
     0.86).
  4. Cumulative monotonic rise re-fires only on each delta crossing:
     cp sequence [0.81, 0.85, 0.86, 0.91] → 3 calls (0.81, 0.86, 0.91).
     Verify last-fired tracking, not first-fired.
  5. Drop below threshold resets state: [0.81, 0.79, 0.82] → 2 calls
     (0.81 fires, 0.79 resets, 0.82 fires fresh).
  6. Level 3 takeover clears state: cp sequence with 5 consecutive >0.9
     hitting LEVEL3_SUSTAINED_WINDOW → `trigger_level3` fires, then a
     subsequent cp=0.81 fires Level 2 fresh (state cleared at
     `_level2_active.pop(asset_id, None)` in Level 3 branch line 191).

### 3.6 Exit criteria
- Six new test cases above pass.
- `_level2_active` type is `dict[str, float]` (not bool) repo-wide; no
  callers introspect the value as bool.
- Existing test `tests/test_stress.py::test_cusum_breach_triggers_level2`
  still passes (unrelated path).
- Manual smoke: log a synthetic cp ramp from 0.79 → 0.95 in 0.01 increments;
  count `trigger_level2` calls. Expect 4 calls (0.81, 0.86, 0.91, 0.95-ish
  exact crossings depending on starting severity tracker — confirm against
  test #4).

### 3.7 Rollback
- Revert the three edits (constant addition, state-type change, body
  replacement).
- No data migration required; `_level2_active` is process-local memory only.

---

## Batch 4 — F-49 CUSUM literal nested-`j`-loop bootstrap calibration

### 4.1 Spec citation
- Decisions log §2 Group E Q-29 (line 76): "Implement the literal nested `j`
  loop per spec. The pathwise `max(c_up, c_down)` pooling is not an
  acceptable approximation. Phase 5. Rewrite
  `compute_cusum_conditional_on_sprint`."
- Audit F-49 (`2026-04-22_offline_spec_vs_code_audit.md` lines 1113–1122 —
  note: NOT in the `copy` audit, only in the original).
- Spec authority: doc 32 PG-07 (lines 285–305) — outer `b ∈ [0, B)`, inner
  `j ∈ [1, max_sprint)`, semantic `compute_cusum_conditional_on_sprint(resample, j)`
  returns C_n | T_n = j.

### 4.2 Pre-flight checks
- Confirm `BOOTSTRAP_B`, `MAX_SPRINT`, `ARL_0` constants at top of
  `b2_cusum.py` and their current values. Recommend leaving the defaults
  alone — Q-29 is silent on these.
- Confirm `random.choices` is the chosen resample method (no NumPy
  vectorised sampler permitted per Q-29 — even though `np.random.choice`
  would be equivalent, Q-29 explicitly forbids vectorisation).
- Confirm there is no existing helper named
  `compute_cusum_conditional_on_sprint`. (`grep -n compute_cusum_conditional_on_sprint
  -- '*.py'` → expected: zero hits.)

### 4.3 Files & line ranges
- **Modify:** `captain-offline/captain_offline/blocks/b2_cusum.py` lines
  100–153 (the entire `calibrate_cusum_limits` function).
- **Add:** new helper `compute_cusum_conditional_on_sprint(resample, j, allowance)`
  immediately above `calibrate_cusum_limits`.

### 4.4 Change shape

**Before** (lines 100–153, simplified):
```python
def calibrate_cusum_limits(in_control_pnl: list[float],
                            B: int = BOOTSTRAP_B,
                            arl_0: int = ARL_0) -> dict[int, float]:
    n = len(in_control_pnl)
    if n < 20:
        logger.warning("CUSUM calibration: insufficient data (%d < 20)", n)
        return {}

    allowance = float(np.std(in_control_pnl)) / 2.0
    percentile = 100.0 * (1.0 - 1.0 / arl_0)

    cusum_by_sprint: dict[int, list[float]] = {}

    for _ in range(B):
        resample = random.choices(in_control_pnl, k=n)
        c_up = 0.0
        c_down = 0.0
        sprint = 0

        for x in resample:
            c_up = max(0.0, c_up + x - allowance)
            c_down = max(0.0, c_down - x - allowance)

            if c_up == 0.0 and c_down == 0.0:
                sprint = 0
            else:
                sprint += 1

            if sprint > 0 and sprint <= MAX_SPRINT:
                cusum_by_sprint.setdefault(sprint, []).append(max(c_up, c_down))

    sequential_limits = {}
    for j in range(1, MAX_SPRINT + 1):
        values = cusum_by_sprint.get(j, [])
        if len(values) >= 10:
            sequential_limits[j] = float(np.percentile(values, percentile))

    return sequential_limits
```

**After** — literal nested `j` loop per Q-29 / PG-07:

```python
def compute_cusum_conditional_on_sprint(resample: list[float],
                                          j: int,
                                          allowance: float) -> list[float]:
    """Walk a CUSUM trajectory over `resample`; collect every
    `max(c_up, c_down)` observed at the exact step where `sprint_length == j`.

    Implements C_n | T_n = j per doc 32 PG-07. A single resample may produce
    zero, one, or many observations at a given sprint length j (the sprint
    counter resets to zero whenever both c_up and c_down hit zero, so a long
    resample can re-traverse sprint length j multiple times).

    Q-29 mandate: literal nested loop, no NumPy vectorisation, no scipy
    shortcuts — even if mathematically equivalent.
    """
    observed: list[float] = []
    c_up = 0.0
    c_down = 0.0
    sprint = 0
    for x in resample:
        c_up = max(0.0, c_up + x - allowance)
        c_down = max(0.0, c_down - x - allowance)
        if c_up == 0.0 and c_down == 0.0:
            sprint = 0
        else:
            sprint += 1
        if sprint == j:
            observed.append(max(c_up, c_down))
    return observed


def calibrate_cusum_limits(in_control_pnl: list[float],
                            B: int = BOOTSTRAP_B,
                            arl_0: int = ARL_0) -> dict[int, float]:
    """P3-PG-07: Bootstrap calibration of sequential control limits.

    For each sprint length j, build the bootstrap distribution of
    C_n | T_n = j across B resamples and take the (1 - 1/ARL_0)-quantile
    as the sequential control limit h(j).

    Q-29: literal nested-loop form per doc 32 PG-07. Outer loop over
    bootstrap resamples (B); inner loop over sprint lengths j; innermost
    walk via `compute_cusum_conditional_on_sprint`.
    """
    n = len(in_control_pnl)
    if n < 20:
        logger.warning("CUSUM calibration: insufficient data (%d < 20)", n)
        return {}

    allowance = float(np.std(in_control_pnl)) / 2.0
    percentile = 100.0 * (1.0 - 1.0 / arl_0)

    # Build conditional bootstrap distribution per sprint length.
    cusum_by_sprint: dict[int, list[float]] = {j: [] for j in range(1, MAX_SPRINT + 1)}

    for b in range(B):                                # outer 1: bootstrap
        resample = random.choices(in_control_pnl, k=n)
        for j in range(1, MAX_SPRINT + 1):            # outer 2: sprint length
            cusum_by_sprint[j].extend(
                compute_cusum_conditional_on_sprint(resample, j, allowance)
            )

    # Per-j quantile → sequential control limit h(j).
    sequential_limits: dict[int, float] = {}
    for j in range(1, MAX_SPRINT + 1):
        values = cusum_by_sprint[j]
        if len(values) >= 10:
            sequential_limits[j] = float(np.percentile(values, percentile))

    logger.info("CUSUM calibration: %d sprint lengths calibrated "
                 "(B=%d, ARL_0=%d, MAX_SPRINT=%d)",
                 len(sequential_limits), B, arl_0, MAX_SPRINT)
    return sequential_limits
```

**Note on the ONLY allowed `numpy` use:** `np.std` and `np.percentile`.
These are fixture-stage scalar operations, not vectorised CUSUM walks.
Q-29 forbids vectorising the **walk**, not statistical reductions on the
final distribution. If reviewer disagrees, replace `np.percentile` with
`statistics.quantiles` and `np.std` with `statistics.stdev`. Flag in PR
description.

### 4.5 Test additions
- **New file:** `tests/test_b2_cusum_calibration.py`.
- **Fixture 1 — deterministic correctness on a known-easy series:**
  Use a synthetic in-control series of 100 i.i.d. N(0, 1) draws with a fixed
  random seed (`random.seed(42)`, `np.random.seed(42)`). Run
  `calibrate_cusum_limits(series, B=200, arl_0=50)`. Assertions:
  1. Returns a non-empty dict.
  2. Every key is an int in `[1, MAX_SPRINT]`.
  3. Limits are non-negative floats.
  4. Limits are roughly monotonically non-decreasing in `j` (sprint length j
     allows more accumulation → higher quantile). Allow 10 % per-step
     tolerance for stochastic noise.
- **Fixture 2 — `compute_cusum_conditional_on_sprint` unit tests:**
  1. Empty resample → empty list.
  2. Resample where CUSUM never crosses zero (e.g. all positive
     `[1.0, 1.0, 1.0]` with allowance=0.0) → for j=1 returns
     `[max(1, 0)]=[1.0]`; for j=2 returns `[max(2, 0)]=[2.0]`; for j=3 returns
     `[max(3, 0)]=[3.0]`; for j>3 returns `[]`.
  3. Resample with a reset (`[1, -1, 1]` allowance=0.0) → c_up=1, c_down=1
     at step 1; sprint resets at step 2 (both zero with this exact
     trajectory? verify — c_up=max(0, 1+(-1)-0)=0, c_down=max(0, 0-(-1)-0)=1
     → not both zero, sprint=2. Re-derive expected values during test
     authoring; lock the trajectory after manual hand-calc).
- **Fixture 3 — divergence from old pathwise pooling:**
  Author a small synthetic where the old (pathwise) and new (nested) forms
  produce *different* outputs. The simplest is a series whose sprint
  re-traverses the same `j`: e.g. `[1, -1, -1, 1, -1, -1, 1]` with appropriate
  allowance — pathwise pooling captures one value per step, nested
  conditional draw can return multiple at j=1. Lock the expected output
  table in the test and assert the new function returns the correct multi-
  observation list. This test guards against regression to vectorised forms.
- **Fixture 4 — anti-vectorisation guard:**
  Static check that `compute_cusum_conditional_on_sprint`'s source does not
  contain forbidden tokens. Use `inspect.getsource` and assert none of:
  `np.cumsum`, `np.maximum.accumulate`, `scipy`, `np.where`. Forces future
  contributors back to the loop form per Q-29.

### 4.6 Exit criteria
- All four fixtures pass.
- `compute_cusum_conditional_on_sprint` exists as a named function and is
  imported nowhere else (single call site is `calibrate_cusum_limits`).
- Quarterly recalibration runtime profile: capture wall-clock for one asset
  on the existing `_run_quarterly` path with B=2000, MAX_SPRINT=20, n=100.
  Document in PR description as "Phase 5 cost note for Nomaan". Expected
  range: 30 s – 3 min per asset depending on hardware. NOT a blocker.
- Existing test `tests/test_stress.py::test_cusum_breach_triggers_level2`
  still passes.
- F-20 (`Quarterly PG-07 persists new CUSUM limits but does not refresh
  in-memory detector`) is NOT addressed in this batch — flag at PR review
  for a separate batch in this same phase OR a Phase 6 ticket. (Audit
  reference: lines 502–519.)

### 4.7 Rollback
- Revert `b2_cusum.py` lines 100–153 + the new helper.
- No data migration required; bootstrap is process-side compute.
- Persisted limits in `p3_d04_decay_detector_states.cusum_sequential_limits`
  remain valid under either implementation; rollback does not invalidate
  stored data, only the *next* recalibration path.

---

## Batch 5 — Tests, deferred-ticket stubs, and Doc 32 amendment for Isaac

### 5.1 Spec citation
- Decisions log §2 Group E Q-07 final sentence (line 74): "Doc 32 PG-15
  should be amended to match — flag this as a doc edit for Isaac."
- Phase plan delta §5 Phase 5 row.
- Nomaan's instruction during plan review: defer Online B4 cp_prob wiring
  to a separate ticket; record in plan.

### 5.2 Pre-flight checks
- Confirm Batches 1–4 are merged and green before producing the deliverables
  in this batch (no code changes here, but the docs reference the new
  contracts).

### 5.3 Files to add or modify
- **Add:** `docs2/audits/phase-ref-docs/phase-2/2026-04-27_doc32_pg15_amendment_for_isaac.md`
  — the literal proposed amendment to doc 32 PG-15.
- **Add:** `docs2/audits/phase-ref-docs/phase-2/2026-04-27_phase5_deferred_tickets.md`
  — capture (a) Online B4 cp_prob wiring, (b) F-20 stale in-memory CUSUM
  limits if not handled in Batch 4, (c) any Doc 32 PG-15 follow-up signals.

### 5.4 Content — Doc 32 PG-15 amendment for Isaac

```markdown
# Proposed amendment to doc 32 — PG-15 cp_prob source

**Context:** Q-07 (Audit Decisions Log §2 Group E) ratifies the Kelly canvas
contract: Redis `captain:bocpd:{asset}` is the canonical source for
`cp_prob`. Doc 32 PG-15 currently reads `P3-D04.current_changepoint_probability`,
which is a divergent secondary source.

**Affected file:** `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md`

**Section:** PG-15 (Block 8 — Kelly Parameter Updates).

**Current text (line 633):**
```
cp_prob = P3-D04[u].current_changepoint_probability
```

**Proposed text:**
```
cp_prob = redis.get("captain:bocpd:{u}")
   -- canonical per Q-07; falls back to P3-D04.current_changepoint_probability on miss.
   -- P3-D04 retains audit/replay role; Redis is the live read path.
```

**Rationale:** brings doc 32 into alignment with the Kelly 7-Layer Pipeline
canvas L1 SIDE INPUTS column ("BOCPD cp_prob (Redis: bocpd:{asset} key)")
and with the live code in `b2_bocpd.py` and `b8_kelly_update.py` after
Phase 5 batches 1–2.

**Decision required from Isaac:** confirm wording (especially the fallback
clause and the canvas-vs-code key shape `captain:bocpd:{asset}` rather than
the canvas-literal `bocpd:{asset}`).
```

### 5.5 Content — deferred tickets

```markdown
# Phase 5 deferred follow-ups

## DEFERRED-1 — Online B4 Kelly cp_prob wiring

Canvas (`Kelly_7_Layer_Pipeline.canvas` L2/L3) annotations reference reading
`bocpd:{asset}` from Redis on the Online side. Code at
`captain-online/captain_online/blocks/b4_kelly_sizing.py` does NOT currently
read cp_prob; Online Kelly is independent of BOCPD output.

**Decision (Phase 5 review):** defer to a separate ticket. Phase 5 fixes
only the offline-side reader (`b8_kelly_update._get_cp_prob`).

**Action:** open ticket `CAP-OFFLINE-F07-FOLLOWUP` titled "Online B4 Kelly:
ingest BOCPD cp_prob per canvas L2/L3" with body:
- Investigate intended L2/L3 use of cp_prob in Online Kelly.
- Decide: (a) wire it in per canvas, OR (b) amend canvas to remove the
  annotation if the offline path is sufficient.
- If (a): add Redis read in `b4_kelly_sizing.py` mirroring the
  `_get_cp_prob` pattern from `b8_kelly_update.py`.

## DEFERRED-2 — F-20 stale in-memory CUSUM limits after quarterly recalibration

`captain-offline/captain_offline/blocks/orchestrator.py:995-1017`
(`_run_quarterly`) calls `calibrate_and_persist` but does not reload the new
limits into the live `CUSUMDetector` instances in `self._detectors`. Audit
F-20 (lines 502–519). HIGH severity.

**Status at end of Phase 5:** unresolved unless Batch 4 reviewer chose to
include it. Confirm and either close or carry forward.

**Action if not addressed:** open ticket `CAP-OFFLINE-F20` to merge returned
limits from `calibrate_and_persist` into the live detector after every
quarterly run, mirroring `_init_cusum_calibration` (lines 577–629).

## DEFERRED-3 — Doc 32 PG-15 amendment

See `2026-04-27_doc32_pg15_amendment_for_isaac.md`. Once Isaac confirms
wording, apply the edit and remove this entry.
```

### 5.6 Exit criteria
- Both new markdown files exist under
  `docs2/audits/phase-ref-docs/phase-2/`.
- Doc 32 amendment file is referenced from `MEMORY.md` or session notes so
  the next session can find it.
- Three deferred tickets are filed (or queued for filing) in whatever issue
  tracker Nomaan uses; their IDs are recorded in `2026-04-27_phase5_deferred_tickets.md`.

### 5.7 Rollback
- Delete the two new markdown files. No code impact.

---

## Cross-batch acceptance gate

Before declaring Phase 5 complete:

1. `pytest tests/ -k 'bocpd or cusum or level_escalation or kelly_cp_prob' -v`
   passes 100 %.
2. `git grep -n 'bocpd:' --include='*.py'` returns:
   - `shared/redis_client.py` (constant)
   - `b2_bocpd.py` (writer)
   - `b8_kelly_update.py` (reader)
   - test files
   …and nothing else.
3. `git grep -n 'compute_cusum_conditional_on_sprint' --include='*.py'`
   returns the helper definition + its single call site + its tests.
4. Doc 32 amendment file is staged for Isaac.
5. Online B4 deferred ticket is filed.
6. Quarterly CUSUM recalibration is profiled once (any asset, any test
   account) and the runtime is recorded in PR description.
7. Existing pre-Phase-5 tests still green: stress, integration_e2e, b5c_circuit.

---

## Change log of Stage-1 audit pass decisions baked into this plan

| Question raised at audit | Decision applied |
|---|---|
| Scope = F-07 + F-19 only? | **No** — scope is F-07 + F-19 + F-49 per Q-29 constraint. |
| Redis key shape? | **`captain:bocpd:{asset}`** (codebase-consistent). Canvas-literal `bocpd:{asset}` rejected. |
| F-19 fix variant? | **Material-delta re-fire, Δ=0.05** (audit option 2). |
| Online B4 cp_prob wiring? | **Deferred** to separate ticket (DEFERRED-1). |
| Doc 32 PG-15 amendment? | **Documentation deliverable for Isaac (Batch 5)** — no code edit to spec docs in Phase 5. |

---

*This build plan is execution-ready for Cursor Composer 2. Each batch is
self-contained: spec citation, pre-flight, files+lines, exact change shape,
tests, exit criteria, rollback. Authority chain (decisions log § §2 > audit >
spec > code) governs every choice; deviations are flagged inline.*
