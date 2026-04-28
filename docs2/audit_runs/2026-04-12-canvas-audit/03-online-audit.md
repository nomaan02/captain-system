# Phase 3: P3-Online Cross-Validation Audit

> **Generated:** 2026-04-12 Phase 3
> **Source:** `00-spec-manifest.md` (P3-Online items) vs `captain-online/` codebase (18 Python files, 7,073 lines)
> **Scope:** Blocks B1-B9, B5B, CB; Programs PG-21 to PG-29, PG-25B, PG-25D, PG-27B; Kelly 7-Layer; CB 5-Layer; 16 AIMs; data stores; feedback loops; signal distribution

---

## COVERAGE SUMMARY

| Category | Spec Items | Implemented | Divergent | Missing | Unspecced |
|----------|-----------|-------------|-----------|---------|-----------|
| Blocks (B1-B9, B5B, CB) | 11 | 11 | 0 | 0 | 4 |
| Programs (PG-21 to PG-29, PG-25B, PG-25D, PG-27B) | 12 | 11 | 0 | 1 | 0 |
| Kelly Layers (L1-L7) | 7 | 7 | 2 | 0 | 0 |
| CB Layers (L0-L4) | 5 | 5 | 0 | 0 | 2 |
| AIM Modules (1-16) | 16 | 11 | 3 | 0 | 0 |
| Data Store Access | 15 | 14 | 1 | 1 | 0 |
| Feedback Loops (Online part) | 5 | 5 | 0 | 0 | 0 |
| Signal Distribution (PG-25D) | 6 steps | 0 | 0 | 6 | 0 |
| Spec Module Names | 20 | 0 | 15 | 5 | 4 |
| **Totals** | **97** | **63** | **21** | **13** | **10** |

**Coverage rate: 63/97 = 65% exact match, 84/97 = 87% functional coverage (including divergent)**

---

## IMPLEMENTED -- Matching Spec (63 items)

### Blocks -- All 11 Present

| Block | Spec Name | Code File | Lines | PG Ref | Scope |
|-------|-----------|-----------|-------|--------|-------|
| B1 | Data Ingestion | `b1_data_ingestion.py` + `b1_features.py` | 851 + 1438 | PG-21 | SHARED |
| B2 | Regime Probability | `b2_regime_probability.py` | 185 | PG-22 | SHARED |
| B3 | AIM Aggregation | `shared/aim_compute.py` | 674 | PG-23 | SHARED |
| B4 | Kelly 7-Layer Sizing | `b4_kelly_sizing.py` | 446 | PG-24 | PER-USER |
| B5 | Trade Selection | `b5_trade_selection.py` | 234 | PG-25 | PER-USER |
| B5B | Quality Gate | `b5b_quality_gate.py` | 171 | PG-25B | PER-USER |
| CB | Circuit Breaker (L0-L4) | `b5c_circuit_breaker.py` | 562 | PG-27B | PER-USER |
| B6 | Signal Output | `b6_signal_output.py` | 359 | PG-26 | PER-USER |
| B7 | Position Monitor | `b7_position_monitor.py` | 517 | PG-27 | PER-USER |
| B8 | Net Concentration | `b8_concentration_monitor.py` | 182 | PG-28 | PER-USER |
| B9 | Capacity Evaluation | `b9_capacity_evaluation.py` + `b9_session_controller.py` | 301 + 150 | PG-29 | PER-USER |

### Programs -- 11 of 12 Present

| PG | Name | Implementation | Notes |
|----|------|---------------|-------|
| PG-21 | Data Ingestion | `b1_data_ingestion.run_data_ingestion()` | 5-check data moderator, concurrent prefetch, roll calendar |
| PG-22 | Regime Probability | `b2_regime_probability.run_regime_probability()` | Binary (C4) + classifier (C1-C3) dual path |
| PG-23 | AIM Aggregation / MoE | `shared/aim_compute.run_aim_aggregation()` | DMA-weighted aggregation (see DIVERGENT) |
| PG-24 | Kelly 7-Layer Sizing | `b4_kelly_sizing.run_kelly_sizing()` | All 7 layers + portfolio risk cap |
| PG-25 | Trade Selection | `b5_trade_selection.run_trade_selection()` | Edge ranking + correlation filter + HMM allocation |
| PG-25B | Quality Gate | `b5b_quality_gate.run_quality_gate()` | Hard floor + graduated ceiling (see DIVERGENT) |
| PG-26 | Signal Output | `b6_signal_output.run_signal_output()` | Signal construction + jitter + Redis Stream publish |
| PG-27 | Position Monitor | `b7_position_monitor.monitor_positions()` | TP/SL monitoring + D03 write + D23 atomic update |
| PG-27B | Circuit Breaker | `b5c_circuit_breaker.run_circuit_breaker_screen()` | All 5 spec layers + 2 post-spec additions |
| PG-28 | Net Concentration | `b8_concentration_monitor.run_concentration_monitor()` | same_dir >= 80% threshold alert |
| PG-29 | Capacity Evaluation | `b9_capacity_evaluation.run_capacity_evaluation()` | Constraint analysis (fill quality absent) |

