# Captain System — Step-by-Step Validation Guide

**Purpose:** Walk through every check needed to confirm the Captain system is correctly loaded with all 11 P2 assets, data is correct, and integrations work.

**Pre-requisite:** Docker Desktop running (whale icon green in system tray).

---

## Step 1 — Start Docker Stack

```bash
cd captain-system
docker-compose up -d
```

Wait ~30 seconds for health checks. Verify all 6 containers:

```bash
docker-compose ps
```

**Expected output:** All 6 services show `Up (healthy)`:
- `questdb` — ports 9000, 8812, 9009
- `redis` — port 6379
- `captain-offline` — healthy
- `captain-online` — healthy
- `captain-command` — healthy
- `nginx` — ports 80, 443

If any container shows `Exit` or `Restarting`, check logs:
```bash
docker-compose logs <service-name> --tail 50
```

---

## Step 2 — Initialize QuestDB Tables

```bash
docker-compose exec captain-command python /app/scripts/init_questdb.py
```

**Expected:** 26 `[OK]` lines, one per table. No `[ERR]`.

Verify via QuestDB web console:
1. Open browser: **http://localhost:9000**
2. Run this query in the SQL editor:

```sql
SELECT table_name FROM information_schema.tables
WHERE table_name LIKE 'p3_%'
ORDER BY table_name;
```

**Expected:** 26 rows including `p3_d00_asset_universe`, `p3_d23_circuit_breaker_intraday`, `p3_d25_circuit_breaker_params`, `p3_d26_hmm_opportunity_state`.

---

## Step 3 — Seed System Parameters

```bash
docker-compose exec captain-command python /app/scripts/seed_system_params.py
```

**Verify in QuestDB console:**

```sql
SELECT count() FROM p3_d17_system_params;
```

**Expected:** `38`

Check a few key params:

```sql
SELECT param_name, value, category
FROM p3_d17_system_params
WHERE param_name IN ('max_users', 'quality_hard_floor', 'max_assets')
ORDER BY param_name;
```

**Expected:**
| param_name | value | category |
|------------|-------|----------|
| max_assets | 50 | capacity |
| max_users | 20 | capacity |
| quality_hard_floor | 0.003 | quality |

---

## Step 4 — Load All 11 Assets into P3-D00

This uses the multi-asset bridge script we built. It stages data AND registers assets in QuestDB:

```bash
docker-compose exec captain-command python /app/scripts/load_p2_multi_asset.py
```

**Note:** If running from host (not Docker), use:
```bash
python captain-system/scripts/load_p2_multi_asset.py
```

**Expected output:** 11 assets processed, each showing:
- D-06 loaded (m, k, OO)
- D-22 filtered trades count
- D-02 regime labels count
- `[OK] Registered in P3-D00`

ZT should show `INACTIVE`.

### Verify: Asset Universe (P3-D00)

```sql
SELECT asset_id, captain_status, point_value, tick_size, exchange_timezone
FROM p3_d00_asset_universe
ORDER BY asset_id;
```

**Expected:** 11 rows:

| asset_id | captain_status | point_value | tick_size | exchange_timezone |
|----------|---------------|-------------|-----------|-------------------|
| ES | WARM_UP | 50.0 | 0.25 | America/New_York |
| M2K | WARM_UP | 5.0 | 0.10 | America/New_York |
| MES | WARM_UP | 5.0 | 0.25 | America/New_York |
| MGC | WARM_UP | 10.0 | 0.10 | America/New_York |
| MNQ | WARM_UP | 2.0 | 0.25 | America/New_York |
| MYM | WARM_UP | 0.5 | 1.0 | America/New_York |
| NKD | WARM_UP | 5.0 | 5.0 | Asia/Tokyo |
| NQ | WARM_UP | 20.0 | 0.25 | America/New_York |
| ZB | WARM_UP | 1000.0 | 0.03125 | America/New_York |
| ZN | WARM_UP | 1000.0 | 0.015625 | America/New_York |
| ZT | INACTIVE | 2000.0 | 0.0078125 | America/New_York |

