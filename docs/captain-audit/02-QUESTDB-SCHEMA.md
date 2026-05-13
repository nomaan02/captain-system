# 02 — QuestDB schema

**TL;DR**

- DDL lives in `shared/canonical_schemas.py`; **`scripts/init_questdb.py`** applies `CANONICAL_DDLS` + `CANONICAL_MIGRATIONS`.
- This doc enumerates **DECIMAL** columns verified by grep at audit commit — everything else is `DOUBLE`/strings/etc. per same file.
- Not covered here: application SELECT ergonomics — use QuestDB console or `.tables`.

**Audit stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`

## 02.1 Source of truth chain

| Layer | File | Lines (indicative) | Role |
|-------|------|-------------------|------|
| Canonical DDL | `shared/canonical_schemas.py` | 77–841 (`CANONICAL_DDLS`) | CREATE TABLE bodies |
| Migrations | `shared/canonical_schemas.py` | 849–1055 (`CANONICAL_MIGRATIONS`) | Idempotent ALTER / ADD |
| Applier | `scripts/init_questdb.py` | 18–60 | Executes DDL then migrations |
| Typed INSERT helper | `shared/questdb_client.py` | 78–95 + `qexecute` | DECIMAL cast + column-type coercion via `COLUMN_TYPES` (~1065+) |

## 02.2 DECIMAL columns (CREATE TABLE bodies)

All `(column, precision)` pairs below are **verbatim** from `shared/canonical_schemas.py` at audit.

| Table (constant) | Column | Type |
|------------------|--------|------|
| `p3_d00_asset_universe` | point_value | DECIMAL(14, 6) |
| | tick_size | DECIMAL(14, 8) |
| | margin_per_contract | DECIMAL(14, 6) |
| `p3_d08_tsm_state` | starting_balance | DECIMAL(18, 2) |
| | current_balance | DECIMAL(18, 2) |
| | current_drawdown | DECIMAL(18, 2) |
| | daily_loss_used | DECIMAL(18, 2) |
| | profit_target | DECIMAL(18, 2) |
| | max_drawdown_limit | DECIMAL(18, 2) |
| | max_daily_loss | DECIMAL(18, 2) |
| | commission_per_contract | DECIMAL(18, 2) |
| | margin_per_contract | DECIMAL(18, 2) |
| `p3_d16_user_capital_silos` | starting_capital | DECIMAL(18, 2) |
| | total_capital | DECIMAL(18, 2) |
| `p3_d25_circuit_breaker_params` | l_star | DECIMAL(18, 2) |
| `p3_d23_circuit_breaker_intraday` | l_t | DECIMAL(18, 2) |
| | effective_l_halt | DECIMAL(18, 2) *(migration M044)* |
| | effective_e_exposure | DECIMAL(18, 2) *(M045)* |
| `p3_d03_trade_outcome_log` | entry_price | DECIMAL(14, 6) |
| | signal_entry_price | DECIMAL(14, 6) |
| | exit_price | DECIMAL(14, 6) |
| | gross_pnl | DECIMAL(18, 4) |
| | commission | DECIMAL(18, 4) |
| | pnl | DECIMAL(18, 4) |
| | slippage | DECIMAL(18, 4) |
| `p3_d28_account_lifecycle` | balance_at_event | DECIMAL(18, 2) |
| | fee_charged | DECIMAL(18, 2) |
| | payout_amount | DECIMAL(18, 2) |
| | payout_net | DECIMAL(18, 2) |
| | tradable_balance | DECIMAL(18, 2) |
| | reserve_balance | DECIMAL(18, 2) |
| `p3_d30_daily_ohlcv` | open/high/low/close | DECIMAL(14, 6) each |

**Line anchors for DDL excerpts:** D00 ~88–90, D08 ~219–232, D16 ~299–300, D25 ~334, D23 ~387–392, D03 ~412–419, D28 ~612–618, D30 ~647–650.

## 02.3 Migration history (high level)

`CANONICAL_MIGRATIONS` entries **M001–M047** — additive columns + DECIMAL conversions + D23 session budgeting (`M043–M047`, see header comment ~1027–1054).

Verify applied migrations (tower):

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T captain-command \
  sh -c 'PGPASSWORD=quest psql -h questdb -p 8812 -U admin -d qdb -c "SHOW TABLES;"'
```

## 02.4 Known schema-documented risks

From module docstring `shared/canonical_schemas.py` ~43–67:

| Flag | Detail |
|------|--------|
| D21 column naming | Mixed `timestamp` vs `ts` writers |
| D33 typing | STRING dates vs TIMESTAMP expectation |
| D29/D30 | Strings retained deliberately |

Cross-link issues: [09](09-KNOWN-ISSUES.md).

## 02.5 DECIMAL runtime casting policy

`shared/questdb_client.py` registers a psycopg2 `Decimal` adapter (~66–69) emitting `cast('…' as DECIMAL(p,s))` sized per value (~40–63) to avoid QuestDB short-literal parser faults documented inline (~23–39).

**Verify casting smoke:**

```bash
PYTHONPATH=/home/nomaan/captain-system:/home/nomaan/captain-system/captain-command \
  python3 /home/nomaan/captain-system/scripts/lint_decimal_boundary.py
```
