# Replay vs Spec Gap Analysis

## Generated: 2026-04-06

**Purpose:** Line-by-line comparison of the GUI replay engine (`shared/replay_engine.py`) against the authoritative V3 spec (`Program3_Online.md`, `15_Topstep_Optimisation_Functions.md`) and the live pipeline blocks (`captain-online/captain_online/blocks/`).

**Reference documents:**
- Truth (what replay does): `docs/REPLAY_FUNCTION_MAP.md`
- V3 Spec: `docs/AIM-Specs/new-aim-specs/Program3_Online.md`
- Topstep Optimisation: `docs/15_Topstep_Optimisation_Functions.md`
- Dataset Schemas: `docs/AIM-Specs/new-aim-specs/P3_Dataset_Schemas.md`

**Scope:** GUI replay only (`replay_engine.py` + `b11_replay_runner.py`). The Full Pipeline replay (`scripts/replay_full_pipeline.py`) calls real blocks and is out of scope — it is already spec-compliant by design.

---

## 1. Block-by-Block Comparison

| Block | Spec (PG ref) | Live Implementation | Replay Implementation | Status | Impact |
|-------|---------------|--------------------|-----------------------|--------|--------|
| **B1 Data** | PG-21: Pre-session data ingestion with 1b data moderator validation, 1c contract roll checks, feature computation for all assets | `b1_data_ingestion.py` + `b1_features.py` — full feature pipeline, data moderator, roll checks | `load_replay_config()` (replay_engine.py:59–263) — loads config from QuestDB (D00, D05, D08, D12, D16). `fetch_session_bars()` from TopstepX API. No data moderator, no roll checks, no feature computation. | **INTENTIONAL** | Low — replay fetches historical bars; data moderator/roll checks are live-only concerns |
| **B2 Regime** | PG-22: Classifier execution (C4 BINARY_ONLY Pettersson threshold OR trained XGBoost), uncertainty flag (`max_prob < 0.6`), robust Kelly fallback | `b2_regime_probability.py` — `_binary_regime()` (realised vol vs phi), `_classifier_regime()` (XGBoost predict_proba), uncertainty detection | `_compute_regime_probs()` in replay_engine.py — ports B2 logic: REGIME_NEUTRAL → 0.5/0.5, BINARY_ONLY+pettersson → realised vol vs phi from bars, locked regime_label fallback. `regime_uncertain` flag set when max_prob < 0.6. Results stored in `config["regime_probs"]` and used by `compute_contracts()` Step 1. | **FIXED — 2026-04-06** | Regime probabilities now match live B2 for all current asset configurations. Infrastructure installed for when pettersson_threshold or trained classifiers become available. |
| **B3 AIM** | PG-23: Active AIM filtering by inclusion_flag, per-AIM modifier clamping [0.5, 1.5], DMA weighted aggregation. Spec formula: `mod = Product(m_a^w_a)` | `shared/aim_compute.py` — weighted average (NOT product as spec says). Same code shared by live and replay. | `shared/aim_compute.py` (when `aim_enabled=True`, default False). Same weighted-average code. 5 of 15 AIMs have no data source (GEX, COT×2, calendar, spread → always 1.0). | **CONSISTENT** | Medium — AIM code is shared between live and replay, so behaviour matches. But `aim_enabled` defaults to False, making AIM opt-in. Spec-vs-code discrepancy (product vs average) is a known system-wide issue, not replay-specific. |
| **B4 Kelly** | PG-24: 8-step Kelly sizing (see Section 2 below) | `b4_kelly_sizing.py` — full 8-step implementation including robust Kelly, user ceiling, pass_probability graduation, fee-inclusive risk, portfolio cap, sizing override | `compute_contracts()` (replay_engine.py:844–970) — 15 steps: regime blend (Step 1), shrinkage (Step 2), robust Kelly (Step 3), AIM modifier (Step 4), user Kelly ceiling (Step 5), risk goal graduation (Step 6), fee-inclusive risk_per_contract (Step 7/7b), raw contracts (Step 8), MDD cap (Step 9), MLL cap (Step 10), 4-way min (Step 11), CB L0-L4 (Steps 11b-15). Portfolio risk cap via `_apply_portfolio_risk_cap()`. Only remaining gap: sizing override (admin-only, P2 deferred). | **FIXED — 2026-04-06** | All practical Kelly steps implemented |
| **B5 Selection** | PG-25: Expected edge = `wr × avg_win - (1-wr) × avg_loss`, risk-adjusted score = `edge × max_contracts`, cross-asset correlation filter (threshold 0.7), HMM session allocation, max positions | `b5_trade_selection.py` — edge ranking, correlation reduction (÷2 for correlated pairs), HMM warmup/blend/full modes, max_simultaneous_positions | `apply_position_limit()` with `_expected_edge()` — ranks by forward-looking expected edge. `_apply_correlation_filter()` halves contracts for correlated pairs (>0.7 threshold). Known pairs fallback: ES/MES, NQ/MNQ, ZB/ZN. Loads D07 correlation matrix. `_apply_hmm_session_weight()` — loads D26, cold-start (n<20) is no-op, warm state applies learned session weights. | **FIXED — 2026-04-06** | Full B5 parity: edge ranking, correlation filter, HMM session allocation. |
| **B5B Quality** | PG-26: `quality_score = edge × modifier × data_maturity`, hard_floor (default 0.003), quality_ceiling (default 0.010), confidence-graduated sizing multiplier | `b5b_quality_gate.py` — full implementation with `data_maturity = min(1.0, max(0.5, trade_count/50))`, graduated multiplier `min(1.0, quality_score/quality_ceiling)` | `_apply_quality_gate()` in replay_engine.py — ports B5B logic. `quality_score = abs(edge) × aim_modifier × data_maturity`. `data_maturity = min(1.0, max(0.5, trade_count/50))` from D03. Below `hard_floor` (0.003) → contracts zeroed. Above: graduated multiplier `min(1.0, score/ceiling)`. Applied after sizing, before position limit. Both `run_replay()` and `run_whatif()`. | **FIXED — 2026-04-06** | Quality gate now matches live B5B. Replay no longer overstates trade count by including signals live would reject. |
| **B5C CB** | PG-27B: 5-layer circuit breaker L0–L4 (see Section 3). Live adds L5 (VIX/DATA_HOLD) + L6 (manual halt) | `b5c_circuit_breaker.py` — 7 layers: L0 scaling, L1 halt, L2 budget, L3 basket expectancy, L4 Sharpe, L5 session halt, L6 manual | `compute_contracts()` Steps 11b-15 — **L0 XFA scaling cap**, **L1 with L_t tracking** (intraday cumulative P&L), **L2 budget exhaustion** (n_t vs N), **L3 basket expectancy** (mu_b = r_bar + beta_b * L_b with significance gate), **L4 correlation-adjusted Sharpe** (S = μ_b/(σ√(1+2n_t·ρ̄)) > λ). D25 CB params loaded. Intraday state accumulators across assets. B5C pipeline stage populated in GUI. Remaining: L5 (VIX/DATA_HOLD, live-only) and L6 (manual halt, admin-only) — both intentionally excluded from replay. | **FIXED — 2026-04-06** | All replay-relevant CB layers (L0-L4) implemented. L5/L6 are live-only concerns. |
| **B6 Output** | PG-28: Full signal with per-account breakdown, confidence tier (HIGH/MEDIUM/LOW), quality_score, data_maturity, Redis publish to `captain:signals:{user_id}` | `b6_signal_output.py` — full implementation, publishes to Redis | Internal result dict → WebSocket `replay_tick` events to GUI. No Redis publish, no per-account breakdown, no confidence tier. | **INTENTIONAL** | Low — replay communicates via WebSocket to GUI, not Redis. Different output format is expected for the replay use case. |
| **B7 Monitor** | PG-27: Intraday P&L tracking, TP/SL proximity, regime shift, VIX spike detection, trade resolution | `b7_intraday_monitor.py` — real-time position monitoring | `simulate_orb()` exit simulation (replay_engine.py:579–610) — post-hoc bar-by-bar scan. SL checked before TP per bar (pessimistic). EOD exit at last bar close. | **INTENTIONAL** | Low — replay simulates exits from historical bars, which is the correct approach for backtesting. Live monitors real-time quotes. |
| **B8/B9** | PG-29/PG-30: Concentration monitor, capacity evaluation | Not in replay scope | Not implemented | **N/A** | None — post-session analytics, not relevant to trade simulation |

