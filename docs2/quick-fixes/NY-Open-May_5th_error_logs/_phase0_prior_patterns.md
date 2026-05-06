# Phase 0C — Prior patterns (read-only synthesis)

## 1. The 5-incident timeline — verified

Cross-checked against `2026-05-06_issue5_decimal_double_root_cause_audit.md` §1.4 (lines 104–114), `docs2/context/tracking_context.md` (lines 262–287, 18–24), and test/doc datelines.

| # | Audit table | Verification |
|---|-------------|--------------|
| 1 | 2026-04-29 — `b4_kelly_sizing` — Decimal − float | Consistent with sibling docs (`EXECUTION_SUMMARY.md` line 3 references `4c225c0`; `test_b7_position_monitor_decimal_boundary.py` lines 15–17). |
| 2 | 2026-04-30 — `b6_signal_output._build_per_account` | Consistent (`test_b6_decimal_d08_boundary.py` lines 3–13; `EXECUTION_SUMMARY.md` lines 47–48). |
| 3 | 2026-04-30 — `b7_position_monitor` Bug C (`<` with float) | Consistent (`test_b7_position_monitor_decimal_boundary.py` lines 1–18 cites 2026-04-30 09:44 ET). |
| 4 | ~2026-05-02 — `account_id` SYMBOL / `DECIMAL -> SYMBOL` | **Correct shape; date should be anchored to primary log, not "~05-02".** `tracking_context.md` documents **"2026-05-01 15:10 BST"** and the **D03 writeback** crash (lines 262–287). Use **2026-05-01** rather than "~2026-05-02". |
| 5 | 2026-05-05 — `aim_modifier_at_entry` DOUBLE | Consistent with audit §1 and `2026-05-06_decimal_remediation_plan.md` header (lines 5–6). |

**Conclusion:** Sequence and **sites/shapes** in §1.4 match the corpus; only **incident 4's date** is looser in the audit than in `tracking_context.md`.

## 2. What's already shipped (`EXECUTION_SUMMARY.md` commits)

| Commit | What shipped | Tests / gates named there | Still in scope for May-06 plan |
|--------|--------------|---------------------------|---------------------------------|
| `03de644` | OR tracker `WAITING` expiry | (prerequisite, not decimal suite) | Out of decimal remediation |
| `1910f71` | `shared/decimal_boundary.py`, B6/B1/orchestrator monetary coercion, `parse_json_decimal` on D08 JSON money | `test_decimal_boundary.py`, `test_b6_decimal_d08_boundary.py`, live purity tests | Producer-side only; does not fix DOUBLE/SYMBOL INSERT casting |
| `9659b4c` | Consolidated aliases, B8 reconciliation + CRITICAL path, B4 fee JSON, offline TSM sim, B6 reports | `test_reconciliation_decimal_boundary.py`, `test_tsm_simulation_decimal_input.py`, `test_kelly_fee_schedule_decimal.py` | Same gap as above |
| `5681fb6` | Replay / pseudotrader / scripts `to_float` discipline | (no new files listed) | Same |
| `dbe550b` | `scripts/lint_decimal_boundary.py` + `test_decimal_boundary_lint.py`, doc updates | Lint + pytest wrapper | Lint still misses non-DECIMAL write targets |

## 3. What's missing — gap this plan closes

**Prior work** focused on **DECIMAL column hygiene**, **falsy-zero**, **explicit `to_float`**, **`dumps_decimal` / `parse_json_decimal` for money in JSON**, and **lint** for `r[N] or 0.0` and no-op ternaries.

**Missed bug class** (`2026-05-06_issue5…` lines 12–16, 89–100): **`Decimal` parameters bound for QuestDB columns that are DOUBLE / SYMBOL / INT**, driven by **global `register_adapter(Decimal, …)`** plus **`loads_decimal._coerce`** turning numeric strings into `Decimal`.

