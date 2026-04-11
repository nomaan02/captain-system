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

**Audited:** 2026-04-11 Session 4
**Scope:** 16 files (14 blocks + orchestrator + main) + 2 shared modules (aim_compute.py, aim_feature_loader.py)
**Spec Documents:** Docs 20, 21, 23, 27, 31, 33

### Summary

| Status | Count |
|--------|-------|
| `[GAP]` | 49 |
| `[VALID]` | ~40 verification points confirmed |
| `[AMENDED]` | 8 |
| `[BLOCKED]` | 0 |
| **Total** | 57 findings (49 GAP + 8 AMENDED) |

| Severity | Count |
|----------|-------|
| CRITICAL | 3 |
| HIGH | 14 |
| MEDIUM | 22 |
| LOW | 10 |

### Findings Table

| ID | Block | File | Spec Ref | Status | Severity | Description |
|----|-------|------|----------|--------|----------|-------------|
| G-ONL-001 | B1-Ingest | b1_data_ingestion.py:444-451 | Doc 33 PG-21 §1b | `[GAP]` | MEDIUM | Timestamp validation failure skips asset via `continue` without setting DATA_HOLD or updating D00 |
| G-ONL-002 | B1-Ingest | b1_data_ingestion.py:426-433 | Doc 33 PG-21 §1b | `[GAP]` | MEDIUM | Volume sanity flags (ZERO_VOLUME, VOLUME_EXTREME) set but no incident created in D21 for audit trail |
| G-ONL-003 | B1-Ingest | b1_data_ingestion.py:635-668 | Doc 33 PG-21 §1b TZ | `[GAP]` | MEDIUM | `_has_valid_timestamp` checks staleness (>300s) but does not validate TZ offset; naive timestamps accepted via `fromisoformat` |
| G-ONL-004 | B1-Features | b1_features.py:863-864 | Doc 33 PG-21 §4 | `[GAP]` | HIGH | `_get_overnight_range` is hard stub returning None; AIM-01 vrp_overnight permanently unavailable in live mode |
| G-ONL-005 | B1-Features | b1_features.py:965-972 | Doc 33 PG-21 §4 | `[GAP]` | HIGH | `_get_options_volume`, `_get_put_iv`, `_get_option_chain` all hard stubs; AIM-02 (pcr, put_skew) and AIM-03 (gex) permanently data-starved |
| G-ONL-006 | B1-Features | b1_features.py:938-940 | Doc 33 PG-21 §4 | `[GAP]` | HIGH | `_get_trailing_pcr` hard stub; AIM-02 pcr_z feature double-blocked (no current + no trailing baseline) |
| G-ONL-007 | B1-Features | aim_feature_loader.py:161-173 | Doc 33 PG-21 §4 | `[GAP]` | MEDIUM | Replay cross_momentum uses 5d/20d return sign (discrete ±1); live uses MACD(12,26,9) (continuous). AIM-09 inconsistent between replay and live |
| G-ONL-008 | B1-Features | b1_features.py:1329-1365 | Doc 33 PG-21 §4 | `[GAP]` | LOW | `_get_recent_5min_vol` hardcodes 09:30 ET session open for all assets; NKD (APAC 18:00 ET) gets wrong window |
| G-ONL-009 | B1-Features | b1_features.py:992-993 | Doc 33 PG-21 §4 | `[GAP]` | LOW | `_get_risk_free_rate` hardcoded 0.05; should read from data source or D17 |
| G-ONL-010 | B1-Features | b1_features.py:1305-1309 | Doc 33 PG-21 §4 | `[GAP]` | LOW | `_get_cl_spot`/`_get_cl_front_futures` hard stubs; AIM-11 CL basis unavailable (CL not in active universe, impact deferred) |
| G-ONL-011 | B1-Features | aim_feature_loader.py:348-365 | Doc 33 PG-21 §4 | `[GAP]` | LOW | Replay `is_opex_window` uses ≤3 calendar days; live uses ≤2 trading days — minor edge-case discrepancy |
| G-ONL-012 | B2 | b2_regime_probability.py:144-178 | Doc 33 PG-22 | `[GAP]` | MEDIUM | `_compute_realised_vol` imports B1 private function `_get_daily_returns`; VRP fallback path is dead code returning None |
| G-ONL-013 | B3 | aim_compute.py:175-178 | Doc 33 PG-23 §3 | `[GAP]` | HIGH | `run_aim_aggregation()` does not return `session_budget_weights`; spec requires AIM-16 HMM budget in B3 return dict. Loaded separately by B5 from D26 |
| G-ONL-014 | B3 | aim_compute.py:192-208 | Doc 33 PG-23 §1 (S2-15) | `[GAP]` | MEDIUM | AIM dispatch iterates `range(1,17)` with no explicit cascade ordering; no AIM currently reads another's output, but no guard against future inter-AIM dependencies |
| G-ONL-015 | B3 | aim_compute.py:136 | Doc 33 PG-23 §2 | `[GAP]` | LOW | Individual AIM modifiers pre-clamped to [0.5,1.5] before weighted aggregation; spec only clamps combined_modifier post-aggregation |
| G-ONL-016 | B3 | aim_compute.py:102-107 | Doc 33 PG-23 | `[GAP]` | LOW | `_AIM_NAMES` dict has duplicate key `7`: first entry overwritten by second; affects log readability only |
| G-ONL-017 | B4 | b4_kelly_sizing.py:132-141 | Doc 33 PG-24 L4 | `[GAP]` | CRITICAL | L4 robust formula: spec says `f_robust = mu/(mu²+var)`; code computes distributional-robust `lower/(upper*lower) = 1/upper`. Algebraically unrelated formulas produce different Kelly fractions during regime uncertainty |
| G-ONL-018 | B4 | b4_kelly_sizing.py:252-260 | Doc 33 PG-24 L6→L7 | `[GAP]` | HIGH | Sizing override applied post-TSM (on final contracts) instead of pre-TSM (on Kelly fraction) as spec positions it between L6 and L7 |
| G-ONL-019 | B4 | b4_kelly_sizing.py:190-193 | Doc 33 PG-24 L7 | `[GAP]` | HIGH | `risk_per_contract` uses EWMA `avg_loss` as primary source instead of spec's `strategy_sl * point_value + expected_fee`; falls back to spec formula only when EWMA unavailable |
| G-ONL-020 | B5 | b5_trade_selection.py:31-130 | Doc 33 PG-25 | `[GAP]` | MEDIUM | No daily dollar budget concept; spec says `compute_daily_budget(user, session_budget_weights[session_id])` for top-down allocation. Code uses position limit + correlation filter instead |
| G-ONL-021 | B5B | b5b_quality_gate.py:49-77 | Doc 33 PG-25B | `[GAP]` | HIGH | Quality gate uses `edge * modifier * data_maturity` score; spec says `dollar_per_contract = signal.score / signal.contracts` with floor/ceiling check. Fundamentally different metric |
| G-ONL-022 | B5B | b5b_quality_gate.py:62-67 | Doc 33 PG-25B | `[GAP]` | MEDIUM | Spec says signals above quality_ceiling should be REMOVED; code uses ceiling as normalization target only — quality_multiplier=1.0 for above-ceiling signals |
| G-ONL-023 | B5B | b5b_quality_gate.py:49-77 | Doc 33 PG-25B | `[GAP]` | MEDIUM | Quality gate does not receive `final_contracts` data; cannot compute spec's `score/contracts` metric |
| G-ONL-024 | B5C | b5c_circuit_breaker.py:296-325 | Doc 33 PG-27B L2 | `[GAP]` | HIGH | L2 implements trade-count ceiling (`n_t >= N`) instead of spec's dollar-budget check (`remaining_budget = E - |L_t|; IF remaining < rho_j → BLOCK`). Oversized signals could pass |
| G-ONL-025 | B5C | b5c_circuit_breaker.py:375-437 | Doc 33 PG-27B L4 | `[GAP]` | HIGH | L4 computes analytical Sharpe `S = mu_b/(sigma*sqrt(1+2*n_t*rho_bar))` from all-time D25 params; spec says `rolling_basket_sharpe(lookback=60d)` from trade history |
| G-ONL-026 | B5C | b5c_circuit_breaker.py:342-353 | Doc 33 PG-27B L3 | `[GAP]` | MEDIUM | Extra significance gate (p>0.05 or n<100 → beta_b=0) beyond spec's simple `IF beta_b not None` check; redundant since Offline gates significance before D25 write |
| G-ONL-027 | B5C | b5c_circuit_breaker.py (whole) | Doc 33 PG-27B | `[GAP]` | MEDIUM | No Redis alert published when any CB layer trips; code only logs via `logger.info`. Operator unaware of CB activity |
| G-ONL-028 | B6 | b6_signal_output.py:94-134 | Doc 20 PG-26 | `[GAP]` | CRITICAL | Signal published to Redis includes `aim_breakdown`, `regime_probs`, `combined_modifier`, `expected_edge` — all PROHIBITED_EXTERNAL_FIELDS. Command B1 pushes unsanitized blob to GUI WebSocket |
| G-ONL-029 | B6 | b6_signal_output.py:94-134 | Doc 20 PG-26 | `[GAP]` | HIGH | Signal blob contains ~30 fields; spec mandates exactly 6 (asset, direction, size, TP, SL, timestamp). Sanitization deferred to Command B1 but not enforced at source |
| G-ONL-030 | B6 | b6_signal_output.py (whole) | Doc 20 PG-26 | `[GAP]` | HIGH | Anti-copy jitter completely missing: spec requires ±30s time jitter, ±1 micro size jitter for multi-user. Zero jitter code exists anywhere in the Online process |
| G-ONL-031 | B6 | b6_signal_output.py:99,269 | CLAUDE.md TZ rule | `[GAP]` | MEDIUM | `datetime.now()` without timezone at lines 99 and 269; should be `datetime.now(ZoneInfo("America/New_York"))` |
| G-ONL-032 | B7 | b7_position_monitor.py:134 | CLAUDE.md TZ rule | `[GAP]` | HIGH | Time-exit uses naive `datetime.now()` for buffer_time comparison; wrong-timezone forced closes possible during DST transitions |
| G-ONL-033 | B7 | b7_position_monitor.py:361-402 | Doc 33 PG-27 | `[GAP]` | MEDIUM | Redis payload uses "commission" field instead of spec's "fee" field; Offline must match field name to pick up commission data |
| G-ONL-034 | B7 | b7_position_monitor.py:386,418,511 | CLAUDE.md TZ rule | `[GAP]` | MEDIUM | Three additional `datetime.now()` calls without timezone in Redis payload and notification timestamps |
| G-ONL-035 | B7 | b7_position_monitor.py:272-296 | Doc 33 PG-27 D03 | `[GAP]` | LOW | D03 write does not set `exit_time` column (table has it in init_questdb.py:121); exit_time always NULL |
| G-ONL-036 | B7-Shadow | b7_shadow_monitor.py:165-170 | Reliability | `[GAP]` | HIGH | Shadow monitor `publish_to_stream` has no retry logic; real B7 has 3-attempt exponential backoff. Shadow publish failure → Category A learning divergence between instances |
| G-ONL-037 | B7-Shadow | b7_shadow_monitor.py:62,88,162 | CLAUDE.md TZ rule | `[GAP]` | MEDIUM | Three `datetime.now()` calls without timezone: created_at, age computation, Redis payload timestamp |
| G-ONL-038 | B7-Shadow | b7_shadow_monitor.py:61 | CLAUDE.md multi-user | `[GAP]` | LOW | Hardcoded fallback "primary_user" in register/resolve paths; should derive from signal context only |
| G-ONL-039 | B8 | b8_concentration_monitor.py:30-109 | Doc 33 PG-28 | `[GAP]` | MEDIUM | PG-28 counts open positions by direction (LONG vs SHORT fraction); code measures user concentration (users_in_direction / total_users). Different metric |
| G-ONL-040 | B8 | b8_concentration_monitor.py:120 | Doc 33 PG-28 | `[GAP]` | LOW | Spec says priority="HIGH" for concentration alert; code uses "CRITICAL" — over-escalation may cause alert fatigue |
| G-ONL-041 | B8 | b8_concentration_monitor.py:76,124 | CLAUDE.md TZ rule | `[GAP]` | LOW | `datetime.now().isoformat()` in alert timestamps without timezone |
| G-ONL-042 | B9 | b9_capacity_evaluation.py:26-162 | Doc 33 PG-29 | `[GAP]` | CRITICAL | Spec requires per-asset fill slippage analysis (fill_quality, slippage_bps, avg_fill_time, fill_rate, volume_participation); code implements supply/demand capacity planning model. None of the five spec metrics exist |
| G-ONL-043 | B9 | b9_capacity_evaluation.py:26-162 | Doc 33 PG-29 | `[GAP]` | HIGH | No notification/alert published when slippage exceeds threshold; spec requires NOTIFY priority="MEDIUM" |
| G-ONL-044 | B9 | b9_capacity_evaluation.py:138,169-186 | Doc 33 PG-29 | `[GAP]` | MEDIUM | Naive `datetime.now()` and `LIKE %s` query without `LATEST ON` deduplication |
| G-ONL-045 | Orch | orchestrator.py:102-136 | Doc 33 | `[GAP]` | MEDIUM | No periodic heartbeat published to `captain:status`; Command cannot distinguish "idle Online" from "dead Online" |
| G-ONL-046 | Orch | orchestrator.py:204-207 | Doc 33 | `[GAP]` | MEDIUM | D00 asset query lacks `LATEST ON last_updated PARTITION BY asset_id`; fetches all historical rows, compensates with `_seen` set |
| G-ONL-047 | Orch | orchestrator.py:714-728 | Doc 33 | `[GAP]` | MEDIUM | D15 user query `SELECT user_id, role FROM p3_d15...` has no `LATEST ON` dedup or WHERE filter; fetches entire user history table |
| G-ONL-048 | Main | main.py:107-110 | Doc 33 crash recovery | `[GAP]` | HIGH | `get_last_checkpoint` called and logged but never acted upon; mid-session crash checkpoint ignored on restart |
| G-ONL-049 | Main | main.py:1-144 | CLAUDE.md TZ rule | `[GAP]` | MEDIUM | No `os.environ["TZ"]` or timezone enforcement at process level; stdlib calls using local time may produce wrong timestamps |

