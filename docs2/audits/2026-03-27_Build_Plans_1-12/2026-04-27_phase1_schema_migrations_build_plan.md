# Phase 1 Build Plan — QuestDB Schema Migrations & canonical_schemas.py Alignment

**Status:** Approved for execution  
**Date:** 2026-04-27  
**Executor:** Cursor Composer (Batch-by-batch — complete each batch before starting the next)  
**Companion documents:**
- `phase-ref-docs/phase-1/captain_offline_audit_decisions_2026-04-27.md` — authoritative decisions log
- `phase-ref-docs/phase-1/2026-04-22_offline_spec_vs_code_audit copy.md` — original findings
- `shared/canonical_schemas.py` — schema source of truth

---

## Audit Summary

### Current state of the four affected tables

| Table | canonical_schemas.py lines | Gap |
|---|---|---|
| `p3_d03_trade_outcome_log` | 367–390 | Missing `model_m INT` |
| `p3_d22_system_health_diagnostic` | 510–525 | No per-asset rerun tracking; no `asset` column |
| `p3_d26_hmm_opportunity_state` | 317–328 | **Already correct — ratification is doc-only** |
| `p2_d07_regime_models` | — | **Does not exist** |

### Migration mechanism gap

`scripts/init_questdb.py` loops `CANONICAL_DDLS` with `CREATE TABLE IF NOT EXISTS` on every container start. This is a no-op for existing tables — **new columns added to DDL strings will never be applied to a running DB**. Batch 0 builds the additive migration runner.

### Writers of `p3_d03_trade_outcome_log` (grep-verified, no others exist)

| File | Lines | Notes |
|---|---|---|
| `captain-online/captain_online/blocks/b7_position_monitor.py` | 284–300 | `_write_trade_outcome()` — live trade writer, 21-col INSERT |
| `scripts/paper_trader.py` | 374–386 (`_log_trade_open`), 395–409 (`_log_trade_close`) | Open + close split inserts |
| `shared/trade_source.py` | 295–313 | Synthetic seeder; TODO comment at L229 explicitly notes missing `model` field |

### Readers of `p3_d22_system_health_diagnostic` (grep-verified)

| File | Lines | Notes |
|---|---|---|
| `captain-offline/captain_offline/blocks/b9_diagnostic.py` | 837 | `SELECT action_queue ... ORDER BY ts DESC LIMIT 1` |
| `captain-offline/captain_offline/blocks/b9_diagnostic.py` | 266–340 | `compute_d3()` — D3 staleness; regime age read at L279–289 via `p3_d00_asset_universe.locked_strategy` JSON |
| `captain-offline/captain_offline/blocks/b9_diagnostic.py` | 880–896 | `run_diagnostic()` INSERT writer (one system-wide row per run) |

### Locked-strategy `m` source (for Batch 2 writers)

The active `m` is persisted in `p3_d00_asset_universe.locked_strategy` JSON (column `m`). Shared helper at `captain-offline/captain_offline/blocks/bootstrap.py:36` (`_load_locked_strategy(asset_id)`) loads it. Since b7_position_monitor runs in captain-online (not captain-offline), **a shared reader must be used**: the cheapest pattern is an inline QuestDB SELECT inside each writer function, or a new helper in `shared/trade_source.py`.

### D26 ratification verdict

Columns in `shared/canonical_schemas.py:318–326`:
```
hmm_params STRING, current_state_probs STRING, opportunity_weights STRING,
prior_alpha STRING, last_trained TIMESTAMP, training_window INT,
n_observations INT, cold_start BOOLEAN, last_updated TIMESTAMP
```
This matches the decisions-log Q-27 column list verbatim. The table alias `p3_d26_hmm_states` in the decisions doc is shorthand only — code name `p3_d26_hmm_opportunity_state` is canonical per Q-02.
**No DDL or code change required.** Batch 4 adds a ratification comment header and CANONICAL_DDLS comment annotation.

---

## Migration Application Strategy

### Idempotency mechanism

QuestDB does not support `ALTER TABLE ADD COLUMN IF NOT EXISTS`. The runner guards each `ALTER` with a broad try/except:

```python
try:
    cur.execute(alter_sql)
except Exception as exc:
    if "already exists" in str(exc).lower() or "duplicate" in str(exc).lower():
        pass  # idempotent
    else:
        raise
```

This means running `init_questdb.py` twice is safe — already-applied migrations are silently skipped.

### Registry location

`CANONICAL_MIGRATIONS: list[tuple[str, str]]` added to `shared/canonical_schemas.py` below `CANONICAL_DDLS`. Each entry is `(migration_id: str, alter_sql: str)`. `migration_id` is a human-readable string (`"M001_..."`) used only for log output.

### Container-restart survival

- QuestDB data volume: `./questdb/db:/var/lib/questdb/db` (host bind-mount, persists across restarts).
- `captain-start.sh:192–217` already invokes `init_questdb.py` on every start.
- After Batch 0, `init_questdb.py` runs `CANONICAL_MIGRATIONS` after `CANONICAL_DDLS`, so new columns are applied automatically on every container start.

### Dev environment apply procedure

