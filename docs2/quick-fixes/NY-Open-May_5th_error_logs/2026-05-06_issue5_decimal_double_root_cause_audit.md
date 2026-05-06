# Issue 5 — Decimal → DOUBLE Conversion Audit & Remediation Plan

**Date:** 2026-05-06
**Audit author:** Cursor agent (Opus 4.7) for Nomaan
**Trigger:** NY-Open 2026-05-05 — `psycopg2.DatabaseError: inconvertible types: DECIMAL(3,2) -> DOUBLE [from=cast, to=aim_modifier_at_entry]` in `b7_position_monitor._write_trade_outcome`
**Status:** READ-ONLY audit. No code changes have been made. This document IS the plan; execution is gated on Nomaan's approval.

---

## TL;DR

The 2026-04-30 `EXHAUSTIVE_AUDIT_REPORT.md` claimed "100% confidence — zero TypeError vulnerabilities" but **only audited the four sister-bug shapes that had already crashed by then** (Decimal/float arithmetic, falsy-zero collapse, Decimal-vs-float comparisons, in-memory dict type drift).

It missed an entire **fifth class of bug**: **type-coerced Decimals being SQL-rendered for non-DECIMAL columns**. The May 5 incident is a fresh crash in this fifth class. The pattern recurred because the existing safety nets (`decimal_boundary` helpers, lint script, e2e flow test) were all designed around DECIMAL columns and ignore DOUBLE / SYMBOL / INT destinations.

The root cause is **structural, not point-local** — a global `psycopg2.extensions.register_adapter(Decimal, …)` in `shared/questdb_client.py:62-65` which **unconditionally** renders any Python `Decimal` as `cast('<v>' as DECIMAL(p,s))`, even when the destination column is DOUBLE / SYMBOL / INT. Combined with `shared/decimal_json.loads_decimal._coerce` (which **aggressively** coerces every numeric-looking JSON string to Decimal), any value flowing through the Redis-backed position lifecycle picks up Decimal type and the downstream INSERT crashes.

This document:

1. Diagnoses the exact failure path for Issue 5.
2. Enumerates **every other DOUBLE / SYMBOL / INT column write site** that is structurally vulnerable to the same crash (≥35 columns across ≥20 tables).
3. Proposes a phased, structural fix that closes the bug class once and for all — not just the May 5 site.

---

## 1. Root cause — exact path of the May 5 crash

### 1.1 The smoking gun

`shared/questdb_client.py` lines 62–65 install a process-wide psycopg2 adapter:

```62:65:shared/questdb_client.py
psycopg2.extensions.register_adapter(
    Decimal,
    lambda d: psycopg2.extensions.AsIs(_decimal_to_cast_sql(d)),
)
```

`_decimal_to_cast_sql` derives `(precision, scale)` from the Decimal's own digit count and emits `cast('<v>' as DECIMAL(<p>, <s>))`. **It has no knowledge of the destination column type** — it cannot, because Python-side adapters don't see the SQL column metadata. So **every** `Decimal` passed to `cur.execute()` becomes a `DECIMAL(p,s)` literal in the wire SQL.

QuestDB allows `DECIMAL(p1,s1) -> DECIMAL(p2,s2)` widening and narrowing on assignment, so this works for the (large) DECIMAL-column population the adapter was designed for. But **QuestDB does NOT allow `DECIMAL(p,s) -> DOUBLE`, `DECIMAL(p,s) -> SYMBOL`, or `DECIMAL(p,s) -> INT`** assignment casts. Hence the crash.

### 1.2 The Decimal injection point upstream

`b7_position_monitor._write_trade_outcome` receives `aim_modifier` from line 410:

```405:413:captain-online/captain_online/blocks/b7_position_monitor.py
        outcome=outcome,
        entry_time=pos.get("entry_time"),
        regime_at_entry=pos.get("regime_state"),
        aim_modifier=pos.get("combined_modifier"),
        aim_breakdown=pos.get("aim_breakdown"),
        session=pos.get("session"),
        tsm_used=pos.get("tsm_id"),
```

`pos["combined_modifier"]` is set in the open-positions Redis hash by `captain-online/.../orchestrator._handle_taken_skipped` at line 1188:

```1185:1191:captain-online/captain_online/blocks/orchestrator.py
                "account": data.get("account_id"),
                "session": data.get("session"),
                "regime_state": data.get("regime_state"),
                "combined_modifier": data.get("combined_modifier"),
                "aim_breakdown": data.get("aim_breakdown"),
                "tsm_id": data.get("tsm_id"),
                "entry_time": datetime.now(_ET),
```

