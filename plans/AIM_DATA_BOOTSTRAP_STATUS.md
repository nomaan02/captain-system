# AIM Data Bootstrap Status

**Created:** 2026-04-01
**Source data:** `/home/nomaan/captain-system-data-extracts/`
**Purpose:** Track what data has been seeded, what's available but needs wiring, and what's still missing.

---

## Seeded (Live and Working)

### AIM-15: Opening Volume — P3-D29

- **Status:** SEEDED
- **Source:** QuantConnect 1-min bars → `or_volume_data/{ASSET}_or_volume.csv`
- **Rows:** 240 (24 days × 10 assets, 2026-02-25 → 2026-03-30)
- **Exceeds minimum:** 24 days > 20 days required
- **Self-sustaining:** YES — orchestrator `_recompute_aim15_volume()` writes to P3-D29 after each OR close
- **Script:** `scripts/seed_or_volumes_from_qc.py`

### AIM-04/11: VIX and VXV — Bundled CSVs

- **Status:** CURRENT (appended 2026-03-31)
- **Source:** Pre-bundled `data/vix/vix_daily_close.csv` (9155 rows, 1990→2026-03-31) + QC extract confirmation
- **VXV:** `data/vix/vxv_daily_close.csv` (4159 rows, 2007→2026-03-31)
- **Exceeds minimum:** 9155 days >> 252 days required for AIM-11 z-score
- **Self-sustaining:** NO — CSV is static. Needs daily append mechanism (Yahoo Finance API, scheduled QC job, or manual update)
- **Action needed:** Wire a daily VIX/VXV update (cron job or startup fetch). Until then, data stops at 2026-03-31.

### AIM-08/09/Overnight: Daily OHLCV — P3-D30

- **Status:** SEEDED + WIRED
- **Source:** QuantConnect daily bars → `aim_data/ohlcv_combined.csv`
- **Table:** `p3_d30_daily_ohlcv` (new)
- **Rows:** 2829 (283 days × 10 assets, 2025-02-25 → 2026-03-30)
- **Exceeds minimum:** 283 days > 252 days required for AIM-08 correlation z-score
- **Powers:**
  - **AIM-08** correlation z-score (252d baseline) — `_get_daily_closes()` now reads P3-D30 first, falls back to TopstepX
  - **AIM-09** momentum MACD (63d) — same `_get_daily_closes()` path
  - **AIM-04** overnight return z-score (60d) — `_get_trailing_overnight_returns()` now computes from P3-D30 open/close pairs
- **Self-sustaining:** YES — orchestrator calls `store_daily_ohlcv()` after each OR close, appending each day's bar from TopstepX into P3-D30
- **Scripts:** `scripts/seed_ohlcv_from_qc.py`, `scripts/init_questdb.py` (P3-D30 table def)
- **Code changes:** `b1_features.py` — `_get_daily_closes()` checks DB first; `_get_trailing_overnight_returns()` implemented; `store_daily_ohlcv()` added. `orchestrator.py` — calls `store_daily_ohlcv()` in Phase B.

### AIM-04/11: VIX/VXV Daily Auto-Update

- **Status:** AUTO-REFRESHED
- **Script:** `scripts/update_vix_daily.py` — fetches from Yahoo Finance v8 chart API (no API key)
- **Integration:** `captain-start.sh` Step 6b — runs on every system startup before containers finish init
- **Reload:** `vix_provider.py` detects CSV mtime change and reloads automatically
- **VIX last date:** 2026-04-01 (24.76)
- **Self-sustaining:** YES — every `captain-start.sh` invocation refreshes data

### AIM-01: ES Implied Vol / Realised Vol — P3-D31

