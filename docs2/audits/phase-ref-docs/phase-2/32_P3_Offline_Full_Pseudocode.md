---
tags:
  - captain-audit
  - P3-offline
---
# Captain Offline — Full Block Pseudocode (Blocks 1–9)

| Field | Value |
|--------|--------|
| **Document** | Transfer Part 2 — 32 |
| **Purpose** | Complete pseudocode for all 9 Offline blocks with every PG program, formula, threshold, dataset R/W, edge case, and response handler. This is the authoritative implementation spec for the strategic brain. |
| **Last updated** | 2026-04-05 |
| **Source** | `research/V3 P1P2P3 Edits/Program3_Offline.md` (1,729 lines — fully incorporated) |

## Cross-references

| Reference | Topic |
|-----------|--------|
| [[04_Captain_Offline|Part 1 doc 04]] | Captain Offline overview |
| [[07_AIM_System|Part 1 doc 07]] | AIM System |
| [[08_Kelly_Sizing_Pipeline|Part 1 doc 08]] | Kelly Sizing Pipeline |
| [[21_Implementation_Guides|Part 2 doc 21]] | Implementation Guides (summary) |
| [[31_AIM_Individual_Specifications|Part 2 doc 31]] | AIM Individual Specifications (per-AIM modifier pseudocode) |

---

**NOTE:** This document contains the FULL pseudocode from the authoritative source. [[21_Implementation_Guides|Part 2 doc 21]] is a summary; this doc 32 is the complete spec. When they conflict, doc 32 governs.

**Execution modes:**
- **Scheduled:** Weekly AIM model retraining (Tier 1), monthly sensitivity scans, quarterly re-testing
- **Event-triggered:** Trade outcome received, Level 3 decay trigger, strategy injection event, TSM file change

---

## Block 1 — AIM Model Training and Management

### PG-01: aim_lifecycle_manager_A

```
FOR EACH aim a IN [AIM-01..AIM-15]:
    current_status = P3-D01[a].status

    SWITCH current_status:
        CASE INSTALLED:
            IF data_pipeline_connected(a):
                SET status = COLLECTING

        CASE COLLECTING:
            IF raw_data_count(a) > 0:
                BEGIN training
                SET status = WARM_UP

        CASE WARM_UP:
            progress = observations_collected(a) / warmup_required(a)
            UPDATE P3-D00.aim_warmup_progress[a] = progress
            IF progress >= 1.0:
                SET status = ELIGIBLE
                NOTIFY "AIM-{a} warm-up complete — eligible for activation"

        CASE ELIGIBLE:
            -- Outputs neutral modifier (1.0) until user activates via GUI
            IF user_activated(a):
                SET status = ACTIVE

        CASE ACTIVE:
            -- Normal operation — modifier flows into Captain (Online)
            IF meta_weight(a) == 0 for 20+ consecutive trades:
                SET status = SUPPRESSED
                LOG suppression event to P3-D06

        CASE BOOTSTRAPPED:
            -- Set during asset_bootstrap() for Tier 1 AIMs with sufficient historical data
            -- Skips INSTALLED→COLLECTING→WARM_UP progression
            IF user_activated(a):
                SET status = ACTIVE

        CASE SUPPRESSED:
            -- Still training, still collecting — but modifier locked at 1.0
            IF meta_weight(a) > 0.1 for 10+ consecutive trades:
                SET status = ACTIVE    -- Auto-recovery
                LOG recovery event to P3-D06

    SAVE updated status to P3-D01[a]
```

### PG-01C: aim16_hmm_train_A

See [[22_HMM_Opportunity_Regime|doc 22]] (HMM Opportunity Regime) for full AIM-16 training spec: Baum-Welch on rolling 60-day window, 240 observations, K=3 states, TVTP, smoothing α=0.3. Stores to [[24_P3_Dataset_Schemas|P3-D26]].

### PG-02: aim_dma_update_A

