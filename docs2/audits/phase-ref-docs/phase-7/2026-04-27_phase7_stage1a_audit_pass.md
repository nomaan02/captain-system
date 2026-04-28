---
title: Phase 7 — Stage 1A Audit Pass (read-only)
date: 2026-04-27
phase: 7
stage: 1A
companion_to:
  - 2026-04-22_offline_spec_vs_code_audit copy.md
  - phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md
status: PROPOSED — awaiting "approved, continue" before Stage 1B (design doc)
purpose: Pre-design read-only audit covering Captain Online B1–B6 shapes, current pseudotrader/injection/auto-expansion call sites, D03 realised P&L source, deprecated replay engines, and pending §3.2 re-asks affecting Phase 7.
---

# Phase 7 Stage 1A — Audit Pass

This is the **fact-gathering** pass that precedes the Phase 7 design doc. No code is changed; no design choices are made. Every claim below cites a file path and (where applicable) a line range. Items flagged as ambiguous or in conflict are listed in §8 as open design questions for Stage 1B to resolve.

Phase 7 scope: **PG-09 / PG-10 / PG-13 pseudotrader chain** plus the cross-cutting requirement (Q-14) to build a real `captain_online_replay` driven by the live online B1–B6 modules.

---

## 1. Audit findings F-22 through F-29 (Phase 7 scope)

Source: `docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md`. Severity tags are verbatim from that file. "Resolution status" reflects what the decisions log §2 has committed to.

| F-ID | Severity | Title | Code today | Spec / decision requires | Decision status |
|---|---|---|---|---|---|
| **F-22** | HIGH | G-OFF-016 marked RESOLVED but pseudotrader gate doesn't run `captain_online_replay` per day | `b3_pseudotrader.py:957–1031` (`run_signal_replay_comparison` — relies on `SignalReplayEngine` precomputed daily P&L) wired through `orchestrator.py:79–87` | `signal = captain_online_replay(d, using=CURRENT_parameters)` rerunning real online B1–B6 against historical bars (doc 32 PG-09 Phase 1–2) | **Q-14 committed** (decisions §2 Group C, §5 Phase 7): build `captain_online_replay` for real; `SignalReplayEngine` does not satisfy G-OFF-016 |
| **F-23** | HIGH | PG-09 Sharpe / PBO / DSR computed from replay P&L; ignore `actual_trade_outcome(d)` | `b3_pseudotrader.py:688–715, 846–867` — D03 used to discover dates only; metrics computed from synthesised replay P&L | `outcome = actual_trade_outcome(d)` = strict realised P&L from D03 paired with the signal that produced the trade | **Q-15 committed** (decisions §2 Group C): realised P&L from D03; replay synthesis not acceptable |
| **F-24** | HIGH | PG-10 Step 1 retroactive AIM replay not implemented; edges use scalar heuristic | `b4_injection.py:46–65, 125–129` — `expected = mean(historical_pnl) * mean_modifier`; AIM modifiers are aggregate, not per-AIM retroactive | `retroactive_modifiers[a] = aim_retroactive_replay(a, new_candidate, historical_window)` per active AIM | Audit "Needs Isaac: NO" — implement per spec |
| **F-25** | HIGH | PG-10 Step 3 always uses precomputed-P&L branch; `pseudotrader_compare` never reruns the strategies | `b4_injection.py:131–134` always passes `baseline_pnl`/`proposed_pnl` to `b3_pseudotrader.run_pseudotrader` (`b3_pseudotrader.py:816–873`) | `pseudotrader_compare(new_candidate, current_strategy, historical_window)` — internal re-run of both strategies on aligned data | Audit "Needs Isaac: NO" |
| **F-26** | HIGH | PG-13 candidate handoff uses identical `holdout_returns` for every viable candidate | `b6_auto_expansion.py:324–374, 367–374` — per-candidate `oos = _candidate_oos_returns(...)` computed but **ignored**; `run_injection_comparison` invoked with `candidate_pnl=holdout_returns` (same series for all) | Each viable candidate compared via PG-10 with its own `oos` plus baseline replay series for `current_strategy` on the same window | Audit "Needs Isaac: NO" |
| **F-27** | HIGH | PG-12 PBO computed on single best-grid cell, not full perturbation set | `b5_sensitivity.py:214–216` selects max-Sharpe cell and runs PBO on that single cell only | `compute_CSCV_PBO(results, S=8)` over the full perturbation grid (Q-16 confirms `S=8`, doc 32 line 470) | **Q-16 resolved by spec** (decisions §2 "Resolved-by-spec"): full grid, S=8 |
| **F-28** | HIGH | PG-13 final DSR uses validation-window Sharpe, not OOS Sharpe | `b6_auto_expansion.py:324–328` calls `_compute_dsr(candidate.fitness, ...)` — fitness is the 70/30-tail validation Sharpe from `_evaluate_candidate` | DSR computed from holdout `oos_result.sharpe`; threshold `dsr > 0.5` | Audit "Needs Isaac: NO" |
| **F-29** | HIGH | PG-13 walk-forward train window unused; GA fitness uses single 70/30 split | `b6_auto_expansion.py:276–289` never passes `historical_returns[:split_idx]`; every fitness evaluated on validation-window tail only | Explicit train + validate windows with rolling folds (`walk_forward_train` / `walk_forward_validate`) | Audit "Needs Isaac: NO" |

