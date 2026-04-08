# Replay Engine Spec Compliance Plan

**Goal:** Implement all 20 fixes from `docs/REPLAY_VS_SPEC_GAP_ANALYSIS.md` to bring `shared/replay_engine.py` into compliance with the V3 authoritative specification.

**Primary file:** `shared/replay_engine.py` (1284 lines)
**Supporting files:** `shared/aim_compute.py`, `captain-gui/src/stores/replayStore.js`

---

## Phase 0: Documentation Discovery (Complete)

### Key Findings

#### A. Regime Probability — Simpler Than Expected
All 10 active assets use `regime_model_type: "BINARY_ONLY"` with `regime_label: "REGIME_NEUTRAL"` (from `bootstrap_production.py:101-102`). Live B2 (`b2_regime_probability.py:150-154`) also returns 0.5/0.5 for REGIME_NEUTRAL assets. **Current replay output matches live for all current assets**, but the infrastructure must be installed for when Pettersson thresholds or trained classifiers become available.

Regime model fields are stored inside the `locked_strategy` JSON blob in D00 — already loaded by `load_replay_config()` at line 75. No new QuestDB query needed; just parse from the existing strategy dict.

#### B. Robust Kelly — Small, Self-Contained Functions
`get_return_bounds()` (b1_features.py:450-464) and `compute_robust_kelly()` (b1_features.py:467-480) are ~30 lines total. They depend only on `math.sqrt`. Can be copied directly into `replay_engine.py` or into `shared/statistics.py`.

#### C. Correlation Matrix — D07 Table Exists
`p3_d07_correlation_model_states` stores `correlation_matrix` as JSON string (`init_questdb.py:215-219`). The correlation filter in live B5 (`b5_trade_selection.py:70-89`) uses threshold 0.7 from `user_silo.correlation_threshold`. Known high-correlation pairs: ES/MES, NQ/MNQ, ZB/ZN.

#### D. Quality Gate — D03 Has Trade Count
`b5b_quality_gate.py` needs `trade_count` from D03 per asset, `hard_floor` (0.003) and `quality_ceiling` (0.010) from D17. Formula: `quality_score = edge * modifier * data_maturity`.

#### E. CB Parameters — D25 Available
`p3_d25_circuit_breaker` stores `r_bar`, `beta_b`, `sigma`, `rho_bar`, `n_observations`, `p_value` per (account_id, model_m). Cold-start: `n_observations=0` → L3/L4 disabled (matching current live behavior).

#### F. Intraday State — Must Be Simulated
Live tracks `L_t` (cumulative PnL), `n_t` (trade count), `L_b` (per-basket PnL) in D23. Replay has no D23 — must simulate these as running accumulators during the replay loop.

### Allowed APIs (Data Already Loaded or Loadable)

| Data | Source | Already in config? | Action needed |
|------|--------|-------------------|---------------|
| Regime model type | D00 `locked_strategy` JSON | YES (parsed) | Extract `regime_model_type`, `regime_label` |
| Pettersson threshold | D00 `locked_strategy` JSON | YES (parsed) | Extract if present |
| Kelly params (per regime) | D12 | YES | Already keyed by (asset, regime, session) |
| EWMA states (win_rate, avg_win, avg_loss) | D05 | YES | Already keyed by (asset, regime, session) |
| User capital, max_positions | D16 | YES | Already loaded |
| TSM state (drawdown, risk_goal, pass_prob) | D08 | YES | Already loaded |
| Topstep params (c, e) | D08 `topstep_params` | YES | Already loaded |
| Correlation matrix | D07 | NO | Add query to `load_replay_config()` |
| Trade count (per asset) | D03 | NO | Add query to `load_replay_config()` |
| CB params (r_bar, beta_b, ...) | D25 | NO | Add query to `load_replay_config()` |
| Quality thresholds | D17 | NO | Add query or hardcode defaults |
| User Kelly ceiling | D16 `risk_allocation` | PARTIAL | Extract from existing D16 load |
| Fee schedule | D08 `fee_schedule` | YES | Already in TSM dict |

### Anti-Patterns to Avoid

1. **Do NOT instantiate XGBoost classifiers** — all current assets are BINARY_ONLY/REGIME_NEUTRAL. Build the code path but don't import sklearn/xgboost.
2. **Do NOT invent new WebSocket events** — use existing event names (`sizing_complete`, `replay_complete`) with added fields.
3. **Do NOT create new config parameter names** that conflict with existing ones — all new params must have defaults so old configs work.
4. **Do NOT write to QuestDB** from the replay engine — replay is read-only by design.
5. **Do NOT break the `run_whatif()` signature** — it must still accept `(config, cached_bars, original_results, target_date, sessions)`.

---

## Phase 1: Core Accuracy (P0 — 2 Gaps)

### Task 1.1: Replace Flat 0.5/0.5 Regime Blend with Actual Regime Probability

**Gap:** #1 (P0) — `replay_engine.py:671-683`
**Port from:** `b2_regime_probability.py:30-193`

#### What to change

In `compute_contracts()` at line 671, replace the hardcoded 0.5/0.5 blend:

```python
# CURRENT (line 671-683):
blended = 0.5 * low_kelly + 0.5 * high_kelly

# NEW:
regime_probs = config.get("regime_probs", {}).get(asset_id, {"LOW_VOL": 0.5, "HIGH_VOL": 0.5})
blended = sum(regime_probs.get(regime, 0.0) * kelly for regime, kelly in [("LOW_VOL", low_kelly), ("HIGH_VOL", high_kelly)])
```

#### Where regime_probs comes from

Add a new helper function `_compute_regime_probs()` that:

1. Reads `regime_model_type` and `regime_label` from `strategy` dict (already loaded from D00 `locked_strategy`)
2. For `BINARY_ONLY` assets with `pettersson_threshold`:
   - Compute realized vol from the session bars (if available) or from EWMA states
   - Compare to `pettersson_threshold`
   - Return `{HIGH_VOL: 1.0, LOW_VOL: 0.0}` or `{HIGH_VOL: 0.0, LOW_VOL: 1.0}`
3. For `REGIME_NEUTRAL` or missing data:
   - Return `{HIGH_VOL: 0.5, LOW_VOL: 0.5}` (matches live B2 behavior at line 153-154)
4. Set `regime_uncertain = (max(probs.values()) < 0.6)` (per spec PG-22 and `b2_regime_probability.py:76-77`)

**Call site:** In `run_replay()` before the per-asset loop (around line 976), compute regime_probs for all assets and store in config:

```python
config["regime_probs"] = {}
config["regime_uncertain"] = {}
for asset_id in active_assets:
    strategy = strategies.get(asset_id, {})
    probs, uncertain = _compute_regime_probs(asset_id, strategy, config)
    config["regime_probs"][asset_id] = probs
    config["regime_uncertain"][asset_id] = uncertain
```

#### Data dependency

- `strategy` dict: already loaded from D00 at line 72-97. Contains `regime_model_type`, `regime_label`, `pettersson_threshold` inside the `locked_strategy` JSON.
- EWMA states: already loaded at lines 116-136. Can compute realized vol proxy from `avg_win`/`avg_loss` statistics.
- Session bars: available if regime computation runs after bar fetching (or use pre-computed EWMA as proxy).

#### Fallback behavior

If regime data is unavailable (no pettersson_threshold, no classifier), default to `{HIGH_VOL: 0.5, LOW_VOL: 0.5}` with `regime_uncertain = True`. This matches live B2 fallback and current replay behavior.

**Complexity:** Medium
**Lines changed:** ~40 new, ~5 modified

---

### Task 1.2: Fix Position Limit to Rank by Expected Edge

**Gap:** #2 (P0) — `replay_engine.py:814-844`
**Port from:** `b5_trade_selection.py:51-67`

#### What to change

In `apply_position_limit()` at line 830, replace sort key:

```python
# CURRENT (line 830):
eligible.sort(key=lambda x: abs(x.get("pnl_per_contract", 0)), reverse=True)

# NEW — rank by forward-looking expected edge:
def _expected_edge(result, config):
    asset_id = result.get("asset_id")
    regime_probs = config.get("regime_probs", {}).get(asset_id, {"LOW_VOL": 0.5, "HIGH_VOL": 0.5})
    dominant_regime = max(regime_probs, key=regime_probs.get)
    ewma_states = config.get("ewma_states", {})
    session_id = result.get("session_id", 1)
    ewma = ewma_states.get((asset_id, dominant_regime, session_id), {})
    wr = ewma.get("win_rate", 0.5)
    avg_win = ewma.get("avg_win", 0.0)
    avg_loss = ewma.get("avg_loss", 0.0)
    return wr * avg_win - (1 - wr) * avg_loss

eligible.sort(key=lambda x: _expected_edge(x, config), reverse=True)
```

#### Signature change

`apply_position_limit()` currently takes `(results, max_positions)`. Must add `config` parameter:

```python
# CURRENT:
def apply_position_limit(results: list[dict], max_positions: int) -> tuple[list[dict], list[dict]]:

# NEW:
def apply_position_limit(results: list[dict], max_positions: int, config: dict | None = None) -> tuple[list[dict], list[dict]]:
```

Default `config=None` preserves backward compatibility — if None, fall back to current abs(pnl_per_contract) sort.

#### Call sites to update

1. `run_replay()` line ~1098: pass `config` to `apply_position_limit()`
2. `run_whatif()` line ~1240: pass `config` to `apply_position_limit()`

#### Store expected_edge in result dict

After computing, store `expected_edge` in each result dict so it's visible in the WebSocket events and GUI:

```python
result["expected_edge"] = _expected_edge(result, config)
```

**Formula reference:** `b5_trade_selection.py:57`: `edge = wr * avg_win - (1 - wr) * avg_loss`

**Complexity:** Low
**Lines changed:** ~25 new, ~8 modified

---

### Phase 1 Verification

1. **Regression test:** Run replay for a known date. Confirm it completes without error. WebSocket events still fire in same order with same event names.
2. **Regime check:** For all current assets (REGIME_NEUTRAL), verify `regime_probs` output is `{HIGH_VOL: 0.5, LOW_VOL: 0.5}` — matching previous behavior.
3. **Edge ranking check:** Compare old sort order (by abs pnl) vs new sort order (by expected edge). Log both to confirm they differ when expected. The selected/excluded assets may change.
4. **What-if still works:** Run a what-if after replay. Confirm it uses expected_edge ranking too.

