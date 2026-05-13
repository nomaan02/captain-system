# Cross-Reference: Pre Deploy Specs vs V3 Additions — Line-by-Line

**Purpose:** For every V3 change, the EXACT location in the original spec where it needs to be integrated. Nomaan reads the original spec, then applies these insertions/modifications.

---

# Program3\_Online.md — 6 Changes

## Change O1: Fee in Kelly Risk (Block 4, Line \~847)

**Original (line 847):**

kelly\_contracts \= account\_kelly \* account\_capital / risk\_per\_contract

final\_contracts\[u\]\[ac\_id\] \= min(floor(kelly\_contracts), tsm\_cap)

**Insert BEFORE line 847:**

expected\_fee \= get\_expected\_fee(ac\_id, u, 1\)

risk\_per\_contract \= risk\_per\_contract \+ expected\_fee

**And CHANGE line 848 to:**

topstep\_daily\_cap \= floor(topstep\_state.daily\_exposure / risk\_per\_contract) IF tsm.get("topstep\_optimisation") ELSE 999

scaling\_cap \= (topstep\_state.scaling\_tier\_micros \- current\_open\_positions\_micros) IF tsm.get("scaling\_plan\_active") ELSE 999

final\_contracts\[u\]\[ac\_id\] \= min(floor(kelly\_contracts), tsm\_cap, topstep\_daily\_cap, scaling\_cap)

**Source:** `Nomaan_Edits_Fees.md` Change 2 \+ `Topstep_Optimisation_Functions.md` Part 6\.

## Change O2: HMM Session Budget in Block 5 (Line \~905-967)

**Original (line 905):** Block 5 `trade_selection_A` ranks by expected\_edge × contracts and selects based on correlation \+ position limits.

**V3 Addition:** BEFORE the ranking, compute session budget from HMM:

\# Insert at start of PG-25, before "Compute expected edge"

IF aim16\_active:

    session\_budget \= aim16\_hmm\_inference(remaining\_daily\_budget, observations\_today)

ELSE:

    session\_budget \= remaining\_daily\_budget  \# equal allocation if HMM not active

\# Then within the ranking loop, enforce session\_budget:

\# ranked\_assets are allocated from session\_budget, top-down by score

\# When session\_budget exhausted → remaining signals BLOCKED with reason "SESSION\_BUDGET\_EXHAUSTED"

**Source:** `HMM_Opportunity_Regime_Spec.md` Part 3, Section 3.7.

## Change O3: Circuit Breaker Screen AFTER Block 5B, BEFORE Block 6 (Line \~1076)

**Insert NEW block between Block 5B and Block 6:**

\# BLOCK 7B — CIRCUIT BREAKER SCREEN

\# Runs AFTER Block 5B quality gate, BEFORE Block 6 signal output.

\# For each recommended trade, check all 5 circuit breaker layers.

\# See Topstep\_Optimisation\_Functions.md Part 6, Section "Online Block 7".

**Full pseudocode:** `Topstep_Optimisation_Functions.md` lines 598-629 (PG-27B).

**Original Block 7 (Position Monitoring)** at line \~1180 is UNCHANGED — the circuit breaker screen is a separate function (PG-27B) that runs before signals are emitted, not during position monitoring.

## Change O4: resolve\_commission Fee Schedule (Line \~1305-1324)

**Original (line 1317):**

IF tsm AND tsm.commission\_per\_contract:

    RETURN tsm.commission\_per\_contract \* contracts \* 2

**Change to:**

IF tsm:

    IF tsm.get("fee\_schedule"):

        instrument\_fees \= tsm\["fee\_schedule"\]\["fees\_by\_instrument"\].get(asset)

        IF instrument\_fees:

            RETURN instrument\_fees\["round\_turn"\] \* contracts

    IF tsm.get("commission\_per\_contract"):

        RETURN tsm.commission\_per\_contract \* contracts \* 2

