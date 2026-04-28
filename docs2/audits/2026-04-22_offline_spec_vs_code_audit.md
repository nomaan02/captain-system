---
title: Captain Offline Spec-vs-Code Audit
date: 2026-04-22
auditor: Claude (Opus 4.7), read-only session
session_basis: docs2/spec-docs-02/offline/ corpus + repo HEAD
mode: AUDIT ONLY — no code, config, or QuestDB changes performed
fan_out: 11 parallel `explore` subagents (SA-1..SA-11), aggregated and deduped in main thread
---

# Captain Offline — Spec-vs-Code Audit (2026-04-22)

## 1. Executive Summary

| Severity  | Count |
| --------- | ----- |
| BLOCKING  | 6     |
| HIGH      | 32    |
| MEDIUM    | 24    |
| LOW       | 17    |
| **Total** | **79**|

- **QuestDB schema changes required:** 2 additive (Q-01 from prior audit re P2-D07 still open; Q-02 P3-D03 basket key; Q-03 D26 smoothing/manifest).
- **Items needing Isaac clarification:** 17 unique questions consolidated in §6.
- **Production-affecting bugs:** 38 (BLOCKING + HIGH).
- **Offline workflow paths fully unwired in production:** 2 (PG-01C HMM training; AIM-7 COT computation).

The offline corpus is implemented but with significant **wiring and contract gaps** rather than logic errors at the algorithm core. Three classes of defect dominate:

1. **Unwired feedback loops.** PG-01C (AIM-16 HMM training) has no orchestrator caller (F-01); PG-11 transition blending has no consumer (F-04); AIM-7 (COT) is not registered in the modifier dispatch (F-13). The implementations exist but never run end-to-end.

2. **Persistence contract drift.** P3-D04 receives partial INSERTs from BOCPD then CUSUM, so `LATEST ON last_updated` returns whichever block wrote last with the other's columns null — Kelly L1's `cp_prob` read is therefore corrupt after every trade (F-03). The same pattern silently breaks AIM-13 FRAGILE → Online (F-05): offline writes a numeric, the online modifier function only reads a dict, so FRAGILE never sizes down. PG-16C reads a `model_m` column that doesn't exist on P3-D03 (F-06).

3. **Spec-vs-canvas internal contradictions.** The Kelly canvas wires BOCPD `cp_prob` through Redis `bocpd:{asset}`; doc 32 PG-15 reads from QuestDB `P3-D04.current_changepoint_probability`; code reads D04. Three spec artifacts disagree (F-08). The DMA canvas mandates Redis hash `aim_modifiers:{asset}`; code computes in-process (F-19). The trade-outcome bus is named `trades` (canvas) / `captain:trade_outcomes` (CLAUDE.md) / `stream:trade_outcomes` (code) — three different names (F-18). These are correctness-via-luck situations: the system works only because no external consumer respects the canvas contract.

The PG-09 / PG-10 / PG-13 chain (pseudotrader → injection → auto-expansion) has cascading defects that compound: injection always uses precomputed P&L (F-26) → auto-expansion passes the same `holdout_returns` for every viable candidate (F-29) → the spec's CSCV PBO on the full perturbation grid is replaced by PBO on a single best cell (F-27) → DSR is computed from validation Sharpe instead of OOS Sharpe (F-28). Together these mean PG-13's adoption gate `pbo<0.5 AND dsr>0.5` is structurally not what the spec defines.

The Block 9 system-health diagnostic runs but D3 (model staleness) uses a single global injection timestamp (F-32), D4 (AIM effectiveness) uses inclusion weights instead of modifier accuracy and can produce scores >1.0 (F-33), and the weekly run only covers 7 of 8 dimensions while monthly covers 8 — making `overall_health` non-comparable across cadences (F-34).

Two "RESOLVED" items in doc 32's Audit Resolutions section don't survive verification: G-OFF-046 (rollback) skips the spec-mandated `ON admin_approval` gate (F-09); G-XCT-012 (crash recovery) is observational logging only — no replay path (F-43).

The two structural divergences (`shared/aim_compute.py` consolidating per-AIM modules; block-prefixed file names vs canvas standalone names) are flagged once each at LOW (F-77, F-78) per the SC-05 stance.

## 2. Spec Coverage Table

| Spec file (offline/) | Sections fully read | Coverage of audit scope | Notes / silences |
|---|---|---|---|
| `32_P3_Offline_Full_Pseudocode.md` | All 9 blocks; PG-01..PG-17; Version Snapshot Policy; Audit Resolutions | Full Offline coverage | "Audit Resolutions" lists 5 items as CRITICAL RESOLVED — verified 3, two (G-OFF-046, G-XCT-012) are partially or non-resolved (F-09, F-43). |
| `22_HMM_Opportunity_Regime 1.md` | All 9 sections | Full PG-01C / AIM-16 spec | TVTP, 7-D obs vector, supervised seeding, α=0.3 smoothing all defined. Spec has one **internal ambiguity**: §6 says 240 obs/window with parenthetical "adjust if 1 obs/day". (Q-02 in §6.) |
| `P3 Offline.canvas` | Single-text-node arch overview | Block-level module + R/W + DEPS + CRON annotations | Authoritative for module-name expectations and Redis key annotations (`adwin:{aim_id}`, retrain flag). |
| `Kelly 7 Layer Pipeline.canvas` | L1–L7 | L1 in scope (Offline B8) | **Internal contradiction with doc 32**: cites Redis `bocpd:{asset}` for BOCPD cp; doc 32 PG-15 cites QuestDB `P3-D04.current_changepoint_probability`. (See F-08.) |
| `DMA MoE Meta-Learning Pipeline.canvas` | Full DMA + MoE flow | Block 1 / Online B3 wiring | Redis hash `aim_modifiers:{asset}` named but not implemented in code (F-19). |
| `AIM System.canvas` | 22 nodes + 8 edges | Per-AIM modifier semantics | Authoritative for AIM-01..15 modifier formulas, warm-up days, tier. AIM-7 marked active but DEC-08 in code disables it (Q-08). |
| `AIM System 1.canvas` | Two duplicated text nodes (SC-01) | Module-name annotations only | Provides the `aim_NN_*.py` per-AIM filename hints the code does not follow (CV-01 / F-77). |

**External cross-references not in this corpus** (per SC-03): `[[24_P3_Dataset_Schemas]]`, `[[31_AIM_Individual_Specifications]]`, `[[21_Implementation_Guides]]`, `[[04_Captain_Offline]]`, `[[07_AIM_System]]`, `[[08_Kelly_Sizing_Pipeline]]`, `[[33_P3_Online_Full_Pseudocode]]`. Schemas backed by `shared/canonical_schemas.py` per Phase 0 confirmation; AIM individual specs partially covered by `AIM System.canvas`. Q-01 in §6.

## 3. Findings

Findings ordered BLOCKING → HIGH → MEDIUM → LOW. Subagent IDs (SA-N-FNN) preserved in parens for traceability.

---

### F-01 — PG-01C (AIM-16 HMM training) is never invoked from the orchestrator

**Severity:** BLOCKING
(merges SA2-F01, SA10-F01)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` lines 86–88 (PG-01C reference); `P3 Offline.canvas` Block 1 — `PG-01C: ... MODULE: hmm_trainer.py. DEPS: hmmlearn`; doc 22 §6 — Baum-Welch on rolling 60-day window; "Persistence: Model snapshots and sufficient statistics → P3-D26".

**Code reference:** `[captain-offline/captain_offline/blocks/orchestrator.py:922-949](captain-offline/captain_offline/blocks/orchestrator.py)` — `_run_weekly` calls `run_tier_retrain` only; `[captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:309](captain-offline/captain_offline/blocks/b1_aim_lifecycle.py)` — `TIER_1_AIMS` excludes 16; `[captain-offline/captain_offline/blocks/b1_aim16_hmm.py:64-186](captain-offline/captain_offline/blocks/b1_aim16_hmm.py)` — `train_aim16_hmm` and `save_hmm_state` defined but no caller exists in repo.

**Divergence:** The implementation exists but the orchestrator has no path to it. Repo-wide search finds no `import` or call of `train_aim16_hmm` / `save_hmm_state` outside the defining file.

**Downstream effect:** Production. P3-D26 is never refreshed by the offline writer. The only D26 writer in the codebase is `save_hmm_state`, which is unreachable. Online B5's `_load_hmm_opportunity_state` therefore sees null/empty `opportunity_weights` and falls back to uniform 1.0/3.0 per session — HMM-driven session budgeting is non-functional. Cascades into F-12 (no obs vector ETL), F-10 (no TVTP), F-11 (empty opportunity_weights).

**Fan-out checked:** `captain-online/.../b5_trade_selection.py` (reads D26), `shared/replay_engine.py` (D26 optional), `shared/aim_compute.py:_aim16_hmm` (downstream consumer of D26).

**QuestDB impact:** NONE (the write path is never reached; no failing INSERT).

**Proposed fix direction:** Add a weekly hook in `_run_weekly` (or explicit cron) that calls a new `_run_aim16_training` driver: build the 7-D observation panel per spec §4, call `train_aim16_hmm`, persist via `save_hmm_state`. Add AIM-16 to a separate Tier (not Tier-1, since cadence differs).

**Needs Isaac:** YES (Q-03 — weekly cadence per asset vs session-global vs on-demand only).

---

### F-02 — Versioned writes to P3-D01 / P3-D02 omit mandatory pre-update snapshots

**Severity:** BLOCKING
(SA1-F01)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` Version Snapshot Policy — `VERSIONED_COMPONENTS = [P3-D01, P3-D02, P3-D05, P3-D12, P3-D17.system_params]`; `FUNCTION snapshot_before_update(component_id, trigger_reason)` with `state: deep_copy(get_current_state(component_id))` before mutating live state.

**Code reference:** `[captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:88-115](captain-offline/captain_offline/blocks/b1_aim_lifecycle.py)`; `[captain-offline/captain_offline/blocks/b1_hdwm_diversity.py:71-90](captain-offline/captain_offline/blocks/b1_hdwm_diversity.py)`; `[captain-offline/captain_offline/blocks/orchestrator.py:468-505](captain-offline/captain_offline/blocks/orchestrator.py)`.

**Divergence:** Most transitions that INSERT into `p3_d01_aim_model_states` (`_update_aim_status`, `_update_warmup_progress`) and HDWM reactivation INSERTs into D01/D02 run with no `snapshot_before_update` call. GUI AIM activate/deactivate applies D01 updates without a snapshot. Only some paths (e.g. ELIGIBLE/BOOTSTRAPPED→ACTIVE, Tier-1 retrain) snapshot selectively.

**Downstream effect:** Production. Audit-and-rollback cannot recover most lifecycle and HDWM mutations. Violates the "snapshot before every versioned write" architectural anchor that G-OFF-046 was supposed to establish.

**Fan-out checked:** Repo-wide grep for `snapshot_before_update` under `captain-offline/`. D17 writes are also unsnapshotted system-wide (separate finding F-22).

**QuestDB impact:** READ-ONLY (existing `p3_d18_version_history` table; missing rows are a logic gap, not a schema issue).

**Proposed fix direction:** Invoke `snapshot_before_update(component, trigger, state=None)` (None triggers `get_current_state` auto-load) immediately before each versioned D01/D02 INSERT; extend `TRIGGERS` enum if needed.

**Needs Isaac:** NO.

---

### F-03 — P3-D04 partial-row INSERT pattern breaks `LATEST ON` reads after every trade

**Severity:** BLOCKING
(SA3-F01)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-05 — "`P3-D04.bocpd[u].run_length_posterior = posterior` … `cp_probability = cp_probability` … SAVE P3-D04"; PG-06 — "`P3-D04.cusum[u].C_up_prev = C_up` … SAVE P3-D04"; PG-15 — "`cp_prob = P3-D04[u].current_changepoint_probability`".

**Code reference:** `[captain-offline/captain_offline/blocks/b2_bocpd.py:217-229](captain-offline/captain_offline/blocks/b2_bocpd.py)`; `[captain-offline/captain_offline/blocks/b2_cusum.py:199-210](captain-offline/captain_offline/blocks/b2_cusum.py)`; `[captain-offline/captain_offline/blocks/orchestrator.py:261-281](captain-offline/captain_offline/blocks/orchestrator.py)`; `[captain-offline/captain_offline/blocks/b8_kelly_update.py:42-52](captain-offline/captain_offline/blocks/b8_kelly_update.py)`; `[captain-offline/captain_offline/blocks/orchestrator.py:530-537](captain-offline/captain_offline/blocks/orchestrator.py)` (`_restore_detectors`).

