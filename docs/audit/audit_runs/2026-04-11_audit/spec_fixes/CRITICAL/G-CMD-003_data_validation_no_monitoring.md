# G-CMD-003 — Data Validation Missing Continuous Monitoring

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Captain Command |
| **Block** | B10 Data Validation |
| **Spec Reference** | Doc 34 PG-41 |
| **File(s)** | `captain-command/captain_command/blocks/b10_data_validation.py` |
| **Fixed In** | Session 2.2, commit `3b218ca` |

## What Was Wrong (Before)

Doc 34 PG-41 requires continuous validation of incoming data streams checking:
1. **Freshness** via `max_staleness` threshold -> `P3_MEDIUM` incident
2. **Completeness** via required fields check -> `P2_HIGH` incident
3. **Format** via schema validation -> `P2_HIGH` incident

The code only validated **user-submitted data** (entry price, commission, balance) and asset configs. There was:
- Zero data feed freshness checking
- No staleness timer or monitoring loop
- No call to `create_incident()` anywhere in the file
- No import of B9 incident response

Stale market data, missing feed fields, or corrupted schemas would go undetected until they caused downstream signal errors.

## What Was Fixed (After)

1. **`monitor_data_freshness(assets, max_staleness_s=300)`**: Queries `p3_session_event_log` for the last event per asset. When the time since last event exceeds `max_staleness_s`, creates a `DATA_STALENESS / P3_MEDIUM` incident via B9.

2. **`validate_completeness(data, required_fields, source)`**: Checks that all required fields exist in incoming data. Creates a `DATA_QUALITY / P2_HIGH` incident on any missing fields.

3. **`validate_format(data, schema, source)`**: Validates field types against a schema definition. Creates a `DATA_QUALITY / P2_HIGH` incident on type mismatches.

4. **B9 integration**: Imported `create_incident` from B9 incident response. `DATA_STALENESS` added to `INCIDENT_TYPES` set in B9.

## Overall Feature: Data Quality Defence (B10)

B10 is the system's **data quality firewall**. It validates data at two boundaries:

1. **User input validation** (existing): Ensures manually-entered values (entry prices, commissions, balances) are within acceptable ranges and formats. Prevents garbage-in from the GUI.

2. **Data feed monitoring** (this fix): Continuously checks that market data streams remain fresh, complete, and correctly formatted. This is the system's early warning for infrastructure failures — a stale data feed means the signal engine is operating on outdated prices, which can produce incorrect signals. The incident system ensures operations staff are notified at the appropriate severity level before stale data reaches the signal pipeline.
