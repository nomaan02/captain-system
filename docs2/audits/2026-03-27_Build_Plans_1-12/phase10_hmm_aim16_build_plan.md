# Phase 10 — HMM / AIM-16 End-to-End Build Plan

**Campaign:** Captain Offline / Online twelve-phase audit fix (`2026-03-27_Build_Plans_1-12`)  
**Executed by:** Composer 2 session (implementation), not this planning session  
**Authoritative inputs:** decisions log `docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md`, audit `docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md`, doc 22 `docs2/spec-docs-02/offline/22_HMM_Opportunity_Regime 1.md`, doc 32 `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md`, doc 33 `docs2/spec-docs-02/online/33_P3_Online_Full_Pseudocode 1.md`  
**Frozen engineering decisions for this phase:**

| Gate | Decision |
|------|-----------|
| **Q-10** | **(d)** Ship **time-homogeneous v1** (Gaussian `hmmlearn` HMM with fixed transition matrix); defer **true TVTP** to **Phase 10b**. Document F-14 semantic gap vs doc 22 §2/§5 as intentional for v1. |
| **Q-11** | **Confirmed for planning:** Offline PG-01C owns `hmm_params`, `training_window`, `n_observations`, `last_trained`; Online PG-23/PG-25B path owns **`current_state_probs`, `opportunity_weights`, `last_updated`**. Offline may also persist **`cold_start`** (training-derived — [CONFIRM] if Isaac wants it under offline-only columns). **`prior_alpha`** is used for online smoothing per doc 22 §7 — treat as online/inference-adjacent [CONFIRM]. |
| **Q-03** | Globally **after every market trading session** — matches Phase 3 wiring (online publishes `SESSION_CLOSE`, offline consumes). |

---

## Stage 1 audit summary (read-only; frozen for this document)

### Authority note on F-01 vs current repo

The audit text for **F-01** (orchestrator never invokes PG-01C) reflected an **older** tree. **Decisions log Q-03 + Phase 3 work supersede that finding for wiring.**

**Verified Phase 3 dispatch path:**

- **Online:** `captain-online/captain_online/blocks/orchestrator.py` — `_run_session` / OR path publishes `"type": "SESSION_CLOSE"` onto `STREAM_COMMANDS` (~lines 379–388, ~506–516 in file; exact line tags may drift).  
- **Offline:** `captain-offline/captain_offline/blocks/orchestrator.py` — `cmd_type == "SESSION_CLOSE"` → `_handle_session_close` → `_run_aim16_hmm_training` (**lines ~471–472, ~557–633**). Imports `train_aim16_hmm`, `save_hmm_state`, `build_observation_panel_stub`.  
- **Tests:** `tests/test_offline_session_close_dispatch.py` — asserts PG-01C dispatch once per close, idempotency, global-not-per-asset.

**Judgment:** Phase 3 precondition **SATISFIED**. Phase 10 does **not** re-wire dispatch; it replaces **stub semantics** (empty observation panel → cold-start behavior) with **spec-correct** training, inference, and D26 ownership.

---

### F-14 — TVTP vs time-homogeneous

| Item | Detail |
|------|--------|
| **Spec (doc 22)** | §2, §3, §5 — TVTP `A(x_t)` with covariates; §6 — Baum–Welch. |
| **Code** | `captain-offline/captain_offline/blocks/b1_aim16_hmm.py` **lines 120–132** — `GaussianHMM` with uniform `transmat_` init, EM fit; **no** covariate-conditioned transitions. Supervised seeding **lines 107–118** uses P25/P75 on `session_pnl` (`_label_from_pnl`). |
| **Delta** | Full TVTP absent. **Mitigation for v1:** Q-10 **(d)** — accept time-homogeneous `A`; track Phase 10b for options (a)/(b) from decisions §3.1. |
| **Dependencies** | None blocking; pairs with observation data (F-15). |

---

### F-15 — Seven-element observation vector