**Divergence:** Each trade performs **two separate INSERTs** (BOCPD then CUSUM) with disjoint column sets. `LATEST ON last_updated PARTITION BY asset_id` returns whichever insert ran last — typically the CUSUM row with BOCPD/`current_changepoint_probability` left null. PG-15 then reads `current_changepoint_probability` from that LATEST row (defaults to 0.1 in `_get_cp_prob`), so adaptive EWMA never sees the BOCPD `cp` written on the prior row. Same pattern in `_restore_detectors` cannot reconstruct both detectors after restart.

**Downstream effect:** Production. Wrong Kelly L1 `cp_prob` after essentially every trade (always 0.1 default → `effective_span=30` → slowest adaptive EWMA). BOCPD/CUSUM restore wrong/incomplete across restarts.

**Fan-out checked:** `b8_kelly_update._get_cp_prob`, `orchestrator._restore_detectors`, `b2_level_escalation` (in-memory path only — unaffected), `b2_cusum.calibrate_and_persist`.

**QuestDB impact:** READ-ONLY (query pattern fix) OR SCHEMA CHANGE (additive — split tables). Recommend the read-pattern fix.

**Proposed fix direction:** Either (a) emit one merged D04 row per trade containing both BOCPD and CUSUM fields (orchestrate from `_handle_trade_outcome`), or (b) change readers to issue separate `LATEST ON` subqueries per logical column group via `ASOF JOIN` and merge.

**Needs Isaac:** NO.

---

### F-04 — PG-11 transition blending has no consumer; `blend_signal` is dead code

**Severity:** BLOCKING
(SA4-F01)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-11 — `FOR day d IN range(1, transition_days + 1):` … `blended_size = weight_new * signal_new.size + weight_old * signal_old.size` … `OUTPUT blended_signal(direction=signal_new.direction, size=blended_size)`.

**Code reference:** `[captain-offline/captain_offline/blocks/b4_injection.py:195-231](captain-offline/captain_offline/blocks/b4_injection.py)` (defines `TransitionPhaser.blend_signal`); `[captain-offline/captain_offline/blocks/orchestrator.py:636-655](captain-offline/captain_offline/blocks/orchestrator.py)` (calls `finalize` only). No references under `captain-online/` to `p3_d06b_active_transitions` or equivalent.

**Divergence:** The blending math exists on `TransitionPhaser`, but nothing in the repo calls `blend_signal`. ADOPT phasing therefore has zero effect on live sizing.

**Downstream effect:** Production. Every ADOPT decision flips the locked strategy instantly with no transition window, contrary to the spec's transition-days behaviour.

**Fan-out checked:** Repo-wide grep for `blend_signal` and `p3_d06b_active_transitions`. Both are zero-consumer.

**QuestDB impact:** READ-ONLY (D06b table exists but is unread).

**Proposed fix direction:** Define a single consumer in Online (B6 signal output is the natural place) that reads `p3_d06b_active_transitions`, calls `blend_signal` per active transition, and applies blended size. Or amend the spec if blending is intentionally out of scope.

**Needs Isaac:** YES (Q-04 — who is the consumer of `blend_signal`).

---

### F-05 — AIM-13 FRAGILE modifier never reaches Online: `_aim13_sensitivity` ignores numeric `current_modifier`

**Severity:** BLOCKING
(SA5-F01)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-12 — "`IF robustness_status == "FRAGILE": ... P3-D01[13].current_modifier = 0.85`"; `AIM System.canvas` AIM-13 node — "READS: P3-D13(QuestDB: sensitivity_scan_results); WRITES: P3-D01".

**Code reference:** `[captain-offline/captain_offline/blocks/b5_sensitivity.py:262-270](captain-offline/captain_offline/blocks/b5_sensitivity.py)` (writes 0.85 as a float); `[shared/aim_compute.py:620-629](shared/aim_compute.py)` (only branches when `current_modifier` is a dict); `[captain-online/captain_online/blocks/b1_data_ingestion.py:124-125](captain-online/captain_online/blocks/b1_data_ingestion.py)` (parses as JSON → float).

**Divergence:** Offline writes `0.85` as a numeric value. B1 loads it as a float via `parse_json`. `_aim13_sensitivity` only applies a non-unity modifier when the value is a **dict**; otherwise returns 1.0. Runtime never reads P3-D13 in `_aim13_sensitivity` despite the canvas READS line.

**Downstream effect:** Production. FRAGILE scans do not reduce AIM-13 sizing. The entire monthly sensitivity-driven safety mechanism is silently inactive.

**Fan-out checked:** `shared/aim_compute.py` dispatch table → `_aim13_sensitivity`; `b1_data_ingestion._load_aim_states`.

**QuestDB impact:** NONE.

**Proposed fix direction:** Either (a) write D01 `current_modifier` as JSON dict (`{"modifier":0.85,"reason_tag":"AIM13_FRAGILE"}`), or (b) teach `_aim13_sensitivity` to accept numeric modifiers and/or read P3-D13 directly per canvas. (a) is the minimum-diff fix and matches the canvas dispatch contract.

**Needs Isaac:** YES (Q-05 — should D01 carry the dict envelope or should AIM-13 read D13 directly).

---

### F-06 — PG-16C requires basket key on P3-D03 that does not exist in canonical schema

**Severity:** BLOCKING
(merges SA7-F01, SA11-F01)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-16C — "`INPUT: P3-D03 trade outcomes for basket b`" / "`trades = P3-D03.filter(basket=b)`".

**Code reference:** `[captain-offline/captain_offline/blocks/b8_cb_params.py:41-50](captain-offline/captain_offline/blocks/b8_cb_params.py)` selects `WHERE account_id=%s AND model_m=%s` from `p3_d03_trade_outcome_log`; `[shared/canonical_schemas.py:366-391](shared/canonical_schemas.py)` defines D03 with no `model_m` or `basket` column; `[captain-online/captain_online/blocks/b7_position_monitor.py](captain-online/captain_online/blocks/b7_position_monitor.py)` and `shared/trade_source.py` writers do not insert `model_m`.

**Divergence:** The query references a column the canonical schema does not declare and that no writer populates.

**Downstream effect:** Production. β_b / `P3-D25` is never correctly estimated — query either errors or returns empty. CB layers 3/4 use the cold-start defaults forever.

**Fan-out checked:** `b5c_circuit_breaker._load_cb_params` (downstream consumer of P3-D25).

**QuestDB impact:** SCHEMA CHANGE (additive). See Q-02 in §4.

**Proposed fix direction:** Add `model_m INT` (or `basket_id SYMBOL`) to `p3_d03_trade_outcome_log`, populate at trade-outcome write time from the active locked-strategy `m`, then keep the WHERE clause. See §4 Q-02.

**Needs Isaac:** YES (Q-06 — confirm column name and basket-key semantics).

---

## HIGH (32 findings)

---

### F-07 — PG-15 BOCPD source: Kelly canvas mandates Redis `bocpd:{asset}`; doc 32 + code use QuestDB D04

**Severity:** HIGH
(merges SA3-F03, SA7-F04, SA10-F03)

**Spec reference:** `Kelly 7 Layer Pipeline.canvas` L1 — "READS: ... BOCPD cp_prob (Redis: bocpd:{asset} key)"; `32_P3_Offline_Full_Pseudocode.md` PG-15 — "`cp_prob = P3-D04[u].current_changepoint_probability`".

**Code reference:** `[captain-offline/captain_offline/blocks/b8_kelly_update.py:42-52](captain-offline/captain_offline/blocks/b8_kelly_update.py)` reads QuestDB D04 only; `[captain-offline/captain_offline/blocks/b2_bocpd.py](captain-offline/captain_offline/blocks/b2_bocpd.py)` writes D04 only; repo-wide search finds no `bocpd:` Redis setter in Python.

**Divergence:** Spec-internal contradiction. Per skill SC-04 doc 32 governs over canvas, so code follows the right authority — but external tooling built to the canvas contract would silently fail. Compounds with F-03 (D04 partial-row issue): even when the right table is read, the value is null after F-03.

**Downstream effect:** Production. Internal consistency OK once F-03 is fixed; cross-process consumers expecting Redis `bocpd:{asset}` see nothing.

**Fan-out checked:** `b2_bocpd.run_bocpd_update`, `b8_kelly_update._get_cp_prob`, all `captain-online/` modules.

**QuestDB impact:** NONE.

**Proposed fix direction:** Amend Kelly canvas (and DMA canvas) to read `P3-D04.current_changepoint_probability`, OR add a thin Redis mirror writer in `b2_bocpd` for spec fidelity. Pick one wire and delete the other from authoritative docs.

**Needs Isaac:** YES (Q-07 — which artifact is canonical when canvas and doc 32 disagree).

---

### F-08 — `rollback_to_version` skips spec-mandated `ON admin_approval` gate (G-OFF-046 partially resolved)

