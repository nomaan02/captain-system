# G-OFF-046 — Version Snapshot: rollback_to_version() Unimplemented

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Offline |
| **Block** | Support (Version Snapshot) |
| **Spec Reference** | Doc 32 Version Snapshot Policy |
| **File(s)** | `captain-offline/captain_offline/blocks/version_snapshot.py` |
| **Fixed In** | Session 4.2, commit `c4572c1` |

## What Was Wrong (Before)

Only `snapshot_before_update()` and `get_latest_version()` existed. The spec requires a full `rollback_to_version(component_id, version_id, admin_user_id)` function with a 7-step safety flow. **No rollback function of any kind existed.**

If a parameter update caused degraded performance, there was no automated way to revert to a known-good state. Manual database intervention would be required — error-prone and slow during a live trading session.

## What Was Fixed (After)

Full 7-step `rollback_to_version()` implemented per spec:

1. **Load target snapshot** from D18 (`version_history` table) by `version_id`
2. **Load current state** via new `get_current_state(component_id)` helper — reads from the correct backing table (D01/D02/D05/D12/D17) based on component type
3. **Pseudotrader comparison** via `run_signal_replay_comparison()` per asset — compares current vs target parameters. If REJECT, abort with HIGH alert
4. **Snapshot current state** before restoring (creates an undo point)
5. **Restore target state** to the backing table
6. **Regression tests** — row count verification + domain invariants (e.g., `inclusion_probability` in 0-1 for D02, non-negative `kelly_full` for D12). If tests fail, automatically revert to the undo snapshot
7. **HIGH notification** published to `captain:alerts` with rollback details

Additional supporting functions:

- **`get_current_state()`** (G-OFF-048): loads from `_COMPONENT_TABLES` mapping, deduplicates by key columns
- **`_enforce_max_versions()`** (G-OFF-047): called after every snapshot write, prunes oldest versions beyond 50-version limit with cold-storage migration logging
- **`snapshot_before_update()`** updated to accept `state=None` (auto-loads via `get_current_state()`)

Returns `{"status": "COMPLETED" | "REJECTED" | "REVERTED"}`.

## Overall Feature: Version Management System

The version snapshot system (D18) maintains a history of all parameter states across the system's learned components (AIM weights, Kelly fractions, EWMA statistics, model states). Every parameter update creates a timestamped snapshot before the change is applied. The rollback function provides the ability to revert to any previous snapshot, validated by the pseudotrader to ensure the rollback won't itself cause performance degradation. This is the system's primary defence against parameter drift — if adaptive learning goes wrong, any previous known-good state can be restored safely.
