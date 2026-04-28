---
title: Captain Offline — Audit Decisions Log
date: 2026-04-27
companion_to: 2026-04-22_offline_spec_vs_code_audit_copy.md
companion_to: captain_offline_clarifications_for_isaac_2026-04-27.md
purpose: Authoritative answers to all clarification questions, ready for Cursor agent consumption when generating amendment plans.
status: 30 of 36 questions resolved; 6 require follow-up (see §3).
---

# Captain Offline — Audit Decisions Log

This document is the authoritative resolution layer that sits between the audit (`2026-04-22_offline_spec_vs_code_audit_copy.md`) and the per-phase amendment plans Cursor will execute. For every BLOCKING / HIGH finding that needed an Isaac decision, the answer is captured here in plain language with the originating finding ID, so any Cursor session can resolve "what should this fix do" by reading this doc + the corresponding F-finding entry.

---

## 1. Executive Summary

| Resolution status | Count | Notes |
|---|---|---|
| Resolved by spec (no Isaac needed) | 4 | Q-08, Q-12 (name only), Q-16, Q-18 |
| Resolved by Isaac | 26 | Direct answers below |
| Counter-questions to Nomaan / engineering call | 3 | Q-10, Q-30, Q-36 — recommendations in §3 |
| Partial / re-ask Isaac | 6 | Q-04, Q-11, Q-22, Q-23, Q-26, Q-27 — see §3 |
| Deferred (out of scope for this campaign) | 3 | Q-21, Q-25, Q-28 (treat as won't-fix in v1) |

**Schema migrations confirmed (3 additive, 1 ratification):**
1. `p3_d03_trade_outcome_log` — add `model_m INT` (Q-06)
2. `p3_d22_system_health_diagnostic` — add per-asset `last_p1p2_rerun_ts` column (Q-19)
3. `p2_d07_regime_models` — separate QuestDB table (Q-01)
4. `p3_d26_hmm_states` — ratify schema per Q-27 answer (no migration needed; document and align canonical_schemas.py)

**Net impact on the original 11-phase plan:** unchanged shape, but Phase 7 (PG-09/10/13 chain) grows because Q-14 commits us to building `captain_online_replay` for real instead of accepting `SignalReplayEngine`. Phase 10 (HMM) is gated on Q-10 (TVTP cost) — see §3.

---

## 2. Decisions by Group

### Group A — Schemas

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-01 | F-50 (prior) | **P2-D07 lives as a separate QuestDB table** `p2_d07_regime_models`. | Phase 1 schema migration. Online B1 reads from new table. |
| Q-02 | many | **`shared/canonical_schemas.py` is authoritative for schemas; `AIM System.canvas` is authoritative for individual AIM modifier semantics.** | No code change — confirms the substitutions we've been making. Where canvas and code disagree on a modifier (F-38, F-40), canvas wins per Q-22 / Q-23. |
| Q-06 | F-06 | **Add `model_m INT` to `p3_d03_trade_outcome_log`.** Column matches `p3_d25_circuit_breaker_params.model_m`. | Phase 1 schema migration. Writers (online B7, paper_trader, trade_source) must populate from active locked-strategy `m`. |

### Group B — AIM-16 / HMM

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-03 | F-01 | **PG-01C runs after every market trading session, globally (not per asset).** One shared HMM, retrained at each session close (NY, LON, APAC). | Phase 3 wiring + Phase 10. Add post-session hook to orchestrator (not weekly cron). |
| Q-10 | F-14 | **PENDING.** Counter-question on TVTP migration cost. See §3. | Recommended path: ship time-homogeneous v1, defer TVTP to a follow-up phase. |
| Q-11 | F-16 | **PARTIAL — re-ask.** Isaac confirmed PG-23 (online inference) wires through D26, and that "PG-23 should also run after each online inference". I'm interpreting that as: **dual-write — offline PG-01C writes `hmm_params` / `training_window` / `n_observations`; online PG-23 / PG-25B writes `current_state_probs` / `opportunity_weights` / `last_updated`** — but he didn't say this explicitly. See §3. |

### Group C — Pseudotrader / injection / auto-expansion

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-14 | F-22 | **Implement `captain_online_replay` for real** — rerun online B1–B6 in replay mode driven by historical bars. `SignalReplayEngine` does not satisfy G-OFF-016. | Major scope expansion in Phase 7. Will need a replay harness that reuses the actual online block code paths against historical features. |
| Q-15 | F-23 | **`actual_trade_outcome(d)` = strict realised P&L from `p3_d03_trade_outcome_log`** for that session day. Theoretical replay P&L is not acceptable. | PG-09 metrics rebuild — Sharpe / PBO / DSR computed from D03 realised series, paired with the signal that produced each trade. |
| Q-04 | F-04 | **PARTIAL — re-ask.** Isaac provided the PG-30 routing spec showing ADOPT_STRATEGY commands forward through Command to Offline (PG-11). What's still unclear: who actually **consumes** `blend_signal` during the transition window. Most likely answer = Online B6 reads `p3_d06b_active_transitions`, calls `blend_signal`, publishes the blended size via Command's signal_queue. See §3. |

### Group D — AIM lifecycle / DMA / suppression

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-09 | F-11 | **Bring code back to single observation-based gate** per doc 32 PG-01. Drop DEC-05 dual-gate. WARM_UP → ELIGIBLE on `progress >= 1.0` only; ELIGIBLE → ACTIVE on user activation only. | Phase 4. Unify GUI activation and cron paths. |
| Q-26 | F-44 | **PARTIAL — re-ask.** Isaac's answer covered HMM training (D03 → D26), not AIM suppression/recovery event logging. The original doc 32 instruction is `LOG suppression event to P3-D06`. Need an explicit answer on storage location for these events. See §3. |
| Q-27 | F-45 | **PARTIAL — re-ask.** Isaac pasted the D26 schema, which only covers AIM-16. The question was about `raw_data_count(a)` for AIMs 1–15 in PG-01's COLLECTING → WARM_UP transition. See §3. |

### Group E — BOCPD / CUSUM / Level Escalation

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-07 | F-07 | **Kelly L1 reads BOCPD `cp_prob` from Redis** (`bocpd:{asset}` key). Canvas wins; doc 32's QuestDB-only path is wrong. **Add a Redis writer in `b2_bocpd`** alongside the existing D04 write. | Phase 5. Writer = `b2_bocpd`. Reader (Kelly L1) switches from QuestDB to Redis. Doc 32 PG-15 should be amended to match — flag this as a doc edit for Isaac. |
| Q-13 | F-21 | **`AWAITING_MANUAL` is the correct terminal state.** The spec wording `SCHEDULE programs_1_2_rerun(asset)` is aspirational; no automation target exists. | Phase 3 close-out: amend the audit's F-21 status to "by-design, not a bug". Update doc 32 to remove the SCHEDULE wording (or add `MANUAL` annotation). Reclassified F-21 to RESOLVED on 2026-04-27 via Phase 3 doc-edit batch B5_F-21. |
| Q-29 | F-49 | **Implement the literal nested `j` loop** per spec. The pathwise `max(c_up, c_down)` pooling is not an acceptable approximation. | Phase 5. Rewrite `compute_cusum_conditional_on_sprint`. |

### Group F — AIM modifiers

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-22 | F-38 | **PARTIAL — re-ask.** Isaac confirmed 60-day lookback for `vrp_overnight_z` is fine. Did **not** address: (a) DEC-01 step function values `0.70/0.85/1.10` vs canvas `1.15/1.05/0.85`; (b) the Monday `× 0.95` term in code; (c) the missing canvas overnight refinement (`base += 0.05`). See §3. |
| Q-23 | F-40 | **PARTIAL — confirm only.** 5-zone Paper 67 map is the product truth for AIM-04. Did **not** explicitly confirm that the EIA Wednesday `× 0.90` overlay belongs on AIM-04 (where code has it) vs AIM-06 (where canvas has it). See §3. |
| Q-24 | F-41 | **AIM-7 (COT) stays disabled.** DEC-08 (no CFTC feed) is the product decision. | Phase 6. Update canvas to mark AIM-7 as DEFERRED rather than ACTIVE. Code's nulling of `cot_smi`/`cot_speculator_z` is correct. |
| Q-05 | F-05 | **Option (a): write D01 `current_modifier` as JSON dict** — `{"modifier": 0.85, "reason_tag": "AIM13_FRAGILE"}`. Keep the dispatch reader as-is. | Phase 2 persistence contract. Affects `b5_sensitivity.py` writer + B1 ingestion. |

### Group G — TSM / Kelly / Circuit Breaker

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-17 | F-33 | **`L_b` is per-basket, cross-day cumulative running loss** (filter `P3-D03` by basket, no daily reset). Code's signed cumulative same-day-with-reset is wrong on both axes. | Phase 8. **Confirmation needed on one sub-point:** "running loss" → loss-only accumulation (negative outcomes only) vs signed cumulative (all outcomes). I'm reading the spec wording as loss-only because that's what makes the OLS regression `r_i = r_bar + beta_b * L_b` interpretable. Flagged in §3 as soft re-ask. |
| Q-31 | F-58 | **TSM PG-14 must honour `D12.sizing_override`** when running its MC. | Phase 8. PG-14 inputs read sizing_override and apply to per-trade returns before bootstrap. |
| Q-32 | F-59 | **Offline owns RPT-07.** The spec's `GENERATE RPT-07(P3-D08)` is a real instruction, not aspirational. Daily Command RPT-07 does not satisfy. | Phase 8. Add RPT-07 generation to PG-14 after each `pass_probability` update. |
| Q-33 | F-61 | **Remove the `p_value > 0.05` zeroing of beta_b** — it's not in spec. **Keep** the `n < 10` cutoff (spec mandates conservative defaults below 10 obs) and the `cold_start = (n < 100)` flag (spec mandates this exact threshold). | Phase 8. Three-way change: drop p_value gate, keep n<10 zero-out, keep n<100 cold_start flag. |

### Group H — Block 9 system health diagnostic

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-19 | F-35 | **Add `last_p1p2_rerun_ts` column to `p3_d22_system_health_diagnostic`,** indexed per asset. | Phase 1 schema migration + Phase 9. Writer = whoever completes a P1/P2 rerun (likely Command or the offline manual-job dispatcher). |
| Q-20 | F-36 | **D4 = (a) hit rate** — modifier direction agrees with subsequent PnL sign. **Window = monthly.** | Phase 9. Replace inclusion-weight proxy with rolling monthly hit-rate per AIM. |
| Q-21 | F-37 (D7 part) | **DEFER.** D7 "pending P1/P2 runs" / "candidate queue depth" is out of scope for v1. | Phase 9: skip the D7 sub-dimension; weekly diagnostic runs D1–D6 + D8 only until queue infrastructure exists. Update doc 32 to reflect deferral. |
| Q-34 | F-63 | **Weighted mean is the operator** for `overall_health = weighted_mean(d1..d8)`. Specific cross-dimension weights are **not yet pinned** — Isaac confirmed the operator but didn't supply the weight vector. **Default to equal weights (1/8 each) for v1**, document as an open tuning parameter. See §3 (soft flag). |

### Group I — Governance / safety

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-25 | F-43 | **DEFER.** Crash recovery as observational logging is acceptable for v1. | Phase 11: amend audit Resolutions in doc 32 to remove "RESOLVED" implication of replay; rephrase as "checkpoint logging only — replay deferred". |
| Q-28 | F-47 | **PARTIAL — soft.** Isaac confirmed D18 is the snapshot location and `version_manager.py` is the module, but didn't explicitly address whether DELETE-only pruning of oldest entries is acceptable for compliance vs cold-storage export per spec. See §3. |
| Q-08 | F-08 | **Resolved by spec.** Doc 32 lines 167–168 are explicit on the two-phase admin-approval gate. Code currently violates this — must be split into `request_rollback` → admin signal → `commit_rollback`. | Phase 11. |

### Group J — Architecture / consolidation

| Q | Finding(s) | Decision | Implementation note |
|---|---|---|---|
| Q-30 | F-54 | **PENDING — engineering call.** See §3 for recommendation. | |
| Q-36 | F-81 | **PENDING — engineering call.** See §3 for recommendation. | |
| Q-12 (transport) | F-18 | **Keep Redis Streams** (`stream:trade_outcomes` with consumer groups). Spec name (`trades`) and CLAUDE.md (`captain:trade_outcomes`) both diverge — code wins. **Do not amend spec docs;** Isaac will note the divergence informally. | Phase 2. Deprecate the pub/sub publisher in `paper_trader.py` to avoid silent data loss. |

### Resolved-by-spec confirmations

| Q | Finding(s) | Resolution |
|---|---|---|
| Q-08 | F-08 | Doc 32 lines 167–168 explicit on `NOTIFY → ON admin_approval → restore_state`. |
| Q-12 (name) | F-18 | Three spec docs (P3 Offline canvas, DMA MoE canvas, doc 33 PG-27 line 435) unanimously call the bus `trades`. Transport is open per Q-12-transport above. |
| Q-16 | F-27 | Doc 32 line 470: `pbo = compute_CSCV_PBO(results, S=8)` — full grid, not single best cell. |
| Q-18 | F-34 | Doc 32 line 702: `r_bar = mean(r_series)`. |

---

## 3. Pending items — counter-questions and re-asks

These are the six items that need a follow-up answer before the corresponding phase can be planned cleanly. Three are engineering calls Nomaan asked me to make; three are partial/mismatched answers that need Isaac to weigh in again.

### 3.1 Engineering calls (Nomaan to confirm or push back)

**Q-10 — TVTP migration heaviness (F-14, Phase 10)**

`hmmlearn` doesn't support time-varying transitions. To get TVTP per doc 22 §2, options ranked by cost:

1. **Build TVTP layer on top of `hmmlearn`.** Train a time-homogeneous HMM, then post-process transition matrices per covariate bucket (e.g., one matrix for Mondays, one for Fridays). Cheapest. ~3–4 days. Approximation, not true TVTP.
2. **Custom EM with TVTP transitions in numpy/scipy.** Faithful implementation. ~1.5–2 weeks for someone with HMM background; longer if learning. Validation required against synthetic data with known regime shifts.
3. **Migrate to `pomegranate`.** Slightly more flexible than `hmmlearn` but still doesn't have native TVTP. Saves no real work over option 2.

**Recommendation: ship time-homogeneous v1, slot true TVTP as a Phase 10b follow-up.** Reasoning: F-01 shows training isn't even wired up today. Getting the basic loop running, observation builder working, and D26 dual-write established (per Q-11) is the bottleneck. TVTP without those is wasted work. Once v1 is stable for 2–4 weeks, Phase 10b implements option 2 with proper validation.

**Decision needed:** "agree, ship time-homogeneous v1" or "TVTP must be in v1 — accept the 2-week extension".

---

**Q-30 — Block 5/6 canvas DEPS (`isotonic`, `kneed`, `deap`) (F-54)**

Honest assessment of cost vs benefit:

- **`isotonic`** (sklearn.isotonic.IsotonicRegression). If code's custom numpy implementation produces equivalent output, swapping to sklearn buys you battle-tested code at the cost of one dependency line. Worth it if isotonic is non-trivially used; not worth it if it's a 20-line numpy thing that works.
- **`kneed`** (knee/elbow detection). Same calculus. The custom curvature-based approach in numpy is ~30 lines and behaves predictably on monotone curves. `kneed` adds robustness on noisy curves. Worth swapping only if you've seen the custom version misbehave.
- **`deap`** (genetic algorithms). Custom GA is harder to debug than `deap`, but rewriting on top of `deap` is a meaningful refactor (~2 days + tests). Cost is high; benefit is mainly maintainability if the GA evolves significantly.

**Recommendation: leave as-is, update canvas DEPS lines to reflect actual implementation.** The cost of swapping is real and the current code apparently works. Re-evaluate if any of these three components produces wrong output in practice.

**Decision needed:** "leave + amend canvas" or "swap one or more libraries — pick which".

---

**Q-36 — Per-AIM modules vs consolidated `shared/aim_compute.py` (F-81)**

Effort estimate for splitting `shared/aim_compute.py` into per-AIM modules (`aim_01_vrp.py`, `aim_02_skew.py`, ...):

- **Mechanical extraction:** ~2 days. Each `_aimNN_*` function moves to its own module; shared helpers stay in a `shared/aim_helpers.py`; dispatch table updated to import from the new locations.
- **Test split:** ~1 day. Existing tests for aim_compute split to per-module test files.
- **Risk:** low. No semantic change, only file layout.

It's not messy as long as the dispatch table is the only seam between caller and AIM logic (which it is per the canvas).

**Recommendation: defer until after the audit fix campaign closes.** Per-AIM modules are a hygiene refactor, not a correctness fix. Consolidated layout works for the campaign. Schedule as a Phase 12 cleanup once the 38 BLOCKING/HIGH findings are resolved. Update canvas after the refactor lands.

**Decision needed:** "defer to Phase 12" or "do it now as part of Phase 6 (AIM modifier realignment)".

### 3.2 Re-asks for Isaac (partial or mismatched answers)

These should be batched into one short follow-up message rather than asked individually.

**Q-04 — `blend_signal` consumer (F-04).** Isaac provided PG-30 routing spec, which confirms ADOPT_STRATEGY commands flow Command → Offline → PG-11. What's still missing: who reads `p3_d06b_active_transitions` during the transition window and applies the blended size? My reading is **Online B6** — it should detect active transitions, call `blend_signal`, and publish the blended-size signal via Command's signal_queue. Need explicit confirmation of (a) the consumer location is Online B6, and (b) PG-11 writes `p3_d06b_active_transitions` and Online B6 reads it.

**Q-11 — D26 dual-write boundary (F-16).** Isaac said offline PG-01C writes after each session AND "PG-23 should also run after each online inference". My interpretation: **offline PG-01C writes `hmm_params` / `training_window` / `n_observations`; online PG-23 / PG-25B writes `current_state_probs` / `opportunity_weights` / `last_updated`**. Need confirmation that this is the intended split, or correction if both write all fields with last-write-wins semantics.

**Q-22 — DEC-01 vs canvas for AIM-01 (F-38).** Isaac confirmed 60-day lookback for `vrp_overnight_z`. Three sub-questions still open:
- Step function: canvas says `vrp_z>1.5→1.15`, `>0.5→1.05`, `<-1→0.85`. Code says `0.70`/`0.85`/`1.10` (per DEC-01 comments). Which is correct?
- Code adds `Monday × 0.95`. This is not in canvas. Keep, drop, or formalise into canvas?
- Canvas specifies `IF overnight_z>1 AND base>=1: base+=0.05` overnight refinement. Code omits. Should this be added back, or is omission intentional?

**Q-23 — EIA Wednesday relocation (F-40).** Isaac confirmed 5-zone Paper 67 map for AIM-04. What about the EIA Wednesday `× 0.90` overlay for CL? Canvas has it under AIM-06 (Economic Calendar). Code applies it inside AIM-04. Is the relocation intentional, or should it move back to AIM-06?

**Q-26 — P3-D06 record shape for AIM suppression/recovery (F-44).** Isaac's answer addressed PG-01C HMM training (D03 → D26), not AIM lifecycle event logging. Doc 32 PG-01 lines 69 / 81 say `LOG suppression event to P3-D06`. Concrete question: is `p3_d06_injection_history` the table (current code uses it), should we add a new `p3_d06_aim_lifecycle_events` table, or is there an existing store we should be using?

**Q-27 — `raw_data_count(a)` for AIMs 1–15 (F-45).** Isaac's answer was the D26 schema for AIM-16. Question is about the 15 non-HMM AIMs: in PG-01's COLLECTING → WARM_UP gate (`IF raw_data_count(a) > 0`), what does `raw_data_count` count, and where is it persisted? Per-AIM feature row count? Trade log row count attributable to that AIM? A new counter?

### 3.3 Soft flags (low-priority confirmations)

These are not blocking but worth flagging to Isaac so he can correct if my interpretation is off:

- **Q-17 (F-33).** I'm reading "running_loss_at_trade_time" as loss-only cumulative (negative outcomes only) because that's what makes the OLS regression `r_i = r_bar + beta_b * L_b` interpretable. If Isaac means signed cumulative across the basket, the resulting `beta_b` has different semantics. Worth a one-line confirmation.
- **Q-28 (F-47).** Spec says `migrate_to_cold_storage(oldest)`; code does DELETE. If compliance requires real cold-storage export, this is a data-retention requirement and we need an export target. If DELETE is acceptable, we just amend the spec.
- **Q-34 (F-63).** Default to equal weights (1/8 each) for `overall_health`. Document as a tunable parameter for later calibration.

---

## 4. Schema migration summary

Single source of truth for Phase 1.

### 4.1 New tables

**`p2_d07_regime_models`** — separate table per Q-01a. Columns TBD from existing JSON shape; should mirror what online B1 currently expects when reading regime_models.

### 4.2 Additive column changes

**`p3_d03_trade_outcome_log`**
- Add `model_m INT` (Q-06). Populated at trade-outcome write time from active locked-strategy `m` for that asset. Writers: online B7 `b7_position_monitor`, `paper_trader.py`, `shared/trade_source.py`.

**`p3_d22_system_health_diagnostic`**
- Add `last_p1p2_rerun_ts TIMESTAMP` per asset (Q-19). Populated by whatever process completes a P1/P2 rerun for that asset. Read by D3 staleness scoring in `b9_diagnostic.py`.

### 4.3 Schema ratifications (no migration; align canonical_schemas.py)

**`p3_d26_hmm_states`** per Q-27 / Q-11 — confirm columns:
```
hmm_params | current_state_probs | opportunity_weights | prior_alpha
| last_trained | training_window | n_observations | cold_start | last_updated
```
Writer split per Q-11 interpretation (subject to confirmation): offline PG-01C owns `hmm_params`, `training_window`, `n_observations`, `last_trained`; online PG-23/PG-25B owns `current_state_probs`, `opportunity_weights`, `last_updated`.

### 4.4 Pending — possibly schema-affecting

- Q-26 outcome may add a `p3_d06_aim_lifecycle_events` table.
- Q-27 outcome may add a per-AIM feature row counter.

Defer until Isaac re-answers.

---

## 5. Phase plan delta

Net changes to the original 11-phase structure based on these answers:

| Phase | Status / change |
|---|---|
| Phase 0 — Isaac clarifications | ~80% complete; 6 follow-ups in §3.2 + 3 engineering calls in §3.1 still open. |
| Phase 1 — Schemas | Scope confirmed (3 tables touched). Can start once §3.2 Q-26 / Q-27 land (they may add schema items). |
| Phase 2 — Persistence contracts | No change. F-05 fix shape confirmed (JSON dict envelope). F-18 keeps Streams. |
| Phase 3 — Orchestrator wiring | F-21 reclassified — `AWAITING_MANUAL` is by-design, not a bug. Saves ~0.5 day. |
| Phase 4 — AIM lifecycle / DMA / HDWM | F-11 simplified — single-gate restoration. Q-26 / Q-27 outcomes feed in. |
| Phase 5 — BOCPD / CUSUM | Adds Redis writer for `bocpd:{asset}` (Q-07). CUSUM nested loop (Q-29) confirmed. |
| Phase 6 — AIM modifier realignment | AIM-7 stays disabled (Q-24). AIM-13 dict envelope (Q-05). AIM-01 / AIM-04 partly confirmed; awaiting Q-22 / Q-23 sub-answers. |
| Phase 7 — PG-09 / PG-10 / PG-13 chain | **Scope expansion.** Q-14 commits us to building `captain_online_replay` for real. Add ~5–8 days. Q-15 confirms realised-P&L metrics. |
| Phase 8 — TSM PG-14 + CB params | Confirmed: sizing_override honoured (Q-31), Offline RPT-07 (Q-32), drop p_value gate / keep n<10 / keep cold_start (Q-33). Q-17 soft confirm needed. |
| Phase 9 — Block 9 diagnostic | D7 deferred (Q-21). D4 = monthly hit rate (Q-20). D3 schema column (Q-19). Equal weights for overall_health (Q-34). |
| Phase 10 — HMM / AIM-16 | Gated on Q-10. If time-homogeneous v1 accepted: ~5 days. If TVTP required in v1: +10 days. |
| Phase 11 — Governance / safety | Crash recovery deferred (Q-25). Rollback two-phase (Q-08). Cold-storage Q-28 soft flag. |
| **Phase 12 — Hygiene refactor (NEW)** | Per-AIM module split (Q-36 deferred here). |

---

## 6. Cross-references

- Audit document: `2026-04-22_offline_spec_vs_code_audit_copy.md` (38 findings)
- Original questions: `captain_offline_clarifications_for_isaac_2026-04-27.md`
- Spec authority chain (per Q-02): `shared/canonical_schemas.py` (schemas) → doc 32 (PG semantics) → AIM canvas (modifier semantics) → other canvases (wiring annotations)
- BOCPD implementation guide: `BOCPD_Implementation_Guide.md` (referenced in Q-07 / Phase 5)

---

*This document is authoritative for the audit fix campaign. When generating amendment plans, Cursor should resolve "what should this fix do" by reading the corresponding F-finding entry in the audit + the matching row in §2 of this doc. Pending items in §3 must be cleared before the affected phases can ship.*