```bash
# Inside the captain-command container (or directly if running locally):
python3 /app/scripts/init_questdb.py

# Verify columns appeared:
# QuestDB web console (http://localhost:9000):
#   SHOW COLUMNS FROM p3_d03_trade_outcome_log;
#   SHOW COLUMNS FROM p3_d22b_asset_rerun_status;
#   SHOW COLUMNS FROM p2_d07_regime_models;
```

---

## Batch 0: Migration Runner Prerequisite

**Must complete before any other batch.**

### 0.1 Spec citation

No specific finding — engineering prerequisite identified during Phase 1 audit. The decisions log assumes a migration runner exists; it does not.

### 0.2 Files to modify

- `shared/canonical_schemas.py` — add `CANONICAL_MIGRATIONS` registry (after `CANONICAL_DDLS` list)
- `scripts/init_questdb.py` — add migration application loop after the existing CREATE loop

### 0.3 Change: `shared/canonical_schemas.py`

After the `CANONICAL_DDLS` list (which ends around line 784), add:

```python
# ---------------------------------------------------------------------------
# Additive column migrations (idempotent ALTER TABLE runs).
# Format: (migration_id, alter_sql)
# init_questdb.py applies these after the CREATE TABLE loop.
# ---------------------------------------------------------------------------
CANONICAL_MIGRATIONS: list[tuple[str, str]] = [
    # Batch 2 — Q-06 / F-06
    (
        "M001_d03_add_model_m",
        "ALTER TABLE p3_d03_trade_outcome_log ADD COLUMN model_m INT",
    ),
]
```

Note: `p3_d22b_asset_rerun_status` (Batch 3) is a new table handled by `CANONICAL_DDLS`, not an ALTER. No migration entry needed for it.

### 0.4 Change: `scripts/init_questdb.py`

Add the import and the migration application loop. After the existing `for ddl in CANONICAL_DDLS:` loop, add:

```python
from shared.canonical_schemas import CANONICAL_DDLS, CANONICAL_MIGRATIONS, table_name_of

# ... existing CREATE loop (unchanged) ...

print(f"  Applying {len(CANONICAL_MIGRATIONS)} additive migrations...")
for migration_id, alter_sql in CANONICAL_MIGRATIONS:
    try:
        with get_cursor() as cur:
            cur.execute(alter_sql)
        print(f"  [OK] {migration_id}")
    except Exception as exc:
        if "already exists" in str(exc).lower() or "duplicate" in str(exc).lower():
            print(f"  [SKIP] {migration_id} (column already present)")
        else:
            print(f"  [FAIL] {migration_id}: {exc}")
            ok = False
```

The `ok` variable is already defined in `init_questdb()` — use it directly.

### 0.5 Tests

- **Schema integrity**: after running `init_questdb.py` twice against a test DB, assert no exception is raised the second time (`SKIP` path exercised).
- **No test needed for runner logic beyond idempotency** — column existence is tested per-batch.

### 0.6 Rollback

To roll back the runner itself: revert `shared/canonical_schemas.py` and `scripts/init_questdb.py` to pre-Batch-0 state. No DB-side change.

### 0.7 Exit criteria

- [ ] `shared/canonical_schemas.py` exports `CANONICAL_MIGRATIONS`
- [ ] `scripts/init_questdb.py` imports and applies `CANONICAL_MIGRATIONS` after CREATE loop
- [ ] Running `python3 scripts/init_questdb.py` twice in a row against a fresh DB prints `[OK]` then `[SKIP]` for each migration
- [ ] `from shared.canonical_schemas import CANONICAL_MIGRATIONS` does not raise in any container Python path

---

## Batch 1: Create `p2_d07_regime_models` Table

### 1.1 Batch ID and title

`Batch 1: Create p2_d07_regime_models table (empty DDL only)`

### 1.2 Spec citation

- Decisions log §2 Group A, Q-01 / F-50: *"P2-D07 lives as a separate QuestDB table `p2_d07_regime_models`."*
- Decisions log §4.1: *"Columns TBD from existing JSON shape; should mirror what online B1 currently expects when reading regime_models."*
- `32_P3_Offline_Full_Pseudocode.md:23` — references P2-D07 as a B9 data source.

**Important:** The decisions log says "Columns TBD". The column set below was derived from `_load_regime_models()` (`captain-online/.../b1_data_ingestion.py:313-332`) + `prediction_model_ref` sub-object in `data/p2_outputs/{ASSET}/p2_d06_locked_strategy.json`. **No reader or writer migration ships in Phase 1** — Online B1 continues synthesizing from D00. The reader/writer wiring is deferred to Phase 7 (captain_online_replay scope per decisions log §5, Phase 7 row).

### 1.3 Pre-flight checks

- [ ] `shared/canonical_schemas.py` does NOT currently contain `p2_d07_regime_models` (verified: no match in grep)
- [ ] `p3_d07_correlation_model_states` exists at line 180 — different table, different prefix — no conflict
- [ ] Batch 0 has been applied (runner available)

### 1.4 Migration DDL

No ALTER needed — this is a new table handled by `CANONICAL_DDLS`. Add DDL constant to `shared/canonical_schemas.py`.

Add the following constant **after the `D07_CORRELATION_MODEL_STATES` block** (near line 180) but **in a new section** to keep `p2_` and `p3_` namespaces distinct. Add a comment block:

```python
# --------------------------------------------------------------------- #
# P2 research output tables (read-only at runtime; populated by P1/P2   #
# pipeline reruns or the offline seed scripts)                           #
# --------------------------------------------------------------------- #

P2_D07_REGIME_MODELS = """
CREATE TABLE IF NOT EXISTS p2_d07_regime_models (
    asset                SYMBOL,
    model_type           STRING,
    feature_list         STRING,
    pettersson_threshold DOUBLE,
    regime_label         STRING,
    training_period      STRING,
    n_training_obs       INT,
    best_hyperparams     STRING,
    cv_score             DOUBLE,
    trained_at           TIMESTAMP,
    last_updated         TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(last_updated, asset);
"""
```

Column semantics:
- `asset` — SYMBOL matching `p3_d00_asset_universe.asset_id`
- `model_type` — e.g. `"BINARY_ONLY"` (from `locked_strategy.prediction_model_ref.model_type`)
- `feature_list` — JSON array of feature names (from `prediction_model_ref.feature_list`)
- `pettersson_threshold` — from `locked_strategy.prediction_model_ref.pettersson_threshold`
- `regime_label` — e.g. `"REGIME_NEUTRAL"` (from `locked_strategy.prediction_model_ref` or default)
- `training_period` — `"YYYY-MM-DD..YYYY-MM-DD"` string
- `n_training_obs` — INT (from `prediction_model_ref.n_training_obs`)
- `best_hyperparams` — JSON STRING (from `prediction_model_ref.best_hyperparams`)
- `cv_score` — DOUBLE (from `prediction_model_ref.cv_score`)
- `trained_at` — TIMESTAMP of last P2 training run for this asset
- `last_updated` — TIMESTAMP, DEDUP key

### 1.5 `shared/canonical_schemas.py` update

Two edits:

**Edit A — add the DDL constant** (above, in new `# P2 research output tables` section).

**Edit B — add to `CANONICAL_DDLS` list** at `shared/canonical_schemas.py:736`. Add `P2_D07_REGIME_MODELS` as the first entry in a new comment group at the bottom of the list, before `AUDIT_LOG`:

```python
    # P2 research output (empty at install; populated by pipeline reruns)
    P2_D07_REGIME_MODELS,
```

### 1.6 Writer updates

**None in Phase 1.** Online B1's `_load_regime_models()` (`captain-online/captain_online/blocks/b1_data_ingestion.py:313-332`) continues synthesizing from `p3_d00_asset_universe.locked_strategy`. Wiring Online B1 to read from `p2_d07_regime_models` instead is Phase 7 scope.

### 1.7 Reader updates

**None in Phase 1.** Document this deferral in the `p2_d07_regime_models` DDL constant comment:

```python
# Phase 1: table created empty. Online B1 still synthesises regime model
# params from p3_d00_asset_universe.locked_strategy (deferred to Phase 7).
# When Phase 7 ships, _load_regime_models() switches to SELECT FROM this table.
```

### 1.8 Tests

Add to `tests/test_schema_migrations.py` (create file if absent):

```python
def test_b1_p2_d07_table_exists():
    """Schema integrity: p2_d07_regime_models table is created."""
    with get_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM p2_d07_regime_models")
        cols = {row[0] for row in cur.fetchall()}
    assert "asset" in cols
    assert "model_type" in cols
    assert "pettersson_threshold" in cols
    assert "last_updated" in cols

def test_b1_p2_d07_round_trip():
    """Round-trip: insert one row, read it back, verify shape."""
    now_ts = datetime.utcnow().isoformat()
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p2_d07_regime_models
               (asset, model_type, feature_list, pettersson_threshold,
                regime_label, n_training_obs, cv_score, trained_at, last_updated)
               VALUES ('ES', 'BINARY_ONLY', '["f1","f2"]', 0.55,
                       'REGIME_NEUTRAL', 100, 0.62, %s, %s)""",
            (now_ts, now_ts),
        )
        cur.execute(
            "SELECT asset, model_type FROM p2_d07_regime_models "
            "WHERE asset = 'ES' LATEST ON last_updated PARTITION BY asset"
        )
        row = cur.fetchone()
    assert row[0] == "ES"
    assert row[1] == "BINARY_ONLY"

def test_b1_p2_d07_backwards_compat():
    """Backwards compat: table starts empty and SELECT does not raise."""
    with get_cursor() as cur:
        cur.execute("SELECT count() FROM p2_d07_regime_models")
        row = cur.fetchone()
    assert row[0] >= 0  # any non-negative count is acceptable
```

### 1.9 Rollback DDL

```sql
DROP TABLE p2_d07_regime_models;
```

Also remove `P2_D07_REGIME_MODELS` constant and list entry from `shared/canonical_schemas.py`.

### 1.10 Exit criteria

- [ ] `shared/canonical_schemas.py` exports `P2_D07_REGIME_MODELS` DDL constant
- [ ] `CANONICAL_DDLS` list includes `P2_D07_REGIME_MODELS`
- [ ] `python3 scripts/init_questdb.py` prints `[OK] p2_d07_regime_models` (or `[SKIP]` if already created)
- [ ] `SHOW COLUMNS FROM p2_d07_regime_models` returns 11 columns
- [ ] All three Batch 1 tests pass
- [ ] Online B1 `_load_regime_models()` is **unchanged** — it still synthesizes from D00

---

## Batch 2: Add `model_m INT` to `p3_d03_trade_outcome_log`

