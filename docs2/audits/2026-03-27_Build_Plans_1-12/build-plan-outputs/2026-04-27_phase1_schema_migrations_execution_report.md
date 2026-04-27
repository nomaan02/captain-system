# Phase 1 Schema Migrations — Execution Report

**Build plan:** `docs2/audits/2026-03-27_Build_Plans_1-12/2026-04-27_phase1_schema_migrations_build_plan.md`  
**Executed:** 2026-04-27  
**Scope:** Batches 0–4 (QuestDB migrations, `p2_d07_regime_models`, D03 `model_m`, D22b sibling table, D26 doc ratification)

---

## Summary of code changes

| Area | File(s) | Change |
|------|---------|--------|
| **Batch 0** | `shared/canonical_schemas.py` | Added `CANONICAL_MIGRATIONS` with `M001_d03_add_model_m` (`ALTER TABLE p3_d03_trade_outcome_log ADD COLUMN model_m INT`). |
| | `scripts/init_questdb.py` | Imports `CANONICAL_MIGRATIONS`; after the `CANONICAL_DDLS` loop, runs each migration with idempotent try/except (`[OK]` / `[SKIP]` / `[FAIL]`). |
| **Batch 1** | `shared/canonical_schemas.py` | Added `P2_D07_REGIME_MODELS` DDL in new “P2 research output tables” section; appended `P2_D07_REGIME_MODELS` to `CANONICAL_DDLS` in the group before `AUDIT_LOG`. |
| **Batch 2** | `shared/canonical_schemas.py` | Added `model_m INT` to `D03_TRADE_OUTCOME_LOG` DDL before `ts`. |
| | `captain-online/.../b7_position_monitor.py` | Added `_get_locked_m()`; `_write_trade_outcome()` inserts `model_m` from D00. |
| | `scripts/paper_trader.py` | Added `_get_locked_m("ES")` (ES-only script, no `pos.asset` on `Position`); `model_m` on open/close D03 inserts. |
| | `shared/trade_source.py` | `read_d03`: `SELECT` includes `model_m`; `"model"` uses DB value with fallback 4. `seed_d03_from_synthetic`: INSERT includes `model_m` from `t.get("model_m")`. |
| **Batch 3** | `shared/canonical_schemas.py` | Added `D22B_ASSET_RERUN_STATUS`; inserted `D22B_ASSET_RERUN_STATUS` after `D22_SYSTEM_HEALTH_DIAGNOSTIC` in `CANONICAL_DDLS`. |
| | `captain-offline/.../orchestrator.py` | `P1P2_RERUN` branch: non-fatal `INSERT` into `p3_d22b_asset_rerun_status` (`rerun_trigger='LEVEL3_STALENESS'`). |
| | `captain-offline/.../b9_diagnostic.py` | `compute_d3()`: load `LATEST ON last_updated PARTITION BY asset` from D22b; per-asset `regime_ts` prefers D22b over locked_strategy fallbacks. |
| **Batch 4** | `shared/canonical_schemas.py` | Doc-only ratification comment block above `D26_HMM_OPPORTUNITY_STATE`. |
| **Tests** | `tests/test_schema_migrations.py` | Ten tests per plan (B1×3, B2×3, B3×3, B4×1); module `pytestmark = real_questdb`. |
| | `tests/conftest.py` | `mock_shared_db` skips mocking when `request.node.get_closest_marker("real_questdb")` is set. |

`captain_online` B1 `_load_regime_models()` was **not** changed (deferred to Phase 7), per the plan.

---

## Verification (implemented in repo)

- **Import smoke:** `from shared.canonical_schemas import CANONICAL_MIGRATIONS` succeeds; `len(CANONICAL_DDLS) == 41` after adding `P2_D07_REGIME_MODELS` and `D22B_ASSET_RERUN_STATUS`.
- **Grep (Batch 4):** No code file uses table alias `p3_d26_hmm_states` outside documentation; only the ratification comment in `canonical_schemas.py` references the shorthand.

---

## Runtime verification (requires QuestDB)

These steps were **not** executed in this environment (no `localhost:8812` listener; Docker Compose plugin unavailable in the runner). They should be run on a machine with QuestDB (e.g. `captain-start.sh` / compose as in `CLAUDE.md`).

1. **Init + idempotency (Batch 0 exit criteria):**
   ```bash
   PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
     python3 scripts/init_questdb.py
   # Run a second time; expect [SKIP] for M001 if column already exists.
   ```

2. **QuestDB console / SQL (Batches 1–3, 4):**
   - `SHOW COLUMNS FROM p2_d07_regime_models;` — expect 11 columns including `asset`, `model_type`, `pettersson_threshold`, `last_updated`, etc.
   - `SHOW COLUMNS FROM p3_d03_trade_outcome_log;` — expect `model_m` INT.
   - `SHOW COLUMNS FROM p3_d22b_asset_rerun_status;` — expect four columns.
   - `SHOW COLUMNS FROM p3_d26_hmm_opportunity_state;` — expect exactly nine columns (unchanged; ratification test asserts set equality).

3. **Pytest (all Batch exit criteria for automated tests):**
   ```bash
   export QUESTDB_HOST=localhost  # or questdb in Docker network
   PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
     python3 -B -m pytest tests/test_schema_migrations.py -v
   ```

`pytest` may emit a `PytestUnknownMarkWarning` for `real_questdb` until a `pytest.ini` registers that marker; functionality is unchanged.

---

## Deviations from the build plan

- **`scripts/init_questdb.py` header comment** still says “39 canonical tables” while the list now has 41 DDL entries. Only the file body was changed per Batch 0/1; consider updating the docstring in a follow-up.
- **Legacy-row test (Batch 2):** `trade_id` uses a time-based suffix so repeated test runs do not violate DEDUP on `trade_id` for the same day partition.
- **`test_b2_d03_model_m_column_exists`:** Assert uses `str(...).upper() == "INT"` for QuestDB type string casing.
- **pytest marker:** `conftest` skip for `real_questdb` was required so autouse `get_cursor` mocks do not break integration tests; not explicitly listed in the plan but necessary for the given `tests/conftest.py` layout.

---

## Files touched (checklist)

- `shared/canonical_schemas.py`
- `scripts/init_questdb.py`
- `captain-online/captain_online/blocks/b7_position_monitor.py`
- `scripts/paper_trader.py`
- `shared/trade_source.py`
- `captain-offline/captain_offline/blocks/orchestrator.py`
- `captain-offline/captain_offline/blocks/b9_diagnostic.py`
- `tests/test_schema_migrations.py` (new)
- `tests/conftest.py`
- `docs2/audits/2026-03-27_Build_Plans_1-12/build-plan-outputs/2026-04-27_phase1_schema_migrations_execution_report.md` (this file)

---

## Sign-off

Phase 1 implementation items from the build plan are **present in the repository**. Full automated verification (init twice + pytest) is **pending** a running QuestDB instance as described above.
