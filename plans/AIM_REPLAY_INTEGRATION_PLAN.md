# AIM Replay Integration Plan

**Goal:** Wire real AIM modifiers into the session replay system so replay results reflect the same AIM influence as live trading.

**Created:** 2026-04-01  
**Status:** Ready for execution

---

## Phase 0 — Discovery Summary

### Architecture

- AIM handlers live in `captain-online/.../b3_aim_aggregation.py` (lines 48-596)
- Replay runs via `shared/replay_engine.py` inside captain-command container
- Different Docker containers — captain-command cannot import from captain-online
- **Solution:** Extract to `shared/aim_compute.py` (pure functions, no class, no state)

### Current State

| Component | File | Line(s) | State |
|-----------|------|---------|-------|
| AIM placeholder | `shared/replay_engine.py` | 688 | `aim_mod = 1.0` hardcoded |
| B3 UI placeholder | `captain-gui/.../BlockDetail.jsx` | 40-69 | Static table, 6 AIMs, all 1.0x |
| Event system | `shared/replay_engine.py` | 833-839 | `_emit(on_event, event_type, data)` — 9 events, no AIM event |
| What-if state | `captain-gui/.../replayStore.js` | 44 | `comparison: null` — exists but unused |
| Config toggle pattern | `captain-gui/.../ReplayConfigPanel.jsx` | 291-305 | CB toggle — reusable pattern |
| AIM panel pattern | `captain-gui/.../AimRegistryPanel.jsx` | 248 | 4×4 grid — reusable pattern |

### b3_aim_aggregation.py Structure (lines 48-596)

Already pure functions — no class, no `self.*`:

| Range | Content |
|-------|---------|
| 44-45 | `MODIFIER_FLOOR = 0.5`, `MODIFIER_CEILING = 1.5` |
| 48-119 | `run_aim_aggregation(active_assets, features, aim_states, aim_weights)` — MoE orchestrator |
| 126-162 | `compute_aim_modifier(aim_id, features, asset_id, state)` — dispatcher |
| 164-572 | 15 handler functions: `_aim01_vrp` through `_aim15_volume` (AIM-16 present but disabled per DEC-06) |
| 589-596 | `_clamp(value, floor, ceiling)` |

All handlers: `(f: dict, state: dict) -> {modifier: float, confidence: float, reason_tag: str}`

### Test Mock Paths (Critical)

Tests mock `captain_online.blocks.b3_aim_aggregation.compute_aim_modifier`. After extraction to `shared.aim_compute`, mock paths must change to `shared.aim_compute.compute_aim_modifier` so the patch intercepts calls from `run_aim_aggregation()` in the same module namespace.

**Affected test files:**
- `tests/test_b3_aim.py` — 15 tests, mocks compute_aim_modifier
- `tests/test_integration_e2e.py` — mocks compute_aim_modifier
- `tests/test_stress.py` — mocks compute_aim_modifier
- `tests/test_pipeline_e2e.py` — mocks compute_aim_modifier

### Data Availability for Historical Feature Computation

| AIM | Feature Keys | Data Source | Coverage |
|-----|-------------|-------------|----------|
| 04 (IVTS) | `ivts`, `overnight_return_z`, `is_eia_wednesday` | VIX/VXV CSVs, p3_d30 OHLCV | Full (9155+ VIX days, 283 OHLCV days) |
| 06 (Calendar) | `event_proximity`, `events_today` | Static calendar logic | Full |
| 08 (Correlation) | `correlation_z` | p3_d30 OHLCV (20d rolling) | Full (283 days) |
| 09 (Momentum) | `cross_momentum` | p3_d30 OHLCV | Full |
| 10 (Calendar Effects) | `is_opex_window` | Static calendar logic | Full |
| 11 (Regime Warning) | `vix_z`, `vix_daily_change_z` | VIX CSVs | Full |
| 15 (Opening Volume) | `opening_volume_ratio` | p3_d29 or p3_d33 | Full (240 rows) |
| 01 (VRP) | `vrp_overnight_z`, `day_of_week` | p3_d31 IV/RV | ES only (122 days) |
| 02 (Skew) | `pcr_z`, `skew_z` | p3_d32 skew | ES only, skew half only (81 days) |
| 12 (Costs) | `spread_z`, `vol_z`, `vix_z` | p3_d33 opening vol | Partial (vol_z only) |
| 03 (GEX) | `gex` | None | Neutral 1.0 (matches production) |
| 05 (Deferred) | — | None | Neutral 1.0 |
| 07 (COT) | `cot_smi`, `cot_speculator_z` | None | Neutral 1.0 |
| 13 (Sensitivity) | `state.current_modifier` | D01 state | Reads from state |
| 14 (Expansion) | — | None | Always 1.0 |
| 16 (HMM) | `state.current_modifier` | D01 state | Disabled in B3 per DEC-06 |