### Kelly 7-Layer Pipeline -- All 7 Layers Present

| Layer | Spec Name | Code Location | Reads | Status |
|-------|-----------|---------------|-------|--------|
| L1 | Regime-Conditional Kelly | `b4_kelly_sizing.py:107-114` | P3-D12 (kelly_params) | Implemented (merged with L2) |
| L2 | Blended Kelly | `b4_kelly_sizing.py:107-114` | regime_probs from B2 | Implemented (merged with L1) |
| L3 | Parameter Uncertainty Shrinkage | `b4_kelly_sizing.py:116-118` | P3-D12 (shrinkage_factor) | Implemented |
| L4 | Robust Kelly Fallback | `b4_kelly_sizing.py:120-131` | P3-D05 (EWMA moments) | Implemented; formula: `mu/(mu^2+var)` |
| L5 | AIM Modifier | `b4_kelly_sizing.py:133-134` | combined_modifier from B3 | Implemented |
| L6 | Account-Type Adjustment | `b4_kelly_sizing.py:136-141` | P3-D16 (user_kelly_ceiling) | Implemented |
| L7 | TSM Hard Constraints | `b4_kelly_sizing.py:143-250` | P3-D08, P3-D23, fees | Implemented; 4-way min |

### Circuit Breaker Layers -- All 5 Spec Layers Present

| Layer | Spec Name | Code Location | Reads | Condition | Status |
|-------|-----------|---------------|-------|-----------|--------|
| L0 | Scaling Cap | `b5c_circuit_breaker.py:236-260` | TSM scaling_tier_micros | open + proposed > tier | Implemented |
| L1 | Preemptive Halt | `b5c_circuit_breaker.py:263-293` | P3-D23 (L_t), TSM | \|L_t\| + rho_j >= L_halt | Implemented |
| L2 | Budget Check | `b5c_circuit_breaker.py:296-321` | P3-D08 (E), P3-D23 | E - \|L_t\| < rho_j | Implemented |
| L3 | beta_b Expectancy | `b5c_circuit_breaker.py:324-368` | P3-D25 (beta_b) | mu_b = r_bar + beta_b*L_b <= 0 | Implemented; cold-start gates |
| L4 | Correlation Sharpe | `b5c_circuit_breaker.py:371-408` | P3-D03 (60-day returns) | S <= lambda | Implemented |

### AIM Modules -- 11 Fully Implemented

| AIM | Name | Feature Computation | Modifier Logic | Status |
|-----|------|--------------------|--------------------|--------|
| AIM-01 | VRP | `b1_features.py:47-75` (vrp, vrp_overnight, vrp_overnight_z) | `aim_compute.py:251-289` | Implemented |
| AIM-04 | Pre-Market | `b1_features.py:571-602` (ivts, overnight_return_z, is_eia_wednesday) | `aim_compute.py:343-401` | Implemented |
| AIM-06 | Calendar | `b1_features.py:139-189` (events_today, event_proximity) | `aim_compute.py:404-434` | Implemented |
| AIM-08 | Correlation | `b1_features.py:234-248` (correlation_20d, correlation_z) | `aim_compute.py:477-498` | Implemented |
| AIM-09 | Momentum | `b1_features.py:249-273` (cross_momentum) | `aim_compute.py:501-514` | Implemented |
| AIM-10 | Calendar Effect | `b1_features.py:280-298` (is_opex_window, day_of_week) | `aim_compute.py:517-528` | Implemented |
| AIM-12 | Cost Estimator | `b1_features.py:323-331, 692-701` (spread_z, vol_z) | `aim_compute.py:577-617` | Implemented |
| AIM-13 | Sensitivity | Reads Offline B5 state from D01 | `aim_compute.py:620-629` | Implemented |
| AIM-14 | Auto-Expansion | Always 1.0 per spec | `aim_compute.py:632-634` | Implemented |
| AIM-15 | Volume Quality | `b1_features.py:338-356` (opening_volume_ratio) | `aim_compute.py:637-658` | Implemented; Phase A=None, Phase B recomputed post-OR |
| AIM-16 | HMM Opportunity | Reads from D26 (trained offline) | `aim_compute.py:661-673` | Implemented; no live inference |

