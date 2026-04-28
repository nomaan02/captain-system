# Phase 9 Build Plan — Block 9 System Health Diagnostic (`b9_diagnostic.py`)

**Status:** Approved for execution (Stage 2)  
**Date:** 2026-04-28  
**Executor:** Cursor Composer 2 (batch-by-batch; complete each batch before starting the next)

**Companion documents (authority order):**

1. `docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md` — §2 Group H (Q-19–Q-21, Q-34), §5 Phase 9 row, §4.2 schema notes  
2. `docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md` — F-35, F-36, F-37  
3. `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` — Block 9 (lines ~721–749)  
4. `shared/canonical_schemas.py` — `p3_d03_trade_outcome_log`, `p3_d22_system_health_diagnostic`, `p3_d22b_asset_rerun_status`

**§3.2 re-asks affecting Phase 9:** None identified; Q-21 is **resolved** as defer D7 (not an open §3.2 item).

---

## Pre-campaign audit snapshot (verified line ranges)

| Topic | Location | Notes |
|--------|-----------|--------|
| `compute_d3` | `captain-offline/captain_offline/blocks/b9_diagnostic.py` ~267–354 | Uses global `max(ts)` from `p3_d06_injection_history`; duplicates injection-based weights; reads `p3_d22b_asset_rerun_status` for per-asset `last_p1p2_rerun_ts` but global injection still dominates composite |
| `compute_d4` | Same file ~361–433 | D02 inclusion/dormancy heuristic; `/15.0` denominator |
| `compute_d7` | Same file ~633–710 | Injection / L3 / expansion — **contradicts Q-21 defer** |
| `run_diagnostic` | Same file ~840–910 | WEEKLY skips `compute_d5` (~861–862); builds `overall_health` as `sum(scores)/len(scores)` (~868) |
| Per-asset rerun DDL | `shared/canonical_schemas.py` ~566–574 | `p3_d22b_asset_rerun_status(asset, last_p1p2_rerun_ts, …)` |
| Aggregate D22 DDL | `shared/canonical_schemas.py` ~549–564 | No `last_p1p2_rerun_ts` column on **`p3_d22_system_health_diagnostic`** (system-wide diagnostic row) |
| Callers of `run_diagnostic` | `captain-offline/captain_offline/blocks/orchestrator.py` ~467–469, ~1128–1129, ~1173 | WEEKLY / MONTHLY / ACTION_RESOLVED |

**Phase 1 dependency (D3):** Per-asset **`last_p1p2_rerun_ts`** exists on **`p3_d22b_asset_rerun_status`** (Phase 1 companion tests in `tests/test_schema_migrations.py` ~103–144). The decisions log **words** Q-19 as a column on **`p3_d22_system_health_diagnostic`**; canonical DDL uses the **D22b** table for per-asset timestamps. Phase 9 implementations **must read from `p3_d22b_asset_rerun_status`** (or reconcile DDL if product insists on a literal column on `p3_d22_system_health_diagnostic` — would be a **schema migration**, out of scope unless Batch 0 added).

---

## Batch 1 — F-35 / Q-19 — D3 Model staleness (per-asset P1/P2 age)

### 1.1 Batch ID and title

**B1_F-35_D3_per_asset_staleness**

### 1.2 Spec citation

- **Decisions:** §2 Group H Q-19; §4.2 (`last_p1p2_rerun_ts` read by D3 staleness in `b9_diagnostic.py`).  
- **Audit:** F-35 (`2026-04-22_offline_spec_vs_code_audit copy.md` ~849–868).  
- **Pseudocode:** `32_P3_Offline_Full_Pseudocode.md` Block 9 table — D3 “Days since last P1/P2 re-run **per asset**” (~731).

### 1.3 Pre-flight checks

- [ ] `SHOW COLUMNS FROM p3_d22b_asset_rerun_status` includes `last_p1p2_rerun_ts` (see `tests/test_schema_migrations.py` ~103–112).  
- [ ] Writers to `last_p1p2_rerun_ts` exist or are planned (decisions: Command / offline dispatcher when P1/P2 completes); if always NULL in dev, D3 tests must inject fixture rows.  
- [ ] Confirm no duplicate authoritative sources: remove reliance on **`max(ts)` from `p3_d06_injection_history`** for **per-asset** staleness scoring where Q-19 applies.

### 1.4 Files and line ranges to modify

| File | Lines (approx.) | Change |
|------|-----------------|--------|
| `captain-offline/captain_offline/blocks/b9_diagnostic.py` | 267–354 | Restructure `compute_d3` |
| Same | 820–827 | `_check_constraint_resolution` branch `PIPELINE_STALENESS` — align “improved” predicate with new staleness definition |