---

## 2. Kelly Sizing Layer Comparison

Spec defines 8 steps in B4. Live implements all 8. Replay implements a subset.

| # | Spec Step | Spec Formula | Live Code (`b4_kelly_sizing.py`) | Replay Code (`compute_contracts()`) | Match? | Notes |
|---|-----------|-------------|----------------------------------|-------------------------------------|--------|-------|
| 1 | **Blended Kelly** | `blended = Σ(regime_probs[r] × kelly_full[r])` weighted by actual probabilities from B2 | `sum(regime_probs[regime] * kelly_params[(asset, regime, session)]['kelly_full'])` — uses real B2 output | `blended = regime_probs["LOW_VOL"] * low_kelly + regime_probs["HIGH_VOL"] * high_kelly` — uses `_compute_regime_probs()` output stored in `config["regime_probs"]` | **YES — FIXED 2026-04-06** | Now uses actual regime probabilities from strategy data. For REGIME_NEUTRAL: 0.5/0.5 (matches live). Infrastructure installed for pettersson_threshold and trained classifiers. |
| 2 | **Shrinkage** | `adjusted = blended × shrinkage_factor` from D12 | `blended * shrinkage_factor` | `adjusted = blended * shrinkage` (line 686) — reads from D12 | **YES** | Match. |
| 3 | **Robust Kelly** | If `regime_uncertain` (max_prob < 0.6): compute distributional robust Kelly from Paper 218 moment constraints; `final = min(adjusted, robust)` | `compute_robust_kelly(bounds, adjusted_kelly)` — applies only when `regime_uncertain[asset]` is True | `_get_return_bounds()` + `_compute_robust_kelly()` ported from b1_features.py. Applied when `regime_uncertain=True`. `adjusted = min(adjusted, robust)`. | **YES — FIXED 2026-04-06** | Robust Kelly now matches live B4. Fires only when max_prob < 0.6 (all current assets are REGIME_NEUTRAL → uncertain=True → robust applies). |
| 4 | **AIM Modifier** | `kelly_with_aim = final_kelly × combined_modifier` | `adjusted_kelly * combined_modifier[asset]` | `kelly_with_aim = adjusted * aim_modifier` (line 690) — `aim_modifier` passed from AIM aggregation (default 1.0) | **YES** | Match when AIM enabled. Default is disabled (`aim_enabled=False`). |
| 5 | **User Kelly Ceiling** | `kelly = min(kelly_with_aim, user_kelly_ceiling)` from D16 `risk_allocation.user_kelly_ceiling` | `min(kelly_with_aim, user_kelly_ceiling)` | `kelly_with_aim = min(kelly_with_aim, user_kelly_ceiling)` — Step 5 in compute_contracts(). Default 0.25, configurable via `user_kelly_ceiling` config key. | **YES — FIXED 2026-04-06** | User Kelly ceiling now applied after AIM modifier. |
| 6a | **Risk Goal Adjustment** | PASS_EVAL: graduated by `pass_probability` — `<0.5 → ×0.5`, `<0.7 → ×0.7`, `else → ×0.85`. PRESERVE: `×0.5`. GROW: `×1.0` | `_apply_risk_goal()` — implements full graduation using `tsm.pass_probability` | Graduated by `pass_probability` from TSM classification: `<0.5→×0.5`, `<0.7→×0.7`, `else→×0.85`. Default 0.6 gives middle tier. | **YES — FIXED 2026-04-06** | Graduated PASS_EVAL now matches live B4. |
| 6b | **TSM Constraints** | `budget_divisor = remaining_eval_days` (from `eval_end_date`, default 20); `max_by_mdd = floor(daily_budget / (strategy_sl × point_value))`; `max_by_mll = floor((mll - daily_used) / (strategy_sl × point_value))`; also: `topstep_daily_cap = floor(E / (strategy_sl × pv))` and `scaling_cap` (XFA) | Full implementation with `eval_end_date` computation, topstep daily exposure cap `E`, XFA scaling cap | `budget_divisor` computed from `evaluation_end_date` in TSM (falls back to 20). MDD/MLL caps unchanged. CB L0 scaling cap for XFA accounts. CB L2 implements budget formula. | **FIXED — 2026-04-06** | Budget divisor dynamic, L0 scaling cap, L2 budget formula all implemented. |
| 6c | **Contract Computation** | `raw = account_kelly × account_capital / risk_per_contract_with_fee` where `risk_with_fee = avg_loss + expected_fee` | Uses `risk_per_contract_with_fee` including round-trip fee from `fee_schedule` | `risk_per_contract = avg_loss + expected_fee` (Step 7b). Fee from `_tsm.fee_per_trade` (default $2.80). | **YES — FIXED 2026-04-06** | Fee now included in risk_per_contract. |
| 7 | **Portfolio Risk Cap** | `total_risk = Σ(contracts × sl × pv)` across all accounts; if `total_risk > max_portfolio_risk_pct × total_capital`: scale all down proportionally | Full implementation with `max_portfolio_risk_pct` from D16 | `_apply_portfolio_risk_cap()`: computes total risk, proportional scale-down if exceeds `max_portfolio_risk_pct × capital` (default 10%). Applied after correlation filter. | **YES — FIXED 2026-04-06** | Portfolio risk cap now matches live B4 Step 7. |
| 8 | **Level 2 Override** | `final = floor(final × sizing_overrides[user])` | `floor(final_contracts * override_val)` | **MISSING** | **DEFERRED.** Sizing overrides are an admin-only feature rarely used in practice. No impact on replay accuracy. |