### Data Store Access -- 14 of 15 Correct

| Store | Expected Access | Code Location | Access Pattern |
|-------|----------------|---------------|----------------|
| P3-D00 | B1 reads asset_universe | `b1_data_ingestion.py:48` | `_load_active_assets()` — QuestDB query |
| P3-D01 | B3 reads AIM states | `b1_data_ingestion.py:99` | `_load_aim_states()` — QuestDB query |
| P3-D02 | B3 reads meta-weights | `b1_data_ingestion.py:136` | `_load_aim_weights()` — QuestDB query |
| P3-D03 | B7 writes trade outcomes | `b7_position_monitor.py:273-297` | `_write_trade_outcome()` — QuestDB insert |
| P3-D05 | B4 reads EWMA states | `b1_data_ingestion.py:164` | `_load_ewma_states()` — QuestDB query |
| P3-D07 | B5 reads correlation matrix | `b5_trade_selection.py:195` | `_load_correlation_matrix()` — QuestDB query |
| P3-D08 | B4/CB reads TSM configs | `b1_data_ingestion.py:226` | `_load_tsm_configs()` — QuestDB query |
| P3-D12 | B4 reads Kelly params | `b1_data_ingestion.py:193` | `_load_kelly_params()` — QuestDB query |
| P3-D16 | B4 reads user profiles | `orchestrator.py:755` | `_load_user_silo()` — QuestDB query |
| P3-D17 | B1/B5B/B9 writes quality log | Multiple locations | System monitor state table |
| P3-D23 | CB reads, B7 writes intraday | `b5c_circuit_breaker.py:482` read, `b7_position_monitor.py:300` write | Atomic read+write pattern |
| P3-D25 | CB L3 reads beta_b params | `b5c_circuit_breaker.py:439` | `_load_cb_params()` — QuestDB query |
| P3-D26 | B3/B5 reads HMM states | `b5_trade_selection.py:217`, `aim_compute.py:175` | `_load_hmm_opportunity_state()` — QuestDB query |
| P2-D07 | B2 reads regime classifier | `b1_data_ingestion.py:310` | `_load_regime_models()` — QuestDB + joblib |

### Feedback Loops -- All 5 Online Participations Correct

| Loop | Online Role | Implementation |
|------|-------------|----------------|
| 1 (AIM Meta-Learning) | B7 on_close -> D03 -> publish | `b7_position_monitor.resolve_position()` writes D03, publishes to `STREAM_TRADE_OUTCOMES` |
| 2 (Decay Detection) | B7 on_close -> D03 -> publish | Same publish triggers Offline BOCPD/CUSUM |
| 3 (Kelly EWMA) | B7 on_close -> D03 -> publish | Same publish triggers Offline EWMA update |
| 4 (beta_b Learning) | B7 on_close -> D03 -> publish | Same publish triggers Offline beta_b fit |
| 5 (Intraday CB State) | B7 on_close -> D23 update | `_update_capital_and_cb()` — atomic l_t, n_t, l_b, n_b update |

### SHARED vs PER-USER Split -- Correct

| Scope | Blocks | Implementation |
|-------|--------|----------------|
| SHARED (once per session) | B1, B2, B3 | `orchestrator._run_session()` L201-280: runs B1-B3 once, stores results |
| PER-USER (per silo) | B4, B5, B5B, CB, B6, B7, B8, B9 | `orchestrator._process_user_sizing()` L516-608: iterates `_get_active_users()` |

### Real-Time vs Batch Boundary -- Correct

Online correctly avoids duplicating Offline work:
- Kelly f* pre-computed offline → Online reads from D12
- EWMA states pre-computed offline → Online reads from D05
- HMM trained offline → Online reads from D26
- BOCPD/CUSUM computed offline → Online reads D04/D25

Online does real-time work only:
- Market data ingestion via TopstepX SignalR WebSocket (`shared/topstep_stream.py`)
- OR tracking from live quotes (`b8_or_tracker.on_quote()` wired to MarketStream callback)
- AIM feature computation from live data (`b1_features.compute_all_features()`)
- Regime classification inference only (`b2_regime_probability._classifier_regime()`)
- Kelly sizing pipeline using offline params (`b4_kelly_sizing.run_kelly_sizing()`)
- TP/SL monitoring from live prices (`b7_position_monitor.monitor_positions()`)

### WebSocket/SignalR Integration Points