| Item | Detail |
|------|--------|
| **Spec** | Doc 22 **§4** — `n_signals`, `mean_OO`, `volume_z`, `vix_level`, `prior_session_pnl`, `cross_asset_corr`, `day_of_week`; **versioned alignment** offline/online. |
| **Code** | `build_observation_panel_stub` (**lines 189–206**) returns **empty** `(obs, session_pnl, n_days)` with `n_days=0` → forces cold-start branch (**lines 78–90**). **No** `compute_observation_vector` in repo. Related feature atoms: `shared/aim_feature_loader.py` (e.g. D29 volumes, AIM features), QuestDB tables per `shared/canonical_schemas.py`; **session-level aggregator for all seven is missing.** |
| **Delta** | Entire PG-01C **feature ETL** absent. Each feature needs a defined source query or derived series [VERIFY] per integration point. |

---

### F-16 — `opportunity_weights` and D26 writers

| Item | Detail |
|------|--------|
| **Spec** | Doc 22 **§6–§7** — persist model to D26; budget weights from **normalised** state probabilities × map + floor; forward + **α=0.3** smoothing [CONFIRM: vector vs logits per doc 22 §7]. |
| **Code (train)** | `train_aim16_hmm` sets `"opportunity_weights": {}` with comment online will populate (**lines 84–85, 99, 155**). |
| **Code (persist)** | `save_hmm_state` **lines 166–186** — single `INSERT` into `p3_d26_hmm_opportunity_state` including `current_state_probs`, `opportunity_weights`, plus training fields. |
| **Code (read)** | `shared/aim_compute.py` **lines 175–197** — loads `opportunity_weights`, `n_observations`, `cold_start`. `captain-online/.../b5_trade_selection.py` **lines 217–232** `_load_hmm_opportunity_state` — same D26 read for `apply_hmm_session_allocation` (**lines 137–187**). `shared/replay_engine.py` (~308–323) optionally reads `hmm_params` from D26. |
| **Writers (grep)** | **Only** `save_hmm_state` in `b1_aim16_hmm.py` writes D26 (application code). |
| **Delta** | `opportunity_weights` never populated by a live **online inference** path; **Q-11 split** not implemented (single writer writes all columns). |

---

### Phase 3 wiring vs “empty” semantics

| Component | Status |
|-----------|--------|
| Dispatch | **OK** — see F-01 section above. |
| `build_observation_panel_stub` | **Empty by design** — Phase 10 replaces. |
| `train_aim16_hmm` | Runs but with **T=0** observations → cold-start return. |
| `save_hmm_state` | **Runs** each session close; persists cold-start JSON. |
| Online B5 HMM | **Reads** D26; falls back to **1/3** per session when weights empty. |

---

### Dependencies and libraries

- **`hmmlearn`:** listed in `captain-offline/requirements.txt` (`hmmlearn>=0.3`); `b1_aim16_hmm.py` imports `GaussianHMM`.  
- **No separate `hmm_inference` function** matching doc 33 PG-23 line `hmm_inference(P3-D26, features, session_id)` — behavior is **split** across `run_aim_aggregation` (D26 read for `session_budget_weights` only) and `apply_hmm_session_allocation` (second D26 read). **Gap:** `aim["session_budget_weights"]` is **not** consumed in `orchestrator._process_user_sizing` (~624–640) — B5 uses its own loader. **Phase 10.6** should align naming and avoid double-read divergence [CONFIRM].

---

### D26 schema vs decisions log §4.3

`shared/canonical_schemas.py` **`D26_HMM_OPPORTUNITY_STATE`** (**lines ~341–359**) defines `p3_d26_hmm_opportunity_state` with:  
`hmm_params`, `current_state_probs`, `opportunity_weights`, `prior_alpha`, `last_trained`, `training_window`, `n_observations`, `cold_start`, `last_updated`.  
This **matches** decisions log **§4.3** column list (canonical table name **`p3_d26_hmm_opportunity_state`**; decisions shorthand `p3_d26_hmm_states`).

---

### Observation feature — source discovery status

| Feature | Source in repo [VERIFY until wired] |
|---------|--------------------------------------|
| `n_signals` | **No** single helper found — derive from signals / logs [VERIFY: QuestDB tables for session-level signal counts]. |
| `mean_OO` | **No** direct `mean_OO` — [VERIFY: link to OO definition in B1/signal pipeline]. |
| `volume_z` | Partial patterns: `opening_volume_ratio` / D29 in `aim_feature_loader.py` — **session z** may need new aggregation. |
| `vix_level` | **Likely** from market data / features dict in B1 — [VERIFY]. |
| `prior_session_pnl` | **Likely** `p3_d03_trade_outcome_log` aggregates — depends Phase 1 `model_m` / session pairing. |
| `cross_asset_corr` | **Likely** `p3_d07_correlation_model_states` or similar — `b5_trade_selection._load_correlation_matrix` pattern. |
| `day_of_week` | Deterministic from session calendar. |

