# Nomaan Edits — Fee, Slippage & Transaction Cost Integration

**From:** Isaac
**Date:** 2026-03-12
**Priority:** HIGH — affects all P&L calculations, OO scores, and risk management
**Scope:** TSM fee schema extension, resolve_commission() update, P1 fee verification, pseudotrader fee handling, and fee-adjusted Topstep optimisation parameters.
**Compatibility:** Backward-compatible. Existing TSM files without `fee_schedule` fall back to `commission_per_contract`.

---

## Pre-Implementation Questions

### For Topstep (RESOLVED)

1. ~~"Does the TopstepX API return per-trade fee/commission data in the fill response?"~~
   **ANSWERED:** No. The API fill response does NOT include fee breakdown fields. A single "Fees" value per trade is visible in the Performance Dashboard after the fact, but not in the API response. **Implication:** `resolve_commission()` Source 1 (API fill data) will return null for Topstep accounts. Source 2 (TSM `fee_schedule`) is the primary source for fee estimation and P3-D03 commission logging.

2. ~~"Are fees reflected immediately in the real-time account balance?"~~
   **ANSWERED:** Yes. Fees are deducted immediately with every filled trade and reflected in Net P&L in real-time. The balance at any point — including at 19:00 EST reconciliation — is already net of fees. **Implication:** SOD parameter A is net of fees. Circuit breaker L_t tracks actual P&L which is automatically fee-adjusted. No intraday fee estimation needed for L_t tracking.

### For Nomaan (RESOLVED)

3. ~~"Does the QuantConnect backtest currently include commission/fee settings?"~~
   **ANSWERED:** Yes — QC has fees, commission, and slippage expectations hardcoded into their backtest engine. **P1 returns (D-22) are already NET of fees and slippage.** No P1 code changes or re-runs required.

   **Remaining question for Nomaan:** "What are the exact hardcoded fee, commission, and slippage values QC applies per instrument (ES, NQ, MES, CL)?" — needed to verify they match the TSM fee_schedule values. If there's a mismatch, the discrepancy should be documented but does NOT require a re-run (QC's built-in values are a reasonable approximation).

**Proceed with all changes. No P1 dependency.**

---

## Change 1 — Extend TSM Fee Schema

### Current State

TSM files have a flat `commission_per_contract` field:

```json
"commission_per_contract": 3.50
```

This does not capture:
- Multi-component fee structures (commission + exchange + regulatory + clearing)
- Instrument-specific fees (ES vs MES vs NQ)
- Account-type differences (Express Funded vs Live Funded)
- Slippage model configuration

### New Schema

Add optional `fee_schedule` block to TSM files. If present, it overrides `commission_per_contract`.

**Topstep Express Funded Account:**

```json
{
    "name": "Topstep 150K Express Funded",
    "classification": {
        "provider": "TopstepX",
        "category": "PROP_FUNDED",
        "stage": "LIVE",
        "risk_goal": "GROW_CAPITAL"
    },
    "starting_balance": 150000,
    "max_drawdown_limit": 4500,

    "commission_per_contract": 1.40,

    "fee_schedule": {
        "type": "TOPSTEP_EXPRESS",
        "fees_by_instrument": {
            "ES":  {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
            "MES": {"round_turn": 0.74, "components": {"nfa_clearing": 0.74}},
            "NQ":  {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
            "MNQ": {"round_turn": 0.74, "components": {"nfa_clearing": 0.74}},
            "CL":  {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}}
        },
        "slippage_model": {
            "type": "FIXED_TICKS",
            "ticks_per_side": 1
        }
    }
}
```

**Topstep Live Funded Account:**

