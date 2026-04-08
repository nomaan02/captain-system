# AIM Data Implementation Plan

**Created:** 2026-03-30
**Scope:** Wire data sources into AIMs 4, 6, 8, 11, 12, 15
**Status:** DRAFT

---

## Phase 0: Prerequisites (USER ACTION REQUIRED)

Before Claude executes any implementation phases, the following must be in place:

### 0a. VIX/VXV Data Update (AIM-11, AIM-04)

The CSV files exist at `data/vix/` but are **stale** — last data point is **2026-03-21** (9 days ago).

**User must do ONE of:**

**Option A — CBOE Direct Download (preferred, no QC needed):**
```bash
# From project root
curl -o data/vix/VIX_History.csv "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
curl -o data/vix/VIX3M_History.csv "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv"
```
Then Claude will convert these to the `vix_daily_close.csv` / `vxv_daily_close.csv` format that `vix_provider.py` expects.

**Option B — QuantConnect Refresh:**
1. Paste `scripts/extract_vix_vxv_cell.py` into QC research notebook
2. Run the cell
3. Copy console output → save to `vix_vxv_raw.txt` in project root
4. Run `python scripts/decode_vix_vxv.py`
5. Verify `data/vix/vix_daily_close.csv` has rows through 2026-03-28

### 0b. Economic Calendar Data (AIM-06)

No external setup needed. Claude will create a static `config/economic_calendar_2026.json` with known FOMC, NFP, CPI dates from public Fed/BLS schedules.

### 0c. No External APIs Required

AIMs 8, 12, and 15 use data already flowing through TopstepX MarketStream and REST API. No new API keys or subscriptions needed.

---

## Phase 1: AIM-11 + AIM-04 (VIX Regime Warning + IVTS)

**Estimated time:** 15 minutes
**Code changes:** 1 file (env var in docker-compose OR symlink in Dockerfile)
**Dependencies:** Phase 0a complete (fresh CSVs)

### What to implement

1. **Fix path mismatch**: `vix_provider.py` resolves to `/app/data/vix/` but container mounts data at `/captain/data/vix/`.
   - **Fix**: Set `VIX_CSV_PATH` and `VXV_CSV_PATH` environment variables in `docker-compose.yml` for all 3 captain services, OR create a symlink in the Dockerfiles.
   - File: `docker-compose.yml` lines 40-48 (captain-offline), 66-74 (captain-online), 103-112 (captain-command)
   - Pattern: Add environment vars pointing to `/captain/data/vix/vix_daily_close.csv`

2. **If using CBOE direct download (Option A)**: Write a converter script that transforms CBOE's format (`DATE,OPEN,HIGH,LOW,CLOSE`) into vix_provider's format (`date,vix_close`).
   - CBOE VIX_History.csv has columns: `DATE,OPEN,HIGH,LOW,CLOSE`
   - CBOE VIX3M_History.csv has columns: `DATE,OPEN,HIGH,LOW,CLOSE`
   - vix_provider expects: `date,vix_close` with date format `YYYY-MM-DD`

3. **Wire AIM-04 IVTS**: The feature computation at `b1_features.py:567-573` already computes `ivts = vix_close / vxv_close`. Once the CSVs load, IVTS flows automatically.

4. **Daily auto-update cron**: Create a script that downloads fresh CBOE CSVs daily and converts them. Schedule via cron or Docker healthcheck.

### Verification checklist
- [ ] `docker exec captain-system-captain-online-1 python3 -c "from shared.vix_provider import get_latest_vix_close; print(get_latest_vix_close())"` returns a float
- [ ] `docker exec captain-system-captain-online-1 python3 -c "from shared.vix_provider import get_latest_vxv_close; print(get_latest_vxv_close())"` returns a float
- [ ] B1 feature output includes non-None `vix_z`, `vix_daily_change_z` for at least one asset
- [ ] B1 feature output includes non-None `ivts` for all assets
- [ ] B3 AIM-11 returns modifier != 1.0
- [ ] B3 AIM-04 returns modifier != 1.0

