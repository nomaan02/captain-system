# Pre-Market Validation Test Flow

**Purpose:** End-to-end validation that a Captain System tower is correctly configured and will execute trades. Run this sequence on any tower before its first live session.

**Time required:** ~10 minutes
**Prerequisites:** All 9 Docker containers running and healthy

---

## Test Sequence

### Test 0: Containers Healthy

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

**Expected:** All 9 containers show `healthy` or `running`. No containers in `restarting` or `exited` state.

---

### Test 1: Captain-Online Startup

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-online 2>&1 | head -20
```

**Expected:**
- `QuestDB: connected`
- `Redis: connected`
- `TopstepX authenticated as <email>`
- `Resolved 10 contracts: [ES, MES, NQ, MNQ, M2K, MYM, NKD, MGC, ZB, ZN]`
- `MarketStream STARTED for 10 contracts`
- `MarketStream CONNECTED`
- `Online orchestrator starting...`

**Fail if:** Auth failed, 0 contracts resolved, or MarketStream not connected.

---

### Test 2: Phase A Dry Run — NY Session

Exercises the full B1→B5C pipeline (data ingestion, regime, AIM, Kelly sizing, trade selection, quality gate, circuit breaker) without publishing signals.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-online python3 /app/dry_run_phase_a.py 1
```

**Expected:**
- `B1: 8 assets, ~224 features computed`
- `B2: 8 assets classified` (all neutral/uncertain on cold start is normal)
- `B3: 8 assets scored` (combined_modifier ~0.95-0.98)
- `B4: 5-6 assets with non-zero contracts`
- `B5: 5 trades selected` (capped at max_simultaneous_positions)
- `B5B: 5 recommended`
- `B5C: 5 passed`
- `VERDICT: Phase A would produce signals. System ready to trade.`

**Fail if:** Any block shows `CRASHED` or `FAILED`. Check the traceback — the most likely cause is a data format issue in QuestDB.

**Note:** "Data missing timezone offset" warnings for all assets are expected — the dry run runs in a separate process without the MarketStream, so the quote cache is empty. This does not occur during real trading.

---

### Test 3: Phase A Dry Run — LON Session

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-online python3 /app/dry_run_phase_a.py 2
```

**Expected:**
- `B1: 1 asset` (MGC only)
- All blocks pass through to B5C
- `VERDICT: Phase A would produce signals.`

**Fail if:** `B1: No active assets for session LON` — means MGC's `session_hours` column in D00 is missing the LON key.

---

### Test 4: Phase A Dry Run — APAC Session

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-online python3 /app/dry_run_phase_a.py 3
```

**Expected:**
- `B1: 1 asset` (NKD only)
- All blocks pass through to B5C
- `VERDICT: Phase A would produce signals.`

**Fail if:** `B1: No active assets for session APAC` — means NKD's `session_hours` column in D00 is missing the APAC key.

---

### Test 5: Captain-Command Adapter Connection

Queries the live health API endpoint inside the running orchestrator process.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command \
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

**Fail if:** `"connected": 0` — the TopstepX adapter failed to initialize. Check command startup logs (Test 6).

---

### Test 6: Captain-Command Startup Logs

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-command \
  | grep -i "topstep\|adapter\|CONNECTED\|account"
```

**Expected:**
- `TopstepX authenticated as <email>`
- `TopstepX account: <ACCOUNT_NAME> (id=<ACCOUNT_ID>, balance=<AMOUNT>)`
- `TopstepX CONNECTED: account=<ACCOUNT_NAME> (id=<ACCOUNT_ID>), balance=<AMOUNT>, canTrade=True`

**Fail if:** `canTrade=False`, no account found, or auth failed.

**Critical check:** The `id=<ACCOUNT_ID>` shown here MUST match what's in QuestDB D16. If it doesn't, signals will size trades for one account but the adapter will look up a different account and silently fail.

---

### Test 7: Account ID Match Verification

Verify the account ID in the adapter matches QuestDB.

```bash
# Check what TopstepX API returns
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command python3 -c "
from shared.topstep_client import get_topstep_client
client = get_topstep_client()
client.authenticate()
for acc in client.get_accounts(only_active=True):
    print(f'  Name: {acc.get(\"name\")}')
    print(f'  ID:   {acc.get(\"id\")}')
    print(f'  Balance: \${acc.get(\"balance\", 0):.2f}')
    print(f'  canTrade: {acc.get(\"canTrade\")}')
    print()
"
```

Compare the ID with what's in D16:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command python3 -c "
from shared.questdb_client import get_cursor
with get_cursor() as cur:
    cur.execute('SELECT accounts FROM p3_d16_user_capital_silos LATEST ON last_updated PARTITION BY user_id')
    row = cur.fetchone()
    print(f'D16 accounts: {row[0] if row else \"NOT FOUND\"}')
"
```

**Expected:** The account ID from the API appears inside the D16 `accounts` JSON array.

**If they don't match:** Run the account migration (see "Account Migration" section below).

---

### Test 8: TopstepX Order Round Trip

Places a limit order that will never fill and immediately cancels it. Proves the full API auth → account → contract resolution → order placement → cancellation path.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command \
  python3 /app/test_order_roundtrip.py
