# QuestDB Monetary Type Migration — Phase 1 Audit & Plan

**Scope:** Audit only (no schema or application code changes in this phase).  
**Environment:** QuestDB 9.3.3 per project context; canonical DDL in `shared/canonical_schemas.py`.  
**Date:** 2026-04-28

---

## 1. Environment summary

### 1.1 Canonical schema and migrations

| Item | Location |
|------|----------|
| Canonical DDL | `shared/canonical_schemas.py` — `CANONICAL_DDLS` list starts at ```789:837:shared/canonical_schemas.py``` |
| Additive migrations | `shared/canonical_schemas.py` — `CANONICAL_MIGRATIONS` ```845:886:shared/canonical_schemas.py``` |
| Highest migration ID (current) | **`M009_d06_add_tracking_days`** — last tuple in ```882:885:shared/canonical_schemas.py``` |
| Init runner | `scripts/init_questdb.py` applies `CANONICAL_DDLS` then each `CANONICAL_MIGRATIONS` entry ```15:37:scripts/init_questdb.py``` |

New DECIMAL column types will require: (1) updates to the `D00_*` / `D03_*` / etc. DDL strings in `canonical_schemas.py` for **greenfield** installs, and (2) **`ALTER TABLE ... ALTER COLUMN ... TYPE DECIMAL(p, s)`** entries appended to `CANONICAL_MIGRATIONS` for existing databases (per your implementation plan).

### 1.2 QuestDB drivers — inventory

| Driver | Where used | Role |
|--------|------------|------|
| **psycopg2** | `shared/questdb_client.py` ```13:46:shared/questdb_client.py``` | Primary PG-wire client: `get_connection`, `get_cursor`, D00 helpers |
| **psycopg2** | `scripts/init_questdb.py` (via `get_cursor` from shared) | Schema bootstrap |
| **psycopg2** | `scripts/compact_questdb_tables.py` ```21:83:scripts/compact_questdb_tables.py``` | Standalone connection for compaction |
| **psycopg2** | `scripts/replay_session.py` ```490:491:scripts/replay_session.py``` | Imported alongside `get_cursor` |
| **psycopg2** | `tests/test_schema_migrations.py` ```6:7:tests/test_schema_migrations.py``` | `OperationalError` handling |

**Search results:**

- **`psycopg` (v3) / `asyncpg` / `sqlalchemy`:** no matches in `*.py` across the repo (pattern: `import psycopg[^2]`, `asyncpg`, `sqlalchemy`).
- **QuestDB ILP (`questdb`, `ingress`, `Sender`):** no matches in `*.py` for ILP ingestion patterns.

**Conclusion:** Application and scripts use **PostgreSQL wire protocol via psycopg2** only. There is **no separate ILP writer path** in the scanned Python tree; migration strategy is **unified ALTER + parameterised inserts** from Python (ILP-specific migration work is **not** required based on this inventory).

---

## 2. Per-table inventory

Legend: **W** = writer (INSERT), **R** = reader (SELECT), **C** = computation before write, **L** = hardcoded numeric literal inside SQL text (excluding `%s` placeholders).

### 2.1 `p3_d03_trade_outcome_log` → DECIMAL columns per your matrix

