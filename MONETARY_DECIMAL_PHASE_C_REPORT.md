# QuestDB Decimal Migration — Phase C Report

**Authority:** `MONETARY_DECIMAL_MIGRATION_PLAN.md` (Phase C — capital silos, asset constants, daily OHLCV)

**Branch:** `migration/decimal-phase-c`

**Commit:** `910582016fb6f1ce579aef5163289d6492967399`

**Parent (pre–Phase C work tree):** `42aa85b223a24fc698916f6a08564c42aceffb2e` (on `migration/decimal-phase-b`)

**Date:** 2026-04-28

---

## 1. Executive summary

Phase C migrates **D16** capital columns, **D00** contract-economics columns, and **D30** OHLC price columns to QuestDB `DECIMAL` types; updates canonical DDL and append-only migration alters **M034–M042**; routes bootstrap **`capital_history`** through **`dumps_decimal`**; upgrades **seed/restore/b1** writers to bind **Decimal**; converts **AIM OHLC feature** and **B5C rho_j** math to **Decimal**-safe paths; adjusts **B4 Kelly** for **Decimal** silo capital and **float** `point_value` for sizing; updates **test fixtures**; adds **round-trip, JSON, and P&L precision** tests.

**Merge to `main`:** not done (awaiting explicit approval per plan).

---

## 2. C.1 Migration matrix (plan compliance)

| Table | Columns migrated | Target type | DDL + migrations |
|-------|------------------|-------------|------------------|
| `p3_d16_user_capital_silos` | `starting_capital`, `total_capital` | `DECIMAL(18, 2)` | `D16_USER_CAPITAL_SILOS` in `shared/canonical_schemas.py`; **M034**, **M035** |
| `p3_d00_asset_universe` | `point_value`, `tick_size`, `margin_per_contract` | `DECIMAL(14, 4)` | `D00_ASSET_UNIVERSE`; **M036–M038** |
| `p3_d30_daily_ohlcv` | `open`, `high`, `low`, `close` | `DECIMAL(14, 4)` | `D30_DAILY_OHLCV`; **M039–M042** |

**Unchanged (per plan):** D16 `max_portfolio_risk_pct`, `correlation_threshold`, `user_kelly_ceiling` (DOUBLE); D00 `warm_up_progress` (DOUBLE); D30 `volume` (LONG).

---

## 3. CANONICAL_MIGRATIONS appended (M034–M042)

All entries are in `shared/canonical_schemas.py` after **M033**, under the comment `# Phase C — capital silos…`.

```text
M034_d16_starting_capital_to_decimal      ALTER TABLE p3_d16_user_capital_silos ALTER COLUMN starting_capital TYPE DECIMAL(18, 2)
M035_d16_total_capital_to_decimal         ALTER TABLE p3_d16_user_capital_silos ALTER COLUMN total_capital TYPE DECIMAL(18, 2)
M036_d00_point_value_to_decimal           ALTER TABLE p3_d00_asset_universe ALTER COLUMN point_value TYPE DECIMAL(14, 4)
M037_d00_tick_size_to_decimal             ALTER TABLE p3_d00_asset_universe ALTER COLUMN tick_size TYPE DECIMAL(14, 4)
M038_d00_margin_per_contract_to_decimal   ALTER TABLE p3_d00_asset_universe ALTER COLUMN margin_per_contract TYPE DECIMAL(14, 4)
M039_d30_open_to_decimal                  ALTER TABLE p3_d30_daily_ohlcv ALTER COLUMN open TYPE DECIMAL(14, 4)
M040_d30_high_to_decimal                  ALTER TABLE p3_d30_daily_ohlcv ALTER COLUMN high TYPE DECIMAL(14, 4)
M041_d30_low_to_decimal                   ALTER TABLE p3_d30_daily_ohlcv ALTER COLUMN low TYPE DECIMAL(14, 4)
M042_d30_close_to_decimal                 ALTER TABLE p3_d30_daily_ohlcv ALTER COLUMN close TYPE DECIMAL(14, 4)
```

---

## 4. C.2 JSON — `capital_history` and `accounts`

