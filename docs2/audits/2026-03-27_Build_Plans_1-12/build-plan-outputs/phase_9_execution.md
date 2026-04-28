# phase_9 — Execution Summary

**Plan:** `docs2/audits/2026-03-27_Build_Plans_1-12/2026-04-28_phase9_block9_diagnostic_build_plan.md`  
**Date:** 2026-04-28  
**Status:** Complete  

*(Deliverable note: instructions referenced `phase_4_execution.md`; this Phase 9 summary is stored as `phase_9_execution.md` to avoid overwriting Phase 4 artifacts.)*

## Batches

| # | Title | Status | Tests | Notes |
|---|--------|--------|-------|-------|
| B1 | F-35 / Q-19 — D3 per-asset P1/P2 staleness (`p3_d22b`) | Complete | `tests/test_b9_diagnostic_phase9.py::test_compute_d3_never_queries_global_injection_history` | Removed `p3_d06_injection_history` from `compute_d3`; composite uses 3 weights (0.40 / 0.35 / 0.25); `PIPELINE_STALENESS` uses worst per-asset staleness |
| B2 | F-36 / Q-20 — D4 monthly AIM hit rate | Complete | `test_modifier_pnl_hit_basic`, `test_compute_d4_monthly_window_sql_uses_trade_outcome_only` | Rolling window `MONTHLY_HIT_WINDOW_DAYS = 31`; D4 reads `p3_d03_trade_outcome_log` only |
| B3 | F-37 / Q-21 — D7 deferred | Complete | `test_run_diagnostic_weekly_no_research_pipeline_key` | Deleted `compute_d7`; `scores` omits `research_pipeline`; `LEVEL3_UNRESOLVED` branch retained for legacy queue items |
| B4 | Q-34 — `overall_health` equal weights | Complete | `test_overall_health_equal_weight_weekly_monthly`, monthly/weekly `run_diagnostic` tests | `_overall_health_equal_weight`; WEEKLY 6 dims, MONTHLY 7 |
| B5 | F-37 optional — D5 weekly scheduling | Skipped | — | Per plan default — product gate not opened |

## Files changed

- `captain-offline/captain_offline/blocks/b9_diagnostic.py`
- `tests/test_b9_diagnostic_phase9.py`

## Tests added

| File | Asserts |
|------|---------|
| `tests/test_b9_diagnostic_phase9.py` | D3 SQL never references `p3_d06_injection_history`; `_modifier_pnl_hit` directional rules; `_overall_health_equal_weight` 1/N; `run_diagnostic(WEEKLY)` has no `research_pipeline` key and mean matches mocks; MONTHLY includes `edge_trajectory` in mean; D4 SQL hits `p3_d03` not `p3_d02` |

## Test results

| Suite | Result |
|-------|--------|
| Phase targeted (`pytest tests/test_b9_diagnostic_phase9.py -v`) | **Pass** (6 tests) |
| Plan checklist `tests/test_schema_migrations.py::test_b3_*` | **Not run** — module marked `@pytest.mark.real_questdb`; QuestDB not available on host (`connection refused :8812`) |
| Full repo (`pytest tests/`) | **Blocked at collection** — 25 files error on import/collection (e.g. missing `AlgorithmImports` / environment); not attributed to Phase 9 |

## Plan vs reality discrepancies

| Batch | Delta | Resolution |
|-------|-------|------------|
| B1 pre-flight | Could not run live `SHOW COLUMNS FROM p3_d22b_asset_rerun_status` | Relied on `shared/canonical_schemas.py` DDL + existing Phase 1 design; integration schema tests require QuestDB |
| B3 | Plan suggested grep/remove `LEVEL3_UNRESOLVED` in `_check_constraint_resolution` | **Kept** branch so historic RESOLVED items mentioning Level 3 still verify; D7 no longer creates new `LEVEL3_*` queue rows |
| Deliverable path | User template pointed at `phase_4_execution.md` | Wrote **`phase_9_execution.md`** here |

## Out-of-scope issues spotted

- **Repo test harness:** Many tests fail **collection** before run (`AlgorithmImports`, etc.) — environment/setup issue outside Phase 9.
- **`real_questdb` tests** (`test_schema_migrations.py`) require a live QuestDB instance; CI/local docs should note when to skip vs run.

## Blocked / skipped batches

- **B5** — Optional D5 weekly scheduling; explicitly skipped per plan §5.3 default.

## Handoff notes

- **GUI:** `captain_command/blocks/b2_gui_data_server.py` iterates `scores.items()` — omitting `research_pipeline` is compatible.
- **Anti-regression grep:** `compute_d7`, `research_pipeline`, and `p3_d06_injection_history` are absent from `b9_diagnostic.py` after Phase 9.
- **Regression testing:** Run `pytest tests/test_b9_diagnostic_phase9.py`; with QuestDB up, add `pytest tests/test_schema_migrations.py::test_b3_d22b_table_exists tests/test_schema_migrations.py::test_b3_compute_d3_empty_table_graceful`.
- **Optional doc polish:** Module still references “Reads … D06” in header while D3 no longer queries injection history for staleness — harmless label drift only.
