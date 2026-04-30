# Captain System — Pre-Market Validation Guide

**Version:** 2026-04-29 (updated after Bug A / Phase A Decimal migration fixes at `4c225c0`)
**Branch this guide was written against:** `fix/b7-pnl-multiplier-tier1`
**Time to run:** ~15 minutes (Tier 1 + 2 + 3)
**Run on:** BOTH towers before every first session after a deploy, wipe, or incident

---

## Why This Guide Exists

Captain System runs three independent Docker processes (captain-online, captain-command,
captain-offline) that share QuestDB and Redis. A failure in any one of them silently
prevents trading — signals never reach the broker, or reach it with wrong sizing. This
guide exercises every layer from market data streaming through order placement in a
sequence that surfaces any hidden error before the next session open.

Three real-world incidents that this guide would have caught:

| Incident | What happened | Test that catches it |
|---|---|---|
| 2026-04-29 Bug A | `b7_position_monitor` used ES point value ($50) for all assets, inflating non-ES PnL by 5×–100×, tripping silo drawdown | T1 dry-run produces wrong gross_pnl for non-ES assets; T5 D08 drawdown check shows mismatch vs broker balance |
| 2026-04-29 B4 crash | Phase A Decimal migration left D08 monetary fields as `Decimal` type; B4 Kelly sizing tried `Decimal - float` and crashed, killing the whole session | T1 dry-run session 1 crashes at B4 stage before even producing a verdict |
| 2026-04-30 B6 crash | Same Phase A migration: `b6_signal_output._build_per_account` did `mdd_limit - current_dd` where the antipattern `r[N] or 0.0` collapsed `Decimal('0.00')` to float, producing a type-mixed dict. Fired on every account at NY/APAC open. | T2 lint: `pytest tests/test_decimal_boundary_lint.py` blocks any new `or 0.0` on monetary columns; T1 dry-run also exercises B6 indirectly via signal publication |

---

## Architecture Context

### What each process does

```
captain-online  (B1→B9)   Market data → Regime → AIM → Kelly → Trade selection → Signals
captain-command (B1→B12)  Receive signal → Compliance gate → Auto-execute → TopstepX API
captain-offline (B1→B9)   Receive trade outcome → Learn (EWMA / Kelly / BOCPD / DMA)
```

### What the dry-run scripts exercise

```
dry_run_phase_a.py <session_id>
  └─ B1: Data ingestion (features, VIX, economic calendar)
  └─ B2: Regime probability (XGBoost classifier)
  └─ B3: AIM aggregation (6 active AIMs × 10 assets)
  └─ B4: Kelly sizing (reads D08 TSM, D05 EWMA, D12 Kelly → computes contracts)  ← crash site of 2026-04-29
  └─ B5: Trade selection (correlation filter, capacity check)
  └─ B5B: Quality gate ($/contract floor + ceiling)
  └─ B5C: Circuit breaker (L0-L4: scaling, preemptive halt, budget, expectancy, Sharpe)
  DOES NOT run B6 (no signals published — purely diagnostic)

dry_run_command.py          ← NOTE: must be checked via API endpoint, not docker exec (see T3.2)
  Checks: adapter registration, API connectivity, account canTrade, contract resolution,
          compliance gate, AUTO_EXECUTE flag — all from inside the running orchestrator
```

### Session schedule (America/New_York)

| Session | Evaluation fires | Assets in scope | OR window |
|---|---|---|---|
| NY | ~09:25 ET | ES, MES, NQ, MNQ, M2K, MYM, ZB, ZN (8) | 09:30–09:35 |
| LON | ~02:55 ET | MGC (1) | 03:00–03:05 |
| APAC | ~17:55 ET | NKD (1) | 18:00–18:05 |

---

## Prerequisites — Do Once Per Session

Open a fish shell on the tower and paste these helpers (they are used throughout):

```fish
cd ~/captain-system

function dco
    docker compose -f docker-compose.yml -f docker-compose.local.yml $argv
end

# Run scripts from /captain/scripts/ inside captain-offline
function cap-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/$script $rest
end

# Run scripts from /app/ inside captain-online
function online-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-online \
        python3 /app/$script $rest
end

# Run scripts from /app/ inside captain-command
function cmd-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-command \
        python3 /app/$script $rest
end
```

