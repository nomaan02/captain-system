# Captain System — Post-Audit Validation Roadmap

**Date:** 2026-04-09
**Branch:** `final_val_1.0`
**Laptop (new):** Post-audit code (this machine)
**Tower (old):** Pre-audit code (captain-system, not yet synced)

---

## How To Use This Document

Work through each section in order. Each section has:
- **What changed** — the before/after and why it matters
- **Test on TOWER (old)** — reproduce the old behavior so you can see the problem
- **Test on LAPTOP (new)** — verify the fix works
- **Pass criteria** — what you need to see to check it off

Some tests require containers running, some are code inspection only. Prerequisites are listed per section.

**Notation:** `[ ]` = not tested, `[x]` = passed, `[!]` = failed (investigate)

---

## Prerequisites

Before starting, get both machines ready:

### Laptop (new code)

Your `.env` needs two new required variables. Generate passwords first:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(16))"
```

Add to your `.env`:
```
QUESTDB_USER=captain
QUESTDB_PASSWORD=<generated-password-1>
REDIS_PASSWORD=<generated-password-2>
```

Then rebuild:
```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

### Tower (old code)

Just make sure containers are up. No `.env` changes needed (it runs on the old defaults).

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

---

## Section 1: Database Authentication (CRITICAL)

**Gaps closed:** NEW-A01 (QuestDB), NEW-A02 (Redis)
**Risk level:** Pre-live blocker — without this, any process on your network can read/write trading data or inject commands

### What Changed

| | Before (Tower) | After (Laptop) |
|---|---|---|
| QuestDB credentials | `admin` / `quest` (factory defaults) | Custom `captain` / `<your-password>` |
| Redis auth | None — wide open | `--requirepass` enforced |
| `.env.template` | QuestDB creds commented out, Redis not mentioned | Both required, with generation command |
| `docker-compose.yml` | No auth env vars passed to containers | `QDB_PG_USER`, `QDB_PG_PASSWORD`, `REDIS_PASSWORD` injected |
| `shared/questdb_client.py` | Defaults to `admin`/`quest` | Defaults to `captain`/`""` (forces explicit password) |
| `shared/redis_client.py` | No `password` parameter | Reads `REDIS_PASSWORD`, passes to Redis constructor |

### Why It Matters

The old system lets any process on localhost (or any machine on your LAN) connect to QuestDB on port 8812 or Redis on port 6379 with zero credentials. That means:
- Read all your trading data, account balances, API keys in vault
- Write fake signals to Redis `captain:signals:*` channel
- Modify Kelly fractions, AIM weights, circuit breaker state
- Issue TAKEN commands for trades you never approved

### Test on TOWER (old) — prove the vulnerability exists

**Test 1.1: QuestDB open access**

```bash
# From the tower, connect with the known default creds
psql -h localhost -p 8812 -U admin -d qdb -c "SELECT count(*) FROM p3_d00_asset_universe;"
# Password: quest
```

- [ ] Connection succeeds with `admin`/`quest`
- [ ] You can read trading data without any custom credentials

**Test 1.2: Redis open access**

```bash
# From the tower, connect with no password
redis-cli -h localhost -p 6379 PING
```

- [ ] Returns `PONG` — no auth required
- [ ] Try publishing a fake command:
  ```bash
  redis-cli -h localhost -p 6379 PUBLISH "captain:commands" '{"type":"test_injection"}'
  ```
- [ ] Message publishes successfully (this is the attack vector)

### Test on LAPTOP (new) — verify auth is enforced

**Test 1.3: QuestDB rejects old defaults**

```bash
# Try the old default credentials — should FAIL
psql -h localhost -p 8812 -U admin -d qdb -c "SELECT 1;"
# Password: quest
```

- [ ] Connection REFUSED or authentication error

**Test 1.4: QuestDB accepts new credentials**

```bash
# Use your new credentials from .env
psql -h localhost -p 8812 -U captain -d qdb -c "SELECT count(*) FROM p3_d00_asset_universe;"
# Password: <your QUESTDB_PASSWORD from .env>
```

- [ ] Connection succeeds
- [ ] Query returns data

