# Cross-Reference: Pre Deploy Specs vs V3 Additions — Line-by-Line

**Purpose:** For every V3 change, the EXACT location in the original spec where it needs to be integrated. Nomaan reads the original spec, then applies these insertions/modifications.

---

# Program3_Online.md — 6 Changes

## Change O1: Fee in Kelly Risk (Block 4, Line ~847)

**Original (line 847):**
```
kelly_contracts = account_kelly * account_capital / risk_per_contract
final_contracts[u][ac_id] = min(floor(kelly_contracts), tsm_cap)
```

**Insert BEFORE line 847:**
```
expected_fee = get_expected_fee(ac_id, u, 1)
risk_per_contract = risk_per_contract + expected_fee
```

**And CHANGE line 848 to:**
```
topstep_daily_cap = floor(topstep_state.daily_exposure / risk_per_contract) IF tsm.get("topstep_optimisation") ELSE 999
scaling_cap = (topstep_state.scaling_tier_micros - current_open_positions_micros) IF tsm.get("scaling_plan_active") ELSE 999
final_contracts[u][ac_id] = min(floor(kelly_contracts), tsm_cap, topstep_daily_cap, scaling_cap)
```

**Source:** `Nomaan_Edits_Fees.md` Change 2 + `Topstep_Optimisation_Functions.md` Part 6.

## Change O2: HMM Session Budget in Block 5 (Line ~905-967)

**Original (line 905):** Block 5 `trade_selection_A` ranks by expected_edge × contracts and selects based on correlation + position limits.

**V3 Addition:** BEFORE the ranking, compute session budget from HMM:
```
# Insert at start of PG-25, before "Compute expected edge"
IF aim16_active:
    session_budget = aim16_hmm_inference(remaining_daily_budget, observations_today)
ELSE:
    session_budget = remaining_daily_budget  # equal allocation if HMM not active

# Then within the ranking loop, enforce session_budget:
# ranked_assets are allocated from session_budget, top-down by score
# When session_budget exhausted → remaining signals BLOCKED with reason "SESSION_BUDGET_EXHAUSTED"
```

**Source:** `HMM_Opportunity_Regime_Spec.md` Part 3, Section 3.7.

## Change O3: Circuit Breaker Screen AFTER Block 5B, BEFORE Block 6 (Line ~1076)

**Insert NEW block between Block 5B and Block 6:**
```
# BLOCK 7B — CIRCUIT BREAKER SCREEN
# Runs AFTER Block 5B quality gate, BEFORE Block 6 signal output.
# For each recommended trade, check all 5 circuit breaker layers.
# See Topstep_Optimisation_Functions.md Part 6, Section "Online Block 7".
```

**Full pseudocode:** `Topstep_Optimisation_Functions.md` lines 598-629 (PG-27B).

**Original Block 7 (Position Monitoring)** at line ~1180 is UNCHANGED — the circuit breaker screen is a separate function (PG-27B) that runs before signals are emitted, not during position monitoring.

## Change O4: resolve_commission Fee Schedule (Line ~1305-1324)

**Original (line 1317):**
```
IF tsm AND tsm.commission_per_contract:
    RETURN tsm.commission_per_contract * contracts * 2
```

**Change to:**
```
IF tsm:
    IF tsm.get("fee_schedule"):
        instrument_fees = tsm["fee_schedule"]["fees_by_instrument"].get(asset)
        IF instrument_fees:
            RETURN instrument_fees["round_turn"] * contracts
    IF tsm.get("commission_per_contract"):
        RETURN tsm.commission_per_contract * contracts * 2
```

**Source:** `Nomaan_Edits_Fees.md` Change 2.

## Change O5: Add get_expected_fee() Function (After line ~1340)

**Insert new function after resolve_actual_entry_price():**
```
FUNCTION get_expected_fee(account_id, asset, contracts=1):
    tsm = tsm_configs.get(account_id)
    IF tsm AND tsm.get("fee_schedule"):
        instrument_fees = tsm["fee_schedule"]["fees_by_instrument"].get(asset)
        IF instrument_fees:
            RETURN instrument_fees["round_turn"] * contracts
    IF tsm AND tsm.get("commission_per_contract"):
        RETURN tsm.commission_per_contract * contracts * 2
    RETURN 0
```

**Source:** `Nomaan_Edits_Fees.md` Change 2.

## Change O6: P3-D23 Intraday State Update (After resolve_position, Line ~1303)

**Insert after `PUBLISH "captain:trade_outcomes"` (line 1303):**
```
# Update circuit breaker intraday state
IF tsm.get("topstep_optimisation"):
    P3-D23[pos.account].L_t += net_pnl
    P3-D23[pos.account].n_t += 1
    P3-D23[pos.account].L_b[pos.model_m] = P3-D23[pos.account].L_b.get(pos.model_m, 0) + net_pnl
    P3-D23[pos.account].n_b[pos.model_m] = P3-D23[pos.account].n_b.get(pos.model_m, 0) + 1
```

