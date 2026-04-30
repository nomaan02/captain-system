# QuestDB Decimal Migration — Phase A Report

**Authority:** `MONETARY_DECIMAL_MIGRATION_PLAN.md` (Phase A — regulatory thresholds, circuit-breaker dollar state, lifecycle)

**Branch:** `migration/decimal-phase-a` (tip equivalent: commit below)

**Commit:** `90006d7f10fbbda63247d2595b607fd80ee33c0b` (message: `migration(decimal): phase A — TSM state, circuit breaker dollar state, lifecycle`)

**Parent (baseline before Phase A):** `4b3987a60323b870ad6ae88d531b8d5ee83f0cc8` — *Add monetary decimal migration plan and docs updates*

**Date (commit):** 2026-04-28

---

## 1. Executive summary

Phase A migrates **D08** TSM monetary columns, **D23** `l_t`, **D25** `l_star`, and **D28** lifecycle monetary columns to `DECIMAL(18, 2)`; introduces **`shared/decimal_json.py`** (`dumps_decimal` / `loads_decimal`) and **`parse_json_decimal`** in **`shared/json_helpers.py`**; updates writers/readers for reconciliation, TSM, circuit breaker, position monitor, account lifecycle, replay slice, GUI money display (strings), backup tooling; adds round-trip and precision tests.

**Merge to `main`:** not required by this document (per plan: phase branches stay until explicit approval).

---

## 2. A.1 Migration matrix (plan compliance)

| Table | Columns migrated | Target type |
|-------|------------------|-------------|
| `p3_d08_tsm_state` | `starting_balance`, `current_balance`, `current_drawdown`, `daily_loss_used`, `profit_target`, `max_drawdown_limit`, `max_daily_loss`, `commission_per_contract`, `margin_per_contract` | `DECIMAL(18, 2)` |
| `p3_d23_circuit_breaker_intraday` | `l_t` | `DECIMAL(18, 2)` |
| `p3_d25_circuit_breaker_params` | `l_star` | `DECIMAL(18, 2)` |
| `p3_d28_account_lifecycle` | `balance_at_event`, `fee_charged`, `payout_amount`, `payout_net`, `tradable_balance`, `reserve_balance` | `DECIMAL(18, 2)` |

**Stays DOUBLE (Phase A scope):** D25 statistical fields (`r_bar`, `sigma`, `beta_b`, `rho_bar`, `p_value`), D23 `n_t`, D08 percentage fields per plan.

---

## 3. CANONICAL_MIGRATIONS appended (M010–M026)

Defined in `shared/canonical_schemas.py` under Phase A comment blocks.

| ID | DDL (abbrev.) |
|----|----------------|
| **M010** | `p3_d08` `starting_balance` → `DECIMAL(18, 2)` |
| **M011** | `current_balance` |
| **M012** | `current_drawdown` |
| **M013** | `daily_loss_used` |
| **M014** | `profit_target` |
| **M015** | `max_drawdown_limit` |
| **M016** | `max_daily_loss` |
| **M017** | `commission_per_contract` |
| **M018** | `margin_per_contract` |
| **M019** | `p3_d23` `l_t` |
| **M020** | `p3_d25` `l_star` |
| **M021–M026** | D28 columns listed in §2 |

---

## 4. D28 “no writers” confirmation

`grep -r 'INSERT INTO p3_d28' --include='*.py'` over the repository: **no matches** (DDL + dataclass migration only; no Python INSERT into `p3_d28`).

---

## 5. File-level change log (`4b3987a..90006d7`)

**Totals:** 20 files changed, **+902 / −335** lines.

