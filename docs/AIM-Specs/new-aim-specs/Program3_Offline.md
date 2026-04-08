# Program 3 — Captain (Offline) Specification

**Version:** 1.0
**Created:** 2026-03-01
**Purpose:** Complete specification of the Captain (Offline) strategic brain — the component that learns, detects decay, retests updates, manages strategy injections, and maintains all AIM models.
**Architecture reference:** `Program3_Architecture.md`
**Companion specs:** `Program3_Online.md`, `Program3_Command.md`
**Research basis:** `AIM_Extractions.md` (115 papers), `AIM_Research_Notes.md`

---

# OVERVIEW

Captain (Offline) is the strategic brain of the Captain system. It runs periodically (scheduled + event-triggered) and handles all operations that require historical data processing, model training, or computational work that cannot run in real-time. Captain (Online) reads the outputs of Captain (Offline) but never writes to them.

**Execution modes:**
- **Scheduled:** Weekly AIM model retraining (Tier 1), monthly sensitivity scans, quarterly re-testing
- **Event-triggered:** Trade outcome received, Level 3 decay trigger, strategy injection event, TSM file change

**9 Blocks:**
1. AIM Model Training and Management
2. Strategy Decay Detection
3. Post-Update Retest (Pseudotrader)
4. Strategy Injection Comparison Protocol
5. AIM-13 Sensitivity Scanner
6. AIM-14 Auto-Expansion
7. TSM Simulation
8. Kelly Parameter Updates
9. System Health Diagnostic

---

# BLOCK 1 — AIM MODEL TRAINING AND MANAGEMENT

## 1.1 Purpose

Trains, updates, and manages the lifecycle of all 15 AIM models. Implements the MoE/DMA meta-learning architecture that determines which AIMs are active and how much weight each receives.

## 1.2 Inputs

| Input | Source | Description |
|-------|--------|-------------|
| P3-D03 | Captain (Online) | Trade outcome log with AIM-contextualised metadata |
| P3-D01 | Self (prior state) | Current AIM model states |
| P3-D02 | Self (prior state) | Current DMA meta-weights |
| P3-D00 | Captain (Command) | Asset universe register (which assets are active) |

## 1.3 AIM Lifecycle Management

```
P3-PG-01: "aim_lifecycle_manager_A"

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
            # Outputs neutral modifier (1.0) until user activates via GUI
            IF user_activated(a):
                SET status = ACTIVE
        
        CASE ACTIVE:
            # Normal operation — modifier flows into Captain (Online)
            IF meta_weight(a) == 0 for 20+ consecutive trades:
                SET status = SUPPRESSED
                LOG suppression event to P3-D06
        
        CASE BOOTSTRAPPED:
            # Set during asset_bootstrap() for Tier 1 AIMs with sufficient historical data.
            # Outputs neutral modifier (1.0) like ELIGIBLE, but skips the normal
            # INSTALLED→COLLECTING→WARM_UP progression because historical data was used.
            # Transitions to ACTIVE when user activates via GUI (same gate as ELIGIBLE).
            IF user_activated(a):
                SET status = ACTIVE
        
        CASE SUPPRESSED:
            # Still training, still collecting — but modifier locked at 1.0
            IF meta_weight(a) > 0.1 for 10+ consecutive trades:
                SET status = ACTIVE  # Auto-recovery
                LOG recovery event to P3-D06

    SAVE updated status to P3-D01[a]
```

## 1.4 DMA Meta-Learning Mechanism (Paper 187)

```
P3-PG-02: "aim_dma_update_A"

# Called after each trade outcome is logged
# SHARED INTELLIGENCE: This program learns from trade outcomes regardless of which user
# took the trade. Trade outcomes are objective market events — the price moved the same
# amount regardless of who traded. In multi-user mode, follows UserManagementSetup.md
# Section 5 learning loop config (v1: all trades; v2: ADMIN only or role-weighted).

INPUT: trade_outcome from P3-D03 (latest entry, includes user_id field)
INPUT: P3-D02 (current model probabilities per AIM)

# Forgetting factor controls adaptation speed
lambda = 0.99  # OPEN PARAMETER: higher = slower adaptation

FOR EACH active aim a:
    # Step 1: Compute prediction likelihood (SPEC-A9: magnitude-weighted)
    modifier_a = aim_modifier_at_trade_time(a, trade_outcome.timestamp)
    u = trade_outcome.asset
    regime = trade_outcome.regime_at_entry
    pnl_pc = trade_outcome.pnl / max(trade_outcome.contracts, 1)
    
    # DMA likelihood uses regime-level EWMA stats aggregated across sessions.
    # P3-D05 is indexed [asset][regime][session]; for DMA we use the weighted average
    # across sessions: avg_win = Σ(session_avg_win * session_trade_count) / total_trades
    # This gives a regime-level view for meta-weight updates.
    IF modifier_a > 1.0:
        # AIM said "size up"
        IF pnl_pc > 0:
            z = min(pnl_pc / max(P3-D05[u][regime].avg_win, 0.01), 3.0)
            likelihood_a = 0.5 + 0.5 * z / 3.0
        ELSE:
            z = min(abs(pnl_pc) / max(P3-D05[u][regime].avg_loss, 0.01), 3.0)
            likelihood_a = 0.5 - 0.5 * z / 3.0
    ELIF modifier_a < 1.0:
        # AIM said "size down" — inverse
        IF pnl_pc < 0:
            z = min(abs(pnl_pc) / max(P3-D05[u][regime].avg_loss, 0.01), 3.0)
            likelihood_a = 0.5 + 0.5 * z / 3.0
        ELSE:
            z = min(pnl_pc / max(P3-D05[u][regime].avg_win, 0.01), 3.0)
            likelihood_a = 0.5 - 0.5 * z / 3.0
    ELSE:
        likelihood_a = 0.5  # Neutral — no prediction to evaluate
    
    # Step 2: Update model probability via forgetting factor
    raw_prob_a = P3-D02[a].inclusion_probability ^ lambda * likelihood_a
    
# Step 3: Normalise across all active AIMs
total = SUM(raw_prob_a for all active a)
FOR EACH active aim a:
    P3-D02[a].inclusion_probability = raw_prob_a / total
    P3-D02[a].inclusion_flag = (P3-D02[a].inclusion_probability > inclusion_threshold)

SAVE P3-D02
```

## 1.4b Version Snapshot Policy

All model update operations in Captain (Offline) MUST save a timestamped snapshot to P3-D18 (version_history_store) BEFORE committing changes. This applies to:

```
VERSIONED_COMPONENTS = [P3-D01, P3-D02, P3-D05, P3-D12, P3-D17.system_params]

FUNCTION snapshot_before_update(component_id, trigger_reason):
    snapshot = {
        version_id:     generate_uuid(),
        component:      component_id,
        timestamp:       now(),
        trigger:        trigger_reason,  # "DMA_UPDATE" | "AIM_RETRAIN" | "KELLY_UPDATE" |
                                         # "EWMA_UPDATE" | "PARAM_CHANGE" | "INJECTION_ADOPT"
        state:          deep_copy(get_current_state(component_id)),
        model_hash:     hash(get_current_state(component_id))
    }
    P3-D18.append(snapshot)
    
    # Enforce max versions per component (default 50)
    max_versions = P3-D17.system_params.max_versions_per_component or 50
    component_versions = P3-D18.filter(component=component_id)
    IF len(component_versions) > max_versions:
        # Remove oldest (but NEVER delete — move to cold storage per retention policy)
        oldest = component_versions.sort_by(timestamp).first()
        migrate_to_cold_storage(oldest)
    
    RETURN snapshot.version_id

# Called by ADMIN via System Overview GUI
FUNCTION rollback_to_version(component_id, version_id, admin_user_id):
    target = P3-D18[version_id]
    
    # Run pseudotrader comparison first (Offline Block 3)
    comparison = run_pseudotrader_comparison(
        current=get_current_state(component_id),
        proposed=target.state
    )
    
    # Present comparison to ADMIN for approval
    NOTIFY(user_id=admin_user_id,
           message="Rollback comparison ready for {component_id} → version {target.timestamp}",
           priority="HIGH", action_required=True)
    
    # ADMIN approves → apply rollback
    ON admin_approval:
        snapshot_before_update(component_id, "ROLLBACK")  # snapshot current before overwriting
        restore_state(component_id, target.state)
        
        # Run regression tests before committing
        IF NOT run_regression_tests():
            REVERT and NOTIFY "Rollback failed regression tests — reverted"
        
        LOG to AdminDecisionLog(
            admin_user_id=admin_user_id,
            decision_type="VERSION_ROLLBACK",
            decision_value="Rolled back {component_id} to version {target.timestamp}",
            context={version_id: version_id, comparison: comparison}
        )

# Snapshot calls are embedded in each update block:
# P3-PG-02 (DMA): snapshot_before_update("P3-D02", "DMA_UPDATE")
# P3-PG-15 (Kelly): snapshot_before_update("P3-D12", "KELLY_UPDATE") + snapshot("P3-D05", "EWMA_UPDATE")
# P3-PG-01 (AIM lifecycle): snapshot_before_update("P3-D01", "AIM_RETRAIN")
# P3-PG-10 (Injection): snapshot_before_update("P3-D01", "INJECTION_ADOPT") when adoption confirmed
# update_system_param: snapshot_before_update("P3-D17.system_params", "PARAM_CHANGE")
```

## 1.5 HDWM Diversity Maintenance (Paper 190)