`data` is the deserialised STREAM_COMMANDS Redis message, parsed by `loads_decimal`. `loads_decimal._coerce` aggressively converts **every numeric-looking string** to `Decimal`:

```47:57:shared/decimal_json.py
    def _coerce(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _coerce(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_coerce(v) for v in obj]
        if isinstance(obj, str):
            try:
                return Decimal(obj)
            except InvalidOperation:
                return obj
        return obj
```

So `"combined_modifier": "0.96"` in the JSON becomes `Decimal("0.96")` in the Python dict, propagates into `open_positions[i]["combined_modifier"]`, gets serialised back to Redis via `dumps_decimal`, deserialised again on the next process restart — and persists as Decimal forever.

Then `_write_trade_outcome` line 555 passes `aim_modifier` (which is `Decimal("0.96")`) into `cur.execute(...)`. The global adapter renders it as `cast('0.96' as DECIMAL(3,2))`. The destination column `aim_modifier_at_entry` is **DOUBLE** (per `shared/canonical_schemas.py:424` and `MONETARY_DECIMAL_MIGRATION_PLAN.md` §B.2 which deliberately kept it DOUBLE per Isaac's spec). QuestDB rejects the assignment.

### 1.3 Why the previous audit missed it

The April 30 `EXHAUSTIVE_AUDIT_REPORT.md` audited 7 surfaces (DECIMAL readers, Redis stream consumers, in-memory dicts, TopstepX serialisation, GUI JSON, D17 logs, Decimal-vs-float-literal comparisons). Crucially, **none** of those surfaces include "Decimal-typed Python values being written to non-DECIMAL columns."

The lint script (`scripts/lint_decimal_boundary.py`) catches:
- The `r[N] or 0.0` falsy-zero collapse
- The `float(x) if not isinstance(x, T) else float(x)` no-op ternary

…but **does not** catch:
- A `Decimal`-typed argument flowing into `cur.execute(... %s ...)` where the corresponding column is DOUBLE / SYMBOL / INT

The April 30 e2e flow test (`tests/test_decimal_e2e_flow.py`) exercises the **happy path** with mocked `cur.execute()` — it never executes against a live QuestDB DOUBLE column, so it cannot catch this crash either.

### 1.4 The recurring pattern

This is the **fifth** Decimal-class bug in the past 2 weeks (history reconstructed from `docs2/quick-fixes/`, `docs2/context/tracking_context.md`, and claude-mem observations #2207, #2208, #2210):

| Date | Site | Shape | Fix |
|------|------|-------|-----|
| 2026-04-29 | `b4_kelly_sizing` | Decimal − float TypeError | Per-site `_money_d` coercion |
| 2026-04-30 | `b6_signal_output._build_per_account` | Decimal − float TypeError | `as_money` boundary helpers |
| 2026-04-30 | `b7_position_monitor.monitor_positions` (Bug C) | Decimal `<` float TypeError on tp/sl proximity | Top-of-loop coercion |
| ~2026-05-02 | B7 INSERT — `account_id` SYMBOL | `cast('21855714' as DECIMAL(8,0)) -> SYMBOL` | Local `str(account_id)` cast at consumer |
| **2026-05-05** | **B7 INSERT — `aim_modifier_at_entry` DOUBLE** | **`cast('0.96' as DECIMAL(3,2)) -> DOUBLE`** | **(this audit)** |

Each fix was point-local. The structural cause — global adapter + over-eager `loads_decimal` — was never addressed, so the bug keeps surfacing on a different column every market open.

---

## 2. Comprehensive risk inventory — every site that could repeat the May 5 crash

### 2.1 Inputs

A site is "at risk" when **both** of these are true:
- It calls `cur.execute("INSERT INTO ... %s ...", (..., x, ...))` where the column for `x` is **DOUBLE, SYMBOL, INT, or LONG** (not DECIMAL).
- `x` could plausibly be a `Decimal` because **at least one** of these is true:
  1. It came from `loads_decimal` / `parse_json_decimal` (Redis or D08 JSON STRING column).
  2. It was assigned from a value of type `Decimal | float`, e.g. `pos.get("combined_modifier")` where the dict was rebuilt via `loads_decimal`.
  3. It is the result of arithmetic where one operand is `Decimal`.
  4. It is the output of one of the `decimal_boundary` helpers (`as_money`, `as_money_or_none`).

### 2.2 DOUBLE-column inventory (35 columns across 20 tables)

Source: `shared/canonical_schemas.py`. Columns listed below are typed `DOUBLE` (or `FLOAT` in legacy). Risk column "🔴 high / 🟠 med / 🟢 low" reflects whether a Decimal could plausibly leak in today.

| Table | DOUBLE columns | Writers | Risk |
|-------|----------------|---------|------|
| D00 | `warm_up_progress` | `bootstrap_production.py`, `update_d00_fields` | 🟢 (literal float) |
| D01 | `warmup_progress`, `missing_data_rate_30d` | `b1_drift_detection`, `bootstrap` | 🟢 (literal/float) |
| D02 | `inclusion_probability`, `recent_effectiveness` | `b1_dma_update`, `b1_hdwm_diversity`, `b1_drift_detection`, `bootstrap_production` | 🟠 (DMA arithmetic) |
| **D03** | **`aim_modifier_at_entry`** | **`b7_position_monitor._write_trade_outcome`** ← FAILED 2026-05-05 | **🔴 (Decimal from Redis)** |
| D04 | `bocpd_cp_probability`, `cusum_c_up_prev`, `cusum_c_down_prev`, `cusum_allowance`, `current_changepoint_probability` | `b2_bocpd`, `b2_cusum`, `b1_drift_detection` | 🟢 (explicit `float()` casts at INSERT) |
| D05 | `win_rate`, `avg_win`, `avg_loss` | `b8_kelly_update._save_ewma`, `bootstrap` | 🟠 (downstream `_load_ewma` coerces, but EWMA writer does NOT) |
| D06 | `expected_new`, `expected_current`, `pbo`, `dsr` | `b4_injection` | 🟠 (`pseudo_results` dict via `dumps_decimal` round-trip) |
| D07_regime | `pettersson_threshold`, `cv_score` | (research output, manual seed) | 🟢 |
| D08 | `margin_buffer_pct`, `pass_probability` | `b8_reconciliation` (3 INSERT sites), bootstrap scripts | 🟠 (D08 JSON columns deserialised via `parse_json_decimal`) |
| D11 | `sharpe_baseline`, `sharpe_updated`, `sharpe_improvement`, `drawdown_change`, `winrate_delta`, `pbo`, `dsr` | `b3_pseudotrader` (4 INSERT sites) | 🟠 (computed from D03 reads which are Decimal) |
| D12 | `kelly_full`, `shrinkage_factor` | `b8_kelly_update` (2 sites), `b2_level_escalation` | 🟠 (Kelly compute uses `to_float` but drift could regress) |
| D13 | `sharpe_stability`, `pbo`, `dsr`, `adjusted_sharpe` | `b5_sensitivity` | 🟠 |
| D14 | `latency_ms` | `b3_api_adapter` (2 sites) | 🟢 (int from network timer) |
| D16 | `max_portfolio_risk_pct`, `correlation_threshold`, `user_kelly_ceiling` | `b7_position_monitor._update_capital_and_cb`, `bootstrap_production` | 🔴 (`_update_capital_and_cb` does **`d16_row[6]`** raw passthrough — if upstream `_load_user_silo` were to switch to `as_money` for these fields, the INSERT would crash) |
| D22 | `overall_health` | `b9_diagnostic` | 🟠 (computed from D03 Decimal reads) |
| D25 | `r_bar`, `beta_b`, `sigma`, `rho_bar`, `p_value` | `bootstrap_production`, `b8_cb_params` (offline) | 🟠 (CB params arithmetic on Decimal pnl values) |
| D29 | `or_range_first_m_min` | bootstrap, `b1_features` | 🟢 |
| D31 | `atm_iv_30d`, `realized_vol_20d`, `vrp` | bootstrap | 🟢 |
| D32 | `cboe_skew`, `skew_spread_proxy` | bootstrap | 🟢 |
| D33 | `opening_range_pct`, `opening_vol_z` | `b1_features` | 🟠 (computed from D30 OHLC which IS Decimal post-Phase B) |
| `p3_spread_history` | `spread` | bootstrap path | 🟢 |

### 2.3 SYMBOL-column inventory — already-burnt sites that could re-crash

`loads_decimal._coerce` will Decimal-wrap any all-digits string. The known SYMBOL columns at risk:

| Column | Tables | Past incident | Current state |
|--------|--------|---------------|---------------|
| `account_id` | D03, D08, D14, D16, D19, D23, D25, D28 | YES — fixed point-by-point in B7 with `str(account_id)` | **NOT systemic** — every other `account_id` INSERT site assumes upstream did its job |
| `user_id` | D03, D08, D09, D10, D15, D16, D19 | None known, but `"primary_user"` has letters so `_coerce` skips it | LATENT |
| `asset_id` / `asset` | D00, D01, D02, D04, D05, D06, D11, D29, D30, D31, D32 | None — symbols always have letters | safe |
| `injection_id`, `recon_id` etc. | various | None — UUID prefixed | safe |

### 2.4 INT-column inventory — DECIMAL → INT casts also rejected

Same shape: any Decimal flowing into an INT column will crash. Known sites:

| Column | Tables | Risk |
|--------|--------|------|
| `session_id`, `session` | D03, D23 | 🟠 (orchestrator wraps in `int(session_id)` at one site, but not all) |
| `direction` | D03 | 🟢 (`coerce_json_int=False` is used in stream loaders) |
| `contracts` | D03 | 🟠 (`int()` at most consumers, but `pos["contracts"]` from Redis hash could regress) |
| `model_m` | D03 | 🟠 (`_get_locked_m` returns int, but the lookup chain is fragile) |
| `n_observations`, `cusum_sprint_length`, `n_trades`, `payouts_taken`, `or_minutes`, `transition_days`, `tracking_days`, `current_day`, `total_days`, `max_contracts`, `scaling_tier_micros`, `max_simultaneous_positions` | various | 🟢 (literal/computed int) |

### 2.5 STRING-with-JSON inventory — silent precision loss path

Any STRING column that holds JSON-serialised dicts of Decimals must use `dumps_decimal` (not stdlib `json.dumps`). Sites:

- `aim_breakdown_at_entry` (D03) — uses `dumps_decimal` ✓
- `topstep_state`, `topstep_params`, `payout_rules`, `fee_schedule`, `instrument_permissions` (D08) — uses `dumps_decimal` ✓
- `l_b` (D23) — uses `dumps_decimal` ✓
- `aim_breakdown` / `pseudo_results` (D04, D06, D11) — uses `dumps_decimal` ✓
- `mismatches` (D19), `details` (D21, D28) — uses stdlib `json.dumps` ⚠️ — but only stores summary strings/floats, not Decimals → low risk
- D26 HMM `hmm_params`, `current_state_probs`, `opportunity_weights`, `prior_alpha` — uses stdlib `json.dumps` ⚠️ — depends on whether HMM internals ever return Decimal

---

## 3. Why each previous "complete fix" failed to stop the cycle

| Fix | Coverage | What it missed |
|-----|----------|----------------|
| `shared/decimal_boundary.py` (`as_money`, `as_money_or_none`, `to_float`) | **Producer side** — coerces values OUT of QuestDB into Python | Does NOT enforce the **consumer side** (Python → QuestDB). A Decimal in Python flowing back into a DOUBLE column has no boundary. |
| `scripts/lint_decimal_boundary.py` | Catches `r[N] or 0.0` and no-op ternaries | Lexical only. Cannot see across function boundaries. Cannot tell that `pos.get("combined_modifier")` is a Decimal. |
| `tests/test_decimal_e2e_flow.py` | Validates the happy-path Decimal flow with mocked cursors | Mocks `cur.execute()` — never round-trips to a live DOUBLE column. |
| Per-site fix at `_write_trade_outcome` lines 533–539 | Coerces 7 monetary fields | Forgot `aim_modifier`. Was incomplete — explicitly listed only DECIMAL-target fields. |
| Per-site fix at B7 for `account_id` SYMBOL | Wraps in `str(...)` at one INSERT call | Doesn't generalise. Every new INSERT site has to remember the same trick. |

---

## 4. Proposed structural fix — three layers, in priority order

> **Goal:** Eliminate the bug class so that **no future Decimal value can crash an INSERT into a non-DECIMAL column**, regardless of which block adds the INSERT or which dict the value came from.

> **Constraint:** Zero precision loss for monetary columns. The DECIMAL-column write path must continue to use `_decimal_to_cast_sql` exactly as today — that path is correct and load-bearing.

### Layer A — Consumer-boundary coercion at `cur.execute()` time (PRIMARY FIX)

Introduce a thin **typed-INSERT helper** in `shared/questdb_client.py` that knows the schema and coerces each parameter to the column's type *before* psycopg2 sees it:

```python
# Sketch — actual implementation will live in shared/questdb_client.py.
# Builds on the existing canonical_schemas.py that already names every column.

def execute_typed(cur, sql: str, params: tuple, *, table: str, columns: list[str]) -> None:
    """psycopg2 cur.execute() wrapper that coerces each param to its column's type.

    For each (col, val) pair, looks up the column's schema type from
    shared.canonical_schemas and applies the right coercion:

    - DECIMAL(p,s)   → no-op (the global adapter still wraps as DECIMAL literal)
    - DOUBLE / FLOAT → float(val) if Decimal else val
    - SYMBOL         → str(val)
    - INT / LONG     → int(val)
    - BOOLEAN        → bool(val)
    - STRING         → str(val) if Decimal else val   # last-ditch defensive
    - TIMESTAMP      → val.isoformat() if datetime else val
    """
```

The helper:

1. Reads column types from a single source of truth (`shared/canonical_schemas.py` already names every column; we just add a parallel type dict).
2. Coerces each parameter at the wire boundary based on its destination column type.
3. Crashes loudly if the column name isn't recognised (so a typo doesn't silently bypass coercion).

**Migration path:** every `cur.execute("INSERT INTO p3_d... ", params)` site is mechanically converted to `execute_typed(cur, sql, params, table="p3_d03_trade_outcome_log", columns=[...])`. The column list is right next to the SQL — typing it is a one-time cost, but it is also a per-site spec checkpoint. Concretely there are ~50 INSERT sites repo-wide; one PR can convert all of them.

**Why this is the elegant fix:**
- One choke point, not one fix per call site.
- Future Decimal injections (e.g. a new block reading from a Decimal-bearing dict) automatically get the right coercion at write time.
- The schema mapping is already there in `canonical_schemas.py` — we just add a column-type dict next to the DDL strings.
- Backwards-compatible: the global Decimal adapter remains for sites that don't migrate yet.

### Layer B — Tighten `loads_decimal._coerce` (SECONDARY DEFENSIVE FIX)

Change `shared/decimal_json.py:loads_decimal` to **stop coercing all-numeric strings to Decimal**. Two design options, in order of preference:

**Option B1 (recommended):** Use a structural marker. When `dumps_decimal` serialises a Decimal, wrap it as `{"__type__": "Decimal", "value": "0.96"}` instead of a bare string. `loads_decimal` then ONLY rebuilds Decimals from that marker. Rest of the JSON stays as native types (int, float, str). This eliminates the "Is `'21855714'` an account ID or a price?" ambiguity once and forever.

**Option B2 (minimal-impact):** Whitelist specific monetary keys. `loads_decimal` accepts a `decimal_keys: set[str]` argument; only those keys get string→Decimal coercion. Default to a global list mirroring `MONETARY_COLUMN_NAMES` from the lint script. Other keys retain their JSON-native types.

**Trade-off:** B1 changes the Redis wire format and requires a coordinated tower restart with empty `captain:open_positions` hash. B2 is a one-line change but the whitelist is a maintenance burden. **Recommend B1** because the marker is canonical and self-documenting.

### Layer C — Lint and test gates (TERTIARY REGRESSION SHIELD)

Extend `scripts/lint_decimal_boundary.py` with a new check:

> **`INSERT INTO p3_d... cur.execute(...)` calls MUST go through `execute_typed` (or be on a hand-curated allowlist of pre-Phase-A INSERTs that are still mid-migration).**

The lint becomes the contract that prevents new INSERT sites from bypassing the consumer-boundary coercion.

Add new e2e regression tests:

- `tests/test_d03_decimal_double_roundtrip.py` — INSERTS `Decimal("0.96")` into `aim_modifier_at_entry` against a live QuestDB and asserts the row reads back as `0.96` with no exception.
- `tests/test_d11_pseudotrader_decimal_to_double.py` — same shape for D11 sharpe_* fields.
- `tests/test_d02_dma_decimal_to_double.py` — same shape for D02 inclusion_probability.
- One catch-all `tests/test_typed_insert_helper.py` — exercises every type coercion path of `execute_typed` independently of any specific block.

---

## 5. Phased remediation plan

> All phases READ-ONLY until Phase 1 ships. No code changes until Nomaan signs off.

### Phase 0 — This audit (DONE in this document)

- ✅ Diagnose Issue 5 root cause.
- ✅ Map all 35+ DOUBLE / SYMBOL / INT INSERT sites.
- ✅ Identify the 5-incident historical pattern.
- ✅ Propose 3-layer structural fix.

### Phase 1 — Targeted hotfix for Issue 5 (UNBLOCKS NEXT NY OPEN)

**Scope:** Only the May 5 crash site. Minimum viable patch.

**Change:**

```python
# captain-online/captain_online/blocks/b7_position_monitor.py:533+
# Add to the existing _write_trade_outcome boundary block:
from shared.decimal_boundary import to_float

aim_modifier = to_float(aim_modifier, default=1.0)  # DOUBLE column — must be float
# (entry_price, exit_price, gross_pnl, etc. stay as as_money_or_none — they are DECIMAL)
```

**Tests:**

- New `tests/test_b7_aim_modifier_double_boundary.py` — feeds a `pos["combined_modifier"] = Decimal("0.96")` through `_publish_trade_outcome` → `_write_trade_outcome` and asserts the SQL parameter is `float(0.96)`, not `Decimal`.
- Live tower test: `cap-run replay_one_session.py --asset MES --inject-sl-hit` → assert D03 row is written.

**Risk:** None. `to_float(Decimal("0.96"))` is exact (within float-64 precision) for the 2-decimal ratios this column carries. Spec doc 11 explicitly allows DOUBLE precision for AIM modifiers.

**Estimated effort:** 10 minutes implementation + 30 minutes test + 10 minutes tower validation.

**Definition of done:**

1. `scripts/lint_decimal_boundary.py` returns 0 violations.
2. New regression test passes.
3. Tower replay through SL_HIT reaches the D03 INSERT and writes the row.
4. Both remotes (`origin` + `multi-user`) carry the fix.

### Phase 2 — Companion hotfixes for the other 🔴 sites (SAME-SESSION SAFETY NET)

**Scope:** The other two sites flagged 🔴 in §2.2 — `_update_capital_and_cb` D16 INSERT and `b7_shadow_monitor._publish_shadow_trade_outcome` (which mirrors `_write_trade_outcome`).

**Why now, not Phase 4:** these are the same shape as Issue 5. If we don't fix them, the next NY/APAC/LON open could trigger the identical crash on `combined_modifier` from the shadow path or on a `correlation_threshold` value if `_load_user_silo` ever returns it as Decimal.

**Estimated effort:** 30 minutes total.

### Phase 3 — Layer A structural fix (`execute_typed` helper)

**Scope:** Build the typed-INSERT helper and migrate all INSERT sites in 4 sub-batches:

- **3a — Helper + canonical column-type dict.** Add `COLUMN_TYPES` dict to `shared/canonical_schemas.py` (machine-derived from the DDL strings, not hand-typed — see implementation note below). Add `execute_typed` to `shared/questdb_client.py`. 100% test coverage on coercion logic. ~1 day.

- **3b — Migrate the 5 hottest INSERT sites:** B7 trade outcome, B8 reconciliation D08, orchestrator D23 init, B6 signal output D17, B7 capital silo D16. ~0.5 day.

- **3c — Migrate the offline learning INSERTs:** B1 DMA, B2 BOCPD, B3 pseudotrader (4 sites), B5 sensitivity, B8 kelly, B8 cb_params. ~0.5 day.

- **3d — Migrate the long tail:** D01, D04 (drift), D14 health, D17 monitor, D21 incident, D22 diagnostic, D26 HMM, bootstrap scripts. ~0.5 day.

**Implementation note for 3a:** to avoid hand-maintaining `COLUMN_TYPES`, parse the DDL strings already in `canonical_schemas.py` at module-import time using a small `re`-based DDL parser (no SQL parser dependency). The output is a dict like:

```python
COLUMN_TYPES["p3_d03_trade_outcome_log"] = {
    "trade_id": "STRING",
    "user_id": "SYMBOL",
    "account_id": "SYMBOL",
    ...
    "aim_modifier_at_entry": "DOUBLE",
    "aim_breakdown_at_entry": "STRING",
    ...
}
```

This is automatically in sync with the DDL — no drift possible.

**Estimated effort:** ~3 days total.

### Phase 4 — Layer B fix (typed Decimal markers in JSON)

**Scope:** Switch `dumps_decimal` / `loads_decimal` to use a structural marker (`{"__type__": "Decimal", "value": "..."}`) instead of bare strings.

**Migration constraint:** existing Redis state (`captain:open_positions`, in-flight stream messages) uses the old format. Two options:

1. **Backwards-compatible reader.** New `loads_decimal` accepts both old strings (only for whitelisted monetary keys) and the new marker. Keep this for 1 release cycle, then strip the legacy path.
2. **Coordinated drain.** Stop `captain-online`, drain `STREAM_COMMANDS`, flush `captain:open_positions`, deploy new code, restart. Documented in the runbook.

**Recommend Option 1** for safety (no required downtime).

**Estimated effort:** ~2 days (incl. the e2e flow test rewrite).

### Phase 5 — Layer C lint + e2e tests

**Scope:**

- Extend `scripts/lint_decimal_boundary.py` with the "INSERT INTO p3_d... must go through `execute_typed`" rule. Allowlist the (shrinking) set of unmigrated sites.
- New live-DB e2e tests under `tests/test_decimal_double_roundtrip*.py` — one per high-risk DOUBLE column.

**Estimated effort:** ~1 day.

### Phase 6 — Decommission the global `register_adapter(Decimal, ...)`

**Scope:** Once 100% of INSERT sites use `execute_typed`, the global adapter becomes unnecessary. Remove it. Replace with a guard that raises if a bare `Decimal` ever reaches `cur.execute()` without going through `execute_typed`.

**Why this matters:** the global adapter is the structural cause of every "Decimal flowing into wrong column type" bug. Removing it means future INSERTs cannot accidentally regress.

**Estimated effort:** ~0.5 day. Gated on Phase 3 reaching 100% migration.

---

## 6. Test plan — proving each phase works

### Phase 1 / 2 (hotfixes)

1. `pytest tests/test_b7_aim_modifier_double_boundary.py` — expects pass.
2. Tower live test — replay one session with an SL hit, observe D03 row written.
3. `dco logs captain-online | grep -i 'decimal\|inconvertible'` — expect zero matches.

### Phase 3 (structural fix)

1. New `tests/test_typed_insert_helper.py` — 100% branch coverage on the type coercion table.
2. Replay every offline learning block end-to-end against a live QuestDB sandbox.
3. Static lint: `scripts/lint_decimal_boundary.py` reports the migration progress (`X/Y INSERT sites migrated`).

### Phase 5 / 6 (regression shield)

1. Live e2e: artificially poison `pos["combined_modifier"]` with `Decimal("0.99")` in a test fixture, run through B7. Should now succeed (Layer A) or be caught by the lint (Layer C) if a new untyped INSERT slipped in.
2. Run the existing 528-test fast gate. Expected: zero new regressions.

---

## 7. Definition of done — for the bug class as a whole

The cycle of recurring Decimal errors is closed when **all** of these hold:

1. **Layer A migration complete** — every `INSERT INTO p3_d...` in the repo goes through `execute_typed`.
2. **Layer B marker rolled out** — `loads_decimal` no longer ambiguously coerces numeric strings.
3. **Layer C gates green** — lint forbids new untyped INSERTs; live-DB e2e tests for every DOUBLE-target column pass.
4. **Layer A1 — global Decimal adapter removed** (Phase 6) — no fall-back path that can render a Decimal as DECIMAL into a DOUBLE column.
5. **Live tower validation** — a full week of NY/LON/APAC opens with zero `inconvertible types` errors in any process log.

---

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Phase 3 introduces a regression (e.g. typo in column-type dict) | Medium | High | Auto-derive types from DDL parsing; 100% branch test on `execute_typed`; dry-run replay before tower deploy |
| Phase 4 leaves Redis with old-format keys at restart | High | Medium | Implement Option 1 (backwards-compatible reader) for ≥1 release cycle |
| `Decimal → float` precision loss for large monetary aggregates | Low | High | Limit `to_float` to columns spec'd as DOUBLE (modifier ratios, probabilities, sharpe-type metrics — all <1e6 in magnitude). Money columns stay DECIMAL. |
| New INSERT site added during migration that bypasses helper | Medium | Medium | Lint gate added in Phase 5 — refuses raw `cur.execute("INSERT INTO p3_d...")` without `execute_typed` |
| Tower downtime during structural fix deploy | Low | High | Each phase is independently deployable. Phase 1 is 10 LOC and zero-downtime. |

---

## 9. Open questions for Nomaan

1. **Approval of phased plan.** Do you want all six phases, or only Phases 1–2 now and the structural work on a separate branch?
2. **Layer B option.** Marker-based (B1, recommended) or whitelist-based (B2)?
3. **Phase 6 timing.** Aggressive (Phase 6 lands as soon as Phase 3 hits 100%) or conservative (live for 1 month before removing the safety-net global adapter)?
4. **Test budget.** Are you OK with one new live-QuestDB e2e per DOUBLE-target column (≈10 new tests, ≈30s combined)? Or should we consolidate?

---

## Appendix A — File:line index of every site mentioned

| Site | File | Line |
|------|------|------|
| Global Decimal psycopg2 adapter | `shared/questdb_client.py` | 62-65 |
| `_decimal_to_cast_sql` | `shared/questdb_client.py` | 36-59 |
| `loads_decimal._coerce` | `shared/decimal_json.py` | 47-57 |
| `as_money` / `as_money_or_none` / `to_float` | `shared/decimal_boundary.py` | 33-90 |
| Lint script | `scripts/lint_decimal_boundary.py` | full |
| `_write_trade_outcome` (FAIL site) | `captain-online/captain_online/blocks/b7_position_monitor.py` | 509-557 |
| `_publish_trade_outcome` (Decimal injection) | `captain-online/captain_online/blocks/b7_position_monitor.py` | 716-720 |
| `resolve_position` caller of `_write_trade_outcome` | `captain-online/captain_online/blocks/b7_position_monitor.py` | 405-413 |
| `_handle_taken_skipped` (Decimal type-purity producer) | `captain-online/captain_online/blocks/orchestrator.py` | 1161-1224 |
| `_update_capital_and_cb` (D16/D23 INSERT) | `captain-online/captain_online/blocks/b7_position_monitor.py` | 560-700 |
| Shadow trade outcome publisher | `captain-online/captain_online/blocks/b7_shadow_monitor.py` | 165-180 |
| D03 schema (DOUBLE for aim_modifier_at_entry) | `shared/canonical_schemas.py` | 404-432 |
| D11 schema (DOUBLE for sharpe_*) | `shared/canonical_schemas.py` | 490-506 |
| D02 INSERT (DOUBLE for inclusion_probability) | `captain-offline/captain_offline/blocks/b1_dma_update.py` | 254-260 |
| D04 BOCPD INSERT | `captain-offline/captain_offline/blocks/b2_bocpd.py` | 251-263 |
| D05 EWMA INSERT | `captain-offline/captain_offline/blocks/b8_kelly_update.py` | 121-126 |
| D06 injection INSERT | `captain-offline/captain_offline/blocks/b4_injection.py` | 126-138 |
| D11 pseudotrader INSERT (4 sites) | `captain-offline/captain_offline/blocks/b3_pseudotrader.py` | 551, 1032, 1368, 1556 |
| D12 Kelly INSERT | `captain-offline/captain_offline/blocks/b8_kelly_update.py` | 293, 303 |
| D13 sensitivity INSERT | `captain-offline/captain_offline/blocks/b5_sensitivity.py` | 257-263 |
| D22 diagnostic INSERT | `captain-offline/captain_offline/blocks/b9_diagnostic.py` | 873-881 |
| D14 health INSERT | `captain-command/captain_command/blocks/b3_api_adapter.py` | 694, 711 |
| D08 reconciliation INSERT (3 sites) | `captain-command/captain_command/blocks/b8_reconciliation.py` | 563, 770, 862 |
| D26 HMM INSERT | `captain-online/captain_online/blocks/hmm_inference_block.py` | 123 |

---

## Appendix B — Why Surface 7 of the previous audit was wrong

The 2026-04-30 `EXHAUSTIVE_AUDIT_REPORT.md` Surface 7 ("Decimal vs float literal comparisons") is correct as written, but **it is the wrong question**. It asks "do we compare a Decimal to a float literal?" The right question for the bug class as a whole is **"can a Decimal ever leave Python and land in a non-DECIMAL column?"** — which the audit never asked.

The full set of failure modes for the Decimal/QuestDB boundary is:

| Direction | Failure mode | Audit covered? |
|-----------|-------------|----------------|
| QuestDB → Python (read) | `r[N] or 0.0` falsy-zero collapse | ✅ Yes (Surface 1) |
| QuestDB → Python (read) | Mixed Decimal/float dict mutation | ✅ Yes (Surface 3) |
| Python in-memory | Decimal/float arithmetic TypeError | ✅ Yes (Surface 7) |
| Python → JSON wire | Stdlib `json.dumps` doesn't handle Decimal | ✅ Yes (Surface 4 + 5) |
| Python → QuestDB (INSERT, DECIMAL column) | Wire-level type cast | ✅ Yes (implicit; works) |
| **Python → QuestDB (INSERT, DOUBLE/SYMBOL/INT column)** | **Global adapter renders DECIMAL literal which QuestDB rejects** | **❌ NO — THIS IS BUG #5** |
| JSON → Python (parse) | `loads_decimal._coerce` over-coercion | ⚠️ Mentioned in tracking_context.md but no audit row |

This audit closes the two missing rows.

---

*End of audit and remediation plan.*