### 2.1 Batch ID and title

`Batch 2: Add model_m INT to p3_d03_trade_outcome_log and update all three writers`

### 2.2 Spec citation

- Decisions log §2 Group A, Q-06 / F-06: *"Add `model_m INT` to `p3_d03_trade_outcome_log`. Column matches `p3_d25_circuit_breaker_params.model_m`. Writers (online B7, paper_trader, trade_source) must populate from active locked-strategy `m`."*
- `p3_d25_circuit_breaker_params` DDL (`shared/canonical_schemas.py:299-312`): `model_m INT` — type confirmed.

### 2.3 Pre-flight checks

- [ ] Batch 0 is complete (`CANONICAL_MIGRATIONS` runner exists)
- [ ] `SHOW COLUMNS FROM p3_d03_trade_outcome_log` does NOT include `model_m` (verified: column is absent)
- [ ] `SHOW COLUMNS FROM p3_d25_circuit_breaker_params` includes `model_m INT` (reference type)

### 2.4 Migration DDL

Already included in Batch 0's `CANONICAL_MIGRATIONS`:

```python
(
    "M001_d03_add_model_m",
    "ALTER TABLE p3_d03_trade_outcome_log ADD COLUMN model_m INT",
),
```

No additional DDL needed. Running `init_questdb.py` after Batch 0 is complete will apply it.

### 2.5 `shared/canonical_schemas.py` update

Add `model_m INT` to the `D03_TRADE_OUTCOME_LOG` DDL constant (`shared/canonical_schemas.py:367-390`). The column should be added **before** the `ts TIMESTAMP` line:

```sql
-- Before (line ~389):
    tsm_used STRING,
    ts TIMESTAMP

-- After:
    tsm_used STRING,
    model_m INT,
    ts TIMESTAMP
```

This keeps the DDL in sync with the live schema (idempotent CREATE will not re-add the column, but the DDL string should document the current schema).

### 2.6 Writer updates

#### Writer A: `captain-online/captain_online/blocks/b7_position_monitor.py` (line 284)

**Context:** `_write_trade_outcome()` function (starts around line 273). This is the live trade writer called at position close.

**Step 1 — Add a helper to look up `m` from D00.** After existing imports at the top of the file, add (or reuse if already present):

```python
def _get_locked_m(asset: str) -> int | None:
    """Return the locked-strategy m for asset from p3_d00_asset_universe."""
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT locked_strategy FROM p3_d00_asset_universe "
                "WHERE asset_id = %s LATEST ON last_updated PARTITION BY asset_id",
                (asset,),
            )
            row = cur.fetchone()
        if row and row[0]:
            return json.loads(row[0]).get("m")
    except Exception:
        pass
    return None
```

**Step 2 — Add `model_m` to `_write_trade_outcome()` signature** (or compute it inside the function). The function already has access to `asset`:

```python
def _write_trade_outcome(trade_id, user_id, account_id, asset, direction,
                         entry_price, signal_entry_price, exit_price, contracts,
                         gross_pnl, commission, net_pnl, slippage, outcome,
                         entry_time, regime_at_entry, aim_modifier, aim_breakdown,
                         session, tsm_used):
    aim_bd_str = json.dumps(aim_breakdown, default=str) if aim_breakdown else None
    entry_ts = entry_time.isoformat() if isinstance(entry_time, datetime) else entry_time
    model_m = _get_locked_m(asset)   # <-- add this line

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d03_trade_outcome_log
               (trade_id, user_id, account_id, asset, direction,
                entry_price, signal_entry_price, exit_price, contracts,
                gross_pnl, commission, pnl, slippage, outcome,
                entry_time, regime_at_entry, aim_modifier_at_entry,
                aim_breakdown_at_entry, session, tsm_used, model_m, ts)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, now())""",
            (trade_id, user_id, account_id, asset, direction,
             entry_price, signal_entry_price, exit_price, contracts,
             gross_pnl, commission, net_pnl, slippage, outcome,
             entry_ts, regime_at_entry, aim_modifier,
             aim_bd_str, session, tsm_used, model_m),   # <-- add model_m
        )
```

#### Writer B: `scripts/paper_trader.py` (lines 374 and 395)

**`_log_trade_open()` (around line 370):**

The INSERT currently uses a partial column list (11 columns for OPEN records). Add `model_m`:

```python
def _log_trade_open(self, pos: Position):
    model_m = _get_locked_m(pos.asset)   # <-- add; see helper below
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d03_trade_outcome_log (
                    trade_id, user_id, account_id, asset, direction,
                    entry_price, contracts, outcome, entry_time,
                    session, model_m, ts
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                (
                    pos.trade_id, USER_ID, ACCOUNT_ID, pos.asset,
                    pos.direction, pos.entry_price, pos.contracts, "OPEN",
                    pos.entry_time.isoformat(), 1, model_m,
                ),
            )
    except Exception as exc:
        logger.warning("D03 open log failed: %s", exc)
```

Note: `paper_trader.py` currently hardcodes `"ES"` as asset in the INSERT. This should be `pos.asset` if the Position object carries it, or left as-is if this is intentionally ES-only. **[UNVERIFIED — inspect `Position` dataclass definition in paper_trader.py and use `pos.asset` if available, else leave `"ES"` and hardcode `m=7` as the ES locked-strategy `m`.]**