### Verify: Locked Strategies

```sql
SELECT asset_id, locked_strategy
FROM p3_d00_asset_universe
ORDER BY asset_id;
```

For each asset, the `locked_strategy` JSON should contain:
- `"model"` and `"feature"` matching P2-D06
- `"regime_class": "REGIME_NEUTRAL"` for all
- `"OO"` matching P2 results

Spot-check ES:

```sql
SELECT asset_id, locked_strategy
FROM p3_d00_asset_universe
WHERE asset_id = 'ES';
```

**Expected:** JSON containing `"model": 7, "feature": 33, "OO": 0.8832...`

### Verify: AIM States Seeded

```sql
SELECT asset_id, count() as aim_count
FROM p3_d01_aim_model_states
GROUP BY asset_id
ORDER BY asset_id;
```

**Expected:** Each of the 11 assets should have `6` AIMs (Tier 1: ids 4, 6, 8, 11, 12, 15).

---

## Step 5 — Run Bootstrap (Phases 3)

This initializes EWMA, BOCPD, and Kelly parameters from historical trade data:

```bash
docker-compose exec captain-command python /app/scripts/load_p2_multi_asset.py --bootstrap
```

Or if assets are already registered from Step 4, run bootstrap separately:

```bash
docker-compose exec captain-offline python -c "
import sys
sys.path.insert(0, '/app')
from scripts.load_p2_multi_asset import run_bootstrap_for_asset, promote_to_active
for asset in ['ES','MES','NQ','MNQ','M2K','MYM','NKD','MGC','ZB','ZN']:
    print(f'Bootstrapping {asset}...')
    run_bootstrap_for_asset(asset)
    promote_to_active(asset)
    print(f'  {asset} -> ACTIVE')
"
```

### Verify: EWMA States (P3-D05)

```sql
SELECT asset_id, regime_label, session_id, win_rate, avg_win, avg_loss, n_trades
FROM p3_d05_ewma_states
ORDER BY asset_id, regime_label, session_id;
```

**Expected:** Multiple rows per asset (2 regimes x sessions). Key checks:
- `win_rate` between 0.0 and 1.0
- `avg_win > 0`, `avg_loss > 0`
- `n_trades >= 5` per cell (fallback to unconditional if fewer)

### Verify: Kelly Parameters (P3-D12)

```sql
SELECT asset_id, regime_label, session_id, kelly_full, shrinkage_factor
FROM p3_d12_kelly_parameters
ORDER BY asset_id, regime_label, session_id;
```

**Expected:**
- `kelly_full >= 0` (can be 0 if win rate is too low)
- `shrinkage_factor` between 0.3 and 1.0
- Multiple rows per asset

### Verify: BOCPD State (P3-D04)

```sql
SELECT asset_id, bocpd_cp_probability, cusum_sprint_length
FROM p3_d04_decay_detector_states
ORDER BY asset_id;
```

**Expected:**
- `bocpd_cp_probability < 0.5` (stable — no detected changepoint)
- One row per asset

### Verify: Assets Promoted to ACTIVE

```sql
SELECT asset_id, captain_status, warm_up_progress
FROM p3_d00_asset_universe
ORDER BY asset_id;
```

**Expected:** 10 assets with `ACTIVE` + `warm_up_progress = 1.0`, ZT stays `INACTIVE`.

---

## Step 6 — Load TSM Account Config

```bash
docker-compose exec captain-command python -c "
import sys
sys.path.insert(0, '/app')
from captain_command.blocks.b4_tsm_manager import load_all_tsm_files
results = load_all_tsm_files()
for r in results:
    v = r['validation']
    print(f'{r[\"filename\"]:40s} valid={v[\"valid\"]}  errors={v.get(\"errors\", [])}')
"
```

**Expected:** All TSM files show `valid=True` with no errors.

### Verify in QuestDB:

```sql
SELECT account_id, name, provider, stage, starting_balance, max_drawdown_limit
FROM p3_d08_topstep_state;
```