---

### Cross-phase boundaries

- **Phase 11 (governance):** No rollback/snapshot work in scope unless a D26 write requires `snapshot_before_update` — **out of scope** unless product mandates.  
- **Phase 12 (hygiene):** Per-AIM file split (Q-36) — **not** in Phase 10.  
- **Phase 1 D03:** Session P&amp;L features for `prior_session_pnl` must respect Phase 1 schema (`model_m`, etc.).

---

### Proposed batch structure (Stage 1 output)

1. **10.1** — D26 schema / comments / ratification vs runtime INSERT (no DB migration).  
2. **10.2** — Observation vector builder (F-15) + versioning hook.  
3. **10.3** — Time-homogeneous training (F-14 partial), 60×4 window, seeding vs doc 22 §6 [CONFIRM quartiles vs P25/P75].  
4. **10.4** — D26 writer split (F-16 + Q-11) — offline vs online columns; UPSERT/merge strategy.  
5. **10.5** — AIM-16 modifier / PG-23 integration semantics (`_aim16_hmm`, MoE if needed).  
6. **10.6** — Online inference: forward + α=0.3 + `opportunity_weights` write; align B3/B5 vs spec PG-23/PG-25B.  
7. **10.7** — Tests (schema, round-trip, HMM invariants, observation completeness, offline/online parity).

---

## Implementation batches

---

### Batch 10.1 — D26 schema ratification and writer/reader documentation

**Spec citation chain:** Decisions log **§4.3**; audit **F-16** (persistence expectations); doc 22 **§6–§7**; doc 32 **PG-01C** (lines ~86–88); Q-11 split (Group B).

**Pre-flight checks**

- Phase 3 wiring present: `captain-offline/.../orchestrator.py` `_handle_session_close` / `_run_aim16_hmm_training` (verified **~557–633**).  
- **Q-10:** **(d)** time-homogeneous v1.  
- **Batch 10.4:** Q-11 **confirmed** for this campaign (user + decisions interpretation) — **not BLOCKED**.  
- Dependencies: none.

**Files to create or modify**

| Path | Action |
|------|--------|
| `shared/canonical_schemas.py` | Tighten comments on `D26_HMM_OPPORTUNITY_STATE` (~341–360): authoritative column list, **Q-11 writer split**, pointer to Phase 10 merge semantics. |
| `scripts/verify_questdb_state.py` | If `check_d26_hmm` assumes a monolithic writer, update expectations (optional). |

**Exact change shape**

- **Before** (`canonical_schemas.py` excerpt ~341–347):

```python
# Writer split (per Q-11 interpretation, subject to Isaac re-confirm):
#   offline PG-01C → hmm_params, training_window, n_observations, last_trained
#   online PG-23/PG-25B → current_state_probs, opportunity_weights, last_updated
```

- **After:** Replace “subject to Isaac re-confirm” with **“confirmed 2026-04-28 Phase 10 plan (Nomaan); implementation in Batch 10.4.”** Add one line: **`cold_start`** and **[CONFIRM] `prior_alpha`** ownership.

**Test additions**

- `tests/test_schema_migrations.py` — `test_b4_d26_column_set_ratification` — **keep** exact 9-column assertion (lines ~147–157).

**Exit criteria**

- Grep confirms no second D26 CREATE with divergent columns; `test_b4_d26_column_set_ratification` passes.

**Rollback**

- `git checkout -- shared/canonical_schemas.py` (and any touched scripts).

---

### Batch 10.2 — Observation vector builder (F-15)

**Spec citation chain:** Doc 22 **§4** (features + versioning); audit **F-15**; doc 32 **PG-01C**; Q-03 (session-global model — one panel for shared HMM).

**Pre-flight checks**

