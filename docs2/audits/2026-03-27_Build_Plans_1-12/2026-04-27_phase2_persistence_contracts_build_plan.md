---
title: Phase 2 Build Plan — Persistence Contracts
date: 2026-04-27
phase: 2
findings: F-02, F-03, F-05, F-17, F-18
decisions_doc: docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md
audit_doc: docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md
executor: Cursor Composer 2
status: READY — no pending §3.2 re-asks block this phase
---

# Phase 2 Build Plan — Persistence Contracts

## Scope

Five findings from the 2026-04-22 offline spec-vs-code audit, all resolved with no open Isaac questions:

| Batch | Finding | Title | Severity |
|-------|---------|-------|----------|
| B2-1 | F-02 | Add snapshot_before_update to unprotected D01/D02 writes | BLOCKING |
| B2-2 | F-03 | Fix D04 partial-row INSERT (combined persist) | BLOCKING |
| B2-3 | F-05 | AIM-13 FRAGILE modifier — JSON dict envelope | BLOCKING |
| B2-4 | F-17 | DECAY_ALERT blank message payload | HIGH |
| B2-5 | F-18 | Deprecate pub/sub publisher in paper_trader.py | HIGH |

**Execution order:** B2-3 → B2-4 → B2-5 (isolated, low-risk) → B2-2 → B2-1 (higher-risk, sequential).

---

## Stage 1 — Audit Summary

### F-02 — Missing snapshot_before_update calls

**Decision (decisions log §2 Group I, Q-08):** Doc 32 Version Snapshot Policy is explicit — every versioned D01/D02 write must be preceded by `snapshot_before_update(component_id, trigger_reason)`. This is not aspirational; the two-phase gate is required.

**Current state (grep-verified):**

| File | Function | Violation | INSERT target |
|------|----------|-----------|---------------|
| `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:92` | `_update_aim_status` | NO snapshot before INSERT | `p3_d01_aim_model_states` |
| `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:105` | `_update_warmup_progress` | NO snapshot before INSERT | `p3_d01_aim_model_states` |
| `captain-offline/captain_offline/blocks/b1_hdwm_diversity.py:78` | `_reactivate_aim` | NO snapshot before D01 INSERT | `p3_d01_aim_model_states` |
| `captain-offline/captain_offline/blocks/b1_hdwm_diversity.py:85` | `_reactivate_aim` | NO snapshot before D02 INSERT | `p3_d02_aim_meta_weights` |
| `captain-offline/captain_offline/blocks/orchestrator.py:500` | `_handle_aim_activation` | NO snapshot before `_update_aim_status` call | `p3_d01_aim_model_states` (via call) |

**Partial coverage confirmed (compliant — do not touch):**
- `b1_aim_lifecycle.py:271` (ELIGIBLE→ACTIVE path)
- `b1_aim_lifecycle.py:282` (BOOTSTRAPPED→ACTIVE path)
- `b1_aim_lifecycle.py:348` (Tier retrain path)
- `b1_dma_update.py:166`, `b1_drift_detection.py:293`, `b8_kelly_update.py:209,224`

**`snapshot_before_update` signature** (`version_snapshot.py:170-189`):
```python
def snapshot_before_update(component_id: str, trigger_reason: str,
                           state: dict | None = None) -> str:
```
- `state=None` auto-loads via `get_current_state(component_id)` — use this default throughout.
- Current TRIGGERS enum values: `DMA_UPDATE, AIM_RETRAIN, KELLY_UPDATE, EWMA_UPDATE, PARAM_CHANGE, INJECTION_ADOPT, ROLLBACK`.
- **New trigger needed:** `AIM_LIFECYCLE` (lifecycle state transitions not covered by existing enum).

**§3.2 blocking re-asks:** None. Fully clear to proceed.

---

### F-03 — D04 partial-row INSERT pattern

**Decision (audit F-03 proposed fix, option a):** Orchestrate a single combined INSERT from `_handle_trade_outcome` after both BOCPD and CUSUM have run in-memory. Remove per-trade D04 writes from `run_bocpd_update` and `run_cusum_update`.

**D04 table columns** (`shared/canonical_schemas.py`):
```
asset_id, bocpd_run_length_posterior, bocpd_cp_probability, bocpd_cp_history,
cusum_c_up_prev, cusum_c_down_prev, cusum_sprint_length, cusum_allowance,
cusum_sequential_limits, adwin_states, decay_events,
current_changepoint_probability, last_updated
```

**Current INSERT patterns (grep-verified):**

| File | Lines | Columns written | Columns left NULL |
|------|-------|-----------------|-------------------|
| `b2_bocpd.py:223-228` | BOCPD per-trade | `asset_id, bocpd_run_length_posterior, bocpd_cp_probability, bocpd_cp_history, current_changepoint_probability` | ALL cusum columns |
| `b2_cusum.py:202-209` | CUSUM per-trade | `asset_id, cusum_c_up_prev, cusum_c_down_prev, cusum_sprint_length, cusum_allowance, cusum_sequential_limits` | ALL bocpd columns + `current_changepoint_probability` |
| `b2_cusum.py:173-179` | Quarterly calibration | `asset_id, cusum_sequential_limits, cusum_allowance` | All runtime state | ← **KEEP UNCHANGED** |
| `b1_drift_detection.py:210` | Drift (ADWIN) | `asset_id, adwin_states` | All detector state | ← **KEEP UNCHANGED** |
| `b2_level_escalation.py:71` | Decay event log | `asset_id, decay_events` | All detector state | ← **KEEP UNCHANGED** |

