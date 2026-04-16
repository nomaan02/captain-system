# Captain System — Linux Tower Deployment Guide

> Complete step-by-step for deploying Captain System on a Linux tower from a fresh git clone.
> All commands are **fish shell** compatible. No bash-only syntax.
>
> **For Isaac's tower:** Replace all instances of `/home/nomaan/` with Isaac's actual home directory, and `User=nomaan` with his username in the systemd service file.

---

## Prerequisites

Before starting, the tower needs:

- **Docker Engine + Docker Compose V2** (native Linux Docker, NOT Docker Desktop)
- **Python 3.10+**
- **curl**, **git**, **nano** (or any text editor)
- **sudo** access

---

## PHASE 1: Clone & Initial Setup

### Step 1 — Clone the repo

```fish
# For YOUR tower (primary instance):
git clone git@github.com:nomaan02/captain-system.git ~/captain-system
cd ~/captain-system

# OR for the SECOND instance (multi-user deployment):
git clone git@github.com:nomaan02/captain-multi-user.git ~/captain-system
cd ~/captain-system
```

### Step 2 — Create the .env file

The `.env` file contains credentials and is NOT in git. You must create it.

**Option A — Interactive wizard (recommended for first-time setup):**

```fish
bash scripts/captain-setup.sh
```

This walks you through everything and handles Steps 3-7 automatically. If you use this, **skip to Step 9**.

**Option B — Manual creation:**

```fish
cp .env.template .env
nano .env
```

Fill in every value. Here's what each one is:

| Variable | Example value | What it is |
|----------|--------------|------------|
| `TOPSTEP_USERNAME` | `nomaanakram4@gmail.com` | Your TopstepX login email |
| `TOPSTEP_API_KEY` | (from TopstepX dashboard) | API key for brokerage access |
| `TOPSTEP_ACCOUNT_NAME` | `150KTC-V2-551001-19064435` | Account name from TopstepX |
| `TRADING_ENVIRONMENT` | `LIVE` or `PAPER` | Trading mode |
| `AUTO_EXECUTE` | `true` or `false` | `true` = auto-trade, `false` = manual confirm in GUI |
| `INSTANCE_PARITY` | `0`, `1`, or blank | `0`=odd signals, `1`=even signals, blank=all signals |
| `TOPSTEP_CONTRACT_ID` | `CON.F.US.MES.M26` | Active contract (changes quarterly) |
| `VAULT_MASTER_KEY` | (generate — see below) | Encryption key for API vault |
| `TELEGRAM_BOT_TOKEN` | (from @BotFather) | For alert notifications |
| `TELEGRAM_CHAT_ID` | `8616119618` | Your Telegram chat ID |
| `JWT_SECRET_KEY` | (generate — see below) | GUI authentication |
| `API_SECRET_KEY` | (generate — see below) | API authentication |
| `JWT_EXPIRY_HOURS` | `24` | How long GUI login lasts |
| `QUESTDB_USER` | `captain` | Database username |
| `QUESTDB_PASSWORD` | (generate — see below) | Database password |
| `REDIS_PASSWORD` | (generate — see below) | Redis password |

**Generate secure values** (run each one, copy the output into .env):

```fish
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # VAULT_MASTER_KEY
python3 -c "import secrets; print(secrets.token_hex(32))"        # JWT_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # API_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(16))"   # QUESTDB_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(16))"   # REDIS_PASSWORD
```

Lock down permissions:

```fish
chmod 600 .env
```

---

## PHASE 2: Transfer Files That Aren't In Git

Some files are gitignored and must be copied from the development laptop.

### Step 3 — What needs transferring

**Two pre-built bundles exist on the laptop** at:

| File | Windows Explorer path | Size | Contents |
|------|-----------------------|------|----------|
| `captain-transfer-small.tar.gz` | `\\wsl.localhost\Ubuntu\home\nomaan\captain-transfer-small.tar.gz` | 644 KB | .env, VIX data, macro data, TLS certs |
| `captain-transfer-questdb.tar.gz` | `\\wsl.localhost\Ubuntu\home\nomaan\captain-transfer-questdb.tar.gz` | 6.2 MB | Entire QuestDB database (all tables, pre-populated) |

**Total transfer: ~7 MB**

### Step 3a — How to transfer via AnyDesk

**Method 1 — AnyDesk file transfer panel:**
1. In AnyDesk toolbar, click the file transfer icon (folder with arrow)
2. Left side (laptop): navigate to `\\wsl.localhost\Ubuntu\home\nomaan\`
3. Right side (tower): navigate to `/home/nomaan/` (or your home dir)
4. Select both `.tar.gz` files, click transfer arrow
5. Takes seconds

**Method 2 — Copy to Windows desktop first:**

On the laptop (in WSL terminal):
```fish
cp /home/nomaan/captain-transfer-small.tar.gz /mnt/c/Users/nomaa/Desktop/
cp /home/nomaan/captain-transfer-questdb.tar.gz /mnt/c/Users/nomaa/Desktop/
```

Then use AnyDesk file transfer from `C:\Users\nomaa\Desktop\` instead.

**Method 3 — SCP (if both on same network):**

On the tower:
```fish
scp nomaan@LAPTOP_IP:/home/nomaan/captain-transfer-small.tar.gz ~/
scp nomaan@LAPTOP_IP:/home/nomaan/captain-transfer-questdb.tar.gz ~/
```

### Step 3b — Extract on the tower

```fish
cd ~/captain-system