```
-- Called after each trade outcome is logged
-- SHARED INTELLIGENCE: learns from all qualifying trades regardless of user

INPUT: trade_outcome from P3-D03 (latest entry, includes user_id field)
INPUT: P3-D02 (current model probabilities per AIM)

lambda = 0.99    -- OPEN PARAMETER: higher = slower adaptation (0.95–0.99 range)

FOR EACH active aim a:
    -- Step 1: Compute prediction likelihood (SPEC-A9: magnitude-weighted)
    modifier_a = aim_modifier_at_trade_time(a, trade_outcome.timestamp)
    u = trade_outcome.asset
    regime = trade_outcome.regime_at_entry
    pnl_pc = trade_outcome.pnl / max(trade_outcome.contracts, 1)

    -- DMA likelihood uses regime-level EWMA stats aggregated across sessions
    IF modifier_a > 1.0:
        -- AIM said "size up"
        IF pnl_pc > 0:
            z = min(pnl_pc / max(P3-D05[u][regime].avg_win, 0.01), 3.0)
            likelihood_a = 0.5 + 0.5 * z / 3.0
        ELSE:
            z = min(abs(pnl_pc) / max(P3-D05[u][regime].avg_loss, 0.01), 3.0)
            likelihood_a = 0.5 - 0.5 * z / 3.0
    ELIF modifier_a < 1.0:
        -- AIM said "size down" — inverse
        IF pnl_pc < 0:
            z = min(abs(pnl_pc) / max(P3-D05[u][regime].avg_loss, 0.01), 3.0)
            likelihood_a = 0.5 + 0.5 * z / 3.0
        ELSE:
            z = min(pnl_pc / max(P3-D05[u][regime].avg_win, 0.01), 3.0)
            likelihood_a = 0.5 - 0.5 * z / 3.0
    ELSE:
        likelihood_a = 0.5    -- Neutral — no prediction to evaluate

    -- Step 2: Update model probability via forgetting factor
    raw_prob_a = P3-D02[a].inclusion_probability ^ lambda * likelihood_a

-- Step 3: Normalise across all active AIMs
total = SUM(raw_prob_a for all active a)
FOR EACH active aim a:
    P3-D02[a].inclusion_probability = raw_prob_a / total
    P3-D02[a].inclusion_flag = (P3-D02[a].inclusion_probability > inclusion_threshold)

SAVE P3-D02
```

### Version Snapshot Policy

```
VERSIONED_COMPONENTS = [P3-D01, P3-D02, P3-D05, P3-D12, P3-D17.system_params]

FUNCTION snapshot_before_update(component_id, trigger_reason):
    snapshot = {
        version_id:  generate_uuid(),
        component:   component_id,
        timestamp:   now(),
        trigger:     trigger_reason,
        state:       deep_copy(get_current_state(component_id)),
        model_hash:  hash(get_current_state(component_id))
    }
    P3-D18.append(snapshot)

    max_versions = P3-D17.system_params.max_versions_per_component or 50
    component_versions = P3-D18.filter(component=component_id)
    IF len(component_versions) > max_versions:
        oldest = component_versions.sort_by(timestamp).first()
        migrate_to_cold_storage(oldest)

    RETURN snapshot.version_id

FUNCTION rollback_to_version(component_id, version_id, admin_user_id):
    target = P3-D18[version_id]
    comparison = run_pseudotrader_comparison(current=get_current_state(component_id), proposed=target.state)
    NOTIFY(user_id=admin_user_id, message="Rollback comparison ready", priority="HIGH", action_required=True)
    ON admin_approval:
        snapshot_before_update(component_id, "ROLLBACK")
        restore_state(component_id, target.state)
        IF NOT run_regression_tests(): REVERT and NOTIFY "Rollback failed regression tests"
        LOG to AdminDecisionLog
```

### PG-03: aim_diversity_check_A (HDWM — Weekly)

```
seed_types = {
    "options":        [AIM-01, AIM-02, AIM-03],
    "microstructure": [AIM-04, AIM-05, AIM-15],
    "macro_event":    [AIM-06, AIM-07],
    "cross_asset":    [AIM-08, AIM-09],
    "temporal":       [AIM-10, AIM-11],
    "internal":       [AIM-12, AIM-13, AIM-14]
}

FOR EACH type IN seed_types:
    active_in_type = [a for a in seed_types[type] if P3-D01[a].status == ACTIVE]

    IF len(active_in_type) == 0:
        best_candidate = argmax(P3-D02[a].recent_effectiveness for a in seed_types[type])
        SET P3-D01[best_candidate].status = ACTIVE
        SET P3-D02[best_candidate].inclusion_probability = 1.0 / num_active_aims
        LOG "HDWM diversity recovery: reactivated AIM-{best_candidate} as seed for {type}"
```

