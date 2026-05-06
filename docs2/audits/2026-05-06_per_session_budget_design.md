---
title: Per-Session Budget Allocation — Design Record
date: 2026-05-06
companion_commits: 4dac522..2a184df (8 commits, Phases 2–8)
status: LANDED — Phases 2–8 merged on `main`. GUI frontend rendering pending in `captain-gui`.
spec_sources:
  - docs2/quick-fixes/circuit-breaker-nkd-issue/15_Topstep_Optimisation_Functions (1).md §4.4.4
  - docs2/quick-fixes/circuit-breaker-nkd-issue/16_HMM_Opportunity_Regime_Spec.md §3.6
---

# Per-Session Budget Allocation — Design Record

## 1. Problem Statement

Nomaan's empirical finding from the rolling 10-day live evaluation: **NKD APAC is consistently profitable when traded alone (+~$7K cumulative over 10 sessions), but is starved of risk capacity when NY and LON consume the global `L_halt` budget earlier in the same trading day.** By the time NKD's APAC session evaluates at 18:00 ET, B5C's preemptive halt formula reports `abs(L_t) + rho_j >= L_halt` and blocks the trade — even on days where NKD's own session has consumed nothing.

### 1.1 The cascade in the pre-2026-05-06 code

B5C's Layer 1 (preemptive hard halt) used a single, globally accumulated intraday ledger:

```
L_t       := Σ r_j   for j ∈ all trades today, all sessions, all assets
L_halt    := computed_sod.L_halt   (a single scalar — c · e · A)
H = 1 iff abs(L_t) + rho_j < L_halt
```

The `abs(L_t)` term is the killer. NY and LON populate `L_t` first (they open at 09:30 and 03:00 ET respectively); whether those sessions **win** or **lose** is irrelevant — both shrink the available headroom for APAC at 18:00 ET, because absolute value treats NY's +$300 win the same as a -$300 loss with respect to APAC's gate.

Concretely, against the eval account's $150K capital with `c=0.5, e=0.01` (pre-2026-05-06):
- `L_halt = 0.5 × 0.01 × 150000 = $750` for the entire trading day.
- A normal NY session producing `L_t = -$400` leaves only `$350` of headroom for APAC.
- NKD APAC's typical `rho_j ≈ $200–$400` fails the preemptive check almost every day where NY did anything at all.

### 1.2 What "per-session budget" fixes

Each session gets its own SOD-allocated `L_halt_w` and `E_w`, indexed by `session_id` (1=NY, 2=LON, 3=APAC). NY's intraday `L_t_NY` no longer pollutes APAC's gate. The carryover formula (§4) ensures the **day-total** budget is conserved — if LON closes flat or is parity-skipped, its unused share rolls forward weighted by remaining-session HMM shares, so NKD APAC actually has more budget than its cold-start 1/3 share alone would give.

---

## 2. Spec Alignment

This work implements two existing Isaac specs verbatim, with one explicit Nomaan extension. No new architecture is being invented.

### 2.1 Isaac — `15_Topstep_Optimisation_Functions (1).md` §4.4.4 "Time-Partitioned Budget"

> Split the day into windows indexed by w. Let α_w = fraction of daily exposure allocated to window w, where Σ α_w = 1:
>
> $$E_w = \alpha_w \cdot e \cdot A$$
>
> $$N_w = \left\lfloor \frac{\alpha_w \cdot e}{p \cdot f(A)} \right\rfloor$$
>
> Each window tracks its own P&L independently:
>
> $$L_w = \sum_{j \in w} r_j$$
>
> Each window has its own halt:
>
> $$H_w(L_w) = \begin{cases} 1 & \text{if } |L_w| < c \cdot E_w \\ 0 & \text{otherwise} \end{cases}$$
>
> **Losses in window 1 do not consume window 2's budget.**

