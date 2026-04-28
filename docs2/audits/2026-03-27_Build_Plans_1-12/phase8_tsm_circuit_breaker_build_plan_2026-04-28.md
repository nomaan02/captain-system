# Phase 8 Build Plan — TSM PG-14 + Circuit Breaker Params
**Date:** 2026-04-28  
**Campaign:** Captain Offline 12-Phase Audit Fix  
**Phase scope:** F-30, F-31, F-32, F-33, F-34 (audit), plus F-58/Q-31, F-59/Q-32, F-61/Q-33 (decisions log Group G)  
**Primary files:** `captain-offline/captain_offline/blocks/b7_tsm_simulation.py` (270 lines), `captain-offline/captain_offline/blocks/b8_cb_params.py` (242 lines)  
**Executor:** Cursor Composer 2  
**Do NOT execute code — implement the batches exactly as specified.**

---

## Stage 1 Audit Summary

### Verified Current State

| Finding | File | Lines | Issue | Status |
|---------|------|-------|-------|--------|
| F-30 | b7_tsm_simulation.py | 59-97 | MLL evaluated per individual return, not per daily-aggregate block | UNFIXED |
| F-31 | b7_tsm_simulation.py | 44-56, 147-153 | `_block_bootstrap_path` generates `remaining_days` individual returns, not `remaining_days` blocks of 3-7 | UNFIXED |
| F-32 | b7_tsm_simulation.py | 143-154, 196-240 | No NULL branch for accounts with no mdd_limit AND no mll_limit | UNFIXED |
| F-58 | b7_tsm_simulation.py | 100-113, orchestrator 921-963 | D12.sizing_override never read in MC path; trade_returns not scaled | UNFIXED |
| F-59 | b7_tsm_simulation.py | — | No RPT-07 generation call after pass_probability write | UNFIXED |
| F-33 | b8_cb_params.py | 161-178 | running_loss resets per day (daily bucket loop); should be cross-day loss-only accumulation | UNFIXED |
| F-34 | b8_cb_params.py | 76-78, 95-96 | `r_bar = float(alpha)` (OLS intercept); spec says `r_bar = mean(r_series)` | UNFIXED |
| F-61 | b8_cb_params.py | 187-188 | `p_value > 0.05` gate zeros beta_b; spec does not include this gate | UNFIXED |

### Callers
- **b7_tsm_simulation.run_tsm_simulation**: called from `orchestrator.py:963` (via `_run_tsm_for_account`)
- **b8_cb_params.estimate_cb_params**: called from `orchestrator.py:327, 331`
- **b3_pseudotrader**: reads CB params (beta_b, r_bar, l_star) from D25 for CB layer-3/4 logic
- **b6_reports.py (Command)**: RPT-07 renderer reads pass_probability from D08 on-demand — this is the read side; Phase 8 adds the Offline write-side generator

### Q-17 Soft Confirmation — Explicit Assumption
Per decisions log §3.3: proceed with **loss-only cumulative interpretation** for `running_loss_at_trade_time`. This means L_b accumulates only negative per-contract P&L (unsigned magnitude), cross-day, with no reset. **If Isaac corrects to signed cumulative, reverse lines 173-178 of b8_cb_params.py.**

---

## Spec Authority Chain

For any ambiguity in Phase 8:
1. `captain_offline_audit_decisions_2026-04-27.md §2 Group G` (highest)
2. `2026-04-22_offline_spec_vs_code_audit_copy.md` findings F-30 through F-34
3. `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` PG-14, PG-16C
4. `docs2/spec-docs-02/offline/kelly_7_layer_pipeline.md`

---

## Batch 8.0 — Rewrite TSM MC Path Generator + Simulator (F-30 + F-31)

### Spec citations
- Audit F-30 (SA6-F01): MLL checked per return, not daily aggregate
- Audit F-31 (SA6-F02): `_block_bootstrap_path` builds 1-return-per-day path, not daily block structure
- Spec doc 32 PG-14 (inner loop):
```
FOR day IN range(remaining_days):
    block_size = random.choice([3, 5, 7])
    start_idx = random.randint(0, len(trade_returns) - block_size)
    daily_returns = trade_returns[start_idx : start_idx + block_size]
    daily_pnl = 0
    FOR ret IN daily_returns:
        sim_balance += ret; daily_pnl += ret
        sim_max_balance = max(sim_max_balance, sim_balance)
        sim_drawdown = sim_max_balance - sim_balance
        IF sim_drawdown > max_drawdown_limit: passed = False; BREAK
    IF daily_pnl < 0 AND abs(daily_pnl) > max_daily_loss: passed = False
    IF NOT passed: BREAK
IF passed AND (sim_balance - starting_balance) >= profit_target: pass_count += 1
```

