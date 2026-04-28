# Amendment questionnaire — deferred gaps & discrepancies

Fill in answers inline (or copy to your notes). Each item ties to **blocked batches**, **partial fixes**, or **open confirmations** from the consolidated execution report and the 2026-04-22 offline audit. Use your answers to drive doc amendments and follow-on build-plan batches.

---

## How to search your spec library

Use the **Spec search keywords** lines under each subsection — they match **doc 32** section tags (`PG-xx`), **canvas** node text, **dataset** short names (`P3-Dxx`, `P2-Dxx`), **audit finding IDs** (`F-xx`), and **programme decisions** (`DEC-xx`, `G-OFF-xxx`, `G-XCT-xxx`).

| Tag | Meaning |
|-----|---------|
| **PG-xx** | `32_P3_Offline_Full_Pseudocode.md` — pseudocode block PG-xx |
| **Block N** | Captain **Offline** architecture block (see `P3 Offline.canvas` / doc 32 block headers) — maps to `captain-offline/.../bN_*` modules |
| **CO** | `captain-offline` |
| **ON** | `captain-online` |
| **CMD** | `captain-command` |
| **SH** | `shared/` (cross-cutting) |
| **DB** | QuestDB schema / `canonical_schemas.py` |
| **RS** | Redis keys / streams / pub-sub |

**Offline block ↔ module map (typical):**

| Block | Topics (doc 32 / package) | Example files / PG refs |
|-------|---------------------------|-------------------------|
| **1** | AIM lifecycle, DMA, HDWM, drift, AIM-16 HMM | `b1_*`, **PG-01–04**, **PG-01C** |
| **2** | BOCPD, CUSUM, level escalation | `b2_*`, **PG-05–08** |
| **3** | Pseudotrader, DMA/Kelly gate | `b3_*`, **PG-09**, G-OFF-016 |
| **4** | Injection, transition phasing | `b4_*`, **PG-10**, **PG-11** |
| **5** | Sensitivity, PBO grid | `b5_*`, **PG-12** |
| **6** | Auto-expansion, GA | `b6_*`, **PG-13** |
| **7** | TSM Monte Carlo | `b7_*`, **PG-14**, RPT-07, P3-D08 |
| **8** | Kelly layers, CB params | `b8_*`, **PG-15**, **PG-16C**, P3-D12, P3-D25 |
| **9** | System health diagnostic | `b9_*`, **D1–D8 dimensions**, `overall_health` |

---

## A. Blocked implementation decisions (need a single chosen direction)

### A1 — PG-11 transition blending (`F-04`, audit **Q-04**)

**Spec search:** `PG-11`, `transition_days`, `blend_signal`, `TransitionPhaser`, `p3_d06b_active_transitions`, `ADOPT`, `injection_comparison`, **Block 4**, **PG-10**

**Components:** **CO** (`b4_injection.py`), consumer TBD → likely **ON** `b6_signal_output.py` / sizing path (**PG-11** consumer gap)

**Datasets:** **P3-D06**, **P3-D06b** (`active_transitions`)

1. Who **consumes** `blend_signal` / reads `p3_d06b_active_transitions` for live sizing — **ON only**, **CMD**, **both**, or **defer** until a named milestone?
2. Should blended sizing apply at **ON B6** (signal output), **ON B7** (position monitor / execution boundary), or elsewhere?
3. Confirm **read/write contract**: which columns and row lifecycle writers/readers must honour (`p3_d06b_*`, transition window expiry).

---

### A2 — AIM suppression / recovery audit trail (`F-12`, audit **Q-26**)

**Spec search:** `PG-01`, `SUPPRESSED`, `ACTIVE`, `meta_weight`, consecutive trades, **AIM suppression**, **injection history**, **Block 1**, **PG-06** (if tied to regime narrative — verify your corpus)