### PG-04: aim_drift_detector_A (Daily)

```
FOR EACH active aim a:
    current_features = get_aim_input_features(a, today)
    reconstruction_error = aim_autoencoder[a].reconstruct(current_features)

    adwin_state[a].add(reconstruction_error)

    IF adwin_state[a].detected_change():
        LOG "Concept drift detected in AIM-{a} input features"
        FLAG aim a for retraining in next scheduled cycle
        P3-D02[a].inclusion_probability *= 0.5
        RENORMALISE P3-D02

SAVE P3-D04.adwin_states
```

---

## Block 2 — Strategy Decay Detection

### PG-05: bocpd_decay_monitor_A

```
-- Run after each trade outcome
-- SHARED INTELLIGENCE: monitors strategy's market-level performance

INPUT: new_trade_pnl from P3-D03

FOR EACH asset u IN active_universe:
    pnl_stream = P3-D03.filter(asset=u).pnl_values

    -- Recursive BOCPD update (Adams & MacKay 2007)
    FOR r IN range(0, max_run_length):
        predictive_prob = compute_predictive(pnl_stream, run_length=r)
        growth_prob = (1 - hazard_rate) * predictive_prob
        changepoint_prob = hazard_rate * predictive_prob
        joint_prob[r+1] = growth_prob * prior_joint[r]
        joint_prob[0] += changepoint_prob * prior_joint[r]

    evidence = SUM(joint_prob)
    posterior = joint_prob / evidence
    cp_probability = posterior[0]

    P3-D04.bocpd[u].run_length_posterior = posterior
    P3-D04.bocpd[u].cp_probability = cp_probability
    P3-D04.bocpd[u].cp_history.append(cp_probability)

    IF cp_probability > 0.8:
        TRIGGER Level_2(asset=u, severity=cp_probability, source="BOCPD")

    recent_5d = P3-D04.bocpd[u].cp_history[-5:]
    IF ALL(p > 0.9 for p in recent_5d) AND len(recent_5d) >= 5:
        TRIGGER Level_3(asset=u, source="BOCPD_sustained")

SAVE P3-D04
```

### PG-06: cusum_decay_monitor_A

```
INPUT: new_trade_pnl from P3-D03

FOR EACH asset u IN active_universe:
    pnl = new_trade_pnl[u]
    k = P3-D04.cusum[u].allowance
    h_sequential = P3-D04.cusum[u].control_limit(sprint_length=T_n)

    C_up = max(0, P3-D04.cusum[u].C_up_prev + pnl - k)
    C_down = max(0, P3-D04.cusum[u].C_down_prev - pnl - k)

    IF C_up == 0 AND C_down == 0:
        T_n = 0
    ELSE:
        T_n = P3-D04.cusum[u].sprint_length + 1

    IF C_up > h_sequential OR C_down > h_sequential:
        TRIGGER Level_2(asset=u, severity="CUSUM_breach", source="CUSUM")
        C_up = 0; C_down = 0; T_n = 0

    P3-D04.cusum[u].C_up_prev = C_up
    P3-D04.cusum[u].C_down_prev = C_down
    P3-D04.cusum[u].sprint_length = T_n

SAVE P3-D04
```

### PG-07: cusum_bootstrap_calibrate_A

```
-- Run once during initialisation, re-run quarterly
INPUT: in_control_trades from P3-D03

FOR EACH asset u:
    in_control_pnl = in_control_trades[u].pnl_values

    FOR b IN range(B=2000):
        resample = bootstrap_sample(in_control_pnl, size=len(in_control_pnl))
        FOR each sprint_length j IN range(1, max_sprint):
            cusum_values_at_j = compute_cusum_conditional_on_sprint(resample, j)
            store bootstrap distribution of [C_n | T_n = j]

    FOR j IN range(1, max_sprint):
        P3-D04.cusum[u].sequential_limits[j] = quantile(
            bootstrap_cusum_dist[j],
            percentile = 1 - 1/ARL_0    -- ARL_0 = 200
        )

SAVE P3-D04
```

