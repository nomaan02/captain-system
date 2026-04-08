# Session Replay Function Map

**Generated:** 2026-04-06
**Purpose:** Factual audit of what the session replay engine actually computes — code as read, not as intended.
**Files audited:**

Backend:
- `captain-command/captain_command/api.py` (lines 587–816)
- `captain-command/captain_command/blocks/b11_replay_runner.py` (717 lines)
- `shared/replay_engine.py` (1944 lines)
- `shared/aim_compute.py` (649 lines)
- `shared/aim_feature_loader.py` (409 lines)
- `scripts/replay_full_pipeline.py` (616 lines)

Frontend:
- `captain-gui/src/pages/ReplayPage.jsx` (193 lines)
- `captain-gui/src/stores/replayStore.js` (254 lines)
- `captain-gui/src/components/replay/ReplayConfigPanel.jsx` (411 lines)
- `captain-gui/src/components/replay/BlockDetail.jsx` (312 lines)
- `captain-gui/src/components/replay/ReplaySummary.jsx` (213 lines)
- `captain-gui/src/components/replay/BatchPnlReport.jsx` (252 lines)
- `captain-gui/src/components/replay/PipelineStepper.jsx` (126 lines)
- `captain-gui/src/components/replay/PlaybackControls.jsx` (141 lines)
- `captain-gui/src/components/replay/WhatIfComparison.jsx` (126 lines)
- `captain-gui/src/components/replay/AssetCard.jsx` (153 lines)
- `captain-gui/src/components/replay/ReplayHistory.jsx` (70 lines)
- `captain-gui/src/components/replay/SimulatedPosition.jsx` (71 lines)
- `captain-gui/src/ws/useWebSocket.js` (184 lines)
- `captain-gui/src/api/client.js` (87 lines)

---

## 1. Entry Points

There are **two independent replay systems** in this codebase:

### 1A. GUI Replay (api.py + b11 + replay_engine.py)

The GUI replay system is accessed via REST endpoints served by captain-command (FastAPI on :8000). All endpoints hardcode `user_id="primary_user"`.

| Endpoint | Method | Pydantic Model | Description |
|----------|--------|----------------|-------------|
| `/api/replay/start` | POST | `ReplayStartRequest` | Start single-day replay, returns `replay_id` |
| `/api/replay/batch/start` | POST | `BatchReplayStartRequest` | Start multi-day batch replay |
| `/api/replay/control` | POST | `ReplayControlRequest` | Pause/resume/speed/skip/stop |
| `/api/replay/save` | POST | `ReplaySaveRequest` | Save results to `p3_replay_results` |
| `/api/replay/status` | GET | — | Get active replay status |
| `/api/replay/history` | GET | — | List saved results (limit 50) from `p3_replay_results` |
| `/api/replay/presets` | GET | — | List saved presets from `p3_replay_presets` |
| `/api/replay/presets` | POST | `ReplayPresetRequest` | Save a config preset |
| `/api/replay/whatif` | POST | `ReplayStartRequest` | Rerun with different config using cached bars |

**Request models (api.py:591–620):**

```python
class ReplayStartRequest:
    date: str                          # YYYY-MM-DD
    sessions: list[str] | None = None  # e.g. ["NY", "LONDON"]
    session: str | None = None         # backward compat, single session
    config_overrides: dict = {}        # any key from config dict
    speed: float = 1.0                 # playback speed multiplier

    # resolved_sessions property: sessions ?? [session] ?? ["NY"]

class BatchReplayStartRequest:
    date_from: str
    date_to: str
    sessions: list[str] = ["NY"]
    config_overrides: dict = {}
    speed: float = 1.0

class ReplayControlRequest:
    action: str   # "pause" | "resume" | "speed" | "skip_to_next" | "stop"
    value: float | None = None  # only for "speed" action

class ReplaySaveRequest:
    replay_id: str
    user_id: str = "primary_user"

class ReplayPresetRequest:
    name: str
    config: dict
    user_id: str = "primary_user"
```

**WebSocket events emitted during replay (b11_replay_runner.py:124–138):**

All events pushed via `gui_push(user_id, {...})` with `type: "replay_tick"`:

| Event Type | When Fired | Key Data Fields |
|------------|------------|-----------------|
| `config_loaded` | After config assembled | user_capital, max_contracts, max_positions, budget_divisor, risk_goal, mdd_limit, mll_limit, cb_enabled, aim_enabled, strategies_count, kelly_count, ewma_count, target_date |
| `auth_complete` | After TopstepX auth | contracts_resolved |
| `aim_scored` | After AIM aggregation (if enabled) | combined_modifier, aim_breakdown, aim_debug |
| `asset_bars_fetched` | Per asset after bar fetch | asset, bar_count, session |
| `or_computed` | Per asset after OR window | asset, or_high, or_low, or_range, or_bars |
| `breakout` | Per asset on breakout | asset, direction, direction_str, entry_price, breakout_time, tp_level, sl_level |
| `exit` | Per asset after exit sim | asset, exit_price, exit_reason, exit_time, pnl_per_contract, pnl_points |
| `sizing_complete` | Per asset after Kelly | asset, aim_modifier, contracts, kelly_blended, kelly_shrunk, kelly_adjusted, risk_per_contract, raw_contracts, mdd_cap, daily_cap, max_contracts, budget_divisor, remaining_mdd, daily_budget, fallback_risk, risk_goal, cb_l1_halt, cb_rho_j, cb_blocked, cb_enabled, binding_constraint |
| `quality_gate_applied` | After quality gate (B5B) | results (list: asset, quality_score, quality_gate_passed, data_maturity, quality_multiplier) |
| `position_limit_applied` | After ranking | selected (list), excluded (list), max_positions |
| `correlation_filter_applied` | After correlation filter (if adjustments made) | adjustments (list: asset, correlated_with, contracts, pre_correlation_contracts) |
| `replay_complete` | Final | summary, all_results |

**Batch-specific events:**
| Event Type | When Fired |
|------------|------------|
| `batch_started` | Start of batch | total_days, dates, sessions |
| `batch_day_started` | Start of each day | date, day_index, total_days |
| `batch_day_completed` | End of each day | date, day_pnl, cumulative_pnl, day_trades, day_wins, day_losses |
| `batch_complete` | End of batch | summary, day_results |

**Playback control (b11_replay_runner.py:67–95):**
- `pause()`: clears `_pause_event` threading.Event
- `resume()`: sets `_pause_event`
- `set_speed(speed)`: clamped to `[0.1, 100.0]`
- `skip_to_next()`: sets `_skip_flag`, also resumes if paused
- `stop()`: sets `_stop_flag`, unblocks pause

Sleep between non-significant events: `0.5 / max(speed, 0.1)` seconds, checked in 0.1s increments.
Significant events (no sleep): `breakout`, `exit`, `error`, `replay_complete`.

### 1B. Full Pipeline Replay (scripts/replay_full_pipeline.py)

A standalone CLI script that runs the **actual live B1→B6 blocks** against historical bars. This is fundamentally different from 1A — it calls the real block functions, not a simplified engine.

```
Usage: PYTHONPATH=.:captain-online:captain-command \
    python scripts/replay_full_pipeline.py --date 2026-03-30 --session NY
```

**Flow:**
1. Fetch 1-min bars from TopstepX for all session assets
2. Run Phase A using **real blocks**: B1 → B2 → B3 → B4 → B5 → B5B → B5C
3. Feed historical bars to an `ORTracker` as synthetic ticks (high, low, close per bar)
4. On OR breakout, run Phase B (B6) — publishes **real signals to Redis**
5. Command process picks up signals → GUI displays them
6. **WARNING: requires AUTO_EXECUTE=false** or real orders will fire

**Key difference from GUI replay:** This script calls the exact same block functions the live orchestrator uses. The GUI replay engine reimplements a simplified version of the pipeline in `shared/replay_engine.py`.

---

## 2. Configuration Loading

### 2.1 load_replay_config() — replay_engine.py:59–263

Called at the start of every GUI replay. Reads QuestDB, assembles config dict, applies overrides.

#### QuestDB Queries (in order):

| Query | Table | Columns | Filter | Dedup | Default if Missing |
|-------|-------|---------|--------|-------|-------------------|
| Locked strategies + specs | `p3_d00_asset_universe` | asset_id, locked_strategy, point_value, tick_size, margin_per_contract | `ORDER BY last_updated DESC` | first occurrence per asset_id | point_value=50.0, tick_size=0.25, margin=0.0 |
| Kelly params | `p3_d12_kelly_parameters` | asset_id, regime, session, kelly_full, shrinkage_factor | `ORDER BY last_updated DESC` | first per (asset_id, regime, session) | kelly_full=0.0, shrinkage_factor=1.0 |
| EWMA states | `p3_d05_ewma_states` | asset_id, regime, session, win_rate, avg_win, avg_loss | `ORDER BY last_updated DESC` | first per (asset_id, regime, session) | win_rate=0.5, avg_win=0.0, avg_loss=0.0 |
| Capital silo | `p3_d16_user_capital_silos` | total_capital, accounts, max_simultaneous_positions | `WHERE user_id = 'primary_user' ORDER BY last_updated DESC LIMIT 1` | single row | capital=150000.0, positions=5 |
| TSM state | `p3_d08_tsm_state` | 11 columns | `WHERE account_id = '20319811' ORDER BY last_updated DESC LIMIT 1` | single row | See defaults below |