---

## TIER 1 — Signal Pipeline (REQUIRED)

**What it tests:** The full B1→B5C captain-online pipeline. This is the only tier that
must pass before the next session open. If anything here fails, no signals will be generated.

**Mechanism:** `dry_run_phase_a.py` loads all production data from QuestDB (D00, D05, D08,
D12, D16, D25), computes features against live/recent market data from TopstepX, runs every
block in sequence, and prints a verdict — but stops before B6 so no signals are published
and no orders are placed.

---

### T1.1 — NY Session Pipeline (8 assets)

```fish
online-run dry_run_phase_a.py 1
```

**What it does:**
Exercises the full B1→B5C pipeline for session NY. Loads 8 NY-eligible assets (ES, MES,
NQ, MNQ, M2K, MYM, ZB, ZN), computes all 224 features, runs regime classification, AIM
aggregation, Kelly sizing (reads D08 TSM including the `max_drawdown_limit` and
`current_drawdown` Decimal fields — the 2026-04-29 crash site), trade selection,
quality gate and 5-layer circuit breaker.

**Expected output:**
```
B1: 8 assets, ~224 features computed
B2: 8 assets classified  (regime_uncertain: all uncertain is normal on cold start)
B3: 8 assets scored      (combined_modifier ~0.95-0.98)
B4: 5-6 assets with non-zero contracts        ← THIS LINE PROVES THE B4 FIX WORKS
B5: 5 trades selected
B5B: 5 recommended
B5C: 5 passed
VERDICT: Phase A would produce signals. System ready to trade.
```

**Pass:** All block lines present, no `CRASHED` or `FAILED` tag, final `VERDICT` line appears.

**Fail — what each failure means:**

| Failure | Cause | Action |
|---|---|---|
| `B4: FAILED` with `TypeError: unsupported operand type(s) for -: decimal.Decimal and float` | B4 Decimal/float fix (`4c225c0`) not loaded | `dco down && dco build --no-cache captain-online && dco up -d` |
| `B4: 0 assets with non-zero contracts` (no traceback) | D08 missing `max_drawdown_limit` / Kelly cold-start (no D03 history) | Acceptable on fresh start. Check D08 via T5.2 |
| `B1: 0 assets, 0 features computed` | D00 not bootstrapped | Run `cap-run bootstrap_production.py` |
| `B1: No active assets for session NY` | D00 `captain_status` not ACTIVE for NY assets | Check `SELECT asset_id, captain_status FROM p3_d00_asset_universe LATEST ON last_updated PARTITION BY asset_id` |
| Any `PointValueResolutionError` | D00 missing `point_value` for an asset | Re-run bootstrap; verify D00 row for that asset |

---

### T1.2 — LON Session Pipeline (MGC only)

```fish
online-run dry_run_phase_a.py 2
```

**What it does:** Same as T1.1 but for the LON session. Only MGC is eligible.
MGC has `point_value = 10` — a 5× inflation asset under Bug A, making this
a meaningful regression check for the b7 fix.

**Expected output:**
```
B1: 1 asset (MGC)
B2–B5C: all pass through
VERDICT: Phase A would produce signals.
```

**Fail:** `B1: No active assets for session LON` → MGC's `session_hours` in D00 is
missing the LON key. Re-run `bootstrap_production.py`.

---

### T1.3 — APAC Session Pipeline (NKD only)

```fish
online-run dry_run_phase_a.py 3
```

**What it does:** APAC session dry-run (NKD only, `point_value = 5`, 10× inflation asset
under Bug A). Evaluates at ~17:55 ET tonight. **Must pass before tonight's canary trade.**

**Expected output:**
```
B1: 1 asset (NKD)
B2–B5C: all pass through
VERDICT: Phase A would produce signals.
```

**Fail:** `B1: No active assets for session APAC` → NKD's `session_hours` in D00 is
missing the APAC key. Re-run `bootstrap_production.py`.

