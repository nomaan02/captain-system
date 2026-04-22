---

## title: Captain System Spec-vs-Code Audit

date: 2026-04-22
auditor: Claude (Opus 4.7), read-only session
session_basis: replay_full_pipeline.py output 2026-04-21 22:53 ET on tower 2
mode: AUDIT ONLY — no code, config, or QuestDB changes performed

# Captain System — Spec-vs-Code Audit (2026-04-22)

## 1. Executive Summary


| Severity  | Count  |
| --------- | ------ |
| BLOCKING  | 4      |
| HIGH      | 4      |
| MEDIUM    | 3      |
| LOW       | 2      |
| **Total** | **13** |


- **QuestDB schema changes required:** 1 (additive, no destructive migrations).
- **Items blocked on Isaac clarification:** 5 (collected at §6).
- **Production-affecting bugs:** 9 (F-01 through F-09).
- **Replay-harness-only bugs:** 2 (F-10, F-11).

The replay symptom Isaac surfaced (CB blocking every micro-asset signal at L1) is the visible tail of three independent defects compounding: (a) the replay harness drops two CB kwargs (F-10), (b) `B1` never loads `topstep_params`/`topstep_state` from `P3-D08`, so even in production CB always uses cold-start defaults (F-01), and (c) `Command B8` SOD computation is gated on the wrong field and writes to the wrong table, so even if `B1` did load `topstep_state` there would be nothing to load (F-02, F-03). 

Independently, B4 sizes on a static 4-point SL while B6 sizes the realised SL volatility-scaled off OR range — the contract count and the realised dollar risk diverge by 1–2 orders of magnitude on micros (F-04). 

Regime probabilities collapse to 50/50 across all assets because `pettersson_threshold` is missing from every `P3-D00.locked_strategy` row (F-05). 

No spec contradiction was found between the six attached docs — there is one **spec silence** (Kelly L7 `strategy_sl` source, see clarification Q1) that affects how F-04 should be patched.

## 2. Spec Coverage Table


| Spec file (attached)                                    | Sections fully read                                                                                   | Coverage of audit scope                                                             | Notes / silences                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `08_Kelly_Sizing_Pipeline.md`                           | All 11 sections, all 7 layers                                                                         | Full Kelly L1–L7 semantics                                                          | **Silent on `strategy_sl` source** — line 260 says "SL distance in dollars per contract (strategy_sl × point_value)" without specifying whether `strategy_sl` is a static field of the locked strategy, the live `sl_multiple × or_range`, or a historical proxy. Affects F-04.                                                                                                                  |
| `Cross_Reference_PreDeploy_vs_V3.md`                    | All 6 P3-Online changes, 3 P3-Offline, 2 P3-Command, 3 architecture, 1 P1, 3 schema additions, AIM-16 | Full V3 amendment register                                                          | Provides verbatim Change C1, O3, O4, O5, A1 cited by code reviews below. Confirms `topstep_params: {p, e, c, lambda}` is an "Open Parameter" (architecture A3).                                                                                                                                                                                                                                  |
| `Nomaan_Edits_Fees.md`                                  | All 5 changes + verification checklist                                                                | Full CB layer + SOD spec (filename mismatch — see below)                            | **File-content mismatch**: file is named `Nomaan_Edits_Fees.md` but contains the Topstep Optimisation & Circuit Breaker Integration spec (5 changes). The actual fees-only doc referenced by `Cross_Reference O4/O5` is not in the upload. Surrogate coverage exists in `Topstep Optimisation Functions.md` Part 3.4 + `Cross_Reference` Change O4/O5 verbatim. **Open clarification Q4.**       |
| `P2-D06 + P3-D00.md`                                    | All 6 parts of the HMM Opportunity Regime spec                                                        | Full AIM-16 design + warm-up sequencing (filename mismatch)                         | **File-content mismatch**: file is named `P2-D06 + P3-D00.md` but contains the HMM Opportunity Regime System spec. **The actual P2-D06 / P3-D00 schema document is not in the upload.** Schemas were reverse-engineered from `b1_data_ingestion._load_active_assets`, `_load_locked_strategies`, `bootstrap_production.py`, and the Cross_Reference schema additions. **Open clarification Q5.** |
| `Topstep Optimisation & Circuit Breaker Integration.md` | All 5 changes                                                                                         | Same content as `Nomaan_Edits_Fees.md` (verbatim duplicate)                         | Treated as canonical for CB integration spec given the duplicate.                                                                                                                                                                                                                                                                                                                                |
| `Topstep Optimisation Functions.md`                     | Parts 1–8 (MDD math, payout, sizing, CB, function map, data sources, pseudotrader)                    | Full SOD parameter math, full 7-layer CB, P3-D08/D23/D25 schema, and B5C pseudocode | Authoritative for B5C and Command B8. Part 3.4 is authoritative for fee schedule semantics. Part 6 line 627 explicitly states B5C READS L_halt from `P3-D08[ac].topstep_state` — this is an architectural anchor for F-07.                                                                                                                                                                       |


## 3. Findings

Findings are ordered BLOCKING → HIGH → MEDIUM → LOW. Each finding is written to be actionable from itself without re-reading the codebase.

---

### F-01 — `B1` never loads `topstep_params` or `topstep_state` from `P3-D08`

**Severity:** BLOCKING

**Spec reference:** `Topstep Optimisation Functions.md` Part 6 (Online Block 7) lines 626–628: B5C must read SOD-locked params (`N`, `E`, `L_halt`, `f(A)`) from `P3-D08[ac].topstep_state`; Part 7 Category B explicitly maps every Topstep param to a `topstep_state.`* field on `P3-D08`.