---

## Phase 2: Signal Filtering (P1 — 4 Gaps)

### Task 2.1: Implement Quality Gate (B5B)

**Gap:** #3 (P1) — entirely missing
**Port from:** `b5b_quality_gate.py:28-98`

#### New function

Add `_apply_quality_gate()` to `replay_engine.py`:

```python
def _apply_quality_gate(results: list[dict], config: dict) -> list[dict]:
    """B5B quality gate: filter/scale trades by quality_score.
    
    Port of b5b_quality_gate.py:49-67.
    quality_score = expected_edge * aim_modifier * data_maturity
    """
    hard_floor = config.get("quality_hard_floor", 0.003)
    quality_ceiling = config.get("quality_ceiling", 0.010)
    trade_counts = config.get("trade_counts", {})  # from D03
    
    for result in results:
        if result.get("direction", 0) == 0:
            continue
        asset_id = result.get("asset_id")
        edge = result.get("expected_edge", 0.0)  # from Task 1.2
        aim_mod = result.get("aim_modifier", 1.0)
        trade_count = trade_counts.get(asset_id, 0)
        
        # Data maturity ramp (b5b_quality_gate.py:54)
        data_maturity = min(1.0, max(0.5, trade_count / 50.0))
        
        quality_score = edge * aim_mod * data_maturity
        result["quality_score"] = quality_score
        result["data_maturity"] = data_maturity
        
        if quality_score < hard_floor:
            result["quality_gate_passed"] = False
            result["original_contracts"] = result.get("contracts", 0)
            result["contracts"] = 0
            result["quality_gate_reason"] = f"score {quality_score:.6f} < floor {hard_floor}"
        else:
            result["quality_gate_passed"] = True
            # Graduated sizing multiplier (b5b_quality_gate.py:66)
            quality_mult = min(1.0, quality_score / quality_ceiling) if quality_ceiling > 0 else 1.0
            result["contracts"] = max(0, int(result.get("contracts", 0) * quality_mult))
            result["quality_multiplier"] = quality_mult
    
    return results
```

#### Data loading: trade_counts from D03

Add to `load_replay_config()` after existing queries:

```python
# Trade counts from D03 (for quality gate data maturity)
trade_counts = {}
with get_cursor() as cur:
    cur.execute(
        "SELECT asset_id, count() as cnt FROM p3_d03_trade_outcomes "
        "GROUP BY asset_id"
    )
    for r in cur.fetchall():
        trade_counts[r[0]] = r[1]
config["trade_counts"] = trade_counts
```

#### Call site

In `run_replay()`, after computing contracts for all assets but **before** `apply_position_limit()` (around line 1095):

```python
if config.get("quality_gate_enabled", True):
    results = _apply_quality_gate(results, config)
```

**New config parameter:** `quality_gate_enabled` (default `True`)

**Complexity:** Medium
**Lines changed:** ~50 new, ~5 modified

---

### Task 2.2: Implement Cross-Asset Correlation Filter

**Gap:** #4 (P1) — entirely missing
**Port from:** `b5_trade_selection.py:70-89`

#### New function

Add `_apply_correlation_filter()` to `replay_engine.py`:

```python
def _apply_correlation_filter(selected: list[dict], config: dict) -> list[dict]:
    """Reduce contracts for highly correlated pairs.
    
    Port of b5_trade_selection.py:70-89.
    For pairs with corr > threshold, halve the lower-scoring asset.
    """
    corr_threshold = config.get("correlation_threshold", 0.7)
    corr_matrix = config.get("correlation_matrix", {})
    
    # Known high-correlation pairs (fallback if D07 not populated)
    DEFAULT_CORR = {
        ("ES", "MES"): 0.99, ("MES", "ES"): 0.99,
        ("NQ", "MNQ"): 0.99, ("MNQ", "NQ"): 0.99,
        ("ZB", "ZN"): 0.85,  ("ZN", "ZB"): 0.85,
    }
    
    if not corr_matrix:
        corr_matrix = DEFAULT_CORR
    
    # Only process eligible trades (direction != 0, contracts > 0)
    eligible = [r for r in selected if r.get("direction", 0) != 0 and r.get("contracts", 0) > 0]
    
    for i, r1 in enumerate(eligible):
        for r2 in eligible[i+1:]:
            a1, a2 = r1["asset_id"], r2["asset_id"]
            corr = corr_matrix.get((a1, a2), corr_matrix.get(f"{a1}_{a2}", 0.0))
            if corr > corr_threshold:
                # Halve the lower-edge asset (b5_trade_selection.py:83-86)
                e1 = r1.get("expected_edge", 0)
                e2 = r2.get("expected_edge", 0)
                if e1 < e2:
                    r1["contracts"] = max(0, r1["contracts"] // 2)
                    r1["correlation_reduced"] = True
                    r1["correlated_with"] = a2
                else:
                    r2["contracts"] = max(0, r2["contracts"] // 2)
                    r2["correlation_reduced"] = True
                    r2["correlated_with"] = a1
    
    return selected
```

