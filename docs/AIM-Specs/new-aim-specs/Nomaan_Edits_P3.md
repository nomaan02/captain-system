# Nomaan Edits — Program 3: Topstep Optimisation & Circuit Breaker Integration

**From:** Isaac
**Date:** 2026-03-12
**Priority:** HIGH
**Scope:** 5 changes to P3. No changes to P1 or P2. Full specification in `Topstep_Optimisation_Functions.md` (same folder).
**Compatibility:** V1-ready. V2/V3-extensible (per-user aggregation loop added later).

---

## Summary

Add a Topstep-specific risk management layer to P3 that:
1. Computes MDD% and daily risk parameters per account at 19:00 EST
2. Screens every incoming trade signal through a 4-layer circuit breaker
3. Tracks intraday state (cumulative P&L, per-basket P&L, trade counts) per account
4. Estimates circuit breaker parameters from historical trade data
5. Tests circuit breaker configurations via pseudotrader replay

**What does NOT change:** Kelly sizing pipeline (Block 4 core), AIM framework (Blocks 1-3), decay detection (Offline Block 2), signal output format (Block 6), Command routing (all Command blocks). The Topstep functions add constraints — they never loosen existing constraints.

---

## Change 1 — SOD Parameter Computation (Command Block 8)

### Where

Add to `P3-PG-39: "daily_reconciliation_A"`, after the existing daily reset section.

### What to Add

After resetting `daily_loss_used`, compute and store Topstep SOD-locked parameters for each account that has `topstep_optimisation: true` in its TSM:

```python
for ac in active_accounts:
    tsm = P3_D08[ac]
    if not tsm.get("topstep_optimisation"):
        continue

    A = tsm.current_balance
    mdd_fixed = tsm.max_drawdown_limit  # $4,500 for 150k account
    p = tsm.topstep_params.p            # from P1 grid search or pseudotrader
    e = tsm.topstep_params.e
    c = tsm.topstep_params.c

    tsm.topstep_state = {
        "mdd_pct": mdd_fixed / A,
        "risk_per_trade_pct": p * (mdd_fixed / A),
        "risk_per_trade_dollar": mdd_fixed * p,
        "max_trades": math.floor(e / (p * mdd_fixed / A)),
        "daily_exposure": e * A,
        "hard_halt_threshold": c * e * A,
        "max_payout": min(5000, 0.5 * max(A - 150000, 0)),
        "post_payout_mdd_pct": mdd_fixed / (A - min(5000, 0.5 * max(A - 150000, 0)))
                                if A > 150000 else mdd_fixed / A
    }
```

### TSM File Extension

Add optional `topstep_optimisation` and `topstep_params` blocks to TSM files for Topstep accounts:

```json
{
    "name": "Topstep 150K Funded",
    "classification": {
        "provider": "TopstepX",
        "category": "PROP_FUNDED",
        "stage": "LIVE",
        "risk_goal": "GROW_CAPITAL"
    },
    "starting_balance": 150000,
    "max_drawdown_limit": 4500,
    "max_daily_loss": null,

    "topstep_optimisation": true,
    "topstep_params": {
        "p": 0.005,
        "e": 0.01,
        "c": 0.5,
        "lambda": 0,
        "time_partitions": null,
        "max_payouts_remaining": 5
    }
}
```

Non-Topstep accounts: `topstep_optimisation` absent or `false`. All existing TSM processing unchanged.

**Effort:** 30 minutes.

---

## Change 2 — Circuit Breaker Intraday State (New Dataset P3-D23)

### What to Create

New dataset in QuestDB, Redis-cached for real-time access:

```
P3-D23: circuit_breaker_intraday_state

Schema per account:
    account_id:     string
    L_t:            float       # cumulative P&L today (all trades)
    n_t:            int         # trades taken today (all baskets)
    L_b:            dict        # {model_m: float}  cumulative P&L per basket
    n_b:            dict        # {model_m: int}    trades per basket
    last_updated:   datetime
```