**Amended Items (intentional deviations):**

| ID | Block | File | Spec Ref | Description | Rationale |
|----|-------|------|----------|-------------|-----------|
| G-ONL-A01 | B1 | b1_data_ingestion.py:48-96 | Doc 33 PG-21 §1 | Active asset filter includes WARM_UP and TRAINING_ONLY beyond spec's ACTIVE-only | Extension: these statuses receive data but signals gated downstream |
| G-ONL-A02 | B3/B5 | aim_compute.py:31, b5_trade_selection.py:149-190 | Doc 33 PG-23 §3 | AIM-16 HMM session budget in B5 not B3 as spec requires | DEC-06: architectural placement change; functionally equivalent via D26 |
| G-ONL-A03 | B2 | b2_regime_probability.py:144-178 | Doc 33 PG-22 | Classifier fallback uses regime_label from P2-D07 when no model available | Pragmatic V1: safe degradation for assets without trained classifier |
| G-ONL-A04 | B4 | b4_kelly_sizing.py:147-148,239-250 | Doc 33 PG-24 | Extra user_kelly_ceiling (step 5) and portfolio risk cap (step 7) beyond spec | Defensive additions; more conservative than spec allows |
| G-ONL-A05 | B5C | b5c_circuit_breaker.py:263-293 | Doc 33 PG-27B L1 | L1 computes `l_halt = c*e*A` inline instead of reading `P3-D08[ac].L_halt` | Functionally equivalent but duplicates formula; drift risk if D08 computation changes |
| G-ONL-A06 | B5C | b5c_circuit_breaker.py:578-580 | Doc 33 PG-27B | L6 manual override is permanent stub returning False | V1 placeholder; manual override not yet implemented |
| G-ONL-A07 | B6 | b6_signal_output.py:263-275 | Doc 20 PG-26 | Redis Streams (`stream:signals`) instead of spec's pub/sub (`signals:{user_id}`) | Durability upgrade: Streams provide consumer group ACK and replay |
| G-ONL-A08 | B7-Shadow | b7_shadow_monitor.py:190-201 | ORB entry | Shadow entry price uses TP/SL midpoint heuristic (1/3 from SL toward TP) | Approximation when no explicit entry_price; fragile if TP/SL ratios change |

