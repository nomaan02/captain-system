# Session A: Exchange Protection Fixes — 2026-04-15

## Fix 1A: Tick-Align TP/SL Prices (P0 — CRITICAL)
- **Status:** APPLIED
- **Files Modified:**
  - `shared/contract_resolver.py` — added `get_tick_size(asset_id)` function
  - `captain-online/captain_online/blocks/b6_signal_output.py` — added `import math`, imported `get_tick_size`, tick-aligned prices in `_compute_tp()` and `_compute_sl()`
- **Changes:**
  - Added `get_tick_size(asset_id)` to `shared/contract_resolver.py` (lines 99-105). Reads tick size from `config/contract_ids.json` for the given asset, falls back to 0.25.
  - In `_compute_tp()`: after computing the raw TP price, rounds it to the nearest valid tick. LONG (direction=1) uses `math.floor` (round toward entry = conservative). SHORT (direction=-1) uses `math.ceil` (round toward entry = conservative).
  - In `_compute_sl()`: after computing the raw SL price, rounds it to the nearest valid tick. LONG (direction=1) uses `math.ceil` (round toward entry = tighter stop). SHORT (direction=-1) uses `math.floor` (round toward entry = tighter stop).
  - Both functions now accept `asset_id` as a 4th parameter. The caller in `run_signal_output()` passes `u` (the asset ID from the `recommended_trades` loop).
- **Validation:**
  - NKD long at 58855, raw SL at 58855.75: `ceil(58855.75 / 5) * 5 = ceil(11771.15) * 5 = 11772 * 5 = 58860`. Correct (rounds SL up toward entry for LONG).
  - MES long at 5500, raw TP at 5507.5375: `floor(5507.5375 / 0.25) * 0.25 = floor(22030.15) * 0.25 = 22030 * 0.25 = 5507.50`. Correct (rounds TP down toward entry for LONG).
  - ES short at 5500, raw SL at 5507.5375: `floor(5507.5375 / 0.25) * 0.25 = floor(22030.15) * 0.25 = 22030 * 0.25 = 5507.50`. Correct (rounds SL down toward entry for SHORT, where SL is above entry).

## Fix 2F: Remove Non-Existent OrderType Enum (P0 — LOW)
- **Status:** APPLIED
- **Files Modified:**
  - `shared/topstep_client.py` — removed `STOP_LIMIT = 3` from `OrderType` class
- **Changes:**
  - Removed `STOP_LIMIT = 3` from the `OrderType` enum (line 63). The TopStepX API enum jumps from 2 (MARKET) to 4 (STOP); value 3 does not exist. Grep confirmed no code references `OrderType.STOP_LIMIT` — only the definition and the investigation doc mentioned it.

## Fix 1C: Flatten Position on SL Failure (P1 — HIGH)
- **Status:** APPLIED
- **Files Modified:**
  - `captain-command/captain_command/blocks/b3_api_adapter.py` — added flatten-on-SL-failure logic in `send_signal()`
- **Changes:**
  - After the existing CRITICAL alert for SL placement failure, added an immediate call to `self._client.close_position(account_id, contract_id, size)` to flatten the unprotected position.
  - If flatten succeeds: sets `result["status"] = "FLATTENED_SL_FAIL"` and logs a warning.
  - If flatten also fails: sets `result["status"] = "EMERGENCY_UNPROTECTED"`, logs at CRITICAL level, and publishes an EMERGENCY-priority alert to `CH_ALERTS` indicating manual intervention is required.
  - The existing CRITICAL alert for SL failure is preserved — the flatten is a remediation step that follows it.

## Summary
- Fixes applied: 3/3
- Files modified:
  - `shared/contract_resolver.py`
  - `shared/topstep_client.py`
  - `captain-online/captain_online/blocks/b6_signal_output.py`
  - `captain-command/captain_command/blocks/b3_api_adapter.py`
- Tests updated: `tests/test_b3_api_adapter_sltp.py` — 2 tests updated to expect `FLATTENED_SL_FAIL` status (was `PLACED`), added `close_position` assertion. All 148 unit tests pass.
- Next steps:
  - Rebuild Docker containers (`captain-online`, `captain-command`) to deploy the fixes
  - Monitor next trading session for tick-alignment in logs (TP/SL prices should now be clean multiples of tick size)
  - Verify SL placement succeeds with tick-aligned prices (the root cause of SL rejection was misaligned prices)
  - The flatten-on-SL-failure is a safety net; with tick alignment fixed, SL placement should no longer fail
