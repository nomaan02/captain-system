### Summary structure

phase_11 — Execution Summary

Plan: `docs2/audits/2026-03-27_Build_Plans_1-12/2026-04-28_phase11_governance_safety_build_plan.md`

Date: 2026-04-28

Status: Complete

Batches

| # | Title | Status | Tests | Notes |
|---|--------|--------|-------|--------|
| 11.1 | Two-phase rollback (`request_rollback` → `commit_rollback`) | Complete | `tests/test_version_rollback_two_phase.py` (6 tests) | Redis proposal store: `captain:rollback_proposal:{uuid}` JSON with TTL (`CAPTAIN_ROLLBACK_PROPOSAL_TTL_SEC`, default 604800s). `_publish_rollback_alert` extended for `VERSION_ROLLBACK_PROPOSAL` + optional `rollback_request_id`. |
| 11.2 | G-XCT-012 Audit Resolutions doc rephrase (F-43) | Complete | N/A (doc-only) | Bullet no longer claims CRITICAL RESOLVED for full automated recovery. |
| 11.3 | Q-28 cold-storage soft flag | Skipped (by design) | None | No code per plan — deferred to compliance / Isaac. |

Files changed

- `captain-offline/captain_offline/blocks/version_snapshot.py` — two-phase API, Redis-backed proposals, `rollback_to_version` → `DeprecationWarning` + `NotImplementedError`.
- `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` — Audit Resolutions line for G-XCT-012 reworded for Q-25.
- `tests/test_version_rollback_two_phase.py` — new test module.

Tests added

- `tests/test_version_rollback_two_phase.py` — rejects do not persist proposals; ADOPT does not call `snapshot_before_update` before commit; wrong `approval_proof` rejected; successful commit + idempotent second `commit_rollback` (`ALREADY_COMPLETED`); distinct `request_rollback` calls get distinct ids/tokens; `rollback_to_version` raises `NotImplementedError`.

Test results

Phase suite: **pass** — `python3 -m pytest tests/test_version_rollback_two_phase.py tests/test_version_snapshot_coverage.py` → **10 passed**, 1 expected `DeprecationWarning` from `test_rollback_to_version_raises`.

Repo suite: **fail / not fully validated** — full `tests/` collection reports **27 errors at import time** (example: `ModuleNotFoundError: No module named 'shared.topstep_client'; 'shared' is not a package` when importing certain modules). Appears to be an existing environment / import-path / `shared` shadowing issue, not introduced by Phase 11. No Phase 11 edits to `shared/` or topstep.

Skipped/flaky: Full-repo run not green; individual Phase 11 tests are deterministic. **5 skipped** globally per prior suite config (unchanged by this work).

Plan vs reality discrepancies

| Batch | What differed | Resolution |
|-------|----------------|------------|
| 11.1 | Plan listed line ranges 404–481 for old `rollback_to_version`; implementation replaced that block with `request_rollback` / `commit_rollback` and a stub `rollback_to_version`. | Functional match to plan; line numbers shifted naturally. |
| 11.1 | Plan example used `approval_proof` in narrative; `request_rollback` returns key **`approval_token`** (same value passed into `commit_rollback` as **`approval_proof`**). | Documented here; API is consistent. |
| 11.1 | No separate Command/CLI caller in this execution (plan marked optional). | Library surface only; ops can wire `commit_rollback` to an admin tool later. |

Out-of-scope issues spotted

- **Regression path** after failed `_run_regression_tests` sets proposal status `FAILED_REGRESSION` in Redis — a second `commit_rollback` returns `INVALID_PROPOSAL_STATE:FAILED_REGRESSION` rather than auto-retry (intentionally conservative; reassess in a later phase if retry semantics are needed).
- **`version_manager.py`** referenced in decisions log for Q-28 — not present in repo; DELETE-only pruning remains in `version_snapshot.py` (`_enforce_max_versions`).
- **`shared` import errors** when collecting the full test tree — worth a hygiene pass (PYTHONPATH / package layout / test isolation).

Blocked/skipped batches

- **11.3 (Q-28 cold-storage):** Blocked on product/compliance stance on `migrate_to_cold_storage` vs DELETE — **unblocks** only if decisions log promotes implementation beyond v1 deferral.

Handoff notes

- **Operations / regression:** Any external tool that called `rollback_to_version` will now get **`NotImplementedError`**. Integrate **`request_rollback` → hand `approval_token` to authorized admin path → `commit_rollback`**. Ensure **Redis** available for pending proposals (same as existing alert pub path).
- **`pytest` ergonomics:** Optionally add `filterwarnings` ignore for `DeprecationWarning` on the stub test, or assert warning type only.
- **Next phase:** Phase 12 hygiene — can remove `rollback_to_version` symbol entirely if grep stays clean.