**Source:** `Nomaan_Edits_Fees.md` Change 2\.

## Change O5: Add get\_expected\_fee() Function (After line \~1340)

**Insert new function after resolve\_actual\_entry\_price():**

FUNCTION get\_expected\_fee(account\_id, asset, contracts=1):

    tsm \= tsm\_configs.get(account\_id)

    IF tsm AND tsm.get("fee\_schedule"):

        instrument\_fees \= tsm\["fee\_schedule"\]\["fees\_by\_instrument"\].get(asset)

        IF instrument\_fees:

            RETURN instrument\_fees\["round\_turn"\] \* contracts

    IF tsm AND tsm.get("commission\_per\_contract"):

        RETURN tsm.commission\_per\_contract \* contracts \* 2

    RETURN 0

**Source:** `Nomaan_Edits_Fees.md` Change 2\.

## Change O6: P3-D23 Intraday State Update (After resolve\_position, Line \~1303)

**Insert after `PUBLISH "captain:trade_outcomes"` (line 1303):**

\# Update circuit breaker intraday state

IF tsm.get("topstep\_optimisation"):

    P3-D23\[pos.account\].L\_t \+= net\_pnl

    P3-D23\[pos.account\].n\_t \+= 1

    P3-D23\[pos.account\].L\_b\[pos.model\_m\] \= P3-D23\[pos.account\].L\_b.get(pos.model\_m, 0\) \+ net\_pnl

    P3-D23\[pos.account\].n\_b\[pos.model\_m\] \= P3-D23\[pos.account\].n\_b.get(pos.model\_m, 0\) \+ 1

**Source:** `Nomaan_Edits_P3.md` Change 2\.

---

# Program3\_Offline.md — 3 Changes

## Change F1: AIM-16 HMM Training (After Block 1, Line \~470)

**Insert new section after Block 1 AIM Training:**

\# AIM-16 — Opportunity Regime HMM Training (PG-01C)

\# See HMM\_Opportunity\_Regime\_Spec.md Part 3, Section 3.5

## Change F2: Pseudotrader CB Extension (After Block 3, Line \~537)

**Insert after existing PG-09:**

\# PG-09B: Pseudotrader Circuit Breaker Replay

\# PG-09C: Circuit Breaker Grid Search

\# See Topstep\_Optimisation\_Functions.md Part 8

## Change F3: β\_b Estimation (In Block 8, After Kelly Updates)

**Insert after existing Kelly parameter updates:**

\# PG-16C: Circuit Breaker Parameter Estimator

\# See Nomaan\_Edits\_P3.md Change 4

---

# Program3\_Command.md — 2 Changes

## Change C1: SOD Topstep Parameters (Block 8 Daily Reconciliation, Line \~1014-1017)

**Insert after daily\_loss\_used reset (line 1016):**

\# Topstep SOD parameter computation

\# See Topstep\_Optimisation\_Functions.md Part 6, Section "Command Block 8"

\# \+ Nomaan\_Edits\_P3.md Change 1

## Change C2: Payout Notification \+ GUI Panels (Block 2 \+ Block 8\)

**Insert after SOD computation:**

\# Payout recommendation notification

\# See Nomaan\_Edits\_P3\_Command\_GUI.md

**Add to Block 2 gui\_data\_server\_A:**

\# Payout panel \+ Scaling display

\# See Nomaan\_Edits\_P3\_Command\_GUI.md

---

# Program3\_Architecture.md — 3 Changes

## Change A1: Data Store Catalogue (Section 3, Line \~148)

**ADD to P3 dataset list:**

P3-D23: circuit\_breaker\_intraday\_state (per account)

P3-D25: circuit\_breaker\_params (per account, per model)

P3-D26: hmm\_opportunity\_state

## Change A2: Asset Onboarding (Section 15\)

**ADD TRAINING\_ONLY to captain\_status enum.**

## Change A3: Open Parameters (Section 9\)

**ADD:**