- Q-10: **(d)**.  
- D26 table exists (Phase 1 / existing deploy).  
- Batch 10.3 depends on **deliverables here** (real `observations` ndarray + `session_pnl` vector).

**Files to create or modify**

| Path | Action |
|------|--------|
| `captain-offline/captain_offline/blocks/b1_aim16_hmm.py` | Replace **`build_observation_panel_stub`** (~189–206) with **`build_observation_panel`** (or new module `b1_aim16_observations.py` if size warrants — [VERIFY] size before split). |
| `captain-offline/captain_offline/blocks/orchestrator.py` | `_run_aim16_hmm_training` (~620): call real builder instead of stub. |

**Exact change shape**

- **Before** (`orchestrator.py` ~600–624):

```python
        from captain_offline.blocks.b1_aim16_hmm import (
            train_aim16_hmm,
            save_hmm_state,
            build_observation_panel_stub,
        )
        ...
        obs, session_pnl, n_days = build_observation_panel_stub(asset_universe)
```

- **After:** Import **`build_observation_panel`** (or same name), pass `asset_universe`, `closed_at` / session calendar context, **`lookback_days=60`**, return `(obs, session_pnl, n_trading_days)` with shape **(T, 7)** and **T ≤ 240** for full window semantics per doc 22 §6.

- **Before** (stub):

```python
def build_observation_panel_stub(...):
    obs = np.zeros((0, N_FEATURES), dtype=float)
    session_pnl = np.zeros((0,), dtype=float)
    return obs, session_pnl, 0
```

- **After:** Implementation that queries/computes **all seven** features; attach **`obs_schema_version`** constant (e.g. `1`) for future alignment with online inference.

**Test additions**

- `tests/test_aim16_observation_panel.py` (new): with **Fixture or mocked QuestDB**, assert shape **(T, 7)**, no NaNs after fill policy, **`day_of_week`** in valid range.

**Exit criteria**

- Unit tests pass; `_run_aim16_hmm_training` logs **non-zero** `n_trading_days` in integration when DB has sufficient history [VERIFY CI data].

**Rollback**

- `git checkout -- captain-offline/captain_offline/blocks/b1_aim16_hmm.py captain-offline/captain_offline/blocks/orchestrator.py` and remove new test file.

---

### Batch 10.3 — HMM training (time-homogeneous v1, F-14 partial)

**Spec citation chain:** Decisions **§3.1 option (d)**; doc 22 **§5–§6** (π, **A** time-homogeneous for v1, μ_k, Σ_k diagonal); audit **F-14**; `b1_aim16_hmm.py` existing `GaussianHMM` path.

**Pre-flight checks**

- Batch **10.2** complete (real observations possible).  
- Q-10: **(d)**.  
- `hmmlearn` available (`captain-offline/requirements.txt`).

**Files to create or modify**

| Path | Action |
|------|--------|
| `captain-offline/captain_offline/blocks/b1_aim16_hmm.py` | Align `_label_from_pnl` with doc 22 **§6** “quartile” wording — **either** true quartiles **or** document P25/P75 as engineering proxy [CONFIRM]. Ensure `n_trading_days` vs `T` consistency. Add **comment block** “TVTP deferred to Phase 10b (Q-10d).” |

**Exact change shape**

- **Before** (`_label_from_pnl` ~54–60): P25/P75 labels.  
- **After:** **Doc-true quartile labels** (or explicit DEC with Isaac).  
- **Before** (model init ~128–129): uniform `transmat_`.  
- **After:** **Keep** uniform init for **(d)** — **no TVTP**. Optional: **log** final `A` row-sums to 1.0 for debugging.

**Test additions**

- `tests/test_aim16_hmm_train.py`: small **synthetic** `(T,7)` and `session_pnl`, assert `hmm_params` JSON round-trips, **row-stochastic** `A`, diagonal `sigma` > 0.

**Exit criteria**

- `train_aim16_hmm` returns non-`None` `hmm_params` when `T >= 240` and labels valid.

**Rollback**

- `git checkout -- captain-offline/captain_offline/blocks/b1_aim16_hmm.py`

---

### Batch 10.4 — D26 writer split (F-16, Q-11)

**Spec citation chain:** Decisions **§4.3** + **Group B Q-11**; audit **F-16**; doc 22 **§6–§7**; doc 33 **PG-23** / **PG-25B** (inference writes D26).