**Severity:** HIGH
(merges SA1-F02, SA10-F04)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` Version Snapshot Policy — `NOTIFY(user_id=admin_user_id, message="Rollback comparison ready", priority="HIGH", action_required=True)` then `ON admin_approval: snapshot_before_update / restore_state`. Audit Resolutions section marks G-OFF-046 as CRITICAL RESOLVED.

**Code reference:** `[captain-offline/captain_offline/blocks/version_snapshot.py:403-480](captain-offline/captain_offline/blocks/version_snapshot.py)` — after pseudotrader returns ADOPT, the code immediately snapshots, restores, and runs regression tests. No separate phase gated on admin approval.

**Divergence:** A single call can apply a full rollback without the two-step human gate the spec sequences. "RESOLVED" is overstated.

**Downstream effect:** Production. Governance/audit expectation from doc 32 not met. A buggy admin tool or compromised credential can drive an automated full state restore.

**Fan-out checked:** `version_snapshot.py` is the single implementation; no Command/GUI gate found.

**QuestDB impact:** DESTRUCTIVE if rollback fires (restore replays INSERTs into live versioned tables) — risk amplified by missing approval gate.

**Proposed fix direction:** Two-phase API: `request_rollback()` → notify → store proposal token → separate `commit_rollback(token, admin_user_id)` triggered by external admin signal.

**Needs Isaac:** YES (Q-08 — is automatic rollback after pseudotrader ADOPT intentional override of doc 32).

---

### F-09 — PG-02 DMA loop updates every D02 row, not "FOR EACH active aim"

**Severity:** HIGH
(SA1-F03)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-02 — `FOR EACH active aim a:` through normalisation and `SAVE P3-D02`.

**Code reference:** `[captain-offline/captain_offline/blocks/b1_dma_update.py:40-62, 158-228](captain-offline/captain_offline/blocks/b1_dma_update.py)`.

**Divergence:** `_load_active_aims` loads every latest D02 row per asset with no join/filter on `p3_d01_aim_model_states.status == 'ACTIVE'`. Likelihoods and normalisation include WARM_UP / ELIGIBLE / SUPPRESSED AIMs.

**Downstream effect:** Production. Inclusion probabilities for inactive AIMs move on every trade; MoE behaviour diverges from doc 32.

**Fan-out checked:** `run_dma_update` callers in orchestrator (`_handle_trade_outcome`, `_handle_signal_outcome`).

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Restrict the DMA loop to AIMs whose latest D01 status is ACTIVE (and document AIM-16 if session-scoped).

**Needs Isaac:** NO.

---

### F-10 — PG-03 HDWM: recovery scope, trigger, and `num_active_aims` all diverge from spec

**Severity:** HIGH
(SA1-F04)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-03 — `IF len(active_in_type) == 0: best_candidate = argmax(P3-D02[a].recent_effectiveness for a in seed_types[type])` and `SET P3-D02[best_candidate].inclusion_probability = 1.0 / num_active_aims`.

**Code reference:** `[captain-offline/captain_offline/blocks/b1_hdwm_diversity.py:59-125](captain-offline/captain_offline/blocks/b1_hdwm_diversity.py)`.

**Divergence:** (1) Recovery runs only when every AIM in the type is non-ACTIVE **and** at least one is SUPPRESSED; spec runs whenever no ACTIVE in type, with `argmax` over **all** AIMs in seed_types[type]. (2) `_count_active_aims` uses `SELECT count() ... WHERE status='ACTIVE'` with no `LATEST ON ... PARTITION BY aim_id`, so append-only history inflates counts.

**Downstream effect:** Production. Diversity recovery may never fire; assigned weights wrong after operational time.

**Fan-out checked:** `run_hdwm_diversity_check` from `_run_weekly` only.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Match spec candidate set and trigger; count distinct `aim_id` after `LATEST ON`.

**Needs Isaac:** NO.

---

### F-11 — PG-01 WARM_UP / ELIGIBLE / progress semantics use dual gates not in doc 32

**Severity:** HIGH
(SA1-F05)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-01 — single observation-based progress to ELIGIBLE; user activation alone to ACTIVE.

**Code reference:** `[captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:238-277](captain-offline/captain_offline/blocks/b1_aim_lifecycle.py)`.

**Divergence:** WARM_UP uses both `feature_days_accumulated` and `learning_warmup_required` gates, writes `min(...)` to warmup progress, moves to ELIGIBLE on the **feature** gate alone. ELIGIBLE→ACTIVE requires both user activation and `trades >= learn_required`.

**Downstream effect:** Production. Lifecycle timing and ACTIVE entry disagree with pseudocode; `_handle_aim_activation` can force ACTIVE while cron path remains stricter.

**Fan-out checked:** `run_aim_lifecycle`, `_handle_aim_activation`.

**QuestDB impact:** NONE.

**Proposed fix direction:** Implement doc 32 verbatim or amend doc 32 to add the dual gate; unify GUI and cron activation rules.

**Needs Isaac:** YES (Q-09 — does the in-code DEC-05 dual warm-up override doc 32).

---

### F-12 — PG-01 suppression/recovery does not implement consecutive-trade `meta_weight` rules

**Severity:** HIGH
(SA1-F06)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-01 — `IF meta_weight(a) == 0 for 20+ consecutive trades:` … `IF meta_weight(a) > 0.1 for 10+ consecutive trades: SET status = ACTIVE`.

**Code reference:** `[captain-offline/captain_offline/blocks/b1_aim_lifecycle.py:286-305, 375-392](captain-offline/captain_offline/blocks/b1_aim_lifecycle.py)`.

**Divergence:** `consecutive_zero` is aliased to `days_below_threshold` on D02 (inclusion below threshold), not 20 consecutive post-trade outcomes with `inclusion_probability == 0`. `consecutive_above` is stubbed.

**Downstream effect:** Production. SUPPRESSED/ACTIVE flips decoupled from spec semantics.

**Fan-out checked:** `_load_meta_weight_history`.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Track consecutive trade-level meta weights from the DMA update path or persist counters.

**Needs Isaac:** NO.

---

### F-13 — PG-04 drift uses modifier JSON as features and skips unfitted autoencoders

**Severity:** HIGH
(SA1-F07)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-04 — `current_features = get_aim_input_features(a, today)`; `reconstruction_error = aim_autoencoder[a].reconstruct(current_features)`.

**Code reference:** `[captain-offline/captain_offline/blocks/orchestrator.py:886-907](captain-offline/captain_offline/blocks/orchestrator.py)`; `[captain-offline/captain_offline/blocks/b1_drift_detection.py:269-333](captain-offline/captain_offline/blocks/b1_drift_detection.py)`.

**Divergence:** Daily scheduling passes `aim_features` built from `current_modifier` JSON value lists, not QuestDB AIM feature vectors. `SimpleAutoEncoder` is skipped when `not ae.fitted`, so reconstruction and ADWIN rarely run.

**Downstream effect:** Production. Drift halving, renormalisation, and retrain flags almost never reflect true input-feature drift.

**Fan-out checked:** `run_drift_detection` from `_run_daily` only.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Load per-AIM features per spec; use trained AE checkpoints (`models/ae_*.pt`) or bootstrap fit before gating on `fitted`.

**Needs Isaac:** NO.

---

### F-14 — TVTP not implemented: AIM-16 HMM uses time-homogeneous transitions

**Severity:** HIGH
(SA2-F02)

**Spec reference:** `22_HMM_Opportunity_Regime 1.md` §2/§3/§5 — "Transitions: TVTP (time-varying transition probabilities)"; "A(x_t) | TVTP transition matrix | K×K; entries depend on covariates x_t (e.g. day-of-week, VIX bucket)"; covariates `x_t = {VIX_level, day_of_week, prior_session_PnL}`.

**Code reference:** `[captain-offline/captain_offline/blocks/b1_aim16_hmm.py:120-132](captain-offline/captain_offline/blocks/b1_aim16_hmm.py)`.

**Divergence:** Standard `hmmlearn.GaussianHMM` with a fixed `transmat_` after uniform init. No TVTP `A(x_t)` driven by the documented covariates.

**Downstream effect:** Production (when training runs — currently F-01 prevents it). Transition behaviour and state paths differ materially from the specified TVTP HMM.

**Fan-out checked:** Consumers of `hmm_params` in `b5_trade_selection._load_hmm_opportunity_state` / replay.

**QuestDB impact:** READ-ONLY (semantic difference, not schema).

**Proposed fix direction:** Introduce a TVTP-capable model (or explicit covariate conditioning on `A`) and pass `x_t` sequences into training.

**Needs Isaac:** YES (Q-10 — is non-TVTP v1 acceptable, or TVTP a release gate).

---

### F-15 — AIM-16 HMM: 7-element observation vector not built from spec sources

**Severity:** HIGH
(SA2-F03)

**Spec reference:** `22_HMM_Opportunity_Regime 1.md` §4 — table listing `n_signals`, `mean_OO`, `volume_z`, `vix_level`, `prior_session_pnl`, `cross_asset_corr`, `day_of_week`. "All elements must be defined, versioned, and aligned between offline training and online inference."

**Code reference:** `[captain-offline/captain_offline/blocks/b1_aim16_hmm.py:64-75](captain-offline/captain_offline/blocks/b1_aim16_hmm.py)` — accepts a pre-sized `observations` ndarray only. Repo search finds no `compute_observation_vector` or PG-01C feature builder.

**Divergence:** The block documents the seven features in its docstring but does not read P3-D03, signal history, or market inputs to build them. With no calling pipeline, none of the seven elements are computed from documented sources.

**Downstream effect:** Production. Even if the scheduler were fixed (F-01), training would not run on real, spec'd inputs unless a separate ETL is added.

**Fan-out checked:** N/A (no production caller).

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Implement `compute_observation_vector` per spec sources, roll a 60×4 (or 240×1) window, then call `train_aim16_hmm`.

**Needs Isaac:** NO (the per-element source is in spec §4).

---

### F-16 — HMM `opportunity_weights` always empty from training; D26 has no other writer

**Severity:** HIGH
(SA2-F04)

**Spec reference:** `22_HMM_Opportunity_Regime 1.md` §6/§7 — "Model snapshots and sufficient statistics → P3-D26"; "Budget weights | Normalised state probabilities (sum = 1) mapped through a fixed, documented map to session budget multipliers".

**Code reference:** `[captain-offline/captain_offline/blocks/b1_aim16_hmm.py:147-161, 166-186](captain-offline/captain_offline/blocks/b1_aim16_hmm.py)`; `[captain-online/captain_online/blocks/b5_trade_selection.py:149-170](captain-online/captain_online/blocks/b5_trade_selection.py)`.

**Divergence:** `train_aim16_hmm` always sets `opportunity_weights={}` with a comment "online will populate". The only D26 writer in code is `save_hmm_state` (unwired per F-01); B5's loader only ever sees null weights and falls back to uniform `1.0/3.0` per session.

**Downstream effect:** Production. HMM session allocation non-functional beyond cold-start defaults.

**Fan-out checked:** B5 trade selection, replay engine.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** After training, derive session `opportunity_weights` from mapped state probabilities (per doc §7) and persist; OR add a documented Online writer with single owner.

**Needs Isaac:** YES (Q-11 — who owns the D26 `opportunity_weights` write — offline or online).

---

### F-17 — Decay alerts use wrong Redis payload; GUI/Telegram receive blank `message`

**Severity:** HIGH
(SA3-F02)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-08 — `NOTIFY_GUI("Level 2: Sizing reduced to {reduction_factor*100}% for {asset}", priority="HIGH", colour="AMBER")` and `NOTIFY_GUI("Level 3: STRATEGY REVIEW — no signals for {asset}", priority="CRITICAL", colour="RED")`.

**Code reference:** `[captain-offline/captain_offline/blocks/b2_level_escalation.py:97-110](captain-offline/captain_offline/blocks/b2_level_escalation.py)` publishes `type: DECAY_ALERT` with no `message` or `event_type`; `[captain-command/captain_command/blocks/orchestrator.py:576-620](captain-command/captain_command/blocks/orchestrator.py)` `_handle_alert` forwards `data.get("message", "")`.

**Divergence:** Operators receive priority HIGH/CRITICAL but blank text. No colour metadata.

**Downstream effect:** Production. Decay notifications structurally fire but are operationally useless.

**Fan-out checked:** Other publishers to `CH_ALERTS` (e.g. `b6_signal_output.py`) use `message` + `event_type` correctly.

**QuestDB impact:** NONE.

**Proposed fix direction:** Align decay publish with `message`/`event_type`/`notif_id` contract `_handle_alert` expects; embed PG-08 strings.

**Needs Isaac:** NO.

---

### F-18 — Trade-outcome bus name disagrees across canvas / CLAUDE.md / code (`trades` vs `captain:trade_outcomes` vs `stream:trade_outcomes`)

**Severity:** HIGH
(merges SA10-F02, SA10-F15)

**Spec reference:** `P3 Offline.canvas` — `TRIGGER: Redis pub/sub "trades" event`; `DMA MoE.canvas` — `Redis pub/sub: trades`; `CLAUDE.md` Redis Channels — `captain:trade_outcomes`.

**Code reference:** `[shared/redis_client.py:29-30, 73-76](shared/redis_client.py)` defines `CH_TRADE_OUTCOMES = "captain:trade_outcomes"` AND `STREAM_TRADE_OUTCOMES = "stream:trade_outcomes"`; `[captain-online/captain_online/blocks/b7_position_monitor.py:37, 402](captain-online/captain_online/blocks/b7_position_monitor.py)` publishes via stream; `[captain-offline/captain_offline/blocks/orchestrator.py:192-198](captain-offline/captain_offline/blocks/orchestrator.py)` consumes via stream consumer group; `[scripts/paper_trader.py:350](scripts/paper_trader.py)` publishes via legacy pub/sub.

**Divergence:** Three names for the same logical bus. Production path is Redis Streams. Anything publishing only to pub/sub (e.g. `paper_trader`) will not reach the offline consumer group.

**Downstream effect:** Production OK if all publishers use streams; replay/test risk.

**Fan-out checked:** Online B7 (stream), Command routing (stream), `paper_trader` (pub/sub — incompatible).

**QuestDB impact:** NONE.

**Proposed fix direction:** Align canvases and CLAUDE.md to streams; deprecate pub/sub in `paper_trader.py`; fix orchestrator docstring at `[captain-offline/captain_offline/blocks/orchestrator.py:7-25](captain-offline/captain_offline/blocks/orchestrator.py)`.

**Needs Isaac:** YES (Q-12 — name the canonical contract: stream key + payload schema).

---

### F-19 — BOCPD L2 debouncing skips re-triggers as `cp_probability` rises monotonically

**Severity:** HIGH
(SA3-F04)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-05 — `IF cp_probability > 0.8: TRIGGER Level_2(asset=u, severity=cp_probability, source="BOCPD")`. PG-08 sizing reduction scales with severity.

**Code reference:** `[captain-offline/captain_offline/blocks/b2_level_escalation.py:199-206, 115-126](captain-offline/captain_offline/blocks/b2_level_escalation.py)`.

**Divergence:** BOCPD Level 2 fires only on first crossing of 0.8 (`_level2_active` debounces). While `cp` remains >0.8 and rises (e.g. 0.82→0.95), `trigger_level2` is not re-called, so `P3-D12.sizing_override` is not refreshed with the stronger `reduction_factor`.

**Downstream effect:** Production. Undersized risk reduction when changepoint probability worsens monotonically without dipping below 0.8.

**Fan-out checked:** `_set_sizing_override` is the only writer of `P3-D12.sizing_override` triggered from L2.

**QuestDB impact:** NONE.

**Proposed fix direction:** Remove debounce or re-fire when severity increases by a material delta, or on every trade while `cp > 0.8`.

**Needs Isaac:** NO.

---

### F-20 — Quarterly PG-07 persists new CUSUM limits but does not refresh in-memory detector

**Severity:** HIGH
(SA3-F05)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-07 — quarterly recalibration; PG-06 — `h_sequential = P3-D04.cusum[u].control_limit(sprint_length=T_n)`.

**Code reference:** `[captain-offline/captain_offline/blocks/orchestrator.py:995-1017](captain-offline/captain_offline/blocks/orchestrator.py)` (`_run_quarterly` calls `calibrate_and_persist` only); `[captain-offline/captain_offline/blocks/orchestrator.py:577-629](captain-offline/captain_offline/blocks/orchestrator.py)` (`_init_cusum_calibration` does load into memory); `[captain-offline/captain_offline/blocks/b2_cusum.py:69-70](captain-offline/captain_offline/blocks/b2_cusum.py)`.

**Divergence:** `_run_quarterly` persists DB but never reloads `calibrate_cusum_limits` into `self._detectors[asset_id][1].sequential_limits`. `run_cusum_update` uses the in-memory dict for `h`, so production keeps pre-quarterly limits until process restart.

**Downstream effect:** Production. Stale CUSUM thresholds for up to months in long-running processes.

**Fan-out checked:** `run_cusum_update`, `_init_cusum_calibration`.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** After each `calibrate_and_persist`, merge returned limits into the live `CUSUMDetector` (mirror init path).

**Needs Isaac:** NO.

---

### F-21 — `programs_1_2_rerun` enqueued but never executed automatically

**Severity:** HIGH
(SA3-F06)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-08 — `SCHEDULE programs_1_2_rerun(asset)`.

**Code reference:** `[captain-offline/captain_offline/blocks/b2_level_escalation.py:166-168](captain-offline/captain_offline/blocks/b2_level_escalation.py)`; `[captain-offline/captain_offline/blocks/orchestrator.py:657-725](captain-offline/captain_offline/blocks/orchestrator.py)`.

**Divergence:** Level 3 enqueues `P1P2_RERUN`, but `_dispatch_pending_jobs` sets status `AWAITING_MANUAL` and only logs a warning. By contrast `AIM14_EXPANSION` invokes `run_auto_expansion`. Spec schedules an actual rerun.

**Downstream effect:** Production. Level 3 does not drive automated P1/P2 recompute as specified.

**Fan-out checked:** `p3_offline_job_queue` consumers.

**QuestDB impact:** NONE.

**Proposed fix direction:** Wire `P1P2_RERUN` to the real batch entrypoint; mark COMPLETED/FAILED accordingly.

**Needs Isaac:** YES (Q-13 — what is the authoritative automation target for `programs_1_2_rerun`).

---

### F-22 — G-OFF-016 marked RESOLVED, but pseudotrader gate still doesn't run `captain_online_replay` per day

**Severity:** HIGH
(SA4-F02)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` Audit Resolutions — `G-OFF-016 — No Pipeline Replay in Pseudotrader (PG-09 §1-2) — CRITICAL RESOLVED`; PG-09 Phase 1–2 — `signal = captain_online_replay(d, using=CURRENT_parameters)`.

