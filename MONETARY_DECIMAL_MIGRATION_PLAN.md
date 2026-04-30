# QuestDB Monetary Type Migration — Phase 2: Phased Implementation



# QuestDB Monetary Type Migration — Implementation Plan

**Status:** Approved for execution

**Authority:** Supersedes ad-hoc decisions; agent must not deviate without stopping and reporting

**Companion docs:** MONETARY_DECIMAL_MIGRATION_[AUDIT.md](http://AUDIT.md) (Phase 1 output)

**Date:** 2026-04-28

**Spec author confirmations incorporated:** l_t / l_star are dollar amounts (Isaac, 2026-04-28)



## How the agent should use this document

1. Read in full before starting any work.

2. Treat the migration matrices, JSON-string column lists, and cross-cutting rules as authoritative — do not infer scope from elsewhere.

3. Execute pre-flight F1–F6 once, then Phase A, then stop at the approval gate.

4. If anything in the codebase contradicts this plan, stop and report. Do not silently adjust.

5. The phase report at each gate is the deliverable that unlocks the next phase.



## Context

You previously produced `MONETARY_DECIMAL_MIGRATION_AUDIT.md` and I have approved the plan. Implement it now in **strict phase order**, with explicit approval gates between phases. The phasing exists to reduce production risk — do not skip ahead, do not batch phases together.

Several scope refinements apply on top of the original audit. Read all of them before starting:

1. **Phase A scope additions confirmed by spec author (Isaac):** `p3_d23_circuit_breaker_intraday.l_t` and `p3_d25_circuit_breaker_params.l_star` are dollar amounts. Migrate both to `DECIMAL(18, 2)` in Phase A. The Phase 1 audit only inventoried D08 and D28 in detail — run a fresh `grep -rn "l_t\|l_star" --include="*.py"` across the captain-system tree and incorporate every writer and reader site for these two columns into Phase A's work before making any code changes.
2. **D28 scope clarification:** No Python writer code currently exists for `p3_d28_account_lifecycle`. This was confirmed by the audit. D28's Phase A work therefore consists of: (a) updating the `D28_ACCOUNT_LIFECYCLE` DDL string in `shared/canonical_schemas.py`, (b) appending `ALTER COLUMN` migrations to `CANONICAL_MIGRATIONS`, and (c) updating the `LifecycleEvent` and related Topstep account dataclasses in `shared/account_lifecycle.py` from `float` to `Decimal` for monetary fields. Before starting D28 work, confirm "no writers" by running `grep -rn "INSERT INTO p3_d28" --include="*.py"` and reporting the result. If anything is found, stop and report.
3. **r_bar and sigma stay DOUBLE.** `p3_d25_circuit_breaker_params.r_bar` and `p3_d25_circuit_breaker_params.sigma` are dollar-denominated statistical estimates from a regression, where sampling error vastly exceeds float precision. They are NOT migrated to DECIMAL. However, they enter mixed-type arithmetic with the Decimal `l_t` and `l_star` columns (formulas like `mu_b = r_bar + beta_b * L_b` and `L_star = -r_bar / beta_b`). At every use site, convert these floats to Decimal at the boundary: `Decimal(str(r_bar)) + Decimal(str(beta_b)) * L_b`. Do not change the column types; only the use-site arithmetic.
4. **JSON-string monetary values must use a Decimal-aware encoder/decoder.** This is the most cross-cutting addition. The migration's value is partially defeated unless dollar values stored inside JSON STRING columns round-trip through a Decimal-aware serialiser. The columns affected per phase are listed in each phase's section below.
5. **Constants in code (not schema).** The Topstep optimisation spec uses literal numeric constants like `4500`, `150000`, `5000`, `160714`, `1000`, `1500` in formulas alongside what will become Decimal operands. Every Python use site of these constants in monetary arithmetic must be wrapped as `Decimal("4500")` (string-constructed to avoid float artefacts). Audit and fix these alongside their owning tables.
6. **Pre-existing bugs are out of scope.** The audit flagged a `timestamp` vs `ts` column mismatch in `b5c_circuit_breaker.py` against D03, with the failure swallowed by a bare `except`. Do NOT fix this in the migration. File it as a separate bug ticket in the final summary document. Bundling unrelated fixes destroys the rollback path.
7. `**p3_d19_reconciliation_log.mismatches` JSON snapshot fields are deferred.** Out of scope for this migration. List in final summary as future work.

Before you start: confirm a clean git working tree on the captain-system main branch. If there is uncommitted work, stop and tell me. Per project discipline, every phase begins with a fresh feature branch and ends with a commit, but no merge to main without my explicit approval.

## Pre-flight: shared infrastructure (do this once before Phase A)

Before any phase begins, build the foundation that all three phases will use.

### F1. Locate or create the Decimal-aware JSON serialiser

Search `shared/`, `captain-command/`, `captain-online/`, and `captain-offline/` for any existing `JSONEncoder` subclass or Decimal-aware serialisation utility. Run:

```bash
grep -rn "JSONEncoder\|parse_float\|DecimalJSON" --include="*.py" .
```

Report what you find. Then:

- **If a suitable encoder already exists**, document its location and use it across all phases. Do not create a duplicate.
- **If none exists**, create `shared/decimal_json.py` with the following utilities (use this exact API — phases below depend on it):

```python
"""Decimal-aware JSON serialisation for monetary values stored in QuestDB STRING columns.

Used wherever a JSON-serialised STRING column contains dollar amounts that must
preserve precision through the round-trip. See MONETARY_DECIMAL_MIGRATION_COMPLETE.md
for the full list of affected columns.
"""
from __future__ import annotations
import json
from decimal import Decimal
from typing import Any


class DecimalJSONEncoder(json.JSONEncoder):
    """Serialises Decimal as a JSON string to preserve precision."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def dumps_decimal(obj: Any) -> str:
    """Serialise an object to JSON, encoding Decimal as string."""
    return json.dumps(obj, cls=DecimalJSONEncoder)


def loads_decimal(s: str) -> Any:
    """Parse JSON, returning all numeric values as Decimal (not float)."""
    return json.loads(s, parse_float=Decimal)
```

Add a unit test in `tests/test_decimal_json.py` covering: round-trip of nested dicts with Decimal values, mixed Decimal/int/string content, and the case where the input JSON contains floats (must come back as Decimal, not float).

### F2. Confirm Redis serialisation path

The audit noted that `b7_position_monitor.py:_publish_trade_outcome` exists but the serialisation path was not documented. Before Phase B, identify how trade outcomes cross the Redis boundary. Run:

```bash
grep -rn "publish\|json.dumps\|msgpack\|pickle" captain-online/captain_online/blocks/b7_position_monitor.py
grep -rn "redis" --include="*.py" shared/ captain-online/ captain-command/
```

Report which serialisation format is used. If it's `json.dumps`, the same encoder applies. If it's `msgpack` or `pickle`, document what the Decimal handling will look like (msgpack needs a custom hook; pickle handles Decimal natively). Phase B's Redis work uses whatever you find here.

### F3. Build a comprehensive hardcoded-literal grep

The Phase 1 audit only caught `fix_bootstrap_data.py:177-179`. Before each phase, run a sweep for hardcoded numeric literals in SQL strings touching that phase's tables:

```bash
# For each table in scope, search for SQL strings containing both the table name and a numeric literal
grep -rnE "p3_d[0-9]{2}.*VALUES.*[0-9]+\.[0-9]" --include="*.py" .
grep -rnE "(SET|WHERE).*=.*[0-9]+\.[0-9]" --include="*.py" .
```

Report every match. Each numeric literal in SQL touching a migrated DECIMAL column needs the `m` suffix or conversion to a parameterised `%s` placeholder bound to a `Decimal` value.

### F4. Resolve audit line-range gaps

The Phase 1 audit hedged with wide line ranges in several places (e.g., `b2_gui_data_server.py — Multiple SELECTs · lines ~185–1554`, `orchestrator.py — Multiple pnl / contracts SELECTs (grep hits 736:1200... region)`, `seed_ohlcv_from_qc.py — Grep hits lines 58, 101 — inspect for INSERT shape`). At the start of each phase, re-run `grep -n` on the phase's tables and produce a precise file:line list before making any code changes. The wide ranges in the audit document are not acceptable as final citations.

### F5. Run the pre-migration data sanity checks

For every column being migrated to DECIMAL across all three phases, run these checks against your QuestDB instance and report results before Phase A starts:

```sql
-- Overflow check (per column)
SELECT MAX(ABS(<column>)), MIN(<column>), MAX(<column>) FROM <table>;

-- NaN check (per column)
SELECT count(*) FROM <table> WHERE <column> != <column>;

-- Infinity check (per column)
SELECT count(*) FROM <table> WHERE <column> = 'Infinity' OR <column> = '-Infinity';
```

If any column has values exceeding the target DECIMAL range, or contains NaN/Infinity, stop and report. Do not proceed until those rows are corrected or nulled.

### F6. Snapshot backups

Before Phase A starts, take a snapshot of every partition for every migrating table. Use whatever backup mechanism is configured (`backup_live_tables.py` if it exists, or copy the relevant directories under `/var/lib/questdb/db/`). Per-table data volume is small. Confirm backups are restorable before proceeding.

---

## Phase order (do not deviate)

- **Phase A** — D08 TSM state + D23.l_t + D25.l_star + D28 (regulatory thresholds, circuit breaker dollar state, lifecycle schema-and-dataclasses)
- **Phase B** — D03 trade outcome log (prices + P&L) + Redis serialisation path
- **Phase C** — D16 user capital silos + D00 asset universe constants + D30 daily OHLCV

After each phase, stop, run validation, report results, and **wait for my explicit approval** before starting the next phase.

---

## Phase A — Regulatory thresholds and circuit breaker dollar state

### A.1 Migration matrix for Phase A


| Table                             | Columns                                                                                                                                                                                 | Target type      |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| `p3_d08_tsm_state`                | `starting_balance`, `current_balance`, `current_drawdown`, `daily_loss_used`, `profit_target`, `max_drawdown_limit`, `max_daily_loss`, `commission_per_contract`, `margin_per_contract` | `DECIMAL(18, 2)` |
| `p3_d23_circuit_breaker_intraday` | `l_t`                                                                                                                                                                                   | `DECIMAL(18, 2)` |
| `p3_d25_circuit_breaker_params`   | `l_star`                                                                                                                                                                                | `DECIMAL(18, 2)` |
| `p3_d28_account_lifecycle`        | `balance_at_event`, `fee_charged`, `payout_amount`, `payout_net`, `tradable_balance`, `reserve_balance`                                                                                 | `DECIMAL(18, 2)` |


Stays DOUBLE in Phase A scope: D25.r_bar, D25.sigma, D25.beta_b, D25.rho_bar, D25.p_value, D23.n_t, D08 percentages.

### A.2 JSON STRING columns requiring Decimal-aware encoding in Phase A

These columns hold dollar amounts inside JSON STRING fields. Migrate every read and write site to use `dumps_decimal` / `loads_decimal` from F1:

- `p3_d08_tsm_state.topstep_state` — contains `daily_exposure`, `hard_halt_threshold`, `max_payout`, `fee_per_trade`, `risk_per_trade_eff`, `post_payout_mdd_pct`
- `p3_d08_tsm_state.fee_schedule` — contains `fees_by_instrument[asset].round_turn` per the Topstep spec
- `p3_d08_tsm_state.payout_rules` — contains payout dollar thresholds
- `p3_d08_tsm_state.evaluation_stages` — contains stage threshold dollar amounts
- `p3_d23_circuit_breaker_intraday.l_b` — per-basket cumulative dollar P&L (running sum, the highest-risk JSON column)

### A.3 Phase A workflow

#### Step 1 — Branch and baseline

Create `migration/decimal-phase-a`. Report the branch name and current commit hash.

#### Step 2 — Run pre-flight checks F1–F6

Execute every pre-flight task above. Do not proceed until F1 (encoder) is in place and F5 (data sanity) passes for Phase A's columns.

#### Step 3 — Update canonical schema

Open `shared/canonical_schemas.py`. For each column in A.1:

- Update the corresponding `CREATE TABLE` string (D08_TSM_STATE, D23_CIRCUIT_BREAKER_INTRADAY, D25_CIRCUIT_BREAKER_PARAMS, D28_ACCOUNT_LIFECYCLE) to use the new DECIMAL types. This affects fresh installs.
- Append `ALTER COLUMN` entries to `CANONICAL_MIGRATIONS` in the form:

```python
  ("M{NNN}_d08_starting_balance_to_decimal",
   "ALTER TABLE p3_d08_tsm_state ALTER COLUMN starting_balance TYPE DECIMAL(18, 2)"),
```

- Use the next available `M{NNN}` after the current highest (audit identified `M009`, so start at `M010`).
- Group migrations contiguously per table with a comment header indicating Phase A.

#### Step 4 — Update writer sites

For every Phase A writer site (use the precise file:line list produced in F4):

- Convert `float` inputs to `Decimal` using `Decimal(str(value))` at the function boundary.
- Use Decimal arithmetic for inline computations. Example: `current_drawdown = peak_balance - current_balance` where both operands are now Decimal.
- For psycopg2 `executemany`/`execute` calls, pass `Decimal` objects directly via `%s` placeholders. psycopg2 handles the type natively over PG-wire.
- Handle the boundary between Decimal columns and DOUBLE columns (e.g., when reading `r_bar` from D25 and computing `mu_b = r_bar + beta_b * L_b`): `Decimal(str(r_bar)) + Decimal(str(beta_b)) * L_b`.

Specific Phase A writer sites from the audit (verify and expand via F4):

- `captain-command/captain_command/blocks/b8_reconciliation.py` (lines ~563–591 and ~655–682)
- `captain-command/captain_command/blocks/b4_tsm_manager.py` (lines ~392–436)
- `captain-offline/captain_offline/blocks/b7_tsm_simulation.py` (lines ~132–158)
- `scripts/fix_bootstrap_data.py` (lines ~167–188 — note hardcoded `0.0` literals on 177–179 that need the `m` suffix or parameterisation)
- D23 / D25 writers identified by the F1 grep
- No D28 writer code exists — verify and document.

#### Step 5 — Update computation sites

For every formula in the Topstep optimisation spec that produces a Phase A monetary value, switch to Decimal arithmetic. Specifically:

- `f(A) = 4500 / A` → result is a percentage (DOUBLE) but the input A is Decimal. Convert: `float(Decimal("4500") / current_balance)` if storing as DOUBLE, or keep as Decimal if used downstream in monetary computations.
- `E(A, e) = e * A` → result is dollars (Decimal). `Decimal(str(e)) * current_balance`.
- `L_halt = c * e * A` → result is dollars (Decimal). `Decimal(str(c)) * Decimal(str(e)) * current_balance`.
- `W(A) = min(5000, 0.5 * (A - 150000))` → result is dollars (Decimal). All literals → `Decimal("5000")`, `Decimal("0.5")`, `Decimal("150000")`.
- `g(A) = 4500 / (A - W(A))` → percentage (DOUBLE). Compute denominator in Decimal, convert at the boundary.
- `rho_j = contracts * (sl_distance * point_value + phi)` → dollars (Decimal). All operands Decimal.
- Layer 1 hard halt check: `abs(L_t) + rho_j >= L_halt` — all three operands now Decimal.
- Layer 3 expectancy check: `mu_b = Decimal(str(r_bar)) + Decimal(str(beta_b)) * L_b > 0`.
- Layer 4 Sharpe: `S = mu_b / (Decimal(str(sigma)) * Decimal(str(math.sqrt(1 + 2 * n_t * rho_bar)))) > Decimal(str(lam))`. The sqrt result must be cast through string conversion to avoid float drift.

Wrap every constant from the spec (4500, 150000, 5000, 160714, 1000, 1500, and any others encountered) as `Decimal("...")` in computation sites.

#### Step 6 — Update reader sites and downstream consumers

For every Phase A reader site:

- Update Pydantic / dataclass type annotations from `float` to `Decimal` for D08 monetary fields. Specifically `LifecycleEvent` in `shared/account_lifecycle.py:175-181` and the Topstep account dataclasses in `shared/account_lifecycle.py:70-181` per the audit.
- For every consumer that does arithmetic between a `SELECT` result and a Python `float`, convert the float to Decimal at the boundary.
- Update GUI assembly code in `captain-command/captain_command/blocks/b2_gui_data_server.py` to either keep values as Decimal through to JSON output (using `dumps_decimal`) or convert to string at the JSON boundary. Do NOT downcast to float.

#### Step 7 — Update JSON-string column read/write sites

For every read of `p3_d08_tsm_state.topstep_state`, `fee_schedule`, `payout_rules`, `evaluation_stages`, and `p3_d23_circuit_breaker_intraday.l_b`:

- Replace `json.loads(value)` with `loads_decimal(value)`.
- Replace `json.dumps(value)` with `dumps_decimal(value)`.

For the running-sum case in `l_b` (spec line 670: `P3-D23[ac].L_b[m] += trade_pnl`):

- Read with `loads_decimal` so existing basket values come back as Decimal.
- Add Decimal `trade_pnl` to the existing Decimal value.
- Write with `dumps_decimal` so the precision is preserved.

#### Step 8 — Update D28 dataclasses and tests

- In `shared/account_lifecycle.py`, change every monetary field type from `float` to `Decimal` for `LifecycleEvent`, the Topstep account dataclasses, and any helper types touching balance/fee/payout fields.
- Update every test fixture that constructs these dataclasses with float literals (e.g., `balance_at_event=1000.0` becomes `balance_at_event=Decimal("1000.00")`).
- Confirm via grep that no `INSERT INTO p3_d28` statements exist. Document this confirmation in the phase report.

#### Step 9 — Update tests

- Update existing tests that assert exact float equality on Phase A values to use Decimal equality. Fixtures in `tests/fixtures/user_fixtures.py`, `tests/fixtures/synthetic_data.py`, `tests/test_b5c_circuit.py`, `tests/test_account_lifecycle.py`, `tests/test_schema_migrations.py` are confirmed in scope.
- **New round-trip test** in `tests/test_d08_decimal_roundtrip.py`: insert `Decimal("12345.67")` into every migrated D08 column, read back, assert exact equality.
- **New round-trip test** in `tests/test_d23_d25_decimal_roundtrip.py`: same pattern for `l_t` and `l_star`.
- **New JSON round-trip test** in `tests/test_topstep_state_json_roundtrip.py`: write a `topstep_state` dict containing Decimal values via `dumps_decimal`, read back via `loads_decimal`, assert all dollar fields are still Decimal with exact precision.
- **New circuit-breaker boundary test** in `tests/test_circuit_breaker_decimal.py`: simulate a sequence of trades where float drift would have flipped the `abs(L_t) + rho_j >= L_halt` comparison at the boundary. Assert the Decimal-typed comparison is correct.
- **New basket P&L precision test** in `tests/test_basket_pnl_precision.py`: simulate 50 trades into a basket via the JSON `l_b` round-trip path. Assert the final basket sum equals the exact Decimal sum, not a drifted float sum.

#### Step 10 — Validation gate (execute every step, do not skip)

a. **Static checks** — `python -m py_compile` on every modified file. Run `ruff check` and `mypy` if configured. Resolve every error.

b. **Schema migration dry-run** — start a fresh QuestDB container (or test instance). Run `scripts/init_questdb.py`. Confirm every Phase A `ALTER TABLE` applies cleanly. Run `SHOW COLUMNS FROM <table>` for D08, D23, D25, D28 and confirm DECIMAL types with correct precision/scale.

c. **Unit tests** — run the full unit suite. All previously passing tests must still pass. New round-trip and precision tests must pass.

d. **Integration tests** — if Docker-Compose-based integration tests exist, run them. Full Captain stack must come up clean against the migrated schema.

e. **Round-trip sanity check** — manually `INSERT` then `SELECT` one row into each migrated table. Confirm exact equality with no `0.30000000000000004`-style artefacts.

f. **JSON round-trip sanity check** — write a `topstep_state` JSON containing `daily_exposure: Decimal("1500.00")` and `hard_halt_threshold: Decimal("750.00")`. Read it back. Confirm both come back as Decimal with exact value.

g. **Circuit breaker boundary check** — synthesise a sequence where `L_t = -495.00`, `rho_j = 495.00`, `L_halt = 750.00`. Confirm Layer 1 blocks the trade (`|L_t| + rho_j = 990 >= 750`).

h. **Reconciliation smoke test** — simulate a TSM balance update with a value that previously caused float drift in `p3_d19_reconciliation_log` (e.g., the kind of value that produces `49999.989999999998` when computed as a float). Confirm no drift is reported.

#### Step 11 — Phase A report and approval gate

Produce a written phase report containing:

- Files changed with diff stats per file
- Migrations added (IDs and DDL)
- Test results — new and existing
- F1–F6 pre-flight outcomes (encoder location, Redis serialisation format, hardcoded literal grep results, line-range resolutions, data sanity check results, backup confirmation)
- D28 "no writers" confirmation
- Any anomalies, surprises, or audit-document discrepancies
- Confirmation that all eleven steps completed without errors

**Stop and wait for my approval.** Do not start Phase B, do not merge to main.

#### Step 12 — Commit (after approval)

```
migration(decimal): phase A — TSM state, circuit breaker dollar state, lifecycle dataclasses

- Schema: ALTER COLUMN to DECIMAL(18,2) for {N} columns across D08, D23, D25, D28
- Writers: updated {K} INSERT sites to use Decimal/PG-wire encoding
- Readers: updated {J} consumers + dataclass annotations float→Decimal
- JSON: dumps_decimal/loads_decimal applied to topstep_state, fee_schedule,
        payout_rules, evaluation_stages, l_b
- Constants: 4500/150000/5000 wrapped as Decimal at all use sites
- Tests: added round-trip, JSON round-trip, circuit breaker boundary,
        basket precision tests
- Migrations: M010 through M{NNN+X} appended to CANONICAL_MIGRATIONS
```

Leave the branch in place. Do NOT merge to main.

---

## Phase B — Trade outcome log

### B.1 Migration matrix for Phase B


| Table                      | Columns                                           | Target type      |
| -------------------------- | ------------------------------------------------- | ---------------- |
| `p3_d03_trade_outcome_log` | `entry_price`, `signal_entry_price`, `exit_price` | `DECIMAL(14, 4)` |
| `p3_d03_trade_outcome_log` | `gross_pnl`, `commission`, `pnl`, `slippage`      | `DECIMAL(18, 4)` |


Stays DOUBLE: `aim_modifier_at_entry` and other statistical/probability fields.

### B.2 JSON STRING columns requiring Decimal-aware encoding in Phase B

- `p3_d03_trade_outcome_log.aim_breakdown_at_entry` — verify whether this contains dollar-denominated AIM contributions. If yes, route through `dumps_decimal`/`loads_decimal`. If purely statistical, leave as-is and document the determination.
- `p3_d06_injection_history.pseudo_results` — contains pnl_delta, baseline_total_pnl, cb_total_pnl per the Topstep spec. Route through Decimal-aware encoder.
- Redis serialisation in `_publish_trade_outcome` — apply whatever encoder F2 identified.

### B.3 Phase B workflow

Follow the same workflow structure as Phase A (steps 1–12) with the following Phase B specifics:

#### Phase B Step 4 — Writer sites (specific to D03)

- `captain-online/captain_online/blocks/b7_position_monitor.py:311-324` (main INSERT)
- `captain-online/captain_online/blocks/b7_position_monitor.py:99-204` (computation: `current_pnl`, `gross_pnl`, `net_pnl`, `slippage`)
- `shared/trade_source.py:296-318` (synthetic seed)
- `scripts/paper_trader.py:398-437` (open and close inserts)
- `scripts/backfill_d03_signal_ids.py:44-54`
- `tests/test_schema_migrations.py:76-81, 97-101`
- `tests/test_schema_d03_signal_id.py` (verify exact lines via F4)

#### Phase B Step 5 — Computation sites (D03-specific)

- P&L formula: `pnl = (exit_price - entry_price) * direction * contracts * point_value - commission`
  - All price operands now Decimal
  - `direction` is INT (no change)
  - `contracts` is INT (convert to Decimal at multiplication: `Decimal(contracts)`)
  - `point_value` is Decimal (from D00 — Phase C migrates D00 but D03 reads D00 today; until Phase C, wrap with `Decimal(str(point_value))`)
  - `commission` now Decimal
- Slippage formula: `slippage = (signal_entry_price - actual_entry_price) * contracts * point_value` — same conversion pattern.

#### Phase B Step 6 — Reader sites (specific to D03)

- `captain-online/captain_online/blocks/b6_signal_output.py:434-446` — `SELECT sum(pnl)` aggregation. The sum is now exact across the trade history, which is one of the migration's primary wins.
- `captain-online/captain_online/blocks/b5c_circuit_breaker.py:575-586` — `SELECT pnl` filtered by timestamp. NOTE: the audit flagged a potential pre-existing bug where this query uses `WHERE timestamp` against a column named `ts`, with the failure swallowed by a bare `except`. Do NOT fix this bug as part of the migration. Document it in the final summary as out-of-scope follow-up.
- `captain-command/captain_command/blocks/b2_gui_data_server.py:354-417` (open positions and closed trades GUI assembly)
- `shared/trade_source.py:384-418` and `_row_to_outcome` at `:422-439` — currently casts DB values via `float(...)`. Replace with `Decimal(str(...))` for monetary fields. Update `RealisedOutcome` dataclass at `:338-358` from `float` to `Decimal` for monetary fields.
- `shared/aim16_observation_panel.py:89-106` (sum(pnl), entry/exit prices in CASE)
- `captain-offline/captain_offline/blocks/orchestrator.py` (resolve precise lines via F4)
- `captain-offline/captain_offline/blocks/b9_diagnostic.py:426`, `b8_cb_params.py:44`, `b3_pseudotrader.py:708`, `b1_aim_lifecycle.py:138`
- `shared/replay_engine.py:258`

#### Phase B Step 7 — Redis serialisation

Apply F2's findings to `b7_position_monitor.py:_publish_trade_outcome:399-429`. Monetary fields in the payload must round-trip through whatever Decimal-aware mechanism F2 identified.

#### Phase B Step 9 — Tests (D03-specific additions)

- **Sum-precision test** in `tests/test_d03_pnl_sum_precision.py`: insert N rows where the float-sum diverges from the exact sum (e.g., 1000 trades of `pnl = Decimal("0.10")` and 500 trades of `pnl = Decimal("0.20")`). Verify `SELECT SUM(pnl)` returns exactly `Decimal("200.00")`, not a float-drifted value.
- **Reconciliation precision test** in `tests/test_d03_reconciliation_precision.py`: simulate a broker statement with exact dollar P&L. Compute the same value via the migrated D03 path. Assert exact equality.
- **Redis round-trip test** in `tests/test_d03_redis_roundtrip.py` (using whatever serialisation F2 identified): publish a trade outcome with Decimal monetary fields, consume on the other side, assert all monetary fields are still Decimal.

#### Phase B Step 10 — Validation additions

- **Sum aggregation check** — manually run `SELECT SUM(pnl), SUM(gross_pnl), SUM(commission), SUM(slippage) FROM p3_d03_trade_outcome_log` after migration. Confirm results are Decimal-typed and exact.
- **Live reconciliation check** — if any historical broker statements are available, recompute the matched values from D03 and confirm zero drift.

#### Phase B Step 12 — Commit message

```
migration(decimal): phase B — trade outcome log + Redis path

- Schema: ALTER COLUMN to DECIMAL(14,4)/DECIMAL(18,4) for D03 prices and P&L
- Writers: updated b7_position_monitor compute path + 5 other INSERT sites
- Readers: updated SUM aggregations, GUI assembly, RealisedOutcome dataclass
- Redis: trade outcome publish path now preserves Decimal precision
- JSON: pseudo_results and aim_breakdown_at_entry (where monetary) routed
        through dumps_decimal/loads_decimal
- Tests: added sum-precision, reconciliation precision, Redis round-trip
- Migrations: M{NNN} through M{NNN+X} appended to CANONICAL_MIGRATIONS

Note: Pre-existing bug in b5c_circuit_breaker.py (timestamp vs ts column)
deliberately NOT fixed in this migration. Filed as separate follow-up.
```

---

## Phase C — Capital silos, asset constants, daily OHLCV

### C.1 Migration matrix for Phase C


| Table                       | Columns                                           | Target type      |
| --------------------------- | ------------------------------------------------- | ---------------- |
| `p3_d16_user_capital_silos` | `starting_capital`, `total_capital`               | `DECIMAL(18, 2)` |
| `p3_d00_asset_universe`     | `point_value`, `tick_size`, `margin_per_contract` | `DECIMAL(14, 4)` |
| `p3_d30_daily_ohlcv`        | `open`, `high`, `low`, `close`                    | `DECIMAL(14, 4)` |


Stays DOUBLE: `max_portfolio_risk_pct`, `correlation_threshold`, `user_kelly_ceiling` (D16); `warm_up_progress` (D00); `volume` is LONG (D30 — not a money column).

### C.2 JSON STRING columns requiring Decimal-aware encoding in Phase C

- `p3_d16_user_capital_silos.capital_history` — dollar capital snapshots over time. Route through Decimal-aware encoder.
- `p3_d16_user_capital_silos.accounts` — verify contents. If it stores account-level dollar amounts, route through encoder. If purely IDs and metadata, no change needed.

### C.3 Phase C workflow

Follow the standard workflow with these specifics:

#### Phase C Step 4 — Writer sites

D16:

- `captain-online/captain_online/blocks/b7_position_monitor.py:377-387` (INSERT after `new_capital = (d16_row[3] or 0) + net_pnl` at `:356-363`)
- `captain-command/captain_command/main.py:213-221`
- `scripts/bootstrap_production.py:227-245` — note hardcoded `0.10`, `0.70` literals are `max_portfolio_risk_pct` (DOUBLE, not migrated). Leave those alone. Migrate only `starting_capital` and `total_capital`.
- `scripts/seed_test_asset.py:115-133`

D00:

- `shared/questdb_client.py:169-189` (`update_d00_fields`)
- `scripts/bootstrap_production.py:181`
- `scripts/load_p2_multi_asset.py:281`
- `scripts/seed_all_assets.py:197`
- `scripts/seed_real_asset.py:311`
- `scripts/seed_test_asset.py:56-79`

D30:

- `captain-online/captain_online/blocks/b1_features.py:1500-1506`
- `scripts/restore_live_delta.py:136-156`
- `scripts/seed_ohlcv_from_qc.py` (resolve exact lines via F4)

#### Phase C Step 5 — Computation sites

The notable computation chain is Phase B's P&L formula consuming Phase C's `point_value`. After Phase C lands, the temporary `Decimal(str(point_value))` wrapper at the D03 use sites becomes unnecessary — `point_value` arrives as Decimal directly. Audit those sites and remove the redundant wrapping.

OHLC arithmetic in `shared/aim_feature_loader.py:136-157` (`prev_close`, `curr_open`) — convert to Decimal arithmetic.

#### Phase C Step 6 — Reader sites

D16:

- `captain-online/captain_online/blocks/b7_position_monitor.py:337-346` (LATEST ON read)
- `captain-command/captain_command/main.py:185-204`
- `captain-online/captain_online/blocks/orchestrator.py:864`
- `scripts/bootstrap_production.py:216-218`
- `scripts/replay_full_pipeline.py:196`

D00:

- `shared/questdb_client.py:152-156` (`read_d00_row`)
- All of: `b7_position_monitor`, `b1_features`, `b1_data_ingestion`, `b2_gui_data_server`, `orchestrator`, `paper_trader` (resolve exact lines via F4)

D30:

- `shared/aim_feature_loader.py:136-157`
- `shared/online_replay_providers.py` (resolve exact lines via F4)
- `captain-online/captain_online/blocks/b1_features.py:1006-1206`

#### Phase C Step 9 — Tests (Phase C specific)

- **D16 round-trip test** — same pattern as Phase A.
- **D00 round-trip test** — verify `point_value`, `tick_size`, `margin_per_contract` round-trip exactly. Important: the audit fixtures in `tests/fixtures/user_fixtures.py` and `tests/fixtures/synthetic_data.py` use float defaults for `point_value` etc. — update them.
- **D30 round-trip test** — OHLC values round-trip exactly.
- **Capital history JSON round-trip** — write a `capital_history` dict containing Decimal snapshots, read back, assert Decimal preservation.
- **End-to-end P&L computation test** — now that point_value is Decimal end-to-end, write a test that simulates a single ES trade (entry, exit, point_value=50.0, contracts=2) and asserts the computed `pnl` is exactly correct with no float drift anywhere in the pipeline. This is the test that proves the migration achieved its goal.

#### Phase C Step 10 — Validation additions

- **End-to-end pipeline check** — run a synthetic trade through the full pipeline (D00 lookup → D30 reference → D03 insert → D08 balance update → D23 L_t update). Confirm no float coercion happens at any boundary. Use `type()` assertions in test code or a logging hook.
- **Cleanup verification** — confirm the temporary `Decimal(str(point_value))` wrappers added in Phase B are removed where Phase C now provides Decimal directly.

#### Phase C Step 12 — Commit message

```
migration(decimal): phase C — capital silos, asset constants, OHLCV

- Schema: ALTER COLUMN to DECIMAL for D16, D00, D30 monetary columns
- Writers: updated INSERT sites across services and seed scripts
- Readers: updated consumers across blocks; removed temporary
        Decimal(str(point_value)) wrappers from Phase B
- JSON: capital_history routed through dumps_decimal/loads_decimal
- Tests: added round-trip tests + end-to-end P&L computation precision test
- Migrations: M{NNN} through M{NNN+X} appended to CANONICAL_MIGRATIONS
```

---

## Cross-cutting rules (apply to every phase)

- **Use `shared.decimal_boundary` at every Decimal/float crossing.** All read sites for DECIMAL columns and all dict-construction sites for monetary fields MUST use `as_money` / `as_money_or_none` / `to_float`. Per-file private `_money*` helpers were consolidated 2026-04-30 — never re-create them. The CI gate `tests/test_decimal_boundary_lint.py` blocks PRs that re-introduce the `r[N] or 0.0` antipattern. See `docs2/quick-fixes/fixing-decimal-errors/` for the audit.
- **Read before write.** Before editing any file, read it in full to confirm its current state matches the audit. If it doesn't, stop and report.
- **One phase at a time.** Do not preemptively touch anything that belongs to a later phase, even if convenient. The exception is Phase B's temporary `Decimal(str(point_value))` wrappers, which Phase C explicitly removes.
- **Cite `file:line` in every phase report** for every change made. The Phase 1 audit's wide line ranges are NOT acceptable as citations — resolve them via F4 before making changes.
- **JSON-string monetary values always round-trip through `dumps_decimal`/`loads_decimal`.** This is non-negotiable for production-readiness. If you encounter a JSON STRING column not listed above that contains dollar amounts, stop and report — do not silently extend scope.
- **Constants in formulas must be wrapped as `Decimal("...")`** — string-constructed, never `Decimal(4500.0)` because that inherits the float representation. This applies to every monetary literal (4500, 150000, 5000, 160714, 1000, 1500, 0.5, 0.7, etc.) appearing alongside Decimal operands.
- **r_bar and sigma stay DOUBLE.** Convert to Decimal at use sites only: `Decimal(str(r_bar)) + Decimal(str(beta_b)) * L_b`. Do not migrate these columns.
- **Float-to-Decimal conversion always uses `Decimal(str(value))`.** Never `Decimal(value)` — that inherits the float representation including any artefacts.
- **psycopg2 PG-wire handles Decimal natively.** Pass Decimal directly via `%s` placeholders. Do not convert to string first.
- **DEDUP keys are unaffected.** None of the migrating columns are part of any DEDUP key. Do not modify DEDUP clauses.
- **Pre-existing bugs are out of scope.** The `timestamp` vs `ts` issue in `b5c_circuit_breaker.py` and the D19 reconciliation_log JSON snapshot fields are documented separately — do not fix them in this migration.
- **If anything in the audit is wrong** — a writer site you can't find, a model that no longer exists, an unexpected file structure — stop, report it, and wait for guidance. Do not improvise.
- **Rollback discipline.** If a validation gate fails and you cannot resolve it in two attempts, revert the branch to its baseline commit and report. Do not leave the codebase in a half-migrated state.
- **Production deployment timing.** Do not run any phase's `ALTER TABLE` against the production QuestDB during active trading hours. The agent does not deploy to production — that is my decision and my action. The agent's job ends with the validated branch ready for deployment.

---

## Final summary (after all three phases approved)

Produce `MONETARY_DECIMAL_MIGRATION_COMPLETE.md` at the repo root summarising:

- Total columns migrated to DECIMAL (with table)
- Total JSON STRING columns now using Decimal-aware encoder (with table)
- Total writer/reader sites changed
- Test coverage added (file list with test counts)
- Branches and commits produced
- Migrations appended (M{NNN} range)
- Constants wrapped as `Decimal("...")` (count by file)
- **Deferred items:**
  - The `timestamp` vs `ts` bug in `b5c_circuit_breaker.py` (out of scope, file as separate ticket)
  - `p3_d19_reconciliation_log.mismatches` JSON snapshot fields (out of scope)
  - `p3_d27_pseudotrader_forecasts.equity_curve` and `metrics` JSON fields (deferred — list explicitly so future work knows)
  - `p3_d06_injection_history.pseudo_results` if not migrated in Phase B (verify and note)
  - r_bar / sigma elevation to DECIMAL (intentionally not done, document Isaac's reasoning)
  - Any additional JSON STRING columns containing dollar values that were discovered during implementation but ruled out of scope
- **Production deployment checklist** for the human deploying this:
  - Recommended maintenance window
  - Ordered ALTER TABLE sequence per phase
  - Backup verification steps
  - Post-deployment smoke tests
  - Rollback procedure