**NOTE:** The account_id `'20319811'` is **hardcoded** in the TSM query (replay_engine.py:162). This will break if the account changes.

#### TSM defaults when no row found (replay_engine.py:152–157):
```python
risk_goal = "GROW_CAPITAL"
max_contracts = 15
mdd_limit = 4500.0
mll_limit = 2250.0
current_drawdown = 0.0
daily_loss_used = 0.0
```

#### Contract IDs (replay_engine.py:208–225):
Loaded from first existing file in order:
1. `/app/contract_ids.json`
2. `/captain/config/contract_ids.json`
3. `{project_root}/config/contract_ids.json`

#### Assembled config dict (replay_engine.py:228–251):

```python
config = {
    "user_capital": user_capital,      # from D16, default 150000.0
    "max_contracts": max_contracts,     # from D08, default 15
    "max_positions": max_positions,     # from D16, default 5
    "budget_divisor": 20,              # HARDCODED
    "risk_goal": risk_goal,            # from D08, default "GROW_CAPITAL"
    "cb_enabled": True,                # HARDCODED default
    "tp_multiple": 0.70,               # HARDCODED default
    "sl_multiple": 0.35,               # HARDCODED default
    "mdd_limit": mdd_limit,            # from D08, default 4500.0
    "mll_limit": mll_limit,            # from D08, default 2250.0
    "current_drawdown": current_drawdown,  # from D08, default 0.0
    "daily_loss_used": daily_loss_used,    # from D08, default 0.0
    "strategies": strategies,          # from D00, per-asset dicts
    "specs": specs,                    # from D00 (point_value, tick_size, margin)
    "kelly_params": kelly_params,      # from D12, keyed by (asset, regime, session)
    "ewma_states": ewma_states,        # from D05, keyed by (asset, regime, session)
    "contracts": contracts,            # from contract_ids.json
    "topstep_params": topstep_params if topstep_params else {"c": 0.5, "e": 0.01},
    "session_config": SESSION_CONFIG,  # static dict
    "asset_session_map": ASSET_SESSION_MAP,  # static dict
    "_tsm": tsm,                       # full TSM row dict
}
```

### 2.2 Override mechanism (replay_engine.py:254–262)

User-provided `config_overrides` are applied on top:
- Keys `strategies`, `specs`, `kelly_params`, `ewma_states`: **merged** (`.update()`) into existing dicts
- All other keys: **replaced** wholesale

Additionally, in b11_replay_runner.py:230–235, if `tp_multiple` or `sl_multiple` are in `config_overrides`, they are propagated to **every** asset's strategy dict.

### 2.3 Session configuration (replay_engine.py:35–53)

```python
SESSION_CONFIG = {
    "NY":     {"or_start": "09:30", "or_end": "09:35", "eod": "15:55"},
    "NY_PRE": {"or_start": "06:00", "or_end": "06:05", "eod": "13:25"},
    "LONDON": {"or_start": "03:00", "or_end": "03:05", "eod": "11:25"},
    "APAC":   {"or_start": "18:00", "or_end": "18:05", "eod": "02:55"},
}

ASSET_SESSION_MAP = {
    "ES": "NY", "MES": "NY", "NQ": "NY", "MNQ": "NY",
    "M2K": "NY", "MYM": "NY",
    "NKD": "APAC",
    "MGC": "LONDON",
    "ZB": "NY_PRE", "ZN": "NY_PRE",
}

ACTIVE_ASSETS = ["ES", "MES", "NQ", "MNQ", "M2K", "MYM", "NKD", "MGC", "ZB", "ZN"]
SESSION_ID_MAP = {"NY": 1, "LONDON": 2, "APAC": 3, "NY_PRE": 1}
```

**NOTE:** `SESSION_ID_MAP` maps `"NY_PRE"` to session ID `1` (same as NY). ZB and ZN are assigned to `"NY_PRE"` in `ASSET_SESSION_MAP` but the live orchestrator groups them under NY (session 1) — so Kelly lookups will use session=1 for both, which is consistent.

---

## 3. ORB Simulation

### 3.1 Bar fetching — replay_engine.py:316–431

**`_fetch_bars_from_api(client, contract_id, target_date, session_type)`** (line 316):
- Calls TopstepX `POST /api/History/retrieveBars`
- Payload: `contractId`, `live: False`, `startTime/endTime` (UTC), `unit: 2` (Minute), `unitNumber: 1`, `limit: 1000`
- Fetch window: `(or_start - 5min)` to `(eod + 30min)`, converted from ET to UTC
- APAC special case: start_day is `target_date - 1 day` (session starts evening before)
- Response bars are reversed from newest-first to chronological (oldest-first)

**`fetch_session_bars(client, asset_id, contract_id, target_date, session_type, use_cache=True)`** (line 389):
- Tries `shared.bar_cache.get_cached_bars(asset_id, date_str, session_type)` first
- On cache miss: calls `_fetch_bars_from_api`, then `cache_bars()`
- Cache is SQLite WAL-based (`shared/bar_cache.py`)

### 3.2 Bar parsing — replay_engine.py:270–309

**`parse_bar_time(bar)`** (line 270):
- Tries keys in order: `t`, `timestamp`, `time`, `dateTime`, `barTime`
- Handles ISO string (`"Z"` replaced with `"+00:00"`) and epoch (int/float, >1e12 treated as ms)

**`get_bar_field(bar, field)`** (line 293):
- Maps long names to short: `open→o`, `high→h`, `low→l`, `close→c`, `volume→v`
- Tries multiple key variants

### 3.3 simulate_orb() — replay_engine.py:437–637

**Inputs:** `bars`, `asset_id`, `session_type`, `target_date`, `strategy`, `spec`

**Step 1: Parse bars (line 460–483)**
- Convert each bar to `{time, open, high, low, close}` in naive ET
- If bar has timezone info, convert to `America/New_York` then strip tzinfo

**Step 2: OR window detection (line 498–520)**
- APAC: `or_date = target_date - 1 day`; all others: `or_date = target_date`
- OR bars: all bars where `or_start_dt <= time < or_end_dt`
- `or_high = max(bar.high for bar in or_bars)`
- `or_low = min(bar.low for bar in or_bars)`
- `or_range = or_high - or_low` (must be > 0)

**Step 3: Breakout detection (line 537–566)**
- Scans post-OR bars (`time >= or_end_dt AND time <= eod_dt`)
- First bar where `high > or_high` → LONG breakout, entry = or_high
- First bar where `low < or_low` → SHORT breakout, entry = or_low
- If neither → `result = "NO_BREAKOUT"`, `pnl_per_contract = 0.0`
- **NOTE:** Only the first breakout direction is taken. If both OR levels are breached in the same bar, `high > or_high` is checked first → LONG bias.

**Step 4: TP/SL levels (line 569–573)**
```python
tp_mult = strategy.get("tp_multiple", 2.0)   # default 2.0 if not in strategy
sl_mult = strategy.get("sl_multiple", 1.0)   # default 1.0 if not in strategy

tp_level = entry_price + (tp_mult * or_range * direction)
sl_level = entry_price - (sl_mult * or_range * direction)
```

**NOTE on defaults:** The `strategy` dict comes from the locked_strategy JSON in D00. These defaults (2.0, 1.0) are only used if the strategy dict has no `tp_multiple`/`sl_multiple` keys. However, the replay config assembles a top-level `tp_multiple=0.70` and `sl_multiple=0.35` which gets propagated to strategy dicts via b11 (line 231–235). So in practice, values will be 0.70/0.35 unless the D00 locked_strategy already contains them.

**Step 5: Exit simulation (line 579–610)**
- Iterates post-OR bars after breakout_time
- For LONG: SL hit if `bar.low <= sl_level`; TP hit if `bar.high >= tp_level`
- For SHORT: SL hit if `bar.high >= sl_level`; TP hit if `bar.low <= tp_level`
- **SL checked before TP within each bar** (pessimistic assumption)
- If neither TP nor SL hit by EOD: `exit_price = last_post_or_bar.close`, reason = "EOD"

**Step 6: PnL calculation (line 611–613)**
```python
pnl_per_contract = (exit_price - entry_price) * direction
point_value = spec.get("point_value", 50.0)
pnl_dollars = pnl_per_contract * point_value
```

---

## 4. Kelly Sizing (compute_contracts)

### compute_contracts() — replay_engine.py:644–807

**Function signature:** `compute_contracts(asset_id, pnl_per_contract, spec, kelly_params, ewma_states, config, strategy, session_id=1, aim_modifier=1.0)`

10 steps, documented with actual formulas:

#### Step 1: Regime-blended Kelly (line ~730)
```python
# Reads regime_probs from config (computed by _compute_regime_probs before sizing loop)
regime_probs = config["regime_probs"][asset_id]  # e.g. {LOW_VOL: 0.5, HIGH_VOL: 0.5}
blended = regime_probs["LOW_VOL"] * low_kelly + regime_probs["HIGH_VOL"] * high_kelly
```
**FIXED (P0-1, 2026-04-06):** Now uses actual regime probabilities from `_compute_regime_probs()`, which ports live B2 logic: REGIME_NEUTRAL → 0.5/0.5, BINARY_ONLY with pettersson_threshold → realised vol vs phi, locked regime_label fallback. Returns `regime_uncertain` flag (max_prob < 0.6) per spec PG-22.

#### Step 2: Shrinkage (line 685–686)
```python
adjusted = blended * shrinkage  # shrinkage_factor from D12, default 1.0
```

#### Step 3: AIM modifier (line 688–690)
```python
kelly_with_aim = adjusted * aim_modifier  # passed in from AIM aggregation
```

#### Step 4: Risk goal scaling (line 692–698)
```python
if risk_goal == "PASS_EVAL":      kelly_with_aim *= 0.7
elif risk_goal == "PRESERVE_CAPITAL": kelly_with_aim *= 0.5
# "GROW_CAPITAL" → no scaling (×1.0)
```

#### Step 5: Risk per contract from EWMA (line 700–716)
- First tries to find `avg_loss` matching `(asset_id, *, session_id)`
- Falls back to any session for the same asset
- Final fallback: `sl_dist * point_value` where `sl_dist = strategy.get("threshold", 4.0)`

**NOTE:** `strategy.get("threshold", 4.0)` — the `threshold` key comes from the locked_strategy JSON. Default 4.0 is a fallback for the OR range in points. This `fallback_risk` is also used in MDD budget and daily loss cap calculations.

#### Step 6: Raw contracts (line 718–722)
```python
raw = kelly_with_aim * user_capital / risk_per_contract
```

#### Step 7: MDD budget cap (line 724–733)
```python
remaining_mdd = max_drawdown_limit - current_drawdown
daily_budget = remaining_mdd / budget_divisor   # budget_divisor default = 20
mdd_cap = floor(daily_budget / fallback_risk)
```

**What `budget_divisor` means:** It divides the remaining MDD headroom into N equal "daily budgets". With MDD=$4500 and no drawdown, each daily budget = $4500/20 = $225. This limits how many contracts can be risked per day relative to remaining MDD capacity.

#### Step 8: Daily loss cap — MLL (line 735–746)
```python
remaining_daily = max_daily_loss - daily_loss_used
daily_cap = floor(remaining_daily / fallback_risk)
```

#### Step 9: 4-way minimum (line 748–751)
```python
final = min(floor(raw), mdd_cap, daily_cap, max_contracts)
final = max(final, 0)
```

#### Step 10: Circuit breaker L1 preemptive halt (line 767–783)
```python
c = topstep_params.get("c", 0.5)
e = topstep_params.get("e", 0.01)
l_halt = c * e * user_capital    # default: 0.5 × 0.01 × 150000 = $750
rho_j = final * fallback_risk

if cb_enabled and rho_j >= l_halt and final > 0:
    # Reduce contracts until rho_j < l_halt
    while final > 0 and (final * fallback_risk) >= l_halt:
        final -= 1
```

**NOTE:** This is **only CB Layer 1**. The live pipeline has 5 layers (L0-L4). Layers L0 (XFA scaling), L2 (budget check using P3-D23 intraday state), L3 (beta_b expectancy from P3-D25), and L4 (correlation Sharpe) are **not implemented** in the replay engine.

---

## 5. AIM Computation

### 5.1 Feature loading — aim_feature_loader.py

**`load_replay_features(target_date, assets)`** (line 29) returns `(features, aim_states, aim_weights)`.

#### Data sources per feature:

| Feature | Source Table/File | Query Details | Used By |
|---------|------------------|---------------|---------|
| `vix_z` | VIX CSV via `vix_provider` | 252-day trailing z-score of VIX close | AIM-11 |
| `vix_daily_change_z` | VIX CSV | z-score of abs(daily VIX change) over 60 days | AIM-11 |
| `ivts` | VIX + VXV CSVs | `latest_vix / latest_vxv` | AIM-04 |
| `overnight_return_z` | `p3_d30_daily_ohlcv` | z-score of `(today_open - yesterday_close)/yesterday_close`, 30 rows trailing | AIM-04 |
| `cross_momentum` | `p3_d30_daily_ohlcv` | Sign alignment of 5-day vs 20-day returns: +1.0, -1.0, or 0.0 | AIM-09 |
| `correlation_z` | `p3_d30_daily_ohlcv` | Pearson correlation of asset vs ES over 20-day returns (ES gets 0.0) | AIM-08 |
| `vrp_overnight_z` | `p3_d31_implied_vol` | z-score of (IV - RV), 30 rows. **ES only** | AIM-01 |
| `skew_z` | `p3_d32_options_skew` | z-score of CBOE skew, 30 rows. **ES only** | AIM-02 |
| `pcr_z` | — | **NOT LOADED** (no PCR data source). Comment: "pcr_z not available" | AIM-02 |
| `vol_z` | `p3_d33_opening_volatility` | z-score of opening_range_pct, 30 rows | AIM-12 |
| `opening_volume_ratio` | `p3_d29_opening_volumes` | today's volume / avg of prior volumes (min 2 rows needed) | AIM-15 |
| `day_of_week` | Pure date computation | `target_date.weekday()` (0=Monday) | AIM-01 |
| `is_opex_window` | Pure date computation | True if within ±3 calendar days of 3rd Friday | AIM-10 |
| `is_eia_wednesday` | Pure date computation | True if Wednesday AND asset == "CL" (not in universe) | AIM-04 |
| `event_proximity` | — | **NOT LOADED** (no calendar feed). Returns None → AIM-06 neutral | AIM-06 |
| `events_today` | — | **NOT LOADED**. Returns None → AIM-06 neutral | AIM-06 |
| `gex` | — | **NOT LOADED** (no GEX data source). Returns None → AIM-03 neutral | AIM-03 |
| `cot_smi` | — | **NOT LOADED** (no COT data source). Returns None → AIM-07 neutral | AIM-07 |
| `cot_speculator_z` | — | **NOT LOADED**. Returns None → AIM-07 neutral | AIM-07 |
| `spread_z` | — | **NOT LOADED** (no spread data). AIM-12 falls back to vol_z only | AIM-12 |
| `cl_basis` | — | **NOT LOADED** (CL not in universe). AIM-11 overlay inactive | AIM-11 |

#### AIM state/weight loading (aim_feature_loader.py:320–378):

| Table | Query | Dedup | Key Fields |
|-------|-------|-------|------------|
| `p3_d01_aim_model_states` | `SELECT aim_id, asset_id, status, current_modifier, warmup_progress ORDER BY last_updated DESC` | First per `(asset_id, aim_id)` | status, current_modifier (JSON), warmup_progress |
| `p3_d02_aim_meta_weights` | `SELECT aim_id, asset_id, inclusion_probability, inclusion_flag, recent_effectiveness, days_below_threshold ORDER BY last_updated DESC` | First per `(asset_id, aim_id)` | inclusion_probability (default 1.0), inclusion_flag (default True) |

### 5.2 Individual AIM models — aim_compute.py

15 handlers registered (AIM-05 DEFERRED, AIM-16 removed from B3 dispatch per DEC-06):

