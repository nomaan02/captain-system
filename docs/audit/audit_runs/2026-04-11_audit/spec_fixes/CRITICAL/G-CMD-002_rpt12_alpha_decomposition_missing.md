# G-CMD-002 — RPT-12 Alpha Decomposition Completely Missing

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Command |
| **Block** | B6 Reports |
| **Spec Reference** | Doc 29 §2.5 (S2-06) |
| **File(s)** | `captain-command/captain_command/blocks/b6_reports.py` |
| **Fixed In** | Session 4.1, commit `4a7e258` |

## What Was Wrong (Before)

Doc 29 defines 12 reports (RPT-01 through RPT-12). RPT-12 "Alpha Decomposition" should decompose PnL into component contributions: base strategy, regime conditioning, AIM modifiers, and Kelly sizing effects.

The code had only **11 entries** in `REPORT_TYPES` (RPT-01 through RPT-11). The module docstring explicitly said "11 report types." The `generators` dict had no RPT-12 entry. No alpha decomposition function existed anywhere in the codebase.

Without this report, it was impossible to determine **whether AIM modifiers, regime conditioning, or the base strategy drive performance** — critical for model validation and informed parameter decisions.

## What Was Fixed (After)

1. **`REPORT_TYPES`** updated with RPT-12 entry:
   ```python
   "RPT-12": {"name": "Alpha Decomposition", "trigger": "monthly", "render": "csv"}
   ```

2. **`generators`** map linked to `_rpt12_alpha_decomposition`.

3. **`_rpt12_alpha_decomposition()`** implemented (lines 522-643) — full per-trade decomposition:

   - Queries D03 (trade outcomes) for actual trades
   - Queries D05 (EWMA states) for baseline win rate and edge
   - Decomposes each trade's P&L into 4 components:
     - **`base_pnl`**: Raw 1-contract signal result (the strategy's edge before any modifiers)
     - **`regime_effect`**: Edge deviation from EWMA baseline via D05 (how much regime conditioning helped/hurt)
     - **`aim_effect`**: Position scaling from combined AIM modifier from D03 (how much AIM scoring helped/hurt)
     - **`kelly_effect`**: Multi-contract sizing contribution (how much Kelly sizing helped/hurt)
   - Outputs per-trade rows with absolute P&L + percentage attribution
   - Appends TOTAL summary row
   - 14-column CSV output

## Overall Feature: Reporting System (B6)

B6 generates 12 reports on various schedules (daily, weekly, monthly, on-demand). Reports cover daily P&L, risk exposure, AIM performance, regime accuracy, and more. RPT-12 is the **model validation report** — it answers "where does our alpha come from?" by decomposing observed returns into the contributions of each system component. This is essential for understanding whether the system's adaptive layers (AIM, regime detection, Kelly sizing) are adding value over the base Opening Range Breakout strategy, and for diagnosing performance degradation to the correct component.
