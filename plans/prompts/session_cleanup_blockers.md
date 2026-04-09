# Agent C — Cleanup Session: Pre-Live Blockers + Partial Fixes

You are AGENT C (Executor). You implement code changes.
This is a targeted cleanup session covering 3 pre-live-trading blockers and 4 partial fixes from the final validation report.

Read `docs/audit/FINAL_VALIDATION_REPORT.md` and `plans/CAPTAIN_RECONCILIATION_MATRIX.md` before starting.

## Assignment (in order — blockers first, then partials)

### 1. NEW-A04 | CRITICAL | uvicorn Overrides Signal Handlers
**File:** captain-command/captain_command/main.py:355-371
**Problem:** `signal.signal(SIGTERM/SIGINT, shutdown_handler)` is registered before `uvicorn.run()`. Uvicorn installs its own async signal handlers on event loop start, silently replacing the custom handler. On Docker SIGTERM: uvicorn shuts down cleanly but `orchestrator.stop()` and `telegram_bot.stop()` are never called. All daemon threads die abruptly — Redis subscriptions dropped without XACK, in-flight signal reads abandoned.
**Fix:** Remove the `signal.signal()` calls. Replace with a FastAPI lifespan context manager:
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown — runs on SIGTERM via uvicorn
    orchestrator.stop()
    if telegram_bot:
        telegram_bot.stop()

app = FastAPI(lifespan=lifespan)
```
Remove the old `shutdown_handler` function and the `signal.signal()` registrations.
**Verify:** Check that `orchestrator.stop()` joins its Redis listener thread (it should from G-044 fix in session 03). Check that `telegram_bot.stop()` exists and drains its queue.

### 2. NEW-A01 | CRITICAL | QuestDB Default Credentials
**File:** shared/questdb_client.py
**File:** docker-compose.yml (questdb service)
**File:** .env.template
**Problem:** QuestDB runs with default admin/quest credentials. Any local process can read/write all trading data (positions, AIM states, Kelly params, trade outcomes).
**Fix:**
1. In `docker-compose.yml`, add environment variables to the questdb service:
   ```yaml
   environment:
     - QDB_PG_USER=${QUESTDB_USER:-captain}
     - QDB_PG_PASSWORD=${QUESTDB_PASSWORD}
   ```
2. In `shared/questdb_client.py`, read credentials from env:
   ```python
   user = os.environ.get("QUESTDB_USER", "captain")
   password = os.environ.get("QUESTDB_PASSWORD", "")
   ```
   Pass these to the psycopg2/pg8000 connection call.
3. In `.env.template`, add:
   ```
   QUESTDB_USER=captain
   QUESTDB_PASSWORD=  # SET THIS — used by all 3 processes
   ```
4. Update any healthcheck that uses QuestDB's pg wire protocol to pass credentials.
**Note:** Do NOT set a default password in code. The `.env` file must have it set explicitly.

### 3. NEW-A02 | HIGH | Redis Without Authentication
**File:** docker-compose.yml (redis service)
**File:** shared/redis_client.py
**File:** .env.template
**Problem:** Redis has no `requirepass`. Any local process can inject trade commands via pub/sub channels (`captain:commands`, `captain:signals:*`).
**Fix:**
1. In `docker-compose.yml`, add command to redis service:
   ```yaml
   command: redis-server --requirepass ${REDIS_PASSWORD} --appendonly yes
   ```
2. In `shared/redis_client.py`, read password from env:
   ```python
   password = os.environ.get("REDIS_PASSWORD", None)
   ```
   Pass to `redis.Redis(password=password, ...)` and `redis.StrictRedis(password=password, ...)`.
3. In `.env.template`, add:
   ```
   REDIS_PASSWORD=  # SET THIS — used by all 3 processes + redis-cli
   ```
4. Update any Redis healthcheck in docker-compose to use `redis-cli -a ${REDIS_PASSWORD} ping`.

### 4. G-030 | MEDIUM | Position Monitor Stub Checks — Wrong Table + Missing Z-Score
**File:** captain-online/captain_online/blocks/b7_position_monitor.py:454-509
**Problem A:** `_check_vix_spike()` queries `system_params` which doesn't exist. Should be `p3_d17_system_params`.
**Problem B:** VIX check uses flat threshold comparison. Spec §2 B7 requires z-score > 2.0 against 60-day trailing mean/stdev.
**Fix A:** Replace table name `system_params` with `p3_d17_system_params` (or whatever the actual D17 table is — verify by reading `scripts/init_questdb.py` for the D17 CREATE TABLE statement).
**Fix B:** Implement proper VIX z-score:
```python
def _check_vix_spike(self):
    # Get current VIX and 60-day history
    rows = self.questdb.query(
        "SELECT vix_close FROM p3_d17_system_params "
        "WHERE param_key = 'VIX' ORDER BY timestamp DESC LIMIT 60"
    )
    if len(rows) < 10:
        return False  # Insufficient history
    values = [r['vix_close'] for r in rows]
    current = values[0]
    mean_60d = sum(values) / len(values)
    stdev_60d = (sum((v - mean_60d) ** 2 for v in values) / len(values)) ** 0.5
    if stdev_60d == 0:
        return False
    z_score = (current - mean_60d) / stdev_60d
    return z_score > 2.0
