# Tower Fresh Start — Wipe → DECIMAL QuestDB → Reseed → Go-Live

**Date:** 2026-04-29
**Tower shell:** fish
**Repo:** `~/captain-system`

**Files read to produce this guide:**

- `scripts/captain-update.sh` — seed loop, integrity check
- `scripts/captain-setup.sh` — fresh-install order
- `scripts/bootstrap_production.py` — D00/D02/D16/D25
- `scripts/seed_system_params.py` — D17
- `scripts/seed_all_assets.py` + `captain-offline/captain_offline/blocks/bootstrap.py` — D00/D01/D04/D05/D12
- `scripts/seed_ohlcv_from_qc.py`, `seed_iv_rv_from_extract.py`, `seed_skew_from_extract.py`, `seed_or_volumes_from_qc.py`, `seed_opening_vol_from_qc.py` — D29–D33
- `scripts/backup_live_tables.py`, `scripts/restore_live_delta.py` — delta workflow
- `scripts/bootstrap_opening_volumes.py` — D29 OR range via TopstepX
- `scripts/update_vix_daily.py` — VIX/VXV CSVs
- `shared/canonical_schemas.py` — 38 tables + 42 DECIMAL migrations
- `docker-compose.yml` + `docker-compose.local.yml` — 9 services
- `captain-command/captain_command/main.py` — D08 TSM auto-link
- `docs2/audits/questdb-re-seed/2026-04-28_questdb_reseed_after_wipe.md` — primary staleness reference
- `docs2/audits/.../2026-04-28_tower_migration_guide_v2.md` — fish shell presentation reference
- `.env.template` — full variable inventory

---

## 0. Shell helpers (paste once per fish session)

```fish
cd ~/captain-system

function dco
    docker compose -f docker-compose.yml -f docker-compose.local.yml $argv
end

function cap-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/$script $rest
end
```

All numbered commands below use these helpers. The long-form `docker compose -f ... -f ...` is shown the first time and for any command with extra `-e` flags.

---

## A) Pre-flight

### A.1 Branch / commit

```fish
cd ~/captain-system
git branch --show-current
# Expected: migration/decimal-phase-c   (current HEAD: c6f771c)
# This branch is 5 commits ahead of main — it carries the monetary DECIMAL
# migrations (Phases A-C, M010-M042) in shared/canonical_schemas.py.
# If you intend to run from main, merge first:
#   git checkout main && git merge migration/decimal-phase-c
```

**Decision:** The wipe-and-reseed creates tables from `shared/canonical_schemas.py` which includes all DECIMAL column types in the DDLs **and** the ALTER TABLE migrations. Running from `migration/decimal-phase-c` (or main after merge) both produce the same schema on a fresh DB. Stay on whichever branch you intend to deploy.

### A.2 Confirm `.env`

```fish
test -f .env; and echo ".env present"; or echo "MISSING — see .env.template"
```

After the TopstepX account reset / credential rotation, update these keys in `.env`:

```fish
# Edit .env and set:
#   TOPSTEP_USERNAME=nomaanakram4@gmail.com
#   TOPSTEP_API_KEY=yEPc+sp5ZTcP5KhzFozRhyU7L5pEF3taJCRtXPDL/0c=
#   TOPSTEP_ACCOUNT_NAME=<new account name, e.g. PRAC-V2-XXXXXX-XXXXXXXX>
#   BOOTSTRAP_ACCOUNT_ID=PRAC-V2-551001-43861321
#   BOOTSTRAP_STARTING_CAPITAL=150000
#
# Also ensure these are set (from .env.template):
#   QUESTDB_USER, QUESTDB_PASSWORD
#   REDIS_PASSWORD
#   JWT_SECRET_KEY, API_SECRET_KEY
#   VAULT_MASTER_KEY
```

Verify parity for multi-instance:

```fish
grep
 INSTANCE_PARITY .env# Tower A=0, Tower B=1, or empty for single-instance
```

### A.3 Confirm TSM config files