### PG-08: decay_response_handler_A

```
FUNCTION Level_2(asset, severity, source):
    reduction_factor = 1.0 - (severity - 0.8) * 2.5    -- scales 0.8→1.0 to 0.5→0.0
    reduction_factor = max(0.5, reduction_factor)        -- floor at 50%

    P3-D12.sizing_override[asset] = reduction_factor

    NOTIFY_GUI("Level 2: Sizing reduced to {reduction_factor*100}% for {asset}", priority="HIGH", colour="AMBER")
    NOTIFY_TELEGRAM(priority="HIGH")
    LOG to P3-D04.decay_events

FUNCTION Level_3(asset, source):
    P3-D00[asset].captain_status = "DECAYED"

    NOTIFY_GUI("Level 3: STRATEGY REVIEW — no signals for {asset}", priority="CRITICAL", colour="RED")
    NOTIFY_TELEGRAM(priority="CRITICAL")

    SCHEDULE programs_1_2_rerun(asset)
    SCHEDULE aim14_search(asset)
    LOG to P3-D04.decay_events
```

---

## Block 3 — Post-Update Retest (Pseudotrader)

### PG-09: pseudotrader_retest_A

```
INPUT: proposed_update (AIM weight change, model retrain, or strategy injection)
INPUT: historical_window from P3-D03

-- Phase 1: Replay WITHOUT update
baseline_results = []
FOR EACH day d IN historical_window:
    signal = captain_online_replay(d, using=CURRENT_parameters)
    outcome = actual_trade_outcome(d)
    baseline_results.append({signal, outcome})

-- Phase 2: Replay WITH update
updated_results = []
FOR EACH day d IN historical_window:
    signal = captain_online_replay(d, using=PROPOSED_parameters)
    outcome = actual_trade_outcome(d)
    updated_results.append({signal, outcome})

-- Phase 3: Compare
sharpe_baseline = compute_sharpe(baseline_results)
sharpe_updated = compute_sharpe(updated_results)
sharpe_improvement = sharpe_updated - sharpe_baseline
drawdown_baseline = max_drawdown(baseline_results)
drawdown_updated = max_drawdown(updated_results)
winrate_baseline = win_rate(baseline_results)
winrate_updated = win_rate(updated_results)

-- Phase 4: Validate (anti-overfitting)
pbo = compute_CSCV_PBO(updated_results, S=16)
dsr = compute_DSR(sharpe_updated, N_trials, skew, kurtosis, T)

-- Phase 5: Store and report
P3-D11.append({
    update_type: proposed_update.type,
    sharpe_improvement, drawdown_change, winrate_delta, pbo, dsr,
    recommendation: "ADOPT" if (sharpe_improvement > 0 AND pbo < 0.5 AND dsr > 0.5) else "REJECT"
})
GENERATE RPT-09(P3-D11.latest)
```

---

## Block 4 — Strategy Injection Comparison

### PG-10: injection_comparison_A

```
INPUT: new_candidate from Programs 1/2 output
INPUT: current_strategy from P3-D00[asset].locked_strategy

-- Step 1: Contextualise — retroactive AIM analysis
FOR EACH active aim a:
    retroactive_modifiers[a] = aim_retroactive_replay(a, new_candidate, historical_window)

-- Step 2: Compute AIM-adjusted expected performance
expected_new = compute_aim_adjusted_edge(new_candidate, retroactive_modifiers)
expected_current = compute_aim_adjusted_edge(current_strategy, P3-D02)

-- Step 3: Run pseudotrader comparison
pseudo_results = pseudotrader_compare(new_candidate, current_strategy, historical_window)

-- Step 4: Decision logic
IF expected_new > expected_current * 1.2 AND pseudo_results.pbo < 0.5:
    recommendation = "ADOPT"; transition_days = 10
ELIF expected_new > expected_current * 0.9 AND expected_new < expected_current * 1.2:
    recommendation = "PARALLEL_TRACK"; tracking_days = 20
ELSE:
    recommendation = "REJECT"

-- Step 5: Store and report
P3-D06.append({asset, candidate, current, expected_new, expected_current, pseudo_results, recommendation, timestamp: now()})
GENERATE RPT-05(P3-D06.latest)
NOTIFY_GUI("New strategy candidate for {asset} — review RPT-05", priority="HIGH")
```