| Integration | Code Location | Description |
|-------------|---------------|-------------|
| MarketStream start | `main.py:43-78` | TopstepX SignalR WebSocket, authenticates + subscribes to all contracts |
| Quote callback | `main.py:54` | `MarketStream(on_quote=or_tracker.on_quote)` — wires OR tracker directly |
| Quote cache | `b1_data_ingestion.py`, `b7_position_monitor.py` | `quote_cache` dict holds latest tick per contract_id (sub-second) |
| Quote-to-Redis | `orchestrator.py:162-191` | `_publish_quotes_to_redis()` — HSET with 10s TTL for GUI |
| REST fallback | `b7_position_monitor.py:430-454` | `_get_live_price()` — REST `get_bars()` if cache miss |

---

## DIVERGENT -- Implemented but Differs from Spec (21 items)

### HIGH Severity

| # | Spec Requirement | Implementation | Impact |
|---|-----------------|----------------|--------|
| D-01 | PG-23: MoE softmax(g/tau) gating | DMA-weighted average in `aim_compute.py:109-168`. Aggregation is `sum(modifier * dma_weight) / sum(dma_weight)` — linear weighting, not softmax temperature gating. | Combined modifier may not respond to regime changes as dynamically as intended. MoE with temperature would concentrate weight on best-performing AIMs. |
| D-02 | PG-25B: $/contract floor + ceiling | `b5b_quality_gate.py:43-66`. `quality_score = edge * modifier * data_maturity` — dimensionless, not dollars. Division by `total_contracts` at L64 does not produce a dollar metric. `hard_floor=0.003` and `quality_ceiling=0.010` are edge-modifier units. | Gate threshold semantics differ from spec. A trade with high contracts could pass the gate while delivering low dollar value per contract. |
| D-03 | PG-25: hmm_opp_wt x daily_budget ranking | `b5_trade_selection.py:47-100`. Primary ranking is `edge * max_contracts`, not `hmm_opp_wt * daily_budget`. HMM allocation is a post-processing multiplier via `apply_hmm_session_allocation()` that scales existing contract counts, not a pre-selection ranking. | Trade priority order may differ from spec intent. HMM weights scale down rather than rerank. |
| D-04 | PG-29: fill_quality + slippage metrics | `b9_capacity_evaluation.py` is purely capacity/constraint analysis. No fill quality measurement, no slippage analysis. Slippage is computed in B7 `resolve_position()` but never aggregated or analyzed in B9. | No session-end execution quality feedback. Cannot detect degrading fill quality over time. |
| D-05 | PG-22: regime_probs:{asset} Redis hash | `b2_regime_probability.py` writes nothing to Redis. Returns `{regime_probs, regime_uncertain}` dict in-memory. Orchestrator passes results to B4/B5 directly. | Any process relying on reading `regime_probs:{asset}` from Redis will get stale/missing data. Spec data flow assumes Redis as the transport. |

### MEDIUM Severity

| # | Spec Requirement | Implementation | Impact |
|---|-----------------|----------------|--------|
| D-06 | Spec: 16 individual AIM .py files (aim_01_vrp.py .. aim_16_hmm.py) | All AIM logic consolidated into two files: features in `b1_features.py` (1438 lines), modifiers in `shared/aim_compute.py` (674 lines). No individual AIM module files exist. | Organizational divergence. Makes per-AIM testing, replacement, and deactivation harder. Each AIM's feature computation and modifier logic are co-located across two files. |
| D-07 | Spec: separate `aim_aggregator.py`, `moe_gating.py`, `hmm_inference.py` | All three merged into `shared/aim_compute.py`. No MoE gating module. HMM reads state from D26 (no live inference). | No standalone MoE gating or HMM inference modules. |
| D-08 | Spec: separate `fee_resolver.py` module | Fee resolution inline as `_get_expected_fee()` in `b4_kelly_sizing.py:407-425` and `_resolve_fee()` in `b5c_circuit_breaker.py:516-535`. | Duplicated fee resolution logic across two files — potential for drift. |
| D-09 | Spec: separate `signal_emitter.py` + `anti_copy_jitter.py` | Both merged into `b6_signal_output.py`. Jitter at L268-284 (±30s time, ±1 micro size). | Organizational only. Jitter logic is functional. |
| D-10 | AIM-02 Skew: pcr from options volume | `b1_features.py:77-87`: `compute_put_call_ratio()` calls `_get_options_volume()` which is a `DATA_UNAVAILABLE` stub returning None. PCR permanently None. Only `skew_z` contributes (0.4 weight in modifier at `aim_compute.py:292-327`). | AIM-02 operates at reduced capacity (skew_z only). Missing 0.6-weight PCR component. |
| D-11 | AIM-03 GEX: dealer gamma from option chain | `b1_features.py:106-137`: Full BSM gamma math present (`_compute_bsm_gamma` at L1019). But `_get_option_chain()` at L993 is a `DATA_UNAVAILABLE` stub. `gex` always None. | AIM-03 fully stubbed — returns None, contributes nothing to combined modifier. |
| D-12 | AIM-11: cl_basis = (spot - front) / spot | `b1_features.py:1329-1333`: `_get_cl_spot()` and `_get_cl_front_futures()` both return None stubs. `cl_basis` always None. | CL-specific contango/backwardation signal absent. Other AIM-11 features (vix_z, vix_daily_change_z) work. |
| D-13 | PG-26: Redis pub/sub `captain:signals:{user_id}` | Code uses Redis Stream `STREAM_SIGNALS` ("stream:signals") via `publish_to_stream()` in `b6_signal_output.py:287-303`. | Durable delivery (improvement over pub/sub fire-and-forget). But consumers must use `XREADGROUP` not `SUBSCRIBE`. Consistent across Command consumer. |
| D-14 | Spec: separate `data_moderator.py` | Inline as `_run_data_moderator()` in `b1_data_ingestion.py:387-466`. | Organizational divergence only. |
| D-15 | Kelly L1+L2: separate Regime-Conditional then Blending steps | Merged into single weighted-average loop at `b4_kelly_sizing.py:107-114`. L1 reads per-regime kelly, L2 blends — both in one pass. | Functionally equivalent but not separable for independent testing or override. |
| D-16 | Kelly L3: _get_shrinkage has no session filter | `b4_kelly_sizing.py:281-286` iterates kelly_params for matching asset_id, takes first match regardless of regime or session_id. | Non-deterministic if multiple rows exist for same asset across sessions. |