threshold\_OO\_floor: 0.55 (P1 Block 5\)

threshold\_OO\_percentile: 0.85 (P1 Block 5\)

topstep\_params: {p, e, c, lambda} (P3 Command Block 8\)

---

# Program1.md — 2 Changes

## Change P1: OO Threshold (Block 5, Line \~927)

**Original:** `OO ≥ threshold_OO; TBD` **Change to:** `OO ≥ threshold_OO_floor (0.55) AND OO in top threshold_OO_percentile (85th) of all (m,k) pairs`

## Change P2: Open Parameters (Part L)

**ADD:**

threshold\_OO\_floor: 0.55

threshold\_OO\_percentile: 0.85

---

# P3\_Dataset\_Schemas.md — 3 Additions

## Add P3-D23 Schema

P3-D23: circuit\_breaker\_intraday\_state

    account\_id: string

    L\_t: float (cumulative net P\&L today)

    n\_t: int (trades taken today)

    L\_b: dict {model\_m: float} (per-basket P\&L)

    n\_b: dict {model\_m: int} (per-basket trade count)

    last\_updated: datetime

    Reset: 19:00 EST daily

## Add P3-D25 Schema

P3-D25: circuit\_breaker\_params

    account\_id: string

    model\_m: int

    r\_bar: float

    beta\_b: float

    sigma: float

    rho\_bar: float

    n\_observations: int

    p\_value: float

    last\_updated: datetime

## Add P3-D26 Schema

P3-D26: hmm\_opportunity\_state

    hmm\_params: {pi, A, mu, sigma, tvtp\_coefs}

    current\_state\_probs: array\[3\]

    opportunity\_weights: dict {session: weight}

    prior\_alpha: dict {session: array\[3\]}

    last\_trained: datetime

    training\_window: int

    n\_observations: int

    cold\_start: bool

## Modify P3-D00 Schema

**ADD to captain\_status enum:** `TRAINING_ONLY`

## Modify P3-D08 Schema

**ADD fields:**

topstep\_optimisation: bool (optional, default false)

topstep\_params: {p, e, c, lambda, max\_payouts\_remaining} (optional)

topstep\_state: {mdd\_pct, fee\_per\_trade, risk\_per\_trade\_eff, max\_trades, ...} (computed at SOD)

fee\_schedule: {type, fees\_by\_instrument, slippage\_model} (optional)

payout\_rules: {max\_per\_payout, commission\_rate, ...} (optional)

scaling\_plan\_active: bool (optional, XFA only)

scaling\_tier\_micros: int (computed from profit tier)

---

# AIMRegistry.md — 1 Addition

## Add AIM-16

AIM-16: Opportunity Regime HMM

    Purpose: Detect opportunity regimes across trading sessions. Output budget allocation weights.

    Data source: Session-level observations (signal count, mean OO, volume z, VIX, cross-asset corr)

    Model: Gaussian HMM with time-varying transition probabilities (TVTP)

    Output: opportunity\_weight per session window

    Consumed by: Online Block 5 (trade selection / budget allocation)

    Training: Offline Block 1 (PG-01C), Baum-Welch on 60-day rolling window

    Cold start: Equal weights, 50/50 blend until Day 60

    Stored in: P3-D26

    See: HMM\_Opportunity\_Regime\_Spec.md

---

# Implementation\_Checklist.md — New Tasks

**ADD to Phase 0:**

- Task 0.3: Write model\_generator.py \+ config (`Nomaan_Edits_P1.md`)  
- Task 0.4: Add OO threshold two-tier filter to Block 5 (`Nomaan_Edits_P1.md`)

**ADD to Phase 1 (after Task 1.2):**

- Task 1.2b: Create P3-D23, D25, D26 tables in QuestDB (schemas above)

**ADD to Phase 2 (new tasks):**

