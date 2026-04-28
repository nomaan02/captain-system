# phase_2 — Execution Summary

**Plan:** [2026-04-27_phase2_persistence_contracts_build_plan.md](./2026-04-27_phase2_persistence_contracts_build_plan.md)

**Date:** 27/04/2026

**Status:** Partial

All five batches (B2-3 → B2-4 → B2-5 → B2-2 → B2-1) were implemented and the **Phase 2 dedicated test set** passes under the project venv (see Test results). The **full** `tests/` run did not achieve a clean pass in this environment due to missing QuestDB and a pre-existing `test_account_lifecycle.py` / `sys.modules["shared"]` interaction (see below). No batch was marked BLOCKED in the plan.

---

## Batches

| # | Title | Status | Tests | Notes |
|---|--------|--------|--------|--------|
| B2-3 | F-05 AIM-13 FRAGILE JSON dict + ROBUST neutral | Complete | 3 passed (`tests/test_b5_sensitivity.py`) | Pre-existed in working tree; verified + tests. `_compute_dsr` stubbed in tests to avoid scipy when absent on system python. |
| B2-4 | F-17 DECAY_ALERT message / event_type / notif_id | Complete | 2 passed (`tests/test_b2_decay.py`) | Uses `_compute_reduction_factor` for Level 2 copy (equivalent to plan formula). |
| B2-5 | F-18 paper_trader stream + dead imports + redis comment | Complete | 1 passed (`tests/test_paper_trader_stream.py`) | Imports `paper_trader` with dotenv/websocket/pysignalr stubs at module load; asserts `paper_trader.publish_to_stream` (bound import). |
| B2-2 | F-03 combined D04 persist | Complete | 6 passed (`tests/test_b2_bocpd_cusum_combined.py`) | **Plan vs reality:** combined INSERT stores **full** `BOCPDDetector.to_dict()` JSON in `bocpd_run_length_posterior` (matches `_restore_detectors`), not only `run_length_posterior` vector as in plan snippet. |
| B2-1 | F-02 snapshot_before_update + AIM_LIFECYCLE | Complete | 4 passed (`tests/test_version_snapshot_coverage.py`) | `TRIGGERS` is a **set of strings** in repo (not a class); added `"AIM_LIFECYCLE"` to the set. Tests use `patch`, not `pytest-mock` `mocker`. |

---

## Files changed

- `captain-offline/captain_offline/blocks/b5_sensitivity.py` — FRAGILE/ROBUST D01 JSON envelopes (already present; Confirmed).
- `captain-offline/captain_offline/blocks/b2_level_escalation.py` — DECAY_ALERT payload + `import uuid`.
- `scripts/paper_trader.py` — `publish_to_stream(STREAM_TRADE_OUTCOMES, outcome)`; imports.
- `shared/redis_client.py` — deprecation comment on `CH_TRADE_OUTCOMES`.
- `captain-command/captain_command/blocks/b1_core_routing.py` — removed unused `CH_TRADE_OUTCOMES` import.
- `captain-command/captain_command/blocks/orchestrator.py` — removed unused `CH_TRADE_OUTCOMES` import.
- `captain-offline/captain_offline/blocks/b2_bocpd.py` — `from __future__ import annotations`; `persist_combined_detector_state`; `CUSUMDetector` import; removed per-trade D04 from `run_bocpd_update`.
- `captain-offline/captain_offline/blocks/b2_cusum.py` — removed per-trade D04 from `run_cusum_update`.
- `captain-offline/captain_offline/blocks/orchestrator.py` — `persist_combined_detector_state` after BOCPD+CUSUM in `_handle_trade_outcome` and `_handle_signal_outcome`.
- `captain-offline/captain_offline/blocks/version_snapshot.py` — `AIM_LIFECYCLE` in `TRIGGERS` set.
- `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py` — snapshots before `_update_aim_status` / `_update_warmup_progress`.
- `captain-offline/captain_offline/blocks/b1_hdwm_diversity.py` — snapshots before D01 and D02 in `_reactivate_aim`.
- `tests/test_b5_sensitivity.py` — **new**.
- `tests/test_b2_decay.py` — **new**.
- `tests/test_paper_trader_stream.py` — **new**.
- `tests/test_b2_bocpd_cusum_combined.py` — **new**.
- `tests/test_version_snapshot_coverage.py` — **new**.
- `docs2/audits/2026-03-27_Build_Plans_1-12/build-plan-outputs_2026-04-phase2_execution.md` — **this file**.

---

## Tests added