### LOW Severity

| # | Spec Requirement | Implementation | Impact |
|---|-----------------|----------------|--------|
| D-17 | CB: spec defines 5 layers (L0-L4) | Code has 7 layers (L0-L6). L5=session halt (VIX>50 or 3+ DATA_HOLD), L6=manual override (permanent stub). Docstring at L20-21 notes "L5/L6 are defensive safety layers added post-spec — kept per DEC-03." | Additive only — more conservative. L6 is inert (stub always returns False). |
| D-18 | Spec: `regime_classifier.py` file | Code: `b2_regime_probability.py`. | Name difference only. |
| D-19 | Spec: `concentration.py` file | Code: `b8_concentration_monitor.py`. | Name difference only. |
| D-20 | Spec: `capacity_eval.py` file | Code: `b9_capacity_evaluation.py`. | Name difference only. |
| D-21 | B2: classifier class ordering verification | `b2_regime_probability.py:168`: hardcoded `proba[0]=LOW_VOL, proba[1]=HIGH_VOL`. No verification against stored model's `classes_` attribute. | Would produce swapped regime probabilities if P2-D07 model was trained with different class order. Low risk if P2 pipeline is consistent. |

---

## MISSING -- Spec Item with No Implementation (13 items)

### CRITICAL Severity

| # | Spec Item | Expected Location | Impact |
|---|-----------|-------------------|--------|
| M-01 | PG-25D Signal Distribution: Step 1 Pool Classification | `signal_distributor.py -> classify_pool()` | No multi-user signal routing by pool. All signals go to all users via parity alternation only. |
| M-02 | PG-25D Signal Distribution: Step 2 Merge & Deduplicate | `signal_distributor.py -> merge_and_dedup()` | No instrument permission filtering or signal deduplication. |
| M-03 | PG-25D Signal Distribution: Step 3 Conflict Key Check | `signal_distributor.py (inline)` | No conflict detection for opposing signals to same user. |
| M-04 | PG-25D Signal Distribution: Step 4 Priority Rotation & EV Balancing | `signal_distributor.py -> distribute_signals()` | No priority queue, no rolling 30-day EV balancing across users. |
| M-05 | PG-25D Signal Distribution: Step 5 Broker-Only Bypass | `signal_distributor.py -> append_broker_only()` | No broker-only signal path. |
| M-06 | PG-25D Signal Distribution: Step 6 Assignment Output | `signal_distributor.py -> finalise_distribution()` | No distribution audit trail or P3-D27 writes. |

> **Note:** PG-25D was also flagged as absent in the Phase 1 Command audit. Multi-user deployment currently uses deterministic parity alternation (INSTANCE_PARITY env var) instead of the spec's 6-step distribution pipeline. This is the largest single gap in the Online process.

### HIGH Severity