**Code reference:** `[captain-offline/captain_offline/blocks/orchestrator.py:79-87](captain-offline/captain_offline/blocks/orchestrator.py)`; `[captain-offline/captain_offline/blocks/b3_pseudotrader.py:957-1031](captain-offline/captain_offline/blocks/b3_pseudotrader.py)`.

**Divergence:** `_pseudotrader_gate` always uses `run_signal_replay_comparison` (relies on `SignalReplayEngine` then `run_pseudotrader` with **precomputed** daily P&L), not the `captain_online_replay → run_replay` path that `run_pseudotrader` would use when `baseline_pnl`/`proposed_pnl` are omitted.

**Downstream effect:** Production. Resolution is partial. DMA/Kelly commit gate uses a different code path than spec.

**Fan-out checked:** `version_snapshot.py` uses the same pattern.

**QuestDB impact:** NONE.

**Proposed fix direction:** Point the gate at the primary `run_pseudotrader` path with explicit param overrides, OR amend Audit Resolutions to state Category A validation uses `SignalReplayEngine`.

**Needs Isaac:** YES (Q-14 — does `SignalReplayEngine`-only satisfy G-OFF-016).

---

### F-23 — PG-09 win-rate / metrics ignore `actual_trade_outcome(d)`; computed from replay P&L only

**Severity:** HIGH
(SA4-F03)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-09 Phase 1–2 — `outcome = actual_trade_outcome(d)`; results append `{signal, outcome}`.

**Code reference:** `[captain-offline/captain_offline/blocks/b3_pseudotrader.py:688-715, 846-867](captain-offline/captain_offline/blocks/b3_pseudotrader.py)`.

**Divergence:** D03 used to discover dates only; Sharpe / PBO / DSR computed from replay P&L. Diverges from spec's signal+actual outcome pairing. Interacts with prior audit's F-04 (Kelly sizes on `strategy.threshold` while live stops use `sl_multiple × or_range`): replay P&L sits on a risk model that doesn't match executed stops.

**Downstream effect:** Production. ADOPT/REJECT can be systematically biased.

**Fan-out checked:** `run_pseudotrader` primary path; `run_signal_replay_comparison`.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Build daily metrics series from D03 realised P&L for the spec-defined `actual_trade_outcome`.

**Needs Isaac:** YES (Q-15 — strict realised P&L vs theoretical replay).

---

### F-24 — PG-10 Step 1 `aim_retroactive_replay` not implemented; edges use scalar heuristic

**Severity:** HIGH
(SA4-F04)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-10 Step 1 — `FOR EACH active aim a: retroactive_modifiers[a] = aim_retroactive_replay(a, new_candidate, historical_window)`.

**Code reference:** `[captain-offline/captain_offline/blocks/b4_injection.py:46-65, 125-129](captain-offline/captain_offline/blocks/b4_injection.py)`.

**Divergence:** Expected edges are `mean(historical_pnl) * mean_modifier`, with `mean_modifier` from AIM weight dict length/totals — not per-AIM retroactive replay.

**Downstream effect:** Production. PG-10 ADOPT/REJECT decision uses an unjustified scalar instead of historical AIM playback.

**Fan-out checked:** `run_injection_comparison` only.

**QuestDB impact:** NONE.

**Proposed fix direction:** Implement per-AIM retroactive replay (call into `shared/aim_compute` with historical features) before forming `expected_new` / `expected_current`.

**Needs Isaac:** NO.

---

### F-25 — PG-10 Step 3 always uses precomputed-P&L branch; `pseudotrader_compare` never reruns the strategies

**Severity:** HIGH
(SA4-F05)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-10 Step 3 — `pseudo_results = pseudotrader_compare(new_candidate, current_strategy, historical_window)`.

**Code reference:** `[captain-offline/captain_offline/blocks/b4_injection.py:131-134](captain-offline/captain_offline/blocks/b4_injection.py)`; `[captain-offline/captain_offline/blocks/b3_pseudotrader.py:816-873](captain-offline/captain_offline/blocks/b3_pseudotrader.py)`.

**Divergence:** `run_injection_comparison` always passes `baseline_pnl`/`proposed_pnl`, so `run_pseudotrader` never takes the primary replay path. Correctness delegated to whoever fills `candidate_pnl`/`current_pnl` on the INJECTION command — no internal alignment check.

**Downstream effect:** Production. Comparison is whatever Command sends; B4 has no defence against misaligned payloads.

**Fan-out checked:** `[captain-offline/captain_offline/blocks/orchestrator.py:438-447](captain-offline/captain_offline/blocks/orchestrator.py)`.

**QuestDB impact:** NONE.

**Proposed fix direction:** Either compute aligned series inside B4 from locked strategy + candidate + D03, or reject misaligned payloads.

**Needs Isaac:** NO.

---

### F-26 — PG-13 candidate handoff to PG-10 uses identical `holdout_returns` for every viable candidate

**Severity:** HIGH
(merges SA4-F06, SA5-F04)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-13 — `injection_comparison(fc.candidate, decayed_asset)` after per-candidate `final_oos_test`.

**Code reference:** `[captain-offline/captain_offline/blocks/b6_auto_expansion.py:324-374, 367-374](captain-offline/captain_offline/blocks/b6_auto_expansion.py)`; per-candidate `oos = _candidate_oos_returns(candidate, ...)` is computed but ignored.

**Divergence:** Each viable candidate gets distinct `oos`, but `run_injection_comparison` is invoked with `candidate_pnl=holdout_returns` (same series for all), instead of per-candidate `oos` plus a P&L series for the **locked** strategy on the same window.

**Downstream effect:** Production. PG-10 ratio and PBO gate are wrong for AIM-14-driven injections.

**Fan-out checked:** `run_auto_expansion` only.

**QuestDB impact:** NONE.

**Proposed fix direction:** Pass `oos` per candidate plus matching baseline replay series for `current_strategy`.

**Needs Isaac:** NO.

---

### F-27 — PG-12 PBO computed on single best-grid cell, not full perturbation set

**Severity:** HIGH
(SA5-F02)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-12 — `pbo = compute_CSCV_PBO(results, S=8)` after building `results` across the full perturbation grid.

**Code reference:** `[captain-offline/captain_offline/blocks/b5_sensitivity.py:214-216](captain-offline/captain_offline/blocks/b5_sensitivity.py)`.

**Divergence:** Selects grid cell with highest Sharpe and runs PBO on that single cell's series, not on aggregate `results`.

**Downstream effect:** Production. PBO and FRAGILE/ROBUST gating disagree materially with spec methodology.

**Fan-out checked:** `b9_diagnostic.py` (reads only the status).

**QuestDB impact:** NONE.

**Proposed fix direction:** Align `compute_pbo` inputs with spec's `results` (multi-config CSCV).

**Needs Isaac:** YES (Q-16 — was a "PBO on best cell" amendment formally adopted).

---

### F-28 — PG-13 final DSR uses validation-window Sharpe, not OOS Sharpe

**Severity:** HIGH
(SA5-F03)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-13 — `oos_result = final_oos_test(candidate, holdout_window)` then `dsr = compute_DSR(oos_result.sharpe, ...)`.

**Code reference:** `[captain-offline/captain_offline/blocks/b6_auto_expansion.py:324-328](captain-offline/captain_offline/blocks/b6_auto_expansion.py)`.

**Divergence:** `_compute_dsr` is called with `candidate.fitness`, the validation-window Sharpe from `_evaluate_candidate`, not Sharpe from holdout/OOS returns.

**Downstream effect:** Production. Acceptance filter `dsr > 0.5` admits/rejects wrong candidates.

**Fan-out checked:** `run_auto_expansion` callers.

**QuestDB impact:** NONE.

**Proposed fix direction:** Compute DSR from OOS replay returns (mirror `oos_result.sharpe`).

**Needs Isaac:** NO.

---

### F-29 — PG-13 walk-forward train window is unused; GA fitness is single 70/30 split only

**Severity:** HIGH
(SA5-F05)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-13 — `walk_forward_train(candidate, training_window)` / `walk_forward_validate(candidate, validation_window)`.

**Code reference:** `[captain-offline/captain_offline/blocks/b6_auto_expansion.py:276-289](captain-offline/captain_offline/blocks/b6_auto_expansion.py)`.

**Divergence:** `historical_returns[:split_idx]` never passed to evaluation; every GA fitness uses `wf_validation_returns` (tail 30%) only. No walk-forward stepping.

**Downstream effect:** Production. Search procedure may overfit relative to intended walk-forward design.

**Fan-out checked:** `_evaluate_candidate`.

**QuestDB impact:** NONE.

**Proposed fix direction:** Implement explicit train vs validate windows (with rolling folds).

**Needs Isaac:** NO.

---

### F-30 — TSM PG-14: max_daily_loss evaluated per resampled return, not per "day" aggregate

**Severity:** HIGH
(SA6-F01)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-14 — `FOR day IN range(remaining_days):` … `FOR ret IN daily_returns:` … `IF daily_pnl < 0 AND abs(daily_pnl) > tsm.max_daily_loss` (MLL on same-day aggregate after 3–7 trades).

**Code reference:** `[captain-offline/captain_offline/blocks/b7_tsm_simulation.py:59-96](captain-offline/captain_offline/blocks/b7_tsm_simulation.py)`.

**Divergence:** `_block_bootstrap_path` + `_simulate_path` treat every list element as one draw for MLL, so a multi-trade "day" in the spec is not modelled.

**Downstream effect:** Production. `pass_probability` and PASS_EVAL/GROW_CAPITAL alerts systematically wrong.

**Fan-out checked:** `run_tsm_simulation` consumers (Redis `CH_ALERTS`, D08 readers).

**QuestDB impact:** READ-ONLY (semantic, not column).

**Proposed fix direction:** Resample blocks, aggregate each block to one `daily_pnl`, then run MDD/MLL/terminal checks per spec.

**Needs Isaac:** NO.

---

### F-31 — TSM PG-14: "remaining days" maps to one return per step, not 3–7 trades per day

**Severity:** HIGH
(SA6-F02)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-14 — outer `FOR day IN range(remaining_days)` with `block_size = random.choice([3, 5, 7])` and nested `FOR ret IN daily_returns`.

**Code reference:** `[captain-offline/captain_offline/blocks/b7_tsm_simulation.py:44-57, 127-135](captain-offline/captain_offline/blocks/b7_tsm_simulation.py)`.

**Divergence:** `_block_bootstrap_path` builds a length-`n_days` list of individual returns, not `remaining_days` outer iterations of 3–7-tick days.

**Downstream effect:** Production. MC time axis differs from spec; ~3× fewer balance updates than intended.

**Fan-out checked:** Same as F-30.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Reimplement path generator to match outer `day` and inner `ret` loops.

**Needs Isaac:** NO.

---

### F-32 — TSM PG-14: `pass_probability=None` for live accounts not implemented

