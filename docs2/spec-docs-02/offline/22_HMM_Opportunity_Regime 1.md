---
tags:
  - P3-offline
  - P3-online
---
# HMM Opportunity Regime — AIM-16

| Field | Value |
|--------|--------|
| **Document** | Transfer Part 2 — 22 |
| **Purpose** | Specify AIM-16: session-level hidden Markov opportunity regime detection, training (PG-01C), online inference (PG-25B), storage (P3-D26), and register boundaries vs P1/P2. |
| **Last updated** | 2026-04-05 |

## Cross-references (Part 1)

| Reference | Topic |
|-----------|--------|
| **[[07_AIM_System|Part 1 doc 07]]** | AIM System — AIM taxonomy, integration with sizing and Captain |
| **[[05_Captain_Online|Part 1 doc 05]]** | Captain Online — online pipeline placement and orchestration |

---

## 1. Overview

| Aspect | Specification |
|--------|----------------|
| **Role** | AIM-16 detects **opportunity regimes across sessions** and outputs **budget allocation weights** (per session, not per asset). |
| **Contrast with AIMs 1–15** | AIMs 1–15 apply **per-asset modifiers**; AIM-16 applies **per-session** weights to capital / risk budget. |
| **Outputs** | Normalised session-level weights consumed by adaptive P3 layer (see §8). |

---

## 2. Selected variant

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Emissions** | **Gaussian HMM** | Continuous observations; Gaussian likelihood sufficient for the observation vector. |
| **Transitions** | **TVTP** (time-varying transition probabilities) | Covariate-driven transitions capture effects such as **Fridays differing from Mondays**. |
| **Stability** | **Exponential smoothing** on inferred probabilities | Reduces **whipsaw** when session-to-session state estimates flicker. |

---

## 3. Hidden states (K = 3)

| State ID | Label | Interpretation (qualitative) |
|----------|--------|------------------------------|
| **S0** | `LOW_OPP` | Unfavourable opportunity — tighten session budget. |
| **S1** | `NORMAL` | Baseline opportunity — neutral session weighting. |
| **S2** | `HIGH_OPP` | Elevated opportunity — allow higher session budget (within global caps). |

| Characteristic | LOW_OPP | NORMAL | HIGH_OPP |
|----------------|---------|--------|----------|
| Typical signal environment | Sparse / weak | Typical | Rich / strong |
| Vol / stress (typical) | Often elevated or chaotic | Mixed | Often supportive |
| Session budget bias | Down-weight | 1.0 reference | Up-weight (capped) |

*Exact numeric priors are training-derived; the table describes intended semantics.*

### State transition diagram (TVTP)

```
          A_01(x_t)              A_12(x_t)
  ┌──────────────────►   ┌──────────────────►
  │                  │   │                  │
┌─┴──┐           ┌──┴───┴─┐           ┌────┴─┐
│ S0 │           │  S1    │           │  S2  │
│LOW │◄──────────│NORMAL  │◄──────────│ HIGH │
│OPP │  A_10(x)  │        │  A_21(x)  │ OPP  │
└─┬──┘           └──┬─────┘           └────┬─┘
  │ A_00(x)         │ A_11(x)              │ A_22(x)
  └──────┐          └──────┐               └──────┐
         ▼                 ▼                      ▼
      (self-loop)       (self-loop)           (self-loop)

TVTP covariates x_t = {VIX_level, day_of_week, prior_session_PnL}
Transitions depend on current covariates — e.g. Fridays have
higher A_*0 (transition toward LOW_OPP) than Mondays.
Smoothing (α=0.3) applied post-inference to reduce whipsaw.
```

---

## 4. Observation vector (7 elements)

| Index | Feature | Description |
|-------|---------|-------------|
| **1** | `n_signals` | Count or intensity of actionable signals (session aggregate). |
| **2** | `mean_OO` | Mean opening–outcome (or defined “OO”) metric across session universe. |
| **3** | `volume_z` | Volume z-score vs recent baseline. |
| **4** | `vix_level` | VIX (or configured fear gauge) level. |
| **5** | `prior_session_pnl` | Realised or labelled P&L proxy for previous session. |
| **6** | `cross_asset_corr` | Cross-asset correlation measure (e.g. mean pairwise corr). |
| **7** | `day_of_week` | Encoded weekday (feeds TVTP / covariates as specified in implementation). |

All elements must be **defined, versioned, and aligned** between offline training and online inference.

---

## 5. Model parameters

| Symbol | Object | Notes |
|--------|--------|--------|
| **π** | Initial state distribution | K-vector; re-estimated on each rolling refit. |
| **A(x_t)** | TVTP transition matrix | K×K; entries depend on covariates **x_t** (e.g. day-of-week, VIX bucket). |
| **μ_k** | Emission means | Per state k; dimension = 7. |
| **Σ_k** | Emission covariance | **Diagonal Σ_k** in v1; full covariance optional later. |

---

## 6. Training ([[32_P3_Offline_Full_Pseudocode|PG-01C]])

| Item | Specification |
|------|----------------|
| **Algorithm** | **Baum–Welch** (EM for HMM). |
| **Window** | **Rolling 60 trading days**; **240 observations** per window (4 obs/day if 4 session slices; adjust if spec uses 1 obs/day — then window = 240 sessions). |
| **Initialisation** | **Supervised seeding** from **quartile P&L labelling** (map historical sessions to provisional states before EM). |
| **Persistence** | Model snapshots and sufficient statistics → **[[24_P3_Dataset_Schemas|P3-D26]]** (`hmm_states` / AIM-16 partition). |
| **Frequency** | Per research calendar; must not leak future labels into past windows. |

---

## 7. Online inference ([[33_P3_Online_Full_Pseudocode|PG-25B]])

| Item | Specification |
|------|----------------|
| **Algorithm** | **Forward algorithm** for filtered state probabilities at **future session windows** (predictive step as defined in pipeline). |
| **Smoothing** | Exponential smoothing with **α = 0.3** applied to probability vector (or to logits — implementation must fix one convention). |
| **Budget weights** | **Normalised state probabilities** (sum = 1) mapped through a **fixed, documented** map to session **budget multipliers** (bounds in risk doc / Kelly pipeline). |

---

## 8. Frozen vs adaptive register

| Register | May P3 adapt? | Examples |
|----------|----------------|----------|
| **P1 / P2** | **Never** | Locked control parameters, AIM definitions 1–15 structure, regime rules — **not** modified by P3. |
| **P3 adaptive** | **Yes** | Kelly layers, **AIM weights**, **BOCPD**, **session budget weights from AIM-16** (new adaptive input). |

---

## 9. TRAINING_ONLY assets

| Concept | Rule |
|---------|------|
| **Universe** | **8000+** symbols (or configured superset) for **training** richer correlation and volume/regime structure. |
| **Live signals** | Only **actively traded** assets receive production signals; TRAINING_ONLY rows do not drive live orders. |
| **Data hygiene** | Same feature definitions; TRAINING_ONLY may have sparse fills — document imputation or exclusion rules. |

---

## Document control

| Field | Value |
|--------|--------|
| **Owner** | Research / architecture sign-off before production |
| **Related datasets** | [[24_P3_Dataset_Schemas|P3-D26]] (HMM / AIM-16 state store) |

## Related Canvases

- [[System 1/Backend/AIM System.canvas|AIM System]]
- [[System 1/Backend/P3 Online.canvas|P3 Online]]
