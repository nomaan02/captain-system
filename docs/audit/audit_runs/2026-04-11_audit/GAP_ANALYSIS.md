# Gap Analysis — Captain System vs Obsidian Spec

**Audit Date:** 2026-04-11
**Source of Truth:** Obsidian vault (`~/obsidian-spec/`)
**Baseline:** Current code on `ux-audit-overhaul` branch + uncommitted changes
**Prior Audit Reference:** `docs/audit/FINAL_VALIDATION_REPORT.md` (2026-04-09, stale)

---

## Status Legend

| Status | Meaning |
|--------|---------|
| `[GAP]` | Code diverges from spec — needs implementation or correction |
| `[VALID]` | Code matches spec — verified compliant |
| `[AMENDED]` | Code differs from spec but change was an intentional architectural decision (DEC-XX) |
| `[BLOCKED]` | Cannot determine — requires Isaac's spec clarification |

## Severity Legend

| Severity | Criteria |
|----------|----------|
| CRITICAL | System will produce wrong trades, lose money, or crash in production |
| HIGH | Feature missing or broken, blocks live trading readiness |
| MEDIUM | Partial implementation, degraded functionality, or spec divergence with workaround |
| LOW | Polish, optimization, or non-essential spec requirement |

---

## P3-Offline — Captain Offline (Strategic Brain)

**Audited:** 2026-04-11 Session 3
**Scope:** 20 files (17 blocks + orchestrator + bootstrap + version_snapshot + main)
**Spec Documents:** Docs 21, 22, 28, 31, 32

### Summary

| Status | Count |
|--------|-------|
| `[GAP]` | 52 |
| `[VALID]` | ~75 verification points confirmed |
| `[AMENDED]` | 3 |
| `[BLOCKED]` | 0 |
| **Total** | 55 findings (52 GAP + 3 AMENDED) |

| Severity | Count |
|----------|-------|
| CRITICAL | 5 |
| HIGH | 20 |
| MEDIUM | 22 |
| LOW | 5 |

### Findings Table