- **Status:** SEEDED (ES only)
- **Source:** QuantConnect extract → `aim_data/es_iv_rv.csv`
- **Table:** `p3_d31_implied_vol`
- **Rows:** 122 (2025-08-22 → 2026-03-27, ES only)
- **Exceeds minimum:** 122 days > 120 days required for feature gate
- **Self-sustaining:** NO — requires options chain access for daily IV updates
- **Script:** `scripts/seed_iv_rv_from_extract.py`
- **Code changes:** `b1_features.py` — `_get_atm_implied_vol()`, `_get_realised_vol()`, `_get_trailing_overnight_vrp()` read P3-D31

### AIM-02: ES CBOE SKEW — P3-D32

- **Status:** SEEDED (ES skew half only)
- **Source:** QuantConnect extract → `aim_data/es_skew.csv`
- **Table:** `p3_d32_options_skew`
- **Rows:** 81 (2025-12-03 → 2026-03-31, ES only)
- **Exceeds minimum:** 81 days > 60 days required for skew z-score
- **Graceful degradation:** AIM-02 operates at 0.4 confidence (skew only) instead of 0.7 (skew + PCR)
- **Self-sustaining:** NO — requires daily CBOE SKEW fetch
- **Script:** `scripts/seed_skew_from_extract.py`
- **Code changes:** `b1_features.py` — `_get_trailing_skew()` reads P3-D32

### AIM-12: Opening Volatility (vol_z) — P3-D33

- **Status:** SEEDED + WIRED
- **Source:** QuantConnect 1-min OR bars → `or_volume_data/{ASSET}_or_volume.csv`
- **Table:** `p3_d33_opening_volatility`
- **Rows:** ~240 (24 sessions × 10 assets, 2026-02-25 → 2026-03-30)
- **Self-sustaining:** YES — `store_opening_volatility()` called from Online orchestrator after OR close
- **Script:** `scripts/seed_opening_vol_from_qc.py`
- **Code changes:** `b1_features.py` — `_get_recent_5min_vol()` computes from live bars, `_get_trailing_open_vol()` reads P3-D33, `store_opening_volatility()` persists daily. `orchestrator.py` — calls `store_opening_volatility()` in Phase B.

---

## Outstanding Data Gaps — AIM-by-AIM Breakdown

This section documents every AIM that is currently degraded or inactive due to missing data, what the AIM does for the trading system, exactly what data it needs, how that data should be retrieved and refreshed daily, and the concrete impact on signal quality while the gap persists.

---

### AIM-01: Volatility Risk Premium (VRP) Monitor

**What it does:** Measures the gap between implied volatility (what the market expects) and realised volatility (what actually happened). When IV is expensive relative to RV (positive VRP), the market is overpricing risk — ORB breakouts are less likely to sustain, so sizing is reduced. When IV is cheap (negative VRP), breakouts run further, so sizing gets a slight boost. The Monday adjustment (×0.95) accounts for weekend uncertainty accumulation.

**Modifier range:** z > +1.5 → 0.70 (reduce), z > +0.5 → 0.85, z < -1.0 → 1.10 (boost), else → 1.00

**Current state:** ACTIVE (ES only) — `_get_atm_implied_vol()` and `_get_realised_vol()` read from P3-D31 (122 days, ES). `_get_trailing_overnight_vrp()` computes IV-RV series for z-score. Other 9 assets still return None (no IV/RV data).

**Data extracted (needs wiring):**
- File: `captain-system-data-extracts/aim_data/es_iv_rv.csv`
- Columns: `date, atm_iv_30d, realized_vol_20d`
- Range: 2025-08-22 → 2026-03-27 (122 days — meets the 120-day feature gate)
- Coverage: ES only. Other 9 assets have no IV/RV data.

**What's needed for full operation:**
- Historical: 120 trading days of ATM 30-day implied vol + 20-day realised vol per asset
- Daily refresh: One new row per trading day — ATM IV from options chain (30d maturity, delta ≈ 0.50), realised vol from trailing 20-day close-to-close standard deviation
- Frequency: Daily, after market close (options IV is closing value)
- Source options: CBOE VIX methodology (for ES/SPX), QuantConnect options universe, Interactive Brokers historical vol data, or Yahoo Finance options chain
- Multi-asset gap: We only have ES data. For the other 9 assets, VRP would require per-asset options data (NQ options, CL options, ZB options, etc.) or a proxy mapping (e.g., use VIX for all equity index futures)