**Components:** **CO** `b1_aim_lifecycle.py`, `b1_dma_update.py`; persistence → **DB** (`p3_d06_*` family)

**Datasets:** **P3-D01**, **P3-D02**, **P3-D06** (`p3_d06_injection_history` vs new table)

4. Log suppression/recovery to **`p3_d06_injection_history`**, **new table**, or other — **minimum columns** (who/when/aim_id/asset/from_state/to_state/reason)?
5. **Append-only** only, or **queryable in compliance/GUI** (**CMD** `b2_gui_data_server` consumers)?

---

### A3 — AIM-04 remaining canvas vs Paper 67 (`F-40`, audit **Q-23** — Phase 6 batch 6.4)

**Spec search:** `AIM-04`, `IVTS`, `ivts`, gap overlay, **EIA**, **CL**, **triple witch**, confidence tier, **Paper 67**, **DEC-03**, `AIM System.canvas`, **PG modifiers** (online path)

**Components:** **SH** `aim_compute.py`, **ON** `b1_features.py`; docs **AIM System.canvas** / **AIM System 1.canvas**

**Dataset / feeds:** features feeding IVTS gap — often **P3** feature bars / options context

6. **Gap overlay:** ×0.95 when gap_z > 1 (code) vs canvas-only — authoritative source?
7. **EIA Wednesday ×0.90 for CL:** under **AIM-04** vs **AIM-06** per canvas — split?
8. **Per-zone confidence:** binary (canvas) vs graded (Paper 67) — which wins?
9. Other **AIM-04** Paper 67 rules required before “canvas parity”?

---

### A4 — AIM-7 COT (`F-41`, audit **Q-24**)

**Spec search:** `AIM-07`, `COT`, `cot`, **CFTC**, **DEC-08**, `compute_aim_modifier`, **MoE**, **Block 1** / online features

**Components:** **SH** `aim_compute.py` dispatch; **ON** `b1_features.py` (COT nulling); feeds external

10. AIM-7 **out of scope** until CFTC (**DEC-08**) vs register **`_aim07_cot`** now with neutral/failsafe behaviour?
11. If in scope: **data feed contract** and **fallback** when feed is down?

---

### A5 — Trade-outcome bus canonical contract (`F-18`, audit **Q-12**)

**Spec search:** `trade_outcomes`, `trades`, **Redis stream**, `captain:trade_outcomes`, `stream:trade_outcomes`, **CH_TRADE_OUTCOMES**, **STREAM_TRADE_OUTCOMES**, `paper_trader`, **P3 Offline.canvas** TRIGGER, **CLAUDE.md** Redis channels

**Components:** **ON** `b7_position_monitor.py` (publish), **CO** orchestrator (consume), **SH** `redis_client.py`, **scripts** `paper_trader.py`

**RS + DB:** stream key vs pub/sub; **P3-D03** writes

12. Single **authoritative** mechanism: **stream name**, **payload schema**, **deprecation** for legacy pub/sub names?

---

## B. Circuit breaker & PG-16C semantics

### B1 — `running_loss_at_trade_time` (`F-33`, audit **Q-17**)

**Spec search:** `PG-16C`, `β_b`, `L_series`, `r_bar`, basket `b`, **circuit breaker**, **P3-D25**, `running_loss`, expectancy regression, **Block 8**

**Components:** **CO** `b8_cb_params.py`; consumers **ON/CMD** circuit-breaker paths (`b5c_*`)

**Datasets:** **P3-D03** (trades), **P3-D25** (CB params)

13. **`L_b` at each trade:** loss-only cumulative vs signed P&amp;L; **within-day vs cross-day**?
14. Do profitable runs **reset** the running-loss series?

---

### B2 — Doc alignment after code changes (audit **Q-33** / PG-16C)

**Spec search:** `PG-16C`, `p_value`, significance, **β_b zero**, cold-start, **F-61**, **Block 8**

**Components:** **CO** `b8_cb_params.py`; **doc 32** text vs implementation