```
P3-PG-03: "aim_diversity_check_A"

# Run weekly to ensure ensemble diversity is maintained

seed_types = {
    "options": [AIM-01, AIM-02, AIM-03],
    "microstructure": [AIM-04, AIM-05, AIM-15],
    "macro_event": [AIM-06, AIM-07],
    "cross_asset": [AIM-08, AIM-09],
    "temporal": [AIM-10, AIM-11],
    "internal": [AIM-12, AIM-13, AIM-14]
}

FOR EACH type IN seed_types:
    active_in_type = [a for a in seed_types[type] if P3-D01[a].status == ACTIVE]
    
    IF len(active_in_type) == 0:
        # All AIMs of this type suppressed — force one back as seed
        best_candidate = argmax(P3-D02[a].recent_effectiveness for a in seed_types[type])
        SET P3-D01[best_candidate].status = ACTIVE
        SET P3-D02[best_candidate].inclusion_probability = 1.0 / num_active_aims
        LOG "HDWM diversity recovery: reactivated AIM-{best_candidate} as seed for {type}"
```

## 1.6 Per-AIM Drift Detection (Paper 191)

```
P3-PG-04: "aim_drift_detector_A"

# Run daily for each active AIM

FOR EACH active aim a:
    # AutoEncoder monitors feature distribution
    current_features = get_aim_input_features(a, today)
    reconstruction_error = aim_autoencoder[a].reconstruct(current_features)
    
    # ADWIN monitors reconstruction error stream for structural change
    adwin_state[a].add(reconstruction_error)
    
    IF adwin_state[a].detected_change():
        LOG "Concept drift detected in AIM-{a} input features"
        FLAG aim a for retraining in next scheduled cycle
        
        # Reduce meta-weight temporarily
        P3-D02[a].inclusion_probability *= 0.5
        RENORMALISE P3-D02

SAVE P3-D04.adwin_states
```

## 1.7 Outputs

| Output | Dataset | Description |
|--------|---------|-------------|
| Updated AIM states | P3-D01 | Status, trained model parameters per AIM |
| Updated meta-weights | P3-D02 | DMA probabilities and inclusion flags |
| Drift flags | P3-D04 | ADWIN states, retraining flags |

---

# BLOCK 2 — STRATEGY DECAY DETECTION

## 2.1 Purpose

Monitors live trade outcomes for signs that the locked strategy's edge has deteriorated. Uses BOCPD (primary) and distribution-free CUSUM (complementary) to detect changes in the P&L distribution.

## 2.2 Inputs

| Input | Source | Description |
|-------|--------|-------------|
| P3-D03 | Captain (Online) | Trade outcome log |
| P3-D04 | Self (prior state) | BOCPD run lengths, CUSUM statistics |
| P3-D05 | Self (prior state) | EWMA states for regime-conditional returns |

## 2.3 BOCPD — Primary Detector (Paper 231)

```
P3-PG-05: "bocpd_decay_monitor_A"

# Run after each trade outcome
# SHARED INTELLIGENCE: Decay detection monitors the strategy's market-level performance,
# not any individual user's capital. Uses all qualifying trades from P3-D03
# (filtered per UserManagementSetup.md Section 5 learning loop config).

INPUT: new_trade_pnl from P3-D03 (filtered by learning loop rules)

# BOCPD maintains posterior over run length r_t
# r_t = time since last changepoint

FOR EACH asset u IN active_universe:
    # Get trade stream for this asset
    pnl_stream = P3-D03.filter(asset=u).pnl_values
    
    # Recursive update (Adams & MacKay 2007)
    # P(r_t, x_{1:t}) = SUM over r_{t-1} of:
    #   P(r_t | r_{t-1}) × P(x_t | r_{t-1}, x^(r)) × P(r_{t-1}, x_{1:t-1})
    
    FOR r IN range(0, max_run_length):
        # Predictive distribution: P(x_t | run data)
        predictive_prob = compute_predictive(pnl_stream, run_length=r)
        
        # Transition: P(r_t | r_{t-1})
        # r_t = r_{t-1} + 1 (continuation) or r_t = 0 (changepoint)
        growth_prob = (1 - hazard_rate) * predictive_prob
        changepoint_prob = hazard_rate * predictive_prob
        
        joint_prob[r+1] = growth_prob * prior_joint[r]
        joint_prob[0] += changepoint_prob * prior_joint[r]
    
    # Normalise to get posterior
    evidence = SUM(joint_prob)
    posterior = joint_prob / evidence
    
    # Changepoint probability = mass at r=0
    cp_probability = posterior[0]
    
    # Store state
    P3-D04.bocpd[u].run_length_posterior = posterior
    P3-D04.bocpd[u].cp_probability = cp_probability
    P3-D04.bocpd[u].cp_history.append(cp_probability)
    
    # Level 2 trigger
    IF cp_probability > 0.8:
        TRIGGER Level_2(asset=u, severity=cp_probability, source="BOCPD")
    
    # Level 3 trigger (sustained)
    recent_5d = P3-D04.bocpd[u].cp_history[-5:]
    IF ALL(p > 0.9 for p in recent_5d) AND len(recent_5d) >= 5:
        TRIGGER Level_3(asset=u, source="BOCPD_sustained")

SAVE P3-D04
```

## 2.4 Distribution-Free CUSUM — Complementary (Paper 232)

```
P3-PG-06: "cusum_decay_monitor_A"

# Complementary to BOCPD — detects mean shifts in P&L

INPUT: new_trade_pnl from P3-D03

FOR EACH asset u IN active_universe:
    pnl = new_trade_pnl[u]
    
    # Bootstrap-calibrated control limits
    # Estimated from in-control data (first N validated trades)
    k = P3-D04.cusum[u].allowance  # typically delta/2
    h_sequential = P3-D04.cusum[u].control_limit(sprint_length=T_n)
    
    # CUSUM statistic (two-sided)
    C_up = max(0, P3-D04.cusum[u].C_up_prev + pnl - k)
    C_down = max(0, P3-D04.cusum[u].C_down_prev - pnl - k)
    
    # Sprint length tracking
    IF C_up == 0 AND C_down == 0:
        T_n = 0
    ELSE:
        T_n = P3-D04.cusum[u].sprint_length + 1
    
    # Signal check against sequential control limit
    IF C_up > h_sequential OR C_down > h_sequential:
        TRIGGER Level_2(asset=u, severity="CUSUM_breach", source="CUSUM")
        # Reset after signal
        C_up = 0; C_down = 0; T_n = 0
    
    # Store state
    P3-D04.cusum[u].C_up_prev = C_up
    P3-D04.cusum[u].C_down_prev = C_down
    P3-D04.cusum[u].sprint_length = T_n

SAVE P3-D04
```

## 2.5 Bootstrap Control Limit Calibration

```
P3-PG-07: "cusum_bootstrap_calibrate_A"

# Run once during initialisation, re-run quarterly

INPUT: in_control_trades from P3-D03 (first N validated trades per asset)

FOR EACH asset u:
    in_control_pnl = in_control_trades[u].pnl_values
    
    # Bootstrap: draw B resamples, compute CUSUM on each
    FOR b IN range(B=2000):
        resample = bootstrap_sample(in_control_pnl, size=len(in_control_pnl))
        FOR each sprint_length j IN range(1, max_sprint):
            cusum_values_at_j = compute_cusum_conditional_on_sprint(resample, j)
            store bootstrap distribution of [C_n | T_n = j]
    
    # For each sprint length, determine control limit at desired ARL
    FOR j IN range(1, max_sprint):
        P3-D04.cusum[u].sequential_limits[j] = quantile(
            bootstrap_cusum_dist[j], 
            percentile = 1 - 1/ARL_0  # e.g., ARL_0 = 200
        )

SAVE P3-D04
```

## 2.6 Level 2 and Level 3 Response

```
P3-PG-08: "decay_response_handler_A"

FUNCTION Level_2(asset, severity, source):
    # Autonomous sizing reduction
    reduction_factor = 1.0 - (severity - 0.8) * 2.5  # scales 0.8→1.0 to 0.5→0.0
    reduction_factor = max(0.5, reduction_factor)  # floor at 50%
    
    P3-D12.sizing_override[asset] = reduction_factor
    
    NOTIFY_GUI("Level 2: Sizing reduced to {reduction_factor*100}% for {asset}", 
               priority="HIGH", colour="AMBER")
    NOTIFY_TELEGRAM(priority="HIGH")
    
    LOG to P3-D04.decay_events

FUNCTION Level_3(asset, source):
    # Halt signals for affected asset
    P3-D00[asset].captain_status = "DECAYED"
    
    NOTIFY_GUI("Level 3: STRATEGY REVIEW IN PROGRESS — no signals for {asset}", 
               priority="CRITICAL", colour="RED")
    NOTIFY_TELEGRAM(priority="CRITICAL")
    
    # Trigger autonomous Programs 1/2 re-run
    SCHEDULE programs_1_2_rerun(asset)
    
    # Trigger AIM-14 auto-expansion search
    SCHEDULE aim14_search(asset)
    
    LOG to P3-D04.decay_events
```

## 2.7 Outputs

| Output | Dataset | Description |
|--------|---------|-------------|
| BOCPD states | P3-D04.bocpd | Run-length posteriors, cp probabilities per asset |
| CUSUM states | P3-D04.cusum | C_up, C_down, sprint lengths, sequential limits |
| Decay events | P3-D04.decay_events | Timestamped log of all Level 2/3 triggers |
| Sizing overrides | P3-D12 | Reduction factors for Level 2 affected assets |

---

# BLOCK 3 — POST-UPDATE RETEST (PSEUDOTRADER)

## 3.1 Purpose

When Captain proposes an update (new AIM weights, retrained model, injected strategy), the pseudotrader replays history to demonstrate the update would have improved performance.

## 3.2 Pseudocode

