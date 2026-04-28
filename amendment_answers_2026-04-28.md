# Amendment questionnaire — consolidated answers (vault research run)

## 1. Run summary

| Field | Value |
|-------|--------|
| **Run date/time** | 2026-04-28 (research execution; wall-clock logged at compose time in workspace session) |
| **Total questions** | 43 |
| **Resolved** | 9 |
| **Deferred** | 34 |
| **Search scope** | Obsidian vault folder **`System 1/`** (recursive): **Direct Information**, **Backend (.md)**, **Backend**, **Audit Resolutions**, **Functional**, **Pseudocode**, **Backend (.md)** ASCII exports. No primary evidence drawn from vault folders outside `System 1/`. |

**Anchor note:** The questionnaire references **`p3_d06b_active_transitions`**, **`blend_signal`** as dataset/code anchors, and **`DEC-08`** / **`DEC-xx`** decision IDs. Inside **`System 1/`**, **`24_P3_Dataset_Schemas.md`** lists **P3-D06** (`injection_history`) but **does not define P3-D06b** or `active_transitions` rows. **`obsidian_global_search`** returned **no matches** for **`blend_signal`** or **`DEC-08`** under **`System 1/`**. **`canonical_schemas`** does **not** appear anywhere under **`System 1/`** (no prose authority statement for Python schema modules).

---

## 2. Resolved answers

### Q6 — AIM-04 gap overlay authority · Section A3 · RESOLVED

**Answer:** For overnight gap extremity, **`31_AIM_Individual_Specifications.md`** scales the AIM-04 modifier when **`gap_z > 2.0`** (not **`gap_z > 1`**), using **`×0.85`** on the evolving **`base`**.

**Evidence:**
- `System 1/Direct Information/31_AIM_Individual_Specifications.md`:`### AIM-04: Pre-Market & Overnight Session Analyzer` — "`gap_z = z_score(abs(features[asset].overnight_return), trailing_60d_gaps[asset])`" then "`IF gap_z > 2.0:` … `base *= 0.85`".
- `System 1/Direct Information/31_AIM_Individual_Specifications.md`:`### AIM-04` — IVTS tier logic sets **`base`** from **`ivts`** thresholds before gap overlay.

**Cross-check:** Same AIM-04 pseudocode block defines both IVTS tiers and gap overlay; no separate canvas excerpt was required because **`doc 31`** is the cited per-AIM authority linked from **`doc 33`** ingestion commentary.

**Doc-amendment hint:** Ensure **`doc 31` AIM-04** stays aligned with any **`AIM System`** canvas exports; amend **`doc 32`** cross-references only if **`PG`** blocks incorporate AIM-04 math.

---

### Q7 — EIA Wednesday ×0.90 for CL under AIM-04 vs AIM-06 · Section A3 · RESOLVED

**Answer:** **EIA petroleum for CL** is applied inside **`compute_aim_modifier_06`** (AIM-06 Economic Calendar), **`NOT`** inside AIM-04 — **`base *= 0.90`** when **`asset == "CL"`** and an **`EIA_PETROLEUM`** event is present.

**Evidence:**
- `System 1/Direct Information/31_AIM_Individual_Specifications.md`:`### AIM-06: Economic Calendar Impact Model` — "`IF asset == \"CL\" AND any(e.name == \"EIA_PETROLEUM\" for e in events):` … `base *= 0.90`".

**Cross-check:** AIM-04 section in the same document handles **`ivts`** / **`gap_z`** only; **EIA CL** appears only under AIM-06.

**Doc-amendment hint:** **`doc 31`** table-of-contents / **`AIM System.canvas`** labels should list **EIA CL** under **AIM-06** to prevent AIM-04 mis-attribution.

---

### Q8 — Per-zone confidence binary vs graded (Paper 67) · Section A3 · RESOLVED

**Answer:** **`doc 31`** AIM-04 sets **`confidence`** to **`0.9`** when **`ivts`** is outside the **`[0.93, 1.0]`** band and **`0.6`** otherwise — i.e., **tiered / graded**, not a single binary.

**Evidence:**
- `System 1/Direct Information/31_AIM_Individual_Specifications.md`:`### AIM-04` — "`confidence = 0.9 IF ivts > 1.0 OR ivts < 0.93 ELSE 0.6`".

