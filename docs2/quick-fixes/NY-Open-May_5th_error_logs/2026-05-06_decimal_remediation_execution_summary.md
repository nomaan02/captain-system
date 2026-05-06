# Decimal Boundary Bug Class — Execution Summary

**Date:** 2026-05-06
**Trigger:** NY-Open May 5 Issue 5 — `psycopg2.DatabaseError: inconvertible types: DECIMAL(3,2) -> DOUBLE [from=cast, to=aim_modifier_at_entry]`
**Status:** All code changes landed. Pending: commits, dual-remote push, 1-week tower validation.

---

## What shipped

### Layer A — `qexecute()` typed-INSERT helper

| Component | File | Lines added |
|-----------|------|------------:|
| `COLUMN_TYPES` auto-derived from DDL | `shared/canonical_schemas.py` | +121 |
| `qexecute(cur, sql, params)` | `shared/questdb_client.py` | +148 |
| 134 INSERT sites migrated | 51 production files | mechanical |
| 6 debug sites suppressed | 2 debug scripts | `# qexecute: ok` |

**How it works:** `qexecute` parses the INSERT SQL at runtime, looks up each column's type from `COLUMN_TYPES` (auto-derived from `canonical_schemas.py` DDLs + migrations), and coerces each `Decimal` param to the right Python type before psycopg2 sees it:
- DECIMAL columns → Decimal (unchanged, existing adapter handles it)
- DOUBLE/FLOAT columns → `float(value)`
- SYMBOL/STRING columns → `str(value)`
- INT/LONG columns → `int(value)`
- None → None (preserves NULL)

### Layer B — Structural Decimal markers in JSON

| Component | File | Change |
|-----------|------|--------|
| Marker emission | `shared/decimal_json.py` | `Decimal("0.96")` → `{"__type__":"Decimal","value":"0.96"}` |
| Marker recognition | `shared/decimal_json.py` | Only marker dicts become Decimal; numeric-looking strings stay str |
| Backwards-compat | `loads_decimal(legacy=True)` | Coerces strings with '.' AND len≥5 during deploy window |

**What this fixes:** `loads_decimal._coerce` no longer converts `"21855714"` (account_id) or `"1"` (session_id) to Decimal. The prior aggressive coercion was the upstream source of the SYMBOL/INT crash incidents.

### Phase 1 hotfix — direct Issue 5 closure

| Site | File | Fix |
|------|------|-----|
| `aim_modifier_at_entry` (DOUBLE) | `b7_position_monitor.py:_write_trade_outcome` | `to_float(aim_modifier, default=1.0)` |
| Shadow monitor mirror | `b7_shadow_monitor.py:_resolve_shadow` | Same `to_float` coercion |
| D16 DOUBLE columns | `b7_position_monitor.py:_update_capital_and_cb` | `to_float(d16_row[6/7/8])` |

### Lint enforcement

| Check | Enforcement |
|-------|-------------|
| Raw `cur.execute("INSERT INTO p3_*")` | Hard-fail; suppression via `# qexecute: ok` |
| `r[N] or 0.0` falsy-zero (existing) | Hard-fail; suppression via `# decimal-boundary: ok` |
| No-op ternary (existing) | Hard-fail |

---

## Test coverage added

| Test file | Tests | Scope |
|-----------|------:|-------|
| `test_b7_decimal_double_boundary.py` | 4 | Phase 1 hotfix regression |
| `test_canonical_column_types.py` | 22 | COLUMN_TYPES auto-derivation |
| `test_qexecute.py` | 12 | qexecute coercion paths |
| `test_decimal_json_marker.py` | 21 | JSON marker round-trip |
| `test_qexecute_lint.py` | 10 | Lint meta-tests |
| **Total new** | **69** | |

Plus 74 existing tests confirmed green (zero regression).

---

## Files changed summary

| Category | Files | Description |
|----------|------:|-------------|
| New shared infra | 2 | `canonical_schemas.py` (+COLUMN_TYPES), `questdb_client.py` (+qexecute) |
| JSON rewrite | 1 | `decimal_json.py` (marker format) |
| B7 hotfix | 2 | `b7_position_monitor.py`, `b7_shadow_monitor.py` |
| INSERT migration (online) | 9 | Mechanical `cur.execute(` → `qexecute(cur,` |
| INSERT migration (offline) | 19 | Same |
| INSERT migration (command) | 12 | Same |
| INSERT migration (shared+scripts) | 19 | Same + 3 f-string `columns=` overrides |
| Lint extension | 1 | `lint_decimal_boundary.py` |
| New test files | 5 | 69 new tests |
| Test fixtures updated | 8 | `# qexecute: ok` markers for legitimate raw-INSERT test fixtures |
| Phase 0 docs | 3 | Discovery deliverables (module summaries, INSERT inventory, prior patterns) |

---

## What's NOT in scope (intentionally left unchanged)

- Global `register_adapter(Decimal, …)` — still load-bearing inside `qexecute` for DECIMAL columns
- `shared/decimal_boundary.py` helpers — still load-bearing for producer-side coercion
- Schema changes — zero `ALTER TABLE`
- GUI / TopstepX API path — already correct at their boundaries
- `cur.executemany` in `scripts/restore_live_delta.py` — different API shape; follow-up if needed
- `version_snapshot._restore_state` dynamic f-string INSERT — uses runtime table names, not in canonical schemas

---

## Known follow-ups

1. **`legacy=False` cutover** — after 1 weekly cycle with zero DeprecationWarning in tower logs, set `legacy=False` in `loads_decimal` callers to fully close the bare-string coercion path.
2. **`executemany` sites** — `scripts/restore_live_delta.py` uses `cur.executemany` for 4 tables; not covered by `qexecute`. Low risk (seed script, not hot path).
3. **Tower live validation** — 1 full week of NY/LON/APAC opens with zero `inconvertible types` errors in any process log.

---

## Verification evidence

```
decimal-boundary lint: 0 violations
74 passed (Phase 1-4 regression panel)
10 passed (qexecute lint meta-tests)
21 passed (JSON marker tests)
0 raw cur.execute INSERT INTO p[23]_ in production code
134 qexecute() call sites across 51 files
6 suppressed debug-only sites
```