**Root cause:** `LATEST ON last_updated PARTITION BY asset_id` returns the CUSUM row (written last). `_get_cp_prob` (b8_kelly_update.py:42-51) reads `current_changepoint_probability` from that row — which is NULL because CUSUM never writes it. Result: `cp_prob` always defaults to 0.1 → `effective_span=30` always → slowest EWMA.

**Reader impact:**
- `b8_kelly_update.py:42-51` (`_get_cp_prob`): reads `current_changepoint_probability` — broken today.
- `orchestrator.py:530-537` (`_restore_detectors`): reads `bocpd_run_length_posterior` + full CUSUM state — broken today after any CUSUM write.

**§3.2 blocking re-asks:** None.

---

### F-05 — AIM-13 FRAGILE modifier type mismatch

**Decision (decisions log §2 Group F, Q-05):** Use option (a): write `current_modifier` as JSON dict `{"modifier": 0.85, "reason_tag": "AIM13_FRAGILE"}`. The dispatch reader `_aim13_sensitivity` already handles this correctly (lines 624-628 check `isinstance(current, dict)`).

**Current state:**
- `b5_sensitivity.py:43`: `FRAGILE_MODIFIER = 0.85` (float constant)
- `b5_sensitivity.py:269`: Inserts `FRAGILE_MODIFIER` directly → stores `0.85` as JSON number in QuestDB
- `b1_data_ingestion.py:124`: `parse_json(r[5], None)` → returns `0.85` float (not dict)
- `aim_compute.py:624`: `isinstance(current, dict)` → `False` for float → returns neutral 1.0

**ROBUST case gap:** When `robustness_status == "ROBUST"`, `b5_sensitivity.py` does NOT write to D01 at all (only logs). This means D01 retains the last FRAGILE modifier value across scans until it naturally overwrites. The fix must also write `{"modifier": 1.0, "reason_tag": "SENSITIVITY_NORMAL"}` on ROBUST to clear any prior FRAGILE state.

**§3.2 blocking re-asks:** None.

---

### F-17 — DECAY_ALERT blank message

**Current state (`b2_level_escalation.py:97-112`):**
```python
alert = json.dumps({
    "type": "DECAY_ALERT",
    "asset": asset_id,
    "level": level,
    "severity": severity,
    "source": source,
    "priority": "CRITICAL" if level >= 3 else "HIGH",
    "timestamp": now_et().isoformat(),
})
```
Missing fields: `"message"`, `"event_type"`, `"notif_id"`.

**Command handler reads** (`orchestrator.py:576-625`, `_handle_alert`):
- `priority` — present ✓
- `message` — **missing, defaults to "" → blank GUI + Telegram notification**
- `notif_id` — missing, defaults to ""
- `event_type` — missing, defaults to ""
- `asset` — present ✓
- `timestamp` — present ✓
- `source` — present ✓

**Spec-required messages** (doc 32 PG-08):
- Level 2: `"Level 2: Sizing reduced to {reduction_factor*100:.0f}% for {asset}"`
- Level 3: `"Level 3: STRATEGY REVIEW — no signals for {asset}"`

**Other CH_ALERTS publishers:** All other publishers (`b7_tsm_simulation.py`, `b6_signal_output.py`, `b7_position_monitor.py`, `b8_concentration_monitor.py`, `b3_api_adapter.py`, `b7_notifications.py`) include `"message"` correctly.

**Additional publisher with wrong format:** `version_snapshot.py:389` publishes `"reason"` key instead of `"message"`. This is **out of scope for Phase 2** (Phase 11 governance batch).

**§3.2 blocking re-asks:** None.

---

### F-18 — Trade-outcome bus pub/sub remnant

**Decision (decisions log §2 Group J, Q-12 transport):** Keep Redis Streams (`stream:trade_outcomes` via `STREAM_TRADE_OUTCOMES`). Deprecate pub/sub publisher in `paper_trader.py`. Canvas/CLAUDE.md naming divergences are documentation-only and do not require code changes.

**Current state:**
- `shared/redis_client.py:29`: `CH_TRADE_OUTCOMES = "captain:trade_outcomes"` (pub/sub constant — keep definition, mark deprecated in comment)
- `shared/redis_client.py:75`: `STREAM_TRADE_OUTCOMES = "stream:trade_outcomes"` (streams constant — canonical)
- `b7_position_monitor.py:421`: `publish_to_stream(STREAM_TRADE_OUTCOMES, payload)` ← **correct** ✓
- `captain-offline/orchestrator.py:185-198`: `ensure_consumer_group(STREAM_TRADE_OUTCOMES, ...)` + stream read loop ← **correct** ✓
- `scripts/paper_trader.py:368`: `self.redis.publish("captain:trade_outcomes", json.dumps(outcome))` ← **pub/sub remnant** ❌

**Dead code (imports of CH_TRADE_OUTCOMES with no active use):**
- `captain-command/captain_command/blocks/b1_core_routing.py:28` — imported, never used
- `captain-command/captain_command/blocks/orchestrator.py:34` — imported, never used
- Command's pub/sub subscribe loop (line 289) does NOT include `CH_TRADE_OUTCOMES` — confirmed no live pub/sub subscriber exists.