| File | What it asserts |
|------|------------------|
| `tests/test_b5_sensitivity.py` | FRAGILE writes `{"modifier":0.85,"reason_tag":"AIM13_FRAGILE"}`; ROBUST writes `SENSITIVITY_NORMAL`; `parse_json` + `_aim13_sensitivity` round-trip. |
| `tests/test_b2_decay.py` | Level 2/3 CH_ALERTS JSON includes `message`, `event_type`, `notif_id`. |
| `tests/test_paper_trader_stream.py` | `_close_position` calls `publish_to_stream` with `STREAM_TRADE_OUTCOMES`; no pub/sub to `captain:trade_outcomes`. |
| `tests/test_b2_bocpd_cusum_combined.py` | Combined INSERT columns; per-trade functions write no D04; `_get_cp_prob` reads row; `_restore_detectors`; `calibrate_and_persist` still hits D04. |
| `tests/test_version_snapshot_coverage.py` | `AIM_LIFECYCLE` before D01/D02 lifecycle writes; tier retrain still uses `AIM_RETRAIN`. |

---

## Test results

**Phase 2 batch tests (venv):** 16 passed (command: `pytest tests/test_b5_sensitivity.py tests/test_b2_decay.py tests/test_paper_trader_stream.py tests/test_b2_bocpd_cusum_combined.py tests/test_version_snapshot_coverage.py`).

**Repo suite:** `pytest tests/ --ignore=tests/test_account_lifecycle.py` → **255 passed, 22 failed** in this run. Failures are overwhelmingly **QuestDB/psycopg2 connection refused** (localhost:8812) for integration/schema/stress tests; not attributed to Phase 2 logic without a running DB.

**With `test_account_lifecycle.py` included:** collection fails for modules that need the real `shared` package after that test module replaces `sys.modules["shared"]` with a `MagicMock` (documented in `test_account_lifecycle.py` header). This is **pre-existing**; not introduced by Phase 2.

**Phase suite:** pass (the 16 tests above).

**Repo suite:** inconclusive / environment-limited — pass count 255; failures 22 (DB + shared mock interaction if account_lifecycle included).

**Skipped/flaky:** none for the 16 Phase 2 tests.

---

## Plan vs reality discrepancies

| Batch | What differed | What we did |
|-------|----------------|-------------|
| B2-3 | Plan shows `TRIGGERS.AIM_LIFECYCLE`-style API; tests reference `mock_db` helpers that do not exist. | Used `monkeypatch` + `MagicMock` cursor; stubbed `_compute_dsr` where scipy missing. Plan’s `_aim13_sensitivity(features=...)` — actual signature is `(f, state)` positional. |
| B2-4 | Plan inlines `reduction_factor` formula. | Used existing `_compute_reduction_factor(severity)` for the message (same math). |
| B2-5 | Plan shows inline `from shared.redis_client import ...` inside `_close_position`; test uses `PaperTrader(redis_client=...)` which does not exist. | Imports at top of `paper_trader.py`; test patches `paper_trader.publish_to_stream` (bound name). |
| B2-2 | Plan’s `persist_combined_detector_state` uses `json.dumps(bocpd_state["run_length_posterior"])` for the first BOCPD column. | Codebase `_restore_detectors` loads `bocpd_run_length_posterior` as **full** `BOCPDDetector.from_dict` JSON; combined persist uses `json.dumps(bocpd_det.to_dict())` for that column to match existing restore path. |
| B2-1 | Plan shows `class TRIGGERS` with attributes. | Repo uses `TRIGGERS` as a **set**; added `"AIM_LIFECYCLE"` string. Plan uses `mock_db_context` / `TRIGGERS.AIM_LIFECYCLE` in tests. | Used `patch` + string `"AIM_LIFECYCLE"` / `"AIM_RETRAIN"`. |

---

## Out-of-scope issues spotted

- `tests/test_account_lifecycle.py` replaces `sys.modules["shared"]` with a mock; breaks any co-collected test needing the real `shared` package — consider isolating that test (separate process or session-scoped restore).
- Full integration tests require **QuestDB** on `localhost:8812` (or configured env).
- System `python3` without venv may lack `scipy`, `psycopg2`, etc.; project expects `captain-offline/requirements.txt` / venv.

---

## Blocked/skipped batches

None from the plan.

---

## Handoff notes

- Use **`.venv`** (or equivalent) with `pip install -r captain-offline/requirements.txt` plus `requests` (and `cryptography` if running command API tests) for local pytest.
- **Regression / CI:** run the **16 Phase 2 tests** as a smoke group; for full suite, start QuestDB or mark DB tests skipped, and **do not** rely on collecting `test_account_lifecycle` in the same session as tests that `import shared.*` unless the shared mock is fixed.
- Combined D04 row semantics: **BOCPD column still holds full serialized BOCPD state** (unchanged from prior per-trade BOCPD write), now **co-written** with CUSUM columns and `current_changepoint_probability` in one INSERT after each trade outcome (and signal outcome path).