### Allowed APIs

| Module | Functions | Source |
|--------|-----------|--------|
| `shared/questdb_client.py` | `get_cursor()` context manager, `cur.execute()`, `cur.fetchall()` | Lines 32-41 |
| `shared/vix_provider.py` | `get_latest_vix_close()`, `get_trailing_vix_closes(252)`, `get_trailing_vix_daily_changes(60)`, `get_latest_vxv_close()` | Lines 107-176 |
| `shared/replay_engine.py` | `_emit(on_event, event_type, data)`, `run_replay(config, target_date, on_event, sessions)` | Lines 833-839, 842-847 |
| `captain-gui replayStore.js` | `handleWsMessage()` event routing, `setComparison()` action, `setConfig()` action | Lines 71-235, 239 |

### Anti-Patterns to Avoid

- **DO NOT** invent QuestDB table names — use only tables confirmed in data bootstrap status
- **DO NOT** import from `captain-online` in shared/ or captain-command — that's the whole problem we're solving
- **DO NOT** change handler thresholds — verbatim extraction only
- **DO NOT** add numpy as dependency to shared/ without checking it's available in captain-command container
- **DO NOT** modify `config/` or `shared/constants.py` (frozen per CLAUDE.md)

---

## Phase 1 — Extract `shared/aim_compute.py` + Refactor `b3_aim_aggregation.py`

**Objective:** Create single source of truth for AIM computation logic accessible by both containers.

### Step 1.1: Create `shared/aim_compute.py`

Copy lines 44-596 from `captain-online/captain_online/blocks/b3_aim_aggregation.py` verbatim into `shared/aim_compute.py`:

```
shared/aim_compute.py
├── MODIFIER_FLOOR = 0.5
├── MODIFIER_CEILING = 1.5
├── run_aim_aggregation(active_assets, features, aim_states, aim_weights) -> dict
├── compute_aim_modifier(aim_id, features, asset_id, state) -> dict
├── _aim01_vrp(f, state) -> dict
├── _aim02_skew(f, state) -> dict
├── _aim03_gex(f, state) -> dict
├── _aim04_ivts(f, state) -> dict
├── _aim06_calendar(f, state) -> dict
├── _aim07_cot(f, state) -> dict
├── _aim08_correlation(f, state) -> dict
├── _aim09_momentum(f, state) -> dict
├── _aim10_calendar_effects(f, state) -> dict
├── _aim11_regime_warning(f, state) -> dict
├── _aim12_costs(f, state) -> dict
├── _aim13_sensitivity(f, state) -> dict
├── _aim14_expansion(f, state) -> dict
├── _aim15_volume(f, state) -> dict
├── _aim16_hmm(f, state) -> dict
└── _clamp(value, floor, ceiling) -> float
```

**Import header:** `import logging` only. No numpy, no external deps. These are pure dict-in/dict-out functions.

### Step 1.2: Refactor `b3_aim_aggregation.py` to thin re-export

Replace the entire body of `captain-online/captain_online/blocks/b3_aim_aggregation.py` with:

```python
"""Block 3 – AIM Aggregation (Mixture-of-Experts)

Delegates to shared.aim_compute for the actual computation logic.
This module re-exports for backward compatibility with existing imports.
"""
from shared.aim_compute import (
    MODIFIER_FLOOR,
    MODIFIER_CEILING,
    run_aim_aggregation,
    compute_aim_modifier,
)

__all__ = [
    "MODIFIER_FLOOR",
    "MODIFIER_CEILING",
    "run_aim_aggregation",
    "compute_aim_modifier",
]
```