### G-OFF-015 / G-OFF-016 status

`docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` Audit Resolutions (lines 794–795) marks both as `CRITICAL RESOLVED`:

```
- G-OFF-015 — Pseudotrader Unwired from Orchestrator (PG-09) — CRITICAL RESOLVED
- G-OFF-016 — No Pipeline Replay in Pseudotrader (PG-09 §1-2) — CRITICAL RESOLVED
```

Both markers are **stale** per F-22:
- **G-OFF-015** is functionally resolved (`orchestrator.py:79` does call into the pseudotrader gate).
- **G-OFF-016** is **not** resolved — the gate calls `SignalReplayEngine` precomputed P&L, not `captain_online_replay` driven by live B1–B6.

Phase 7 must satisfy G-OFF-016 in fact, not just on paper.

---

## 2. Captain Online B1–B6 module shapes

Files in `captain-online/captain_online/blocks/`. All entry points are pure-ish Python functions returning dicts; the orchestrator chains them per session. No block writes to D01/D02/D05/D08/D12 — those are read-only from offline state, which is the property that makes a headless replay tractable (per online spec lines 28–31).

| Block | File | Entry point (signature) | External I/O | Time deps | Replay-injection seam |
|---|---|---|---|---|---|
| **B1** | `b1_data_ingestion.py` (delegates to `b1_features.py`) | `run_data_ingestion(session_id: int) → dict\|None` (L778–856) — returns `{active_assets, assets_detail, features, aim_states, aim_weights, ewma_states, kelly_params, sizing_overrides, tsm_configs, locked_strategies, regime_models, session_id}` | QuestDB reads: D00, D01, D02, D05, D12, D08, D17 (L48–350); TopstepX REST `get_bars()` (L526–602); stream `quote_cache`; file: `data/economic_calendar.json`; ThreadPoolExecutor for parallel prefetch (L357–383) | `now_et()` for staleness gates (`_has_valid_timestamp` L640–673); `_assert_system_timezone()` blocks if not America/New_York | All TopstepX/quote-cache reads are concentrated in B1 + `b1_features.py`. Replay must mock these without touching B2–B6. |
| **B2** | `b2_regime_probability.py` | `run_regime_probability(active_assets, features, regime_models) → {regime_probs, regime_uncertain}` (L30–92) | None (pure compute over inputs) | `_compute_realised_vol` may call `now_et()` (L132–154) | Pure-function block; replay reuses verbatim. |
| **B3 (online)** | `shared/aim_compute.py` (`run_aim_aggregation(...)` invoked from `orchestrator.py`) — there is no `b3_*.py` file in online; aggregation lives in `shared/aim_compute.py` | `run_aim_aggregation(active_assets, features, aim_states, aim_weights) → {aim_breakdown, combined_modifier}` | Reads P3-D26 only when HMM active | None directly | Pure compute over inputs. |
| **B4** | `b4_kelly_sizing.py` | `run_kelly_sizing(active_assets, regime_probs, regime_uncertain, combined_modifier, kelly_params, ewma_states, tsm_configs, sizing_overrides, user_silo, locked_strategies, assets_detail, session_id) → dict\|None` (L45–267) | QuestDB read: D17 system params (L454–470); Redis publish: `CH_ALERTS` on silo drawdown (L63–74) | `now_et()` for alert timestamp only | Stateless; replay supplies `user_silo`. |
| **B5** | `b5_trade_selection.py` | `run_trade_selection(active_assets, final_contracts, account_recommendation, account_skip_reason, ewma_states, regime_probs, user_silo, session_id) → dict` (L31–130) | QuestDB read: P3-D26 HMM state (L217–232); correlation matrix (L195–205) | None | Mutates `final_contracts` / `account_recommendation` dicts in place. |
| **B5B** | `b5b_quality_gate.py` | `run_quality_gate(selected_trades, expected_edge, combined_modifier, regime_probs, user_silo, session_id, final_contracts=None) → dict` (L28–112) | QuestDB read: D17 thresholds, D03 trade count (L119–145) | None | Stateless. |
| **B5C** | `b5c_circuit_breaker.py` | `run_circuit_breaker_screen(recommended_trades, final_contracts, account_recommendation, account_skip_reason, accounts, tsm_configs, session_id, ...) → dict` (L49–177) | QuestDB read: D17, D23, D03 rolling Sharpe; VIX provider (CSV); D00 DATA_HOLD count | Module-level `_seen` set deduping intra-session D23 writes (L2017) — **carry across replay sessions risks contamination** | Layer 6 manual halt (L477–482) is a stub returning False. |
| **B6** | `b6_signal_output.py` | `run_signal_output(recommended_trades, available_not_recommended, quality_results, final_contracts, account_recommendation, account_skip_reason, features, ewma_states, aim_breakdown, combined_modifier, regime_probs, expected_edge, locked_strategies, tsm_configs, user_silo, assets_detail, session_id) → dict` (L39–194) | Redis publish: `STREAM_SIGNALS` with 3-attempt retry (L332–360); `CH_ALERTS` on publish failure | `datetime.now(ZoneInfo("America/New_York"))` per signal (L86); UUID per signal (L84) | **Live signal publication must be disabled in replay.** Either skip publish or route to a replay-only sink. |
| **Orch** | `orchestrator.py` | `OnlineOrchestrator._run_session(session_id)` (L239–384) and `_check_or_breakouts()` (L386–492) | Spawns daemon `_command_listener` thread (L834–859); 1-second `_session_loop` (L156–198); position monitor every tick (L172–174); heartbeat to `CH_STATUS` (L139–154) | Hardcoded `SESSION_IDS` from `shared/constants.py`; `_session_evaluated_today` per-day re-entry guard | Two-phase pipeline: Phase A (B1–B5C) shared once per session; Phase B (B6) deferred until OR breakout. Replay must invoke a headless equivalent (no daemon thread, no 1-second tick) — likely an `OnlineReplaySession` class or a pure function reusing the same B1→B5C→B6 wiring. |

