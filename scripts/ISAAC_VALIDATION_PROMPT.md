# Isaac's Captain System — Full Audit, Validation & Auto-Fix Prompt

> **Usage:** Copy everything below into a fresh Claude Code conversation on Isaac's machine.
> Run from the captain-system project root directory.

---

```
You are performing a comprehensive audit, validation, and auto-fix of a Captain System instance deployed for a second user (Isaac). This is a multi-instance trading system where two independent Captain instances (Nomaan=PARITY 0, Isaac=PARITY 1) run on separate machines, splitting trades deterministically.

Your job is to validate EVERY aspect of the deployment and fix anything that's broken. At the end, the system must be fully operational and ready for the next NY session open (09:30 ET).

IMPORTANT: Read CLAUDE.md first to understand the project. Then execute every section below IN ORDER. Do not skip sections. Report a summary at the end with PASS/FAIL for each check.

---

## PHASE 0: ENVIRONMENT & PREREQUISITES

### 0.1 — Operating System & Docker
Run these checks:
- Confirm we're on Linux (WSL2 or native) — `uname -a`
- Confirm Docker is running — `docker info` (just check it works, don't dump all output)
- Confirm Docker Compose v2 — `docker compose version`
- Check `vm.max_map_count` >= 1048576 — `sysctl vm.max_map_count`
  - **AUTO-FIX**: If below threshold, run `sudo sysctl -w vm.max_map_count=1048576`

### 0.2 — Git Repository State
- Run `git remote -v` to confirm the remotes
- Run `git branch` to confirm which branch we're on (should be `main`)
- Run `git status` to check for uncommitted changes
- Run `git log --oneline -5` to see recent commits
- **IMPORTANT**: If the branch is NOT `main`, ask the user before switching. If there are uncommitted changes, warn but don't discard them.

### 0.3 — Required Project Files Exist
Verify ALL of these files/directories exist. Report any missing ones:
```bash
# Core compose files
docker-compose.yml
docker-compose.local.yml

# Environment
.env                    # CRITICAL — must exist with real credentials
.env.template           # Reference

# Nginx
nginx/nginx-local.conf

# Config
config/compliance_gate.json
config/contract_ids.json
config/tsm/             # Directory must exist with at least 1 .json file

# Shared code
shared/topstep_client.py
shared/topstep_stream.py
shared/contract_resolver.py
shared/questdb_client.py
shared/redis_client.py
shared/vix_provider.py
shared/vault.py
shared/journal.py
shared/constants.py
shared/replay_engine.py

# Scripts
scripts/init_questdb.py
scripts/init_all.py
scripts/bootstrap_production.py
scripts/seed_all_assets.py
scripts/seed_system_params.py

# Process entry points
captain-offline/captain_offline/main.py
captain-online/captain_online/main.py
captain-command/captain_command/main.py
captain-command/captain_command/api.py

# Data directories
data/p1_outputs/
data/p2_outputs/
data/vix/