**Pre-flight checks**

- Batches **10.2–10.3** produce training outputs.  
- **Q-11** **confirmed** (this plan).  
- **Q-10:** **(d)**.

**Files to create or modify**

| Path | Action |
|------|--------|
| `captain-offline/.../b1_aim16_hmm.py` | **`save_hmm_state`** (~166–186): write **only** offline-owned columns **or** use `UPDATE ...` merge — [VERIFY QuestDB partial UPSERT pattern]. Stop writing **`opportunity_weights`** (always `{}`) from offline; **stop full overwrite** of `current_state_probs` if Q-11 assigns them to online **OR** merge last-known online values from prior row. |
| `captain-online/.../` **new or** `b5_trade_selection.py` / dedicated **`hmm_online_inference.py`** | Implement **online writer** for `current_state_probs`, `opportunity_weights`, `last_updated` after forward + normalization + smoothing. |

**Exact change shape**

- **Before** (`save_hmm_state`): single INSERT of all nine logical fields from one `state` dict.  
- **After:**  
  - Offline INSERT/UPSERT: `hmm_params`, `training_window`, `n_observations`, `cold_start`, `last_trained` — **minimal** merge with existing online fields (read-modify-write **or** two-column-family pattern) [VERIFY].  
  - Online: **`INSERT`** or **`UPDATE`** setting `current_state_probs`, `opportunity_weights`, `prior_alpha` (if used), **`last_updated`**.

**Test additions**

- Integration test with mocked cursor: offline write does **not** null out pre-populated **`opportunity_weights`** when merging.

**Exit criteria**

- Documented reconciliation: after offline train + online inference cycle, D26 row has consistent **`hmm_params`** from offline and **`opportunity_weights`** from online.

**Rollback**

- Revert edits to **`save_hmm_state`** and new online writer; restore monolithic INSERT (tech-debt note in commit message).

---

### Batch 10.5 — AIM-16 dispatch semantic correctness (`_aim16_hmm`, PG-23)

**Spec citation chain:** Doc 33 **§Block 3** (AIM-16 session budget weights); DEC-06 (AIM-16 not standard per-asset MoE modifier); `shared/aim_compute.py`; audit **F-16** downstream.

**Pre-flight checks**

- Batch **10.4** provides populated **`opportunity_weights`** online.  
- Phase 3 **`run_aim_aggregation`** remains entry point (**~305–309** orchestrator).

**Files to create or modify**

| Path | Action |
|------|--------|
| `shared/aim_compute.py` | **`_aim16_hmm`** (~697–709): today returns **1.0 / `HMM_NO_DATA`** unless `state["current_modifier"]` dict. Align with product: **either** exclude AIM-16 from MoE `range(1,17)` when session budget owns AIM-16 [VERIFY product], **or** pass neutral modifier **`1.0`** with explicit tag **`HMM_SESSION_BUDGET_ONLY`**. **`run_aim_aggregation`** may need to **skip MoE inclusion** for AIM-16 (**lines 113–143**) — [CONFIRM] with DMA/canvas. |

**Exact change shape**

- **Before** (`_aim16_hmm`):

```python
    current = state.get("current_modifier")
    if current is not None and isinstance(current, dict):
        ...
    return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "HMM_NO_DATA"}
```

- **After:** Deterministic neutral participation in MoE **without double-counting** session budget loaded in **`apply_hmm_session_allocation`**.

**Test additions**

- `tests/test_b3_aim.py` — update AIM-16 expectations if MoE skips AIM-16.

**Exit criteria**

- No inflated Kelly from **duplicate** AIM-16 application (session budget vs modifier).

**Rollback**

- `git checkout -- shared/aim_compute.py`

---

### Batch 10.6 — Online inference path (forward + smoothing, PG-25B / doc 33)

**Spec citation chain:** Doc 22 **§7** (forward, smoothing **α=0.3**, budget map); doc 33 **PG-23 step 3** (`hmm_inference`); **`docs/captain-core-docs/16_HMM_Opportunity_Regime_Spec.md`** §3.6 (pseudocode for PG-25B-style inference — corroborating, not over doc 22); audit **F-14/F-16**.

**Pre-flight checks**