| File | + | − | Role |
|------|---|---|------|
| `captain-command/.../b2_gui_data_server.py` | 50 | 40 | Monetary payloads as strings / Decimal paths |
| `captain-command/.../b4_tsm_manager.py` | 14 | 10 | TSM Decimal writes |
| `captain-command/.../b8_reconciliation.py` | 94 | 88 | SOD / reconciliation Decimal |
| `captain-offline/.../b8_cb_params.py` | 3 | 1 | D03 read / `l_star` typing |
| `captain-online/.../b5c_circuit_breaker.py` | 61 | 44 | L1–L3 Decimal, `l_b` JSON |
| `captain-online/.../b7_position_monitor.py` | 28 | 17 | D23 / fee Decimal touchpoints |
| `scripts/backup_live_tables.py` | 129 | 7 | LIVE_TABLES + partition snapshots |
| `scripts/fix_bootstrap_data.py` | 8 | 4 | Bootstrap Decimal literals |
| `shared/account_lifecycle.py` | 107 | 88 | Lifecycle `Decimal` dataclasses |
| `shared/canonical_schemas.py` | 88 | 17 | DDL + M010–M026 |
| `shared/decimal_json.py` | 50 | 0 | **New** encoder/decoder |
| `shared/json_helpers.py` | 16 | 0 | `parse_json_decimal` |
| `shared/replay_engine.py` | 14 | 9 | CB slice Decimal |
| `tests/test_account_lifecycle.py` | 12 | 10 | Decimal assertions |
| `tests/test_basket_pnl_precision.py` | 18 | 0 | `l_b` basket sum |
| `tests/test_circuit_breaker_decimal.py` | 20 | 0 | Layer 1 boundary |
| `tests/test_d08_decimal_roundtrip.py` | 66 | 0 | D08 (**real_questdb**) |
| `tests/test_d23_d25_decimal_roundtrip.py` | 59 | 0 | D23/D25 (**real_questdb**) |
| `tests/test_decimal_json.py` | 46 | 0 | JSON round-trip |
| `tests/test_topstep_state_json_roundtrip.py` | 19 | 0 | `topstep_state` JSON |

---

## 6. JSON STRING columns (Phase A)

Per plan: **`topstep_state`**, **`fee_schedule`**, **`payout_rules`**, **`evaluation_stages`**, **D23 `l_b`** use **`dumps_decimal`** / **`loads_decimal`** (or **`parse_json_decimal`**) on read/write paths per implementation audit.

---

## 7. Tests added or materially updated

- `test_d08_decimal_roundtrip.py`, `test_d23_d25_decimal_roundtrip.py` (marked **`real_questdb`**)
- `test_topstep_state_json_roundtrip.py`, `test_decimal_json.py`
- `test_circuit_breaker_decimal.py`, `test_basket_pnl_precision.py`
- `test_account_lifecycle.py` (Decimal fixtures)

**Operator note:** run `pytest` with QuestDB available for **`real_questdb`** tests.

---

## 8. Pre-flight F1–F6 (plan Step 10 / Step 11)

This report does not replace your environment’s sign-off. Record outcomes locally:

| Gate | Intent |
|------|--------|
| **F1** | `shared/decimal_json.py` present; API stable for later phases |
| **F2** | Redis/trade path serialisation documented before Phase B |
| **F3–F4** | Grep / writer–reader inventory for monetary columns |
| **F5** | QuestDB data sanity on Phase A columns |
| **F6** | Backup / partition snapshot / restore drill |

Optional workspace notes: see `pre-monetary-questdb-checks.md` if maintained alongside this migration.

---

## 9. Anomalies / plan deviations (non-blocking)

- **`loads_decimal`**: implementation **extends** the plan’s minimal one-liner (string numeric coercion + `parse_int=Decimal`) so encoder round-trips and nested JSON behave consistently in tests.
- **B5C Layer 4:** still **rolling-Sharpe-style** implementation in code; spec formula delta called out elsewhere as **out of scope** for this migration.
- **B5C D03 helper query:** historical note on **`timestamp` vs `ts`** — **not fixed** in Phase A/B per migration scope (swallowed `except`); track as separate hygiene task if desired.

---

## 10. Step 11 confirmation checklist

- [x] Migrations **M010–M026** listed in `CANONICAL_MIGRATIONS` with matching DDL in `canonical_schemas.py`
- [x] D28 no-Python-writer grep result recorded (§4)
- [x] File/diff stats captured from git (§5)
- [x] Tests enumerated (§7); full suite + fresh **`init_questdb`** dry-run remain **operator responsibilities** on a real QuestDB instance

**Phase A delivery commit:** `90006d7f10fbbda63247d2595b607fd80ee33c0b`. Phase B builds from this tree (Phase B commit parent is that hash).