```json
{
    "name": "Topstep 150K Live Funded",
    "classification": {
        "provider": "TopstepX",
        "category": "PROP_FUNDED",
        "stage": "LIVE",
        "risk_goal": "GROW_CAPITAL"
    },
    "starting_balance": 150000,
    "max_drawdown_limit": 4500,

    "commission_per_contract": 1.40,

    "fee_schedule": {
        "type": "TOPSTEP_LIVE",
        "fees_by_instrument": {
            "ES":  {"round_turn": 2.80, "components": {"commission": 0.00, "exchange": 2.46, "regulatory": 0.04, "clearing": 0.30}},
            "NQ":  {"round_turn": 4.18, "components": {"commission": 0.72, "exchange": 2.46, "regulatory": 0.04, "clearing": 0.96}},
            "MES": {"round_turn": 0.74, "components": {"commission": 0.00, "exchange": 0.62, "regulatory": 0.02, "clearing": 0.10}},
            "MNQ": {"round_turn": 1.12, "components": {"commission": 0.18, "exchange": 0.62, "regulatory": 0.02, "clearing": 0.30}},
            "CL":  {"round_turn": 4.30, "components": {"commission": 0.72, "exchange": 2.58, "regulatory": 0.04, "clearing": 0.96}}
        },
        "slippage_model": {
            "type": "FIXED_TICKS",
            "ticks_per_side": 1
        }
    }
}
```

**Broker Account (IBKR):**

```json
{
    "name": "IBKR Live",
    "classification": {
        "provider": "IBKR",
        "category": "BROKER_RETAIL",
        "stage": "LIVE",
        "risk_goal": "GROW_CAPITAL"
    },

    "commission_per_contract": 2.25,

    "fee_schedule": {
        "type": "BROKER",
        "fees_by_instrument": {
            "ES": {"round_turn": 4.50, "components": {"commission": 2.25, "exchange": 2.25}}
        },
        "slippage_model": {
            "type": "SPREAD_BASED",
            "spread_multiple": 0.5
        }
    }
}
```

### Backward Compatibility

If `fee_schedule` is absent: fall back to `commission_per_contract × contracts × 2` (round-trip). No existing TSM files break.

### Fee Lookup Function

```python
def get_fee_for_trade(tsm, asset, contracts=1):
    if tsm.get("fee_schedule"):
        instrument_fees = tsm["fee_schedule"]["fees_by_instrument"].get(asset)
        if instrument_fees:
            return instrument_fees["round_turn"] * contracts
    
    if tsm.get("commission_per_contract"):
        return tsm["commission_per_contract"] * contracts * 2
    
    return 0
```

**Effort:** 30 minutes.

---

## Change 2 — Update `resolve_commission()` in P3 Online Block 7

### Current Code (Line 1305 of Program3_Online.md)

Source 2 (TSM config) currently reads:

```python
if tsm and tsm.commission_per_contract:
    return tsm.commission_per_contract * contracts * 2
```

### Updated Code

```python
if tsm:
    if tsm.get("fee_schedule"):
        instrument_fees = tsm["fee_schedule"]["fees_by_instrument"].get(asset)
        if instrument_fees:
            return instrument_fees["round_turn"] * contracts
    
    if tsm.get("commission_per_contract"):
        return tsm["commission_per_contract"] * contracts * 2
```

### New Function: `get_expected_fee()`

Add alongside `resolve_commission()`. Used PRE-TRADE by Kelly sizing (Block 4) and circuit breaker (Block 7B) to estimate fees before actual fill data exists:

```python
def get_expected_fee(account_id, asset, contracts=1):
    tsm = tsm_configs.get(account_id)
    if tsm:
        return get_fee_for_trade(tsm, asset, contracts)
    return 0
```

This is distinct from `resolve_commission()` which uses the 3-source chain (API → TSM → fallback) AFTER a trade is filled.

### Integration with Kelly Sizing (Online Block 4)

In the existing Kelly sizing pipeline, `risk_per_contract` is used to compute contract count. Add expected fee to risk:

```python
risk_per_contract = ewma_states[u][argmax(regime_probs[u])].avg_loss
expected_fee = get_expected_fee(ac_id, u, 1)
risk_per_contract_with_fee = risk_per_contract + expected_fee
kelly_contracts = account_kelly * account_capital / risk_per_contract_with_fee
```