### Step 1.3: Update test mock paths

In all 4 test files, change the mock target from `captain_online.blocks.b3_aim_aggregation.compute_aim_modifier` to `shared.aim_compute.compute_aim_modifier`:

| File | Change |
|------|--------|
| `tests/test_b3_aim.py` | `@patch("shared.aim_compute.compute_aim_modifier")` (8 occurrences) |
| `tests/test_integration_e2e.py` | `@patch("shared.aim_compute.compute_aim_modifier")` |
| `tests/test_pipeline_e2e.py` | `@patch("shared.aim_compute.compute_aim_modifier")` |
| `tests/test_stress.py` | `@patch("shared.aim_compute.compute_aim_modifier")` |

Also update import statements in these files: change `from captain_online.blocks.b3_aim_aggregation import ...` to `from shared.aim_compute import ...`.

### Step 1.4: Also copy `z_score()` utility into `shared/aim_compute.py`

The `z_score()` helper from `b1_features.py:357-369` will be needed by the feature loader (Phase 2). Add it to `shared/aim_compute.py` as a standalone function. Implementation:

```python
def z_score(value, trailing_series):
    """Standard z-score: (value - mean) / std. None if insufficient data."""
    if trailing_series is None or len(trailing_series) < 10:
        return None
    n = len(trailing_series)
    mu = sum(trailing_series) / n
    variance = sum((x - mu) ** 2 for x in trailing_series) / n
    sigma = variance ** 0.5
    if sigma == 0:
        return 0.0
    return (value - mu) / sigma
```

**Note:** Pure-Python implementation (no numpy) to avoid adding numpy as a dependency to shared/. The original uses numpy but the logic is identical — standard z-score with a minimum 10 data points guard.

### Verification

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/test_b3_aim.py -v
```

All 15 AIM tests must pass. Then run the full suite (excluding container-dependent tests).

---

## Phase 2 — Historical Feature Loader

**Objective:** Build `shared/aim_feature_loader.py` that constructs the `features` dict for a given date and asset set using historical QuestDB data and VIX CSVs.

### Step 2.1: Create `shared/aim_feature_loader.py`

```
shared/aim_feature_loader.py
├── load_replay_features(target_date: date, assets: list[str]) -> dict
│   Returns {asset_id: {feature_key: value, ...}, ...}
│   Calls sub-loaders below, assembles per-asset feature dicts
│
├── _load_vix_features(target_date) -> dict
│   Uses shared/vix_provider.py
│   Computes: vix_z, vix_daily_change_z, ivts (VIX/VXV ratio)
│
├── _load_ohlcv_features(target_date, asset_id, cur) -> dict
│   Queries p3_d30_daily_ohlcv for trailing 30 days
│   Computes: overnight_return_z, correlation_z, cross_momentum
│
├── _load_iv_rv_features(target_date, asset_id, cur) -> dict
│   Queries p3_d31_implied_vol (ES only, 122 rows)
│   Computes: vrp_overnight_z
│
├── _load_skew_features(target_date, asset_id, cur) -> dict
│   Queries p3_d32_options_skew (ES only, 81 rows)
│   Computes: skew_z (pcr_z stays None — no PCR data)
│
├── _load_volume_features(target_date, asset_id, cur) -> dict
│   Queries p3_d33_opening_volatility
│   Computes: vol_z, opening_volume_ratio
│
├── _load_calendar_features(target_date) -> dict
│   Pure computation from date
│   Computes: day_of_week, is_opex_window, is_eia_wednesday
│   (event_proximity, events_today = None — no calendar feed in replay)
│
└── _load_aim_states_and_weights(assets, cur) -> tuple[dict, dict]
    Queries p3_d01_aim_model_states and p3_d02_aim_meta_weights
    Returns (aim_states, aim_weights) in the format run_aim_aggregation expects