| ID | Block | File | Spec Ref | Status | Severity | Description |
|----|-------|------|----------|--------|----------|-------------|
| G-OFF-001 | B1-HMM | b1_aim16_hmm.py:104-115 | Doc 22 §2 TVTP | `[GAP]` | CRITICAL | AIM-16 uses hmmlearn GaussianHMM with static transition matrix; spec requires TVTP conditioned on {VIX, DoW, prior_PnL} |
| G-OFF-002 | B1-HMM | b1_aim16_hmm.py:40 | Doc 22 §6 | `[GAP]` | HIGH | 240 minimum observation count not enforced; SESSIONS_PER_DAY=4 defined but never used |
| G-OFF-003 | B1-HMM | b1_aim16_hmm.py:43 | Doc 22 §7 | `[GAP]` | HIGH | SMOOTHING_ALPHA=0.3 defined but never used or included in output state for online inference |
| G-OFF-004 | B1-Drift | b1_drift_detection.py:269-319 | Doc 32 PG-04:207-208 | `[GAP]` | HIGH | On drift: weight*=0.5 applied but no retrain flag set in P3-D01 as spec requires |
| G-OFF-005 | B1-DMA | b1_dma_update.py:40-62 | Doc 32 PG-02:100 | `[GAP]` | MEDIUM | DMA iterates ALL AIMs from D02, not filtered to ACTIVE status from D01 |
| G-OFF-006 | B1-Lifecycle | b1_aim_lifecycle.py:286-305 | Doc 32 PG-01:64-68 | `[GAP]` | MEDIUM | Suppression and recovery events not logged to P3-D06 as spec requires |
| G-OFF-007 | B1-Lifecycle | b1_aim_lifecycle.py:375-392 | Doc 32 PG-01:64-67 | `[GAP]` | MEDIUM | Consecutive weight tracking hardcodes recovery count=10 instead of actual tracking |
| G-OFF-008 | B1-Lifecycle | b1_aim_lifecycle.py:244-262 | Doc 32 PG-01:55-57 | `[GAP]` | LOW | No NOTIFY on WARM_UP→ELIGIBLE transition as spec requires |
| G-OFF-009 | B2-BOCPD | b2_bocpd.py:142-156,177-184 | Doc 32 PG-05 | `[GAP]` | HIGH | run_length_posterior and NIG priors not persisted to P3-D04; full BOCPD state lost on restart |
| G-OFF-010 | B2-CUSUM | b2_cusum.py + orchestrator.py | Doc 32 PG-07 | `[GAP]` | HIGH | S2-19: Bootstrap calibration not run at init; only quarterly. Sequential limits empty until first quarterly boundary |
| G-OFF-011 | B2-BOCPD/CUSUM | orchestrator.py:51,154-166 | Doc 32 PG-05+PG-06 | `[GAP]` | HIGH | Detectors cached in memory only; from_dict deserializers exist but never called on startup |
| G-OFF-012 | B2-CUSUM | b2_cusum.py:38,44 | Doc 32 PG-06 | `[GAP]` | MEDIUM | Fresh CUSUM detector defaults to allowance=0.0 instead of loading calibrated value from D04 |
| G-OFF-013 | B2-Escalation | b2_level_escalation.py:13 | Doc 32 PG-05 | `[GAP]` | MEDIUM | L3 "5 consecutive days" checked per-trade (cp_history), not per calendar day |
| G-OFF-014 | B2-Escalation | b2_level_escalation.py:209 | Doc 32 PG-06:274 | `[GAP]` | MEDIUM | CUSUM breach severity hardcoded as 0.85 float; spec passes string label |
| G-OFF-015 | B3 | orchestrator.py (entire) | Doc 32 PG-09 | `[GAP]` | CRITICAL | B3 pseudotrader ZERO references in orchestrator; never triggered by any event |
| G-OFF-016 | B3 | b3_pseudotrader.py:441-512 | Doc 32 PG-09 §1-2 | `[GAP]` | CRITICAL | Spec requires captain_online_replay(); code accepts pre-computed P&L lists instead |
| G-OFF-017 | B3 | b3_pseudotrader.py (entire) | Doc 28 §7 | `[GAP]` | HIGH | No SHA256 deterministic tick stream generator for synthetic replay |
| G-OFF-018 | B3 | b3_pseudotrader.py (entire) | Doc 28 §8 | `[GAP]` | HIGH | No LEGACY vs IDEAL mode parameter; no mode-labelled results |
| G-OFF-019 | B3 | b3_pseudotrader.py:169-438 | Doc 28 §5 | `[GAP]` | HIGH | No per-account-type replay iteration; single account_config only |
| G-OFF-020 | B3 | b3_pseudotrader.py:169-438 | Doc 28 §4 | `[GAP]` | HIGH | No bankruptcy check (running_balance ≤ 0); Live accounts with mdd_limit=None unprotected |
| G-OFF-021 | B3 | b3_pseudotrader.py:619-755 | Doc 32 PG-09B | `[GAP]` | HIGH | G-025 UNRESOLVED: CB pseudotrader ignores DLL/MDD/scaling/hours account constraints |
| G-OFF-022 | B3 | b3_pseudotrader.py:475 | Doc 32 PG-09 §4 | `[GAP]` | MEDIUM | DSR n_trials hardcoded to 1; defeats multiple-testing correction purpose |
| G-OFF-023 | B3 | b3_pseudotrader.py:619-755 | Doc 32 PG-09B | `[GAP]` | MEDIUM | CB pseudotrader computes PBO but hardcodes dsr=0.0 |
| G-OFF-024 | B3 | b3_pseudotrader.py (entire) | Doc 32 PG-09 | `[GAP]` | MEDIUM | P3-D03 (trade_outcome_log) never queried; uses pre-computed data or JSON files |
| G-OFF-025 | B4 | b4_injection.py:142-149 | Doc 32 PG-10 §4 | `[GAP]` | HIGH | PARALLEL_TRACK missing upper bound (ratio ≤ 1.2); high-ratio high-PBO candidates enter parallel |
| G-OFF-026 | B4 | b4_injection.py:46-65 | Doc 32 PG-10 §1 | `[GAP]` | MEDIUM | Simplified retroactive AIM analysis; no per-AIM replay over candidate's historical window |
| G-OFF-027 | B4 | b4_injection.py:109-169 | Doc 32 PG-10 §5 | `[GAP]` | MEDIUM | No RPT-05 report generation or GUI notification on injection result |
| G-OFF-028 | B4 | b4_injection.py:109-169 | Doc 32 PG-11 | `[GAP]` | MEDIUM | REJECT does not reset P3-D00.captain_status to ACTIVE as spec requires |
| G-OFF-029 | B5 | b5_sensitivity.py:169-177 | Doc 32 PG-12 | `[GAP]` | CRITICAL | Perturbation deltas applied uniformly to ALL params; spec requires per-parameter grid (7 vs N×7) |
| G-OFF-030 | B5 | b5_sensitivity.py:59-62 | Doc 32 PG-12 | `[GAP]` | MEDIUM | PBO computed on base_returns instead of perturbation grid results |
| G-OFF-031 | B5 | b5_sensitivity.py:231-246 | Doc 32 PG-12 | `[GAP]` | MEDIUM | No GUI notification or RPT-03 section on FRAGILE detection |
| G-OFF-032 | B6 | b6_auto_expansion.py:234-263 | Doc 32 PG-13 §2 | `[GAP]` | HIGH | GA fitness evaluated on full window; no walk-forward train/validate split |
| G-OFF-033 | B6 | b6_auto_expansion.py:269-275 | Doc 32 PG-13 §4 | `[GAP]` | HIGH | PBO computed on raw holdout_returns identically for all candidates; should use per-candidate OOS |
| G-OFF-034 | B6 | b6_auto_expansion.py:211-214 | Doc 32 PG-13 §4 | `[GAP]` | MEDIUM | DSR uses hardcoded Gaussian (skew=0, kurt=3) instead of actual distributional parameters |
| G-OFF-035 | B6 | b6_auto_expansion.py:296-297 | Doc 32 PG-13 §5 | `[GAP]` | MEDIUM | No CRITICAL notification when no viable replacement candidates found |
| G-OFF-036 | B7 | b7_tsm_simulation.py:59-97 | Doc 32 PG-14:563-588 | `[GAP]` | MEDIUM | Two-level sim loop flattened; MLL checked per-return instead of per-day aggregate |
| G-OFF-037 | B7 | b7_tsm_simulation.py:59-97 | Doc 32 PG-14:566-567 | `[GAP]` | MEDIUM | sim_drawdown starts at 0 instead of initializing from tsm.current_drawdown |
| G-OFF-038 | B7 | b7_tsm_simulation.py:147-152 | Doc 32 PG-14:569-572 | `[GAP]` | MEDIUM | Block bootstrap produces flat path (1 return/day) instead of daily blocks of 3-7 returns |
| G-OFF-039 | B8-Kelly | b8_kelly_update.py:108-116 | Doc 32 PG-15:664-666; Doc 21 L3 | `[GAP]` | HIGH | Shrinkage uses 1/√N proxy instead of compute_estimation_variance(P3-D05[u]) |
| G-OFF-040 | B8-CB | b8_cb_params.py:134-207 | Doc 32 PG-16C:709-713 | `[GAP]` | HIGH | L_star breakeven (L* = -r̄/β_b) not computed or stored in P3-D25 |
| G-OFF-041 | B8-CB | b8_cb_params.py:134-207 | Doc 32 PG-16C:686-715 | `[GAP]` | HIGH | cold_start field missing from D25 writes; basket grouping replaced by (account,model) |
| G-OFF-042 | B8-CB | b8_cb_params.py:57-99 | Doc 32 PG-16C:697-702 | `[GAP]` | MEDIUM | r_bar computed as OLS intercept instead of mean(r_series) as spec defines |
| G-OFF-043 | B8-CB | b8_cb_params.py:36-37 | Doc 32 PG-16C:690-695 | `[GAP]` | MEDIUM | Single cold start threshold at n<100; spec has two tiers: n<10 (skip) and n<100 (cold_start flag) |
| G-OFF-044 | B9 | b9_diagnostic.py:826-853 | Doc 32 PG-17:739 | `[GAP]` | MEDIUM | D8 Resolution Verification lacks event-triggered path for ADMIN item resolution |
| G-OFF-045 | B9 | b9_diagnostic.py:854 | Doc 32 PG-17:747 | `[GAP]` | LOW | overall_health uses arithmetic mean; spec says "weighted_mean" |
| G-OFF-046 | Support | version_snapshot.py:51-79 | Doc 32 Version Snapshot | `[GAP]` | CRITICAL | rollback_to_version() completely unimplemented (no admin approval, regression tests, or revert) |
| G-OFF-047 | Support | version_snapshot.py:23 | Doc 32 Version Snapshot | `[GAP]` | HIGH | MAX_VERSIONS=50 defined but never enforced; no pruning or cold_storage migration |
| G-OFF-048 | Support | version_snapshot.py:51-79 | Doc 32 Version Snapshot | `[GAP]` | HIGH | snapshot_before_update requires caller to pass state dict; no internal get_current_state() |
| G-OFF-049 | Support | bootstrap.py:80-211 | Doc 32 PG-02 | `[GAP]` | HIGH | D02 (aim_meta_weights) not initialized by bootstrap; first DMA update will fail to find rows |
| G-OFF-050 | Support | orchestrator.py:128-192 | Doc 32 | `[GAP]` | MEDIUM | Single try/except wraps all 7 trade outcome steps; one failure skips all subsequent steps |
| G-OFF-051 | Support | orchestrator.py + main.py | CLAUDE.md Redis channels | `[GAP]` | LOW | No heartbeat published to captain:status channel; GUI will show Offline as Unknown |
| G-OFF-052 | Support | main.py:128-132 | Doc 32 | `[GAP]` | LOW | Crash recovery journal read on startup but never acted upon |

