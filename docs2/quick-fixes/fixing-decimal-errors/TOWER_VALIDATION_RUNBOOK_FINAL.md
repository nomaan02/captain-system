# Tower Validation Runbook — Decimal/Float Audit Final

**Date:** 2026-04-30
**Shell:** fish (Linux towers)
**Branch:** `main`
**Required SHA:** `2169e7c` or later (Phase 5 patch + e2e tests)
**Run on:** BOTH towers, after every `git pull origin main`, before every market open

This runbook is the **single source of truth** for verifying a tower is safe to enable `AUTO_EXECUTE` after the Decimal/float fixes. It assumes the standard fish helpers (`dco`, `cap-run`) and venv setup from `TOWER_TEST_RUNBOOK.md` are already configured.

---

## Section 0 — Pre-flight (60 seconds)

```fish
cd ~/captain-system
git pull origin main --ff-only
git rev-parse HEAD
```

**Pass:** Prints `2169e7c` or a later SHA. Both towers must show the SAME SHA before market open.

```fish
dco up -d --build
sleep 15
dco ps
```

**Pass:** All 9 services show `Up` or `Up (healthy)`.

---

## Section 1 — Static test gate (3 minutes)

```fish
cd ~/captain-system
source .venv/bin/activate.fish
set -gx PYTHONPATH $PWD $PWD/captain-online $PWD/captain-offline $PWD/captain-command
set -gx QUESTDB_HOST 127.0.0.1
set -gx QUESTDB_PORT 8812

# Lockdown: Decimal-boundary regression suite (~80 tests)
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

**Pass:** `~135 passed, 1 skipped` (the 1 skipped is `test_make_json_safe_decimal_to_string` if fastapi is missing on the host — runs successfully inside the container).

**Fail:** Any FAILED line → patch is not loaded. `git status` must be clean and `git rev-parse HEAD` must equal `2169e7c` or later.

---

## Section 2 — Live QuestDB type-purity (30 seconds, requires QuestDB up)

```fish
cd ~/captain-system
source .venv/bin/activate.fish
set -gx QUESTDB_HOST 127.0.0.1
set -gx QUESTDB_PORT 8812

python -B -m pytest \
    tests/test_tsm_config_type_purity.py \
    tests/test_user_silo_type_purity.py \
    tests/test_active_assets_type_purity.py \
    -v
```

**Pass:** `3 passed`. Every monetary field returned by `_load_tsm_configs`, `_load_user_silo`, `_load_active_assets` is `Decimal` (or `Decimal | None` for nullable).

**Fail:** If a test fails with `field 'X' expected Decimal, got float`, the producer-side coercion was not applied — `git status` and re-pull.

**Skip-reason:** If `psycopg2.OperationalError: connection refused`, the QuestDB container is not running. `dco up -d questdb` and retry.

---

## Section 3 — QuestDB SQL inspection (verify schema + active state)

Open the QuestDB web console at `http://localhost:9000` (or `http://<tower-ip>:9000`), then run each query below.

### 3.1 Schema drift gate (CRITICAL — must pass)

```fish
cap-run verify_schema_drift.py
echo $status
```

**Pass:** Last line is `PASS: all <N> canonical tables match live QuestDB schema`. Exit code `0`.

**Fail:** Any `MISSING` / `DRIFT` / `FAIL` → run `cap-run init_questdb.py` and recheck.

### 3.2 Confirm DECIMAL types are applied to D08

```sql
-- Run in QuestDB web console
SHOW COLUMNS FROM p3_d08_tsm_state;
```

**Pass:** The following columns must show `DECIMAL(18, 2)`:
- `starting_balance`
- `current_balance`
- `current_drawdown`
- `daily_loss_used`
- `profit_target`
- `max_drawdown_limit`
- `max_daily_loss`
- `commission_per_contract`
- `margin_per_contract`

**Fail:** If any of those show `DOUBLE`, the Phase A migration was not applied. Run `cap-run init_questdb.py`.

### 3.3 Confirm DECIMAL types are applied to D03

```sql
SHOW COLUMNS FROM p3_d03_trade_outcome_log;
```

**Pass:** The following columns must show DECIMAL:
- `entry_price`, `signal_entry_price`, `exit_price` → `DECIMAL(14, 6)`
- `gross_pnl`, `commission`, `pnl`, `slippage` → `DECIMAL(18, 4)`

### 3.4 Confirm DECIMAL types on D16, D23, D25, D28, D00, D30

```sql
SHOW COLUMNS FROM p3_d16_user_capital_silos;     -- starting_capital, total_capital → DECIMAL(18,2)
SHOW COLUMNS FROM p3_d23_circuit_breaker_intraday; -- l_t → DECIMAL(18,2)
SHOW COLUMNS FROM p3_d25_circuit_breaker_params;   -- l_star → DECIMAL(18,2)
SHOW COLUMNS FROM p3_d28_account_lifecycle;        -- 6 monetary cols → DECIMAL(18,2)
SHOW COLUMNS FROM p3_d00_asset_universe;           -- point_value, tick_size, margin_per_contract → DECIMAL
SHOW COLUMNS FROM p3_d30_daily_ohlcv;              -- open, high, low, close → DECIMAL(14,6)
```