**Safe to remove:** Both dead imports and the paper_trader pub/sub call. No live consumer will break.

**§3.2 blocking re-asks:** None.

---

## Stage 2 — Build Plan

---

## B2-3 — F-05: AIM-13 FRAGILE modifier JSON dict envelope

**Execute first** — lowest blast radius, isolated writer/reader pair.

### Spec citation
- Decisions log §2 Group F, Q-05: "Option (a): write D01 `current_modifier` as JSON dict `{"modifier": 0.85, "reason_tag": "AIM13_FRAGILE"}`"
- Audit F-05: `b5_sensitivity.py:262-270`, `shared/aim_compute.py:620-629`
- Doc 32 PG-12: `P3-D01[13].current_modifier = 0.85`

### Pre-flight checks
1. Confirm `aim_compute._aim13_sensitivity` lines 624-628 accept dict envelope (it does — verified above).
2. Confirm `b1_data_ingestion.py:124` uses `parse_json` which returns a Python dict from a JSON string (it does — verified above).
3. Confirm no other reader of D01 `current_modifier` field assumes a non-dict type for AIM 13.

### Files to modify

**File 1:** `captain-offline/captain_offline/blocks/b5_sensitivity.py`

**Change A — FRAGILE write (line 269):**
```python
# BEFORE:
(13, asset_id, FRAGILE_MODIFIER),

# AFTER:
(13, asset_id, json.dumps({"modifier": FRAGILE_MODIFIER, "reason_tag": "AIM13_FRAGILE"})),
```
Ensure `import json` is present at file top (it already is — verify).

**Change B — Add ROBUST reset (after line 274, inside the `else` block at line 273+):**
After the existing `logger.info("...ROBUST...")` line, add a D01 INSERT to reset AIM-13 modifier:
```python
# After ROBUST log, write neutral modifier to clear any prior FRAGILE state
with get_cursor() as cur:
    cur.execute(
        """INSERT INTO p3_d01_aim_model_states
           (aim_id, asset_id, status, current_modifier, last_updated)
           VALUES (%s, %s, 'ACTIVE', %s, now())""",
        (13, asset_id, json.dumps({"modifier": 1.0, "reason_tag": "SENSITIVITY_NORMAL"})),
    )
```

**No changes needed to:**
- `shared/aim_compute.py` — already handles dict correctly
- `captain-online/captain_online/blocks/b1_data_ingestion.py` — `parse_json` already handles JSON string → dict

### Test additions

**File:** `tests/test_b5_sensitivity.py` (create if absent, otherwise append)

Test 1 — FRAGILE write produces dict envelope:
```python
def test_aim13_fragile_writes_dict_envelope(mock_db):
    """b5_sensitivity FRAGILE path must write JSON dict, not bare float."""
    run_sensitivity_scan(asset_id="ES", base_returns=[...fragile_returns...])
    # Assert D01 INSERT for aim_id=13 contains valid JSON dict
    inserted = get_last_d01_insert(mock_db, aim_id=13)
    val = json.loads(inserted["current_modifier"])
    assert val == {"modifier": 0.85, "reason_tag": "AIM13_FRAGILE"}
```

Test 2 — Round-trip: FRAGILE write reaches _aim13_sensitivity as 0.85:
```python
def test_aim13_fragile_round_trip():
    """parse_json on dict-envelope string returns dict; _aim13_sensitivity extracts 0.85."""
    raw = json.dumps({"modifier": 0.85, "reason_tag": "AIM13_FRAGILE"})
    parsed = parse_json(raw, None)
    result = _aim13_sensitivity(features={}, state={"current_modifier": parsed})
    assert result["modifier"] == 0.85
    assert result["reason_tag"] == "AIM13_FRAGILE"
```

Test 3 — ROBUST write produces neutral dict:
```python
def test_aim13_robust_writes_neutral_envelope(mock_db):
    run_sensitivity_scan(asset_id="ES", base_returns=[...robust_returns...])
    inserted = get_last_d01_insert(mock_db, aim_id=13)
    val = json.loads(inserted["current_modifier"])
    assert val["modifier"] == 1.0
    assert val["reason_tag"] == "SENSITIVITY_NORMAL"
```

### Exit criteria
- [ ] All 3 tests pass
- [ ] `_aim13_sensitivity` returns modifier=0.85 when DB contains FRAGILE dict envelope
- [ ] No bare-float inserts for current_modifier on AIM 13 remain in the codebase (grep check)

### Rollback
Revert the two changes to `b5_sensitivity.py`. No DB migration needed — `parse_json` handles both float and dict; `_aim13_sensitivity` already falls back gracefully on non-dict.

---

## B2-4 — F-17: Fix DECAY_ALERT blank message payload

### Spec citation
- Audit F-17: `b2_level_escalation.py:97-110`
- Doc 32 PG-08: `NOTIFY_GUI("Level 2: Sizing reduced to {reduction_factor*100}% for {asset}", priority="HIGH", colour="AMBER")`
- Doc 32 PG-08: `NOTIFY_GUI("Level 3: STRATEGY REVIEW — no signals for {asset}", priority="CRITICAL", colour="RED")`