D08 auto-link reads from `config/tsm/providers/`. These are committed:

```fish
ls config/tsm/providers/
# Expected: topstep_150k_eval.json  topstep_150k_live.json  topstep_150k_xfa.json  ibkr_retail.json
```

If missing, the `_link_tsm_to_account()` startup path in captain-command will fail silently and D08 stays empty.

### A.4 Optional: pre-wipe backup

If you want to preserve any accumulated live data (D30 bars, D29 OR volumes, D33, spread history, D03 trade log, D08, D16, etc.) for potential delta restore:

```fish
dco exec -T -e PYTHONPATH=/app captain-offline \
    python3 /captain/scripts/backup_live_tables.py --backup-root /captain/backups
```

The `${HOME}/captain-backups` directory on the host is bind-mounted into the container at `/captain/backups` (see `docker-compose.local.yml`), so the resulting `live-tables-<YYYYMMDD-HHMMSS>/` folder appears at both paths simultaneously. `restore_live_delta.py` can re-insert D29/D30/D33/spread rows beyond the seed frontier later (see D.5).

### A.5 Disk check

```fish
du -sh questdb/db/ 2>/dev/null
df -h .
```

---

## B) Wipe + Bring Stack Up

### B.1 Stop containers

```fish
cd ~/captain-system
dco down
```

### B.2 Delete QuestDB data

```fish
rm -rf questdb/db/*
```

This removes all tables, partitions, and WAL state. The directory itself is a Docker bind-mount and must remain.

### B.3 Redis decision

QuestDB wipe does **not** touch Redis. If you want a fully clean slate (parity counters reset, quote cache cleared):

```fish
# OPTIONAL — only if you want full reset:
rm -rf redis/appendonly.aof redis/dump.rdb 2>/dev/null
```

**Side effect:** `captain:parity_counter` resets to 0. On a multi-instance deployment, both towers must be reset together or the parity sequence will diverge.

### B.4 Start stack

```fish
dco up -d --build
```

Wait for infrastructure (QuestDB + Redis) to become healthy:

```fish
# Quick poll (or just wait ~30s):
sleep 15
dco ps
# All 9 services should show "Up" or "Up (healthy)"
```

---

## C) Schema + Baseline Seeds

There are **two options**. Option 1 is a single script that handles steps C.1–C.3. Option 2 is running seeds manually.

### Option 1: Use `captain-update.sh --skip-pull` (recommended)

```fish
bash scripts/captain-update.sh --skip-pull
```

This runs in order:

1. Syncs `config/` into service build contexts
2. Backs up QuestDB (skipped — dir is empty)
3. Rebuilds and restarts containers (`dco up -d --build`)
4. Waits for QuestDB + Redis
5. `init_questdb.py` → 38 tables + 42 DECIMAL migrations
6. `seed_all_assets.py` → D00 (17 assets), D01 (60 AIMs), D04 (10 BOCPD), D05 (60 EWMA), D12 (60 Kelly)
7. Five CSV seed scripts → D31, D32, D30, D29, D33
8. Integrity check

**Expected output at step 8:** `DATA INTEGRITY CHECK FAILED` — this is normal at this stage because D02 and D16 are not yet populated. The script prints a scary error but containers keep running. Proceed to C.4.

### Option 2: Manual (if captain-update.sh already ran or you prefer granular control)

```fish
# C.1 Schema
cap-run init_questdb.py

# C.2 Core asset bootstrap
cap-run seed_all_assets.py

# C.3 AIM data seeds
cap-run seed_iv_rv_from_extract.py
cap-run seed_skew_from_extract.py
cap-run seed_ohlcv_from_qc.py
cap-run seed_or_volumes_from_qc.py
cap-run seed_opening_vol_from_qc.py
```

### C.4 Bootstrap production (CRITICAL — not in captain-update.sh)