**`_log_trade_close()` (around line 395):** Same pattern — add `model_m` to column list and VALUES tuple.

**Helper:** Add `_get_locked_m(asset: str) -> int | None` to `scripts/paper_trader.py` (or import from `shared.trade_source` after Step 2c below):

```python
def _get_locked_m(asset: str) -> int | None:
    """Return locked-strategy m from p3_d00_asset_universe, or None."""
    try:
        import json
        from shared.questdb_client import get_cursor
        with get_cursor() as cur:
            cur.execute(
                "SELECT locked_strategy FROM p3_d00_asset_universe "
                "WHERE asset_id = %s LATEST ON last_updated PARTITION BY asset_id",
                (asset,),
            )
            row = cur.fetchone()
        if row and row[0]:
            return json.loads(row[0]).get("m")
    except Exception:
        pass
    return None
```

Alternatively — if QuestDB is unavailable during paper_trader runs — fall back to the JSON file:

```python
def _get_locked_m(asset: str) -> int | None:
    import json, os
    try:
        path = os.path.join(
            os.path.dirname(__file__), "..", "data", "p2_outputs",
            asset.upper(), "p2_d06_locked_strategy.json"
        )
        with open(path) as f:
            return json.load(f).get("m")
    except Exception:
        return None
```

Choose the QuestDB path (first snippet) for consistency; fall back to the file path only if paper_trader does not have DB access at call time.

#### Writer C: `shared/trade_source.py` (line 295)

The synthetic seeder at `seed_d03_from_synthetic()` inserts rows from a list of synthetic trade dicts. Add `model_m` to the INSERT:

```python
# In the INSERT column list, add model_m before ts:
(trade_id, user_id, account_id, asset, ..., "SYNTHETIC",
 t.get("model_m"),   # <-- add; synthetic data may carry "m" from make_locked_strategy fixture
),
```

If `t.get("model_m")` is `None` for existing synthetic datasets, that is acceptable — the column is nullable (INT, no NOT NULL constraint).

Also remove or resolve the TODO comment at `shared/trade_source.py:229`:
```python
# Before: "model": 4,  # default model — D03 doesn't store model index
# After: remove this comment — D03 now stores model_m
```

### 2.7 Reader updates

No Phase 1 reader changes. The new column is purely additive. Existing readers use explicit column lists (`SELECT col1, col2 ...`) and will not break. The two readers that will benefit from `model_m` in later phases:
- `captain-offline/.../b8_cb_params.py:46` — per-`m` CB calibration (Phase 8)
- `captain-online/.../b5c_circuit_breaker.py:558` — per-`m` loss attribution (Phase 8)

### 2.8 Tests

Add to `tests/test_schema_migrations.py`:

```python
def test_b2_d03_model_m_column_exists():
    """Schema integrity: model_m INT column present in p3_d03_trade_outcome_log."""
    with get_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM p3_d03_trade_outcome_log")
        cols = {row[0]: row[1] for row in cur.fetchall()}
    assert "model_m" in cols
    assert cols["model_m"] == "INT"

def test_b2_d03_model_m_round_trip():
    """Round-trip: insert a row with model_m, read it back, verify value."""
    trade_id = f"TEST-MODELM-{int(time.time())}"
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d03_trade_outcome_log
               (trade_id, user_id, account_id, asset, direction,
                outcome, model_m, ts)
               VALUES (%s, 'test_user', 'test_acct', 'ES', 1,
                       'SYNTHETIC', 7, now())""",
            (trade_id,),
        )
        cur.execute(
            "SELECT model_m FROM p3_d03_trade_outcome_log "
            "WHERE trade_id = %s LATEST ON ts PARTITION BY trade_id",
            (trade_id,),
        )
        row = cur.fetchone()
    assert row[0] == 7

def test_b2_d03_model_m_backwards_compat():
    """Backwards compat: existing rows without model_m return NULL gracefully."""
    # Insert a row omitting model_m (simulating a pre-migration row)
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d03_trade_outcome_log
               (trade_id, user_id, account_id, asset, direction,
                outcome, ts)
               VALUES ('LEGACY-ROW-001', 'test_user', 'test_acct', 'ES', 1,
                       'SYNTHETIC', now())""",
        )
        cur.execute(
            "SELECT model_m FROM p3_d03_trade_outcome_log "
            "WHERE trade_id = 'LEGACY-ROW-001' LATEST ON ts PARTITION BY trade_id"
        )
        row = cur.fetchone()
    # model_m is nullable — NULL is the correct value for legacy rows
    assert row[0] is None
```

### 2.9 Rollback DDL

There is no `ALTER TABLE DROP COLUMN IF EXISTS` in QuestDB. Rollback requires:
1. Remove `model_m` from all INSERT statements across the three writer files (revert code).
2. The column remains in QuestDB (benign — NULL-filled, not read by any code after rollback).
3. If full removal is required: recreate table and reseed from D03 backup (destructive — only if spec changes).

For Phase 1 purposes, code rollback (step 1) is sufficient.

### 2.10 Exit criteria