**Reset:** At 19:00 EST (same trigger as Command Block 8 daily reset), zero all fields for every account.

**Update:** After each TAKEN trade confirmation flows through Command Block 1 routing, update P3-D23[ac] with the trade's P&L.

**Effort:** 30 minutes (schema + reset hook + update hook).

---

## Change 3 — Circuit Breaker Screen Function (Online Block 7)

### Where

Add new program `P3-PG-27B: "circuit_breaker_screen_A"` to Online Block 7.

### When It Runs

Called AFTER Kelly sizing (Block 4) and AFTER trade selection (Block 5), but BEFORE signal output (Block 6). Every signal that would normally be emitted is first screened by this function. If it returns `take: False`, the signal is suppressed with the reason logged.

### Integration Point in Online Orchestrator

Current flow:
```
Block 4 (Kelly) → Block 5 (Trade Selection) → Block 6 (Signal Output)
```

New flow:
```
Block 4 (Kelly) → Block 5 (Trade Selection) → Block 7B (Circuit Breaker) → Block 6 (Signal Output)
```

### Implementation

Full pseudocode in `Topstep_Optimisation_Functions.md` Part 6, Section 6.1 (Online Block 7). Key points:

- Read SOD-locked params from P3-D08[ac].topstep_state (including scaling_tier_micros)
- Read intraday state from P3-D23[ac]
- Read current open positions from Online Block 7 position tracker
- Read basket params from P3-D25[ac][m]
- **Layer 0 (XFA only): Simultaneous position check.** `current_open_micros + proposed_micros > scaling_tier_micros` → BLOCKED. This limits concurrent exposure, NOT daily volume. When positions close, those slots become available again. Live accounts skip this layer (no scaling plan).
- **Layer 1 uses PREEMPTIVE check:** `abs(L_t) + rho_j >= L_halt` where rho_j = contracts × (SL × point_value + fee). This blocks trades whose worst-case SL outcome would breach the halt — not just trades where L_t has already breached it. Verified by pipeline trace: prevents double-loss scenarios where two consecutive SL hits exceed L_halt.
- 5 layers checked sequentially (Layer 0-4); first failure returns with reason
- If all pass, signal proceeds to Block 6
- Suppressed signals logged to P3-D23 with reason code

### Skip Condition

If account does not have `topstep_optimisation: true`, skip entirely. Non-Topstep accounts pass through with no screening.

**Effort:** 1-2 hours.

---

## Change 4 — Circuit Breaker Parameter Estimation (Offline Block 8)

### Where

Add new program `P3-PG-16C: "circuit_breaker_param_estimator_A"` to Offline Block 8.

### New Dataset P3-D25

```
P3-D25: circuit_breaker_params

Schema per account, per model:
    account_id:     string
    model_m:        int
    r_bar:          float       # unconditional mean return
    beta_b:         float       # loss-predictiveness coefficient
    sigma:          float       # per-trade return std dev
    rho_bar:        float       # average same-day trade correlation
    n_observations: int         # sample size used for estimation
    p_value:        float       # significance of beta_b
    last_updated:   datetime
```

### When It Runs

Same trigger as existing Kelly updates (Offline Block 8): after each trade outcome batch, or daily at minimum. Only processes accounts with `topstep_optimisation: true`.

### Cold Start

Before 100 observations per basket: β_b = 0, ρ̄ = 0. Layers 3-4 of the circuit breaker are effectively disabled. Hard halt (Layer 1) and budget (Layer 2) protect the account from day 1.

### Full Pseudocode

In `Topstep_Optimisation_Functions.md` Part 6, Section "Offline Block 8."

**Effort:** 1-2 hours.

---

## Change 5 — Pseudotrader Circuit Breaker Replay (Offline Block 3)

### Where

Add new programs `P3-PG-09B` and `P3-PG-09C` to Offline Block 3.

### What They Do