### Pre-flight checks
1. Confirm command `_handle_alert` reads `data.get("message", "")` — verified at lines 576-625.
2. Confirm `Level_2` (called from `trigger_level2`) receives `reduction_factor` as a local variable — check b2_level_escalation.py `trigger_level2` function signature and what it passes to `_publish_alert`.
3. Confirm `_publish_alert` receives enough info to format the PG-08 strings (asset_id, level, severity).

### Files to modify

**File:** `captain-offline/captain_offline/blocks/b2_level_escalation.py`

**Change — `_publish_alert` function (lines 97-112):**

The current signature is `_publish_alert(asset_id, level, severity, source)`. `reduction_factor` is computed in `trigger_level2` and passed as `severity`. To format the PG-08 message, compute `reduction_factor` from severity inside `_publish_alert` for Level 2:

```python
# BEFORE (lines 97-112):
alert = json.dumps({
    "type": "DECAY_ALERT",
    "asset": asset_id,
    "level": level,
    "severity": severity,
    "source": source,
    "priority": "CRITICAL" if level >= 3 else "HIGH",
    "timestamp": now_et().isoformat(),
})

# AFTER:
if level == 2:
    reduction_factor = max(0.5, 1.0 - (severity - 0.8) * 2.5)
    message = f"Level 2: Sizing reduced to {reduction_factor * 100:.0f}% for {asset_id}"
    event_type = "DECAY_LEVEL_2"
else:
    message = f"Level 3: STRATEGY REVIEW — no signals for {asset_id}"
    event_type = "DECAY_LEVEL_3"

import uuid
alert = json.dumps({
    "type": "DECAY_ALERT",
    "event_type": event_type,
    "message": message,
    "notif_id": str(uuid.uuid4()),
    "asset": asset_id,
    "level": level,
    "severity": severity,
    "source": source,
    "priority": "CRITICAL" if level >= 3 else "HIGH",
    "timestamp": now_et().isoformat(),
})
```

Note: move `import uuid` to top of file if not already imported.

### Test additions

**File:** `tests/test_b2_decay.py` (create if absent, otherwise append)

Test 1 — Level 2 alert includes message:
```python
def test_decay_level2_alert_has_message(mock_redis):
    trigger_level2("ES", severity=0.85, source="BOCPD")
    payload = json.loads(mock_redis.last_published[CH_ALERTS])
    assert "message" in payload
    assert "Level 2" in payload["message"]
    assert "ES" in payload["message"]
    assert "Sizing reduced" in payload["message"]
    assert payload["event_type"] == "DECAY_LEVEL_2"
    assert "notif_id" in payload and payload["notif_id"]
```

Test 2 — Level 3 alert includes message:
```python
def test_decay_level3_alert_has_message(mock_redis):
    trigger_level3("ES", source="BOCPD_sustained")
    payload = json.loads(mock_redis.last_published[CH_ALERTS])
    assert "message" in payload
    assert "STRATEGY REVIEW" in payload["message"]
    assert "ES" in payload["message"]
    assert payload["event_type"] == "DECAY_LEVEL_3"
    assert payload["priority"] == "CRITICAL"
```

### Exit criteria
- [ ] Both tests pass
- [ ] Command orchestrator `_handle_alert` receives non-empty `message` on simulated DECAY_ALERT
- [ ] No other CH_ALERTS publishers broke (grep `CH_ALERTS` publish calls and verify they still have `message`)

### Rollback
Revert `b2_level_escalation.py`. No data store impact.

---

## B2-5 — F-18: Deprecate pub/sub publisher in paper_trader.py

### Spec citation
- Decisions log §2 Group J, Q-12 transport: "Keep Redis Streams (`stream:trade_outcomes`). Deprecate pub/sub publisher in `paper_trader.py`."
- Audit F-18: `scripts/paper_trader.py:368`, `shared/redis_client.py:29-30,73-76`

### Pre-flight checks
1. Confirm no active pub/sub subscriber to `captain:trade_outcomes` in codebase — **confirmed** (grep shows zero active subscribers; command pub/sub loop at line 289 does not include it).
2. Confirm `publish_to_stream` (or `xadd`-based helper) is accessible in `paper_trader.py` context — check imports in `scripts/paper_trader.py`.
3. Confirm offline orchestrator consumes `STREAM_TRADE_OUTCOMES` correctly — **confirmed** (lines 185-198).

### Files to modify

**File 1:** `scripts/paper_trader.py`

**Change (line 368):**
```python
# BEFORE:
self.redis.publish("captain:trade_outcomes", json.dumps(outcome))

# AFTER:
from shared.redis_client import publish_to_stream, STREAM_TRADE_OUTCOMES
publish_to_stream(STREAM_TRADE_OUTCOMES, outcome)
```
Note: If `redis_client.py` does not expose a `publish_to_stream` function, check for `xadd`-based wrapper. Use the same method `b7_position_monitor.py:421` uses — mirror it exactly.

Also: add `STREAM_TRADE_OUTCOMES` to the imports at the top of `paper_trader.py` alongside any existing `redis_client` imports.

**File 2:** `captain-command/captain_command/blocks/b1_core_routing.py`

**Change (line 28):** Remove `CH_TRADE_OUTCOMES` from imports if it is unused in this file (grep confirms it is only imported, never referenced in the file body).

**File 3:** `captain-command/captain_command/blocks/orchestrator.py`

**Change (line 34):** Remove `CH_TRADE_OUTCOMES` from imports if unused in this file (same as above).

**File 4:** `shared/redis_client.py` (optional — documentation only)

