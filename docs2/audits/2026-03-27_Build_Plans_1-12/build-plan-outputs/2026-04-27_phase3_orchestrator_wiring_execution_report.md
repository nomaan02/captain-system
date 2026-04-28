# Phase 3 — Orchestrator Wiring & Dispatch — Execution Summary

**Plan:** `/home/nomaan/captain-system/docs2/audits/2026-03-27_Build_Plans_1-12/2026-04-27_phase3_orchestrator_wiring_build_plan.md`
**Date:** 2026-04-27 (executed late evening — 2026-04-28 00:05 GMT+1)
**Status:** **Complete** (5 of 6 batches landed; B2 BLOCKED per plan as expected)

---

## Batches

| # | Title | Status | Tests | Notes |
|---|---|---|---|---|
| B1 | F-01 — skeleton-wire PG-01C dispatch (post-session hook) | Complete | 3 (skipped on host: scipy missing) | `SESSION_CLOSE` publish from Online `_run_session` legacy path **and** OR-resolved path; Offline `_handle_session_close` with idempotency token; stub observation panel preserves cold-start path. |
| B2 | F-04 — `blend_signal` consumer | **Blocked** | 0 | Awaiting Isaac re-ask Q-04 (decisions log §3.2). Not implemented. |
| B3 | F-13 — PG-04 drift uses real features + bootstrap-fit AE | Complete | 3 (passing) | Canonical loader `load_aim_features(asset_id, aim_id, as_of=...)` does **not** exist in `shared/aim_feature_loader.py`. Added `SimpleAutoEncoder.bootstrap_fit()` and a `TODO[F-13]` block. Existing modifier-JSON path retained as a documented gap; full loader is a Phase 4+ scope item. |
| B4 | F-20 — Quarterly PG-07 in-memory CUSUM refresh | Complete | 3 (skipped on host: scipy) | `calibrate_and_persist` now returns `Dict[int, float] \| None`; `_run_quarterly` refreshes `self._detectors[asset_id][1].sequential_limits`. |
| B5 | F-21 — Doc-edit only (`AWAITING_MANUAL` is by-design) | Complete | n/a | Three doc edits per plan §6.3. No code change. |
| B6 | F-42 — L3 immediate dispatch | Complete | 5 (skipped on host: scipy) | `trigger_level3` returns dict with `level=3`; both `_handle_trade_outcome` and `_handle_signal_outcome` call `_dispatch_pending_jobs(filter_job_type="AIM14_EXPANSION", filter_asset=asset_id)` immediately. `P1P2_RERUN` stays AWAITING_MANUAL (preserves F-21). |

---

## Files changed

- `captain-online/captain_online/blocks/orchestrator.py` — added `publish_to_stream` import; emit `SESSION_CLOSE` to `STREAM_COMMANDS` at end of `_run_session` legacy path **and** at OR-resolved completion in `_check_or_breakouts`. Uses existing `_ET` (America/New_York).
- `captain-offline/captain_offline/blocks/orchestrator.py` — added `SESSION_CLOSE` branch in `_handle_command`; new `_handle_session_close()` (idempotency token) and `_run_aim16_hmm_training()` skeleton; `_run_quarterly` captures `calibrate_and_persist` return and refreshes in-memory CUSUM `sequential_limits`; `_dispatch_pending_jobs` accepts optional `filter_job_type` / `filter_asset`; both `_handle_trade_outcome` and `_handle_signal_outcome` immediate-dispatch `AIM14_EXPANSION` on `level==3`.
- `captain-offline/captain_offline/blocks/b1_aim16_hmm.py` — added `build_observation_panel_stub(asset_universe, lookback_days=60)` returning `(np.zeros((0,7)), np.zeros((0,)), 0)`.
- `captain-offline/captain_offline/blocks/b1_drift_detection.py` — added `SimpleAutoEncoder.bootstrap_fit()` (no-op when no history); `run_drift_detection` calls bootstrap on unfitted AE; empty-features short-circuit; `TODO[F-13]` block for canonical loader gap.
- `captain-offline/captain_offline/blocks/b2_cusum.py` — `calibrate_and_persist` returns `Dict[int, float] \| None`.
- `captain-offline/captain_offline/blocks/b2_level_escalation.py` — `trigger_level3` returns `{"level": 3, "l3_triggered": True, "asset_id", "enqueued", "source"}`; `check_level_escalation` propagates the result.
- `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` — line 328: `SCHEDULE programs_1_2_rerun(asset)` → `MANUAL programs_1_2_rerun(asset)  # AWAITING_MANUAL — no automation target per Q-13 (2026-04-27)`.
- `docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md` — F-21 severity changed `HIGH` → `RESOLVED`; appended Resolution paragraph citing decisions log Q-13.
- `docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md` — Q-13 row appended `Reclassified F-21 to RESOLVED on 2026-04-27 via Phase 3 doc-edit batch B5_F-21.`