### Anti-pattern guards
- Do NOT modify `vix_provider.py` internals — use env vars
- Do NOT change CSV column names — must match `date,vix_close` / `date,vxv_close`
- Do NOT use `ivts_daily.csv` directly — let b1_features compute VIX/VXV ratio live

### Documentation references
- `shared/vix_provider.py:27-29` — path resolution and env var override
- `b1_features.py:567-573` — IVTS computation
- `b1_features.py:639-662` — VIX z-score computation
- `b3_aim_aggregation.py:219-236` — AIM-04 handler
- `b3_aim_aggregation.py:346-372` — AIM-11 handler

---

## Phase 2: AIM-15 (Volume Quality)

**Estimated time:** 30 minutes
**Code changes:** 1 file (`b1_features.py`)
**Dependencies:** None (uses live MarketStream data)

### What to implement

1. **Fix volume computation path**: The current code at `b1_features.py:575-585` calls `_get_historical_volume_first_N_min()` which is stubbed (returns None). But `_get_session_volume()` and `_get_historical_session_volumes()` are already implemented and use TopstepX data.

2. **Replace first-N-min approach with daily volume ratio**: Modify the AIM-15 feature computation to use:
   - Current: `_get_session_volume(asset_id)` — reads `quote_cache[contract_id]["volume"]`
   - Historical: `_get_historical_session_volumes(asset_id, lookback=20)` — calls TopstepX `get_bars()` for daily bars
   - Ratio: `current_volume / mean(historical_volumes)`

3. **Fallback**: If current session volume is 0 (pre-market), use None (AIM-15 stays neutral).

### Verification checklist
- [ ] B1 features include non-None `opening_volume_ratio` for assets with active MarketStream quotes
- [ ] Volume ratio is reasonable (0.1 to 10.0 range during market hours)
- [ ] B3 AIM-15 returns modifier != 1.0 when ratio is unusual

### Documentation references
- `b1_features.py:575-585` — current AIM-15 computation
- `b1_features.py:746-771` — `_get_session_volume()` and `_get_historical_session_volumes()`
- `b3_aim_aggregation.py:409-425` — AIM-15 handler thresholds

---

## Phase 3: AIM-12 (Dynamic Costs / Spread)

**Estimated time:** 1-2 hours
**Code changes:** 2 files (`b1_features.py`, `init_questdb.py`)
**Dependencies:** MarketStream bestBid/bestAsk (confirmed available)

### What to implement

1. **Current spread is already wired**: `_get_best_bid()` and `_get_best_ask()` at `b1_features.py:866-884` read from `quote_cache["bestBid"]` / `quote_cache["bestAsk"]`. The spread computation at `b1_features.py:664-672` uses `get_live_spread()` which calls these.

2. **Create spread history table**: Add `p3_spread_history` table to `scripts/init_questdb.py`:
   ```sql
   CREATE TABLE IF NOT EXISTS p3_spread_history (
       asset_id SYMBOL,
       session_id INT,
       spread DOUBLE,
       timestamp TIMESTAMP
   ) timestamp(timestamp) PARTITION BY MONTH;
   ```

3. **Write spread at session end**: After B1 computes `current_spread`, write it to `p3_spread_history`. Add a one-line insert in the B1 feature computation.

4. **Implement `_get_trailing_spreads()`**: Read last 60 entries from `p3_spread_history` for the given asset. Replace the stub at `b1_features.py:946`.

5. **Bootstrap**: Approximate historical spreads from TopstepX daily bars — use `(high - low) * tick_size_ratio` as a proxy for typical spread. Insert 60 days of approximate data into `p3_spread_history` for each asset.

### Verification checklist
- [ ] `p3_spread_history` table exists in QuestDB
- [ ] `_get_trailing_spreads()` returns list of 60+ floats for bootstrapped assets
- [ ] B1 features include non-None `current_spread` and `spread_z`
- [ ] B3 AIM-12 returns modifier != 1.0 when spread is unusual

