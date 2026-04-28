---
title: Phase 3 Build Plan — Orchestrator Wiring & Dispatch
date: 2026-04-27
phase: 3 of 12
companion_to:
  - docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md
  - docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md
  - docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md
  - docs2/spec-docs-02/offline/P3 Offline copy.md
  - docs2/spec-docs-02/offline/P3_online.md
findings_addressed: [F-01, F-04, F-13, F-20, F-21, F-42]
status: ready_for_cursor_composer_2
blocked_batches: [B2_F-04]
---

# Phase 3 — Orchestrator Wiring & Dispatch

## 0. Audit Pass (Stage 1) — Read-Only Summary

This section captures the wiring state observed in code at the time of plan authoring. Each finding row links the current dispatch shape to the resolution in the decisions log §2 and the canonical spec.

### 0.1 Findings overview

| F-ID | Severity | Decisions log row | Spec authority | Wiring state in code | Phase 3 disposition |
|---|---|---|---|---|---|
| F-01 | BLOCKING | §2 Group B / Q-03 (resolved) | doc 32 lines 86–88 (PG-01C); doc 22 §6 | `train_aim16_hmm` exists at `b1_aim16_hmm.py:64`; `save_hmm_state` at `b1_aim16_hmm.py:166`; **zero callers** repo-wide | **Skeleton wire** only. Phase 10 fills HMM internals. |
| F-04 | BLOCKING | §2 Group C / Q-04 (PARTIAL — re-ask in §3.2) | doc 32 PG-11 (lines 414–441) | `TransitionPhaser.blend_signal` at `b4_injection.py:207`; **zero callers**; `p3_d06b_active_transitions` table exists but is unread by Online | **BLOCKED**. Awaits Isaac confirmation that consumer is Online B6. |
| F-13 | HIGH | not in §2 (silent) — follow audit | doc 32 PG-04 (lines 199–213) | `_run_daily` at `orchestrator.py:911` calls `run_drift_detection`; `b1_drift_detection.py:269–333` builds features from D01 modifier JSON, skips unfitted AE | Wire fix in Phase 3. |
| F-20 | HIGH | not in §2 (silent) — follow audit | doc 32 PG-07 (lines 287–306) | `_run_quarterly` at `orchestrator.py:995–1017` calls `calibrate_and_persist` only; `_init_cusum_calibration` at `orchestrator.py:577–629` is the in-memory load path; `self._detectors` is never refreshed quarterly | Wire fix in Phase 3. |
| F-21 | HIGH (reclassified) | §2 Group E / Q-13 (resolved — by-design) | doc 32 PG-08 (line 328) | `b2_level_escalation.py:166–168` enqueues `P1P2_RERUN`; `orchestrator.py:700` sets `AWAITING_MANUAL` and logs warning | **Doc edit only.** No production code change. |
| F-42 | HIGH | not in §2 (silent) — follow audit | `P3 Offline.canvas` Block 6 ("TRIGGER: L3 decay") | `b2_level_escalation.py:171–172` enqueues `AIM14_EXPANSION`; `_dispatch_pending_jobs` is only called from `_run_daily` (`orchestrator.py:920`), giving up to ~24h latency | Wire fix in Phase 3. |

### 0.2 PG-01C cadence confirmation (Q-03)

Decisions log §2 Group B: **"PG-01C runs after every market trading session, globally (not per asset). One shared HMM, retrained at each session close (NY, LON, APAC). Add post-session hook to orchestrator (not weekly cron)."**

Current state in code:
- Offline `_run_scheduler` (`captain-offline/.../orchestrator.py:822–867`) is time-based with daily/weekly/monthly/quarterly gates only — **no session-aware tick**.
- Online `_run_session(session_id)` (`captain-online/.../orchestrator.py:239`) runs the per-session pipeline but **does not publish any session-close event** on `STREAM_COMMANDS` or any other channel.
- `STREAM_COMMANDS` consumer group `GROUP_OFFLINE_COMMANDS` is wired (`offline/orchestrator.py:186, 210, 214`); Online publishes nothing onto it today.

Implication for Phase 3 wiring (F-01): Online must emit a `SESSION_CLOSE` command at the end of `_run_session`, and Offline must add a `_handle_session_close` branch in `_handle_command` that dispatches a global PG-01C run. The HMM internals stay stubbed in this phase per the constraint "F-01 lands here in skeleton form; Phase 10 makes it semantically correct."

### 0.3 F-04 §3.2 re-ask status

Decisions log §3.2 Q-04 reads: *"Need explicit confirmation of (a) the consumer location is Online B6, and (b) PG-11 writes `p3_d06b_active_transitions` and Online B6 reads it."*