**Test 1.5: Redis rejects unauthenticated access**

```bash
# Try without password — should FAIL
redis-cli -h localhost -p 6379 PING
```

- [ ] Returns `NOAUTH Authentication required` (not PONG)

**Test 1.6: Redis accepts password**

```bash
# Use your password from .env
redis-cli -h localhost -p 6379 -a "<your REDIS_PASSWORD>" PING
```

- [ ] Returns `PONG`

**Test 1.7: All three Captain processes connect successfully**

```bash
# Check all containers are healthy
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

- [ ] `captain-offline` — healthy
- [ ] `captain-online` — healthy
- [ ] `captain-command` — healthy
- [ ] No auth errors in logs:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=50 captain-command 2>&1 | grep -i "auth\|password\|denied"
  ```

### Pass Criteria

All of: 1.3 fails, 1.4 succeeds, 1.5 fails, 1.6 succeeds, 1.7 all healthy. Old defaults locked out, new credentials work, all processes connect.

---

## Section 2: Graceful Shutdown (CRITICAL)

**Gap closed:** NEW-A04
**Risk level:** Pre-live blocker — without this, `docker stop` kills the Command process mid-execution with no cleanup

### What Changed

| | Before (Tower) | After (Laptop) |
|---|---|---|
| Shutdown mechanism | `signal.signal(SIGTERM, handler)` in `main.py` | FastAPI `lifespan` context manager in `api.py` |
| What happens on `docker stop` | uvicorn overrides the signal handler — orchestrator and telegram bot are NEVER stopped. Process is force-killed after Docker's 10s grace period | Lifespan shutdown fires: orchestrator.stop() + telegram_bot.stop() run cleanly |
| WebSocket connections | Severed mid-stream | Closed gracefully |
| Background loops | Killed mid-iteration | Allowed to complete current cycle, then exit |

### Why It Matters

In the old code, `main.py` calls `signal.signal(SIGTERM, shutdown_handler)` **before** `uvicorn.run()`. But uvicorn installs its own SIGTERM handler when it starts, silently overwriting yours. Your `shutdown_handler` never fires. The orchestrator's background thread keeps running until Docker force-kills the container at the 10-second timeout. This means:
- Open positions aren't checkpointed
- Telegram bot doesn't send a "going offline" message
- Redis subscriptions aren't unsubscribed
- SQLite journal isn't flushed

### Test on TOWER (old) — prove shutdown is broken

**Test 2.1: Watch docker stop behavior**

```bash
# In one terminal, follow Command logs
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-command

# In another terminal, stop the container
docker stop captain-command
```

Watch the log output carefully.