**Daily retrieval mechanism needed:**
1. After 16:15 ET daily: fetch ES ATM IV (30d) from options data source
2. Compute 20-day realised vol from P3-D30 daily closes (already stored)
3. Append to a persistent store (CSV or QuestDB table)
4. `_get_atm_implied_vol()` and `_get_trailing_overnight_vrp()` read from this store

**Impact while inactive:** The system loses its only measure of whether options markets are pricing risk correctly relative to actual moves. In high-VRP environments (like pre-earnings or pre-FOMC), the system will trade at full size when it should be reducing by 15-30%. In low-VRP environments, it misses a 10% sizing boost. This is a **Tier 2 AIM** (monthly retrain cycle), so the DMA meta-weight won't learn to downweight it — it will simply contribute nothing.

---

### AIM-02: Options Skew & Positioning Analyzer

**What it does:** Combines two signals — the Put-Call Ratio (institutional hedging demand) and the DOTM-OTM put IV spread (tail risk pricing) — into a weighted fear/greed indicator. High combined z-score means heavy put buying + steep skew = market fear, so sizing is reduced. Low combined z-score means bullish positioning, so sizing gets a boost.

**Modifier range:** combined > +1.5 → 0.75, > +0.5 → 0.90, < -1.0 → 1.10, else → 1.00
**Combination:** combined = 0.6 × z_score(PCR, 30d) + 0.4 × z_score(skew, 60d)

**Current state:** PARTIAL (ES skew half) — `_get_trailing_skew()` reads from P3-D32 (81 days, ES). AIM-02 operates at 0.4 confidence for ES (skew only, no PCR). Other assets still return None.

**Data extracted (skew half — needs wiring):**
- File: `captain-system-data-extracts/aim_data/es_skew.csv`
- Columns: `date, cboe_skew, skew_spread_proxy`
- Range: 2025-12-03 → 2026-03-31 (81 days — meets the 60-day feature gate for skew half)

**Data NOT extracted (PCR half — needs sourcing):**
- Daily equity put volume / call volume ratio for ES/SPX options
- Source options: CBOE daily PCR report (free, published daily), QuantConnect options universe (aggregate from chain), Yahoo Finance options page
- 30 days minimum for z-score, 60 days for full feature gate

**What's needed for full operation:**
- **PCR:** Daily total put volume / total call volume for ES/SPX options. One number per day.
- **Skew:** Daily CBOE SKEW index value (already extracted) OR computed as DOTM put IV (10-delta) minus OTM put IV (25-delta) from options chain
- Historical: 60 trading days for both signals
- Daily refresh: After 16:15 ET, fetch closing PCR + SKEW values
- Source: CBOE publishes both free daily — PCR at cboe.com/market-statistics, SKEW index at cboe.com/vix

**Daily retrieval mechanism needed:**
1. After 16:15 ET daily: fetch CBOE PCR and SKEW closing values
2. Append to persistent store
3. Wire `_get_trailing_pcr()` and `_get_trailing_skew()` to read from store

**Impact while inactive:** The system has no read on institutional positioning or tail-risk pricing. Before major events (earnings season, debt ceiling, election), put buying surges and skew steepens — the system should be reducing size by 10-25% but instead trades at full size. Conversely, in complacent markets with flat skew, the system misses a 10% boost. AIM-02 uses graceful degradation — if only one signal is available (e.g., skew but not PCR), it operates at reduced confidence (0.4 instead of 0.7). **Wiring the skew data alone would partially activate AIM-02.**

---

### AIM-03: Gamma Exposure (GEX) Estimator

**What it does:** Estimates whether options market-makers are net long gamma (positive GEX) or net short gamma (negative GEX). Positive gamma means dealers hedge by selling into rallies and buying dips — this dampens price moves and makes ORB breakouts stall (mean-reversion). Negative gamma means dealers amplify moves — breakouts run further. This is the most directly relevant AIM for ORB strategy performance.

