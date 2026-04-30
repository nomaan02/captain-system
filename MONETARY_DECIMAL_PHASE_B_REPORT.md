# QuestDB Decimal Migration — Phase B Report

**Authority:** `MONETARY_DECIMAL_MIGRATION_PLAN.md` (Phase B — D03 trade outcome log + Redis)

**Branch:** `migration/decimal-phase-b` (tip equivalent: commit below)

**Commit:** `42aa85b223a24fc698916f6a08564c42aceffb2e` (message: `migration(decimal): phase B — D03 trade outcome DECIMAL, streams, consumers`)

**Parent (Phase A tip):** `90006d7` — Phase A commit above

**Date (commit):** 2026-04-28

---

## 1. Executive summary

Phase B migrates **`p3_d03_trade_outcome_log`** prices to **`DECIMAL(14, 4)`** and P&L fields to **`DECIMAL(18, 4)`**; adds **M027–M033**; switches **Redis streams** to **`dumps_decimal`** / **`loads_decimal(..., coerce_json_int=False)`** so integers stay **`int`** and monetary values round-trip as **Decimal**; updates **B7** compute/INSERT, **`trade_source` / `RealisedOutcome`**, **paper trader**, **B6** daily sum, **B5c** rolling returns, **GUI** (B2 stringify + **`api._make_json_safe`** for WebSocket JSON), **offline orchestrator** and learning blocks (DMA, Kelly, CB params, B9 D4), **B4** `pseudo_results` encoding, **B6 reports** RPT-04/RPT-12; adds D03-focused tests.

**Downstream:** Phase C (`9105820` on `migration/decimal-phase-c`) assumes Phase B is applied; parent of Phase C commit is **`42aa85b`**.

---

## 2. B.1 Migration matrix

| Table | Columns | Target type |
|-------|---------|---------------|
| `p3_d03_trade_outcome_log` | `entry_price`, `signal_entry_price`, `exit_price` | `DECIMAL(14, 4)` |
| `p3_d03_trade_outcome_log` | `gross_pnl`, `commission`, `pnl`, `slippage` | `DECIMAL(18, 4)` |

**Unchanged:** `aim_modifier_at_entry` (DOUBLE) and other non-monetary fields per plan.

---

## 3. CANONICAL_MIGRATIONS appended (M027–M033)

| ID | Target |
|----|--------|
| **M027** | `entry_price` |
| **M028** | `signal_entry_price` |
| **M029** | `exit_price` |
| **M030** | `gross_pnl` |
| **M031** | `commission` |
| **M032** | `pnl` |
| **M033** | `slippage` |

---

## 4. Redis / JSON (Phase B Step 7)

- **`shared/redis_client.py`:** `publish_to_stream` uses **`dumps_decimal`**; **`read_stream`** / **`read_pending_stream`** use **`loads_decimal(..., coerce_json_int=False)`**.
- **`shared/decimal_json.py`:** **`dumps_decimal`** adds **`default=str`** (datetime-safe like prior `json.dumps(..., default=str)`); **`loads_decimal(..., coerce_json_int=False)`** keeps **`direction`** / **`contracts`** as **`int`**.
- **B7 `_publish_trade_outcome`:** payload includes **Decimal** monetary fields; serialised via stream encoder above.
- **`captain-command/.../api.py`:** **`_make_json_safe`** maps **`Decimal` → fixed-point string** for **`gui_push`**.

---

## 5. JSON STRING columns (Phase B §B.2)

| Column | Disposition |
|--------|----------------|
| **`p3_d03_trade_outcome_log.aim_breakdown_at_entry`** | **B7** writes with **`dumps_decimal`** when present. **B9** `compute_d4` and **B6** RPT-04 read with **`loads_decimal`** (with JSON fallback on parse errors). Mixed statistical + numeric content: dollar-ish numeric strings round-trip as **Decimal**; non-numeric strings unchanged. |
| **`p3_d06_injection_history.pseudo_results`** | **B4** `_store_injection` uses **`dumps_decimal(pseudo_results)`**. No dedicated read path in-repo at Phase B beyond JSON consumers updating as needed. |