This is exactly what we shipped. `α_w` becomes the HMM-derived `share` (per session 2.2 below), `E_w` is `effective_e_exposure`, the per-window `L_w` is the per-session `l_t` ledger in `p3_d23_circuit_breaker_intraday`, and the per-window halt threshold is `effective_l_halt = c · α_w · e · A` (multiplied by `c` per Isaac's §4.2 definition of `L_halt`).

### 2.2 Isaac — `16_HMM_Opportunity_Regime_Spec.md` §3.6 "Online Inference"

> ```
> # Budget allocation for next session window
> remaining_budget = E - budget_consumed_today
> budget_for_next_session = remaining_budget × opportunity_weight[next_session]
> ```

`opportunity_weight[w]` is computed by `shared.sod_session_budget.session_budget_shares` from the AIM-16 HMM state in `p3_d26_hmm_opportunity_state`. Cold-start (`n_obs<20`) returns equal `1/3` per session. Blended (`20≤n<60`) is 50% equal + 50% HMM, then floored at `0.05` and renormalised. Full HMM (`n≥60`) is the floored/renormalised raw weights.

### 2.3 Nomaan extension — Parity-skip carryover

The two-instance deployment splits signals deterministically (Tower A takes odd, Tower B takes even). When a session emits exactly **one** signal and that signal goes to the other tower, the local tower's `l_t_w_final` for that session is `0` and no budget was consumed. Rather than letting that share evaporate, Nomaan's instruction is to roll the unused share forward weighted by remaining-session shares. Concretely (formula in §4):

```
remaining_budget at session_target = (sod_total − Σ |l_t_w_final|) × shares[target] / Σ shares[remaining]
```

This is a strict superset of Isaac's §3.6 formulation: when no sessions are skipped and no carryover is needed, the formula collapses back to `share × sod_total`. The behaviour is observable via `effective_l_halt` and `effective_e_exposure` columns on each D23 session-open row, which B5C reads directly without re-deriving.

---

## 3. Locked Design Decisions

Five decisions were locked before Phase 2 implementation began. Each is captured here so that future audits know which of these are amendable and which are load-bearing.

### D-1 — D23 schema with composite key `(account_id, session_id)`

Four new columns added via M043–M046, plus M047 to extend the DEDUP UPSERT key set. Per `shared/canonical_schemas.py:1027-1054`:

```1027:1054:shared/canonical_schemas.py
    # --- Per-Session Budget Allocation (2026-05-06) ---
    # D23 partitions intraday CB state per (account_id, session_id) so each session
    # has its own L_t / n_t / l_b / n_b ledger and SOD-locked effective L_halt / E.
    # See docs2/audits/2026-05-06_per_session_budget_design.md for the full design.
    (
        "M043_d23_add_session_id",
        "ALTER TABLE p3_d23_circuit_breaker_intraday ADD COLUMN session_id INT",
    ),
    (
        "M044_d23_add_effective_l_halt",
        "ALTER TABLE p3_d23_circuit_breaker_intraday ADD COLUMN effective_l_halt DECIMAL(18, 2)",
    ),
    (
        "M045_d23_add_effective_e_exposure",
        "ALTER TABLE p3_d23_circuit_breaker_intraday ADD COLUMN effective_e_exposure DECIMAL(18, 2)",
    ),
    (
        "M046_d23_add_session_opened_at",
        "ALTER TABLE p3_d23_circuit_breaker_intraday ADD COLUMN session_opened_at TIMESTAMP",
    ),
    # M047: extend DEDUP UPSERT KEYS to include session_id so per-(account, session)
    # rows on the same last_updated nanosecond are not collapsed.
    (
        "M047_d23_dedup_include_session_id",
        "ALTER TABLE p3_d23_circuit_breaker_intraday DEDUP ENABLE UPSERT KEYS(last_updated, account_id, session_id)",
    ),
```

DEDUP keys must include `session_id`; without M047, two rows for the same `(account, last_updated)` from different sessions would collapse into one. QuestDB allows `DEDUP ENABLE` to override a previously set key list on a WAL table (per the QuestDB `alter-table-enable-deduplication.md` reference), so M047 is a re-enable, not a fresh create. Existing rows pre-migration get `session_id = NULL`; B5C/B7 readers filter `WHERE session_id = %s`, so legacy rows are silently ignored after Phase 4 lands.

### D-2 — D08 nested `computed_sod.session.{NY,LON,APAC}` map

The new SOD output shape, written by `b8_reconciliation._compute_sod_topstep_params` (Phase 2 commit `d158cc9`):

```json
{
  "computed_sod": {
    "L_halt": 1500.00,
    "E_daily_exposure": 1500.00,
    "session": {
      "NY":   {"L_halt": 500.00, "E_daily_exposure": 500.00, "N_max_trades": 33, "share": 0.3333},
      "LON":  {"L_halt": 500.00, "E_daily_exposure": 500.00, "N_max_trades": 33, "share": 0.3333},
      "APAC": {"L_halt": 500.00, "E_daily_exposure": 500.00, "N_max_trades": 33, "share": 0.3333}
    },
    "session_shares_source": "EQUAL_COLD_START"
  }
}
```

Legacy flat scalars `L_halt` and `E_daily_exposure` are kept for **one release** as fallback. After the Phase 2 → Phase 4–8 chain has been live for ≥7 days and we confirm no readers fall back, the legacy keys can be removed in a follow-up.

### D-3 — HMM-weighted shares from `shared.sod_session_budget.session_budget_shares`

Single source of truth for share computation. Both Command B8 (writer) and Online B5C / B4 (readers) call this exact function so they cannot drift. Cold-start / blended / full-HMM regimes are documented in the function docstring (`shared/sod_session_budget.py:84-128`). Floor at `0.05`, renormalised. The `session_shares_source` attribution string (`HMM_FULL` / `HMM_BLENDED` / `EQUAL_COLD_START`) is persisted alongside the shares for observability — it tells us at a glance which regime the SOD computation was in when it ran.

### D-4 — Layer 0 (XFA scaling cap) stays account-scoped

L0 caps the **simultaneous open positions in mini-equivalents** per `15_Topstep_Optimisation_Functions (1).md` Part 6 lines 580–605. This is a Topstep platform constraint on instantaneous open exposure, not on day-total risk taken. Splitting it per-session would let APAC re-use the same micros that NY currently has open, which violates Topstep's actual rule. **L0 deliberately remains account-scoped; per-session is L1/L2/L3 only.**

### D-5 — Keep `abs(L_t)` in L1 for v1

Isaac's §4.2 formula uses `abs(L_t) + rho_j >= L_halt`. The `abs()` means any P&L excursion (win or loss) consumes headroom at the same rate — a debated design choice ("losses-only" vs "magnitude-on-both-sides" is a separate amendment Nomaan flagged). For v1 of per-session, **the cascade is fixed by the per-session split alone**, regardless of the `abs()` debate. NY's `+$300` win still consumes NY's L_halt, but it does NOT consume APAC's. The wins-vs-losses semantics are unchanged from pre-2026-05-06; we revisit only if production traces show per-session L1 trips on winning sessions.

---

## 4. Carryover Formula

Implemented in `shared.sod_session_budget.compute_session_carryover` (lines 214–296). Isaac's "available × share / remaining" formula is:

```
consumed_so_far  = Σ |L_t_w_final|        for w in completed earlier sessions today
available        = max(0, sod_total − consumed_so_far)
remaining_sum    = Σ shares[r]            for r in remaining_session_ids (incl. target)
effective[target] = available × shares[target] / remaining_sum
```

Two design notes carried in the docstring:
1. Tracks **realised** consumption `|L_t_w_final|`, not the effective allocations of completed sessions. This avoids double-counting the carryover that an earlier session may itself have already absorbed.
2. Uses `abs()` for consistency with B5C L1's preemptive formula (D-5).

### 4.1 Worked example A — equal cold-start, no skips, no losses

`sod_total = $1500`, shares = `{NY: 1/3, LON: 1/3, APAC: 1/3}`, no completed sessions yet.

| Session | available | remaining_sum | share | effective |
|---------|-----------|---------------|-------|-----------|
| LON (opens first, at 03:00) | $1500 | 1.0 | 1/3 | $500 |
| NY (after LON closes l_t=0)  | $1500 | 2/3 | 1/3 | $750 ← but only if LON skipped |
| APAC (after NY closes l_t=0) | $1500 | 1/3 | 1/3 | $1500 ← only if both prior skipped |

The formula gives **exactly** the SOD share (`$500`) when `consumed_so_far == 0 AND remaining_sum == 1.0` — i.e., at the very start of the day before any earlier session has CLOSED. Walk-through: at LON's 03:00 open, `available=1500`, `remaining_sum = shares[LON]+shares[NY]+shares[APAC] = 1`, `effective = 1500 × (1/3) / 1 = $500`. ✓

### 4.2 Worked example B — parity-skip case

LON opens, but the only signal that fires goes to the other tower (parity skip). LON closes with `l_t_final = 0`. NY then opens at 09:30:

| Quantity | Value |
|----------|-------|
| `consumed_so_far` | `|0| = 0` |
| `available` | `max(0, 1500 − 0) = 1500` |
| `remaining_session_ids` | `(NY=1, APAC=3)` (LON now removed) |
| `remaining_sum` | `shares[NY] + shares[APAC] = 2/3` |
| `shares[NY]` | `1/3` |
| `effective[NY]` | `1500 × (1/3) / (2/3) = 750` |

So NY at open gets **$750** of effective L_halt, vs the **$500** bare share. The parity-skipped LON budget rolls forward into the remaining-session pool. ✓

### 4.3 Worked example C — APAC after LON skipped + NY lost $300

LON: `l_t_final = 0` (skipped). NY: `l_t_final = -300` (one loss). APAC opens at 18:00:

| Quantity | Value |
|----------|-------|
| `consumed_so_far` | `|0| + |-300| = 300` |
| `available` | `max(0, 1500 − 300) = 1200` |
| `remaining_session_ids` | `(APAC=3,)` |
| `remaining_sum` | `shares[APAC] = 1/3` |
| `shares[APAC]` | `1/3` |
| `effective[APAC]` | `1200 × (1/3) / (1/3) = 1200` |

APAC gets the entire remaining $1200 because it's the last session of the day. This is the worked-out form of the limitation noted in §9 — strict day-total conservation is not enforced at the per-session step; the last session always absorbs the residue. Acceptable per design.

---

## 5. Reader / Writer Matrix

Field-level audit of which block writes / reads each piece of state, and how the touch points changed.

| Field | Writer | Reader(s) | Write frequency | Before 2026-05-06 | After |
|-------|--------|-----------|-----------------|-------------------|-------|
| `D08.computed_sod.L_halt` (legacy flat) | B8 reconciliation | B5C L1 (legacy fallback), B4 cap (legacy fallback) | 19:00 ET daily | Sole source of L_halt | Kept as fallback for one release |
| `D08.computed_sod.E_daily_exposure` (legacy flat) | B8 reconciliation | B4 cap (legacy fallback) | 19:00 ET daily | Sole source of E | Kept as fallback for one release |
| `D08.computed_sod.session.{NY,LON,APAC}.L_halt` | B8 reconciliation (Phase 2, `d158cc9`) | Online orchestrator session-open hook (Phase 3a) → effective_l_halt | 19:00 ET daily | did not exist | New primary L_halt source |
| `D08.computed_sod.session.{NY,LON,APAC}.E_daily_exposure` | B8 reconciliation (Phase 2) | B4 cap (Phase 5, `5891534`) | 19:00 ET daily | did not exist | Per-session E for B4 daily-cap |
| `D08.computed_sod.session.{NY,LON,APAC}.N_max_trades` | B8 reconciliation (Phase 2) | B5C L2 (Phase 4) | 19:00 ET daily | did not exist | Per-session trade-count cap |
| `D08.computed_sod.session_shares_source` | B8 reconciliation (Phase 2) | (observability only — logs / GUI) | 19:00 ET daily | did not exist | `HMM_FULL` / `HMM_BLENDED` / `EQUAL_COLD_START` |
| `D08.daily_loss_used` | B8 reconciliation `_reset_daily_counters` | (TSM cap path) | 19:00 ET reset + per-trade | Bug: NEVER actually reset to 0 (audit-log only) | **Fixed in Phase 2** — now SELECT-latest + INSERT new row |
| `D23.session_id` (NEW) | Orchestrator session-open hook (Phase 3a, `4e3c30b`); B7 trade close (Phase 3, `d69554d`) | B5C `_load_intraday_state` (Phase 4, `8ec6aa0`) | Per session-open + per trade close | did not exist | Required field on every D23 row |
| `D23.l_t` | B7 trade close (Phase 3) | B5C L1 | Per trade close | Single global ledger | Per-(account, session) ledger |
| `D23.n_t` | B7 trade close (Phase 3) | B5C L2 | Per trade close | Single global counter | Per-(account, session) counter |
| `D23.l_b` (basket P&L map) | B7 trade close (Phase 3) | B5C L3 | Per trade close | Keys: `<model_m>` | Keys: `<session_id>:<model_m>` (Phase 3 namespacing) |
| `D23.n_b` (basket count map) | B7 trade close (Phase 3) | B5C L3 | Per trade close | Keys: `<model_m>` | Keys: `<session_id>:<model_m>` |
| `D23.effective_l_halt` (NEW) | Orchestrator session-open hook (Phase 3a) | B5C L1 | Once per session open | did not exist | SOD-locked, carryover-adjusted |
| `D23.effective_e_exposure` (NEW) | Orchestrator session-open hook (Phase 3a) | (currently observability — B5C L2 still uses computed_sod path) | Once per session open | did not exist | SOD-locked, carryover-adjusted |
| `D23.session_opened_at` (NEW) | Orchestrator session-open hook (Phase 3a) | Idempotency guard in same hook | Once per session open | did not exist | Used to detect "already initialised today" |
| `D26.opportunity_weights` | Offline B1 AIM-16 trainer | `session_budget_shares()` (Phase 2 read site, Phase 3a fallback) | Per AIM-16 train (after each trade batch) | Existed but unused by SOD | Now consumed by both SOD writer and orchestrator session-open hook |
| Replay engine `_intraday_cumulative_pnl_per_session` | `compute_contracts` per-trade update (Phase 7, `2264871`) | `compute_contracts` L1 in same fn | Per simulated trade | did not exist | Mirrors prod B5C per-session ledger |
| Replay engine `_intraday_basket_pnl_per_session` | `compute_contracts` per-trade update (Phase 7) | `compute_contracts` L3 in same fn | Per simulated trade | Single basket dict | Per-session basket dict + legacy fallback |
| GUI `_get_tsm_status[i].per_session.{NY,LON,APAC}` | B2 GUI data server (Phase 8, `2a184df`) | captain-gui frontend (pending) | Per polling cycle | did not exist | Per-session L_t / N_t / used_pct breakdown |

---

## 6. Phase Manifest

All 8 commits between `4dac522` (excl.) and `2a184df` (HEAD) on `main`. Listed earliest-first to match deployment order.

| # | SHA | Phase | Title | Surface area touched |
|---|-----|-------|-------|----------------------|
| 1 | `d158cc9` | 2 | B8 SOD per-session writes + reset bug fix + c=1.0 | `captain-command/.../b8_reconciliation.py` (+213/-23), `config/tsm/providers/topstep_150k_eval.json` (c bumped), `tests/test_b8_reconciliation_sod_signature.py` (+126) |
| 2 | `249ffa9` | (rules) | docs(rules): smarter cmd-run + record `/app` vs `/captain/scripts` path mismatch | `.cursor/rules/captain-deploy-and-tower-discipline.mdc` (+84/-33) — out-of-scope for this design but lands in the same window |
| 3 | `4e3c30b` | 3a | Orchestrator session-open budget hook | `captain-online/.../orchestrator.py` (+223), `tests/test_orchestrator_session_budget_init.py` (+309) |
| 4 | `d69554d` | 3 | B7 writes per-session D23 + per-(session,m) basket | `captain-online/.../b7_position_monitor.py` (+81/-14), `tests/test_b7_per_session_d23_writes.py` (+203) |
| 5 | `8ec6aa0` | 4 | B5C circuit breaker per-session reads | `captain-online/.../b5c_circuit_breaker.py` (+202/-47), `tests/test_b5c_per_session_layers.py` (+153) |
| 6 | `5891534` | 5 | B4 `_compute_topstep_daily_cap` per-session | `captain-online/.../b4_kelly_sizing.py` (+43/-9), `tests/test_b4_per_session_cap.py` (+86) |
| 7 | `3d561b3` | 6 | B5 `apply_hmm_session_allocation` observability-only | `captain-online/.../b5_trade_selection.py` (+67/-27), `tests/test_b5_session_allocation_observability.py` (+83) |
| 8 | `2264871` | 7 | Replay engine per-session accumulators | `shared/replay_engine.py` (+169/-14), `tests/test_replay_engine_per_session.py` (+186) |
| 9 | `2a184df` | 8 | GUI TSM panel per-session breakdown | `captain-command/.../b2_gui_data_server.py` (+61) |

**Dependency order** (matches deployment order above): Phase 2 must land first (writes the new map). Phase 3a depends on Phase 2's writes. Phase 3 depends on session_id reaching B7 via the position dict. Phases 4 and 5 are reader-side and depend on 2 + 3. Phase 6 (B5) is observability-only and parity-safe with Phase 5. Phase 7 (replay engine) brings the historical sim to parity. Phase 8 (GUI) is a read-only render of D23 + D08.

The non-budget commit (`249ffa9`, the cmd-run/path fix) landed in the same window because it was needed by the tower-side validation runbook for this rollout. It is documented separately in the deploy-discipline rule file and is **not** part of the per-session budget surface.

### 6.1 Important config change in Phase 2: c bumped 0.5 → 1.0

`config/tsm/providers/topstep_150k_eval.json` flipped `c` from `0.5` to `1.0` in commit `d158cc9` per Nomaan's instruction. Rationale captured in the commit body: with `c=0.5` and equal cold-start shares (each session gets 1/3 of the day), per-session `L_halt ≈ $250`, which is still tight enough to choke a 2-contract NY trade on a single SL. With `c=1.0` and the same shares, per-session `L_halt ≈ $500` — gives each session room to run its locked strategy without L1 cascading across sessions inside that session. Pure config change, fully reversible.

---

## 7. Test Coverage

| File | New | Purpose | Invariants tested |
|------|-----|---------|-------------------|
| `tests/test_sod_session_budget.py` | 27 tests | Unit-test the central helpers in `shared/sod_session_budget.py` | `session_budget_shares` (cold/blended/full + floor + renorm); `get_session_l_halt` / `get_session_e_exposure` / `get_session_n_max_trades` (lookup chain + legacy fallback); `compute_session_carryover` (worked examples A/B/C above + edge cases like all-skipped, single-session, zero-share denominators); `sessions_earlier_in_day` / `sessions_remaining_in_day` ordering |
| `tests/test_b8_reconciliation_sod_signature.py` | +2 tests | Phase 2 writer correctness | Per-session map written with cold-start equal thirds; HMM-warm 60/25/15 weights pass through; `session_shares_source` populated correctly per regime |
| `tests/test_orchestrator_session_budget_init.py` | 6 tests | Phase 3a hook behaviour | LON-open with no prior sessions; NY-after-LON-skip carryover correct; APAC-after-NY-loss carryover correct; idempotency (second call same session is no-op); NY_PRE legacy fallback; no-computed_sod accounts skip cleanly without aborting session |
| `tests/test_b7_per_session_d23_writes.py` | 4 tests | Phase 3 writer correctness | SELECT clause includes `WHERE session_id = %s`; INSERT preserves SOD-locked `effective_l_halt` / `effective_e_exposure` / `session_opened_at` (without preservation, first trade close clobbers session budget); per-`<session_id>:<model_m>` basket key namespacing; `session_id` default fallback chain (pos["session"] missing → 1=NY) |
| `tests/test_b5c_per_session_layers.py` | 8 tests | Phase 4 reader correctness | L1 reads `effective_l_halt` from D23 row; L1 falls back to `computed_sod.session.<KEY>.L_halt`; falls back further to legacy `computed_sod.L_halt`; falls back finally to live `c × e × A`; **flagship parity-isolation: LON loss does NOT pollute NY's L1 gate when intraday is per-session**; L2 symmetric chain for E_daily_exposure; L3 prefers `<session_id>:<model_m>` basket key, falls back to bare `<model_m>` |
| `tests/test_b4_per_session_cap.py` | 4 tests | Phase 5 reader correctness | Per-session cap reads session-specific E; flat-E fallback when no session block; cap = 999 when `topstep_optimisation=False`; static `topstep_params.daily_contract_cap` fallback when SOD has never run |
| `tests/test_b5_session_allocation_observability.py` | 3 tests | Phase 6 (observability-only) | `apply_hmm_session_allocation` no longer scales contracts: passes `final_contracts` through unchanged in (a) HMM-not-trained, (b) cold-start, (c) full-HMM modes — log line still fires for tuning observability |
| `tests/test_replay_engine_per_session.py` | 3 tests | Phase 7 historical-sim parity | Flagship: LON consumed $400 of L_t → APAC NKD gets non-zero contracts because its session L_t is independently 0; per-session L1 still blocks when APAC ITSELF has consumed $480 of $500; L3 basket scoping: NY m=6 P&L does NOT affect APAC's m=6 mu_b |
| `tests/test_d23_d25_decimal_roundtrip.py` | +1 test | Phase 1 schema check | Decimal columns on the new D23 fields (`effective_l_halt`, `effective_e_exposure`) round-trip through psycopg2 without the DOUBLE-cast bug from `2026-05-06_issue5_decimal_double_root_cause_audit.md` |

**Total new tests: ~58 across the 8 phases**, plus regression coverage from existing `test_b7_position_monitor_decimal_boundary.py`, `test_decimal_e2e_flow.py`, and `test_circuit_breaker_decimal.py` confirmed still passing per the per-phase commit messages.

---

## 8. Backwards Compatibility

The cardinal property of this rollout: **every reader falls back to legacy behaviour when its preferred state is absent.** This means partial deployment (only some commits land, e.g. tower A is on Phase 4 but tower B is still on pre-Phase-2 code) is operationally safe — the system runs with single-budget behaviour until the writer side starts populating the new map.

| Reader | Preferred path | Fallback chain |
|--------|----------------|----------------|
| B5C L1 (`_layer1_preemptive_halt`) | `intraday["effective_l_halt"]` (Phase 3a-written) | → `computed_sod.session.<KEY>.L_halt` → `computed_sod.L_halt` (legacy flat) → live `c × e × A` |
| B5C L2 (`_layer2_budget`) | Symmetric for E | Symmetric chain |
| B5C L3 (`_layer3_basket_expectancy`) | basket key `<session_id>:<model_m>` | Falls back to bare `<model_m>` for legacy `l_b` dicts |
| B4 `_compute_topstep_daily_cap` | `computed_sod.session.<KEY>.E_daily_exposure` | → flat `computed_sod.E_daily_exposure` → static `topstep_params.daily_contract_cap` → `999` |
| `shared.sod_session_budget.get_session_l_halt` | `computed_sod.session.<KEY>.L_halt` | → flat `computed_sod.L_halt` → `Decimal("0")` |
| `shared.sod_session_budget.get_session_e_exposure` | symmetric | symmetric |
| Replay engine `compute_contracts` L1 | `_intraday_cumulative_pnl_per_session[session_id]` against `_session_budget_map[session_id]` | Falls back to legacy global accumulators if the per-session dict is absent (e.g. an old replay driver) |
| Orchestrator `_initialize_session_budget` | succeeds with computed_sod populated | If exception during init: logs ERROR, does NOT abort session evaluation. B5C falls back to legacy single-budget for that session — matches the safety net in `get_session_l_halt` |

**Failure mode envelope:** in the absolute worst case (Phase 2 reverted on the writer side, Phase 4 still live on the reader side), B5C L1 falls all the way through to live `c × e × A`, which is the pre-2026-05-06 behaviour. No reader will crash, no session will be aborted, and the system runs as if per-session were never deployed. This is the property that makes the rollout safe to ship in 8 separately-revertible commits.

---

## 9. Known Limitations / Future Work

### 9.1 NY_PRE excluded from `TRADING_DAY_SESSION_ORDER` for v1

`shared/sod_session_budget.py:320` defines:

```python
TRADING_DAY_SESSION_ORDER: tuple[int, ...] = (2, 1, 3)
# = (LON, NY, APAC) by session_id
```

The HMM (`probs_to_ny_lon_apac` in `shared/hmm_online_inference.py`) only produces weights for 3 sessions. Including NY_PRE with a default share would break the budget-conservation property (shares would sum > 1). Practical impact: assets that trade only NY_PRE (currently MCL, ZT) fall through to the legacy flat L_halt/E behaviour — they get the full day budget, not a per-session slice. Future iteration: extend the HMM observation panel to produce 4-session weights, then add `4` to the tuple.

### 9.2 GUI frontend rendering pending

Backend (Phase 8 / `2a184df`) ships the `_get_tsm_status[].per_session` block in the GUI data server response. The captain-gui frontend cards (NY/LON/APAC budget tiles in the dashboard) are **not yet** rendering this — out of scope for the captain-system repo, will land in a follow-up commit on captain-gui. The data is already on the wire, so the frontend change is purely additive.

### 9.3 Carryover formula does not enforce strict day-total conservation under prior-skip

§4.3 worked example shows it: APAC after LON-skipped + NY-lost-$300 receives `effective_l_halt = $1200` (the entire remaining sod_total). On a day where LON also skips (l_t_final = 0), APAC could receive `effective_l_halt = $1500` — i.e. the full day budget concentrated into one session. This is **acceptable per design** because the single remaining session is the only place to spend the budget; not allowing it would leave money on the table. But it does mean L1's protective ceiling is locally larger than `c × e × A` per-session would suggest. Flag for awareness; not a bug. If we want strict daily-total conservation across sessions, we'd need an additional account-level cap on top of the per-session caps — separate amendment.

### 9.4 D-5 `abs(L_t)` semantics not changed

Per D-5, the `abs()` in B5C L1 still treats wins and losses identically with respect to budget consumption. The per-session split alone resolved the cascade Nomaan reported, so this is shipped as-is. If production traces show per-session L1 trips on winning sessions, escalate to the `losses-only-vs-magnitude` amendment.

### 9.5 Legacy flat scalars still written

D-2 keeps `computed_sod.L_halt` and `computed_sod.E_daily_exposure` for one release. Until both are removed, B8's SOD path writes both shapes, which means the JSON payload is ~30% larger than necessary. Cleanup ticket: after 7 days of clean production traces, remove the legacy keys.

---

## 10. Approval

### Reviewed by Isaac
Date: ____________
Comments: ____________

### Reviewed by Nomaan
Date: ____________
Comments: ____________

---

*Design record landed alongside Phases 2–8. No further code or schema changes are made by this document — it is a record of decisions taken between `4dac522` and `2a184df` on `main`, both remotes (`origin` and `multi-user`) at the time of writing.*