- [ ] `SHOW COLUMNS FROM p3_d03_trade_outcome_log` includes `model_m INT`
- [ ] `shared/canonical_schemas.py` `D03_TRADE_OUTCOME_LOG` DDL includes `model_m INT` before `ts`
- [ ] `CANONICAL_MIGRATIONS` includes `M001_d03_add_model_m`
- [ ] b7_position_monitor.py INSERT at line 284 includes `model_m` in column list and VALUES
- [ ] paper_trader.py INSERTs at lines ~374 and ~395 include `model_m`
- [ ] trade_source.py INSERT at line 295 includes `model_m`
- [ ] TODO comment at trade_source.py:229 removed
- [ ] All three Batch 2 tests pass

---

## Batch 3: Create `p3_d22b_asset_rerun_status` Sibling Table

### 3.1 Batch ID and title

`Batch 3: Create p3_d22b_asset_rerun_status + wire writer in orchestrator + wire reader in compute_d3`

### 3.2 Spec citation

- Decisions log §2 Group H, Q-19 / F-35: *"Add `last_p1p2_rerun_ts` column to `p3_d22_system_health_diagnostic`, indexed per asset."*
- Phase 1 design decision (approved 2026-04-27): implement as sibling table `p3_d22b_asset_rerun_status` — cleaner separation, leaves D22 single-row diagnostic flow untouched.
- Decisions log §5, Phase 9 row: *"D3 schema column (Q-19)"* — the reader in `compute_d3` must use this data.
- Decisions log §2 Group H, Q-19 writer: *"Writer = whoever completes a P1/P2 rerun for that asset (likely Command or the offline manual-job dispatcher)."* The existing P1P2_RERUN job handler is at `captain-offline/captain_offline/blocks/orchestrator.py:698`.

### 3.3 Pre-flight checks

- [ ] `p3_d22_system_health_diagnostic` DDL at `shared/canonical_schemas.py:510-525` — confirm no `asset` or `last_p1p2_rerun_ts` column (verified: absent)
- [ ] No existing table `p3_d22b_asset_rerun_status` (grep: none found)
- [ ] `captain-offline/.../orchestrator.py:698` P1P2_RERUN handler exists (verified)
- [ ] `captain-offline/.../b9_diagnostic.py` `compute_d3()` at lines 266–340 (verified)

### 3.4 Migration DDL

New table — handled via `CANONICAL_DDLS`, no `ALTER` required.

Add DDL constant to `shared/canonical_schemas.py` **after `D22_SYSTEM_HEALTH_DIAGNOSTIC`** (around line 526):

```python
D22B_ASSET_RERUN_STATUS = """
CREATE TABLE IF NOT EXISTS p3_d22b_asset_rerun_status (
    asset                SYMBOL,
    last_p1p2_rerun_ts   TIMESTAMP,
    rerun_trigger        STRING,
    last_updated         TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(asset);
"""
```

Column semantics:
- `asset` — SYMBOL matching `p3_d00_asset_universe.asset_id`; DEDUP key (one row per asset, upserted on each rerun)
- `last_p1p2_rerun_ts` — when the P1/P2 rerun for this asset completed (or was triggered)
- `rerun_trigger` — human-readable reason string (e.g. `"LEVEL3_STALENESS"`, `"MANUAL"`)
- `last_updated` — partition timestamp

### 3.5 `shared/canonical_schemas.py` update

**Edit A — add constant** as above (after D22 block, ~line 526).

**Edit B — add to `CANONICAL_DDLS` list** immediately after `D22_SYSTEM_HEALTH_DIAGNOSTIC`:

```python
    D22_SYSTEM_HEALTH_DIAGNOSTIC,
    D22B_ASSET_RERUN_STATUS,           # <-- add
    D27_PSEUDOTRADER_FORECASTS,
```

### 3.6 Writer updates

**File:** `captain-offline/captain_offline/blocks/orchestrator.py`  
**Location:** P1P2_RERUN handler at lines 698–706

When `job_type == "P1P2_RERUN"` completes (currently sets `result_status = "AWAITING_MANUAL"`), add an UPSERT to `p3_d22b_asset_rerun_status`:

```python
elif job_type == "P1P2_RERUN":
    # P1/P2 rerun requires external pipeline — log as actionable
    result_status = "AWAITING_MANUAL"
    result_msg = (
        f"P1/P2 rerun required for {asset_id}. "
        "Run pipeline manually or via automation trigger."
    )
    logger.warning("P1/P2 rerun for %s requires manual execution", asset_id)

    # Record the rerun request timestamp for D3 staleness scoring
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d22b_asset_rerun_status
                   (asset, last_p1p2_rerun_ts, rerun_trigger, last_updated)
                   VALUES (%s, now(), 'LEVEL3_STALENESS', now())""",
                (asset_id,),
            )
    except Exception as exc:
        logger.warning("D22b rerun timestamp write failed for %s: %s", asset_id, exc)
```

The `try/except` matches the pattern of other non-critical writes in this codebase.

### 3.7 Reader updates

**File:** `captain-offline/captain_offline/blocks/b9_diagnostic.py`  
**Function:** `compute_d3()` at lines 266–340  
**Target:** Replace the `locked_strategy.timestamp` proxy for per-asset P1/P2 staleness (lines 275–289) with a read from `p3_d22b_asset_rerun_status`.

Currently at lines ~278–290:
```python
regime_model_ages = {}
for ar in asset_rows:
    s = json.loads(ar[1]) if ar[1] else {}
    # Use strategy timestamp or P2 completion date if available
    regime_ts = s.get("p2_locked_at") or s.get("timestamp") or ar[2]
    regime_model_ages[ar[0]] = _safe_days_since(regime_ts)
```