| Kind | File:line | Notes |
|------|-----------|-------|
| **W** | `captain-online/captain_online/blocks/b7_position_monitor.py` ```311:324:captain-online/captain_online/blocks/b7_position_monitor.py``` | `INSERT INTO p3_d03_trade_outcome_log` — monetary columns via `%s` |
| **W** | `shared/trade_source.py` ```296:318:shared/trade_source.py``` | Synthetic seed `INSERT INTO p3_d03_trade_outcome_log` |
| **W** | `scripts/paper_trader.py` ```398:437:scripts/paper_trader.py``` | Open + close inserts (partial column lists) |
| **W** | `scripts/backfill_d03_signal_ids.py` ```44:54:scripts/backfill_d03_signal_ids.py``` | `REINSERT_SQL` — parameters only |
| **W** | `tests/test_schema_migrations.py` ```76:81:tests/test_schema_migrations.py```, ```97:101:tests/test_schema_migrations.py``` | Minimal INSERTs (model_m / legacy) |
| **W** | `tests/test_schema_d03_signal_id.py` | Multiple `INSERT INTO p3_d03_trade_outcome_log` blocks (files starts ```97:161:tests/test_schema_d03_signal_id.py``` region — inspect file for exact lines when implementing) |
| **C** | `captain-online/captain_online/blocks/b7_position_monitor.py` ```99:204:captain-online/captain_online/blocks/b7_position_monitor.py``` | `current_pnl`, `gross_pnl`, `net_pnl`, `slippage` from floats × `point_value` |
| **R** | `captain-online/captain_online/blocks/b6_signal_output.py` ```434:446:captain-online/captain_online/blocks/b6_signal_output.py``` | `SELECT sum(pnl) FROM p3_d03_trade_outcome_log` |
| **R** | `captain-online/captain_online/blocks/b5c_circuit_breaker.py` ```575:586:captain-online/captain_online/blocks/b5c_circuit_breaker.py``` | `SELECT pnl FROM p3_d03_trade_outcome_log WHERE timestamp ...` |
| **R** | `captain-command/captain_command/blocks/b2_gui_data_server.py` ```354:417:captain-command/captain_command/blocks/b2_gui_data_server.py``` | Open positions + closed trades — returns prices/pnl into GUI dicts |
| **R** | `shared/trade_source.py` ```384:418:shared/trade_source.py``` | `SELECT ... pnl, gross_pnl, commission ... FROM p3_d03_trade_outcome_log` |
| **R** | `shared/trade_source.py` ```422:439:shared/trade_source.py``` | `_row_to_outcome` — casts DB values with `float(...)` |
| **R** | `shared/aim16_observation_panel.py` ```89:106:shared/aim16_observation_panel.py``` | `sum(pnl)`, `entry_price` / `exit_price` / `signal_entry_price` in CASE |
| **R** | `captain-offline/captain_offline/blocks/orchestrator.py` | Multiple `pnl` / `contracts` SELECTs (grep hits ```736:1200:captain-offline/captain_offline/blocks/orchestrator.py``` region) |
| **R** | `captain-offline/captain_offline/blocks/b9_diagnostic.py` ```426:426:captain-offline/captain_offline/blocks/b9_diagnostic.py``` | `pnl`, `aim_breakdown_at_entry` |
| **R** | `captain-offline/captain_offline/blocks/b8_cb_params.py` ```44:44:captain-offline/captain_offline/blocks/b8_cb_params.py``` | `FROM p3_d03_trade_outcome_log` |
| **R** | `captain-offline/captain_offline/blocks/b3_pseudotrader.py` ```708:708:captain-offline/captain_offline/blocks/b3_pseudotrader.py``` | Trade history |
| **R** | `captain-offline/captain_offline/blocks/b1_aim_lifecycle.py` ```138:138:captain-offline/captain_offline/blocks/b1_aim_lifecycle.py``` | Count by asset |
| **R** | `shared/replay_engine.py` ```258:258:shared/replay_engine.py``` | Aggregates |
| **L** | No standalone SQL string in-repo was exhaustively enumerated with `column = 123.45`; most writes use bound parameters. Tests use Python floats bound via `%s` — driver sends typed params; **review any raw SQL string containing numeric literals** in migrations/fixtures during implementation. |

**Ambiguity / follow-up:** `b5c_circuit_breaker.py` filters on **`timestamp`** ```580:582:captain-online/captain_online/blocks/b5c_circuit_breaker.py``` while canonical D03 DDL names the designated timestamp column **`ts`** ```425:426:shared/canonical_schemas.py```. Failures are swallowed by `except`; confirm runtime behaviour vs QuestDB reserved names during implementation.

---

### 2.2 `p3_d08_tsm_state`

| Kind | File:line | Notes |
|------|-----------|-------|
| **W** | `captain-command/captain_command/blocks/b8_reconciliation.py` ```563:591:captain-command/captain_command/blocks/b8_reconciliation.py``` | Balance correction INSERT — monetary columns copied from SELECT |
| **W** | `captain-command/captain_command/blocks/b8_reconciliation.py` ```655:682:captain-command/captain_command/blocks/b8_reconciliation.py``` | `topstep_state` persist — same INSERT shape |
| **W** | `captain-command/captain_command/blocks/b4_tsm_manager.py` ```416:436:captain-command/captain_command/blocks/b4_tsm_manager.py``` | New TSM row from dict `tsm.get("starting_balance", 0)` etc. ```392:414:captain-command/captain_command/blocks/b4_tsm_manager.py``` |
| **W** | `captain-offline/captain_offline/blocks/b7_tsm_simulation.py` ```132:158:captain-offline/captain_offline/blocks/b7_tsm_simulation.py``` | INSERT after MC / pass_probability path |
| **W** | `scripts/fix_bootstrap_data.py` ```167:188:scripts/fix_bootstrap_data.py``` | INSERT with **inline SQL literals** `0.0`, `0.0`, `0.0` in VALUES ```177:179:scripts/fix_bootstrap_data.py``` — needs `m` suffix or parameters when columns are DECIMAL |
| **R** | `captain-command/captain_command/blocks/b8_reconciliation.py` ```533:551:captain-command/captain_command/blocks/b8_reconciliation.py``` | Full-row SELECT for rewrite |
| **R** | `captain-online/captain_online/blocks/b1_data_ingestion.py` ```241:241:captain-online/captain_online/blocks/b1_data_ingestion.py``` | `FROM p3_d08_tsm_state` |
| **R** | `captain-command/captain_command/main.py` ```90:90:captain-command/captain_command/main.py``` | `count()` |
| **R** | `captain-command/captain_command/blocks/b2_gui_data_server.py` | Multiple SELECTs · lines ~185–1554 (grep `p3_d08_tsm_state`) |
| **R** | `scripts/replay_session.py` ```548:548:scripts/replay_session.py``` | Replay bootstrap |
| **R** | `scripts/verify_questdb_state.py` ```693:737:scripts/verify_questdb_state.py``` | Health thresholds on balances |