- **P3-PG-09B:** Replays historical trade sequences per-account at intraday resolution, applying the circuit breaker at each trade. Compares P&L/Sharpe/drawdown WITH vs WITHOUT circuit breaker.
- **P3-PG-09C:** Grid search mode — runs P3-PG-09B across multiple parameter combinations (c, λ), ranks by Sharpe improvement, filters by PBO < 0.5, selects best parameters.

### Key Difference from Existing Pseudotrader

The existing pseudotrader (P3-PG-09) replays at signal level (one per session per asset). The circuit breaker pseudotrader replays at trade level (multiple trades per day, chronologically ordered, with running intraday state). Phase 1 runs once (no CB), Phase 2 runs per parameter set (with CB). Same Phase 3-4 comparison and anti-overfitting validation.

### Output

Results stored in P3-D11 (existing retest results dataset) with `update_type: "CIRCUIT_BREAKER"`. RPT-09 generated with comparison metrics.

### Full Pseudocode

In `Topstep_Optimisation_Functions.md` Part 8.

**Effort:** 2-3 hours.

---

## What NOT to Change

| Component | Change? | Why |
|-----------|---------|-----|
| Online Blocks 1-3 (data ingestion, regime, AIM) | **No** | Shared market intelligence — circuit breaker is downstream |
| Online Block 4 (Kelly core) | **No** | Topstep cap added as `min()` constraint, not replacement |
| Online Block 5 (trade selection) | **No** | Selection logic unchanged; circuit breaker screens AFTER selection |
| Online Block 6 (signal output) | **No** | Output format unchanged; suppressed signals just don't reach Block 6 |
| Offline Blocks 1-2 (AIM training, decay) | **No** | Unrelated to Topstep optimisation |
| Offline Block 4 (injection) | **No** | Strategy injection unchanged |
| Command Blocks 1-7, 9-10 | **No** | Routing, GUI, API, TSM load, injection flow, reports, notifications, incidents, validation all unchanged |
| P1 | **No** | P1 operates at daily resolution. Circuit breaker is intraday. |
| P2 | **No** | Regime conditioning unchanged. |

---

## Verification Checklist

After implementing:

- [ ] SOD params compute correctly at 19:00 EST for Topstep accounts (verify f(A), N, E, L_halt match manual calculation)
- [ ] P3-D23 resets to zero at 19:00 EST for all accounts
- [ ] P3-D23 updates correctly after each TAKEN trade (L_t, n_t, L_b, n_b)
- [ ] Circuit breaker screen returns `take: False` when hard halt is breached (test: set L_halt very low)
- [ ] Circuit breaker **preemptive halt** blocks trades whose worst-case SL would breach L_halt (test: L_t = -$400, rho_j = $500, L_halt = $750 → abs(-400) + 500 = 900 ≥ 750 → BLOCKED)
- [ ] Circuit breaker screen returns `take: True` when all layers pass
- [ ] Non-Topstep accounts bypass circuit breaker entirely (no screening)
- [ ] P3-D25 populates with β_b = 0 during cold start (< 100 observations)
- [ ] P3-D25 produces non-zero β_b after 100+ observations (verify regression runs)
- [ ] Pseudotrader P3-PG-09B produces different P&L with vs without circuit breaker
- [ ] Pseudotrader P3-PG-09C grid search selects parameters that pass PBO < 0.5

---

## Timeline

| Task | Effort | Dependency |
|------|--------|------------|
| Change 1: SOD params in Command Block 8 | 30 min | None |
| Change 2: P3-D23 dataset + hooks | 30 min | None |
| Change 3: Circuit breaker screen (Online Block 7) | 1-2 hours | Changes 1, 2 |
| Change 4: Parameter estimation (Offline Block 8) | 1-2 hours | Change 2 |
| Change 5: Pseudotrader extension (Offline Block 3) | 2-3 hours | Changes 3, 4 |
| **Total** | **5-8 hours** | |

Changes 1 and 2 can be built in parallel. Change 3 depends on both. Change 4 can be built in parallel with Change 3. Change 5 depends on everything else.