**Audit overconfidence:** `EXHAUSTIVE_AUDIT_REPORT.md` claims **"PASS — zero new TypeError vulnerabilities"** (line 7), **"No unhandled TypeError risk"** at any boundary (lines 240–241), and **"100% confident"** (line 244). The May-01/05 incidents were **`psycopg2.DatabaseError`**, not `TypeError`, and the **`_handle_taken_skipped` "SAFE"** classification did not consider **non-DECIMAL INSERT targets**. The April-30 audit was **accurate for the four in-memory sister bugs** but **wrong to imply no new decimal-related production crashes** from Redis/QuestDB typing.

`2026-05-06_decimal_remediation_plan.md` (lines 22–23, 34–36) matches this gap: add **consumer-side `qexecute`**, **JSON marker / `loads_decimal` fix**, **typed-INSERT lint**, **live e2e**.

## 4. Tower test ritual (Phase 7) — fish, distilled

**Lint sweep**

```fish
cd ~/captain-system
python3 scripts/lint_decimal_boundary.py
python -B -m pytest tests/test_decimal_boundary_lint.py -v
```

**Fast static gate (host venv, no live QuestDB requirement)**

```fish
cd ~/captain-system
source .venv/bin/activate.fish
set -gx PYTHONPATH $PWD $PWD/captain-online $PWD/captain-offline $PWD/captain-command
set -gx QUESTDB_HOST 127.0.0.1
set -gx QUESTDB_PORT 8812
set -gx QUESTDB_USER (grep '^QUESTDB_USER=' .env | cut -d= -f2)
set -gx QUESTDB_PASSWORD (grep '^QUESTDB_PASSWORD=' .env | cut -d= -f2)

python -B -m pytest \
    tests/test_decimal_boundary.py \
    tests/test_decimal_boundary_lint.py \
    tests/test_b6_decimal_d08_boundary.py \
    tests/test_b7_position_monitor_decimal_boundary.py \
    tests/test_reconciliation_decimal_boundary.py \
    tests/test_tsm_simulation_decimal_input.py \
    tests/test_kelly_fee_schedule_decimal.py \
    tests/test_decimal_e2e_flow.py \
    tests/test_b4_kelly.py \
    tests/test_b5c_circuit.py \
    tests/test_b7_pnl_per_symbol.py \
    -v
```

**Live-QuestDB producer purity (tower)**

```fish
python -B -m pytest \
    tests/test_tsm_config_type_purity.py \
    tests/test_user_silo_type_purity.py \
    tests/test_active_assets_type_purity.py \
    -v
```

**Live pipeline dry run (container)**

```fish
for s in 1 2 3
    echo "=== Session $s (1=NY, 2=LON, 3=APAC) ==="
    dco exec -T -e PYTHONPATH=/app captain-online \
        python -u /app/dry_run_phase_a.py $s
    echo ""
end
```

**Dual-remote push verification (per `.cursor/rules/captain-deploy-and-tower-discipline.mdc`)**

After push, run `git fetch origin` and `git fetch multi-user`, then confirm `git rev-parse HEAD` equals both `origin/main` and `multi-user/main`.

## 5. Phase 4 (JSON marker rewrite) — test file impact

Legend: **MUST** = depends on bare-string Decimal wire form or exact `dumps_decimal`/`loads_decimal` semantics; **May** = uses them for fixtures/assertions indirectly; **No** = in-memory / SQL-only / no JSON round-trip.