| AIM | Handler | Feature(s) | Thresholds → Modifier | Data Available in Replay? |
|-----|---------|-----------|----------------------|--------------------------|
| **01** VRP | `_aim01_vrp` (line 227) | `vrp_overnight_z`, `day_of_week` | z>1.5→0.70, z>0.5→0.85, z<-1.0→1.10, else→1.00; Monday: ×0.95 | ES only (p3_d31). All others → MISSING → 1.0 |
| **02** Skew | `_aim02_skew` (line 268) | `pcr_z`, `skew_z` | combined=0.6×pcr_z+0.4×skew_z; >1.5→0.75, >0.5→0.90, <-1.0→1.10 | Partial: skew_z for ES only. pcr_z never loaded → single-signal degraded mode (confidence=0.4) |
| **03** GEX | `_aim03_gex` (line 306) | `gex` | gex>0→0.90, gex<0→1.10 | **No** — always MISSING → 1.0 |
| **04** IVTS | `_aim04_ivts` (line 319) | `ivts`, `overnight_return_z`, `is_eia_wednesday` | 5-zone: >1.10→0.65, >1.0→0.80, ≥0.93→1.10, ≥0.85→0.90, <0.85→0.80; overnight gap overlay; EIA overlay | **Yes** for ivts (VIX/VXV). overnight_return_z for assets with OHLCV. EIA never triggers (CL not in universe) |
| **06** Calendar | `_aim06_calendar` (line 380) | `event_proximity`, `events_today` | Tier1 ±30min→0.70, Tier1 later→1.05, Tier2 ±30min→0.85 | **No** — no calendar feed → always neutral 1.0 |
| **07** COT | `_aim07_cot` (line 413) | `cot_smi`, `cot_speculator_z` | SMI +1→1.05, -1→0.90; spec_z>1.5→×0.95, spec_z<-1.5→×1.10 | **No** — always MISSING → 1.0 |
| **08** Correlation | `_aim08_correlation` (line 453) | `correlation_z` | z>1.5→0.80, z>0.5→0.90, z<-0.5→1.05 | **Yes** for all assets with OHLCV data (uses raw Pearson, not z-scored rolling correlations) |
| **09** Momentum | `_aim09_momentum` (line 477) | `cross_momentum` | >0.5→1.10, <-0.5→0.90 | **Yes** for assets with ≥20 days OHLCV |
| **10** Calendar FX | `_aim10_calendar_effects` (line 493) | `is_opex_window` | OPEX→0.95, else→1.0. (DOW effects removed per DEC-04) | **Yes** — pure date computation |
| **11** Regime Warning | `_aim11_regime_warning` (line 507) | `vix_z`, `vix_daily_change_z`, `cl_basis` | vix_z>1.5→0.75, >0.5→0.90, <-0.5→1.05; change_z>2.0→×0.85; CL basis overlay | **Partial**: vix_z and vix_daily_change_z available. CL basis never triggers |
| **12** Costs | `_aim12_costs` (line 553) | `spread_z`, `vol_z`, `vix_z` | spread_z>1.5 OR vol_z>1.5→0.85; >0.5→0.95; both<-0.5→1.05; vix_z>1.0→×0.95 | **Partial**: vol_z from D33. spread_z not loaded → defaults to 0.0 |
| **13** Sensitivity | `_aim13_sensitivity` (line 596) | `state.current_modifier` | From Offline B5 result stored in AIM state JSON | **Yes** if Offline has run and stored results |
| **14** Expansion | `_aim14_expansion` (line 608) | — | Always 1.0 | Always available |
| **15** Volume | `_aim15_volume` (line 613) | `opening_volume_ratio` | ratio>1.5→1.15, >1.0→1.05, <0.7→0.80 | **Partial**: needs ≥2 rows in D29 |

### 5.3 MoE aggregation — aim_compute.py:109–178

For each asset:
1. Loop AIM-01 through AIM-16
2. Skip if: no state in D01, status != "ACTIVE", no weight in D02, `inclusion_flag == False`
3. Compute modifier via dispatch handler, clamp to `[0.5, 1.5]`
4. **Weighted average** (not product):
```python
total_weight = sum(dma_weight for all active AIMs)
weighted_sum = sum(modifier × (dma_weight / total_weight))
combined_modifier = clamp(weighted_sum, 0.5, 1.5)
```
5. If no active AIMs → combined_modifier = 1.0 (neutral)

**NOTE:** This is a **weighted average**, not a product. The live B3 uses the same `shared/aim_compute.py`, so this is consistent. But the spec says `mod = Product(m_a^w_a)` (PG-23). This is a known discrepancy between code and spec.

### 5.4 How AIM modifier is applied

In `run_replay()` (replay_engine.py:941–983):
- AIM aggregation only runs if `config.get("aim_enabled", False)` is True
- Default is **False** — AIM is opt-in for GUI replay
- The combined modifier per asset is passed to `compute_contracts()` as `aim_modifier`
- Applied at Kelly Step 3: `kelly_with_aim = adjusted * aim_modifier`

---

## 6. Position Limit & Edge Ranking

### apply_position_limit() — replay_engine.py:~934

**Inputs:** `results` (all assets), `max_positions` (from config, default 5), `config` (for EWMA and regime data)

**Step 1: Filter eligible trades**
```python
eligible = [r for r in results if direction != 0 and contracts > 0]
```

**Step 2: Compute and rank by expected edge**
```python
# _expected_edge() ports live B5 (b5_trade_selection.py:51-61):
#   1. Get dominant regime from regime_probs
#   2. Look up EWMA for (asset, dominant_regime, session_id)
#   3. edge = wr * avg_win - (1 - wr) * avg_loss
eligible.sort(key=lambda x: x["expected_edge"], reverse=True)
```

**FIXED (P0-2, 2026-04-06):** Now uses forward-looking expected edge matching live B5, instead of realised PnL. The `expected_edge` value is attached to each result dict for downstream display. Falls back gracefully if config is not provided.

**Step 3: Take top N**
- If `len(eligible) <= max_positions`: all selected
- Otherwise: top N selected, rest excluded with `excluded_reason = f"Position limit ({max_positions})"`

---

## 6A. Quality Gate (B5B) — ADDED 2026-04-06

### _apply_quality_gate() — replay_engine.py

**Port of:** `b5b_quality_gate.py:49-67`

**Called:** After sizing, before position limit (in both `run_replay()` and `run_whatif()`)

**Inputs per result:**
- `expected_edge` — pre-computed by `_expected_edge()` after sizing
- `aim_modifier` — from AIM aggregation (default 1.0)
- `trade_count` — from D03 `p3_d03_trade_outcome_log` per asset (loaded in `load_replay_config()`)

**Formula:**
```python
data_maturity = min(1.0, max(0.5, trade_count / 50.0))  # cold-start floor 0.5
quality_score = abs(expected_edge) * aim_modifier * data_maturity
```

**Gate logic:**
- `quality_score < hard_floor` (default 0.003): contracts zeroed, `quality_gate_passed = False`
- `quality_score >= hard_floor`: `quality_multiplier = min(1.0, quality_score / quality_ceiling)` (default ceiling 0.010), contracts scaled down

**Config parameters:**
- `quality_gate_enabled` (default `True`) — master toggle
- `quality_hard_floor` (default `0.003`) — minimum quality score
- `quality_ceiling` (default `0.010`) — full-size threshold

**WebSocket event:** `quality_gate_applied` — emitted after gate with per-asset quality_score, data_maturity, quality_gate_passed

---

## 6B. Cross-Asset Correlation Filter — ADDED 2026-04-06

### _apply_correlation_filter() — replay_engine.py

**Port of:** `b5_trade_selection.py:70-89`

**Called:** After position limit, on selected trades (in both `run_replay()` and `run_whatif()`)

**Logic:** For each pair of selected trades, if their correlation exceeds threshold (default 0.7), the asset with the lower `expected_edge` gets its contracts halved (`// 2`).

**Data source:** D07 `p3_d07_correlation_model_states` (loaded in `load_replay_config()`). Falls back to known high-correlation pairs if D07 not populated:
- ES/MES: 0.99
- NQ/MNQ: 0.99
- ZB/ZN: 0.85

**Config parameters:**
- `correlation_filter_enabled` (default `True`) — master toggle
- `correlation_threshold` (default `0.7`) — minimum correlation to trigger reduction

**Fields added to result:**
- `correlation_reduced` (bool) — whether contracts were halved
- `correlated_with` (str) — the asset it's correlated with
- `pre_correlation_contracts` (int) — contracts before halving

**WebSocket event:** `correlation_filter_applied` — emitted when any adjustments made

---

## 6C. Portfolio Risk Cap (B4 Step 7) — ADDED 2026-04-06

### _apply_portfolio_risk_cap() — replay_engine.py

**Port of:** `b4_kelly_sizing.py:236-247`

**Called:** After correlation filter, on selected trades (in both `run_replay()` and `run_whatif()`)

**Logic:** Compute total portfolio risk as `Σ(contracts × SL_distance × point_value)`. If exceeds `max_portfolio_risk_pct × user_capital`, scale all contracts down proportionally.

**Config parameters:**
- `portfolio_risk_cap_enabled` (default `True`) — master toggle
- `max_portfolio_risk_pct` (default `0.10`) — maximum portfolio risk as fraction of capital

**Fields added to result:**
- `portfolio_risk_scaled` (bool) — whether contracts were scaled down
- `portfolio_scale_factor` (float) — the scale factor applied

**WebSocket event:** `portfolio_risk_cap_applied` — emitted when any scaling occurs

---

## 6D. Robust Kelly (Paper 218) — ADDED 2026-04-06

### _get_return_bounds() and _compute_robust_kelly() — replay_engine.py

**Port of:** `b1_features.py:450-480`

**Called:** Inside `compute_contracts()` Step 3, when `regime_uncertain=True` (max regime prob < 0.6)

**Formula:**
```python
mu = avg_win * wr - avg_loss * (1 - wr)
variance = avg_win² * wr + avg_loss² * (1 - wr) - mu²
sigma = sqrt(max(0, variance))
bounds = (mu - 1.5 * sigma, mu + 1.5 * sigma)
robust_f = lower / (upper * lower)  # min-max
```
If `lower <= 0`: conservative fallback `0.3 × standard_kelly`. Capped at 0.5.

**Integration:** `adjusted = min(adjusted, robust_kelly)` — the robust Kelly acts as a protective cap.

**Field added to sizing output:** `robust_kelly_applied` (bool)

---

## 6E. CB L2/L3 and Intraday State Tracking — ADDED 2026-04-06