---

### 2.3 `p3_d16_user_capital_silos`

| Kind | File:line | Notes |
|------|-----------|-------|
| **W** | `captain-online/captain_online/blocks/b7_position_monitor.py` ```377:387:captain-online/captain_online/blocks/b7_position_monitor.py``` | INSERT after `new_capital = (d16_row[3] or 0) + net_pnl` ```356:363:captain-online/captain_online/blocks/b7_position_monitor.py``` |
| **W** | `captain-command/captain_command/main.py` ```213:221:captain-command/captain_command/main.py``` | Telegram chat_id merge INSERT |
| **W** | `scripts/bootstrap_production.py` ```227:245:scripts/bootstrap_production.py``` | Bootstrap INSERT (`max_portfolio_risk_pct` etc. literals `0.10`, `0.70` — **not** in your DECIMAL migrate list) |
| **W** | `scripts/seed_test_asset.py` ```115:133:scripts/seed_test_asset.py``` | `starting_capital`, `total_capital` via `%s` |
| **R** | `captain-online/captain_online/blocks/b7_position_monitor.py` ```337:346:captain-online/captain_online/blocks/b7_position_monitor.py``` | LATEST ON read |
| **R** | `captain-command/captain_command/main.py` ```185:204:captain-command/captain_command/main.py``` | SELECT for telegram update |
| **R** | `captain-online/captain_online/blocks/orchestrator.py` ```864:864:captain-online/captain_online/blocks/orchestrator.py``` | GUI/orchestration |
| **R** | `scripts/bootstrap_production.py` ```216:218:scripts/bootstrap_production.py``` | `SELECT starting_capital` |
| **R** | `scripts/replay_full_pipeline.py` ```196:196:scripts/replay_full_pipeline.py``` | Replay |

---

### 2.4 `p3_d28_account_lifecycle`

| Kind | File:line | Notes |
|------|-----------|-------|
| **DDL only** | `shared/canonical_schemas.py` ```596:619:shared/canonical_schemas.py``` | Table defined; comment notes planned integration |
| **W** | — | **No `INSERT INTO p3_d28` found** in `*.py` under `captain-command/`, `captain-online/`, `captain-offline/`, `shared/`, `scripts/`, `tests/` |

**Implication:** migrating D28 is **schema-forward** today; **no Python writer** to update until `account_lifecycle` → QuestDB persistence is implemented. Runtime logic for dollar amounts exists in **`shared/account_lifecycle.py`** (dataclasses) — see §3.

---

### 2.5 `p3_d00_asset_universe`

| Kind | File:line | Notes |
|------|-----------|-------|
| **W** | `shared/questdb_client.py` ```169:189:shared/questdb_client.py``` | `update_d00_fields` — full-row INSERT from merged dict |
| **W** | `scripts/bootstrap_production.py` ```181:181:scripts/bootstrap_production.py``` | Dynamic INSERT |
| **W** | `scripts/load_p2_multi_asset.py` ```281:281:scripts/load_p2_multi_asset.py``` | INSERT |
| **W** | `scripts/seed_all_assets.py` ```197:197:scripts/seed_all_assets.py``` | INSERT |
| **W** | `scripts/seed_real_asset.py` ```311:311:scripts/seed_real_asset.py``` | INSERT |
| **W** | `scripts/seed_test_asset.py` ```56:79:scripts/seed_test_asset.py``` | ES seed — `point_value`, `tick_size`, `margin_per_contract` as Python literals in tuple |
| **R** | `shared/questdb_client.py` ```152:156:shared/questdb_client.py``` | `read_d00_row` SELECT |
| **R** | Widespread | `b7_position_monitor`, `b1_features`, `b1_data_ingestion`, `b2_gui_data_server`, orchestrator, paper_trader, etc. (grep: `p3_d00_asset_universe`) |