## Tests added

- `tests/test_offline_session_close_dispatch.py` — asserts (a) `SESSION_CLOSE` cmd routes to `_handle_session_close` and triggers `train_aim16_hmm` + `save_hmm_state` once each in cold-start mode; (b) duplicate token (same `session_id`+`closed_at`) is deduped; (c) PG-01C is global, not per-asset (single training run per close).
- `tests/test_online_session_close_publish.py` — asserts `_run_session` (legacy non-OR path) publishes exactly one `SESSION_CLOSE` to `STREAM_COMMANDS` with correct `type`, `session_id`, `closed_at`.
- `tests/test_pg04_drift.py` — asserts (a) empty feature vector skips cleanly; (b) unfitted AE without history → warm-up gate stays active (`bootstrap_fit` no-ops); (c) pre-fitted AE produces `reconstruction_error` and feeds ADWIN.
- `tests/test_pg07_quarterly_recalibration.py` — asserts (a) `_run_quarterly` refreshes in-memory CUSUM `sequential_limits` from new return; (b) returns `None` → in-memory dict unchanged; (c) `calibrate_and_persist` returns the persisted dict.
- `tests/test_l3_immediate_dispatch.py` — asserts (a) `trigger_level3` returns the new dict shape with `level=3`; (b) `check_level_escalation` returns `None` below threshold; (c) sustained high `cp_prob` triggers L3 + immediate `AIM14_EXPANSION` dispatch in same call frame; (d) L2-only does NOT immediate-dispatch; (e) filter SQL excludes `P1P2_RERUN` (preserves F-21).

All five new test files use `pytest.importorskip("scipy")` or `pytest.importorskip("pysignalr")` where the orchestrator transitively imports container-only deps. They auto-skip on the host and run inside the captain-offline / captain-online containers (or any host with scipy + hmmlearn + pysignalr installed).

---

## Test results

- **Phase suite (5 new test files):** **3 passed, 4 skipped, 0 failed.** The 4 skipped tests are scipy/pysignalr-gated (per CLAUDE.md: "Some tests need container-only deps").
- **Repo suite (full unit run with the standard ignore list + pre-existing scipy-only `test_b2_bocpd_cusum_combined.py` + QuestDB-only `test_schema_migrations.py`):** **190 passed, 4 skipped, 0 failed** (40s wall).
- **Skipped/flaky:**
  - `tests/test_offline_session_close_dispatch.py` (3 tests) — needs scipy.
  - `tests/test_pg07_quarterly_recalibration.py` (3 tests) — needs scipy.
  - `tests/test_l3_immediate_dispatch.py` (5 tests) — needs scipy.
  - `tests/test_online_session_close_publish.py` (1 test) — needs pysignalr.
  - Pre-existing untracked `tests/test_b2_bocpd_cusum_combined.py` — collection error (scipy missing). Not from Phase 3.
  - Pre-existing `tests/test_schema_migrations.py` — 10 failures from `psycopg2.OperationalError` (no live QuestDB). Marked `real_questdb` and not part of the unit suite per CLAUDE.md.

### Plan §8.3 grep gates