# Extract small files (.env, VIX data, macro data, certs)
tar xzf ~/captain-transfer-small.tar.gz

# Extract QuestDB database (needs sudo due to file ownership)
sudo rm -rf questdb/db
sudo tar xzf ~/captain-transfer-questdb.tar.gz

# Verify
echo "--- .env ---"
ls -la .env
echo "--- VIX data ---"
ls data/vix/
echo "--- QuestDB ---"
sudo du -sh questdb/db/
```

**Expected output:**
- `.env` file exists (763 bytes)
- `data/vix/` has 5 CSV files (vix_daily_close.csv, vxv_daily_close.csv, etc.)
- `questdb/db/` is ~1016 MB

**Troubleshooting:**

| Error | Fix |
|-------|-----|
| `tar: Error opening archive` | File didn't transfer completely. Re-transfer. |
| `Permission denied` on QuestDB extract | Use `sudo tar xzf` as shown above. QuestDB files are owned by container UID. |
| `No such file or directory: captain-system` | You haven't cloned the repo yet. Go back to Step 1. |
| `Cannot mkdir: Permission denied` | You forgot `sudo rm -rf questdb/db` before extracting. Clear it first. |

### What's in git vs what needs transferring

| Source | In Git? | Transfer needed? |
|--------|---------|-----------------|
| All source code, configs, scripts | YES | NO — `git clone` gets it |
| `data/p1_outputs/` (81 MB, P1 research) | YES | NO |
| `data/p2_outputs/` (1.2 MB, locked strategies) | YES | NO |
| `data/seed/` (1.7 MB, AIM bootstrap data) | YES | NO |
| `data/qdb_export/` (344 KB, table exports) | YES | NO |
| `.env` (credentials) | NO | YES — in small bundle |
| `data/vix/` (VIX daily CSVs) | NO | YES — in small bundle |
| `data/macro/` (GPR index) | NO | YES — in small bundle |
| `nginx/certs/` (self-signed TLS) | NO | YES — in small bundle (or regenerate) |
| `questdb/db/` (1 GB database) | NO | YES — in QuestDB bundle (or re-bootstrap from Step 8) |
| `redis/` (transient) | NO | NO — reconstructs from QuestDB at startup |
| `vault/` (empty) | NO | NO — fresh init on new machine |

---

## PHASE 3: Build & Start Containers

### Step 4 — Set kernel parameter (QuestDB requirement)

```fish
sudo sysctl -w vm.max_map_count=1048576

# Make permanent (survives reboots)
echo "vm.max_map_count=1048576" | sudo tee -a /etc/sysctl.conf
```

Verify:
```fish
cat /proc/sys/vm/max_map_count
```
Should print `1048576`.

Also set memory overcommit for Redis:
```fish
sudo sysctl -w vm.overcommit_memory=1

