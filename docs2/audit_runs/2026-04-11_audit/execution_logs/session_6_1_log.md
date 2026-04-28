            # Execution Log — Session 6.1: Online Sizing Pipeline Fixes

            | Field | Value |
            |-------|-------|
            | **Phase** | 6 |
            | **Started** | 2026-04-11 12:35:35 ET |
            | **CRITICALs** | None |
            | **Git HEAD (before)** | `b238041` |
            | **Worktree** | `/home/nomaan/captain-system` |
            | **Status** | RUNNING |

            ---

            ## Passover Prompt

            <details>
            <summary>Click to expand (2171 chars)</summary>

            ```
            ## Execution Session 6.1 — Online Sizing Pipeline HIGH Fixes

You are executing Session 6.1 of the Captain System gap analysis fix plan.
**Prerequisite:** Phase 0 must be complete.

### Context
7 HIGH-severity findings in the Online signal pipeline: missing data sources for features
(overnight range, options data, PCR), Kelly sizing override position, loss-per-contract
formula, quality gate metric, and AIM session budget weights.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/33 - Kelly Criterion and Bet-Sizing")` — sizing layers, quality gate
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/23 - AIM Scoring")` — AIM aggregation, session budget
3. Code: `captain-online/captain_online/blocks/b1_features.py` — lines 863-864, 938-972
4. Code: `captain-online/captain_online/blocks/b4_kelly_sizing.py` — lines 190-193, 252-260
5. Code: `captain-online/captain_online/blocks/b5b_quality_gate.py` — lines 49-77
6. Code: `shared/aim_compute.py` — lines 175-178
7. Audit: search GAP_ANALYSIS.md for G-ONL-004 to G-ONL-021

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-ONL-004 | Implement _get_overnight_range data source or document unavailability (HIGH) |
| 2 | G-ONL-005 | Implement options data pipeline or mark AIM-02/03 as DATA_UNAVAILABLE (HIGH) |
| 3 | G-ONL-006 | Implement _get_trailing_pcr or deactivate AIM-02 pcr_z feature (HIGH) |
| 4 | G-ONL-018 | Move sizing override to pre-TSM position (between L6 and L7) (HIGH) |
| 5 | G-ONL-019 | Use spec formula: strategy_sl * point_value + expected_fee (HIGH) |
| 6 | G-ONL-021 | Implement dollar_per_contract = score / contracts in quality gate (HIGH) |
| 7 | G-ONL-013 | Return session_budget_weights from run_aim_aggregation() (HIGH) |

### Verification
Run unit tests. Verify sizing pipeline layer order and formula correctness.

### When Done
1. In GAP_ANALYSIS.md: Change all 7 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 6.1 as COMPLETE
3. Commit: `fix(online): sizing pipeline — features data, Kelly override/formula, quality gate, AIM budget — resolves G-ONL-004 to G-ONL-021`
            ```

            </details>

            ---

            ## Execution Output

            ```
Session 6.1 complete. Commit `39b50f3`. Here's the summary of all 7 fixes:

| # | Finding | Fix Applied |
|---|---------|-------------|
| 1 | **G-ONL-004** | `_get_overnight_range` now computes `abs(open/prior_close - 1)` from TopstepX daily bars — AIM-01 vrp_overnight is live |
| 2 | **G-ONL-005** | Options stubs (`_get_options_volume`, `_get_put_iv`, `_get_option_chain`) documented as DATA_UNAVAILABLE with one-time session log; AIM-02/03 degrade gracefully to neutral |
| 3 | **G-ONL-006** | `_get_trailing_pcr` documented as DATA_UNAVAILABLE (requires options volume); AIM-02 uses skew_z alone at 0.4 weight |
| 4 | **G-ONL-018** | Sizing override moved from Step 8 (post-TSM, on contracts) to Step 5b (pre-TSM, on Kelly fraction) — matches spec L6→L7 position |
| 5 | **G-ONL-019** | `risk_per_contract` now uses spec formula `strategy_sl * point_value + expected_fee` instead of EWMA avg_loss |
| 6 | **G-ONL-021** | Quality gate computes `dollar_per_contract = quality_score / total_contracts` with floor/ceiling check; `final_contracts` parameter added and wired from orchestrator |
| 7 | **G-ONL-013** | `run_aim_aggregation()` now loads session_budget_weights from D26 and includes in return dict |

All 95 unit tests pass. All 7 GAP_ANALYSIS entries updated to `[RESOLVED]`.

```

---

## Post-Execution State

| Field | Value |
|-------|-------|
| **Status** | **COMPLETED** |
| **Completed** | 2026-04-11 12:46:15 ET |
| **Duration** | 10m 40s |
| **Git HEAD (after)** | `39b50f3` |
| **Commit** | `39b50f3` |