**Expected:** At least 1 row for the XFA account. Check `max_drawdown_limit = 4500`.

---

## Step 7 — Verify Redis Channels

```bash
docker-compose exec redis redis-cli ping
```

**Expected:** `PONG`

Check Redis is empty (no stale data):

```bash
docker-compose exec redis redis-cli DBSIZE
```

**Expected:** `(integer) 0` or a small number (cached states only).

Test pub/sub connectivity:

```bash
# Terminal 1: Subscribe
docker-compose exec redis redis-cli SUBSCRIBE captain:signals:test

# Terminal 2: Publish (separate terminal)
docker-compose exec redis redis-cli PUBLISH captain:signals:test '{"test": true}'
```

**Expected:** Terminal 1 shows the test message.

---

## Step 8 — Verify GUI

Open browser: **https://localhost** (or **http://localhost:80**)

If you get a certificate warning (self-signed cert), click "Advanced" > "Proceed".

### What to Look For:

1. **Dashboard loads** — React SPA renders without blank page
2. **Asset panel** — Shows 10 ACTIVE assets + 1 INACTIVE (ZT)
3. **Signal panel** — Empty (no signals generated yet — expected)
4. **Account panel** — Shows Topstep 150K XFA account with:
   - Balance: $150,000
   - MDD limit: $4,500
   - MDD%: 3.00%
5. **Scaling display** — Shows current tier (Tier 1: 30 micros at $0 profit)
6. **Payout panel** — Shows "No payout recommended" (profit = $0)
7. **System health** — All indicators green/healthy

### If GUI doesn't load:

```bash
# Check nginx logs
docker-compose logs nginx --tail 20

# Check command API
docker-compose exec captain-command curl -s http://localhost:8000/health
```

**Expected health response:** `{"status": "healthy", ...}`

---

## Step 9 — Verify TopstepX API Connection

```bash
docker-compose logs captain-command --tail 50 | grep -i topstep
```

**Expected log lines:**
- `TopstepX: authenticating as nomaanakram4@gmail.com`
- `TopstepX: auth success, token expires ...`
- `TopstepX: resolved account 150KTC-V2-...`
- `MarketStream: connected`
- `UserStream: connected`

### Test API manually:

```bash
docker-compose exec captain-command python -c "
import sys
sys.path.insert(0, '/app')
from shared.topstep_client import get_topstep_client
client = get_topstep_client()
accounts = client.get_accounts()
for a in accounts:
    print(f'Account: {a[\"name\"]}  Balance: {a.get(\"balance\", \"N/A\")}')
"
```

**Expected:** Shows your Topstep account name and balance.

### If auth fails:

Check `.env` file has correct values:
```bash
cat captain-system/.env | grep TOPSTEP
```

Required:
- `TOPSTEP_USERNAME=nomaanakram4@gmail.com`
- `TOPSTEP_API_KEY=<your key>`

---

## Step 10 — End-to-End Data Integrity Check

Run this comprehensive query to verify the full data pipeline:

```sql
-- 1. Asset count
SELECT 'D00 assets' as check, count() as value FROM p3_d00_asset_universe
UNION ALL
SELECT 'D00 active', count() FROM p3_d00_asset_universe WHERE captain_status = 'ACTIVE'
UNION ALL
SELECT 'D00 inactive', count() FROM p3_d00_asset_universe WHERE captain_status = 'INACTIVE'
UNION ALL
-- 2. AIM states
SELECT 'D01 aim_states', count() FROM p3_d01_aim_model_states
UNION ALL
-- 3. EWMA cells
SELECT 'D05 ewma_cells', count() FROM p3_d05_ewma_states
UNION ALL
-- 4. Kelly params
SELECT 'D12 kelly_params', count() FROM p3_d12_kelly_parameters
UNION ALL
-- 5. BOCPD states
SELECT 'D04 bocpd_states', count() FROM p3_d04_decay_detector_states
UNION ALL
-- 6. System params
SELECT 'D17 sys_params', count() FROM p3_d17_system_params
UNION ALL
-- 7. TSM accounts
SELECT 'D08 tsm_accounts', count() FROM p3_d08_topstep_state;
```