---

### 2.6 `p3_d30_daily_ohlcv`

| Kind | File:line | Notes |
|------|-----------|-------|
| **W** | `captain-online/captain_online/blocks/b1_features.py` ```1500:1506:captain-online/captain_online/blocks/b1_features.py``` | `float(opn)`, `float(high)`, etc. bound as parameters |
| **W** | `scripts/restore_live_delta.py` ```136:156:scripts/restore_live_delta.py``` | `executemany` with `float(...)` for OHLC |
| **W** | `scripts/seed_ohlcv_from_qc.py` | Grep hits lines 58, 101 — inspect for INSERT shape |
| **R** | `shared/aim_feature_loader.py` ```136:157:shared/aim_feature_loader.py``` | OHLC for features — arithmetic on `prev_close`, `curr_open` |
| **R** | `shared/online_replay_providers.py` | Multiple `close` SELECTs |
| **R** | `captain-online/captain_online/blocks/b1_features.py` ```1006:1206:captain-online/captain_online/blocks/b1_features.py``` | Feature baselines |

---

## 3. Affected models (dataclasses / typed structures)

| Type | Location | Current | Required after DECIMAL read path |
|------|----------|---------|----------------------------------|
| `RealisedOutcome` | `shared/trade_source.py` ```338:358:shared/trade_source.py``` | `pnl`, `gross_pnl`, `commission`, `entry_price`, `exit_price`: `float` | Prefer `Decimal` for monetary fields **or** normalise at DB boundary with explicit `float(Decimal)` only where JSON/contracts require floats |
| `LifecycleEvent` (and related account types) | `shared/account_lifecycle.py` ```175:181:shared/account_lifecycle.py``` | `balance_at_event`, `fee_charged`, `payout_*`, `tradable_balance`, `reserve_balance`: `float` | Align with D28 DECIMAL when persistence lands |
| Topstep account dataclasses | `shared/account_lifecycle.py` ```70:181:shared/account_lifecycle.py``` | Various `float` balances / limits | Same — spec alignment |

**Pydantic:** `captain-command/captain_command/api.py` uses `BaseModel` for requests ```585:593:captain-command/captain_command/api.py```; **`ValidateInputRequest.value: float`** is generic — **not** tied to QuestDB columns. **No dedicated Pydantic model** for D03/D08 rows was found in the audited paths; GUI payloads are mostly **`dict`** assembled from SQL rows.

---

## 4. Affected tests (representative list)

| Area | Files | Update type |
|------|-------|-------------|
| D03 helper / PG-09 | `tests/test_actual_trade_outcome.py` | Mock rows use floats; assertions on `== 12.5` etc. ```53:79:tests/test_actual_trade_outcome.py``` — extend for `Decimal` or keep mocks as floats + boundary casts |
| Signal / trade pipeline | `tests/test_signal_id_flow.py`, `tests/test_g_off_016_resolution.py`, `tests/test_pg09_pseudotrader.py` | Construct `RealisedOutcome`-like data with floats |
| Circuit breaker | `tests/test_b5c_circuit.py` | `current_balance`, `point_value` kwargs ```91:570:tests/test_b5c_circuit.py``` |
| Integration | `tests/test_integration_e2e.py`, `tests/test_trade_closed_pipeline.py` | PnL assertions |
| Fixtures | `tests/fixtures/user_fixtures.py`, `tests/fixtures/synthetic_data.py` | `total_capital`, `point_value` defaults |
| Schema / migrations | `tests/test_schema_migrations.py`, `tests/test_schema_d03_signal_id.py` | INSERT round-trips — verify psycopg2 returns `Decimal` for DECIMAL columns |
| Account lifecycle | `tests/test_account_lifecycle.py` | Float balances throughout |

---

## 5. Phased implementation plan

### Phase A — D08 + D28 (regulatory thresholds + lifecycle schema)

| Workstream | Files / areas | Effort | Risk |
|------------|---------------|--------|------|
| DDL + migrations | `shared/canonical_schemas.py` — `D08_TSM_STATE` ```213:249:shared/canonical_schemas.py```; append `CANONICAL_MIGRATION` ALTERs; `D28_ACCOUNT_LIFECYCLE` ```599:619:shared/canonical_schemas.py``` | Medium | **High** — TSM drives breaker comparisons |
| Writers | `b8_reconciliation.py`, `b4_tsm_manager.py`, `b7_tsm_simulation.py`, `fix_bootstrap_data.py` | Medium | **High** |
| Readers | GUI, `verify_questdb_state.py`, ingestion | Medium | Medium |
| D28 | Schema only until writers exist — **`shared/account_lifecycle.py`** types in same phase when Isaac confirms persistence | Low–Medium | Low until wired |