This fills D00 strategy overlay, D02 AIM meta-weights, D16 capital silo, D25 circuit breaker. **Without it, Online signal generation and position sizing break.**

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml \
    exec -T -e PYTHONPATH=/app \
    -e BOOTSTRAP_ACCOUNT_ID=(grep BOOTSTRAP_ACCOUNT_ID .env | cut -d= -f2) \
    -e BOOTSTRAP_USER_ID=primary_user \
    -e BOOTSTRAP_STARTING_CAPITAL=(grep BOOTSTRAP_STARTING_CAPITAL .env | cut -d= -f2) \
    captain-offline python /captain/scripts/bootstrap_production.py
```

Or if you prefer to set the values explicitly:

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml \
    exec -T -e PYTHONPATH=/app \
    -e BOOTSTRAP_ACCOUNT_ID=<your_new_account_id> \
    -e BOOTSTRAP_USER_ID=primary_user \
    -e BOOTSTRAP_STARTING_CAPITAL=150000 \
    captain-offline python /captain/scripts/bootstrap_production.py
```

**Verify output:** should end with `BOOTSTRAP COMPLETE — System ready for live trading`.

### C.5 Seed system parameters (not in captain-update.sh)

```fish
cap-run seed_system_params.py
```

Seeds D17 with 36 rows (quality thresholds, risk limits, AIM config, execution mode). Required by Online and Offline blocks.

### C.6 Restart captain-command for D08 TSM auto-link

After `.env` has new TopstepX credentials, restart captain-command so it authenticates and auto-links D08:

```fish
dco restart captain-command
sleep 10
dco logs --tail=30 captain-command | grep -i 'tsm\|auto-link\|authenticated'
```

The `_link_tsm_to_account()` in `captain-command/captain_command/main.py` (lines 73–133) will:

1. Authenticate against TopstepX API
2. Match the discovered account to the best TSM provider JSON in `config/tsm/providers/`
3. Write a full D08 row with starting/current balance from the live API

---

## D) "Up to Today" / API Gap Analysis

### D.1 Committed seed frontiers (verified from repo)


| Domain          | Table                          | Assets      | Max Date in CSV | How to verify                                       |
| --------------- | ------------------------------ | ----------- | --------------- | --------------------------------------------------- |
| D30 OHLCV       | `p3_d30_daily_ohlcv`           | All 10      | **2026-03-30**  | `tail -1 data/seed/aim_data/ohlcv_ES.csv`           |
| D31 IV/RV       | `p3_d31_implied_vol`           | **ES only** | **2026-03-27**  | `tail -1 data/seed/aim_data/es_iv_rv.csv`           |
| D32 Skew        | `p3_d32_options_skew`          | **ES only** | **2026-03-31**  | `tail -1 data/seed/aim_data/es_skew.csv`            |
| D29 OR Vol      | `p3_d29_opening_volumes`       | All 10      | **2026-03-30**  | `tail -1 data/seed/or_volume_data/ES_or_volume.csv` |
| D33 Opening Vol | `p3_d33_opening_volatility`    | All 10      | **2026-03-30**  | Same OR volume CSVs                                 |
| VIX CSV         | `data/vix/vix_daily_close.csv` | N/A         | **2026-04-09**  | `tail -1 data/vix/vix_daily_close.csv`              |
| VXV CSV         | `data/vix/vxv_daily_close.csv` | N/A         | **2026-04-09**  | `tail -1 data/vix/vxv_daily_close.csv`              |


### D.2 Will default seeds alone be current through today?

**No.** Today is 2026-04-29. Every market data table has a gap of ~4 weeks (2026-03-30 → today). Specifically:

- **D30/D29/D33 (all assets):** ~20 trading days missing. Online `b1_features.py` will write new rows forward-only once live sessions begin. The gap between seed frontier and first live session remains permanent unless you restore from backup.
- **D31 IV/RV:** ES stops at 2026-03-27; 9 other assets have **zero** IV/RV rows. No existing script pulls IV/RV from an API for non-ES assets. **Gap: needs new script or manual CSV update.**
- **D32 Skew:** ES stops at 2026-03-31; 9 other assets have **zero** skew rows. Same gap.
- **VIX/VXV:** Stops at 2026-04-09. Refreshable immediately (see D.3).