---

## TIER 2 — Infrastructure & Schema Health (~3 min)

**What it tests:** Container health, QuestDB schema integrity (all Phase A/B/C Decimal
migrations applied), critical table row counts, QuestDB read/write cycles, and VIX
data freshness.

---

### T2.1 — Container health

```fish
dco ps
```

**Expected:** All 9 containers in `running` or `healthy` state.

| Container | Role |
|---|---|
| questdb | Time-series database (port 8812, 9000) |
| redis | Message bus + AOF persistence (port 6379) |
| captain-online | Signal engine |
| captain-command | Execution + API layer |
| captain-offline | Learning brain |
| captain-gui | React SPA static build |
| gui-dist | Static asset serving |
| nginx | Reverse proxy (port 80) |
| vault-backup | Encrypted key backup |

**Fail:** Any container shows `exited` or `restarting` → `dco logs <container-name>` to
diagnose, then `dco up -d --force-recreate <container-name>`.

---

### T2.2 — Schema drift gate

```fish
cap-run verify_schema_drift.py
echo "exit=$status"
```

**What it does:** Compares every canonical table definition in `shared/canonical_schemas.py`
(including all Decimal migrations M010–M042 from Phase A/B/C) against the live QuestDB
schema. Exits non-zero if any column type, name, or constraint differs.

**Expected:**
```
PASS: all <N> canonical tables match live QuestDB schema
exit=0
```

**Fail:** `DRIFT` or `MISSING` → Phase A/B/C migrations were not applied. Run:
```fish
cap-run init_questdb.py
cap-run verify_schema_drift.py
```

---

### T2.3 — QuestDB connectivity + table smoke

```fish
cap-run health_smoke_test.py
echo "exit=$status"
```

**What it does:** Verifies QuestDB connectivity via the standard `get_cursor()` code path
(same as every block uses), reads one row from each of the 7 critical tables, then runs
a scratch-table write → read → dedup-replace → drop cycle to confirm WAL + DEDUP is working.

**Expected:**
```
1. QuestDB health gate (wait_for_questdb, max 30s)…  reachable.
2. Reading one row from each critical table…
   D00  p3_d00_asset_universe: 10 rows
   D02  p3_d02_aim_meta_weights: 60 rows
   D08  p3_d08_tsm_state: <N> rows
   D12  p3_d12_kelly_parameters: 60 rows
   D16  p3_d16_user_capital_silos: <N> rows
   D25  p3_d25_circuit_breaker_params: 1 rows
   D30  p3_d30_daily_ohlcv: <N> rows
3. Scratch table write/read/dedup-replace…  PASS
exit=0
```

**Fail:** Any table at 0 rows → bootstrap scripts were not run. See
`docs2/audits/questdb-re-seed/2026-04-29_tower_fresh_start_go_live.md` for the
full seed sequence.

---

### T2.4 — Full QuestDB state audit

```fish
cap-run verify_questdb_state.py
```

**What it does:** Detailed per-table row count, freshness, and value-range checks.
Reports PASS / WARN / CRITICAL per table. Takes about 5 seconds.

**Expected:** No `CRITICAL` rows. `WARN` is acceptable (e.g. D03 empty on fresh start).

**Fail:** Any `CRITICAL` line in the output. Read the message — it tells you exactly
which table and what the expected vs actual state is.

---

### T2.5 — VIX data freshness

```fish
tail -1 ~/captain-system/data/vix/vix_daily_close.csv
tail -1 ~/captain-system/data/vix/vxv_daily_close.csv
```

**What it does:** Checks that VIX and VXV daily close CSVs contain data from within the
last 2 trading days. AIM-04 (IVTS) uses the VIX/VXV ratio as an input to the AIM modifier.
Stale VIX causes AIM-04 to output a zero modifier for all assets, compressing combined_mod.

**Expected:** Both files end with a line dated 2026-04-28 or 2026-04-29.

**Fail:** Date is more than 2 trading days old. Fix:
```fish
cap-run update_vix_daily.py
```

---

### T2.6 — Regression tests (host venv or in container)