- **`hmm_params`** readable from D26; observation at inference time computable with **same builder version** as offline (Batch 10.2).  
- Q-10: **(d)** (forward uses fixed `A` from training).

**Files to create or modify**

| Path | Action |
|------|--------|
| New: e.g. `captain-online/captain_online/blocks/b1_hmm_inference.py` **or** `shared/hmm_inference.py` | Implement **`hmm_forward_opportunity_weights(hmm_params, obs_history, ...)`** → dict **`NY`/`LON`/`APAC`** (match **`b5`** keys **157** Session map `{1:'NY',2:'LON',3:'APAC'}`). Apply **`SMOOTHING_ALPHA = 0.3`** per doc 22 **[CONFIRM vector vs logits]**. Normalize + **floor 0.05** per existing **`FLOOR_PER_SESSION`** in `b1_aim16_hmm.py` (**line 44**). |
| `captain-online/.../orchestrator.py` | Invoke inference **after** B1 features or before B5 — [VERIFY pipeline hook: **once per session** when AIM-16 active]. Persist via Batch **10.4** writer. |
| `shared/aim_compute.py` | Optionally replace duplicate D26 read with single **`hmm_inference`** result passed into orchestrator (closes gap where **`session_budget_weights`** is computed but unused in sizing — **lines 175–203**). |

**Exact change shape**

- **Before:** `apply_hmm_session_allocation` only reads stale D26; no forward pass recomputes probabilities using **today’s** partial observations.  
- **After:** Documented forward step + write **`opportunity_weights`** + **`last_updated`**.

**Test additions**

- `tests/test_hmm_online_inference.py`: synthetic `hmm_params`, two-step forward, asserts weights sum to **1** after norm, floor applied, smoothing changes state vs unsmoothed.

**Exit criteria**

- After a full session, D26 **`opportunity_weights`** JSON non-empty for **`NY`/`LON`/`APAC`** keys (or spec’d key scheme).

**Rollback**

- Remove new module and orchestrator hook; revert B5 to read-only.

---

### Batch 10.7 — Tests and verification matrix

**Spec citation chain:** All above; doc 32 **PG-01C**; doc 33 **PG-23/25/25B**.

**Pre-flight checks**

- Batches **10.1–10.6** complete.

**Files**

| Path | Purpose |
|------|---------|
| `tests/test_d26_hmm_round_trip.py` (new) | Write training fields, read back, assert JSON shapes. |
| `tests/test_hmm_phase10_e2e.py` (new) | Mark **integration** / container if needed. |
| `tests/test_offline_session_close_dispatch.py` | Extend if new builder changes mock contract. |

**Assertions (mandatory)**

- **Schema:** nine columns, types per `canonical_schemas.py`.  
- **Round-trip:** `save` (offline) + online update → read.  
- **HMM:** `A` rows sum to 1; means length 7.  
- **Observation vector:** all 7 finite.  
- **Offline/online:** same feature definition constant (`OBS_SCHEMA_VERSION`).  
- **TVTP N/A for v1** — skip covariate Monday/Friday assert; **add Phase 10b** placeholder test file `skip` or `xfail`.

**Exit criteria**

- `pytest tests/test_aim16_*.py tests/test_hmm_*.py tests/test_d26_*.py` green in CI image with `hmmlearn` + `scipy`.

**Rollback**

- Delete new test files; revert `pytest` config if added.

---

## Plan-level rollback (entire phase)

```bash
git revert <commit_range_for_phase10>   # or git reset --hard <sha_before_phase10> on feature branch
```

Restore QuestDB D26 rows from backup if test data pollution matters (no migration expected).

---

## Open items explicitly not invented here

- **[CONFIRM]** Smoothing α applies to **probability vector** vs **logits** (doc 22 §7).  
- **[CONFIRM]** MoE: should AIM-16 be **excluded** from **`range(1,17)`** loop?  
- **[CONFIRM]** `prior_alpha` and **`cold_start`** column ownership under Q-11.  
- **[VERIFY]** Exact QuestDB queries for **`n_signals`**, **`mean_OO`** (Batch 10.2).  
- **[VERIFY]** Orchestrator injection point for online forward pass vs **`_run_session`** timing.

---

*End of Phase 10 build plan.*