**Code reference:** 

`[captain-online/captain_online/blocks/b1_data_ingestion.py:226-281`

`](captain-online/captain_online/blocks/b1_data_ingestion.py)`

**Divergence:** The TSM loader's `SELECT` clause at lines 230–241 omits the `topstep_params` and `topstep_state` columns of `p3_d08_tsm_state`. The dict returned at lines 252–280 therefore has no `topstep_params` key and no `topstep_state` key. Every downstream consumer (`B4._compute_topstep_daily_cap` line 380–386, `B5C._layer1_preemptive_halt` line 273–276, `B5C._layer2_budget` line 303–305, `B5C._layer4_correlation_sharpe` line 384–385) reads `tsm.get("topstep_params")` or `tsm.get("topstep_state")` and unconditionally falls back to the per-call defaults `c=0.5`, `e=0.01`, `lambda=0`, `daily_contract_cap=999`, `E_daily_exposure=0`.

**Downstream effect:** Production AND replay. Even with a correctly populated `P3-D08`, B5C computes `L_halt = 0.5 × 0.01 × current_balance` and B4 computes `topstep_daily_cap = 999`. None of the SOD-locked Topstep math is ever consulted at runtime. The user-visible failure on tower 2 (L1 halt at $750 on a $150k account) is consistent with this: the value is the cold-start default formula, not a value read from the database.

**Fan-out checked:** `b4_kelly_sizing.py:380-390` (reads only `tsm.get("topstep_state")`), `b5c_circuit_breaker.py:273-276, 303-305, 384-385` (reads only `tsm.get("topstep_params")`), `orchestrator.py:566-579` (passes the broken TSM dict through unchanged), `replay_full_pipeline.py:218-231` (same). Every consumer shares the defect because the data never leaves `B1`.

**QuestDB impact:** READ-ONLY. The columns `topstep_params` and `topstep_state` already exist in `p3_d08_tsm_state` (verified via `b4_tsm_manager.py:416` INSERT and `shared/canonical_schemas.py:215-216`).

**Proposed fix direction:** Extend the `SELECT` in `_load_tsm_configs` to include `topstep_params` and `topstep_state`, parse both via `parse_json`, attach to the returned dict. No schema or migration work needed. Verify by spot-checking `tsm["topstep_params"]["c"]` is non-empty after `B1` for an account with `topstep_optimisation=true`.
**Needs Isaac:** NO.

---

### F-02 — Command B8 SOD computation gated on `scaling_plan_active` instead of `topstep_optimisation`

**Severity:** BLOCKING

**Spec reference:** `Topstep Optimisation Functions.md` Part 6 ("Command Block 8 — Daily Reconciliation") and `Cross_Reference_PreDeploy_vs_V3.md` Change C1: SOD parameter computation must run for every account where `topstep_optimisation == true`, regardless of XFA/Live status. Live accounts have `topstep_optimisation=true` but `scaling_plan_active=false` (verified in `config/tsm/providers/topstep_150k_live.json:48,58`).

**Code reference:** `[captain-command/captain_command/blocks/b8_reconciliation.py:73-74](captain-command/captain_command/blocks/b8_reconciliation.py)`

**Divergence:** The reconciliation loop reads `if ac.get("scaling_plan_active"): _compute_sod_topstep_params(...)`. Per spec the gate is `if not tsm.get("topstep_optimisation"): continue`. The two are not equivalent: scaling is XFA-only and is correctly off for Live funded accounts.