**Expected results:**

| check | value |
|-------|-------|
| D00 assets | 11 |
| D00 active | 10 |
| D00 inactive | 1 |
| D01 aim_states | 66 (11 assets x 6 AIMs) |
| D05 ewma_cells | ~60+ (10 assets x regimes x sessions) |
| D12 kelly_params | ~60+ (matching D05) |
| D04 bocpd_states | 10 (1 per active asset) |
| D17 sys_params | 38 |
| D08 tsm_accounts | 1+ |

---

## Step 11 — Per-Asset Deep Validation

Pick any asset (e.g., ES) and verify the complete data chain:

### A. Locked Strategy Correct

```sql
SELECT locked_strategy FROM p3_d00_asset_universe WHERE asset_id = 'ES';
```
Verify: `model=7, feature=33, OO=0.883, regime_class=REGIME_NEUTRAL`

### B. EWMA Has Sensible Values

```sql
SELECT * FROM p3_d05_ewma_states WHERE asset_id = 'ES';
```
Verify: `win_rate` close to 0.5 (50% is typical for ORB), `avg_win > avg_loss` (positive edge)

### C. Kelly Fraction Positive

```sql
SELECT * FROM p3_d12_kelly_parameters WHERE asset_id = 'ES';
```
Verify: `kelly_full > 0` (indicates profitable strategy after shrinkage)

### D. No Decay Detected

```sql
SELECT * FROM p3_d04_decay_detector_states WHERE asset_id = 'ES';
```
Verify: `bocpd_cp_probability < 0.3` (well within stable range)

### E. Circuit Breaker State Clean

```sql
SELECT * FROM p3_d23_circuit_breaker_intraday;
```
Verify: Empty or all zeros (no trades have occurred yet)

### F. HMM State Initialized

```sql
SELECT * FROM p3_d26_hmm_opportunity_state;
```
Verify: Empty (HMM trains after first trade batches) — this is expected at cold start.

---

## Troubleshooting Quick Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container `Restarting` | Missing env var or failed import | `docker-compose logs <service> --tail 50` |
| QuestDB web console not loading | Port 9000 not exposed | Check `docker-compose ps` for port mapping |
| `Connection refused` on 8812 | QuestDB not ready yet | Wait 30s, retry. Check `docker-compose logs questdb` |
| GUI shows blank page | nginx not serving build files | `docker-compose logs nginx`, check `gui-dist` volume |
| TopstepX auth fails | Wrong credentials | Verify `.env` has correct email + API key |
| Bootstrap fails with < 20 trades | D-22 not filtered correctly | Check `captain-system/data/p1_outputs/{asset}/` file |
| Redis SUBSCRIBE shows nothing | Channel name mismatch | Verify channel names in `shared/constants.py` |
| TSM validation errors | Missing required fields | Compare against schema in `b4_tsm_manager.py` |

---

## What Success Looks Like

When everything is validated:

```
P3-D00:  11 assets (10 ACTIVE, 1 INACTIVE)
P3-D01:  66 AIM states (6 per asset, all BOOTSTRAPPED for active)
P3-D04:  10 BOCPD states (all stable, cp_prob < 0.5)
P3-D05:  60+ EWMA cells (win_rate, avg_win, avg_loss populated)
P3-D08:  1+ TSM account (Topstep 150K XFA, 12 instruments in fee schedule)
P3-D12:  60+ Kelly params (kelly_full > 0, shrinkage applied)
P3-D17:  38 system parameters
P3-D23:  Empty (no intraday trades yet)
P3-D25:  Empty (CB params populate after 100+ live trades)
P3-D26:  Empty (HMM trains after 20+ trading days)

Docker:  6 containers UP (healthy)
Redis:   PONG
GUI:     Dashboard loads, 10 active assets visible
Topstep: Auth success, account resolved, streams connected
```

**The system is then ready for Phase 8 (Shadow Deployment).**