# Make permanent
echo "vm.overcommit_memory=1" | sudo tee -a /etc/sysctl.conf
```

**Troubleshooting:**

| Error | Fix |
|-------|-----|
| `Permission denied` | You need sudo. If no sudo, ask whoever set up the tower. |
| Value resets after reboot | The `tee -a /etc/sysctl.conf` line makes it permanent. Check it was written: `grep max_map_count /etc/sysctl.conf` |

### Step 5 — Create required directories

```fish
cd ~/captain-system
mkdir -p questdb/db redis logs logs/incidents logs/crash_reports backups/questdb vault
```

If you extracted the QuestDB bundle, `questdb/db/` already has data. `mkdir -p` won't overwrite it.

### Step 6 — Build and start all containers

```fish
cd ~/captain-system
bash captain-start.sh --build
```

**First build takes ~5 minutes** (downloads Docker images, compiles Python deps, builds React GUI).
Subsequent starts without `--build` take ~30 seconds.

**What you'll see (in order):**

1. `vm.max_map_count OK` — kernel parameter validated
2. `Docker daemon OK` — Docker engine running
3. `Project files OK` — docker-compose.yml, .env found
4. `Backing up QuestDB data` — backs up before touching containers
5. `Config synced into build contexts` — copies config/ into service dirs
6. Docker build output (downloading, compiling...)
7. `QuestDB SQL engine: ready` — database is up
8. `Redis: PONG` — Redis is up
9. `QuestDB table init complete` — 34 tables created/verified
10. `INTEGRITY_OK` or `INTEGRITY_FAIL` — data check on critical tables
11. `VIX/VXV update complete` — fresh VIX data
12. `All containers running` — all 6 services healthy
13. `Captain System running (local mode)` — done

**Note:** If you see `Redis not ready after 60s`, the Redis health check may be failing to authenticate. Verify Redis is actually healthy with `docker compose -f docker-compose.yml -f docker-compose.local.yml ps`. If Redis shows `healthy`, this is cosmetic — the startup script reads `REDIS_PASSWORD` from `.env` for the health check, but if the `.env` path can't be resolved, the check runs without auth and times out. Re-running usually resolves it.

**Troubleshooting:**

| Error | Cause | Fix |
|-------|-------|-----|
| `Docker Desktop not available` | Docker not running | `sudo systemctl start docker` then verify with `docker info` |
| `Cannot cd to /home/nomaan/captain-system` | Wrong path hardcoded | Run with: `CAPTAIN_DIR=/home/YOURUSER/captain-system bash captain-start.sh --build` |
| `Missing .env` | .env not created | Go back to Step 2 |
| `port 9000 already in use` | Another process on that port | `sudo lsof -i :9000` to find it, then stop it |
| `INTEGRITY_FAIL` | QuestDB has no data | Expected if you DIDN'T transfer QuestDB. Continue to Step 8. |
| `no matching manifest for linux/amd64` | Wrong CPU architecture | `uname -m` should be `x86_64` |
| Build hangs or very slow | Low RAM | `free -h` — need at least 4 GB free |
| `Redis not ready after 60s` | Password auth issue in check | Cosmetic. If `docker compose ps` shows redis healthy, ignore this. |

**If the script fails partway**, it's safe to re-run:
```fish
bash captain-start.sh --build
```

### Step 7 — Verify all containers are running

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

**Expected:** 6 containers, all showing `Up` and `(healthy)`:
- `questdb` — ports 8812, 9000, 9009
- `redis` — port 6379
- `captain-offline` — no exposed port
- `captain-online` — no exposed port
- `captain-command` — port 8000
- `nginx` — port 80

---

## PHASE 4: Bootstrap QuestDB Data

> **Skip this entire phase if you transferred `captain-transfer-questdb.tar.gz` and the integrity check in Step 6 showed `INTEGRITY_OK`.**
>
> The transferred database already has all data from the laptop.

If `INTEGRITY_FAIL` appeared, or you didn't transfer QuestDB, run these to populate from scratch.

> **IMPORTANT — Schema fix required before bootstrapping (fresh bootstrap only).**
> If you transferred `captain-transfer-questdb.tar.gz`, these columns already exist — skip this box.
>
> If bootstrapping from scratch, the bootstrap script expects two columns that `init_questdb.py` does not create. Add them **before** running Step 8a, or the script will fail at phase 4:
>
> ```fish
> docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T questdb curl -s "http://localhost:9000/exec?query=ALTER+TABLE+p3_d25_circuit_breaker_params+ADD+COLUMN+l_star+DOUBLE"
> docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T questdb curl -s "http://localhost:9000/exec?query=ALTER+TABLE+p3_d25_circuit_breaker_params+ADD+COLUMN+cold_start+BOOLEAN"
> ```
>
> Both should return `{"ddl":"OK"}`. If you see `duplicate column`, the column already exists — safe to continue.

> **WARNING — These scripts are NOT idempotent.** QuestDB is append-only, so re-running any bootstrap or seed script creates duplicate rows. **Run each step exactly once.** If a step fails partway through, see "Recovery: Truncate and re-run" below before retrying.

### Step 8a — Seed all assets (D00 base rows, EWMA, Kelly, AIM states)

This populates: D00 (asset universe base rows), D01 (AIM model states), D05 (EWMA states), D12 (Kelly parameters).

> **This must run BEFORE bootstrap.** The bootstrap script updates D00 rows — they must exist first.

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/seed_all_assets.py
```

**Expected:** 10 assets seeded with EWMA, Kelly, BOCPD states from P1/P2 trade logs.

**Troubleshooting:**

| Error | Fix |
|-------|-----|
| `container captain-offline is not running` | Start containers first: `bash captain-start.sh` |
| `psycopg2.OperationalError: connection refused` | QuestDB not ready. Wait 30s and retry. |

### Step 8b — Bootstrap production config

This updates D00 with locked strategies and populates: D02 (AIM weights), D16 (capital silo), D25 (circuit breaker).

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app -e BOOTSTRAP_ACCOUNT_ID=20319811 -e BOOTSTRAP_USER_ID=primary_user -e BOOTSTRAP_STARTING_CAPITAL=150000 captain-offline python /captain/scripts/bootstrap_production.py
```

Change `BOOTSTRAP_ACCOUNT_ID` to your actual TopstepX account ID if different from `20319811`.

**Expected:** Phases 1-4 complete, 10 assets updated, 60 AIM weights, 1 capital silo, 1 circuit breaker row.

**Troubleshooting:**

| Error | Fix |
|-------|-----|
| `Asset ES not found in p3_d00_asset_universe` | Step 8a was not run first, or D00 was truncated. Run Step 8a first. |
| `Invalid column: l_star` | You skipped the schema fix above. Run the two ALTER TABLE commands, then see "Recovery" below. |
| `Invalid column: cold_start` | You skipped the schema fix above. Run the two ALTER TABLE commands, then see "Recovery" below. |
| `container captain-offline is not running` | Start containers first: `bash captain-start.sh` |
| `psycopg2.OperationalError: connection refused` | QuestDB not ready. Wait 30s and retry. |

### Recovery: Truncate and re-run

If bootstrap or seed scripts were run more than once (e.g. after fixing a column error), you **must** truncate all affected tables before re-running. Otherwise row counts will be inflated with duplicates.

```fish
# Truncate all bootstrap/seed tables
for tbl in p3_d00_asset_universe p3_d01_aim_model_states p3_d02_aim_meta_weights p3_d05_ewma_states p3_d08_tsm_state p3_d12_kelly_parameters p3_d16_user_capital_silos p3_d25_circuit_breaker_params p3_d29_opening_volumes p3_d30_daily_ohlcv p3_d31_implied_vol p3_d32_options_skew p3_d33_opening_volatility
    docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T questdb curl -s "http://localhost:9000/exec?query=TRUNCATE+TABLE+$tbl"
    echo "$tbl truncated"