As of plan authoring (2026-04-27), Isaac has **not** answered this re-ask. Per the phase-specific constraint, batch B2 (F-04) is marked **BLOCKED**. The other batches proceed.

### 0.4 F-21 doc-edit confirmation (Q-13)

Decisions log §2 Group E / Q-13: *"`AWAITING_MANUAL` is the correct terminal state. The spec wording `SCHEDULE programs_1_2_rerun(asset)` is aspirational; no automation target exists."*

Required doc edits (Phase 3 only):
1. **`docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` line 328** — change `SCHEDULE programs_1_2_rerun(asset)` to `MANUAL programs_1_2_rerun(asset)` (or add `# AWAITING_MANUAL — no automation target` annotation).
2. **`docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md` F-21 entry** — append `**Resolution:** by-design per Q-13 (decisions log 2026-04-27); no code change.` and reclassify severity from HIGH to RESOLVED.

Code touch scope: **none**. The Phase 3 audit pass surfaced no residual issue beyond the doc drift.

### 0.5 Caller / callee table (affected dispatch paths)

| Path | Callers (file:line) | Callees (file:line) | Trigger |
|---|---|---|---|
| AIM-16 HMM training | none (target: new `_handle_session_close` in offline orchestrator) | `b1_aim16_hmm.train_aim16_hmm` (L64), `b1_aim16_hmm.save_hmm_state` (L166) | post-session via Online publish |
| Strategy transition blending | none today (target Phase 4+: Online B6) | `b4_injection.TransitionPhaser.blend_signal` (L207) | per-tick during transition window |
| Drift detection daily | `_run_daily` at offline `orchestrator.py:911` | `b1_drift_detection.run_drift_detection` (L269) | daily 16:00 ET |
| CUSUM quarterly recalibration | `_run_quarterly` at offline `orchestrator.py:995–1017` | `b2_cusum.calibrate_and_persist`; missing: in-memory refresh into `self._detectors[asset_id][1].sequential_limits` | quarterly Jan/Apr/Jul/Oct |
| Level 2 / Level 3 dispatch | `_handle_trade_outcome` at offline `orchestrator.py:281, 371` → `check_level_escalation` (`b2_level_escalation.py:179`) → `trigger_level3` (L155) → enqueue (L171) | dispatch only via `_run_daily` → `_dispatch_pending_jobs` (`orchestrator.py:920`) | trade outcome event |

---

## 1. Stage 2 — Plan Generation

### 1.1 Spec authority chain (recap)

Decisions log §2 supersedes audit; audit supersedes spec; spec supersedes code. Where decisions log is silent (F-13, F-20, F-42), follow audit. Never invent a third option.

### 1.2 Phase 3 batches at a glance

| # | Batch ID | Title | Severity | Status |
|---|---|---|---|---|
| 1 | B1_F-01 | Skeleton-wire PG-01C dispatch (post-session hook + offline command branch) | BLOCKING | READY |
| 2 | B2_F-04 | Wire `blend_signal` consumer (Online B6 reads `p3_d06b_active_transitions`) | BLOCKING | **BLOCKED on §3.2 re-ask Q-04** |
| 3 | B3_F-13 | PG-04 drift uses real AIM input features and trained autoencoders | HIGH | READY |
| 4 | B4_F-20 | Quarterly PG-07 refreshes in-memory CUSUM detectors after persist | HIGH | READY |
| 5 | B5_F-21 | Doc-edit reclassification — `AWAITING_MANUAL` is by-design | HIGH (reclassified) | READY (doc-only) |
| 6 | B6_F-42 | L3 trigger dispatches `AIM14_EXPANSION` immediately, not on daily tick | HIGH | READY |

> Adjust file paths and exact line numbers from the audit pass (Stage 1) before each edit. Line numbers cited below are accurate as of `git rev-parse HEAD` at plan authoring; they may have drifted by the time Cursor executes — re-anchor with `grep -n` rather than relying on the integer.

---

## 2. Batch 1 — `B1_F-01`: Skeleton-wire PG-01C dispatch

**Severity:** BLOCKING. **Status:** READY.

### 2.1 Spec citation
- Decisions log §2 Group B / Q-03 (resolved): post-session global cadence; one shared HMM at NY/LON/APAC close.
- Audit `F-01` (BLOCKING): `train_aim16_hmm` and `save_hmm_state` are unreachable.
- Pseudocode `32_P3_Offline_Full_Pseudocode.md` lines 86–88; cross-ref doc 22 §6.
- Canvas `P3 Offline.canvas` Block 1 — `MODULE: hmm_trainer.py. DEPS: hmmlearn`.
- Online dispatch reference: `P3_online.md` block diagram — no current session-close emission.