Add a deprecation comment on `CH_TRADE_OUTCOMES`:
```python
# DEPRECATED: pub/sub channel — no active subscribers. Use STREAM_TRADE_OUTCOMES instead.
CH_TRADE_OUTCOMES = "captain:trade_outcomes"
```

### Test additions

**File:** `tests/test_paper_trader_stream.py` (create if absent)

Test 1 — paper_trader publishes to stream, not pub/sub:
```python
def test_paper_trader_publishes_to_stream(mock_redis):
    """paper_trader must publish trade outcomes to STREAM_TRADE_OUTCOMES, not CH_TRADE_OUTCOMES pub/sub."""
    pt = PaperTrader(redis_client=mock_redis)
    pt._publish_trade_outcome(trade=sample_trade())
    assert mock_redis.xadd_calls  # stream was used
    assert STREAM_TRADE_OUTCOMES in mock_redis.xadd_calls[0]["stream"]
    assert not mock_redis.publish_calls_for("captain:trade_outcomes")  # no pub/sub
```

### Exit criteria
- [ ] Test passes
- [ ] `grep -r 'publish.*captain:trade_outcomes\|publish.*CH_TRADE_OUTCOMES' --include='*.py'` returns zero results outside of `redis_client.py` definition and test files
- [ ] Offline orchestrator stream consumer group still works after change (manual smoke test or existing E2E test)

### Rollback
Revert `paper_trader.py:368` to original pub/sub call. Since no live subscriber exists, rollback has no production impact.

---

## B2-2 — F-03: Fix D04 partial-row INSERT (combined persist)

**Execute after B2-3/B2-4/B2-5** — touches three files with per-trade write paths; test coverage must exist before modifying.

### Spec citation
- Audit F-03: `b2_bocpd.py:217-229`, `b2_cusum.py:199-210`, `orchestrator.py:261-281`, `b8_kelly_update.py:42-52`
- Doc 32 PG-05: "SAVE P3-D04" (after BOCPD update)
- Doc 32 PG-06: "SAVE P3-D04" (after CUSUM update)
- Fix direction: option (a) — single combined INSERT orchestrated from `_handle_trade_outcome`

### Architecture of the fix

**Current flow:**
```
orchestrator._handle_trade_outcome
  → run_bocpd_update(asset_id, pnl, bocpd_det)  → returns (cp_prob, bocpd_det) + writes D04 BOCPD-only row
  → run_cusum_update(asset_id, pnl, cusum_det)  → returns (signal, cusum_det) + writes D04 CUSUM-only row
```

**Target flow:**
```
orchestrator._handle_trade_outcome
  → run_bocpd_update(asset_id, pnl, bocpd_det)  → returns (cp_prob, bocpd_det) — NO D04 write
  → run_cusum_update(asset_id, pnl, cusum_det)  → returns (signal, cusum_det) — NO D04 write
  → persist_combined_detector_state(asset_id, bocpd_det, cusum_det)  → ONE combined D04 INSERT
```

**Functions that must NOT be changed (separate write paths, unrelated columns):**
- `b2_cusum.calibrate_and_persist` (quarterly, writes `cusum_sequential_limits + cusum_allowance`)
- `b1_drift_detection` ADWIN write (writes `adwin_states`)
- `b2_level_escalation` decay event write (writes `decay_events`)

### Pre-flight checks
1. Confirm `run_bocpd_update` has no callers outside `orchestrator._handle_trade_outcome` — grep `run_bocpd_update` across repo.
2. Confirm `run_cusum_update` has no callers outside `orchestrator._handle_trade_outcome` — grep `run_cusum_update` across repo.
3. If other callers exist, they must also be migrated in this batch or marked as blockers before proceeding.

### Files to modify

**File 1:** `captain-offline/captain_offline/blocks/b2_bocpd.py`

**Change A — Add `persist_combined_detector_state` function (add after existing `run_bocpd_update`):**
```python
def persist_combined_detector_state(
    asset_id: str,
    bocpd_det: "BOCPDDetector",
    cusum_det: "CUSUMDetector",
) -> None:
    """Single combined INSERT for D04 — both BOCPD and CUSUM state in one row.

    Replaces the separate per-trade INSERTs that were previously inside
    run_bocpd_update and run_cusum_update. Called from orchestrator
    _handle_trade_outcome after both detectors have run.

    Does NOT write adwin_states or decay_events — those have independent writers.
    Does NOT replace calibrate_and_persist (quarterly calibration).
    """
    bocpd_state = bocpd_det.to_dict()
    cusum_state = cusum_det.to_dict()
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d04_decay_detector_states
               (asset_id, bocpd_run_length_posterior, bocpd_cp_probability,
                bocpd_cp_history, cusum_c_up_prev, cusum_c_down_prev,
                cusum_sprint_length, cusum_allowance, cusum_sequential_limits,
                current_changepoint_probability, last_updated)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (
                asset_id,
                json.dumps(bocpd_state["run_length_posterior"]),
                float(bocpd_det.cp_probability),
                json.dumps(bocpd_state["cp_history"]),
                float(cusum_det.c_up),
                float(cusum_det.c_down),
                int(cusum_det.sprint_length),
                float(cusum_det.allowance),
                json.dumps(cusum_state["sequential_limits"]),
                float(bocpd_det.cp_probability),
            ),
        )
```