**Amended Items (intentional deviations):**

| ID | Block | File | Spec Ref | Description | Rationale |
|----|-------|------|----------|-------------|-----------|
| G-OFF-A01 | B1 | b1_aim_lifecycle.py:264-277 | Doc 32 PG-01:59-62 | ELIGIBLE→ACTIVE adds learning gate beyond spec's user_activated-only | DEC-05: dual gate prevents premature activation |
| G-OFF-A02 | B8 | b8_kelly_update.py:173-176 | Doc 32 PG-15:674-675 | snapshot_before_update called BEFORE save (spec says after) | Code ordering is semantically correct (snapshot pre-overwrite) |
| G-OFF-A03 | B7 | b7_tsm_simulation.py:167-169 | Doc 32 PG-14 | PRESERVE_CAPITAL risk goal alert added beyond spec | Extension for conservative accounts |

### Detailed Findings — CRITICAL

---

#### G-OFF-001 — AIM-16 HMM: No Time-Varying Transition Probabilities (TVTP)

**Block:** B1-HMM | **File:** `b1_aim16_hmm.py:104-115` | **Spec:** Doc 22 §2, Doc 32 PG-01C

**Spec requires:** Transition matrix A(x_t) depends on covariates x_t = {VIX_level, day_of_week, prior_session_PnL}. States shift more readily during high-VIX regimes.