### Detailed Findings — CRITICAL

---

#### G-ONL-017 — Kelly L4 Robust Fallback Formula Algebraically Wrong

**Block:** B4 | **File:** `b4_kelly_sizing.py:132-141` | **Spec:** Doc 33 PG-24 L4, Doc 21 Part 3

**Spec requires:** `f_robust = mu / (mu^2 + var) IF mu > 0 ELSE 0` — a standard mean-variance Kelly approximation that fires when `regime_uncertain[u]` is true.

**Code implements:** Delegates to `compute_robust_kelly` in `b1_features.py:468-481` which computes return bounds `(mu - 1.5*sigma, mu + 1.5*sigma)` then `f_robust = lower / (upper * lower)`. This simplifies algebraically to `1/upper`, which is a distributional-robust min-max approach — an entirely different formula.

**Impact:** During regime uncertainty (the exact scenario where this fallback fires), the two formulas produce substantially different Kelly fractions. For a typical `mu=0.02, sigma=0.05`: spec yields `f_robust = 0.02/(0.0004+0.0025) = 6.9`, code yields `1/(0.02+0.075) = 10.5` — a 52% oversize. Position sizing is directly affected.

**Recommendation:** Replace the robust formula with the spec's `mu / (mu^2 + var)` or document the intentional deviation with DEC-XX.

---

#### G-ONL-028 — Prohibited Fields Leak Through GUI WebSocket

**Block:** B6 | **File:** `b6_signal_output.py:94-134` | **Spec:** Doc 20 PG-26, `shared/constants.py` PROHIBITED_EXTERNAL_FIELDS

**Spec requires:** Signal output limited to 6 fields: `asset, direction, size, TP, SL, timestamp`. PROHIBITED_EXTERNAL_FIELDS must never appear in external-facing signals.

**Code implements:** B6 publishes ~30 fields to Redis including `aim_breakdown`, `regime_probs`, `combined_modifier`, `expected_edge`, `win_rate`, `payoff_ratio` — all prohibited. Command B1's `sanitise_for_api()` correctly strips these for the API adapter, but `gui_push_fn` at `b1_core_routing.py:78-81` pushes the full unsanitized blob to the GUI WebSocket.

**Impact:** Any user with GUI access can see the system's internal signal reasoning — AIM weights, regime probabilities, Kelly edge. In multi-user deployment, this leaks proprietary trading intelligence. The sanitization boundary is deferred to Command rather than enforced at source.

**Recommendation:** Apply field sanitization in B6 before Redis publish, or add a separate sanitization step in Command B1's `gui_push_fn` path.

---

#### G-ONL-042 — Capacity Evaluation Implements Entirely Different Algorithm

**Block:** B9 | **File:** `b9_capacity_evaluation.py:26-162` | **Spec:** Doc 33 PG-29

**Spec requires:** Per-asset fill slippage analysis: compare actual fill prices to expected signal prices, compute `fill_quality`, `slippage_bps`, `avg_fill_time`, `fill_rate`, `volume_participation`. Alert when `slippage_bps > threshold`.

**Code implements:** A multi-user capacity planning model based on signal supply/demand ratios, quality pass rates, correlation-adjusted diversity, and strategy homogeneity. None of the five spec metrics (slippage_bps, avg_fill_time, fill_rate, volume_participation, fill_quality) exist in the code. The code never reads trade fill data or signal prices.

**Impact:** No empirical fill quality monitoring exists. If market microstructure degrades (slippage increases), the system has no way to detect or alert. The implemented model serves a different purpose (multi-user capacity planning) that is useful but does not replace the spec's fill quality monitoring.

**Recommendation:** Implement the spec's PG-29 fill analysis as a separate function alongside the existing capacity planning. Both serve valid but different purposes.

---

### Detailed Findings — HIGH (Selected)

---

#### G-ONL-004/005/006 — Three AIMs Data-Starved by Hard Stubs

**Block:** B1-Features | **Files:** `b1_features.py:863,965-972,938` | **Spec:** Doc 33 PG-21 §4

Three feature data source functions are permanently stubbed returning None: `_get_overnight_range` (AIM-01 vrp_overnight), `_get_options_volume`/`_get_put_iv`/`_get_option_chain` (AIM-02 pcr/put_skew, AIM-03 gex), and `_get_trailing_pcr` (AIM-02 pcr_z). These AIMs may have ACTIVE status in D01 but produce zero useful signal. The AIM aggregation handles None gracefully (neutral modifier), so no wrong trades result, but three intelligence modules contribute nothing.

---

#### G-ONL-024 — CB L2 Uses Trade-Count Budget Instead of Dollar Budget

**Block:** B5C | **File:** `b5c_circuit_breaker.py:296-325` | **Spec:** Doc 33 PG-27B L2

Spec: `remaining_budget = E - |L_t|; IF remaining < rho_j → BLOCK`. Code: `IF n_t >= N → BLOCK` where `N = floor((e*A)/(MDD*p+phi))`. A trade-count ceiling cannot detect that a single large-rho_j signal exceeds the dollar budget when total trade count is still under N. Conversely, it may block small signals when count hits N even though dollar budget remains.

---