#### Data loading: correlation matrix from D07

Add to `load_replay_config()`:

```python
# Correlation matrix from D07 (for cross-asset filter)
correlation_matrix = {}
try:
    with get_cursor() as cur:
        cur.execute(
            "SELECT correlation_matrix FROM p3_d07_correlation_model_states "
            "ORDER BY last_updated DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row and row[0]:
            correlation_matrix = json.loads(row[0]) if isinstance(row[0], str) else row[0]
except Exception:
    pass  # D07 may not be populated yet
config["correlation_matrix"] = correlation_matrix
```

#### Call site

In `run_replay()`, after `apply_position_limit()` returns selected trades (around line 1100):

```python
if config.get("correlation_filter_enabled", True):
    selected = _apply_correlation_filter(selected, config)
```

**New config parameter:** `correlation_filter_enabled` (default `True`)

**Complexity:** Medium
**Lines changed:** ~45 new, ~10 modified

---

### Task 2.3: Fix PASS_EVAL Graduated Sizing — COMPLETE (2026-04-06)

**Gap:** #5 (P1) — `replay_engine.py:692-698`
**Port from:** `b4_kelly_sizing.py:305-317`

#### What to change

In `compute_contracts()` at line 692:

```python
# CURRENT (line 692-698):
if risk_goal == "PASS_EVAL":
    kelly_with_aim *= 0.7

# NEW — graduated by pass_probability (b4_kelly_sizing.py:305-317):
if risk_goal == "PASS_EVAL":
    pass_prob = config.get("_tsm", {}).get("pass_probability", 0.6)
    if pass_prob < 0.5:
        kelly_with_aim *= 0.5
    elif pass_prob < 0.7:
        kelly_with_aim *= 0.7
    else:
        kelly_with_aim *= 0.85
elif risk_goal == "PRESERVE_CAPITAL":
    kelly_with_aim *= 0.5
# GROW_CAPITAL: kelly_with_aim unchanged (multiplier = 1.0)
```

#### Data dependency

`pass_probability` is already in `_tsm` dict loaded from D08 at line 162. No new query needed. If not present, default 0.6 gives the middle tier (0.7x), matching current behavior.

**Complexity:** Low
**Lines changed:** ~8 modified

---

### Task 2.4: Fix budget_divisor Computation — COMPLETE (2026-04-06)

**Gap:** #6 (P1) — `replay_engine.py:232`
**Port from:** `b4_kelly_sizing.py:331-341`

#### What to change

In `load_replay_config()` around line 232 where `budget_divisor` is set:

```python
# CURRENT (line 232):
config['budget_divisor'] = 20

# NEW — compute from remaining eval days (b4_kelly_sizing.py:331-341):
eval_end = config.get("_tsm", {}).get("evaluation_end_date")
if eval_end:
    try:
        if isinstance(eval_end, str):
            eval_end = date.fromisoformat(eval_end)
        remaining = (eval_end - date.today()).days
        config['budget_divisor'] = max(remaining, 1)
    except (ValueError, TypeError):
        config['budget_divisor'] = 20  # fallback
else:
    config['budget_divisor'] = 20  # no end date → default
```

Also respect overrides — if user explicitly sets `budget_divisor` in config overrides, honor that value (existing override logic at line 254-262 handles this).

**Complexity:** Low
**Lines changed:** ~12 modified

---

### Phase 2 Verification

1. **Quality gate test:** Replay a date. Verify some trades now show `quality_gate_passed: false` with `contracts: 0`. Confirm `quality_score` and `data_maturity` appear in results.
2. **Correlation filter test:** Replay a date where ES and MES both have signals. Confirm the lower-edge one gets halved.
3. **PASS_EVAL test:** Override `risk_goal: "PASS_EVAL"` and `pass_probability: 0.4` in config. Verify multiplier is 0.5 (not 0.7).
4. **budget_divisor test:** Override `evaluation_end_date` to 5 days from now. Verify `budget_divisor` is 5 (not 20).
5. **Backward compatibility:** Replay with no overrides still works. Default params produce same behavior as before for GROW_CAPITAL risk_goal.

---

## Phase 3: Risk Controls (P1 — 6 Gaps) — COMPLETE (2026-04-06)

### Task 3.1: Implement Portfolio Risk Cap (Kelly Step 7)

**Gap:** #7 (P1) — entirely missing
**Port from:** `b4_kelly_sizing.py:236-247`

#### New function

Add `_apply_portfolio_risk_cap()` to `replay_engine.py`:

```python
def _apply_portfolio_risk_cap(results: list[dict], config: dict) -> list[dict]:
    """PG-24 Step 7: Scale down all contracts if total risk exceeds portfolio cap.
    
    Port of b4_kelly_sizing.py:236-247.
    total_risk = Σ(contracts × SL_distance × point_value) across all trades
    """
    max_pct = config.get("max_portfolio_risk_pct", 0.05)  # 5% default
    user_capital = config.get("user_capital", 150000.0)
    max_risk = max_pct * user_capital
    strategies = config.get("strategies", {})
    specs = config.get("specs", {})
    
    # Sum risk of all active trades
    total_risk = 0.0
    active = []
    for r in results:
        if r.get("direction", 0) != 0 and r.get("contracts", 0) > 0:
            asset_id = r["asset_id"]
            sl_dist = strategies.get(asset_id, {}).get("threshold", 4)
            pv = specs.get(asset_id, {}).get("point_value", 50.0)
            risk = r["contracts"] * sl_dist * pv
            total_risk += risk
            active.append(r)
    
    if total_risk > max_risk and total_risk > 0:
        scale = max_risk / total_risk
        for r in active:
            original = r["contracts"]
            r["contracts"] = max(0, int(r["contracts"] * scale))
            if r["contracts"] < original:
                r["portfolio_risk_scaled"] = True
                r["portfolio_scale_factor"] = scale
    
    return results
```

#### Call site

In `run_replay()`, after position limit and correlation filter, before final summary:

```python
if config.get("portfolio_risk_cap_enabled", True):
    selected = _apply_portfolio_risk_cap(selected, config)
```

**New config parameter:** `max_portfolio_risk_pct` (default `0.05`)

**Complexity:** Medium
**Lines changed:** ~35 new, ~3 modified

---

### Task 3.2: Implement CB L2 Budget Exhaustion

**Gap:** #8 (P1) — entirely missing
**Port from:** `b5c_circuit_breaker.py:292-321`

#### Implementation

Add L2 check inside `compute_contracts()` after existing L1 check (line 783):

```python
# --- CB L2: Budget exhaustion (b5c_circuit_breaker.py:292-321) ---
if cb_enabled:
    p = topstep_params.get("p", 0.005)
    mdd_pct_val = config.get("mdd_limit", 4500.0)
    phi = config.get("_tsm", {}).get("fee_per_trade", 2.80)
    denominator = mdd_pct_val * p + phi
    N_budget = int((e * user_capital) / denominator) if denominator > 0 else 999
    n_t = config.get("_intraday_trade_count", 0)
    cb_l2_blocked = (n_t >= N_budget)
    if cb_l2_blocked and final > 0:
        final = 0
```

Also add to output dict: `cb_l2_blocked`, `cb_l2_N_budget`, `cb_l2_n_t`.

#### Intraday counter

In `run_replay()`, track trade count as results are computed:

```python
intraday_trade_count = 0
# ... in per-asset loop, after sizing:
if result["direction"] != 0 and result["contracts"] > 0:
    intraday_trade_count += 1
config["_intraday_trade_count"] = intraday_trade_count
```

**Complexity:** Medium
**Lines changed:** ~20 new, ~5 modified

---

### Task 3.3: Implement CB L3 Basket Expectancy

**Gap:** #9 (P1) — entirely missing
**Port from:** `b5c_circuit_breaker.py:324-368`

#### Data loading: CB params from D25

Add to `load_replay_config()`:

```python
# CB basket parameters from D25
cb_params = {}
try:
    with get_cursor() as cur:
        cur.execute(
            "SELECT account_id, model_m, r_bar, beta_b, sigma, rho_bar, "
            "n_observations, p_value "
            "FROM p3_d25_circuit_breaker ORDER BY last_updated DESC"
        )
        seen = set()
        for r in cur.fetchall():
            key = (r[0], r[1])
            if key in seen:
                continue
            seen.add(key)
            cb_params[key] = {
                "r_bar": r[2] or 0.0,
                "beta_b": r[3] or 0.0,
                "sigma": r[4] or 0.0,
                "rho_bar": r[5] or 0.0,
                "n_observations": r[6] or 0,
                "p_value": r[7] or 1.0,
            }
except Exception:
    pass
config["cb_params"] = cb_params
```

#### Implementation

Add L3 check after L2 in `compute_contracts()`:

```python
# --- CB L3: Basket expectancy (b5c_circuit_breaker.py:324-368) ---
if cb_enabled and final > 0:
    account_id = config.get("_tsm", {}).get("account_id", "20319811")
    model_m = strategy.get("m", 0)
    bp = config.get("cb_params", {}).get((account_id, model_m), {})
    n_obs = bp.get("n_observations", 0)
    
    cb_l3_blocked = False
    if n_obs > 0:
        r_bar = bp.get("r_bar", 0.0)
        beta_b = bp.get("beta_b", 0.0)
        p_val = bp.get("p_value", 1.0)
        
        # Significance gate (b5c_circuit_breaker.py:345-347)
        if p_val > 0.05 or n_obs < 100:
            beta_b = 0.0
        
        l_b = config.get("_intraday_basket_pnl", {}).get(str(model_m), 0.0)
        mu_b = r_bar + beta_b * l_b
        
        if mu_b <= 0 and beta_b > 0:
            cb_l3_blocked = True
            final = 0
```

#### Intraday basket PnL tracker

In `run_replay()` per-asset loop, after ORB simulation:

```python
# Track per-basket PnL for CB L3
basket_pnl = config.get("_intraday_basket_pnl", {})
model_m = str(strategy.get("m", 0))
if result.get("direction", 0) != 0:
    basket_pnl[model_m] = basket_pnl.get(model_m, 0.0) + result.get("total_pnl", 0.0)
config["_intraday_basket_pnl"] = basket_pnl
```