### Pre-flight checks
```bash
grep -n "_block_bootstrap_path\|_simulate_path" captain-offline/captain_offline/blocks/b7_tsm_simulation.py
# Expect: _block_bootstrap_path defined at ~L44, _simulate_path at ~L59
# Confirm neither is called from outside this file
grep -rn "_block_bootstrap_path\|_simulate_path" captain-offline/ --include="*.py"
# Must return only b7_tsm_simulation.py
```

### Changes to `b7_tsm_simulation.py`

**Delete** lines 44-97 (both helper functions) and **replace** with a single `_simulate_one_path` function:

```python
# BEFORE (lines 44-97):
def _block_bootstrap_path(trade_returns: list[float], n_days: int) -> list[float]:
    ...

def _simulate_path(path_returns: list[float], starting_balance: float, ...) -> dict:
    ...
```

```python
# AFTER (replaces both functions — one function matching spec PG-14 structure):
def _simulate_one_path(
    trade_returns: list[float],
    remaining_days: int,
    starting_balance: float,
    max_drawdown_limit: float | None,
    max_daily_loss: float | None,
    profit_target: float | None,
) -> dict:
    """One MC path: outer day loop with inner block of 3-7 trades per spec PG-14.

    MDD is checked per-trade (inner loop).
    MLL is checked on daily_pnl aggregate (after inner loop).
    """
    n = len(trade_returns)
    sim_balance = starting_balance
    sim_max_balance = starting_balance
    passed = True

    for _ in range(remaining_days):
        block_size = random.choice(BLOCK_SIZES)
        start_idx = random.randint(0, max(n - block_size, 0))
        daily_returns = trade_returns[start_idx:start_idx + block_size]

        daily_pnl = 0.0
        for ret in daily_returns:
            sim_balance += ret
            daily_pnl += ret
            sim_max_balance = max(sim_max_balance, sim_balance)
            sim_drawdown = sim_max_balance - sim_balance

            if max_drawdown_limit is not None and sim_drawdown > max_drawdown_limit:
                passed = False
                break

        if not passed:
            break

        if max_daily_loss is not None and daily_pnl < 0 and abs(daily_pnl) > max_daily_loss:
            passed = False
            break

    target_reached = True
    if profit_target is not None:
        target_reached = (sim_balance - starting_balance) >= profit_target

    return {
        "passed": passed and target_reached,
        "final_balance": sim_balance,
        "max_drawdown": sim_max_balance - sim_balance,
    }
```

**Update the MC loop** (currently lines 143-154) to call the new function:

```python
# BEFORE (lines 147-154):
    for _ in range(N_PATHS):
        path = _block_bootstrap_path(trade_returns, remaining_days)
        sim = _simulate_path(path, current_balance, mdd_limit, mll_limit, remaining_target)
        results.append(sim)
        if sim["passed"]:
            pass_count += 1
```

```python
# AFTER:
    for _ in range(N_PATHS):
        sim = _simulate_one_path(
            trade_returns, remaining_days, current_balance,
            mdd_limit, mll_limit, remaining_target,
        )
        results.append(sim)
        if sim["passed"]:
            pass_count += 1
```

### Tests to add (`tests/test_b7_tsm_simulation.py`)
```python
def test_simulate_one_path_mdd_breach_checked_per_trade():
    # Returns: [+100, +100, -250] in one block — drawdown hits mid-block
    # MDD limit = 200. Peak after +100+100 = 200. Then -250 → drawdown=250 > 200
    result = _simulate_one_path(
        trade_returns=[100, 100, -250],
        remaining_days=1,
        starting_balance=1000,
        max_drawdown_limit=200,
        max_daily_loss=None,
        profit_target=None,
    )
    assert result["passed"] is False

def test_simulate_one_path_mll_checked_on_daily_aggregate():
    # Returns: [-80, -80] → daily_pnl = -160. MLL=150.
    # Neither individual trade breaches MLL. Aggregate does.
    result = _simulate_one_path(
        trade_returns=[-80, -80],
        remaining_days=1,
        starting_balance=1000,
        max_drawdown_limit=None,
        max_daily_loss=150,
        profit_target=None,
    )
    assert result["passed"] is False

def test_simulate_one_path_block_size_is_3_to_7():
    # Run many paths and verify each block sampled has 3–7 trades consumed
    # (statistical test via monkeypatch on random.choice)
    with mock.patch("random.choice", return_value=5) as m:
        _simulate_one_path([1.0]*20, 3, 1000, None, None, None)
    assert m.call_count == 3  # one call per day (remaining_days=3)
```