| Column | Disposition |
|--------|--------------|
| `p3_d16_user_capital_silos.capital_history` | **Migrated behaviour:** **`dumps_decimal`** for the initial-bootstrap payload in **`scripts/bootstrap_production.py`** (phase 2 INSERT). See **`dumps_decimal` call ~246–249** in current file (lines shift if edited later). |
| `p3_d16_user_capital_silos.accounts` | **No encoder change.** Content remains account IDs/metadata (`json.dumps(...)` lists). Matches plan (“purely IDs and metadata”). |

Encoder implementation remains **`shared/decimal_json.py`** (Phase F1); no duplicate encoder introduced.

---

## 5. File-level change log (diff stats per file)

From **`git show 9105820 --stat`** — **17 files**, **+366 / −83** lines total.

| File | Insertions | Deletions | Role in Phase C |
|------|------------|-----------|------------------|
| `shared/canonical_schemas.py` | 55 | 20 | DDL + **M034–M042** |
| `tests/test_phase_c_decimal_roundtrip.py` | 141 | 0 | D16/D00/D30 round-trip (**real_questdb**) |
| `shared/aim_feature_loader.py` | 67 | 24 | **`_d_price`**, Decimal OHLC / correlation path |
| `captain-online/.../b4_kelly_sizing.py` | 29 | 13 | **`_silo_money`**, drawdown **`Decimal`**; **`float(asset_detail point_value)`** |
| `scripts/bootstrap_production.py` | 22 | 7 | **`Decimal`** D00 merge + **`STARTING_CAPITAL`** **`Decimal`** + **`dumps_decimal`** capital_history |
| `scripts/seed_ohlcv_from_qc.py` | 17 | 11 | **`Decimal(str(...))`** OHLC payloads |
| `tests/fixtures/user_fixtures.py` | 17 | 6 | **`make_user_silo`** / **`make_silo_drawdown_blocked`** **Decimal** capitals |
| `scripts/seed_test_asset.py` | 8 | 5 | D00/D16 **`Decimal`** inserts |
| `captain-online/.../b5c_circuit_breaker.py` | 9 | 3 | **`_pv`** + **`rho_j`** ( **`float \| Decimal` point_value** ) |
| `tests/fixtures/synthetic_data.py` | 11 | 4 | **`make_assets_detail`** **Decimal** defaults |
| `scripts/load_p2_multi_asset.py` | 7 | 2 | D00 INSERT **Decimal(str(meta[...]))** |
| `scripts/restore_live_delta.py` | 9 | 4 | **`Decimal(str(...))`** D30 CSV columns |
| `scripts/seed_all_assets.py` | 6 | 2 | **`Decimal(str(spec[...]))`** D00 |
| `scripts/seed_real_asset.py` | 6 | 3 | **`Decimal`** D00 literals |
| `captain-online/.../b1_features.py` | 6 | 3 | **`Decimal(str(...))`** daily OHLC insert |
| `tests/test_phase_c_e2e_pnl_precision.py` | 23 | 0 | ES trade **Decimal** formula test |
| `tests/test_phase_c_capital_history_json_roundtrip.py` | 16 | 0 | **`dumps_decimal` / `loads_decimal`** |

---

## 6. Detailed citations (`file` + line ranges for substantive edits)

Line numbers refer to **`9105820`** (use `git show 9105820:<path>` if your tree differs).

### 6.1 Schema

- **`shared/canonical_schemas.py`**: `D00_ASSET_UNIVERSE` — **`point_value` / `tick_size` / `margin_per_contract`** → **`DECIMAL(14, 4)`** (approx. lines **88–90** region in CREATE block).
- **`shared/canonical_schemas.py`**: `D16_USER_CAPITAL_SILOS` — **`starting_capital` / `total_capital`** → **`DECIMAL(18, 2)`** (approx. **298–300** region).
- **`shared/canonical_schemas.py`**: `D30_DAILY_OHLCV` — **`open/high/low/close`** → **`DECIMAL(14, 4)`** (approx. **643–646** region).
- **`shared/canonical_schemas.py`**: **`CANONICAL_MIGRATIONS`** — **M034–M042** (approx. lines **986–1023**).

### 6.2 Writers (plan Step 4)

