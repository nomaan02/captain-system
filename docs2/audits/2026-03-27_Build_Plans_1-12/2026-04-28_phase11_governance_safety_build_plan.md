# Phase 11 — Governance / Safety Build Plan

**Campaign:** Captain Offline twelve-phase audit fix (`2026-03-27_Build_Plans_1-12`)  
**Plan date:** 2026-04-28  
**Executed by:** Cursor Composer 2 (implementation sessions)  
**Authoritative inputs (spec authority chain: decisions log §2 → audit F-IDs → doc 32 → code):**

| Document | Role |
|----------|------|
| `docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md` | **Group I** Q-08, Q-25, Q-28; **§5** Phase 11 row |
| `docs2/audits/2026-03-27_offlice_spec_vs_code_answers/2026-03-27_offlice_spec_vs_code_answers.md` | Same Group I / §5 content (companion) |
| `docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md` | **F-08**, **F-43** full entries |
| `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` | **Version Snapshot Policy** (lines ~140–173); **Audit Resolutions** (~789–798) |

**Frozen scope for this phase**

| ID | Handling |
|----|----------|
| **F-08** | Implement **two-phase** rollback — `request_rollback` → **admin approval signal** → `commit_rollback`. **No** single-call destructive rollback that applies restore without the approval gate after `NOTIFY`. |
| **F-43** | **Documentation only:** reclassify Audit Resolutions line for G-XCT-012 so it does **not** read as full “CRITICAL RESOLVED” replay readiness. **Decision Q-25** — observational logging acceptable for v1. |
| **Q-28 / F-47** | **Soft flag only** — DELETE vs cold-storage export; **no implementation** unless promoted beyond decisions log “won’t-fix / defer v1”. |

---

## Frozen Stage 1 findings (audit pass 2026-04-28)

- **`rollback_to_version`** lives in `captain-offline/captain_offline/blocks/version_snapshot.py` **404–481**; performs comparison then **immediate** snapshot + restore + regression on ADOPT — **no** discrete admin gate between NOTIFY and destructive restore aligned with pseudocode **`ON admin_approval:`**.
- **`rollback_to_version` has zero in-repo Python callers** — implementation work must still split the API for future CLI/Command/UI wiring without single-phase footgun.
- **G-XCT-012 “RESOLVED”** offending line: **`32_P3_Offline_Full_Pseudocode.md` line ~798**, Audit Resolutions bullet for `G-XCT-012_crash_recovery_write_only`.
- **Checkpoint code:** `captain-offline/captain_offline/main.py` **124–128** logs `get_last_checkpoint` only; `shared/journal.py` **55–104** has no replay API — consistent with deferred replay (Q-25).

---

## Batch 11.1 — F-08: Two-phase version rollback API

### 1. Title

**11.1 — Two-phase rollback (`request_rollback` → admin signal → `commit_rollback`)**

### 2. Spec citation

- **Decisions log Group I Q-08:** “must be split into `request_rollback` → admin signal → `commit_rollback`.”
- **Doc 32 Version Snapshot Policy** (`32_P3_Offline_Full_Pseudocode.md` **164–173**): `NOTIFY` … then **`ON admin_approval:`** → `snapshot_before_update` / `restore_state` / regression / log.
- **Audit F-08** (`2026-04-22_offline_spec_vs_code_audit copy.md` **226–246**): single-path rollback without human gate; proposed two-phase API with proposal token + external admin signal.

### 3. Pre-flight checks

- [ ] Read current `rollback_to_version` and helpers in `version_snapshot.py` (**258–481**).
- [ ] Confirm no other module imports `rollback_to_version` (grep `rollback_to_version` under `captain-offline/`, `captain-command/`, `tests/`).
- [ ] Decide **where pending proposals persist** — must survive process restart (minimal: Redis key with TTL **or** append-only QuestDB proposals table — **pick one documented pattern already in repo**, e.g. Redis like `captain_offline.blocks.version_snapshot` already uses `get_redis_client` + `CH_ALERTS`). Do **not** invent a new infra without documenting it in this batch’s verification.
- [ ] Confirm **who issues admin approval**: for v1 acceptable as explicit function argument `commit_rollback(..., approving_admin_user_id=...)` + optional **`approval_token`** returned from `request_rollback` (secret link) OR separate Command handler that calls `commit_rollback` — document chosen seam.

### 4. Files and line ranges to modify