After Batch 3, augment this with a per-asset check of `p3_d22b_asset_rerun_status`:

```python
# Load last P1/P2 rerun timestamps per asset
with get_cursor() as cur:
    cur.execute(
        "SELECT asset, last_p1p2_rerun_ts FROM p3_d22b_asset_rerun_status "
        "LATEST ON last_updated PARTITION BY asset"
    )
    rerun_rows = cur.fetchall()
rerun_ts_by_asset = {row[0]: row[1] for row in (rerun_rows or [])}

regime_model_ages = {}
for ar in asset_rows:
    s = json.loads(ar[1]) if ar[1] else {}
    # Prefer actual rerun timestamp; fall back to locked_strategy proxy
    regime_ts = (
        rerun_ts_by_asset.get(ar[0])
        or s.get("p2_locked_at")
        or s.get("timestamp")
        or ar[2]
    )
    regime_model_ages[ar[0]] = _safe_days_since(regime_ts)
```

This is additive: the fallback chain ensures `compute_d3` continues working on systems where `p3_d22b_asset_rerun_status` is empty (e.g. fresh install, or before any P1P2_RERUN job has been processed).

### 3.8 Tests

Add to `tests/test_schema_migrations.py`:

```python
def test_b3_d22b_table_exists():
    """Schema integrity: p3_d22b_asset_rerun_status table exists with correct columns."""
    with get_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM p3_d22b_asset_rerun_status")
        cols = {row[0] for row in cur.fetchall()}
    assert "asset" in cols
    assert "last_p1p2_rerun_ts" in cols
    assert "rerun_trigger" in cols
    assert "last_updated" in cols

def test_b3_d22b_round_trip():
    """Round-trip: upsert two rows for same asset, LATEST ON reads most recent."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d22b_asset_rerun_status
               (asset, last_p1p2_rerun_ts, rerun_trigger, last_updated)
               VALUES ('ES', now(), 'TEST_RUN_1', now())"""
        )
        time.sleep(0.01)
        cur.execute(
            """INSERT INTO p3_d22b_asset_rerun_status
               (asset, last_p1p2_rerun_ts, rerun_trigger, last_updated)
               VALUES ('ES', now(), 'TEST_RUN_2', now())"""
        )
        cur.execute(
            "SELECT rerun_trigger FROM p3_d22b_asset_rerun_status "
            "LATEST ON last_updated PARTITION BY asset WHERE asset = 'ES'"
        )
        row = cur.fetchone()
    assert row[0] == "TEST_RUN_2"

def test_b3_compute_d3_empty_table_graceful():
    """Backwards compat: compute_d3 does not raise when p3_d22b_asset_rerun_status is empty."""
    # Truncate the table if it has rows, then verify compute_d3 still runs
    # (This test requires a live DB connection and a minimal D00 row)
    # Minimal smoke: the new SELECT does not raise on an empty table
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset, last_p1p2_rerun_ts FROM p3_d22b_asset_rerun_status "
            "LATEST ON last_updated PARTITION BY asset"
        )
        rows = cur.fetchall()
    assert isinstance(rows, list)  # empty list is valid
```

### 3.9 Rollback DDL

```sql
DROP TABLE p3_d22b_asset_rerun_status;
```

Also revert `shared/canonical_schemas.py` constant + list entry, revert `orchestrator.py` P1P2_RERUN writer addition, and revert `b9_diagnostic.py` `compute_d3()` reader augmentation.

### 3.10 Exit criteria

- [ ] `SHOW COLUMNS FROM p3_d22b_asset_rerun_status` returns 4 columns: `asset, last_p1p2_rerun_ts, rerun_trigger, last_updated`
- [ ] `shared/canonical_schemas.py` exports `D22B_ASSET_RERUN_STATUS` constant
- [ ] `CANONICAL_DDLS` list includes `D22B_ASSET_RERUN_STATUS` after `D22_SYSTEM_HEALTH_DIAGNOSTIC`
- [ ] `captain-offline/.../orchestrator.py` P1P2_RERUN branch writes to `p3_d22b_asset_rerun_status` (non-fatal try/except)
- [ ] `captain-offline/.../b9_diagnostic.py` `compute_d3()` reads from `p3_d22b_asset_rerun_status` with fallback to `locked_strategy.timestamp`
- [ ] All three Batch 3 tests pass
- [ ] `p3_d22_system_health_diagnostic` DDL is **unchanged** (no columns added, no DEDUP key change)

---

## Batch 4: D26 Schema Ratification (Doc-Only)

### 4.1 Batch ID and title

`Batch 4: Ratify p3_d26_hmm_opportunity_state column set — canonical_schemas.py comment only`

### 4.2 Spec citation

- Decisions log §2 Group D, Q-27 / F-45: *"Ratify schema per Q-27 answer (no migration needed; document and align canonical_schemas.py)."*
- Decisions log §4.3: documented shape `hmm_params | current_state_probs | opportunity_weights | prior_alpha | last_trained | training_window | n_observations | cold_start | last_updated` — matches canonical DDL exactly.
- Decisions log §2 Group A, Q-02: *"canonical_schemas.py is authoritative for schemas."*
- Table name: `p3_d26_hmm_opportunity_state` (code). Decisions log uses shorthand `p3_d26_hmm_states`. Per Q-02, code name wins.

