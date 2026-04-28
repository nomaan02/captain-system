---
tags:
  - captain-audit
  - P3-online
---
# Captain Online — Full Block Pseudocode (Blocks 1–9 + 5B + Circuit Breaker)

| Field            | Value                                                                                                                                                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Document**     | Transfer Part 2 — 33                                                                                                                                                                                                    |
| **Purpose**      | Complete pseudocode for all Online blocks: data ingestion, regime, AIM aggregation, Kelly 7-layer, trade selection, quality gate, 5-layer circuit breaker, signal output, position monitoring, concentration, capacity. |
| **Last updated** | 2026-04-05                                                                                                                                                                                                              |
| **Source**       | `research/V3 P1P2P3 Edits/Program3_Online.md` (1,756 lines — key blocks incorporated)                                                                                                                                   |

## Cross-references

| Reference | Topic |
|-----------|--------|
| [[05_Captain_Online|Part 1 doc 05]] | Captain Online overview |
| [[21_Implementation_Guides|Part 2 doc 21]] | Implementation Guides (summary) |
| [[25_Fee_Payout_System|Part 2 doc 25]] | Fee Resolution & Payout |
| [[31_AIM_Individual_Specifications|Part 2 doc 31]] | AIM Individual Specifications |
| [[32_P3_Offline_Full_Pseudocode|Part 2 doc 32]] | P3 Offline Full Pseudocode |

---

**Design principles:**
- Strategy-agnostic (processes ANY validated strategy type)
- Multi-session (NY, London, APAC)
- Blocks 1–3 SHARED (computed once per session). Blocks 4–9 PER-USER
- Read-only from Offline (uses [[24_P3_Dataset_Schemas|P3-D01]], D02, D05, D08, D12 but never writes to them)

---

## Block 1 — Pre-Session Data Ingestion (PG-21)