end
```

Each line should return `{"ddl":"OK"}`. After truncating, re-run Steps 8a through 8e **once each**.

### Step 8c — Seed AIM historical data

Run each command one at a time. These populate D29-D33 tables.

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/seed_iv_rv_from_extract.py
```

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/seed_skew_from_extract.py
```

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/seed_ohlcv_from_qc.py
```

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/seed_or_volumes_from_qc.py
```

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/seed_opening_vol_from_qc.py
```

### Step 8e — Initialize D08 TSM state and activate AIMs

> **IMPORTANT:** `bootstrap_production.py` does NOT insert D08 (TSM state) rows. Without this step, the system has no account trading limits and will not execute trades.

This script does three things:
1. Converts EWMA avg_win/avg_loss from r_mi units to dollars
2. Activates Tier 1 AIMs (INSTALLED → ACTIVE) in D01
3. Inserts the D08 TSM state row with TopstepX 150K combine limits ($2,250 max daily loss, $4,500 max drawdown, $6,000 profit target)

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/fix_bootstrap_data.py
```

**Expected:**
- `FIX 1: Convert EWMA values from r_mi to dollars` — converts ~60 entries
- `FIX 2: Activate Tier 1 AIMs` — activates 60 AIMs (10 assets x 6 AIMs)
- `FIX 3: Set TSM max_daily_loss` — inserts complete D08 row
- `Result: PASS`

You can preview changes first with `--dry-run`:
```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/fix_bootstrap_data.py --dry-run
```

**Troubleshooting:**

| Error | Fix |
|-------|-----|
| `Result: FAIL` after EWMA fix | Some values may already be in dollars. Re-running is safe — it only converts values < 10.0. |
| `No module named 'shared'` | PYTHONPATH not set. Ensure `-e PYTHONPATH=/app` is in the command. |

### Step 8f — Verify data was populated

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T questdb curl -s "http://localhost:9000/exec?query=SELECT+count()+FROM+p3_d00_asset_universe"
```

Should return JSON with `"dataset":[[10]]` (10 assets).

Check all critical tables:

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T questdb curl -s "http://localhost:9000/exec?query=SELECT+count()+FROM+p3_d01_aim_model_states"
```

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T questdb curl -s "http://localhost:9000/exec?query=SELECT+count()+FROM+p3_d02_aim_meta_weights"
```

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T questdb curl -s "http://localhost:9000/exec?query=SELECT+count()+FROM+p3_d12_kelly_parameters"
```

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T questdb curl -s "http://localhost:9000/exec?query=SELECT+count()+FROM+p3_d16_user_capital_silos"
```

**Expected row counts from a clean single run:**

| Table | Expected | Notes |
|-------|----------|-------|
| p3_d00_asset_universe | ~37 | 17 base + update rows (QuestDB append-only). NOT 10 — that's the distinct active count. |
| p3_d01_aim_model_states | ~120 | From P1/P2 trade logs |
| p3_d02_aim_meta_weights | 60 | 10 assets x 6 AIMs |
| p3_d05_ewma_states | 60 | 10 assets x 6 AIMs |
| p3_d12_kelly_parameters | 60 | 10 assets x 6 AIMs |
| p3_d16_user_capital_silos | 1 | Single user |
| p3_d25_circuit_breaker_params | 1 | Single account |
| p3_d08_tsm_state | 1 | Single account (from Step 8e) |

**If counts are significantly higher** (e.g. D00 > 100), scripts were run more than once. See "Recovery: Truncate and re-run" above.

---

## PHASE 4.5: Account Migration (Multi-User Deployments)

> **Skip this phase if:**
> - You bootstrapped from scratch (Steps 8a-8e) with the correct `BOOTSTRAP_ACCOUNT_ID` for this tower
> - This tower uses the same TopstepX account as the source data
>
> **You MUST run this phase if:**
> - You transferred the QuestDB bundle from another tower (e.g. Nomaan's laptop → Isaac's tower)
> - The QuestDB data contains a different account ID than this tower's TopstepX account

When the QuestDB bundle is transferred, D16 (capital silo), D08 (TSM state), and D25 (circuit breaker) all contain the **source tower's** account ID. This tower's TopstepX account has a different ID, so these tables must be migrated.