**Note:** During cold-start (n_observations=0), L3 is a no-op — matches live behavior. This is the current system state per D25 bootstrap.

**Complexity:** Medium
**Lines changed:** ~40 new, ~10 modified

---

### Task 3.4: Implement Robust Kelly Fallback (Step 3)

**Gap:** #10 (P1) — entirely missing
**Port from:** `b1_features.py:450-480`
**Depends on:** Task 1.1 (regime_probs and regime_uncertain)

#### Copy utility functions

Copy `get_return_bounds()` and `compute_robust_kelly()` from `b1_features.py:450-480` into `replay_engine.py` (or `shared/statistics.py` if preferred). These are pure math functions with no dependencies beyond `math.sqrt`:

```python
def _get_return_bounds(ewma_state: dict) -> tuple[float, float]:
    """Paper 218: uncertainty set bounds from EWMA statistics."""
    wr = ewma_state.get("win_rate", 0.5)
    avg_win = ewma_state.get("avg_win", 0.0)
    avg_loss = ewma_state.get("avg_loss", 0.0)
    mu = avg_win * wr - avg_loss * (1 - wr)
    variance = avg_win ** 2 * wr + avg_loss ** 2 * (1 - wr) - mu ** 2
    sigma = math.sqrt(max(0, variance))
    return (mu - 1.5 * sigma, mu + 1.5 * sigma)

def _compute_robust_kelly(return_bounds: tuple[float, float], standard_kelly: float = 0.0) -> float:
    """Paper 218: min-max robust Kelly."""
    lower, upper = return_bounds
    if lower <= 0:
        return 0.3 * standard_kelly
    if upper * lower == 0:
        return 0.0
    robust_f = lower / (upper * lower)
    return max(0.0, min(robust_f, 0.5))
```

#### Integration into compute_contracts()

After shrinkage (line ~686) and before AIM modifier:

```python
# Step 3: Robust Kelly fallback (b4_kelly_sizing.py:129-138)
regime_uncertain = config.get("regime_uncertain", {}).get(asset_id, False)
if regime_uncertain:
    dominant_regime = max(regime_probs.items(), key=lambda x: x[1])[0]
    ewma_key = (asset_id, dominant_regime, session_id)
    ewma = ewma_states.get(ewma_key, {})
    bounds = _get_return_bounds(ewma)
    robust = _compute_robust_kelly(bounds, adjusted)
    adjusted = min(adjusted, robust)
```

**Complexity:** Low (functions are self-contained)
**Lines changed:** ~25 new, ~5 modified

---

### Task 3.5: Fix What-If AIM Recompute

**Gap:** #11 (P1) — `replay_engine.py:1160-1284`
**Port from:** internal — pass existing AIM data through

#### What to change

In `run_whatif()`, the AIM modifiers from the original replay are not passed to `compute_contracts()`. Fix by:

1. Accept `original_aim_modifiers` in the what-if config or extract from original results:

```python
# In run_whatif(), before per-asset loop:
aim_modifiers = {}
if config.get("aim_enabled", False):
    # Extract AIM modifiers from original results
    for r in original_results.get("results", []):
        asset_id = r.get("asset_id")
        if asset_id:
            aim_modifiers[asset_id] = r.get("aim_modifier", 1.0)
```

2. Pass to `compute_contracts()`:

```python
sizing = compute_contracts(
    ...,
    aim_modifier=aim_modifiers.get(asset_id, 1.0),
)
```

**Complexity:** Low
**Lines changed:** ~10 new, ~3 modified

---

### Task 3.6: Fix CB L1 L_t Accumulator

**Gap:** #12 (P1) — `replay_engine.py:773`
**Port from:** `b5c_circuit_breaker.py:259-289`

#### What to change

In `compute_contracts()` at line 773, the CB L1 check ignores L_t:

```python
# CURRENT (line 773):
rho_j = final * fallback_risk
if cb_enabled and rho_j >= l_halt and final > 0:

# NEW — include L_t (b5c_circuit_breaker.py:273-275):
l_t = abs(config.get("_intraday_cumulative_pnl", 0.0))
rho_j = final * (fallback_risk + config.get("_fee_per_trade", 0.0))
if cb_enabled and (l_t + rho_j >= l_halt) and final > 0:
```

#### Intraday P&L accumulator

In `run_replay()` per-asset loop, after ORB simulation produces a PnL result:

```python
# Track cumulative intraday P&L for CB L1
if result.get("direction", 0) != 0:
    cumulative = config.get("_intraday_cumulative_pnl", 0.0)
    cumulative += result.get("total_pnl", 0.0)
    config["_intraday_cumulative_pnl"] = cumulative
```

Initialize before the loop: `config["_intraday_cumulative_pnl"] = 0.0`

**Complexity:** Medium
**Lines changed:** ~10 new, ~5 modified

---

### Phase 3 Verification

