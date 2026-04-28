# Phase 5 deferred follow-ups

**Issue tracker IDs:** Record here when filed (e.g. Linear/Jira): DEFERRED-1 → `____________`, DEFERRED-2 → `____________`, DEFERRED-3 → `____________`.

## DEFERRED-1 — Online B4 Kelly cp_prob wiring

Canvas (`Kelly_7_Layer_Pipeline.canvas` L2/L3) annotations reference reading `bocpd:{asset}` from Redis on the Online side. Code at `captain-online/captain_online/blocks/b4_kelly_sizing.py` does NOT currently read cp_prob; Online Kelly is independent of BOCPD output.

**Decision (Phase 5 review):** defer to a separate ticket. Phase 5 fixes only the offline-side reader (`b8_kelly_update._get_cp_prob`).

**Action:** open ticket `CAP-OFFLINE-F07-FOLLOWUP` titled "Online B4 Kelly: ingest BOCPD cp_prob per canvas L2/L3" with body:

- Investigate intended L2/L3 use of cp_prob in Online Kelly.
- Decide: (a) wire it in per canvas, OR (b) amend canvas to remove the annotation if the offline path is sufficient.
- If (a): add Redis read in `b4_kelly_sizing.py` mirroring the `_get_cp_prob` pattern from `b8_kelly_update.py`.

## DEFERRED-2 — F-20 stale in-memory CUSUM limits after quarterly recalibration

`captain-offline/captain_offline/blocks/orchestrator.py:995-1017` (`_run_quarterly`) calls `calibrate_and_persist` but does not reload the new limits into the live `CUSUMDetector` instances in `self._detectors`. Audit F-20 (lines 502–519). HIGH severity.

**Status at end of Phase 5:** unresolved unless Batch 4 reviewer chose to include it. Confirm and either close or carry forward.

**Action if not addressed:** open ticket `CAP-OFFLINE-F20` to merge returned limits from `calibrate_and_persist` into the live detector after every quarterly run, mirroring `_init_cusum_calibration` (lines 577–629).

## DEFERRED-3 — Doc 32 PG-15 amendment

See `2026-04-27_doc32_pg15_amendment_for_isaac.md`. Once Isaac confirms wording, apply the edit and remove this entry.

---

**Session pointer:** Phase 5 execution summary lives at `docs2/audits/2026-03-27_Build_Plans_1-12/build-plan-outputs/phase_5_execution.md` (repository has no root `MEMORY.md`).
