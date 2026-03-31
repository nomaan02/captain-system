# Topstep Evaluation (Trading Combine) — TSM Template

**Date:** 2026-03-15
**Status:** DRAFT — requires Isaac's confirmation of flagged values
**Source:** Derived from XFA/Live rules in C2_CONTROL_MODELS.md Appendix A (Quant Project 2026.pdf)
**Purpose:** `PROP_EVAL` TSM template for P3. Fills the gap identified in Nomaan Feedstock Audit (B1).

---

## PROP_EVAL TSM Template

```json
{
    "name": "Topstep 150K Trading Combine",
    "classification": {
        "provider": "TopstepX",
        "category": "PROP_EVAL",
        "stage": "STAGE_1",
        "risk_goal": "PASS_EVAL"
    },
    "starting_balance": 150000,
    "profit_target": 9000,
    "max_drawdown_limit": 4500,
    "max_daily_loss": 3000,
    "max_contracts": 15,
    "scaling_plan": null,
    "consistency_rule": { "max_daily_profit": 4500 },
    "overnight_allowed": false,
    "trading_hours": {
        "session_open": "18:00 EST",
        "session_close": "16:10 EST",
        "flat_by": "16:10 EST",
        "risk_manager_flatten": "16:08 EST",
        "eod_exit_buffer": "15:55 EST",
        "weekend_close": "Friday 16:10 EST",
        "weekend_open": "Sunday 18:00 EST",
        "note": "Session spans overnight (18:00 to 16:10 next day). Positions held within session are allowed. Must be flat by 16:10 EST daily."
    },
    "evaluation_stages": [
        {
            "stage": "STAGE_1",
            "profit_target": 9000,
            "max_drawdown_limit": 4500,
            "max_daily_loss": 3000,
            "time_limit_days": null
        }
    ],
    "evaluation_end_date": null,
    "commission_per_contract": 1.40,
    "fee_schedule": {
        "type": "TOPSTEP_EXPRESS",
        "fees_by_instrument": {
            "ES": {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
            "NQ": {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
            "MES": {"round_turn": 0.74, "components": {"nfa_clearing": 0.74}},
            "MNQ": {"round_turn": 0.74, "components": {"nfa_clearing": 0.74}},
            "CL": {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
            "MCL": {"round_turn": 0.74, "components": {"nfa_clearing": 0.74}}
        },
        "slippage_model": {"type": "FIXED_TICKS", "ticks_per_side": 1}
    },
    "topstep_optimisation": true,
    "topstep_params": {"p": 0.005, "e": 0.01, "c": 0.5, "lambda": 0, "max_payouts_remaining": 0}
}
```

> **CORRECTION 2026-03-15:** `scaling_plan` removed — contract scaling is XFA-only, does NOT apply to Evaluation. Eval accounts have a flat `max_contracts` limit but no progressive scaling tiers. Trading hours added as structured object per Isaac's specification.

---

## Items Requiring Isaac's Confirmation

| # | Field | Current Value | Question |
|---|-------|---------------|----------|
| 1 | `profit_target` | $9,000 | Derived from XFA consistency rule ($4,500 = 50% of $9k target). Confirm this is the Trading Combine target for $150k. |
| 2 | `max_drawdown_limit` | $4,500 | Same as XFA. Confirm for evaluation. |
| 3 | `max_daily_loss` | $3,000 | Same as XFA. Confirm for evaluation (some Combine tiers may differ). |
| 4 | ~~`scaling_plan`~~ | ~~Same as XFA~~ | **RESOLVED:** Contract scaling is XFA-only. Eval has flat max_contracts=15, no scaling tiers. |
| 5 | `consistency_rule` | $4,500 max daily profit | Confirm: does the consistency rule apply during evaluation? |
| 6 | `time_limit_days` | null (no limit) | Topstep removed time limits. Confirm no deadline. |
| 7 | `evaluation_stages` | Single stage | Is the Trading Combine single-stage or multi-stage (e.g., Step 1 + Step 2)? |
| 8 | `fee_schedule` | Same as Express | Confirm: are evaluation fees identical to Express Funded? |
| 9 | `max_payouts_remaining` | 0 | No payouts during evaluation. Correct? |
| 10 | `max_contracts` | 15 | Confirm: is the Eval max 15 minis from day 1 (no scaling), or a different limit? |

---

## Differences from XFA Template

| Parameter | PROP_EVAL | PROP_FUNDED (XFA) | PROP_FUNDED (Live) |
|-----------|-----------|-------------------|--------------------|
| `classification.category` | `PROP_EVAL` | `PROP_FUNDED` | `PROP_FUNDED` |
| `classification.stage` | `STAGE_1` | `XFA` | `LIVE` |
| `classification.risk_goal` | `PASS_EVAL` | `GROW_CAPITAL` | `GROW_CAPITAL` |
| `profit_target` | $9,000 (pass target) | null | null |
| `scaling_plan` | **null** (no scaling) | Contract tiers (3→15) | **null** (no contract scaling) |
| `capital_unlock` | null | null | Profit-target based ($9k per 20% block) |
| `starting_tradable` | $150,000 (full) | $150,000 (full) | $30,000 (20% of transferred) |
| `evaluation_stages` | Present | null | null |
| `max_daily_loss` | $3,000 | $3,000 | $4,500 (scales with DRE) |
| `topstep_params.max_payouts_remaining` | 0 | 5 | N/A |

**Key account type distinctions:**
- **Eval:** No scaling, no capital unlock, no payouts. Goal is to reach profit target.
- **XFA:** Contract scaling tiers (profit-based tier progression), consistency rule, capped at $50k net profit per account.
- **Live:** Capital unlock from 20% reserve (each $9k profit unlocks next 20% block), no contract scaling, DLL scales with equity via Dynamic Risk Expansion.

---

## P3 Integration Points

This template is consumed by:
- **P3-D08:** TSM runtime state — loads these constraints at SOD
- **P3 Offline Block 7:** `pass_probability` simulation uses `profit_target`, `evaluation_end_date`, `max_daily_loss`
- **P3 Online Block 4:** Kelly sizing applies 0.85x multiplier for `PASS_EVAL` risk_goal
- **P3 Online Block 7 (PG-27B):** Circuit breaker uses `topstep_optimisation` flag
- **Pseudotrader (PG-09B):** Should replay with these constraints (see spec amendment)