```

### Step 2.2: Feature computation details

**VIX features** (from `shared/vix_provider.py`):
- `vix_z = z_score(latest_vix, trailing_252)` — 252-day trailing window
- `vix_daily_change_z = z_score(latest_change, trailing_60_changes)` — 60-day change window
- `ivts = vix / vxv` — VIX/VXV ratio (IV term structure)

**OHLCV features** (from `p3_d30_daily_ohlcv`):
- Query: `SELECT trade_date, asset_id, open, high, low, close FROM p3_d30_daily_ohlcv WHERE asset_id = $1 AND trade_date <= $2 ORDER BY trade_date DESC LIMIT 30`
- `overnight_return = (today_open - yesterday_close) / yesterday_close`
- `overnight_return_z = z_score(overnight_return, trailing_20_overnight_returns)`
- `correlation_z` = rolling 20-day return correlation with ES (z-scored)
- `cross_momentum` = sign alignment of 5-day vs 20-day returns

**IV/RV features** (from `p3_d31_implied_vol`, ES only):
- Query: `SELECT trade_date, iv, rv FROM p3_d31_implied_vol WHERE asset_id = 'ES' AND trade_date <= $1 ORDER BY trade_date DESC LIMIT 30`
- `vrp = iv - rv` (volatility risk premium)
- `vrp_overnight_z = z_score(vrp, trailing_20_vrps)`

**Skew features** (from `p3_d32_options_skew`, ES only):
- Query: `SELECT trade_date, skew FROM p3_d32_options_skew WHERE asset_id = 'ES' AND trade_date <= $1 ORDER BY trade_date DESC LIMIT 30`
- `skew_z = z_score(latest_skew, trailing_20_skews)`
- `pcr_z = None` (no PCR data available)

**Volume features** (from `p3_d33_opening_volatility`):
- `vol_z = z_score(latest_vol, trailing_20_vols)`
- `opening_volume_ratio` from `p3_d29_opening_volumes` if available

**Calendar features** (pure date computation):
- `day_of_week = target_date.weekday()` (0=Monday)
- `is_opex_window = True` if date is within OpEx week (3rd Friday ± 2 days)
- `is_eia_wednesday = True` if Wednesday and asset is CL
- `event_proximity = None`, `events_today = None` (no calendar feed)

### Step 2.3: Missing features gracefully degrade

Features that can't be computed (no data) return `None` in the features dict. Handler functions already handle this — they return neutral 1.0 when expected features are missing (e.g., `f.get("gex")` returns None → `_aim03_gex` returns 1.0).

### Verification

Write a quick smoke test that calls `load_replay_features(date(2026, 3, 28), ["ES"])` and verifies the returned dict has the expected keys with non-None values for features with data.

---

## Phase 3 — Wire AIM Computation into Replay Engine

**Objective:** Replace `aim_mod = 1.0` with real AIM computation. Emit `aim_scored` event.

### Step 3.1: Modify `shared/replay_engine.py`

**At the top** (imports):
```python
from shared.aim_compute import run_aim_aggregation
from shared.aim_feature_loader import load_replay_features
```

**In `run_replay()`** — after bar fetching, before Kelly sizing (around line 685):

```python
# --- AIM scoring (new) ---
aim_results_by_asset = {}
if config.get("aim_enabled", False):
    replay_features, aim_states, aim_weights = load_replay_features(
        target_date, list(asset_results.keys())
    )
    aim_output = run_aim_aggregation(
        active_assets=list(asset_results.keys()),
        features=replay_features,
        aim_states=aim_states,
        aim_weights=aim_weights,
    )
    aim_results_by_asset = aim_output.get("aim_breakdown", {})
    _emit(on_event, "aim_scored", {
        "combined_modifier": aim_output.get("combined_modifier", {}),
        "aim_breakdown": aim_results_by_asset,
    })