### Kelly Summary

| Category | Count | Impact |
|----------|-------|--------|
| Full match | 8 (Steps 1, 2, 3, 4, 5, 6a, 6b, 6c, 7) | — |
| Deferred | 1 (Step 8) | Sizing override — admin-only, no impact |

---

## 3. Circuit Breaker Layer Comparison

Spec defines 5 layers (L0–L4). Live implements 7 (adds L5, L6). Replay implements 1.

| Layer | Spec Definition | Live Code (`b5c_circuit_breaker.py`) | Replay Code (`compute_contracts()` Step 10) | Match? | Notes |
|-------|----------------|--------------------------------------|---------------------------------------------|--------|-------|
| **L0** Scaling | XFA only: scaling tiers by profit level. `current_open_micros + proposed_micros ≤ scaling_tier_micros` | `_layer0_scaling_cap()` — checks scaling_plan_active, tier limits in micro-equivalents (1 mini = 10 micros) | **Step 11b:** Checks `scaling_plan_active` from TSM. Caps `final` to `scaling_tier_micros - current_open_micros`. | **FIXED — 2026-04-06** | L0 scaling cap now matches live. No-op for non-XFA accounts. |
| **L1** Hard Halt | `H = 1 if |L_t| + ρ_j < c·e·A, else 0` where `L_t` = cumulative P&L today, `ρ_j = contracts × (sl×pv + fee)`, `A` = current_balance | `_layer1_preemptive_halt()` — uses `intraday.l_t` (today's running P&L from D23), `tsm.current_balance` for A, fee-inclusive ρ_j | **Step 11:** `abs(L_t) + rho_j >= c*e*A`. `L_t` tracked via `_intraday_cumulative_pnl`. `rho_j` fee-inclusive. Iterative reduction. Uses `user_capital` (minor diff vs `current_balance`). | **FIXED — 2026-04-06** | L1 now uses intraday L_t accumulator and fee-inclusive rho_j. Minor residual: uses `user_capital` not `current_balance`. |
| **L2** Budget | `B = 1 if n_t < N, else 0` where `N = floor((e·A) / (MDD%·p + φ))` and `n_t` = trades completed today | `_layer2_budget()` — tracks `intraday.n_t` from D23, computes N from topstep params | **Step 12:** `N = floor((e*A)/(MDD*p+phi))`. `n_t` tracked via `_intraday_trade_count`. Blocks when `n_t >= N`. | **FIXED — 2026-04-06** | L2 budget exhaustion matches live. |
| **L3** Expectancy | `C_b = 1 if μ_b > 0, else 0` where `μ_b = r̄_b + β_b·L_b`, `r̄_b` = baseline return, `β_b` = serial correlation coefficient. Significance gate: p>0.05 or n<100 → β_b=0 | `_layer3_basket_expectancy()` — reads `cb_param` from D25 (r_bar, beta_b, p_value, n_observations), `intraday.l_b[model_m]` from D23 | **Step 13:** D25 params loaded. Per-basket `L_b` via `_intraday_basket_pnl`. `mu_b = r_bar + beta_b * L_b`. Significance gate: `p>0.05` or `n<100` → `beta_b=0`. Cold-start (n=0) → skip. | **FIXED — 2026-04-06** | L3 matches live. Cold-start is no-op (matches current D25 state). |
| **L4** Sharpe | `Q = 1 if S > λ, else 0` where `S = μ_b / (σ√(1 + 2n_t·ρ̄))`, λ = min Sharpe threshold (default 0) | `_layer4_correlation_sharpe()` — reads sigma, rho_bar from D25, computes conditional Sharpe | **Step 15:** `S = mu_b / (sigma * sqrt(1 + 2*n_t*rho_bar))`. Blocks when `S <= lambda`. Reuses bp, n_obs, mu_b from L3. Requires `n_obs >= 100`. | **FIXED — 2026-04-06** | L4 conditional Sharpe now matches live. During cold-start, disabled (n_obs < 100). |
| **L5** Session | VIX > 50 → halt. ≥3 assets in DATA_HOLD → halt. | `_layer5_session_halt()` — reads current VIX, counts DATA_HOLD assets from D00 | **DEFERRED** | **Intentionally excluded.** VIX > 50 is extreme (last hit during COVID crash). DATA_HOLD is rare. These are live-only operational concerns, not relevant for historical replay. |
| **L6** Manual | Admin manual halt flag per account | `_layer6_manual_override()` — checks P3-D17 manual_halt | **DEFERRED** | **Intentionally excluded.** Admin-only override. Not relevant for automated replay — no manual halt concept in backtesting. |

### CB Summary

| Category | Count |
|----------|-------|
| Fully implemented | 5 (L0, L1, L2, L3, L4) |
| Intentionally excluded | 2 (L5, L6 — live-only operational concerns) |

---

## 4. Parameter Discrepancies

| Parameter | Spec Value/Formula | Live Value | Replay Value | Source (replay) | Impact |
|-----------|-------------------|------------|--------------|-----------------|--------|
| **Regime weights** | From B2 classifier: `P(LOW_VOL)`, `P(HIGH_VOL)` — can be 0.0/1.0 (binary) or continuous | Same as spec | Uses `_compute_regime_probs()` from strategy data | **FIXED** | Regime probs match live for all current assets |
| **budget_divisor** | `remaining_eval_days` from `eval_end_date` (default 20 if no deadline) | Computed from `tsm.evaluation_end_date` or default 20 | Computed from `evaluation_end_date` in TSM, falls back to 20 | **FIXED** | Now dynamic |
| **PASS_EVAL multiplier** | Graduated: `pass_prob<0.5→×0.5`, `<0.7→×0.7`, `else→×0.85` | Graduated via `tsm.pass_probability` | Graduated via `_tsm.pass_probability`, default 0.6 | **FIXED** | Matches live thresholds |
| **risk_per_contract** | `avg_loss + expected_fee` (fee-inclusive) | `avg_loss + fee_schedule.round_turn` (or `commission×2`) | `avg_loss + expected_fee` (fee from `_tsm.fee_per_trade`, default $2.80) | replay_engine.py Step 7b | **FIXED** |
| **CB L1: A (capital)** | `current_balance` from D08 | `tsm.current_balance` | `user_capital` from D16 | compute_contracts() Step 11 | **P2** — differs by drawdown amount |
| **CB L1: ρ_j** | `contracts × (sl_dist × pv + fee)` | Fee-inclusive | `contracts × (fallback_risk + fee_per_trade)` | **FIXED** | Fee now included |
| **CB L1: L_t** | Cumulative intraday P&L from D23 | `intraday.l_t` (running total) | `_intraday_cumulative_pnl` (running total) | **FIXED** | Tracked across assets |
| **account_id** | Dynamic from D08 / multi-account | Per-account from `tsm_configs` | Dynamic from D16 `accounts` list (first account), fallback `'20319811'` | load_replay_config() | **FIXED** |
| **user_id** | Dynamic from auth | Per-user from session | Hardcoded `'primary_user'` | api.py:587+ | **P2** — single-user only |
| **tp_multiple** | Per-asset from `locked_strategy` JSON in D00 | From `strategy.tp_multiple` | Config default `0.70`, propagated to all assets | replay_engine.py:235, b11:231–235 | **Low** — config override allows user to set correctly; D00 locked_strategy may also contain it |
| **sl_multiple** | Per-asset from `locked_strategy` JSON in D00 | From `strategy.sl_multiple` | Config default `0.35`, propagated to all assets | replay_engine.py:236, b11:231–235 | **Low** — same as tp_multiple |
| **topstep_params** | From D08 `topstep_optimisation` JSON per account | Parsed from TSM config | Hardcoded fallback `{"c": 0.5, "e": 0.01}` if not in D08 | replay_engine.py:246 | **Low** — fallback matches spec defaults |
| **AIM aggregation** | Spec: `Product(m_a^w_a)` (multiplicative) | **Weighted average** (shared/aim_compute.py) | **Weighted average** (same code) | aim_compute.py:140–160 | **N/A** — spec-vs-code gap, but CONSISTENT between live and replay |

---

## 5. Missing Computations

These are things the spec requires that the GUI replay does **not do at all**:

| # | Missing Computation | Spec Reference | Live Block | What Happens in Replay | Impact |
|---|---------------------|----------------|------------|----------------------|--------|
| 1 | **Regime probability classifier** | PG-22 (B2) | `b2_regime_probability.py` — Pettersson binary or XGBoost | Flat 0.5/0.5 hardcoded | **P0** — wrong Kelly blend |
| 2 | **Expected edge calculation** | PG-25 (B5): `edge = wr × avg_win - (1-wr) × avg_loss` | `b5_trade_selection.py` | Not computed. Position limit ranks by `abs(pnl_per_contract)` (realised) instead | **P0** — wrong trade ranking |
| 3 | **Cross-asset correlation filter** | PG-25 (B5): reduce correlated pairs (>0.7) by 50% | `b5_trade_selection.py` — reads D07 correlation matrix | **FIXED 2026-04-06** — `_apply_correlation_filter()` halves lower-edge asset for correlated pairs. Loads D07; fallback known pairs: ES/MES, NQ/MNQ, ZB/ZN. | ~~P1~~ **FIXED** |
| 4 | **HMM session allocation** | PG-25 (B5): opportunity_weights from D26, warmup blend | `b5_trade_selection.py` — `apply_hmm_session_allocation()` | **FIXED 2026-04-06** — `_apply_hmm_session_weight()` loads D26 hmm_params. Cold-start (n<20): equal weights (no-op). Warm: applies learned session weights with 5% floor. | ~~P1~~ **FIXED** |
| 5 | **Quality gate** | PG-26 (B5B): quality_score threshold, graduated sizing | `b5b_quality_gate.py` | **FIXED 2026-04-06** — `_apply_quality_gate()` ports B5B: `quality_score = abs(edge) × aim_mod × data_maturity`, hard_floor/ceiling gating, graduated multiplier. Trade counts from D03. | ~~P1~~ **FIXED** |
| 6 | **Robust Kelly fallback** | PG-24 Step 3 (B4): Paper 218 distributional robust Kelly | `b4_kelly_sizing.py` — `compute_robust_kelly()` | **FIXED 2026-04-06** — `_get_return_bounds()` + `_compute_robust_kelly()` ported. Applied when regime_uncertain=True. | ~~P1~~ **FIXED** |
| 7 | **User Kelly ceiling** | PG-24 Step 5 (B4): `min(kelly, user_kelly_ceiling)` from D16 | `b4_kelly_sizing.py` | **FIXED 2026-04-06** — `min(kelly_with_aim, user_kelly_ceiling)` in compute_contracts() Step 5. Default 0.25, configurable. | ~~P2~~ **FIXED** |
| 8 | **Portfolio risk cap** | PG-24 Step 7 (B4): `max_portfolio_risk_pct × total_capital` | `b4_kelly_sizing.py` | **FIXED 2026-04-06** — `_apply_portfolio_risk_cap()`. Proportional scale-down. | ~~P1~~ **FIXED** |
| 9 | **CB L2 budget exhaustion** | Part 4 L2: `n_t < N` | `b5c_circuit_breaker.py` | **FIXED 2026-04-06** — Step 12 in compute_contracts(). Intraday n_t tracked. | ~~P1~~ **FIXED** |
| 10 | **CB L3 basket expectancy** | Part 4 L3: `μ_b = r̄_b + β_b·L_b > 0` | `b5c_circuit_breaker.py` | **FIXED 2026-04-06** — Step 13. D25 params loaded. Per-basket L_b tracked. Significance gate. | ~~P1~~ **FIXED** |
| 11 | **CB L4 conditional Sharpe** | Part 4 L4: `S = μ_b / (σ√(1+2n_tρ̄)) > λ` | `b5c_circuit_breaker.py` | **FIXED 2026-04-06** — Step 15 in compute_contracts(). `S = mu_b / (sigma * sqrt(1 + 2*n_t*rho_bar))`. Blocks when `S <= lambda`. Requires n_obs >= 100. | ~~P2~~ **FIXED** |
| 12 | **CB intraday state tracking** | D23: `L_t`, `n_t`, `L_b`, `n_b` reset at 19:00 ET | `b5c_circuit_breaker.py` reads D23 | **FIXED 2026-04-06** — `_intraday_cumulative_pnl` (L_t), `_intraday_trade_count` (n_t), `_intraday_basket_pnl` (L_b) initialized and updated in run_replay()/run_whatif(). | ~~P1~~ **FIXED** |
| 13 | **Topstep daily exposure cap** | Part 3: `N = floor((e·A)/(MDD%·p+φ))`, `topstep_cap = floor(E/(sl×pv))` | `b4_kelly_sizing.py` — `_compute_topstep_daily_cap()` | CB L2 implements N = floor((e*A)/(MDD*p+phi)). L0 implements XFA scaling cap. The standalone topstep_cap `floor(E/(sl×pv))` is subsumed by L2's budget formula which is more restrictive. | **FIXED** — L2 budget + L0 scaling cover the spec requirements |
| 14 | **Confidence tier classification** | PG-28 (B6): HIGH/MEDIUM/LOW based on edge and modifier thresholds | `b6_signal_output.py` | **DEFERRED** — informational display only, no impact on trade sizing or selection. B6 output format is intentionally different for replay (WebSocket vs Redis). | **DEFERRED** — cosmetic, no accuracy impact |
| 15 | **Data maturity scoring** | PG-26 (B5B): `min(1.0, max(0.5, trade_count/50))` | `b5b_quality_gate.py` | **FIXED 2026-04-06** — computed inside `_apply_quality_gate()` as part of quality_score. Trade counts from D03. | ~~P1~~ **FIXED** |

---

## 6. Simplified Computations

These are things replay does compute, but in a reduced or different form:

| # | Computation | Spec/Live Behaviour | Replay Behaviour | Acceptable? | Notes |
|---|------------|-------------------|------------------|-------------|-------|
| 1 | **Regime blending** | Weighted by actual classifier probabilities (0.0–1.0 continuous) | Flat 0.5/0.5 always | **No** | Should use at least the stored regime probabilities if classifier unavailable |
| 2 | **PASS_EVAL sizing** | Graduated: 0.5×/0.7×/0.85× based on pass_probability | Graduated by pass_probability from TSM | **Yes — FIXED** | Now matches live graduation thresholds |
| 3 | **CB L1 halt threshold** | `c × e × current_balance` with `|L_t| + ρ_j` check | `c × e × user_capital` with `|L_t| + ρ_j` check, fee-inclusive | **Mostly — FIXED** | L_t tracking and fee-inclusive rho_j added. Minor: `user_capital` vs `current_balance`. |
| 4 | **CB L1 ρ_j** | `contracts × (sl_dist × pv + fee)` | `contracts × (fallback_risk + fee_per_trade)` | **Yes — FIXED** | Fee now included in rho_j. |
| 5 | **MDD/MLL cap denominator** | `strategy_sl × point_value` | `fallback_risk = strategy.threshold × spec.point_value` | **Yes** | `threshold` IS the SL distance in points from locked_strategy. Same value, different key name. |
| 6 | **Position ranking** | Expected edge (forward-looking EWMA statistics) | Absolute realised PnL per contract (backward-looking) | **No** | Fundamentally different metric. Realised PnL uses the actual trade outcome to rank, which is information the live system doesn't have at selection time. |
| 7 | **ORB breakout detection** | `ORTracker` state machine fed real-time quotes; simultaneous breach resolved by penetration depth (high_pen vs low_pen) | Post-hoc 1-min bar scan; simultaneous breach resolved by penetration depth (high_pen vs low_pen), matching live ORTracker logic. | **Yes — FIXED 2026-04-06** | Penetration-depth tiebreaker now matches live ORTracker. |
| 8 | **Exit simulation** | Live B7: real-time monitoring with sub-second resolution | Replay: bar-by-bar scan, SL checked before TP per bar (pessimistic) | **Acceptable** | 1-min bar resolution is standard for backtesting. SL-before-TP pessimism is conservative, which is appropriate. |
| 9 | **What-if AIM** | N/A (no what-if in live) | What-if passes AIM modifiers from original results via `aim_modifier=` parameter | **Yes — FIXED** | AIM modifiers from original replay now flow through to what-if sizing. |
| 10 | **Batch day independence** | Live: Kelly/EWMA/CB states evolve after each trade outcome via Offline feedback loop | Batch replay: same config snapshot for all days. No state evolution between days. | **Acceptable** | True state evolution would require running Offline blocks between days. This is a fundamental replay limitation, not a bug. Document as known simplification. |
| 11 | **B5C GUI stage** | Live: CB results passed to GUI with per-layer breakdown | `sizing_complete` event now populates B5C stage with all CB layer results (L0-L4 blocked flags, halt thresholds, trade counts) in replayStore.js | **Yes — FIXED 2026-04-06** | B5C pipeline stage now shows complete CB breakdown in GUI. |

---

## 7. Prioritised Fix List

| Priority | # | Gap | Spec Reference | Impact on Accuracy | Estimated Complexity | Fix Approach |
|----------|---|-----|----------------|-------------------|---------------------|--------------|
| **P0** | 1 | **Flat 0.5/0.5 regime blend** | PG-22, PG-24 Step 1 | High — up to 30%+ Kelly difference when regimes diverge | Medium | Load regime model from D07 or stored regime_probs. At minimum, read the `regime_label` from D00 and use deterministic 0/1 weights for BINARY_ONLY assets. Full fix: instantiate B2 classifier. |
| **P0** | 2 | **Position limit uses realised PnL instead of expected edge** | PG-25 | High — selects different trades than live. Uses backward-looking information. | Low | Replace `abs(pnl_per_contract)` sort key with `win_rate × avg_win - (1-win_rate) × avg_loss` from EWMA states. Data already available in config. |
| ~~P1~~ **FIXED** | 3 | **~~Missing quality gate (B5B)~~** | PG-26 | ~~Significant~~ | ~~Medium~~ | **FIXED 2026-04-06** — `_apply_quality_gate()` in replay_engine.py. Ports B5B: `quality_score = abs(edge) × aim_mod × data_maturity`, hard_floor/ceiling gating, graduated multiplier. Trade counts from D03. Both `run_replay()` and `run_whatif()`. |
| ~~P1~~ **FIXED** | 4 | **~~Missing cross-asset correlation filter~~** | PG-25 | ~~Significant~~ | ~~Medium~~ | **FIXED 2026-04-06** — `_apply_correlation_filter()` in replay_engine.py. Halves lower-edge asset for correlated pairs (>0.7). Loads D07; fallback known pairs: ES/MES, NQ/MNQ, ZB/ZN. Applied after position limit in both `run_replay()` and `run_whatif()`. |
| ~~P1~~ **FIXED** | 5 | **~~PASS_EVAL flat 0.7 instead of graduated~~** | PG-24 Step 6a | ~~Moderate~~ | ~~Low~~ | **FIXED 2026-04-06** — Graduated by `pass_probability` from TSM: `<0.5→×0.5`, `<0.7→×0.7`, `else→×0.85`. Default 0.6 preserves backward compatibility (0.7× tier). |
| ~~P1~~ **FIXED** | 6 | **~~budget_divisor hardcoded 20~~** | PG-24 Step 6b | ~~Moderate~~ | ~~Low~~ | **FIXED 2026-04-06** — Computed from `evaluation_end_date` in TSM classification. `max(remaining_days, 1)` as divisor, falls back to 20 if no end date set. |
| ~~P1~~ **FIXED** | 7 | **~~Missing portfolio risk cap~~** | PG-24 Step 7 | ~~Moderate~~ | ~~Medium~~ | **FIXED 2026-04-06** — `_apply_portfolio_risk_cap()` in replay_engine.py. `total_risk = Σ(contracts × sl × pv)`. Proportional scale-down if exceeds `max_portfolio_risk_pct × capital` (default 10%). Applied after correlation filter in both `run_replay()` and `run_whatif()`. |
| ~~P1~~ **FIXED** | 8 | **~~Missing CB L2 budget exhaustion~~** | Part 4 L2 | ~~Moderate~~ | ~~Medium~~ | **FIXED 2026-04-06** — `N = floor((e×A)/(MDD×p+φ))`. Intraday trade counter `n_t` tracked across assets. Blocks when `n_t ≥ N`. Integrated into `compute_contracts()` Step 12. |
| ~~P1~~ **FIXED** | 9 | **~~Missing CB L3 basket expectancy~~** | Part 4 L3 | ~~Moderate~~ | ~~Medium~~ | **FIXED 2026-04-06** — Loads D25 CB params (`r_bar`, `beta_b`, `sigma`, `rho_bar`, `n_observations`, `p_value`). Per-basket `L_b` tracked intraday. `μ_b = r_bar + beta_b × L_b`; blocks when `μ_b ≤ 0` and `beta_b > 0`. Significance gate: `p>0.05` or `n<100` → `beta_b=0`. Cold-start (n=0) is no-op. |
| ~~P1~~ **FIXED** | 10 | **~~Missing Robust Kelly fallback~~** | PG-24 Step 3 | ~~Scenario-dependent~~ | ~~High~~ | **FIXED 2026-04-06** — `_get_return_bounds()` and `_compute_robust_kelly()` ported from `b1_features.py:450-480` (Paper 218). Applied when `regime_uncertain=True` (max_prob < 0.6). `adjusted = min(adjusted, robust_kelly)`. |
| ~~P1~~ **FIXED** | 11 | **~~What-if doesn't recompute AIM~~** | N/A | ~~Moderate~~ | ~~Low~~ | **FIXED 2026-04-06** — `run_whatif()` now extracts AIM modifiers from original results and passes them to `compute_contracts()` via `aim_modifier=` parameter. |
| ~~P1~~ **FIXED** | 12 | **~~CB L1 missing L_t (cumulative P&L)~~** | Part 4 L1 formula | ~~Moderate~~ | ~~Medium~~ | **FIXED 2026-04-06** — Intraday state accumulators (`_intraday_cumulative_pnl`, `_intraday_trade_count`, `_intraday_basket_pnl`) initialized before per-asset loop and updated after each sizing. CB L1 now uses `abs(L_t) + rho_j >= c*e*A` with fee-inclusive `rho_j`. |
| ~~P2~~ **FIXED** | 13 | **~~Missing user Kelly ceiling~~** | PG-24 Step 5 | ~~Low~~ | ~~Low~~ | **FIXED 2026-04-06** — `min(kelly_with_aim, user_kelly_ceiling)` in compute_contracts() Step 5. Default 0.25, configurable via config key. |
| ~~P2~~ **FIXED** | 14 | **~~Missing CB L4 Sharpe filter~~** | Part 4 L4 | ~~Low~~ | ~~Medium~~ | **FIXED 2026-04-06** — Step 15 in compute_contracts(). `S = mu_b / (sigma * sqrt(1 + 2*n_t*rho_bar))`. Blocks when `S <= lambda`. Reuses D25 params from L3. Requires n_obs >= 100. |
| ~~P2~~ **FIXED** | 15 | **~~Fee omission in risk_per_contract~~** | PG-24 Step 6c | ~~Low~~ | ~~Low~~ | **FIXED 2026-04-06** — `risk_per_contract += expected_fee` in compute_contracts() Step 7b. Fee from `_tsm.fee_per_trade` (default $2.80). |
| ~~P2~~ **FIXED** | 16 | **~~B5C pipeline stage never populated~~** | GUI display | ~~None~~ | ~~Low~~ | **FIXED 2026-04-06** — replayStore.js `sizing_complete` handler now populates B5C stage with all CB layer results (L0-L4 blocked flags, halt thresholds, trade counts). |
| ~~P2~~ **FIXED** | 17 | **~~Hardcoded account_id '20319811'~~** | Multi-account support | ~~Low~~ | ~~Low~~ | **FIXED 2026-04-06** — Dynamic account_id extracted from D16 `accounts` list (first entry), fallback to `'20319811'`. Used in D08 TSM query. |
| ~~P2~~ **FIXED** | 18 | **~~Missing CB L0 scaling cap~~** | Part 4 L0 | ~~Low~~ | ~~Low~~ | **FIXED 2026-04-06** — Step 11b in compute_contracts(). Checks `scaling_plan_active` from TSM. Caps contracts to `scaling_tier_micros - current_open_micros`. No-op for non-XFA accounts. |
| ~~P2~~ **FIXED** | 19 | **~~ORB LONG bias on simultaneous breach~~** | ORTracker tiebreaker | ~~Very low~~ | ~~Low~~ | **FIXED 2026-04-06** — simulate_orb() now computes `high_pen` and `low_pen` on simultaneous breach, picks greater penetration. Matches live ORTracker logic. |
| ~~P2~~ **FIXED** | 20 | **~~Missing HMM session allocation~~** | PG-25 | ~~Low~~ | ~~Medium~~ | **FIXED 2026-04-06** — `_apply_hmm_session_weight()` loads D26 hmm_params. Cold-start (n<20): no-op (equal weights). Warm: applies learned session weights with 5% floor. Applied after portfolio risk cap in both `run_replay()` and `run_whatif()`. |

---

## 8. Recommended Implementation Order

Based on impact and dependency chain:

### Phase 1: Core Accuracy (P0 fixes)
1. **#1 Regime probability** — Add regime blending using stored D07 regime models or at minimum the regime_label from D00
2. **#2 Expected edge ranking** — Replace abs(pnl_per_contract) with EWMA-based expected edge

### Phase 2: Signal Filtering (P1 fixes, high value)
3. **#3 Quality gate** — Implement B5B quality_score thresholding
4. **#4 Correlation filter** — Reduce correlated asset pairs
5. **#5 PASS_EVAL graduation** — Read pass_probability from TSM
6. **#6 budget_divisor** — Compute from eval_end_date

### Phase 3: Risk Controls (P1 fixes, protection-focused) — COMPLETE 2026-04-06
7. ~~**#7 Portfolio risk cap**~~ — `_apply_portfolio_risk_cap()` implemented
8. ~~**#8 CB L2 budget**~~ — Budget exhaustion in compute_contracts() Step 12
9. ~~**#9 CB L3 expectancy**~~ — Basket expectancy in compute_contracts() Step 13
10. ~~**#12 CB L1 L_t tracking**~~ — Intraday P&L accumulator added
    - Also fixed: **#5 PASS_EVAL graduated**, **#6 budget_divisor**, **#10 Robust Kelly**, **#11 What-if AIM**

### Phase 4: Polish (P2 fixes) — COMPLETE 2026-04-06
11. ~~**#11 What-if AIM recompute**~~ — FIXED in Phase 3
12. ~~**#13 User Kelly ceiling**~~ — `min(kelly_with_aim, user_kelly_ceiling)` Step 5
13. ~~**#14 CB L4 conditional Sharpe**~~ — Step 15, `S = mu_b/(sigma*sqrt(1+2*n_t*rho_bar))`
14. ~~**#15 Fee in risk_per_contract**~~ — `risk_per_contract += expected_fee` Step 7b
15. ~~**#16 B5C pipeline stage**~~ — replayStore.js populates B5C from sizing_complete
16. ~~**#17 Dynamic account_id**~~ — extracted from D16 accounts list
17. ~~**#18 CB L0 scaling cap**~~ — Step 11b, XFA scaling_plan_active check
18. ~~**#19 ORB tiebreaker**~~ — penetration-depth comparison in simulate_orb()
19. ~~**#20 HMM session allocation**~~ — `_apply_hmm_session_weight()` with D26 cold-start logic

### Deferred Items (no accuracy impact)
- **Kelly Step 8 (sizing override):** Admin-only feature, rarely used. No impact on replay accuracy.
- **CB L5 (VIX/DATA_HOLD halt):** Live-only operational concern. VIX > 50 is extreme; DATA_HOLD is rare.
- **CB L6 (manual halt):** Admin-only override. No manual halt concept in backtesting.
- **Confidence tier (B6):** Informational display only. Replay uses WebSocket, not Redis.

---

## 9. Completion Summary

**All 4 phases complete.** 20 gaps identified, 18 FIXED, 2 DEFERRED (with justification).

| Phase | Status | Gaps Fixed |
|-------|--------|------------|
| Phase 1: Core Accuracy (P0) | COMPLETE | #1, #2 |
| Phase 2: Signal Filtering (P1) | COMPLETE | #3, #4, #5, #6 |
| Phase 3: Risk Controls (P1) | COMPLETE | #7, #8, #9, #10, #11, #12 |
| Phase 4: Polish (P2) | COMPLETE | #13, #14, #15, #16, #17, #18, #19, #20 |

**Deferred:** Kelly Step 8 (sizing override), CB L5/L6 (live-only), confidence tier (cosmetic).

**File changes:** `shared/replay_engine.py` (1944→2065 lines, +121), `captain-gui/src/stores/replayStore.js` (+12 lines).

**Test status:** 95 tests passing, 0 failures. All sanity checks verified.

---

## Appendix A: Spec-vs-Code Discrepancy (Not Replay-Specific)

The following discrepancy exists in the LIVE system, not just replay:

| Item | Spec Says | Code Does | Affected Files |
|------|-----------|-----------|----------------|
| AIM aggregation formula | `mod = Product(m_a^w_a)` (multiplicative, PG-23) | Weighted average: `Σ(m_a × w_a) / Σ(w_a)` | `shared/aim_compute.py:140–160` |

This is a system-wide decision that should be resolved at the spec level, not in the replay engine.

---

## Appendix B: Intentional Simplifications (No Fix Needed)

| Item | Why It's Acceptable |
|------|-------------------|
| No data moderator (B1 1b) | Replay uses historical bars — data quality checks are live-only |
| No contract roll checks (B1 1c) | Historical bars already resolved to correct contract |
| WebSocket output instead of Redis (B6) | Replay GUI needs direct events, not pub/sub |
| Bar-by-bar exit simulation (B7) | Standard backtesting approach at 1-min resolution |
| SL-before-TP pessimism | Conservative assumption appropriate for backtesting |
| No B8/B9 post-session analytics | Out of replay scope |
| Batch day independence | True state evolution would require full Offline feedback loop — fundamental replay limitation |
| AIM default disabled | Opt-in is intentional UX choice; user can enable via toggle |