- Task 2.X: Implement circuit breaker screen PG-27B (`Nomaan_Edits_P3.md`)  
- Task 2.X: Implement β\_b estimation PG-16C (`Nomaan_Edits_P3.md`)  
- Task 2.X: Implement pseudotrader CB extension PG-09B/C (`Nomaan_Edits_P3.md`)  
- Task 2.X: Update resolve\_commission for fee\_schedule (`Nomaan_Edits_Fees.md`)  
- Task 2.X: Add get\_expected\_fee() (`Nomaan_Edits_Fees.md`)  
- Task 2.X: Implement SOD Topstep params in Block 8 (`Topstep_Optimisation_Functions.md`)  
- Task 2.X: Add payout notification to Command Block 8 (`Nomaan_Edits_P3_Command_GUI.md`)  
- Task 2.X: Add GUI payout panel \+ scaling display (`Nomaan_Edits_P3_Command_GUI.md`)

**ADD to Phase 3:**

- Task 3.X: Implement AIM-16 HMM training PG-01C (`HMM_Opportunity_Regime_Spec.md`)  
- Task 3.X: Implement HMM session allocation in Block 5 (`HMM_Opportunity_Regime_Spec.md`)  
- Task 3.X: Add TRAINING\_ONLY status to P3-D00 (`HMM_Opportunity_Regime_Spec.md`)

---

# Files with NO Changes Required

The following Pre Deploy files are UNCHANGED by the V3 additions and remain valid as-is:

| File | Reason No Change Needed |
| :---- | :---- |
| Block 2 KTR.md | P1 Block 2 unchanged |
| Block 3 Threshold.md | P1 Block 3 unchanged |
| Block 4.md | P1 Block 4 unchanged |
| Block 5.md | P1 Block 5 changes are in Nomaan\_Edits\_P1.md (additive, not modification) |
| BOCPD\_Implementation\_Guide.md | BOCPD unchanged |
| Kelly\_Implementation\_Guide.md | Kelly core unchanged (fee is additive) |
| DMA\_MoE\_Implementation\_Guide.md | DMA unchanged (AIM-16 uses same framework) |
| XGBoost Manual.md | Regime classifier unchanged |
| GovernancePolicy.md | Governance unchanged |
| ChangeManagementPolicy.md | CMP unchanged |
| NotificationSpec.md | Notification framework unchanged (new notifications use existing system) |
| ModelValidationPolicy.md | Validation policy unchanged |
| RegimeClassificationMethods.md | Methods unchanged |
| All 2026-02-\* dated files | Research/reference docs, not spec |
| AIM\_Extractions.md | Research reference |
| AIM\_Research\_Notes.md | Research reference |
| SystemBuild\_\*.md | Build context docs |
| CaptainNotes.md | Planning notes |
| Program3\_BuildContext.md | Build context |
| PROGRAM\_FULL\_FLOW.md | Flow overview (Master Build Guide supersedes for reading order) |
| ProgramFlowOverall.md | Flow overview |
| README.md | Readme |
| Nomaan\_Send.md | Original send instructions (Master Build Guide supersedes) |
| NomaanSendHowTo.md | Send instructions |
| Phase3\_Upload\_Checklist.md | Upload checklist |
| LocalFileRequirements.md | File requirements |
| TestIndex.md | Test reference |
| C2\_CONTROL\_MODELS.md | Control model reference |
| EdgeImprovementPlanNotes.md | Research reference |
| SystemPointCheck.md | Point check reference |
| Program1\_Program2\_Changes\_For\_Nomaan.md | Already applied changes |
| Program3\_Online\_PrepNotes.md | Prep notes |
| Program3\_Remaining\_PrepNotes.md | Prep notes |
| Program2.md | Minor additions only (V3+ regime types — handled in V3\_Architecture\_Plan.md) |
| UserManagementSetup.md | Already describes multi-user — no changes needed, just build it from start |
| 26/2/26 V1.md | Historical architecture reference — superseded by Program1.md. No V3 conflicts. |