### D.3 Scripts that close the gap


| Table                      | Script                                           | API?                         | What it does                                                      | Command                              |
| -------------------------- | ------------------------------------------------ | ---------------------------- | ----------------------------------------------------------------- | ------------------------------------ |
| VIX/VXV CSVs               | `update_vix_daily.py`                            | Yahoo (no key)               | Appends missing days to `data/vix/*.csv`                          | `python scripts/update_vix_daily.py` |
| D29 `or_range_first_m_min` | `bootstrap_opening_volumes.py`                   | **Yes** — TopstepX           | Fetches ~35 days of 1-min bars, fills NULL `or_range_first_m_min` | See D.4 below                        |
| D29/D30/D33/spread         | `restore_live_delta.py`                          | No (backup CSV)              | Re-inserts rows beyond seed frontier from pre-wipe backup         | See D.5 below                        |
| D30/D29/D33 (future)       | Online `b1_features.py` / `b1_data_ingestion.py` | **Yes** — TopstepX WebSocket | Writes new rows each live session going forward                   | Automatic once captain-online runs   |


**No existing script** produces D31 IV/RV or D32 skew for non-ES assets, nor can it fill the 2026-03-27→today gap for ES. This is a **gap**.

### D.4 Bootstrap D29 OR range (optional, requires TopstepX)

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml \
    exec -T -e PYTHONPATH=/app captain-command \
    python /captain/scripts/bootstrap_opening_volumes.py
```

Runs inside **captain-command** (needs `shared/topstep_client.py` and live API auth). Fetches last 35 days of 1-min bars for all 10 assets. Fills `or_range_first_m_min` which CSV seeds leave as NULL.

### D.5 Restore live delta (optional, if backup exists)

The host's `~/captain-backups/` is bind-mounted into the container at `/captain/backups/` (see `docker-compose.local.yml`). Pass the **in-container** path — the script runs inside the container and won't see your host `~/`.

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml \
    exec -T -e PYTHONPATH=/app captain-offline \
    python /captain/scripts/restore_live_delta.py \
    --backup-dir /captain/backups/live-tables-20260421-140617
```

This computes per-asset seed frontiers from committed CSVs, then inserts only rows with dates **after** the frontier. Covers D30, D29, D33, and `p3_spread_history`. Does **not** restore D03, D08, or any other tables.

### D.6 Update VIX/VXV

```fish
python scripts/update_vix_daily.py
```

Fetches from Yahoo Finance (no API key). Appends to `data/vix/vix_daily_close.csv` and `data/vix/vxv_daily_close.csv`. These are flat files read at runtime by `shared/vix_provider.py` — not QuestDB tables, so they survive any DB wipe.

---

## E) Post-Seed Runtime Verification

### E.1 Row count checks (QuestDB console at [http://127.0.0.1:9000](http://127.0.0.1:9000))