**Cross-check:** **`Paper 67`** is not referenced inside **`System 1/`** search hits for **`Paper 67`** beyond unrelated **`PRIMARY`** research-method vocabulary in **`15_Model_Definitions.md`** — graded tiers stand solely on **`doc 31`** until **`Paper 67`** mapping exists.

**Doc-amendment hint:** If **`Paper 67`** parity is required, add an explicit mapping table **`Paper 67 zone ↔ doc 31 tiers`** under **`doc 31`** §AIM-04 notes.

---

### Q12 — Trade-outcome bus canonical contract · Section A5 · RESOLVED

**Answer:** **`doc 33`** specifies **`Redis`** **`PUBLISH`** to channel **`"trades"`** after **`P3-D03`** writes on trade close; **ASCII DMA canvas export** corroborates **`Redis pub/sub: trades`** as the offline DMA trigger path beside **`QuestDB`** **`trade_outcomes` / `trade_outcome_log`** naming alignment via **`doc 24 P3-D03`**.

**Evidence:**
- `System 1/Direct Information/33_P3_Online_Full_Pseudocode.md`:`## Block 7 — Position Monitoring (PG-27)` — "`PUBLISH Redis \"trades\" → outcome`".
- `System 1/Backend (.md)/(MD) DMA MoE Meta-Learning Pipeline.md` — ASCII diagram "`Redis pub/sub: trades`" feeding DMA worker after **`P3-D03`** feedback.

**Cross-check:** **`doc 24`** **`### P3-D03`** defines **`trade_outcome_log`** columns (`ts`, `trade_id`, `asset_id`, `pnl`, …); **`doc 33`** positions **`Redis`** notification adjacent to **`WRITE P3-D03`**.

**Doc-amendment hint:** Consolidate naming (**`trade_outcomes`** vs **`trade_outcome_log`**) across **`doc 24`**, **`DMA`** ASCII, and **`CLAUDE.md`** (outside scope here) under **`DEC-xx`** transport hygiene.

---

### Q17 — TVTP vs time-homogeneous v1 · Section C1 · RESOLVED

**Answer:** **`doc 22`** selects **`TVTP`** (**time-varying transition probabilities**) as the transition mechanism alongside Gaussian emissions — **time-homogeneous v1 is not chosen there**.

**Evidence:**
- `System 1/Direct Information/22_HMM_Opportunity_Regime.md`:`## 2. Selected variant` — "**Transitions** | **TVTP** …".

**Cross-check:** **`doc 32`** **`PG-01C`** defers training detail to **`doc 22`** — **`PG-xx`** pointer satisfies canonical-authority pairing.

**Doc-amendment hint:** Any Phase roadmap (**Phase 10b**) referencing homogeneous simplifications needs a **`DEC-xx`** override **`doc 22 §2`**.

---

### Q24 — G-XCT-012 “resolved” scope · Section E1 · RESOLVED

**Answer:** **`G-XCT-012`** audit resolution defines **`SQLite`** journal **`shared/journal.py`** as enabling **`idempotent recovery`** (**resume**, **duplicate avoidance**) across Offline/Online/Command checkpoints — **not** merely logging checkpoints without branching behaviour.

**Evidence:**
- `System 1/Audit Resolutions/G-XCT-012_crash_recovery_write_only.md`:`## Overall Feature` — "**idempotent recovery** — resume from where it left off".

**Cross-check:** **`doc 33`** audit footer references **`G-XCT-012`** (**startup/recovery**) tying **`PG`** lifecycle alignment.

**Doc-amendment hint:** **`DEC-xx`** governance referencing **`PG-xx`** spans should cite **`G-XCT-012`** recovery branching tables (**Offline / Online / Command** bullets).

---

### Q30 — D03 realised P&amp;L vs replay P&amp;L rule · Section F3 · RESOLVED

**Answer:** **`PG-09`** **`Phase 1–2`** builds **`baseline_results`** / **`updated_results`** using **`captain_online_replay`** for **`signal`** while **`outcome = actual_trade_outcome(d)`** — **`historical`** **`actual`** outsomes **`always`** anchor **`Sharpe`** / comparison metrics independent of **`replay`** **`PnL`** hypotheses.

**Evidence:**
- `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md`:`### PG-09: pseudotrader_retest_A` — both replay phases "`outcome = actual_trade_outcome(d)`".

