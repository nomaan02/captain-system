# G-OFF-015 — Pseudotrader Completely Unwired from Orchestrator

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Offline |
| **Block** | B3 Pseudotrader / Orchestrator |
| **Spec Reference** | Doc 32 PG-09 |
| **File(s)** | `captain-offline/captain_offline/blocks/orchestrator.py`, `b1_dma_update.py`, `b8_kelly_update.py` |
| **Fixed In** | Session 1.1, commit `28e6161` |

## What Was Wrong (Before)

The offline orchestrator had **zero references** to `b3_pseudotrader.py`. No event — trade outcome, weekly schedule, monthly schedule, or injection — dispatched to B3. The only caller was B4 `injection_comparison`, which imported `run_pseudotrader` directly and was itself not part of the standard orchestrator flow.

This meant DMA weight updates (D02), Kelly fraction updates (D12), and EWMA stat updates (D05) were committed to the database **without any pseudotrader validation**. The system could self-modify its own trading parameters with no safety gate checking whether the new parameters would degrade performance.

## What Was Fixed (After)

1. **`_pseudotrader_gate()`** added to the orchestrator — calls `run_signal_replay_comparison()` before any parameter write to D02, D05, or D12. If the pseudotrader comparison returns REJECT, the update is discarded and a HIGH alert is published.

2. **Fail-safe behaviour**: if the pseudotrader itself crashes during comparison, the update is REJECTED (safe default).

3. **Epsilon fast-path**: trivial changes where `max(|delta|) < 1e-4` skip the full replay to avoid unnecessary latency on negligible updates.

4. **`commit=False` dry-run mode** added to `b1_dma_update.py` and `b8_kelly_update.py` — these blocks now return `{current_weights, proposed_weights}` (or equivalent) without writing to the database, allowing the pseudotrader to compare before/after.

5. Gate applied to both `_handle_trade_outcome` and `_handle_signal_outcome` code paths.

## Overall Feature: Pseudotrader Safety Gate

The pseudotrader (B3) is the offline system's **parameter change validator**. Before any learned parameter (AIM weights, Kelly fractions, EWMA statistics) is committed to the database, the pseudotrader replays recent trading sessions using both the current and proposed parameters. It compares outcomes (Sharpe ratio, drawdown, win rate) and only allows the update if the proposed parameters do not degrade performance beyond acceptable thresholds.

PG-09 defines this as a mandatory gate on `proposed_update` events. Without it, the system's adaptive learning loop has no guardrail — a single bad trade outcome could cascade into parameter drift that degrades all future signals.