### PG-11: strategy_transition_A

```
INPUT: adoption_decision from Captain (Command)
INPUT: new_strategy, old_strategy

IF adoption_decision == "ADOPT":
    FOR day d IN range(1, transition_days + 1):
        weight_new = d / transition_days
        weight_old = 1 - weight_new
        signal_new = generate_signal(new_strategy, d)
        signal_old = generate_signal(old_strategy, d)
        blended_size = weight_new * signal_new.size + weight_old * signal_old.size
        OUTPUT blended_signal(direction=signal_new.direction, size=blended_size)
    P3-D00[asset].locked_strategy = new_strategy
    P3-D00[asset].captain_status = "ACTIVE"

ELIF adoption_decision == "PARALLEL_TRACK":
    FOR day d IN range(1, tracking_days + 1):
        signal_current = generate_signal(old_strategy, d)
        signal_candidate = generate_signal(new_strategy, d)    -- tracked not acted
        LOG both signals
    GENERATE RPT-05_final_comparison()

ELIF adoption_decision == "REJECT":
    LOG rejection to P3-D06
    P3-D00[asset].captain_status = "ACTIVE"
```

---

## Block 5 — AIM-13 Sensitivity Scanner (Monthly)

### PG-12: sensitivity_scanner_A

```
FOR EACH asset u IN active_universe:
    strategy = P3-D00[u].locked_strategy
    base_params = strategy.parameters

    -- Generate perturbation grid (±5%, ±10%, ±20% per parameter)
    perturbation_grid = []
    FOR EACH param p IN base_params:
        FOR delta IN [-0.20, -0.10, -0.05, 0, +0.05, +0.10, +0.20]:
            perturbed = base_params.copy()
            perturbed[p] = base_params[p] * (1 + delta)
            perturbation_grid.append(perturbed)

    results = []
    FOR EACH config IN perturbation_grid:
        perf = backtest_with_config(config, recent_oos_window)
        results.append({config, sharpe: perf.sharpe, dd: perf.max_drawdown, wr: perf.win_rate})

    sharpe_values = [r.sharpe for r in results]
    sharpe_stability = std(sharpe_values) / mean(sharpe_values)    -- CV: lower = more robust

    pbo = compute_CSCV_PBO(results, S=8)
    dsr = compute_DSR(max(sharpe_values), N_trials=len(perturbation_grid), skew, kurtosis, T)
    complexity_penalty = num_parameters(strategy) * penalty_coefficient
    adjusted_sharpe = max(sharpe_values) - complexity_penalty

    flags = []
    IF sharpe_stability > 0.5: flags.append("FRAGILE — parameter-sensitive")
    IF pbo > 0.5: flags.append("OVERFIT — likely data-mined")
    IF dsr < 0.5: flags.append("INSIGNIFICANT — insufficient evidence")

    robustness_status = "FRAGILE" if len(flags) >= 2 else "ROBUST"

    P3-D13[u] = {sharpe_stability, pbo, dsr, adjusted_sharpe, robustness_status, flags, scan_date: now()}

    IF robustness_status == "FRAGILE":
        NOTIFY_GUI("AIM-13: Strategy for {u} flagged FRAGILE — {flags}", priority="HIGH")
        P3-D01[13].current_modifier = 0.85

GENERATE RPT-03_section("AIM-13 Sensitivity Results", P3-D13)
SAVE P3-D13
```

---

## Block 6 — AIM-14 Auto-Expansion (Level 3 Trigger)

### PG-13: auto_expansion_search_A

