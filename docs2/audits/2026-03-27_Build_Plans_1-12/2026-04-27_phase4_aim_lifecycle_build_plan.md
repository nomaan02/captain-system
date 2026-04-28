---
title: Phase 4 Build Plan — AIM Lifecycle / DMA / HDWM Corrections
date: 2026-04-27
phase: 4
companion_to:
  - docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md
  - docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md
  - docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md
  - docs2/spec-docs-02/offline/AIM_System.md
  - docs2/spec-docs-02/offline/DMA MoE Meta-Learning Pipeline.md
findings_addressed: [F-09, F-10, F-11, F-12]
status: READY (Batches 1, 2, 3); BLOCKED-PARTIAL (Batch 4 logging sub-task)
authority_chain: decisions log §2 > audit > spec > code
---

# Phase 4 — AIM Lifecycle / DMA / HDWM Corrections

Scope: bring `b1_aim_lifecycle.py`, `b1_dma_update.py`, `b1_hdwm_diversity.py`
into spec compliance with doc 32 PG-01, PG-02, PG-03 and the resolutions in the
Audit Decisions Log §2 Group D.

Plan mode: **build plan for Cursor Composer 2 — do not execute code**.

---

## Stage 1 — Audit Pass (read-only)

### F-09 — DMA loops over all D02 rows, not "FOR EACH active aim"

- **Code today:** `captain-offline/captain_offline/blocks/b1_dma_update.py:39-62`
  (`_load_active_aims`) selects every latest D02 row for the asset with no JOIN
  to `p3_d01_aim_model_states.status`. Function name claims "active" but query
  does not filter.
- **Callers:** `captain-offline/captain_offline/blocks/orchestrator.py:242-256`
  (`_handle_trade_outcome`), `:340-352` (`_handle_signal_outcome`).
- **Decisions log:** §2 Group D is silent on F-09 directly; audit `Needs Isaac:
  NO`. Spec authority falls through to doc 32 PG-02 — `FOR EACH active aim a`.
- **Action:** ungate `_load_active_aims` against D01 status='ACTIVE' via JOIN
  with `LATEST ON` on D01.

### F-10 — HDWM trigger, candidate set, and active count diverge

- **Code today:** `captain-offline/captain_offline/blocks/b1_hdwm_diversity.py:59-67`
  (`_count_active_aims`) uses `SELECT count() ... WHERE status='ACTIVE'`
  with **no `LATEST ON ... PARTITION BY aim_id, asset_id`** — append-only D01
  history inflates the count.
- **Code today:** `b1_hdwm_diversity.py:111-121` triggers recovery only when
  `len(active_in_type)==0 AND len(suppressed_in_type)>0`, and `argmax` runs
  over `suppressed_in_type` only.
- **Spec (doc 32 PG-03 lines 187-194):** trigger is `IF len(active_in_type)==0`,
  `argmax` over **all** AIMs in `seed_types[type]`, set
  `inclusion_probability = 1.0 / num_active_aims`.
- **Callers:** `orchestrator.py:955` (weekly).
- **Decisions log:** silent → audit governs; `Needs Isaac: NO`.

### F-11 — WARM_UP / ELIGIBLE dual gate (RESTORATION TO SINGLE GATE)

- **Code today:** `b1_aim_lifecycle.py:244-279`. WARM_UP uses both
  `feature_days_accumulated` and `learning_warmup_required`; writes
  `min(feat_progress, learn_progress)` to `warmup_progress`. ELIGIBLE→ACTIVE
  requires user activation **AND** `trades >= learn_required`.
- **Spec (doc 32 PG-01 lines 53-64):** single observation-based gate.
  `WARM_UP → ELIGIBLE` when `progress = observations_collected(a) /
  warmup_required(a) >= 1.0`. `ELIGIBLE → ACTIVE` on `user_activated(a)` only.
- **Decisions log §2 Group D, Q-09:** **"Bring code back to single
  observation-based gate per doc 32 PG-01. Drop DEC-05 dual-gate. WARM_UP →
  ELIGIBLE on `progress >= 1.0` only; ELIGIBLE → ACTIVE on user activation
  only. Phase 4. Unify GUI activation and cron paths."**