**Source:** `Nomaan_Edits_P3.md` Change 2.

---

# Program3_Offline.md — 3 Changes

## Change F1: AIM-16 HMM Training (After Block 1, Line ~470)

**Insert new section after Block 1 AIM Training:**
```
# AIM-16 — Opportunity Regime HMM Training (PG-01C)
# See HMM_Opportunity_Regime_Spec.md Part 3, Section 3.5
```

## Change F2: Pseudotrader CB Extension (After Block 3, Line ~537)

**Insert after existing PG-09:**
```
# PG-09B: Pseudotrader Circuit Breaker Replay
# PG-09C: Circuit Breaker Grid Search
# See Topstep_Optimisation_Functions.md Part 8
```

## Change F3: β_b Estimation (In Block 8, After Kelly Updates)

**Insert after existing Kelly parameter updates:**
```
# PG-16C: Circuit Breaker Parameter Estimator
# See Nomaan_Edits_P3.md Change 4
```

---

# Program3_Command.md — 2 Changes

## Change C1: SOD Topstep Parameters (Block 8 Daily Reconciliation, Line ~1014-1017)

**Insert after daily_loss_used reset (line 1016):**
```
# Topstep SOD parameter computation
# See Topstep_Optimisation_Functions.md Part 6, Section "Command Block 8"
# + Nomaan_Edits_P3.md Change 1
```

## Change C2: Payout Notification + GUI Panels (Block 2 + Block 8)

**Insert after SOD computation:**
```
# Payout recommendation notification
# See Nomaan_Edits_P3_Command_GUI.md
```

**Add to Block 2 gui_data_server_A:**
```
# Payout panel + Scaling display
# See Nomaan_Edits_P3_Command_GUI.md
```

---

# Program3_Architecture.md — 3 Changes

## Change A1: Data Store Catalogue (Section 3, Line ~148)

**ADD to P3 dataset list:**
```
P3-D23: circuit_breaker_intraday_state (per account)
P3-D25: circuit_breaker_params (per account, per model)
P3-D26: hmm_opportunity_state
```

## Change A2: Asset Onboarding (Section 15)

**ADD TRAINING_ONLY to captain_status enum.**

## Change A3: Open Parameters (Section 9)

**ADD:**
```
threshold_OO_floor: 0.55 (P1 Block 5)
threshold_OO_percentile: 0.85 (P1 Block 5)
topstep_params: {p, e, c, lambda} (P3 Command Block 8)
```

---

# Program1.md — 2 Changes

## Change P1: OO Threshold (Block 5, Line ~927)

**Original:** `OO ≥ threshold_OO; TBD`
**Change to:** `OO ≥ threshold_OO_floor (0.55) AND OO in top threshold_OO_percentile (85th) of all (m,k) pairs`

## Change P2: Open Parameters (Part L)

**ADD:**
```
threshold_OO_floor: 0.55
threshold_OO_percentile: 0.85
```

---

# P3_Dataset_Schemas.md — 3 Additions

## Add P3-D23 Schema

```
P3-D23: circuit_breaker_intraday_state
    account_id: string
    L_t: float (cumulative net P&L today)
    n_t: int (trades taken today)
    L_b: dict {model_m: float} (per-basket P&L)
    n_b: dict {model_m: int} (per-basket trade count)
    last_updated: datetime
    Reset: 19:00 EST daily
```

## Add P3-D25 Schema

```
P3-D25: circuit_breaker_params
    account_id: string
    model_m: int
    r_bar: float
    beta_b: float
    sigma: float
    rho_bar: float
    n_observations: int
    p_value: float
    last_updated: datetime
```

## Add P3-D26 Schema

```
P3-D26: hmm_opportunity_state
    hmm_params: {pi, A, mu, sigma, tvtp_coefs}
    current_state_probs: array[3]
    opportunity_weights: dict {session: weight}
    prior_alpha: dict {session: array[3]}
    last_trained: datetime
    training_window: int
    n_observations: int
    cold_start: bool
```

## Modify P3-D00 Schema

**ADD to captain_status enum:** `TRAINING_ONLY`

## Modify P3-D08 Schema

**ADD fields:**
```
topstep_optimisation: bool (optional, default false)
topstep_params: {p, e, c, lambda, max_payouts_remaining} (optional)
topstep_state: {mdd_pct, fee_per_trade, risk_per_trade_eff, max_trades, ...} (computed at SOD)
fee_schedule: {type, fees_by_instrument, slippage_model} (optional)
payout_rules: {max_per_payout, commission_rate, ...} (optional)
scaling_plan_active: bool (optional, XFA only)
scaling_tier_micros: int (computed from profit tier)
```

---

# AIMRegistry.md — 1 Addition

## Add AIM-16

