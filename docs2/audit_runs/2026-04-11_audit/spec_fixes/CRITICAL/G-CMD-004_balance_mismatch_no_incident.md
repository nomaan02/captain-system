# G-CMD-004 — Balance Mismatch Not Recorded as Incident

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Command |
| **Block** | B8 Reconciliation |
| **Spec Reference** | Doc 34 PG-39 Step 1 |
| **File(s)** | `captain-command/captain_command/blocks/b8_reconciliation.py` |
| **Fixed In** | Session 2.2, commit `3b218ca` |

## What Was Wrong (Before)

Doc 34 PG-39 step 1: if `abs(broker_balance - system_balance) > reconciliation_threshold`, the system must call:
```
create_incident("RECONCILIATION", "P2_HIGH", "FINANCE", "Balance mismatch for {ac}...")
```

The code at `b8_reconciliation.py:109-111` pushed a **GUI notification with priority "MEDIUM"** and logged the correction, but:
- Never called `create_incident()`
- Did not import B9 incident response
- The mismatch was auto-corrected (broker = source of truth) without creating an auditable incident record in P3-D21

Balance mismatches — which could indicate unauthorized trades, API errors, or accounting bugs — left **no formal incident trail**. An admin could not review historical reconciliation failures.

## What Was Fixed (After)

1. **Imported `create_incident`** from B9 incident response.

2. **Added `create_incident()` call** in the balance mismatch block:
   ```python
   create_incident("RECONCILIATION", "P2_HIGH", "FINANCE",
                   f"Balance mismatch for {ac_id}: system ${system_balance:,.2f} "
                   f"vs broker ${broker_balance:,.2f} (diff: ${mismatch:,.2f})")
   ```

3. **Existing GUI notification preserved** as a secondary alert — users still see the real-time notification, but the incident is now also recorded in D21 for audit trail.

4. **`notify_fn` passthrough** added to `_reconcile_api_account()` for flexibility in notification routing.

## Overall Feature: Account Reconciliation (B8)

B8 runs periodically (start-of-day and on-demand) to reconcile the system's internal account state with the broker's truth. For each API-connected account, it compares system-tracked balance against the broker's reported balance. Mismatches are auto-corrected (broker is the trusted source), but the system must maintain a **formal incident record** (D21) of every correction.

This serves two purposes: (1) **audit trail** — any balance discrepancy is logged with timestamp, amounts, and source, enabling post-hoc investigation of whether the mismatch was caused by missed fills, API errors, or external activity; (2) **pattern detection** — repeated reconciliation incidents for the same account may indicate a systemic integration issue that requires engineering attention.