```
P3-PG-21: "data_ingestion_A"

INPUT: session_id (NY=1, LON=2, APAC=3)

-- Step 1: Determine active assets for this session
active_assets = []
FOR EACH asset u IN P3-D00:
    IF P3-D00[u].captain_status == "ACTIVE" AND session_match(u, session_id):
        active_assets.append(u)

IF len(active_assets) == 0: RETURN empty

-- Step 1b: DATA MODERATOR — pre-ingestion sanity checks
FOR EACH asset u IN P3-D00 WHERE captain_status == "ACTIVE":

    -- Price bounds check (>5% deviation → DATA_HOLD)
    current_price = get_latest_price(u)
    prior_close = close_price(u, yesterday)
    IF prior_close > 0:
        price_deviation = abs(current_price - prior_close) / prior_close
        IF price_deviation > 0.05:
            P3-D00[u].data_quality_flag = "PRICE_SUSPECT"
            create_incident("DATA_QUALITY", "P2_HIGH", "DATA_FEED",
                           "Price for {u} deviates {price_deviation*100:.1f}%")
            P3-D00[u].captain_status = "DATA_HOLD"
            CONTINUE

    -- Volume sanity check
    current_volume = get_current_session_volume(u)
    avg_volume = avg_session_volume_20d(u)
    IF avg_volume > 0 AND current_volume == 0:
        P3-D00[u].data_quality_flag = "ZERO_VOLUME"
    ELIF avg_volume > 0 AND current_volume > avg_volume * 10:
        P3-D00[u].data_quality_flag = "VOLUME_EXTREME"
    ELSE:
        P3-D00[u].data_quality_flag = "CLEAN"

    -- Missing data check
    FOR EACH required_feature IN get_required_features(u):
        source_available = check_data_source_for_feature(u, required_feature)
        IF NOT source_available:
            P3-D00[u].data_quality_flag = "STALE_FEATURE"

    -- Timestamp validation
    IF NOT has_timezone_offset(get_latest_timestamp(u)):
        create_incident("DATA_QUALITY", "P2_HIGH", "DATA_FEED", "Missing TZ offset for {u}")
        CONTINUE

-- Step 1c: Contract roll calendar check
FOR EACH asset u IN P3-D00:
    roll_info = P3-D00[u].roll_calendar
    IF roll_info:
        days_to_roll = (roll_info.next_roll_date - today()).days
        IF days_to_roll <= 0 AND NOT roll_info.roll_confirmed:
            NOTIFY "CONTRACT ROLL: {u} today. Signals paused." priority="CRITICAL"
            P3-D00[u].captain_status = "ROLL_PENDING"
        ELIF days_to_roll <= 3:
            NOTIFY "CONTRACT ROLL: {u} in {days_to_roll} days" priority="HIGH"

-- Step 2: Load Offline outputs (read-only from QuestDB)
aim_states       = READ P3-D01
aim_weights      = READ P3-D02
ewma_states      = READ P3-D05
tsm_configs      = READ P3-D08
kelly_params     = READ P3-D12
sizing_overrides = READ P3-D12.sizing_override

-- Step 3: Load P2 outputs (read-only)
locked_strategies = READ P2-D06
regime_models     = READ P2-D07

-- Step 4: Compute per-AIM features for each asset
FOR EACH asset u IN active_assets:
    features[u].overnight_return = (open_price(u, today) / close_price(u, yesterday)) - 1

    -- AIM-01: VRP (if active)
    IF aim_states["AIM-01"].status == ACTIVE:
        features[u].vrp = compute_vrp(u)
        features[u].vrp_overnight = compute_overnight_vrp(u)

    -- AIM-04: IVTS (critical regime filter)
    features[u].ivts = vix_close_yesterday / vxv_close_yesterday

    -- AIM-15: Opening volume ratio
    or_minutes = get_or_window_minutes(locked_strategies[u].m)
    features[u].opening_volume_ratio = volume_first_N_min(u, or_minutes) / avg_volume_first_N_min(u, or_minutes)

    -- AIM-06: Economic calendar
    features[u].events_today = check_economic_calendar(today, asset=u)
    features[u].event_proximity = min_distance_to_event(features[u].events_today, session_open_time)

    -- AIM-07: COT positioning
    features[u].cot_smi = latest_smi_polarity(u)
    features[u].cot_speculator_z = speculator_z_score(u)

    -- AIM-08: Cross-asset correlation
    features[u].correlation_z = z_score(rolling_20d_correlation("ES", "CL"), trailing_252d)

    -- AIM-09: Cross-asset momentum
    features[u].cross_momentum = compute_cross_asset_momentum(u, lookback=21)

    -- AIM-03: GEX
    features[u].gex = compute_dealer_net_gamma(u)

    -- AIM-02: Skew
    features[u].pcr = compute_put_call_ratio(u)
    features[u].put_skew = compute_dotm_otm_put_spread(u)

    -- AIM-10: Calendar
    features[u].is_opex_window = is_within_opex_window(today)
    features[u].day_of_week = today.weekday()

    -- AIM-11: Regime warning
    features[u].vix_z = z_score(vix_close_yesterday, trailing_252d)
    features[u].vix_daily_change_z = z_score(abs(vix_change_today), trailing_60d_vix_changes)

    -- AIM-12: Cost estimation
    features[u].current_spread = get_live_spread(u)
    features[u].spread_z = z_score(features[u].current_spread, trailing_60d_open_spreads)

RETURN active_assets, features, all loaded states
```

Feature computation functions (compute_vrp, compute_put_call_ratio, compute_dealer_net_gamma, check_economic_calendar, etc.) are fully specified in [[31_AIM_Individual_Specifications|doc 31]] (AIM Individual Specifications) under each AIM's data source and computation logic.

---

## Block 2 — Regime Probability (PG-22)