This is a 2-line addition to Block 4, not a rewrite.

**Effort:** 30 minutes.

---

## Change 3 — P1 Fee Documentation (RESOLVED — No Code Change)

**Status:** RESOLVED. QC hardcodes fees, commission, and slippage into backtests. P1 D-22 returns are already NET. No P1 code changes or re-runs required.

### What to Do

Document the fee assumption in the model generator config for traceability:

```json
{
    "entry_variants": [...],
    "exit_grid": {...},
    "fee_config": {
        "source": "QuantConnect hardcoded",
        "note": "QC applies built-in fees, commission, and slippage per instrument. D-22 returns are NET.",
        "verify_with_nomaan": "Request exact per-instrument fee/commission/slippage values from QC config for cross-check against TSM fee_schedule"
    },
    "output_directory": "models_raw_dataset/"
}
```

### Verification Step

Ask Nomaan to report the exact QC hardcoded values per instrument. Compare against TSM fee_schedule:

| Instrument | QC Hardcoded (Nomaan to report) | TSM Express | TSM Live | Match? |
|-----------|-------------------------------|-------------|----------|--------|
| ES | ? | $2.80 | $2.80 | TBD |
| NQ | ? | $2.80 | $4.18 | TBD |
| MES | ? | $0.74 | — | TBD |
| CL | ? | $2.80 | $4.30 | TBD |

If QC values differ from TSM, the discrepancy is documented but NOT a blocker — QC's built-in values are a reasonable approximation for backtest purposes. Live trading uses actual fees from the API or TSM fee_schedule (not QC values).

**Effort:** 15 minutes (documentation only).

---

## Change 4 — Fee-Adjusted Topstep SOD Parameters

### Update to Command Block 8 SOD Computation

The `topstep_state` computation (from Nomaan_Edits_P3.md, Change 1) needs φ:

```python
for ac in active_accounts:
    tsm = P3_D08[ac]
    if not tsm.get("topstep_optimisation"):
        continue

    A = tsm.current_balance
    mdd_fixed = tsm.max_drawdown_limit
    p = tsm.topstep_params.p
    e = tsm.topstep_params.e
    c = tsm.topstep_params.c
    
    # Fee from TSM fee_schedule
    active_asset = get_primary_trading_asset(ac)
    phi = get_fee_for_trade(tsm, active_asset, contracts=1)

    tsm.topstep_state = {
        "mdd_pct": mdd_fixed / A,
        "fee_per_trade": phi,
        "risk_per_trade_pct": p * (mdd_fixed / A) + phi / A,
        "risk_per_trade_dollar": mdd_fixed * p + phi,
        "max_trades": math.floor((e * A) / (mdd_fixed * p + phi)),
        "daily_exposure": e * A,
        "hard_halt_threshold": c * e * A,
        "max_payout": min(5000, 0.5 * max(A - 150000, 0)),
        "post_payout_mdd_pct": mdd_fixed / (A - min(5000, 0.5 * max(A - 150000, 0)))
                                if A > 150000 else mdd_fixed / A
    }
```

This supersedes the SOD computation in `Nomaan_Edits_P3.md` Change 1 — use this version instead (it includes φ).

**Effort:** Already included in Nomaan_Edits_P3.md scope (update, not additional work).

---

## Change 5 — Pseudotrader Fee Handling (RESOLVED — No Code Change)

**Status:** RESOLVED. Both data sources are already NET:

- **P3-D03 (live trade history):** `pnl` field is NET — fees deducted by `resolve_commission()` at trade close.
- **P1 D-22 (backtest history):** Returns are NET — QC hardcodes fees, commission, and slippage into backtests.

**No pseudotrader changes needed.** Whichever data source the pseudotrader replays, P&L is already net of fees.

### Slippage in Pseudotrader