### 1.5 Exact change shape (before → after)

**Before**

- Global `days_since_injection` from `SELECT max(ts) FROM p3_d06_injection_history` feeds score weights (0.3 + 0.2 duplicate) and **`PIPELINE_STALENESS`** actions (~269–273, ~324–331, ~349–354).  
- Per-asset ages use `p3_d22b_asset_rerun_status` only inside `regime_model_ages` merge (~284–302).

**After**

- **Primary D3 staleness signal:** for each active asset, **days since `last_p1p2_rerun_ts`** from **`p3_d22b_asset_rerun_status`** (existing `LATEST ON … PARTITION BY asset` query pattern ~284–289). If NULL/missing row, define deterministic fallback (e.g. max days or conservative score) **documented in code comment** referencing Q-19 — avoid silently substituting global injection age as proxy for per-asset P1/P2.  
- **Remove duplicated weight lines** that both used global injection (~349–354): replace with independent components aligned to spec (regime age, AIM retrain age, **aggregate per-asset P1/P2 staleness** — exact inner `_weighted_mean` weights must sum sensibly and match §removal of duplicate injection term per F-35).  
- **`PIPELINE_STALENESS`:** either re-target to **worst per-asset** staleness across portfolio, or drop global injection title/body in favour of per-asset messaging — **must not** contradict “per asset” wording.

### 1.6 Test additions

| File | Assertions |
|------|------------|
| **New:** `tests/test_b9_diagnostic_d3.py` (or `tests/test_b9_diagnostic.py`) | **(1)** Mock/fixture QuestDB or stub `get_cursor`: when `p3_d22b_asset_rerun_status` returns known timestamps per asset, `compute_d3` score moves in expected direction when one asset’s `last_p1p2_rerun_ts` ages. **(2)** Global injection `max(ts)` mutation does **not** change D3 score when D22b data fixed (proves decoupling). **(3)** Empty D22b → graceful behaviour (no crash; bounded score), consistent with `test_b3_compute_d3_empty_table_graceful` (~136–144 `tests/test_schema_migrations.py`). |

Reuse project test DB patterns from existing offline tests (`tests/conftest.py` if present).

### 1.7 Exit criteria

- `compute_d3` docstring and audit trail reflect **per-asset** P1/P2 age from **`p3_d22b_asset_rerun_status`**.  
- No composite term **double-counting** the same global injection series (F-35).  
- `PIPELINE_STALENESS` / D8 verification branch for `PIPELINE_STALENESS` consistent with new definition.

### 1.8 Rollback procedure

- Revert commits touching `b9_diagnostic.py` / new test file; restore prior `compute_d3` from git.  
- Data migration not required (read-only behaviour change).

---

## Batch 2 — F-36 / Q-20 — D4 AIM effectiveness (monthly hit rate)

### 2.1 Batch ID and title

**B2_F-36_D4_monthly_aim_hit_rate**

### 2.2 Spec citation

- **Decisions:** §2 Group H Q-20 — hit rate = modifier direction agrees with subsequent PnL sign; **window = monthly**; replace inclusion-weight proxy.  
- **Audit:** F-36 (~872–891).  
- **Pseudocode:** Block 9 — D4 “Per-AIM modifier accuracy, PnL attribution by modifier direction” (~732).

### 2.3 Pre-flight checks

- [ ] `p3_d03_trade_outcome_log` columns: `pnl`, `ts`, `direction`, `aim_breakdown_at_entry STRING` — see `shared/canonical_schemas.py` ~398–424.  
- [ ] Confirm JSON shape for `aim_breakdown_at_entry`: keyed by aim id string → `{ "modifier": float, … }` (see `captain-offline/.../b1_dma_update.py` ~189–192).  
- [ ] **Monthly definition:** implement **rolling calendar-month window** ending at `now_et()` (or UTC per project norm) **or** last 30/31 days — **pick one** and document in module docstring; decisions phrase “rolling monthly” (~Phase 9 narrative) supports rolling window; **do not** introduce weekly or daily cadence.

### 2.4 Files and line ranges to modify

| File | Lines (approx.) | Change |
|------|-----------------|--------|
| `captain-offline/captain_offline/blocks/b9_diagnostic.py` | 361–433 | Replace `compute_d4` implementation |
| Same | 11–24 | Update module header comments if D4 description changes |

### 2.5 Exact change shape (before → after)

**Before**

- Loads `p3_d02_aim_meta_weights`, `p3_d01_aim_model_states`; scores active/dormant/dominant/warmup (~362–433).