#### G-ONL-030 — Anti-Copy Jitter Completely Missing

**Block:** B6 | **File:** `b6_signal_output.py` (whole) | **Spec:** Doc 20 PG-26

Spec: `time_jitter = random_uniform(-30, +30) seconds; size_jitter = random_choice([-1, 0, +1]) micros`. Grep across entire codebase confirms zero matches for "jitter", "anti_copy", or related patterns. This is required for multi-instance deployment to avoid prop firm copy-trading detection. Single-instance V1 is unaffected.

---

#### G-ONL-032 — Position Monitor Time-Exit Uses Naive datetime

**Block:** B7 | **File:** `b7_position_monitor.py:134` | **Spec:** CLAUDE.md timezone rule

Time-exit forced close uses `datetime.now()` without timezone. During DST transitions (spring forward/fall back), naive datetime could be off by 1 hour, causing premature or late forced exits. All other time-critical logic in the Online process uses `ZoneInfo("America/New_York")`.

---

### Key Validated Areas

The following spec requirements were verified as correctly implemented:

**B1 — Data Ingestion:**
- Contract rollover: `roll_confirmed` flag, `ROLL_PENDING` status, CRITICAL alert for ≤0 days, HIGH for ≤3 days (S2-22 **satisfied**)
- Price bounds: 5% threshold → `PRICE_SUSPECT` + `DATA_HOLD` + D21 incident
- Session matching: SESSION_IDS constant (1=NY, 2=LON, 3=APAC) with fallback
- Feature list completeness: all 20+ spec features mapped in AIM_FEATURE_MAP across 16 AIMs
- IVTS (VIX/VXV): always computed regardless of AIM-04 status as CRITICAL regime filter
- Correlation z-score: rolling 20d with dynamic asset pairs, trailing 252d baseline
- Cross-asset momentum: MACD(12,26,9) with 21-day lookback
- Offline data loading: D01, D02, D05, D08, D12 all correctly loaded with dedup

**B2 — Regime Probability:**
- `regime_uncertain` threshold at strict `< 0.6` (not ≤0.6) — matches spec
- BINARY_THRESHOLD classifier branch exists and returns correct probabilities
- S2-05: AIM-05 (Order Book) deferred status correctly returns modifier=1.0, confidence=0.0

**B3 — AIM Aggregation:**
- MoE weighted aggregation: `sum(m_i * w_i) / sum(w_i)` with fallback to 1.0 — correct
- `combined_modifier` clamped to [0.5, 1.5] via MODIFIER_FLOOR/CEILING constants
- `aim_breakdown` stored per asset and passed through orchestrator to B7 for learning loop

**B4 — Kelly Sizing:**
- L2 blended Kelly: regime-weighted sum across LOW_VOL/HIGH_VOL — correct
- L3 shrinkage: multiplication by shrinkage_factor — correct
- L5 AIM modifier: multiplication by combined_modifier — correct
- L6 account adjustment: pass_prob thresholds (0.5→0.5, 0.7→0.7, else→0.85), PRESERVE_CAPITAL→0.5 — all correct
- L7 TSM: MDD cap, MLL cap, max_contracts, XFA scaling cap, fee in risk_per_contract — all present

**B5 — Trade Selection:**
- Signal ranking by edge × contracts: correct sorting
- HMM session allocation: cold-start ramp (<20 equal, 20-59 blended, 60+ full HMM), 0.05 floor

**B5C — Circuit Breaker:**
- L0 scaling cap: XFA-only guard with micro_equivalent comparison — correct
- L1 preemptive halt: `rho_j = contracts * (sl_distance * pv + fee)`, halt check — correct
- L3 beta_b expectancy: `mu_b = r_bar + beta_b * L_t`, block if ≤0 — correct

**B6 — Signal Output:**
- S2-04 priority rotation correctly deferred for V1 single-user
- Direction-zero safety guard prevents publishing directionless signals
- TP/SL ORB computation: `tp_multiple * or_range` and `sl_multiple * or_range` — correct

**B7 — Position Monitor:**
- D03 outcome includes aim_breakdown_at_entry from Block 3 cache
- D23 L_t and n_t updated atomically on trade close
- Commission resolution: 4-source chain (API, fee_schedule, per_contract, zero fallback)
- Redis publish to `stream:trade_outcomes` with 3-attempt exponential backoff retry

**B7-Shadow — Shadow Monitor:**
- Registers all signals as shadows, removes on TAKEN — correct Category A learning flow
- Publishes theoretical outcomes with `theoretical=True` flag for Offline shared intelligence

**B8 — Concentration + OR Tracker:**
- 80% concentration threshold matches spec (DEFAULT_CONCENTRATION_THRESHOLD=0.8)
- Advisory only — does not block execution
- OR Tracker: proper ET timezone, thread-safe with Lock, complete state machine (WAITING→FORMING→COMPLETE→BREAKOUT/EXPIRED)

**Orchestrator:**
- B1-B3 SHARED computed once per session before per-user loop — correct
- B4-B9 PER-USER iterates over active users — correct
- Session-driven dispatch via session_registry.json with dedup guard
- Redis Stream consumer for commands channel with ACK and exponential backoff

**S2-Flagged Item Resolution:**
- S2-04: Signal Distribution priority rotation → correctly deferred for V1 (**VALID**)
- S2-05: AIM-05 deferred → modifier=1.0, confidence=0.0 (**VALID**)
- S2-15: AIM cascade ordering → no explicit cascade; currently no inter-AIM deps (**G-ONL-014 MEDIUM**)
- S2-22: Contract rollover roll_confirmed → fully implemented (**VALID**)

---

## P3-Command — Captain Command (Linking Layer)

### Summary

| Status | Count |
|--------|-------|
| `[GAP]` | 65 |
| `[VALID]` | ~35 |
| `[AMENDED]` | 3 |
| `[BLOCKED]` | 0 |
| **Total** | 68 |

**Severity Breakdown:**

| Severity | Count |
|----------|-------|
| CRITICAL | 4 |
| HIGH | 15 |
| MEDIUM | 31 |
| LOW | 18 |
| AMENDED | 3 |
| **Total Findings** | **71** |

### Findings Table

