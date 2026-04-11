            # Execution Log — Session 6.2: Online Circuit Breaker + Signal Output Fixes

            | Field | Value |
            |-------|-------|
            | **Phase** | 6 |
            | **Started** | 2026-04-11 12:46:20 ET |
            | **CRITICALs** | None |
            | **Git HEAD (before)** | `39b50f3` |
            | **Worktree** | `/home/nomaan/captain-system` |
            | **Status** | COMPLETE |

            ---

            ## Passover Prompt

            <details>
            <summary>Click to expand (2328 chars)</summary>

            ```
            ## Execution Session 6.2 — Online Circuit Breaker + Signal Output HIGH Fixes

You are executing Session 6.2 of the Captain System gap analysis fix plan.

### Context
7 HIGH-severity findings: CB dollar-budget check, rolling basket Sharpe, signal blob reduction,
anti-copy jitter, timezone-aware time-exit, shadow monitor retry, and crash recovery wiring.

### Before You Start — Read These Files
1. Spec: `mcp__obsidian__get_note("System 1/Direct Information/33 - Kelly Criterion and Bet-Sizing")` — CB layers
2. Spec: `mcp__obsidian__get_note("System 1/Direct Information/20 - P3 Command - Signal Routing and Execution")` — signal output
3. Code: `captain-online/captain_online/blocks/b5c_circuit_breaker.py` — lines 296-325, 375-437
4. Code: `captain-online/captain_online/blocks/b6_signal_output.py` — lines 94-134
5. Code: `captain-online/captain_online/blocks/b7_position_monitor.py` — line 134
6. Code: `captain-online/captain_online/blocks/b7_shadow_monitor.py` — lines 165-170
7. Code: `captain-online/captain_online/main.py` — lines 107-110
8. Audit: search GAP_ANALYSIS.md for G-ONL-024 to G-ONL-048

### Tasks
| # | Finding | Fix |
|---|---------|-----|
| 1 | G-ONL-024 | Replace trade-count ceiling with dollar-budget check in CB (HIGH) |
| 2 | G-ONL-025 | Replace analytical Sharpe with rolling_basket_sharpe(lookback=60d) (HIGH) |
| 3 | G-ONL-029 | Reduce signal blob to 6 spec fields at source (HIGH) |
| 4 | G-ONL-030 | Implement anti-copy jitter: +/-30s time, +/-1 micro size (HIGH) |
| 5 | G-ONL-032 | Fix time-exit to use timezone-aware datetime (HIGH) |
| 6 | G-ONL-036 | Add 3-attempt exponential backoff retry to shadow monitor publish (HIGH) |
| 7 | G-ONL-048 | Wire crash recovery checkpoint branching — coordinated with Phase 3 (HIGH) |

**Note:** Task 7 may already be partially done if Phase 3 Session 3.1 ran first.
Check `captain-online/main.py` for existing checkpoint branching before implementing.

### Verification
Run unit tests. Verify CB uses dollar budget, signal has 6 fields, time-exit is tz-aware.

### When Done
1. In GAP_ANALYSIS.md: Change all 7 findings from `[GAP]` to `[RESOLVED]`
2. In EXECUTION_ORCHESTRATOR.md: Mark Session 6.2 and Phase 6 as COMPLETE
3. Commit: `fix(online): CB dollar-budget, signal reduction, anti-copy jitter, tz-fix, retry — resolves G-ONL-024 to G-ONL-048`
            ```

            </details>

            ---

            ## Execution Output

### G-ONL-024 (HIGH) — CB L2 Dollar Budget
- **File:** `b5c_circuit_breaker.py` — replaced `_layer2_budget` function
- **Before:** Trade-count ceiling `n_t >= N` where `N = floor((e*A)/(MDD*p+phi))`
- **After:** Dollar-budget check `remaining = E - |L_t|; IF remaining < rho_j → BLOCK`
- Updated call site to pass `rho_j` instead of `fee_per_trade`

### G-ONL-025 (HIGH) — CB L4 Rolling Basket Sharpe
- **File:** `b5c_circuit_breaker.py` — replaced `_layer4_correlation_sharpe`
- **Before:** Analytical Sharpe from D25 CB params `S = mu_b/(sigma*sqrt(1+2*n_t*rho_bar))`
- **After:** `rolling_basket_sharpe(lookback=60d)` querying per-trade P&L from D03
- Added `_get_rolling_trade_returns()` helper; cold start < 10 trades → skip

### G-ONL-029 (HIGH) — Signal Blob Reduction
- **File:** `b6_signal_output.py` — restructured signal dict
- **Before:** ~30 fields flat in signal dict
- **After:** 6 spec fields at top level (asset, direction, size, tp_level, sl_level, timestamp) + routing (user_id, session, per_account) + `_context` sub-dict for internal fields
- Updated shadow monitor `register_shadow_position` to read from `_context`

### G-ONL-030 (HIGH) — Anti-Copy Jitter
- **File:** `b6_signal_output.py` — added `_apply_jitter()` function
- Time jitter: `random.uniform(-30, 30)` seconds on timestamp
- Size jitter: `random.choice([-1, 0, 1])` on contract size (floor at 1)
- Applied to published copies only; internal signals unchanged

### G-ONL-032 (HIGH) — Timezone-Aware Time-Exit
- **File:** `b7_position_monitor.py` — two changes
- `monitor_positions` line 134: `datetime.now()` → `datetime.now(ZoneInfo("America/New_York"))`
- `_parse_close_time`: `datetime.now()` → `datetime.now(ZoneInfo("America/New_York"))`

### G-ONL-036 (HIGH) — Shadow Monitor Retry
- **File:** `b7_shadow_monitor.py` — `_resolve_shadow` publish block
- Added 3-attempt exponential backoff (0.5s, 1s, 2s) matching B7 real publish pattern

### G-ONL-048 (HIGH) — Crash Recovery Checkpoint Branching
- **File:** `main.py` — checkpoint logic after `get_last_checkpoint()`
- Detects mid-session crash (next_action not in shutdown/initialization)
- Writes CRASH_RECOVERY checkpoint, logs warning with prior state

### Tests
- All 95 unit tests pass (0.54s)
- Updated `test_b5c_circuit.py`: L2 tests use dollar-budget semantics, L4 tests mock `_get_rolling_trade_returns`, all integration tests include rolling returns mock
- Updated `test_b6_signal.py`: `REQUIRED_SIGNAL_FIELDS` updated to match new 6-field + routing + _context structure

            ```