### Step 8.5a — Find this tower's account ID

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command python3 -c "
from shared.topstep_client import get_topstep_client
client = get_topstep_client()
client.authenticate()
for acc in client.get_accounts(only_active=True):
    print(f'  Name: {acc.get(\"name\")}')
    print(f'  ID:   {acc.get(\"id\")}')
    print(f'  Balance: \${acc.get(\"balance\", 0):.2f}')
    print(f'  canTrade: {acc.get(\"canTrade\")}')
"
```

Note the `ID` value — this is the NEW account ID.

### Step 8.5b — Check what's currently in QuestDB

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command python3 -c "
from shared.questdb_client import get_cursor
with get_cursor() as cur:
    cur.execute('SELECT accounts FROM p3_d16_user_capital_silos LATEST ON last_updated PARTITION BY user_id')
    row = cur.fetchone()
    print(f'D16 accounts: {row[0] if row else \"NOT FOUND\"}')
"
```

If the D16 account ID **already matches** the API account ID from Step 8.5a, skip to Phase 5.

### Step 8.5c — Run the migration

Replace `OLD_ID`, `NEW_ID`, and `NEW_NAME` with actual values:
- `OLD_ID`: the account ID currently in D16 (from Step 8.5b)
- `NEW_ID`: this tower's account ID (from Step 8.5a)
- `NEW_NAME`: the account name from Step 8.5a

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-command python3 /app/scripts/migrate_account.py OLD_ID NEW_ID "NEW_NAME"
```

**Example** (migrating from Nomaan's account to Isaac's):
```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-command python3 /app/scripts/migrate_account.py 20319811 20260837 "150KTC-V2-551001-19064435"
```

**Expected:**
- `D16: OK` — capital silo updated with new account
- `D08: OK` — TSM state migrated (balance reset to starting capital, drawdown reset to 0)
- `D25: OK` — circuit breaker params copied (or cold-start defaults inserted)
- `MIGRATION COMPLETE`

### Step 8.5d — Update .env and restart

```fish
nano ~/captain-system/.env
# Update: TOPSTEP_ACCOUNT_NAME=<NEW_NAME from Step 8.5a>

# Restart containers to pick up new .env
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

**Troubleshooting:**

| Error | Fix |
|-------|-----|
| `No existing D16 row found` | QuestDB has no capital silo data. Run Phase 4 (bootstrap from scratch) instead. |
| `No D08 row for account X` | D08 was never initialized. Run Step 8e first with the OLD account, then re-run migration. |
| Account ID still wrong after migration | QuestDB is append-only — the migration inserts new rows. The `LATEST ON` queries will pick them up. Restart containers. |

---

## PHASE 5: Cron Jobs & Automation

### Step 9 — Install cron jobs (VIX update, health monitoring, backups)

All three cron jobs are installed in one step using a non-interactive command.

> **Change `/home/nomaan/` to the actual home directory** if deploying on a different user account.

First, create the healthcheck script:

```fish
printf '#!/bin/bash
cd ~/captain-system
TELEGRAM_TOKEN=$(grep -oP '"'"'TELEGRAM_BOT_TOKEN=\\K.+'"'"' .env 2>/dev/null || echo "")
CHAT_ID=$(grep -oP '"'"'TELEGRAM_CHAT_ID=\\K.+'"'"' .env 2>/dev/null || echo "")

send_alert() {
    if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \\
            -d "chat_id=${CHAT_ID}" -d "text=CAPTAIN $(hostname): $1" --max-time 10 >/dev/null 2>&1
    fi
    echo "$(date '"'"'+%%Y-%%m-%%d %%H:%%M:%%S'"'"') $1"
}

for svc in questdb redis captain-offline captain-online captain-command nginx; do
    state=$(docker compose -f docker-compose.yml -f docker-compose.local.yml ps --format '"'"'{{.State}}'"'"' "$svc" 2>/dev/null)
    if [ "$state" != "running" ]; then
        send_alert "$svc is $state — restarting..."
        docker compose -f docker-compose.yml -f docker-compose.local.yml restart "$svc" 2>/dev/null
        sleep 15
        new_state=$(docker compose -f docker-compose.yml -f docker-compose.local.yml ps --format '"'"'{{.State}}'"'"' "$svc" 2>/dev/null)
        if [ "$new_state" = "running" ]; then
            send_alert "$svc recovered after restart."
        else
            send_alert "$svc FAILED TO RESTART ($new_state). Manual intervention required."
        fi
    fi
done
' > ~/healthcheck.sh
chmod +x ~/healthcheck.sh
```

Create the backup directory:

```fish
mkdir -p ~/backups
```

Now install all three cron jobs at once (non-interactive — do NOT use `crontab -e`, it opens a blank editor):

```fish
printf '# VIX/VXV daily data update — weekdays 10 PM
0 22 * * 1-5 /home/nomaan/captain-system/scripts/update_vix_data.sh >> /home/nomaan/captain-system/logs/vix_update.log 2>&1

# Container health monitoring — every 5 minutes
*/5 * * * * /home/nomaan/healthcheck.sh >> /home/nomaan/captain-system/logs/healthcheck.log 2>&1

# Daily QuestDB backup — 2 AM, 14-day retention
0 2 * * * cd /home/nomaan/captain-system && tar czf /home/nomaan/backups/questdb-$(date +\\%%Y\\%%m\\%%d).tar.gz questdb/db/ 2>/dev/null && find /home/nomaan/backups/ -name "questdb-*.tar.gz" -mtime +14 -delete
' | crontab -
```

