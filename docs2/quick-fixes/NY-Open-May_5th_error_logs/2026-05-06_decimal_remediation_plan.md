# Decimal Boundary Bug Class — Final Remediation Plan

**Date:** 2026-05-06
**Author:** Cursor agent (Opus 4.7) for Nomaan
**Source audit:** `2026-05-06_issue5_decimal_double_root_cause_audit.md` (this folder)
**Execution mode:** Single in-session deep fix via `/do` skill (subagents). All phases execute consecutively in this session.
**Goal:** Close the Decimal/QuestDB bug class **once and forever**. After this work lands, no future market open should crash on a Decimal/type-mismatch error.

---

## Decisions locked in (from clarifying questions)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Layer B (`loads_decimal` over-coercion fix) included? | **YES — structural marker `{"__type__":"Decimal","value":"…"}` with backwards-compat reader for one cycle** |
| 2 | Typed-INSERT helper shape | **Functional `qexecute(cur, sql, params)` — auto-parses SQL, ~50 mechanical site changes** |
| 3 | Deployment cadence | **Single deep-fix session, executed by Cursor via subagents and `/do`** |

---

## Architectural shape of the fix (one paragraph)

The whole codebase already has a clean producer-side boundary (`shared/decimal_boundary.py`: `as_money` / `as_money_or_none` / `to_float`). What's missing is the **consumer-side boundary** at the `cur.execute()` write site. We add ONE function — `qexecute(cur, sql, params)` in `shared/questdb_client.py` — that auto-parses the destination table + columns out of the SQL, looks up each column's type from `shared.canonical_schemas.COLUMN_TYPES` (auto-derived from existing DDL strings, zero manual maintenance), and coerces each `Decimal` parameter to the right Python type **before** psycopg2 sees it. Combine with a Layer B marker rewrite of `dumps_decimal`/`loads_decimal` so Redis JSON stops creating spurious Decimals from numeric-looking strings (e.g. account IDs). Add a lint rule that refuses any new raw `cur.execute("INSERT INTO p3_…")` and a live-DB e2e regression test per high-risk DOUBLE column. Done. **No new abstractions. No clever metaclasses. No global cursor magic.** The complexity sits in exactly two functions (`COLUMN_TYPES` parser + `qexecute`) and one JSON marker change.

---

## Phase map at a glance

| Phase | Scope | Subagent count | Parallelisable | Effort |
|-------|-------|----------------|----------------|--------|
| **0** | Documentation Discovery | 3 (parallel) | yes | 0.5h |
| **1** | Hotfix — close Issue 5 + 2 sister-shape sites | 1 | sequential | 0.5h |
| **2** | Foundation — `COLUMN_TYPES` + `qexecute` helper + unit tests | 1 | sequential | 1.5h |
| **3** | Migration — convert ~50 INSERT/UPDATE sites to `qexecute` | 4 (parallel by process) | yes | 2h |
| **4** | Layer B — structural Decimal markers in `dumps_decimal`/`loads_decimal` + backwards-compat reader | 1 | sequential | 1.5h |
| **5** | Lint hardening — refuse raw `cur.execute("INSERT INTO p3_…")` | 1 | sequential | 0.5h |
| **6** | Live-DB e2e regression suite | 1 | sequential | 1h |
| **7** | Final verification, commit, dual-remote push | 1 | sequential | 0.5h |

**Total wall-clock:** ~8h of focused execution; ~5–6h with parallel Phase-3 subagents.

---

## Cross-phase rules (anti-patterns guarded against in EVERY phase)

These rules apply to every subagent in every phase. Bake them into the subagent prompt.

1. **Never invent psycopg2/QuestDB APIs.** If a function is referenced, the subagent must read it before calling it (verify name + signature + return type).
2. **Never use `Decimal(0.1)` with a float argument.** Always `Decimal(str(x))` or `Decimal("0.1")` per `shared/decimal_boundary.py:41`.
3. **Never use `value or 0.0` on a monetary field.** Use `as_money(value)` per `scripts/lint_decimal_boundary.py`. Suppress with `# decimal-boundary: ok` only for genuine non-monetary defaults (probabilities, divisors).
4. **Never use the no-op ternary `float(x) if not isinstance(x, T) else float(x)`.** Use `to_float(x)` from `shared.decimal_boundary`. Caught by the existing lint at `scripts/lint_decimal_boundary.py:68-72`.
5. **Never bypass `qexecute` for INSERT/UPDATE into `p3_*` tables** (after Phase 3 lands). The lint added in Phase 5 enforces this.
6. **Never `--force` push to either `origin` or `multi-user` remote.** Per `.cursor/rules/captain-deploy-and-tower-discipline.mdc`.
7. **Never modify** the lint-allowlisted test files in `scripts/lint_decimal_boundary.py:78-86` (canonical_schemas, decimal_boundary itself, the lint script, etc.) — adding a violation in those files breaks the meta-tests.

---

## Phase 0 — Documentation Discovery (3 parallel subagents)

### Why first

Per the make-plan skill's MANDATORY rule: discover before implementing. The output of this phase is a single consolidated `_phase0_findings.md` that every later phase references — so subagents in Phase 1+ don't re-read the same files.

### Subagent 0A — Module deep-read (read-only)

**Sources to consult (every file MUST be opened with the Read tool, not summarised from memory):**

- `shared/questdb_client.py` — focus on `_decimal_to_cast_sql` (lines 36–59), `register_adapter` (62–65), `get_cursor` (171–186), the `D00_COLUMNS` constant (193–200), and the `update_d00_fields` f-string INSERT pattern (226–252).
- `shared/decimal_boundary.py` — full file. Note the four public APIs and the docstring conventions.
- `shared/decimal_json.py` — full file. Specifically the `_coerce` aggressive Decimal coercion at lines 47–57.
- `shared/json_helpers.py` — full file. Note `parse_json_decimal` is a thin wrapper around `loads_decimal`.
- `shared/canonical_schemas.py` — full file. This is the source of truth for column types.
- `scripts/lint_decimal_boundary.py` — full file. Note the suppression marker (`# decimal-boundary: ok`) and the no-op-ternary check.

**Deliverable:** `docs2/quick-fixes/NY-Open-May_5th_error_logs/_phase0_module_summaries.md` containing:

- Current `register_adapter(Decimal, …)` behaviour and exactly which call paths rely on it.
- Current `loads_decimal._coerce` over-coercion rule and the reasoning behind it.
- Current public API of `decimal_boundary` helpers with exact signatures.
- A table of every column type in `canonical_schemas.py` keyed by table name (this becomes the basis for `COLUMN_TYPES` in Phase 2).
- A "what NOT to break" list — load-bearing behaviour that the structural fix MUST preserve.

**Confidence note required:** subagent must list any module it could not read in full (timeout, permissions) and explicitly call out what's missing.

### Subagent 0B — INSERT/UPDATE site inventory (read-only)

**Method:** Run Grep (NOT find/rg from terminal) for each pattern below, in parallel where possible:

- `INSERT INTO p3_` — production INSERTs
- `UPDATE p3_` — production UPDATEs
- `cur\.execute\(\s*"""\s*INSERT INTO\s+p3_` — multi-line INSERTs
- `cur\.execute\(\s*f"INSERT INTO\s+p3_` — f-string INSERTs (these need explicit `columns=` in Phase 3)

For each match, capture: file path, line number, table name, column list (if statically determinable), source of `params` (literal tuple? variable? function arg?).

**Deliverable:** `docs2/quick-fixes/NY-Open-May_5th_error_logs/_phase0_insert_inventory.md` — a CSV-shaped table:

```
| process       | file:line                                        | table                    | columns_static | f_string | needs_explicit |
|---------------|--------------------------------------------------|--------------------------|----------------|----------|----------------|
| online        | b7_position_monitor.py:551                       | p3_d03_trade_outcome_log | yes (24 cols)  | no       | no             |
| command       | b8_reconciliation.py:563                         | p3_d08_tsm_state         | yes (28 cols)  | no       | no             |
| online        | shared/questdb_client.py:243 (update_d00_fields) | p3_d00_asset_universe    | no (D00_COLUMNS dict) | yes | YES (use columns=D00_COLUMNS) |
| ...           | ...                                              | ...                      | ...            | ...      | ...            |
```

Bucket by process (online / offline / command / shared / scripts / tests) for Phase 3 parallel allocation.

**Expected count:** ≈75 production sites, ≈50 in tests/scripts.

### Subagent 0C — Prior-pattern review (read-only)

**Sources to consult:**

- `docs2/quick-fixes/fixing-decimal-errors/EXHAUSTIVE_AUDIT_REPORT.md`
- `docs2/quick-fixes/fixing-decimal-errors/EXECUTION_SUMMARY.md`
- `docs2/quick-fixes/fixing-decimal-errors/TOWER_VALIDATION_RUNBOOK_FINAL.md` (for the existing test ritual)
- `docs2/context/tracking_context.md` (for the prior `account_id` SYMBOL bug history)
- This audit (`2026-05-06_issue5_decimal_double_root_cause_audit.md`)
- `MONETARY_DECIMAL_MIGRATION_PLAN.md` and `MONETARY_DECIMAL_PHASE_B_REPORT.md`

**Deliverable:** `docs2/quick-fixes/NY-Open-May_5th_error_logs/_phase0_prior_patterns.md` containing:

- The 5-incident timeline (already in the audit) — verify it's complete.
- The "what's already shipped vs what's missing" delta.
- Any tower validation rituals that Phase 7 must reproduce.
- Any test files that the Phase 4 JSON-marker change will need to update.

### Phase 0 verification

- All three deliverable files exist and pass a hand-check that they're not empty / not summary-from-memory.
- `_phase0_module_summaries.md` includes the column-type table.
- `_phase0_insert_inventory.md` count matches the existing grep totals.
- Each subagent's "Confidence" section is filled in.

---

## Phase 1 — Immediate hotfix (single subagent)

### Goal

Patch the three 🔴-flagged sites from the audit so the next NY/LON/APAC open does not crash on Issue 5 even if the structural fix later in this session has a regression.

### What to implement

In `captain-online/captain_online/blocks/b7_position_monitor.py`:

```python
# In _write_trade_outcome (~line 533, ABOVE the existing as_money_or_none block):
# DOUBLE-target columns must be float, not Decimal — the global psycopg2 adapter
# would render Decimal as cast('<v>' as DECIMAL(p,s)) which QuestDB rejects for DOUBLE.
aim_modifier = to_float(aim_modifier, default=1.0)
```

Required import addition near line 45:

```python
from shared.decimal_boundary import as_money as _money_d, as_money_or_none, to_float
```

In `captain-online/captain_online/blocks/b7_shadow_monitor.py:_publish_shadow_trade_outcome` (around line 174 where `aim_modifier_at_entry` is set in the outcome dict), apply the same `to_float` coercion before publishing.

In `captain-online/captain_online/blocks/b7_position_monitor.py:_update_capital_and_cb` (around line 660–685), the D16 INSERT writes `max_portfolio_risk_pct` / `correlation_threshold` / `user_kelly_ceiling` (all DOUBLE) via raw passthrough of `d16_row[6]`/`[7]`/`[8]`. Wrap each in `to_float(d16_row[N], default=0.0)` at the INSERT call site.

### References (the subagent MUST read these before editing)

- This audit `§1.2` for the exact failure path.
- `_phase0_module_summaries.md` for the `to_float` signature.
- The current `_write_trade_outcome` lines 533–540 — note how `entry_price` etc. already use `as_money_or_none`. Match the style exactly.

### Tests to add

`tests/test_b7_decimal_double_boundary.py` with three test cases:

1. `_write_trade_outcome` accepts `aim_modifier=Decimal("0.96")` and the cursor sees `0.96` (float), NOT a Decimal.
2. `_publish_shadow_trade_outcome` mirrors the same coercion.
3. `_update_capital_and_cb` D16 INSERT receives floats for the three DOUBLE columns even when the D16 row read returns Decimals.

Each test uses a `MockCursor` (pattern at `tests/test_orchestrator_session_budget_init.py`) to inspect the INSERT param tuple types.

### Verification checklist

- [ ] `python3 -m pytest tests/test_b7_decimal_double_boundary.py -v` — all 3 pass.
- [ ] `python3 scripts/lint_decimal_boundary.py` — exits 0.
- [ ] Existing `tests/test_b7_position_monitor_decimal_boundary.py` still passes.
- [ ] No diff outside the three named functions.

### Anti-patterns to refuse