### 3.5 Verify D08 monetary values are well-formed (no NULL where unexpected)

```sql
SELECT account_id, name,
    starting_balance, current_balance,
    current_drawdown, daily_loss_used,
    max_drawdown_limit, max_daily_loss
FROM p3_d08_tsm_state
LATEST ON last_updated PARTITION BY account_id;
```

**Pass:** Every row has non-NULL `starting_balance`, `current_balance`. `max_drawdown_limit` / `max_daily_loss` may be NULL for `BROKER_LIVE` accounts (expected).

**Fail:** If `current_balance` is NULL, the bootstrap is incomplete. Re-run `bootstrap_production.py`.

### 3.6 Verify D16 capital silo

```sql
SELECT user_id, status, role, starting_capital, total_capital, accounts
FROM p3_d16_user_capital_silos
LATEST ON last_updated PARTITION BY user_id;
```

**Pass:** Active user has non-NULL `starting_capital` and `total_capital`. `accounts` is a JSON list with at least one account ID matching D08.

### 3.7 Verify D03 recent trade outcomes have correct types

```sql
-- Latest 5 closed trades (should be Decimal-typed prices and PnL)
SELECT trade_id, asset, direction, contracts,
    entry_price, exit_price,
    gross_pnl, commission, pnl, slippage,
    outcome, ts
FROM p3_d03_trade_outcome_log
WHERE outcome IS NOT NULL
ORDER BY ts DESC
LIMIT 5;
```

**Pass:** Numeric values display without scientific notation (e.g. `4500.25` not `4.50025e3`). PnL = `(exit_price - entry_price) × direction × contracts × point_value - commission` (verify a row by hand).

### 3.8 Inspect Redis open positions for type purity

```fish
# Show one open position from Redis
docker exec captain-system-redis-1 redis-cli -a $REDIS_PASSWORD --no-auth-warning HGETALL captain:open_positions | head -50
```

**Pass:** If positions exist, monetary fields are encoded as JSON strings (Decimal serialisation via `dumps_decimal`). Example:
```
"entry_price": "4500.25",
"tp_level": "4505.00",
"sl_level": "4498.00",
"point_value": "5",
```

**Fail:** If you see numeric values (`"entry_price": 4500.25`) instead of strings, the position was written before the Phase 5 fix. Restart captain-online to use the new serialisation path:
```fish
dco restart captain-online
```

---

## Section 4 — Container log greps (immediate post-rebuild)

After `dco up -d --build`, wait 60 seconds for the orchestrators to come up and run their first session evaluation. Then check the logs for any `TypeError` or Decimal/float issues.

**Note:** Use `grep -iE` (POSIX). Towers may not have `ripgrep` (`rg`) installed by default. If you prefer `rg`, install it: `sudo apt install ripgrep`.

```fish
# Check captain-online for the original Bug C signature
dco logs --tail=500 captain-online 2>&1 | grep -iE "TypeError.*decimal|Position monitor error|monitor_positions" | head -20
```

**Pass:** No matches.

```fish
# Check captain-command for the original Bug A round 2 signature
dco logs --tail=500 captain-command 2>&1 | grep -iE "TypeError.*decimal|reconciliation.*FAIL|RECONCILIATION_FAILURE" | head -20
```

**Pass:** No matches.

```fish
# Check captain-offline for any Decimal/float issues
dco logs --tail=500 captain-offline 2>&1 | grep -iE "TypeError.*decimal" | head -20
```

**Pass:** No matches.

```fish
# Check for the previous "B6 silent skip" pattern
dco logs --tail=500 captain-online 2>&1 | grep -E "ON-B6-SUMMARY|B6 signal FAILED|_build_per_account" | head -20
```

**Pass:** Either no matches OR the matches show successful `ON-B6-SUMMARY` lines (e.g. `recommended=N built=M`). NO `B6 signal FAILED` errors.

---

## Section 5 — End-to-end dry run (the gold standard)

This exercises the FULL B1 → B5C pipeline against the live QuestDB without publishing signals to Redis. It would have caught all four sister-bugs before market open.

```fish
for s in 1 2 3
    echo "=== Session $s (1=NY, 2=LON, 3=APAC) ==="
    dco exec -T -e PYTHONPATH=/app captain-online \
        python -u /app/dry_run_phase_a.py $s
    echo ""
end
```

**Pass:** Each session prints:
```
================================================================
DRY RUN COMPLETE: PASS
================================================================
silo_<user_id>: PASS
b1_<asset>: PASS  (×10 assets)
b2: PASS
b3: PASS
b4: PASS
b5: PASS
b5b: PASS
b5c: PASS
================================================================
```