15. Removing **p-value zeroing of β_b** — confirm **product truth**; amend **doc 32 PG-16C** or revert code?

---

## C. HMM / AIM-16 (`F-14`, audit **Q-03**, **Q-10**, **Q-11**)

### C1 — Training & inference policy

**Spec search:** `PG-01C`, **AIM-16**, **HMM**, **Baum-Welch**, **TVTP**, `hmmlearn`, **P3-D26**, `opportunity_weights`, **session budget**, doc **22_HMM_Opportunity_Regime**, **Block 1**

**Components:** **CO** `b1_aim16_hmm.py`, `orchestrator.py` (`SESSION_CLOSE`, `_run_aim16_hmm_training`); **ON** `hmm_inference_block.py`, `orchestrator.py`

**Datasets:** **P3-D26** (`p3_d26_hmm_opportunity_state`)

16. **Cadence:** per asset / session-global / weekly / **SESSION_CLOSE**-only / mixed — final rule?
17. **TVTP** — **release gate** vs **time-homogeneous v1** until Phase 10b (search: **Q-10**, **F-14**)?
18. **D26 merge:** offline training row vs online inference row — conflict resolution for `current_state_probs`, `opportunity_weights`, `prior_alpha` (**Q-11**)?

---

### C2 — Engineering placeholders (Phase 10 handoff)

**Spec search:** `probs_to_ny_lon_apac`, NY / LON / APAC session weights, **forward filter**, smoothing, `[CONFIRM]`, **doc 33** (if referenced for online HMM)

**Components:** **SH** `hmm_online_inference.py`; **ON** inference persist

19. **`probs_to_ny_lon_apac`:** approve heuristic vs config vs temporary?
20. Run online inference **every session** (ingestion OK) vs **only when AIM-16 ACTIVE** in **P3-D01**?

---

## D. Diagnostics & doc 32 parity (`F-37`, audit **Q-21**, **Q-34**, Phase 9 optional B5)

### D1 — Scheduling & dimensions

**Spec search:** `Block 9`, **D1–D8**, `D3` staleness, `D4` AIM effectiveness, `D5` edge trajectory, `D7` backlog, **`research_pipeline`**, **`overall_health`**, weekly vs monthly, **P3-D22**, **P3-D22b**, **PG** system health pseudocode sections in doc 32

**Components:** **CO** `b9_diagnostic.py`; readers **CMD** GUI / reports

**Datasets:** **P3-D22**, **P3-D22b**, **P3-D03**, job queues (`p3_offline_job_queue` etc. — confirm in schemas)

21. **Weekly** run: add **light D5** (edge trajectory) — yes/no; **frequency**?
22. **`research_pipeline` / D7:** reintroduce queue-depth / pending P1–P2 — **which tables/queues**; **minimum fields**?
23. **`overall_health`:** **equal weights** (code) vs **doc 32 weights** — authoritative (**Q-34**)?

---

## E. Crash recovery & governance (`F-43`, audit **Q-25**, **Q-28**, Phase 11)

### E1 — G-XCT-012 intent

**Spec search:** **G-XCT-012**, crash recovery, journal, checkpoint, **`shared/journal.py`**, **Audit Resolutions**, write-only, replay

**Components:** **CO** `main.py`, orchestrator multi-step writes; **SH** `journal.py`

24. **“Resolved”** means: logging only / **idempotent replay** / runbook / other — **scope** (**which PG-xx** segments after crash)?

---

### E2 — Version history retention

**Spec search:** **G-OFF-046** (rollback governance — related), **Q-28**, `p3_d18_version_history`, cold storage, DELETE pruning, **`version_snapshot.py`**, **Version Snapshot Policy**, **PG** versioned components **P3-D01**, **P3-D02**, **P3-D05**, **P3-D12**, **P3-D17**

**Components:** **CO** `version_snapshot.py`; compliance stance