The pseudotrader does NOT model additional slippage during replay — QC already applied slippage in D-22, and P3-D03 captures actual slippage from live fills. No adjustment needed.

**Effort:** 0 (no change required).

---

## Change 6 — Where Fees Apply: Complete System Map

### Every Point Where Fees/Slippage/Transaction Costs Touch the System

| # | Component | What It Does With Fees | Data Source | Change Needed? |
|---|-----------|----------------------|-------------|---------------|
| 1 | **TSM File** | Stores fee schedule per account, per instrument | User upload | **YES** — extend schema (Change 1) |
| 2 | **P1 QC Algorithm** | Applies fees during backtest → net returns in D-22 | QC hardcoded | **No** — CONFIRMED net. Document QC values for cross-check. |
| 3 | **P1 Blocks 2-5** | All OO computations use returns from D-22 | D-22 (confirmed net) | **No** — blocks are fee-adjusted automatically |
| 4 | **P2** | Strategy selection uses OO scores from P1 | D-24 | **No** — reads net OO scores from P1 |
| 5 | **P3 Online Block 1** | Loads TSM fee_schedule at session open | P3-D08 | **No** — already loads TSM configs |
| 6 | **P3 Online Block 4 (Kelly)** | risk_per_contract should include expected fee | TSM fee_schedule | **YES** — 2-line addition (Change 2) |
| 7 | **P3 Online Block 5 (Trade Selection)** | Selects trades from universe | Block 4 output | **No** — receives fee-adjusted sizing from Block 4 |
| 8 | **P3 Online Block 6 (Signal Output)** | Displays expected fee in signal to user | TSM fee_schedule | **NICE TO HAVE** — add expected_fee field to signal_display |
| 9 | **P3 Online Block 7 (Position Monitor)** | Deducts actual fee from gross P&L on trade close | `resolve_commission()` | **YES** — update TSM source parsing (Change 2) |
| 10 | **P3 Online Block 7B (Circuit Breaker)** | N uses fee-adjusted risk per trade | topstep_state.risk_per_trade_dollar | **YES** — included in SOD computation (Change 4) |
| 11 | **P3-D03 (Trade Outcome Log)** | Stores gross_pnl, commission, net_pnl, slippage | resolve_commission() output | **No** — schema already supports this |
| 12 | **P3-D23 (Circuit Breaker State)** | L_t tracks cumulative net P&L | P3-D03.pnl | **No** — already uses net P&L |
| 13 | **P3 Offline Block 2 (Decay Detection)** | BOCPD/CUSUM on net returns | P3-D03.pnl | **No** — already uses net P&L |
| 14 | **P3 Offline Block 3 (Pseudotrader)** | Replays with fees included | P3-D03 or D-22 | **No** — both sources confirmed NET |
| 15 | **P3 Offline Block 8 (Kelly Updates)** | Kelly params from net returns | P3-D03.pnl | **No** — already uses net P&L |
| 16 | **P3 Offline Block 8 (β_b Estimation)** | Regression on net trade returns | P3-D03.pnl | **No** — already uses net P&L |
| 17 | **P3 Command Block 8 (Reconciliation)** | SOD parameter computation includes φ | TSM fee_schedule | **YES** — included in SOD computation (Change 4) |
| 18 | **AIM-12 (Slippage)** | Learns from actual slippage data | P3-D03.slippage | **No** — already works correctly |
| 19 | **RPT-07 (TSM Compliance Report)** | Should include fee drag analysis | TSM fee_schedule | **NICE TO HAVE** — add fee summary section |
| 20 | **RPT-02 (Weekly Performance)** | Should show gross vs net breakdown | P3-D03 | **NICE TO HAVE** — add fee column |

### Summary of Changes Required

| Status | Count | Items |
|--------|-------|-------|
| **YES — Must Change** | 5 | #1, #6, #9, #10, #17 |
| **NICE TO HAVE** | 3 | #8, #19, #20 |
| **No Change** | 12 | #2, #3, #4, #5, #7, #11, #12, #13, #14, #15, #16, #18 |