# Startup
captain-start.sh
```

---

## PHASE 1: ENVIRONMENT VARIABLES (.env)

### 1.1 — Read .env and validate every variable
Read the `.env` file. Check each of these variables exists and has a non-placeholder value:

**REQUIRED — system won't work without these:**
| Variable | Valid Check | Notes |
|----------|-----------|-------|
| `TOPSTEP_USERNAME` | Must be a real email, NOT `your_topstep_email@example.com` | Isaac's TopstepX login email |
| `TOPSTEP_API_KEY` | Must be non-empty, NOT `your_topstep_api_key_here` | From TopstepX dashboard |
| `TOPSTEP_ACCOUNT_NAME` | Must match pattern `PRAC-V2-*` or `XFA-*` or `LIVE-*` | Isaac's account name |
| `TRADING_ENVIRONMENT` | Must be `PAPER` or `LIVE` | |
| `VAULT_MASTER_KEY` | Must be non-empty (44-char base64url) | AES-256-GCM key |

**REQUIRED FOR MULTI-INSTANCE:**
| Variable | Valid Check | Notes |
|----------|-----------|-------|
| `INSTANCE_PARITY` | Must be `1` for Isaac's instance | If empty or 0, STOP and ask user — Isaac should be parity 1 |

**RECOMMENDED:**
| Variable | Valid Check | Notes |
|----------|-----------|-------|
| `AUTO_EXECUTE` | Should be `true` or `false` | Recommend `true` for practice accounts |
| `TELEGRAM_BOT_TOKEN` | Non-empty if notifications wanted | Optional but recommended |
| `TELEGRAM_CHAT_ID` | Non-empty if bot token set | Required if bot token is set |

**AUTO-FIX**: If `INSTANCE_PARITY` is empty or missing, ask: "Isaac's instance should have INSTANCE_PARITY=1. Should I set it?" If user confirms, update .env.

### 1.2 — Cross-reference .env.template
Compare `.env` against `.env.template`. Flag any variables in .env.template that are missing from .env. This catches new variables added in updates that the user hasn't configured yet.

---

## PHASE 2: DATA FILES (P1/P2/VIX)

### 2.1 — P2 Output Files (10 active + 1 eliminated)
For each of these 11 assets, verify ALL 3 P2 files exist in `data/p2_outputs/{ASSET}/`:
- `p2_d02_regime_labels.json`
- `p2_d06_locked_strategy.json`
- `p2_d08_classifier_validation.json`

Assets to check: ES, MES, NQ, MNQ, M2K, MYM, NKD, MGC, ZB, ZN, ZT

For each `p2_d06_locked_strategy.json`, read it and verify:
- Has `m`, `k`, `OO` fields
- Values match the expected locked strategies:

| Asset | m | k | OO |
|-------|---|---|-----|
| ES | 7 | 33 | 0.8832 |
| MES | 7 | 32 | 0.8879 |
| NQ | 3 | 32 | 0.8242 |
| MNQ | 5 | 32 | 0.8236 |
| M2K | 5 | 32 | 0.9245 |
| MYM | 9 | 115 | 0.7705 |
| NKD | 6 | 6 | 0.8533 |
| MGC | 2 | 29 | 0.8892 |
| ZB | 10 | 113 | 0.8054 |
| ZN | 4 | 37 | 0.9058 |

**CRITICAL**: If any m/k values don't match, STOP and flag — the strategies are frozen from P2 and must never be changed.

### 2.2 — P1 Trade Logs (10 active + 1 eliminated)
For each of these 11 assets, verify the D-22 trade log exists:
- `data/p1_outputs/{ASSET}/d22_trade_log_{asset_lowercase}.json`

Read each file and verify:
- Is valid JSON
- Contains at least 20 trades (the minimum for bootstrap)
- Each trade has `trade_date` and `r_mi` fields

### 2.3 — VIX/VXV Data Files
Check `data/vix/` contains:
- `vix_daily_close.csv` — VIX daily closes
- `vxv_daily_close.csv` — VXV (VIX3M) daily closes

For each CSV:
- Verify it's parseable (has date and close columns)
- Check the most recent date — if more than 3 business days stale, warn
- VIX file should have ~4000+ rows (2009-present)
- VXV file should have ~4000+ rows

**AUTO-FIX**: If VIX files are missing entirely, check if `data/vix/VIX_History_raw.csv` and `data/vix/VIX3M_History_raw.csv` exist (CBOE raw downloads). If so, note they need to be processed via `scripts/decode_vix_vxv.py`.

**FLAG**: If VIX data is more than a week stale, remind the user about the VIX update cron job:
```
Check if cron is installed: crontab -l | grep vix
If not: bash deploy/install-vix-cron.sh
```

---

## PHASE 3: DOCKER CONTAINERS

### 3.1 — Sync Config into Build Contexts
Before building, ensure config files are copied into each service's build context (Docker COPY can only access files within the build context):
```bash
for svc in captain-offline captain-online captain-command; do
    cp -r config/ "$svc/config/" 2>/dev/null
done
```

### 3.2 — Build and Start All Containers
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

Wait for build to complete. If any service fails to build, read the error logs:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=50 <service_name>
```

### 3.3 — Verify All 6 Containers Running
After startup, verify all 6 services are running:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

Expected services (all should show "running" or "Up"):
1. `questdb` — healthy
2. `redis` — healthy
3. `captain-offline` — running
4. `captain-online` — running
5. `captain-command` — running (healthy)
6. `nginx` — running (healthy)