1. **Portfolio risk cap:** Replay a date with many signals. Override `max_portfolio_risk_pct: 0.01` (very low). Verify contracts are scaled down. Check `portfolio_risk_scaled` flag in results.
2. **CB L2:** Override `_intraday_trade_count: 999`. Verify all trades blocked by L2. Check `cb_l2_blocked` in output.
3. **CB L3:** Only testable post-cold-start. Verify that with `n_observations: 0` (current state), L3 is a no-op. Manually inject `n_observations: 200, beta_b: 0.5, r_bar: 10.0` and negative `_intraday_basket_pnl` to trigger block.
4. **Robust Kelly:** Set `regime_uncertain: True` for an asset. Verify `adjusted_kelly` is capped by robust Kelly value.
5. **What-if AIM:** Run replay with `aim_enabled: True`, then what-if. Verify `aim_modifier` appears in what-if sizing output.
6. **CB L1 with L_t:** Inject `_intraday_cumulative_pnl: 500.0`. Verify L1 triggers sooner (lower rho_j needed to breach threshold).
7. **Cold-start safety:** With default D25 data (n_observations=0, beta_b=0), verify L3 and L4 are no-ops. Replay output should match pre-Phase-3 output when CB params are cold-start.

---

## Phase 4: Polish (P2 — 8 Gaps) — COMPLETE (2026-04-06)

### Task 4.1: Add User Kelly Ceiling (Step 5) — COMPLETE (2026-04-06)

**Gap:** #13 (P2) — `compute_contracts()` missing Step 5
**Port from:** `b4_kelly_sizing.py:144-145`

In `compute_contracts()`, after AIM modifier (line ~690) and before risk goal adjustment:

```python
# Step 5: User Kelly ceiling (b4_kelly_sizing.py:144-145)
user_kelly_ceiling = config.get("user_kelly_ceiling", 0.25)
kelly_with_aim = min(kelly_with_aim, user_kelly_ceiling)
```

**Lines changed:** 2 new

---

### Task 4.2: Add Fee to risk_per_contract — COMPLETE (2026-04-06)

**Gap:** #15 (P2) — `replay_engine.py:722`
**Port from:** `b4_kelly_sizing.py:422-440`

```python
# CURRENT (line 722):
risk_per_contract = avg_loss

# NEW:
fee = config.get("_tsm", {}).get("fee_per_trade", 2.80)
risk_per_contract = avg_loss + fee
```

Store fee for CB L1 use: `config["_fee_per_trade"] = fee`

**Lines changed:** 3 modified

---

### Task 4.3: Implement CB L4 Conditional Sharpe — COMPLETE (2026-04-06)

**Gap:** #14 (P2) — entirely missing
**Port from:** `b5c_circuit_breaker.py:371-433`

Add after L3 in `compute_contracts()`:

```python
# --- CB L4: Correlation-adjusted Sharpe (b5c_circuit_breaker.py:371-433) ---
if cb_enabled and final > 0 and n_obs >= 100:
    sigma_cb = bp.get("sigma", 0.0)
    rho_bar = bp.get("rho_bar", 0.0)
    n_t = config.get("_intraday_trade_count", 0)
    lambda_threshold = topstep_params.get("lambda", 0.0)
    
    if sigma_cb > 0:
        denom = sigma_cb * math.sqrt(1.0 + 2.0 * n_t * max(rho_bar, 0.0))
        S = mu_b / denom if denom > 0 else 0.0
        if S <= lambda_threshold:
            cb_l4_blocked = True
            final = 0
```

**Lines changed:** ~15 new

---

### Task 4.4: Fix B5C Pipeline Stage in GUI — COMPLETE (2026-04-06)

**Gap:** #16 (P2) — `replayStore.js`

In `captain-gui/src/stores/replayStore.js`, in the WebSocket message handler for `sizing_complete` event, add:

```javascript
// Set B5C stage when CB data is present
if (data.cb_enabled !== undefined) {
    set((state) => ({
        pipelineStages: {
            ...state.pipelineStages,
            B5C: {
                status: "complete",
                data: {
                    cb_l1_halt: data.cb_l1_halt,
                    cb_rho_j: data.cb_rho_j,
                    cb_blocked: data.cb_blocked,
                    cb_l2_blocked: data.cb_l2_blocked,
                    cb_l3_blocked: data.cb_l3_blocked,
                }
            }
        }
    }));
}
```

**Lines changed:** ~15 modified in replayStore.js

---

### Task 4.5: Remove Hardcoded account_id — COMPLETE (2026-04-06)

**Gap:** #17 (P2) — `replay_engine.py:162`

Replace hardcoded `'20319811'` with dynamic account_id from D16:

```python
# In load_replay_config(), after D16 query:
accounts = config.get("accounts", ["20319811"])
account_id = accounts[0] if accounts else "20319811"

# In D08 TSM query (line 162):
cur.execute(
    "SELECT ... FROM p3_d08_tsm_state WHERE account_id = %s ...",
    (account_id,)
)
```

**Lines changed:** ~5 modified

---

### Task 4.6: Add CB L0 Scaling Cap — COMPLETE (2026-04-06)

**Gap:** #18 (P2) — entirely missing
**Port from:** `b5c_circuit_breaker.py:232-256`

Add before L1 in `compute_contracts()`:

```python
# --- CB L0: Scaling cap for XFA accounts (b5c_circuit_breaker.py:232-256) ---
scaling_plan_active = config.get("_tsm", {}).get("scaling_plan_active", False)
if cb_enabled and scaling_plan_active and final > 0:
    scaling_tier_micros = config.get("_tsm", {}).get("scaling_tier_micros", 150)
    current_open_micros = config.get("_current_open_micros", 0)
    if current_open_micros + final > scaling_tier_micros:
        final = max(0, scaling_tier_micros - current_open_micros)
        cb_l0_blocked = (final == 0)
```

**Lines changed:** ~10 new

---

### Task 4.7: Fix ORB Simultaneous Breach Tiebreaker — COMPLETE (2026-04-06)

**Gap:** #19 (P2) — `replay_engine.py:537-566`

In `simulate_orb()`, at the breakout detection logic:

```python
# CURRENT: checks high > or_high first (LONG bias)
# NEW: if both levels breached in same bar, pick by penetration magnitude
if high > or_high and low < or_low:
    high_pen = high - or_high
    low_pen = or_low - low
    if high_pen >= low_pen:
        direction = 1   # LONG
        entry_price = or_high
    else:
        direction = -1  # SHORT
        entry_price = or_low
elif high > or_high:
    direction = 1
    entry_price = or_high
elif low < or_low:
    direction = -1
    entry_price = or_low
```

**Lines changed:** ~10 modified

---

### Task 4.8: Add HMM Session Allocation (Stub) — COMPLETE (2026-04-06)

**Gap:** #20 (P2) — entirely missing
**Port from:** `b5_trade_selection.py:135-185`

During cold-start (current system state), HMM uses equal 1/3 weights per session — which is a no-op for single-session replays. Add a stub that:

1. Loads HMM state from D26 if available
2. For cold-start (`n_observations < 20`): applies equal weight (no change)
3. For warm state: applies learned session weights

```python
def _apply_hmm_session_weight(results: list[dict], config: dict) -> list[dict]:
    """Apply HMM session allocation weights. No-op during cold start."""
    hmm_state = config.get("hmm_state", {})
    n_obs = hmm_state.get("n_observations", 0)
    
    if n_obs < 20:
        return results  # Cold start: equal weights, no change
    
    session_weights = hmm_state.get("session_weights", {})
    for r in results:
        session = r.get("session_type", "NY")
        weight = session_weights.get(session, 1.0 / 3.0)
        weight = max(weight, 0.05)  # Floor at 5%
        if r.get("contracts", 0) > 0:
            r["contracts"] = max(1, int(r["contracts"] * weight))
    
    return results
```

**Lines changed:** ~20 new

---

### Phase 4 Verification

1. **Kelly ceiling:** Override `user_kelly_ceiling: 0.01`. Verify all Kelly fractions capped at 0.01.
2. **Fee deduction:** Verify `risk_per_contract` in sizing output now includes fee (~$2.80 for ES).
3. **B5C stage:** Check GUI pipeline stepper shows B5C as "complete" after sizing.
4. **Account_id:** Remove `20319811` hardcode, verify replay works with dynamically loaded account.
5. **ORB tiebreaker:** Hard to test in production (rare). Verify logic is correct by code review.
6. **HMM stub:** During cold-start, verify no change to output (no-op). Log message confirming cold-start detection.

---

## Post-Implementation Checklist

After all 4 phases:

1. **Update `docs/REPLAY_FUNCTION_MAP.md`** — mark each function's new behavior
2. **Update `docs/REPLAY_VS_SPEC_GAP_ANALYSIS.md`** — mark all 20 gaps as FIXED with implementation notes
3. **Full regression test:** Run replay for 3 different dates, compare output structure (same WebSocket events, same field names, additional fields)
4. **What-if regression:** Run what-if on all 3 dates, confirm comparison dict structure unchanged
5. **Config backward compatibility:** Run replay with empty overrides dict. Confirm all new parameters have working defaults.
6. **No QuestDB writes:** Grep replay_engine.py for INSERT/UPDATE — should find zero matches

---

## Summary: Lines of Change Estimate

| Phase | New Lines | Modified Lines | New Functions | Files Touched |
|-------|-----------|----------------|---------------|---------------|
| Phase 1 | ~65 | ~13 | 2 (`_compute_regime_probs`, `_expected_edge`) | replay_engine.py |
| Phase 2 | ~95 | ~25 | 2 (`_apply_quality_gate`, `_apply_correlation_filter`) | replay_engine.py |
| Phase 3 | ~120 | ~28 | 2 (`_get_return_bounds`, `_compute_robust_kelly`) | replay_engine.py |
| Phase 4 | ~75 | ~25 | 2 (`_apply_portfolio_risk_cap`, `_apply_hmm_session_weight`) | replay_engine.py, replayStore.js |
| **Total** | **~355** | **~91** | **8** | **2** |

## Execution Order

Phases MUST be executed in order (1→2→3→4) because:
- Phase 2 depends on `expected_edge` from Phase 1 (Task 1.2)
- Phase 3 depends on `regime_uncertain` from Phase 1 (Task 1.1) and `expected_edge` for quality gate
- Phase 4 depends on CB infrastructure from Phase 3

Each phase is independently deployable — the system works correctly after any phase boundary.