| Gate | Result |
|---|---|
| `grep -rn "SCHEDULE programs_1_2_rerun" docs2/spec-docs-02/` | empty ✓ |
| `grep -rn "train_aim16_hmm" captain-offline/` | callers in `orchestrator.py:587, 607` ✓ |
| `grep -n "filter_job_type" captain-offline/.../orchestrator.py` | 5 hits (signature + 2 call sites + SQL filter + docstring) ✓ |
| `grep -rn "SESSION_CLOSE" captain-online/ captain-offline/` | publish at online `:379, 506`; handler at offline `:464` ✓ |

---

## Plan vs reality discrepancies

- **B1 — `_handle_command` field name.** Plan example uses `payload.get("cmd_type")`; actual code reads `command.get("type", "")`. Followed the existing pattern — `SESSION_CLOSE` is published with `"type": "SESSION_CLOSE"`, not `"cmd_type"`.
- **B1 — `save_hmm_state` signature.** Plan example passes `conn=...` and `session_id=...`. Real signature is `save_hmm_state(state)` only — function gets its own cursor via `shared.questdb_client.get_cursor()`. Called the real signature; no `conn`/`session_id` kwargs.
- **B1 — no `_questdb_conn()` method on offline orchestrator.** Existing pattern is `from shared.questdb_client import get_cursor; with get_cursor() as cur: ...`. Used the existing pattern for the asset-universe fetch in `_run_aim16_hmm_training`.
- **B1 — OR-tracker session timing.** Plan only specifies the publish at end of `_run_session`. The OR-tracker path returns early from `_run_session` and finishes inside `_check_or_breakouts`. Added a parallel publish there so PG-01C still fires for OR sessions. One-line scope expansion, same payload shape, documented.
- **B3 — canonical AIM feature loader does NOT exist.** Plan assumed `shared.aim_feature_loader.load_aim_features(asset_id, aim_id, as_of=...)`. Repo has `load_replay_features(target_date, assets)` plus internal helpers — different shape. Refused to invent the API. Added `SimpleAutoEncoder.bootstrap_fit()` so the AE warm-up gate stops being a permanent skip, and left a `TODO[F-13]` block at the feature-build site. Drift now exits cleanly on empty features and computes reconstruction error when the AE is fitted, but the canonical per-AIM feature ETL is a Phase 4+ scope item.
- **B6 — duplicate L3 handling.** Both `_handle_trade_outcome` and `_handle_signal_outcome` now run the same escalation-then-immediate-dispatch sequence. Identified as a small refactor opportunity but not done in Phase 3 per the plan's "stop, file as Phase-N follow-up" rule.
- **Test extensions to non-existent files.** Plan §5.5 / §7.5 ask to extend `tests/test_b2_cusum.py` and `tests/test_b2_level_escalation.py` — neither exists in the repo. Folded the equivalent assertions into the new `tests/test_pg07_quarterly_recalibration.py` and `tests/test_l3_immediate_dispatch.py` respectively.

---

## Out-of-scope issues spotted

(For future audit cycles — not acted on this phase.)

- **`cmd_type` vs `type` payload-field inconsistency** across command handlers and publishers. Some sites reassign `cmd_type` from `command.get("type", "")` and downstream code mixes the two names. Mostly cosmetic but the next refactor should pick one.
- **`b1_drift_detection._load_drift_states` / `_save_drift_states`** read/write D04 detector states as JSON in `adwin_states` — independent of the canonical per-AIM feature loader the spec calls for. Captured implicitly in the `TODO[F-13]` block; full fix is downstream.
- **OR-tracker session-close timing** may emit `SESSION_CLOSE` later than the spec's "session close" instant (whenever the OR resolves, vs scheduled close time). Phase 4 transitions work may want a tighter trigger.
- **Offline orchestrator L3 handlers in two places.** `_handle_trade_outcome` and `_handle_signal_outcome` should likely share an `_apply_escalation(...)` helper.
- **Pre-existing untracked `tests/test_b2_bocpd_cusum_combined.py`** crashes at collection on hosts without scipy. Either add `pytest.importorskip("scipy")` or move it under a container-only marker. Pre-existing — not introduced by Phase 3.
- **`test_schema_migrations.py`** uses `pytest.mark.real_questdb` but the marker isn't registered (warning at collection). Register it in `pyproject.toml` / `setup.cfg`.