`captain-gui` will show "exited (0)" — that's normal (it builds static assets then exits).

**AUTO-FIX**: If a container is in restart loop, check logs and diagnose. Common issues:
- QuestDB: `vm.max_map_count` too low → fix in Phase 0
- captain-online: missing `.env` variables → fix in Phase 1
- nginx: missing nginx-local.conf → check Phase 0.3

### 3.4 — Wait for Infrastructure
Wait for QuestDB and Redis to be fully ready:
```bash
# QuestDB (wait up to 60s)
until docker exec $(docker ps -q -f name=questdb) curl -sf 'http://localhost:9000/exec?query=SELECT%201' > /dev/null 2>&1; do sleep 2; done

# Redis (wait up to 30s)
until docker exec $(docker ps -q -f name=redis) redis-cli ping 2>/dev/null | grep -q PONG; do sleep 2; done
```

---

## PHASE 4: QUESTDB TABLES

### 4.1 — Create/Verify All Tables
Run init_questdb.py inside the captain-offline container (it uses CREATE TABLE IF NOT EXISTS, so it's idempotent):
```bash
docker exec $(docker ps -q -f name=captain-offline) python /captain/scripts/init_questdb.py
```

### 4.2 — Verify All 33 Tables Exist
Query QuestDB to list all tables. There should be exactly 33 tables:

```bash
docker exec $(docker ps -q -f name=questdb) curl -s 'http://localhost:9000/exec?query=SELECT+table_name+FROM+information_schema.tables()&limit=0,100' | python3 -c "
import json, sys
data = json.load(sys.stdin)
tables = sorted([row[0] for row in data.get('dataset', [])])
print(f'Total tables: {len(tables)}')
for t in tables:
    print(f'  {t}')
"
```

**Expected 33 tables:**
```
p3_d00_asset_universe
p3_d01_aim_model_states
p3_d02_aim_meta_weights
p3_d03_trade_outcome_log
p3_d04_decay_detector_states
p3_d05_ewma_states
p3_d06_injection_history
p3_d06b_active_strategy_transitions
p3_d07_correlation_model_states
p3_d08_tsm_state
p3_d09_report_archive
p3_d10_notification_log
p3_d11_pseudotrader_results
p3_d12_kelly_parameters
p3_d13_sensitivity_scan_results
p3_d14_api_connection_states
p3_d15_user_session_data
p3_d16_user_capital_silos
p3_d17_system_monitor_state
p3_d18_version_history_store
p3_d19_reconciliation_log
p3_d21_incident_log
p3_d22_system_health_diagnostic
p3_d23_circuit_breaker_intraday
p3_d25_circuit_breaker_params
p3_d26_hmm_opportunity_state
p3_d27_pseudotrader_forecasts
p3_d28_account_lifecycle
p3_offline_job_queue
p3_replay_presets
p3_replay_results
p3_session_event_log
p3_spread_history
```

**AUTO-FIX**: If any tables are missing, re-run init_questdb.py. If that doesn't create them, the script may be out of date — check git log for recent schema changes.

---

## PHASE 5: BOOTSTRAP DATA VALIDATION

This is the most critical phase. The bootstrap populates 5 key tables that the system needs to operate.

### 5.1 — D00: Asset Universe (10 active assets)
```sql
SELECT asset_id, captain_status, warm_up_progress, locked_strategy, point_value, tick_size, margin_per_contract, exchange_timezone, session_hours
FROM p3_d00_asset_universe
LATEST ON last_updated PARTITION BY asset_id
WHERE captain_status = 'ACTIVE'
```

**Expected**: 10 rows with captain_status='ACTIVE' for: ES, MES, NQ, MNQ, M2K, MYM, NKD, MGC, ZB, ZN

For each row, verify:
- `locked_strategy` is NOT null/empty — must contain JSON with m, k, OO fields
- `point_value` matches the expected values (ES=50, MES=5, NQ=20, MNQ=2, M2K=5, MYM=0.5, NKD=5, MGC=10, ZB=1000, ZN=1000)
- `tick_size` is populated
- `margin_per_contract` is populated
- `exchange_timezone` is set (America/New_York for most, Asia/Tokyo for NKD, America/Chicago for ZB/ZN)
- `warm_up_progress` = 1.0
- `session_hours` is NOT null

**AUTO-FIX**: If D00 is empty or incomplete, run the bootstrap:
```bash
docker exec $(docker ps -q -f name=captain-offline) python /captain/scripts/bootstrap_production.py
```

Note: bootstrap_production.py reads env vars for account-specific config:
- BOOTSTRAP_ACCOUNT_ID (Isaac's TopstepX account ID — get from .env TOPSTEP_ACCOUNT_NAME or ask user)
- BOOTSTRAP_USER_ID (default: "primary_user")
- BOOTSTRAP_STARTING_CAPITAL (default: "150000" — verify with user what Isaac's account capital is)

### 5.2 — D01: AIM Model States (270 rows = 10 assets × 27 AIMs, or at minimum 60 Tier 1 rows)
```sql
SELECT asset_id, aim_id, status, COUNT(*)
FROM p3_d01_aim_model_states
LATEST ON last_updated PARTITION BY asset_id, aim_id
GROUP BY asset_id, aim_id, status
```

**Expected minimum**: 60 rows (10 assets × 6 Tier 1 AIMs: 4, 6, 8, 11, 12, 15)
- Tier 1 AIMs should have status = 'BOOTSTRAPPED' or 'ACTIVE'
- Other AIMs (if seeded) should have status = 'INSTALLED'

**AUTO-FIX**: AIM states are seeded automatically by captain-offline on startup (main.py _seed_aim_states). If missing, restart captain-offline:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml restart captain-offline
```
Wait 30 seconds, then re-check.

### 5.3 — D02: AIM Meta-Weights (60 rows = 10 assets × 6 Tier 1 AIMs)
```sql
SELECT asset_id, aim_id, inclusion_probability, inclusion_flag
FROM p3_d02_aim_meta_weights
LATEST ON last_updated PARTITION BY asset_id, aim_id
```

**Expected**: 60 rows
- Each should have `inclusion_probability` ≈ 0.1667 (1/6)
- Each should have `inclusion_flag` = true

**AUTO-FIX**: If empty, run bootstrap_production.py (Phase 5.1 fix).

### 5.4 — D05: EWMA States (60 rows = 10 assets × 2 regimes × 3 sessions, OR 10 × 6 combos)
```sql
SELECT asset_id, regime, session, win_rate, avg_win, avg_loss, n_trades
FROM p3_d05_ewma_states
LATEST ON last_updated PARTITION BY asset_id, regime, session
```

**Expected**: At least 20 rows (varies by asset — some only have NY session data)
- `win_rate` should be between 0.0 and 1.0
- `avg_win` should be > 0
- `avg_loss` should be < 0 (negative)
- `n_trades` should be > 0

**AUTO-FIX**: If empty, EWMA states come from seed_all_assets.py, not bootstrap_production.py. Run:
```bash
docker exec $(docker ps -q -f name=captain-offline) python /captain/scripts/seed_all_assets.py
```

### 5.5 — D12: Kelly Parameters (same shape as D05)
```sql
SELECT asset_id, regime, session, kelly_full, shrinkage_factor
FROM p3_d12_kelly_parameters
LATEST ON last_updated PARTITION BY asset_id, regime, session
```

**Expected**: Same row count as D05
- `kelly_full` should be between 0 and 1.0 (realistic Kelly fractions)
- `shrinkage_factor` should be 0.5 (initial bootstrap value)

**AUTO-FIX**: Same fix as D05 — run seed_all_assets.py.

### 5.6 — D16: Capital Silo (1 row for Isaac's user)
```sql
SELECT user_id, status, role, starting_capital, total_capital, accounts, max_simultaneous_positions
FROM p3_d16_user_capital_silos
LATEST ON last_updated PARTITION BY user_id
```

**Expected**: 1 row
- `user_id` = the BOOTSTRAP_USER_ID (default "primary_user")
- `status` = 'ACTIVE'
- `starting_capital` and `total_capital` should match Isaac's account capital
- `accounts` should be a JSON array containing Isaac's account ID
- `max_simultaneous_positions` should be > 0 (default 5)

**AUTO-FIX**: If empty, run bootstrap_production.py with correct env vars for Isaac's account.

### 5.7 — D08: TSM State (1 row per account)
```sql
SELECT account_id, user_id, name, classification, starting_balance, max_drawdown_limit, max_daily_loss, max_contracts
FROM p3_d08_tsm_state
LATEST ON last_updated PARTITION BY account_id
```

**Expected**: At least 1 row with Isaac's account ID
- Verify the account ID matches what's in `.env` (TOPSTEP_ACCOUNT_NAME)
- `starting_balance` should match the account type (150K for Trading Combine, 50K for Express, etc.)
- `max_drawdown_limit` should be populated
- `max_daily_loss` should be populated

If TSM state is missing, it gets populated by captain-command on startup when it connects to TopstepX and auto-links the account. Check captain-command logs:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=100 captain-command | grep -i "tsm\|account\|link"
```

### 5.8 — D17: System Parameters (35+ rows)
```sql
SELECT COUNT(*) FROM p3_d17_system_monitor_state
```

**Expected**: 35+ rows

Spot-check critical parameters:
```sql
SELECT param_key, param_value, category
FROM p3_d17_system_monitor_state
LATEST ON last_updated PARTITION BY param_key
WHERE param_key IN ('system_timezone', 'execution_mode', 'tsm_budget_divisor_default', 'max_users', 'circuit_breaker_vix_threshold')
```

**Expected values**:
- system_timezone = "America/New_York"
- execution_mode = "MANUAL"
- tsm_budget_divisor_default = "20"
- max_users = "20"
- circuit_breaker_vix_threshold = "50"

**AUTO-FIX**: If empty, run:
```bash
docker exec $(docker ps -q -f name=captain-offline) python /captain/scripts/seed_system_params.py
```

### 5.9 — D25: Circuit Breaker Params (1 row per account)
```sql
SELECT account_id, model_m, beta_b, n_observations
FROM p3_d25_circuit_breaker_params
LATEST ON last_updated PARTITION BY account_id
```

**Expected**: 1 row with Isaac's account ID
- `model_m` = 0 (cold start)
- `beta_b` = 0.0 (layers 3-4 disabled until enough observations)
- `n_observations` = 0

**AUTO-FIX**: If empty, run bootstrap_production.py.

### 5.10 — D04: Decay Detector States (10 rows)
```sql
SELECT asset_id, bocpd_cp_probability, current_changepoint_probability
FROM p3_d04_decay_detector_states
LATEST ON last_updated PARTITION BY asset_id
```

**Expected**: 10 rows (one per active asset)
- Should have been populated by seed_all_assets.py

**AUTO-FIX**: If empty, run seed_all_assets.py.

---

## PHASE 6: NETWORKING & API

### 6.1 — Nginx Reverse Proxy
Test that nginx is serving the GUI and proxying API requests:
```bash
# GUI loads (returns HTML)
curl -s -o /dev/null -w "%{http_code}" http://localhost:80/

# API proxied through nginx
curl -s http://localhost/api/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d, indent=2))"

# Direct API access (bypass nginx)
curl -s http://localhost:8000/api/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d, indent=2))"
```

**Expected**:
- GUI returns HTTP 200
- Both health endpoints return JSON with `"status": "OK"` or `"status": "DEGRADED"`
- If DEGRADED, check `captain-offline` and `captain-online` logs

### 6.2 — WebSocket Endpoint
```bash
# Quick WebSocket test (just verify it accepts upgrade)
curl -s -o /dev/null -w "%{http_code}" -H "Upgrade: websocket" -H "Connection: Upgrade" http://localhost/ws/primary_user
```
HTTP 426 or 101 are both acceptable — it means the endpoint exists.

### 6.3 — QuestDB Web Console
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/
```
**Expected**: HTTP 200

### 6.4 — Redis Connectivity
```bash
docker exec $(docker ps -q -f name=redis) redis-cli ping
```
**Expected**: PONG

Check Redis streams exist:
```bash
docker exec $(docker ps -q -f name=redis) redis-cli KEYS '*'
```
Should show stream keys after first startup.

---

## PHASE 7: PROCESS-SPECIFIC HEALTH

### 7.1 — Captain Offline Logs
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=50 captain-offline
```

**Check for**:
- "AIM states seeded" or "All AIMs already exist" — confirms D01 population
- No crash loops or repeated errors
- No "table busy" errors (occasional retries are OK)

### 7.2 — Captain Online Logs
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=50 captain-online
```

**Check for**:
- "MarketStream started" or "Streams connected" — confirms TopstepX connection
- "Orchestrator started" — confirms session loop is running
- No authentication errors (would indicate bad TOPSTEP_USERNAME/API_KEY)
- No "contract not found" errors

### 7.3 — Captain Command Logs
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=50 captain-command
```

**Check for**:
- "FastAPI started" or "Uvicorn running on 0.0.0.0:8000"
- "TopstepX connected" or "Account linked"
- "TSM loaded" — confirms Trade State Machine configuration
- No vault decryption errors

### 7.4 — Common Issues to Check
1. **Authentication failures**: Look for "401", "unauthorized", "invalid credentials" in any log
2. **QuestDB connection refused**: Look for "connection refused" on port 8812
3. **Redis connection refused**: Look for "connection refused" on port 6379
4. **VIX provider warnings**: Look for "VIX data not available" — means data/vix/ files are missing or the path is wrong
5. **Journal errors**: Look for "journal" errors — journal.py should auto-initialize but check

---

## PHASE 8: MULTI-INSTANCE SPECIFIC CHECKS

### 8.1 — Parity Configuration
Verify INSTANCE_PARITY=1 is correctly read by the command process:
```bash
docker exec $(docker ps -q -f name=captain-command) env | grep INSTANCE_PARITY
```
**Expected**: `INSTANCE_PARITY=1`

### 8.2 — Shadow Monitor Present
Verify b7_shadow_monitor.py exists in captain-online:
```bash
docker exec $(docker ps -q -f name=captain-online) ls -la /app/captain_online/blocks/b7_shadow_monitor.py
```

### 8.3 — VIX Environment Variables in Containers
Each process container must have VIX_CSV_PATH and VXV_CSV_PATH set correctly AND the files must be accessible at those paths:
```bash
for svc in captain-offline captain-online captain-command; do
    echo "=== $svc ==="
    container=$(docker ps -q -f name=$svc)
    docker exec $container env | grep VIX
    docker exec $container ls -la /captain/data/vix/ 2>/dev/null || echo "  VIX DIR NOT FOUND"
done
```

**Expected**: Each container shows:
- `VIX_CSV_PATH=/captain/data/vix/vix_daily_close.csv`
- `VXV_CSV_PATH=/captain/data/vix/vxv_daily_close.csv`
- `/captain/data/vix/` directory exists and contains both CSV files

**AUTO-FIX**: If VIX path env vars are missing from docker-compose.yml, they need to be added under each service's `environment:` block.

### 8.4 — Config Files Inside Containers
Verify critical config files are accessible inside containers:
```bash
for svc in captain-offline captain-online captain-command; do
    container=$(docker ps -q -f name=$svc)
    echo "=== $svc ==="
    docker exec $container ls /app/config/compliance_gate.json 2>/dev/null && echo "  compliance_gate: OK" || echo "  compliance_gate: MISSING"
    docker exec $container ls /app/config/contract_ids.json 2>/dev/null && echo "  contract_ids: OK" || echo "  contract_ids: MISSING"
    docker exec $container ls /app/shared/constants.py 2>/dev/null && echo "  shared/constants: OK" || echo "  shared/constants: MISSING"
done
```

---

## PHASE 9: CONTRACT EXPIRY CHECK

### 9.1 — Verify Contract IDs Are Current
Read `config/contract_ids.json` and check that no contracts have expired. Current date matters here.

**Known expiry to watch**: MGC uses April 2026 (J26) expiry — if we're past April expiry, this needs to be rolled to the next month.

Most other contracts use June 2026 (M26) — these are good through mid-June.

If any contract has expired, FLAG immediately — the system will fail to place orders for that asset until the contract is rolled to the new front month.

---

## PHASE 10: COMPLIANCE & SECURITY

### 10.1 — Compliance Gate
Read `config/compliance_gate.json` and verify all 11 RTS 6 rules are set to `true`:
- rts6_01 through rts6_11 must ALL be `true`

### 10.2 — Vault Encryption
Check the vault file exists:
```bash
ls -la vault/keys.vault
```
If the vault doesn't exist yet, it will be created on first TopstepX authentication. That's OK for a fresh install.

### 10.3 — No Secrets in Git
```bash
git log --diff-filter=A --name-only --pretty="" | grep -iE '\.env$|\.key$|\.pem$|\.vault$|secret|credential' || echo "No sensitive files in git history"
```

---

## PHASE 11: RUN UNIT TESTS

Run the host-side test suite to validate block logic:
```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/ \
  --ignore=tests/test_integration_e2e.py \
  --ignore=tests/test_pipeline_e2e.py \
  --ignore=tests/test_pseudotrader_account.py \
  --ignore=tests/test_offline_feedback.py \
  --ignore=tests/test_stress.py \
  --ignore=tests/test_account_lifecycle.py \
  -v --tb=short 2>&1 | tail -30
```

**Expected**: All 64+ tests pass. If any fail, investigate and report.

Note: Some tests may need container-only dependencies (pysignalr, numpy). If imports fail, that's expected on the host — report but don't fail the audit for import errors on optional deps.

---

## PHASE 12: FINAL VALIDATION SUMMARY

After completing all phases, produce a summary report in this format:

```
╔══════════════════════════════════════════════════════════════════╗
║              CAPTAIN SYSTEM — ISAAC INSTANCE AUDIT              ║
║                    Date: YYYY-MM-DD HH:MM ET                    ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  PHASE 0: Environment & Prerequisites     [ PASS / FAIL ]       ║
║  PHASE 1: Environment Variables (.env)    [ PASS / FAIL ]       ║
║  PHASE 2: Data Files (P1/P2/VIX)         [ PASS / FAIL ]       ║
║  PHASE 3: Docker Containers              [ PASS / FAIL ]       ║
║  PHASE 4: QuestDB Tables (33)            [ PASS / FAIL ]       ║
║  PHASE 5: Bootstrap Data                 [ PASS / FAIL ]       ║
║    5.1  D00 Asset Universe (10 active)   [ PASS / FAIL ]       ║
║    5.2  D01 AIM Model States (60+)      [ PASS / FAIL ]       ║
║    5.3  D02 AIM Meta-Weights (60)       [ PASS / FAIL ]       ║
║    5.4  D05 EWMA States (20+)          [ PASS / FAIL ]       ║
║    5.5  D12 Kelly Parameters (20+)     [ PASS / FAIL ]       ║
║    5.6  D16 Capital Silo (1)           [ PASS / FAIL ]       ║
║    5.7  D08 TSM State (1+)            [ PASS / FAIL ]       ║
║    5.8  D17 System Parameters (35+)    [ PASS / FAIL ]       ║
║    5.9  D25 Circuit Breaker (1)        [ PASS / FAIL ]       ║
║    5.10 D04 Decay Detector (10)        [ PASS / FAIL ]       ║
║  PHASE 6: Networking & API               [ PASS / FAIL ]       ║
║  PHASE 7: Process Health                 [ PASS / FAIL ]       ║
║  PHASE 8: Multi-Instance Config          [ PASS / FAIL ]       ║
║  PHASE 9: Contract Expiry               [ PASS / FAIL ]       ║
║  PHASE 10: Compliance & Security         [ PASS / FAIL ]       ║
║  PHASE 11: Unit Tests                    [ PASS / FAIL ]       ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  OVERALL STATUS:    READY / NOT READY                           ║
║  AUTO-FIXES APPLIED: N                                          ║
║  MANUAL ACTIONS REQUIRED: N                                     ║
╚══════════════════════════════════════════════════════════════════╝
```

If MANUAL ACTIONS REQUIRED > 0, list each one with:
- What needs to be done
- Why it can't be auto-fixed
- Exact command or step to fix it

If OVERALL STATUS is READY, the system is fully validated and ready for the next trading session.
```