```
AIM-16: Opportunity Regime HMM
    Purpose: Detect opportunity regimes across trading sessions. Output budget allocation weights.
    Data source: Session-level observations (signal count, mean OO, volume z, VIX, cross-asset corr)
    Model: Gaussian HMM with time-varying transition probabilities (TVTP)
    Output: opportunity_weight per session window
    Consumed by: Online Block 5 (trade selection / budget allocation)
    Training: Offline Block 1 (PG-01C), Baum-Welch on 60-day rolling window
    Cold start: Equal weights, 50/50 blend until Day 60
    Stored in: P3-D26
    See: HMM_Opportunity_Regime_Spec.md
```

---

# Implementation_Checklist.md — New Tasks

**ADD to Phase 0:**
- Task 0.3: Write model_generator.py + config (`Nomaan_Edits_P1.md`)
- Task 0.4: Add OO threshold two-tier filter to Block 5 (`Nomaan_Edits_P1.md`)

**ADD to Phase 1 (after Task 1.2):**
- Task 1.2b: Create P3-D23, D25, D26 tables in QuestDB (schemas above)

**ADD to Phase 2 (new tasks):**
- Task 2.X: Implement circuit breaker screen PG-27B (`Nomaan_Edits_P3.md`)
- Task 2.X: Implement β_b estimation PG-16C (`Nomaan_Edits_P3.md`)
- Task 2.X: Implement pseudotrader CB extension PG-09B/C (`Nomaan_Edits_P3.md`)
- Task 2.X: Update resolve_commission for fee_schedule (`Nomaan_Edits_Fees.md`)
- Task 2.X: Add get_expected_fee() (`Nomaan_Edits_Fees.md`)
- Task 2.X: Implement SOD Topstep params in Block 8 (`Topstep_Optimisation_Functions.md`)
- Task 2.X: Add payout notification to Command Block 8 (`Nomaan_Edits_P3_Command_GUI.md`)
- Task 2.X: Add GUI payout panel + scaling display (`Nomaan_Edits_P3_Command_GUI.md`)

**ADD to Phase 3:**
- Task 3.X: Implement AIM-16 HMM training PG-01C (`HMM_Opportunity_Regime_Spec.md`)
- Task 3.X: Implement HMM session allocation in Block 5 (`HMM_Opportunity_Regime_Spec.md`)
- Task 3.X: Add TRAINING_ONLY status to P3-D00 (`HMM_Opportunity_Regime_Spec.md`)

---

# Files with NO Changes Required

The following Pre Deploy files are UNCHANGED by the V3 additions and remain valid as-is:

| File | Reason No Change Needed |
|------|----------------------|
| Block 2 KTR.md | P1 Block 2 unchanged |
| Block 3 Threshold.md | P1 Block 3 unchanged |
| Block 4.md | P1 Block 4 unchanged |
| Block 5.md | P1 Block 5 changes are in Nomaan_Edits_P1.md (additive, not modification) |
| BOCPD_Implementation_Guide.md | BOCPD unchanged |
| Kelly_Implementation_Guide.md | Kelly core unchanged (fee is additive) |
| DMA_MoE_Implementation_Guide.md | DMA unchanged (AIM-16 uses same framework) |
| XGBoost Manual.md | Regime classifier unchanged |
| GovernancePolicy.md | Governance unchanged |
| ChangeManagementPolicy.md | CMP unchanged |
| NotificationSpec.md | Notification framework unchanged (new notifications use existing system) |
| ModelValidationPolicy.md | Validation policy unchanged |
| RegimeClassificationMethods.md | Methods unchanged |
| All 2026-02-* dated files | Research/reference docs, not spec |
| AIM_Extractions.md | Research reference |
| AIM_Research_Notes.md | Research reference |
| SystemBuild_*.md | Build context docs |
| CaptainNotes.md | Planning notes |
| Program3_BuildContext.md | Build context |
| PROGRAM_FULL_FLOW.md | Flow overview (Master Build Guide supersedes for reading order) |
| ProgramFlowOverall.md | Flow overview |
| README.md | Readme |
| Nomaan_Send.md | Original send instructions (Master Build Guide supersedes) |
| NomaanSendHowTo.md | Send instructions |
| Phase3_Upload_Checklist.md | Upload checklist |
| LocalFileRequirements.md | File requirements |
| TestIndex.md | Test reference |
| C2_CONTROL_MODELS.md | Control model reference |
| EdgeImprovementPlanNotes.md | Research reference |
| SystemPointCheck.md | Point check reference |
| Program1_Program2_Changes_For_Nomaan.md | Already applied changes |
| Program3_Online_PrepNotes.md | Prep notes |
| Program3_Remaining_PrepNotes.md | Prep notes |
| Program2.md | Minor additions only (V3+ regime types — handled in V3_Architecture_Plan.md) |
| UserManagementSetup.md | Already describes multi-user — no changes needed, just build it from start |
| 26/2/26 V1.md | Historical architecture reference — superseded by Program1.md. No V3 conflicts. |