**Severity:** HIGH
(SA6-F03)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-14 — `IF NOT tsm.max_drawdown_limit AND NOT tsm.max_daily_loss: P3-D08[ac].pass_probability = None`.

**Code reference:** `[captain-offline/captain_offline/blocks/b7_tsm_simulation.py:120-155, 197-240](captain-offline/captain_offline/blocks/b7_tsm_simulation.py)`.

**Divergence:** No branch sets `pass_probability` to `None` before INSERT when both limits are null; insert always uses computed `pass_probability`.

**Downstream effect:** Production. D08 shows misleading "pass probability" for unconstrained accounts; GUIs/Command RPT-07 may treat the value as meaningful.

**Fan-out checked:** Command B6 `b6_reports.py` RPT-07.

**QuestDB impact:** READ-ONLY (use NULL).

**Proposed fix direction:** Short-circuit MC and INSERT NULL when both limits are absent.

**Needs Isaac:** NO.

---

### F-33 — PG-16C `running_loss_at_trade_time` replaced by signed cumulative same-day P&L

**Severity:** HIGH
(SA7-F02)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-16C — `L_series = [running_loss_at_trade_time(t) for t in trades]`; model `r_i = r_bar + beta_b * L_b_at_time_i + epsilon`.

**Code reference:** `[captain-offline/captain_offline/blocks/b8_cb_params.py:161-184](captain-offline/captain_offline/blocks/b8_cb_params.py)`.

**Divergence:** Code uses signed cumulative same-day per-contract returns with daily reset. Spec calls for running **loss** at each trade time for the basket, no within-day-only reset stated.

**Downstream effect:** Production. CB layer-3 expectancy and `L_star` systematically wrong vs spec.

**Fan-out checked:** B5C L3/L4.

**QuestDB impact:** NONE (logic).

**Proposed fix direction:** Implement `running_loss_at_trade_time` per spec semantics (loss accumulation, cross-day behaviour).

**Needs Isaac:** YES (Q-17 — exact definition of `L_b`).

---

### F-34 — PG-16C `r_bar` is OLS intercept, not `mean(r_series)`

**Severity:** HIGH
(SA7-F03)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` PG-16C — `r_bar = mean(r_series)` and `beta_b = ols_slope(r_series, L_series)`.

**Code reference:** `[captain-offline/captain_offline/blocks/b8_cb_params.py:58-100, 183-184](captain-offline/captain_offline/blocks/b8_cb_params.py)`.

**Divergence:** `_ols_regression` sets `r_bar` to intercept `alpha = y_mean - beta * x_mean`. Spec fixes `r_bar` as unconditional mean. Unless `L` is centered, these differ; stored `r_bar` and `L_star = -r_bar / beta_b` deviate.

**Downstream effect:** Production. `mu_b = r_bar + beta_b * L_b` semantics in CB misaligned.

**Fan-out checked:** P3-D25 → B5C.

**QuestDB impact:** NONE.

**Proposed fix direction:** Set `r_bar = mean(r_series)`; keep OLS slope.

**Needs Isaac:** YES (Q-18 — confirm intent).

---

### F-35 — D3 system-health uses global injection timestamp instead of per-asset P1/P2 re-run age

**Severity:** HIGH
(SA8-F01)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` Block 9 — "D3 | Model Staleness Tracker | Days since last P1/P2 re-run **per asset**".

**Code reference:** `[captain-offline/captain_offline/blocks/b9_diagnostic.py:267-340](captain-offline/captain_offline/blocks/b9_diagnostic.py)`.

**Divergence:** D3 scores from `max(ts)` on `p3_d06_injection_history` (global "last injection") plus per-asset regime/AIM ages. Never computes "days since last P1/P2 re-run per asset". Composite repeats injection-based term twice (weights 0.3 and 0.2).

**Downstream effect:** Production. D3 and `overall_health` mis-rank staleness.

**Fan-out checked:** D22 GUI consumers.

**QuestDB impact:** READ-ONLY (may need persisted per-asset P1/P2 timestamps).

**Proposed fix direction:** Persist per-asset P1/P2 completion timestamps; remove duplicated weight.

**Needs Isaac:** YES (Q-19 — canonical source for "last P1/P2 re-run per asset").

---

### F-36 — D4 ignores spec inputs (modifier accuracy, PnL attribution); can yield scores >1.0

**Severity:** HIGH
(SA8-F02)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` Block 9 — "D4 | AIM Effectiveness Portfolio | Per-AIM modifier accuracy, PnL attribution by modifier direction".

**Code reference:** `[captain-offline/captain_offline/blocks/b9_diagnostic.py:347-419](captain-offline/captain_offline/blocks/b9_diagnostic.py)`.

**Divergence:** Driven by D02 inclusion weights and dormancy heuristics, not modifier hit-rate or directional PnL attribution. Components use hard-coded `/ 15.0` while system has 16 AIMs; can exceed 1.0 or go negative, violating "scored ∈ [0,1]".

**Downstream effect:** Production. D4 and `overall_health` not comparable to spec; numerically invalid.

**Fan-out checked:** D22 readers.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Implement per-AIM accuracy / directional PnL; clamp; divide by `max(n_aims, 1)`.

**Needs Isaac:** YES (Q-20 — definition of "modifier accuracy" / attribution window).

---

### F-37 — Weekly diagnostic omits D5; D7 backlog logic inverted

**Severity:** HIGH
(SA8-F03)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` Block 9 — "Run weekly (D1-D7) and monthly (D5 deep analysis)"; D5 "Monthly rolling expectancy and Sharpe trend"; D7 "Pending P1/P2 runs, candidate queue depth, injection backlog".

**Code reference:** `[captain-offline/captain_offline/blocks/b9_diagnostic.py:826-852, 426-506, 619-696](captain-offline/captain_offline/blocks/b9_diagnostic.py)`.

**Divergence:** (1) `run_diagnostic(mode="WEEKLY")` never calls `compute_d5`; weekly `overall_health` is mean of 7 vs monthly 8. (2) D5 uses EWMA-based edge only, not Sharpe trend. (3) D7 "Level 3 unresolved" treats `ACTIVE` assets as resolved and builds `truly_unresolved` from assets **not** in that set — opposite of spec.

**Downstream effect:** Production. Wrong scheduling for D5/D7; misleading health and action queue.

**Fan-out checked:** Orchestrator weekly/monthly.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Add weekly D5 (light) vs monthly D5 (deep); add Sharpe trend; fix L3 unresolved set logic; wire queue-depth sources.

**Needs Isaac:** YES (Q-21 — where do "pending P1/P2 runs" and "candidate queue depth" live).

---

### F-38 — AIM-01 VRP modifier ladder, overnight refinement, and Monday term diverge from canvas

**Severity:** HIGH
(SA9-F01)

**Spec reference:** `AIM System.canvas` AIM-01 + Pseudocode — `vrp_z>1.5→1.15`; `vrp_z<-1→0.85`; overnight refinement `IF overnight_z>1 AND base>=1: base+=0.05`.

**Code reference:** `[shared/aim_compute.py:251-289](shared/aim_compute.py)`.

**Divergence:** `_aim01_vrp` applies different step function (`0.70`/`0.85`/`1.10` per "DEC-01" comments), adds **Monday × 0.95**, omits canvas overnight refinement. Feature uses `vrp_overnight_z` 60d window vs canvas `z_score(vrp, 120d)`.

**Downstream effect:** Production. VRP leg of MoE shifts materially vs canvas.

**Fan-out checked:** `run_aim_aggregation` consumers; `b1_features.compute_all_features`.

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Realign to canvas; drop Monday term or add to canvas; align lookback.

**Needs Isaac:** YES (Q-22 — does internal DEC-01 supersede canvas).

---

### F-39 — AIM-03 GEX uses raw sign, omits z-score ladder and event multipliers

**Severity:** HIGH
(SA9-F02)

**Spec reference:** `AIM System.canvas` AIM-03 + Pseudocode — `gex_z<-1→0.85`; `gex_z>1→1.10`; `expiry_day×0.95`; `triple_witch×0.90`.

**Code reference:** `[shared/aim_compute.py:330-340](shared/aim_compute.py)`.

**Divergence:** Branches on raw `gex` (`>0→0.90`, else `1.10`), no z-score, no expiry/triple-witch multipliers.

**Downstream effect:** Production. GEX leg not comparable to canvas.

**Fan-out checked:** `compute_dealer_net_gamma → f["gex"] → _aim03_gex`.

**QuestDB impact:** NONE.

**Proposed fix direction:** Add `gex_z` (60d), three-branch rule, event multipliers from calendar/session metadata.

**Needs Isaac:** NO.

---

### F-40 — AIM-04 IVTS zone map, gap overlay, confidence diverge from canvas PROC

**Severity:** HIGH
(SA9-F03)

**Spec reference:** `AIM System.canvas` AIM-04 + Pseudocode — three branches `ivts>1→0.65`, `ivts>=0.93→1.10`, else `0.80`; gap `>2→×0.85`; `confidence=0.9 if extreme else 0.6`.

**Code reference:** `[shared/aim_compute.py:343-401](shared/aim_compute.py)`.

**Divergence:** Five-band map with breakpoints `1.10`/`1.0`, "quiet" band `0.90` for `[0.85,0.93)`. Gap overlay also applies `>1.0→×0.95` (not in canvas). EIA Wednesday `×0.90` for CL applied here but in canvas under AIM-06. Per-zone confidence not binary.

**Downstream effect:** Production. IVTS and gap modifiers differ in mid-range.

**Fan-out checked:** `b1_features` IVTS, gap, `is_eia_wednesday`; `aim_ab_test.ivts_expected_modifier` mirrors code (same divergence).

**QuestDB impact:** READ-ONLY.

**Proposed fix direction:** Collapse to three-branch logic; apply only `gap_z>2`; align confidence; relocate CL-EIA term.

**Needs Isaac:** YES (Q-23 — Paper 67 / DEC-03 vs canvas).

---

### F-41 — AIM-7 (COT) not registered in `compute_aim_modifier` dispatch; canvas mandates it

**Severity:** HIGH
(SA9-F05)

**Spec reference:** `AIM System.canvas` overview + AIM-07 node + MACRO Pseudocode `PROC aim_07`.

**Code reference:** `[shared/aim_compute.py:217-238](shared/aim_compute.py)` (no `7` in `dispatch`); `[captain-online/captain_online/blocks/b1_features.py:517-520, 626-630](captain-online/captain_online/blocks/b1_features.py)` (`cot_smi` / `cot_speculator_z` forced to None).

**Divergence:** `compute_aim_modifier(..., 7, ...)` returns `NO_HANDLER` (modifier=1.0, confidence=0.0). `_aim07_cot` exists but never registered.

**Downstream effect:** Production. No COT contribution to MoE; any ACTIVE AIM-7 in state/weights is a neutral placeholder.

**Fan-out checked:** `aim_feature_loader` (replay also nulls COT).

**QuestDB impact:** NONE.

**Proposed fix direction:** Wire `_aim07_cot` in dispatch and CFTC pipeline, OR amend canvas to "disabled until CFTC feed".

**Needs Isaac:** YES (Q-24 — is DEC-08 (no CFTC) the product decision).

---

### F-42 — L3 trigger has up-to-1-day delay (queued for daily dispatch instead of immediate)

**Severity:** HIGH
(SA10-F09)

**Spec reference:** `P3 Offline.canvas` Block 6 — "TRIGGER: L3 decay".

**Code reference:** `[captain-offline/captain_offline/blocks/b2_level_escalation.py:171-172](captain-offline/captain_offline/blocks/b2_level_escalation.py)` enqueues `AIM14_EXPANSION`; `[captain-offline/captain_offline/blocks/orchestrator.py:657-727, 869-915](captain-offline/captain_offline/blocks/orchestrator.py)` `_dispatch_pending_jobs` only from `_run_daily`.

**Divergence:** L3 schedules via queue, but `AIM14_EXPANSION` runs on daily schedule, not immediately on L3.

**Downstream effect:** Production. Up to ~1-day latency reacting to L3.

**Fan-out checked:** No `_dispatch_pending_jobs` from `_handle_trade_outcome`.

**QuestDB impact:** NONE.

**Proposed fix direction:** Call `_dispatch_pending_jobs()` after enqueue or on a short timer.

**Needs Isaac:** NO.

---

### F-43 — G-XCT-012: crash recovery is observational logging only, not state replay

**Severity:** HIGH
(SA10-F08)

**Spec reference:** `32_P3_Offline_Full_Pseudocode.md` Audit Resolutions — `G-XCT-012 — Crash Recovery Write-Only — CRITICAL RESOLVED`.

**Code reference:** `[captain-offline/captain_offline/main.py:124-128](captain-offline/captain_offline/main.py)` (`get_last_checkpoint` logged only); `[shared/journal.py:55-104](shared/journal.py)` (append + get_last_checkpoint; no replay API).

