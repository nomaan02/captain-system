# API Contract Audit -- B7/B8/B9 + Orchestrator

```
AUDIT-META
  auditor:    ln-643-api-contract-auditor
  scope:      b7_notifications.py, b8_reconciliation.py, b9_incident_response.py, orchestrator.py
  date:       2026-04-09
  critical:   1
  high:       2
  medium:     3
  low:        1
  penalty:    (1 x 2.0) + (2 x 1.0) + (3 x 0.5) + (1 x 0.2) = 5.7
  score:      4.3 / 10
```

## Findings

| # | Severity | Rule | Location | Description |
|---|----------|------|----------|-------------|
| 1 | CRITICAL | R6: Architectural honesty | `orchestrator.py` L300-335 `_check_parity_skip()` | Read-named predicate (`_check_...`) mutates Redis via `client.incr(counter_key)`. Every call increments the daily signal counter. If called twice for the same signal (retry, exception-restart), the counter skews and **both instances permanently desynchronize** their parity sequence. The write must be extracted to a separate `_advance_parity_counter()` and the check must be pure. |
| 2 | HIGH | R4: Error contracts | `b9_incident_response.py` L136-189 `resolve_incident()` | Mixed error contract: success returns `{"incident_id", "status", ...}`, failure returns `{"error": str(exc)}`. Callers cannot distinguish success from failure without inspecting dict keys. Should raise on failure or use a typed result wrapper. |
| 3 | HIGH | R6: Architectural honesty | `b8_reconciliation.py` L298-391 `_check_payout_recommendation()` | Named `_check_*` but sends GUI push notifications and calls `notify_fn()` (write side-effects). Callers expect a check/predicate; the function silently dispatches user-visible notifications. Should be renamed to `_evaluate_and_notify_payout()` or split into check + notify. |
| 4 | MEDIUM | R2: Missing DTO | `b8_reconciliation.py` L298-302 `_check_payout_recommendation()` | 10 positional parameters (ac_id, user_id, ac, profit, W, commission_rate, tier_floor, scaling, gui_push_fn, notify_fn). 6+ of these are repeated between `_compute_sod_topstep_params` and `_check_payout_recommendation`. Should be grouped into a `TopstepComputationContext` dataclass. |
| 5 | MEDIUM | R4: Error contracts | `b9_incident_response.py` L221-258 `get_incident_detail()` | Three distinct return shapes: (a) success dict, (b) `{"error": "...not found"}` on missing, (c) `{"error": "...query failed"}` on exception, plus unreachable `{"error": "Unexpected state"}` at L258. No typed contract; callers cannot programmatically distinguish not-found from query failure. |
| 6 | MEDIUM | Encapsulation | `orchestrator.py` L67-69 | Imports 3 private (`_`-prefixed) functions from b7: `_get_all_active_user_ids`, `_is_in_quiet_hours`, `_get_user_preferences`. These are internal implementation details consumed cross-module, violating Python encapsulation convention. Should be promoted to public API (drop underscore) or wrapped in a public facade. |
| 7 | LOW | R2: Missing DTO | `b7_notifications.py` L479-524 `_log_notification_full()` | 9 positional parameters. While internal-only, the parameter list duplicates the notification shape already present in the `notif` dict passed to `route_notification()`. Could accept the notification dict directly. |

## Rule-by-Rule Summary

| Rule | Status | Notes |
|------|--------|-------|
| R1: Layer leakage | PASS | No HTTP types (Request, Response, Headers) in any block file. API boundary cleanly separated in `api.py`. |
| R2: Missing DTO | 2 findings | `_check_payout_recommendation` (10 params) and `_log_notification_full` (9 params). |
| R3: Entity leakage | PASS | No ORM used. All DB results manually mapped to plain dicts. No entity objects leak to API. |
| R4: Error contracts | 2 findings | `resolve_incident()` mixes return-dict-with-error and success-dict. `get_incident_detail()` has 3 return shapes + unreachable code. |
| R5: Redundant overloads | PASS | No `_with_`/`_and_` suffix patterns found. |
| R6: Architectural honesty | 2 findings | `_check_parity_skip()` mutates Redis counter (critical). `_check_payout_recommendation()` sends notifications (high). |

## Recommended Fixes (Priority Order)

1. **[CRITICAL] Split `_check_parity_skip`** into `_advance_signal_counter() -> int` (write) and `_should_skip_parity(trade_number, my_parity) -> bool` (pure read). This eliminates the retry-corruption risk.
2. **[HIGH] Standardize error contracts in B9** -- either raise exceptions consistently or adopt a `Result[T, E]` pattern. Remove unreachable code at L258.
3. **[HIGH] Rename `_check_payout_recommendation`** to `_evaluate_and_send_payout_recommendation` or split into check + notify.
4. **[MEDIUM] Promote B7 private functions** imported by orchestrator to public API (drop `_` prefix).
5. **[MEDIUM] Introduce `TopstepContext` dataclass** to bundle the 10 params flowing between SOD computation functions.