```
Adapt the query and column names to match the actual schema (READ the init script first).

### 5. G-031 | MEDIUM | Shadow Monitor Wrong Table Name
**File:** captain-online/captain_online/blocks/b7_shadow_monitor.py:217-221
**Problem:** Queries `asset_universe` instead of `p3_d00_asset_universe`. Will throw `DatabaseError` at runtime. Falls back to hardcoded 50.0 (wrong for non-ES assets).
**Fix:** Change table name:
```python
# FROM: "SELECT asset_id, point_value FROM asset_universe ..."
# TO:   "SELECT asset_id, point_value FROM p3_d00_asset_universe ..."
```
Verify the column name is correct — read `scripts/init_questdb.py` for D00 schema. It might be `contract_multiplier` instead of `point_value`.

### 6. G-038 | MEDIUM | Capacity Evaluator N+1 — _load_param Still Sequential
**File:** captain-online/captain_online/blocks/b9_capacity_evaluation.py:162-170
**Problem:** `_load_param()` makes 4 separate DB queries for individual config keys (signal_threshold, concentration_limit, min_quality_rate, max_concurrent_positions). The asset batch query was fixed but param loading wasn't.
**Fix:** Batch into single query:
```python
def _load_params(self):
    keys = ('signal_threshold', 'concentration_limit',
            'min_quality_rate', 'max_concurrent_positions')
    placeholders = ', '.join(f"'{k}'" for k in keys)
    rows = self.questdb.query(
        f"SELECT param_key, param_value FROM p3_d17_system_params "
        f"WHERE param_key IN ({placeholders}) LATEST ON timestamp PARTITION BY param_key"
    )
    return {row['param_key']: row['param_value'] for row in rows}
```
Update all callers of `_load_param(key)` to use the batched dict. Verify the D17 table name and schema by reading `scripts/init_questdb.py`.

### 7. G-039 | MEDIUM | Capacity Evaluator Full Table Load
**File:** captain-online/captain_online/blocks/b9_capacity_evaluation.py:180-195
**Problem:** `_get_strategy_models()` fetches entire D00 table then filters in Python. Should use SQL WHERE clause.
**Fix:** Add WHERE clause:
```python
def _get_strategy_models(self):
    strategy_ids = ', '.join(f"'{s}'" for s in self.active_strategies)
    rows = self.questdb.query(
        f"SELECT asset_id, locked_strategy FROM p3_d00_asset_universe "
        f"WHERE asset_id IN ({strategy_ids}) LATEST ON timestamp PARTITION BY asset_id"
    )
    return {row['asset_id']: row['locked_strategy'] for row in rows}
```
Verify column names match actual schema.

## Post-Fix

After ALL items:
1. Run `python3 -B -m pytest tests/ --ignore=tests/test_integration_e2e.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py --ignore=tests/test_account_lifecycle.py -v --tb=short 2>&1 | head -80`
2. Run `/ln-621-security-auditor` targeting shared/questdb_client.py, shared/redis_client.py, docker-compose.yml
3. Run `/ln-629-lifecycle-auditor` targeting captain-command/captain_command/main.py

## Reporting

After all fixes and audits, append to `docs/audit/FINAL_VALIDATION_REPORT.md` a new section:

```markdown
## Cleanup Session: Blockers + Partial Fixes

**Date:** [today's date]
**Items resolved:** 7

### Pre-Live Blockers (3)

| ID | Title | Status | Verification |
|----|-------|--------|--------------|
| NEW-A04 | uvicorn signal handler override | FIXED | FastAPI lifespan replaces signal.signal(); orchestrator.stop() confirmed called |
| NEW-A01 | QuestDB default credentials | FIXED | Auth via env vars; .env.template updated |
| NEW-A02 | Redis without auth | FIXED | requirepass enabled; all clients pass password |

### Partial Fix Completions (4)

| ID | Title | Status | Verification |
|----|-------|--------|--------------|
| G-030 | Position monitor stubs | FIXED | Table name corrected; VIX z-score implemented per spec §2 B7 |
| G-031 | Shadow monitor point values | FIXED | Table name corrected to p3_d00_asset_universe |
| G-038 | Capacity evaluator N+1 | FIXED | _load_params() batched to single query |
| G-039 | Capacity evaluator full table | FIXED | SQL WHERE clause added |

### Post-Fix Audit Results

[Paste ln-621 and ln-629 findings here]

### Remaining Items

- G-025: Pseudotrader god module (DEFERRED — pending DEC-04)
- 33 LOW-severity items (DEFERRED)
- CLAUDE.md stale counts (documentation-only, non-blocking)
```

Also update `plans/CAPTAIN_RECONCILIATION_MATRIX.md`:
- NEW-A01, NEW-A02, NEW-A04: Add entries with status FIXED
- G-030, G-031, G-038, G-039: Update status from FIXED to VERIFIED
- Update §6 Dashboard counts

## Rules

1. **ONE ITEM AT A TIME.** After each: show the diff, run pytest.
2. **Read actual files before editing** — verify table names, column names, function signatures against the real code and init scripts. Do not trust the line numbers in this prompt blindly.
3. **Do not modify frozen files** (shared/constants.py, config/ control values) without flagging.
4. Git commit after completing all items.