**Cross-check:** **`G-OFF-016`** stresses **`captain_online_replay`** fidelity vs **`baseline_pnl`** shortcuts — reinforces **`actual_trade_outcome`** role vs **`PnL`** lists.

**Doc-amendment hint:** **`doc 28 Pseudotrader`** narrative should mirror **`PG-09`** wording **`actual_trade_outcome`** (**already cited by **`G-OFF-016`**).

---

### Q39 — RPT-07 emission scope Offline vs CMD · Section I4 · RESOLVED

**Answer:** **`PG-14`** (**Offline**) generates **`GENERATE RPT-07(P3-D08)`** after **`TSM`** **`Monte Carlo`**; **`doc 34`** **`PG-35`** registers **`RPT-07`** **`TSM Compliance`** in **`REPORT_SPECS`** (**Command report generator A**) — **`both`** **`process`** **`contracts`** **`touch`** **`RPT-07`**.

**Evidence:**
- `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md`:`### PG-14: tsm_simulation_A` — "`GENERATE RPT-07(P3-D08)`".
- `System 1/Direct Information/34_P3_Command_Full_Pseudocode.md`:`## Block 6 — Reports (PG-35)` — **`\"RPT-07\"`** `{ name: \"TSM Compliance\", … sources: [P3-D08], … }`.