```

**Replace line 688** (`aim_mod = 1.0`):
```python
aim_mod = aim_output.get("combined_modifier", {}).get(asset_id, 1.0) if config.get("aim_enabled") else 1.0
```

**In the `sizing_complete` event** (line 1025), add `aim_modifier` to the emitted data:
```python
_emit(on_event, "sizing_complete", {
    ...existing fields...,
    "aim_modifier": aim_mod,
})
```

### Step 3.2: Thread `aim_enabled` through `b11_replay_runner.py`

In `captain-command/captain_command/blocks/b11_replay_runner.py`:

**`start_replay()` (line 210):** Accept `aim_enabled` from the API request and include it in config_overrides:
```python
config_overrides["aim_enabled"] = aim_enabled
```

**`load_replay_config()` (called at line 226):** Ensure `aim_enabled` passes through to the config dict that reaches `run_replay()`.

### Step 3.3: Add API endpoint parameter

In the replay API handler (likely in `captain-command/captain_command/blocks/b3_api_adapter.py` or the WebSocket handler), accept `aim_enabled` from the frontend request body and pass it to `start_replay()`.

### Verification

1. Start a replay via API with `aim_enabled: true` for a date with known data (e.g., 2026-03-28)
2. Verify the `aim_scored` WebSocket event is received with non-trivial modifiers for ES
3. Verify `sizing_complete` events include `aim_modifier` values
4. Start a replay with `aim_enabled: false` — verify `aim_mod = 1.0` (unchanged behavior)

---

## Phase 4 — Frontend: Store + Event Handling + Config Toggle

**Objective:** Handle the new `aim_scored` event, add toggle to config panel, wire config sending.

### Step 4.1: Update `replayStore.js`

**Add state fields:**
```javascript
aimBreakdown: {},      // {asset_id: {aim_id: {modifier, confidence, reason_tag, dma_weight}}}
combinedModifier: {},  // {asset_id: float}
```

**Add `aim_scored` event handler in `handleWsMessage()`** (after line 148, inside the `replay_tick` switch):
```javascript
case "aim_scored":
    set({
        aimBreakdown: eventData.aim_breakdown || {},
        combinedModifier: eventData.combined_modifier || {},
        pipelineStages: { ...get().pipelineStages, B3: eventData },
    });
    break;
```

**Reset aimBreakdown/combinedModifier** when a new replay starts (in the `replay_started` handler).

### Step 4.2: Add AIM toggle to config

**In `replayStore.js` config defaults:** Add `aimEnabled: false`.

**In `ReplayConfigPanel.jsx`:** Add an AIM toggle switch after the CB toggle (line 305), using the identical toggle pattern:

```jsx
{/* AIM Scoring */}
<div className="flex items-center justify-between">
    <span className="text-xs text-gray-400">AIM Scoring</span>
    <button
        onClick={() => setConfig({ aimEnabled: !config.aimEnabled })}
        role="switch"
        aria-checked={config.aimEnabled}
        className={`h-[16px] w-[32px] rounded-full relative ${
            config.aimEnabled ? "bg-[#10b981]" : "bg-[#374151]"
        }`}
    >
        <div className={`absolute h-[12px] w-[12px] rounded-full bg-white top-[2px] transition-all ${
            config.aimEnabled ? "left-[18px]" : "left-[2px]"
        }`} />
    </button>