- **Multi-gate code path to remove:** `b1_aim_lifecycle.py:244-260` (dual
  feature/learning progress); `:265-277` (ELIGIBLE→ACTIVE learning gate).
  `_handle_aim_activation` in orchestrator (`orchestrator.py:468`) must be
  unified with the cron path so a single rule governs ACTIVE entry.
- **Callers:** `orchestrator.py:888-899` (`_run_daily`); `:425, :468`
  (`_handle_aim_activation` GUI command path).
- **Q-27 (§3.2) — PENDING.** Concerns the meaning of `raw_data_count(a)` for
  AIMs 1-15 in PG-01's COLLECTING→WARM_UP gate. Current code reads
  `observations_collected` and accepts `>0` (matches spec literal). The
  COLLECTING transition is therefore **not blocked** by Q-27; only the deeper
  question of *what counter to read* is open. Treat as soft flag in this phase
  — keep current `observations_collected` semantics, surface a TODO marker
  in code referencing Q-27.

### F-12 — Suppression/recovery does not implement consecutive-trade rules

- **Code today:** `b1_aim_lifecycle.py:286-305` reads
  `_load_meta_weight_history` which aliases `consecutive_zero` to
  `days_below_threshold` (a *daily* counter on D02), and stubs
  `consecutive_above = 10 if days_below==0 else 0`
  (`b1_aim_lifecycle.py:375-392`). DMA writer
  (`b1_dma_update.py:217-225`) increments `days_below_threshold` per **DMA
  invocation** (per trade outcome), not per trade with strict zero/>0.1.
- **Spec (doc 32 PG-01 lines 67-80):**
  `IF meta_weight(a) == 0 for 20+ consecutive trades → SUPPRESSED`,
  `IF meta_weight(a) > 0.1 for 10+ consecutive trades → ACTIVE`,
  `LOG suppression event to P3-D06`, `LOG recovery event to P3-D06`.
- **Callers:** DMA writer (counter source), `_load_meta_weight_history`
  (counter reader). HDWM does not depend on these counters.
- **Q-26 (§3.2) — PENDING.** "P3-D06 record shape for AIM
  suppression/recovery" — destination table is unresolved (current code uses
  `p3_d06_injection_history`; spec wording matches but Isaac re-ask not yet
  answered). The **counter-tracking sub-task is unblocked** (state-machine
  semantics fully specified by PG-01); the **event-log sub-task is BLOCKED**
  pending Isaac's answer on whether D06 = `injection_history` or a new
  `p3_d06_aim_lifecycle_events` table.

### Authority chain confirmation

For each finding, decisions log §2 was checked first:

| Finding | Decisions log §2 entry | Effect |
|---|---|---|
| F-09 | none — silent | Audit governs |
| F-10 | none — silent | Audit governs |
| F-11 | Group D, Q-09 — **RESOLVED single-gate** | Decisions log governs (matches spec) |
| F-12 | Group D, Q-26 — **PARTIAL** (event log only) | Counter logic unblocked; event-log destination BLOCKED |

---

## Stage 2 — Build Plan (Cursor execution)

Four batches, executed in order. Each batch is committable independently.

---

### Batch 1 — F-09: DMA loop filtered to ACTIVE AIMs only

**Spec citation:**
- Decisions log: silent (audit governs).
- Audit `2026-04-22_offline_spec_vs_code_audit copy.md` §F-09.
- Doc 32 PG-01 line 101 / PG-02 line 101: `FOR EACH active aim a:`.
- AIM_System.canvas: `DMA/MoE AGGREGATION` block — D02 inclusion update
  scoped to active AIM modifier outputs.

**Pre-flight checks:**
1. Confirm D01 latest-state query pattern used by HDWM (`b1_hdwm_diversity.py:38-43`)
   is the canonical `LATEST ON last_updated PARTITION BY aim_id, asset_id`.
2. Confirm AIM-16 status: per AIM_System.canvas it is "session-scoped, not
   per-asset". If D01 has no per-asset row for AIM-16 the JOIN will exclude
   it from DMA, which is correct — DMA is per-asset, AIM-16 outputs session
   weights, not per-asset modifiers.