```
INPUT: decayed_asset from Level 3 trigger
INPUT: feature_space from Program 1 feature library

-- Step 1: Define search space (theory-constrained)
candidate_params = {
    OR_window:       range(3, 15, 1),
    threshold:       range(0.05, 0.30, 0.025),
    SL_multiplier:   range(0.20, 0.50, 0.05),
    TP_multiplier:   range(0.50, 1.50, 0.10),
    features:        Program1_feature_library.top_k(k=10)
}

-- Step 2: GA search with rough set rules
population = initialise_population(candidate_params, size=100)

FOR generation IN range(50):
    FOR EACH candidate IN population:
        training_results = walk_forward_train(candidate, training_window)
        validation_results = walk_forward_validate(candidate, validation_window)
        candidate.fitness = validation_results.robust_sharpe
    population = evolve(population, selection="tournament", crossover_rate=0.8, mutation_rate=0.1)

-- Step 3: Select top candidates
top_candidates = sorted(population, key=fitness, reverse=True)[:5]

-- Step 4: Final OOS test (ONCE only)
final_candidates = []
FOR EACH candidate IN top_candidates:
    oos_result = final_oos_test(candidate, holdout_window)
    pbo = compute_CSCV_PBO(oos_result)
    dsr = compute_DSR(oos_result.sharpe, N_trials=len(population)*50)
    IF pbo < 0.5 AND dsr > 0.5:
        final_candidates.append({candidate, oos_result, pbo, dsr})

-- Step 5: Present to user (Level 3 requires human approval)
IF len(final_candidates) > 0:
    FOR EACH fc IN final_candidates:
        injection_comparison(fc.candidate, decayed_asset)
ELSE:
    NOTIFY_GUI("AIM-14: No viable replacements for {decayed_asset}. Manual intervention required.", priority="CRITICAL")
```

---

## Block 7 — TSM Simulation

### PG-14: tsm_simulation_A

```
-- Run after each trade, when TSM file changes

INPUT: P3-D08, P3-D03, P3-D12

FOR EACH account ac WITH active TSM:
    tsm = P3-D08[ac]
    risk_goal = tsm.classification.risk_goal
    trade_returns = P3-D03.filter(account=ac).pnl_values
    current_balance = tsm.current_balance
    remaining_days = tsm.evaluation_end_date - today()
    mdd_remaining = tsm.max_drawdown_limit - tsm.current_drawdown
    target_profit = tsm.profit_target - (current_balance - tsm.starting_balance)

    pass_count = 0
    N_PATHS = 10000

    FOR path IN range(N_PATHS):
        sim_balance = current_balance
        sim_max_balance = current_balance
        sim_drawdown = tsm.current_drawdown
        passed = True

        FOR day IN range(remaining_days):
            block_size = random.choice([3, 5, 7])
            start_idx = random.randint(0, len(trade_returns) - block_size)
            daily_returns = trade_returns[start_idx : start_idx + block_size]

            daily_pnl = 0
            FOR ret IN daily_returns:
                sim_balance += ret
                daily_pnl += ret
                sim_max_balance = max(sim_max_balance, sim_balance)
                sim_drawdown = sim_max_balance - sim_balance
                IF sim_drawdown > tsm.max_drawdown_limit:
                    passed = False; BREAK

            IF daily_pnl < 0 AND abs(daily_pnl) > tsm.max_daily_loss:
                passed = False
            IF NOT passed: BREAK

        IF passed AND (sim_balance - tsm.starting_balance) >= tsm.profit_target:
            pass_count += 1

    pass_probability = pass_count / N_PATHS
    P3-D08[ac].pass_probability = pass_probability

    IF risk_goal == "PASS_EVAL":
        IF pass_probability < 0.3: NOTIFY priority="CRITICAL"
        ELIF pass_probability < 0.5: NOTIFY priority="HIGH"
    ELIF risk_goal == "GROW_CAPITAL" AND tsm.max_drawdown_limit:
        ruin_probability = 1 - pass_probability
        IF ruin_probability > 0.3: NOTIFY priority="HIGH"

    IF NOT tsm.max_drawdown_limit AND NOT tsm.max_daily_loss:
        P3-D08[ac].pass_probability = None

GENERATE RPT-07(P3-D08)
SAVE P3-D08
```

---

## Block 8 — Kelly Parameter Updates

### PG-15: kelly_parameter_update_A

