# D08 TSM INSERT Debug Handoff

## Status: ACTIVE BUG — D08 `_store_tsm_in_d08` fails silently on fresh QuestDB

**Branch:** `migration/decimal-phase-c`  
**Both towers affected:** captain-tower-1 (nomaan), captain-tower-2 (isaac)  
**Latest commit:** `1744d30` on `migration/decimal-phase-c`

---

## Context: Tower Fresh Start Flow

The user is following the guide at `docs2/audits/questdb-re-seed/2026-04-29_tower_fresh_start_go_live.md` for a full QuestDB wipe + reseed.

### Steps completed successfully:
1. **B.2** — QuestDB wiped (`sudo rm -rf questdb/db/*`), stack brought up
2. **C.1** — `captain-update.sh --skip-pull` — schema created, seeds run (benign M042 FAIL for already-DECIMAL columns)
3. **C.4** — `bootstrap_production.py` — all 10 assets inserted into D00, D02/D16/D25 populated (after fixing Decimal + tick_size precision issues)
4. **C.5** — `seed_system_params.py` — D17 populated
5. **E.1** — `captain-command` restart for D08 TSM auto-link — **THIS IS WHERE IT FAILS**

### The bug:
`captain-command` starts, authenticates with TopstepX, fetches TSM data, and calls `_store_tsm_in_d08()` in `captain-command/captain_command/blocks/b4_tsm_manager.py`. The INSERT into `p3_d08_tsm_state` fails with a **blank** `psycopg2.DatabaseError` (no error message, just `LINE 1: INSERT INTO p3_d08_tsm_state(` with caret at position 1). The function returns `False`, but the TSM is linked in-memory so `TSM auto-linked` still prints. D08 remains empty.

---

## What has been tried and ruled out

### 1. Decimal type adapter (FIXED — separate issue)
- **Problem:** psycopg2 sends Python `Decimal` as NUMERIC wire type; QuestDB maps to DOUBLE, rejects DOUBLE→DECIMAL cast
- **Fix:** Global adapter in `shared/questdb_client.py` line 22: `register_adapter(Decimal, ...)`  
- **Also:** Belt-and-suspenders `str(Decimal(...))` wrapping in all seed/bootstrap scripts
- **Status:** RESOLVED — bootstrap_production.py works for all 10 assets

### 2. DECIMAL(14,4) precision too narrow (FIXED — separate issue)
- **Problem:** ZB tick_size=0.03125 (5 places), ZN=0.015625 (6 places), OHLCV prices up to 6 places
- **Fix:** Widened in `shared/canonical_schemas.py`: tick_size→DECIMAL(14,8), prices→DECIMAL(14,6)
- **Status:** RESOLVED — requires fresh QuestDB wipe to apply

### 3. Timezone-aware ISO timestamp (PARTIALLY FIXED)
- **Problem:** `now_et().isoformat()` produces `2026-04-28T21:32:08.572123-04:00`; QuestDB PG wire rejects timezone offset for designated timestamps
- **Fix:** Changed D08 INSERT to use `now()` SQL function instead of `%s` with Python timestamp
- **Status:** Applied but D08 INSERT still fails — timestamp was not the only issue

### 4. Python bool via PG wire (PARTIALLY FIXED)
- **Problem:** psycopg2 sends Python `True`/`False` using binary boolean format; QuestDB may not support it
- **Fix:** Global adapter in `shared/questdb_client.py`: `register_adapter(bool, ...)` sends as SQL keywords
- **Status:** Applied, error output is reduced but INSERT still fails silently

### 5. Table existence (VERIFIED — not the issue)
- `SELECT count() FROM p3_d08_tsm_state` returns 0 (table exists, empty)
- HTTP API INSERT works: `INSERT INTO p3_d08_tsm_state(account_id,starting_balance,last_updated) VALUES('TEST','100',now())` → OK
- PG wire minimal INSERT works: `cur.execute("INSERT INTO p3_d08_tsm_state(account_id, starting_balance, last_updated) VALUES(%s, %s, now())", ('TEST2', '200'))` → SUCCESS

---

## Key diagnostic data (from debug logging, now removed)

The debug commit `c0fbe85` (since removed in `d82b662`) captured the exact params:

```
D08 params types: [
  (0, 'str', "'20319811'"),                          # account_id SYMBOL
  (1, 'str', "'primary_user'"),                      # user_id SYMBOL  
  (2, 'str', "'Topstep 150K Trading Combine'"),      # name STRING
  (3, 'str', '\'{"provider": "TopstepX",...}'),      # classification STRING
  (4, 'str', "'150000'"),                            # starting_balance DECIMAL(18,2)
  (5, 'str', "'148155.93'"),                         # current_balance DECIMAL(18,2)
  (6, 'str', "'4500'"),                              # max_drawdown_limit DECIMAL(18,2)
  (7, 'NoneType', 'None'),                           # max_daily_loss DECIMAL(18,2) — NULL
  (8, 'str', "'0'"),                                 # daily_loss_used DECIMAL(18,2)
  (9, 'str', "'9000'"),                              # profit_target DECIMAL(18,2)
  (10, 'int', '15'),                                 # max_contracts INT
  (11, 'str', "'1.4'"),                              # commission_per_contract DECIMAL(18,2)
  (12, 'bool', 'False'),                             # overnight_allowed BOOLEAN
  (13, 'str', '\'{"session_open": "18:00 EST",...}'),# trading_hours STRING
  (14, 'str', "'PASS_EVAL'"),                        # risk_goal STRING
  (15, 'bool', 'True'),                              # topstep_optimisation BOOLEAN
  (16, 'bool', 'False'),                             # scaling_plan_active BOOLEAN
  (17, 'str', '\'{"topstep_params": {"p": 0.005,...}'), # topstep_state STRING
  (18, 'str', '\'{"type": "TOPSTEP_EXPRESS",...}'),  # fee_schedule STRING
  (19, 'str', "'{}'"),                               # payout_rules STRING
  (20, 'str', "'2026-04-28T21:38:34...-04:00'")     # last_updated TIMESTAMP (now removed, uses now())
]
```

**After the latest fixes, param 20 is removed (now() used), and bools 12/15/16 go through the adapter.**
**Remaining param count: 20 params for 20 `%s` placeholders + 1 `now()` = 21 values for 21 columns.**

---

## Files to read

| File | Why |
|------|-----|
| `captain-command/captain_command/blocks/b4_tsm_manager.py` (lines 380-460) | The `_store_tsm_in_d08` function with the failing INSERT |
| `shared/questdb_client.py` (lines 1-25) | Global psycopg2 adapters (Decimal, bool) |
| `shared/canonical_schemas.py` (lines 214-249) | D08 DDL — 32 columns, DECIMAL(18,2), BOOLEAN, TIMESTAMP |
| `captain-command/captain_command/main.py` | Calls `_link_tsm_to_account` which calls `_store_tsm_in_d08` |

## Suggested next debugging steps

1. **Re-add debug logging** to `_store_tsm_in_d08` — specifically `cur.mogrify(sql, params)` to see the EXACT SQL being sent to QuestDB after all adapters fire. Print at ERROR level so it appears in logs.

2. **Binary search the params** — split the INSERT into two halves (first 10 columns, last 10) to isolate which parameter causes the blank error. A helper script inside the container can test this quickly.

3. **Check `None` handling** — param 7 (`max_daily_loss`) is `None`. Test if passing `None` for a `DECIMAL(18,2)` column via PG wire causes the blank error. Try the minimal INSERT: `INSERT INTO p3_d08_tsm_state(account_id, max_daily_loss, last_updated) VALUES('NULLTEST', NULL, now())`.

4. **Check `int` handling** — param 10 (`max_contracts`) is a Python `int` (15). No adapter is registered for int. Test: does psycopg2's native int handling work for QuestDB INT columns?

5. **Try HTTP API fallback** — if PG wire continues to be problematic, consider using QuestDB's REST API (`/exec?query=...`) for this specific INSERT as a workaround.

## Important: `now_et().isoformat()` pattern is widespread

Even after D08 is fixed, the same timezone-aware timestamp pattern is used in INSERT statements across many runtime blocks. These will fail during live operations:
- `captain-command/blocks/b8_reconciliation.py` — session event log, D08 updates
- `captain-command/blocks/b1_core_routing.py` — session events, notifications
- `captain-online/blocks/b7_position_monitor.py` — D03 trade close, D16/D23 updates
- `captain-command/blocks/b7_notifications.py` — notification log

These all need `now_et().isoformat()` replaced with `now()` for designated timestamp columns before NY open.

---

## Docker compose context
- Compose files: `docker-compose.yml` + `docker-compose.local.yml`
- `dco` is a fish alias for `docker compose -f docker-compose.yml -f docker-compose.local.yml`
- `shared/` is bind-mounted at `/app/shared:ro` in all service containers
- `captain-command/captain_command/` is bind-mounted at `/app/captain_command:ro`
- `scripts/` is bind-mounted at `/captain/scripts:ro` in captain-offline only
- Changes to bind-mounted files are visible immediately; only need `dco restart <service>`