**Downstream effect:** Production. Every Live Topstep funded account skips SOD computation entirely. Account 20319784 (the user's tower-2 account) is presumed Live based on the `current_balance=$150,000` and the absence of XFA scaling tier detail in the replay output. For these accounts no `computed_sod` block is ever written even by the (separately broken) write path of F-03. XFA accounts would have run SOD and triggered F-03, but the user's account doesn't even reach F-03.

**Fan-out checked:** `_get_all_accounts` line 477 selects `scaling_plan_active` and `topstep_optimisation` separately, so the data is available; only the gate condition is wrong. The reset block (`_reset_daily_counters`) at line 399 does run unconditionally for all accounts — no further fan-out impact.

**QuestDB impact:** NONE (logic-only change).

**Proposed fix direction:** Replace the `scaling_plan_active` gate with `topstep_optimisation`. Keep scaling-tier resolution inside the function gated on `scaling_plan_active` (call to `get_scaling_tier` at line 250) so Live accounts skip the XFA-only sub-block but still get f(A), R_eff, N, E, L_halt, W(A), g(A) computed.
**Needs Isaac:** YES — confirm that account 20319784 is the Live TSM (`topstep_150k_live.json`) and not the XFA TSM. The fix is the same either way, but it should be matched to the right account-type assertion in tests. (Q3 in §6.)

---

### F-03 — `_compute_sod_topstep_params` writes to `p3_session_event_log` instead of `p3_d08_tsm_state`

**Severity:** BLOCKING

**Spec reference:** `Topstep Optimisation Functions.md` Part 7 Category B: every SOD-derived parameter (`f_A`, `R_eff`, `N_max_trades`, `E_daily_exposure`, `L_halt`, `W_max_payout`, `g_A_post_payout_mdd`, `scaling_tier_micros`) is mapped to a field under `P3-D08[ac].topstep_state.`*. The Cross_Reference Change C1 reinforces that `topstep_state` is the persistence target.

**Code reference:** `[captain-command/captain_command/blocks/b8_reconciliation.py:589-604](captain-command/captain_command/blocks/b8_reconciliation.py)` — the helper named `_update_topstep_state` only inserts a `TOPSTEP_SOD_UPDATE` event row into `p3_session_event_log`. There is no `INSERT INTO p3_d08_tsm_state` carrying the new `topstep_state` JSON.

**Divergence:** The function name implies a D08 update; the implementation is an audit-log write only. The carefully computed `computed_sod` dict assembled at lines 254–276 is serialised, logged, and discarded — never reachable by any session-loop reader.

**Downstream effect:** Production (XFA accounts only — Live accounts already blocked at F-02). Even after F-01 and F-02 are fixed, every session-open `B1` would re-load the static `topstep_state` originally written by `_store_tsm_in_d08` (`b4_tsm_manager.py:385-390`), with `computed_sod` never present. Daily reset would never refresh CB caps as account balance compounds.

**Fan-out checked:** Searched repo-wide for any other writer of the `topstep_state` column in `p3_d08_tsm_state`; only `b4_tsm_manager._store_tsm_in_d08` writes the column, and it writes the static config block (no `computed_sod`). The replay engine (`shared/replay_engine.py:217`) constructs a `topstep_params` dict in-memory but never persists. So D08 has no rotating writer for `computed_sod`.

**QuestDB impact:** NONE if the fix reuses the existing `topstep_state STRING` column. Recommend keeping the audit-log row in `p3_session_event_log` (it's a useful trail), but ALSO writing a corrected `p3_d08_tsm_state` row with the merged `topstep_state` JSON via the same row-rewrite pattern used by `_update_account_balance` at lines 511–571.

**Proposed fix direction:** Rename `_update_topstep_state` to make its semantics explicit (`_persist_topstep_state_to_d08`), follow the `_update_account_balance` pattern (re-read latest D08 row, replace `topstep_state` field, insert new row), keep the event-log entry. Add a unit test that asserts a fresh `p3_d08_tsm_state` row appears with `computed_sod.L_halt > 0` after `_compute_sod_topstep_params` runs.
**Needs Isaac:** NO.

---

### F-04 — B4 sizes on `strategy.threshold` (default 4.0) but B6 sizes the realised SL on `sl_multiple × or_range`

**Severity:** BLOCKING

**Spec reference:** `08_Kelly_Sizing_Pipeline.md` §8 line 260 and `Topstep Optimisation Functions.md` Part 6 line 580: both use the symbol `strategy_sl × point_value` to define risk per contract, but neither doc specifies the source of `strategy_sl`. `bootstrap_production.py:106-108` has been written by the team with the comment "SL distance in points (B4 Kelly fallback)", documenting an assumed convention that the locked strategy carries a static `threshold` field separate from the live-computed `sl_multiple`. **This is a spec silence, not a contradiction** — the convention exists in the seed script but is not in any of the six attached spec docs.

**Code reference:**

- `[captain-online/captain_online/blocks/b4_kelly_sizing.py:163-208](captain-online/captain_online/blocks/b4_kelly_sizing.py)`: `strategy_sl = strategy.get("threshold", 4.0)`, then `risk_per_contract_with_fee = strategy_sl * point_value + expected_fee`.
- `[captain-online/captain_online/blocks/b6_signal_output.py:238-257](captain-online/captain_online/blocks/b6_signal_output.py)`: `_compute_sl` uses `sl_multiple = strategy.get("sl_multiple", 0.10)`; `sl_dist = sl_multiple * or_range`. The realised in-market SL distance is not communicated back to B4.
- `scripts/bootstrap_production.py:106-108`: seeds both fields but they are independent.
**Divergence:** B4 sizes contracts as `kelly × capital / (4.0 × point_value + fee)` for any asset whose locked strategy is missing a `threshold`. B6 then attaches an SL at `0.10 × or_range`. For the tower-2 replay assets the per-contract dollar risk implied by B4's denominator and the per-contract dollar risk B6 will actually realise diverge wildly:
  - MNQ (`point_value=$2`, OR≈100.5pt): B4 sizing risk = 4 × 2 = $8/contract; B6 realised SL = 10.05pt × $2 = ~$20/contract.
  - MYM (`point_value=$0.50`, OR≈120pt): B4 = 4 × 0.5 = $2/contract; B6 realised = 12pt × $0.50 = ~$6/contract.
  - ES (`point_value=$50`, OR≈13.75pt): B4 = 4 × 50 = $200/contract; B6 realised = 1.375pt × $50 = ~$68.75/contract.
  Because B4 always uses an SL distance larger than what B6 will use on these ORB assets, B4 over-counts dollar risk per contract and **under-allocates contracts**. Conversely, on assets where the realised SL distance exceeds 4 points (high-vol days), B4 would **over-allocate**. There is no consistency mechanism ensuring B4's denominator matches B6's actual stop level.

**Downstream effect:** Production AND replay. The user-visible symptom on tower 2 (10–15 contracts of micros that produce `rho_j` figures looking absurd) is the over-allocation half of this divergence. Sizing is decorrelated from realised dollar risk; Kelly's mathematical guarantees do not hold once the denominator and the actual stop disagree.
**Fan-out checked:**

- `kelly_pipeline.py` / `fee_resolver.py` — confirmed not present as separate files; the spec diagrams in `08_Kelly_Sizing_Pipeline.md` use them as logical names only. Implementation is inline in `b4_kelly_sizing.py`. No second consumer of `strategy_sl` to keep in sync.
- `b5c_circuit_breaker.py:99-104` — uses the same `strategy.threshold` field via `locked_strategies[u].threshold`. So when production passes `locked_strategies` (it does — orchestrator line 624) B5C and B4 use the **same** `strategy_sl`. This is internally consistent across B4 and B5C, but inconsistent with B6.
- `scripts/replay_session.py:330` — uses `strategy.get("threshold", 4.0)` identically to B4. Same defect.
- `shared/replay_engine.py` — uses `topstep_params` for risk math, separate code path; not impacted.
- **QuestDB impact:** Depends on resolution direction (Q1 in §6).
- If Isaac confirms B4 must use `sl_multiple × historical_avg_or_range` instead of a static `threshold`, no schema change is needed (historical OR range is already in `p3_d29_opening_volume` derivative datasets).
- If Isaac confirms B4 should keep using `threshold` but seed scripts must guarantee it for every asset, no schema change needed (`locked_strategy` is `STRING` JSON in `p3_d00_asset_universe`).
- If Isaac wants a separate `sizing_sl_distance` field added to `p3_d00_asset_universe`, that is a schema add (additive only).
- **Proposed fix direction:** Three viable shapes — wait on Q1 before patching. Whichever is chosen, add a B4 log warning when the fallback default of 4.0 is hit, so this regresses loudly next time.  
- **Needs Isaac:** YES — Q1 in §6 (single precise question).

---

### F-05 — `pettersson_threshold` missing from every `P3-D00.locked_strategy` row

**Severity:** HIGH

**Spec reference:** `Cross_Reference_PreDeploy_vs_V3.md` references `Program3_Online.md` Block 2 (P3-PG-22) and the locked-strategy schema as the source of `pettersson_threshold` for `BINARY_ONLY` regime models. The `P2-D06 + P3-D00.md` file in the upload covers HMM Opportunity Regime only and **does not contain the regime-classifier schema** — see Q5.

**Code reference:** `[captain-online/captain_online/blocks/b1_data_ingestion.py:310-329](captain-online/captain_online/blocks/b1_data_ingestion.py)` reads `pettersson_threshold` from inside the `locked_strategy` JSON blob loaded from `p3_d00_asset_universe`. `[captain-online/captain_online/blocks/b2_regime_probability.py:101-104](captain-online/captain_online/blocks/b2_regime_probability.py)` returns `None` for the regime when `phi is None`, which the caller (lines 69–73) converts to neutral 50/50 + a warning.

**Divergence:** All eight assets in the replay log emit `ON-B2: No pettersson_threshold for X — using neutral`. None of the bootstrap or seed scripts inspected (`bootstrap_production.py`, `seed_real_asset.py`, `seed_all_assets.py`, `load_p2_multi_asset.py`, `fix_locked_strategies.py`) write a `pettersson_threshold` field into the `locked_strategy` JSON. Three diagnostic possibilities, only one is correct:

1. **Data gap** — `pettersson_threshold` is supposed to live inside `locked_strategy` and the seed pipeline simply forgets to copy it from the upstream P2 source.
2. **Architectural gap** — `pettersson_threshold` should live in a separate `p2_d07` table (the regime classifier table) and `_load_regime_models` should query it independently rather than reading from `locked_strategy`.
3. **Code gap** — `_load_regime_models` is reading the right field but the file is named differently in P2 outputs (e.g. stored under a different JSON key like `phi` or `regime_threshold`).
  Confirming which one requires the actual P2-D06/P3-D00 schema doc, which is not in the upload (Q5).

**Downstream effect:** Production AND replay. With every asset stuck at neutral 50/50, Blended Kelly degenerates to the equal-weighted average of `LOW_VOL` and `HIGH_VOL` Kelly fractions per asset — not catastrophic, but materially weaker than spec intent (which segments edge by regime). Combined with the cold-start tiny Kelly fractions visible in the replay (e.g. ES `kelly_full = 0.0002`), this also pushes large assets to zero contracts after capital × Kelly / risk_per_contract floor.  

**Fan-out checked:** `_classifier_regime` at `b2_regime_probability.py:144-178` has its own fallback when `classifier_object` is missing — also degrades to neutral 50/50 if `regime_label == REGIME_NEUTRAL`. Both code paths share the underlying issue: P3-D00 is not being seeded with regime intelligence.  

**QuestDB impact:** Depends on (1) vs (2). If (1), the column is already a JSON STRING — no schema change, only a seed-script fix. If (2), a `p2_d07_regime_models` table needs to be wired to `B1` (the spec mentions P2-D07 already; see clarification Q5).  

**Proposed fix direction:** Diagnose first. Inspect a single asset's `data/p2_outputs/{ASSET}/p2_d06_locked_strategy.json` for a `pettersson_threshold` field. If present, fix `bootstrap_production.py:79-127` and `load_p2_multi_asset.py:251-293` to copy it. If absent, decide with Isaac whether P2-D07 should be a separate table; that affects the schema and `B1` loader.  
**Needs Isaac:** YES — Q2 in §6.

---

### F-06 — Replay harness omits `locked_strategies` and `assets_detail` kwargs to B5C

**Severity:** HIGH

**Spec reference:** Not a spec divergence per se — replay harness is auxiliary tooling. However, audit constraint "production is authoritative over replay" means this is a harness defect rather than a spec defect.

**Code reference:** `[scripts/replay_full_pipeline.py:272-281](scripts/replay_full_pipeline.py)` calls `run_circuit_breaker_screen(...)` without `locked_strategies` or `assets_detail` kwargs. Production orchestrator at `[captain-online/captain_online/blocks/orchestrator.py:615-626](captain-online/captain_online/blocks/orchestrator.py)` and the dry-run script at `[captain-online/dry_run_phase_a.py:322-334](captain-online/dry_run_phase_a.py)` both pass them.

**Divergence:** Without those kwargs B5C falls back at lines 99–104 to the scalar defaults `sl_distance=4.0, point_value=50.0` for every asset, regardless of instrument micro/full status. `rho_j = contracts × $200` for everything; on a $150k account at the cold-start `L_halt=$750`, even modest micro-asset positions trip the L1 preemptive halt.

**Downstream effect:** REPLAY ONLY. Production already passes the kwargs (verified). The replay's "all four micros blocked at L1" symptom is fully explained by this defect — but only after F-01/F-02/F-03/F-05 are fixed will production produce the correct data for the replay to consume meaningfully.

**Fan-out checked:** Repo-wide grep for `run_circuit_breaker_screen(` returned four call sites — production orchestrator (correct), `dry_run_phase_a.py` (correct), `replay_full_pipeline.py` (defective), and `tests/test_b5c_circuit.py` (passes scalars explicitly per-test, intentional). Only the replay script needs patching.

**QuestDB impact:** NONE.

**Proposed fix direction:** Add `locked_strategies=b1["locked_strategies"]` and `assets_detail=b1["assets_detail"]` to the kwargs at line 280–281. Also patch `model_m=` if Isaac wants per-model L3/L4 to fire in replay (currently `None`, so basket layers always pass — that may be acceptable for a harness).

**Needs Isaac:** NO (production is the authority; the fix is mechanical).

---

### F-07 — B5C recomputes `L_halt` from `c × e × A` instead of reading SOD-locked `L_halt` from `topstep_state`

**Severity:** HIGH

**Spec reference:** `Topstep Optimisation Functions.md` Part 6, "Online Block 7" pseudocode line 627: `INPUT: SOD-locked params from P3-D08[ac]: N, E, L_halt, f(A)`. The architectural intent is that L_halt is **frozen** at 19:00 ET and then read by B5C; mid-day balance changes do not move L_halt until next SOD.

**Code reference:** `[captain-online/captain_online/blocks/b5c_circuit_breaker.py:263-293](captain-online/captain_online/blocks/b5c_circuit_breaker.py)`: `_layer1_preemptive_halt` reads `c, e` from `topstep_params` and `A` from `tsm["current_balance"]`, then computes `l_halt = c * e * A`.

**Divergence:** Mathematically equivalent to the SOD value at 19:00 ET, but architecturally B5C should read `tsm["topstep_state"]["computed_sod"]["L_halt"]` (per Part 7 mapping, line 768). The B5C re-derivation means any mid-day adjustment to `topstep_params` or `current_balance` would silently shift L_halt during the trading day, violating the SOD-frozen contract.

**Downstream effect:** Production. Today the consequence is masked because (i) `topstep_state.computed_sod.L_halt` is never populated (F-01/F-03), and (ii) `current_balance` doesn't change intraday in the current code paths. Fixing F-01/F-03 without also fixing this would leave B5C using the live recomputation in preference to the now-available SOD value — defeating the purpose of fixing F-01/F-03 for L1 specifically.

**Fan-out checked:** `_layer2_budget` lines 296–321 has the **identical issue** with `E = e × A` (re-derived rather than reading `computed_sod.E_daily_exposure`). Treat as part of the same fix.

**QuestDB impact:** NONE (read pattern only).

**Proposed fix direction:** When F-01 lands, switch L1 to `topstep_state.get("computed_sod", {}).get("L_halt")` with a fallback to the current `c × e × A` recomputation if `computed_sod` is missing (cold start before first SOD has run). Same for L2 reading `computed_sod.E_daily_exposure`. Log a `WARN` when the fallback path is taken so we notice if SOD stops firing.

**Needs Isaac:** NO.

---

### F-08 — B4 `_compute_topstep_daily_cap` reads `topstep_state` that B1 never loaded

**Severity:** HIGH

**Spec reference:** `Topstep Optimisation Functions.md` Part 6, "Online Block 4 — Kelly Sizing (Extended)" lines 605–610: `topstep_daily_cap = floor(E / (strategy_sl × point_value))` where E is the SOD-locked daily exposure. Cross_Reference Change O1 specifies the same formula for the V3 amendment.

**Code reference:** `[captain-online/captain_online/blocks/b4_kelly_sizing.py:372-390](captain-online/captain_online/blocks/b4_kelly_sizing.py)`: `_compute_topstep_daily_cap` reads `tsm["topstep_state"]` and `topstep_state["computed_sod"]["E_daily_exposure"]` — neither of which is in the dict produced by `B1` (per F-01). Falls back to `topstep_params.daily_contract_cap` (also unloaded), then to the function default `999`.

**Divergence:** `topstep_daily_cap` is always `999` in the user's logs (`topstep=999` consistently in the replay output). The 4-way `min(raw, tsm_cap, topstep_daily_cap, scaling_cap)` therefore reduces to `min(raw, tsm_cap, scaling_cap)`. The Topstep daily exposure cap is mathematically inactive.

**Downstream effect:** Production AND replay. A V3 hard constraint specified in `Cross_Reference O1` is a no-op. On compounding accounts the tsm_cap (from MDD budget divisor) tracks balance loosely, but the Topstep daily exposure budget is never enforced.

**Fan-out checked:** Same root cause as F-01 (B1 doesn't load `topstep_state`). Fixing F-01 fixes this transitively for the input side; the function logic is correct.

**QuestDB impact:** NONE (covered by F-01 fix).

**Proposed fix direction:** Covered by F-01.

**Needs Isaac:** NO.

---

### F-09 — B5C Layer 0 reads `current_open_micros` from `tsm` but B1 never loads it

**Severity:** HIGH
**Spec reference:** `Topstep Optimisation Functions.md` Part 6 lines 638–645: Layer 0 uses `current_open_micros` from B7's position tracker (not from D08), and is XFA-only.

**Code reference:** `[captain-online/captain_online/blocks/b5c_circuit_breaker.py:236-260](captain-online/captain_online/blocks/b5c_circuit_breaker.py)`: `_layer0_scaling_cap` reads `tsm.get("current_open_micros", 0)`. `[captain-online/captain_online/blocks/b4_kelly_sizing.py:195](captain-online/captain_online/blocks/b4_kelly_sizing.py)`: same field.

**Divergence:** The spec sources this value from B7's position tracker (live state), not from a TSM column. The implementation reads it from the TSM dict, which never has it (B1 doesn't load it; no TSM JSON file declares it; b4_tsm_manager doesn't write it). Returns 0 always. Layer 0 therefore can never block on scaling cap saturation; only the static `scaling_tier_micros` floor (loaded correctly by B1 line 239) caps it.

**Downstream effect:** Production. XFA accounts can over-fill their scaling tier intraday because the cap is checked against `0 + proposed`, not `current_open + proposed`. Only relevant once a user runs an XFA account with topstep_optimisation; user 20319784 is presumed Live, so impact is latent.

**Fan-out checked:** `B7` position tracker is in `b7_position_monitor.py` (not read in this audit; flagged for Isaac if implementation is required). The `current_open_micros` field needs to come from there or via a Redis hash.

**QuestDB impact:** NONE (live state, Redis-cached per spec).

**Proposed fix direction:** B5C needs a Redis read or a position-tracker import. Either compute the live open micros once at B5C entry (sum micro-equivalents across `open_positions`) or have the orchestrator inject the value into B5C as a kwarg. The latter is cheaper to test.

**Needs Isaac:** NO (implementation choice has two reasonable shapes; pick one).

---

### F-10 — Cold-start L_halt of $750 may be substantively too tight even when all upstream defects are fixed

**Severity:** MEDIUM


**Spec reference:** `Topstep Optimisation Functions.md` Part 4.2 line 288: "Dollar threshold at defaults: c × e × A = 0.5 × 0.01 × 150,000 = $750." Spec accepts this as the design value.


**Code reference:** `[captain-online/captain_online/blocks/b5c_circuit_breaker.py:263-291](captain-online/captain_online/blocks/b5c_circuit_breaker.py)` and `[config/tsm/providers/topstep_150k_live.json:49-53](config/tsm/providers/topstep_150k_live.json)` (`p=0.005, e=0.01, c=0.5`).


**Divergence:** Not a code/spec divergence. A flag for Isaac: with `c=0.5, e=0.01` on $150k, **one full ES contract at a 4-point SL = $200 risk = 27% of L_halt**. Four contracts ($800) trips L1. The user's earlier message implied this felt unworkably tight. The Topstep_Optimisation spec deliberately picks these defaults; the math is internally consistent. But after F-04 is resolved (assume B4/B5C agree on `sl_multiple × or_range`), realised per-contract risk on full-size assets will frequently exceed 5–10% of L_halt and the L1 preemptive check will routinely trigger on multi-contract entries even when SOD is correctly running.


**Downstream effect:** Operational. May warrant tuning `c` upward (relaxing L1) once Pseudotrader (`P3-PG-09C`) has produced grid-search recommendations. Not an audit finding to "fix" — flagged so it doesn't get re-discovered after the BLOCKING fixes ship.


**QuestDB impact:** NONE.


**Proposed fix direction:** Run `P3-PG-09C` (`captain-offline/captain_offline/blocks/b3_pseudotrader.py` extension) once enough live-trade data exists; until then, leave defaults at spec values.


**Needs Isaac:** NO (no immediate action; flag only).

---

### F-11 — `replay_full_pipeline.py` independently re-implements L1 inside `compute_contracts` in `replay_session.py`

**Severity:** MEDIUM


**Spec reference:** `Topstep Optimisation Functions.md` Part 6 — B5C is the single canonical location for the L1 check.


**Code reference:** `[scripts/replay_session.py:408-421](scripts/replay_session.py)` reimplements L1 (`l_halt = c * e * user_capital; rho_j = final * fallback_risk; while final > 0 and (final * fallback_risk) >= l_halt: final -= 1`).


**Divergence:** Uses a different formula (drops `|L_t|` term, no `+ fee`, decrements contracts in a loop instead of binary block). Two separate L1 implementations means a future spec change would have to be applied in two places, with no cross-validation that they agree.


**Downstream effect:** Replay only. The user's reported audit was run via `replay_full_pipeline.py`, not `replay_session.py`, so this defect is dormant in their current workflow but a tripping hazard.


**Fan-out checked:** `shared/replay_engine.py:1048-1120` also has its own CB layer math (`c_param`, `e_param`, `lambda_threshold`) — three implementations exist. None call into `b5c_circuit_breaker.run_circuit_breaker_screen` directly.


**QuestDB impact:** NONE.


**Proposed fix direction:** Have replay scripts import and call `run_circuit_breaker_screen` from `b5c_circuit_breaker` rather than reimplementing. If structured as a real "replay through production code" harness, this would have caught F-04, F-06, and F-09 in CI.


**Needs Isaac:** NO.

---

### F-12 — Test fixtures in `test_b5c_circuit.py` set `sl_distance=4.0, point_value=50.0` directly

**Severity:** LOW


**Spec reference:** N/A (test design).


**Code reference:** `[tests/test_b5c_circuit.py:121-122](tests/test_b5c_circuit.py)` and similar throughout.


**Divergence:** Tests pass scalar SL/point_value rather than per-asset dicts. This is appropriate for unit testing each layer in isolation, but means the kwarg-omission defect (F-06) and the `locked_strategies` fallback path in B5C (lines 99–104) are not exercised by the CI suite. A regression that breaks per-asset resolution wouldn't be caught.


**Downstream effect:** None at runtime. Test coverage gap.


**QuestDB impact:** NONE.


**Proposed fix direction:** Add at least one test that exercises B5C with `locked_strategies={"MNQ": {"threshold": 4.0}}` and `assets_detail={"MNQ": {"point_value": 2.0}}`, asserting `rho_j = contracts × 8` (not × 200).


**Needs Isaac:** NO.

---

### F-13 — `b1_data_ingestion._load_locked_strategies` and `_load_regime_models` collapse P2-D06 and P2-D07 into a single P3-D00 column

**Severity:** LOW (architectural, may be intentional)


**Spec reference:** `P2-D06 + P3-D00.md` (mislabeled file, contains HMM spec) Part 2 register: P2-D06 is the locked strategy, P2-D07 is the regime classifier — listed as separate datasets. The actual P2-D06/P3-D00 schema document is not in the upload.


**Code reference:** `[captain-online/captain_online/blocks/b1_data_ingestion.py:284-329](captain-online/captain_online/blocks/b1_data_ingestion.py)`: both `_load_locked_strategies` and `_load_regime_models` query `p3_d00_asset_universe.locked_strategy` JSON. The comment at line 287 says "P2-D06 data is pre-loaded into P3-D00 during asset onboarding"; comment at line 313 says "P2-D07 data is stored as part of asset config" implying P2-D07 was also collapsed into the same JSON.


**Divergence:** May be a deliberate simplification for V1, or may be a divergence from the unloaded schema spec. Without that spec doc, cannot confirm. Connected to F-05.


**Downstream effect:** Production. If the spec keeps P2-D06/D07 as separate datasets, then a `p2_d07_regime_models` table is missing from QuestDB and `_load_regime_models` is reading from the wrong place.


**QuestDB impact:** SCHEMA CHANGE REQUIRED only if Isaac confirms P2-D07 should be its own table. Otherwise NONE.


**Proposed fix direction:** Wait on Q5 (spec doc retrieval). If spec confirms separate datasets, define `p2_d07_regime_models` table (asset_id, model_type, model_blob, pettersson_threshold, regime_label, last_trained), seed from `data/p2_outputs/`, repoint `_load_regime_models`. If spec confirms collapsed-into-D00 is intentional for V1, document it explicitly and fix the F-05 seed gap only.


**Needs Isaac:** YES — Q5 in §6.

---

## 4. QuestDB Change Register

Only one finding requires schema work today; everything else is logic-only or seed-data only.


| #    | Table                        | Change                                                                                                                                                                                                                                                                   | Migration sketch                                                                          | Backfill                                                                                        | Affected writers                                                    | Affected readers                                                                                    | Triggered by |
| ---- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------ |
| Q-01 | `p2_d07_regime_models` (NEW) | New table only **if Isaac confirms separate-dataset architecture per Q5**. Schema: `asset_id SYMBOL, model_type SYMBOL, model_blob STRING, pettersson_threshold DOUBLE, regime_label SYMBOL, regime_feature_list STRING, last_trained TIMESTAMP, last_updated TIMESTAMP` | `CREATE TABLE p2_d07_regime_models (...) timestamp(last_updated) PARTITION BY MONTH WAL;` | Backfill from `data/p2_outputs/{ASSET}/p2_d07_*.json` if such files exist; otherwise from refit | New offline writer (P2 build pipeline; out of scope for this audit) | `b1_data_ingestion._load_regime_models` (rewrite to query p2_d07 instead of p3_d00.locked_strategy) | F-05, F-13   |


**No other schema work** is needed for the BLOCKING fixes:

- F-01 reuses existing `topstep_params` and `topstep_state` columns (already present in `p3_d08_tsm_state` per `shared/canonical_schemas.py:215-216`).
- F-02 is logic-only.
- F-03 reuses existing `topstep_state` STRING column — write pattern needs to follow the row-rewrite used by `_update_account_balance`.
- F-04 (if resolved as "store separate `sizing_sl_distance` field") could optionally introduce a new column on `p3_d00_asset_universe`, but reusing the existing JSON `locked_strategy.threshold` field is also valid. Decision is in Q1.
- F-05 is seed-script only IF the locked_strategy-collapsed model is correct (Q5).
- F-06 / F-09 / F-11 / F-12 are code-only.

## 5. Suggested Amendment Sequence

Dependency-ordered. **Each step's prerequisites must complete first.**

1. **Resolve clarifications** (Isaac, §6). Without Q1 and Q5 the F-04 and F-13 fixes cannot be patched correctly. Q3 confirms the test fixture for F-02 verification.
2. **Schema work, if Q5 → "separate dataset"**: create `p2_d07_regime_models` (Q-01). Deploy and backfill before any reader migration.
3. **F-02 fix** (`b8_reconciliation.py:73` gate). Smallest BLOCKING change; unblocks Live SOD computation. Must land before F-03 because F-03's persistence path is only useful if F-02 is letting the function run for the right accounts.
4. **F-03 fix** (`_update_topstep_state` writes to `p3_d08_tsm_state`). Required before F-01's read path can deliver SOD-locked values; otherwise F-01 will load stale config-only `topstep_state`.
5. **F-01 fix** (extend `_load_tsm_configs` SELECT to include `topstep_params` and `topstep_state`, parse and attach). Production B5C and B4 immediately consume the SOD output landed by F-02 + F-03.
6. **F-07 + F-08 fix** (B5C reads SOD-locked `L_halt`/`E` from `computed_sod` with fallback). Bundle with F-01 verification.
7. **F-04 fix** (per Q1's resolution direction). Touches B4 risk-per-contract formula, possibly seed scripts, possibly `b5c_circuit_breaker`. Must land before F-06 because validating the replay output requires production sizing to be correct.
8. **F-05 fix** (per Q5's resolution: seed-script patch or new offline writer). Independent of the F-01..F-04 chain; can run in parallel after Q5 is answered.
9. **F-09 fix** (B5C Layer 0 reads `current_open_micros` from B7 / Redis). Independent; XFA-only impact.
10. **F-12 fix** (test coverage for per-asset CB resolution). Add tests before F-06 patch.
11. **F-06 fix** (replay harness adds two CB kwargs). Last in the chain because the replay output only becomes meaningful once F-01..F-08 are in.
12. **F-11 fix** (consolidate replay's reimplemented L1 to call `run_circuit_breaker_screen`). Cleanup; deprioritise behind shipping the BLOCKING fixes.
13. **F-10 review** (post-deployment): once SOD math runs end-to-end and Pseudotrader has accumulated data, run `P3-PG-09C` grid search to validate or retune `c, e, lambda`.

## 6. Clarifications for Isaac

Grouped by topic, smallest possible context, ordered by criticality.

### Kelly semantics

**Q1.** `08_Kelly_Sizing_Pipeline.md` line 260 and `Topstep Optimisation Functions.md` Part 6 line 580 both use `strategy_sl × point_value` to define risk per contract but neither doc defines the source of `strategy_sl`. `bootstrap_production.py:108` seeds a static `threshold` field per asset (e.g. ES = 4 points) into `locked_strategy`, and B4 reads exactly that field. B6, however, computes the live SL distance as `sl_multiple × or_range`. For ORB strategies these can disagree by 3×–10× per asset. Which is canonical for sizing — the static `threshold`, or `sl_multiple × historical_avg_or_range`, or live `sl_multiple × or_range` (which would require B4 to run in Phase B after OR forms)? (Affects F-04.)

### Circuit breaker / Topstep parameters

**Q2.** In `b8_reconciliation.py:73` the SOD computation is gated on `scaling_plan_active`. Per the spec, the gate should be `topstep_optimisation`. Account 20319784 — is it the Live TSM (`config/tsm/providers/topstep_150k_live.json`) or the XFA TSM (`topstep_150k_xfa.json`)? Either way the fix is the same; we need this to write the correct test assertion. (Affects F-02 verification.)

### Regime model

**Q3.** Open one of `data/p2_outputs/ES/p2_d06_locked_strategy.json` or the equivalent file for any asset that survived through to P3-D00. Does the JSON contain a `pettersson_threshold` field at the top level? If yes, the seed pipeline (`bootstrap_production.py` and `load_p2_multi_asset.py`) is dropping it on the way into `p3_d00_asset_universe.locked_strategy` — fix is seed-script-only. If no, where is `pettersson_threshold` actually stored in the P2 outputs? (Affects F-05.)

### Locked strategy / regime model schema

**Q4.** The file in `docs2/spec-docs-01/Nomaan_Edits_Fees.md` actually contains the Topstep CB Integration spec (5 changes), and `docs2/spec-docs-01/Topstep Optimisation & Circuit Breaker Integration.md` is a verbatim duplicate. Is the original Nomaan_Edits_Fees doc (the one referenced by `Cross_Reference O4/O5` describing `resolve_commission` and `get_expected_fee`) supposed to be in the upload? Surrogate coverage exists via the Cross_Reference verbatim cites and `Topstep Optimisation Functions.md` Part 3.4, but if a more authoritative or updated version exists I'd like to read it before finalising any fee-resolution code review. (Spec coverage gap.)

**Q5.** The file `docs2/spec-docs-01/P2-D06 + P3-D00.md` contains the HMM Opportunity Regime spec, not the P2-D06 / P3-D00 schema document its filename suggests. The actual P2-D06/D07 schema doc is not in the upload. Specifically: (a) is `pettersson_threshold` a field of P2-D06.locked_strategy or a field of a separate P2-D07 regime-model record? (b) Is collapsing P2-D06 + P2-D07 into a single `p3_d00_asset_universe.locked_strategy` JSON column (as the current code does) intentional for V1, or a divergence from the original schema design? (Affects F-05, F-13, and Q-01 schema decision.)

---

*Audit complete. No code, config, or QuestDB modifications were made during this session. The findings above are written to be patched in dependency order per §5; the read-only constraints in the original mandate were respected throughout.*