**Key facts for the design pass:**

1. **B1 is the only block with non-trivial external I/O.** B2–B6 are essentially pure functions over the dict B1 produces. If B1's external reads are made injection-friendly, the rest of the chain is replayable verbatim.
2. **B5C carries module-level state** (`_seen` deduplication around D23 writes). Replay must reset this between sessions or skip the dedup guard entirely.
3. **B6 publishes to Redis.** Replay must disable the publish or redirect it.
4. **AIM-15 is recomputed in Phase B** (orchestrator L494–557) post-OR. Whether replay runs Phase B at all is an open design question (§8.6).
5. **B7–B9 are out of scope.** Position monitoring, concentration, and capacity blocks read live position state (D23/D16) and are not part of the PG-09 replay surface.

---

## 3. Pseudotrader / injection / auto-expansion call sites

Files in `captain-offline/captain_offline/blocks/`.

### 3.1 `b3_pseudotrader.py` (PG-09)

| Function | Lines | Role |
|---|---|---|
| `fetch_d03_trade_outcomes(...)` | 688–715 | Loads D03 rows for user/asset/date range (date discovery only today) |
| `captain_online_replay(...)` | 718–777 | **Wrapper** that calls `shared.replay_engine.run_replay()` and `run_whatif()` against a cached bar set. **Per Q-14 this is the spec function name; the implementation underneath must be rebuilt to call live online B1–B6, not the parallel logic in `replay_engine.py`.** |
| `run_pseudotrader(...)` | 780–934 | Primary entry. Falls back to direct P&L comparison if `baseline_pnl`/`proposed_pnl` are passed. |
| `run_signal_replay_comparison(...)` | 937–1038 | Spec-named entry for PG-09 Phase 1–2 — **today uses `SignalReplayEngine`, must be rewired to `captain_online_replay`** |
| `run_cb_pseudotrader(...)` | 1041–1332 | 4-layer CB validation (out of Phase 7 scope; informational) |
| `run_cb_grid_search(...)` | 1335–1390 | Grid search over (c, λ) (out of Phase 7 scope; informational) |
| `run_multistage_replay(...)` | 1393–1525 | EVAL→XFA→LIVE simulation (out of Phase 7 scope; informational) |
| `generate_forecast(...)` | 1651–1892 | Comprehensive metrics + system-state snapshot to D27 |
| `generate_dual_forecasts(...)` | 1927–2009 | Forecast A (full history) + Forecast B (rolling 252-day) |