3. Run `git grep "_load_active_aims"` to confirm only one caller.

**Files / line ranges:**
- `captain-offline/captain_offline/blocks/b1_dma_update.py:39-62`
  (`_load_active_aims`).

**Change shape (before → after):**

Before (`b1_dma_update.py:39-62`): query selects all D02 rows for asset.

After: rewrite to JOIN-equivalent — fetch active aim_ids from D01 first
(LATEST ON), then load D02 rows restricted to that set. QuestDB does not
support the JOIN-LATEST-ON form across both tables in one query reliably;
two-step query is the pragmatic shape:

```python
def _load_active_aims(asset_id: str) -> list[dict]:
    """Load D02 rows ONLY for AIMs whose latest D01 status is ACTIVE.
    PG-02 line 101: FOR EACH active aim a.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT aim_id FROM p3_d01_aim_model_states
               WHERE asset_id = %s AND status = 'ACTIVE'
               LATEST ON last_updated PARTITION BY aim_id, asset_id""",
            (asset_id,),
        )
        active_ids = [r[0] for r in cur.fetchall()]
    if not active_ids:
        return []
    placeholders = ",".join(["%s"] * len(active_ids))
    with get_cursor() as cur:
        cur.execute(
            f"""SELECT aim_id, inclusion_probability, inclusion_flag,
                       recent_effectiveness, days_below_threshold
                FROM p3_d02_aim_meta_weights
                WHERE asset_id = %s AND aim_id IN ({placeholders})
                LATEST ON last_updated PARTITION BY aim_id, asset_id
                ORDER BY aim_id""",
            (asset_id, *active_ids),
        )
        rows = cur.fetchall()
    return [
        {"aim_id": r[0], "inclusion_probability": r[1], "inclusion_flag": r[2],
         "recent_effectiveness": r[3], "days_below_threshold": r[4]}
        for r in rows
    ]
```

**Tests (additions):** `tests/test_b1_dma_active_filter.py` (new file).
- `test_dma_excludes_warm_up_aims`: insert D01 rows {AIM-1=ACTIVE, AIM-2=WARM_UP,
  AIM-3=SUPPRESSED, AIM-4=ELIGIBLE}; insert D02 rows for all four; assert
  `_load_active_aims` returns AIM-1 only.
- `test_dma_normalisation_only_over_active`: stub trade outcome, run
  `run_dma_update(commit=False)`; assert `proposed_weights` keys match the
  ACTIVE set.
- `test_dma_empty_active_set_returns_empty`: D01 has no ACTIVE rows; assert
  `run_dma_update` short-circuits with `{}`.

**Exit criteria:**
- All three new tests pass.
- Existing `tests/test_b3_aim.py` / orchestrator tests still pass.
- `git grep "p3_d02_aim_meta_weights" captain-offline/captain_offline/blocks/b1_dma_update.py`
  shows the updated two-step query, no orphan WHERE clauses.

**Rollback procedure:**
- `git revert <batch1 commit>`.
- DMA returns to pre-fix all-rows behaviour. No schema or data writes are
  involved — pure read path change, fully reversible.

---

### Batch 2 — F-10: HDWM trigger, candidate set, active count

**Spec citation:**
- Audit §F-10. Decisions log silent (audit governs).
- Doc 32 PG-03 lines 187-194 — full pseudocode.
- AIM_System.canvas: `SVC: offline_worker (HDWM weekly)` block
  (`dma_engine.py → diversity_check()`); reads `P3-D01,D02(QuestDB)`.
- DMA MoE Meta-Learning Pipeline.md — confirm seed-type taxonomy unchanged.

**Pre-flight checks:**
1. Confirm `SEED_TYPES` mapping in `b1_hdwm_diversity.py:21-29` matches
   PG-03 lines 178-185 verbatim (it does — 6 seed types, AIM-16 excluded).
2. Confirm test path `tests/test_b1_hdwm.py` does not exist; new file.

**Files / line ranges:**
- `captain-offline/captain_offline/blocks/b1_hdwm_diversity.py:59-67`
  (`_count_active_aims` — fix LATEST ON).