---

## Blocked / skipped batches

- **B2 (F-04 — `blend_signal` consumer).** Blocked on Isaac re-ask Q-04 (decisions log §3.2): explicit confirmation that (a) the consumer is Online B6 and (b) PG-11 writes `p3_d06b_active_transitions` for B6 to read. Until Isaac answers, no implementation can land without inventing a third option (forbidden by spec authority chain). **Unblocks when:** Isaac answers Q-04. Lift into Phase 3.5 or fold into Phase 4.

---

## Handoff notes for Nomaan

1. **B1 is skeleton only.** The HMM training call writes a cold-start D26 row at every session close. Real Baum-Welch fit and the 7-D observation panel land in Phase 10. There is a `TODO[F-01 / Phase 10]` comment in `_run_aim16_hmm_training` pointing at the future plan.
2. **B3 is partial.** Drift no longer skips forever on unfitted AE, but until the canonical per-AIM feature loader exists, drift still consumes the modifier-JSON value list (current code's input shape). The `TODO[F-13]` block in `b1_drift_detection.run_drift_detection` is the next-phase entry point. **This is a documented deviation from the audit's recommended fix** — please confirm whether to schedule a feature-loader phase or accept the partial as-is.
3. **`SESSION_CLOSE` fires from both `_run_session` and `_check_or_breakouts`.** Inside a container with hmmlearn + scipy + pysignalr installed, you'll see one `[pg01c]` log line per session close (NY ~16:00 ET, LON ~12:30 ET, APAC ~02:00 ET). If the OR-tracker is enabled, the publish moves to OR resolution time — confirm this matches the cadence Isaac wants (Q-03 says "post-session global", not "pre-OR" — semantics may need tightening in Phase 4).
4. **Idempotency token.** `_handle_session_close` uses `f"{session_id}:{closed_at}"` as a dedup token. If Online ever rebroadcasts on retry, duplicate training runs are suppressed.
5. **Quarterly CUSUM refresh.** After `_run_quarterly` runs (1 Jan / 1 Apr / 1 Jul / 1 Oct), `self._detectors[asset_id][1].sequential_limits` is hot-swapped without a process restart. Verify in production logs by tailing `[pg07] refreshed in-memory CUSUM limits for ...` after the next quarterly tick.
6. **L3 immediate dispatch.** A trade outcome that pushes `cp_prob > 0.9` for 5+ trades now triggers `AIM14_EXPANSION` synchronously inside `_handle_trade_outcome` (no longer waits for `_run_daily`). `P1P2_RERUN` still parks at `AWAITING_MANUAL` per F-21 / Q-13.
7. **Container-only test deps.** Four of the five new test files auto-skip on the host because of scipy/pysignalr/hmmlearn. To run them locally: `pip install scipy hmmlearn pysignalr` (mirrors the container requirements). In CI, they should run inside the captain-offline / captain-online image.
8. **Pre-existing landmines unrelated to Phase 3.** Untracked `tests/test_b2_bocpd_cusum_combined.py` crashes on hosts without scipy; `tests/test_schema_migrations.py` needs a live QuestDB. Both pre-existed Phase 3 — flagging so they don't surprise you when running the suite.
9. **Nothing committed.** All changes are unstaged. Commit when you're ready: the recommended message is something like:
   > `Phase 3 — wire PG-01C skeleton, refresh CUSUM in-memory, immediate L3 dispatch, real PG-04 AE bootstrap; reclassify F-21 (DOC); B2/F-04 BLOCKED on Q-04 re-ask`
10. **Next phase.** Phase 4 (AIM lifecycle / DMA / HDWM) is queued. The `TODO[F-13]` block makes a natural feed for Phase 4's per-AIM feature loader work.