**Divergence:** Marked RESOLVED but startup does not branch on checkpoint to redo/abort partial work; journal is a write trail, not a recovery state machine.

**Downstream effect:** Production. Crash between multi-step updates relies on QuestDB `LATEST ON` semantics, not journal-driven replay.

**Fan-out checked:** `write_checkpoint` call sites.

**QuestDB impact:** NONE.

**Proposed fix direction:** Define minimal recovery actions per checkpoint enum or amend Audit Resolutions to drop "RESOLVED".

**Needs Isaac:** YES (Q-25 — what was "resolved" intended to mean for XCT-012).

---

## MEDIUM (24 findings)

---

### F-44 — PG-01 suppression/recovery not persisted to P3-D06

**Severity:** MEDIUM (SA1-F08)
**Spec ref:** `32` PG-01 — "LOG suppression/recovery event to P3-D06".
**Code ref:** `[b1_aim_lifecycle.py:291-305](captain-offline/captain_offline/blocks/b1_aim_lifecycle.py)`.
**Divergence:** Logger calls only; no durable D06 write.
**Downstream:** Production — no queryable audit of suppression/recovery.
**QuestDB:** SCHEMA CHANGE (additive event row) unless existing D06 table is repurposed.
**Fix:** INSERT structured events to agreed P3-D06 table.
**Needs Isaac:** YES (Q-26 — which D06 table/row shape).

### F-45 — PG-01 COLLECTING→WARM_UP uses trade-log count, not `raw_data_count(a)`

**Severity:** MEDIUM (SA1-F09)
**Spec ref:** `32` PG-01 — `IF raw_data_count(a) > 0`.
**Code ref:** `[b1_aim_lifecycle.py:132-141, 238-242](captain-offline/captain_offline/blocks/b1_aim_lifecycle.py)`.
**Divergence:** `observations_collected` counts D03 rows for the asset, not per-AIM raw_data_count.
**Downstream:** Production — COLLECTING flips without per-AIM readiness.
**QuestDB:** READ-ONLY.
**Fix:** Define per-AIM raw/feature readiness query.
**Needs Isaac:** YES (Q-27 — where is per-AIM raw_data_count defined).

### F-46 — `max_versions_per_component` not loaded from P3-D17

**Severity:** MEDIUM (SA1-F10)
**Spec ref:** `32` Version Snapshot Policy — `max_versions = P3-D17.system_params.max_versions_per_component or 50`.
**Code ref:** `[version_snapshot.py:28-37, 132-167](captain-offline/captain_offline/blocks/version_snapshot.py)`.
**Divergence:** Constant 50; no D17 read.
**Downstream:** Production — retention untunable.
**Fix:** Read from D17 with fallback 50.
**Needs Isaac:** NO.

### F-47 — `migrate_to_cold_storage` is DELETE-only

**Severity:** MEDIUM (SA1-F11)
**Spec ref:** `32` Version Snapshot Policy — `migrate_to_cold_storage(oldest)`.
**Code ref:** `[version_snapshot.py:149-167](captain-offline/captain_offline/blocks/version_snapshot.py)`.
**Divergence:** Pruned snapshots deleted, not archived externally.
**Downstream:** Production — long-tail compliance/forensics data lost.
**Fix:** Export pruned rows to cold storage before DELETE.
**Needs Isaac:** YES (Q-28 — DELETE-only acceptable, or real cold storage required).

### F-48 — α=0.3 smoothing not applied or persisted in PG-01C

**Severity:** MEDIUM (SA2-F05)
**Spec ref:** `22` §7 — α=0.3 applied to probability vector or logits; "implementation must fix one convention".
**Code ref:** `[b1_aim16_hmm.py:43-45, 133-160, 168-186](captain-offline/captain_offline/blocks/b1_aim16_hmm.py)`; `[canonical_schemas.py:316-327](shared/canonical_schemas.py)` no `smoothing_alpha` column.
**Divergence:** α echoed in-memory; `current_state_probs` not smoothed; α not persisted.
**Downstream:** Test/Latent — online has no D26 value to read; uses defaults.
**QuestDB:** SCHEMA CHANGE (additive `smoothing_alpha DOUBLE`) optional. See Q-03 in §4.
**Fix:** Apply one convention before persist; add column.
**Needs Isaac:** NO.

### F-49 — PG-07 bootstrap: pathwise pooling not nested per-`j` conditional draw

**Severity:** MEDIUM (SA3-F07)
**Spec ref:** `32` PG-07 — `FOR each sprint_length j IN range(1, max_sprint): cusum_values_at_j = compute_cusum_conditional_on_sprint(resample, j)`.
**Code ref:** `[b2_cusum.py:127-150](captain-offline/captain_offline/blocks/b2_cusum.py)`.
**Divergence:** Walks each resample once; appends `max(c_up, c_down)` per sprint step. Approximates marginal sprint-indexed highs, not the spec's nested conditional draw.
**Downstream:** Production — quantiles may differ from spec for ARL_0=200.
**Fix:** Match nested structure or amend spec.
**Needs Isaac:** YES (Q-29 — pathwise pooling acceptable).

### F-50 — Canvas Block 4 reads P2-D06/D07 from QuestDB; B4 takes them as caller args

**Severity:** MEDIUM (SA4-F07, SA11-F02)
**Spec ref:** `P3 Offline.canvas` Block 4 — "R: P2-D06,D07(QuestDB)"; doc 32 PG-10 names `P3-D00[asset].locked_strategy`.
**Code ref:** `[b4_injection.py:7-23](captain-offline/captain_offline/blocks/b4_injection.py)` — no P2 reads; callers supply `new_candidate` and PnL lists.
**Divergence:** Canvas vs implementation contract divergence; doc 32 collapses to D00; no P2 QuestDB tables exist.
**Downstream:** Production — integration contract.
**QuestDB:** Conditional SCHEMA CHANGE per Q-01 (prior audit) if Isaac requires separate P2 tables.
**Fix:** Amend canvas/R tags; document collapsed-into-D00 model.
**Needs Isaac:** YES (Q-01 from prior audit).

### F-51 — PG-10 omits `NOTIFY_GUI` and `RPT-05` generation

**Severity:** MEDIUM (SA4-F08)
**Spec ref:** `32` PG-10 Step 5 — `GENERATE RPT-05` + `NOTIFY_GUI(..., priority="HIGH")`.
**Code ref:** `[b4_injection.py:84-106](captain-offline/captain_offline/blocks/b4_injection.py)`.
**Divergence:** Persists to D06 only; no GUI alert or RPT-05 hook.
**Downstream:** Production — operators may miss new candidates.
**Fix:** Emit D10 notification row and call shared report generator.
**Needs Isaac:** NO.

### F-52 — PG-11 REJECT branch: no D06 log or D00 status update

**Severity:** MEDIUM (SA4-F09)
**Spec ref:** `32` PG-11 — `LOG rejection to P3-D06`; `P3-D00[asset].captain_status = "ACTIVE"`.
**Code ref:** `[orchestrator.py:449-454](captain-offline/captain_offline/blocks/orchestrator.py)`.
**Divergence:** REJECT returns immediately with no D06 append, no D00 status write.
**Downstream:** Production — REJECT decision invisible to audit / GUI.
**Fix:** Append outcome to D06; update D00 status.
**Needs Isaac:** NO.

### F-53 — PARALLEL_TRACK days default to 10 in handler vs spec 20

**Severity:** MEDIUM (SA4-F10)
**Spec ref:** `32` PG-10 — `recommendation = "PARALLEL_TRACK"; tracking_days = 20`.
**Code ref:** `[orchestrator.py:456-461](captain-offline/captain_offline/blocks/orchestrator.py)`; `[b4_injection.py:41-43, 145-147](captain-offline/captain_offline/blocks/b4_injection.py)`.
**Divergence:** B4 sets 20 in result; adoption handler defaults to 10 if Command omits.
**Downstream:** Production — PARALLEL runs 10 days instead of 20 if Command silent.
**Fix:** Default to 20 for PARALLEL_TRACK or require Command to echo B4.
**Needs Isaac:** NO.

### F-54 — Canvas DEPS unused: no `sklearn.isotonic`/`kneed` (PG-12); no `deap` (PG-13)

**Severity:** MEDIUM (SA5-F06)
**Spec ref:** `P3 Offline.canvas` Block 5/6.
**Code ref:** `[b5_sensitivity.py](captain-offline/captain_offline/blocks/b5_sensitivity.py)`, `[b6_auto_expansion.py](captain-offline/captain_offline/blocks/b6_auto_expansion.py)`.
**Divergence:** Neither imports nor uses; PG-13 uses hand-rolled GA.
**Downstream:** Production — documented isotonic/knee/DEAP behaviour absent.
**Fix:** Add deps + logic per canvas, OR update canvas to reflect consolidated implementation.
**Needs Isaac:** YES (Q-30 — implement DEPS or amend canvas).

### F-55 — PG-12 perturbation scoped to SL/TP only; complexity penalty not on `num_parameters(strategy)`

**Severity:** MEDIUM (SA5-F07)
**Spec ref:** `32` PG-12 — `FOR EACH param p IN base_params:`; `complexity_penalty = num_parameters(strategy) * penalty_coefficient`.
**Code ref:** `[b5_sensitivity.py:184-226](captain-offline/captain_offline/blocks/b5_sensitivity.py)`.
**Divergence:** Only SL/TP in grid; penalty uses `len(perturbable_params)` (typically 2), not full strategy parameter cardinality.
**Downstream:** Production — fragile dimensions in other strategy fields missed.
**Fix:** Derive perturbable keys from locked strategy; use `num_parameters` for penalty.
**Needs Isaac:** NO.

### F-56 — PG-13 search dims `OR_window` / `feature_idx` don't reach replay

**Severity:** MEDIUM (SA5-F08)
**Spec ref:** `32` PG-13 — search includes `OR_window`, features.
**Code ref:** `[b6_auto_expansion.py:72-80, 146-159, 235-248](captain-offline/captain_offline/blocks/b6_auto_expansion.py)`.
**Divergence:** `strategy_replay` called with threshold and SL/TP only; `or_window` and `feature_idx` not threaded through.
**Downstream:** Production — advertised search space partially exercised.
**Fix:** Thread OR window + feature selection into replay, or shrink spec.
**Needs Isaac:** NO.

### F-57 — TSM PG-14 GROW_CAPITAL ruin alert ignores `max_drawdown_limit` guard

**Severity:** MEDIUM (SA6-F04)
**Spec ref:** `32` PG-14 — `ELIF risk_goal == "GROW_CAPITAL" AND tsm.max_drawdown_limit:`.
**Code ref:** `[b7_tsm_simulation.py:164-166](captain-offline/captain_offline/blocks/b7_tsm_simulation.py)`.
**Divergence:** GROW_CAPITAL branch doesn't require `mdd_limit`; can emit HIGH for unconstrained accounts.
**Downstream:** Production — spurious TSM_ALERT volume.
**Fix:** Add the spec guard.
**Needs Isaac:** NO.

### F-58 — P3-D12 declared PG-14 input but never read

**Severity:** MEDIUM (SA6-F05)
**Spec ref:** `32` PG-14 — `INPUT: P3-D08, P3-D03, P3-D12`; `P3 Offline.canvas` — `R: P3-D08,D03,D12`.
**Code ref:** `[b7_tsm_simulation.py:1-24](captain-offline/captain_offline/blocks/b7_tsm_simulation.py)`; `[orchestrator.py:756-805](captain-offline/captain_offline/blocks/orchestrator.py)` loads only D08+D03.
**Divergence:** D12 listed but unread.
**Downstream:** Production / Replay — behaviour matches "D08+D03 only".
**Fix:** Either wire D12 (e.g. `sizing_override`) or amend spec.
**Needs Isaac:** YES (Q-31 — was D12 ever meant to influence MC).

### F-59 — `GENERATE RPT-07` not called from PG-14

**Severity:** MEDIUM (SA6-F06)
**Spec ref:** `32` PG-14 — `GENERATE RPT-07(P3-D08)`.
**Code ref:** No `RPT-07` in `captain-offline/`; reporting in `captain-command/.../b6_reports.py` not invoked from `b7`.
**Divergence:** Pseudocode's report step absent; relies on Command's daily report.
**Downstream:** Test/process audit — Offline-only deployments lack TSM compliance report at PG-14 time.
**Fix:** Add explicit call from Offline, or document Command-only RPT-07 satisfies PG-14.
**Needs Isaac:** YES (Q-32 — Command RPT-07 sufficient).

### F-60 — Version snapshots for D05 / D12 pass partial state