</div>
```

**In the config-sending logic** (lines 41-79), add `aim_enabled: config.aimEnabled` to the overrides object sent to the API.

### Verification

- Toggle AIM switch in config panel — verify it reflects in store
- Start replay with AIM enabled — verify `aim_scored` event populates `aimBreakdown` state
- Start replay with AIM disabled — verify `aimBreakdown` stays empty, behavior identical to before

---

## Phase 5 — Frontend: Visual Components

**Objective:** Build B3 detail table, AIM modifier badge on AssetCard, and optional AIM panel.

### Step 5.1: Replace B3Detail in `BlockDetail.jsx` (lines 40-69)

Replace the static B3Detail with a dynamic component that reads `aimBreakdown` from `useReplayStore`:

```jsx
const B3Detail = ({ data }) => {
    const { aimBreakdown, combinedModifier } = useReplayStore();
    // If no AIM data, show disabled message
    // Otherwise: table with all 16 AIMs showing modifier, confidence, weight, reason_tag
    // Highlight active vs inactive (ACTIVE AIMs have real modifiers, others show 1.0/N/A)
    // Show combined modifier per asset at bottom
};
```

**Table columns:** AIM ID | Name | Modifier | Confidence | DMA Weight | Reason Tag | Status

Use the `modColor()` pattern from `AimRegistryPanel.jsx:87-94` for color-coding modifiers.

### Step 5.2: Add AIM modifier badge to `AssetCard.jsx`

In the header row (after the Session badge, around line 56), add a small badge showing the combined AIM modifier:

```jsx
{aimModifier && aimModifier !== 1.0 && (
    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
        aimModifier > 1.0 ? "bg-emerald-900/50 text-emerald-400" :
        "bg-red-900/50 text-red-400"
    }`}>
        AIM {aimModifier.toFixed(2)}x
    </span>
)}
```

The `aimModifier` value comes from `combinedModifier[asset_id]` in the replay store, passed as a prop.

### Step 5.3: Wire AssetCard props in `ReplayPage.jsx`

In the asset card rendering loop (line 107), pass the AIM modifier:

```jsx
<AssetCard
    key={asset}
    asset={asset}
    {...assetResults[asset]}
    aimModifier={combinedModifier[asset]}
/>
```

### Verification

- Run replay with AIM enabled → B3 detail shows dynamic table with real modifiers
- AssetCards show colored AIM badges (green >1.0, red <1.0)
- Run replay with AIM disabled → B3 detail shows "AIM scoring disabled" message
- AssetCards show no AIM badge when disabled

---

## Phase 6 — What-If Comparison + Final Verification

**Objective:** Enable A/B comparison (AIM on vs off) using existing `comparison` state. Full verification.

### Step 6.1: Add Compare button

In `ReplayConfigPanel.jsx` or `ReplaySummary`, add a "Compare without AIMs" button that:
1. Takes the current replay config
2. Runs a second replay with `aim_enabled: false`
3. Stores the result in `comparison` state via `setComparison()`
4. `WhatIfComparison` component (already in right column at `ReplayPage.jsx:122`) displays the delta

**Implementation note:** The existing `WhatIfComparison` component and `comparison` store field were designed for this pattern. Verify its current rendering logic and adapt if needed.

### Step 6.2: Run full test suite

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

All 95 tests must pass (64 block-level + others).

### Step 6.3: Docker rebuild and manual test

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-command captain-gui
```

Manual verification:
1. Open GUI at `http://localhost`
2. Go to Replay page
3. Enable AIM toggle, select date 2026-03-28, NY session
4. Run replay — verify:
   - `aim_scored` event appears in pipeline stepper (B3 stage lights up)
   - B3 detail shows real AIM breakdown table
   - AssetCards show AIM modifier badges
   - ES has non-trivial modifiers (has IV/RV + skew data)
   - Other assets have fewer active AIMs (less data)
5. Disable AIM toggle, re-run — verify identical to pre-change behavior
6. Click "Compare without AIMs" — verify P&L delta shown

### Step 6.4: Verify no regressions

- Live system (captain-online) still imports from b3_aim_aggregation.py → re-exports from shared/aim_compute.py → identical behavior
- Replay without AIM enabled → `aim_mod = 1.0` → identical to current behavior
- No changes to `config/` or `shared/constants.py`
- All timestamps America/New_York

---

## Execution Order Summary

| Phase | Files Created/Modified | Estimated Effort |
|-------|----------------------|------------------|
| **1** | `shared/aim_compute.py` (new), `b3_aim_aggregation.py` (refactor), 4 test files (mock paths) | Backend, ~1 hour |
| **2** | `shared/aim_feature_loader.py` (new) | Backend, ~2 hours |
| **3** | `shared/replay_engine.py` (modify), `b11_replay_runner.py` (modify), API handler (modify) | Backend, ~1 hour |
| **4** | `replayStore.js` (modify), `ReplayConfigPanel.jsx` (modify) | Frontend, ~1 hour |
| **5** | `BlockDetail.jsx` (modify), `AssetCard.jsx` (modify), `ReplayPage.jsx` (modify) | Frontend, ~1.5 hours |
| **6** | `WhatIfComparison` (verify/adapt), full test run, Docker rebuild | Verification, ~1 hour |

**Total:** ~7.5 hours across 6 phases

**Start with Phase 1** — it's the foundation and immediately verifiable via tests.