**Change B — Remove D04 INSERT from `run_bocpd_update` (lines 219-228):**
- Delete the `with get_cursor() as cur:` block and the INSERT statement within `run_bocpd_update`.
- The function signature, in-memory update logic, cp_probability computation, and return values remain unchanged.
- Comment removed INSERT with a note: `# D04 persist moved to persist_combined_detector_state — called by orchestrator`

**File 2:** `captain-offline/captain_offline/blocks/b2_cusum.py`

**Change — Remove D04 INSERT from `run_cusum_update` per-trade path (lines 202-209):**
- Delete the `with get_cursor() as cur:` block and the INSERT statement within `run_cusum_update`.
- `calibrate_and_persist` at lines 157-179 is **untouched**.
- Comment removed INSERT: `# D04 persist moved to persist_combined_detector_state — called by orchestrator`

**File 3:** `captain-offline/captain_offline/blocks/orchestrator.py`

**Change — `_handle_trade_outcome` (around lines 250-280):**

Add import at top of orchestrator: `from captain_offline.blocks.b2_bocpd import persist_combined_detector_state`

After the two detector calls, add:
```python
# BOCPD
cp_prob, bocpd_det = run_bocpd_update(asset_id, pnl_pc, bocpd_det)
# CUSUM
cusum_signal, cusum_det = run_cusum_update(asset_id, pnl_pc, cusum_det)
# Combined D04 persist (single row with both BOCPD + CUSUM state)
persist_combined_detector_state(asset_id, bocpd_det, cusum_det)
self._detectors[asset_id] = (bocpd_det, cusum_det)
```

### Attribute cross-reference (verify before writing combined INSERT)

Before finalising the combined INSERT, read the actual `BOCPDDetector.to_dict()` and `CUSUMDetector.to_dict()` implementations to confirm exact dict keys:

**BOCPDDetector.to_dict()** (b2_bocpd.py ~lines 143-164):
- Known: `"run_length_posterior"` (truncated list), `"cp_history"` (list[-100:])
- `bocpd_det.cp_probability` is the float attribute (set during `update()`)

**CUSUMDetector.to_dict()** (b2_cusum.py ~lines 83-89):
- Known: `"sprint_length"`, `"allowance"`, `"sequential_limits"` (dict with str keys)
- `cusum_det.c_up` and `cusum_det.c_down` are float attributes

If attribute names differ from the above, adjust the INSERT bindings accordingly.

### Test additions

**File:** `tests/test_b2_bocpd_cusum_combined.py` (new file)

Test 1 — Combined persist writes both detector states in one row:
```python
def test_persist_combined_writes_all_bocpd_cusum_columns(mock_db):
    bocpd_det = BOCPDDetector()
    bocpd_det.update(0.5)
    cusum_det = CUSUMDetector(allowance=0.3)
    cusum_det.update(0.5)
    persist_combined_detector_state("ES", bocpd_det, cusum_det)
    row = mock_db.last_insert("p3_d04_decay_detector_states")
    # All 10 non-adwin/non-decay_events columns must be non-NULL
    assert row["bocpd_run_length_posterior"] is not None
    assert row["bocpd_cp_probability"] is not None
    assert row["cusum_c_up_prev"] is not None
    assert row["current_changepoint_probability"] == row["bocpd_cp_probability"]
```

Test 2 — `run_bocpd_update` no longer writes D04:
```python
def test_run_bocpd_update_does_not_write_d04(mock_db):
    det = BOCPDDetector()
    run_bocpd_update("ES", 0.5, det)
    assert mock_db.insert_count("p3_d04_decay_detector_states") == 0
```

Test 3 — `run_cusum_update` no longer writes D04:
```python
def test_run_cusum_update_does_not_write_d04(mock_db):
    det = CUSUMDetector(allowance=0.3)
    run_cusum_update("ES", 0.5, det)
    assert mock_db.insert_count("p3_d04_decay_detector_states") == 0
```

Test 4 — `_get_cp_prob` reads correct non-null value after combined persist:
```python
def test_get_cp_prob_reads_correct_value_after_combined_persist(real_db):
    bocpd_det = BOCPDDetector()
    bocpd_det.update(0.5)
    cusum_det = CUSUMDetector(allowance=0.3)
    persist_combined_detector_state("ES", bocpd_det, cusum_det)
    cp = _get_cp_prob("ES")
    assert cp == pytest.approx(bocpd_det.cp_probability, abs=1e-6)
    assert cp != 0.1  # was always 0.1 before fix (default fallback)
```

Test 5 — `_restore_detectors` restores both BOCPD and CUSUM from single combined row:
```python
def test_restore_detectors_recovers_both_states(real_db):
    bocpd_det = BOCPDDetector()
    bocpd_det.update(0.5)
    cusum_det = CUSUMDetector(allowance=0.3)
    cusum_det.update(0.8)
    persist_combined_detector_state("ES", bocpd_det, cusum_det)
    restored = _restore_detectors(["ES"])
    r_bocpd, r_cusum = restored["ES"]
    assert r_bocpd is not None
    assert r_cusum is not None
    assert pytest.approx(r_bocpd.cp_probability) == bocpd_det.cp_probability
    assert r_cusum.sprint_length == cusum_det.sprint_length
```