Verify all three are installed:
```fish
crontab -l
```

Test the VIX update works right now:
```fish
bash ~/captain-system/scripts/update_vix_data.sh
echo $status
tail -3 ~/captain-system/data/vix/vix_daily_close.csv
```

**Troubleshooting:**

| Error | Fix |
|-------|-----|
| `curl: command not found` | `sudo apt install curl` |
| `python3: command not found` | `sudo apt install python3` |
| Script runs but VIX file empty | CBOE may be down. Check: `curl -I https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv` |
| Cron doesn't seem to run | Check log: `cat ~/captain-system/logs/vix_update.log`. Verify cron daemon is running: `systemctl status cron` |
| `crontab -e` opens blank editor | Don't use `-e`. Use the `printf ... | crontab -` method above. |

### Step 10 — (Recommended) Auto-start on boot

Makes Captain start automatically when the tower reboots.

```fish
printf '[Unit]
Description=Captain Trading System
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=nomaan
WorkingDirectory=/home/nomaan/captain-system
ExecStart=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.local.yml down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
' | sudo tee /etc/systemd/system/captain.service > /dev/null
```

**Change `User=nomaan` and all paths** to match the tower's actual username.

Then enable the service:
```fish
sudo systemctl daemon-reload
sudo systemctl enable captain.service
```

Test it:
```fish
sudo systemctl start captain.service
sudo systemctl status captain.service
```

### Step 11 — (Recommended) Health monitoring with Telegram alerts

Checks every 5 minutes if containers are alive. Restarts dead ones and sends Telegram alerts.

Create the script:

```fish
nano ~/healthcheck.sh
```

Paste this content:

```bash
#!/bin/bash
cd ~/captain-system
TELEGRAM_TOKEN=$(grep -oP 'TELEGRAM_BOT_TOKEN=\K.+' .env 2>/dev/null || echo "")
CHAT_ID=$(grep -oP 'TELEGRAM_CHAT_ID=\K.+' .env 2>/dev/null || echo "")

send_alert() {
    if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
            -d "chat_id=${CHAT_ID}" -d "text=CAPTAIN $(hostname): $1" --max-time 10 >/dev/null 2>&1
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1"
}

for svc in questdb redis captain-offline captain-online captain-command nginx; do
    state=$(docker compose -f docker-compose.yml -f docker-compose.local.yml ps --format '{{.State}}' "$svc" 2>/dev/null)
    if [ "$state" != "running" ]; then
        send_alert "$svc is $state — restarting..."
        docker compose -f docker-compose.yml -f docker-compose.local.yml restart "$svc" 2>/dev/null
        sleep 15
        new_state=$(docker compose -f docker-compose.yml -f docker-compose.local.yml ps --format '{{.State}}' "$svc" 2>/dev/null)
        if [ "$new_state" = "running" ]; then
            send_alert "$svc recovered after restart."
        else
            send_alert "$svc FAILED TO RESTART ($new_state). Manual intervention required."
        fi
    fi
done
```

Save, exit, make executable:

```fish
chmod +x ~/healthcheck.sh
```

Add to crontab (`crontab -e`):

```
*/5 * * * * /home/nomaan/healthcheck.sh >> /home/nomaan/captain-system/logs/healthcheck.log 2>&1
```

### Step 12 — (Recommended) Daily QuestDB backups

Add to crontab (`crontab -e`):

```
0 2 * * * cd /home/nomaan/captain-system && tar czf /home/nomaan/backups/questdb-$(date +\%Y\%m\%d).tar.gz questdb/db/ 2>/dev/null && find /home/nomaan/backups/ -name "questdb-*.tar.gz" -mtime +14 -delete
```

Create the backup directory:

```fish
mkdir -p ~/backups
```

Backs up QuestDB at 2 AM daily, keeps 14 days.

---

## PHASE 6: Pre-Market Validation (15 Tests)

> **Purpose:** End-to-end validation that the tower is correctly configured and will execute trades at the next session open. Run this sequence on any tower before its first live session.
>
> **Time required:** ~10 minutes
>
> **The full test suite is documented in `docs/FINAL-VAL-TESTS/pre-market-validation-guide.md`. Below is the same sequence inline for convenience.**
>
> **All tests pass = system will trade at next session open.**

### Test 0 — Containers healthy

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

**Expected:** All containers show `healthy` or `running`. No containers in `restarting` or `exited` state.

### Test 1 — Captain-Online startup

```fish
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

### Test 2 — Phase A dry run (NY session)

Exercises the full B1→B5C pipeline (data ingestion, regime, AIM, Kelly sizing, trade selection, quality gate, circuit breaker) without publishing signals.

```fish
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

### Test 3 — Phase A dry run (LON session)

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-online python3 /app/dry_run_phase_a.py 2
```

**Expected:**
- `B1: 1 asset` (MGC only)
- All blocks pass through to B5C
- `VERDICT: Phase A would produce signals.`

**Fail if:** `B1: No active assets for session LON` — means MGC's `session_hours` column in D00 is missing the LON key.

### Test 4 — Phase A dry run (APAC session)

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-online python3 /app/dry_run_phase_a.py 3
```