| File | Scope | `dumps_decimal` / `loads_decimal` | Phase 4 |
|------|-------|-----------------------------------|---------|
| `tests/test_decimal_boundary.py` | `decimal_boundary` helpers | No | No |
| `tests/test_decimal_boundary_lint.py` | CI wrapper for lint script | No | No |
| `tests/test_decimal_e2e_flow.py` | Full mocked Redis hop + B6/B7/offline | Yes — `test_dumps_decimal_handles_full_outcome_dict` | 🟠 May |
| `tests/test_b1_core_routing_decimal_log.py` | D17 log INSERT JSON | Yes — `loads_decimal` on `details` | 🟠 May |
| `tests/test_b6_decimal_d08_boundary.py` | `_build_per_account` D08 Decimal | No | 🟢 No |
| `tests/test_b7_position_monitor_decimal_boundary.py` | Bug C monitor loop | No | 🟢 No |
| `tests/test_d23_d25_decimal_roundtrip.py` | Live D23/D25 DECIMAL columns | No | 🟢 No |
| `tests/test_d08_decimal_roundtrip.py` | Live D08 DECIMAL columns | No | 🟢 No |
| `tests/test_phase_c_decimal_roundtrip.py` | Live D16/D00/D30 DECIMAL | No | 🟢 No |
| `tests/test_d03_pnl_sum_precision.py` | `SUM(pnl)` precision | No | 🟢 No |
| `tests/test_kelly_fee_schedule_decimal.py` | Fee schedule via `dumps_decimal` in TSM dict | Yes | 🟠 May |
| `tests/test_orchestrator_session_budget_init.py` | `MockCursor` + session budget | Yes — `_make_d08_row` uses `dumps_decimal` | 🟠 May |
| `tests/test_reconciliation_decimal_boundary.py` | Reconciliation mismatch | No | 🟢 No |
| `tests/test_tsm_simulation_decimal_input.py` | Offline TSM sim Decimal config | No | 🟢 No |
| `tests/test_decimal_json.py` | Core JSON round-trip contract | Yes throughout | 🔴 **MUST update** |
| `tests/test_d03_redis_roundtrip.py` | Redis stream + `loads_decimal` | Yes | 🟠 May |
| `tests/test_circuit_breaker_decimal.py` | L1 halt with `topstep_state` JSON | Yes | 🟠 May |
| `tests/test_topstep_state_json_roundtrip.py` | `topstep_state` money in JSON | Yes | 🔴 **MUST update** |
| `tests/test_phase_c_capital_history_json_roundtrip.py` | `capital_history` list JSON | Yes | 🔴 **MUST update** |
| `tests/test_d03_reconciliation_precision.py` | `RealisedOutcome` arithmetic | No | 🟢 No |

## 6. Existing test conventions to copy (Phase 6)

- **`MockCursor` pattern** — `tests/test_orchestrator_session_budget_init.py` lines 19–54: `inserts` list, `execute` routes INSERT vs SELECT via substring match, `fetchone`/`fetchall` from last matched SELECT rows.
- **Live QuestDB setup** — `tests/test_d23_d25_decimal_roundtrip.py` lines 1–43: `pytestmark = pytest.mark.real_questdb`, `_skip_if_no_questdb()` with `get_cursor()` probe, `INSERT` + `wait_for_row`, `Decimal(str(row[0]))` assertion.
- **`wait_for_row`** — `tests/_qdb_helpers.py` lines 25–62: signature `(cur, sql, params=None, *, max_wait=2.0, interval=0.05)`; returns first `fetchone()` or `None` at timeout.
- **Skipif / marks** — `real_questdb` pytest mark + operational skip inside tests.

## 7. Confidence note + open questions

**Contradictions**

1. **`EXHAUSTIVE_AUDIT_REPORT.md` lines 7, 238–244** vs production `DatabaseError` on SYMBOL/DOUBLE — different exception type; audit scoped to TypeError + four shapes only.
2. **Incident 4 date:** `issue5` §1.4 "~2026-05-02" vs `tracking_context.md` line 262 "2026-05-01 15:10 BST".
3. **Tower SHA checks:** `TOWER_VALIDATION_RUNBOOK_FINAL.md` §7 vs **dual-remote mandatory verification** in tower-discipline rule (only the rule enforces `origin` + `multi-user` identity).
4. **`EXECUTION_SUMMARY.md` "5 commits"** includes `03de644` non-decimal OR fix; "decimal Phases 1–4" are really **four** decimal commits if OR is excluded.

**Files read partially:** `MONETARY_DECIMAL_MIGRATION_PLAN.md` (first 150 lines), `TOWER_VALIDATION_RUNBOOK_FINAL.md` / `TOWER_TEST_RUNBOOK.md` (sections 1–2, 5–7 / 2, 4–6), `2026-05-06_decimal_remediation_plan.md` (first ~250 lines).

**Conclusion:** Timeline sites/shapes consistent; incident 4 date should follow `tracking_context.md:262`. EXHAUSTIVE claims narrowly true for TypeError but missed the SQL cast class.