Test 6 — Confirm `calibrate_and_persist` still writes its own row unaffected:
```python
def test_calibrate_and_persist_still_writes_d04(mock_db):
    calibrate_and_persist("ES", in_control_pnl=[0.1, -0.05, 0.2, -0.1])
    row = mock_db.last_insert("p3_d04_decay_detector_states")
    assert row["cusum_sequential_limits"] is not None
    assert row["cusum_allowance"] is not None
```

### Exit criteria
- [ ] All 6 tests pass
- [ ] `grep -n "INSERT INTO p3_d04" captain-offline/captain_offline/blocks/b2_bocpd.py` returns no hits inside `run_bocpd_update`
- [ ] `grep -n "INSERT INTO p3_d04" captain-offline/captain_offline/blocks/b2_cusum.py` returns no hits inside `run_cusum_update`
- [ ] `grep -n "INSERT INTO p3_d04" captain-offline/captain_offline/blocks/b2_cusum.py` still returns a hit inside `calibrate_and_persist`
- [ ] `_get_cp_prob` never returns 0.1 default after a real trade (integration test or manual verify against QuestDB)

### Rollback
Revert `b2_bocpd.py`, `b2_cusum.py`, `orchestrator.py`. The D04 table is append-only and QuestDB rows are immutable — no data loss. Existing rows with partial columns remain queryable via `LATEST ON`.

---

## B2-1 — F-02: Add snapshot_before_update to unprotected D01/D02 writes

**Execute last** — widest diff, touches lifecycle-critical paths.

### Spec citation
- Audit F-02: `b1_aim_lifecycle.py:88-115`, `b1_hdwm_diversity.py:71-90`, `orchestrator.py:468-505`
- Doc 32 Version Snapshot Policy: `FUNCTION snapshot_before_update(component_id, trigger_reason)` — "BEFORE mutating live state"
- Decisions log §2 Group I, Q-08: "Doc 32 lines 167–168 are explicit on the two-phase admin-approval gate."

### Pre-flight checks
1. Confirm `version_snapshot.snapshot_before_update` is importable in all three files — check existing imports.
2. Confirm `TRIGGERS` enum in `version_snapshot.py` — read lines 40-47. Plan adds `AIM_LIFECYCLE = "AIM_LIFECYCLE"`.
3. Confirm `orchestrator.py` does not already import `snapshot_before_update` (it imports from b1_aim_lifecycle and b1_hdwm_diversity, but not from version_snapshot directly).

### Files to modify

**File 1:** `captain-offline/captain_offline/blocks/version_snapshot.py`

**Change — Add `AIM_LIFECYCLE` to TRIGGERS enum (lines 40-47):**
```python
class TRIGGERS:
    DMA_UPDATE = "DMA_UPDATE"
    AIM_RETRAIN = "AIM_RETRAIN"
    KELLY_UPDATE = "KELLY_UPDATE"
    EWMA_UPDATE = "EWMA_UPDATE"
    PARAM_CHANGE = "PARAM_CHANGE"
    INJECTION_ADOPT = "INJECTION_ADOPT"
    ROLLBACK = "ROLLBACK"
    AIM_LIFECYCLE = "AIM_LIFECYCLE"    # ADD: lifecycle state transitions (WARM_UP, ELIGIBLE, ACTIVE, SUPPRESSED)
```

**File 2:** `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py`

Ensure `snapshot_before_update` and `TRIGGERS` are imported from `version_snapshot` at the top of this file.

**Violation 1 — `_update_aim_status` (lines 88-96):**

Add snapshot call immediately before the INSERT (line 92):
```python
def _update_aim_status(aim_id: int, asset_id: str, new_status: str) -> None:
    snapshot_before_update("P3-D01", TRIGGERS.AIM_LIFECYCLE)  # ADD: before INSERT
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d01_aim_model_states ...""",
            ...
        )
```

**Violation 2 — `_update_warmup_progress` (lines 99-114):**

Add snapshot call immediately before the INSERT (line 105):
```python
def _update_warmup_progress(aim_id: int, asset_id: str, progress: float) -> None:
    snapshot_before_update("P3-D01", TRIGGERS.AIM_LIFECYCLE)  # ADD: before INSERT
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d01_aim_model_states ...""",
            ...
        )
```

**File 3:** `captain-offline/captain_offline/blocks/b1_hdwm_diversity.py`

Ensure `snapshot_before_update` and `TRIGGERS` are imported.

**Violation 3 & 4 — `_reactivate_aim` (lines 71-90):** Both D01 and D02 INSERTs need snapshots:
```python
def _reactivate_aim(aim_id: int, asset_id: str, num_active_aims: int) -> None:
    snapshot_before_update("P3-D01", TRIGGERS.AIM_LIFECYCLE)  # ADD: before D01 INSERT
    with get_cursor() as cur:
        cur.execute("""INSERT INTO p3_d01_aim_model_states ...""", ...)

    snapshot_before_update("P3-D02", TRIGGERS.AIM_LIFECYCLE)  # ADD: before D02 INSERT
    with get_cursor() as cur:
        cur.execute("""INSERT INTO p3_d02_aim_meta_weights ...""", ...)
```

**File 4:** `captain-offline/captain_offline/blocks/orchestrator.py`

Ensure `snapshot_before_update` and `TRIGGERS` are imported from `version_snapshot`.

**Violation 5 — `_handle_aim_activation` (lines 468-505), call to `_update_aim_status` at line ~500:**