### Provider-Agnostic Design Principle

The fee system is NOT Topstep-specific. Every account — Topstep, IBKR, any future provider — uses the same TSM `fee_schedule` schema. The system reads fees from TSM at runtime. Provider-specific logic lives ONLY in the TSM file (user-uploaded), never in code.

Adding a new provider means uploading a new TSM file with that provider's fee schedule. No code changes. No Nomaan involvement.

---

## Verification Checklist

After implementing:

- [ ] TSM files with `fee_schedule` load correctly (validate schema)
- [ ] TSM files WITHOUT `fee_schedule` still work (backward compatibility via `commission_per_contract`)
- [ ] `resolve_commission()` reads from fee_schedule when present, falls back to commission_per_contract when not
- [ ] `get_expected_fee()` returns correct fee for each instrument
- [ ] Kelly sizing (Block 4) includes expected fee in risk_per_contract
- [ ] SOD topstep_state.max_trades reflects fee-adjusted N (should be lower than fee-free N)
- [ ] Circuit breaker Block 7B uses fee-adjusted N from SOD params
- [ ] P3-D03 `commission` field correctly records fee from fee_schedule source
- [x] P1 returns confirmed net of fees (CONFIRMED — QC hardcodes fees/commission/slippage)
- [ ] **Nomaan:** Report exact QC hardcoded fee, commission, and slippage values per instrument (ES, NQ, MES, CL) — fill in the comparison table in Change 3. This determines how accurate the pseudotrader's cold-start replay is before live data (P3-D03) accumulates.

---

---

# PART 2 — PROVIDER-AGNOSTIC ACCOUNT ONBOARDING

## Design Principle

The system is NOT built for Topstep. It is built for ANY prop firm or broker. Topstep is the first provider, but the architecture must handle any future provider (Apex, FTMO, Earn2Trade, IBKR, Tradovate, etc.) by uploading a TSM file — not by changing code.

**Provider-specific logic lives ONLY in the TSM file.** Every piece of code reads from TSM fields generically. No `if provider == "Topstep"` branches anywhere in the codebase.

## What a TSM File Defines (Complete Field Register)

A TSM file is the single configuration document for one account. It tells the system everything it needs to know about that account's constraints, fees, and risk rules. Every account — regardless of provider — uses the same TSM schema.

### Required Fields (All Providers)

| Field | Type | Description |
|-------|------|-------------|
| name | string | Human-readable account identifier |
| classification.provider | string | Provider name (e.g., "TopstepX", "Apex", "IBKR") |
| classification.category | enum | PROP_EVAL, PROP_FUNDED, PROP_SCALING, BROKER_RETAIL, BROKER_INSTITUTIONAL |
| classification.stage | string | Current stage (STAGE_1, STAGE_2, LIVE, etc.) |
| classification.risk_goal | enum | PASS_EVAL, GROW_CAPITAL, PRESERVE_CAPITAL |
| starting_balance | float | Initial account balance |
| commission_per_contract | float | Flat fallback fee (round-trip per contract, used if fee_schedule absent) |

### Optional Fields (Provider-Dependent)

| Field | Type | Used By | Description |
|-------|------|---------|-------------|
| max_drawdown_limit | float | Prop firms | Maximum trailing drawdown ($). null for brokers without hard MDD. |
| max_daily_loss | float | Prop firms | Maximum daily loss limit ($). null if not enforced. |
| max_contracts | int | Prop firms | Hard contract cap. null if no cap. |
| profit_target | float | Eval accounts | Profit target to pass evaluation. null if not applicable. |
| evaluation_stages | array | Eval accounts | Multi-stage evaluation rules. null if not applicable. |
| scaling_plan | array | Funded accounts | Balance → max_contracts tiers. null if flat. |
| overnight_allowed | bool | All | Whether positions can be held overnight. |
| trading_hours | string | All | Permitted trading window (e.g., "09:30-16:00 America/New_York"). |
| margin_per_contract | float | Brokers | Margin requirement per contract. null for prop firms. |
| margin_buffer_pct | float | Brokers | Buffer multiplier on margin. null for prop firms. |
| fee_schedule | object | All | Structured fee schedule (see below). Falls back to commission_per_contract if absent. |
| topstep_optimisation | bool | Topstep-specific | Enables MDD%/circuit breaker functions. false for non-Topstep. |
| topstep_params | object | Topstep-specific | {p, e, c, lambda, max_payouts_remaining}. Only if topstep_optimisation = true. |