### Intraday state accumulators

Initialized before the per-asset loop in both `run_replay()` and `run_whatif()`:
- `config["_intraday_cumulative_pnl"]` = 0.0 — L_t for CB L1
- `config["_intraday_trade_count"]` = 0 — n_t for CB L2
- `config["_intraday_basket_pnl"]` = {} — L_b per model_m for CB L3

Updated after each asset's sizing produces non-zero contracts.

### CB L1 (Step 11) — Fixed
- Now uses `abs(L_t) + rho_j >= c * e * A` with fee-inclusive rho_j
- L_t reflects cumulative PnL from prior trades in same replay day

### CB L2 — Budget Exhaustion (Step 12)
**Port of:** `b5c_circuit_breaker.py:292-321`
- `N = floor((e * A) / (MDD * p + phi))` — max trades per day
- Blocks when `n_t >= N`
- At defaults (A=150k, p=0.005, e=0.01, phi=2.80): N=59

### CB L3 — Basket Expectancy (Step 13)
**Port of:** `b5c_circuit_breaker.py:324-368`
- Loads D25 params: `r_bar`, `beta_b`, `sigma`, `rho_bar`, `n_observations`, `p_value`
- `mu_b = r_bar + beta_b * L_b`
- Blocks when `mu_b <= 0` and `beta_b > 0`
- Significance gate: `p > 0.05` or `n < 100` → `beta_b = 0` (effectively disabled)
- Cold-start (`n_observations=0`): skip entirely (no-op, matches live)

**Sizing output fields:** `cb_l1_l_t`, `cb_l2_blocked`, `cb_l2_N`, `cb_l2_n_t`, `cb_l3_blocked`, `cb_l3_mu_b`

---

## 6F. Phase 4 Polish — ADDED 2026-04-06

### User Kelly Ceiling (Step 5)
- **Location:** `compute_contracts()` Step 5, after AIM modifier
- `kelly_with_aim = min(kelly_with_aim, user_kelly_ceiling)`
- Default ceiling: 0.25, configurable via `user_kelly_ceiling` config key
- **Output field:** `user_kelly_ceiling`

### Fee in risk_per_contract (Step 7b)
- **Location:** `compute_contracts()` Step 7b, after avg_loss lookup
- `risk_per_contract += expected_fee` where `expected_fee = _tsm.fee_per_trade` (default $2.80)
- Affects raw contract computation — slightly reduces raw count (~2-3%)

### CB L0 Scaling Cap (Step 11b)
- **Location:** `compute_contracts()` Step 11b, before L1
- Checks `_tsm.scaling_plan_active` (XFA accounts only)
- Caps `final` to `scaling_tier_micros - current_open_micros`
- No-op for non-XFA accounts (current system state)
- **Output field:** `cb_l0_blocked`

### CB L4 Conditional Sharpe (Step 15)
- **Location:** `compute_contracts()` Step 15, after L3
- Reuses `bp`, `n_obs`, `mu_b` from L3 scope
- `S = mu_b / (sigma * sqrt(1 + 2*n_t*rho_bar))`
- Blocks when `S <= lambda` (from topstep_params, default 0)
- Requires `n_obs >= 100` (cold-start: disabled)
- **Output field:** `cb_l4_blocked`

### Dynamic account_id
- **Location:** `load_replay_config()`, D16 accounts parsing
- Extracts first account from D16 `accounts` JSON list
- Fallback to `'20319811'` if not available
- Used in D08 TSM query (parameterized, no longer hardcoded)

### ORB Simultaneous Breach Tiebreaker
- **Location:** `simulate_orb()`, breakout detection loop
- When both `high > or_high` AND `low < or_low` in same bar:
  - Computes `high_pen = high - or_high` and `low_pen = or_low - low`
  - Greater penetration wins (matching live ORTracker logic)
- Previous behavior: always picked LONG on simultaneous breach

### HMM Session Allocation
- **Function:** `_apply_hmm_session_weight(results, config)`
- **Data source:** D26 `p3_d26_hmm_opportunity_state.hmm_params` (loaded in `load_replay_config()`)
- Cold-start (`n_observations < 20`): returns results unchanged (no-op)
- Warm state: applies `session_weights[session_type]` with 5% floor
- Applied after portfolio risk cap, before final summary
- Both `run_replay()` and `run_whatif()`

### B5C Pipeline Stage (GUI)
- **Location:** `replayStore.js`, `sizing_complete` event handler
- When `payload.cb_enabled` is present, populates B5C stage with:
  - `cb_enabled`, `cb_blocked`, `cb_l1_halt`, `cb_rho_j`, `cb_l1_l_t`
  - `cb_l2_blocked`, `cb_l2_N`, `cb_l2_n_t`
  - `cb_l3_blocked`, `cb_l3_mu_b`
  - `cb_l0_blocked`, `cb_l4_blocked`
- PipelineStepper now shows B5C as "complete" instead of perpetual "pending"

---

## 7. What-If Reruns

### run_whatif() — replay_engine.py:1160–1284

**Triggered by:** `POST /api/replay/whatif` with `config_overrides`

**What happens:**
1. In b11 (line 338–374): finds the most recent completed replay for the user
2. Loads fresh config via `load_replay_config(config_overrides)`
3. Propagates `tp_multiple`/`sl_multiple` to all strategy dicts (same as start)
4. Calls `engine_whatif()` with cached bars from original replay + original results

**What recomputes:**
- ORB simulation (with possibly changed `tp_multiple`/`sl_multiple`)
- Kelly sizing (with possibly changed `user_capital`, `budget_divisor`, `max_contracts`, etc.)
- Quality gate (B5B) — applies same quality_score gating as run_replay()
- Position limit
- Cross-asset correlation filter — applies same halving as run_replay()

**What stays the same:**
- Bars (no API call — uses cached from original)
- AIM modifiers from original replay are extracted and passed through to `compute_contracts()` via `aim_modifier=` parameter (FIXED 2026-04-06)
- Intraday state accumulators (L_t, n_t, L_b) initialized fresh for what-if

**What-if comparison output:**
```python
{
    "whatif_results": [...],
    "whatif_trades": [selected],
    "whatif_excluded": [excluded],
    "whatif_total_pnl": float,
    "original_total_pnl": float,
    "pnl_delta": float,
    "comparison": [
        {
            "asset": str,
            "original_contracts": int,
            "original_pnl": float,
            "whatif_contracts": int,
            "whatif_pnl": float,
            "direction": int,
            "exit_reason": str,
            "sizing_diff": dict,  # full sizing breakdown
        }
    ],
    "errors": [...],
}
```

**Parameters that can be overridden in what-if:**
Any config key. Common ones: `user_capital`, `max_contracts`, `budget_divisor`, `tp_multiple`, `sl_multiple`, `cb_enabled`, `risk_goal`, `max_positions`.

---

## 8. Batch Replay

### BatchReplaySession — b11_replay_runner.py:382–613

**Start:** `POST /api/replay/batch/start` with `date_from`, `date_to`, `sessions`, `config_overrides`, `speed`

**Date generation (line 637–648):**
- Generates all weekdays (Mon-Fri) in range
- Max 60 weekdays per batch

**Per-day execution (line 473–555):**
- Calls `run_replay()` for each date sequentially in a background thread
- Uses same config for all days (loaded once at batch start)
- Supports pause/resume between days
- Emits `batch_day_started` and `batch_day_completed` events per day
- Minimal speed delay: `0.1 / max(speed, 1)` seconds per non-significant event

**Batch summary (line 579–613):**
```python
{
    "total_pnl": sum of daily PnLs,
    "total_trades": sum of daily trade counts,
    "total_wins": sum,
    "total_losses": sum,
    "win_rate": total_wins / total_trades × 100,
    "best_day": max(daily PnLs),
    "worst_day": min(daily PnLs),
    "avg_daily_pnl": total_pnl / total_days,
    "max_drawdown": peak-to-trough of cumulative PnL curve,
    "total_days": count,
    "profitable_days": count where pnl > 0,
    "losing_days": count where pnl < 0,
}
```

**Max drawdown calculation (line 589–596):**
```python
peak = 0; max_dd = 0; cum = 0
for p in daily_pnls:
    cum += p
    if cum > peak: peak = cum
    dd = peak - cum
    if dd > max_dd: max_dd = dd
```

**NOTE:** Batch replay reuses the same config for all days. It does not simulate evolving Kelly/EWMA/CB states between days — each day is independent with the same snapshot of QuestDB data as of batch start.

---

## 9. Config Parameter Reference Table