```
P3-PG-09: "pseudotrader_retest_A"

INPUT: proposed_update (AIM weight change, model retrain, or strategy injection)
INPUT: historical_window from P3-D03 (all trades from Captain start to now)

# Phase 1: Replay WITHOUT update
baseline_results = []
FOR EACH day d IN historical_window:
    signal = captain_online_replay(d, using=CURRENT_parameters)
    outcome = actual_trade_outcome(d)
    baseline_results.append({signal, outcome})

# Phase 2: Replay WITH update
updated_results = []
FOR EACH day d IN historical_window:
    signal = captain_online_replay(d, using=PROPOSED_parameters)
    outcome = actual_trade_outcome(d)  # same actual outcomes
    updated_results.append({signal, outcome})

# Phase 3: Compare
sharpe_baseline = compute_sharpe(baseline_results)
sharpe_updated = compute_sharpe(updated_results)
sharpe_improvement = sharpe_updated - sharpe_baseline

drawdown_baseline = max_drawdown(baseline_results)
drawdown_updated = max_drawdown(updated_results)
drawdown_change = drawdown_updated - drawdown_baseline

winrate_baseline = win_rate(baseline_results)
winrate_updated = win_rate(updated_results)
winrate_delta = winrate_updated - winrate_baseline

# Phase 4: Validate (anti-overfitting)
pbo = compute_CSCV_PBO(updated_results, S=16)  # Paper 152
dsr = compute_DSR(sharpe_updated, N_trials, skew, kurtosis, T)  # Paper 150

# Phase 5: Store and report
P3-D11.append({
    update_type: proposed_update.type,
    sharpe_improvement: sharpe_improvement,
    drawdown_change: drawdown_change,
    winrate_delta: winrate_delta,
    pbo: pbo,
    dsr: dsr,
    recommendation: "ADOPT" if (sharpe_improvement > 0 AND pbo < 0.5 AND dsr > 0.5) else "REJECT"
})

GENERATE RPT-09(P3-D11.latest)
```

---

# BLOCK 4 — STRATEGY INJECTION COMPARISON PROTOCOL

## 4.1 Purpose

When a new Programs 1/2 run completes, evaluates the new candidate strategy against the current locked strategy using AIM-contextualised performance comparison.

## 4.2 Pseudocode

```
P3-PG-10: "injection_comparison_A"

INPUT: new_candidate from Programs 1/2 output (P2-D06 candidate, P2-D07 regime model)
INPUT: current_strategy from P3-D00[asset].locked_strategy

# Step 1: Contextualise — retroactive AIM analysis
FOR EACH active aim a:
    retroactive_modifiers[a] = aim_retroactive_replay(a, new_candidate, historical_window)

# Step 2: Compute AIM-adjusted expected performance
expected_new = compute_aim_adjusted_edge(new_candidate, retroactive_modifiers)
expected_current = compute_aim_adjusted_edge(current_strategy, P3-D02)

# Step 3: Run pseudotrader comparison
pseudo_results = pseudotrader_compare(new_candidate, current_strategy, historical_window)

# Step 4: Decision logic
IF expected_new > expected_current * 1.2 AND pseudo_results.pbo < 0.5:
    recommendation = "ADOPT"
    transition_days = 10
ELIF expected_new > expected_current * 0.9 AND expected_new < expected_current * 1.2:
    recommendation = "PARALLEL_TRACK"
    tracking_days = 20
ELSE:
    recommendation = "REJECT"

# Step 5: Store and report
P3-D06.append({
    asset: asset,
    candidate: new_candidate,
    current: current_strategy,
    expected_new: expected_new,
    expected_current: expected_current,
    pseudo_results: pseudo_results,
    recommendation: recommendation,
    timestamp: now()
})

GENERATE RPT-05(P3-D06.latest)
NOTIFY_GUI("New strategy candidate for {asset} — review RPT-05", priority="HIGH")
```

## 4.3 Transition Phasing

```
P3-PG-11: "strategy_transition_A"

# Called when user approves adoption via GUI

INPUT: adoption_decision from Captain (Command)
INPUT: new_strategy, old_strategy

IF adoption_decision == "ADOPT":
    FOR day d IN range(1, transition_days + 1):
        weight_new = d / transition_days
        weight_old = 1 - weight_new
        
        # Both strategies generate signals
        signal_new = generate_signal(new_strategy, d)
        signal_old = generate_signal(old_strategy, d)
        
        # Blended signal for sizing (direction follows new strategy)
        blended_size = weight_new * signal_new.size + weight_old * signal_old.size
        
        OUTPUT blended_signal(direction=signal_new.direction, size=blended_size)
    
    # After transition period: fully switch
    P3-D00[asset].locked_strategy = new_strategy
    P3-D00[asset].captain_status = "ACTIVE"
    LOG "Transition complete: {asset} now using {new_strategy}"

ELIF adoption_decision == "PARALLEL_TRACK":
    # Both produce signals for tracking_days, only current one acted on
    FOR day d IN range(1, tracking_days + 1):
        signal_current = generate_signal(old_strategy, d)
        signal_candidate = generate_signal(new_strategy, d)  # tracked but not acted on
        LOG both signals for comparison
    
    # After tracking: present final comparison
    GENERATE RPT-05_final_comparison()
    NOTIFY_GUI("Parallel tracking complete for {asset} — final review required")

ELIF adoption_decision == "REJECT":
    LOG rejection to P3-D06
    P3-D00[asset].captain_status = "ACTIVE"  # Resume normal operation
```

---

# BLOCK 5 — AIM-13 SENSITIVITY SCANNER (MONTHLY)

## 5.1 Purpose

Monthly automated scan that perturbs locked strategy parameters to assess robustness. Flags fragile strategies for human review.

## 5.2 Pseudocode

```
P3-PG-12: "sensitivity_scanner_A"

# Run monthly (scheduled by Captain Offline orchestrator)

FOR EACH asset u IN active_universe:
    strategy = P3-D00[u].locked_strategy
    base_params = strategy.parameters  # SL, TP, OR_window, threshold, etc.
    
    # Generate perturbation grid
    perturbation_grid = []
    FOR EACH param p IN base_params:
        FOR delta IN [-0.20, -0.10, -0.05, 0, +0.05, +0.10, +0.20]:
            perturbed = base_params.copy()
            perturbed[p] = base_params[p] * (1 + delta)
            perturbation_grid.append(perturbed)
    
    # Evaluate each perturbation
    results = []
    FOR EACH config IN perturbation_grid:
        perf = backtest_with_config(config, recent_oos_window)
        results.append({config, sharpe: perf.sharpe, dd: perf.max_drawdown, wr: perf.win_rate})
    
    # Compute stability metrics
    sharpe_values = [r.sharpe for r in results]
    sharpe_stability = std(sharpe_values) / mean(sharpe_values)  # CV — lower = more robust
    
    # PBO on perturbation grid (Paper 152)
    pbo = compute_CSCV_PBO(results, S=8)
    
    # DSR (Paper 150)
    dsr = compute_DSR(max(sharpe_values), N_trials=len(perturbation_grid), 
                       skew=skewness(sharpe_values), kurtosis=kurtosis(sharpe_values),
                       T=len(recent_oos_window))
    
    # Covariance-penalty for complexity (Paper 165)
    complexity_penalty = num_parameters(strategy) * penalty_coefficient
    adjusted_sharpe = max(sharpe_values) - complexity_penalty
    
    # Flag determination
    flags = []
    IF sharpe_stability > 0.5: flags.append("FRAGILE — parameter-sensitive")
    IF pbo > 0.5: flags.append("OVERFIT — likely data-mined")
    IF dsr < 0.5: flags.append("INSIGNIFICANT — insufficient evidence")
    
    robustness_status = "FRAGILE" if len(flags) >= 2 else "ROBUST"
    
    # Store results
    P3-D13[u] = {
        sharpe_stability, pbo, dsr, adjusted_sharpe, 
        robustness_status, flags, perturbation_grid_results: results,
        scan_date: now()
    }
    
    # Alert if fragile
    IF robustness_status == "FRAGILE":
        NOTIFY_GUI("AIM-13: Strategy for {u} flagged FRAGILE — {flags}", priority="HIGH")
        # Apply modifier reduction
        P3-D01[13].current_modifier = 0.85

GENERATE RPT-03_section("AIM-13 Sensitivity Results", P3-D13)
SAVE P3-D13
```

---

# BLOCK 6 — AIM-14 AUTO-EXPANSION (LEVEL 3 TRIGGER)

## 6.1 Purpose

When AIM-13 flags decay AND Level 3 is triggered, AIM-14 generates replacement strategy candidates using theory-constrained automated search.

## 6.2 Pseudocode