### fee_schedule Block (Provider-Agnostic)

```json
"fee_schedule": {
    "type": "string",
    "fees_by_instrument": {
        "<SYMBOL>": {
            "round_turn": float,
            "components": {
                "<component_name>": float,
                ...
            }
        }
    },
    "slippage_model": {
        "type": "FIXED_TICKS | SPREAD_BASED | NONE",
        "ticks_per_side": int,
        "spread_multiple": float
    }
}
```

The `type` field is informational (for logging and reports). The code never branches on it. The code reads `round_turn` for fee estimation and `components` for detailed logging/reporting.

## Onboarding Flow: Adding a New Account

### Step 1 — Create TSM File

User (Isaac or ADMIN) creates a JSON file following the schema above. Templates for common providers:

**Template: Topstep Express 150K**
```json
{
    "name": "Topstep 150K Express #1",
    "classification": {"provider": "TopstepX", "category": "PROP_FUNDED", "stage": "XFA", "risk_goal": "GROW_CAPITAL"},
    "starting_balance": 150000,
    "max_drawdown_limit": 4500,
    "max_daily_loss": 3000,
    "max_contracts": 15,
    "scaling_plan": {"0": 3, "1500": 4, "2000": 5, "3000": 10, "4500": 15},
    "consistency_rule": {"max_daily_profit": 4500},
    "overnight_allowed": false,
    "trading_hours": {"session_open": "18:00 EST", "session_close": "16:10 EST", "flat_by": "16:10 EST", "eod_exit_buffer": "15:55 EST", "weekend_close": "Friday 16:10 EST", "weekend_open": "Sunday 18:00 EST"},
    "commission_per_contract": 1.40,
    "fee_schedule": {
        "type": "TOPSTEP_EXPRESS",
        "fees_by_instrument": {
            "ES": {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
            "NQ": {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}},
            "MES": {"round_turn": 0.74, "components": {"nfa_clearing": 0.74}},
            "MNQ": {"round_turn": 0.74, "components": {"nfa_clearing": 0.74}},
            "CL": {"round_turn": 2.80, "components": {"nfa_clearing": 2.80}}
        },
        "slippage_model": {"type": "FIXED_TICKS", "ticks_per_side": 1}
    },
    "topstep_optimisation": true,
    "topstep_params": {"p": 0.005, "e": 0.01, "c": 0.5, "lambda": 0, "max_payouts_remaining": 5}
}
```