| # | Spec Item | Expected Location | Impact |
|---|-----------|-------------------|--------|
| M-07 | P3-D27 distribution_state Redis key | `distribution_state` | No priority queue state or rolling_30d_ev for signal distribution. |
| M-08 | P3-D27 distribution_audit QuestDB table | `distribution_audit` writes | No audit trail of signal-to-user assignments. |
| M-09 | `signal_distributor.py` module | Online or Command process | Module does not exist anywhere in the codebase. |
| M-10 | B9 fill_quality metric | `capacity_eval.py` | No execution quality measurement at session end. |
| M-11 | B9 slippage analysis | `capacity_eval.py` | Slippage computed per-trade in B7 but never aggregated or analyzed. |

### MEDIUM Severity

| # | Spec Item | Expected Location | Impact |
|---|-----------|-------------------|--------|
| M-12 | AIM-05 Orderbook (LOB) | `aim_05_orderbook.py` | Spec marks as DEFERRED (stub returns 1.0). No feature computation, no handler in dispatch table. Spec-acknowledged gap. |
| M-13 | `sanitise_for_api()` function | `signal_emitter.py` or `command_router.py` | Signal context is separated into `_context` sub-key at construction time, not stripped via explicit sanitization function. Functionally equivalent but no named function exists. |

---

## UNSPECCED -- In Code but Not in Spec (10 items)

| # | Code Item | Location | Lines | Purpose | Severity |
|---|-----------|----------|-------|---------|----------|
| U-01 | Shadow Monitor | `b7_shadow_monitor.py` | 256 | Tracks theoretical TP/SL outcomes for all B6 signals. Publishes to `STREAM_SIGNAL_OUTCOMES` with `theoretical=True` flag for Offline Category A learning. Multi-instance parity feature. | LOW (additive safety) |
| U-02 | OR Tracker | `b8_or_tracker.py` | 394 | Live Opening Range breakout detection from MarketStream quotes. State machine: WAITING -> FORMING -> COMPLETE -> BREAKOUT_LONG/SHORT or EXPIRED. Wired directly to MarketStream callback. | LOW (critical for ORB strategy) |
| U-03 | Two-Phase Pipeline | `orchestrator.py:201-454` | ~250 | Phase A (B1-B5C) runs at session open. Phase B (B6) deferred per-asset until ORTracker reports breakout. Pending state stored in `_pending_sessions`. | LOW (architectural improvement) |
| U-04 | Session Controller | `b9_session_controller.py` | 150 | Session lifecycle management: open time calculation, asset-session routing, session config loading. Not spec'd as separate module. | LOW (organizational) |
| U-05 | CB L5 Session Halt | `b5c_circuit_breaker.py:411-424` | 14 | VIX > 50.0 OR 3+ DATA_HOLD assets -> BLOCK. Session-level (not per-account). | LOW (additive safety) |
| U-06 | CB L6 Manual Override | `b5c_circuit_breaker.py:427-432` | 6 | Per-account manual halt check. **Permanent stub** — `_check_manual_halt()` always returns False. | LOW (inert) |
| U-07 | Quote-to-Redis Publishing | `orchestrator.py:162-191` | 30 | Publishes live quote snapshots to `captain:quotes` Redis hash with 10s TTL. Consumed by Command GUI. | LOW (GUI feature) |
| U-08 | Category A/B Learning Split | `b7_shadow_monitor.py` + `orchestrator.py` | ~80 | All signals registered as shadows. TAKEN -> shadow removed, real B7 tracks. SKIPPED -> shadow resolves theoretically for Category A only. `theoretical=True` flag prevents Category B consumption. | LOW (multi-instance design) |
| U-09 | Orchestrator-Level CB | `orchestrator.py:701-734` | 34 | Pre-session check: `data_hold >= 3`, `vix > 50`, `manual_halt`. Separate from B5C per-trade CB. | LOW (defense in depth) |
| U-10 | Silo Drawdown Check | `b4_kelly_sizing.py:62-96` | 35 | Step 0 before Kelly pipeline: if `(1 - total/starting) > max_silo_dd` (default 0.30), blocks all sizing with CRITICAL alert. | LOW (risk management) |

---

## DETAILED ANALYSIS

### Kelly 7-Layer Pipeline (PG-24) -- Deep Dive

**Spec formula `f* = (pW - (1-p)L) / W`:** NOT applied in Online B4. The `kelly_full` values are pre-computed by Offline B8 (`kelly_ewma.py`) and stored in P3-D12. Online B4 reads these values and applies the 7-layer pipeline on top. The classical formula appears in the L4 robust fallback as `mu/(mu^2+var)` — the Kelly-optimal fraction under EWMA moments — which is mathematically equivalent for the Bernoulli case.