```
P3-PG-13: "auto_expansion_search_A"

# Triggered by Level 3 decay detection

INPUT: decayed_asset from Level 3 trigger
INPUT: feature_space from Program 1 feature library
INPUT: economic_constraints (theory-bounded search — Paper 162)

# Step 1: Define search space (theory-constrained)
candidate_params = {
    OR_window: range(3, 15, 1),         # minutes
    threshold: range(0.05, 0.30, 0.025), # percentage
    SL_multiplier: range(0.20, 0.50, 0.05),
    TP_multiplier: range(0.50, 1.50, 0.10),
    features: Program1_feature_library.top_k(k=10)  # top by prior OO scores
}

# Step 2: GA search with rough set rules (Paper 163)
population = initialise_population(candidate_params, size=100)

FOR generation IN range(50):
    FOR EACH candidate IN population:
        # Walk-forward validation with double OOS (Paper 161)
        training_results = walk_forward_train(candidate, training_window)
        validation_results = walk_forward_validate(candidate, validation_window)
        candidate.fitness = validation_results.robust_sharpe
    
    # Selection, crossover, mutation
    population = evolve(population, selection="tournament", crossover_rate=0.8, mutation_rate=0.1)

# Step 3: Select top candidates
top_candidates = sorted(population, key=lambda c: c.fitness, reverse=True)[:5]

# Step 4: Final OOS test (ONCE — Paper 161)
final_candidates = []
FOR EACH candidate IN top_candidates:
    oos_result = final_oos_test(candidate, holdout_window)  # tested ONCE only
    
    pbo = compute_CSCV_PBO(oos_result)
    dsr = compute_DSR(oos_result.sharpe, N_trials=len(population)*50)
    
    IF pbo < 0.5 AND dsr > 0.5:
        final_candidates.append({candidate, oos_result, pbo, dsr})

# Step 5: Present to user (Level 3 requires human approval)
IF len(final_candidates) > 0:
    FOR EACH fc IN final_candidates:
        # Run injection comparison protocol (Block 4)
        injection_comparison(fc.candidate, decayed_asset)
ELSE:
    NOTIFY_GUI("AIM-14: No viable replacement candidates found for {decayed_asset}. Manual intervention required.", priority="CRITICAL")

LOG search results to P3-D06
```

---

# BLOCK 7 — TSM SIMULATION

## 7.1 Purpose

Monte Carlo simulation estimating the probability of passing a prop firm evaluation or achieving a target under current strategy and market conditions.

## 7.2 Pseudocode

```
P3-PG-14: "tsm_simulation_A"

# Run: after each trade, when TSM file changes

INPUT: P3-D08 (active TSM configuration)
INPUT: P3-D03 (trade outcome log)
INPUT: P3-D12 (current Kelly parameters)

FOR EACH account ac WITH active TSM:
    tsm = P3-D08[ac]
    risk_goal = tsm.classification.risk_goal  # PASS_EVAL, GROW_CAPITAL, PRESERVE_CAPITAL
    trade_returns = P3-D03.filter(account=ac).pnl_values
    
    # Current state
    current_balance = tsm.current_balance
    remaining_days = tsm.evaluation_end_date - today()
    mdd_remaining = tsm.max_drawdown_limit - tsm.current_drawdown
    target_profit = tsm.profit_target - (current_balance - tsm.starting_balance)
    
    # Monte Carlo simulation
    pass_count = 0
    N_PATHS = 10000
    
    FOR path IN range(N_PATHS):
        sim_balance = current_balance
        sim_max_balance = current_balance
        sim_drawdown = tsm.current_drawdown
        passed = True
        
        FOR day IN range(remaining_days):
            # Block bootstrap: sample returns preserving autocorrelation
            block_size = random.choice([3, 5, 7])
            start_idx = random.randint(0, len(trade_returns) - block_size)
            daily_returns = trade_returns[start_idx : start_idx + block_size]
            
            daily_pnl = 0
            FOR ret IN daily_returns:
                # ret is a historical per-trade PnL from this account's trade log
                # TSM simulation applies returns as-is (already sized from live trading)
                sim_balance += ret
                daily_pnl += ret
                sim_max_balance = max(sim_max_balance, sim_balance)
                sim_drawdown = sim_max_balance - sim_balance
                
                # Check MDD breach
                IF sim_drawdown > tsm.max_drawdown_limit:
                    passed = False
                    BREAK
            
            # Check MLL breach (daily loss limit)
            IF daily_pnl < 0 AND abs(daily_pnl) > tsm.max_daily_loss:
                passed = False
            
            IF NOT passed: BREAK
        
        # Check if target reached
        IF passed AND (sim_balance - tsm.starting_balance) >= tsm.profit_target:
            pass_count += 1
    
    pass_probability = pass_count / N_PATHS
    
    # Store and report
    P3-D08[ac].pass_probability = pass_probability
    P3-D08[ac].simulation_date = now()
    
    # Alert based on account risk goal
    IF risk_goal == "PASS_EVAL":
        IF pass_probability < 0.3:
            NOTIFY(user_id=get_account(ac).user_id,
                   message="TSM: Pass probability for {ac} critically low ({pass_probability*100}%)",
                   priority="CRITICAL")
        ELIF pass_probability < 0.5:
            NOTIFY(user_id=get_account(ac).user_id,
                   message="TSM: Pass probability for {ac} at {pass_probability*100}% — consider reducing risk",
                   priority="HIGH")
    
    ELIF risk_goal == "GROW_CAPITAL" AND tsm.max_drawdown_limit:
        # Funded/scaling prop accounts: track ruin probability (hitting MDD = account loss)
        ruin_probability = 1 - pass_probability  # probability of hitting MDD
        IF ruin_probability > 0.3:
            NOTIFY(user_id=get_account(ac).user_id,
                   message="TSM: Drawdown risk elevated for {ac} ({ruin_probability*100}% breach probability)",
                   priority="HIGH")
    
    ELIF risk_goal == "PRESERVE_CAPITAL":
        # Account is in protective mode — alert if drawdown risk is non-trivial
        IF tsm.max_drawdown_limit AND pass_probability < 0.7:
            NOTIFY(user_id=get_account(ac).user_id,
                   message="TSM: Account {ac} in PRESERVE_CAPITAL mode, breach risk at {(1-pass_probability)*100}%",
                   priority="HIGH")
    
    # Broker accounts (no MDD/MLL): simulation skipped, pass_probability set to None
    IF NOT tsm.max_drawdown_limit AND NOT tsm.max_daily_loss:
        P3-D08[ac].pass_probability = None  # not applicable for unconstrained broker accounts

GENERATE RPT-07(P3-D08)
SAVE P3-D08
```

---

# BLOCK 8 — KELLY PARAMETER UPDATES

## 8.1 Purpose

Updates the regime-conditional expected return estimates and Kelly fractions used by Captain (Online) for sizing. This block produces the regime-specific Kelly inputs that Captain (Online) Block 4 blends using regime probability weights per Paper 219 (MacLean & Zhao).

## 8.2 Pseudocode

```
P3-PG-15: "kelly_parameter_update_A"

# Run after each trade outcome

INPUT: trade_outcome from P3-D03
INPUT: P3-D05 (current EWMA states)
INPUT: P3-D12 (current Kelly parameters)

u = trade_outcome.asset
IF u NOT IN active_universe:
    RETURN  # asset not in active universe — skip update

# Get regime at time of trade
regime = trade_outcome.regime_at_entry  # LOW_VOL or HIGH_VOL
    
    # NORMALISE: convert absolute PnL to per-contract return
    # This removes sizing bias (AIM modifier, account capital, contract count)
    # and ensures EWMA tracks the STRATEGY's inherent edge, not deployed edge.
    contracts = trade_outcome.contracts
    IF contracts <= 0:
        LOG "Invalid contract count for trade — skipping EWMA update"
        RETURN
    
    pnl_per_contract = trade_outcome.pnl / contracts
    
    # Separate EWMA for win rate and payoff ratio (these move independently)
    IF pnl_per_contract > 0:
        win = 1
        win_size = pnl_per_contract  # per-contract win amount
    ELSE:
        win = 0
        loss_size = abs(pnl_per_contract)  # per-contract loss amount
    
    # SPEC-A12: Adaptive EWMA decay — alpha scales with BOCPD changepoint probability
    cp_prob = P3-D04[u].current_changepoint_probability
    IF cp_prob < 0.2:
        effective_span = 30   # stable — slower learning, more precise
    ELIF cp_prob < 0.5:
        effective_span = 20   # default
    ELIF cp_prob < 0.8:
        effective_span = 12   # elevated instability — faster
    ELSE:
        effective_span = 8    # near-changepoint — rapid adaptation
    alpha = 2 / (effective_span + 1)
    
    # SPEC-A8: Session-specific EWMA — P3-D05 indexed by [asset][regime][session]
    session = trade_outcome.session  # NY=1, LON=2, APAC=3
    
    P3-D05[u][regime][session].win_rate = (1 - alpha) * P3-D05[u][regime][session].win_rate + alpha * win
    
    IF win:
        P3-D05[u][regime][session].avg_win = (1 - alpha) * P3-D05[u][regime][session].avg_win + alpha * win_size
    ELSE:
        P3-D05[u][regime][session].avg_loss = (1 - alpha) * P3-D05[u][regime][session].avg_loss + alpha * loss_size
    
    # All values in P3-D05 are now in per-contract dollar terms
    # avg_win = EWMA of dollars won per contract on winning trades
    # avg_loss = EWMA of dollars lost per contract on losing trades
    
    # Recompute Kelly fraction per regime per session (SPEC-A8)
    FOR EACH regime r IN [LOW_VOL, HIGH_VOL]:
      FOR EACH ss IN [1, 2, 3]:  # NY, LON, APAC
        p = P3-D05[u][r][ss].win_rate
        W = P3-D05[u][r][ss].avg_win    # per-contract
        L = P3-D05[u][r][ss].avg_loss   # per-contract
        
        IF L > 0 AND p > 0:
            b = W / L  # win/loss ratio (dimensionless — sizing-independent)
            kelly_full = p - (1 - p) / b  # Kelly formula
            kelly_full = max(0, kelly_full)  # floor at 0
        ELSE:
            kelly_full = 0
        
        P3-D12[u][r][ss].kelly_full = kelly_full
    
    # Shrinkage factor (Paper 217)
    N_trades = P3-D03.filter(asset=u).count()
    estimation_variance = compute_estimation_variance(P3-D05[u])
    shrinkage = max(0.3, 1.0 - estimation_variance)  # floor at 0.3 (never < 30% Kelly)
    
    # As data accumulates, shrinkage approaches 1.0
    P3-D12[u].shrinkage_factor = shrinkage
    P3-D12[u].last_updated = now()

SAVE P3-D05
SAVE P3-D12

# Infrastructure: checkpoint written to SQLite WAL journal (P3-D20) after each EWMA/Kelly update
# This ensures crash recovery can restore the last known good state
CHECKPOINT(component="OFFLINE", stage="KELLY_UPDATE_COMPLETE", asset=u)

# Regulatory: this update triggers a version snapshot (P3-D18) which satisfies
# model change tracking requirements (ESMA Supervisory Briefing paragraph 30 —
# "series of minor changes could accumulate into a material change")
snapshot_before_update(component="P3-D05", trigger="EWMA_UPDATE")
snapshot_before_update(component="P3-D12", trigger="KELLY_UPDATE")
```