25. **DELETE-only pruning** acceptable vs **mandatory cold-storage export** — **retention period**?

---

### E3 — Rollback proposals (Phase 11 behaviour)

**Spec search:** `request_rollback`, `commit_rollback`, **FAILED_REGRESSION**, **Redis** `captain:rollback_proposal`, admin approval gate, **two-phase rollback**

**Components:** **CO** `version_snapshot.py`; **CMD** optional admin tooling

26. After **`FAILED_REGRESSION`**: **retry commit** / **new `request_rollback`** / other?

---

## F. Pseudotrader / replay / Phase 12 roadmap

### F1 — Intraday fidelity (`Phase 7` deferral)

**Spec search:** **PG-09**, `captain_online_replay`, **`replay_session`**, intraday bars, **P3-D34** / bar storage roadmap, **SignalReplayEngine**, **G-OFF-016**

**Components:** **SH** `online_replay.py`, `replay_engine.py`; **CO** `b3_pseudotrader.py`

**Datasets:** bar tables (**P3-D29**, hypothetical **intraday** table — search schemas)

27. Priority: **1-minute bar storage** before trusting **intraday PG-09** gates — required / nice-to-have / out of scope?

---

### F2 — Legacy callers & deletion (`Phase 12`)

**Spec search:** **SignalReplayEngine**, `replay_engine.run_replay`, **`delegate_to_replay_session`**, **PG-12** sensitivity grid (`b5_sensitivity`), deprecation warnings, **`run_signal_replay_comparison`**

**Components:** **SH** `signal_replay.py`, `replay_engine.py`; **CO** `b5_sensitivity.py`, `b3_pseudotrader.py`

28. **Timeline** to delete legacy replay stack after **`b5_sensitivity`** migration — cutoff date?
29. **`captain_online_replay`** wrapper kwargs **`cached_bars` / `baseline_result`** — confirm **safe to remove**?

---

### F3 — Strict PG-09 outcomes (audit **Q-15**)

**Spec search:** **PG-09**, `actual_trade_outcome`, **P3-D03**, realised vs replay P&amp;L, **Sharpe**, **PBO**, **D11** pseudotrader persistence

**Components:** **CO** `b3_pseudotrader.py`; **SH** `trade_source.py`

30. **D03 realised P&amp;L** always wins vs **replay P&amp;L** for gates — one-sentence rule?

---

## G. Drift detection (`F-13`)

### G1 — Feature source

**Spec search:** **PG-04**, drift, **ADWIN**, autoencoder, `get_aim_input_features`, **`TODO[F-13]`**, **Block 1**, `b1_drift_detection.py`

**Components:** **CO** `b1_drift_detection.py`, `orchestrator.py` `_run_daily`

31. Target: **per-AIM QuestDB vectors** — **which tables/pipelines** first?
32. Interim: **modifier-JSON + AE bootstrap** — acceptable with **sunset date**, or **not production-ready**?

---

## H. Schema & corpus substitutions (audit **Q-01**, **Q-02**, **Q-06**)

### H1 — P2 research outputs

**Spec search:** **P2-D07**, `p2_d07_regime_models`, regime classifier, **Pettersson**, locked strategy, **P3-D00**, `_load_regime_models`, **Block 2** online ingestion regime usage

**Components:** **ON** `b1_data_ingestion.py`; **DB** migrations Phase 1

33. **`_load_regime_models`:** move to **SELECT P2-D07** vs stay **P3-D00 locked_strategy** vs hybrid — **when**?

---

### H2 — Missing external docs

**Spec search:** `[[24_P3_Dataset_Schemas]]`, `[[31_AIM_Individual_Specifications]]`, **canonical_schemas**, **SC-03**, dataset authority

**Components:** **SH** `canonical_schemas.py`; docs corpus cross-ref