```
-- Run after each trade outcome

INPUT: trade_outcome from P3-D03
INPUT: P3-D05, P3-D12

u = trade_outcome.asset
regime = trade_outcome.regime_at_entry
contracts = trade_outcome.contracts
IF contracts <= 0: RETURN

pnl_per_contract = trade_outcome.pnl / contracts

IF pnl_per_contract > 0:
    win = 1; win_size = pnl_per_contract
ELSE:
    win = 0; loss_size = abs(pnl_per_contract)

-- SPEC-A12: Adaptive EWMA decay — alpha scales with BOCPD cp
cp_prob = P3-D04[u].current_changepoint_probability
IF cp_prob < 0.2:    effective_span = 30
ELIF cp_prob < 0.5:  effective_span = 20
ELIF cp_prob < 0.8:  effective_span = 12
ELSE:                effective_span = 8
alpha = 2 / (effective_span + 1)

-- SPEC-A8: Session-specific EWMA
session = trade_outcome.session    -- NY=1, LON=2, APAC=3

P3-D05[u][regime][session].win_rate = (1 - alpha) * P3-D05[u][regime][session].win_rate + alpha * win
IF win:
    P3-D05[u][regime][session].avg_win = (1 - alpha) * P3-D05[u][regime][session].avg_win + alpha * win_size
ELSE:
    P3-D05[u][regime][session].avg_loss = (1 - alpha) * P3-D05[u][regime][session].avg_loss + alpha * loss_size

-- Recompute Kelly fraction per regime per session
FOR EACH regime r IN [LOW_VOL, HIGH_VOL]:
    FOR EACH ss IN [1, 2, 3]:    -- NY, LON, APAC
        p = P3-D05[u][r][ss].win_rate
        W = P3-D05[u][r][ss].avg_win
        L = P3-D05[u][r][ss].avg_loss

        IF L > 0 AND p > 0:
            b = W / L
            kelly_full = max(0, p - (1 - p) / b)
        ELSE:
            kelly_full = 0

        P3-D12[u][r][ss].kelly_full = kelly_full

-- Shrinkage factor
N_trades = P3-D03.filter(asset=u).count()
estimation_variance = compute_estimation_variance(P3-D05[u])
shrinkage = max(0.3, 1.0 - estimation_variance)

P3-D12[u].shrinkage_factor = shrinkage
P3-D12[u].last_updated = now()

SAVE P3-D05
SAVE P3-D12
CHECKPOINT(component="OFFLINE", stage="KELLY_UPDATE_COMPLETE", asset=u)
snapshot_before_update("P3-D05", "EWMA_UPDATE")
snapshot_before_update("P3-D12", "KELLY_UPDATE")
```

### PG-16C: beta_b_estimator_A

```
-- Per-basket β_b learning (cold start n<100)

INPUT: P3-D03 trade outcomes for basket b
INPUT: P3-D25 (current β_b parameters)

FOR EACH basket b:
    trades = P3-D03.filter(basket=b)
    n = len(trades)

    IF n < 10:
        -- Insufficient data — use conservative default
        P3-D25[b].beta_b = 0.0
        P3-D25[b].r_bar = 0.0
        P3-D25[b].cold_start = True
        CONTINUE

    -- OLS regression: r_i = r_bar + beta_b * L_b_at_time_i + epsilon
    L_series = [running_loss_at_trade_time(t) for t in trades]
    r_series = [t.pnl_per_contract for t in trades]

    r_bar = mean(r_series)
    beta_b = ols_slope(r_series, L_series)

    P3-D25[b].beta_b = beta_b
    P3-D25[b].r_bar = r_bar
    P3-D25[b].n_obs = n
    P3-D25[b].cold_start = (n < 100)

    -- Compute L* (breakeven loss level): mu_b = r_bar + beta_b * L_b = 0 → L* = -r_bar / beta_b
    IF beta_b < 0:
        P3-D25[b].L_star = -r_bar / beta_b
    ELSE:
        P3-D25[b].L_star = None    -- beta_b >= 0 means no negative expectancy crossover

SAVE P3-D25
```

---

## Block 9 — System Health Diagnostic

### PG-17 / PG-16B: system_health_diagnostic_A

8 dimensions scored ∈ [0, 1]. Each may queue prioritised action items for ADMIN.