### 3.2 `b4_injection.py` (PG-10 / PG-11)

| Function / class | Lines | Role |
|---|---|---|
| `_compute_aim_adjusted_edge(...)` | 46–65 | **F-24** — scalar heuristic, must become per-AIM retroactive replay |
| `_load_aim_weights(...)` | 68–81 | Reads P3-D02 inclusion probabilities |
| `_store_injection(...)` | 84–106 | Persists to `p3_d06a_injection_decisions` |
| `run_injection_comparison(...)` | 109–169 | Main PG-10 entry. **F-25** — always passes precomputed P&L; **F-26 caller** — receives identical `holdout_returns` per candidate |
| `TransitionPhaser` | 172–308 | PG-11 ramp; `blend_signal()` (L207–231) is **unwired** (F-04 out of Phase 7 scope, but on the critical path through PG-11). Phase 6 / Phase 4 batch may handle. |

### 3.3 `b6_auto_expansion.py` (PG-13)

| Function | Lines | Role |
|---|---|---|
| `_random_candidate(...)` | 72–80 | GA seed |
| `_crossover(...)` / `_mutate(...)` / `_tournament_select(...)` | 83–114 | GA primitives |
| `_evaluate_candidate(...)` | 117–205 | **F-29** — every fitness uses 70/30-tail validation only; train window unused |
| `_compute_pbo(...)` / `_compute_dsr(...)` | 208–217 | Delegate to `shared.statistics` |
| `_candidate_oos_returns(...)` | 220–261 | Per-candidate OOS replay — **F-26** the result is computed but discarded |
| `run_auto_expansion(...)` | 264–380 | Main PG-13 entry. **F-28** — DSR built from `candidate.fitness` (validation Sharpe) instead of OOS Sharpe; **F-26** — passes identical `holdout_returns` to `run_injection_comparison` for every viable candidate |

### 3.4 Orchestrator wiring (`captain-offline/.../orchestrator.py`)