**After**

- **Per AIM `a`:** over trades in the **monthly window**, compute **hit rate** = fraction of trades where **modifier directional agreement with trade outcome** holds per Q-20. Use `aim_breakdown_at_entry[str(a)]["modifier"]` and realised **`pnl`** (and **`direction`** if needed for sign convention). Exact rule must match trading semantics: if ambiguity remains, encode the minimal rule in tests (e.g. bullish modifier + long + positive PnL ⇒ hit — **derive from existing DMA likelihood philosophy** in `b1_dma_update.py` without copying inclusion weights).  
- **D4 aggregate score:** combine per-AIM hit rates into a single score **∈ [0, 1]** (mean of per-AIM rates, or min — **use unweighted mean across AIMs that appear in window**, clamp). **Do not** use `/15.0` if AIM count differs — use **dynamic count** from active AIM set or from breakdown keys.  
- **Queue actions:** refresh messages so they reference hit-rate / attribution failures, not dormant/dominance alone (keep dormancy as secondary optional signal only if still desired — **decisions supersede**: primary metric is hit rate).

### 2.6 Test additions

| File | Assertions |
|------|------------|
| `tests/test_b9_diagnostic_d4.py` | **(1)** Synthetic trades in-window vs out-of-window — only in-window rows affect score. **(2)** Known modifiers + pnls → known hit rate for one AIM. **(3)** Score clamped to [0, 1]. **(4)** Empty monthly window → deterministic neutral (0.0 or documented neutral). |

### 2.7 Exit criteria

- `compute_d4` does **not** depend on inclusion_probability dormancy as **primary** driver (F-36 cleared).  
- Monthly cadence only (Q-20); no alternate cadence in code paths.

### 2.8 Rollback procedure

- Git revert `compute_d4` and D4 tests; redeploy previous binary logic.

---

## Batch 3 — F-37 / Q-21 — D7 deferred (remove or guard)

### 3.1 Batch ID and title

**B3_F-37_Q21_D7_deferred**

### 3.2 Spec citation

- **Decisions:** §2 Group H Q-21 — **DEFER** D7 for v1; weekly diagnostic **D1–D6 + D8 only** until queue infra exists; doc 32 update flagged (engineering/docs — optional note).  
- **Audit:** F-37 (~894–914) — partially superseded by Q-21 for D7 substance (queue-depth wiring **not** implemented).  
- **Pseudocode:** D7 row (~735) — informational; decisions defer implementation.

### 3.3 Pre-flight checks

- [ ] Grep `compute_d7` / `research_pipeline` consumers: only `run_diagnostic` and INSERT payload keys (`captain-command/.../b2_gui_data_server.py` reads JSON **`scores`** — confirm GUI tolerates missing key or expects placeholder).

### 3.4 Files and line ranges to modify

| File | Lines (approx.) | Change |
|------|-----------------|--------|
| `captain-offline/captain_offline/blocks/b9_diagnostic.py` | 633–710 | Delete **or** retain dead code behind `if False:` / feature flag default **off** (prefer **delete** + git history for clarity) |
| Same | ~865 | Remove `scores["research_pipeline"] = compute_d7(...)` |
| Same | 11–24 | Docstring: D7 deferred |

### 3.5 Exact change shape (before → after)

**Before**

- `run_diagnostic` always sets `scores["research_pipeline"]` (~865).

**After**

- **No D7 score** and **no `research_pipeline` key** in weekly/monthly outputs **or** explicit `null` / omission documented — **prefer omission** to avoid misleading downstream parsers seeing stale semantics.  
- **`_check_constraint_resolution`:** remove or adjust branches that reference **`LEVEL3_UNRESOLVED`** (~809–818) if those constraints were only queued by D7 — ensure D8 resolution logic does not reference removed constraint types (grep `LEVEL3`, `INJECTION_DROUGHT`).

### 3.6 Test additions

- Unit test: `run_diagnostic(mode="WEEKLY")` result dict **`scores`** has **no** `research_pipeline` key (or agreed sentinel).  
- Regression: no exception from GUI-facing INSERT JSON schema if Command expects fixed keys — **add integration check** or update `b2_gui_data_server.py` if it assumes seven keys.

### 3.7 Exit criteria

- Q-21 satisfied: no operational “candidate queue depth” / pending P1/P2 backlog scoring in v1.

### 3.8 Rollback procedure

- Restore `compute_d7` and `run_diagnostic` wiring from git.

---

## Batch 4 — F-63 / Q-34 — `overall_health` equal weights over active dimensions

### 4.1 Batch ID and title