- `b1_hdwm_diversity.py:99-122` (`run_hdwm_diversity_check` — fix trigger
  and candidate set).

**Change shape:**

Change 1 — `_count_active_aims` (lines 59-67):

```python
def _count_active_aims(asset_id: str) -> int:
    """Count distinct AIMs whose latest D01 status is ACTIVE.
    PG-03 line 193 — num_active_aims used for equal-weight init.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT count() FROM (
                 SELECT aim_id FROM p3_d01_aim_model_states
                 WHERE asset_id = %s
                 LATEST ON last_updated PARTITION BY aim_id, asset_id
               ) WHERE status = 'ACTIVE'""",
            (asset_id,),
        )
        row = cur.fetchone()
    return row[0] if row else 0
```

NOTE: QuestDB `LATEST ON` cannot be combined with an outer filter in
all versions. If the nested form fails, equivalent two-step:

```python
with get_cursor() as cur:
    cur.execute(
        """SELECT aim_id, status FROM p3_d01_aim_model_states
           WHERE asset_id = %s
           LATEST ON last_updated PARTITION BY aim_id, asset_id""",
        (asset_id,),
    )
    return sum(1 for _, s in cur.fetchall() if s == "ACTIVE")
```

Use whichever is verified by Phase 1 schema-migration build plan as the
canonical pattern.

Change 2 — `run_hdwm_diversity_check` (lines 99-122):

Before: triggers only when `len(active_in_type)==0 AND len(suppressed)>0`;
`argmax` over `suppressed_in_type`.

After (matches PG-03 exactly):

```python
for type_name, aim_ids in SEED_TYPES.items():
    active_in_type = [
        aid for aid in aim_ids
        if _get_aim_status(aid, asset_id) == "ACTIVE"
    ]
    if len(active_in_type) > 0:
        continue  # diversity intact for this type

    # Spec PG-03 line 191: argmax over ALL AIMs in seed_types[type]
    best_aid = max(
        aim_ids,
        key=lambda aid: _get_recent_effectiveness(aid, asset_id),
    )
    _reactivate_aim(best_aid, asset_id, num_active)
    num_active += 1
    reactivated += 1
    logger.warning(
        "HDWM diversity recovery: reactivated AIM-%d as seed for '%s' [%s]",
        best_aid, type_name, asset_id,
    )
```

**Tests (additions):** `tests/test_b1_hdwm_diversity.py` (new file).
- `test_hdwm_recovers_when_no_active_in_type_even_without_suppressed`:
  type "options" has all three AIMs in WARM_UP / ELIGIBLE; assert recovery
  fires and reactivates the AIM with highest `recent_effectiveness`.
- `test_hdwm_argmax_over_full_seed_set`: best `recent_effectiveness` belongs
  to a WARM_UP AIM (not SUPPRESSED); assert it is the one reactivated.
- `test_hdwm_skips_when_one_active_in_type`: type "macro_event" has AIM-6
  ACTIVE, AIM-7 SUPPRESSED; assert no reactivation.
- `test_count_active_aims_dedupes_history`: insert two D01 history rows for
  AIM-1 (status ACTIVE then SUPPRESSED); assert `_count_active_aims` returns
  0, not 1.

**Exit criteria:**
- All four tests pass.
- HDWM weekly orchestrator path (`orchestrator.py:955`) executes without
  regression on a smoke run.

**Rollback procedure:** `git revert`. No data migration; D01/D02 inserts
performed by `_reactivate_aim` are append-only and idempotent at the
state-machine level (re-running converges).

---

### Batch 3 — F-11: Restore single-gate WARM_UP / ELIGIBLE / ACTIVE

**Spec citation:**
- Decisions log §2 Group D, **Q-09 (RESOLVED)**: "Bring code back to single
  observation-based gate per doc 32 PG-01. Drop DEC-05 dual-gate. WARM_UP →
  ELIGIBLE on `progress >= 1.0` only; ELIGIBLE → ACTIVE on user activation
  only. Phase 4. Unify GUI activation and cron paths."
- Audit §F-11.
- Doc 32 PG-01 lines 49-64.