**Cross-check:** **`doc 34`** **`REPORT_SPECS`** (**Command**) **`pairs`** **`with`** **`Offline`** **`GENERATE`** (**above**) **`without`** **`contradiction`** (**different`** **`lifecycle`** **`roles`**).

**Doc-amendment hint:** **`DOC`** **`34`** **`gather_data`** responsibilities vs **`Offline`** **`GENERATE`** hooks — **`DEC-xx`** **`ownership`** (**who **`archives`** **`first`** **`—`** **`outside`** **`vault`** **`detail`** **`optional`**).

---

### Q41 — CUSUM calibration fidelity pooling vs literal **`j`** loop · Section I6 · RESOLVED

**Answer:** **`PG-07`** pseudocode nests **`bootstrap`** **`b`** iterations **AND** **`FOR each sprint_length j`** loops storing **`cusum_values_at_j`** — **`literal`** **`j`** **structured** **`bootstrap`** **`distribution`**.

**Evidence:**
- `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md`:`### PG-07: cusum_bootstrap_calibrate_A` — nested **`FOR each sprint_length j IN range(1, max_sprint)`** inside **`FOR b IN range(B=2000)`**.

**Cross-check:** Canonical **`PG-xx`** block stands alone (**no conflicting canvas excerpt located**).

**Doc-amendment hint:** If implementation adopts **`max pooling`**, **`DEC-xx`** waiver **`PG-07`** fidelity (**audit Q-29**).

---

## 3. Deferred questions

### Q1 — PG-11 **`blend_signal`** consumer · Section A · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md`:`### PG-11: strategy_transition_A` — **`OUTPUT blended_signal`** inside **`Offline`** **`strategy_transition`** pseudocode (**no Online/CMD consumer named**).

**What is missing:** Named downstream consumer (**ON**, **CMD**, **both**) **`blend_signal`** **`READ`** **`contract`** (**Redis**, **`PG-xx`** **`segment`**).

**Suggested action for Nomaan to take to me:** Ask **`Isaac`** **`DEC-xx`** **`binding`** **`blend_signal`** **`routing`** (**Online **`PG-26`** vs **`CMD`** **`PG-30`** queue).

---

### Q2 — Blended sizing ON B6 vs B7 placement · Section A · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- `System 1/Direct Information/33_P3_Online_Full_Pseudocode.md`:**Blocks** **`6–7`** headings (**`PG-26`** **`signal_output`**, **`PG-27`** **`position_monitor`**) — **neither references **`blend_signal`**.

**What is missing:** **`PG-xx`** **`sentence`** tying **`transition`** **`weights`** **`into`** **`Kelly`** **`contracts`** **`pipeline`** (**Block** **`4–6`** ordering).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** **`placement`** (**Kelly **`PG-24`** vs **`signal_output`** **`PG-26`**).

---

### Q3 — **`p3_d06b_*`** **read/write contract** · Section A · DEFERRED

**Reason for defer:** **MISSING_DOC**

**What I found:**
- `System 1/Direct Information/24_P3_Dataset_Schemas.md`:`## 2. Dataset index` — **`P3-D06`** **`injection_history`** listed; **`no`** **`P3-D06b`** **`row`**.

**What is missing:** **`Vault`** **`schema`** **`section`** **`for`** **`active_transitions`** **`/`** **`p3_d06b`** **`columns`** **`lifecycle`**.

**Suggested action for Nomaan to take to me:** **`Publish`** **`24`** **`addendum`** **`OR`** **`DEC-xx`** **`dataset`** **`split`** **`rationale`**.

---

### Q4 — Suppression log destination columns · Section A · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md`:`### PG-01` — **`LOG suppression event to P3-D06`** (**events list lacks column schema**).

**What is missing:** **`Minimum`** **`column`** **`manifest`** (**who/when/aim_id/asset/from/to/reason**) **`matching`** **`injection_history`** **`payload`** **`shape`**.

**Suggested action for Nomaan to take to me:** **`DEC-xx`** **`schema`** **`delta`** **`doc`** **`24`** **`§P3-D06`**.

---

### Q5 — Append-only vs GUI-queryable suppression logs · Section A · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- `System 1/Direct Information/34_P3_Command_Full_Pseudocode.md`:`### gui_data_server_A` — **`aim_panel`** **`metrics`** (**no **`SUPPRESSED`** **`audit`** **`trail`** **`fields`**).

**What is missing:** **`Compliance`** **`visibility`** **`requirement`** **`DEC-xx`** **`CMD`** **`GUI`** **`panels`**.

**Suggested action for Nomaan to take to me:** **`Governance`** **`sign-off`** **`SUPPRESSED`** **`logging`** **`tier`**.

---

### Q9 — Other AIM-04 Paper 67 rules · Section A · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- **`Paper 67`** **`keyword`** **`hits`** **`non-authoritative`** **`research`** **`tables`** (**`15_Model_Definitions`** **`PRIMARY`** definitions).

**What is missing:** **`Dedicated`** **`Paper`** **`67`** **`rule`** **`manifest`** **`inside`** **`System`** **`1`**.

**Suggested action for Nomaan to take to me:** **`Import`** **`Paper`** **`67`** **`overlay`** **`matrix`** **`into`** **`doc`** **`31`** **`notes`**.

---

### Q10 — AIM-07 **`DEC-08`** vs **`_aim07_cot`** register timing · Section A · DEFERRED

**Reason for defer:** **MISSING_DECISION**

**What I found:**
- **`DEC-08`** **`zero`** **`hits`** **`System`** **`1`** (**search failure confirmed earlier).
- `System 1/Direct Information/31_AIM_Individual_Specifications.md`:`### AIM-07` — **`Tier`** **`3`** **`build`** **`later`** (**dispatch stub absent **`DEC`** **`gate`**).

**What is missing:** **`Recorded`** **`DEC-xx`** **`CFTC`** **`availability`** **`policy`**.

**Suggested action for Nomaan to take to me:** **`Ask`** **`Isaac`** **`DEC-08`** **`text`** **`insert`** **`decisions`** **`log`**.

---

### Q11 — AIM-07 feed contract fallback · Section A · DEFERRED

**Reason for defer:** **MISSING_DECISION**

**What I found:**
- `System 1/Direct Information/31_AIM_Individual_Specifications.md`:`### AIM-07` — **`IF smi is None`** **`RETURN`** **`neutral`** **`modifier`**.

**What is missing:** **`Operational`** **`SLO`** **`when`** **`feed`** **`partial`** (**lags**) **`vs`** **`hard`** **`down`** (**engineering **`adapter`** **`contract`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** **`adapter`** **`fallback`** **`levels`**.

---

### Q13 — **`L_b`** loss-only vs signed; intra-day vs cross-day · Section B · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md`:`### PG-16C` — **`L_series = [running_loss_at_trade_time(t) for t in trades]`** (**definition unresolved **`inside`** **`PG-16C`** **`snippet`**).

**What is missing:** **`Formal`** **`definition`** **`running_loss_at_trade_time`** (**loss-only accumulate**, **`cross-session`** **`reset`** **`rules`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** **`numeric`** **`definition`** **`attach`** **`PG-16C`** **`footnote`**.

---

### Q14 — Profitable runs reset running-loss · Section B · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- **`PG-16C`** (**above**) (**no **`reset`** **`clause`**).

**What is missing:** **`Reset`** **`/`** **`carry`** **`policy`** **`explicit`** **`sentence`**.

**Suggested action for Nomaan to take to me:** **`Joint`** **`answer`** **`with`** **`Q13`** **`DEC-xx`**.

---

### Q15 — **`p-value`** zeroing **`β_b`** removal product truth · Section B · DEFERRED

**Reason for defer:** **MISSING_DECISION**

**What I found:**
- **`PG-16C`** (**vault excerpt**) (**contains **`cold`** **`start`** **`β_b=0`** **`when`** **`n<10`** — **`no`** **`p-value`** **`test`** **`clause`**).

**What is missing:** **`Human`** **`product`** **`sign-off`** **`matching`** **`implementation`** **`delta`** (**audit **`F-61`** **`outside`** **`vault`** **`scope`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** **`choose`** **`spec`** **`vs`** **`code`** (**reference **`F-61`**).

---

### Q16 — HMM cadence (**SESSION_CLOSE**, weekly, …) · Section C · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- `System 1/Direct Information/22_HMM_Opportunity_Regime.md`:`## 6. Training` — "**Frequency** | Per research calendar".

**What is missing:** **`Concrete`** **`cadence`** (**asset/session/global**) **`locking`** **`SESSION_CLOSE`** (**keyword **`timeout`** **`search`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** **`calendar`** **`binding`** (**offline **`PG-01C`** **`caller`**).

---

### Q18 — D26 merge conflict · Section C · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- `System 1/Direct Information/24_P3_Dataset_Schemas.md`:`### P3-D26` — **`probability`** **`columns`** (**no **`merge`** **`policy`**).

**What is missing:** **`Conflict`** **`resolution`** (**offline **`snapshot`** **`vs`** **`online`** **`forward`** **`filter`** **`states`**).

**Suggested action for Nomaan to take to me:** **`Extend`** **`doc`** **`22`** **`§storage`** **`OR`** **`DEC-xx`**.

---

### Q19 — **`probs_to_ny_lon_apac`** approval · Section C · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- **`Zero`** **`hits`** (**`probs_to_ny_lon_apac`** **`System`** **`1`**).

**What is missing:** Any **`spec`** **`paragraph`** (**placeholder heuristic**) **`inside`** **`vault`** **`folder`**.

**Suggested action for Nomaan to take to me:** **`Author`** **`doc`** **`33`** **`footnote`** **`OR`** **`DEC-xx`** **`temporary`** **`flag`**.

---

### Q20 — Online inference cadence vs AIM-16 ACTIVE gate · Section C · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- `System 1/Direct Information/33_P3_Online_Full_Pseudocode.md`:`### PG-23` — **`IF aim_states[16].status == ACTIVE`** **`session_budget_weights = hmm_inference(...)`** **`ELSE`** **`equal`** **`weights`**.

**What is missing:** **`Scheduling`** (**every **`session`** **`ingestion`** **`tick`** **`vs`** **`lazy`**) **`explicit`** **`outside`** **`conditional`** (**performance **`budget`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** **`online`** **`scheduler`** (**PG-23 **`paragraph`** **`expansion`**).

---

### Q21 — Weekly light D5 vs frequency · Section D · DEFERRED

**Reason for defer:** **SOURCE_CONFLICT**

**What I found:**
- `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md`:`### PG-17 / PG-16B: system_health_diagnostic_A` — comment lines "`Run weekly (D1-D7) and monthly (D5 deep analysis)`" and "`Event-triggered: D8 runs when ADMIN marks action item as RESOLVED`", followed later by **`overall_health = weighted_mean(d1..d8 scores)`** (**weekly`** **`range`** **`D1-D7`** **`does`** **`not`** **`enumerate`** **`D8`** **`inside`** **`same`** **`sentence`** **`as`** **`weekly`** **`runner`**).

**What is missing:** Single **`DEC-xx`** **clean narrative**: whether **`weekly`** **`job`** **`scores`** **`all`** **`eight`** **`dimensions`** (**including **`light`** **`D5`** **`edge`** **`tick`**) **`or`** **`weekly`** **`skips`** **`D8`** **`/`** **`which`** **`dimensions`** **`participate`** **`in`** **`weighted_mean`** **`inputs`** **`each`** **`cadence`**.

**Suggested action for Nomaan to take to me:** Ask **`Isaac`** **`DEC-xx`** **`PG-17`** **`cadence`** **`table`** (**weekly`** **`/`** **`monthly`** **`/`** **`event`** **`×`** **`dimension`** **`matrix`**).

---

### Q22 — **`research_pipeline`** **`D7`** tables · Section D · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md`:`### PG-17` — **`D7`** **`dimension`** **`definition`** (**queues**) (**no **`table`** **`names`**).

**What is missing:** **`Physical`** **`queue`** **`/`** **`QuestDB`** **`table`** **`mapping`** (**minimum **`fields`**).

**Suggested action for Nomaan to take to me:** **`Schema`** **`ticket`** **`doc`** **`24`** **`§system_health`** **`detail`** **`/`** **`operations`** **`registry`**.

---

### Q23 — **`overall_health`** weights parity · Section D · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- **`PG-17`** snippet — **`overall_health = weighted_mean(d1..d8 scores)`** (**dimension **`weights`** **`unspecified`** **`numerically`**).

**What is missing:** **`Weight`** **`vector`** (**equal **`vs`** **`tiered`**) **`explicit`** (**implementation **`hint`** **`outside`** **`spec`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** (**tie **`audit`** **`Q-34`**).

---

### Q25 — DELETE pruning vs cold-storage retention · Section E · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md`:`### Version Snapshot Policy` — **`migrate_to_cold_storage(oldest)`** **`when`** **`rolling`** **`cap`** (**no **`retention`** **`months`** **`mandate`**).

**What is missing:** **`Cold`** **`storage`** **`obligation`** (**legal **`/`** **`audit`** **`period`**).

**Suggested action for Nomaan to take to me:** **`Governance`** **`DEC-xx`** (**finance **`/`** **`security`** **`review`**).

---

### Q26 — **`FAILED_REGRESSION`** rollback **`retry`** **`policy`** · Section E · DEFERRED

**Reason for defer:** **MISSING_DECISION**

**What I found:**
- **`Version`** **`Snapshot`** **`Policy`** — **`IF NOT run_regression_tests(): REVERT`** (**no **`retry`** **`/`** **`new`** **`proposal`** **`workflow`**).

**What is missing:** **`Operational`** **`branch`** (**retry **`commit`** **`/`** **`halt`** **`/`** **`new`** **`rollback`** **`ticket`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** **`failure`** **`runbook`** (**tie **`redis`** **`proposal`** **`systems`** **`if`** **`used`**).

---

### Q27 — 1-minute bars prerequisite vs **`PG-09`** intraday · Section F · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- **`PG-09`** (**depends **`captain_online_replay(d)`**) (**no **`bar`** **`resolution`** **`gate`** **`sentence`** **`inside`** **`PG-09`** **`block`**).

**What is missing:** **`Infrastructure`** **`dependency`** **`manifest`** (**minute **`bars`** **`vs`** **`daily`** **`replay`** **`acceptable`**).

**Suggested action for Nomaan to take to me:** **`Infrastructure`** **`DEC-xx`** (**tie **`P3-D23`** **`/`** **`intraday`** **`roadmap`**).

---

### Q28 — Legacy replay deletion timeline · Section F · DEFERRED

**Reason for defer:** **MISSING_DECISION**

**What I found:**
- **`G-OFF-016`** (**engineering **`fixes`**) (**no **`sunset`** **`date`** **`for`** **`SignalReplayEngine`**).

**What is missing:** **`Calendar`** **`cutoff`** (**Phase **`12`** **`binding`**).

**Suggested action for Nomaan to take to me:** **`Roadmap`** **`DEC-xx`** (**programme **`milestone`**).

---

### Q29 — **`captain_online_replay`** kwarg removal safety · Section F · DEFERRED

**Reason for defer:** **MISSING_DECISION**

**What I found:**
- **`G-OFF-016`** — **`cached_bars`** **`performance`** **`reuse`** (**no **`approval`** **`to`** **`delete`** **`kwargs`**).

**What is missing:** **`Architecture`** **`sign-off`** (**performance **`vs`** **`simplicity`**).

**Suggested action for Nomaan to take to me:** **`Technical`** **`ADR`** **`DEC-xx`**.

---

### Q31 — Drift-detection QuestDB tables prioritisation · Section G · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- **`DMA`** **`ASCII`** (`Backend (.md)/(MD) DMA MoE Meta-Learning Pipeline.md`) lists **`QuestDB`** **`aim_features_{N}`** (**targets **`tables`** **`informally`**).

**What is missing:** **`Authoritative`** **`priority`** **`ordering`** (**which **`AIM`** **`vectors`** **`first`** **`PG-04`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** **`sequence`** (**tie **`PG-04`**).

---

### Q32 — Modifier JSON AE interim sunset · Section G · DEFERRED

**Reason for defer:** **MISSING_DECISION**

**What I found:**
- **`PG-04`** (**generic **`autoencoder`** **`/`** **`ADWIN`**).

**What is missing:** **`Sunset`** **`date`** **`/`** **`production`** **`readiness`** **`criterion`** (**TODO[F-13]** **`vault`** **`absent`**).

**Suggested action for Nomaan to take to me:** **`Risk`** **`DEC-xx`** (**technical **`debt`** **`register`**).

---

### Q33 — **`_load_regime_models`** migration timing (**P2-D07`** **`vs`** **`P3-D00`**) · Section H · DEFERRED

**Reason for defer:** **MISSING_DECISION**

**What I found:**
- `System 1/Direct Information/33_P3_Online_Full_Pseudocode.md`:`### PG-21` — **`regime_models = READ P2-D07`** (**online **`today`** **`binding`**).

**What is missing:** **`Migration`** **`clock`** (**when **`offline`** **`snapshots`** **`replace`** **`live`** **`loads`** **`/`** **`hybrid`** **`legacy`** **`paths`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** (**dataset **`lifecycle`** **`Phase`** **`1`** **`migration`**).

---

### Q34 — **`canonical_schemas.py`** if **`doc`** **`24`** absent · Section H · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- **`canonical_schemas`** (**zero **`hits`** **`System`** **`1`**).
- **`doc`** **`24`** **`§Document`** **`control`** — **`[[10_Dataset_Catalogue]]`** **`authority`** (**Python`** **`module`** **`unnamed`**).

**What is missing:** **`Explicit`** **`fallback`** **`rule`** (**repo **`Python`** **`vs`** **`markdown`**).

**Suggested action for Nomaan to take to me:** **`Architecture`** **`DEC-xx`** (**cite **`SC-03`** **`outside`** **`vault`** **`if`** **`needed`**).

---

### Q35 — **`model_m`** **`vs`** **`basket_id`** (**P3-D03`** **`linkage`**) · Section H · DEFERRED

**Reason for defer:** **SOURCE_CONFLICT**

**What I found:**
- **`doc`** **`24`** **`§P3-D03`** (**columns **`exclude`** **`both`** **`identifiers`**).
- **`doc`** **`33`** **`PG-27B`** uses **`signal.basket`** (**circuit`** **`breaker`** **`layer`**).

**What is missing:** **`Single`** **`schema`** **`truth`** (**bridge`** **`table`** **`/`** **`column`** **`addendum`**).

**Suggested action for Nomaan to take to me:** **`Schema`** **`DEC-xx`** (**amend **`doc`** **`24`** **`/`** **`33`** **`alignment`**).

---

### Q36 — **`new_prob == 0`** **`vs`** **`epsilon`** (**DMA**) · Section I · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- **`PG-02`** (**vault excerpt**) (**uses **`meta_weight`** **`trade`** **`logic`** — **`no`** **`epsilon`** **`band`** **`sentence`**).

**What is missing:** **`Floating-point`** **`comparison`** **`policy`** (**SUPPRESSED`** **`counter`** **`increment`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** (**tie **`Redis`** **`aim_counters`** **`implementation`** **`note`**).

---

### Q37 — Triple-witch **`vs`** **`full`** **`OPEX`** **`week`** · Section I · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- **`AIM-03`** pseudocode (**`is_triple_witching(today)`**) (**definition **`not`** **`exported`** **`here`**).
- **`AIM-10`** (**separate **`is_opex_window`** **`/`** **`OPEX_WINDOW`** **`/`** **`third`** **`Friday`** **`±2`** **`logic`**).

**What is missing:** **`Exclusive`** **`classification`** (**triple`** **`witch`** **`subset`** **`rules`** **`vs`** **`broader`** **`OPEX`** **`week`** **`modifiers`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** (**calendar **`taxonomy`** **`diagram`**).

---

### Q38 — **`sizing_override`** **`feeds`** **`TSM`** **`MC`** (**PG-14**) · Section I · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- **`PG-14`** (**INPUT lists **`P3-D12`**) (**loop body **`only`** **`samples`** **`trade_returns`** **`from`** **`P3-D03`** **`/`** **`does`** **`not`** **`multiply`** **`path`** **`PnL`** **`by`** **`override`** **`explicitly`**).

**What is missing:** **`Normative`** **`statement`** (**whether **`Kelly`** **`layer`** **`decay`** **`reduction`** **`belongs`** **`inside`** **`TSM`** **`simulation`** **`paths`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** (**numerical`** **`intent`** **`PG-14`** **`revision`**).

---

### Q40 — **`PG-12`** **`/`** **`PG-13`** libraries (**isotonic`** **`/`** **`deap`**) · Section I · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- **`PG-12`** **`/`** **`PG-13`** (**numpy-ish pseudocode**) (**library names **`absent`**).

**What is missing:** **`Approved`** **`dependency`** **`list`** (**canvas **`DEPS`** **`blob`** **`not`** **`loaded`** **`here`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** (**dependency`** **`parity`** **`audit`** **`canvas`** **`Functional`** **`folder`** **`manual`** **`review`**).

---

### Q42 — **`CV-01`** **`aim_compute`** consolidation · Section I · DEFERRED

**Reason for defer:** **NO_EVIDENCE**

**What I found:**
- **`DISPATCH`** map **`doc`** **`31`** (**single **`compute_aim_modifier`** **`hub`** **`specified`**).

**What is missing:** **`Roadmap`** **`DEC-xx`** (**mono-repo **`vs`** **`split`** **`modules`** **`future`** **`state`** **`explicit`**).

**Suggested action for Nomaan to take to me:** **`Architecture`** **`DEC-xx`** (**tie **`CV-01`** **`external`** **`tracker`** **`if`** **`exists`** **`outside`** **`vault`**).

---

### Q43 — AIM-12 **`vix_z > 1`** overlay **`stacked`** **`on`** **`systematic`** **`0.95`** · Section I · DEFERRED

**Reason for defer:** **INTENT_GAP**

**What I found:**
- **`AIM-12`** (**uses **`spread_z`** **`/`** **`vol_z`** **`derived`** **`from`** **`features[vix_z]`** **`with`** **`composite`** **`threshold`** **`1.5`**) (**after **`systematic`** **`×0.95`** **`penalty`**).

**What is missing:** **`Explicit`** **`rule`** **`"`**`vix_z > 1`**`"`** **`overlay`** (**distinct **`from`** **`spread`** **`tier`** **`logic`** **`/`** **`audit`** **`Q-35`** **`numerics`**).

**Suggested action for Nomaan to take to me:** **`DEC-xx`** (**confirm **`whether`** **`question`** **`should`** **`cite`** **`AIM-11`** **`instead`** **`/`** **`adjust`** **`thresholds`** **`doc`** **`31`**).

---

## 4. Incidental findings

- **`System 1/Direct Information/24_P3_Dataset_Schemas.md`**: **`§2`** **`dataset`** **`index`** **`omits`** **`P3-D06b`** **`referenced`** **`externally`** (**questionnaire**) — severity **minor**.
- **`obsidian_global_search`** (**sessions**) **`timed`** **`out`** **`for`** **`narrow`** **`tokens`** (**fallback`** **`cache`** **`empty`**) — **`research`** **`relied`** **`on`** **`full`** **`file`** **`reads`** (**severity`** **`info`**).
- **`PG-08`** (**vault **`doc`** **`32`** **`via`** **`MCP`**) **`differs`** **`from`** **`workspace`** **`captain-system`** **`mirror`** (**`SCHEDULE`** **`vs`** **`MANUAL`** **`programs_1_2_rerun`**) — **`potential`** **`spec`** **`drift`** — severity **blocker** (**requires`** **`human`** **`diff`** **`outside`** **`this`** **`run`**).

---

_End of consolidated answers._