**B4_Q34_overall_health_equal_weights**

### 4.2 Spec citation

- **Decisions:** §2 Group H Q-34 / §3.3 — weighted mean operator; **equal weights for v1**; document tunable later. §5 Phase 9 row ties to equal weights with D7 deferred.  
- **Pseudocode:** `overall_health = weighted_mean(d1..d8)` (~747) — **decisions** specify defer D7 and equal weights; effective subset is **active dimensions only**.

### 4.3 Pre-flight checks

- [ ] After Batch 3, enumerate keys in `scores` for WEEKLY vs MONTHLY (WEEKLY: typically **no** `edge_trajectory`; MONTHLY: includes `edge_trajectory`; **no** `research_pipeline`).  
- [ ] Confirm denominator: **N = number of keys included** (equal **1/N**), **not** fixed 8 while omitting D7.

### 4.4 Files and line ranges to modify

| File | Lines (approx.) | Change |
|------|-----------------|--------|
| `captain-offline/captain_offline/blocks/b9_diagnostic.py` | ~856–868 | Replace `overall = sum(scores.values()) / len(scores)` with explicit **equal-weight mean over declared dimension list** |

### 4.5 Exact change shape (before → after)

**Before**

```python
overall = sum(scores.values()) / len(scores) if scores else 0.0
```

**After**

- Define ordered list of dimension keys participating in **`overall_health`** for each **mode** (e.g. WEEKLY: six dimensions after dropping D5 and D7 — **align with Batch 5 decision on D5**).  
- `overall_health = mean(selected scores only)`.  
- **Forbidden:** Introducing non-equal weights or magic coefficients (Q-34).

### 4.6 Test additions

- Assert WEEKLY `overall_health` equals arithmetic mean of the configured WEEKLY keys (fixture scores).  
- Assert MONTHLY includes `edge_trajectory` in mean when present.

### 4.7 Exit criteria

- Document in docstring: equal weights **1/N** over active diagnostic dimensions for this mode.

### 4.8 Rollback procedure

- Restore single `sum/len` line.

---

## Batch 5 — F-37 (optional) — D5 weekly scheduling vs spec wording

### 5.1 Batch ID and title

**B5_F-37_D5_schedule_disambiguation** (**OPTIONAL / product gate**)

### 5.2 Spec citation

- **Audit:** F-37 (~894–906) — WEEKLY omits `compute_d5`.  
- **Decisions §5 Phase 9 row:** Lists D4, D3, D7 defer, equal weights — **silent** on forcing D5 into WEEKLY.  
- **Pseudocode:** Comment block (~739–740) “weekly (D1–D7) and monthly (D5 deep analysis)” — ambiguous vs current code (`run_diagnostic` ~861–862).

### 5.3 Recommendation

- **Default for Phase 9:** **do not** change D5 scheduling unless product explicitly adopts audit’s “light weekly D5” — decisions Phase 9 row did not mandate it.  
- If executed: add **`compute_d5_light`** or call **`compute_d5`** on WEEKLY with documented reduced inputs — requires separate test matrix.

### 5.4 Exit / rollback

- N/A if skipped; if implemented, revert orchestrator + `run_diagnostic` mode branching.

---

## Final verification phase

### Checklist

1. `pytest tests/test_b9_diagnostic*.py tests/test_schema_migrations.py::test_b3_*` passes.  
2. Grep guards (anti-regression):

```bash
rg 'compute_d7|research_pipeline' captain-offline/captain_offline/blocks/b9_diagnostic.py
# Expect no compute_d7 definition/call if Batch 3 deletes — tune pattern accordingly
rg 'max\(ts\) FROM p3_d06_injection_history' captain-offline/captain_offline/blocks/b9_diagnostic.py
# Expect zero uses inside compute_d3 scoring after Batch 1 — adjust if legitimately used elsewhere with different semantics
```

3. Manual: run offline `run_diagnostic(WEEKLY)` in dev against seeded QuestDB — inspect latest `p3_d22_system_health_diagnostic` row JSON **`scores`** shape.

### §3.2 re-asks

- Confirm none introduced; if Isaac later re-opens Q-34 weights, this batch stands until superseded.

---

## Campaign rollback (whole Phase 9)

1. Revert merge branch or `git revert <phase9-merge-commit>`.  
2. Re-run QuestDB bootstrap — **no DDL rollback** expected from Phase 9 alone if batches stayed read-mostly.  
3. Restore GUI snapshots if `scores` key omission breaks Command UI — coordinate with `captain_command/blocks/b2_gui_data_server.py` (~869–898).

---

*End of Phase 9 build plan.*