These are the pytest tests that pin the bugs fixed on 2026-04-29 and 2026-04-30.

```fish
# Host venv (faster)
set -gx PYTHONPATH $PWD $PWD/captain-online $PWD/captain-offline $PWD/captain-command
python -B -m pytest \
    tests/test_b7_pnl_per_symbol.py \
    tests/test_b4_kelly.py \
    tests/test_decimal_boundary.py \
    tests/test_b6_decimal_d08_boundary.py \
    tests/test_reconciliation_decimal_boundary.py \
    tests/test_tsm_simulation_decimal_input.py \
    tests/test_kelly_fee_schedule_decimal.py \
    tests/test_decimal_boundary_lint.py \
    -v

# OR inside container (no venv needed)
dco exec -T -e PYTHONPATH=/app captain-online \
    python -B -m pytest /app/tests/test_b7_pnl_per_symbol.py \
        /app/tests/test_b4_kelly.py /app/tests/test_decimal_boundary.py \
        /app/tests/test_b6_decimal_d08_boundary.py \
        /app/tests/test_reconciliation_decimal_boundary.py \
        /app/tests/test_tsm_simulation_decimal_input.py \
        /app/tests/test_kelly_fee_schedule_decimal.py \
        /app/tests/test_decimal_boundary_lint.py -v
```

**What it tests:**
- `test_b7_pnl_per_symbol.py` (27 cases) — `resolve_position` uses D00 `point_value`
  per asset; historic 50.0 default cascade is gone; raises on D00 miss.
- `test_b4_kelly.py` — Kelly helpers compute correctly and `_to_float` coerces
  D08 Decimal fields without TypeError.
- `test_decimal_boundary.py` (27 cases) — `as_money` / `as_money_or_none` /
  `to_float` / `assert_money_dict` primitives.
- `test_b6_decimal_d08_boundary.py` — exact NY-open 2026-04-30 failure mode
  (zero `current_drawdown` + zero `daily_loss_used` + Decimal `max_drawdown_limit`).
- `test_reconciliation_decimal_boundary.py` — broker-float vs system-Decimal
  mismatch path + new CRITICAL log + GUI alert when reconciliation fails.
- `test_tsm_simulation_decimal_input.py` — `run_tsm_simulation` accepts a fully
  Decimal-typed `tsm_config` (was the silent TypeError mode in offline MC).
- `test_kelly_fee_schedule_decimal.py` — Phase-A-encoded `fee_schedule` JSON
  round-trips through `parse_json_decimal` + `as_money` correctly.
- `test_decimal_boundary_lint.py` — CI gate: refuses any new `or 0.0` antipattern
  on monetary columns (calls `scripts/lint_decimal_boundary.py`).

**Expected:** `~80 passed`

**Fail:** Any FAILED line → the patch is not loaded. Re-checkout the branch and rebuild.

---

## TIER 3 — Live Broker Integration (~3 min)

**What it tests:** The full captain-command → TopstepX path: authentication, account
resolution, contract IDs, compliance gate, and AUTO_EXECUTE state.

**Note:** These commands touch the live TopstepX API. They are read-only (no orders
placed) except T3.3 which places and immediately cancels a limit order. Run only when
you are at the keyboard, ready to intervene if needed.

---

### T3.1 — TopstepX integration verify

```fish
cap-run verify_topstep_integration.py
```

**What it does:** Authenticates to TopstepX, resolves the account, verifies `canTrade=True`,
checks all 10 contract IDs resolve, and confirms the account balance is non-zero.

**Expected:** All checks PASS, `canTrade=True`, 10/10 contracts resolved.

**Fail:** `canTrade=False` → account is not active. Check TopstepX dashboard.
Auth fail → verify `.env` `TOPSTEP_USERNAME` and `TOPSTEP_API_KEY`.

---

### T3.2 — Captain-command adapter live check

**IMPORTANT:** Do NOT use `cmd-run dry_run_command.py` for this check. That script
reads the in-memory `_active_connections` dict from a fresh subprocess (always empty),
so it always shows `FAILED` even when the live orchestrator is fully connected.
Query the running orchestrator via its API endpoint instead:

```fish
# Live orchestrator health (real adapter state)
curl -s http://localhost:8000/api/health | python3 -m json.tool
```

**Expected:**
```json
{
    "status": "OK",
    "api_connections": {
        "connected": 1,
        "total": 1
    }
}
```

**Confirm canTrade via logs:**
```fish
dco logs --since 2h captain-command | grep -iE "canTrade|TopstepX CONNECTED|balance" | head -5
```

**Expected log line:**
```
TopstepX CONNECTED: account=PRAC-V2-..., balance=148133.40, canTrade=True
```

**Fail:** `connected: 0` in health endpoint → adapter did not register at startup.
Check: `dco logs --since 2h captain-command | grep -iE "error|FAIL|adapter"`.
Most common cause: wrong `.env` credentials, or account name doesn't match.

---

### T3.3 — D08 TSM state correct for active account

```fish
# Paste into QuestDB web console (http://localhost:9000)
# OR run via psql:
dco exec -T -e PYTHONPATH=/app captain-command python3 -c "
from shared.questdb_client import get_cursor
with get_cursor() as cur:
    cur.execute('''
        SELECT account_id, name, starting_balance, max_drawdown_limit,
               current_balance, daily_loss_used, last_updated
        FROM p3_d08_tsm_state
        LATEST ON last_updated PARTITION BY account_id
    ''')
    row = cur.fetchone()
    if row:
        print(f'account_id      : {row[0]}')
        print(f'tsm_name        : {row[1]}')
        print(f'starting_balance: \${row[2]}')
        print(f'max_drawdown_lmt: \${row[3]}')
        print(f'current_balance : \${row[4]}')
        print(f'daily_loss_used : \${row[5]}')
        print(f'last_updated    : {row[6]}')
    else:
        print('NO D08 ROW FOUND')
"
```

**What it does:** Confirms D08 was populated by `_link_tsm_to_account` at startup and
has the correct TSM for the active account. B4 Kelly sizing reads this every session —
if these values are wrong, every sizing result is wrong.

**Expected for Nomaan's 150K Trading Combine:**
```
account_id      : 20319811
tsm_name        : Topstep 150K Trading Combine
starting_balance: $150000.00
max_drawdown_lmt: $4500.00
current_balance : $148133.40   (matches broker balance from T3.1)
daily_loss_used : $0.00        (resets at SOD 19:00 ET)
```

**Fail — D08 has wrong account ID:** Run the account migration (see
`docs/FINAL-VAL-TESTS/pre-market-validation-guide.md` — Account Migration section).

**Fail — D08 is empty (`NO D08 ROW FOUND`):** TSM auto-link failed silently. Check:
```fish
dco logs --since 2h captain-command | grep -iE "TSM.*linked\|No matching TSM\|TSM auto"
```
Then trigger manually:
```fish
dco exec -T -e PYTHONPATH=/app captain-command python3 -c "
from captain_command.blocks.b4_tsm_manager import load_all_tsm_files
results = load_all_tsm_files()
for r in results:
    print(r['filename'], r['validation']['valid'], r['validation'].get('errors',''))
"
```

---

### T3.4 — D16 capital silo matches broker balance

```fish
dco exec -T -e PYTHONPATH=/app captain-command python3 -c "
from shared.questdb_client import get_cursor
with get_cursor() as cur:
    cur.execute('''
        SELECT user_id, starting_capital, total_capital, last_updated
        FROM p3_d16_user_capital_silos
        LATEST ON last_updated PARTITION BY user_id
    ''')
    row = cur.fetchone()
    if row:
        delta = float(row[2]) - float(row[1])
        print(f'user_id         : {row[0]}')
        print(f'starting_capital: \${row[1]}')
        print(f'total_capital   : \${row[2]}')
        print(f'cumulative pnl  : \${delta:+.2f}')
        print(f'last_updated    : {row[3]}')
    else:
        print('NO D16 ROW FOUND')
"
```