```
P3-PG-22: "regime_probability_A"

-- SHARED: computed once per session, same result for all users

FOR EACH asset u IN active_assets:
    -- Load trained classifier from P2
    classifier = regime_models[u]    -- XGBoost / LogReg / Binary per P2 tier

    -- Build feature vector from today's data
    x_today = build_classifier_features(u, features)
    -- x_today = [f1..f14] per doc 23 (XGBoost Classifier Manual)

    -- Predict regime probabilities
    IF classifier.type == "BINARY_THRESHOLD":
        sigma_t = ewma_states[u].latest_sigma
        phi = classifier.threshold
        IF sigma_t > phi:
            regime_probs[u] = {LOW_VOL: 0.0, HIGH_VOL: 1.0}
        ELSE:
            regime_probs[u] = {LOW_VOL: 1.0, HIGH_VOL: 0.0}
    ELSE:
        probs = classifier.predict_proba(x_today)
        regime_probs[u] = {LOW_VOL: probs[0], HIGH_VOL: probs[1]}

    -- Flag regime uncertainty for robust Kelly fallback (L4)
    regime_uncertain[u] = (max(regime_probs[u].values()) < 0.6)

CACHE regime_probs → Redis
```

---

## Block 3 — AIM Aggregation (PG-23)

```
P3-PG-23: "aim_aggregation_A"

-- SHARED: computed once, same combined_modifier for all users

FOR EACH asset u IN active_assets:
    -- Step 1: Compute per-AIM modifiers (see doc 31 for each AIM's logic)
    FOR EACH aim_id IN [1..16]:
        IF aim_states[aim_id].status == ACTIVE:
            aim_output[aim_id] = compute_aim_modifier(aim_id, features, u)
        ELSE:
            aim_output[aim_id] = {modifier: 1.0, confidence: 0.0}

    -- Step 2: MoE weighted aggregation using DMA probabilities
    weighted_sum = 0.0; weight_sum = 0.0
    FOR EACH aim_id WHERE aim_weights[aim_id].inclusion_flag:
        w = aim_weights[aim_id].inclusion_probability
        m = aim_output[aim_id].modifier
        weighted_sum += m * w
        weight_sum += w

    IF weight_sum > 0:
        combined_modifier[u] = clamp(weighted_sum / weight_sum, 0.5, 1.5)
    ELSE:
        combined_modifier[u] = 1.0

    -- Step 3: AIM-16 HMM session budget weights (if active)
    IF aim_states[16].status == ACTIVE:
        session_budget_weights = hmm_inference(P3-D26, features, session_id)
    ELSE:
        session_budget_weights = {NY: 1.0, LON: 1.0, APAC: 1.0}    -- equal

    -- Step 4: Store breakdown for P3-D03 (trade outcome learning)
    aim_breakdown[u] = {aim_id: {modifier, weight, contribution} for all active aims}

CACHE combined_modifier, session_budget_weights, aim_breakdown → Redis
```

---

## Block 4 — Kelly Sizing (PG-24)

Full 7-layer pipeline — see [[21_Implementation_Guides|doc 21]] Part 3 and [[32_P3_Offline_Full_Pseudocode|doc 32]] Block 8 ([[32_P3_Offline_Full_Pseudocode|PG-15]]) for offline EWMA/Kelly updates. Online Block 4 executes layers L2–L7:

```
P3-PG-24: "kelly_sizing_A"

-- PER-USER: runs for each active user's accounts

FOR EACH user IN active_users:
    FOR EACH account ac IN user.accounts:
        FOR EACH asset u IN active_assets:
            -- L2: Blended Kelly
            f = 0.0
            FOR EACH regime IN [LOW_VOL, HIGH_VOL]:
                f += regime_probs[u][regime] * kelly_params[u][regime][session].kelly_full
            
            -- L3: Shrinkage
            f *= kelly_params[u].shrinkage_factor
            
            -- L4: Robust fallback
            IF regime_uncertain[u]:
                mu = expected_return(ewma_states[u])
                var = return_variance(ewma_states[u])
                f_robust = mu / (mu^2 + var) IF mu > 0 ELSE 0
                f = min(f, f_robust)
            
            -- L5: AIM modifier
            f *= combined_modifier[u]
            
            -- L6: Account adjustment
            risk_goal = tsm_configs[ac].classification.risk_goal
            pass_prob = tsm_configs[ac].pass_probability
            IF risk_goal == "PASS_EVAL":
                IF pass_prob < 0.5: f *= 0.5
                ELIF pass_prob < 0.7: f *= 0.7
                ELSE: f *= 0.85
            ELIF risk_goal == "PRESERVE_CAPITAL": f *= 0.5
            
            -- Sizing override from decay detection
            IF sizing_overrides[u] is not None:
                f *= sizing_overrides[u]
            
            -- L7: TSM hard constraints
            risk_per_contract = strategy_sl * point_value + get_expected_fee(ac, u)
            raw_contracts = floor(f * account_capital(ac) / risk_per_contract) IF risk_per_contract > 0 ELSE 0
            
            IF tsm_configs[ac].category STARTS_WITH "PROP":
                mdd_cap = (mdd_limit - current_dd) / risk_per_contract
                mll_cap = (mll_limit - daily_loss_used) / risk_per_contract
                cap = min(mdd_cap, mll_cap, tsm_configs[ac].max_contracts or 999)
                -- XFA scaling cap
                IF tsm_configs[ac].scaling_plan_active:
                    scaling_cap = tier_micros - current_open_micros
                    cap = min(cap, scaling_cap)
            ELSE:
                margin = margin_per_contract(u)
                cap = account_capital(ac) / (margin * 1.5)
                cap = min(cap, tsm_configs[ac].max_contracts or 999)
            
            contracts[ac][u] = max(0, min(raw_contracts, floor(cap)))
```

---

## Block 5 — Trade Selection (PG-25) + Block 5B Quality Gate (PG-25B)

```
P3-PG-25: "trade_selection_A"

-- PER-USER: allocates daily budget across assets

FOR EACH user IN active_users:
    daily_budget = compute_daily_budget(user, session_budget_weights[session_id])

    -- Rank signals by edge × contracts
    candidates = []
    FOR EACH asset u WHERE contracts[user][u] > 0:
        edge = kelly_params[u].expected_edge
        score = edge * contracts[user][u]
        candidates.append({asset: u, score, contracts: contracts[user][u]})

    candidates = sort(candidates, key=score, DESC)

    -- Top-down allocation within budget
    allocated = []; spent = 0
    FOR EACH c IN candidates:
        cost = c.contracts * risk_per_contract(c.asset)
        IF spent + cost <= daily_budget:
            allocated.append(c)
            spent += cost

    -- Quality gate (PG-25B)
    FOR EACH signal IN allocated:
        dollar_per_contract = signal.score / signal.contracts
        IF dollar_per_contract < quality_floor OR dollar_per_contract > quality_ceiling:
            REMOVE signal from allocated
```

---

## Circuit Breaker (PG-27B) — 5 Layers

```
P3-PG-27B: "circuit_breaker_screen_A"

FOR EACH signal IN allocated:
    ac = signal.account

    -- L0: Scaling cap (XFA only)
    IF tsm_configs[ac].scaling_plan_active:
        current_open_micros = sum(open_positions.micro_equivalent)
        proposed_micros = signal.contracts
        IF current_open_micros + proposed_micros > tsm_configs[ac].scaling_tier_micros:
            BLOCK signal; reason = "SCALING_CAP_EXCEEDED"
            CONTINUE

    -- L1: Preemptive halt
    rho_j = signal.contracts * (strategy_sl * point_value + get_expected_fee(ac, signal.asset))
    IF abs(P3-D23[ac].L_t) + rho_j >= P3-D08[ac].L_halt:
        BLOCK signal; reason = "PREEMPTIVE_HALT"
        CONTINUE

    -- L2: Budget check
    remaining_budget = P3-D08[ac].E - abs(P3-D23[ac].L_t)
    IF remaining_budget < rho_j:
        BLOCK signal; reason = "BUDGET_EXHAUSTED"
        CONTINUE

    -- L3: β_b expectancy (per-basket conditional)
    IF P3-D25[signal.basket].beta_b is not None:
        mu_b = P3-D25[signal.basket].r_bar + P3-D25[signal.basket].beta_b * P3-D23[ac].L_t
        IF mu_b <= 0:
            BLOCK signal; reason = "NEGATIVE_EXPECTANCY"
            CONTINUE

    -- L4: Correlated Sharpe
    basket_sharpe = rolling_basket_sharpe(signal.basket, lookback=60d)
    IF basket_sharpe < sharpe_threshold:
        BLOCK signal; reason = "LOW_BASKET_SHARPE"
        CONTINUE

    PASS signal → Block 6
```