| File | Scope |
|------|--------|
| `captain-offline/captain_offline/blocks/version_snapshot.py` | **404–481** (`rollback_to_version` becomes split or wrapper); helpers **289–382** reused; optionally new module-level proposal store |
| Callers **to add** after this batch | CLI script under `captain-command/` OR `captain-offline`**/** `main`/API — **optional** follow-up ticket if Phase 11 timeboxed to library-only |
| Tests | **`tests/`** new file — see §6 |

### 5. Exact change shape (before → after)

**Before**

- **`rollback_to_version(component_id, version_id, admin_user_id)`** — one call executes: load targets → pseudotrader comparison → on ADOPT: `snapshot_before_update` (**454–455**) → `_restore_state` (**456**) → `_run_regression_tests` (**458–459**) → alerts.

**After (required public shape)**

Align names with decisions log literally:

```text
request_rollback(component_id, version_id, requester_admin_user_id) -> Proposal
  - Load D18 target; load current_state; run _run_rollback_comparison-only.
  - If REJECT: return terminal status + comparison (no persistence of proposal).
  - If ADOPT: NOTIFY (“Rollback comparison ready”, HIGH) via existing _publish_rollback_alert semantics OR a distinct “PROPOSAL_CREATED” subtype.
  - Persist a pending proposal keyed by rollback_request_id (UUID): component_id, version_id, snapshot of target_state reference, comparison summary, timestamps, expiry.
  - MUST NOT call _restore_state, snapshot_before_update(ROLLBACK) for destructive apply yet.

commit_rollback(rollback_request_id, approving_admin_user_id, approval_proof) -> Completion
  - Load proposal; verify status PENDING and not expired; verify approval_proof (opaque token tied to proposal OR shared secret keyed in env — spell out one approach in code comments).
  - ONLY here: execute current sequence matching spec “ON admin_approval”: snapshot_before_update(component_id, "ROLLBACK"), _restore_state, _run_regression_tests, revert-with-notify path on regression failure (**458–466** logic preserved inside commit).
  - Idempotency: second commit same id → return idempotent ALREADY_COMPLETED without double-restore OR clear error — choose one behavior and test it.
```

**Compatibility**

- **Deprecate** public `rollback_to_version`: either **`raise`** with message directing callers to two-phase APIs, or delegate to **`request_rollback`** + **`NotImplementedError`** for commit (must not silently keep old semantics). Prefer **DeprecationWarning** then remove in Phase 12 if no callers.

### 6. Test additions

| Item | Detail |
|------|--------|
| **New file** | `tests/test_version_rollback_two_phase.py` (or `tests/offline/test_version_rollback_two_phase.py` matching repo convention) |

**Assertions (minimum)**

1. **`request_rollback` idempotency of read path:** Repeated `request_rollback` creates **distinct** proposals OR replaces same pending consistently — behaviour fixed in tests once store chosen (document expected UX).
2. **Admin gate:** After `request_rollback` (ADOPT), **live QuestDB-backed state** for affected component unchanged until `commit_rollback` (**assert rows/hash before vs after request**).
3. **`commit_rollback`:**
   - Fails/closes cleanly with **wrong** `approval_proof` / wrong approving id.
   - Succeeds with **correct** proof and matches **pre-commit** pseudocode semantics (snapshot undo version created, `_restore_state` applied, regression mocked or seeded fixture).
4. **Irreversibility / completion:** Successful commit marks proposal **COMPLETED**; second commit is idempotent **`ALREADY_COMPLETED`** or deterministic error (**no second restore**, no extra D18 rows beyond spec).
5. **REJECT branch:** `request_rollback` comparison REJECT ⇒ **no** pending proposal persisted (or terminal REJECT row — document one).

**(Optional)** Unit-test `_run_rollback_comparison` + `_run_regression_tests` in isolation with mocks if integration tests prove heavy — keep scope minimal.

### 7. Exit criteria

- Two public entry points **`request_rollback`** and **`commit_rollback`** exist with behaviour above; **`rollback_to_version`** no longer exposes single-shot destructive rollback without approval step.
- `pytest` subset for Phase 11 passes locally/CI for new tests.
- **No** behavioural regression for **`snapshot_before_update`** callers in **`b1_***`, **`b8_kelly_update`**, **`b1_drift_detection`** unrelated to rollback.

### 8. Meta-rollback procedure (rollback of Batch 11.1)

1. Git revert commits for `version_snapshot.py` + tests.  
2. Redeploy previous package if Composer published artifacts.  
3. If Redis/QuestDB persisted proposal structs were added, document manual cleanup (`KEYS`/`DELETE` Redis pattern or truncate helper table — keep migration reversible or unused in rollback path).

---

## Batch 11.2 — F-43: Audit Resolutions doc edit (G-XCT-012)

### 1. Title

**11.2 — Rephrase G-XCT-012 status (“checkpoint logging only — replay deferred”)**

### 2. Spec citation

- **Decisions log Group I Q-25:** “Phase 11: amend audit Resolutions in doc 32 … rephrase as **checkpoint logging only — replay deferred**.”  
- **Audit F-43** (**1033–1052**): observational logging vs replay; doc marked RESOLVED but code has no replay.  
- **Doc 32** **Audit Resolutions** section ~**789–798**.

### 3. Pre-flight checks

- [ ] Open `32_P3_Offline_Full_Pseudocode.md`, locate **line ~798**:  
  `- [[...G-XCT-012...|...]] (...) — CRITICAL RESOLVED`

### 4. Files to modify

| Path | Change |
|------|--------|
| `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` | **Audit Resolutions bullet for G-XCT-012 (~798)** |

**Residual code audit:** Batch 11 closes F-43 **unless** codebase search finds user-facing guarantees that say “replay implemented” (**grep**: `replay`, `G-XCT`, `crash recovery` under `captain-offline/`). If contradictory comments remain, **optional** one-line clarification on `main.py`/journal header — minimal diffs only.

### 5. Exact change shape (before → after)

**Before (verbatim intent)**

- Bullet reads **CRITICAL RESOLVED**, implying XCT-012 is fully settled.

**After (example wording — adjust to match markdown link style)**

- Replace status segment with wording equivalent to: **“DOCUMENTED ONLY — Checkpoint logging acceptable for v1; state replay deferred (Q-25). Not CRITICAL RESOLVED for automated recovery.”**

Preserve the `[[wikilink]]` slug pattern used by adjacent bullets for consistency — **avoid breaking Obsidian/link conventions**.

### 6. Test additions

- **Automated:** None required (“doc edit only”).  
- **Verification:** CI or manual reviewer checklist — **grep Audit Resolutions** for `G-XCT-012` and confirm absent misleading **CRITICAL RESOLVED** for replay completeness.

### 7. Exit criteria

- Audit Resolutions no longer overstretch crash-recovery completeness; aligns with **Q-25** deferral narrative.  
- Cross-link from **Batch 11 notes** optional (not required).

### 8. Meta-rollback procedure

- Git revert documentation-only commits; restores prior Audit Resolutions text.

---

## Batch 11.3 — Q-28 / F-47: Cold-storage vs DELETE (tracking only — no implementation)

### 1. Title

**11.3 — Q-28 cold-storage soft flag (explicitly OUT OF IMPLEMENTATION SCOPE)**

### 2. Spec citation

- **Decisions log §3.3**: DELETE vs cold-storage (`migrate_to_cold_storage`); **§2 Group I Q-28**: partial — soft until compliance stance known.  
- **Doc 32 Version Snapshot Policy** **156–161** (`migrate_to_cold_storage(oldest)`).  
- **Code:** `captain-offline/captain_offline/blocks/version_snapshot.py` **`_enforce_max_versions` 133–168** — DELETE from `p3_d18_version_history`.

### 3. Pre-flight checks

-n/a (no implementation).

### 4. Planned artifacts

- **Deliverable:** A short **footnote or “Open items”** paragraph in **`CLAUDE.md` or team runbook only if stakeholders require traceability — NOT required unless product asks.** Default:** carry Q-28 only inside this Phase 11 build plan README section (self-contained).

### 5. Exact change shape

**No code edits** for cold-storage/export in Phase 11 per campaign rules.

### 6. Tests

- None.

### 7. Exit criteria

- Q-28 recorded in campaign tracking as **blocked on Isaac/compliance**.

### 8. Meta-rollback procedure

-n/a.

---

## Final Phase 11 verification (after all batches)

1. **F-08:** Grep forbids undocumented `rollback_to_version(...)` direct **destructive** path from operational code without `commit_rollback`; tests pass.  
2. **F-43:** Audit Resolutions wording verified.  
3. **Q-28:** No accidental implementation (grep **`migrate_to_cold_storage`** / **new export adapters** absent unless explicitly approved).  
4. **Anti-pattern guards:** Do not add **three-option** rollback behaviors not in decisions log/spec; do **not** implement replay engine for checkpoints in Phase 11.

---

## Cross-reference: Phase 10 plan note superseded here

Earlier draft text in `phase10_hmm_aim16_build_plan.md` suggested rollback/snapshot governance as **Phase 11 out of scope**. **This Phase 11 document supersedes** that snippet for rollback work (Q-08 requires implementation here).

---

*End of `2026-04-28_phase11_governance_safety_build_plan.md`.*
