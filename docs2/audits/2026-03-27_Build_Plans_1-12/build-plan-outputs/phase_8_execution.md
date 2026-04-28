# phase_8 — Execution Summary

**Plan:** `docs2/audits/2026-03-27_Build_Plans_1-12/phase8_tsm_circuit_breaker_build_plan_2026-04-28.md`

**Date:** 2026-04-28

**Status:** Complete

**Note:** The runbook asked for this summary at `build-plan-outputs/phase_4_execution.md`, which is the existing Phase 4 record. This file is written as `phase_8_execution.md` alongside `phase_5_execution.md`–`phase_7_execution.md` so Phase 4 history is not overwritten.

## Batches

| # | Title | Status | Tests | Notes |
|---|--------|--------|-------|--------|
| 8.0 | Rewrite TSM MC path (`_simulate_one_path`, PG-14) | Complete | PASS | `tests/test_b7_tsm_simulation.py` (MDD per-trade, MLL daily aggregate, block size) |
| 8.1 | NULL `pass_probability` unconstrained accounts | Complete | PASS | Early return + `_write_pass_probability` |
| 8.2 | D12 `sizing_override` → MC returns | Complete | PASS | `orchestrator._run_tsm_for_account` + `run_tsm_simulation(..., sizing_override=...)` |
| 8.3 | RPT-07 Redis generation (Offline) | Complete | PASS | `_generate_rpt07`; `b6_reports.py` untouched |
| 8.4 | Cross-day loss-only `running_loss` | Complete | PASS | `_build_regression_arrays`; Q-17-ASSUMPTION comment |
| 8.5 | `r_bar = mean(y)` | Complete | PASS | `_ols_regression` return |
| 8.6 | Remove p-value gate on `beta_b` | Complete | PASS | `SIGNIFICANCE_THRESHOLD` removed; n<10 and cold_start intact |

## Files changed

- `captain-offline/captain_offline/blocks/b7_tsm_simulation.py`
- `captain-offline/captain_offline/blocks/b8_cb_params.py`
- `captain-offline/captain_offline/blocks/orchestrator.py`
- `tests/test_b7_tsm_simulation.py`
- `tests/test_b8_cb_params.py`

## Tests added

- `tests/test_b7_tsm_simulation.py` — `_simulate_one_path` MDD/MLL/block sampling; unconstrained NULL + `_write_pass_probability`; `sizing_override` scaling + default 1.0; `_generate_rpt07` on normal and unconstrained paths (with `N_PATHS` patched low and DB/Redis helpers mocked where needed for speed and offline CI).
- `tests/test_b8_cb_params.py` — `_build_regression_arrays` cross-day carry and profit skip; `_ols_regression` `r_bar` vs intercept; p-value no longer zeroing `beta_b` in OLS; `estimate_cb_params` n<10 and `cold_start` for n=50 / n=120 via mocks.

## Test results

**Phase suite (plan cross-batch guard, adjusted):** **PASS** — command used:

`PYTHONPATH=./:./captain-online:./captain-offline:./captain-command python -m pytest tests/test_b7_tsm_simulation.py tests/test_b8_cb_params.py tests/test_b8_kelly_cp_prob_source.py tests/test_b5c_circuit.py -v`

(Plan filename `tests/test_b8_kelly_update.py` does not exist; repo uses `tests/test_b8_kelly_cp_prob_source.py`.)

**Repo suite:** **Partial / environment-dependent** — With `.venv` containing `captain-offline`, `captain-online`, and `captain-command` requirements, `pytest tests/ --ignore=tests/test_account_lifecycle.py` completed with **481 passed**, **31 failed**, **1 skipped**. Failures are dominated by **QuestDB/live schema** tests (`test_schema_migrations.py`, `test_schema_d03_signal_id.py`) and several **integration/e2e** tests; none reference TSM (`b7`) or CB params (`b8_cb_params`) changes.

**Skipped/flaky:** Plan Batch 8.0–8.6 had no BLOCKED rows — none skipped. `test_account_lifecycle.py` was **ignored** for the full-suite attempt only (see below).

## Plan vs reality discrepancies

| Batch | What differed | What we did |
|-------|----------------|------------|
| 8.2 | `p3_d12_kelly_parameters.sizing_override` is a **STRING** (JSON-serialised float per `b2_level_escalation`), not a bare double in SQL | Orchestrator **parses** each row with `json.loads` / numeric coercion before `min` and `[0,1]` clamp |
| 8.2 | Plan prose says “active assets on this account”; SQL has **no `account_id` filter** | Implemented **exactly** the plan’s SQL; noted under out-of-scope |
| Tests | Plan snippets for `test_sizing_override_default_1_no_scaling` omit mocks; unconstrained path calls `_write_pass_probability` (QuestDB) | Added mocks for `_write_pass_probability` and `_generate_rpt07` so the test runs without DB |
| Tests | Plan uses full `N_PATHS` (10k) in MC tests | Patched `N_PATHS` to a small value in tests that exercise the MC loop (practical CI runtime) |
| Deliverable path | Request named `phase_4_execution.md` | Wrote **`phase_8_execution.md`** to avoid deleting the Phase 4 execution record |

## Out-of-scope issues spotted (for future audits; not fixed here)

- **`tests/test_account_lifecycle.py`** replaces `sys.modules["shared"]` with a `MagicMock`, breaking collection/import of real `shared.*` for many other tests in the same process (documented in prior phase outputs).
- **D12 query** in 8.2: global min of non-null `sizing_override` across all assets may be conservative but not “per account” unless schema/join is extended later.
- **System Python** on this runner: `/usr/bin/python3` lacked `scipy` while another `python3` on PATH had it; **`b8_cb_params`** needs the same dependency set as `captain-offline/requirements.txt` for consistent local runs.

## Blocked/skipped batches

None. All batches 8.0–8.6 executed.

## Handoff notes

- **Q-17:** Batch 8.4 uses **unsigned loss-only** cumulative `L_b` with `# Q-17-ASSUMPTION`; decisions log says reverse if Isaac specifies signed cumulative.
- **RPT-07:** Offline now writes Redis key `captain:reports:rpt07:{account_id}` (24h TTL). Command `b6_reports` consumer should remain compatible; verify in staging that Redis is available where TSM runs.
- **Unconstrained accounts:** `pass_probability` is `None`, `n_paths` is `0`, and D08 write is skipped if there is **no** existing D08 row (silent), matching the plan.
- **Regression testing:** Run the phase guard command above first; for full suite use a **venv** with all service `requirements.txt` files and either **ignore** `test_account_lifecycle.py` or isolate it; expect **QuestDB-dependent** tests to fail without a live DB.
- **Requested deliverable path:** If you need this content **in** `phase_4_execution.md`, copy or merge manually; that file currently remains the Phase 4 AIM lifecycle summary.