```sql
-- Core state tables (must have data after C.1–C.5)
SELECT 'D00' as tbl, count() as rows FROM p3_d00_asset_universe;        -- expect 17
SELECT 'D01' as tbl, count() as rows FROM p3_d01_aim_model_states;      -- expect ~60
SELECT 'D02' as tbl, count() as rows FROM p3_d02_aim_meta_weights;      -- expect 60
SELECT 'D04' as tbl, count() as rows FROM p3_d04_decay_detector_states; -- expect 10
SELECT 'D05' as tbl, count() as rows FROM p3_d05_ewma_states;          -- expect 60
SELECT 'D12' as tbl, count() as rows FROM p3_d12_kelly_parameters;     -- expect 60
SELECT 'D16' as tbl, count() as rows FROM p3_d16_user_capital_silos;   -- expect >=1
SELECT 'D17' as tbl, count() as rows FROM p3_d17_system_monitor_state; -- expect 36
SELECT 'D25' as tbl, count() as rows FROM p3_d25_circuit_breaker_params; -- expect >=1

-- Market data seeds
SELECT 'D30' as tbl, count() as rows FROM p3_d30_daily_ohlcv;          -- expect ~2830
SELECT 'D29' as tbl, count() as rows FROM p3_d29_opening_volumes;      -- expect ~200+
SELECT 'D31' as tbl, count() as rows FROM p3_d31_implied_vol;          -- expect ~122 (ES only)
SELECT 'D32' as tbl, count() as rows FROM p3_d32_options_skew;         -- expect ~81 (ES only)
SELECT 'D33' as tbl, count() as rows FROM p3_d33_opening_volatility;   -- expect ~200+

-- D08 TSM (populated by captain-command auto-link — check after C.6)
SELECT account_id, name, starting_balance, current_balance
FROM p3_d08_tsm_state
LATEST ON last_updated PARTITION BY account_id;
-- expect: 1 row with your new account_id and correct balance

-- D00 strategy check
SELECT asset_id, captain_status, locked_strategy
FROM p3_d00_asset_universe
LATEST ON last_updated PARTITION BY asset_id
WHERE captain_status = 'ACTIVE';
-- expect: 10 rows, each with a non-empty locked_strategy JSON
```

### E.2 DECIMAL schema verification

```sql
-- Confirm monetary columns are DECIMAL after fresh create:
SHOW COLUMNS FROM p3_d08_tsm_state;
-- starting_balance, current_balance, etc. should show DECIMAL(18,2)

SHOW COLUMNS FROM p3_d03_trade_outcome_log;
-- entry_price, exit_price should show DECIMAL(14,4); pnl DECIMAL(18,4)

SHOW COLUMNS FROM p3_d30_daily_ohlcv;
-- open/high/low/close should show DECIMAL(14,4)
```

On a fresh DB the DDLs in `shared/canonical_schemas.py` create columns with DECIMAL directly — the 42 ALTER TABLE migrations in `CANONICAL_MIGRATIONS` are no-ops but run harmlessly.

### E.3 Captain-command TSM link check

```fish
dco logs --tail=50 captain-command | grep -iE 'tsm|auto-link|authenticated|account'
```

Look for:

- `TopstepX API: authenticated` — API credentials work
- `TSM auto-linked: account=<name> → <tsm_file>` — D08 row written
- If you see `TSM auto-link failed` or `Authentication failed`, check `.env` credentials

If D08 is empty after captain-command has started, restart it:

```fish
dco restart captain-command
sleep 15
dco logs --tail=30 captain-command | grep -i tsm
```

### E.4 Re-run integrity check (should now pass)

```fish
bash scripts/captain-update.sh --skip-pull 2>&1 | tail -20
```

After `bootstrap_production.py` and `seed_system_params.py`, the inline integrity check should print `INTEGRITY_OK`. If it still fails, check which table is short via E.1 queries.

### E.5 Schema drift + health audit

```fish
cap-run verify_schema_drift.py
cap-run verify_questdb_state.py
```

Both should exit 0. `verify_questdb_state.py` may warn about D08 if captain-command hasn't linked yet — that's expected until TopstepX auth succeeds.

---

## F) "Tomorrow NY Open" Checklist

Ordered steps. Complete all before the next 09:30 ET session.

### F.1 Must-do

- `**.env` credentials:** `TOPSTEP_USERNAME`, `TOPSTEP_API_KEY`, `TOPSTEP_ACCOUNT_NAME` updated for the new/reset account. `BOOTSTRAP_ACCOUNT_ID` and `BOOTSTRAP_STARTING_CAPITAL` match.
- **TSM config present:** `ls config/tsm/providers/` shows `topstep_150k_eval.json` (or the matching file for your account type).
- **Containers healthy:** `dco ps` — all 9 services Up.
- **Schema + seeds complete:** Sections C.1–C.5 executed. D00=17, D01≥60, D02=60, D05=60, D12=60, D16≥1, D17=36, D25≥1 (verify with E.1 SQL).
- **D08 TSM linked:** `SELECT count() FROM p3_d08_tsm_state;` returns ≥1. If zero, `dco restart captain-command` and recheck.
- **VIX/VXV refreshed:** `python scripts/update_vix_daily.py` — closes gap from 2026-04-09 to yesterday.