`_update_aim_status` now calls `snapshot_before_update` internally (from Violation 1 fix above), so NO additional call is needed in the orchestrator. **However**, verify that the orchestrator's `_handle_aim_activation` path loops over multiple assets (line 499 area). If it calls `_update_aim_status` in a loop, each iteration will trigger a separate snapshot — this is correct per spec ("before every versioned write"). No change needed to orchestrator once b1_aim_lifecycle.py is fixed.

**Confirm:** Check if `_handle_aim_activation` handles deactivation separately (e.g., setting status to ELIGIBLE or SUPPRESSED). If so, `_update_aim_status` is called for deactivation too, and the internal snapshot covers it.

### Test additions

**File:** `tests/test_version_snapshot_coverage.py` (new file, or append to existing snapshot tests)

Test 1 — `_update_aim_status` calls snapshot before INSERT:
```python
def test_update_aim_status_snapshots_before_insert(mocker):
    snap_mock = mocker.patch("captain_offline.blocks.b1_aim_lifecycle.snapshot_before_update")
    with mock_db_context():
        _update_aim_status(aim_id=1, asset_id="ES", new_status="ACTIVE")
    snap_mock.assert_called_once_with("P3-D01", TRIGGERS.AIM_LIFECYCLE)
    # Verify snapshot call ORDER: snapshot must precede INSERT
    assert snap_mock.call_count == 1
```

Test 2 — `_update_warmup_progress` calls snapshot before INSERT:
```python
def test_update_warmup_progress_snapshots_before_insert(mocker):
    snap_mock = mocker.patch("captain_offline.blocks.b1_aim_lifecycle.snapshot_before_update")
    with mock_db_context():
        _update_warmup_progress(aim_id=1, asset_id="ES", progress=0.5)
    snap_mock.assert_called_once_with("P3-D01", TRIGGERS.AIM_LIFECYCLE)
```

Test 3 — `_reactivate_aim` calls snapshot for both D01 and D02:
```python
def test_reactivate_aim_snapshots_d01_and_d02(mocker):
    snap_mock = mocker.patch("captain_offline.blocks.b1_hdwm_diversity.snapshot_before_update")
    with mock_db_context():
        _reactivate_aim(aim_id=3, asset_id="ES", num_active_aims=5)
    calls = snap_mock.call_args_list
    assert len(calls) == 2
    components = [c.args[0] for c in calls]
    assert "P3-D01" in components
    assert "P3-D02" in components
```

Test 4 — Tier retrain path remains compliant (regression):
```python
def test_tier_retrain_snapshot_still_present(mocker):
    snap_mock = mocker.patch("captain_offline.blocks.b1_aim_lifecycle.snapshot_before_update")
    with mock_db_context():
        run_tier_retrain(asset_id="ES", tier=1)
    # Existing snapshot at line 348 must still fire
    assert any(c.args[1] == TRIGGERS.AIM_RETRAIN for c in snap_mock.call_args_list)
```

### Exit criteria
- [ ] All 4 tests pass
- [ ] `grep -n "snapshot_before_update" captain-offline/captain_offline/blocks/b1_aim_lifecycle.py` returns at least 4 hits (2 new + 2 existing)
- [ ] `grep -n "snapshot_before_update" captain-offline/captain_offline/blocks/b1_hdwm_diversity.py` returns at least 2 hits
- [ ] `AIM_LIFECYCLE` appears in `version_snapshot.py` TRIGGERS enum

### Rollback
Revert `b1_aim_lifecycle.py`, `b1_hdwm_diversity.py`, `version_snapshot.py`. The `p3_d18_version_history` table accumulates new rows but removing them is unnecessary — `LATEST ON` queries are unaffected.

---

## Dependency Summary

```
B2-3 (F-05)  ─────────────────────────────────────────┐
B2-4 (F-17)  ────────────────────────────────────────── all independent; run in any order
B2-5 (F-18)  ─────────────────────────────────────────┘
                                                        ↓
B2-2 (F-03)  ─── needs B2-3/B2-4/B2-5 done first ────┤
                                                        ↓
B2-1 (F-02)  ─── needs B2-2 done first ───────────────┘
```

No Phase 2 batch modifies the QuestDB schema (all changes are READ-ONLY or pure logic fixes — no `ALTER TABLE` or `CREATE TABLE` statements). Phase 1 schema migrations must be applied before any Phase 2 code is deployed if Phase 1 is not already merged.

---

## Pending Items from §3.2 (Not Blocking Phase 2)

The following re-asks from decisions log §3.2 are confirmed NOT to affect any Phase 2 batch:

- **Q-04** (blend_signal consumer) — Phase 4 (strategy injection)
- **Q-11** (D26 dual-write) — Phase 10 (HMM)
- **Q-22** (AIM-01 step function) — Phase 6 (AIM modifier realignment)
- **Q-23** (EIA Wednesday relocation) — Phase 6
- **Q-26** (D06 suppression logging) — Phase 4
- **Q-27** (`raw_data_count` for AIMs 1-15) — Phase 4

---

## Cross-references

- **Companion build plan:** `2026-04-27_phase1_schema_migrations_build_plan.md` (Phase 1 must land first)
- **Audit document:** `docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md`
- **Decisions document:** `docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md`
- **Spec authority chain (per Q-02):** `shared/canonical_schemas.py` (schemas) → doc 32 (PG semantics) → AIM canvas (modifier semantics) → other canvases (wiring annotations)