**Fail:** Any `FAIL` line → match against the table below:

| Output line | Cause | Fix |
|---|---|---|
| `b4: FAIL` with `TypeError: ... 'decimal.Decimal' and 'float'` | Phase 1 (b4_kelly) patch missing | `git pull` + `dco up -d --build` |
| `b6 fail` with same TypeError | Phase 1 (b6_signal_output) patch missing | Same |
| `silo_<user>: FAIL` with `NoneType` on `total_capital` | D16 bootstrap incomplete | `cap-run bootstrap_production.py` |
| `b5c: FAIL` | Check log for specific error | Likely D23/D25 not bootstrapped |

---

## Section 6 — Stress test the position monitor specifically (Bug C)

This invokes `monitor_positions` against a synthetic Decimal-typed position to prove the inner loop is safe.

```fish
cd ~/captain-system
source .venv/bin/activate.fish
set -gx PYTHONPATH $PWD $PWD/captain-online $PWD/captain-offline $PWD/captain-command

python -B -m pytest tests/test_b7_position_monitor_decimal_boundary.py -v
```

**Pass:** `9 passed`. Each test exercises a different Decimal/float mixing scenario.

---

## Section 7 — Cross-tower SHA parity

Both towers MUST end on the same `git rev-parse HEAD` before market open. Run on each tower:

```fish
git rev-parse HEAD
```

**Pass:** Both print the same SHA (`2169e7c` or later).

---

## Section 8 — Production smoke after first signal of the day

After the first signal fires (visible in GUI or `dco logs --tail=20 captain-online | grep ON-B6-SUMMARY`), verify the full chain executed cleanly:

```fish
# Check signal was published to Redis
docker exec captain-system-redis-1 redis-cli -a $REDIS_PASSWORD --no-auth-warning XRANGE stream:signals - + COUNT 5 | head -30
```

**Pass:** Recent entries with `signal_id`, `asset`, `direction`, `tp_level`, `sl_level` (as JSON strings).

```fish
# Check command processed it
dco logs --tail=200 captain-command 2>&1 | grep -iE "signal batch received|AUTO-EXECUTE|TopstepX" | head -10
```

**Pass:** See `Signal batch received` followed by `AUTO-EXECUTE` (if `AUTO_EXECUTE=true`) and `TopstepX BRACKET order PLACED` or `TopstepX order PLACED`.

```fish
# Check position monitor is running cleanly
sleep 30
dco logs --tail=100 captain-online 2>&1 | grep -iE "monitor_positions|Position resolved|Position monitor" | head -20
```

**Pass:** Either no log lines (no positions yet) OR clean position monitoring messages with no TypeError.

```fish
# Verify a trade outcome reaches offline learning (if a position closed)
dco logs --tail=200 captain-offline 2>&1 | grep -iE "trade outcome received|kelly update|dma update" | head -10
```

**Pass:** `Trade outcome received: <asset> pnl=$<value>` followed by `Kelly update`, `DMA update`, etc. — no TypeError.

---

## Section 9 — Definition of done

Tower is ready for market open when **ALL** of these are green:

1. ✅ `git rev-parse HEAD` = `2169e7c` or later
2. ✅ Both towers on the same SHA
3. ✅ All 9 Docker services `Up`
4. ✅ Section 1 static gate: `~135 passed`
5. ✅ Section 2 live producer purity: `3 passed`
6. ✅ Section 3.1 schema drift gate: `PASS`
7. ✅ Section 3.2-3.4 SHOW COLUMNS: all monetary cols are DECIMAL
8. ✅ Section 4 log greps: no TypeError matches
9. ✅ Section 5 dry runs: `DRY RUN COMPLETE: PASS` for sessions 1, 2, 3
10. ✅ Section 6 monitor stress test: `9 passed`

If any of those is red, **do not enable AUTO_EXECUTE for the next session**. Report which gate failed and we troubleshoot.

---

## What to ask me if anything fails

- **"Section X failed with output Y"** — paste the exact output and I'll trace the cause
- **"Container log shows new TypeError"** — paste the full traceback (last ~30 lines) and we identify the new failure mode
- **"SHOW COLUMNS shows DOUBLE instead of DECIMAL"** — Phase A migration didn't apply; we need to investigate `init_questdb.py` output
- **"Both towers show different SHAs"** — one tower's `git pull` failed; we resolve the divergence

---

## Companion files in this folder

- `EXECUTION_SUMMARY.md` — chronological summary of Phase 1-5 commits
- `EXHAUSTIVE_AUDIT_REPORT.md` — comprehensive surface-area audit with classifications
- `TOWER_TEST_RUNBOOK.md` — original Phase 1-4 tower runbook
- `TOWER_VALIDATION_RUNBOOK_FINAL.md` — THIS FILE (post-audit consolidated runbook)

---

*End of runbook.*