| ID | Block | File | Spec Ref | Status | Severity | Description |
|----|-------|------|----------|--------|----------|-------------|
| G-CMD-001 | api.py | api.py:113-142 | Doc 19 §4 (S2-09) | `[GAP]` | CRITICAL | No RBAC enforcement: JWT middleware extracts user_id but never validates roles; any authenticated user accesses any endpoint |
| G-CMD-002 | B6 | b6_reports.py:32-44 | Doc 29 §2.5 (S2-06) | `[GAP]` | CRITICAL | RPT-12 Alpha Decomposition completely missing; only 11 of 12 reports exist |
| G-CMD-003 | B10 | b10_data_validation.py (entire) | Doc 34 PG-41 | `[GAP]` | CRITICAL | Missing continuous data freshness/staleness monitoring; code only validates user inputs, no data feed checks |
| G-CMD-004 | B8 | b8_reconciliation.py:109-111 | Doc 34 PG-39 step 1 | `[GAP]` | CRITICAL | Balance mismatch sends GUI notification only; spec requires create_incident("RECONCILIATION", "P2_HIGH", "FINANCE") for audit trail in D21 |
| G-CMD-005 | api.py | api.py:281,557,574,584,784+ | Doc 19 §7 (S2-07) | `[GAP]` | HIGH | Hardcoded "primary_user" in 13 locations; multi-user data isolation completely broken |
| G-CMD-006 | api.py | api.py (entire) | Doc 19 §10 (S2-18) | `[GAP]` | HIGH | No audit trail logging; no AuditLog table; no user_id/timestamp/action/old_value/new_value records |
| G-CMD-007 | api.py | api.py:284 | Doc 19 §6 | `[GAP]` | HIGH | No JWT silent refresh mechanism; 24h expiry with no /auth/refresh endpoint |
| G-CMD-008 | B3 | b3_api_adapter.py:432-438 | Doc 34 PG-32 | `[GAP]` | HIGH | API connection failure uses notify_fn() not create_incident(); no incident record in D21 |
| G-CMD-009 | B3 | b3_api_adapter.py:468-471 | Doc 34 PG-32 (S2-12) | `[GAP]` | HIGH | No compliance_check function with max_contracts/instrument_permitted; B12 only checks global gate flags |
| G-CMD-010 | B7 | b7_notifications.py:241-256 | Doc 26 §7 | `[GAP]` | HIGH | LOW priority routed to GUI; spec says log-only with optional digest |
| G-CMD-011 | B7 | b7_notifications.py (entire) | Doc 26 §1,§7 | `[GAP]` | HIGH | Email channel completely unimplemented; P1_CRITICAL requires ALL channels including Email |
| G-CMD-012 | B7 | b7_notifications.py:449 | Doc 26 | `[GAP]` | HIGH | _get_users_by_roles uses $1,$2 PostgreSQL placeholders instead of QuestDB %s; role-based queries fail at runtime |
| G-CMD-013 | B8 | b8_reconciliation.py:73 | Doc 25+34 (S2-13) | `[GAP]` | HIGH | Scaling tier gated on topstep_optimisation instead of scaling_plan_active; XFA scaling skipped for accounts without topstep_optimisation flag |
| G-CMD-014 | B9 | b9_incident_response.py:41 | Doc 26 §7, Doc 29 §2.4 | `[GAP]` | HIGH | P1_CRITICAL routes to ADMIN only on GUI+Telegram; spec requires ADMIN+DEV, ALL channels, quiet hours override |
| G-CMD-015 | B9 | b9_incident_response.py (entire) | Doc 29 §2.4 (S2-21) | `[GAP]` | HIGH | No escalation matrix: P1=5min, P2=30min, P3=4hr, P4=next day — no timers, no acknowledgement tracking |
| G-CMD-016 | B10 | b10_data_validation.py (entire) | Doc 34 PG-41 | `[GAP]` | HIGH | Missing completeness validation with incident creation; returns dicts instead of calling create_incident |
| G-CMD-017 | B10 | b10_data_validation.py (entire) | Doc 34 PG-41 | `[GAP]` | HIGH | Missing format/schema validation with incident creation |
| G-CMD-018 | B12 | b12_compliance_gate.py (entire) | Doc 34 PG-32 (S2-12) | `[GAP]` | HIGH | Missing instrument_permitted check per signal; only checks 11 RTS6 boolean flags |
| G-CMD-019 | B12 | b12_compliance_gate.py (entire) | Doc 34 PG-32 (S2-12) | `[GAP]` | HIGH | Missing max_contracts check per signal; gate is global pass/fail not per-order |
| G-CMD-020 | B1 | b1_core_routing.py:40 | Doc 34 PG-30 | `[GAP]` | MEDIUM | PROHIBITED_EXTERNAL_FIELDS imported but never enforced at runtime; whitelist approach works but no defensive assertion |
| G-CMD-021 | B1 | b1_core_routing.py:84-93 | Doc 34 PG-30 | `[GAP]` | MEDIUM | No account_belongs_to_user(ac_id, user_id) validation in signal routing; multi-user cross-account risk |
| G-CMD-022 | B2 | b2_gui_data_server.py:117-136 | Doc 34 PG-31 | `[GAP]` | MEDIUM | Dashboard field names diverge from spec: pending_signals→signals, open_positions→positions, capital_silo→capital, aim_states→aim_panel |
| G-CMD-023 | B2 | b2_gui_data_server.py:117-136 | Doc 34+18 PG-31 | `[GAP]` | MEDIUM | Dashboard missing universe (P3-D00) field entirely |
| G-CMD-024 | B2 | b2_gui_data_server.py:425-458 | Doc 18 §5 | `[GAP]` | MEDIUM | AIM panel summary missing Confidence, 30-day hit rate, Last retrained; meta_weight always None |
| G-CMD-025 | B2 | b2_gui_data_server.py:144-164 | Doc 18 §7 | `[GAP]` | MEDIUM | System overview missing all_users section and parameter_editor (read-only params only) |
| G-CMD-026 | B2 | b2_gui_data_server.py (entire) | Doc 18 §3 | `[GAP]` | MEDIUM | No autonomy tier support: FULL_AUTO/SEMI_AUTO(default)/MANUAL not implemented |
| G-CMD-027 | B3 | b3_api_adapter.py:354-366 | Doc 34 PG-32 | `[GAP]` | MEDIUM | No per-account adapter loading loop with api_type dispatch; single hardcoded TopstepX adapter |
| G-CMD-028 | B3 | b3_api_adapter.py:147-190 | Doc 34 PG-32 | `[GAP]` | MEDIUM | Initial connect bypasses per-account vault credential loading; uses env vars directly |
| G-CMD-029 | B4 | b4_tsm_manager.py:179-217 | Doc 34 PG-33 | `[GAP]` | MEDIUM | No onboard_account() that atomically stores D08 + appends D16; stores split across main.py and bootstrap |
| G-CMD-030 | B4 | b4_tsm_manager.py:274-299 | Doc 25 | `[GAP]` | MEDIUM | Missing resolve_commission(tsm, asset, contracts) function; caller must multiply fee × contracts |
| G-CMD-031 | B4 | b4_tsm_manager.py:274-299 | Doc 25 | `[GAP]` | MEDIUM | Missing get_expected_fee(tsm, asset) named function; similar function exists under different name |
| G-CMD-032 | B5 | b5_injection_flow.py:169-176 | Doc 34 PG-34 | `[GAP]` | MEDIUM | Decision enum uses abbreviated names (ADOPT/REJECT vs ADOPT_STRATEGY/REJECT_STRATEGY) at API boundary |
| G-CMD-033 | B6 | b6_reports.py:32-44 | Doc 29 §2.5 | `[GAP]` | MEDIUM | Report names deviate from spec: "Monthly Decay" vs "Monthly Health", "Strategy Comparison" vs "Injection Comparison" |
| G-CMD-034 | B6 | b6_reports.py:32-44 | Doc 34 PG-35 | `[GAP]` | MEDIUM | No scheduled trigger mechanism; all 11 reports are on-demand only despite spec triggers (pre-session, weekly, monthly) |
| G-CMD-035 | B6 | b6_reports.py:529-549 | Doc 34 PG-35 | `[GAP]` | MEDIUM | D09 archive stores metadata only (6 fields); actual report content/data payload discarded |
| G-CMD-036 | B6 | b6_reports.py:145-529 | Doc 29 §2.5 | `[GAP]` | MEDIUM | 9 of 11 reports are shallow: raw query dump to CSV without spec-required analytics/aggregation (RPT-04 and RPT-07 are exceptions) |
| G-CMD-037 | B7 | b7_notifications.py:479-524 | Doc 26 §6 | `[GAP]` | MEDIUM | D10 delivery log missing channel field; uses boolean flags per row instead of per-channel rows |
| G-CMD-038 | B7 | b7_notifications.py:290-297 | Doc 26 | `[GAP]` | MEDIUM | No delivery retry mechanism; failed Telegram sends silently dropped |
| G-CMD-039 | B8 | b8_reconciliation.py:419-437 | Doc 34 PG-39 step 3 | `[GAP]` | MEDIUM | D23 reset inserts L_t=0, n_t=0 but does not clear session_trades[] as spec requires |
| G-CMD-040 | B8 | b8_reconciliation.py:298-391 | Doc 25 (S2-14) | `[GAP]` | MEDIUM | Payout missing XFA 5-winning-days requirement; only BROKER_LIVE checks winning_days |
| G-CMD-041 | B9 | b9_incident_response.py:42 | Doc 26 §7 | `[GAP]` | MEDIUM | P2_HIGH routes to ADMIN only; spec requires ADMIN + RISK |
| G-CMD-042 | B9 | b9_incident_response.py:43 | Doc 26 §7, Doc 29 §2.4 | `[GAP]` | MEDIUM | P3_MEDIUM routes to generic ADMIN; spec says assigned owner |
| G-CMD-043 | B10 | b10_data_validation.py (entire) | Doc 34 PG-41 | `[GAP]` | MEDIUM | No integration with B9 incident response; validation errors returned as dicts, never trigger incidents |
| G-CMD-044 | B11 | b11_replay_runner.py:206 | N/A (quality) | `[GAP]` | MEDIUM | _active_sessions dict has no eviction/cleanup; completed sessions accumulate unboundedly |
| G-CMD-045 | B12 | b12_compliance_gate.py:46-54 | N/A (quality) | `[GAP]` | MEDIUM | compliance_gate.json reloaded from disk on every call with no caching |
| G-CMD-046 | api.py | api.py:211-216 | Doc 34 PG-30 (S2-16) | `[GAP]` | MEDIUM | Health endpoint never returns HALTED overall status; CB halt doesn't propagate to top-level status |
| G-CMD-047 | api+orch | api.py:159, orchestrator.py:107+ | CLAUDE.md TZ rule | `[GAP]` | MEDIUM | Naive datetime.now() in 8+ locations; functionally OK in Docker but fragile outside container |
| G-CMD-048 | api.py | api.py:257-271 | Doc 18 §10 | `[GAP]` | MEDIUM | /api/status leaks internal adapter state and WebSocket session counts beyond 6-field limit |
| G-CMD-049 | telegram | telegram_bot.py:39-53 | Doc 26 §3 | `[GAP]` | MEDIUM | Rate limiter _rate_window and _mute_until dicts unprotected across threads |
| G-CMD-050 | telegram | telegram_bot.py:600-608 | Doc 26 §3 | `[GAP]` | MEDIUM | HTML injection possible via unsanitized message text in parse_mode=HTML Telegram calls |
| G-CMD-051 | B1 | b1_core_routing.py:160 | Doc 34 PG-30 | `[GAP]` | LOW | TAKEN and SKIPPED merged into single TAKEN_SKIPPED command type with sub-field discriminator |
| G-CMD-052 | B1 | b1_core_routing.py:290-331 | Doc 34 PG-30 | `[GAP]` | LOW | Push notification channel missing from routing (V2 feature) |
| G-CMD-053 | B2 | b2_gui_data_server.py:461-585 | Doc 18 §5 | `[GAP]` | LOW | AIM detail modal returns inclusion_probability but no explicit "Confidence" alias |
| G-CMD-054 | B4 | b4_tsm_manager.py:115-116 | Doc 25+34 PG-33 | `[GAP]` | LOW | No default_fee_schedule(category) function; fees silently default to 0 |
| G-CMD-055 | B5 | b5_injection_flow.py:51-62 | Doc 34 PG-34 | `[GAP]` | LOW | RPT-05 not proactively generated on candidate notification; user must fetch on demand |
| G-CMD-056 | B5 | b5_injection_flow.py:144-146 | Security | `[GAP]` | LOW | Error response leaks raw exception string to API consumers |
| G-CMD-057 | B6 | b6_reports.py:32-44 | Doc 29 §2.5 | `[GAP]` | LOW | Notification priority mapping per report not implemented (RPT-03,10,11=LOW; others=MEDIUM) |
| G-CMD-058 | B6 | b6_reports.py:47-103 | Doc 29 | `[GAP]` | LOW | Data source documentation missing per report; only RPT-04 has proper docstring |
| G-CMD-059 | B7 | b7_notifications.py:49 | Doc 26 §2 | `[GAP]` | LOW | CRITICAL event count comment says "9 events" but actual count is 10 |
| G-CMD-060 | B7 | b7_notifications.py:339 | Doc 26 | `[GAP]` | LOW | zoneinfo re-imported inside function body on every quiet hours check |
| G-CMD-061 | B8 | b8_reconciliation.py:221 | Doc 25 | `[GAP]` | LOW | MDD fallback default 4500 hardcoded; should warn when triggered |
| G-CMD-062 | B9 | b9_incident_response.py:86 | Doc 34 PG-40 | `[GAP]` | LOW | Incident ID truncated UUID hex (12 chars) instead of full UUID |
| G-CMD-063 | B9 | b9_incident_response.py:56 | Doc 34 PG-40 | `[GAP]` | LOW | system_snapshot is optional param (default None); spec says auto-capture on every incident |
| G-CMD-064 | B11 | b11_replay_runner.py:184-193 | Security | `[GAP]` | LOW | Error string leakage to GUI WebSocket via str(exc) |
| G-CMD-065 | telegram | telegram_bot.py:586-623 | Doc 26 §3 | `[GAP]` | LOW | Uses raw urllib.request instead of python-telegram-bot library's send API |
| G-CMD-066 | telegram | telegram_bot.py:113 | Doc 26 §3 | `[GAP]` | LOW | Open position count uses fragile WHERE exit_time IS NULL query on outcome log |
| G-CMD-067 | main.py | main.py (entire) | CLAUDE.md TZ rule | `[GAP]` | LOW | No explicit timezone set in code; relies entirely on Docker ENV TZ |
| G-CMD-068 | orch | api.py:156-160, orchestrator.py:104-108 | N/A (quality) | `[GAP]` | LOW | Duplicate process_health dicts in api.py and orchestrator.py; divergence risk |