### 2.2 Pre-flight checks
1. `grep -n "train_aim16_hmm\|save_hmm_state" -r captain-offline/ captain-online/ shared/` returns only the definition site (`b1_aim16_hmm.py:64, 166`). If any other caller has appeared, STOP and re-anchor.
2. Confirm `STREAM_COMMANDS` consumer-group wiring in offline orchestrator at `captain-offline/captain_offline/blocks/orchestrator.py:186, 210` is unchanged.
3. Confirm `shared/redis_client.py` already exposes `STREAM_COMMANDS = "stream:commands"` (verified at `redis_client.py:76`).
4. Confirm Online `_run_session` at `captain-online/captain_online/blocks/orchestrator.py:239` does not already publish to `STREAM_COMMANDS`.
5. **Phase 10 boundary** — confirm with Cursor that this batch only wires; the observation panel and Baum-Welch fit stay stubbed.

### 2.3 Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-online/captain_online/blocks/orchestrator.py` | end of `_run_session` (currently `~L380` block) | publish `SESSION_CLOSE` command after session pipeline finishes |
| `captain-offline/captain_offline/blocks/orchestrator.py` | `_handle_command` (L404–429) | route `cmd_type == "SESSION_CLOSE"` to new `_handle_session_close` |
| `captain-offline/captain_offline/blocks/orchestrator.py` | new method block, place after `_handle_aim_activation` (after L505) | add `_handle_session_close(payload)` and `_run_aim16_hmm_training(session_id, closed_at)` skeleton |
| `captain-offline/captain_offline/blocks/b1_aim16_hmm.py` | new module-level helper after L186 | add `build_observation_panel_stub(asset_universe, lookback_days=60) -> Tuple[np.ndarray, np.ndarray, int]` returning shape-correct zeros + `n_trading_days=0` so cold-start path triggers |
| `captain-offline/captain_offline/main.py` | (optional) add `SESSION_CLOSE` to startup log line | no functional change |

### 2.4 Exact change shape (before → after)

**A. Online publish (new — `captain-online/.../orchestrator.py` near end of `_run_session`):**

```python
# BEFORE: _run_session returns after B6 signal output, no Offline notification

# AFTER: append at end of _run_session(session_id)
from shared.redis_client import publish_to_stream, STREAM_COMMANDS
publish_to_stream(STREAM_COMMANDS, {
    "cmd_type": "SESSION_CLOSE",
    "session_id": int(session_id),
    "closed_at": _utc_now_iso(),
    "source": "captain-online.orchestrator._run_session",
})
self.logger.info(f"[session_close] published SESSION_CLOSE for session_id={session_id}")
```

**B. Offline route (`captain-offline/.../orchestrator.py:404–429`):**

```python
# BEFORE
def _handle_command(self, payload: dict) -> None:
    cmd_type = payload.get("cmd_type")
    if cmd_type == "INJECTION":
        self._handle_injection(payload)
    elif cmd_type == "ADOPTION":
        self._handle_adoption(payload)
    elif cmd_type == "AIM_ACTIVATION":
        self._handle_aim_activation(payload)
    else:
        self.logger.warning(f"unknown cmd_type={cmd_type}")

# AFTER — add SESSION_CLOSE branch
def _handle_command(self, payload: dict) -> None:
    cmd_type = payload.get("cmd_type")
    if cmd_type == "INJECTION":
        self._handle_injection(payload)
    elif cmd_type == "ADOPTION":
        self._handle_adoption(payload)
    elif cmd_type == "AIM_ACTIVATION":
        self._handle_aim_activation(payload)
    elif cmd_type == "SESSION_CLOSE":
        self._handle_session_close(payload)
    else:
        self.logger.warning(f"unknown cmd_type={cmd_type}")
```

**C. Offline new methods (skeleton):**

```python
def _handle_session_close(self, payload: dict) -> None:
    """PG-01C dispatch entry per Q-03 — post-session global cadence."""
    session_id = int(payload.get("session_id", -1))
    closed_at = payload.get("closed_at", "")
    self.logger.info(
        f"[pg01c] session_close received session_id={session_id} "
        f"closed_at={closed_at}; dispatching AIM-16 HMM training (skeleton)"
    )
    try:
        self._run_aim16_hmm_training(session_id, closed_at)
    except Exception as exc:
        self.logger.exception(f"[pg01c] training dispatch failed: {exc}")

def _run_aim16_hmm_training(self, session_id: int, closed_at: str) -> None:
    """SKELETON wiring per Phase 3 plan §B1_F-01.

    Phase 10 replaces the stub observation panel with the real 7-D panel
    (doc 22 §4) and rewires the cold-start logic. Today this exists only
    so the dispatch path is reachable and end-to-end tests can assert the
    write to P3-D26 occurs at session close.
    """
    from captain_offline.blocks.b1_aim16_hmm import (
        train_aim16_hmm,
        save_hmm_state,
        build_observation_panel_stub,
    )
    obs, session_pnl, n_days = build_observation_panel_stub(self._asset_universe)
    state = train_aim16_hmm(
        observations=obs,
        session_pnl=session_pnl,
        n_trading_days=n_days,
    )
    save_hmm_state(state, conn=self._questdb_conn(), session_id=session_id)
    self.logger.info(
        f"[pg01c] HMM state persisted session_id={session_id} "
        f"n_trading_days={n_days} (cold-start={n_days < 20})"
    )
```