| # | Dimension | What it measures |
|---|-----------|-----------------|
| D1 | Strategy Portfolio Health | Diversity (distinct strategy types), freshness (age), weakest OO, consistency |
| D2 | Feature Portfolio Health | Feature reuse concentration, distinct features used across assets |
| D3 | Model Staleness Tracker | Days since last P1/P2 re-run per asset |
| D4 | AIM Effectiveness Portfolio | Per-AIM modifier accuracy, PnL attribution by modifier direction |
| D5 | Edge Trajectory | Monthly rolling expectancy and Sharpe trend (declining/stable/improving) |
| D6 | Data Coverage Gaps | Missing feeds, stale data per AIM and per asset |
| D7 | Research Pipeline Throughput | Pending P1/P2 runs, candidate queue depth, injection backlog |
| D8 | Resolution Verification | Did previously resolved action items actually improve the target metric? |

```
-- Run weekly (D1-D7) and monthly (D5 deep analysis)
-- Event-triggered: D8 runs when ADMIN marks action item as RESOLVED

FOR EACH dimension d IN [D1..D8]:
    d_score = evaluate_dimension(d, inputs)
    IF d_score < threshold[d]:
        QUEUE_ACTION(priority, category, dimension, constraint_type, title, detail, recommendation)

overall_health = weighted_mean(d1..d8 scores)
P3-D22 = {dimension_scores, action_queue, overall_health, timestamp}
SAVE P3-D22
```

Full dimension pseudocode (D1 example — Strategy Portfolio Health):

```
strategy_models = {}; strategy_ages = {}; oo_scores = {}

FOR EACH asset u IN P3-D00.active_assets:
    locked = P2-D06[u]
    strategy_models[u] = (locked.m, locked.k)
    strategy_ages[u] = (now() - locked.timestamp).days
    oo_scores[u] = locked.OO

type_count = len(set(strategy_models.values()))
age_max = max(strategy_ages.values())
oo_min = min(oo_scores.values())
oo_spread = max(oo_scores.values()) - oo_min

d1_score = weighted_mean([
    (1.0 if type_count >= 3 else type_count / 3.0,   0.3),
    (max(0, 1.0 - age_max / 365.0),                   0.3),
    (oo_min,                                           0.2),
    (1.0 - min(oo_spread, 0.5) / 0.5,                 0.2)
])

IF type_count == 1:
    QUEUE_ACTION(priority="HIGH", category="MODEL_DEV", dimension="D1",
        constraint_type="STRATEGY_HOMOGENEITY",
        title="All assets use same (model, feature) pair",
        recommendation="Develop alternative strategy types via P1/P2")

IF age_max > 180:
    QUEUE_ACTION(priority="MEDIUM", category="RESEARCH", dimension="D1",
        constraint_type="STRATEGY_STALENESS",
        recommendation="Schedule P1/P2 re-run for stale assets")
```

Remaining dimensions (D2-D8) follow the same pattern: compute score from inputs, queue action items when below threshold. See source for full per-dimension pseudocode.

## Audit Resolutions

> [!note] 2026-04-11 Gap Analysis — CRITICAL fixes
> The following audit resolutions reference specifications in this document:

- [[G-OFF-015_pseudotrader_unwired|G-OFF-015 — Pseudotrader Unwired from Orchestrator]] (PG-09) — CRITICAL RESOLVED
- [[G-OFF-016_pseudotrader_no_replay|G-OFF-016 — No Pipeline Replay in Pseudotrader]] (PG-09 §1-2) — CRITICAL RESOLVED
- [[G-OFF-029_sensitivity_uniform_perturbation|G-OFF-029 — Sensitivity Uniform Perturbation]] (PG-12) — CRITICAL RESOLVED
- [[G-OFF-046_version_rollback_unimplemented|G-OFF-046 — Version Rollback Unimplemented]] (Version Snapshot Policy) — CRITICAL RESOLVED
- [[G-XCT-012_crash_recovery_write_only|G-XCT-012 — Crash Recovery Write-Only]] (startup/recovery) — CRITICAL RESOLVED

## Related Canvases

- [[System 1/Backend/P3 Offline.canvas|P3 Offline]]