**Pre-flight checks:**
1. Confirm `_handle_aim_activation` location — `orchestrator.py:468`. Read
   that function and confirm it is the GUI command path (it is invoked from
   `:425` based on Stage-1 grep).
2. Confirm whether `feature_days_accumulated`, `feature_warmup_days`,
   `learning_warmup_required` helpers in `b1_aim_lifecycle.py` are used
   anywhere else (`git grep`). If unused after this batch, delete; if used
   elsewhere, leave the helpers but unwire from PG-01 path.
3. Confirm `SUPPRESSION_CONSECUTIVE_ZERO` and `RECOVERY_CONSECUTIVE` constants
   are not touched by this batch (Batch 4 owns those).

**Files / line ranges:**
- `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:244-279`
  (WARM_UP and ELIGIBLE blocks).
- `captain-offline/captain_offline/blocks/orchestrator.py:468` and
  surrounding `_handle_aim_activation` (verify-and-unify).

**Change shape:**

Replace lines 244-279 with single-gate logic:

```python
elif current_status == "WARM_UP":
    obs = observations_collected(aim_id, asset_id)
    required = warmup_required(aim_id)  # observation-based, single source
    progress = obs / required if required > 0 else 1.0
    _update_warmup_progress(aim_id, asset_id, min(progress, 1.0))

    if progress >= 1.0:
        _update_aim_status(aim_id, asset_id, "ELIGIBLE")
        logger.info(
            "AIM-%d [%s]: WARM_UP -> ELIGIBLE (%d/%d observations)",
            aim_id, asset_id, obs, required,
        )

elif current_status == "ELIGIBLE":
    # PG-01 spec: ELIGIBLE → ACTIVE on user activation alone.
    if aim_id in user_activated_aims:
        snapshot_before_update("P3-D01", "AIM_RETRAIN", state)
        _update_aim_status(aim_id, asset_id, "ACTIVE")
        logger.info(
            "AIM-%d [%s]: ELIGIBLE -> ACTIVE (user activated)",
            aim_id, asset_id,
        )
```

`warmup_required(aim_id)` consolidates the prior `learning_warmup_required`
/ `feature_warmup_days` split into one observation count per AIM. If the
two helpers currently return the same value, choose `learning_warmup_required`
as the canonical name → rename to `warmup_required`. Add a per-AIM map
in `b1_aim_lifecycle.py` near the constants block.

Unify `_handle_aim_activation` (orchestrator.py:468):
- Remove any learning-gate or feature-gate check it performs before flipping
  to ACTIVE.
- Make it call the same cron path: append `aim_id` to a transient
  `user_activated_aims` set, invoke `run_aim_lifecycle(asset_id, {aim_id})`,
  let the unified PG-01 logic handle ELIGIBLE→ACTIVE.

Q-27 marker: in `observations_collected`, leave a one-line `# TODO(Q-27):
re-confirm counter source post-Isaac re-ask` comment. **Do not change
semantics.**

**Tests (additions):** `tests/test_b1_aim_lifecycle_singlegate.py` (new file).
- `test_warmup_progresses_on_observations_alone`: AIM-1 WARM_UP with
  obs=required-1 → progress<1.0, stays WARM_UP. obs=required → ELIGIBLE.
- `test_eligible_to_active_on_user_activation_alone`: AIM-1 ELIGIBLE,
  trades=0 (would have failed dual gate); call
  `run_aim_lifecycle(asset, {1})`; assert status=ACTIVE.
- `test_handle_aim_activation_unified_path`: simulate GUI command;
  `_handle_aim_activation({"aim_id": 1, "asset_id": "ES"})` flips ELIGIBLE
  AIM directly to ACTIVE; assert no learning-gate veto.
- `test_no_dual_gate_residue`: `git grep -n "feat_progress\|learn_progress"`
  in lifecycle file returns no matches (negative test in CI).

**Exit criteria:**
- All four tests pass.
- `git grep "DEC-05"` in `b1_aim_lifecycle.py` returns no matches except a
  short historical note in the file header (or zero matches — preferred).
- Existing `tests/test_b3_aim.py` passes; if it asserts dual-gate behaviour,
  update it as part of this batch and document the change in the commit.