**Severity:** MEDIUM (SA1-F12, SA7-F05)
**Spec ref:** `32` Version Snapshot Policy — `state: deep_copy(get_current_state(component_id))`.
**Code ref:** `[b1_dma_update.py:164-166](captain-offline/captain_offline/blocks/b1_dma_update.py)`; `[b1_drift_detection.py:292-294](captain-offline/captain_offline/blocks/b1_drift_detection.py)`; `[b8_kelly_update.py:208-226](captain-offline/captain_offline/blocks/b8_kelly_update.py)`.
**Divergence:** Callers pass partial dicts; `state=None` (auto-load via `get_current_state`) not used.
**Downstream:** Production — weaker rollback fidelity for D02/D05/D12.
**Fix:** Pass `state=None` or merge with `get_current_state`.
**Needs Isaac:** NO.

### F-61 — PG-16C extra significance gate (`p_value > 0.05` or `n < 100` → β_b = 0) beyond spec

**Severity:** MEDIUM (SA7-F06)
**Spec ref:** `32` PG-16C — cold-start at `n < 10`, `cold_start = (n < 100)`; no p-value gate.
**Code ref:** `[b8_cb_params.py:186-188](captain-offline/captain_offline/blocks/b8_cb_params.py)`.
**Divergence:** Extra gate forces β_b=0; more conservative than spec.
**Downstream:** Production — β_b often 0.
**Fix:** Drop or feature-flag; or document as spec amendment.
**Needs Isaac:** YES (Q-33 — significance gate intentional).

### F-62 — RESOLVED event runs full weekly diagnostic, not D8-only

**Severity:** MEDIUM (SA8-F04)
**Spec ref:** `32` Block 9 — "D8 runs when ADMIN marks action item as RESOLVED".
**Code ref:** `[orchestrator.py:427-429](captain-offline/captain_offline/blocks/orchestrator.py)`; `[b9_diagnostic.py:826-852](captain-offline/captain_offline/blocks/b9_diagnostic.py)`.
**Divergence:** `ACTION_RESOLVED` calls `mode="WEEKLY"` (recomputes D1-D4, D6-D8).
**Downstream:** Production — extra D22 churn.
**Fix:** Add `mode="D8_VERIFY"` running `compute_d8` only.
**Needs Isaac:** NO.

### F-63 — `overall_health` is unweighted mean, not `weighted_mean(d1..d8)`

**Severity:** MEDIUM (SA8-F05)
**Spec ref:** `32` Block 9 — `overall_health = weighted_mean(d1..d8 scores)`.
**Code ref:** `[b9_diagnostic.py:841-854](captain-offline/captain_offline/blocks/b9_diagnostic.py)`.
**Divergence:** `sum/len`; weights implicit equal over present keys (7 weekly vs 8 monthly).
**Downstream:** Production — `overall_health` not comparable across cadences.
**Fix:** Fix weekly/monthly key set to 8; apply documented weights.
**Needs Isaac:** YES (Q-34 — official cross-dimension weights).

### F-64 — D22 persisted shape uses `scores`/`ts` vs spec `dimension_scores`/`timestamp`

**Severity:** MEDIUM (SA8-F06, SA11-F05)
**Spec ref:** `32` Block 9 — `P3-D22 = {dimension_scores, action_queue, overall_health, timestamp}`.
**Code ref:** `[b9_diagnostic.py:856-890](captain-offline/captain_offline/blocks/b9_diagnostic.py)`; `[canonical_schemas.py:509-524](shared/canonical_schemas.py)`.
**Divergence:** `scores` key (not `dimension_scores`); `ts` column (not `timestamp`); plus extra denormalised columns. Semantically aligned.
**Downstream:** Production — strict spec parsers fail.
**Fix:** Document as implementation contract or alias in API layer.
**Needs Isaac:** NO.

### F-65 — D8 verification mostly ignores stored pre-resolution metrics

**Severity:** MEDIUM (SA8-F07)
**Spec ref:** `32` Block 9 D8 — "Did previously resolved action items actually improve the target metric?".
**Code ref:** `[b9_diagnostic.py:703-819](captain-offline/captain_offline/blocks/b9_diagnostic.py)`.
**Divergence:** Most handlers re-query current state instead of comparing to `metric_snapshot_at_creation`.
**Downstream:** Production — false VERIFIED / false reopen decisions.
**Fix:** Thread snapshot into each branch; compare numerically.
**Needs Isaac:** NO.

### F-66 — AIM-06 calendar missing FOMC and CL+EIA multipliers

**Severity:** MEDIUM (SA9-F04)
**Spec ref:** `AIM System.canvas` MACRO Pseudocode — `IF CL+EIA: ×0.90. IF FOMC: ×0.85`.
**Code ref:** `[shared/aim_compute.py:404-434](shared/aim_compute.py)`.
**Divergence:** Tier/proximity only; no event-type multipliers.
**Downstream:** Production / Replay — combined modifier less event-specific.
**Fix:** Parse FOMC/CL+EIA from `events_today` and apply.
**Needs Isaac:** NO.

### F-67 — AIM-09 momentum uses MACD net sign vs strategy_direction agreement

**Severity:** MEDIUM (SA9-F06)
**Spec ref:** `AIM System.canvas` CROSS-ASSET — `IF agrees with strategy_direction: 1.10; disagree: 0.85`.
**Code ref:** `[shared/aim_compute.py:501-514](shared/aim_compute.py)`; `[b1_features.py:259-283](captain-online/captain_online/blocks/b1_features.py)`.
**Divergence:** `cross_momentum` is net MACD vote in [-1,1]; "disagree" → 0.90, not 0.85.
**Downstream:** Production / Replay — momentum semantics differ.
**Fix:** Compare cross-asset sign to locked strategy direction; use 0.85.
**Needs Isaac:** NO.

---

## LOW (17 findings)

---

### F-68 — Init-time CUSUM calibration runs B=2000 bootstrap twice per asset
(SA3-F08) Startup latency only. Fix: return limits from `calibrate_and_persist` and reuse. **Needs Isaac:** NO.

### F-69 — PG-09 win_rate uses daily P&L, not trade outcomes
(SA4-F11) Replay/Test metric interpretation. Fix: define on trade outcomes if D03 supplies multiple trades per day. **Needs Isaac:** NO.

### F-70 — PG-12/PG-13 NOTIFY_GUI replaced by logger only
(SA5-F09) Operators may miss FRAGILE / no-candidate states. Fix: reuse Redis `CH_ALERTS`. **Needs Isaac:** NO.

### F-71 — PG-13 discrete `range(...)` grids implemented as continuous sampling
(SA5-F10) Reproducibility vs spec text differs. Fix: encode discrete alleles. **Needs Isaac:** NO.

### F-72 — PG-14 `risk_goal` read from column, not `classification.risk_goal` JSON path
(SA6-F07) Possible wrong branch if writers don't duplicate the column. Fix: parse `classification` JSON with defined precedence. **Needs Isaac:** YES if writers don't always duplicate.

### F-73 — PG-14 PRESERVE_CAPITAL branch is in code but not in pseudocode
(SA6-F08) Extra Redis alerts. Fix: remove or add to spec. **Needs Isaac:** NO.

### F-74 — PG-15 `_get_cp_prob` defaults to 0.1 when D04 missing
(SA7-F07) Slow-learning EWMA when D04 absent. Fix: log warning when defaulting. **Needs Isaac:** NO.

### F-75 — D1 homogeneity action gated on `n_assets > 1` vs spec
(SA8-F08) Suppresses action for single-asset fleet. Fix: match spec or document. **Needs Isaac:** NO.

### F-76 — Block 9 canvas lists P2-D06 reads; b9 only reads D00 (locked copy)
(SA8-F09) OK if D00 is single SOR. Fix: document SOR. **Needs Isaac:** NO.

### F-77 — AIM-12 adds VIX_z overlay beyond canvas PROC
(SA9-F08) Stricter modifier in high-VIX. Fix: remove or fold systematic 0.95. **Needs Isaac:** YES (Q-35).

### F-78 — AIM-10 missing `high_vol_regime × 0.97` multiplier
(SA9-F07) Calendar effect weaker than spec. Fix: add `high_vol_regime` flag and multiply; set conf=0.3. **Needs Isaac:** NO.

### F-79 — `compute_aim_modifier` return shape missing `timestamp`
(SA9-F09) Consumers expecting `timestamp` get KeyError. Fix: add UTC `timestamp` to every return. **Needs Isaac:** NO.

### F-80 — `run_aim_aggregation` logging map duplicates key `7`
(SA9-F11) Mislabelled logs. Fix: use distinct label. **Needs Isaac:** NO.

### F-81 — CV-01: one-file-per-AIM canvas vs consolidated `shared/aim_compute.py`
(SA9-F10, SA10-F11) Structural divergence flagged once per SC-05. Fix: doc 32 amendment or split files. **Needs Isaac:** YES (Q-36 — confirm consolidation permanent).

### F-82 — CV-02: standalone module names in canvas vs block-prefixed implementation
(SA10-F12) Structural divergence flagged once. Fix: amendment to doc 32 + canvases with translation table. **Needs Isaac:** NO.

### F-83 — `combined_modifier:{asset}` Redis sink (canvas) vs in-process dict (code)
(SA10-F13) Production OK; external consumers see nothing. Fix: amend canvas or add Redis publish. **Needs Isaac:** NO.

### F-84 — No automated test covering `rollback_to_version`
(SA10-F14) Test gap. Fix: add integration test with D18 fixture + small D02/D12 restore. **Needs Isaac:** NO.

### F-85 — No CI job invoking `verify_schema_drift.py`
(SA11-F07) Schema drift may reach deploys undetected. Fix: add CI step (with QuestDB service or skip). **Needs Isaac:** NO.

### F-86 — No PG-01C unit tests
(SA2-F06) CI gap. Fix: synthetic 240×7 panel + PnL fixtures; assert `hmm_params` shape and INSERT payload. **Needs Isaac:** NO.

### F-87 — Drift state in QuestDB D04 vs canvas Redis `adwin:{aim_id}` and retrain flag
(SA10-F05) Internal consistency OK. Fix: amend canvas or add Redis mirrors for observability. **Needs Isaac:** NO.

### F-88 — `aim_modifiers:{asset}` Redis hash named in DMA canvas not implemented
(SA10-F06) Production OK if all consumers use `aim_compute`. Fix: amend canvas or add optional Redis cache writer. **Needs Isaac:** NO.

### F-89 — D17 (`system_params`) not snapshotted before writes despite VERSIONED_COMPONENTS membership
(SA10-F07) Rollback/version history incomplete for system params. Fix: wrap D17 writes with snapshot helper. **Needs Isaac:** NO.

### F-90 — PG-09 wiring is synchronous gate vs spec "proposed_update event"
(SA10-F10) Production OK; harder to test. Fix: document as intentional or add command topic for replay. **Needs Isaac:** NO.

### F-91 — P3-D04 nested BOCPD/CUSUM stored as flat STRING/scalar columns
(SA11-F04) Implementation detail; readers/writers consistent. Fix: document mapping. **Needs Isaac:** NO.

### F-92 — P3-D18 `timestamp` field stored as `ts` column
(SA11-F06) Naming-only. Fix: none. **Needs Isaac:** NO.

---

## 4. QuestDB Change Register

Three additive changes; one inherited from prior audit.

| # | Table | Change | Migration sketch | Backfill | Affected writers | Affected readers | Triggered by |
|---|---|---|---|---|---|---|---|
| Q-01 | `p2_d07_regime_models` (NEW) | **Inherited from prior audit (2026-04-22)**. Open until Q-01 in §6 is answered. | `CREATE TABLE p2_d07_regime_models (asset_id SYMBOL, model_type SYMBOL, model_blob STRING, pettersson_threshold DOUBLE, regime_label SYMBOL, regime_feature_list STRING, last_trained TIMESTAMP, last_updated TIMESTAMP) timestamp(last_updated) PARTITION BY MONTH WAL;` | From `data/p2_outputs/{ASSET}/p2_d07_*.json` if present | New offline writer (P2 build pipeline) | `b1_data_ingestion._load_regime_models` | F-05 from prior audit, F-50 here |
| Q-02 | `p3_d03_trade_outcome_log` | Add `model_m INT` (or `basket_id SYMBOL`) for basket/strategy id aligned with `p3_d25_circuit_breaker_params.model_m` | `ALTER TABLE p3_d03_trade_outcome_log ADD COLUMN model_m INT;` | NULL for historical rows; optional backfill from `aim_breakdown` / locked-strategy at trade time if available | `b7_position_monitor`, `paper_trader`, `shared/trade_source`, replay seeders | `b8_cb_params._load_trades_by_account_model`; future `P3-D03.filter(basket=*)` | F-06 |
| Q-03 | `p3_d26_hmm_opportunity_state` | Add `smoothing_alpha DOUBLE`; optional `observation_feature_manifest STRING` (JSON: ordered feature names + version) | `ALTER TABLE p3_d26_hmm_opportunity_state ADD COLUMN smoothing_alpha DOUBLE;` | `0.3` for existing rows (spec-fixed) | `b1_aim16_hmm.save_hmm_state` | Online HMM consumers (B5) | F-48 |