---

# BLOCK 9 — SYSTEM HEALTH DIAGNOSTIC

## 9.1 Purpose

Performs deep portfolio-level self-diagnosis across 8 dimensions, generates a prioritised human action queue with structured work items, and verifies whether previously resolved constraints actually improved. This is the system's mechanism for identifying its own limitations and telling ADMINs what human work is needed — from "run more P1/P2 tests" to "AIM-07 data feed is unreliable" to "edge is declining, investigate causes."

Distinct from Online Block 9 (lightweight session-end constraint flagging that runs every session), this block performs computationally heavier portfolio analysis on a weekly/monthly schedule.

Distinct from AIM-13 (parameter sensitivity of individual strategies): this block analyses the health of the entire system portfolio.

## 9.2 Schedule

- **Weekly:** Dimensions D1–D4, D6–D8 (portfolio health, staleness, AIMs, data, pipeline, resolution verification)
- **Monthly:** Dimension D5 (edge trajectory — requires 30d minimum window for meaningful trend) + full re-run of all dimensions
- **Event-triggered:** D8 (resolution verification) also runs when an ADMIN marks an action item as RESOLVED

## 9.3 Pseudocode

```
P3-PG-16B: "system_health_diagnostic_A"

INPUT: P2-D06 (locked strategies per asset)
INPUT: P2-D07 (regime prediction models per asset)
INPUT: P3-D00 (asset universe register)
INPUT: P3-D01 (AIM model states)
INPUT: P3-D02 (AIM meta-weights)
INPUT: P3-D03 (trade outcome log)
INPUT: P3-D04 (decay detector states)
INPUT: P3-D05 (EWMA states)
INPUT: P3-D06 (injection history)
INPUT: P3-D13 (sensitivity scan results)
INPUT: P3-D17 (capacity_state from Online Block 9)
INPUT: P3-D22 (previous diagnostic results + action queue)

OUTPUT: P3-D22 (updated diagnostic results + action queue)

# ════════════════════════════════════════════════
# DIMENSION 1: STRATEGY PORTFOLIO HEALTH
# ════════════════════════════════════════════════

strategy_models = {}
strategy_ages = {}
oo_scores = {}

FOR EACH asset u IN P3-D00.active_assets:
    locked = P2-D06[u]
    strategy_models[u] = (locked.m, locked.k)
    strategy_ages[u] = (now() - locked.timestamp).days
    oo_scores[u] = locked.OO

type_count = len(set(strategy_models.values()))
age_max = max(strategy_ages.values())
age_mean = mean(strategy_ages.values())
oo_min = min(oo_scores.values())
oo_spread = max(oo_scores.values()) - oo_min

d1_score = weighted_mean([
    (1.0 if type_count >= 3 else type_count / 3.0,   0.3),   # strategy diversity
    (max(0, 1.0 - age_max / 365.0),                   0.3),   # freshness
    (oo_min,                                           0.2),   # weakest link
    (1.0 - min(oo_spread, 0.5) / 0.5,                 0.2)    # consistency
])

IF type_count == 1:
    QUEUE_ACTION(priority="HIGH", category="MODEL_DEV", dimension="D1",
        constraint_type="STRATEGY_HOMOGENEITY",
        title="All {len(strategy_models)} assets use the same (model, feature) pair",
        detail="No strategy diversification. Single strategy failure would affect all assets.",
        impact_estimate="Adding 1 alternative strategy type would reduce single-point strategy risk by ~50%",
        recommendation="Develop swing or multi-day strategies via Programs 1/2")

IF age_max > 180:
    stale_assets = [u for u, age in strategy_ages.items() if age > 180]
    QUEUE_ACTION(priority="MEDIUM", category="RESEARCH", dimension="D1",
        constraint_type="STRATEGY_STALENESS",
        title="Strategy for {stale_assets} is {age_max} days old",
        detail="Strategies older than 180 days may have degraded. Market microstructure shifts over 6+ months.",
        impact_estimate="Re-running P1/P2 on stale assets may confirm current strategy or find improvement",
        recommendation="Schedule Programs 1/2 re-run for assets: {stale_assets}")

IF oo_min < 0.55:
    weak_assets = [u for u, oo in oo_scores.items() if oo < 0.55]
    QUEUE_ACTION(priority="MEDIUM", category="MODEL_DEV", dimension="D1",
        constraint_type="WEAK_OO_SCORE",
        title="Assets {weak_assets} have OO scores below 0.55",
        detail="OO range [{oo_min:.2f}, {max(oo_scores.values()):.2f}]. Bottom assets may benefit from re-run with additional models/features.",
        impact_estimate="Re-running P1/P2 with expanded model set could lift bottom OO scores",
        recommendation="Run Programs 1/2 with additional models for {weak_assets}")

# ════════════════════════════════════════════════
# DIMENSION 2: FEATURE PORTFOLIO HEALTH
# ════════════════════════════════════════════════

feature_usage = {}
FOR EACH asset u IN P3-D00.active_assets:
    f = P2-D06[u].k
    IF f NOT IN feature_usage:
        feature_usage[f] = []
    feature_usage[f].append(u)

distinct_features = len(feature_usage)
max_reuse = max(len(assets) for assets in feature_usage.values())
most_reused_feature = max(feature_usage, key=lambda f: len(feature_usage[f]))

# Check ICIR decay flags from Program 1 (if available in P2-D06 or D-24 metadata)
decay_flagged_features = [f for f in feature_usage if has_icir_decay_flag(f)]

d2_score = weighted_mean([
    (min(distinct_features / max(len(P3-D00.active_assets), 1), 1.0),  0.4),
    (1.0 - max_reuse / max(len(P3-D00.active_assets), 1),              0.3),
    (1.0 - len(decay_flagged_features) / max(distinct_features, 1),     0.3)
])

IF max_reuse >= 0.6 * len(P3-D00.active_assets):
    QUEUE_ACTION(priority="MEDIUM", category="FEATURE_DEV", dimension="D2",
        constraint_type="FEATURE_CONCENTRATION",
        title="{max_reuse}/{len(P3-D00.active_assets)} assets use feature {most_reused_feature}",
        detail="Feature concentration risk — if this feature's predictive power degrades, most assets are affected.",
        impact_estimate="Developing 2-3 alternative features would reduce single-feature dependency",
        recommendation="Research additional features for Program 1. Consider asset-specific feature engineering.")

IF len(decay_flagged_features) > 0:
    QUEUE_ACTION(priority="HIGH", category="RESEARCH", dimension="D2",
        constraint_type="FEATURE_DECAY_FLAG",
        title="Features with ICIR decay flag: {decay_flagged_features}",
        detail="These features showed strong ICIR on discovery sample but weak ICIR on OOS — potential temporal decay.",
        impact_estimate="Revalidating or replacing decayed features directly improves signal quality",
        recommendation="Re-run Program 1 Block 2B for affected assets to confirm or replace these features")

# ════════════════════════════════════════════════
# DIMENSION 3: MODEL STALENESS TRACKER
# ════════════════════════════════════════════════

last_p1_run = get_last_program1_run_date()  # from P3-D06 injection history or metadata
last_p2_run = get_last_program2_run_date()
days_since_p1 = (now() - last_p1_run).days IF last_p1_run ELSE 999
days_since_p2 = (now() - last_p2_run).days IF last_p2_run ELSE 999

regime_model_ages = {}
FOR EACH asset u IN P3-D00.active_assets:
    # P2-D07.training_period is "S_{(discovery)} date range" — .end extracts end date
    regime_model_ages[u] = (now() - P2-D07[u].training_period.end).days

aim_retrain_ages = {}
FOR EACH aim_id IN range(1, 16):
    IF P3-D01[aim_id].last_retrained:
        aim_retrain_ages[aim_id] = (now() - P3-D01[aim_id].last_retrained).days
    ELSE:
        aim_retrain_ages[aim_id] = 999

d3_score = weighted_mean([
    (max(0, 1.0 - days_since_p1 / 180.0),                          0.3),
    (max(0, 1.0 - max(regime_model_ages.values()) / 365.0),        0.3),
    (max(0, 1.0 - max(aim_retrain_ages.values()) / 90.0),          0.2),
    (max(0, 1.0 - days_since_p2 / 180.0),                          0.2)
])

IF days_since_p1 > 90:
    QUEUE_ACTION(priority="MEDIUM" if days_since_p1 < 180 else "HIGH",
        category="RESEARCH", dimension="D3",
        constraint_type="PIPELINE_STALENESS",
        title="No Programs 1/2 run in {days_since_p1} days",
        detail="Strategy pipeline has not been refreshed. Market conditions may have shifted.",
        impact_estimate="Fresh P1/P2 run may identify improved strategies or confirm current ones",
        recommendation="Schedule full Programs 1/2 run across all assets")

FOR EACH asset u, age IN regime_model_ages.items():
    IF age > 180:
        QUEUE_ACTION(priority="MEDIUM", category="MODEL_DEV", dimension="D3",
            constraint_type="REGIME_MODEL_STALE",
            title="Regime model for {u} is {age} days old",
            detail="Regime classification models degrade as market volatility structure evolves.",
            impact_estimate="Retraining regime model captures recent volatility structure",
            recommendation="Re-run Program 2 Block 3b for {u} with expanded training window")

# ════════════════════════════════════════════════
# DIMENSION 4: AIM EFFECTIVENESS PORTFOLIO
# ════════════════════════════════════════════════

aim_weights = {}
aim_status = {}
dormant_aims = []
dominant_aims = []

FOR EACH aim_id IN range(1, 16):
    w = P3-D02[aim_id].inclusion_probability
    aim_weights[aim_id] = w
    aim_status[aim_id] = P3-D01[aim_id].status  # ACTIVE, WARM_UP, DORMANT
    
    IF w < 0.05 AND aim_status[aim_id] == "ACTIVE":
        days_low = P3-D02[aim_id].days_below_threshold
        IF days_low > 30:
            dormant_aims.append((aim_id, w, days_low))
    
    IF w > 0.30:
        dominant_aims.append((aim_id, w))

active_count = len([a for a in aim_status.values() if a == "ACTIVE"])
warmup_count = len([a for a in aim_status.values() if a == "WARM_UP"])

d4_score = weighted_mean([
    (active_count / 15.0,                                    0.3),
    (1.0 - len(dormant_aims) / max(active_count, 1),         0.3),
    (1.0 - len(dominant_aims) / max(active_count, 1),         0.2),
    (1.0 - warmup_count / 15.0,                               0.2)
])

FOR EACH aim_id, w, days_low IN dormant_aims:
    aim_name = AIM_REGISTRY[aim_id].name
    QUEUE_ACTION(priority="LOW", category="AIM_IMPROVEMENT", dimension="D4",
        constraint_type="AIM_DORMANT",
        title="AIM-{aim_id:02d} ({aim_name}) dormant — weight {w:.3f} for {days_low} days",
        detail="DMA has suppressed this AIM due to low predictive value. May indicate data quality issues or genuinely uninformative signal.",
        impact_estimate="Investigating data quality or retraining may restore AIM contribution",
        recommendation="Check data feed quality for AIM-{aim_id:02d}. If data is clean, AIM may be uninformative for current universe.")

FOR EACH aim_id, w IN dominant_aims:
    aim_name = AIM_REGISTRY[aim_id].name
    QUEUE_ACTION(priority="MEDIUM", category="AIM_IMPROVEMENT", dimension="D4",
        constraint_type="AIM_DOMINANT",
        title="AIM-{aim_id:02d} ({aim_name}) contributes {w:.1%} of total modifier — concentration risk",
        detail="System reliance on single AIM. If this AIM degrades, combined modifier quality drops significantly.",
        impact_estimate="Diversifying AIM contributions reduces single-point-of-failure risk",
        recommendation="Review why other AIMs are underperforming. Consider expanding data sources for weaker AIMs.")

IF warmup_count > 5:
    warming_aims = [a for a, s in aim_status.items() if s == "WARM_UP"]
    QUEUE_ACTION(priority="LOW", category="DATA_ACQUISITION", dimension="D4",
        constraint_type="AIM_WARMUP_BACKLOG",
        title="{warmup_count} AIMs still in warm-up: {warming_aims}",
        detail="Large warm-up backlog means system is operating with limited intelligence.",
        impact_estimate="Providing historical data for bootstrapping could accelerate warm-up",
        recommendation="Review warm-up progress. Consider providing bootstrapped historical data for slow-warming AIMs.")

# ════════════════════════════════════════════════
# DIMENSION 5: EDGE TRAJECTORY (monthly only)
# ════════════════════════════════════════════════

IF diagnostic_mode == "MONTHLY":

    edge_30d = compute_system_edge(P3-D05, window=30)
    edge_60d = compute_system_edge(P3-D05, window=60)
    edge_90d = compute_system_edge(P3-D05, window=90)
    edge_start = compute_system_edge(P3-D05, window="ALL")
    
    # Per-regime breakdown
    edge_low_vol = compute_regime_edge(P3-D05, regime="LOW_VOL", window=60)
    edge_high_vol = compute_regime_edge(P3-D05, regime="HIGH_VOL", window=60)
    
    # Trend: compare 30d to 90d
    IF edge_90d > 0:
        edge_trend = (edge_30d - edge_90d) / edge_90d
    ELSE:
        edge_trend = 0.0
    
    d5_score = weighted_mean([
        (min(max(edge_30d, 0) / 0.02, 1.0),               0.3),   # current edge level
        (0.5 + min(max(edge_trend, -0.5), 0.5),            0.4),   # trend direction
        (min(max(min(edge_low_vol, edge_high_vol), 0) / 0.01, 1.0), 0.3)  # worst regime
    ])
    
    IF edge_trend < -0.15:
        QUEUE_ACTION(priority="HIGH", category="RESEARCH", dimension="D5",
            constraint_type="EDGE_DECLINING",
            title="System-wide expected edge declined {abs(edge_trend)*100:.0f}% over 60 days",
            detail="30d edge: {edge_30d:.4f}, 90d edge: {edge_90d:.4f}. Declining edge may indicate strategy decay, market microstructure shift, or AIM degradation.",
            impact_estimate="Identifying the cause (decay vs regime shift vs data issue) is prerequisite to corrective action",
            recommendation="Cross-reference with decay detector (D4), AIM weights (D4), and regime labels. If decay detected, Level 3 re-run may already be triggered.")
    
    IF edge_high_vol < 0:
        QUEUE_ACTION(priority="HIGH", category="RESEARCH", dimension="D5",
            constraint_type="REGIME_EDGE_COLLAPSE",
            title="HIGH_VOL regime edge is negative ({edge_high_vol:.4f})",
            detail="Strategy is losing money in high-volatility regimes. AIM-11 transition warnings and regime model accuracy should be checked.",
            impact_estimate="Fixing regime conditioning could prevent losses during volatile periods",
            recommendation="Check AIM-11 transition accuracy, regime model validation (P2-D08), and consider regime-conditional position sizing adjustments")

ELSE:
    d5_score = P3-D22.previous_diagnostic.d5_score IF EXISTS ELSE 0.5

# ════════════════════════════════════════════════
# DIMENSION 6: DATA COVERAGE GAPS
# ════════════════════════════════════════════════

data_issues = []
FOR EACH aim_id IN range(1, 16):
    IF P3-D01[aim_id].status == "ACTIVE":
        missing_rate = P3-D01[aim_id].missing_data_rate_30d
        IF missing_rate > 0.1:
            data_issues.append((aim_id, missing_rate))

asset_data_quality = {}
FOR EACH asset u IN P3-D00.active_assets:
    data_hold_count = count_data_holds(u, window=30)
    # Derive clean_rate from data_quality_log entries for this asset
    recent_logs = [e for e in P3-D17.data_quality_log if e.session in last_30_sessions]
    asset_entries = [e for e in recent_logs if u in e.flagged_assets or u not in e.held_assets]
    clean_count = sum(1 for e in recent_logs if u not in getattr(e, 'flagged_assets', []))
    quality_score = clean_count / max(len(recent_logs), 1)
    asset_data_quality[u] = {"holds": data_hold_count, "quality": quality_score}

d6_score = weighted_mean([
    (1.0 - len(data_issues) / 15.0,                                     0.5),
    (mean([v["quality"] for v in asset_data_quality.values()]),           0.3),
    (1.0 - sum(1 for v in asset_data_quality.values() if v["holds"] > 2) / max(len(asset_data_quality), 1), 0.2)
])

FOR EACH aim_id, missing_rate IN data_issues:
    aim_name = AIM_REGISTRY[aim_id].name
    QUEUE_ACTION(priority="HIGH" if missing_rate > 0.2 else "MEDIUM",
        category="DATA_ACQUISITION", dimension="D6",
        constraint_type="AIM_DATA_GAP",
        title="AIM-{aim_id:02d} ({aim_name}) data feed: {missing_rate*100:.0f}% missing in last 30d",
        detail="High missing rate degrades AIM quality and may cause DMA to suppress the AIM.",
        impact_estimate="Fixing data feed reliability restores AIM contribution to sizing decisions",
        recommendation="Verify data source availability. Check API connectivity. Consider alternative data providers.")

FOR EACH asset u, quality IN asset_data_quality.items():
    IF quality["holds"] >= 3:
        QUEUE_ACTION(priority="MEDIUM", category="DATA_ACQUISITION", dimension="D6",
            constraint_type="ASSET_DATA_UNRELIABLE",
            title="Asset {u}: {quality['holds']} DATA_HOLD events in 30 days",
            detail="Frequent data holds indicate unreliable price/volume feed for this asset.",
            impact_estimate="Unreliable data causes missed trading sessions and degrades EWMA/Kelly accuracy",
            recommendation="Investigate data source for {u}. Consider alternative data feeds or removing asset from universe if unresolvable.")

# ════════════════════════════════════════════════
# DIMENSION 7: RESEARCH PIPELINE THROUGHPUT
# ════════════════════════════════════════════════

last_injection = P3-D06.latest_event_timestamp()
days_since_injection = (now() - last_injection).days IF last_injection ELSE 999

# Level 3 decay events — how many triggered vs resolved
level3_events = P3-D04.decay_events.filter(level=3, window=90)
level3_unresolved = [e for e in level3_events if NOT e.resolved]

# AIM-14 auto-expansion attempts
expansion_attempts = P3-D06.filter(type="AUTO_EXPANSION", window=90)
expansion_successes = [e for e in expansion_attempts if e.outcome == "ADOPTED"]

d7_score = weighted_mean([
    (max(0, 1.0 - days_since_injection / 120.0),                            0.4),
    (1.0 - len(level3_unresolved) / max(len(level3_events), 1),             0.3),
    (len(expansion_successes) / max(len(expansion_attempts), 1),             0.3)
])

IF days_since_injection > 120:
    QUEUE_ACTION(priority="HIGH" if days_since_injection > 180 else "MEDIUM",
        category="RESEARCH", dimension="D7",
        constraint_type="INJECTION_DROUGHT",
        title="No new strategy injection in {days_since_injection} days",
        detail="System is running on stale research. No new strategies have been tested or compared.",
        impact_estimate="Fresh P1/P2 runs with new models/features could discover improved strategies",
        recommendation="Schedule Programs 1/2 run. Consider new model hypotheses or additional features.")

IF len(level3_unresolved) > 0:
    affected_assets = [e.asset for e in level3_unresolved]
    QUEUE_ACTION(priority="HIGH", category="RESEARCH", dimension="D7",
        constraint_type="LEVEL3_UNRESOLVED",
        title="{len(level3_unresolved)} Level 3 decay events unresolved — assets: {affected_assets}",
        detail="Level 3 decay has halted signals for these assets but no replacement strategy has been found or adopted.",
        impact_estimate="Each unresolved asset is producing zero signals — direct revenue loss",
        recommendation="Prioritise P1/P2 re-runs for {affected_assets}. If re-runs completed, review injection comparison results.")

# ════════════════════════════════════════════════
# DIMENSION 8: RESOLUTION VERIFICATION
# ════════════════════════════════════════════════

resolved_items = P3-D22.action_queue.filter(status="RESOLVED")
FOR EACH item IN resolved_items:
    metric_before = item.metric_snapshot_at_creation
    metric_now = get_current_metric(item.constraint_type)
    
    IF metric_improved(metric_before, metric_now, item.constraint_type):
        item.status = "VERIFIED"
        item.verified_at = now()
        item.verification_result = "IMPROVED"
    ELIF metric_unchanged(metric_before, metric_now):
        item.verification_result = "INCONCLUSIVE"
        # Keep as RESOLVED — may need more time
    ELSE:
        item.status = "OPEN"  # reopen
        item.verification_result = "NOT_IMPROVED"
        item.notes += " [Auto-reopened: metric did not improve after resolution]"

# Stale detection
FOR EACH item IN P3-D22.action_queue.filter(status IN ["OPEN", "ACKNOWLEDGED"]):
    IF (now() - item.created).days > 90:
        item.status = "STALE"

d8_score = 1.0 - len([i for i in P3-D22.action_queue if i.status in ["OPEN", "STALE"]]) / max(len(P3-D22.action_queue), 1)

# ════════════════════════════════════════════════
# AGGREGATE AND STORE
# ════════════════════════════════════════════════

diagnostic_result = {
    timestamp:      now(),
    mode:           diagnostic_mode,  # "WEEKLY" or "MONTHLY"
    scores: {
        strategy_portfolio:     d1_score,
        feature_portfolio:      d2_score,
        model_staleness:        d3_score,
        aim_effectiveness:      d4_score,
        edge_trajectory:        d5_score,
        data_coverage:          d6_score,
        research_pipeline:      d7_score,
        resolution_health:      d8_score
    },
    overall_health:  mean([d1_score, d2_score, d3_score, d4_score, d5_score, d6_score, d7_score, d8_score]),
    action_items_generated: len(new_actions_this_run),
    critical_count:  len([a for a in new_actions_this_run if a.priority == "CRITICAL"]),
    high_count:      len([a for a in new_actions_this_run if a.priority == "HIGH"]),
    queue_total:     len(P3-D22.action_queue),
    open_count:      len([a for a in P3-D22.action_queue if a.status == "OPEN"]),
    stale_count:     len([a for a in P3-D22.action_queue if a.status == "STALE"])
}

P3-D22.diagnostic_results.append(diagnostic_result)
SAVE P3-D22

# Notify if critical items generated
IF diagnostic_result.critical_count > 0:
    NOTIFY(user_id="ALL_ADMINS",
           message="System Health Diagnostic: {diagnostic_result.critical_count} CRITICAL action items generated. Overall health: {diagnostic_result.overall_health:.0%}",
           priority="HIGH")

GENERATE RPT-03 (Monthly Health — includes diagnostic summary)
```