**Code implements:** `hmmlearn.hmm.GaussianHMM` with a uniform initial transition matrix (`np.full((3,3), 1/3)`). Baum-Welch learns static transitions. The library does not support covariate-dependent transitions.

**Impact:** HMM opportunity regime detection ignores the market context that should modulate state transitions. Session budget weights (HIGH_OPP gets more allocation) will be less responsive to current market conditions.

**Recommendation:** Implement a custom TVTP layer (e.g., logistic transition model conditioned on covariates), or use a library supporting covariate-dependent HMMs (pomegranate, pyro). Alternatively, post-hoc adjust transition probs using covariate-indexed lookup tables as a pragmatic V1 workaround.

---

#### G-OFF-015 — Pseudotrader Completely Unwired from Orchestrator

**Block:** B3 | **File:** `orchestrator.py` (entire) | **Spec:** Doc 32 PG-09

**Spec requires:** PG-09 triggers on proposed_update events — AIM weight changes, model retrains, strategy injections. It gates parameter commits with a before/after replay comparison.

**Code implements:** The orchestrator has ZERO imports from `b3_pseudotrader.py`. No event (trade outcome, weekly schedule, monthly schedule, injection) dispatches to B3. The only caller is B4 `injection_comparison`, which imports `run_pseudotrader` directly.