**No other schema work** is needed for the BLOCKING fixes:
- F-01 wires the existing pipeline; no new tables.
- F-02 reuses existing P3-D18.
- F-03 is a query/insert pattern fix; no schema change.
- F-04 reads existing P3-D06b.
- F-05 reuses existing P3-D01 column (re-encoded as JSON dict).

P2-D06 / P2-D07 absence (F-50) is logically a schema gap but Q-01 already covers it. The current code collapses both into `p3_d00_asset_universe.locked_strategy` JSON, which is a documentation divergence (canvas) that may be intentional architecture (V1 collapse).

## 5. Suggested Amendment Sequence

Dependency-ordered. Each step's prerequisites must complete first.

1. **Resolve clarifications** (Isaac, §6). The 17 questions block several fixes from being precisely scoped:
   - Q-01 (P2-D07 from prior audit) blocks Q-01 / F-50.
   - Q-06 (PG-16C basket key) blocks F-06 / Q-02.
   - Q-07 (canvas vs doc 32 BOCPD source) blocks F-07.
   - Q-11 (D26 owner) blocks F-16.
   - Others are non-blocking but tighten fix designs.

2. **Schema work** (independent, can start in parallel with §3):
   - Q-02 (`p3_d03_trade_outcome_log` add `model_m`) — required before F-06 fix.
   - Q-03 (D26 `smoothing_alpha`) — bundled with F-15/F-16 fix.
   - Q-01 (P2-D07 NEW) — only if Q-01 confirms separate dataset.

3. **F-01 fix** (wire PG-01C). Smallest BLOCKING change. Add `_run_aim16_training` driver to `_run_weekly` calling existing `train_aim16_hmm` + `save_hmm_state`. Before this, F-15 / F-16 are dormant (no writer). Bundle F-15 (build 7-D obs vector) into the same change since the driver needs it as input.

4. **F-03 fix** (P3-D04 partial-row INSERT pattern). Highest-leverage BLOCKING fix because Kelly L1's `cp_prob` is currently null on every read. Either merge BOCPD+CUSUM into a single per-trade INSERT, or rewrite readers to use `ASOF JOIN` on per-detector latest. Verify by checking `_get_cp_prob` returns non-default on real trade data.

5. **F-05 fix** (AIM-13 modifier wiring). Encode D01 `current_modifier` as JSON dict; verify FRAGILE → 0.85 reaches Online via `_aim13_sensitivity`.

6. **F-06 fix** (PG-16C basket key). Apply Q-02 schema migration; thread `model_m` through trade INSERT writers; PG-16C query then resolves correctly.

7. **F-02 fix** (versioned writes snapshots). Wrap D01/D02 INSERT paths in `b1_aim_lifecycle.py`, `b1_hdwm_diversity.py`, `b1_dma_update.py`, `b1_drift_detection.py` with `snapshot_before_update(component, trigger, state=None)`. Also fixes F-89 (D17 snapshots) and F-60 (partial state).

8. **F-04 fix** (PG-11 transition consumer). Add Online B6 consumer for `p3_d06b_active_transitions` that invokes `blend_signal`. Or amend spec.

9. **F-07/F-08 fix** (BOCPD source contract + rollback admin gate). Both depend on Isaac decisions but small once decided.

10. **HIGH-tier wiring fixes** (F-09..F-13, F-14, F-17..F-21):
    - F-17 (decay alert payload) — trivial; sequence first.
    - F-18 (trade-outcome bus name) — doc fix only.
    - F-09/F-10 (DMA active filter, HDWM) — small logic patches.
    - F-19/F-20 (BOCPD L2 debounce, CUSUM in-memory refresh) — small.
    - F-21 (programs_1_2_rerun) — needs Q-13 first.
    - F-11/F-12/F-13 (lifecycle + drift) — larger; can land later.
    - F-14 (TVTP) — only needed if Q-10 says TVTP is release-gate.

11. **Pseudotrader / injection / auto-expansion chain** (F-22..F-29). These compound; fix in order: F-23 (PG-09 metrics from D03 outcomes) → F-22 (gate uses correct replay path) → F-24 (PG-10 retroactive AIM) → F-25 (PG-10 alignment check) → F-27 (PG-12 PBO on full set) → F-28 (PG-13 OOS DSR) → F-26 (PG-13 candidate handoff) → F-29 (walk-forward train).

12. **TSM PG-14 fixes** (F-30, F-31, F-32, F-57). Reimplement `_block_bootstrap_path` per spec; bundle with F-32 (None for live accounts) and F-57 (GROW_CAPITAL guard).

13. **Diagnostic D3..D7** (F-35, F-36, F-37). Largest work item; needs Q-19, Q-20, Q-21.

14. **AIM modifier alignment** (F-38..F-41, F-66, F-67). Per-AIM fixes; can run in parallel after Q-22, Q-23, Q-24 are decided.

15. **G-XCT-012 / G-OFF-016 reconciliation** (F-43, F-22). Needs Q-25 / Q-14 to know what "RESOLVED" was supposed to mean.

16. **MEDIUM cleanup** (F-44..F-67) — once BLOCKING / HIGH chains are stable.

17. **LOW cleanup** (F-68..F-92) — including CV-01/CV-02 (F-81/F-82) doc amendments.

## 6. Clarifications for Isaac

Grouped by topic, smallest possible context, ordered by criticality.

### Schemas / external spec references
- **Q-01.** *(Inherited from prior audit.)* Should P2-D06/D07 be a separate QuestDB table (`p2_d07_regime_models`), kept collapsed into `p3_d00_asset_universe.locked_strategy` for V1, or sourced from `data/p2_outputs/` JSON files? Affects Q-01 schema item, F-50, prior audit's F-05.
- **Q-02.** Doc 32 cross-references `[[24_P3_Dataset_Schemas]]` and `[[31_AIM_Individual_Specifications]]`. Neither is in the offline corpus. Per Phase 0 we treated `shared/canonical_schemas.py` as authoritative for D26 schema and `AIM System.canvas` as authoritative for individual AIM modifier semantics. **Confirm both substitutions, or share the missing docs.**

### AIM-16 HMM / PG-01C
- **Q-03.** Should AIM-16 HMM training (PG-01C) run weekly per asset, weekly globally (session-shared model), or only on demand? Affects F-01 driver design.
- **Q-10.** Is **TVTP** a release gate, or is the time-homogeneous v1 acceptable? Affects F-14.
- **Q-11.** Who owns the write to `p3_d26_hmm_opportunity_state.opportunity_weights` — offline after training, online after PG-25B inference, or both with a merge policy? Affects F-16.

### Version snapshot policy / rollback
- **Q-08.** Doc 32 mandates `NOTIFY → ON admin_approval → restore_state` as a two-step gate. Code performs all three in one call after pseudotrader ADOPT. Is the automatic rollback intentional, or must the admin-approval gate be enforced? Affects F-08.
- **Q-25.** What was "G-XCT-012 — Crash Recovery Write-Only — CRITICAL RESOLVED" intended to mean — observational logging, or idempotent replay of partial PG-15/PG-02 writes? Affects F-43.
- **Q-28.** Is DELETE-only pruning of `p3_d18_version_history` acceptable, or is real cold-storage export required for compliance? Affects F-47.

### AIM lifecycle / DMA
- **Q-09.** Does the in-code DEC-05 dual warm-up (feature-days + trades) supersede doc 32's single observation-based warm-up for AIMs? Affects F-11.
- **Q-26.** Which P3-D06 table/row shape should record AIM suppression and recovery — `p3_d06_injection_history`, a new store, or another dataset? Affects F-44.
- **Q-27.** Where is authoritative `raw_data_count(a)` defined relative to the offline corpus (per-AIM feature store vs trade log)? Affects F-45.

### BOCPD / CUSUM
- **Q-07.** Which artifact is canonical when `Kelly 7 Layer Pipeline.canvas` says Redis `bocpd:{asset}` and doc 32 PG-15 says `P3-D04.current_changepoint_probability`? Code follows doc 32. Affects F-07.
- **Q-13.** What executable should `programs_1_2_rerun(asset)` invoke in automation — Command publish, shell pipeline, or third-party scheduler — and should `AWAITING_MANUAL` remain a terminal state? Affects F-21.
- **Q-29.** For PG-07, is the pathwise `max(c_up, c_down)` pooling at each sprint step an acceptable approximation to `compute_cusum_conditional_on_sprint(resample, j)`, or should the code match the nested `j` loop literally? Affects F-49.

### Pseudotrader / injection / auto-expansion
- **Q-04.** Who is the intended consumer of PG-11 `blend_signal` — Captain Online B6/B4, Command, or a not-yet-implemented module? Should `p3_d06b_active_transitions` be the contract? Affects F-04.
- **Q-14.** Is G-OFF-016 satisfied if DMA/Kelly gating uses `SignalReplayEngine` only, or must it use `captain_online_replay` / `shared.replay_engine.run_replay` per doc 32? Affects F-22.
- **Q-15.** For PG-09, should `actual_trade_outcome(d)` be strictly realised P&L from `p3_d03_trade_outcome_log` for that session day, or theoretical replay P&L from the pipeline? Affects F-23.

### Sensitivity / auto-expansion
- **Q-16.** Was a "PBO on best grid config" amendment formally adopted, superseding PG-12's `compute_CSCV_PBO(results, S=8)`? Affects F-27.
- **Q-30.** Should Block 5/6 implement canvas DEPS (`isotonic`, `kneed`, `deap`), or should the canvas be updated to reflect the consolidated numpy / custom-GA implementation? Affects F-54.

### TSM / Kelly
- **Q-31.** Was P3-D12 (e.g. `sizing_override`) ever meant to adjust TSM PG-14 MC inputs, or is its mention in spec/canvas a documentation artifact? Affects F-58.
- **Q-32.** Is PG-14 `GENERATE RPT-07` fully satisfied by Command's daily RPT-07, or must Offline emit/archive RPT-07 on each D08 `pass_probability` update? Affects F-59.
- **Q-17.** Exact definition of `running_loss_at_trade_time(t)` for PG-16C — loss-only cumulative, cross-day, per basket? Affects F-33.
- **Q-18.** For PG-16C, should `r_bar` be `mean(r_series)` (spec) or the OLS intercept from `r ~ L` (code)? Affects F-34.
- **Q-33.** Is the `p_value > 0.05` / `n < 100` zeroing of β_b in `b8_cb_params.py` an intentional override of doc 32 PG-16C? Affects F-61.

### System health diagnostic
- **Q-19.** Where should "last P1/P2 re-run per asset" live (column, table, file lineage) so D3 can be implemented without a global injection proxy? Affects F-35.
- **Q-20.** Exact offline definition of "per-AIM modifier accuracy" and "PnL attribution by modifier direction" for D4 (windows, labels)? Affects F-36.
- **Q-21.** Where are "pending P1/P2 runs" and "candidate queue depth" stored for D7? Affects F-37.
- **Q-34.** What are the authoritative cross-dimension weights for `overall_health` (doc 32 only gives within-D1 weights)? Affects F-63.

### AIM modifiers
- **Q-22.** Should DEC-01 / internal extraction docs override `AIM System.canvas` for AIM-01 (and similarly DEC-03 for AIM-04)? Affects F-38, F-40.
- **Q-23.** For AIM-04, is the 5-zone Paper 67 map the product truth, with the canvas updated later? Affects F-40.
- **Q-24.** Is AIM-7 (COT) officially out of scope until a CFTC feed (DEC-08), or should code match the canvas? Affects F-41.
- **Q-35.** For AIM-12, is the `vix_z > 1 → ×0.95` overlay required on top of the PROC's systematic 0.95? Affects F-77.

### Trade-outcome bus / consolidation
- **Q-12.** Name the canonical contract for the trade-outcome bus: stream key + payload schema. Canvas says `trades`; CLAUDE.md says `captain:trade_outcomes`; code uses `stream:trade_outcomes`. Affects F-18.
- **Q-36.** Is the consolidation in `shared/aim_compute.py` (CV-01) the long-term architecture, requiring canvas/doc amendments only? Affects F-81.
- **Q-06.** For PG-16C basket key on P3-D03, should the column be `model_m` (matching `p3_d25_circuit_breaker_params.model_m`) or a separate `basket_id` / `strategy_id`? Affects F-06 / Q-02.

---

*Audit complete. No code, config, or QuestDB modifications were made during this session. All findings are written to be patched in dependency order per §5; the read-only constraints in the original mandate were respected throughout. Subagent IDs (SA-N-FNN) are preserved next to each finding for traceability back to the parallel-explore raw outputs.*