### QUEUE_ACTION Helper

```
FUNCTION QUEUE_ACTION(priority, category, dimension, constraint_type, title, detail, impact_estimate, recommendation):
    
    # Deduplication: don't create a new action item if one with the same constraint_type
    # already exists and is OPEN, ACKNOWLEDGED, or IN_PROGRESS
    existing = P3-D22.action_queue.find(
        constraint_type=constraint_type, 
        status IN ["OPEN", "ACKNOWLEDGED", "IN_PROGRESS"]
    )
    IF existing:
        existing.last_seen = now()
        existing.detail = detail  # update with latest data
        RETURN
    
    # Snapshot current metric value for resolution verification (D8)
    metric_snapshot = get_current_metric(constraint_type)
    
    action = {
        action_id:          generate_action_id(),  # e.g. "ACT-2026-03-07-001"
        created:            now(),
        priority:           priority,
        category:           category,
        dimension:          dimension,
        constraint_type:    constraint_type,
        title:              title,
        detail:             detail,
        impact_estimate:    impact_estimate,
        recommendation:     recommendation,
        status:             "OPEN",
        acknowledged_by:    None,
        acknowledged_at:    None,
        resolved_at:        None,
        verified_at:        None,
        verification_result: None,
        notes:              "",
        metric_snapshot_at_creation: metric_snapshot,
        last_seen:          now()
    }
    
    P3-D22.action_queue.append(action)
    new_actions_this_run.append(action)
```