**Impact:** Parameter updates (DMA weights, Kelly fractions, EWMA stats) are committed without any pseudotrader validation. There is no safety gate preventing harmful parameter changes from going live.

**Recommendation:** Wire B3 into the orchestrator. At minimum, `run_pseudotrader` should be called before committing D02/D05/D12 updates, with the result gating the commit. For DMA updates (frequent), a fast-path check may be needed to avoid latency.

---

#### G-OFF-016 — No Actual Pipeline Replay in Pseudotrader

**Block:** B3 | **File:** `b3_pseudotrader.py:441-512` | **Spec:** Doc 32 PG-09 Phases 1-2

**Spec requires:** `captain_online_replay(d, using=CURRENT_parameters)` and `captain_online_replay(d, using=PROPOSED_parameters)` — full re-execution of the Online signal pipeline per historical day.

**Code implements:** `run_pseudotrader()` accepts pre-computed `baseline_pnl` and `proposed_pnl` lists. It compares them statistically but never executes the Online pipeline. A separate `run_signal_replay_comparison()` uses `SignalReplayEngine` but is never called from the orchestrator.

**Impact:** Pseudotrader cannot detect parameter interaction effects (e.g., a DMA weight change that alters AIM aggregation, which changes Kelly sizing, which changes signal output). Only direct P&L impact of pre-computed scenarios is tested.

**Recommendation:** Integrate `SignalReplayEngine`-based replay as the primary path. Pre-computed P&L can remain as a fast fallback with appropriate labelling.

---

#### G-OFF-029 — Sensitivity Scanner: Uniform Perturbation Instead of Per-Parameter

**Block:** B5 | **File:** `b5_sensitivity.py:169-177` | **Spec:** Doc 32 PG-12

**Spec requires:** `FOR EACH param p IN base_params: FOR delta IN [...]: perturbed[p] = base_params[p] * (1 + delta)` — each parameter perturbed individually while others stay at base. This produces N_params × 7 grid points.

**Code implements:** Iterates 7 deltas and applies each delta uniformly to ALL SL/TP multipliers simultaneously. Produces only 7 grid points.

**Impact:** Cannot detect if a strategy is fragile to ONE specific parameter while robust to others. A strategy that collapses when SL_mult changes by 5% but is stable for TP_mult changes would test as robust under uniform perturbation.

**Recommendation:** Restructure the perturbation loop to iterate each parameter individually, holding others constant, per the spec's nested FOR loop.

---

#### G-OFF-046 — Version Snapshot: rollback_to_version() Unimplemented

**Block:** Support | **File:** `version_snapshot.py:51-79` | **Spec:** Doc 32 Version Snapshot Policy

**Spec requires:** `rollback_to_version(component_id, version_id, admin_user_id)` that: (1) loads target snapshot from D18, (2) runs pseudotrader comparison, (3) sends HIGH-priority notification for admin approval, (4) snapshots current state before restoring, (5) runs regression tests after rollback, (6) reverts if tests fail, (7) logs to AdminDecisionLog.

**Code implements:** Only `snapshot_before_update()` and `get_latest_version()` exist. No rollback function of any kind.

**Impact:** If a parameter update causes degraded performance, there is no automated way to revert to a known-good state. Manual intervention would be required.

**Recommendation:** Implement `rollback_to_version()` per spec. This requires integration with B3 pseudotrader for comparison, admin notification via alerts, approval workflow, and regression test trigger.

---

### Detailed Findings — HIGH (Selected)

---

#### G-OFF-009/011 — BOCPD/CUSUM State Not Persisted; Lost on Restart

**Block:** B2 | **Files:** `b2_bocpd.py:142-156`, `orchestrator.py:51` | **Spec:** Doc 32 PG-05

The BOCPD `to_dict()` only stores `cp_probability` and `cp_history` — not the full `run_length_posterior` or per-run-length NIG sufficient statistics. The QuestDB schema has a `bocpd_run_length_posterior` column that is never written. On process restart, all BOCPD/CUSUM detectors start fresh with default priors. The `from_dict()` deserializers exist but are never called by the orchestrator's startup. This means changepoint detection accuracy degrades after every restart until the detector re-converges.