### F.2 Recommended

- **D29 OR-range backfill:** Run `bootstrap_opening_volumes.py` (section D.4) — fills `or_range_first_m_min` for last ~35 days via TopstepX API. Without this, AIM-15 features for the opening range use NULL for the OR range column.
- **Delta restore:** If you took a pre-wipe backup (section A.4), run `restore_live_delta.py` (section D.5) to re-insert D30/D29/D33 rows from 2026-03-30 through the wipe date.
- **Redis decision:** If multi-instance, confirm both towers agree on parity counter state. If you wiped Redis, both must be reset together.

### F.3 Accept as cold-start

These are **expected** to be empty or frozen after a fresh start. No action needed:


| Domain                | State               | Why                                                                                                                                                                  |
| --------------------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D01 `model_object`    | NULL                | AIM models retrain via live Offline `b1_aim_lifecycle.py`. Cold-start / BOOTSTRAPPED status until ~50+ sessions.                                                     |
| D03 trade history     | Empty               | Populated by Online B7 on each trade close. No seed script for this.                                                                                                 |
| D04 BOCPD/CUSUM       | Cold-start from P1  | Reset to `bocpd_cp_probability=0.01`, no live changepoint history.                                                                                                   |
| D05/D12 EWMA/Kelly    | P1 research vintage | Frozen to historical trade stats (2009–2025). Updated by Offline on each D03 event.                                                                                  |
| D06/D06b injection    | Empty               | Populated by Offline `b5_strategy_injection.py` at runtime.                                                                                                          |
| D11 pseudotrader      | Empty               | Populated by Offline `b3_pseudotrader.py`. Default backtest behavior does **not** require old D11 rows — the block reads D03/D05/D12 and generates new D11/D27 rows. |
| D26 HMM               | Empty (cold-start)  | Offline PG-01C trains after enough sessions. Online uses uniform opportunity weights in the meantime.                                                                |
| D31/D32 (non-ES)      | Empty               | **Gap:** no seed CSV or API script exists for these 9 assets. AIM features 4/6 start from scratch.                                                                   |
| `p3_spread_history`   | Empty               | **CRITICAL flag is benign on a fresh tower.** Auto-populated by Online B1 at next session open (one row per spread tick). Only non-empty if a pre-wipe backup was restored via `restore_live_delta.py` (D.5). |
| All event/log tables  | Empty               | D09, D10, D13, D18, D19, D21, D22, D27, D28, audit_log, replay, session events — all runtime-only.                                                                   |


### F.4 Pseudotrader note

The pseudotrader (Offline `b3_pseudotrader.py`) does **not** depend on old D11 rows for "default backtest behavior." It reads current D03 (trade outcomes), D05 (EWMA), D12 (Kelly), and D00 (strategy) to generate new D11 results and D27 forecasts. On a fresh start with empty D03, it has nothing to process until live trades accumulate — this is correct behavior.

---

## G) Tower Recovery / Lessons Learned

Both towers have walked this guide end-to-end. Two recurring footguns surfaced; this section documents the recovery for each so the next operator doesn't trip on them.

### G.1 Missed AIM-data seeds (D31, D32, D33)

**Symptom:** `verify_questdb_state.py` emits 3 CRITICALs:

```
[X] Freshness :: p3_d33_opening_volatility — 0 rows — external data not seeded
[X] Freshness :: p3_d31_implied_vol         — 0 rows — external data not seeded
[X] Freshness :: p3_d32_options_skew        — 0 rows — external data not seeded
```

**Cause:** Steps C.3 (or `captain-update.sh` step 7) was skipped or run before `init_questdb.py` finished. The seed CSVs (`data/seed/aim_data/es_iv_rv.csv`, `es_skew.csv`, `data/seed/or_volume_data/*_or_volume.csv`) **are** committed to git, so a `git pull` on any tower has them.

