# Batch 3 — F5 + §8.3: Jitter Symmetry Confirmation + Trail-Block Observability

**Generated:** 2026-05-19 (planning + execution, Sonnet 4.6)
**Status:** EXECUTED — code changes applied, tests green, commit and push complete.
**Severity:** LOW — F5 is structurally resolved by Batch 1 (jitter_j now threads from B6 to position dict). §8.3 adds observability that would have flagged F2 on the first NKD trade. Both fixes are additive only — no phase-math or ratchet logic changed.
**Source audit:** [`REJECTED_ORDERS_AUDIT.md`](REJECTED_ORDERS_AUDIT.md) §0 F5, §4.2, §5.2, §8.2, §8.3.
**Build plan:** [`BUILD_PLAN.md`](BUILD_PLAN.md) §4 "Batch 3".
**Batch 1 plan:** [`BATCH_1_F2_F3_TRAIL_FORWARDING.md`](BATCH_1_F2_F3_TRAIL_FORWARDING.md) §3 Edit Site D (what `_handle_taken_skipped` changed).
**Workspace rules:** [`.cursor/rules/captain-deploy-and-tower-discipline.mdc`](../../../../../.cursor/rules/captain-deploy-and-tower-discipline.mdc) §1 (dual-remote push).

---

## 1. Summary

**§8.3 silent-skip log:** `scan_nkd_trails` currently `continue`s past every NKD position where `is_nkd_trail=False` without emitting any log evidence — the empty D34 table was the only post-hoc signal that the trail had been inert for an entire 22h trade. The fix adds one `skipped_inert` counter, incremented only when the skipped position has `asset == "NKD"`, and emits a single aggregate INFO line at the end of the scan loop if `skipped_inert > 0`. This would have fired on the very first poll after the APAC TAKEN on 2026-05-18, giving an immediate diagnostic before the operator even checked D34.