**Modifier:** positive GEX → 0.90 (reduce — breakouts stall), negative GEX → 1.10 (boost — breakouts run)

**Current state:** COMPLETELY INACTIVE — `_get_dealer_gamma()` returns None. AIM-03 always outputs 1.0 with tag `GEX_MISSING`.

**Data needed:**
- Net dealer gamma exposure estimate, computed daily from options open interest
- Formula: GEX = Σ(OI × gamma × contract_multiplier × sign) across all strikes, where sign = +1 for calls, -1 for puts (dealers are assumed short calls and long puts from retail flow)
- Historical: 60 trading days for z-score baseline
- Frequency: Daily, after options close (16:15 ET)

**Why this is the hardest gap to fill:**
- Requires the full options chain (all strikes, all expirations) with Greeks (specifically gamma per strike)
- Must be computed, not downloaded as a single number — no public source publishes dealer GEX directly
- QuantConnect can provide options chain data with Greeks, but the aggregation logic must be implemented
- Alternative: Use a GEX proxy service (SpotGamma, Menthor Q, or similar) that publishes daily GEX estimates — this is simpler but adds a paid data dependency

**Daily retrieval mechanism needed:**
1. After 16:15 ET: fetch full ES/SPX options chain (OI + gamma per strike)
2. Compute net dealer gamma = Σ(call_OI × gamma × 100) - Σ(put_OI × gamma × 100)
3. Store daily GEX value
4. Wire `_get_dealer_gamma()` to read from store

**Impact while inactive:** This is arguably the most impactful missing AIM for ORB specifically. On days with strong positive gamma (like post-OpEx), breakouts routinely fail within the first 15 minutes — the system should be sizing down 10% but doesn't know to. On negative gamma days (like approaching large expirations), breakouts run aggressively — the system misses a 10% boost. The binary nature of GEX (dampen vs amplify) means the signal is high-conviction when it fires. The DMA meta-weight will eventually learn to ignore AIM-03 since it never contributes, making it harder to re-activate later.

---

### AIM-07: Commitment of Traders (COT) Positioning

**What it does:** Reads CFTC weekly Commitment of Traders data to identify whether large commercial hedgers and speculators are positioning for up or down moves. The Speculative Momentum Index (SMI) captures whether institutional flow is net long or short. Extreme positioning (crowded longs or contrarian opportunities) adds an overlay modifier.

**Modifier:** SMI +1 → 1.05 (institutional longs = slight boost), SMI -1 → 0.90 (institutional shorts = reduce). Extreme overlay: speculator_z > 1.5 → ×0.95 (crowded, elevated risk), speculator_z < -1.5 → ×1.10 (contrarian opportunity)

**Current state:** COMPLETELY INACTIVE — `cot_smi` and `cot_speculator_z` always None. AIM-07 outputs 1.0 with tag `COT_MISSING`.

**Data needed:**
- CFTC Commitment of Traders (Futures Only) report for: E-Mini S&P 500 (ES), E-Mini NASDAQ-100 (NQ), Crude Oil (CL), US Treasury Bonds (ZB), 10-Year T-Notes (ZN), Gold (MGC → use GC contract)
- Fields per asset per week: `commercial_long, commercial_short, noncommercial_long, noncommercial_short, nonreportable_long, nonreportable_short`
- From these, compute: SMI = sign(commercial_net - speculator_net), speculator_z = z_score(speculator_net, 52-week trailing)
- Historical: 260 trading days / 52 weeks (longest feature gate of any AIM)
- Frequency: WEEKLY — data reflects positions as of Tuesday, released Friday at 15:30 ET

**Source options:**
- Quandl/Nasdaq Data Link: `CFTC/{SYMBOL}_F_ALL` — free tier available, structured data
- CFTC.gov direct: Weekly CSV downloads from cftc.gov/dea/futures/
- QuantConnect: `QuantConnect.Data.Custom.CFTC` data universe