**Amended Items (intentional deviations):**

| ID | Block | File | Spec Ref | Description | Rationale |
|----|-------|------|----------|-------------|-----------|
| G-CMD-A01 | B1 | b1_core_routing.py:71-100 | Doc 20 S2-04 | Signal distribution priority rotation deferred | V1 single-user; no distribution needed |
| G-CMD-A02 | B4 | b4_tsm_manager.py:38-52 | Doc 34 PG-33 | Validation requires 5 fields (superset of spec's 3) and accepts 7 categories (superset of spec's 5) | More restrictive onboarding; forward-compatible categories |
| G-CMD-A03 | B4 | b4_tsm_manager.py:296-299 | Doc 25 | Fee fallback uses cpc × 2 (round-turn) per-contract matching spec | Caller multiplies by contracts; correct total |

### Detailed Findings — CRITICAL

#### G-CMD-001 — No RBAC Enforcement Anywhere in API

**Spec:** Doc 19 §4 defines 6 roles (ADMIN, ANALYST/DEV, TRADER, VIEWER, SYSTEM, AUDITOR) with tag-based permissions. ADMIN gets full control; VIEWER is read-only; AUDITOR gets read logs with no mutating actions.

**Code:** `api.py:113-142` — JWT middleware extracts `sub` (user_id) from the token and stores it in `request.state`, but the JWT payload (`api.py:299-303`) contains only `sub`, `iat`, and `exp` — no `roles` or `tags` field. Endpoints like `/api/system-overview` (line 592) and `/api/aim/{aim_id}/activate` (line 571) have comments saying "ADMIN only" but zero enforcement code exists. Any authenticated user can: activate/deactivate AIMs, view system overview, modify notification preferences, start replays, and access all endpoints indiscriminately.