---

# ORCHESTRATOR — CAPTAIN (OFFLINE) SCHEDULING

```
P3-ORCH-OFFLINE: "captain_offline_orchestrator_A"

# Always running — event loop

WHILE Captain is active:
    
    # EVENT: New trade outcome received (via Redis SUBSCRIBE "captain:trade_outcomes")
    ON trade_outcome_received(outcome):
        RUN P3-PG-02 (DMA meta-learning update)
        RUN P3-PG-05 (BOCPD decay monitor)
        RUN P3-PG-06 (CUSUM decay monitor)
        RUN P3-PG-15 (Kelly parameter update)
        RUN P3-PG-14 (TSM simulation update)
    
    # SCHEDULED: Daily
    ON daily_close():
        RUN P3-PG-04 (per-AIM drift detection)
        RUN P3-PG-01 (AIM lifecycle check)
        RUN asset_warmup_check()  # check if any WARM_UP assets can transition to ACTIVE
    
    # EVENT: New asset added to universe
    ON asset_added(asset_id):
        RUN asset_bootstrap(asset_id)  # initialise EWMA/BOCPD/CUSUM from P1/P2 history
    
    # SCHEDULED: Weekly
    ON weekly_schedule():
        RUN Tier_1_AIM_retrain()  # Calls P3-PG-01 (AIM lifecycle manager) filtered to Tier 1 AIMs: 04, 06, 08, 11, 12, 15
        RUN P3-PG-03 (HDWM diversity check)
        RUN P3-PG-16B (system health diagnostic — WEEKLY mode)
    
    # SCHEDULED: Monthly
    ON monthly_schedule():
        RUN P3-PG-12 (AIM-13 sensitivity scan)
        RUN Tier_2_3_AIM_retrain()  # Calls P3-PG-01 (AIM lifecycle manager) filtered to Tier 2/3 AIMs: 01, 02, 03, 07, 09, 10, 13, 14
        RUN P3-PG-16B (system health diagnostic — MONTHLY mode, includes edge trajectory)
        GENERATE RPT-03 (Monthly Health)
        GENERATE RPT-04 (AIM Effectiveness)
        GENERATE RPT-08 (Probability Accuracy)
    
    # EVENT: Level 3 triggered
    ON level_3_trigger(asset):
        RUN P3-PG-13 (AIM-14 auto-expansion)
        SCHEDULE programs_1_2_rerun(asset)
    
    # EVENT: Strategy injection received
    ON injection_event(candidate, asset):
        RUN P3-PG-10 (injection comparison)
    
    # EVENT: User adoption decision
    ON adoption_decision(decision, asset):
        RUN P3-PG-11 (strategy transition)
    
    # EVENT: TSM file changed
    ON tsm_change(account):
        RUN P3-PG-14 (TSM re-simulation)
    
    # EVENT: Action item resolved by ADMIN
    ON action_item_resolved(action_id):
        RUN P3-PG-16B (system health diagnostic — D8 resolution verification only)
    
    # SCHEDULED: Quarterly
    ON quarterly_schedule():
        RUN P3-PG-07 (CUSUM bootstrap recalibration)
        GENERATE RPT-09 (Decision Change Impact — quarterly summary)
    
    # SCHEDULED: Annually
    ON annual_schedule():
        GENERATE RPT-10 (Annual Review)
```

---

# ASSET BOOTSTRAP AND WARM-UP TRANSITION