**Daily retrieval mechanism needed:**
1. Every Friday after 15:30 ET (or Saturday morning): fetch latest CFTC report
2. Parse commercial and speculator positions per futures contract
3. Compute SMI polarity and speculator z-score
4. Store in persistent table (one row per asset per week)
5. Wire `_load_cot_history()` to read from store, surface as `cot_smi` and `cot_speculator_z`
6. Values persist all week (data only changes weekly)

**Impact while inactive:** The system has no visibility into institutional positioning. In 2022 and 2023, COT data flagged several major turning points where speculators were extremely crowded long before large drawdowns — the system would have reduced exposure by 5-10% via the extreme overlay. Conversely, contrarian opportunities (extreme bearishness in speculators) preceded strong breakout environments. AIM-07 is a Tier 2 AIM with a 260-day feature gate, so even after data is connected, it takes a full year of weekly data before z-scores become meaningful. **Starting data collection sooner is better even if the AIM isn't immediately activated.**

---

### AIM-12: 5-Minute Opening Volatility (vol_z component)

**What it does:** AIM-12 estimates dynamic trading costs using two signals: bid-ask spread z-score (already working) and 5-minute opening volatility z-score (missing). High opening vol means worse fill quality on stop orders — ORB entries may slip significantly. The dual-signal design uses OR logic for cost detection (either signal alone is sufficient) and AND logic for low-cost detection (both must confirm).

**Modifier (full):** spread_z > 1.5 OR vol_z > 1.5 → 0.85, spread_z > 0.5 OR vol_z > 0.5 → 0.95, spread_z < -0.5 AND vol_z < -0.5 → 1.05, else → 1.00. VIX overlay: VIX_z > 1.0 → ×0.95.

**Current state:** FULL — spread_z works (from TopstepX quote cache + `p3_spread_history`). vol_z now reads from P3-D33 (`_get_trailing_open_vol()`) and live 1-min bars (`_get_recent_5min_vol()`). Bootstrapped with 24 sessions per asset from QC OR bars. Self-sustaining via `store_opening_volatility()` in orchestrator. VIX overlay works.

**Data needed:**
- Standard deviation of 1-min bar returns during the first 5 minutes of the session, per asset per day
- Historical: 60 trading days for z-score baseline
- This is COMPUTABLE from data we already have — the QC OR volume extract includes 1-min OHLCV bars for the OR window

**Daily retrieval mechanism needed:**
1. At OR close (after first m minutes): compute std_dev of 1-min returns from the live TopstepX stream bars received during the OR window
2. Store in a persistent table or append to P3-D30
3. Wire `_get_recent_5min_vol()` and `_get_trailing_open_vol()` to read from store
4. Self-sustaining from day 1 via TopstepX live stream data

**Impact while inactive:** On high-volatility opens (e.g., gap days, CPI release mornings), the first 5 minutes see 3-5x normal price movement — stop-loss orders fill at much worse levels. AIM-12 should detect this via vol_z and reduce sizing by 5-15%, but currently only detects wide spreads. Since the OR logic uses OR, the spread_z signal alone catches some high-cost situations, but misses volatility-specific events where spreads are normal but price is whipping. **This is the easiest gap to fill** since the data comes from TopstepX live stream — no external source needed.

---

### AIM-04/11: VIX/VXV Daily Refresh (maintenance gap)

**What it does:**
- **AIM-04 (IVTS):** VIX/VXV ratio determines the volatility term structure regime — the single most critical regime filter in the system. The [0.93, 1.0] optimal zone (Paper 67 validated) is where ORB breakouts have the highest edge.
- **AIM-11 (Regime Warning):** VIX z-score (252-day trailing) flags stress regime probability — high VIX z means elevated transition probability to crisis.