- [ ] You do NOT see "Shutdown signal received" in the logs
- [ ] You do NOT see any orchestrator cleanup messages
- [ ] The container takes the full 10 seconds to stop (Docker's grace period)
- [ ] The final log line is just uvicorn shutting down, nothing from your code

**Test 2.2: Time the shutdown**

```bash
time docker stop captain-command
```

- [ ] Takes close to 10 seconds (the Docker SIGTERM timeout — your handler never ran, so it waits for force-kill)

### Test on LAPTOP (new) — verify clean shutdown

**Test 2.3: Watch docker stop behavior**

```bash
# In one terminal, follow Command logs
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-command

# In another terminal, stop the container
docker stop captain-command
```

- [ ] You see `"Lifespan shutdown: stopping orchestrator and telegram bot"` in the logs
- [ ] Orchestrator stop messages appear (background loops exiting)
- [ ] Container stops in under 5 seconds (no force-kill needed)

**Test 2.4: Time the shutdown**

```bash
time docker stop captain-command
```

- [ ] Takes noticeably less than 10 seconds (clean exit, not forced)

**Test 2.5: Restart and verify clean state**

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d captain-command
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=20 captain-command
```

- [ ] Starts cleanly with no "recovery" or "orphaned" warnings
- [ ] Health endpoint responds:
  ```bash
  curl -s http://localhost:8000/health | python3 -m json.tool
  ```

### Pass Criteria

Tower takes ~10s to stop with no cleanup messages. Laptop stops in <5s with explicit "Lifespan shutdown" log line. The difference is the orchestrator and bot actually running their cleanup code.

---

## Section 3: VIX Spike Detection (HIGH)

**Gap closed:** G-030
**Risk level:** Position safety — wrong alerting logic means you miss real VIX events

### What Changed

| | Before (Tower) | After (Laptop) |
|---|---|---|
| Detection method | Flat threshold: `VIX >= 50.0` | Z-score: `(current - mean_60d) / stdev_60d > 2.0` |
| Threshold source | Tried to load from `system_params` table (doesn't exist), fell back to hardcoded 50.0 | Computed from 60-day trailing VIX history via `get_trailing_vix_closes(lookback=60)` |
| Alert sensitivity | Almost never fires — VIX hasn't hit 50 since 2020 | Fires on relative spikes. If 60d mean=16, stdev=3, alerts at VIX 22.1+ |
| Alert message | `"VIX spike: 22.1 >= 50"` | `"VIX spike: 22.1 (z=2.03)"` |
| Spec compliance | Non-compliant (spec requires z-score) | Compliant with spec section 2, B7 |

### Why It Matters

A flat VIX threshold of 50 is almost useless — it only triggers in extreme crashes. The spec requires a statistical approach: alert when VIX is 2 standard deviations above its own recent history. This catches regime shifts even when absolute VIX levels are moderate.

Example: If VIX has been around 14-18 for two months and suddenly jumps to 24, that's a significant move (z-score ~2.5) even though 24 is not historically "high". The old code would stay silent. The new code alerts you.

### Test on TOWER (old) — inspect the broken logic

**Test 3.1: Find the hardcoded threshold**

```bash
# SSH into tower or open the code
grep -n "VIX_SPIKE" captain-online/captain_online/blocks/b7_position_monitor.py
```

- [ ] See `VIX_SPIKE_DEFAULT_THRESHOLD = 50.0`
- [ ] See the `system_params` query (table that doesn't exist)

**Test 3.2: Check if the query would fail**

```bash
# On tower, try the old query in QuestDB console (http://localhost:9000)
SELECT value FROM system_params LATEST ON ts PARTITION BY key WHERE key = 'circuit_breaker_vix_threshold';
```

- [ ] Query fails with "table does not exist" (confirming it always fell back to 50.0)

### Test on LAPTOP (new) — verify z-score logic

**Test 3.3: Verify the code uses z-score**

```bash
grep -n "z_score\|z-score\|VIX_SPIKE_Z" captain-online/captain_online/blocks/b7_position_monitor.py
```

- [ ] See `VIX_SPIKE_Z_THRESHOLD = 2.0`
- [ ] See `z_score = (current - mean_60d) / stdev_60d`
- [ ] See `if z_score > 2.0:`

**Test 3.4: Verify the VIX data source works**

```bash
# Inside the captain-online container (or with PYTHONPATH set)
docker exec captain-online python3 -c "
import sys; sys.path.insert(0, '/captain/shared')
from vix_provider import get_trailing_vix_closes
closes = get_trailing_vix_closes(lookback=60)
print(f'Got {len(closes)} VIX closes')
if closes:
    mean = sum(closes) / len(closes)
    stdev = (sum((v - mean)**2 for v in closes) / len(closes))**0.5
    print(f'Latest: {closes[-1]:.2f}, Mean: {mean:.2f}, Stdev: {stdev:.2f}')
    print(f'Alert threshold: {mean + 2*stdev:.2f}')
"
```

- [ ] Returns 60 (or however many days of VIX data you have)
- [ ] Shows a reasonable alert threshold (likely somewhere in the 20s, not 50)

**Test 3.5: Unit test passes**

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/ -k "vix or position_monitor" -v 2>&1 | tail -20
```

- [ ] All VIX/position monitor tests pass

### Pass Criteria

Old code has hardcoded 50.0 and queries a non-existent table. New code computes z-score from trailing data. Alert threshold is a realistic number (not 50).

---

## Section 4: Wrong Table Names (HIGH)

**Gaps closed:** G-030 (partial — commission query), G-031 (shadow monitor)
**Risk level:** Silent data failures — queries return nothing, code falls back to hardcoded defaults

### What Changed

Two separate wrong-table-name bugs were found and fixed:

**4A: Position Monitor — Commission Query (b7_position_monitor.py)**

| | Before | After |
|---|---|---|
| Table | `system_params` | `p3_d17_system_monitor_state` |
| Columns | `value`, `ts`, `key` | `param_value`, `last_updated`, `param_key` |
| Result | SQL error → silent fallback to hardcoded commission | Correct commission loaded from D17 |

**4B: Shadow Monitor — Point Value Query (b7_shadow_monitor.py)**

| | Before | After |
|---|---|---|
| Table | `asset_universe` | `p3_d00_asset_universe` |
| Partition column | `ts` | `last_updated` |
| Placeholder syntax | `$1` (wrong for psycopg2) | `%s` (correct) |
| Parameter format | `[asset_id]` (list) | `(asset_id,)` (tuple) |
| Result | SQL error → silent fallback to hardcoded POINT_VALUES dict | Live point values from D00 |

### Why It Matters

Both bugs cause silent failures. The code catches the SQL exception and falls back to hardcoded values. This means:
- Commission calculations use a default fee instead of the actual fee schedule
- Shadow monitor P&L calculations use stale hardcoded point values instead of live data
- If point values change (contract rollover, exchange update), the shadow monitor diverges from reality
- The hardcoded fallback isn't logged at WARNING level, so you'd never know it's happening

### Test on TOWER (old) — prove the queries fail

**Test 4.1: Position monitor commission query**

```bash
# In QuestDB console (http://localhost:9000), run the OLD query:
SELECT value FROM system_params LATEST ON ts PARTITION BY key WHERE key = 'default_commission_per_contract';
```

- [ ] Fails with "table does not exist"

**Test 4.2: Shadow monitor point value query**

```bash
# The old query uses $1 placeholder syntax and wrong table:
SELECT point_value FROM asset_universe LATEST ON ts PARTITION BY asset_id WHERE asset_id = $1;
```

- [ ] Fails (table `asset_universe` does not exist — it's `p3_d00_asset_universe`)

**Test 4.3: Verify hardcoded fallback is being used**

```bash
# Check captain-online logs for the silent exception
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-online 2>&1 | grep -i "point_value\|commission\|fallback"
```

- [ ] Likely see debug-level messages about fallback, or no mention at all (silently swallowed)

### Test on LAPTOP (new) — verify correct tables

**Test 4.4: New commission query works**

```bash
# In QuestDB console (http://localhost:9000), run the NEW query:
SELECT param_value FROM p3_d17_system_monitor_state LATEST ON last_updated PARTITION BY param_key WHERE param_key = 'default_commission_per_contract';
```

- [ ] Query succeeds (may return 0 rows if param not seeded, but no error)

**Test 4.5: New point value query works**

```bash
# Run the corrected query:
SELECT point_value FROM p3_d00_asset_universe LATEST ON last_updated PARTITION BY asset_id WHERE asset_id = 'ES';
```

- [ ] Returns the correct point value for ES (should be 50.0 for E-mini S&P)

**Test 4.6: Code inspection**

```bash
grep -n "system_params\|asset_universe" captain-online/captain_online/blocks/b7_position_monitor.py captain-online/captain_online/blocks/b7_shadow_monitor.py
```

- [ ] Zero matches for the bare `system_params` (only `p3_d17_system_monitor_state`)
- [ ] Zero matches for bare `asset_universe` (only `p3_d00_asset_universe`)

### Pass Criteria

Old queries fail against QuestDB. New queries succeed. No bare table names remain in code.

---

## Section 5: Regime Probability Fallback (HIGH)

**Gap closed:** (b2 classifier resilience)
**Risk level:** Pipeline blockage — a None return from B2 stops the entire signal chain for that asset

### What Changed

| | Before (Tower) | After (Laptop) |
|---|---|---|
| REGIME_NEUTRAL handling | Early return `{HIGH_VOL: 0.5, LOW_VOL: 0.5}` before checking classifier | Falls through to unified label handler at bottom |
| Missing features | Returns `None` (blocks pipeline) | Logs warning, falls back to P2 regime label |
| Classifier exception | Returns `None` (blocks pipeline) | Logs error, falls back to P2 regime label |
| No classifier object | Returns label-based probs | Same — but now unified with the other fallback paths |

### Why It Matters

In the old code, two failure modes return `None`:
1. Classifier exists but a feature is missing → `return None`
2. Classifier throws an exception → `return None`

When B2 returns `None`, the pipeline for that asset stops. No AIM aggregation, no Kelly sizing, no signal. The asset is silently skipped for the entire session. You'd never get an alert — just a missing signal.

The spec says B2 should always produce a result. The P2 regime label (from the locked strategy) is the designed fallback — that's the regime detected during research, before any live classifier is trained.

### Test on TOWER (old) — inspect the None paths

**Test 5.1: Find the None returns**

```bash
grep -n "return None" captain-online/captain_online/blocks/b2_regime_probability.py
```

- [ ] See at least two `return None` inside `_classifier_regime`

### Test on LAPTOP (new) — verify no None paths

**Test 5.2: Confirm None returns are gone**

```bash
grep -n "return None" captain-online/captain_online/blocks/b2_regime_probability.py
```

- [ ] Zero matches inside `_classifier_regime` (there may be `None` in other functions — that's fine)

**Test 5.3: Verify fallback logging**

```bash
grep -n "falling back to regime label" captain-online/captain_online/blocks/b2_regime_probability.py
```

- [ ] See log messages for both missing-features and classifier-failed paths

**Test 5.4: Unit test**

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/ -k "regime" -v 2>&1 | tail -20
```

- [ ] All regime tests pass

### Pass Criteria

Old code has `return None` paths that block the pipeline. New code always returns a probability dict, falling back to the P2 regime label.

---

## Section 6: Capacity Evaluator Performance (MEDIUM)

**Gaps closed:** G-038 (N+1 params), G-039 (full table scan)
**Risk level:** Performance — unnecessary DB round-trips and over-fetching

### What Changed

Four N+1 / over-fetch patterns fixed in `b9_capacity_evaluation.py`:

| # | Before | After | Savings |
|---|---|---|---|
| 6A | 4 separate `_load_param()` calls, 4 DB round-trips | 1 `_load_params_batch()` call, 1 query with `IN (...)` | 4 queries → 1 |
| 6B | Loop over 10 assets, 1 query each for `locked_strategy` | 1 query with `WHERE asset_id IN (...)` + `LATEST ON` | 10 queries → 1 |
| 6C | Load ALL `session_log` rows, filter in Python by `session_id` | SQL `WHERE ... AND param_key LIKE 'session_log_42_%'` | Full scan → filtered |
| 6D | Load ALL rows from `p3_d00_asset_universe`, dedup in Python | `WHERE asset_id IN (...)` + `LATEST ON PARTITION BY` | Full scan → filtered |

Also fixed: constraint field `"detail"` → `"message"` so the GUI can display it.

### Test on TOWER (old) — see the N+1 pattern

**Test 6.1: Count the queries**

```bash
# Find the old _load_param function (called 4 times)
grep -n "_load_param\b" captain-online/captain_online/blocks/b9_capacity_evaluation.py
```

- [ ] See 4 separate `_load_param(` calls
- [ ] See the single-key function definition

**Test 6.2: Check the full table scan**

```bash
grep -n "ORDER BY last_updated DESC" captain-online/captain_online/blocks/b9_capacity_evaluation.py
```

- [ ] See `_load_session_log` fetching ALL session_log rows with no `WHERE` filter on session_id

### Test on LAPTOP (new) — verify batched queries

**Test 6.3: Verify batch loading**

```bash
grep -n "_load_params_batch\|IN ({}" captain-online/captain_online/blocks/b9_capacity_evaluation.py
```

- [ ] See `_load_params_batch(param_defaults)` — single call
- [ ] See `WHERE asset_id IN (...)` patterns (not loops)

**Test 6.4: Verify session log filtering**

```bash
grep -n "LIKE" captain-online/captain_online/blocks/b9_capacity_evaluation.py
```

- [ ] See `AND param_key LIKE %s` in `_load_session_log`

**Test 6.5: Verify constraint field name**

```bash
grep -n '"detail"\|"message"' captain-online/captain_online/blocks/b9_capacity_evaluation.py
```

- [ ] See `"message"` (not `"detail"`) in the ASSET_CLASS_HOMOGENEITY constraint

**Test 6.6: Check the GUI**

Open the Captain GUI on the laptop → navigate to the Capacity page (if accessible).

- [ ] If an ASSET_CLASS_HOMOGENEITY constraint appears, it shows a message (not blank)

**Test 6.7: Unit test**

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/ -k "capacity" -v 2>&1 | tail -20
```

- [ ] All capacity tests pass

### Pass Criteria

Old code has 4 separate `_load_param` calls and unfiltered queries. New code has 1 batch call and filtered queries. Constraint message field is `"message"`.

---

## Section 7: Multi-Instance User ID (MEDIUM)

**Gap closed:** Hardcoded `primary_user` in Command main.py
**Risk level:** Multi-instance — tower deployment would always write `primary_user` to TSM state

### What Changed

| | Before | After |
|---|---|---|
| `_link_tsm_to_account` | `best["user_id"] = "primary_user"` | `best["user_id"] = os.environ.get("BOOTSTRAP_USER_ID", "primary_user")` |

### Why It Matters

In a multi-instance deployment (your laptop = PARITY 0, a client's machine = PARITY 1), each instance has its own user_id configured via `BOOTSTRAP_USER_ID`. The old code ignored this and always wrote `"primary_user"` to D08 TSM state. This means both instances would fight over the same TSM row, corrupting each other's account lifecycle state.

### Test

**Test 7.1: Verify env var usage**

```bash
grep -n "primary_user\|BOOTSTRAP_USER_ID" captain-command/captain_command/main.py
```

- [ ] See `os.environ.get("BOOTSTRAP_USER_ID", "primary_user")` — not a bare `"primary_user"` string

**Test 7.2: Compare with tower**

```bash
# On tower:
grep -n "primary_user" captain-command/captain_command/main.py
```

- [ ] See hardcoded `"primary_user"` assignment

### Pass Criteria

Laptop reads from env var with fallback. Tower has hardcoded value.

---

## Section 8: DRY — Shared JSON Parser (LOW)

**Gap closed:** G-035
**Risk level:** Maintenance — 7 identical copies of `_parse_json` across block files

### What Changed

| | Before | After |
|---|---|---|
| `_parse_json` function | Copy-pasted into 7 block files (~10 lines each) | Single `shared/json_helpers.py`, imported everywhere |
| Total copies | 7 | 1 |
| Files affected | b1, b2 (not changed), b4, b5, b5c, b6, b7_position_monitor | All import from `shared.json_helpers` |

### Why It Matters

If you ever need to fix a bug in JSON parsing (e.g., handle a new edge case), you'd need to find and update 7 copies. Miss one and you have divergent behavior between blocks. With a shared module, one fix covers everything.

### Test

**Test 8.1: Verify no local copies remain**

```bash
grep -rn "def _parse_json" captain-online/ captain-command/ captain-offline/
```

- [ ] Zero matches — all local definitions removed

**Test 8.2: Verify shared module exists**

```bash
cat shared/json_helpers.py
```

- [ ] Contains `def parse_json(raw, default):` with None check, isinstance check, json.loads

**Test 8.3: Verify imports**

```bash
grep -rn "from shared.json_helpers import" captain-online/ captain-command/
```

- [ ] See imports in b1, b4, b5, b5c, b6, b7_position_monitor

**Test 8.4: Count on tower for comparison**

```bash
# On tower:
grep -rn "def _parse_json" captain-online/ captain-command/ captain-offline/
```

- [ ] See 6-7 separate definitions

### Pass Criteria

Laptop: 0 local `_parse_json` definitions, 1 shared module, all blocks import it. Tower: 7 copies.

---

## Section 9: Full System Validation

After completing all individual section tests, run these end-to-end checks on the laptop.

### Test 9.1: Full test suite

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/ \
  --ignore=tests/test_integration_e2e.py \
  --ignore=tests/test_pipeline_e2e.py \
  --ignore=tests/test_pseudotrader_account.py \
  --ignore=tests/test_offline_feedback.py \
  --ignore=tests/test_stress.py \
  --ignore=tests/test_account_lifecycle.py \
  -v
```

- [ ] 95 passed, 0 failed

### Test 9.2: All containers healthy

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

- [ ] All containers show `healthy` or `running`
- [ ] No containers in restart loops

### Test 9.3: QuestDB tables accessible

```bash
# Verify the key tables exist and have data
psql -h localhost -p 8812 -U captain -d qdb -c "
  SELECT 'D00' as tbl, count(*) FROM p3_d00_asset_universe
  UNION ALL
  SELECT 'D01', count(*) FROM p3_d01_aim_model_states
  UNION ALL
  SELECT 'D08', count(*) FROM p3_d08_tsm_state
  UNION ALL
  SELECT 'D12', count(*) FROM p3_d12_kelly_params
  UNION ALL
  SELECT 'D16', count(*) FROM p3_d16_capital_silos
  UNION ALL
  SELECT 'D17', count(*) FROM p3_d17_system_monitor_state
  UNION ALL
  SELECT 'D25', count(*) FROM p3_d25_circuit_breaker;
"
```

- [ ] All tables return row counts (no errors)
- [ ] D00: 17 rows (10 active + 7 eliminated)
- [ ] D25: at least 1 row

### Test 9.4: Redis pub/sub working

```bash
# In one terminal, subscribe:
redis-cli -h localhost -p 6379 -a "<your REDIS_PASSWORD>" SUBSCRIBE "captain:status"

# In another terminal, check if Command is publishing heartbeats:
# (wait 30 seconds for a status message)
```

- [ ] Receive status/heartbeat messages on the channel

### Test 9.5: API responding

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

- [ ] Returns JSON with health status
- [ ] No authentication errors in response

### Test 9.6: GUI accessible

Open `http://localhost` in browser.

- [ ] GUI loads
- [ ] Dashboard shows asset data
- [ ] No console errors related to auth or connection failures

---

## Summary Checklist

| # | Section | Severity | Tower (Old) | Laptop (New) | Status |
|---|---------|----------|-------------|-------------|--------|
| 1 | DB Authentication | CRITICAL | Open access | Auth enforced | [ ] |
| 2 | Graceful Shutdown | CRITICAL | 10s force-kill, no cleanup | Clean <5s shutdown | [ ] |
| 3 | VIX Spike Detection | HIGH | Flat threshold 50 (useless) | Z-score > 2.0 (statistical) | [ ] |
| 4 | Wrong Table Names | HIGH | Queries fail silently | Correct tables | [ ] |
| 5 | Regime Fallback | HIGH | None → pipeline blocked | Always returns probs | [ ] |
| 6 | Capacity N+1 | MEDIUM | 15+ queries | 4 queries | [ ] |
| 7 | Multi-Instance UserID | MEDIUM | Hardcoded | Env-driven | [ ] |
| 8 | DRY JSON Parser | LOW | 7 copies | 1 shared module | [ ] |
| 9 | Full System | — | — | 95/95 tests, all healthy | [ ] |

---

## After Validation

Once all sections pass:

1. **Commit** the changes on the laptop (`final_val_1.0` branch)
2. **Create PR** from `final_val_1.0` → `main`
3. **Sync tower** — push to `multi-user` remote, run `captain-update.sh` on tower
4. **Re-run Section 1 on tower** to confirm auth is enforced there too

### Remaining Deferred Items (not blocking go-live)

These are documented in `plans/CAPTAIN_RECONCILIATION_MATRIX.md` but don't need to be fixed before live trading:

- G-025: Pseudotrader god module refactor (1,432 lines) — needs architectural decision
- 33 LOW-severity items across the reconciliation matrix
- CLAUDE.md has stale counts (tables, blocks, channels)
- Test coverage at 23% block coverage, Command pipeline at 0%
- 49 stale documentation claims flagged by fact-checker