```
FUNCTION asset_bootstrap(asset_id):
    # Initialise EWMA, BOCPD, CUSUM for a newly added asset using P1/P2 historical data
    # Called when asset is added to universe (P3-D00)
    # P1 data path: P3-D00[asset_id].p1_data_path (e.g. /captain/data/p1_outputs/ES/)
    # P2 data path: P3-D00[asset_id].p2_data_path (e.g. /captain/data/p2_outputs/ES/)
    # Both validated by Command Block 10 (P3-PG-42) at onboarding.
    # Data is loaded from these paths into QuestDB for runtime READ/LOAD access.
    
    INPUT: P1 D-22 model_trade_log for asset_id's locked (m, k) from P2-D06
    INPUT: P2-D02 regime labels for asset_id
    
    # Step 1: Load historical trades using locked strategy's (m, k)
    locked = P2-D06[asset_id]
    historical_trades = LOAD D-22 WHERE m == locked.m AND k == locked.k
    regime_labels = LOAD P2-D02 WHERE asset == asset_id
    
    IF len(historical_trades) < 20:
        LOG "Insufficient historical trades for {asset_id} bootstrap — staying in WARM_UP"
        P3-D00[asset_id].captain_status = "WARM_UP"
        P3-D00[asset_id].warm_up_progress = len(historical_trades) / 20.0
        RETURN
    
    # Step 2: Initialise P3-D05 EWMA states from historical trades
    FOR EACH regime r IN [LOW_VOL, HIGH_VOL]:
        FOR EACH session ss IN [1, 2, 3]:
            # D-22 has regime_tag but no session field; derive session from trade date/time
            # using the asset's exchange_timezone and session schedule from P3-D00
            regime_session_trades = [t for t in historical_trades
                                     if t.regime_tag == r
                                     and derive_session(t.date, P3-D00[asset_id].exchange_timezone) == ss]
            IF len(regime_session_trades) >= 5:
                wins = [t for t in regime_session_trades if t.r > 0]
                losses = [t for t in regime_session_trades if t.r <= 0]
                P3-D05[asset_id][r][ss].win_rate = len(wins) / len(regime_session_trades)
                P3-D05[asset_id][r][ss].avg_win = mean([t.r for t in wins]) IF wins ELSE 0
                P3-D05[asset_id][r][ss].avg_loss = mean([abs(t.r) for t in losses]) IF losses ELSE 0
            ELSE:
                # Insufficient data for this regime/session — use unconditional
                P3-D05[asset_id][r][ss] = compute_unconditional(historical_trades)
    
    # Step 3: Initialise P3-D04 BOCPD/CUSUM from in-control baseline
    in_control_returns = [t.r for t in historical_trades]
    P3-D04[asset_id].bocpd = initialise_bocpd(in_control_returns)
    P3-D04[asset_id].cusum = initialise_cusum(in_control_returns)
    
    # Step 4: Compute initial Kelly parameters
    FOR EACH regime r IN [LOW_VOL, HIGH_VOL]:
        FOR EACH ss IN [1, 2, 3]:
            p = P3-D05[asset_id][r][ss].win_rate
            W = P3-D05[asset_id][r][ss].avg_win
            L = P3-D05[asset_id][r][ss].avg_loss
            IF L > 0 AND p > 0:
                P3-D12[asset_id][r][ss].kelly_full = p - (1 - p) * (L / W) IF W > 0 ELSE 0
            ELSE:
                P3-D12[asset_id][r][ss].kelly_full = 0
    
    # Step 5: Bootstrap Tier 1 AIM states to BOOTSTRAPPED
    # Resolves first-startup circular dependency: assets need AIMs to be at least
    # BOOTSTRAPPED to transition WARM_UP → ACTIVE, and AIMs need active assets for data.
    # By setting Tier 1 AIMs to BOOTSTRAPPED from historical data, the first asset
    # can activate without waiting for real-time AIM warm-up.
    tier1_aims = [4, 6, 8, 11, 12, 15]
    FOR EACH aim_id IN tier1_aims:
        IF P3-D01[aim_id].status IN ["INSTALLED", "COLLECTING", "WARM_UP"]:
            P3-D01[aim_id].status = "BOOTSTRAPPED"
            LOG "AIM-{aim_id} set to BOOTSTRAPPED from historical data for asset {asset_id}"
    
    LOG "Asset {asset_id} bootstrapped from {len(historical_trades)} historical trades"

FUNCTION asset_warmup_check():
    # Daily check: can any WARM_UP assets transition to ACTIVE?
    
    FOR EACH asset u IN P3-D00 WHERE captain_status == "WARM_UP":
        
        # Condition 1: EWMA baseline exists (min 20 regime-conditional trades)
        ewma_ready = all(
            P3-D05[u][r][ss].win_rate is not None
            for r in [LOW_VOL, HIGH_VOL]
            for ss in [1, 2, 3]
        )
        
        # Condition 2: All Tier 1 AIMs at least BOOTSTRAPPED or ELIGIBLE for this asset
        # BOOTSTRAPPED = set by asset_bootstrap() from historical data (first-startup path)
        # ELIGIBLE = reached via normal lifecycle (INSTALLED→COLLECTING→WARM_UP→ELIGIBLE)
        # ACTIVE = already activated by user
        tier1_aims = [4, 6, 8, 11, 12, 15]
        aims_ready = all(
            P3-D01[a].status IN ["BOOTSTRAPPED", "ELIGIBLE", "ACTIVE"]
            for a in tier1_aims
        )
        
        # Condition 3: Regime model available
        regime_ready = P2-D07[u] is not None AND P2-D07[u].model_object is not None OR P2-D07[u].model_type == "BINARY_ONLY"
        
        # Condition 4: P1/P2 validation complete
        p1p2_ready = P3-D00[u].p1_status == "VALIDATED" AND P3-D00[u].p2_status == "VALIDATED"
        
        IF ewma_ready AND aims_ready AND regime_ready AND p1p2_ready:
            P3-D00[u].captain_status = "ACTIVE"
            LOG "Asset {u} transitioned from WARM_UP to ACTIVE"
            NOTIFY(user_id="ALL_ADMINS",
                   message="Asset {u} is now ACTIVE — signals will be generated at next session.",
                   priority="HIGH")
        ELSE:
            # Update progress
            checks = [ewma_ready, aims_ready, regime_ready, p1p2_ready]
            P3-D00[u].warm_up_progress = sum(checks) / len(checks)
```

---

# P1/P2 RE-RUN INTERFACE

When Level 3 decay triggers `SCHEDULE programs_1_2_rerun(asset)`, the mechanism is:

1. Captain logs the re-run request to P3-D06 (injection_history) with status `RERUN_REQUESTED`
2. ADMIN is notified via all channels: "Level 3 decay for {asset} — Programs 1/2 re-run required"
3. The team runs Programs 1/2 externally (these are batch pipelines, not part of Captain runtime)
4. When P1/P2 outputs are available, team uploads them via the GUI "Upload new asset" action or triggers injection event
5. Captain's strategy injection flow (Offline Block 4) processes the new candidate

This is a human-in-the-loop handoff by design — Programs 1/2 require model hypotheses and dataset preparation that cannot be fully automated.

---

# BLOCK-TO-BLOCK DATA FLOW

```
Block 1 (AIM Training) ──► P3-D01 (model states) ──► Captain (Online) Block 3
                       ──► P3-D02 (meta-weights) ──► Captain (Online) Block 3

Block 2 (Decay Detection) ──► P3-D04 (detector states) ──► Block 6 (Level 3 trigger)
                          ──► P3-D12 (sizing overrides) ──► Captain (Online) Block 4

Block 3 (Pseudotrader) ──► P3-D11 (retest results) ──► Block 4 (injection input)
                       ──► RPT-09

Block 4 (Injection) ──► P3-D06 (injection history) ──► Block 3 (phasing)
                    ──► RPT-05

Block 5 (AIM-13 Scan) ──► P3-D13 (sensitivity results) ──► Block 6 (trigger)
                      ──► RPT-03

Block 6 (AIM-14 Expansion) ──► Block 4 (new candidates) ──► RPT-05

Block 7 (TSM Simulation) ──► P3-D08 (pass probabilities) ──► Captain (Online) Block 4
                         ──► RPT-07

Block 8 (Kelly Updates) ──► P3-D05 (EWMA states) ──► Captain (Online) Block 4
                        ──► P3-D12 (Kelly params) ──► Captain (Online) Block 4

Block 9 (Health Diagnostic) ──► P3-D22 (diagnostic results + action queue) ──► Captain (Command) GUI
                             ◄── P3-D17 (Online Block 9 capacity_state)
                             ◄── P2-D06, P2-D07, P3-D00..D06, P3-D13
```

---

# ERROR HANDLING

| Block | Failure | Response |
|-------|---------|----------|
| Block 1 (AIM Training) | Single AIM fails to train | Lock AIM at neutral (1.0), flag for manual review, other AIMs unaffected |
| Block 2 (Decay Detection) | BOCPD numerical overflow | Reset run-length distribution, alert, use CUSUM as sole detector until resolved |
| Block 3 (Pseudotrader) | Replay crashes on historical data | Skip pseudotrader, present injection with "UNTESTED" flag, require extra user scrutiny |
| Block 5 (AIM-13) | Perturbation grid too large | Cap at 500 configurations, sample randomly, note reduced coverage |
| Block 7 (TSM Simulation) | No in-control data available | Use unconditional return distribution, flag reduced confidence |
| Block 4 (Injection) | Offline comparison timeout (>24h) | Present injection with "COMPARISON PENDING" flag, alert user |
| Block 6 (AIM-14) | No viable candidates found | Alert user for manual intervention, retain current strategy |
| Block 8 (Kelly) | Division by zero (no losses) | Cap Kelly at 0.5 (half-Kelly), flag as "insufficient loss data" |
| Block 9 (Health Diagnostic) | Dimension computation fails | Score that dimension at 0.5 (neutral), log error, proceed with other dimensions. Non-blocking — does not affect signal delivery. |
| Block 9 (Health Diagnostic) | P3-D22 write fails | Retry once. If still fails, alert ADMIN. Diagnostic results lost for this cycle but no impact on trading operations. |

---

*This document specifies all Captain (Offline) operations. For Captain (Online) see `Program3_Online.md`. For Captain (Command) see `Program3_Command.md`.*