**L7 4-way min implementation** at `b4_kelly_sizing.py:196-197`:
```
final = min(floor(kelly_contracts), tsm_cap, topstep_daily_cap, scaling_cap)
```
Where:
- `kelly_contracts = account_kelly * account_capital / risk_per_contract_with_fee`
- `risk_per_contract_with_fee = strategy_sl * point_value + expected_fee` (matches spec PG-24 L7)
- `tsm_cap` = min(MDD budget, MLL budget, max_contracts)
- `topstep_daily_cap` = E / (sl * point_value) from SOD reconciliation
- `scaling_cap` = tier_micros - current_open_micros (XFA only)

**Portfolio risk cap** (post-L7) at `b4_kelly_sizing.py:224-233`: total_risk across all accounts vs `max_portfolio_risk_pct * total_capital`. Proportional scale-down if exceeded.

### Circuit Breaker Layer Ordering (PG-27B) -- Deep Dive

Execution order in `_check_all_layers()` at `b5c_circuit_breaker.py:169-229`:

```
L0 (Scaling Cap) → L1 (Preemptive Halt) → L2 (Budget) → L3 (beta_b) → L4 (Sharpe) → L5 (Session) → L6 (Manual)
```

Sequential cascade — first non-None BLOCK stops evaluation. This means:
- L0 fires before L1 for XFA accounts (correct — cheapest check first)
- L3 cold-start gates: `n_obs==0` skips entirely; `p_value > 0.05 OR n_obs < 100` forces `beta_b=0` (significance gate)
- L4 cold-start: `len(returns) < 10` skips entirely
- L5 duplicates orchestrator-level CB check (VIX/DATA_HOLD) — defense in depth
- L6 always passes (stub)

**Non-TopstepX bypass** at L112-113: `if topstep_optimisation == False: skip` — broker_retail/institutional accounts skip the entire CB. This is a significant scope limitation not explicit in spec.

### HMM-16 in the Live Pipeline

**Training:** Offline B1 (PG-01C) trains HMM via hmmlearn GaussianHMM with 60-day Baum-Welch. Writes to P3-D26 (`hmm_states`).

**Online inference path:**
1. `aim_compute.run_aim_aggregation()` at L175-202: loads `p3_d26_hmm_opportunity_state` for `session_budget_weights`
2. `aim_compute._aim16_hmm()` at L661-673: reads `state["current_modifier"]` from D01 AIM states — pre-computed offline, no live Viterbi inference
3. `b5_trade_selection.apply_hmm_session_allocation()` at L137-187: loads `opportunity_weights` from D26, applies session weight multiplier to contract counts

**No live HMM inference occurs in Online.** All HMM outputs are read from offline-computed state. This is architecturally correct — HMM training requires batch data and the Baum-Welch algorithm is not suited for single-tick updates.

### XGBoost Classifier Integration (PG-22, Doc 23)

**Model loading:** `b1_data_ingestion._load_regime_models()` at L310 loads from P2-D07 via QuestDB. The `classifier_object` field contains the serialized model.

**Inference:** `b2_regime_probability._classifier_regime()` at L144-178:
1. Calls `extract_classifier_features()` from `b1_features.py:441` — builds feature vector from B1 output
2. `X = np.array([feature_vector])`
3. `classifier_obj.predict_proba(X)[0]` — uses sklearn-compatible API (XGBoost or LogisticRegression)
4. Returns `{LOW_VOL: proba[0], HIGH_VOL: proba[1]}`

**Features (f1..f14):** The `extract_classifier_features()` function builds the feature vector from the B1 features dict, selecting features listed in `model["classifier_features"]` (from P2-D07). The specific f1-f14 mapping depends on what was trained in P2.

**Fallback chain:**
1. Classifier with probabilities (primary)
2. Regime label from P2-D07 (if classifier fails or features missing)
3. Equal 0.5/0.5 (if no model at all)

### Timezone Inconsistency in OR Tracker

`b8_or_tracker.py` uses `pytz.timezone("America/New_York")` (L33) and raw `datetime.now(_ET)` in `register_asset()` and `on_quote()`. All other Online files use `zoneinfo.ZoneInfo(SYSTEM_TIMEZONE)` via `shared.constants.now_et()`. This is an internal inconsistency but not a functional bug — both resolve to America/New_York.

---

## CROSS-CUTTING OBSERVATIONS

### Architecture Quality

1. **Two-phase OR-gated pipeline** (UNSPECCED U-03) is a strong architectural choice. Phase A runs immediately at session open to pre-compute shared intelligence and per-user sizing. Phase B waits for ORTracker breakout confirmation before emitting signals. This prevents acting on incomplete OR data.