**Fix:**

```fish
cap-run seed_iv_rv_from_extract.py        # → 122 rows in p3_d31_implied_vol (ES only)
cap-run seed_skew_from_extract.py         # →  81 rows in p3_d32_options_skew (ES only)
cap-run seed_opening_vol_from_qc.py       # → ~240 sessions in p3_d33_opening_volatility (10 assets)
cap-run verify_questdb_state.py
```

Expected: 3 CRITICALs gone. `p3_spread_history` may remain CRITICAL — that's benign per F.3.

### G.2 `REPRO_TEST` poison row in D16 (debug-script artifact)

**Symptom:** `verify_questdb_state.py` emits 2 CRITICALs:

```
[X] D16 capital :: REPRO_TEST.accounts                  — empty list
[X] D16 capital :: REPRO_TEST.max_simultaneous_positions — None
```

**Cause:** `scripts/debug_d08_minimal_repro.py` writes a row with `user_id='REPRO_TEST'` to D16 as part of its Q3 baseline test. Older revisions of the script (pre-2026-04-29) used `accounts='[]'` and omitted `max_simultaneous_positions`, both of which trip `check_d16_capital`. The cleanup section that DELETEs the row was added on 2026-04-29 — towers that ran the debug script before that commit will carry the poison row forward.

The row is invisible to production code (which filters `WHERE user_id = %s` on the active `BOOTSTRAP_USER_ID`); it only affects the verifier's `LATEST ON … PARTITION BY user_id` projection.

**Fix (surgical, no service restart):**

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml \
    exec -T -e PYTHONPATH=/app captain-offline \
    python -c "