| Parameter | Default Value | Source | Type | Description |
|-----------|--------------|--------|------|-------------|
| `user_capital` | 150000.0 | D16 `total_capital` | float | Trading account capital base for Kelly sizing |
| `max_contracts` | 15 | D08 `max_contracts` | int | Absolute cap on contracts per signal |
| `max_positions` | 5 | D16 `max_simultaneous_positions` | int | Max concurrent positions across all assets |
| `budget_divisor` | **20 (hardcoded)** | replay_engine.py:232 | int | Divides remaining MDD into daily risk budgets. E.g. $4500/20 = $225/day |
| `risk_goal` | "GROW_CAPITAL" | D08 `risk_goal` | str | "GROW_CAPITAL" (×1.0), "PASS_EVAL" (×0.7), "PRESERVE_CAPITAL" (×0.5) |
| `cb_enabled` | **True (hardcoded)** | replay_engine.py:234 | bool | Enable CB Layer 1 preemptive halt check |
| `tp_multiple` | **0.70 (hardcoded)** | replay_engine.py:235 | float | Take-profit distance as multiple of OR range |
| `sl_multiple` | **0.35 (hardcoded)** | replay_engine.py:236 | float | Stop-loss distance as multiple of OR range |
| `mdd_limit` | 4500.0 | D08 `max_drawdown_limit` | float | Maximum drawdown limit (TopstepX account rule) |
| `mll_limit` | 2250.0 | D08 `max_daily_loss` | float | Maximum loss limit per day |
| `current_drawdown` | 0.0 | D08 `current_drawdown` | float | Current drawdown from account peak |
| `daily_loss_used` | 0.0 | D08 `daily_loss_used` | float | P&L already consumed today |
| `aim_enabled` | **False (hardcoded)** | replay_engine.py:884 | bool | Whether AIM scoring runs during replay |
| `topstep_params.c` | 0.5 | D08 `topstep_optimisation` JSON | float | CB L1 halt constant (in formula `l_halt = c × e × A`) |
| `topstep_params.e` | 0.01 | D08 `topstep_optimisation` JSON | float | CB L1 exposure fraction (in formula `l_halt = c × e × A`) |
| `strategies` | from D00 `locked_strategy` JSON | D00 per asset | dict | Per-asset strategy params (m, k, tp_multiple, sl_multiple, etc.) |
| `specs` | from D00 | D00 per asset | dict | Per-asset contract specs (point_value, tick_size, margin) |
| `kelly_params` | from D12 | D12 per (asset, regime, session) | dict | Kelly fractions and shrinkage per regime |
| `ewma_states` | from D05 | D05 per (asset, regime, session) | dict | Win rate, avg win, avg loss per regime |
| `contracts` | contract_ids.json | config file | dict | TopstepX contract ID mapping |
| `session_config` | static | replay_engine.py:35–39 | dict | OR/EOD times per session |
| `asset_session_map` | static | replay_engine.py:42–48 | dict | Which session each asset trades in |

### Parameters from locked_strategy (per-asset, inside `strategies` dict):
| Parameter | Default (fallback) | Description |
|-----------|-------------------|-------------|
| `tp_multiple` | 2.0 (in simulate_orb) | TP as multiple of OR range |
| `sl_multiple` | 1.0 (in simulate_orb) | SL as multiple of OR range |
| `threshold` | 4.0 (in compute_contracts) | Used for fallback_risk = threshold × point_value |

---

## 10. Full Pipeline Replay vs GUI Replay — Key Differences

| Aspect | GUI Replay (replay_engine.py) | Full Pipeline Replay (replay_full_pipeline.py) |
|--------|------------------------------|----------------------------------------------|
| **Regime** | `_compute_regime_probs()` — ports B2 logic (REGIME_NEUTRAL → 0.5/0.5, BINARY_ONLY + pettersson) | Real B2 regime probability |
| **AIM** | `shared/aim_compute.py` with historical features | Real B3 via `captain_online.blocks.b3_aim_aggregation` |
| **Kelly** | Simplified 10-step in `compute_contracts()` | Real B4 7-layer Kelly |
| **Trade selection** | Edge-rank by expected edge (`_expected_edge()`) | Real B5 HMM session allocation + expected edge |
| **Quality gate** | `_apply_quality_gate()` — ports B5B (quality_score, hard_floor, graduated sizing) | Real B5B $/contract floor |
| **Correlation filter** | `_apply_correlation_filter()` — halves lower-edge correlated pairs (>0.7) | Real B5 correlation reduction |
| **Circuit breaker** | L1 only | Real B5C L0-L4 |
| **OR detection** | Post-hoc scan of 1-min bars | ORTracker fed synthetic ticks (high/low/close) |
| **Signal output** | Internal dict, no Redis publish | Real B6 → Redis → GUI |
| **State mutation** | Read-only (no QuestDB writes) | Read-only except D29 volume store + D30/D33 optional |
| **AIM-15 Phase B** | Not implemented | Implemented (replay_full_pipeline.py:320–388) |
| **B8/B9 post-loop** | Not implemented | Not implemented |
| **Multi-user** | Hardcoded `primary_user` | Single user from D16 |

---

## 11. GUI Layout & Component Hierarchy

### Page structure (ReplayPage.jsx)

```
ReplayPage (h-screen, flex col)
├── TopBar                                          [shrink-0]
├── PlaybackControls                                [shrink-0, hidden when status="idle"]
├── 3-column grid [280px | 1fr | 280px]            [flex-1, min-h-0]
│   ├── LEFT COLUMN (280px, scrollable)
│   │   └── ReplayConfigPanel                       [config sliders, toggles, presets, run button]
│   │
│   ├── CENTER COLUMN (1fr)
│   │   ├── SimulatedPosition                       [shrink-0, shows active breakout position]
│   │   └── Asset card area (scrollable)
│   │       ├── Empty state: "Configure and click RUN REPLAY" (when idle + no assets)
│   │       ├── Loading state: "Initializing replay..." (when running + no assets)
│   │       └── AssetCard grid (2-col)              [one card per asset, keyed by asset symbol]
│   │
│   └── RIGHT COLUMN (280px, scrollable)
│       ├── BatchPnlReport                          [hidden when batchStatus="idle"]
│       ├── ReplaySummary                           [hidden when batchStatus!="idle"]
│       ├── WhatIfComparison                        [hidden when comparison=null]
│       └── ReplayHistory                           [always visible]
│
└── ResizableBottomPanel                            [shrink-0]
    ├── PipelineStepper                             [always visible, horizontal stage indicators]
    └── BlockDetail                                 [visible only when expandedStage != null]
        └── (height: user-draggable, min 100px, max 70vh, default 250px)
```

### ErrorBoundary pattern

Every component is wrapped in an `ErrorBoundary` with a `name` prop. On error, renders a red-bordered box showing the component name and error message. The boundary is a class component defined inline in ReplayPage.jsx.

### Data sources per component

| Component | Store Selectors Used | API Calls | Props |
|-----------|---------------------|-----------|-------|
| ReplayPage | assetOrder, assetResults, combinedModifier, expandedStage, status | `api.replayPresets()`, `api.replayHistory()` on mount | — |
| ReplayConfigPanel | config, speed, status, presets, reset | `api.replayStart()`, `api.replayBatchStart()`, `api.replayPresets()`, `api.replayPresetSave()` | — |
| PlaybackControls | status, speed, progress, currentAsset, batchStatus, batchCurrentDay, batchCompletedDays, batchTotalDays, batchProgress | `api.replayControl()` | — |
| PipelineStepper | pipelineStages, expandedStage, status | — | — |
| BlockDetail | pipelineStages[blockId], (B2: none, B3: aimBreakdown/combinedModifier/aimDebug/config.aimEnabled/pipelineStages.B3, B4: assetResults) | — | `blockId: string` |
| AssetCard | — | — | `asset: string, data: object, aimModifier: number` |
| SimulatedPosition | activeSimPosition | — | — |
| ReplaySummary | status, summary, replayId, assetResults, assetOrder, config, batchStatus | `api.replaySave()`, `api.replayWhatIf()` | — |
| BatchPnlReport | batchStatus, batchDayResults, batchSummary, batchCurrentDay, batchCompletedDays, batchTotalDays | — | — |
| WhatIfComparison | comparison, summary, assetResults, assetOrder | — | — |
| ReplayHistory | replayHistory | `api.replayHistory()` on mount | — |

### Dev tooling

In dev mode (`import.meta.env.DEV`), `window.__replayStore` is set to the Zustand store for console debugging.

---

## 12. Config UI Parameters

### Control inventory (ReplayConfigPanel.jsx)