**Rollback procedure:** `git revert`. State-machine change is forward-only
in terms of data (more AIMs may flip to ACTIVE earlier under new rules);
pre-existing ACTIVE AIMs are unaffected. To roll back a "premature"
activation, manually demote via `INSERT INTO p3_d01_aim_model_states ...
status='ELIGIBLE'`.

---

### Batch 4 — F-12: Consecutive-trade meta_weight tracking

**Status:** **PARTIALLY BLOCKED.**
- **Sub-task 4a (counter logic): UNBLOCKED.** State-machine semantics fully
  specified by doc 32 PG-01 lines 67-80.
- **Sub-task 4b (event log): BLOCKED — awaiting Isaac re-ask resolution
  on Q-26.** Do not implement event-log writes until Q-26 is answered.

**Spec citation:**
- Doc 32 PG-01 lines 67-80.
- Audit §F-12. Decisions log §2 Group D — Q-26 PARTIAL (event log
  destination unresolved).

**Pre-flight checks:**
1. Confirm `days_below_threshold` field exists on D02 (it does — used in
   `b1_dma_update.py:217`). New consecutive-trade counter must NOT reuse
   this field — different semantics (daily vs trade).
2. Decision required (flag for Nomaan): add new D02 columns
   `consecutive_zero_trades INT` and `consecutive_above_trades INT`, OR
   maintain in Redis (`hash aim_counters:{aim_id}:{asset_id}`)?
   - **Recommendation:** Redis. PG-01 runs daily; counters reset when AIM
     transitions; pure post-trade-outcome state. QuestDB append-only writes
     would inflate D02 history. **Flag for Isaac confirmation if Phase 1
     schema migration was already locked without these columns.**
3. Confirm orchestrator trade-outcome path (`orchestrator.py:242-256`,
   `:340-352`) runs **after** DMA update — counters increment from the
   *new* `inclusion_probability`, not the pre-update one.

**Files / line ranges (sub-task 4a — UNBLOCKED):**
- `captain-offline/captain_offline/blocks/b1_dma_update.py:217-225`
  (post-DMA counter increment).
- `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:286-305`
  (ACTIVE→SUPPRESSED check), `:303-310` (SUPPRESSED→ACTIVE check),
  `:374-392` (`_load_meta_weight_history` rewrite).

**Change shape (4a):**

In `b1_dma_update.py`, after computing `proposed_weights[aid]`:

```python
# Spec PG-01 lines 67-80: track consecutive trades for suppression/recovery.
import shared.redis_client as rc
key = f"aim_counters:{aid}:{asset_id}"
new_prob = proposed_weights[aid]
if new_prob == 0:
    rc.client().hincrby(key, "consecutive_zero", 1)
    rc.client().hset(key, "consecutive_above", 0)
elif new_prob > 0.1:
    rc.client().hincrby(key, "consecutive_above", 1)
    rc.client().hset(key, "consecutive_zero", 0)
else:
    # 0 < new_prob <= 0.1 — neither counter increments
    rc.client().hset(key, "consecutive_above", 0)
```

In `b1_aim_lifecycle.py`, replace `_load_meta_weight_history` body with:

```python
def _load_meta_weight_history(aim_id: int, asset_id: str) -> dict:
    """Return consecutive-trade counters tracked by DMA update."""
    import shared.redis_client as rc
    raw = rc.client().hgetall(f"aim_counters:{aim_id}:{asset_id}")
    return {
        "consecutive_zero": int(raw.get(b"consecutive_zero", 0)),
        "consecutive_above": int(raw.get(b"consecutive_above", 0)),
    }
```

Reset both counters on any state transition that resolves the suppression
event (i.e., when ACTIVE→SUPPRESSED fires, zero out
`consecutive_zero`; when SUPPRESSED→ACTIVE fires, zero out
`consecutive_above`). Add the resets inside the `_update_aim_status` calls
in those two branches.

**Files / line ranges (sub-task 4b — BLOCKED):**