2. **Thread model is minimal:** 2 threads (main session loop + command listener daemon). All position list mutations guarded by `_position_lock`. No thread pools, no async — straightforward synchronous design.

3. **Shadow monitor** (UNSPECCED U-01) enables Category A learning from all signals regardless of TAKEN/SKIPPED status. This is critical for multi-instance deployment where each instance only takes ~50% of signals.

### Known QuestDB Query Patterns

Several files use `ORDER BY ... DESC LIMIT 1` instead of QuestDB's native `LATEST ON ... PARTITION BY` syntax:
- `b5_trade_selection._load_correlation_matrix()` (L195)
- `b5_trade_selection._load_hmm_opportunity_state()` (L217)
- `b9_capacity_evaluation._load_correlation_matrix()` (L200)
- `b1_features._get_atm_implied_vol()` (L819)

These are functionally correct but may have performance implications on large tables.

### Data Unavailability Stubs

Three AIM modules have feature computation code but are permanently inactive due to TopstepX being a futures-only broker (no options data):
- **AIM-02**: `_get_options_volume()` stub → pcr always None
- **AIM-03**: `_get_option_chain()` stub → gex always None
- **AIM-11**: `_get_cl_spot()`, `_get_cl_front_futures()` stubs → cl_basis always None

These are data availability limitations, not code gaps. The computation logic is fully implemented and would activate if data sources were connected.

### Comparison with Phase 1 + Phase 2 Findings

| Gap | Phase 1 (Command) | Phase 2 (Offline) | Phase 3 (Online) |
|-----|-------------------|-------------------|------------------|
| PG-25D Signal Distribution | CRITICAL — absent | N/A | CRITICAL — absent (confirmed cross-process) |
| P3-D07 DCC-GARCH | N/A | MISSING (static z-score instead) | Reads D07 but data is static z-score not DCC-GARCH |
| AIM-07 COT | N/A | Disabled (DEC-08) | Disabled — stubs return None |
| AIM-05 Orderbook | N/A | DEFERRED per spec | DEFERRED — no handler in dispatch |

---

## FILE INVENTORY

| File | Lines | Role | Spec Module Match |
|------|-------|------|-------------------|
| `orchestrator.py` | 864 | Session pipeline, 2-phase OR-gated execution | `session_evaluator.py` (partial) |
| `main.py` | 150 | Startup, MarketStream init, signal handlers | -- |
| `b1_data_ingestion.py` | 851 | Data loading, quality moderation, prefetch | `data_ingestion.py` + `data_moderator.py` |
| `b1_features.py` | 1438 | AIM feature computation for 16 modules | `aim_feature_compute.py` + `aim_01..aim_16.py` (features only) |
| `b2_regime_probability.py` | 185 | Regime classifier inference | `regime_classifier.py` |
| `b4_kelly_sizing.py` | 446 | Kelly 7-layer sizing pipeline + fee resolution | `kelly_pipeline.py` + `fee_resolver.py` |
| `b5_trade_selection.py` | 234 | Edge ranking, correlation filter, HMM allocation | `trade_selector.py` |
| `b5b_quality_gate.py` | 171 | Quality floor/ceiling gate | `quality_gate.py` |
| `b5c_circuit_breaker.py` | 562 | 7-layer CB (5 spec + 2 post-spec) | `circuit_breaker.py` |
| `b6_signal_output.py` | 359 | Signal construction, jitter, publish | `signal_emitter.py` + `anti_copy_jitter.py` |
| `b7_position_monitor.py` | 517 | Live TP/SL monitoring, trade outcome writing | `position_monitor.py` |
| `b7_shadow_monitor.py` | 256 | Theoretical outcome tracking | -- (UNSPECCED) |
| `b8_concentration_monitor.py` | 182 | Directional concentration alert | `concentration.py` |
| `b8_or_tracker.py` | 394 | Live OR breakout detection | -- (UNSPECCED) |
| `b9_capacity_evaluation.py` | 301 | Capacity constraint analysis | `capacity_eval.py` |
| `b9_session_controller.py` | 150 | Session lifecycle management | -- (UNSPECCED) |
| `shared/aim_compute.py` | 674 | AIM modifier logic + aggregation | `aim_aggregator.py` + `moe_gating.py` + `hmm_inference.py` + `aim_01..aim_16.py` (modifiers only) |
| `shared/aim_feature_loader.py` | 462 | Replay feature loading from DB | -- (UNSPECCED, replay/testing utility) |
| **Total** | **7,196** | | |