| UI Control | Parameter Name | Type | Range/Options | Default | Maps to Backend Param |
|------------|---------------|------|---------------|---------|----------------------|
| Mode toggle (2 buttons) | `config.mode` | string | `"single"` \| `"period"` | `"single"` | Determines endpoint: `replayStart` vs `replayBatchStart` |
| Date picker | `config.date` | string | any date (YYYY-MM-DD) | today's date | `date` (request body) |
| Date From picker | `config.dateFrom` | string | any date | `""` | `date_from` (batch request) |
| Date To picker | `config.dateTo` | string | any date | `""` | `date_to` (batch request) |
| Session checkboxes (4) | `config.sessions` | string[] | `["NY", "LONDON", "APAC", "NY_PRE"]` | all 4 checked | `sessions` (request body) |
| Capital ($) number input | `config.capital` | number | min=0, step=1000 | `150000` | `user_capital` |
| Budget Divisor number input | `config.budgetDivisor` | number | min=1 | `20` | `budget_divisor` |
| MDD Limit ($) number input | `config.mddLimit` | number | min=0, step=100 | `4500` | `mdd_limit` |
| MLL Limit ($) number input | `config.mllLimit` | number | min=0, step=100 | `2250` | `mll_limit` |
| Risk Goal dropdown | `config.riskGoal` | string | `"PASS_EVAL"` \| `"GROW_CAPITAL"` \| `"PRESERVE_CAPITAL"` | `"PASS_EVAL"` | `risk_goal` |
| Max Positions number input | `config.maxPositions` | number | min=1, max=20 | `5` | `max_positions` |
| Max Contracts number input | `config.maxContracts` | number | min=1, max=100 | `15` | `max_contracts` |
| TP Multiple number input | `config.tpMultiple` | number | min=0, max=5, step=0.05 | `0.70` | `tp_multiple` |
| SL Multiple number input | `config.slMultiple` | number | min=0, max=5, step=0.05 | `0.35` | `sl_multiple` |
| CB L1 Enabled toggle | `config.cbEnabled` | boolean | on/off | `true` | `cb_enabled` |
| AIM Scoring toggle | `config.aimEnabled` | boolean | on/off | `false` | `aim_enabled` |
| Playback Speed buttons (4) | `speed` (top-level, not in config) | number | `1` \| `10` \| `50` \| `100` | `50` | `speed` (request body) |
| Preset selector dropdown | — | — | loaded from `api.replayPresets()` | — | — |
| Preset name text + Save | — | — | free text | — | `api.replayPresetSave(name, config)` |

### camelCase → snake_case mapping (handleRun)

The `handleRun` function in ReplayConfigPanel builds the `overrides` object that gets sent as `config_overrides`:

```javascript
const overrides = {
  user_capital:   config.capital,       // 150000
  budget_divisor: config.budgetDivisor, // 20
  risk_goal:      config.riskGoal,      // "PASS_EVAL"
  max_positions:  config.maxPositions,  // 5
  max_contracts:  config.maxContracts,  // 15
  tp_multiple:    config.tpMultiple,    // 0.70
  sl_multiple:    config.slMultiple,    // 0.35
  cb_enabled:     config.cbEnabled,     // true
  aim_enabled:    config.aimEnabled,    // false
  mdd_limit:      config.mddLimit,     // 4500
  mll_limit:      config.mllLimit,     // 2250
};
```

### Reset to Live defaults (handleResetToLive)

Calls `reset()` then `setConfig()` with hardcoded values identical to the initial store state. Resets mode to `"single"`, date to today, all parameters to their defaults.

### Validation

- Period mode: silently returns if `dateFrom` or `dateTo` empty, or if `dateFrom > dateTo`
- Session checkboxes: cannot deselect all (minimum 1 enforced in onChange handler)
- No other client-side validation — backend handles invalid values

---

## 13. WebSocket Event Flow

### Connection setup (useWebSocket.js)

- URL: `ws[s]://{window.location.host}/ws/{userId}`
- userId hardcoded as `"primary_user"` in ReplayPage mount
- Reconnect: exponential backoff starting at 2s, max 30s, resets on successful open
- Eviction code 4001 prevents reconnection
- All JSON messages parsed and dispatched by `data.type` switch

### Replay message routing

The following `data.type` values are routed to `replayStore.handleWsMessage(data)`:

```
replay_tick, replay_started, replay_complete, replay_error,
replay_paused, replay_resumed, batch_started, batch_day_started,
batch_day_completed, batch_complete
```

All other types (`dashboard`, `live_market`, `signal`, `bar_update`, etc.) are routed to their respective stores and are NOT related to replay.

### Events sent from frontend to backend

**No replay-specific WebSocket messages are sent from the frontend.** All replay commands use REST API calls:

| Action | API Call | Endpoint |
|--------|---------|----------|
| Start single replay | `api.replayStart(date, sessions, overrides, speed)` | `POST /api/replay/start` |
| Start batch replay | `api.replayBatchStart(dateFrom, dateTo, sessions, overrides, speed)` | `POST /api/replay/batch/start` |
| Pause | `api.replayControl("pause")` | `POST /api/replay/control` |
| Resume | `api.replayControl("resume")` | `POST /api/replay/control` |
| Skip | `api.replayControl("skip")` | `POST /api/replay/control` |
| Change speed | `api.replayControl("speed", newSpeed)` | `POST /api/replay/control` |
| Save results | `api.replaySave(replayId)` | `POST /api/replay/save` |
| Run what-if | `api.replayWhatIf(overrides)` | `POST /api/replay/whatif` |
| Load presets | `api.replayPresets()` | `GET /api/replay/presets` |
| Save preset | `api.replayPresetSave(name, config)` | `POST /api/replay/presets` |
| Load history | `api.replayHistory()` | `GET /api/replay/history` |

### Events received from backend — single replay sequence

```
1. replay_started           → {replay_id}
2. replay_tick/config_loaded → {user_capital, max_positions, ...}
3. replay_tick/auth_complete → {contracts_resolved}
4. replay_tick/aim_scored    → {combined_modifier, aim_breakdown, aim_debug}  [if aim_enabled]
   [Per asset, repeated for each active asset:]
5. replay_tick/asset_bars_fetched → {asset, bar_count, session}
6. replay_tick/or_computed        → {asset, or_high, or_low, or_range}
7. replay_tick/breakout           → {asset, direction, entry_price, tp_level, sl_level}
8. replay_tick/exit               → {asset, exit_price, exit_reason, pnl_per_contract}
9. replay_tick/sizing_complete    → {asset, contracts, kelly_blended, ...sizing details}
   [End per-asset loop]
10. replay_tick/quality_gate_applied      → {results[]: asset, quality_score, quality_gate_passed, data_maturity}
11. replay_tick/position_limit_applied    → {selected[], excluded[]}
12. replay_tick/correlation_filter_applied → {adjustments[]: asset, correlated_with, contracts}  [if any pairs reduced]
13. replay_tick/replay_complete           → {summary}
```

### Events received from backend — batch replay sequence

```
1. batch_started           → {replay_id, total_days, dates, sessions}
   [Per day:]
2. batch_day_started       → {date, day_index, total_days}
3. [Normal single-day events: config_loaded through replay_complete]
4. batch_day_completed     → {date, day_pnl, cumulative_pnl, day_trades, day_wins, day_losses}
   [End per-day loop]
5. batch_complete          → {summary}
```

### Message payload extraction

The store's `handleWsMessage` extracts payload via destructuring:
```javascript
const { type: _t, replay_id: _r, event: _e, ...payload } = data;
```

The backend flattens `event_data` into the top-level message via `**event_data`, so fields like `asset`, `direction`, `entry_price` appear alongside `type`, `replay_id`, `event`.

---

## 14. Store State Management

### All state variables (replayStore.js, Zustand)

| Variable | Type | Initial Value | Description |
|----------|------|---------------|-------------|
| `replayId` | string\|null | `null` | UUID of active/completed replay |
| `status` | string | `"idle"` | `"idle"` \| `"running"` \| `"paused"` \| `"complete"` |
| `speed` | number | `50` | Playback speed multiplier |
| `progress` | number | `0` | Single-replay progress 0–100 |
| `currentAsset` | string\|null | `null` | Asset currently being processed |
| `config` | object | (see Section 12) | Full config state, sandboxed from live |
| `presets` | array | `[]` | Saved config presets |
| `pipelineStages` | object | `{}` | `{B1: {status, data}, B2: {...}, ...}` |
| `expandedStage` | string\|null | `null` | Which pipeline stage's BlockDetail is shown |
| `assetResults` | object | `{}` | `{ES: {orResult, sizing, breakout, exitResult, status, error, bar_count}, ...}` |
| `assetOrder` | array | `[]` | Asset symbols in order of arrival |
| `activeSimPosition` | object\|null | `null` | `{asset_id, direction, entry_price, contracts, tp_level, sl_level}` |
| `summary` | object\|null | `null` | Final summary from replay_complete |
| `comparison` | object\|null | `null` | What-if comparison result |
| `aimBreakdown` | object | `{}` | `{asset_id: {aim_id: {modifier, confidence, reason_tag, dma_weight}}}` |
| `combinedModifier` | object | `{}` | `{asset_id: float}` — per-asset combined AIM modifier |
| `aimDebug` | object | `{}` | `{asset_id: {aim_id: {modifier, weight, tag}}}` |
| `replayHistory` | array | `[]` | Past replay entries from GET /api/replay/history |
| `batchStatus` | string | `"idle"` | `"idle"` \| `"running"` \| `"paused"` \| `"complete"` |
| `batchDayResults` | array | `[]` | `[{date, trades, wins, losses, pnl, cumulativePnl}]` |
| `batchSummary` | object\|null | `null` | Overall batch summary from batch_complete |
| `batchCurrentDay` | string\|null | `null` | Date string of day currently being replayed |
| `batchTotalDays` | number | `0` | Total weekdays in batch range |
| `batchCompletedDays` | number | `0` | Days completed so far |
| `batchProgress` | number | `0` | Batch progress 0–100 |