### Exit criteria
- `_block_bootstrap_path` and `_simulate_path` are gone
- `_simulate_one_path` passes the three tests above
- No other file imports the deleted functions

### Rollback
Restore lines 44-97 of b7_tsm_simulation.py from git; revert MC loop caller.

---

## Batch 8.1 — NULL pass_probability for Unconstrained Accounts (F-32)

### Spec citation
- Audit F-32 (SA6-F03): no NULL branch for accounts where both mdd_limit and mll_limit are absent
- Spec doc 32 PG-14: `IF NOT tsm.max_drawdown_limit AND NOT tsm.max_daily_loss: P3-D08[ac].pass_probability = None`

### Pre-flight checks
```bash
grep -n "mdd_limit\|mll_limit\|pass_probability" captain-offline/captain_offline/blocks/b7_tsm_simulation.py
# Confirm mdd_limit/mll_limit loaded at ~L122-123
# Confirm pass_probability always set to computed value at ~L154
```

### Changes to `b7_tsm_simulation.py`

Insert early-return block immediately after `remaining_target` is computed (after current line ~141, before the MC loop at line ~143):

```python
# AFTER remaining_target assignment (around line 142), ADD:

    # Spec PG-14: accounts with no constraints get NULL pass_probability
    if mdd_limit is None and mll_limit is None:
        _write_pass_probability(account_id, existing_row=None, pass_probability=None,
                                risk_goal=risk_goal)
        logger.info("TSM simulation %s: unconstrained account — pass_probability=None", account_id)
        return {
            "account_id": account_id,
            "pass_probability": None,
            "ruin_probability": None,
            "n_paths": 0,
            "remaining_days": remaining_days,
            "risk_goal": risk_goal,
            "alert": None,
        }
```

Also extract the D08 INSERT block into a helper `_write_pass_probability(account_id, existing_row, pass_probability, risk_goal)` so both the NULL path and the normal path share the same writer. In the NULL path, if no existing D08 row is found yet, skip the write silently.

**Note:** The D08 INSERT at lines 196-240 always passes computed `pass_probability`. After this batch, `pass_probability` can be `None` (Python `None` → SQL `NULL`). The INSERT at line 234 already uses `%s`, so this requires no schema change — `None` binds to NULL.

### Tests to add
```python
def test_null_pass_probability_for_unconstrained_account():
    tsm_config = {
        "starting_balance": 100000,
        "current_balance": 100000,
        "max_drawdown_limit": None,
        "max_daily_loss": None,
        "profit_target": None,
        "risk_goal": "GROW_CAPITAL",
    }
    with mock.patch("captain_offline.blocks.b7_tsm_simulation._write_pass_probability") as w:
        result = run_tsm_simulation("acc1", list(range(20)), tsm_config)
    assert result["pass_probability"] is None
    w.assert_called_once_with("acc1", mock.ANY, None, "GROW_CAPITAL")
    assert result["alert"] is None
```

### Exit criteria
- Accounts with `mdd_limit=None` AND `mll_limit=None` → `pass_probability=None` in return dict and NULL in D08
- Accounts with at least one limit set → computed value as before

### Rollback
Revert the early-return block and the `_write_pass_probability` extraction.

---

## Batch 8.2 — Wire D12.sizing_override into MC Trade Returns (F-58 / Q-31)

### Spec citation
- Decisions log §2 Group G, Q-31 / F-58: "TSM PG-14 must honour `D12.sizing_override` when running its MC. Phase 8. PG-14 inputs read sizing_override and apply to per-trade returns before bootstrap."
- Spec doc 32 PG-14 header: `INPUT: P3-D08, P3-D03, P3-D12`

### Pre-flight checks
```bash
grep -n "sizing_override" captain-offline/captain_offline/blocks/b8_kelly_update.py
# Expect: D12 INSERT at ~L295, L305 writes sizing_override as None (NULL default)
grep -n "sizing_override" captain-offline/captain_offline/blocks/b2_level_escalation.py
# Expect: writes non-NULL sizing_override on Level 2 decay
```

### Changes to `orchestrator.py` (`_run_tsm_for_account` method, ~lines 914-963)

Add D12 sizing_override load before calling `run_tsm_simulation`:

```python
# BEFORE (orchestrator ~L960-963):
            run_tsm_simulation(account_id, trade_returns, tsm_config)

# AFTER — add sizing_override load before call:
            # Q-31: read current sizing_override for active assets on this account
            # Use min across active assets (conservative: apply worst decay reduction)
            with get_cursor() as cur:
                cur.execute(
                    """SELECT sizing_override
                       FROM p3_d12_kelly_parameters
                       WHERE sizing_override IS NOT NULL
                       LATEST ON last_updated PARTITION BY asset_id""",
                )
                so_rows = cur.fetchall()
            sizing_override = min((r[0] for r in so_rows if r[0] is not None), default=1.0)
            sizing_override = max(0.0, min(1.0, sizing_override))  # clamp [0, 1]

            run_tsm_simulation(account_id, trade_returns, tsm_config, sizing_override)
```

### Changes to `b7_tsm_simulation.py`

Update function signature to accept `sizing_override`:

```python
# BEFORE (line 100):
def run_tsm_simulation(account_id: str, trade_returns: list[float],
                        tsm_config: dict) -> dict:
```

```python
# AFTER:
def run_tsm_simulation(account_id: str, trade_returns: list[float],
                        tsm_config: dict, sizing_override: float = 1.0) -> dict:
```

Apply the scaling before the MC loop (after the NULL-branch guard from Batch 8.1):

```python
    # Q-31: scale historical returns to reflect current decay-adjusted sizing
    if sizing_override != 1.0:
        trade_returns = [r * sizing_override for r in trade_returns]
```

### Tests to add
```python
def test_sizing_override_scales_returns_before_mc():
    # With sizing_override=0.5, trade_returns should be halved internally
    # Use large positive returns to ensure pass without override,
    # tiny positive returns (after 0.5 scale) fail to hit profit target
    trade_returns = [200.0] * 50  # big wins → would easily pass target
    tsm_config = {
        "starting_balance": 100000,
        "current_balance": 100000,
        "max_drawdown_limit": 50000,
        "max_daily_loss": 5000,
        "profit_target": 10000,
        "risk_goal": "PASS_EVAL",
    }
    with mock.patch("captain_offline.blocks.b7_tsm_simulation._simulate_one_path",
                    wraps=_simulate_one_path) as wrapped:
        run_tsm_simulation("acc1", trade_returns, tsm_config, sizing_override=0.5)
    # All calls to _simulate_one_path must receive returns scaled to 100.0 each
    first_call_returns = wrapped.call_args_list[0][0][0]
    assert all(abs(r - 100.0) < 1e-9 for r in first_call_returns)

def test_sizing_override_default_1_no_scaling():
    trade_returns = [50.0] * 20
    tsm_config = {"starting_balance": 100000, "current_balance": 100000,
                  "max_drawdown_limit": None, "max_daily_loss": None,
                  "profit_target": None, "risk_goal": "GROW_CAPITAL"}
    result = run_tsm_simulation("acc1", trade_returns, tsm_config, sizing_override=1.0)
    assert result["pass_probability"] is None  # unconstrained → NULL (Batch 8.1)
```

### Exit criteria
- `run_tsm_simulation` signature includes `sizing_override: float = 1.0`
- `_run_tsm_for_account` in orchestrator loads minimum sizing_override from D12 and passes it
- Trade returns are scaled before MC entry

### Rollback
Revert signature, remove scaling line, remove orchestrator D12 load.

---

## Batch 8.3 — Add RPT-07 Generation to Offline PG-14 (F-59 / Q-32)

### Spec citation
- Decisions log §2 Group G, Q-32 / F-59: "Offline owns RPT-07. The spec's `GENERATE RPT-07(P3-D08)` is a real instruction. Add RPT-07 generation to PG-14 after each `pass_probability` update."
- Spec doc 32 PG-14 final lines: `GENERATE RPT-07(P3-D08)` then `SAVE P3-D08`

### Current state
RPT-07 is entirely in `captain-command/captain_command/blocks/b6_reports.py` as an on-demand reader/renderer (lines 358-399). It reads from D08 on request. There is no Offline-side generation. The Command renderer stays unchanged — this batch adds the generation step in Offline.

### Changes to `b7_tsm_simulation.py`

Add a `_generate_rpt07` helper and call it after the D08 write:

```python
# ADD this function (below the imports, above run_tsm_simulation):

_RPT07_KEY_TEMPLATE = "captain:reports:rpt07:{account_id}"
_RPT07_TTL = 86400  # 24 hours


def _generate_rpt07(account_id: str, pass_probability: float | None,
                    ruin_probability: float | None, risk_goal: str,
                    remaining_days: int, n_paths: int, alert: dict | None):
    """PG-14 GENERATE RPT-07: store MC summary to Redis for Command renderer.

    Key: captain:reports:rpt07:{account_id}
    TTL: 24 hours (refreshed on each simulation run)
    """
    try:
        import json
        client = get_redis_client()
        report = {
            "account_id": account_id,
            "pass_probability": pass_probability,
            "ruin_probability": ruin_probability,
            "risk_goal": risk_goal,
            "remaining_days": remaining_days,
            "n_paths": n_paths,
            "alert_priority": alert["priority"] if alert else None,
            "generated_at": now_et().isoformat(),
        }
        key = _RPT07_KEY_TEMPLATE.format(account_id=account_id)
        client.setex(key, _RPT07_TTL, json.dumps(report))
    except Exception as e:
        logger.error("RPT-07 generation failed for %s: %s", account_id, e)
```

