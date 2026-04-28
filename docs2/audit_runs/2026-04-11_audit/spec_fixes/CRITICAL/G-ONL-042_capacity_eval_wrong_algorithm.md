# G-ONL-042 — Capacity Evaluation Implements Entirely Different Algorithm

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Online |
| **Block** | B9 Capacity Evaluation |
| **Spec Reference** | Doc 33 PG-29 |
| **File(s)** | `captain-online/captain_online/blocks/b9_capacity_evaluation.py` |
| **Fixed In** | Session 2.1, commit `e492ece` |

## What Was Wrong (Before)

The spec requires **per-asset fill slippage analysis** with 5 specific metrics:
- `fill_quality` — mean absolute difference between fill price and signal price
- `slippage_bps` — fill quality normalised to basis points
- `avg_fill_time` — seconds from signal generation to fill
- `fill_rate` — ratio of executed trades to generated signals
- `volume_participation` — our contract volume vs market volume

The code implemented a **multi-user capacity planning model** based on signal supply/demand ratios, quality pass rates, correlation-adjusted diversity, and strategy homogeneity. None of the 5 spec metrics existed. The code never read trade fill data or signal prices.

The existing model served a valid purpose (capacity planning for multi-user scaling) but did not replace the spec's fill quality monitoring requirement.

## What Was Fixed (After)

Added `compute_fill_quality(session_id)` alongside the existing capacity evaluation:

1. **`fill_quality`**: Queries D03 (trade outcomes) for actual fill prices and D17 (session log) for signal prices. Computes `mean(abs(fill_price - signal_price))` per asset.

2. **`slippage_bps`**: `fill_quality / mean(expected_prices) * 10000` — normalised to basis points for cross-asset comparison.

3. **`avg_fill_time_s`**: Seconds from signal generation timestamp (D17) to fill timestamp (D03 `entry_time`).

4. **`fill_rate`**: `count(D03 trades) / count(D17 signals)` for the session.

5. **`volume_participation`**: `our_contracts / market_volume` from D30/D29 bar data.

Results saved to D17 under category `fill_quality`. Orchestrator wired to call at both session-end paths. When `slippage_bps > threshold` (configurable via D17 `slippage_threshold_bps`, default 50bps), a MEDIUM priority alert is published to `CH_ALERTS`.

## Overall Feature: Session-End Evaluation (B9)

B9 runs at session end to evaluate trading quality. It serves two purposes:

1. **Capacity planning** (existing): Evaluates whether the system can support additional users/accounts based on signal supply, asset diversity, and correlation structure. Produces constraints and recommendations for the System Overview GUI.

2. **Fill quality monitoring** (this fix): Empirically measures execution quality — how closely actual fills match expected prices, how fast fills arrive, and what fraction of signals successfully execute. This is the system's early warning for market microstructure degradation (widening spreads, increased latency, reduced fill rates). Both functions run independently at session end.