**What it does:** The silo drawdown check in B4 computes `(1 - total/starting)` and
blocks all trading if it exceeds 30%. This verifies total_capital is close to the
broker's actual balance and the drawdown is not phantom-inflated (which is what
Bug A caused — phantom ~39% drawdown on a real ~1.8% loss).

**Expected:** `total_capital` within a few dollars of broker `current_balance` from T3.1.
`cumulative pnl` reflects actual trade history.

**Fail — total_capital shows ~$91K on a ~$148K broker balance:** The capital state
was not reset after the Bug A incident. Run:
```fish
cap-run reset_capital_state_to_broker_truth.py --user primary_user --account 20319811
# Review the proposed delta, then:
cap-run reset_capital_state_to_broker_truth.py --user primary_user --account 20319811 --apply
```

---

### T3.5 — AUTO_EXECUTE state

```fish
dco exec -T captain-command python3 -c "
import os
v = os.environ.get('AUTO_EXECUTE', '')
active = v.lower() in ('1', 'true', 'yes')
print(f'AUTO_EXECUTE={v!r}  active={active}')
"
```

**Expected (when ready to trade):** `AUTO_EXECUTE='true'  active=True`

**Expected (deliberate canary / watch-only mode):** `AUTO_EXECUTE='false'  active=False`

**Set it in `.env` and restart the command container if it needs changing:**
```fish
# Enable:
sed -i 's/^AUTO_EXECUTE=.*/AUTO_EXECUTE=true/' .env
dco up -d --force-recreate captain-command captain-online
```

---

### T3.6 — Order placement round-trip (REAL ORDER — optional but recommended)

Places a far-from-market MES limit order that will never fill, then cancels it.
Proves the full auth → account → contract → order placement → cancellation path.

**Only run this when you are at the keyboard ready to handle a stuck order.**

```fish
cmd-run test_order_roundtrip.py
```

**Expected:**
```
Authenticated as nomaanakram4@gmail.com
Account: PRAC-V2-... (id=20319811)
Balance: $148133.40, canTrade: True
MES → CON.F.US.MES.M26
Order PLACED: orderId=<number>
Order CANCELLED
Clean: no leftover orders
RESULT: PASSED
```

**Fail:** Order rejected → check account `canTrade`, market hours, and contract roll.
Cancel failed → check TopstepX dashboard and cancel manually if needed.

---

## TIER 4 — Extended Pytest (optional, ~5 min)

Run on the first deployment of a new branch or after any block-level change.

```fish
set -gx PYTHONPATH $PWD $PWD/captain-online $PWD/captain-offline $PWD/captain-command

# Phase 7 live-parity guards (B1/B6 default to live paths unchanged)
python -B -m pytest tests/test_phase7_live_parity.py -v

# Full B2→B6 pipeline with mocked dependencies
python -B -m pytest tests/test_pipeline_e2e.py -v

# Day-1 trade → Day-2 reflects updated Kelly (full learning loop)
python -B -m pytest tests/test_integration_e2e.py -v
```

---

## Summary Checklist

Copy this before each session open. A box is checked = test passed.

```
TIER 1 — Signal pipeline (REQUIRED)
  [ ] T1.1  NY session dry-run (dry_run_phase_a.py 1) — B4 clean, VERDICT shown
  [ ] T1.2  LON session dry-run (dry_run_phase_a.py 2) — B1: 1 asset, VERDICT shown
  [ ] T1.3  APAC session dry-run (dry_run_phase_a.py 3) — B1: 1 asset, VERDICT shown

TIER 2 — Infrastructure & schema (REQUIRED)
  [ ] T2.1  All 9 containers running/healthy (dco ps)
  [ ] T2.2  Schema drift gate PASS, exit=0 (verify_schema_drift.py)
  [ ] T2.3  QuestDB smoke PASS, exit=0 (health_smoke_test.py)
  [ ] T2.4  QuestDB state audit — no CRITICAL rows (verify_questdb_state.py)
  [ ] T2.5  VIX/VXV CSVs within 2 trading days
  [ ] T2.6  44 passed — test_b7_pnl_per_symbol + test_b4_kelly

TIER 3 — Live broker integration (REQUIRED before AUTO_EXECUTE=true)
  [ ] T3.1  TopstepX integration — all PASS, canTrade=True (verify_topstep_integration.py)
  [ ] T3.2  /api/health → connected: 1 AND "canTrade=True" in logs
  [ ] T3.3  D08 has correct account, starting_balance=$150000, max_drawdown_limit=$4500
  [ ] T3.4  D16 total_capital matches broker balance ± a few dollars
  [ ] T3.5  AUTO_EXECUTE=true (or deliberately false for watch-only canary)
  [ ] T3.6  Order round-trip PASSED (optional — test_order_roundtrip.py)

All boxes ticked on both towers = system will trade at next session open.
```