### Anti-pattern guards
- Do NOT use spread_z from bootstrap data to make live trading decisions on day 1 — the proxy is approximate
- Do NOT write spreads outside market hours (would skew the baseline)

### Documentation references
- `b1_features.py:664-672` — spread feature computation
- `b1_features.py:866-884` — bestBid/bestAsk from quote_cache
- `b3_aim_aggregation.py:375-389` — AIM-12 handler thresholds

---

## Phase 4: AIM-08 (Cross-Asset Correlation)

**Estimated time:** 1-2 hours
**Code changes:** 1 file (`b1_features.py`)
**Dependencies:** TopstepX daily bars API (already works)

### What to implement

1. **Increase lookback in `_get_daily_closes()`**: Currently defaults to `lookback=35` at `b1_features.py:828`. For 252-day correlation z-score, need `lookback=260` (252 + buffer for rolling window).

2. **Implement `_get_trailing_correlations()`**: Replace stub at `b1_features.py:949` with:
   - Fetch 260 daily closes for both assets in the pair
   - Compute rolling 20-day Pearson correlations for each window
   - Return list of correlation values (length ~240)

3. **The z-score computation already exists**: `b1_features.py:600-615` calls `z_score()` (a utility function) on the trailing correlations with the current 20-day correlation.

4. **Pair selection**: `_get_correlation_pair()` at `b1_features.py:528` already maps assets to their most relevant pair (e.g., ES↔CL, NQ↔ES).

### Verification checklist
- [ ] `_get_daily_closes("ES", lookback=260)` returns 252+ values
- [ ] `_get_trailing_correlations("ES", "NQ", lookback=252)` returns 230+ values
- [ ] B1 features include non-None `correlation_20d` and `correlation_z`
- [ ] B3 AIM-08 returns modifier != 1.0 when correlation z is extreme

### Anti-pattern guards
- Do NOT fetch 260 bars per asset per session × 10 assets sequentially — batch or cache daily bars
- Do NOT assume TopstepX returns exactly N bars — handle holidays and gaps
- The rolling correlation needs both assets to have aligned dates

### Documentation references
- `b1_features.py:233-241` — `rolling_20d_correlation()` implementation
- `b1_features.py:600-615` — correlation feature pipeline
- `b1_features.py:528-535` — `_get_correlation_pair()` mapping
- `b3_aim_aggregation.py:292-304` — AIM-08 handler thresholds

---

## Phase 5: AIM-06 (Economic Calendar)

**Estimated time:** 2-3 hours
**Code changes:** 2 files (`b1_features.py`, new `config/economic_calendar_2026.json`)
**Dependencies:** None (static data)

### What to implement

1. **Create `config/economic_calendar_2026.json`**: Static JSON with all major events for 2026:
   - **Tier 1 (FOMC)**: 8 meeting dates from Federal Reserve schedule
   - **Tier 1 (NFP)**: First Friday of each month, 08:30 ET
   - **Tier 2 (CPI)**: Monthly BLS release dates, 08:30 ET
   - **Tier 2 (GDP)**: Quarterly BEA release dates, 08:30 ET
   - **Tier 3 (EIA)**: Weekly Wed 10:30 ET (affects CL only)
   - **Tier 3 (ISM)**: First business day of month, 10:00 ET
   
   Format per event:
   ```json
   {
     "name": "FOMC Rate Decision",
     "date": "2026-01-28",
     "time": "14:00",
     "timezone": "America/New_York",
     "tier": 1,
     "scope": "ALL",
     "affected_assets": []
   }
   ```

2. **Implement `_load_economic_calendar()`**: Replace stub at `b1_features.py:812` to read from the JSON file. Filter by date. Return events matching the session date.

3. **Mount config in containers**: Already mounted — `config/` is available at `/captain/config/` in all containers.

### Verification checklist
- [ ] `config/economic_calendar_2026.json` exists with 50+ events
- [ ] `_load_economic_calendar(date(2026, 3, 30))` returns correct events for that date
- [ ] B1 features include non-empty `events_today` on event days
- [ ] B1 features include non-None `event_proximity` on event days
- [ ] B3 AIM-06 returns modifier < 1.0 when FOMC/NFP is nearby