---

#### G-OFF-010 — S2-19: CUSUM Bootstrap Calibration Missing at Init

**Block:** B2 | **File:** `b2_cusum.py`, `orchestrator.py` | **Spec:** Doc 32 PG-07

Spec requires calibration at init AND quarterly. Quarterly is implemented (`_run_quarterly`). Init-time calibration is NOT implemented. After fresh bootstrap, `sequential_limits` is empty and the CUSUM detector falls back to `default_limit=5.0` for all sprint lengths. This hardcoded limit may be too loose or too tight depending on the asset's volatility.

---

#### G-OFF-021 — G-025 CB Pseudotrader Still Not Account-Aware

**Block:** B3 | **File:** `b3_pseudotrader.py:619-755` | **Spec:** Doc 32 PG-09B

The prior audit flagged this as G-025 HIGH and deferred it via DEC-04. It remains unresolved. `run_cb_pseudotrader()` replays trades with/without CB layers but ignores DLL, MDD, scaling tiers, trading hours, and all other account constraints. The CB replay operates purely on CB parameters with no `account_config` input.

---

#### G-OFF-039 — Kelly Shrinkage Uses 1/√N Proxy

**Block:** B8 | **File:** `b8_kelly_update.py:108-116` | **Spec:** Doc 32 PG-15:664-666, Doc 21 L3

Spec: `shrinkage = max(0.3, 1.0 - compute_estimation_variance(P3-D05[u]))`. Code: `shrinkage = max(0.3, 1.0 - 1.0/sqrt(n_trades))`. The 1/√N proxy always produces the same shrinkage for a given N regardless of data noise. A volatile asset with 200 trades gets the same shrinkage as a stable one. This affects position sizing accuracy.

---

#### G-OFF-040/041 — CB Params: L_star Missing and cold_start Not Written

**Block:** B8 | **File:** `b8_cb_params.py:134-207` | **Spec:** Doc 32 PG-16C:686-715

L_star = -r̄/β_b (breakeven loss level) is not computed or stored. This is the threshold telling the circuit breaker at what cumulative loss the expected next-trade return turns negative. Without it, CB Layer 3 cannot make informed blocking decisions. Additionally, the `cold_start` boolean is missing from D25 writes, and the spec's two-tier threshold (n<10 skip entirely, 10≤n<100 cold_start=true) is collapsed to a single n<100 threshold.

---

#### G-OFF-049 — Bootstrap Does Not Initialize D02 (aim_meta_weights)

**Block:** Support | **File:** `bootstrap.py:80-211` | **Spec:** Doc 32 PG-02

The bootstrap initializes D05 (EWMA), D04 (decay), D12 (Kelly), D01 (AIM statuses) but NOT D02 (aim_meta_weights / inclusion probabilities). The DMA update (PG-02) requires existing D02 rows to apply the forgetting factor. Without D02 seeding, the first DMA update after bootstrap will either fail or produce undefined behavior.

---

### Key Validated Areas

The following spec requirements were verified as correctly implemented:

**B1 — AIM Training:**
- K=3 HMM states, N_FEATURES=7, 60-day training window, diagonal covariance, quartile P&L seeding
- DMA: λ=0.99, magnitude-weighted likelihood (SPEC-A9), z-score clamped at 3.0, normalisation
- HDWM: 6 seed types with correct AIM assignments, AIM-16 excluded, force-reactivate logic
- Drift: ADWIN detector, autoencoder pattern, weight *= 0.5, renormalisation

**B2 — Decay Detection:**
- BOCPD: Adams & MacKay 2007, NIG→Student-t, hazard=1/200, cp thresholds 0.8/0.9
- CUSUM: Two-sided, B=2000 bootstrap, ARL₀=200, sprint length tracking
- Level escalation: L2 reduction formula, L3 DECAYED + P1P2 + AIM14 scheduling
- Quarterly CUSUM recalibration schedule, Category A shared intelligence