**Template: Topstep Live 150K**
```json
{
    "name": "Topstep 150K Live #1",
    "classification": {"provider": "TopstepX", "category": "PROP_FUNDED", "stage": "LIVE", "risk_goal": "GROW_CAPITAL"},
    "starting_balance": 150000,
    "starting_tradable": 30000,
    "reserve_balance": 120000,
    "capital_unlock": {"target_per_block": 9000, "block_size_pct": 0.20, "note": "Each $9k profit target unlocks next 20% from reserves"},
    "max_drawdown_limit": 4500,
    "max_daily_loss": 4500,
    "low_balance_dll_override": {"threshold": 10000, "dll_override": 2000},
    "scaling_plan": null,
    "overnight_allowed": false,
    "trading_hours": {"session_open": "18:00 EST", "session_close": "16:10 EST", "flat_by": "16:10 EST", "eod_exit_buffer": "15:55 EST", "weekend_close": "Friday 16:10 EST", "weekend_open": "Sunday 18:00 EST"},
    "commission_per_contract": 1.40,
    "fee_schedule": {
        "type": "TOPSTEP_LIVE",
        "fees_by_instrument": {
            "ES": {"round_turn": 2.80, "components": {"commission": 0.00, "exchange": 2.46, "regulatory": 0.04, "clearing": 0.30}},
            "NQ": {"round_turn": 4.18, "components": {"commission": 0.72, "exchange": 2.46, "regulatory": 0.04, "clearing": 0.96}},
            "MES": {"round_turn": 0.74, "components": {"commission": 0.00, "exchange": 0.62, "regulatory": 0.02, "clearing": 0.10}},
            "MNQ": {"round_turn": 1.12, "components": {"commission": 0.18, "exchange": 0.62, "regulatory": 0.02, "clearing": 0.30}},
            "CL": {"round_turn": 4.30, "components": {"commission": 0.72, "exchange": 2.58, "regulatory": 0.04, "clearing": 0.96}}
        },
        "slippage_model": {"type": "FIXED_TICKS", "ticks_per_side": 1}
    },
    "topstep_optimisation": true,
    "topstep_params": {"p": 0.005, "e": 0.01, "c": 0.5, "lambda": 0, "max_payouts_remaining": 5}
}
```

**Template: Apex Trader Funding 150K**
```json
{
    "name": "Apex 150K Funded",
    "classification": {"provider": "Apex", "category": "PROP_FUNDED", "stage": "LIVE", "risk_goal": "GROW_CAPITAL"},
    "starting_balance": 150000,
    "max_drawdown_limit": 5250,
    "max_daily_loss": null,
    "max_contracts": 15,
    "overnight_allowed": false,
    "trading_hours": "EXTENDED",
    "commission_per_contract": 1.57,
    "fee_schedule": {
        "type": "APEX_FUNDED",
        "fees_by_instrument": {
            "ES": {"round_turn": 3.14, "components": {"commission": 0.00, "exchange": 2.46, "clearing": 0.68}},
            "NQ": {"round_turn": 3.14, "components": {"commission": 0.00, "exchange": 2.46, "clearing": 0.68}}
        },
        "slippage_model": {"type": "FIXED_TICKS", "ticks_per_side": 1}
    },
    "topstep_optimisation": false
}
```

**Template: IBKR Retail**
```json
{
    "name": "IBKR Live",
    "classification": {"provider": "IBKR", "category": "BROKER_RETAIL", "stage": "LIVE", "risk_goal": "GROW_CAPITAL"},
    "starting_balance": 25000,
    "max_drawdown_limit": null,
    "max_daily_loss": null,
    "max_contracts": null,
    "margin_per_contract": 6600,
    "margin_buffer_pct": 1.5,
    "overnight_allowed": true,
    "trading_hours": "EXTENDED",
    "commission_per_contract": 2.25,
    "fee_schedule": {
        "type": "BROKER_IBKR",
        "fees_by_instrument": {
            "ES": {"round_turn": 4.50, "components": {"commission": 2.25, "exchange": 2.25}}
        },
        "slippage_model": {"type": "SPREAD_BASED", "spread_multiple": 0.5}
    },
    "topstep_optimisation": false
}
```

### Step 2 — Upload via GUI or File

**Current method (V1):** Drop the JSON file into the TSM directory. Captain Command Block 4 (`tsm_manager_A`) picks it up via `load_tsm()`.

**Future method (V2 GUI):** Upload through the GUI account management panel. GUI calls `load_tsm()` via Command Block 4 the same way.

Either way, `load_tsm()` validates the schema (including `fee_schedule` if present), stores in P3-D08, and triggers any downstream recalculation.

### Step 3 — System Validates and Activates