**Impact:** In V2 multi-user deployment, a VIEWER-role user could activate/deactivate AIMs or trigger diagnostics. Even in V1, the complete absence of role infrastructure means adding RBAC later requires changes across every endpoint.

#### G-CMD-002 — RPT-12 Alpha Decomposition Completely Missing

**Spec:** Doc 29 §2.5 defines 12 reports (RPT-01 through RPT-12). RPT-12 "Alpha Decomposition" should decompose PnL into: base strategy contribution, regime conditioning, AIM modifiers, and Kelly sizing effects. Sources: P3-D03, D02, D05, D12. Trigger: monthly / on-demand.

**Code:** `b6_reports.py:32-44` — `REPORT_TYPES` registry contains only 11 entries (RPT-01 through RPT-11). Module docstring at line 9 says "11 report types." The `generators` dict at lines 76-88 has no RPT-12 entry. No alpha decomposition function exists anywhere in the codebase.

**Impact:** The system cannot attribute returns to its component strategies. Without alpha decomposition, it is impossible to determine whether AIM modifiers, regime conditioning, or the base strategy drive performance — critical for model validation (Doc 29 Part 3).

#### G-CMD-003 — B10 Data Validation Missing Continuous Monitoring

**Spec:** Doc 34 PG-41 requires continuous validation of incoming data streams checking: (1) freshness via max_staleness threshold → P3_MEDIUM incident, (2) completeness via required_fields → P2_HIGH incident, (3) format via schema validation → P2_HIGH incident.

**Code:** `b10_data_validation.py` validates user-submitted data (entry price, commission, balance) and asset configs. There is zero data feed freshness checking, no staleness timer, no monitoring loop, and no call to `create_incident()` anywhere in the file. The block does not import B9 incident response.

**Impact:** Stale market data, missing feed fields, or corrupted schemas will not be detected until they cause downstream signal errors. The system has no automated data quality defense.

#### G-CMD-004 — B8 Balance Mismatch Not Recorded as Incident

**Spec:** Doc 34 PG-39 step 1: if `abs(broker_balance - system_balance) > reconciliation_threshold`, call `create_incident("RECONCILIATION", "P2_HIGH", "FINANCE", "Balance mismatch for {ac}...")`.

**Code:** `b8_reconciliation.py:109-111` pushes a GUI notification with priority "MEDIUM" and logs the correction, but never calls `create_incident()`. The B9 module is not imported. The mismatch is auto-corrected (broker = source of truth) without creating an auditable incident record in P3-D21.

**Impact:** Balance mismatches — which could indicate unauthorized trades, API errors, or accounting bugs — leave no formal incident trail. ADMIN cannot review historical reconciliation failures.

### Detailed Findings — HIGH (Selected)

#### G-CMD-005 — Hardcoded "primary_user" Breaks Multi-User Isolation

**Code:** `api.py` has 13 instances of hardcoded `"primary_user"` across lines 281, 557, 574, 584, 784, 790, 803, 830, 849, 873, 919, 926, 983. Examples: `api_aim_activate` (line 574) hardcodes `user_id: "primary_user"` instead of reading from JWT `request.state.user_id`; replay endpoints (lines 803, 926) use hardcoded user_id in SQL queries. **Spec (Doc 19 §7):** P3-D16 capital silos must isolate per-user.

#### G-CMD-009/018/019 — Compliance Gate Missing Per-Signal Checks

**Code:** B12 (`b12_compliance_gate.py`) checks 11 RTS6 boolean flags and `AUTO_EXECUTE` env var — a global gate status. B3 (`b3_api_adapter.py:468-471`) delegates to B12. Neither checks `signal.contracts > max_contracts` nor `instrument_permitted(signal.asset)` as spec requires. B4 (`b4_tsm_manager.py:243-246`) caps contracts at `max_contracts` but doesn't reject with the spec-mandated `{approved: False, reason: "EXCEEDS_MAX_CONTRACTS"}` format.

#### G-CMD-012 — SQL Placeholder Syntax Crash in B7 Role Queries

**Code:** `b7_notifications.py:449` builds `$1, $2, ...` PostgreSQL-style positional placeholders, but QuestDB via psycopg2 uses `%s` placeholders (as used everywhere else in the codebase). Any call to `_get_users_by_roles` for non-TRADER roles will raise a database error, meaning ADMIN/DEV/RISK notifications are undeliverable.

#### G-CMD-015 — No Incident Escalation Matrix

**Spec:** Doc 29 §2.4: P1 acknowledged within 5 minutes, P2 within 30 minutes, P3 within 4 hours, P4 next business day. **Code:** B9 creates incidents as OPEN and supports manual resolution, but has no timers, no acknowledgement tracking, no auto-escalation on timeout. Unacknowledged P1 incidents will never auto-notify additional responders.

### S2-Flagged Items Resolution

| S2-ID | Finding | Resolution |
|-------|---------|------------|
| S2-06 | RPT-12 Alpha Decomposition | **GAP CONFIRMED (G-CMD-002 CRITICAL)**: Missing entirely. Only 11 of 12 reports exist. |
| S2-07 | P3-D16 capital_silos per-user isolation | **GAP CONFIRMED (G-CMD-005 HIGH)**: api.py hardcodes "primary_user" in 13 locations; no per-user scoping from JWT. |
| S2-09 | RBAC 6 roles | **GAP CONFIRMED (G-CMD-001 CRITICAL)**: JWT has no roles field; zero enforcement across all endpoints. |
| S2-10 | Quiet hours 22:00-06:00 with CRITICAL override | **VALID**: b7_notifications.py:98-100 defaults 22:00-06:00 local TZ. Line 266 checks `priority != "CRITICAL"` for quiet hours bypass. Correctly implemented. |
| S2-11 | Per-user notification preferences | **VALID**: b7_notifications.py:88-105 includes channel toggles (telegram/email/push), priority threshold, asset filters (allowlist), sound per priority. All spec preference types present. |
| S2-12 | Compliance gate completeness | **GAP CONFIRMED (G-CMD-009/018/019 HIGH)**: B12 checks global flags only; no instrument_permitted or max_contracts per-signal checks. |
| S2-13 | XFA scaling tiers end-of-day | **PARTIAL GAP (G-CMD-013 HIGH)**: B4 has correct 5-tier lookup table; B8 gates evaluation on `topstep_optimisation` instead of `scaling_plan_active`. |
| S2-14 | Payout recommendation logic | **PARTIAL GAP (G-CMD-040 MEDIUM)**: XFA $5k/50% cap and 10% commission implemented; 5 winning days requirement missing for XFA accounts. |
| S2-16 | Health endpoint with 30s monitoring | **MOSTLY VALID (G-CMD-046 MEDIUM)**: 7/7 required fields present; 30s health check schedule confirmed; overall status never returns "HALTED" even when CB is halted. |
| S2-21 | Incident escalation matrix | **GAP CONFIRMED (G-CMD-015 HIGH)**: No escalation timers, acknowledgement tracking, or auto-escalation. |

