# G-OFF-016 — No Actual Pipeline Replay in Pseudotrader

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Offline |
| **Block** | B3 Pseudotrader |
| **Spec Reference** | Doc 32 PG-09 Phases 1-2 |
| **File(s)** | `captain-offline/captain_offline/blocks/b3_pseudotrader.py` |
| **Fixed In** | Session 1.1, commit `28e6161` |

## What Was Wrong (Before)

The spec requires `captain_online_replay(d, using=CURRENT_parameters)` and `captain_online_replay(d, using=PROPOSED_parameters)` — full re-execution of the Online signal pipeline (B1 through B6) per historical day.

The code accepted pre-computed `baseline_pnl` and `proposed_pnl` lists as arguments. It compared them statistically (Sharpe, drawdown) but **never executed the Online pipeline**. A separate `run_signal_replay_comparison()` existed using `SignalReplayEngine` but was never called from the orchestrator.

This meant the pseudotrader could not detect **parameter interaction effects** — for example, a DMA weight change that alters AIM aggregation, which changes Kelly sizing, which changes signal output. Only direct P&L impact of pre-computed scenarios was tested.

## What Was Fixed (After)

1. **`captain_online_replay()`** implemented as a full B1-B6 pipeline replay for a single day. Uses `shared.replay_engine.run_replay()` for the first call (fetching cached bar data), then `run_whatif()` on subsequent calls with zero additional API calls (reuses `cached_bars`).

2. **`run_pseudotrader()` primary path updated**: when `baseline_pnl`/`proposed_pnl` are `None` (the default), the function fetches D03 trade outcomes, determines unique trading days, runs `captain_online_replay` for each day with current parameters (caching bars), then reruns with proposed parameters using the cached bars. This is the spec-correct full pipeline replay.

3. **Fast fallback preserved**: when P&L lists are provided directly, the old statistical comparison path remains available. This supports injection comparison (B4) where pre-computed P&L is the appropriate input.

4. **`run_signal_replay_comparison()`** wired as the entry point for the orchestrator's `_pseudotrader_gate()`, loading replay context per asset and delegating to `run_pseudotrader()`.

## Overall Feature: Pipeline Replay Comparison

The pseudotrader's core value is that it runs the **actual signal generation pipeline** with both current and proposed parameters. This catches interaction effects that a simple P&L comparison would miss — e.g., a small Kelly fraction change that causes a previously-viable signal to fall below the quality threshold, eliminating it entirely. The full replay path ensures the before/after comparison reflects exactly what would happen in live trading.