The existing `validate_tsm_schema()` in Command Block 4 needs one addition — validate `fee_schedule` structure if present:

```python
def validate_fee_schedule(fee_schedule):
    if fee_schedule is None:
        return True  # optional field
    
    assert "fees_by_instrument" in fee_schedule, "fee_schedule missing fees_by_instrument"
    
    for instrument, fees in fee_schedule["fees_by_instrument"].items():
        assert "round_turn" in fees, f"Missing round_turn for {instrument}"
        assert fees["round_turn"] >= 0, f"Negative round_turn for {instrument}"
        if "components" in fees:
            component_sum = sum(fees["components"].values())
            if abs(component_sum - fees["round_turn"]) > 0.01:
                log_warning(f"{instrument}: component sum ({component_sum}) != round_turn ({fees['round_turn']})")
    
    if "slippage_model" in fee_schedule:
        assert fee_schedule["slippage_model"]["type"] in ["FIXED_TICKS", "SPREAD_BASED", "NONE"]
    
    return True
```

### Step 4 — Done

No further steps. The system reads all constraints from the TSM file at runtime. Kelly sizing reads `max_drawdown_limit`, `max_daily_loss`, `max_contracts`. Fee functions read `fee_schedule`. Topstep optimisation reads `topstep_params`. Everything is driven by the TSM file.

## Adding a New Prop Firm: What's Required

| Item | Who | Effort |
|------|-----|--------|
| Research the firm's fee structure, MDD rules, daily loss rules, contract limits | Isaac | 30 min |
| Create a TSM JSON file using the schema above | Isaac | 15 min |
| Upload the file | Isaac (drop file or GUI upload) | 1 min |
| Code changes | Nobody | 0 |
| Nomaan involvement | None | 0 |

**Zero code changes to add any provider.** The TSM schema handles every prop firm constraint variant. If a future provider introduces a constraint type not in the schema (e.g., "maximum consecutive losing days"), a new optional field is added to the schema — but the existing fields and all existing TSM files remain valid.

## Fee Source Priority Chain (Updated with Topstep Answers)

For each trade, the system resolves the commission using this chain:

```
Source 1: API fill data → adapter.get_last_fill_commission()
    ↓ (returns null for Topstep — API does not expose fee fields)
Source 2: TSM fee_schedule → fee_schedule.fees_by_instrument[asset].round_turn × contracts
    ↓ (returns value if fee_schedule present)
Source 3: TSM flat fallback → commission_per_contract × contracts × 2
    ↓ (returns value if commission_per_contract present)
Source 4: Fallback → return 0, notify user to input
```

For Topstep accounts: Source 1 returns null (confirmed — API does not expose fees), Source 2 provides the estimate. Since Topstep deducts fees immediately from the balance (confirmed), the P&L tracked by the circuit breaker (L_t) is automatically net of fees. The Source 2 estimate is used for:
- P3-D03 `commission` field logging
- Pre-trade fee estimation (`get_expected_fee()`)
- N (max trades) computation in the Topstep optimisation functions

For broker accounts with API fee support (e.g., IBKR): Source 1 returns actual fee from API. Source 2 is unused.

---

## Timeline

| Task | Effort | Dependency |
|------|--------|------------|
| Change 1: TSM fee schema + templates | 30 min | None |
| Change 2: resolve_commission() + get_expected_fee() + Kelly integration | 30 min | Change 1 |
| Change 3: P1 fee documentation | 15 min | None (resolved — QC is net) |
| Change 4: SOD params with φ | Already in Nomaan_Edits_P3.md | Change 1 |
| Change 5: Pseudotrader fee handling | 0 min | None (resolved — both sources are net) |
| Change 6: Applicability map | Documentation only | None |
| Provider onboarding: fee_schedule validation in tsm_manager_A | 15 min | Change 1 |
| Provider onboarding: TSM templates (4 providers documented above) | 0 min | Already in this document |
| **Total** | **1.5-2 hours** | |