- **`scripts/bootstrap_production.py`**: **`phase1_update_d00`** — updates dict **`point_value` / `tick_size` / `margin_per_contract`** bound as **`Decimal(str(...))`** (see **`updates`** block ~**157–159** region); **`phase2_update_capital_silo`** **`INSERT`** — **`STARTING_CAPITAL`** **`Decimal`**, **`dumps_decimal`** for **`capital_history`** (~**229–251**).
- **`scripts/seed_test_asset.py`**: **`seed_es_asset`** / **`seed_capital_silo`** — **`Decimal`** for D00/D16 monetary literals (~**71–131** region).
- **`scripts/seed_all_assets.py`**: **`register_asset`** **`INSERT`** — **`Decimal(str(...))`** (~**212–217**region).
- **`scripts/seed_real_asset.py`**: **`_ensure_asset_registered`** **`INSERT`** — **`Decimal("50")`** etc. (~**331–333** region).
- **`scripts/load_p2_multi_asset.py`**: **`INSERT p3_d00`** — **`Decimal(str(meta[...]))`** (~**307–309** region).
- **`scripts/restore_live_delta.py`**: **`restore_d30`** — tuple uses **`Decimal(str(row[...]))`** for OHLC (~**148–157** region).
- **`scripts/seed_ohlcv_from_qc.py`**: **`seed_from_combined` / `seed_from_per_asset`** — row dicts use **`Decimal(str(...))`** for OHLC.
- **`captain-online/.../b1_features.py`**: **`_store_daily_ohlcv`** (persist daily bar) — **`INSERT`** uses **`Decimal(str(...))`** for OHLC (~**1499–1507** region).
- **`captain-online/.../b7_position_monitor.py`**: **no diff in Phase C commit.** D16 **`INSERT`** / **`Decimal`** **`new_capital`** path was already aligned with Decimal math from earlier phases; verified compatible with DECIMAL columns.

### 6.3 Computation / cleanup (plan Step 5)

- **`captain-online/.../b5c_circuit_breaker.py`**: **`_check_all_layers`** — **`_pv = point_value if isinstance(point_value, Decimal) else Decimal(str(point_value))`**; **`rho_j`** uses **`_pv`** (~**231–236**).
- **`shared/aim_feature_loader.py`**: **`_d_price`** (~**30–36**); **`_load_ohlcv_features`** — **`Decimal`** pipelines for overnight / **`cross_momentum`** / **`correlation_z`** return series (**~158–229** regions); VRP fallback uses **`float(_d_price(r[0]))`** where needed.
- **Phase B `Decimal(str(point_value))` removal:** codebase had **no** remaining **`Decimal(str(point_value))`** except B5C; that site updated as above (**grep**-verified at delivery time).

### 6.4 Readers / consumers

- **`captain-online/.../b4_kelly_sizing.py`**: **`_silo_money`** (~**44–50**); Step 0 drawdown uses **`Decimal("1") - (total/starting)`** vs **`Decimal(str(max_silo_dd))`** (~**83–95**); per-asset **`point_value = float(asset_detail.get(...))`** (~**175** region); **`max_risk`** uses **`float(total_capital)`** (~**268** region).
- **`shared/questdb_client.py`**, **`captain-command/.../main.py`**, **`captain-online/.../orchestrator.py`**, **`scripts/replay_full_pipeline.py`**, **`b1_data_ingestion`**, **`paper_trader`**, **`b2_gui_data_server`**: **No edits in Phase C commit.** **Rationale:** reads receive **`Decimal`** from psycopg2; **`float(...)`**, **`json.loads`**, and formatting either accept **`Decimal`** or remain correct; **`b7_position_monitor`** **`_money_d`** already normalises **`point_value`** for P&L.

### 6.5 Test fixtures (plan Step 9)

- **`tests/fixtures/user_fixtures.py`**: **`make_user_silo`** — **`starting_capital` / `total_capital`** defaults **`Decimal`**; **`make_silo_drawdown_blocked`** — **`Decimal`** literals.
- **`tests/fixtures/synthetic_data.py`**: **`make_assets_detail`** — **`point_value` / `tick_size` / `margin_per_contract`** **`Decimal`**.

---