**D. `b1_aim16_hmm.py` stub helper (skeleton observation builder):**

```python
def build_observation_panel_stub(asset_universe) -> tuple[np.ndarray, np.ndarray, int]:
    """Phase 3 placeholder. Phase 10 replaces with the doc 22 §4 panel.

    Returns shape-correct zeros so train_aim16_hmm hits its cold-start
    branch (n_trading_days < 20 → equal-prob output) without raising.
    """
    obs = np.zeros((0, 7), dtype=float)
    session_pnl = np.zeros((0,), dtype=float)
    return obs, session_pnl, 0
```

> Cursor: this is intentionally minimal. Do **not** wire a real observation builder, do **not** import hmmlearn data structures — Phase 10 owns those.

### 2.5 Test additions

| File | Test |
|---|---|
| `tests/test_offline_session_close_dispatch.py` (new) | `test_session_close_command_dispatches_pg01c` — publish `SESSION_CLOSE` to `STREAM_COMMANDS`, assert `_run_aim16_hmm_training` is called once and `save_hmm_state` writes one D26 row in cold-start mode |
| `tests/test_offline_session_close_dispatch.py` | `test_session_close_idempotent_on_duplicate` — publish two `SESSION_CLOSE` messages with the same `session_id`+`closed_at`; assert second call no-ops or writes deterministically (Phase 10 may tighten this) |
| `tests/test_online_session_close_publish.py` (new) | `test_run_session_publishes_session_close` — mock `publish_to_stream`, run `_run_session(session_id=1)`, assert one publish with `cmd_type="SESSION_CLOSE"` and matching `session_id` |
| `tests/test_pipeline_e2e.py` | extend the existing E2E to assert that one `SESSION_CLOSE` and one D26 row appear per session in the run window |

Assertions to include: dispatch order (online publish → offline ack → train called → save called), cadence (one PG-01C per `_run_session` completion, not one per asset), idempotency on session_id repeat.

### 2.6 Exit criteria

1. `grep -rn "SESSION_CLOSE" captain-online/ captain-offline/` shows publish + handler.
2. New unit tests pass under the standard `PYTHONPATH=...` invocation (see CLAUDE.md).
3. `train_aim16_hmm` is reachable from a live process (verifiable via `docker compose logs captain-offline | grep pg01c`).
4. Phase 10 hand-off note is present: a TODO comment in `_run_aim16_hmm_training` points to `docs2/audits/2026-03-27_Build_Plans_1-12/<phase10-plan>` once that plan is authored.

### 2.7 Rollback procedure

1. Revert the offline `_handle_command` branch and remove `_handle_session_close` / `_run_aim16_hmm_training`.
2. Revert the online `_run_session` publish call.
3. Remove `build_observation_panel_stub` from `b1_aim16_hmm.py`.
4. Drop new test files. Leave existing tests untouched.
5. Restart `captain-online` and `captain-offline` containers — no schema change to roll back.

---

## 3. Batch 2 — `B2_F-04`: Wire `blend_signal` consumer

**Severity:** BLOCKING. **Status:** 🚫 BLOCKED on Isaac re-ask Q-04 (decisions log §3.2).

### 3.1 Why blocked
Decisions log §3.2 (Q-04) requires explicit Isaac confirmation that:
- (a) the consumer of `blend_signal` is Online B6, **and**
- (b) Offline PG-11 writes `p3_d06b_active_transitions` and Online B6 reads it.

Until both are confirmed, Phase 3 cannot author the consumer wiring without inventing a third option (forbidden by the spec authority chain rule).

### 3.2 Tentative shape (do not implement until unblocked)

If Isaac confirms the §3.2 reading:
- Reader = `captain-online/captain_online/blocks/b6_signal_output.py`. Add `_apply_active_transitions(signal)` that loads any active row from `p3_d06b_active_transitions` for the signal's asset and calls `TransitionPhaser.blend_signal(signal_new=signal, signal_old=...)`.
- Source for `signal_old` is the previous locked-strategy signal — needs a generator path; Phase 4 may own that.
- Writer = Offline `_handle_adoption` already calls `TransitionPhaser.save()` indirectly through `_active_transitions` / `_advance_transitions` — verify rows are landing in `p3_d06b_active_transitions` before declaring this batch done.