> **BLOCKED — awaiting Isaac re-ask resolution.**
> Q-26 (decisions log §3.2): "P3-D06 record shape for AIM
> suppression/recovery — is `p3_d06_injection_history` the table, should we
> add a new `p3_d06_aim_lifecycle_events` table, or is there an existing
> store we should be using?"
>
> Until answered, do NOT implement the `LOG suppression event to P3-D06` /
> `LOG recovery event to P3-D06` writes from PG-01 lines 69 / 81. Leave a
> `# BLOCKED — see Q-26` marker at the relevant lines in
> `b1_aim_lifecycle.py` (currently :294, :303).

**Tests (additions):** `tests/test_b1_aim_suppression_counters.py` (new file).
- `test_consecutive_zero_increments_on_zero_dma_output`: simulate 20 DMA
  updates each producing `inclusion_probability == 0`; assert Redis counter
  reaches 20 and `run_aim_lifecycle` flips ACTIVE→SUPPRESSED.
- `test_consecutive_zero_resets_on_nonzero`: 19 zero updates then one >0
  update; assert counter resets to 0 and AIM stays ACTIVE.
- `test_consecutive_above_recovery`: SUPPRESSED AIM, 10 DMA updates with
  `inclusion_probability > 0.1`; assert lifecycle flips SUPPRESSED→ACTIVE.
- `test_mid_band_does_not_count`: DMA outputs 0.05 (above zero, below 0.1);
  assert neither counter advances.
- (4b deferred) `test_suppression_event_logged_to_p3_d06` — write but
  mark `pytest.skip(reason="BLOCKED — Q-26 unresolved")` until Isaac
  re-asks.

**Exit criteria (4a):**
- All four counter tests pass.
- `git grep "days_below_threshold" captain-offline/captain_offline/blocks/b1_aim_lifecycle.py`
  returns no matches in suppression logic (only Phase-2 / DMA persistence
  code may still touch it for other reasons).
- Redis key TTL: counters persist across orchestrator restarts (no expiry
  set; explicit reset on transition).

**Rollback procedure:** `git revert` for code; `redis-cli --scan --pattern
'aim_counters:*' | xargs redis-cli del` to clear stale counters. State
machine reverts to the prior (incorrect) `days_below_threshold` proxy.

---

## Cross-batch summary

| Batch | Finding | Status | Test count | New files |
|---|---|---|---|---|
| 1 | F-09 | READY | 3 | tests/test_b1_dma_active_filter.py |
| 2 | F-10 | READY | 4 | tests/test_b1_hdwm_diversity.py |
| 3 | F-11 | READY (Q-09 RESOLVED) | 4 | tests/test_b1_aim_lifecycle_singlegate.py |
| 4a | F-12 counters | READY | 4 | tests/test_b1_aim_suppression_counters.py |
| 4b | F-12 event log | **BLOCKED — Q-26** | 1 (skipped) | (same file) |

## Open questions to escalate before merge

1. **Q-26 (Isaac re-ask) — BLOCKING for 4b:** P3-D06 destination for
   suppression/recovery events. Decisions log §3.2.
2. **Q-27 (Isaac re-ask) — soft flag, non-blocking:** `raw_data_count(a)`
   semantics for AIMs 1-15 in COLLECTING gate. Current code accepts
   `observations_collected > 0`, which matches the literal spec; flag with
   TODO and proceed.
3. **Schema decision for Batch 4a counters (not in §3.2):** Redis vs new
   D02 columns. Recommendation: Redis. Confirm with Nomaan before
   implementing if Phase 1 schema migrations have not yet shipped.

## Authority chain footnote

For each in-scope finding, this plan resolves "what should the fix do" by
reading, in order:
1. Audit Decisions Log `captain_offline_audit_decisions_2026-04-27.md` §2
   Group D and §3.2 for re-asks.
2. Audit `2026-04-22_offline_spec_vs_code_audit copy.md` F-09…F-12 entries.
3. Spec doc 32 `32_P3_Offline_Full_Pseudocode.md` PG-01 / PG-02 / PG-03.
4. Canvas references (`AIM_System.canvas`, `DMA MoE Meta-Learning Pipeline`)
   for wiring annotations only.

Where any layer is silent, the next layer governs. No third option is invented.
