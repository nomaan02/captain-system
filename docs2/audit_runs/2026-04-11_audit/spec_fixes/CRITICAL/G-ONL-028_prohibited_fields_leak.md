# G-ONL-028 / G-XCT-015 — Prohibited Fields Leak Through GUI WebSocket

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Online (B6) + Captain Command (B1) |
| **Block** | B6 Signal Output / B1 Core Routing |
| **Spec Reference** | Doc 20 PG-26, `shared/constants.py` PROHIBITED_EXTERNAL_FIELDS |
| **File(s)** | `captain-command/captain_command/blocks/b1_core_routing.py` |
| **Fixed In** | Session 0.1, commit `3a474ba` |

## What Was Wrong (Before)

Signal output had two outbound paths with inconsistent sanitization:

1. **API Adapter path** (B6 -> Redis -> Command B1 -> `sanitise_for_api()` -> B3 -> Brokerage): **Correctly sanitized** — only 6 fields (`asset, direction, size, tp, sl, timestamp`).

2. **GUI WebSocket path** (B6 -> Redis -> Command B1 -> `gui_push_fn(signal)` -> WebSocket -> Browser): **No sanitization** — all ~30 fields pushed directly, including `aim_breakdown`, `regime_probs`, `combined_modifier`, `expected_edge`, `win_rate`, `payoff_ratio`.

Any user with browser DevTools could inspect WebSocket messages and see the system's internal signal reasoning — AIM weights, regime probabilities, Kelly edge. In multi-user/multi-instance deployment, this leaked proprietary trading intelligence.

## What Was Fixed (After)

Added `sanitise_for_gui()` function in B1 core routing that strips all 9 `PROHIBITED_EXTERNAL_FIELDS` before the WebSocket push:

```python
gui_push_fn(user_id, {
    "type": "signal",
    "signal": sanitise_for_gui(signal),
})
```

The 9 prohibited fields:
`aim_breakdown`, `combined_modifier`, `regime_probs`, `kelly_params`, `aim_weights`, `strategy_logic`, `ewma_states`, `decay_states`, `sensitivity_results`

The Redis channel signal remains **unchanged** — internal processes (Command B1, Offline feedback loop) still receive the full signal blob for routing and learning. Sanitization is applied at the **external boundary** (GUI WebSocket and API adapter), not at the source.

## Overall Feature: Signal Sanitization Boundary

The system produces signals with ~30 internal fields for routing, sizing, and learning. The spec (Doc 20, PG-26) defines a strict **external boundary**: only 6 display-safe fields may reach end users. `PROHIBITED_EXTERNAL_FIELDS` in `shared/constants.py` is the canonical blacklist. Both outbound paths (API adapter for brokerage, GUI WebSocket for browser) must enforce this boundary. This is both a security concern (proprietary algorithm details) and a compliance concern (multi-user isolation requires that users cannot see each other's signal reasoning).