---

## Block 6 — Signal Output (PG-26)

```
P3-PG-26: "signal_output_A"

FOR EACH passed signal:
    -- Anti-copy jitter (multi-user)
    IF multi_user_active:
        time_jitter = random_uniform(-30, +30) seconds
        size_jitter = random_choice([-1, 0, +1]) micros    -- ±1 micro from computed size
        signal.timestamp += time_jitter
        signal.contracts += size_jitter
        signal.contracts = max(1, signal.contracts)

    -- Publish via Redis pub/sub
    PUBLISH Redis channel "signals:{user_id}" → sanitised signal
    -- Sanitised = 6 fields only: asset, direction, size, TP, SL, timestamp
```

---

## Block 7 — Position Monitoring (PG-27)

```
P3-PG-27: "position_monitor_A"

-- Continuous intraday monitoring

ON trade_close(asset, account):
    -- Record outcome
    outcome = {
        asset, account, pnl, contracts, entry_price, exit_price,
        regime_at_entry, session, timestamp,
        aim_breakdown: aim_breakdown_at_entry[asset]    -- stored from Block 3
    }
    WRITE P3-D03 ← outcome

    -- Update intraday state
    P3-D23[account].L_t += outcome.pnl
    P3-D23[account].n_t += 1

    -- Resolve commission
    fee = resolve_commission(tsm_configs[account], asset, contracts)
    outcome.fee = fee

    -- Trigger Offline learning loops (async)
    PUBLISH Redis "trades" → outcome    -- picked up by Offline DMA, BOCPD, Kelly workers
```

---

## Block 8 — Net Concentration (PG-28)

```
P3-PG-28: "net_concentration_A"

-- Check after each new signal assignment
total_long = count(open_positions WHERE direction == LONG)
total_short = count(open_positions WHERE direction == SHORT)
total = total_long + total_short

IF total > 0:
    dominant_pct = max(total_long, total_short) / total
    IF dominant_pct > 0.80:
        NOTIFY "80% same-direction concentration alert" priority="HIGH"
        -- Does NOT block — advisory only
```

---

## Block 9 — Capacity Evaluation (PG-29)

```
P3-PG-29: "capacity_eval_A"

-- Run at session end

FOR EACH asset u WITH trades today:
    fills = get_fills(u, today)
    expected_prices = get_signal_prices(u, today)

    fill_quality = mean(abs(fill.price - expected.price) for fill, expected in zip)
    slippage_bps = fill_quality / mean(expected_prices) * 10000

    P3-D17.capacity[u] = {
        slippage_bps, avg_fill_time, fill_rate,
        volume_participation: our_volume / market_volume
    }

    IF slippage_bps > slippage_threshold:
        NOTIFY "Capacity concern for {u}: {slippage_bps}bps slippage" priority="MEDIUM"
```

## Audit Resolutions

> [!note] 2026-04-11 Gap Analysis — CRITICAL fixes
> The following audit resolutions reference specifications in this document:

- [[G-ONL-017_kelly_l4_formula_wrong|G-ONL-017 — Kelly L4 Formula Wrong]] (PG-24 L4) — CRITICAL RESOLVED
- [[G-ONL-042_capacity_eval_wrong_algorithm|G-ONL-042 — Capacity Eval Wrong Algorithm]] (PG-29) — CRITICAL RESOLVED
- [[G-XCT-012_crash_recovery_write_only|G-XCT-012 — Crash Recovery Write-Only]] (startup/recovery) — CRITICAL RESOLVED

## Related Canvases

- [[System 1/Backend/P3 Online.canvas|P3 Online]]