### Key Validated Areas

**V-CMD-001 | B1 | 6-field sanitisation:** `sanitise_for_api()` returns exactly 6 fields (asset, direction, size, tp, sl, timestamp) via whitelist. PROHIBITED_EXTERNAL_FIELDS constant in `shared/constants.py` matches spec's 9 prohibited fields.

**V-CMD-002 | B1 | 13+ command types handled:** `route_command()` dispatches all spec command types: TAKEN/SKIPPED (combined), ADOPT_STRATEGY, REJECT_STRATEGY, PARALLEL_TRACK, SELECT_TSM, ACTIVATE_AIM, DEACTIVATE_AIM, CONFIRM_ROLL, UPDATE_ACTION_ITEM, TRIGGER_DIAGNOSTIC, MANUAL_PAUSE, MANUAL_RESUME. Plus extensions: CONCENTRATION_PROCEED, CONCENTRATION_PAUSE.

**V-CMD-003 | B1 | Notification logging to D10:** `_log_notification()` inserts to `p3_d10_notification_log`. Telegram routing fires for CRITICAL and HIGH priority.

**V-CMD-004 | B1 | Broadcast to all users:** `route_notification()` calls `_get_all_active_user_ids()` when `user_id` absent, correctly broadcasting system alerts.

**V-CMD-005 | B2 | Payout panel:** `_get_payout_panel()` implements per-account recommended payout with net-after-commission and tier impact, matching Doc 18 §6.

**V-CMD-006 | B2 | 8-dimension diagnostics:** `_get_diagnostic_health()` queries P3-D22 for all 8 system health dimensions per PG-17.

**V-CMD-007 | B2 | Thread-safe snapshot:** `_state_lock` and atomic snapshot pattern protect mutable state for concurrent GUI clients.

**V-CMD-008 | B3 | Adapter interface:** ABC with 5 lifecycle methods (connect, send_signal, receive_fill, get_account_status, disconnect) plus ping. TopstepX concrete adapter with bracket order placement.

**V-CMD-009 | B3 | 30s health check with 3-retry reconnect:** Matches spec's auto-reconnect requirement.

**V-CMD-010 | B3 | 4-field inbound boundary:** balance, equity, drawdown, open_positions — information from broker correctly restricted.

**V-CMD-011 | B4 | TSM validation:** Required fields, classification block, numeric sanity, V3 fee_schedule with per-instrument fees.

**V-CMD-012 | B4 | Scaling tier lookup:** `get_scaling_tier()` implements correct 5-tier balance-threshold lookup matching Doc 25 table.

**V-CMD-013 | B5 | Injection flow end-to-end:** Receives candidate from Offline B4 via D06 query, presents to user via GUI push, captures ADOPT/PARALLEL_TRACK/REJECT, forwards to Offline via Redis CH_COMMANDS.

**V-CMD-014 | B6 | RPT-04 (AIM Effectiveness):** Fully implemented with DMA weights, modifier accuracy, PnL contribution, and days suppressed.

**V-CMD-015 | B6 | RPT-07 (TSM Compliance):** Computes drawdown vs MDD, budget remaining, pass probability.

**V-CMD-016 | B7 | Quiet hours with CRITICAL override:** 22:00-06:00 local TZ, CRITICAL bypasses, queue capped at 50 with FIFO eviction.

**V-CMD-017 | B7 | Per-user preferences:** Channel toggles, priority threshold, asset filters, sound per priority all implemented.

**V-CMD-018 | B7 | Rate limit 60/hr:** Enforced in telegram_bot.py per chat.

**V-CMD-019 | B8 | SOD formulas correct:** f(A)=4500/A, R_eff=(4500p+phi)/A, N=floor(eA/(4500p+phi)), E=eA, L_halt=ceA all match spec.

**V-CMD-020 | B8 | Broker balance as source of truth:** Auto-corrects system balance to match broker on mismatch.

**V-CMD-021 | B8 | Reconciliation logged to D19:** Correct data store write.

**V-CMD-022 | B9 | Incident persistence to D21:** UUID-based ID, severity validation, OPEN status, resolution flow all correct.

**V-CMD-023 | telegram | 7 commands implemented:** /status, /signals, /positions, /reports, /tsm, /mute, /help.

**V-CMD-024 | telegram | Inline TAKEN/SKIPPED buttons:** On signal notifications, callback validation for action type.

**V-CMD-025 | telegram | Security controls:** Chat ID whitelist from D16, bot token from vault, no strategy details in messages, CRITICAL bypasses mute.

**V-CMD-026 | orch | Parity filter:** `_check_parity_skip` correctly implements INSTANCE_PARITY with daily Redis counter and deterministic trade splitting.

**V-CMD-027 | orch | Always-on architecture:** 4 threads (signal reader, Redis listener, log forwarder, scheduler) with exponential backoff.

**V-CMD-028 | api.py | Health endpoint fields:** All 7 required fields present: status, uptime_seconds, last_signal_time, active_users, circuit_breaker, api_connections, last_heartbeat.

**V-CMD-029 | api.py | JWT authentication:** HS256 signing, 24h expiry, middleware validation on all non-exempt paths, WebSocket JWT verification.

**V-CMD-030 | api.py | WebSocket per-user scoping:** Sessions tracked per-user; dashboard pushes per-user.

**V-CMD-031 | api.py | Graceful shutdown:** FastAPI lifespan stops orchestrator and Telegram bot on SIGTERM/SIGINT.

**V-CMD-032 | main.py | Initialization sequence:** QuestDB+Redis verify → TSM load → Telegram bot → chat_id to D16 → TopstepX auth → TSM link → orchestrator thread → uvicorn main thread.

**V-CMD-033 | B12 | RTS6 gate:** All 11 flags checked with fail-safe default to MANUAL mode. AUTO_EXECUTE env var required.

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
| P3-Offline | 52 | ~75 | 3 | 0 | 55 | 5 CRITICAL |
| P3-Online | 49 | ~40 | 8 | 0 | 57 | 3 CRITICAL |
| P3-Command | 65 | ~35 | 3 | 0 | 71 | 4 CRITICAL |
| Shared | — | — | — | — | — | — |
| Cross-Cutting | — | — | — | — | — | — |
| **TOTAL** | — | — | — | — | — | **—** |

**Overall Verdict:** _(Session 6 will determine: READY / NOT READY)_

**BLOCKED Items Requiring Isaac's Input:**

_(Session 6 will list)_