### Phase B — D03 (trade outcome log)

| Workstream | Files / areas | Effort | Risk |
|------------|---------------|--------|------|
| Computation | `b7_position_monitor.py` resolve path ```171:204:captain-online/captain_online/blocks/b7_position_monitor.py``` | Medium | **High** — volume of float math |
| Writers + seed | `trade_source.py`, `paper_trader.py`, `backfill_d03_signal_ids.py`, tests | Medium | Medium |
| Aggregates | `b6_signal_output.py` `sum(pnl)` ```440:441:captain-online/captain_online/blocks/b6_signal_output.py``` | Low | Medium |

### Phase C — D16 + D00 + D30

| Workstream | Files / areas | Effort | Risk |
|------------|---------------|--------|------|
| D16 | `b7_position_monitor.py` `_update_capital_and_cb`, `main.py`, bootstrap scripts | Medium | Medium |
| D00 | `questdb_client.update_d00_fields`, all seed scripts | Medium | Medium |
| D30 | `b1_features.store_daily_ohlcv`, `restore_live_delta`, `aim_feature_loader` | Medium | Medium–Low |

**Cross-cutting for every phase**

- **`Decimal(str(x))`** when converting from uncertain floats before INSERT.
- **JSON / Redis:** trade outcomes in `b7_position_monitor.py` `_publish_trade_outcome` ```399:429:captain-online/captain_online/blocks/b7_position_monitor.py``` — ensure serialisation (`default=str` or decimal encoder).
- **SQL literals:** replace inline floats in SQL text with **`Nm` DECIMAL literals** where literals remain (e.g. `fix_bootstrap_data.py` ```177:179:scripts/fix_bootstrap_data.py```).

---

## 6. Open questions

1. **`p3_d23_circuit_breaker_intraday.l_t`** — Is this a **dollar cumulative PnL** (then DECIMAL) or a **normalised statistic**? **Do not assume;** confirm with Isaac/spec. (Reader/writer: `b7_position_monitor.py` ```349:371:captain-online/captain_online/blocks/b7_position_monitor.py```.)

2. **`p3_d25_circuit_breaker_params.l_star`** — Same question: **dollar-equivalent threshold** vs **normalised**? Schema: ```324:338:shared/canonical_schemas.py```.

3. **D03 query column `timestamp` vs `ts`** in `b5c_circuit_breaker.py` ```580:582:captain-online/captain_online/blocks/b5c_circuit_breaker.py``` — verify against live QuestDB and fix if dead/broken.

4. **D28** — No writer exists; confirm whether Phase A includes **DDL-only** migration or **blocked** until account lifecycle persistence is specified.

5. **`p3_d19_reconciliation_log`** — Not in your seven-table list; mismatch column is JSON (`mismatches`) in `b8_reconciliation.py` ```715:717:captain-command/captain_command/blocks/b8_reconciliation.py``` — confirm if separate DECIMAL work is needed for stored snapshot fields.

---

## 7. Rollback strategy

1. **Per-phase forward migration:** Keep each `CANONICAL_MIGRATIONS` entry **reversible** via companion `ALTER COLUMN ... TYPE DOUBLE` scripts (QuestDB supports type change; validate on 9.3.3 staging with a **copy** of production volume).

2. **Order of rollback:** Reverse **Phase C → B → A** if production issues appear, restoring DOUBLE on those columns **after** stopping writers that emit DECIMAL.

3. **Data:** DECIMAL → DOUBLE may introduce **rounding** when casting narrow monetary values; snapshot **backup tables** (`backup_live_tables.py` pattern) before each phase.

4. **Application rollback:** Redeploy previous Python version that still uses `float` **only after** columns are DOUBLE again, or keep `Decimal` tolerance in reader layer (prefer schema rollback for consistency).

---

## 8. Anti-hallucination notes (this audit)

- Every file path above was obtained from **repository grep/read** in this session; if a line range drifted after the audit date, re-grep.
- **No ILP client** was found in `*.py`; if a service outside this tree uses ILP, it was **not** in the search scope.
- **`INSERT INTO p3_d28`** — **no results** in Python code; stated explicitly in §2.4.

---

*End of Phase 1 audit document.*