34. **`canonical_schemas.py`** authoritative if **24** absent — yes/no?
35. **`model_m`** vs **`basket_id`** — **final column name** linking **P3-D03** to baskets (**Q-06**, **PG-16C**).

---

## I. Minor product confirmations (`[CONFIRM]` / audit tails)

### I1 — DMA / suppression float equality (`F-12` implementation detail)

**Spec search:** **PG-02**, DMA, **inclusion_probability**, suppression consecutive trades, **Redis** `aim_counters`

**Components:** **CO** `b1_dma_update.py`, `b1_aim_lifecycle.py`

36. **`new_prob == 0`** exact vs **epsilon** band for suppression counters?

---

### I2 — AIM-03 calendar overlays (Phase 6 handoff)

**Spec search:** **AIM-03**, **GEX**, expiry_day, triple_witch, **OPEX**, session calendar

**Components:** **SH** `aim_compute.py`; **ON** `b1_features.py`

37. **Triple-witch** rule: third Friday + quarter only vs **full OPEX week**?

---

### I3 — TSM vs Kelly sizing interaction

**Spec search:** **PG-14**, **TSM**, **P3-D08**, **`pass_probability`**, **P3-D12**, `sizing_override`, **Kelly** interaction (**audit Q-31**)

**Components:** **CO** `b7_tsm_simulation.py`, `orchestrator.py` `_run_tsm_for_account`

38. **`sizing_override` (D12)** intentionally feeds **TSM MC** inputs — yes/no?

---

### I4 — RPT-07 emission scope

**Spec search:** **RPT-07**, **PG-14**, Redis `captain:reports:rpt07`, **CMD** `b6_reports.py`, offline emit

**Components:** **CO** TSM path; **CMD** reports

39. **Offline** must emit/archive **RPT-07**, **CMD only**, or **both** (**Q-32**)?

---

### I5 — Sensitivity implementation stack

**Spec search:** **PG-12**, **PG-13**, canvas DEPS **`isotonic`**, **`kneed`**, **`deap`**, GA, CSCV **PBO**, **Block 5** / **Block 6**

**Components:** **CO** `b5_sensitivity.py`, `b6_auto_expansion.py`

40. Implement canvas libraries vs **numpy/custom GA** — amend canvas vs code (**Q-30**)?

---

### I6 — CUSUM calibration fidelity

**Spec search:** **PG-07**, **CUSUM**, **`calibrate_cusum_limits`**, **`compute_cusum_conditional_on_sprint`**, sprint nested **`j`** loop vs pooling (**Q-29**)

**Components:** **CO** `b2_cusum.py`

41. Accept **pathwise max pooling** vs literal **`j`** loop — doc amend vs code (**Q-29**)?

---

### I7 — Architecture naming (`CV-01`)

**Spec search:** **`shared/aim_compute.py`**, **AIM System.canvas** filenames `aim_NN_*.py`, consolidation (**Q-36**)

**Components:** **SH** vs per-AIM modules

42. Long-term: **single consolidation** + amend canvases vs **split modules later**?

---

### I8 — AIM-12 VIX overlay (`audit Q-35`)

**Spec search:** **AIM-12**, **VIX**, systematic ×0.95, **`vix_z`** overlay

**Components:** **SH** `aim_compute.py`

43. **`vix_z > 1`** overlay **on top of** systematic 0.95 — required?

---

## How to use this list

- **Sections A–E** unblock **blocked batches** and **legal/product** wording.
- **Sections F–G** unblock **Phase 12** and **drift/HMM** engineering plans.
- **Sections H–I** reduce **schema/doc drift** and **tiny CONFIRM debt**.
- Use **Spec search** lines as **grep/query phrases** across `docs2/spec-docs-02/`, canvases, and **`32_P3_Offline_Full_Pseudocode.md`**.

After you answer, map each numbered reply to **doc 32 / canvas / decisions-log amendments** first, then to **numbered build-plan phases** as needed.
