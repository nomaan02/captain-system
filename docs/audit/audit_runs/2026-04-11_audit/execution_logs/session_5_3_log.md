            # Execution Log — Session 5.3: Offline B7-B9 Kelly/CB/Diagnostic Fixes

            | Field | Value |
            |-------|-------|
            | **Phase** | 5 |
            | **Started** | 2026-04-11 12:18:19 ET |
            | **CRITICALs** | None |
            | **Git HEAD (before)** | `0b233ac` |
            | **Worktree** | `/home/nomaan/captain-system` |
            | **Status** | RUNNING |

            ---

            ## Passover Prompt

            <details>
            <summary>Click to expand (2091 chars)</summary>

            ```
            ## Execution Session 5.3 — Offline B7-B9 Kelly/CB/Diagnostic + Remaining B3 HIGH Fixes

You are executing Session 5.3 of the Captain System gap analysis fix plan.

### Context
6 HIGH-severity findings: Kelly estimation variance, CB L_star computation, CB cold_start
field, per-candidate OOS for PBO, pseudotrader SHA256 tick stream, and LEGACY/IDEAL modes.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/32 - Offline Pseudocode")` — PG-12 (Kelly update), PG-13 (CB params)
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/28 - Pseudotrader")` — sections 7-8 (SHA256, LEGACY/IDEAL)
3. Code: `captain-offline/captain_offline/blocks/b8_kelly_update.py` — lines 108-116
4. Code: `captain-offline/captain_offline/blocks/b8_cb_params.py` — lines 134-207
5. Code: `captain-offline/captain_offline/blocks/b6_auto_expansion.py` — lines 269-275
6. Code: `captain-offline/captain_offline/blocks/b3_pseudotrader.py` — full file (SHA256 + modes)
7. Audit: search GAP_ANALYSIS.md for G-OFF-039, G-OFF-040, G-OFF-041, G-OFF-033, G-OFF-017, G-OFF-018

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-OFF-039 | Replace 1/sqrt(N) proxy with compute_estimation_variance(P3-D05[u]) (HIGH) |
| 2 | G-OFF-040 | Compute and store L_star = -r_bar/beta_b in D25 circuit breaker params (HIGH) |
| 3 | G-OFF-041 | Add cold_start field to D25 writes; implement two-tier CB threshold (HIGH) |
| 4 | G-OFF-033 | Per-candidate OOS for PBO computation in auto-expansion (HIGH) |
| 5 | G-OFF-017 | SHA256 deterministic tick stream generator for synthetic regression tests (HIGH) |
| 6 | G-OFF-018 | LEGACY vs IDEAL mode parameter with mode-labelled results (HIGH) |

### Verification
Run unit tests. Focus on Kelly update and CB params tests.

### When Done
1. In GAP_ANALYSIS.md: Change all 6 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 5.3 and Phase 5 as COMPLETE
3. Commit: `fix(offline): Kelly variance, CB L_star/cold_start, PBO OOS, pseudotrader SHA256+modes — resolves G-OFF-017 to G-OFF-041`
            ```

            </details>

            ---

            ## Execution Output

            ```
Session 5.3 complete. Here's the summary:

## Session 5.3 Results — 6 HIGH findings resolved

| # | Finding | Fix | File(s) |
|---|---------|-----|---------|
| 1 | **G-OFF-039** | `_compute_estimation_variance()` — delta-method propagation of EWMA uncertainty through Kelly formula. Volatile assets now get more shrinkage than stable ones at same N. | `b8_kelly_update.py` |
| 2 | **G-OFF-040** | `L_star = -r_bar / beta_b` computed and stored in D25. NULL when beta_b >= 0 (no crossover). | `b8_cb_params.py`, `init_questdb.py` |
| 3 | **G-OFF-041** | Two-tier threshold: n<10 skip regression entirely, 10<=n<100 cold_start=true, n>=100 warm. `cold_start` boolean added to D25 schema + all write paths. | `b8_cb_params.py`, `init_questdb.py`, `bootstrap_production.py` |
| 4 | **G-OFF-033** | `_candidate_oos_returns()` replays each GA candidate on holdout data. PBO now computed on candidate-specific OOS P&L. | `b6_auto_expansion.py` |
| 5 | **G-OFF-017** | `SHA256TickStream` class with deterministic GBM mid-price + bid/ask spread model. Same seed = bitwise-identical ticks. | `b3_pseudotrader.py` |
| 6 | **G-OFF-018** | `REPLAY_MODE_IDEAL` / `REPLAY_MODE_LEGACY` parameter on `run_account_aware_replay` and `run_pseudotrader`. LEGACY strips account constraints; all results carry `mode` + `production` labels. | `b3_pseudotrader.py` |

**Tests:** 95/95 pass. **Phase 5: COMPLETE** (all 3 sessions done).

```

---

## Post-Execution State

| Field | Value |
|-------|-------|
| **Status** | **COMPLETED** |
| **Completed** | 2026-04-11 12:35:30 ET |
| **Duration** | 17m 11s |
| **Git HEAD (after)** | `b238041` |
| **Commit** | `b238041` |