from shared.questdb_client import get_cursor
with get_cursor() as cur:
    cur.execute(\"DELETE FROM p3_d16_user_capital_silos WHERE user_id = 'REPRO_TEST'\")
    cur.execute(\"DELETE FROM p3_d08_tsm_state WHERE account_id IN ('FMT_PROBE_0','FMT_PROBE_1','FMT_PROBE_2','FMT_PROBE_3','FMT_PROBE_4','FMT_PROBE_5','FMT_PROBE_6','FMT_PROBE_7','SHAPE_3a','SHAPE_4a','SHAPE_4b','SHAPE_4c','SHAPE_5a','SHAPE_5b','SHAPE_5c','SHAPE_5d','FULL_PROBE','BARE_PROBE','CAST_PROBE')\")
print('D16 REPRO_TEST + D08 probe rows removed')
"
cap-run verify_questdb_state.py
```

DELETE on WAL tables is supported (production reference: `captain-offline/captain_offline/blocks/version_snapshot.py:168`).

**Fallback if DELETE rejects the table for any reason:** drop and rebootstrap *just* D16. All other tables are untouched, and `bootstrap_production.py` is idempotent (line 218-226 explicitly skips already-bootstrapped users):

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml \
    exec -T questdb \
    curl -s 'http://localhost:9000/exec' \
    --data-urlencode "query=DROP TABLE p3_d16_user_capital_silos;"

cap-run init_questdb.py                  # recreates D16 schema only (CREATE TABLE IF NOT EXISTS)
docker compose -f docker-compose.yml -f docker-compose.local.yml \
    exec -T -e PYTHONPATH=/app \
    -e BOOTSTRAP_ACCOUNT_ID=(grep BOOTSTRAP_ACCOUNT_ID .env | cut -d= -f2) \
    -e BOOTSTRAP_USER_ID=primary_user \
    -e BOOTSTRAP_STARTING_CAPITAL=(grep BOOTSTRAP_STARTING_CAPITAL .env | cut -d= -f2) \
    captain-offline python /captain/scripts/bootstrap_production.py
cap-run fix_bootstrap_data.py
```

### G.3 `p3_spread_history` CRITICAL on a fresh tower

**Symptom:** `verify_questdb_state.py` emits

```
[X] Freshness :: p3_spread_history — 0 rows — external data not seeded
   fix: Auto-populated by Online B1; will fill on session open
```

**Cause:** No pre-wipe backup was restored via `restore_live_delta.py` (D.5). Tower-1's GO-LIVE READY state had 666 rows from a backup at `~/captain-backups/live-tables-20260421-140617/`; fresh towers without that snapshot start at 0 rows.

**Action:** None required. Online B1 writes one row per spread tick during live sessions, so the table fills the moment captain-online sees its first websocket message at session open. This CRITICAL is **benign** for go-live readiness on a fresh tower (tracked in F.3).

If you want the CRITICAL gone before session open *and* you have a backup to restore from, run D.5.

---

## Summary Table


| Domain              | Table                           | Seed Script                                      | In `captain-update.sh`? | API needed?        | Committed frontier   | Gap to today              |
| ------------------- | ------------------------------- | ------------------------------------------------ | ----------------------- | ------------------ | -------------------- | ------------------------- |
| D00 asset universe  | `p3_d00_asset_universe`         | `seed_all_assets.py` + `bootstrap_production.py` | Partial (no bootstrap)  | No                 | N/A (config data)    | None                      |
| D01 AIM states      | `p3_d01_aim_model_states`       | `seed_all_assets.py`                             | Yes                     | No                 | N/A (status only)    | model_object=NULL         |
| D02 AIM weights     | `p3_d02_aim_meta_weights`       | `bootstrap_production.py`                        | **No**                  | No                 | N/A (config data)    | None after bootstrap      |
| D04 BOCPD           | `p3_d04_decay_detector_states`  | `seed_all_assets.py`                             | Yes                     | No                 | P1 vintage           | Cold-start                |
| D05 EWMA            | `p3_d05_ewma_states`            | `seed_all_assets.py`                             | Yes                     | No                 | P1 vintage           | Frozen until live D03     |
| D08 TSM             | `p3_d08_tsm_state`              | captain-command auto-link                        | No (runtime)            | **Yes** — TopstepX | N/A                  | Auto at startup           |
| D12 Kelly           | `p3_d12_kelly_parameters`       | `seed_all_assets.py`                             | Yes                     | No                 | P1 vintage           | Frozen until live D03     |
| D16 capital silo    | `p3_d16_user_capital_silos`     | `bootstrap_production.py`                        | **No**                  | No                 | N/A                  | None after bootstrap      |
| D17 sys params      | `p3_d17_system_monitor_state`   | `seed_system_params.py`                          | **No**                  | No                 | N/A                  | None after seed           |
| D25 circuit breaker | `p3_d25_circuit_breaker_params` | `bootstrap_production.py`                        | **No**                  | No                 | N/A                  | Cold-start                |
| D29 OR volumes      | `p3_d29_opening_volumes`        | `seed_or_volumes_from_qc.py`                     | Yes                     | No (CSV)           | 2026-03-30           | ~20 days                  |
| D29 OR range        | (same table)                    | `bootstrap_opening_volumes.py`                   | No                      | **Yes** — TopstepX | NULL in seeds        | All rows                  |
| D30 OHLCV           | `p3_d30_daily_ohlcv`            | `seed_ohlcv_from_qc.py`                          | Yes                     | No (CSV)           | 2026-03-30           | ~20 days                  |
| D31 IV/RV           | `p3_d31_implied_vol`            | `seed_iv_rv_from_extract.py`                     | Yes                     | No (CSV)           | 2026-03-27 (ES only) | ~21 days + 9 assets empty |
| D32 Skew            | `p3_d32_options_skew`           | `seed_skew_from_extract.py`                      | Yes                     | No (CSV)           | 2026-03-31 (ES only) | ~19 days + 9 assets empty |
| D33 Opening vol     | `p3_d33_opening_volatility`     | `seed_opening_vol_from_qc.py`                    | Yes                     | No (CSV)           | 2026-03-30           | ~20 days                  |
| VIX/VXV             | `data/vix/*.csv` (flat file)    | `update_vix_daily.py`                            | No                      | Yahoo (no key)     | 2026-04-09           | ~14 days                  |


