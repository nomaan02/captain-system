            # Execution Log — Session 6.1: Online Sizing Pipeline Fixes

            | Field | Value |
            |-------|-------|
            | **Phase** | 6 |
            | **Started** | 2026-04-11 12:35:35 ET |
            | **CRITICALs** | None |
            | **Git HEAD (before)** | `b238041` |
            | **Worktree** | `/home/nomaan/captain-system` |
            | **Status** | COMPLETE |

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