## 7. Tests added (Phase C Step 9)

| Test module | Marker | Purpose |
|-------------|--------|---------|
| `tests/test_phase_c_decimal_roundtrip.py` | **`@pytest.mark.real_questdb`** | Insert/select **D16**, **D00**, **D30** monetary columns; assert **`Decimal(str(...))`** equality. |
| `tests/test_phase_c_capital_history_json_roundtrip.py` | (none) | **`dumps_decimal` / `loads_decimal`** preserves **`capital`** **`Decimal`** in list payloads. |
| `tests/test_phase_c_e2e_pnl_precision.py` | (none) | Closed-form ES P&L (**entry/exit/dir/contracts/point_value/commission**) — exact **`Decimal`** result (formula-level “no drift”). |

**Regression spot-check (non-QuestDB, `PYTHONPATH=.`):** `test_b4_kelly`, `test_b5c_circuit`, `test_decimal_json` exercised together with Phase C modules — **53 passed** in the implementation environment.

---

## 8. Phase C Step 10 — validation status

| Gate item | Status |
|-----------|--------|
| **Static checks** (`py_compile` on touched modules) | **Done** in implementation environment. |
| **Schema migration dry-run** (`init_questdb` + **`SHOW COLUMNS`** for D16/D00/D30) | **Not run here** — requires live QuestDB / CI container matching project procedure. |
| **Unit/integration suite full** | **Partial:** targeted **`pytest`** with **`PYTHONPATH=.`**; full repo **`pytest`** not run (environment/import constraints). |
| **End-to-end pipeline** (plan: D00 → D30 → D03 → D08 → D23 with **`type()`** boundary checks) | **Not automated in this branch.** Covered in part by **`test_phase_c_e2e_pnl_precision`** (formula only). **Recommend** follow-up integration test or manual smoke per deployment checklist. |
| **Cleanup: Phase B `Decimal(str(point_value))`** | **Confirmed** redundant pattern removed/superseded as in §6.3. |

---

## 9. Plan cross-check — files listed in Phase C §C.3 with no Phase C commit hunk

The plan cites several locations for completeness; the following **required no code change in Phase C** once DECIMAL types and callers above were verified:

| Plan reference | Finding |
|----------------|---------|
| **`b7_position_monitor.py`** (D16 read/write) | Already **`Decimal`** for **`net_pnl`** / **`new_capital`**; compatible with **`DECIMAL`** columns. |
| **`main.py`** (D16 SELECT/INSERT) | Bound values remain valid; psycopg2 **`Decimal`** round-trip. |
| **`orchestrator.py` / `replay_full_pipeline.py`** (D16 read) | **`float(...)`** / **`f"{...:,.0f}"`** work with **`Decimal`** inputs. |
| **`read_d00_row` / `update_d00_fields`** | Pass-through dicts; **`Decimal`** in **`updates`** from **`bootstrap_production`**. |
| **`online_replay_providers.py`** (D30 **`close`**) | **`float(row[0])`** accepts **`Decimal`**. |
| **`b1_features.py` 1006–1206** | SQL unchanged; cell types now **`Decimal`** at driver; consumer paths use **`float`** where needed or unchanged. |

If any of these surfaces a runtime issue after **`ALTER`**, treat as a **bugfix follow-up** with a focused diff (not assumed in this report).

---

## 10. Anomalies / follow-ups

1. **Full-stack Step 10 pipeline test** (D00 → D03 → D08 → D23) is **not** in-repo; recommend before production cutover.
2. **`accounts` JSON** stays plain **`json.dumps`** — **intentional** per plan (non-monetary).
3. **Merge discipline:** do **not** merge **`migration/decimal-phase-c`** to **`main`** until you explicitly approve (per migration plan).

---

## 11. Approval checkpoint

Phase C implementation is **complete on branch `migration/decimal-phase-c` at `9105820`**, pending:

- [ ] Your **approval** to merge (or to open PR).
- [ ] **QuestDB-backed** run of **`test_phase_c_decimal_roundtrip`** and **`init_questdb`** migration apply on a test instance.
- [ ] Optional: **Step 10** full pipeline integration test or documented manual smoke.

---

*End of Phase C report.*