**Current state:** WORKING + AUTO-REFRESHED. VIX CSV updated to 2026-04-01 (24.76) via `scripts/update_vix_daily.py`. Auto-runs on every system startup via `captain-start.sh`. `vix_provider.py` detects CSV mtime changes and reloads automatically.

**Data needed:**
- VIX daily close (CBOE Volatility Index)
- VXV/VIX3M daily close (CBOE 3-Month Volatility Index)
- One row per trading day, appended to `data/vix/vix_daily_close.csv` and `data/vix/vxv_daily_close.csv`

**Daily retrieval mechanism needed:**
1. After 16:15 ET daily: fetch VIX and VIX3M closing values
2. Append one row to each CSV: `{date},{close}`
3. `vix_provider.py` re-reads CSVs on next startup (or implement hot-reload)
4. Sources: Yahoo Finance (`^VIX`, `^VIX3M`) — free, no API key needed. FRED (`VIXCLS`) — free. CBOE direct download.
5. Implementation: a cron job or pre-session startup script that runs `curl` + `awk` to append the day's value

**Impact if not maintained:** AIM-04 and AIM-11 together account for approximately 30-40% of the total AIM modifier influence (both are Tier 1 with weekly retrain). If VIX data goes stale:
- AIM-04 IVTS ratio becomes frozen — the system won't detect regime transitions between contango and backwardation
- AIM-11 VIX z-score drifts — a VIX spike to 35 wouldn't register as elevated if the baseline is months old
- The overnight return z-score overlay (AIM-04) continues working since it uses P3-D30 OHLCV data, but the primary IVTS zone classification becomes unreliable
- **This is the highest-priority maintenance item** since AIM-04 and AIM-11 are otherwise fully functional

---

### AIM-11: CL Basis Overlay (minor gap)

**What it does:** An overlay within AIM-11 that fires only for CL (crude oil). When the front-month/back-month futures spread is in backwardation (basis < -0.02) AND VIX is elevated (VIX_z > 0.5), it indicates persistent commodity stress — sizing for CL is reduced by an additional ×0.90.

**Current state:** Overlay never fires — `_get_cl_front_futures()` and `_get_cl_back_futures()` return None.

**Data needed:**
- CL front-month and first-deferred-month daily settlement prices
- One pair of values per trading day

**Source:** TopstepX provides CL contract data, but we'd need both the front and back month contract IDs resolved simultaneously. Alternatively, CME group publishes settlement prices daily.

**Impact while inactive:** Only affects CL. The primary AIM-11 VIX z-score and VIX change overlay still work for all assets. The CL basis overlay is a refinement that would catch commodity-specific stress signals (like the 2022 oil backwardation episode). CL is not currently in the active universe (the 10 traded assets are equity indices, bonds, and gold), so this gap has **zero current impact**.

---

## Summary: System Impact While Gaps Persist

| AIM | Status | Modifier Output | Impact on Signal Quality |
|-----|--------|----------------|--------------------------|
| AIM-01 VRP | **ACTIVE (ES only)** | IV-RV z-score for ES | ES gets VRP adjustment; other 9 assets still 1.0 (no IV/RV data). |
| AIM-02 Skew | **PARTIAL (ES skew half)** | 0.4 × skew_z for ES | ES gets skew-based fear/greed read at reduced confidence (0.4 vs 0.7). PCR half still missing. |
| AIM-03 GEX | INACTIVE | Always 1.0 | No gamma regime awareness. Most impactful gap for ORB strategy. |
| AIM-07 COT | INACTIVE | Always 1.0 | No institutional flow signal. Misses crowded/contrarian setups. |
| AIM-12 vol_z | **FULL (spread_z + vol_z)** | Both signals active | Full OR-logic cost detection: spread spikes OR volatility spikes trigger sizing reduction. |
| AIM-04/11 VIX | **AUTO-REFRESHED** | Current VIX/VXV data | Daily auto-update via Yahoo Finance on system startup. No longer stale. |
| AIM-11 CL basis | INACTIVE (overlay) | VIX z-score still works | Zero impact — CL not in active universe. |