### 3.3 Pre-flight (run when unblocked)
1. Re-read decisions log §2 Group C and §3.2 Q-04 — copy the new answer verbatim into the batch header.
2. Confirm `p3_d06b_active_transitions` schema includes `weight_new`, `weight_old`, `transition_day`, `total_days`, `asset_id`, `is_active`.
3. `grep -rn "blend_signal\|p3_d06b_active_transitions" captain-online/ captain-offline/ shared/` to capture all touch points before editing.

### 3.4 Hand-off note
This batch lifts to Phase 3.5 or Phase 4 (Cursor's call) the moment Isaac answers. Do not stall the rest of Phase 3 waiting on it.

---

## 4. Batch 3 — `B3_F-13`: PG-04 drift uses real features and trained autoencoders

**Severity:** HIGH. **Status:** READY.

### 4.1 Spec citation
- Decisions log §2 — silent on F-13. Per the authority chain, follow audit.
- Audit `F-13` (HIGH).
- Pseudocode `32_P3_Offline_Full_Pseudocode.md` lines 199–213 (PG-04): `current_features = get_aim_input_features(a, today)`; `reconstruction_error = aim_autoencoder[a].reconstruct(current_features)`.

### 4.2 Pre-flight checks
1. Confirm trained autoencoder checkpoints exist on the deployment host (`models/ae_aim*.pt` or equivalent). If missing, surface as a separate ops task before starting.
2. `grep -n "get_aim_input_features\|aim_input_features" -r captain-offline/ captain-online/ shared/` to find the canonical feature loader (likely `shared/aim_feature_loader.py`).
3. Confirm `b1_drift_detection.SimpleAutoEncoder.fitted` is the correct guard flag (`b1_drift_detection.py:269–333`).

### 4.3 Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-offline/captain_offline/blocks/b1_drift_detection.py` | `run_drift_detection` (L269–333) | replace D01-modifier-JSON feature build with `shared.aim_feature_loader.load_aim_features(asset_id, aim_id, as_of=today)` per AIM |
| `captain-offline/captain_offline/blocks/b1_drift_detection.py` | autoencoder load path | bootstrap-fit (or load checkpoint) before the `if not ae.fitted: continue` skip; promote skip to a single warm-up gate at AIM-installation time, not per-tick |
| `captain-offline/captain_offline/blocks/orchestrator.py` | `_run_daily` call site (currently L911) | no signature change; ensure today's date is passed unambiguously (UTC-aware → America/New_York per CLAUDE.md timezone rule) |

### 4.4 Exact change shape (before → after)

```python
# BEFORE (b1_drift_detection.run_drift_detection, simplified)
for aim_id, state in aim_states.items():
    aim_features = _extract_features_from_modifier_json(state.current_modifier)
    if not autoencoder[aim_id].fitted:
        continue
    err = autoencoder[aim_id].reconstruct(aim_features)
    adwin[aim_id].add(err)
    ...

# AFTER
from shared.aim_feature_loader import load_aim_features

for aim_id, state in aim_states.items():
    aim_features = load_aim_features(asset_id=asset_id, aim_id=aim_id, as_of=today)
    if aim_features is None or len(aim_features) == 0:
        logger.debug(f"[pg04] no features for asset={asset_id} aim={aim_id} as_of={today}")
        continue
    ae = autoencoder[aim_id]
    if not ae.fitted:
        ae.bootstrap_fit(aim_features_history)  # one-shot fit during warm-up
        if not ae.fitted:
            logger.warning(f"[pg04] AE for aim={aim_id} still not fitted after bootstrap")
            continue
    err = ae.reconstruct(aim_features)
    adwin[aim_id].add(err)
    ...
```

### 4.5 Test additions

| File | Test |
|---|---|
| `tests/test_pg04_drift.py` (new or extend) | `test_drift_uses_questdb_features_not_modifier_json` — patch `load_aim_features` to a known vector, assert AE reconstruction error matches expected, assert no read of `current_modifier` JSON during the call |
| `tests/test_pg04_drift.py` | `test_unfitted_ae_bootstraps_on_first_call` — start with `fitted=False`, run drift, assert `fitted` flips to True and a reconstruction is computed |
| `tests/test_pg04_drift.py` | `test_drift_skips_when_no_features_available` — empty feature vector, assert clean continue without raising |

### 4.6 Exit criteria
1. `_run_daily` produces non-zero `reconstruction_error` for at least one ACTIVE AIM in the e2e replay run.
2. `P3-D02.inclusion_probability` halving on detected drift is exercised end-to-end (verifiable in `p3_d02_meta_weight_matrix` audit row).
3. New tests green.

### 4.7 Rollback procedure
1. Revert `b1_drift_detection.run_drift_detection` to the modifier-JSON path.
2. Remove `bootstrap_fit` call.
3. Drop new tests.
4. No schema change.

---

## 5. Batch 4 — `B4_F-20`: Quarterly PG-07 refreshes in-memory CUSUM

**Severity:** HIGH. **Status:** READY.

### 5.1 Spec citation
- Decisions log §2 — silent on F-20. Follow audit.
- Audit `F-20` (HIGH).
- Pseudocode `32_P3_Offline_Full_Pseudocode.md` lines 287–306 (PG-07).

### 5.2 Pre-flight checks
1. `grep -n "calibrate_and_persist\|sequential_limits" captain-offline/captain_offline/blocks/b2_cusum.py captain-offline/captain_offline/blocks/orchestrator.py` to anchor exact lines.
2. Confirm `_init_cusum_calibration` (`orchestrator.py:577–629`) is the canonical in-memory loader. If `calibrate_and_persist` already returns the limits dict, reuse; otherwise add a return value.
3. Confirm `self._detectors[asset_id]` is a `Tuple[BOCPDDetector, CUSUMDetector]` and `[1].sequential_limits` is the right attribute (verified via audit pass).

### 5.3 Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-offline/captain_offline/blocks/orchestrator.py` | `_run_quarterly` (L995–1017) | after each `calibrate_and_persist(asset_id)`, refresh `self._detectors[asset_id][1].sequential_limits` from the returned (or re-loaded) limits |
| `captain-offline/captain_offline/blocks/b2_cusum.py` | `calibrate_and_persist` signature | ensure return type includes the new `sequential_limits: Dict[int, float]` payload |

### 5.4 Exact change shape (before → after)

```python
# BEFORE (orchestrator._run_quarterly, simplified)
for asset_id in active_assets:
    calibrate_and_persist(asset_id, conn=self._questdb_conn())

# AFTER
for asset_id in active_assets:
    new_limits = calibrate_and_persist(asset_id, conn=self._questdb_conn())
    if new_limits and asset_id in self._detectors:
        self._detectors[asset_id][1].sequential_limits = dict(new_limits)
        self.logger.info(
            f"[pg07] refreshed in-memory CUSUM limits for {asset_id} "
            f"({len(new_limits)} sprint buckets)"
        )
    else:
        self.logger.warning(
            f"[pg07] recalibration ran but no in-memory detector to update for {asset_id}"
        )
```

### 5.5 Test additions

| File | Test |
|---|---|
| `tests/test_pg07_quarterly_recalibration.py` (new) | `test_quarterly_refreshes_in_memory_limits` — seed `self._detectors[asset_id][1].sequential_limits = {1: 0.1}`, run `_run_quarterly` with mocked `calibrate_and_persist` returning `{1: 0.5, 2: 0.6}`, assert in-memory dict matches the new return |
| `tests/test_pg07_quarterly_recalibration.py` | `test_quarterly_no_op_when_calibration_returns_empty` — return `{}`, assert in-memory dict unchanged and warning logged |
| `tests/test_b2_cusum.py` | extend to assert `calibrate_and_persist` returns the same dict it persists |

### 5.6 Exit criteria
1. After a synthetic quarterly run, `self._detectors[asset_id][1].sequential_limits` matches the latest persisted row.
2. New tests green.
3. No regression in `test_b2_cusum.py` baseline.

### 5.7 Rollback procedure
1. Revert `_run_quarterly` to ignore the return value.
2. Optionally revert `calibrate_and_persist` signature, but the wider return is harmless.
3. Drop new tests.

---

## 6. Batch 5 — `B5_F-21`: Doc-edit reclassification (no code touch)

**Severity:** HIGH (reclassified to RESOLVED). **Status:** READY (doc-only).

### 6.1 Spec citation
- Decisions log §2 Group E / Q-13 (resolved): *"`AWAITING_MANUAL` is the correct terminal state. The spec wording `SCHEDULE programs_1_2_rerun(asset)` is aspirational; no automation target exists."*
- Audit `F-21` (HIGH) — to be reclassified.
- Phase plan delta §5: *"F-21 reclassified — `AWAITING_MANUAL` is by-design, not a bug. Saves ~0.5 day."*

### 6.2 Pre-flight checks
1. Confirm code path in `orchestrator.py:700` setting `AWAITING_MANUAL` is unchanged since audit.
2. Confirm the audit pass surfaces no residual issue beyond the doc drift (Stage 1 §0.4 confirms: none).

### 6.3 Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` | line 328 | rewrite `SCHEDULE programs_1_2_rerun(asset)` → `MANUAL programs_1_2_rerun(asset)  # AWAITING_MANUAL — no automation target per Q-13 (2026-04-27)` |
| `docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md` | F-21 entry | append `**Resolution:** by-design per Q-13 (decisions log 2026-04-27). Reclassified from HIGH to RESOLVED.` and update the severity field at the entry header |
| `docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md` | §2 Group E / Q-13 row | add `Reclassified F-21 to RESOLVED on 2026-04-27 via Phase 3 doc-edit batch B5_F-21.` (one-line append; do not rewrite the row) |

### 6.4 Exact change shape

```diff
- SCHEDULE programs_1_2_rerun(asset)
+ MANUAL programs_1_2_rerun(asset)  # AWAITING_MANUAL — no automation target per Q-13 (2026-04-27)
```

### 6.5 Test additions
None (doc-only). Cursor should run `markdownlint` (or the repo equivalent) over the three edited docs and assert no broken anchors.

### 6.6 Exit criteria
1. `git diff` covers exactly the three doc files above; no production code change.
2. Doc-link sweep passes (`mcp__obsidian__find_broken_links` if available, otherwise `grep -n "F-21" docs2/`).
3. Audit doc shows `RESOLVED` for F-21.

### 6.7 Rollback procedure
Revert the three doc edits. No code or schema rollback necessary.

> **Soft flag:** if a future spec rewrite (Isaac) reintroduces an automation target for `programs_1_2_rerun`, this reclassification becomes obsolete and a follow-up phase will re-open F-21.

---

## 7. Batch 6 — `B6_F-42`: L3 trigger dispatches `AIM14_EXPANSION` immediately

**Severity:** HIGH. **Status:** READY.

### 7.1 Spec citation
- Decisions log §2 — silent on F-42. Follow audit.
- Audit `F-42` (HIGH).
- Canvas `P3 Offline.canvas` Block 6 — *"TRIGGER: L3 decay"* (immediate semantics implied).

### 7.2 Pre-flight checks
1. Confirm L3 path: `_handle_trade_outcome` (`orchestrator.py:281, 371`) → `check_level_escalation` (`b2_level_escalation.py:179`) → `trigger_level3` (L155) → enqueue `AIM14_EXPANSION` (L171).
2. Confirm `_dispatch_pending_jobs` (`orchestrator.py:657–740`) is currently called only from `_run_daily` (L920).
3. Confirm `_run_aim14_expansion` (`orchestrator.py:742–766`) is reentrant-safe (single asset job per dispatch). If not, add an idempotency guard before changing the trigger cadence.

### 7.3 Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-offline/captain_offline/blocks/orchestrator.py` | `_handle_trade_outcome` (L281, L371) | after `check_level_escalation` returns and a Level 3 was triggered for this asset, call `self._dispatch_pending_jobs(filter_job_type="AIM14_EXPANSION", filter_asset=asset_id)` |
| `captain-offline/captain_offline/blocks/orchestrator.py` | `_dispatch_pending_jobs` (L657–740) | accept optional `filter_job_type` and `filter_asset` arguments; when omitted, behaviour matches today |
| `captain-offline/captain_offline/blocks/b2_level_escalation.py` | `trigger_level3` (L155–176) | return a small dict `{"l3_triggered": True, "asset_id": asset_id, "enqueued": [...]}` so the orchestrator caller can decide whether to immediate-dispatch |

### 7.4 Exact change shape (before → after)

```python
# BEFORE (b2_level_escalation.trigger_level3, simplified — returns None)
def trigger_level3(...):
    ...
    enqueue("AIM14_EXPANSION", asset_id, ...)
    enqueue("P1P2_RERUN", asset_id, ...)
    publish_alert(...)

# AFTER
def trigger_level3(...) -> dict:
    ...
    enqueue("AIM14_EXPANSION", asset_id, ...)
    enqueue("P1P2_RERUN", asset_id, ...)
    publish_alert(...)
    return {"l3_triggered": True, "asset_id": asset_id,
            "enqueued": ["AIM14_EXPANSION", "P1P2_RERUN"]}
```

```python
# BEFORE (_handle_trade_outcome — drops escalation result)
escalation = check_level_escalation(...)
# escalation result not used for dispatch

# AFTER
escalation = check_level_escalation(...)
if escalation and escalation.get("level") == 3:
    self.logger.info(f"[l3] immediate-dispatch for asset={asset_id}")
    self._dispatch_pending_jobs(filter_job_type="AIM14_EXPANSION",
                                filter_asset=asset_id)
```

```python
# BEFORE (_dispatch_pending_jobs(self) — no filters)
def _dispatch_pending_jobs(self):
    rows = fetch_pending_jobs()
    for row in rows:
        ...

# AFTER
def _dispatch_pending_jobs(self,
                           filter_job_type: str | None = None,
                           filter_asset: str | None = None):
    rows = fetch_pending_jobs(job_type=filter_job_type, asset=filter_asset)
    for row in rows:
        ...
```

### 7.5 Test additions

| File | Test |
|---|---|
| `tests/test_l3_immediate_dispatch.py` (new) | `test_l3_trigger_dispatches_aim14_immediately` — feed a synthetic trade outcome that pushes `cp_prob > 0.9` for 5+ trades, assert `_run_aim14_expansion` is called within the same `_handle_trade_outcome` call frame |
| `tests/test_l3_immediate_dispatch.py` | `test_l2_does_not_immediate_dispatch` — Level 2 only, assert no `_run_aim14_expansion` call until `_run_daily` |
| `tests/test_l3_immediate_dispatch.py` | `test_dispatch_filter_excludes_p1p2_rerun` — asserts `P1P2_RERUN` job stays `AWAITING_MANUAL` after the immediate-dispatch (preserves F-21 by-design behaviour) |
| `tests/test_b2_level_escalation.py` | extend to assert `trigger_level3` returns the new dict shape |

### 7.6 Exit criteria
1. End-to-end replay where a Level 3 fires shows `AIM14_EXPANSION` completing before the next trade outcome is processed (visible in container logs).
2. Daily dispatch path still functions (no regression in existing daily tests).
3. New tests green.

### 7.7 Rollback procedure
1. Revert `_dispatch_pending_jobs` signature to no-arg.
2. Revert `_handle_trade_outcome` to ignore escalation return.
3. Revert `trigger_level3` return shape.
4. Drop new tests.

---

## 8. Cross-batch verification

After all READY batches land, run the following verification block before declaring Phase 3 complete:

1. **Full unit suite:**
   ```bash
   PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
     python3 -B -m pytest tests/ \
     --ignore=tests/test_integration_e2e.py \
     --ignore=tests/test_pipeline_e2e.py \
     --ignore=tests/test_pseudotrader_account.py \
     --ignore=tests/test_offline_feedback.py \
     --ignore=tests/test_stress.py \
     --ignore=tests/test_account_lifecycle.py -v
   ```
2. **Replay harness** (`tests/test_pipeline_e2e.py` once dependencies are container-resident) — assert one `SESSION_CLOSE` and one D26 cold-start row per session.
3. **Grep gates:**
   - `grep -rn "SCHEDULE programs_1_2_rerun" docs2/spec-docs-02/` returns nothing.
   - `grep -rn "train_aim16_hmm" captain-offline/` shows at least one caller in `orchestrator.py`.
   - `grep -rn "filter_job_type" captain-offline/captain_offline/blocks/orchestrator.py` shows the new signature.
4. **Container smoke:** `docker compose -f docker-compose.yml -f docker-compose.local.yml up -d` and tail `captain-offline` logs for `[pg01c]`, `[pg07]`, `[l3]` markers within 10 minutes of session close.
5. **Audit doc state:** F-01 status = WIRED (skeleton), F-04 = BLOCKED-PENDING-Q04, F-13/F-20/F-42 = RESOLVED, F-21 = RESOLVED-BY-DESIGN.

---

## 9. Phase 3 hand-off

| Outgoing artifact | Destination |
|---|---|
| Skeleton PG-01C dispatch | Phase 10 (HMM internals) — replace `build_observation_panel_stub` with real 7-D panel and Baum-Welch fit |
| Pending Q-04 re-ask | When Isaac answers, lift batch B2 into Phase 3.5 (or fold into Phase 4 transitions work) |
| Doc reclassification | Update `docs2/audits/phase-ref-docs/` index to reflect F-21 RESOLVED |
| Updated F-counts | Audit running totals: 2 BLOCKING resolved (F-01 skeleton, F-21 doc), 3 HIGH resolved (F-13, F-20, F-42), 1 BLOCKING still open (F-04 pending Isaac) |

---

## 10. Notes for Cursor Composer 2

- Re-anchor every line number with `grep -n` before editing — the integers above are accurate at plan authoring (`git rev-parse HEAD` of 2026-04-27 morning) but will drift.
- Where the spec authority chain points to a single source (e.g., decisions log Q-03 supersedes whatever the spec says about cadence), do not hedge — implement what Q-03 says and add an inline comment citing the decisions log.
- Phase 3 is intentionally narrow: dispatch wiring, no semantic depth. If a batch tempts you to "while I'm here, fix X" — stop, file X as a Phase-N follow-up note in the audit doc, and move on.
- Idempotency on session boundaries is a recurring test theme — please add the assertion even where the batch description does not call it out explicitly.
- This plan was generated read-only. The audit pass (Stage 1 §0) is informational; do not promote any of its observations to a code change unless they appear in a numbered batch (B1–B6).