```

**Expected:**
- `Authenticated as <email>`
- `Account: <NAME> (id=<ID>)`
- `Balance: $<AMOUNT>, canTrade: True`
- `MES → CON.F.US.MES.M26`
- `Order PLACED: orderId=<NUMBER>`
- `Order CANCELLED`
- `Clean: no leftover orders`
- `RESULT: PASSED`

**Fail if:** Order rejected, cancel failed, or auth error. Check the error message — common causes are account not active, market closed for the contract, or API rate limiting.

---

### Test 9: AUTO_EXECUTE Enabled

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command \
  python3 -c "import os; v=os.environ.get('AUTO_EXECUTE',''); print(f'AUTO_EXECUTE={v} (active={v.lower() in (\"1\",\"true\",\"yes\")})')"
```

**Expected:** `AUTO_EXECUTE=true (active=True)`

**Fail if:** `active=False` — signals will appear in the GUI but orders will NOT be placed automatically. Update `.env` and restart.

---

### Test 10: Instance Parity (Multi-Instance Only)

Only relevant if two towers are running. Skip for single-instance deployments.

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command \
  python3 -c "import os; print(f'INSTANCE_PARITY={os.environ.get(\"INSTANCE_PARITY\", \"(not set — takes all trades)\")}')"
```

**Expected:**
- Tower-1 (Nomaan): `INSTANCE_PARITY=0` (takes odd signals)
- Tower-2 (Isaac): `INSTANCE_PARITY=1` (takes even signals)
- Single instance: `(not set — takes all trades)`

---

## Results Summary

| Test | What it proves |
|------|---------------|
| 0 | Infrastructure running |
| 1 | Market data streaming |
| 2 | NY signal pipeline (B1-B5C) |
| 3 | LON signal pipeline (MGC) |
| 4 | APAC signal pipeline (NKD) |
| 5 | API adapter connected |
| 6 | Correct account linked |
| 7 | D16 ↔ adapter account match |
| 8 | Order placement works |
| 9 | Auto-execute enabled |
| 10 | Parity correctly assigned |

**All 10 pass = system will trade at next session open.**

---

## Account Migration

If Test 7 reveals a mismatch between the TopstepX account ID and QuestDB, or if setting up a new tower with a different account, the D16/D08/D25 tables need updating.

### Getting the account ID

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command python3 -c "
from shared.topstep_client import get_topstep_client
client = get_topstep_client()
client.authenticate()
for acc in client.get_accounts(only_active=True):
    print(f'  Name: {acc.get(\"name\")}')
    print(f'  ID:   {acc.get(\"id\")}')
    print(f'  Balance: \${acc.get(\"balance\", 0):.2f}')
    print(f'  canTrade: {acc.get(\"canTrade\")}')
    print()
"
```

### Running the migration

The migration script is instance-specific (account IDs and names differ per tower). To generate the correct script for a new tower:

**Prompt to give Claude Code:**

> I need to run the account migration on Isaac's tower. His old account ID is `OLD_ID`, new account ID is `NEW_ID`, and account name is `ACCOUNT_NAME`. Run the migration script with these values. The command is:
>
> ```
> docker compose -f docker-compose.yml -f docker-compose.local.yml run --rm \
>   -v "$(pwd)/scripts:/app/scripts" captain-command \
>   python3 /app/scripts/migrate_account.py OLD_ID NEW_ID "ACCOUNT_NAME"
> ```
>
> Replace OLD_ID, NEW_ID, and ACCOUNT_NAME with the actual values from the account query above.

### After migration

```bash
# 1. Update .env
nano .env
# Set: TOPSTEP_ACCOUNT_NAME=<ACCOUNT_NAME from above>

# 2. Restart containers
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d

# 3. Re-run Tests 5, 6, 7 to verify
```

---

## Session Schedule

All times are America/New_York (ET):

| Session | Open | Assets | OR Window |
|---------|------|--------|-----------|
| LON | 03:00 | MGC | 03:00–03:05 |
| NY | 09:30 | ES, MES, NQ, MNQ, M2K, MYM, ZB, ZN | 09:30–09:35 |
| APAC | 18:00 | NKD | 18:00–18:05 |

The orchestrator detects each session within a 5-minute window of the open time. Phase A runs immediately, Phase B (signal output) fires when OR breakouts are detected after the OR window closes.

---

## Troubleshooting

### "No active assets for session X"
The asset's `session_hours` column in D00 is missing the session key. Re-run `bootstrap_production.py` to fix.

### "Session NY evaluation FAILED"
Check the full traceback in captain-online logs. The 2026-04-14 crash was caused by timezone-naive economic calendar datetimes — fixed in commit `8061381`.

### Adapter connected=0
Check captain-command logs for TopstepX auth errors. Common causes:
- Wrong `TOPSTEP_USERNAME` or `TOPSTEP_API_KEY` in `.env`
- `TOPSTEP_ACCOUNT_NAME` doesn't match any active account
- TopstepX API outage

### Signals generated but no orders placed
- Check `AUTO_EXECUTE=true` in `.env`
- Verify account ID match (Test 7)
- Check compliance gate: `config/compliance_gate.json`
- Check command logs for "Auto-execute: adapter not connected" or "no adapter for account"