---

## 6. File-level change log (`90006d7..42aa85b`)

**Totals:** 21 files changed, **+454 / −100** lines.

| File | + | − | Role |
|------|---|---|------|
| `captain-command/.../api.py` | 3 | 0 | `_make_json_safe` **Decimal** |
| `captain-command/.../b2_gui_data_server.py` | 14 | 5 | `_gui_money_json` for open/closed trades |
| `captain-command/.../b6_reports.py` | 25 | 10 | RPT-04 **`loads_decimal`**; RPT-12 float boundaries |
| `captain-offline/.../b1_dma_update.py` | 2 | 1 | `float(pnl)`, `float(modifier)` |
| `captain-offline/.../b4_injection.py` | 2 | 1 | **`dumps_decimal`** pseudo_results |
| `captain-offline/.../b8_cb_params.py` | 6 | 1 | **`float(pnl)`** in trade dict |
| `captain-offline/.../b8_kelly_update.py` | 1 | 1 | `float(pnl)` |
| `captain-offline/.../b9_diagnostic.py` | 12 | 5 | D4 **`loads_decimal`** breakdown |
| `captain-offline/.../orchestrator.py` | 33 | 9 | `_stream_numeric_float`; D03 return **`float`** boundaries |
| `captain-online/.../b5c_circuit_breaker.py` | 7 | 1 | Rolling **`float(pnl)`** |
| `captain-online/.../b6_signal_output.py` | 7 | 1 | Daily **`sum(pnl)`** → float |
| `captain-online/.../b7_position_monitor.py` | 59 | 16 | Decimal P&L path; **`dumps_decimal`** aim breakdown |
| `scripts/paper_trader.py` | 9 | 5 | Decimal D03 inserts; stream **Decimal** pnl |
| `shared/canonical_schemas.py` | 36 | 7 | D03 DDL + **M027–M033** |
| `shared/decimal_json.py` | 16 | 7 | `default=str`, **`coerce_json_int`** |
| `shared/redis_client.py` | 17 | 6 | Stream encode/decode |
| `shared/trade_source.py` | 54 | 24 | **`RealisedOutcome` Decimal** |
| `tests/test_d03_pnl_sum_precision.py` | 48 | 0 | SUM precision (**real_questdb**) |
| `tests/test_d03_reconciliation_precision.py` | 64 | 0 | gross − commission = net |
| `tests/test_d03_redis_roundtrip.py` | 30 | 0 | mocked Redis xadd round-trip |
| `tests/test_decimal_json.py` | 9 | 0 | **`coerce_json_int=False`** |

---

## 7. Tests (Phase B Step 9)

- **`tests/test_d03_redis_roundtrip.py`** — stream payload **Decimal** round-trip, **`coerce_json_int=False`**
- **`tests/test_d03_reconciliation_precision.py`** — **`RealisedOutcome`** / aggregate **`gross − commission = net`**
- **`tests/test_d03_pnl_sum_precision.py`** — many small **`pnl`** rows; **`SELECT sum(pnl)`** exact (**requires QuestDB**, **`real_questdb`**)
- **`tests/test_decimal_json.py`** — extended for stream mode

---

## 8. Known follow-ups (not fixed in migration)

- **B5c `_get_rolling_trade_returns`:** QuestDB query uses **`WHERE timestamp`** while table partition key is **`ts`**; failure may be swallowed by bare **`except`** — **separate defect**, called out in plan; **do not conflate with Decimal migration**.
- **Manual Step 10:** Run **`SELECT SUM(pnl), SUM(gross_pnl), SUM(commission), SUM(slippage)`** on production-like data post-migration; broker reconciliation if statements available.

---

## 9. Step 11 / Step 12 confirmation

- [x] **M027–M033** present; D03 DDL in **`canonical_schemas.py`** matches matrix
- [x] Redis path uses shared **`dumps_decimal` / `loads_decimal`**
- [x] Writer/reader inventory reflected in §6
- [x] Tests in §7; full **`pytest`** + **`init_questdb`** on clean DB = **operator validation**

**Phase B delivery commit:** `42aa85b`.