### Anti-pattern guards
- Do NOT hardcode event times without timezone — always use America/New_York
- Do NOT include events from other years — keep 2026 only for cleanliness
- Update the JSON file when Fed publishes 2027 schedule

### Documentation references
- `b1_features.py:138-183` — `check_economic_calendar()` and `min_distance_to_event()`
- `b1_features.py:587-592` — AIM-06 feature computation
- `b3_aim_aggregation.py:238-262` — AIM-06 handler thresholds and tier logic

---

## Phase 6: IVTS Automation Pipeline (AIM-04 ongoing data)

**Estimated time:** 1 hour
**Code changes:** 1 new script, 1 cron entry
**Dependencies:** Phase 1 complete, CBOE URLs accessible

### What to implement

1. **Create `scripts/update_vix_data.sh`**: Daily script that:
   - Downloads CBOE VIX_History.csv and VIX3M_History.csv
   - Converts to vix_provider format (`date,vix_close` / `date,vxv_close`)
   - Writes to `data/vix/vix_daily_close.csv` and `data/vix/vxv_daily_close.csv`
   - Logs success/failure

2. **Schedule via host crontab**: Run daily at 18:00 ET (after market close, before APAC session):
   ```
   0 18 * * 1-5 /path/to/captain-system/scripts/update_vix_data.sh >> /path/to/logs/vix_update.log 2>&1
   ```

3. **Hot reload in container**: After CSV update, the next B1 run will pick up new data because `vix_provider.py` uses lazy loading with no cache expiry — but it loads once. Add a `reload()` call at session start OR set a TTL on the cached data.

### Verification checklist
- [ ] `scripts/update_vix_data.sh` runs without error
- [ ] CSVs update with today's date as the last row
- [ ] Cron fires daily at 18:00 ET on weekdays
- [ ] Container picks up new data at next session

### Documentation references
- CBOE VIX download: `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`
- CBOE VIX3M download: `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv`
- `shared/vix_provider.py:155-162` — `reload()` function

---

## Phase 7: Verification & Integration Test

**Estimated time:** 30 minutes
**Code changes:** None (testing only)

### What to verify

1. **Rebuild and restart** all 3 captain containers
2. **Run the full pipeline replay** (`scripts/replay_full_pipeline.py --date 2026-03-30`)
3. **Check B3 output**: All 6 Tier 1 AIMs should report non-default modifiers for at least some assets
4. **Check combined_modifier**: Should be != 1.000 for most assets (weighted average of non-neutral AIMs)
5. **Compare sizing**: Run `replay_session.py` before and after — contracts should differ where modifiers are significant

### Expected outcomes by AIM

| AIM | Expected Modifier Range | What Triggers Non-Neutral |
|-----|------------------------|---------------------------|
| AIM-04 | 0.70-1.10 | IVTS > 1.0 (backwardation) or < 0.85 (deep contango) |
| AIM-06 | 0.60-1.00 | FOMC/NFP day within 30 min of open |
| AIM-08 | 0.85-1.10 | Correlation z-score > 2.0 or < -2.0 |
| AIM-11 | 0.63-1.10 | VIX z-score > 1.0 or < -1.0 |
| AIM-12 | 0.80-1.05 | Spread z-score > 1.0 or < -1.0 |
| AIM-15 | 0.80-1.15 | Volume ratio > 1.5x or < 0.7x |

---

## Execution Order Summary

| Phase | AIM(s) | Effort | User Action Required |
|-------|--------|--------|---------------------|
| **0** | — | 10 min | Download fresh CBOE CSVs (or run QC workflow) |
| **1** | 11 + 04 | 15 min | None |
| **2** | 15 | 30 min | None |
| **3** | 12 | 1-2 hrs | None |
| **4** | 08 | 1-2 hrs | None |
| **5** | 06 | 2-3 hrs | None |
| **6** | 04 auto | 1 hr | Verify cron works |
| **7** | ALL | 30 min | Review results |