**B3 — Pseudotrader:**
- CSCV PBO with S=16, DSR threshold 0.5, ADOPT/REJECT decision logic
- CB 4-layer implementation (halt, budget, expectancy, correlation Sharpe)
- Dual forecast system (Forecast A + B), multistage EVAL→XFA→LIVE lifecycle

**B4-B6 — Injection / Sensitivity / Expansion:**
- Thresholds: ADOPT_RATIO=1.2, PARALLEL_RATIO=0.9, PBO_THRESHOLD=0.5 (all match)
- Transition blending: linear weight over transition_days, correct ADOPT/PARALLEL semantics
- Sensitivity deltas: [-0.20, -0.10, -0.05, 0, +0.05, +0.10, +0.20], CSCV_SPLITS=8
- GA: population=100, generations=50, crossover=0.8, mutation=0.1, top_k=5

**B7-B9 — TSM / Kelly / CB / Diagnostic:**
- Kelly: f*=p-(1-p)/b, adaptive EWMA α from BOCPD cp, per-[asset][regime][session]
- All 8 health dimensions (D1-D8) implemented and scored ∈[0,1] (S2-20 satisfied)
- Weekly + monthly diagnostic scheduling, action item generation

**Support:**
- Category A vs B learning split correct (shared vs per-account)
- Event-triggered + scheduled execution modes
- Redis consumer groups with acknowledgment, exponential backoff
- Bootstrap: Kelly formula, AIM BOOTSTRAPPED status, Tier 1 set correct

---

## P3-Online — Captain Online (Signal Engine)

### Summary

| Status | Count |
|--------|-------|
| `[GAP]` | — |
| `[VALID]` | — |
| `[AMENDED]` | — |
| `[BLOCKED]` | — |
| **Total** | — |

### Findings

| ID | Block | File | Spec Ref | Status | Severity | Description |
|----|-------|------|----------|--------|----------|-------------|
| | | | | | | _(Session 4 will populate)_ |

### Detailed Findings

_(See `findings/`, `validation/`, `amendments/` subdirectories for per-component detail files)_

---

## P3-Command — Captain Command (Linking Layer)

### Summary

| Status | Count |
|--------|-------|
| `[GAP]` | — |
| `[VALID]` | — |
| `[AMENDED]` | — |
| `[BLOCKED]` | — |
| **Total** | — |

### Findings

| ID | Block | File | Spec Ref | Status | Severity | Description |
|----|-------|------|----------|--------|----------|-------------|
| | | | | | | _(Session 5 will populate)_ |

### Detailed Findings

_(See `findings/`, `validation/`, `amendments/` subdirectories for per-component detail files)_

---

## Shared Modules

### Summary

| Status | Count |
|--------|-------|
| `[GAP]` | — |
| `[VALID]` | — |
| `[AMENDED]` | — |
| `[BLOCKED]` | — |
| **Total** | — |

### Findings

| ID | Module | File | Spec Ref | Status | Severity | Description |
|----|--------|------|----------|--------|----------|-------------|
| | | | | | | _(Sessions 3-5 will populate as shared modules are referenced)_ |

---

## Cross-Cutting Concerns

### Summary

| Status | Count |
|--------|-------|
| `[GAP]` | — |
| `[VALID]` | — |
| `[AMENDED]` | — |
| `[BLOCKED]` | — |
| **Total** | — |

### Findings

| ID | Area | File(s) | Spec Ref | Status | Severity | Description |
|----|------|---------|----------|--------|----------|-------------|
| | | | | | | _(Session 6 will populate)_ |

---

## Final Rollup

| Program | GAP | VALID | AMENDED | BLOCKED | Total | Verdict |
|---------|-----|-------|---------|---------|-------|---------|
| P3-Offline | — | — | — | — | — | — |
| P3-Online | — | — | — | — | — | — |
| P3-Command | — | — | — | — | — | — |
| Shared | — | — | — | — | — | — |
| Cross-Cutting | — | — | — | — | — | — |
| **TOTAL** | — | — | — | — | — | **—** |

**Overall Verdict:** _(Session 6 will determine: READY / NOT READY)_

**BLOCKED Items Requiring Isaac's Input:**

_(Session 6 will list)_