| Site | Calls |
|---|---|
| L62–127 (`_pseudotrader_gate`) | `run_signal_replay_comparison()` (L79) |
| L252, L294, L348, L384 | Trade/signal outcome handlers → pseudotrader gate |
| L414, L438–451, L468–514 | `_handle_injection`, `_handle_aim_activation`, GUI activation, transition resume |
| L694, L744–766 | Level-3 dispatch → `run_auto_expansion(training, holdout)` |

All three blocks (B3/B4/B6) are wired to the orchestrator today. Phase 7 is **rewiring + rebuilding** the chain, not first-time wiring.

---

## 4. D03 schema and realised P&L source

Source: `shared/canonical_schemas.py:398–427`. Table `p3_d03_trade_outcome_log`, partitioned by day, dedup on `ts`. **23 columns** (after Phase 1's `model_m INT` addition):

```
trade_id STRING, user_id SYMBOL, account_id SYMBOL, asset SYMBOL,
direction INT, entry_price DOUBLE, signal_entry_price DOUBLE, exit_price DOUBLE,
contracts INT, gross_pnl DOUBLE, commission DOUBLE, pnl DOUBLE,
slippage DOUBLE, outcome STRING, entry_time TIMESTAMP, exit_time TIMESTAMP,
regime_at_entry STRING, aim_modifier_at_entry DOUBLE, aim_breakdown_at_entry STRING,
session INT, tsm_used STRING, model_m INT, ts TIMESTAMP
```

Realised-P&L columns per Q-15: **`gross_pnl`** (pre-commission), **`pnl`** (net). Both are populated from broker fill outcomes; D03 does not store theoretical P&L.

### 4.1 Writers

| File:line | Path of `gross_pnl` / `pnl` |
|---|---|
| `captain-online/captain_online/blocks/b7_position_monitor.py:303–316` (`_write_trade_outcome`) | Live: `gross_pnl = (exit − entry) × contracts × direction`; `commission = get_commission_from_tsm()` (L251–270); `pnl = gross_pnl − commission`. |
| `scripts/paper_trader.py:393–404` (`_log_trade_open`) | Stub at open; P&L not yet known. |
| `scripts/paper_trader.py:416–433` (`_log_trade_close`) | Backtest: `gross_pnl = round(net_pnl + commission, 2)`, `pnl = round(net_pnl, 2)`. |
| `shared/trade_source.py:295–314` (`seed_d03_from_synthetic`) | Synthetic seed: `gross_pnl = pnl = trade["pnl"]` (no slippage/commission split). |

### 4.2 Readers (15+ sites)

Confirmed reader sites (selection): `b3_pseudotrader.py:708–711`, `b8_cb_params.py:46–50`, `b6_signal_output.py:387–391`, `b1_aim_lifecycle.py:154–157`, `orchestrator.py:607–611` (offline), `b5c_circuit_breaker.py:558`, `b6_reports.py:155, 237, 415, 469, 500, 541` (command), `b2_gui_data_server.py:355, 804`, `telegram_bot.py:112, 162`.

### 4.3 Critical gap — no signal_id linkage

**No D03 column ties a row back to the originating signal.** Existing readers either aggregate (Sharpe/DD/winrate over a date window) or fetch raw P&L sequences for detector calibration. None reconstruct `{signal, outcome}` pairs.

Spec PG-09 (doc 32 line 357) requires `baseline_results.append({signal, outcome})` where `outcome = actual_trade_outcome(d)` from D03. This requires either:

- (a) adding `signal_id STRING` to D03 and back-filling/forward-filling it from B6's signal envelope through to B7's writer, or
- (b) adopting a join key built from `(user_id, account_id, asset, entry_time, direction)` if signals can be uniquely matched on that tuple, or
- (c) building a separate `p3_d17_signal_execution_log` table that maps signal_id ↔ trade_id.

This is the **single largest schema gap** for Phase 7 and is **not covered by Phase 1's schema migrations** (Phase 1 added only `model_m` to D03 and `last_p1p2_rerun_ts` to D22). It is an open design question for Stage 1B (§8.1).

---

## 5. Existing replay engines — what must NOT be reused

### 5.1 `shared/signal_replay.py` — **MUST DEPRECATE per Q-14**

| Surface | Lines | Notes |
|---|---|---|
| `class SignalReplayEngine` | 68–517 | Class-based; replays B2–B5 only (no B1, no B6) |
| `SignalReplayEngine.sizing_replay(...)` | 84–207 | Re-sizes historical trades under new Kelly params |
| `SignalReplayEngine.strategy_replay(...)` | 213–364 | Replays historical dates under new SL/TP/feature thresholds |
| `SignalReplayEngine.load_replay_context(...)` | 434–517 | Loads trade data via `shared.trade_source` |

**Callers to retire/redirect (per Q-14):**

- `b3_pseudotrader.py:957–969` — `run_signal_replay_comparison` uses `engine.strategy_replay()`. Phase 7 rewires this to `captain_online_replay`.
- `b5_sensitivity.py:95–128, 178–179` — parameter perturbation. **Out of Phase 7 scope** but should be flagged for Phase 12 hygiene cleanup.
- `b6_auto_expansion.py:135–151, 228–240` — GA fitness via `strategy_replay()`. **In Phase 7 scope (F-28, F-29)** — must rewire to live B1–B6 driver.

### 5.2 `shared/replay_engine.py` — **PARTIALLY REUSABLE if refactored**

| Surface | Lines | Notes |
|---|---|---|
| `load_replay_config(...)` | 58–382 | Loads 9 QuestDB tables — useful pattern for replay state hydration |
| `run_replay(...)` | 1485–1879 | **Parallel B1–B6 implementation** — duplicates B2/B4/B5 logic instead of importing live blocks |
| `run_whatif(...)` | 1886–2071 | Cached-bar what-if rerun |
| `simulate_orb(...)` | 556–770 | OR simulation — duplicates B1 OR-tracker logic |
| `_compute_regime_probs(...)` | 777–816 | Duplicates B2 |
| `compute_contracts(...)` | 889–1167 | Duplicates B4's 7-layer pipeline |
| `_apply_quality_gate(...)`, `_apply_correlation_filter(...)`, `_apply_portfolio_risk_cap(...)` | 1255–1438 | Duplicate B5/B5B |

**Status under Q-14:** the *function name* `captain_online_replay` is correct (`b3_pseudotrader.py:718–777`), but its *implementation* delegates to `replay_engine.run_replay()`, which is a parallel pipeline that does **not** call live B1–B6. Q-14's "real online B1–B6" requirement is **not** satisfied here. Phase 7 must either:

- rebuild `captain_online_replay` to import and invoke `captain_online.blocks.b1_data_ingestion.run_data_ingestion(...)` (and so on) directly, with substituted bar/quote inputs, **or**
- rebuild `replay_engine.run_replay` to be a thin orchestrator over the live blocks rather than a parallel implementation.

The first option is cleaner and is the implied direction in Q-14. The second preserves the existing GUI replay flow (`b11_replay_runner.py`) but risks regressions.

### 5.3 `shared/bar_cache.py` — **REUSABLE AS-IS**

Pure infrastructure (SQLite WAL cache for TopstepX 1-min bars; L1–129). Used only by `replay_engine.fetch_session_bars()` (L525, L543). No business logic, no audit findings. Keep.

### 5.4 What "deprecate" looks like in practice

Phase 7 implementation plan (Pass 2) should treat `SignalReplayEngine` as **frozen** — no new callers, existing callers migrated to the new replay harness, and the class itself either deleted or reduced to a deprecation stub. `replay_engine.py`'s parallel B-block logic should be deleted in favour of imports from `captain-online`.

---

## 6. §3.2 pending re-asks affecting Phase 7

From `phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md` §3.2 (lines 180–198). Of the six pending re-asks, only one touches Phase 7.

| Q-ID | F-ID | Touches Phase 7? | Effect on plan |
|---|---|---|---|
| **Q-04** | F-04 (`blend_signal` consumer) | **Indirect** — PG-10 produces ADOPT decisions that PG-11 acts on. PG-11's `blend_signal` consumer (Online B6) is unresolved. Phase 7 builds and tests PG-09/PG-10/PG-13; PG-11's blend wiring is owned by Phase 4 / persistence-contracts work. | If Q-04 is still open when Pass 2 is authored, Phase 7's PG-10 batches stay green — PG-10 only outputs the recommendation; downstream PG-11 wiring is a separate phase. **Flag, do not block.** |
| Q-11 | F-16 (D26 dual-write boundary) | No (Phase 10 / HMM scope). | — |
| Q-22 | F-38 (AIM-01 VRP) | No (Phase 6). | — |
| Q-23 | F-40 (AIM-04 EIA Wed) | No (Phase 6). | — |
| Q-26 | F-44 (suppression event log) | No (Phase 4). | — |
| Q-27 | F-45 (`raw_data_count` for AIMs 1–15) | No (Phase 4). | — |

**Soft flags (§3.3):** none touch Phase 7.

**Engineering calls (§3.1):**
- Q-10 (TVTP) — Phase 10. Not relevant.
- Q-30 (DEPS) — Phase 6 / Phase 12. Not relevant.
- Q-36 (per-AIM module split) — Phase 12. Not relevant.

**Net:** Phase 7 is **not blocked** by any §3.2 / §3.1 item. Q-04 is a watch item that affects PG-11 chaining downstream of Phase 7's deliverables.

---

## 7. Resolution of `aim_retroactive_replay` (F-24)

`aim_retroactive_replay(a, new_candidate, historical_window)` is **not implemented** anywhere in the repo. Doc 32 PG-10 Step 1 references it as if it exists; no spec doc defines the signature. Phase 7 must define it.

Plausible shape (to be confirmed in Stage 1B):

```python
def aim_retroactive_replay(aim_id: int, candidate_strategy: dict, historical_window: tuple[date, date]) -> dict:
    """For each session day in historical_window, recompute AIM `aim_id`'s modifier
    against `candidate_strategy`'s feature inputs (using historical features from
    QuestDB) and return a per-day modifier series."""
```

This shares a lot of plumbing with the replay harness (it needs the same historical-feature loader). The design doc should consider whether `aim_retroactive_replay` is built as a side-output of the replay run, or as a standalone function reusing `shared/aim_compute.py`.

---

## 8. Open design questions for Stage 1B

These are the design choices Stage 1B must resolve before Pass 2 can be written.

1. **D03 ↔ signal_id join (§4.3).** Add `signal_id STRING` column to D03 (Phase 1.5 amendment), build a separate `signal_execution_log` table, or use a tuple key? **Largest open question.** Affects schema, B6 writer, B7 writer, paper_trader, synthetic seeder, and every D03 reader that needs signal context.
2. **`captain_online_replay` driver shape.** Headless function (`replay_session(date, params) → signals`), class (`OnlineReplaySession`), or async coroutine? Must avoid the 1-second `_session_loop` and the daemon command listener.
3. **B1 substitution seam.** Where is the cleanest injection point for historical bars and synthetic quotes? Options: (a) parameterise B1's TopstepX/quote-cache reads through an abstract data provider, (b) monkey-patch in replay tests, (c) introduce a `replay_mode=True` flag on `run_data_ingestion`. Option (a) is the cleanest but largest refactor.
4. **Module-level state contamination.** B5C's `_seen` dedup set (L2017) and any cached state in `shared/aim_compute.py` need explicit reset hooks or per-replay isolation.
5. **B6 publish disablement.** Inject a no-op publisher, or skip publish entirely in replay? Either way, signals must be returned to the harness, not lost.
6. **Phase B (OR-tracker) replay.** Does replay run the deferred Phase B (OR breakout → AIM-15 recompute → B6) per session day, or does it short-circuit to a synchronous B1→B6 chain? Implications for AIM-15 fidelity.
7. **D26 / HMM state in replay.** PG-23 reads HMM state. For a historical replay day, what HMM state do we use — frozen-as-of-`d`, or current? Q-15's "strict realised P&L" rule implies frozen-as-of-`d`, but no historical D26 snapshots exist. Open question for HMM-active replays.
8. **Multi-user fan-out.** B4–B6 are per-user. Does PG-09 replay run for one user (whose strategies are being tested), or fan out to all users? The decisions log assumes single user; clarify with Nomaan.
9. **`SignalReplayEngine` deletion vs deprecation.** Hard-delete once callers migrated, or keep a stub for one release? Phase 7's risk profile is high enough that a stub period seems prudent.
10. **`replay_engine.py` refactor scope.** Refactor in place (replace parallel logic with live-block calls) or build a new `online_replay.py` driver and retire `replay_engine.py` over time? The GUI replay path (`b11_replay_runner.py`) constrains the answer.
11. **`aim_retroactive_replay` shape.** Standalone function or harness side-output (§7)?
12. **Schema authority for the new replay-decision log.** PG-09 writes to P3-D11; PG-10 writes to P3-D06. Both columns in `canonical_schemas.py` should be re-checked against the metric set the decisions log mandates (Sharpe / PBO / DSR computed from D03).

---

## 9. Sources, confidence, gaps

### Sources consulted

- `docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md` — F-22…F-29 entries, Audit Resolutions section
- `docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md` — §2 Group C, §3.2, §5 Phase 7 row
- `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` — PG-09 (L337–378), PG-10 (L385–413), PG-11 (L416–442), PG-13 (L498–541), Audit Resolutions (L794–795)
- `docs2/spec-docs-02/online/33_P3_Online_Full_Pseudocode 1.md` — PG-21…PG-26 high-level structure (L28–407)
- `docs2/spec-docs-02/offline/P3 Offline copy.md` — block wiring
- `shared/canonical_schemas.py:398–427` — D03 schema
- `shared/signal_replay.py` (full file)
- `shared/replay_engine.py` (full file, focus on L58–382, L1485–2071)
- `shared/bar_cache.py` (full file)
- `captain-online/captain_online/blocks/{b1_data_ingestion,b1_features,b2_regime_probability,b4_kelly_sizing,b5_trade_selection,b5b_quality_gate,b5c_circuit_breaker,b6_signal_output,orchestrator}.py`
- `captain-offline/captain_offline/blocks/{b3_pseudotrader,b4_injection,b6_auto_expansion,orchestrator}.py`
- `captain-online/captain_online/blocks/b7_position_monitor.py:303–316`
- `scripts/paper_trader.py:393–433`
- `shared/trade_source.py:295–314`

### Confidence

**HIGH:**
- F-22…F-29 severity/title/code refs/spec refs (verbatim from audit)
- B1–B6 entry-point signatures (read directly)
- D03 schema column list and writer call paths
- `SignalReplayEngine` API surface and caller list
- §3.2 re-ask filtering against Phase 7 scope

**MEDIUM:**
- The exact list of changes required to make B1 injection-friendly — depends on Stage 1B design choice between abstract data provider / monkey-patching / `replay_mode` flag
- Whether `replay_engine.py` is refactor-in-place or replaced — depends on GUI replay constraints not yet inspected (`b11_replay_runner.py` was named but not deeply read)

**LOW:**
- Multi-user replay fan-out semantics — decisions log is silent; needs explicit answer in Stage 1B (§8.8)
- HMM-state-as-of-`d` policy — no historical D26 snapshots exist (§8.7)

### Known gaps

- `b11_replay_runner.py` (GUI replay) was identified as a `replay_engine.py` consumer but not deeply audited. Stage 1B must verify how a `replay_engine.py` refactor affects the GUI replay path.
- `aim_retroactive_replay` is undefined in code or spec; Phase 7 must invent the signature (§7).
- `signal_id` column does not exist in D03. The Phase 1 build plan (`2026-04-27_phase1_schema_migrations_build_plan.md`) does not include it. A Phase 1.5 amendment may be needed if the design picks option (a) in §4.3.

---

*End of Stage 1A. Awaiting "approved, continue" before Stage 1B (design doc generation).*