**Net effect:** The combined_modifier now reflects 10 of 12 active AIMs: AIM-01 (VRP, ES only), AIM-02 (skew half, ES only), AIM-04 (IVTS zones), AIM-06 (calendar), AIM-08 (correlation), AIM-09 (momentum), AIM-10 (OPEX), AIM-11 (VIX z-score + spike), AIM-12 (spread_z + vol_z), and AIM-15 (volume). Only AIM-03 (GEX) and AIM-07 (COT) remain inactive — both blocked on external data sources (options chain / CFTC report).

---

## Priority Actions

| Priority | Action | AIMs Unlocked | Effort | Status |
|----------|--------|---------------|--------|--------|
| ~~1~~ | ~~Wire OHLCV data → QuestDB table + update stubs~~ | ~~AIM-08, AIM-09, overnight returns~~ | ~~Medium~~ | **DONE** (2026-04-01) |
| ~~2~~ | ~~VIX/VXV daily auto-update (Yahoo Finance + captain-start.sh)~~ | ~~AIM-04, AIM-11 longevity~~ | ~~Small~~ | **DONE** (2026-04-01) |
| ~~3~~ | ~~Wire ES IV/RV data → b1_features stubs~~ | ~~AIM-01 (ES only)~~ | ~~Small~~ | **DONE** (2026-04-01, ES only, no daily refresh) |
| ~~4~~ | ~~Wire ES skew data → b1_features stub~~ | ~~AIM-02 (skew half)~~ | ~~Small~~ | **DONE** (2026-04-01, ES skew half only) |
| ~~5~~ | ~~Compute vol_z from TopstepX live 1-min bars~~ | ~~AIM-12 (vol_z half)~~ | ~~Small~~ | **DONE** (2026-04-01, bootstrap + live persistence) |
| 6 | Extract PCR from CBOE daily report | AIM-02 (PCR half) | Medium — daily scrape + store | BLOCKED on source |
| 7 | Extract COT from CFTC/Quandl | AIM-07 | Medium — weekly pipeline | BLOCKED on source |
| 8 | Compute GEX from options chain | AIM-03 | Hard — needs full chain + Greeks | BLOCKED on source |

---

## Data File Locations

| File | Path | Format |
|------|------|--------|
| OR volumes (per asset) | `captain-system-data-extracts/or_volume_data/{ASSET}_or_volume.csv` | datetime_et, OHLCV, is_or |
| OHLCV daily (per asset) | `captain-system-data-extracts/aim_data/ohlcv_{ASSET}.csv` | date, OHLCV |
| OHLCV daily (combined) | `captain-system-data-extracts/aim_data/ohlcv_combined.csv` | asset, date, OHLCV |
| VIX daily | `captain-system-data-extracts/aim_data/vix_daily.csv` | date, close |
| VXV daily | `captain-system-data-extracts/aim_data/vxv_daily.csv` | date, close |
| ES IV/RV | `captain-system-data-extracts/aim_data/es_iv_rv.csv` | date, atm_iv_30d, realized_vol_20d |
| ES Skew | `captain-system-data-extracts/aim_data/es_skew.csv` | date, cboe_skew, skew_spread_proxy |
| Bundled VIX | `data/vix/vix_daily_close.csv` | date, vix_close (9156 rows, 1990-2026, auto-updated) |
| Bundled VXV | `data/vix/vxv_daily_close.csv` | date, vxv_close (4159 rows, 2007-2026, auto-updated) |

### QuestDB Tables Added (2026-04-01)

| Table | Source | Rows | Purpose |
|-------|--------|------|---------|
| `p3_d31_implied_vol` | ES IV/RV extract | 122 | AIM-01 VRP (ES only) |
| `p3_d32_options_skew` | ES SKEW extract | 81 | AIM-02 skew half (ES only) |
| `p3_d33_opening_volatility` | QC OR bars + live | ~240 | AIM-12 vol_z (all 10 assets) |