**Expected:**
- `B1: 1 asset` (NKD only)
- All blocks pass through to B5C
- `VERDICT: Phase A would produce signals.`

**Fail if:** `B1: No active assets for session APAC` — means NKD's `session_hours` column in D00 is missing the APAC key.

### Test 5 — QuestDB data integrity

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command python3 -c "
from shared.questdb_client import get_cursor
tables = {
    'p3_d00_asset_universe': 10,
    'p3_d01_aim_model_states': 60,
    'p3_d02_aim_meta_weights': 60,
    'p3_d05_ewma_states': 60,
    'p3_d08_tsm_state': 1,
    'p3_d12_kelly_parameters': 60,
    'p3_d16_user_capital_silos': 1,
    'p3_d25_circuit_breaker_params': 1,
}
with get_cursor() as cur:
    for table, expected in tables.items():
        cur.execute(f'SELECT count() FROM {table}')
        count = cur.fetchone()[0]
        status = 'OK' if count >= expected else 'LOW'
        print(f'  {table}: {count} rows (expect >= {expected}) {status}')
    cur.execute('SELECT account_id, max_daily_loss, max_drawdown_limit, profit_target FROM p3_d08_tsm_state ORDER BY last_updated DESC LIMIT 1')
    row = cur.fetchone()
    if row:
        print(f'  D08 account={row[0]}, max_daily_loss=\${row[1]}, max_drawdown=\${row[2]}, profit_target=\${row[3]}')
    else:
        print('  D08: NO TSM STATE ROW — run fix_bootstrap_data.py')
"
```

**Expected:** All tables `OK`. D08 shows correct account ID with trading limits.

**Fail if:** D08 missing — run Step 8e. Any table `LOW` — re-run Phase 4 bootstrap.

### Test 6 — Captain-Command adapter connection

```fish
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

### Test 6 — Captain-Command startup logs

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-command \
  | grep -i "topstep\|adapter\|CONNECTED\|account"
```

**Expected:**
- `TopstepX authenticated as <email>`
- `TopstepX account: <ACCOUNT_NAME> (id=<ACCOUNT_ID>, balance=<AMOUNT>)`
- `TopstepX CONNECTED: account=<ACCOUNT_NAME> (id=<ACCOUNT_ID>), balance=<AMOUNT>, canTrade=True`

**Fail if:** `canTrade=False`, no account found, or auth failed.

**Critical check:** The `id=<ACCOUNT_ID>` shown here MUST match what's in QuestDB D16. If it doesn't, signals will size trades for one account but the adapter will look up a different account and silently fail.

### Test 7 — Account ID match verification

Verify the account ID in the adapter matches QuestDB.

```fish
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
"
```

Compare the ID with what's in D16:

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command python3 -c "
from shared.questdb_client import get_cursor
with get_cursor() as cur:
    cur.execute('SELECT accounts FROM p3_d16_user_capital_silos LATEST ON last_updated PARTITION BY user_id')
    row = cur.fetchone()
    print(f'D16 accounts: {row[0] if row else \"NOT FOUND\"}')
"
```

**Expected:** The account ID from the API appears inside the D16 `accounts` JSON array.

**If they don't match:** Go back to Phase 4.5 (Account Migration).

### Test 9 — Command execution path dry run

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command \
  python3 /app/dry_run_command.py
```

**Expected:** `7/7 checks PASSED` — adapter registration, connectivity, API latency, account status, contract resolution (8/8), compliance gate, AUTO_EXECUTE all pass.

**Fail if:** Any check `FAIL`. Most common: adapter not registered (restart captain-command) or contract IDs expired (update `config/contract_ids.json`).

### Test 10 — TopstepX order round trip

Places a limit order that will never fill and immediately cancels it. Proves the full API auth → account → contract resolution → order placement → cancellation path.

```fish
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

**Fail if:** Order rejected, cancel failed, or auth error. Common causes: account not active, market closed for the contract, or API rate limiting.

### Test 11 — AUTO_EXECUTE enabled

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command \
  python3 -c "import os; v=os.environ.get('AUTO_EXECUTE',''); print(f'AUTO_EXECUTE={v} (active={v.lower() in (\"1\",\"true\",\"yes\")})')"
```

**Expected:** `AUTO_EXECUTE=true (active=True)`

**Fail if:** `active=False` — signals will appear in the GUI but orders will NOT be placed automatically. Update `.env` and restart.

### Test 12 — VIX data freshness

```fish
tail -1 data/vix/vix_daily_close.csv
tail -1 data/vix/vxv_daily_close.csv
```

**Expected:** Both show a recent date (within last 2 trading days).

**Fail if:** Stale dates. Run: `bash scripts/update_vix_data.sh`

### Test 13 — .env permissions

```fish
stat -c '%a' .env
```

**Expected:** `600`. If wider, run `chmod 600 .env`.

### Test 14 — Instance parity (multi-instance only)

Only relevant if two towers are running. Skip for single-instance deployments.

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec captain-command \
  python3 -c "import os; print(f'INSTANCE_PARITY={os.environ.get(\"INSTANCE_PARITY\", \"(not set — takes all trades)\")}')"
```