**F5 + §8.2 Isaac CRITICAL alert:** After Batch 1, `jitter_j` is threaded from B6 through the position dict, so the first-poll defence-in-depth re-sampler at `_scan_one_trail:660` becomes a no-op on the normal path (`first_poll is False`). If it fires — meaning `jitter_j` arrived as `None` — on an Isaac tower (`parity_env == "1"`), that proves the B6→position-dict thread has regressed, because a fresh `J_b ≠ J_a` (B6's TP bracket J), violating Isaac's "one signed J per trade" spec (audit §8.2, memory anchor #3343). The fix emits a CRITICAL `NKD_TRAIL_JITTER_MISSING` alert via `_emit_alert` *before* re-sampling so the operator has an immediate signal to roll back Batch 1. The re-sampling itself is fully preserved as defence-in-depth: even with a regression, the position is never unprotected.

---

## 2. Edit Site A: `scan_nkd_trails` silent-skip log (§8.3 fix)

**File:** [`captain-online/captain_online/blocks/b7b_nkd_trail.py`](../../../../../captain-online/captain_online/blocks/b7b_nkd_trail.py)
**Post-edit anchor lines:** 530-565

### Sub-edit A1 — counter initialisation + NKD-asset check in skip branch

**BEFORE (original lines 530–534):**
```python
    seen_signal_ids: set[str] = set()

    for pos in (open_positions or []):
        if not pos.get("is_nkd_trail"):
            continue
```

**AFTER (lines 530–537):**
```python
    seen_signal_ids: set[str] = set()
    skipped_inert = 0

    for pos in (open_positions or []):
        if not pos.get("is_nkd_trail"):
            if (pos.get("asset") or "").upper() == "NKD":
                skipped_inert += 1
            continue
```

### Sub-edit A2 — aggregate INFO log before `_purge_prev_pnl`

**BEFORE (original lines 555–556):**
```python
    _purge_prev_pnl(seen_signal_ids)
    return diagnostics
```

**AFTER (lines 558–565):**
```python
    if skipped_inert > 0:
        logger.info(
            "ON-B7B-NKD: scan saw %d NKD position(s) with is_nkd_trail=False — "
            "trail logic inert for those positions; verify F2 fix is on tower",
            skipped_inert,
        )
    _purge_prev_pnl(seen_signal_ids)
    return diagnostics
```

**Format rationale:** `"ON-B7B-NKD: ..."` prefix matches all 12+ existing log calls in the module (verified by grep). `%d` `%`-style formatting matches module convention. Single aggregate log line per scan cycle prevents log spam when N positions are skipped simultaneously — the total count `skipped_inert` communicates severity without N repeated lines.

---

## 3. Edit Site B: CRITICAL alert before first-poll re-sample (F5/§8.2 fix)

**File:** [`captain-online/captain_online/blocks/b7b_nkd_trail.py`](../../../../../captain-online/captain_online/blocks/b7b_nkd_trail.py)
**Post-edit anchor lines:** 667–692

**BEFORE (original lines 658–669):**
```python
    jitter_j_raw = pos.get("jitter_j")
    first_poll = jitter_j_raw is None
    if first_poll:
        x, y, j = sample_isaac_jitter(parity_env)
        pos["jitter_x"] = x
        pos["jitter_y"] = y
        pos["jitter_j"] = j
        jitter_j = j
        logger.info(
            "ON-B7B-NKD: jitter sampled signal=%s parity=%s X=%s Y=%d J=%s",
            sig_id, parity_env or "0", x, y, j,
        )
```

**AFTER (lines 667–692):**
```python
    jitter_j_raw = pos.get("jitter_j")
    first_poll = jitter_j_raw is None
    if first_poll:
        # Alert on Isaac tower: post-Batch-1 (F2 fix), jitter_j must arrive
        # pre-populated from B6 via the position dict. If it is still None on
        # the first poll, B6->position-dict threading has regressed and the SL
        # trail will use a different J from the TP bracket price (audit §8.2).
        # Defence-in-depth re-sampling below still protects the position.
        if parity_env == "1":
            _emit_alert(
                redis_client, user_id, "CRITICAL", "NKD_TRAIL_JITTER_MISSING",
                f"NKD trail: jitter_j absent from position dict on first poll "
                f"(Isaac tower, signal={sig_id}). B6->position-dict threading "
                f"may have regressed; SL will use a fresh J that differs from "
                f"the TP bracket J. Re-sampling now (defence-in-depth).",
                {"signal_id": sig_id, "asset": asset},
            )
        x, y, j = sample_isaac_jitter(parity_env)
        pos["jitter_x"] = x
        pos["jitter_y"] = y
        pos["jitter_j"] = j
        jitter_j = j
        logger.info(
            "ON-B7B-NKD: jitter sampled signal=%s parity=%s X=%s Y=%d J=%s",
            sig_id, parity_env or "0", x, y, j,
        )
```

**Key constraints honoured:** `_emit_alert` call signature `(redis_client, user_id, priority, event_type, message, extra)` matches the two existing calls at lines 601-606 and 613-619 in `_scan_one_trail`. The re-sample block (`x, y, j = sample_isaac_jitter(parity_env)`) is fully preserved and still executes after the alert. Phase-math and ratchet logic untouched.

---

## 4. New tests

### 4.1 `tests/test_b7b_nkd_trail.py` — `TestScanObservability` (2 new methods)

Added class after `TestComputeStopPrice`. Uses `pytest.caplog` with `logging.INFO` and logger `captain_online.blocks.b7b_nkd_trail`.

**`test_scan_logs_when_nkd_position_skipped`**: Injects one NKD position dict with `is_nkd_trail=False` (overriding the helper's `True` default). Captures log at INFO. Asserts exactly 1 record containing `"is_nkd_trail=False"` and that the message contains `"1 NKD position(s)"`.

**`test_scan_does_not_log_when_no_nkd_positions`**: Two sub-cases: (a) empty position list and (b) an ES position with `is_nkd_trail=False`. Asserts zero records containing `"is_nkd_trail=False"` in both cases, confirming the counter only fires for NKD assets.

### 4.2 `tests/test_b7b_isaac_jitter_stress.py` — `TestJitterMissingAlert` (2 new methods)

Added class after `TestEffectiveBufferJitter`. Calls `scan_nkd_trails(...)` directly (not via `_scan` helper which hard-codes `redis_client=None`) to inject a `MagicMock()` redis_client. Sets `mock_redis.hget.return_value = None` so `_mirror_position_to_redis` early-returns without decoding.

**`test_first_poll_critical_alert_when_jitter_missing_on_isaac`**: `parity_env="1"`, `jitter_j=None`. Asserts `mock_redis.publish.called`, then parses `call_args_list` JSON payloads to find exactly one call where `event_type == "NKD_TRAIL_JITTER_MISSING"` and `priority == "CRITICAL"`. Asserts `pos["jitter_j"] != Decimal("0")` after the scan, proving defence-in-depth re-sampling ran and produced a non-zero Isaac J.

**`test_first_poll_no_alert_on_nomaan`**: `parity_env=""`, `jitter_j=None`. Asserts zero `NKD_TRAIL_JITTER_MISSING` events in `publish.call_args_list`. Asserts `pos["jitter_j"] == Decimal("0")` (Nomaan's J is always zero from `sample_isaac_jitter("")`).

---

## 5. Validation gate output

```
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -m pytest tests/test_b7b_nkd_trail.py \
    tests/test_b7b_isaac_jitter_stress.py \
    tests/test_nkd_jitter_lifecycle.py -v

============================= 101 passed in 1.25s ==============================
```

| Test file | Baseline | New | Result |
|---|---|---|---|
| `tests/test_b7b_nkd_trail.py` | 46 | +2 | **48 passed / 0 failed** |
| `tests/test_b7b_isaac_jitter_stress.py` | 47 | +2 | **49 passed / 0 failed** |
| `tests/test_nkd_jitter_lifecycle.py` | 4 | 0 | **4 passed / 0 failed** |
| **TOTAL** | **97** | **+4** | **101 passed / 0 failed** |

---

## 6. Risk register

- **R1 — Log spam from many skipped positions**: mitigated by the single aggregate `skipped_inert` counter — N simultaneous skipped NKD positions produce exactly 1 INFO line, not N lines.
- **R2 — `_emit_alert` mock signature mismatch in tests**: the `_emit_alert` call uses `(redis_client, user_id, "CRITICAL", "NKD_TRAIL_JITTER_MISSING", message, {"signal_id": sig_id, "asset": asset})` — matches the existing calls at b7b lines 601-606 and 613-619 exactly. Test assertions inspect `redis_client.publish.call_args_list` JSON payloads, not the `_emit_alert` mock itself, so the signature contract is automatically enforced at runtime.
- **R3 — `caplog` not capturing INFO log**: resolved by `caplog.at_level(logging.INFO, logger="captain_online.blocks.b7b_nkd_trail")` scope — confirmed by `logger = logging.getLogger(__name__)` at b7b line 55.
- **R4 — `parity_env="0"` vs `parity_env=""`**: `sample_isaac_jitter` treats any non-`"1"` string as Nomaan; both produce `J=Decimal("0")`. Test 4 uses `parity_env=""` (real default from `os.environ.get("INSTANCE_PARITY", "")`), matching `_scan_one_trail`'s guard `if parity_env == "1":`.
- **R5 — `_mirror_position_to_redis` decoding the raw MagicMock**: fixed by `mock_redis.hget.return_value = None` in alert tests so `_mirror_position_to_redis` early-returns at the `if existing_raw is None: return` guard (b7b line 966).

---

## 7. Completion checklist

### Pre-flight
- [x] Pre-flight gate — Batch 1 (`c23b68b`, F2/F3) and Batch 2 (`441671d`, F4) verified on both `origin/main` and `multi-user/main` before any edits.

### Code edits (2 edit sites in 1 file)
- [x] **Edit Site A1** applied to `captain-online/captain_online/blocks/b7b_nkd_trail.py:530`: `skipped_inert = 0` initialised alongside `seen_signal_ids: set[str] = set()`. Anchor: `skipped_inert += 1` inside `if (pos.get("asset") or "").upper() == "NKD":` block at line 536.
- [x] **Edit Site A2** applied to `captain-online/captain_online/blocks/b7b_nkd_trail.py:558`: `if skipped_inert > 0: logger.info("ON-B7B-NKD: scan saw %d NKD position(s) with is_nkd_trail=False — trail logic inert for those positions; verify F2 fix is on tower", skipped_inert)` inserted before `_purge_prev_pnl`. Anchor: `"verify F2 fix is on tower"` at line 561.
- [x] **Edit Site B** applied to `captain-online/captain_online/blocks/b7b_nkd_trail.py:669`: `if parity_env == "1": _emit_alert(redis_client, user_id, "CRITICAL", "NKD_TRAIL_JITTER_MISSING", ...)` inserted inside `if first_poll:` block, BEFORE `x, y, j = sample_isaac_jitter(parity_env)`. Re-sampling block unchanged and still executes. Anchor: `"NKD_TRAIL_JITTER_MISSING"` at line 677. Comment cites `audit §8.2`.
- [x] No phase-math, ratchet, or `_emit_alert` signature changes.

### New tests
- [x] `tests/test_b7b_nkd_trail.py`: added `import logging` at top; added `TestScanObservability` class with `test_scan_logs_when_nkd_position_skipped` and `test_scan_does_not_log_when_no_nkd_positions`.
- [x] `tests/test_b7b_isaac_jitter_stress.py`: added `import json` at top; added `TestJitterMissingAlert` class with `test_first_poll_critical_alert_when_jitter_missing_on_isaac` and `test_first_poll_no_alert_on_nomaan`. Both tests configure `mock_redis.hget.return_value = None` to avoid `_mirror_position_to_redis` decode error.

### Validation gate
- [x] `pytest tests/test_b7b_nkd_trail.py tests/test_b7b_isaac_jitter_stress.py tests/test_nkd_jitter_lifecycle.py -v` — **101 passed / 0 failed / 0 errors** (48 + 49 + 4).

### Commit + push
- [x] Single atomic commit with conventional-commits message (see §8 below).
- [x] Commit SHA: *(filled in post-commit)*
- [x] `git push origin HEAD` — succeeded.
- [x] `git push multi-user HEAD` — succeeded.
- [x] Post-push SHA parity verified: local == origin/main == multi-user/main → `OK: both remotes synced`.

### Sample log output (new INFO line)
When a NKD position with `is_nkd_trail=False` exists at poll time, the following appears in `captain-online` logs:
```
ON-B7B-NKD: scan saw 1 NKD position(s) with is_nkd_trail=False — trail logic inert for those positions; verify F2 fix is on tower
```

### Sample alert payload (CRITICAL, from test assertion)
When Isaac tower has `jitter_j=None` on first poll:
```json
{
  "user_id": "primary_user",
  "priority": "CRITICAL",
  "event_type": "NKD_TRAIL_JITTER_MISSING",
  "message": "NKD trail: jitter_j absent from position dict on first poll (Isaac tower, signal=SIG-JITSTRESS-0001). B6->position-dict threading may have regressed; SL will use a fresh J that differs from the TP bracket J. Re-sampling now (defence-in-depth).",
  "source": "ON-B7B-NKD",
  "timestamp": "...",
  "signal_id": "SIG-JITSTRESS-0001",
  "asset": "NKD"
}
```

---

## 8. Commit message

```
feat(b7b_nkd_trail): observability for inert trail + missing-jitter (F5/§8.3)

Adds an INFO aggregate log line per scan_nkd_trails poll when one or
more NKD positions are skipped due to is_nkd_trail=False (would have
flagged F2 on the first NKD trade). Adds a CRITICAL alert
NKD_TRAIL_JITTER_MISSING when the first-poll defence-in-depth
sampler fires on Isaac tower (parity_env="1") — that path indicates
B6->position-dict threading has regressed. Defence-in-depth
re-sampling is preserved so the position is never unprotected.

Refs: docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/REJECTED_ORDERS_AUDIT.md
      §4.2, §8.2, §8.3
```

---

## 9. Cross-references

- Audit: [`REJECTED_ORDERS_AUDIT.md`](REJECTED_ORDERS_AUDIT.md) §0 F5, §4.2, §5.2, §8.2, §8.3
- Build plan: [`BUILD_PLAN.md`](BUILD_PLAN.md) §4 "Batch 3"
- Batch 1 plan: [`BATCH_1_F2_F3_TRAIL_FORWARDING.md`](BATCH_1_F2_F3_TRAIL_FORWARDING.md) §3 Edit Site D
- Workspace rules: [`.cursor/rules/captain-deploy-and-tower-discipline.mdc`](../../../../../.cursor/rules/captain-deploy-and-tower-discipline.mdc)

---

**End of Batch 3 plan.**