### 4.3 Pre-flight checks

- [ ] `SHOW COLUMNS FROM p3_d26_hmm_opportunity_state` returns exactly 9 columns matching the DDL at `shared/canonical_schemas.py:318-326`
- [ ] No code file references `p3_d26_hmm_states` (grep confirmed: zero hits outside `docs2/`)

### 4.4 Migration DDL

**None.** No DDL change. No ALTER. No new table.

### 4.5 `shared/canonical_schemas.py` update

Add a ratification comment header to the `D26_HMM_OPPORTUNITY_STATE` DDL constant (lines ~315-328):

```python
# Q-27 RATIFIED 2026-04-27 — column set matches decisions log §4.3 exactly.
# Canonical name: p3_d26_hmm_opportunity_state (decisions doc uses shorthand
# "p3_d26_hmm_states" — per Q-02 code name is authoritative).
# Writer split (per Q-11 interpretation, subject to Isaac re-confirm):
#   offline PG-01C → hmm_params, training_window, n_observations, last_trained
#   online PG-23/PG-25B → current_state_probs, opportunity_weights, last_updated
D26_HMM_OPPORTUNITY_STATE = """
CREATE TABLE IF NOT EXISTS p3_d26_hmm_opportunity_state (
    ...
```

### 4.6 Writer updates

None. Single writer (`captain-offline/.../b1_aim16_hmm.py:167-187`) confirmed correct.

### 4.7 Reader updates

None. Six readers confirmed correct (listed in Audit Summary above).

### 4.8 Tests

Add to `tests/test_schema_migrations.py`:

```python
def test_b4_d26_column_set_ratification():
    """Ratification: p3_d26_hmm_opportunity_state has exactly the 9 ratified columns."""
    expected = {
        "hmm_params", "current_state_probs", "opportunity_weights",
        "prior_alpha", "last_trained", "training_window",
        "n_observations", "cold_start", "last_updated",
    }
    with get_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM p3_d26_hmm_opportunity_state")
        actual = {row[0] for row in cur.fetchall()}
    assert actual == expected, f"Column drift: extra={actual-expected}, missing={expected-actual}"

# Round-trip and backwards-compat tests not required for ratification-only batch
# (no schema change, no new writer, no new reader).
```

### 4.9 Rollback

Remove the comment header from `D26_HMM_OPPORTUNITY_STATE` constant. No DB change.

### 4.10 Exit criteria

- [ ] `shared/canonical_schemas.py` `D26_HMM_OPPORTUNITY_STATE` constant has the ratification comment header
- [ ] `SHOW COLUMNS FROM p3_d26_hmm_opportunity_state` still returns exactly 9 columns (unchanged)
- [ ] `test_b4_d26_column_set_ratification` passes
- [ ] No code file references `p3_d26_hmm_states` (re-verify grep after this batch)

---

## Out of Scope / Known Follow-ups

### Reader/writer wiring for `p2_d07_regime_models` → Phase 7

Online B1 `_load_regime_models()` (`captain-online/.../b1_data_ingestion.py:313-332`) still synthesizes from `p3_d00_asset_universe.locked_strategy`. Migrating it to read from `p2_d07_regime_models` — and adding a P2-rerun completion writer — is Phase 7 scope (decisions log §5, Phase 7 row: "implement `captain_online_replay` for real").

### Q-26 pending: may add `p3_d06_aim_lifecycle_events` table

If Isaac's re-ask answer (§3.2 Q-26) creates a new lifecycle events table, a Phase 1b will add its DDL to `CANONICAL_DDLS`. No conflict with any of the four batches above.

### Q-27 pending: may add `raw_data_count` per-AIM column

If Isaac's re-ask answer (§3.2 Q-27) specifies a `raw_data_count` counter, a Phase 1b will add it to `p3_d01_aim_model_states` via `CANONICAL_MIGRATIONS`. No conflict.

### D3 staleness scoring (full Phase 9 work)

Batch 3 only wires the writer and the timestamp read in `compute_d3`. The full D3 scoring rewrite (D4 = monthly hit rate per Q-20, D7 deferral per Q-21, overall weighted mean per Q-34) is Phase 9.

### `paper_trader.py` hardcoded `"ES"` asset

Noted during Batch 2 writer audit. If `Position` carries `asset`, use `pos.asset`. If paper_trader.py is ES-only intentionally, the hardcoded `"ES"` + `model_m=7` (ES locked-strategy m from CLAUDE.md) is fine. **[UNVERIFIED — inspect `Position` dataclass in paper_trader.py before committing].**

---

## Test File Summary

All tests in this build plan land in `tests/test_schema_migrations.py` (create if absent). Import skeleton:

```python
"""Schema migration tests for Phase 1."""
import time
from datetime import datetime
import pytest
from shared.questdb_client import get_cursor
```

Total new tests: **10** (3 per Batch 1, 3 per Batch 2, 3 per Batch 3, 1 per Batch 4).

Run with:
```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/test_schema_migrations.py -v
```

These tests require a running QuestDB instance. If running on host without containers, set `QUESTDB_HOST=localhost` and ensure `init_questdb.py` has been run first.