**Expected:**
- Tower-1 (Nomaan): `INSTANCE_PARITY=0` (takes odd signals)
- Tower-2 (Isaac): `INSTANCE_PARITY=1` (takes even signals)
- Single instance: `(not set — takes all trades)`

### Additional checks

**Cron jobs installed?**
```fish
crontab -l
```
Expected: Lines for VIX update, healthcheck, and backup.

**Open GUI in browser:**

Navigate to `http://TOWER_IP` or `http://localhost` (if on the tower directly).

### Results summary

| Test | What it proves |
|------|---------------|
| 0 | Infrastructure running |
| 1 | Market data streaming |
| 2 | NY signal pipeline (B1-B5C) |
| 3 | LON signal pipeline (MGC) |
| 4 | APAC signal pipeline (NKD) |
| 5 | QuestDB data + D08 TSM state exists |
| 6 | API adapter connected |
| 7 | Correct account linked |
| 8 | D16 ↔ adapter account match |
| 9 | Command execution path (7 checks) |
| 10 | Order placement works |
| 11 | Auto-execute enabled |
| 12 | VIX data fresh |
| 13 | .env permissions locked |
| 14 | Parity correctly assigned (multi-instance) |

### Validation troubleshooting

| Problem | Fix |
|---------|-----|
| `No active assets for session X` | Asset's `session_hours` in D00 is missing the session key. Re-run `bootstrap_production.py`. |
| `Session NY evaluation FAILED` | Check captain-online logs for traceback. The 2026-04-14 crash was caused by timezone-naive economic calendar datetimes — fixed in commit `8061381`. |
| Adapter connected=0 | Check captain-command logs for TopstepX auth errors: wrong credentials, account name mismatch, or API outage. |
| Signals generated but no orders | Check `AUTO_EXECUTE=true`, account ID match (Test 7), and compliance gate config. |

---

## Complete Crontab Reference

When fully set up, your crontab should contain:

```
# VIX/VXV daily data update — weekdays 10 PM
0 22 * * 1-5 /home/nomaan/captain-system/scripts/update_vix_data.sh >> /home/nomaan/captain-system/logs/vix_update.log 2>&1

# Container health monitoring — every 5 minutes
*/5 * * * * /home/nomaan/healthcheck.sh >> /home/nomaan/captain-system/logs/healthcheck.log 2>&1

# Daily QuestDB backup — 2 AM, 14-day retention
0 2 * * * cd /home/nomaan/captain-system && tar czf /home/nomaan/backups/questdb-$(date +\%Y\%m\%d).tar.gz questdb/db/ 2>/dev/null && find /home/nomaan/backups/ -name "questdb-*.tar.gz" -mtime +14 -delete
```

---

## External Data Sources

| Source | URL | Update method | Frequency |
|--------|-----|--------------|-----------|
| CBOE VIX | `cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv` | `update_vix_data.sh` cron | Weekdays 10 PM |
| CBOE VXV | `cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv` | `update_vix_data.sh` cron | Weekdays 10 PM |
| Yahoo Finance VIX | `query1.finance.yahoo.com/v8/finance/chart/^VIX` | `update_vix_daily.py` (at startup) | Each startup |
| TopstepX REST | `api.topstepx.com/api` | Live via captain containers | Real-time |
| TopstepX WebSocket | `wss://rtc.topstepx.com/hubs/market` + `/hubs/user` | Live via captain containers | Real-time |
| GPR Index | `matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls` | Manual via `sat_013_gpr_fetch.py` | As needed |

---

## Daily Operations

**Start the system (normal daily start):**
```fish
cd ~/captain-system
bash captain-start.sh
```

**Start with rebuild (after code changes):**
```fish
bash captain-start.sh --build
```

**Stop the system:**
```fish
cd ~/captain-system
docker compose -f docker-compose.yml -f docker-compose.local.yml down
```

**View logs:**
```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f
```

**View logs for one service:**
```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-online
```

**Restart one container:**
```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml restart captain-command
```

**Pull code updates:**
```fish
bash scripts/captain-update.sh
```

**Access QuestDB console:**

Open browser to `http://TOWER_IP:9000`

---

## Recovering From Problems

**Container won't start:**
```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml logs SERVICE_NAME --tail 50
```

**QuestDB data corrupted:**
```fish
# Find latest backup
ls -lt ~/backups/questdb-*.tar.gz | head -3

# Restore
docker compose -f docker-compose.yml -f docker-compose.local.yml down
sudo rm -rf questdb/db
sudo tar xzf ~/backups/questdb-YYYYMMDD.tar.gz
bash captain-start.sh
```

**Redis corrupted (AOF error):**
```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml down
sudo rm -rf redis/*
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```
Redis data is transient and reconstructs from QuestDB.

**Re-bootstrap from scratch (nuclear option):**
```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml down
sudo rm -rf questdb/db redis/*
bash captain-start.sh --build
# Then run Phase 4 (Steps 8a through 8d) to repopulate QuestDB
```