### All actions

| Action | Signature | Effect |
|--------|-----------|--------|
| `setConfig` | `(updates: object)` | Shallow-merges updates into `config` |
| `setSpeed` | `(speed: number)` | Sets `speed` |
| `setExpandedStage` | `(stage: string)` | Toggles: if same as current → `null`, else → `stage` |
| `reset` | `()` | Resets all state **except** `config`, `speed`, `presets`, `replayHistory` |
| `handleWsMessage` | `(data: object)` | Main dispatcher — routes by `data.type \|\| data.event` (see Section 12) |
| `setPresets` | `(presets: array)` | Sets `presets` |
| `setHistory` | `(history: array)` | Sets `replayHistory` |
| `setComparison` | `(comparison: object)` | Sets `comparison` |

### Data flow

```
REST API (start/control/save/whatif)
    ↓ response
    → handleWsMessage() [for start — injects replay_started]
    → setComparison() [for what-if]

WebSocket (/ws/{userId})
    ↓ onmessage
    → useWebSocket switch(data.type)
    → replayStore.handleWsMessage(data)
    → set() calls update Zustand state
    → Zustand selectors in components trigger re-renders
    → Components read from store via useReplayStore((s) => s.field)
```

### Pipeline stage tracking

The `pipelineStages` object is built incrementally by handleWsMessage as events arrive:

| Event | Pipeline Stage Set | Status |
|-------|--------------------|--------|
| `config_loaded` | `B1` | `"complete"` |
| `auth_complete` | `B1_AUTH` | `"complete"` |
| `aim_scored` | `B3` | `"complete"` |
| `sizing_complete` | `B4` | `"complete"` |
| `quality_gate_applied` | `B5B` | `"complete"` |
| `position_limit_applied` | `B5` | `"complete"` |
| `correlation_filter_applied` | (no stage) | Logged in results |
| `replay_complete` | `B6` | `"complete"` |

B2 is set to `"complete"` when any `or_computed` event arrives (hardcoded summary: `"Regime neutral"`).

**NOTE:** PipelineStepper defines 7 stages: `B1, B2, B3, B4, B5, B5C, B6`. The store never sets `B5C` from any event — it remains in "pending" state throughout replay. This means the Circuit Breaker stage in the stepper never lights up, even though CB L1 is computed inside the sizing step.

---

## 15. User Flows

### Single-day replay

1. **Configure**: User adjusts parameters in ReplayConfigPanel (left column). All controls disabled while `isRunning` (status = "running" or "paused").
2. **Run**: User clicks "RUN REPLAY" button.
3. **Reset**: `handleRun()` calls `useReplayStore.getState().reset()` — clears all results but preserves config.
4. **Build overrides**: Maps camelCase config → snake_case overrides object (11 parameters).
5. **API call**: `api.replayStart(date, sessions, overrides, speed)` → `POST /api/replay/start`.
6. **Immediate store update**: On API response with `replay_id`, injects `{type: "replay_started", replay_id}` into `handleWsMessage`.
7. **Status change**: Store sets `status="running"` → PlaybackControls bar appears, RUN button disabled.
8. **WebSocket streaming**: Backend emits `replay_tick` events through the shared WebSocket connection.
9. **Pipeline lights up**: `config_loaded` → B1 green. `or_computed` → B2 green. `aim_scored` → B3. `sizing_complete` → B4. `position_limit_applied` → B5.
10. **Asset cards appear**: `asset_bars_fetched` adds asset to grid (shimmer animation). `or_computed` shows OR range. `breakout` shows entry/TP/SL and direction badge. `sizing_complete` shows contract count. `exit` shows PnL and exit reason badge.
11. **SimulatedPosition**: Appears on `breakout` event (shows direction, entry, TP, SL, contracts). Clears on `exit` event.
12. **Completion**: `replay_complete` → `status="complete"`, `progress=100`, B6 green. ReplaySummary shows total PnL, win/loss counts, win rate, all trades sorted by PnL.
13. **Post-completion**: User can click "What-If" or "Save" buttons in ReplaySummary. Clicking a pipeline stage opens BlockDetail in the resizable bottom panel.

### Batch (period) replay

1. **Select period mode**: User clicks "Period" button in mode toggle.
2. **Set date range**: User picks From/To dates. UI shows weekday count inline (computed client-side, skipping Sat/Sun).
3. **Validation**: If `dateFrom` empty, `dateTo` empty, or `dateFrom > dateTo`, `handleRun()` returns silently (no error message).
4. **API call**: `api.replayBatchStart(dateFrom, dateTo, sessions, overrides, speed)` → `POST /api/replay/batch/start`.
5. **Immediate inject**: On API response, injects `{type: "batch_started", replay_id, total_days: 0}` — total_days=0 is placeholder.
6. **Real batch_started arrives**: WebSocket `batch_started` with actual `total_days`. Store: `batchStatus="running"`.
7. **Per-day cycle**:
   - `batch_day_started`: resets `assetResults`, `assetOrder`, `pipelineStages`, `activeSimPosition`, `summary` — per-day slate is clean.
   - Normal single-day events stream (same as steps 8–12 above, but center column refreshes each day).
   - `batch_day_completed`: appends `{date, trades, wins, losses, pnl, cumulativePnl}` to `batchDayResults`. Updates `batchProgress`.
8. **UI during batch**: BatchPnlReport appears in right column (ReplaySummary hides when `batchStatus != "idle"`). Shows progress bar, day counter, and live day-by-day result rows.
9. **Completion**: `batch_complete` → `batchStatus="complete"`, `batchSummary` populated. BatchPnlReport switches to finished view with "Day-by-Day" / "Overall" toggle and CSV download button.
10. **CSV export**: `handleDownloadCSV()` generates client-side blob with headers `Date,Trades,Wins,Losses,PnL,Cumulative PnL`, triggers download via anchor click.

### What-if comparison

1. **Prerequisite**: A single-day replay must be complete (`status="complete"`).
2. **Adjust config**: User changes parameters in the left panel (e.g., different capital, TP/SL multiples). Config is still editable since `isRunning` is false when complete.
3. **Click What-If**: Button in ReplaySummary. `handleWhatIf()` builds overrides from current config state (same mapping as `handleRun` but **without** `aim_enabled`).
4. **API call**: `api.replayWhatIf(overrides)` → `POST /api/replay/whatif`. This is a **synchronous** REST call (not streamed via WebSocket).
5. **Backend**: Finds most recent completed replay, loads fresh config with overrides, re-runs ORB simulation and Kelly sizing using **cached bars** from original run. AIM is **NOT recomputed**.
6. **Response**: Full what-if result object set via `setComparison(result)`.
7. **WhatIfComparison renders**: 4-column table (Metric / Original / What-If / Delta) showing:
   - Total P&L (highlighted row)
   - Trade count
   - Blocked count
   - Per-asset contract changes (original → what-if with delta)
   - Status changes (assets that changed between exited/blocked/sized)
8. **No "close" button**: WhatIfComparison stays visible until next `reset()` (e.g., running a new replay).

### Playback controls flow

- **Play/Pause**: Only enabled when `isRunning || isPaused`. Calls `api.replayControl("pause")` or `api.replayControl("resume")`.
- **Skip**: Calls `api.replayControl("skip")`. Skips to next significant event on backend.
- **Speed change**: Updates local store via `setSpeed()` AND sends `api.replayControl("speed", newSpeed)` if currently active. Speed pills duplicated in both PlaybackControls bar and ReplayConfigPanel.
- **Progress bar**: Shows `progress` for single replay or `batchProgress` for batch (determined by `batchStatus != "idle"`).
- **Status badge**: Shows uppercase `status` string with color-coded border (green=running, amber=paused, grey=other).
- **Hidden when idle**: Entire PlaybackControls bar returns `null` when `status === "idle"`.

### Pipeline detail expansion

1. User clicks any stage button in PipelineStepper (B1–B6).
2. `setExpandedStage(stage)` toggles: if clicking same stage, sets `null` (collapses). Otherwise sets new stage.
3. ResizableBottomPanel shows BlockDetail with drag handle (5px hover zone) when `expandedStage` is non-null.
4. BlockDetail renders stage-specific component based on `BLOCK_RENDERERS` map:
   - **B1**: Config summary (capital, max positions, budget divisor, risk goal, MDD/MLL limits)
   - **B1_AUTH**: Raw JSON
   - **B2**: Static text "All assets: REGIME_NEUTRAL (50/50 blend)" + explanation
   - **B3**: Full AIM debug panel — per-asset combined modifier + table of all active AIMs with modifier, confidence, DMA weight, reason tag. Shows diagnostic messages for disabled/skipped/failed states.
   - **B4**: Sizing table with columns: Asset, Kelly, Risk/Ct, Raw, MDD, Daily, Max, CB, Final
   - **B5**: Selected vs excluded asset lists with PnL/reason
   - **B5C**: Raw JSON (never populated — see note in Section 14)
   - **B6**: Raw JSON