Call it in `run_tsm_simulation` immediately after the D08 write block (after line ~241, before the alert publish):

```python
    # PG-14: GENERATE RPT-07(P3-D08)
    _generate_rpt07(account_id, pass_probability, ruin_probability,
                    risk_goal, remaining_days, N_PATHS, alert)
```

Also call it in the NULL-branch (Batch 8.1 early return) with `pass_probability=None`:

```python
    # In the unconstrained-account early return:
    _generate_rpt07(account_id, None, None, risk_goal, remaining_days, 0, None)
```

### Tests to add
```python
def test_rpt07_generated_after_simulation():
    tsm_config = {
        "starting_balance": 100000, "current_balance": 100000,
        "max_drawdown_limit": 50000, "max_daily_loss": 3000,
        "profit_target": 10000, "risk_goal": "PASS_EVAL",
    }
    trade_returns = [100.0] * 30
    with mock.patch("captain_offline.blocks.b7_tsm_simulation._generate_rpt07") as gen, \
         mock.patch("captain_offline.blocks.b7_tsm_simulation._write_pass_probability"):
        result = run_tsm_simulation("acc1", trade_returns, tsm_config)
    gen.assert_called_once()
    call_kwargs = gen.call_args
    assert call_kwargs[0][0] == "acc1"  # account_id
    assert call_kwargs[0][3] == "PASS_EVAL"  # risk_goal

def test_rpt07_generated_for_unconstrained_account():
    tsm_config = {
        "starting_balance": 100000, "current_balance": 100000,
        "max_drawdown_limit": None, "max_daily_loss": None,
        "profit_target": None, "risk_goal": "GROW_CAPITAL",
    }
    with mock.patch("captain_offline.blocks.b7_tsm_simulation._generate_rpt07") as gen, \
         mock.patch("captain_offline.blocks.b7_tsm_simulation._write_pass_probability"):
        run_tsm_simulation("acc1", list(range(20)), tsm_config)
    gen.assert_called_once()
    assert gen.call_args[0][1] is None  # pass_probability=None
```

### Exit criteria
- `_generate_rpt07` exists in `b7_tsm_simulation.py`
- Called in all exit paths (normal path AND unconstrained-account NULL path)
- `captain-command/captain_command/blocks/b6_reports.py` is **not modified**

### Rollback
Remove `_generate_rpt07` function and its two call sites.

---

## Batch 8.4 — Fix running_loss_at_trade_time: Cross-Day Loss-Only Accumulation (F-33 / Q-17)

### Spec citation
- Decisions log §2 Group G, Q-17 / F-33: "`L_b` is per-basket, cross-day cumulative running loss (filter P3-D03 by basket, no daily reset). Code's signed cumulative same-day-with-reset is wrong on both axes."
- Decisions log §3.3 (soft flag): "reading 'running_loss_at_trade_time' as loss-only cumulative (negative outcomes only)."
- **⚠ Q-17 ASSUMPTION FLAG:** This plan proceeds with loss-only (unsigned magnitude accumulation). If Isaac confirms signed cumulative (running_loss += pnl_pc when pnl_pc < 0, keeping sign), reverse the accumulation at line marked `# Q-17-ASSUMPTION`.
- Spec doc 32 PG-16C: `L_series = [running_loss_at_trade_time(t) for t in trades]`

### Pre-flight checks
```bash
grep -n "by_day\|cumulative\|running_loss" captain-offline/captain_offline/blocks/b8_cb_params.py
# Expect: by_day defaultdict at ~L163, cumulative reset per day in inner loop ~L174
```

### Changes to `b8_cb_params.py` (lines 161-181)

**Delete** the entire `by_day` bucketing and per-day loop (lines 161-181). **Replace** with cross-day sequential accumulation:

```python
# BEFORE (lines 161-181):
    by_day = defaultdict(list)
    for t in trades:
        if t["ts"]:
            day = str(t["ts"])[:10]
            pnl_pc = t["pnl"] / max(t["contracts"], 1)
            by_day[day].append(pnl_pc)

    x_vals = []  # cumulative basket P&L before trade
    y_vals = []  # per-contract return of trade

    for day, returns in by_day.items():
        cumulative = 0.0
        for r in returns:
            x_vals.append(cumulative)
            y_vals.append(r)
            cumulative += r
```

```python
# AFTER (replaces lines 161-181):
    # Q-17: running_loss_at_trade_time — cross-day, loss-only accumulation
    # L_b = sum of abs(pnl_pc) for all prior trades where pnl_pc < 0
    # Trades already sorted by ts from _load_trades_by_account_model
    x_vals = []  # L_b at trade time (loss-only, unsigned, cross-day)
    y_vals = []  # per-contract return of this trade

    running_loss = 0.0
    for t in trades:
        pnl_pc = t["pnl"] / max(t["contracts"], 1)
        x_vals.append(running_loss)   # L_b BEFORE this trade
        y_vals.append(pnl_pc)
        if pnl_pc < 0:
            running_loss += abs(pnl_pc)  # Q-17-ASSUMPTION: loss-only unsigned accumulation
```

Also remove `from collections import defaultdict` import at line 31 IF it is now only used here (verify it is not used elsewhere in the file first — `_compute_same_day_correlation` also uses `defaultdict`, so **keep the import**).

### Tests to add
```python
def test_running_loss_accumulates_cross_day():
    # Simulate trades across two days: day1=[+10, -20], day2=[+5, -15]
    # Expected L_b sequence: [0, 0, 20, 20] (loss from day1-trade2 carries into day2)
    # (x_vals = L_b BEFORE each trade)
    from datetime import datetime
    trades = [
        {"pnl": 10, "contracts": 1, "ts": datetime(2026, 1, 1, 10, 0)},
        {"pnl": -20, "contracts": 1, "ts": datetime(2026, 1, 1, 11, 0)},
        {"pnl": 5, "contracts": 1, "ts": datetime(2026, 1, 2, 10, 0)},
        {"pnl": -15, "contracts": 1, "ts": datetime(2026, 1, 2, 11, 0)},
    ]
    # Call _build_regression_arrays (extract from estimate_cb_params or inline)
    # Verify x_vals = [0, 0, 20, 20]
    # (This may require extracting the accumulation logic to a helper for testability)

def test_running_loss_ignores_profits():
    trades = [
        {"pnl": 50, "contracts": 1, "ts": some_ts},   # profit — L stays 0
        {"pnl": 50, "contracts": 1, "ts": some_ts},   # profit — L stays 0
        {"pnl": -30, "contracts": 1, "ts": some_ts},  # loss — L becomes 30 AFTER
    ]
    # x_vals should be [0, 0, 0] — first two trades see L=0; loss trade also sees L=0 before it
    # After processing: running_loss = 30 (but that's not in x_vals since 4th trade not present)
```

**Implementation note:** For testability, extract the accumulation block into a module-level `_build_regression_arrays(trades: list[dict]) -> tuple[list, list]` helper. `estimate_cb_params` calls it. Tests call it directly.

### Exit criteria
- `by_day` defaultdict loop removed from the x_vals/y_vals building section
- New `running_loss` accumulation is sequential (no day reset), loss-only
- Q-17 assumption flag comment present in code
- Tests confirm cross-day carry and profit-skip behaviour

### Rollback
Restore original lines 161-181 (day-bucketed version).

---

## Batch 8.5 — Fix r_bar = mean(r_series) (F-34 / Q-18)

### Spec citation
- Decisions log §2 Resolved-by-spec, Q-18: "Doc 32 line 702: `r_bar = mean(r_series)`."
- Audit F-34 (SA7-F03): `r_bar` is set to OLS intercept (`alpha = y_mean - beta * x_mean`) instead of unconditional mean.

### Pre-flight checks
```bash
grep -n "r_bar\|alpha\|y_mean" captain-offline/captain_offline/blocks/b8_cb_params.py
# Expect: alpha computed at ~L77, "r_bar": float(alpha) at ~L96
```

### Changes to `b8_cb_params.py` (`_ols_regression`, lines 58-100)

Change the return value of `_ols_regression` so that `r_bar` is `y_mean`, not `alpha`:

```python
# BEFORE (line 96):
    return {
        "r_bar": float(alpha),
        ...
    }
```

```python
# AFTER:
    return {
        "r_bar": float(y_mean),   # Q-18: r_bar = mean(r_series) per spec doc 32 line 702
        ...
    }
```

