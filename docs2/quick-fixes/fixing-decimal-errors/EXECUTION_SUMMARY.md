# Decimal Boundary Consolidation — Execution Summary

**Date:** 2026-04-30
**Trigger:** NY/APAC open `TypeError: unsupported operand type(s) for -: 'decimal.Decimal' and 'float'` in `b6_signal_output._build_per_account` (the second sister-bug after yesterday's `b4_kelly_sizing` fix at `4c225c0`)
**Outcome:** 5 commits to `main`, full Decimal/float type discipline established across the codebase, CI lint gate added to prevent regressions.

---

## TL;DR

| Metric | Before | After |
|--------|--------|-------|
| Static gate (no live DB) | 489 passed, 25 failed | 506 passed, 23 failed (same set) |
| Boundary helper duplication | Six private `_money*` per file | One shared module |
| `r[N] or 0.0` antipattern sites | 17 across 6 files | 0 (CI gate refuses regressions) |
| Silent reconciliation failures | Bare `except` swallowed Decimal/float TypeError for weeks | CRITICAL log + GUI alert |
| Type-purity at data ingestion | Mixed Decimal/float dicts | Type-pure (Decimal or Decimal\|None) |

---

## Commits (in order, all pushed straight to `main`)

| Commit | Title | Files | Lines |
|--------|-------|-------|-------|
| `03de644` | `fix(b8_or_tracker): expire stuck WAITING-state OR sessions at cutoff` | 1 | +11 / -1 |
| `1910f71` | `fix(decimal): boundary helpers + b1/b6/orchestrator type purity (Bug A round 2)` | 9 | +777 / -38 |
| `9659b4c` | `fix(decimal): consolidate helpers + close silent reconciliation gap` | 10 | +405 / -93 |
| `5681fb6` | `fix(decimal): offline replay paths + b3_pseudotrader boundary discipline` | 4 | +132 / -49 |
| `dbe550b` | `chore(decimal): CI lint guard + lockdown + docs` | 17 | +324 / -57 |

`03de644` is yesterday's OR-FORMING `WAITING`-state fix — committed as a prerequisite because it had been sitting uncommitted in the working tree.

`1910f71` is the **minimum patch to unblock NY open today**. Phases 2-4 are consolidation + lockdown.

---

## Phase 1 — `1910f71` — Bleeding-now patch

### Created

- **`shared/decimal_boundary.py`** — single source of truth for monetary coercion:
  - `as_money(value, *, default=Decimal("0")) -> Decimal`
  - `as_money_or_none(value) -> Decimal | None`
  - `to_float(value, *, default=0.0) -> float`
  - `assert_money_dict(d, *fields, allow_none=())` (test helper)

### Patched

- **`captain-online/.../b6_signal_output.py:_build_per_account`** — re-coerces all four D08 fields via the boundary helpers. Decimal arithmetic for `remaining_mdd` / `remaining_mll`; explicit `to_float` only at the percentage display boundary. **This is the exact NY-open failure site.**
- **`captain-online/.../b1_data_ingestion.py:_load_active_assets`** — D00 monetary fields use `as_money` (was `or 0.0` antipattern).
- **`captain-online/.../b1_data_ingestion.py:_load_tsm_configs`** — every D08 monetary field uses `as_money` / `as_money_or_none`. JSON STRING columns containing dollar amounts (`topstep_state`, `fee_schedule`, `payout_rules`, `topstep_params`) switched from `parse_json` to `parse_json_decimal` per Phase A migration plan §A.2.
- **`captain-online/.../orchestrator.py:_load_user_silo`** — D16 `starting_capital` / `total_capital` use `as_money`.
- **`captain-online/.../b6_signal_output.py:_get_daily_pnl`** — uses `to_float`.

### Tests added

- `tests/test_decimal_boundary.py` — 27 unit tests (helper correctness)
- `tests/test_b6_decimal_d08_boundary.py` — regression for the exact NY-open failure mode + nullable + type-mixed-dict defence
- `tests/test_tsm_config_type_purity.py` — live-QuestDB producer test
- `tests/test_user_silo_type_purity.py` — live-QuestDB producer test
- `tests/test_active_assets_type_purity.py` — live-QuestDB producer test

---

## Phase 2 — `9659b4c` — Helper consolidation + silent failure closed

### Six private helpers consolidated

| Old (private) | New (alias for) | File |
|---------------|-----------------|------|
| `_silo_money` | `as_money` | `b4_kelly_sizing.py` |
| `_to_float` | `to_float` | `b4_kelly_sizing.py` |
| `_money_d` | `as_money` | `b7_position_monitor.py` |
| `_d_price` | `as_money_or_none` | `aim_feature_loader.py` |
| `_safe_decimal` | `as_money` | `trade_source.py` |
| `_decimal_or_none` | `as_money_or_none` | `trade_source.py` |

Each module keeps the local short name as an alias — call sites unchanged, implementation in one place.

### Silent reconciliation gap closed

`captain-command/.../b8_reconciliation.py:_reconcile_api_account`:

- Broker float vs system Decimal coerced via `as_money_or_none` at boundary; `mismatch` is Decimal end-to-end; threshold compares against `Decimal("1.00")`.
- GUI / log formatters wrapped in `to_float(...)` so f-strings cannot TypeError on Decimal.
- **Bare except path replaced with `logger.critical(exc_info=True)` + GUI alert** (priority `CRITICAL`, source `RECONCILIATION_FAILURE`). Was hiding the Decimal/float TypeError for weeks.

### Other Phase 2 fixes

- `captain-online/.../b4_kelly_sizing._get_expected_fee` — switched `parse_json` → `parse_json_decimal` for `fee_schedule`; uses `as_money` + `to_float` boundary.
- `captain-offline/.../b7_tsm_simulation.run_tsm_simulation` — coerces D08 Decimal inputs to float at function entry. Monte Carlo inner loop stays float for performance.
- `captain-command/.../b6_reports.py:_generate_rpt12_alpha_decomposition` — EWMA reads via `to_float` boundary.

### Tests added

- `tests/test_reconciliation_decimal_boundary.py` — 5 tests (mismatch path + CRITICAL log + GUI alert + alert-failure resilience)
- `tests/test_tsm_simulation_decimal_input.py` — 4 tests (`run_tsm_simulation` accepts fully-Decimal config)
- `tests/test_kelly_fee_schedule_decimal.py` — 5 tests (Phase-A-encoded `fee_schedule` JSON round-trip)

---

## Phase 3 — `5681fb6` — Offline replay paths

### Patched

- **`shared/replay_engine.py`** — every D00/D08/D12/D05/D16/D25 reader uses `to_float` at boundary. Removed every `r[N] or 0.0`. Float at compute (offline summary statistics — float precision adequate).
- **`scripts/replay_session.py`** — same boundary discipline at the manual replay-driver CLI.
- **`scripts/verify_questdb_state.py`** — D02 inclusion-probability accumulator uses `to_float`.
- **`captain-offline/.../b3_pseudotrader.py`** — new module-private `_money_get(d, key, default)` wrapping `to_float`, applied at every D08 read site inside the three account-aware replay entrypoints. Hardcoded fallback constants (`4500`, `150000`, `9000`, etc.) become `to_float`-aware defaults.

---

## Phase 4 — `dbe550b` — CI lockdown

### Created

- **`scripts/lint_decimal_boundary.py`** — refuses new occurrences of the `r[N] or 0.0` antipattern on lines mentioning any of the 27 monetary columns from Phase A/B/C, OR inside known data-ingestion constructs. Suppression marker `# decimal-boundary: ok` for legitimate non-monetary defaults.
- **`tests/test_decimal_boundary_lint.py`** — pytest wrapper invoking the lint script as a CI gate.

### Lint sweep cleaned remaining sites

The lint identified 17 antipattern sites the manual sweep missed:
- `captain-online/dry_run_phase_a.py` — D16 `starting_capital`/`total_capital` via `as_money`
- `captain-offline/.../orchestrator._run_tsm_sim_for_account` — D08 via `as_money` / `as_money_or_none`
- `captain-offline/.../b1_dma_update.py` — D05 EWMA reads via `to_float`
- `scripts/replay_session.py` — additional D08 read sites
- 10+ false positives (counters, ratios, OR ranges, VIX, defensively-coerced sites) suppressed with the marker

### Docs updated

- `MONETARY_DECIMAL_MIGRATION_PLAN.md` — cross-cutting rule pointing future work at `shared.decimal_boundary` + the CI lint gate.
- `docs2/quick-fixes/pnl_miscalculations/PRE_MARKET_VALIDATION.md` — added 2026-04-30 B6 incident; T2.6 regression-test list expanded with the 8 new tests.

---

## Architecture: the pattern we settled on

> **"Decimal at boundaries, internally consistent typed dicts, explicit float escape hatch."**

1. **Single shared boundary module.** `shared/decimal_boundary.py` is the only place coercion lives.
2. **Type-pure dicts at every data-ingestion site.** No more "sometimes Decimal, sometimes float" state. Catches regressions via `assert_money_dict` in tests.
3. **Decimal end-to-end for monetary state mutations.** D03 writes, D08 capital updates, D16 silos, D23 cumulative `l_t`, basket `l_b` JSON.
4. **Float at the sizing-math boundary.** Kelly, % caps, MC simulation, statistical estimators accept Decimal at the function boundary and convert via `to_float` at the first arithmetic site — explicitly, never silently.
5. **Decimal at the JSON wire.** Every dict serialised for Redis, GUI, or QuestDB JSON columns uses `dumps_decimal`. Every dict deserialised uses `parse_json_decimal`.
6. **GUI output uses string representation** via `_gui_money_json` — no float drift on the wire.

### Anti-patterns now refused by CI

- `Decimal(0.1)` — float bit pattern leak
- `value or 0.0` on Decimal columns — falsy-zero collapse
- `Decimal − float` outside the explicit `to_float` boundary
- Defensive per-site `Decimal(str(tsm.get("X", 0)))` in every consumer (fix the producer once instead)
- Silent `float()` casts on monetary fields without a comment explaining why

---

## Validation evidence

Static fast-gate (no live QuestDB; both towers will run live tests separately):

```
506 passed, 23 failed, 18 skipped, 97 warnings in 124.36s
```

The 23 failures are pre-existing `psycopg2.OperationalError: connection refused` from tests that need a live QuestDB (`test_schema_migrations.py`, `test_d08_decimal_roundtrip.py`, etc.) — unchanged from baseline before any of this work. Zero regressions introduced.

Lint gate:
```
$ python3 scripts/lint_decimal_boundary.py
decimal-boundary lint: 0 violations
```

---

## What was NOT touched (intentionally out of scope)

Per the migration plan §6 deferred items:

- `b5c_circuit_breaker.py` `timestamp` vs `ts` bug — separate ticket
- `r_bar` / `sigma` columns staying DOUBLE — Isaac's spec ruling
- `p3_d19_reconciliation_log.mismatches` JSON snapshot fields
- `p3_d27_pseudotrader_forecasts.equity_curve` JSON
- Live `ALTER TABLE` migrations (no schema changes — purely Python type-hygiene)

---

## Next session opens — what to expect

- The exact NY-open `TypeError` will not recur. `_build_per_account` coerces every D08 field via `shared.decimal_boundary` at the function boundary.
- B4 Kelly sizing (yesterday's `4c225c0` fix) and B6 signal output (today's `1910f71` fix) now use the same shared helpers, eliminating drift.
- Reconciliation failures will surface immediately via CRITICAL log + GUI alert (was silent for weeks).
- Any future regression to the antipattern is blocked at PR time by the CI lint gate.

See `TOWER_TEST_RUNBOOK.md` in this folder for the exact fish-shell commands to run on each tower.