---

## Known Non-Blocking Warnings

These appear in the logs on every start and are safe to ignore:

| Warning | Where | Why it's safe |
|---|---|---|
| `TSM topstep_150k_live.json has errors: ['Missing required field: starting_balance', 'Missing required field: max_drawdown_limit']` | captain-command startup | `topstep_150k_live.json` intentionally has null values — Live Funded accounts get their balance from broker SOD reconciliation, not a hardcoded constant. The current Combine account (`PRAC-V2-*`) auto-links to `topstep_150k_eval.json` which has correct values. This warning is about an unused config file. |
| `[aim16-online] inference persist skipped: name 'hp' is not defined` | captain-online, session eval | AIM-16 HMM state is not being saved across sessions. Non-blocking — AIM-16 still infers correctly during the session; it just can't persist state. Separate bug tracked for a future fix. |
| `pass_probability absent for account 20319811 (PASS_EVAL) — using default 0.85 Kelly multiplier` | B4 at session eval | No historical pass-probability data yet (needs ≥30 Pseudotrader sessions). B4 falls back to 0.85× Kelly multiplier — conservative, not zero. Trading proceeds normally. |
| `regime_uncertain for <asset>: max_prob=0.500` | B2 at session eval | Regime classifier is uncertain on cold start (equal probability). B4 uses robust Kelly (distributional min-max) in this case. Trading proceeds normally; edge estimates sharpen with more history. |
| `PytestUnknownMarkWarning: Unknown pytest.mark.real_questdb` | pytest | The `real_questdb` marker is unregistered in `pytest.ini`. Informational only — the tests still run/skip correctly. |

---

## Quick Troubleshooting Reference

| Symptom | Most likely cause | Fix |
|---|---|---|
| B4 crashes with `TypeError: unsupported operand type(s) for -: decimal.Decimal and float` | Container running old code (pre-`4c225c0` fix) | `dco down && dco build --no-cache captain-online && dco up -d` |
| `PointValueResolutionError` in B7 | D00 missing `point_value` for an asset | Re-run `cap-run bootstrap_production.py` |
| `Session NY evaluation complete` but 0 signals, no error | B4 returned 0 contracts (cold start — no D03 history) | Normal on fresh start. Trade history accumulates; use D03 reconciliation results to improve Kelly state over time |
| `sizing FAILED` with any error | Any uncaught exception in B4 | Read the traceback; most likely a new Decimal/float boundary or a missing D08/D12 row |
| `/api/health → connected: 0` | Captain-command adapter not registered | `dco logs captain-command | grep -i error`; most likely auth failure in `.env` |
| Silo drawdown triggered (>30%), trading blocked | D16 `total_capital` corrupted or not reset after an incident | Run `reset_capital_state_to_broker_truth.py` (see `UNPAUSE_RUNBOOK.md`) |
| D03 has test residue rows | Schema validation tests left rows behind | `TRUNCATE TABLE p3_d03_trade_outcome_log` in QuestDB console (Note: DELETE FROM ... WHERE is not supported in QuestDB — only TRUNCATE or DROP PARTITION) |
| Session evaluation fired early (e.g. 09:25 instead of 09:30) | Design: orchestrator evaluates 5 min before OR open | Expected. B1→B5C run at 09:25; signals published via B6 when OR breakout detected after 09:35. |

---

*End of guide. Questions about specific test failures → paste the exact traceback.*