`alpha` is still computed as an intermediate (it's needed for the residuals calculation at line 80: `y_pred = alpha + beta * x`). Keep it in scope; only change the return.

Also verify the `ss_xx < 1e-10` early return at line 74 — it already returns `float(y_mean)` for `r_bar` in the degenerate case. No change needed there.

**L_star downstream** (line 204): `l_star = -reg["r_bar"] / beta_b` — this now uses the correct `r_bar = mean(r_series)`. No structural change needed.

### Tests to add
```python
def test_r_bar_is_unconditional_mean():
    x = np.array([0.0, 10.0, 20.0, 30.0])
    y = np.array([2.0, 4.0, 3.0, 5.0])
    result = _ols_regression(x, y)
    expected_r_bar = float(np.mean(y))  # = 3.5
    assert abs(result["r_bar"] - expected_r_bar) < 1e-9

def test_r_bar_not_ols_intercept():
    # OLS intercept (alpha = y_mean - beta*x_mean) would differ from y_mean
    # when x_mean != 0 and beta != 0
    x = np.array([0.0, 10.0, 20.0, 30.0])
    y = np.array([2.0, 4.0, 3.0, 5.0])
    result = _ols_regression(x, y)
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    beta = result["beta_b"]
    ols_intercept = y_mean - beta * x_mean
    # r_bar should equal y_mean, NOT ols_intercept (they differ when x_mean!=0)
    assert abs(result["r_bar"] - y_mean) < 1e-9
    assert abs(result["r_bar"] - ols_intercept) > 1e-6  # confirms they differ
```

### Exit criteria
- `_ols_regression` returns `r_bar = float(y_mean)`, not `float(alpha)`
- Two tests above pass

### Rollback
Change `"r_bar": float(y_mean)` back to `"r_bar": float(alpha)`.

---

## Batch 8.6 — Drop p_value Gate from beta_b Estimation (F-61 / Q-33)

### Spec citation
- Decisions log §2 Group G, Q-33 / F-61: "Remove the `p_value > 0.05` zeroing of beta_b — it's not in spec. **Keep** the `n < 10` cutoff and the `cold_start = (n < 100)` flag."
- Spec doc 32 PG-16C: no p_value gate exists; spec has only `n < 10` skip and `cold_start = (n < 100)`.

### Pre-flight checks
```bash
grep -n "SIGNIFICANCE_THRESHOLD\|p_value\|cold_start\|MIN_OBS" captain-offline/captain_offline/blocks/b8_cb_params.py
# Expect:
#   MIN_OBS_REGRESSION=10 at L36
#   MIN_OBS_WARM=100 at L37
#   SIGNIFICANCE_THRESHOLD=0.05 at L38
#   if reg["p_value"] > SIGNIFICANCE_THRESHOLD or ... at L187
#   cold_start = n < MIN_OBS_WARM at L208
```

### Changes to `b8_cb_params.py`

**1. Delete the significance gate** (lines 186-188):

```python
# BEFORE (lines 186-188):
    # Significance gate
    if reg["p_value"] > SIGNIFICANCE_THRESHOLD or reg["n_obs"] < MIN_OBS_WARM:
        reg["beta_b"] = 0.0
```

```python
# AFTER: delete all three lines (comment + condition + assignment)
```

**2. Remove `SIGNIFICANCE_THRESHOLD` constant** (line 38) since it is now unused:

```python
# BEFORE (line 38):
SIGNIFICANCE_THRESHOLD = 0.05
```

```python
# AFTER: delete this line
```

**3. Keep unchanged (do not touch):**
- Lines 150-158: `if n < MIN_OBS_REGRESSION: ... return` (n<10 cutoff — spec mandates this)
- Line 208: `cold_start = n < MIN_OBS_WARM` (cold_start=(n<100) — spec mandates this)
- `MIN_OBS_REGRESSION = 10` and `MIN_OBS_WARM = 100` constants (both stay)

**4. Update docstring** at lines 15-21 to remove the p_value gate description:

```python
# BEFORE (line 19):
Significance gate: p_value > 0.05 OR n_obs < 100 -> beta_b = 0
```

```python
# AFTER:
Significance gate: REMOVED (Q-33 — not in spec).
Cold start (n < 10): skip regression, use conservative defaults.
Cold start (n < 100): run regression but cold_start=True (layers 3-4 conservative).
```

### Tests to add
```python
def test_p_value_gate_absent():
    # Previously: a high p_value (0.9) would zero out beta_b
    # Now: beta_b should be the OLS estimate regardless of p_value
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
    y = np.array([0.1, 0.2, 0.15, 0.3, 0.25, 0.35, 0.2, 0.4, 0.3, 0.45])
    result = _ols_regression(x, y)
    # The gate is gone — beta_b must be the OLS slope, not 0.0
    assert abs(result["beta_b"]) > 1e-6

def test_n_lt_10_still_triggers_early_return():
    # n<10 cutoff must still apply (spec-mandated)
    with mock.patch("captain_offline.blocks.b8_cb_params._load_trades_by_account_model",
                    return_value=[{"pnl": 10, "contracts": 1, "ts": some_ts}] * 5):
        with mock.patch("captain_offline.blocks.b8_cb_params._save_params") as saved:
            estimate_cb_params("acc1", 7)
    saved_params = saved.call_args[0][2]
    assert saved_params["beta_b"] == 0.0  # conservative default
    assert saved_params["cold_start"] is True

def test_cold_start_true_for_n_lt_100():
    # n=50 (≥10, <100): regression runs, cold_start=True
    trades_50 = [{"pnl": (i % 2 - 0.3) * 10, "contracts": 1, "ts": some_ts} for i in range(50)]
    with mock.patch("captain_offline.blocks.b8_cb_params._load_trades_by_account_model",
                    return_value=trades_50):
        with mock.patch("captain_offline.blocks.b8_cb_params._save_params") as saved:
            estimate_cb_params("acc1", 7)
    saved_params = saved.call_args[0][2]
    assert saved_params["cold_start"] is True

def test_cold_start_false_for_n_ge_100():
    # n=120 (≥100): cold_start=False
    trades_120 = [{"pnl": (i % 2 - 0.3) * 10, "contracts": 1, "ts": some_ts} for i in range(120)]
    with mock.patch("captain_offline.blocks.b8_cb_params._load_trades_by_account_model",
                    return_value=trades_120):
        with mock.patch("captain_offline.blocks.b8_cb_params._save_params") as saved:
            estimate_cb_params("acc1", 7)
    saved_params = saved.call_args[0][2]
    assert saved_params["cold_start"] is False
```

### Exit criteria
- `SIGNIFICANCE_THRESHOLD` constant deleted
- `p_value > SIGNIFICANCE_THRESHOLD` gate block deleted
- `n<10` early-return block intact
- `cold_start = n < MIN_OBS_WARM` intact
- All four tests above pass

### Rollback
Restore `SIGNIFICANCE_THRESHOLD = 0.05` constant and the `if reg["p_value"] > SIGNIFICANCE_THRESHOLD or reg["n_obs"] < MIN_OBS_WARM: reg["beta_b"] = 0.0` block.

---

## Execution Order

Execute batches in this sequence:

```
8.0 → 8.1 → 8.2 → 8.3 → 8.4 → 8.5 → 8.6
```

Batches 8.0–8.3 all touch `b7_tsm_simulation.py`. Commit after each batch to avoid merge conflicts. Batches 8.4–8.6 all touch `b8_cb_params.py`. Same rule.

---

## Cross-Batch Regression Guard

After all 7 batches, run the test suite targeting Phase 8 files:

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/test_b7_tsm_simulation.py tests/test_b8_kelly_update.py tests/test_b5c_circuit.py -v
```

Expected outcome: all Phase 8 tests pass; no regressions in `test_b5c_circuit.py` (Circuit Breaker online side).

---

## Pending Items

| Item | Action |
|------|--------|
| Q-17 soft-confirm | If Isaac confirms signed cumulative (not unsigned loss-only), revert Batch 8.4 accumulation line marked `# Q-17-ASSUMPTION` |
| Q-17 "running_loss vs signed cumul" | Flag in next Isaac message: "Batch 8.4 proceeded with unsigned loss-only L_b per §3.3. Please confirm or correct." |

---

## Summary of Files Modified

| File | Batches | Change type |
|------|---------|-------------|
| `captain-offline/captain_offline/blocks/b7_tsm_simulation.py` | 8.0, 8.1, 8.2, 8.3 | Delete+replace helper functions; add NULL branch; add sizing_override param; add RPT-07 generator |
| `captain-offline/captain_offline/blocks/b8_cb_params.py` | 8.4, 8.5, 8.6 | Replace day-bucketed accumulation with cross-day loss-only; fix r_bar to y_mean; drop p_value gate |
| `captain-offline/captain_offline/blocks/orchestrator.py` | 8.2 | Add D12 sizing_override load before TSM call |
| `tests/test_b7_tsm_simulation.py` | 8.0–8.3 | New/extended test file |
| `tests/test_b8_cb_params.py` (new or existing) | 8.4–8.6 | New test file or extension |

**Not modified:** `captain-command/captain_command/blocks/b6_reports.py` — the Command RPT-07 renderer reads from D08 on demand and is unaffected.