- Do NOT replace `as_money_or_none` for the 7 DECIMAL fields with `to_float`. Those columns ARE DECIMAL — they need Decimal-typed Python values to round-trip correctly.
- Do NOT add `to_float` to `aim_breakdown` (that's a STRING JSON column, handled by `dumps_decimal`).
- Do NOT touch `_decimal_to_cast_sql` or `register_adapter`. Those stay as-is.

---

## Phase 2 — Foundation (single subagent)

### Goal

Build the typed-INSERT helper foundation. After this phase, the code exists and is unit-tested, but no INSERT site uses it yet (that's Phase 3).

### Sub-phase 2a — Auto-derive `COLUMN_TYPES`

In `shared/canonical_schemas.py`, add a new module-level `COLUMN_TYPES` dict, derived at import time by parsing the existing DDL strings.

**Implementation sketch:**

```python
import re

# Regex matches lines like "    column_name TYPE_KEYWORD," inside a CREATE TABLE.
# Captures both bare types (DOUBLE, INT, SYMBOL, BOOLEAN, STRING, TIMESTAMP, LONG)
# and parameterised types (DECIMAL(18, 2), DECIMAL(14, 6)). Strips trailing
# comma, comment, and column constraints.
_COLUMN_RE = re.compile(
    r"^\s+([a-z_][a-z0-9_]*)\s+"               # column name
    r"(DECIMAL\s*\(\s*\d+\s*,\s*\d+\s*\)"      # DECIMAL(p,s)
    r"|DOUBLE|FLOAT|INT|LONG|SHORT|BOOLEAN"
    r"|STRING|VARCHAR|SYMBOL|TIMESTAMP|DATE|UUID|CHAR"
    r")\b",
    re.IGNORECASE,
)

def _parse_columns(ddl: str) -> dict[str, str]:
    """Extract {column_name: column_type} from a CREATE TABLE DDL string."""
    cols: dict[str, str] = {}
    for line in ddl.splitlines():
        m = _COLUMN_RE.match(line)
        if not m:
            continue
        col, typ = m.group(1), m.group(2).upper().replace(" ", "")
        cols[col] = typ
    return cols

def _build_column_types() -> dict[str, dict[str, str]]:
    """Build {table_name: {column_name: column_type}} from CANONICAL_DDLS."""
    out: dict[str, dict[str, str]] = {}
    for ddl in CANONICAL_DDLS:
        table = table_name_of(ddl)
        cols = _parse_columns(ddl)
        if cols:
            out[table] = cols
    return out

COLUMN_TYPES: dict[str, dict[str, str]] = _build_column_types()
```

**Required tests:** `tests/test_canonical_column_types.py`:

1. Every DDL in `CANONICAL_DDLS` produces a non-empty column dict.
2. `COLUMN_TYPES["p3_d03_trade_outcome_log"]["aim_modifier_at_entry"] == "DOUBLE"`.
3. `COLUMN_TYPES["p3_d03_trade_outcome_log"]["entry_price"].startswith("DECIMAL")`.
4. `COLUMN_TYPES["p3_d08_tsm_state"]["account_id"] == "SYMBOL"`.
5. `COLUMN_TYPES["p3_d08_tsm_state"]["max_contracts"] == "INT"`.
6. `CANONICAL_MIGRATIONS` ALTER TABLE entries are reflected (e.g. `current_balance` is DECIMAL(18,2), not the original DOUBLE) — this requires the parser to also process `ALTER COLUMN ... TYPE ...` statements OR to be re-run after migrations land. Choose: process `CANONICAL_MIGRATIONS` too. Add a second pass.

### Sub-phase 2b — `qexecute` helper

In `shared/questdb_client.py`, add **after** the existing `register_adapter(Decimal, …)` block:

```python
# ------------------------------------------------------------------------- #
# Typed-INSERT consumer-boundary helper (May 2026, fixes Issue 5 bug class) #
# ------------------------------------------------------------------------- #
#
# The global Decimal adapter above renders every Decimal as
# cast('<v>' as DECIMAL(p,s)) — correct for DECIMAL columns, FATAL for
# DOUBLE / SYMBOL / INT columns (QuestDB rejects DECIMAL→DOUBLE casts on
# assignment). qexecute() looks up each column's type from
# shared.canonical_schemas.COLUMN_TYPES and coerces Decimal-typed params
# to the right Python type BEFORE psycopg2 sees them.
#
# Usage:
#   qexecute(cur, "INSERT INTO p3_d03_trade_outcome_log (col1, col2, ...) VALUES (%s, %s, ...)", (v1, v2, ...))
#
# For dynamic SQL (f-strings) where columns can't be auto-parsed, pass:
#   qexecute(cur, sql, params, columns=["col1", "col2", ...])
#
# Returns the cursor's rowcount — same as cur.execute().

import re
from decimal import Decimal
from datetime import datetime
from shared.canonical_schemas import COLUMN_TYPES

_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+(p[23]_[a-z0-9_]+)\s*\(([^)]+)\)\s*VALUES",
    re.IGNORECASE | re.DOTALL,
)
_UPDATE_RE = re.compile(
    r"UPDATE\s+(p[23]_[a-z0-9_]+)\s+SET\s+(.+?)(?:\s+WHERE|\s*$)",
    re.IGNORECASE | re.DOTALL,
)


def _parse_insert_columns(sql: str) -> tuple[str, list[str]] | None:
    """Extract (table_name, [columns]) from an INSERT statement.

    Returns None for non-INSERT statements or unparseable SQL — caller
    falls through to default behaviour.
    """
    m = _INSERT_RE.search(sql)
    if not m:
        return None
    table = m.group(1).lower()
    cols = [c.strip() for c in m.group(2).split(",") if c.strip()]
    return table, cols


def _coerce_for_column(value: object, col_type: str) -> object:
    """Coerce a single param to the right Python type for col_type.

    DECIMAL columns: leave Decimal as-is (existing global adapter handles it).
    DOUBLE / FLOAT:   Decimal -> float; None stays None.
    SYMBOL / VARCHAR / STRING / CHAR: Decimal -> str; None stays None.
    INT / LONG / SHORT / BYTE:       Decimal -> int; None stays None.
    BOOLEAN:          Decimal/numeric -> bool; None stays None.
    TIMESTAMP / DATE: datetime -> isoformat string; passthrough otherwise.
    UUID / GEOHASH / IPv4: passthrough.
    """
    if value is None:
        return None
    if col_type.startswith("DECIMAL"):
        return value
    if col_type in ("DOUBLE", "FLOAT"):
        if isinstance(value, Decimal):
            return float(value)
        return value
    if col_type in ("SYMBOL", "VARCHAR", "STRING", "CHAR"):
        if isinstance(value, Decimal):
            return str(value)
        return value
    if col_type in ("INT", "LONG", "SHORT", "BYTE"):
        if isinstance(value, Decimal):
            return int(value)
        return value
    if col_type == "BOOLEAN":
        if isinstance(value, Decimal):
            return bool(int(value))
        return value
    if col_type in ("TIMESTAMP", "DATE"):
        if isinstance(value, datetime):
            return value.isoformat()
        return value
    return value  # unknown column type — passthrough (safer than crashing)


def qexecute(cur, sql: str, params: tuple = (), *, table: str | None = None,
             columns: list[str] | None = None) -> int:
    """psycopg2 cur.execute() wrapper that coerces each param to its column's type.

    For INSERT and UPDATE statements into p3_*/p2_* tables:
      - Parses the destination table + column list from the SQL (or uses
        the explicit `table=` / `columns=` overrides for f-string SQLs).
      - Looks up each column's type in shared.canonical_schemas.COLUMN_TYPES.
      - Coerces each param to the right Python type via _coerce_for_column.
      - Calls cur.execute(sql, coerced_params) and returns rowcount.

    For non-INSERT/UPDATE statements (SELECT, DELETE, DDL): pass-through to
    cur.execute() with no coercion — params for filter clauses are not
    column-write targets.
    """
    if not isinstance(sql, str):
        cur.execute(sql, params)
        return cur.rowcount

    parsed_table = None
    parsed_cols = None
    if columns is not None:
        parsed_table = table
        parsed_cols = columns
    else:
        parse = _parse_insert_columns(sql)
        if parse is not None:
            parsed_table, parsed_cols = parse

    if parsed_table is None or parsed_cols is None:
        # Not an INSERT/UPDATE we can route — pass through unchanged.
        cur.execute(sql, params)
        return cur.rowcount

    type_map = COLUMN_TYPES.get(parsed_table)
    if type_map is None:
        # Unknown table (probably a test stub or out-of-scope) — pass through.
        cur.execute(sql, params)
        return cur.rowcount

    # Coerce each positional param against the matching column's type.
    coerced = list(params)
    for i, col in enumerate(parsed_cols):
        if i >= len(coerced):
            break  # SQL has more cols than params (NULL or now() literals)
        col_type = type_map.get(col)
        if col_type is None:
            continue
        coerced[i] = _coerce_for_column(coerced[i], col_type)

    cur.execute(sql, tuple(coerced))
    return cur.rowcount
```

### Required tests for Phase 2b

`tests/test_qexecute.py`:

1. `qexecute` with a Decimal aim_modifier into D03 sends a `float` to the cursor.
2. `qexecute` with a Decimal account_id into D08 sends a `str` to the cursor.
3. `qexecute` with a Decimal session_id into D03 sends an `int` to the cursor.
4. `qexecute` with a Decimal entry_price into D03 sends a `Decimal` (no change — it's a DECIMAL column).
5. `qexecute` with `None` for `max_drawdown_limit` sends `None` (preserves NULL).
6. `qexecute` with a multi-line SQL string parses correctly.
7. `qexecute` with f-string-built SQL + explicit `columns=` parameter works.
8. `qexecute` on a SELECT statement passes through unchanged (no coercion).
9. `qexecute` on a `cur.execute("CREATE TABLE …")` DDL passes through unchanged.
10. `qexecute` with an unknown table name (no entry in COLUMN_TYPES) passes through unchanged with a single warning log.

### Phase 2 verification checklist

- [ ] `python3 -m pytest tests/test_canonical_column_types.py tests/test_qexecute.py -v` — all green.
- [ ] `from shared.questdb_client import qexecute` succeeds.
- [ ] `from shared.canonical_schemas import COLUMN_TYPES; assert COLUMN_TYPES["p3_d03_trade_outcome_log"]["aim_modifier_at_entry"] == "DOUBLE"`.
- [ ] `python3 scripts/lint_decimal_boundary.py` — still 0 violations.

### Anti-patterns to refuse

- Do NOT add a side effect to `qexecute` other than the call to `cur.execute`. No metric/log emission inside the hot path.
- Do NOT remove or alter `_decimal_to_cast_sql` / `register_adapter` — those still handle the DECIMAL column path inside `qexecute`.
- Do NOT make `qexecute` call `cur.executemany` or batch — it's a 1-to-1 wrapper for clarity.

---

## Phase 3 — Migration to `qexecute` (4 parallel subagents by process)

### Goal

Convert every production INSERT/UPDATE site into `p3_*`/`p2_*` tables to call `qexecute` instead of raw `cur.execute`.

### Subagent 3a — captain-online

Files (verify against `_phase0_insert_inventory.md`):

- `captain-online/captain_online/blocks/b1_data_ingestion.py`
- `captain-online/captain_online/blocks/b1_features.py`
- `captain-online/captain_online/blocks/b6_signal_output.py`
- `captain-online/captain_online/blocks/b7_position_monitor.py`
- `captain-online/captain_online/blocks/b7_shadow_monitor.py`
- `captain-online/captain_online/blocks/b8_concentration_monitor.py`
- `captain-online/captain_online/blocks/b9_capacity_evaluation.py`
- `captain-online/captain_online/blocks/b5b_quality_gate.py`
- `captain-online/captain_online/blocks/hmm_inference_block.py`
- `captain-online/captain_online/blocks/orchestrator.py`

### Subagent 3b — captain-offline

Files:

- `captain-offline/captain_offline/blocks/orchestrator.py`
- `captain-offline/captain_offline/blocks/version_snapshot.py`
- `captain-offline/captain_offline/blocks/bootstrap.py`
- `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py`
- `captain-offline/captain_offline/blocks/b1_aim16_hmm.py`
- `captain-offline/captain_offline/blocks/b1_dma_update.py`
- `captain-offline/captain_offline/blocks/b1_drift_detection.py`
- `captain-offline/captain_offline/blocks/b1_hdwm_diversity.py`
- `captain-offline/captain_offline/blocks/b2_bocpd.py`
- `captain-offline/captain_offline/blocks/b2_cusum.py`
- `captain-offline/captain_offline/blocks/b2_level_escalation.py`
- `captain-offline/captain_offline/blocks/b3_pseudotrader.py`
- `captain-offline/captain_offline/blocks/b4_injection.py`
- `captain-offline/captain_offline/blocks/b5_sensitivity.py`
- `captain-offline/captain_offline/blocks/b7_tsm_simulation.py`
- `captain-offline/captain_offline/blocks/b8_cb_params.py`
- `captain-offline/captain_offline/blocks/b8_kelly_update.py`
- `captain-offline/captain_offline/blocks/b9_diagnostic.py`

### Subagent 3c — captain-command

Files:

- `captain-command/captain_command/api.py`
- `captain-command/captain_command/main.py`
- `captain-command/captain_command/blocks/orchestrator.py`
- `captain-command/captain_command/blocks/b1_core_routing.py`
- `captain-command/captain_command/blocks/b3_api_adapter.py`
- `captain-command/captain_command/blocks/b4_tsm_manager.py`
- `captain-command/captain_command/blocks/b5_injection_flow.py`
- `captain-command/captain_command/blocks/b6_reports.py`
- `captain-command/captain_command/blocks/b7_notifications.py`
- `captain-command/captain_command/blocks/b8_reconciliation.py`
- `captain-command/captain_command/blocks/b9_incident_response.py`
- `captain-command/captain_command/blocks/b11_replay_runner.py`
- `captain-command/captain_command/blocks/telegram_bot.py`

### Subagent 3d — shared + scripts

Files:

- `shared/questdb_client.py` (the `update_d00_fields` f-string INSERT — needs `columns=D00_COLUMNS` explicit override)
- `shared/trade_source.py`
- `scripts/bootstrap_production.py`
- `scripts/load_p2_multi_asset.py`
- `scripts/seed_*.py` (all)
- `scripts/backfill_*.py` (all)
- `scripts/fix_bootstrap_data.py`
- `scripts/reset_capital_state_to_broker_truth.py`
- `scripts/restore_live_delta.py`
- `scripts/paper_trader.py`
- `scripts/bootstrap_opening_volumes.py`

### Migration recipe (every subagent uses this exact recipe)

For each file:

1. **Read the file** to locate every `cur.execute("INSERT INTO p3_…)` and `cur.execute("UPDATE p3_…)` call.
2. **Add the import** if not present:
   ```python
   from shared.questdb_client import get_cursor, qexecute
   ```
3. **Mechanical replacement:**
   - `cur.execute(sql, params)` → `qexecute(cur, sql, params)` for every `INSERT INTO p3_*` and `UPDATE p3_*` site.
   - Do NOT touch SELECT, DELETE, CREATE TABLE, or non-`p3_*`/`p2_*` statements.
   - For f-string-built SQL where columns are computed at runtime (only known case: `update_d00_fields` in `shared/questdb_client.py`), use `qexecute(cur, sql, params, columns=D00_COLUMNS)`.
4. **Run the existing tests for that block** to confirm no regression.
5. **Diff check:** the per-file diff should be ONLY `cur.execute(` → `qexecute(cur, ` plus an import — no other logic changes.

### Phase 3 verification checklist (each subagent runs at end of its bucket)

- [ ] `grep -rn 'cur\.execute(\s*"""\?INSERT INTO p3_' <bucket>` returns zero matches (all converted).
- [ ] Existing block tests pass (`pytest tests/ -k <block_name>`).
- [ ] No accidental conversion of SELECT/DDL.

### Phase 3 final verification (orchestrator runs after all 4 subagents)

- [ ] Repo-wide `grep -rn 'cur\.execute(\s*"""\?INSERT INTO p[23]_' --include='*.py' captain-online captain-offline captain-command shared scripts` returns zero matches (excluding test files which migrate in Phase 6).
- [ ] `python3 scripts/lint_decimal_boundary.py` — 0 violations.
- [ ] Full fast-gate runs: `PYTHONPATH=./:./captain-online:./captain-offline:./captain-command python3 -B -m pytest tests/ --ignore=tests/test_integration_e2e.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py --ignore=tests/test_account_lifecycle.py -v` — all green.

### Anti-patterns to refuse in Phase 3

- Do NOT change ANY logic during migration — pure mechanical replacement.
- Do NOT migrate test files in this phase (they migrate selectively in Phase 6 alongside the e2e tests).
- Do NOT introduce new try/except wrappers around `qexecute` calls.
- Do NOT change variable names, even ones that look outdated.

---

## Phase 4 — Layer B: Structural Decimal markers in JSON (single subagent)

### Goal

Stop `loads_decimal._coerce` from over-coercing every numeric-looking string to Decimal. Switch to a structural marker so only **explicitly serialised** Decimals come back as Decimal.

### Sub-phase 4a — Update `dumps_decimal`

In `shared/decimal_json.py`, replace `DecimalJSONEncoder.default` so a `Decimal` is serialised as a marker dict, not a bare string:

```python
class DecimalJSONEncoder(json.JSONEncoder):
    """Serialise Decimal as a structural marker to enable lossless round-trip
    without ambiguous string→Decimal heuristics on the decode side."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return {"__type__": "Decimal", "value": format(obj, "f")}
        return super().default(obj)
```

`format(obj, "f")` matches the existing `_decimal_to_cast_sql` precision discipline (expands scientific notation).

### Sub-phase 4b — Update `loads_decimal`

```python
def loads_decimal(s: str, *, coerce_json_int: bool = True, legacy: bool = True) -> Any:
    """Parse JSON. Decimals are reconstructed ONLY from the structural marker
    {"__type__": "Decimal", "value": "<digits>"}. JSON ints/floats follow the
    parse_int/parse_float behaviour. Plain strings stay strings — no more
    ambiguous numeric-string coercion.

    `legacy=True` (default during the 2026-05 migration window): also accepts
    bare-string Decimals that match a heuristic (numeric, contains a decimal
    point, length >= 5) for backwards compatibility with in-flight Redis
    payloads written by pre-marker producers. This compat path emits a
    DeprecationWarning the first time it fires per process.

    Set `legacy=False` once the migration window closes (≥1 weekly cycle
    after Phase 4 deploys, confirmed via `captain:open_positions` Redis hash
    inspection showing all entries use the new marker format).
    """
    parse_int = Decimal if coerce_json_int else int
    data = json.loads(s, parse_float=Decimal, parse_int=parse_int)

    return _coerce_with_marker(data, legacy=legacy)


_LEGACY_WARNED = False


def _coerce_with_marker(obj: Any, *, legacy: bool) -> Any:
    if isinstance(obj, dict):
        # Marker detection: {"__type__": "Decimal", "value": "<v>"}
        if obj.get("__type__") == "Decimal" and "value" in obj:
            try:
                return Decimal(str(obj["value"]))
            except InvalidOperation:
                return obj  # malformed marker — leave as dict
        return {k: _coerce_with_marker(v, legacy=legacy) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_with_marker(v, legacy=legacy) for v in obj]
    if isinstance(obj, str) and legacy:
        # Legacy heuristic: bare-string Decimal from pre-marker producers.
        # Only fires for strings that look explicitly numeric AND contain a
        # decimal point AND are long enough to be unambiguous (excludes
        # account IDs like "21855714" which are integer-shaped).
        if "." in obj and len(obj) >= 5:
            try:
                v = Decimal(obj)
                global _LEGACY_WARNED
                if not _LEGACY_WARNED:
                    import warnings
                    warnings.warn(
                        "loads_decimal: legacy bare-string Decimal coercion fired. "
                        "Set legacy=False once all producers emit the structural "
                        "marker (see shared/decimal_json.py:dumps_decimal).",
                        DeprecationWarning,
                        stacklevel=3,
                    )
                    _LEGACY_WARNED = True
                return v
            except InvalidOperation:
                return obj
        return obj
    return obj
```

**Critical:** the legacy heuristic ONLY matches strings with a decimal point AND length ≥ 5. This excludes:
- `"21855714"` (account ID, integer-shaped) — stays str ✓
- `"primary_user"` (alphabetic) — stays str ✓
- `"SIG-...."` (UUID-shaped) — stays str ✓
- `"1"`, `"0"`, `"1.5"` (short numeric) — stays str ✓
- `"4523.50"`, `"0.96000000"` (decimal-shaped, ≥5 chars) — coerces to Decimal ✓ (matches old behaviour for legitimate price strings)

### Sub-phase 4c — Backwards-compat producer test

In `tests/test_decimal_json_marker.py`:

1. `dumps_decimal({"price": Decimal("0.96")})` produces `{"price": {"__type__": "Decimal", "value": "0.96"}}`.
2. `loads_decimal(...)` of the above returns `{"price": Decimal("0.96")}`.
3. `loads_decimal('{"account_id": "21855714"}')` returns `{"account_id": "21855714"}` (NOT Decimal). **This test is the canary against the old over-coercion bug.**
4. `loads_decimal('{"price": "0.96"}', legacy=True)` returns `{"price": Decimal("0.96")}` (legacy compat fires + DeprecationWarning).
5. `loads_decimal('{"price": "0.96"}', legacy=False)` returns `{"price": "0.96"}` (no compat, strict behaviour).
6. `loads_decimal('{"id": "1"}')` returns `{"id": "1"}` even with `legacy=True` (length-5 floor protects it).
7. Round-trip: `loads_decimal(dumps_decimal(x)) == x` for `x = {"a": Decimal("0.96"), "b": [Decimal("1.5"), {"c": Decimal("3.14")}]}`.

### Sub-phase 4d — Update tests that asserted old format

Search for tests that hard-coded the old bare-string format:

```bash
grep -rn 'Decimal.*str.*dumps_decimal\|dumps_decimal.*Decimal' tests/
```

Update each to assert against the new marker format. Notable files (verify against `_phase0_prior_patterns.md`):

- `tests/test_decimal_e2e_flow.py`
- `tests/test_b1_core_routing_decimal_log.py`
- `tests/test_b8_reconciliation_sod_signature.py`
- `tests/test_orchestrator_session_budget_init.py`
- `tests/test_d23_d25_decimal_roundtrip.py`

If a test asserts `parsed["price"] == Decimal("0.96")` after `loads_decimal`, it still passes — we only change the WIRE format, not the in-memory return. Most tests should be unaffected.

### Phase 4 verification checklist

- [ ] `python3 -m pytest tests/test_decimal_json_marker.py -v` — all 7 pass.
- [ ] `python3 -m pytest tests/test_decimal_e2e_flow.py -v` — green.
- [ ] `python3 -m pytest tests/test_b1_core_routing_decimal_log.py -v` — green.
- [ ] `python3 -m pytest tests/test_orchestrator_session_budget_init.py -v` — green.
- [ ] DeprecationWarning fires exactly once per process when legacy bare-string is encountered.

### Anti-patterns to refuse in Phase 4

- Do NOT remove the legacy compat path in this phase. It stays for ≥ 1 weekly cycle after deploy.
- Do NOT change `dumps_decimal`'s `default=str` fallback — datetimes still serialise via the stdlib path.
- Do NOT introduce a new "trim whitespace" or "lowercase" coercion in `_coerce_with_marker`. Strings stay byte-for-byte unless they match the explicit marker shape.

---

## Phase 5 — Lint hardening (single subagent)

### Goal

Ensure no future code path can re-introduce the bug class.

### What to add to `scripts/lint_decimal_boundary.py`

Two new checks:

**Check 1: `INSERT INTO p3_*` must use `qexecute`**

```python
# Catches raw cur.execute("INSERT INTO p3_..." or "INSERT INTO p2_..."
# Suppress with `# qexecute: ok` for the unmigrated test sites.
RAW_INSERT_RE = re.compile(
    r"cur\.execute\(\s*[\"\']*\s*[\"\']?\s*(INSERT\s+INTO|UPDATE)\s+p[23]_",
    re.IGNORECASE,
)
QEXECUTE_SUPPRESSION_MARKER = "# qexecute: ok"
```

**Check 2: `dumps_decimal` round-trip must use marker** (post Phase 4)

```python
# Catches the old bare-string Decimal pattern: json.dumps({"price": str(d)})
# Suppress with `# decimal-marker: ok` for legitimate non-Decimal stringification.
BARE_DECIMAL_DUMP_RE = re.compile(
    r"json\.dumps\([^)]*\bstr\s*\(\s*[a-z_][a-z0-9_]*\s*\).*Decimal",
    re.IGNORECASE,
)
```

The lint should print a clear message pointing at the fix:

```
captain-online/.../my_block.py:42: cur.execute("INSERT INTO p3_d05_ewma_states ...
  → use qexecute(cur, sql, params) from shared.questdb_client (auto-coerces
    Decimal to the right Python type for each column). Or suppress with
    `# qexecute: ok` if this is intentional (test fixtures, benchmarks).
```

### Phase 5 verification checklist

- [ ] `python3 scripts/lint_decimal_boundary.py` — 0 violations across the production codebase (post-Phase-3).
- [ ] Add a test: `tests/test_qexecute_lint.py` that creates a temp file with a raw `cur.execute("INSERT INTO p3_d99 ..." )` and asserts the lint flags it.
- [ ] Add a test: `tests/test_qexecute_lint.py` that creates a temp file with `# qexecute: ok` suppression and asserts the lint passes.

### Anti-patterns to refuse in Phase 5

- Do NOT add the lint rule before Phase 3 finishes — it would hard-fail mid-migration.
- Do NOT add a "warning" tier — this is a hard-fail rule. The whole point is making regression impossible.

---

## Phase 6 — Live-DB e2e regression suite (single subagent)

### Goal

Prove that `qexecute` actually works against a live QuestDB for every high-risk DOUBLE / SYMBOL / INT column.

### Tests to add (new file: `tests/test_qexecute_live_roundtrip.py`)

This file requires a live QuestDB (will be skipped on the laptop fast-gate, runs on the tower). Pattern: copy the connection setup from `tests/test_d23_d25_decimal_roundtrip.py`.

For each high-risk column from the audit `§2.2` table, write a test:

| # | Test name | Assertion |
|---|-----------|-----------|
| 1 | `test_d03_aim_modifier_decimal_to_double` | INSERT with `Decimal("0.96")` succeeds; SELECT returns `0.96` |
| 2 | `test_d03_account_id_decimal_to_symbol` | INSERT with `Decimal("21855714")` succeeds; SELECT returns `"21855714"` |
| 3 | `test_d03_session_decimal_to_int` | INSERT with `Decimal("1")` succeeds; SELECT returns `1` |
| 4 | `test_d11_pseudotrader_decimal_to_double` | INSERT with `Decimal("0.42")` for `sharpe_improvement` succeeds |
| 5 | `test_d02_dma_decimal_to_double` | INSERT with `Decimal("0.85")` for `inclusion_probability` succeeds |
| 6 | `test_d05_ewma_decimal_to_double` | INSERT with `Decimal("0.55")` for `win_rate` succeeds |
| 7 | `test_d12_kelly_decimal_to_double` | INSERT with `Decimal("0.05")` for `kelly_full` succeeds |
| 8 | `test_d13_sensitivity_decimal_to_double` | INSERT with `Decimal("0.7")` for `sharpe_stability` succeeds |
| 9 | `test_d22_diagnostic_decimal_to_double` | INSERT with `Decimal("85.0")` for `overall_health` succeeds |
| 10 | `test_d16_silo_decimal_to_double` | INSERT with `Decimal("0.05")` for `max_portfolio_risk_pct` succeeds |
| 11 | `test_qexecute_decimal_to_decimal_unchanged` | INSERT with `Decimal("4523.5")` for D03 `entry_price` (DECIMAL) round-trips losslessly |
| 12 | `test_qexecute_none_preserves_null` | INSERT with `None` for `max_drawdown_limit` writes NULL |

### Plus 1 marker round-trip integration test

`tests/test_decimal_marker_roundtrip_e2e.py`:

- Build a position dict with mixed types (Decimal price, int contracts, str account_id)
- `dumps_decimal` → Redis → `loads_decimal`
- Verify type purity: prices Decimal, contracts int, account_id str
- Pass through `qexecute` to D03
- Verify the row reads back with correct types

### Phase 6 verification checklist

- [ ] `python3 -m pytest tests/test_qexecute_live_roundtrip.py -v` against tower QuestDB — 12 pass.
- [ ] `python3 -m pytest tests/test_decimal_marker_roundtrip_e2e.py -v` — green.

### Anti-patterns to refuse in Phase 6

- Do NOT skip the test if QuestDB is unreachable — `pytest.mark.skipif` with a clear message, not silent skip.
- Do NOT use `time.sleep` to wait for QuestDB — use the existing `wait_for_row` helper at `tests/test_d23_d25_decimal_roundtrip.py`.

---

## Phase 7 — Final verification, commit, dual-remote push (single subagent)

### Goal

Sign off that the bug class is closed. Land all changes on both remotes per `.cursor/rules/captain-deploy-and-tower-discipline.mdc`.

### Run sheet

1. **Full fast-gate test run** (host, no live DB):
   ```bash
   PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
     python3 -B -m pytest tests/ \
     --ignore=tests/test_integration_e2e.py \
     --ignore=tests/test_pipeline_e2e.py \
     --ignore=tests/test_pseudotrader_account.py \
     --ignore=tests/test_offline_feedback.py \
     --ignore=tests/test_stress.py \
     --ignore=tests/test_account_lifecycle.py \
     -v
   ```
   Expected: zero new failures vs. baseline 528 passed / 23 failed.

2. **Lint sweep:**
   ```bash
   python3 scripts/lint_decimal_boundary.py
   ```
   Expected: `decimal-boundary lint: 0 violations`.

3. **Repo-wide smoke check** (must all return zero matches):
   ```bash
   grep -rn 'cur\.execute(\s*"""\?INSERT INTO p[23]_' --include='*.py' \
     captain-online captain-offline captain-command shared scripts
   grep -rn 'cur\.execute(\s*"""\?UPDATE p[23]_' --include='*.py' \
     captain-online captain-offline captain-command shared scripts
   ```

4. **Live tower e2e** (Phase 6 tests against tower QuestDB) — gated on the user running it post-deploy.

5. **Commits.** Group changes into logically coherent commits per phase, NOT one giant commit:
   - `fix(b7): coerce aim_modifier to float for D03 DOUBLE column (Issue 5 hotfix)`
   - `feat(decimal): COLUMN_TYPES auto-derived from canonical_schemas DDL`
   - `feat(decimal): qexecute() typed-INSERT helper at consumer boundary`
   - `refactor(decimal): migrate captain-online INSERTs to qexecute (Phase 3a)`
   - `refactor(decimal): migrate captain-offline INSERTs to qexecute (Phase 3b)`
   - `refactor(decimal): migrate captain-command INSERTs to qexecute (Phase 3c)`
   - `refactor(decimal): migrate shared+scripts INSERTs to qexecute (Phase 3d)`
   - `feat(decimal): structural marker for Decimal in JSON round-trip (Layer B)`
   - `chore(lint): qexecute compliance + decimal marker checks`
   - `test(decimal): live-DB e2e regression suite for qexecute`

6. **Dual-remote push** per the captain-deploy rule:
   ```bash
   git push origin HEAD
   git push multi-user HEAD
   git fetch origin; git fetch multi-user
   # verify both heads match local HEAD
   ```

7. **Update the issue tracker.** Edit `docs2/quick-fixes/NY-Open-May_5th_error_logs/NY_open_errors_2026-05-05.md` to mark Issue 5 ✅ Resolved with a one-line note pointing at this plan.

### Phase 7 verification checklist

- [ ] Fast-gate test count delta ≥ 0 (we add tests, never remove).
- [ ] Lint passes.
- [ ] Both grep smoke checks return zero matches.
- [ ] `git rev-parse HEAD == git rev-parse origin/main == git rev-parse multi-user/main`.
- [ ] Issue 5 marked Resolved in the tracker table.
- [ ] No PII / secrets in any commit message.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| `_INSERT_RE` regex misses an unusual SQL shape | Low | Medium | Phase 0B inventory captures every variant; explicit `columns=` override available |
| Phase 3 mechanical migration introduces subtle logic bug | Low | High | Per-bucket subagent runs existing block tests after migration; diff is `cur.execute(` → `qexecute(cur, ` only |
| Phase 4 Layer B legacy heuristic still over-coerces an edge case | Low | Medium | Length-5 floor + decimal-point requirement excludes account/session IDs; tests assert `"21855714"` stays str |
| `COLUMN_TYPES` parser misses a new DDL added between phases | Very Low | Low | Re-derived at every import; CI test covers every existing DDL |
| Tower has stale `captain:open_positions` Redis state with old format | Medium | Low | Layer B keeps `legacy=True` for ≥ 1 cycle |
| `qexecute` adds latency to hot paths | Very Low | Low | Pure-Python overhead per call: 1 dict lookup + N type checks. Negligible vs. network round-trip |
| Phase 6 live-DB tests fail on tower due to schema drift | Medium | Medium | Phase 6 tests INSERT real values that should pass independently of historical data |

---

## Definition of done — for the entire bug class

The cycle of recurring Decimal errors is closed when **all** of the following hold (re-stated from the audit, made concrete by this plan):

1. ✅ **Layer A (typed-INSERT helper) shipped** — every `INSERT INTO p3_*` and `UPDATE p3_*` site goes through `qexecute`.
2. ✅ **Layer B (structural Decimal markers) shipped** — `loads_decimal` no longer ambiguously coerces numeric strings; explicit marker required.
3. ✅ **Lint gates active** — raw `cur.execute("INSERT INTO p3_…")` and bare-string Decimal-in-JSON patterns both lint-fail.
4. ✅ **Live-DB e2e regression tests pass** — 12+ tests exercising every high-risk DOUBLE/SYMBOL/INT column.
5. ✅ **Both remotes synced** — `git push origin && git push multi-user` confirmed.
6. ⏳ **One full week of live tower opens (NY/LON/APAC) with zero `inconvertible types` errors in any process log.** This is the ultimate validation; tracked in the issue file post-deploy.

---

## What we deliberately are NOT doing

These are out of scope for this plan and explicitly NOT to be touched:

- **Removing the global `register_adapter(Decimal, …)`.** It still handles the DECIMAL-column dispatch inside `qexecute`. Removing it requires 100% migration confidence + a separate decommission cycle. Decision: keep it forever as the inner adapter behind `qexecute`. The global adapter is no longer the threat — the consumer-side miscoercion is, and that's solved by `qexecute`.
- **Removing or rewriting `decimal_boundary.py` helpers (`as_money`, `to_float`, etc.).** Those are the producer-side boundary. Still load-bearing.
- **Touching the existing `_decimal_to_cast_sql` / its (p,s) derivation.** Empirically validated against QuestDB's parser; risky to alter.
- **Rewriting `b3_pseudotrader.py`'s D11 INSERTs to consolidate into one helper.** The 4 INSERTs have different column lists; consolidation is a separate refactor with its own review.
- **Schema changes.** Zero `ALTER TABLE` in this plan.
- **Touching the GUI or TopstepX API path.** Both already cast to float at their boundary (`_make_json_safe` and explicit `float()` in `b3_api_adapter`).

---

## Quick reference — files to be modified

| Phase | New file | Modified file |
|-------|----------|---------------|
| 1 | `tests/test_b7_decimal_double_boundary.py` | `b7_position_monitor.py`, `b7_shadow_monitor.py` |
| 2 | `tests/test_canonical_column_types.py`, `tests/test_qexecute.py` | `shared/canonical_schemas.py`, `shared/questdb_client.py` |
| 3a | — | 10 captain-online files |
| 3b | — | 17 captain-offline files |
| 3c | — | 13 captain-command files |
| 3d | — | `shared/questdb_client.py` (update_d00_fields), `shared/trade_source.py`, ~12 scripts |
| 4 | `tests/test_decimal_json_marker.py` | `shared/decimal_json.py`, possibly 5 existing test files |
| 5 | `tests/test_qexecute_lint.py` | `scripts/lint_decimal_boundary.py` |
| 6 | `tests/test_qexecute_live_roundtrip.py`, `tests/test_decimal_marker_roundtrip_e2e.py` | — |
| 7 | — | `docs2/quick-fixes/NY-Open-May_5th_error_logs/NY_open_errors_2026-05-05.md` |

**Total new files:** 7. **Total modified files:** ~55. **Estimated diff size:** ~1500 LOC additions, ~250 LOC deletions, but ~80% of the diff is the mechanical `cur.execute(` → `qexecute(cur,` rename.

---

## Ready signal

This plan is execution-ready for `/do`. Each phase is self-contained for a fresh subagent context: it cites concrete files, exact line numbers, copy-ready code snippets, verification checklists, and explicit anti-pattern guards. Execute by invoking `/do` against this document.

If anything in this plan is unclear, surface it before Phase 0 starts — re-scoping mid-execution is significantly more expensive than re-scoping now.

*End of remediation plan.*
