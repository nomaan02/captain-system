# 2026-04-14 ERROR: Timezone-Naive Datetime Crash — Zero Trades at NY Open

**Date:** 2026-04-14
**Severity:** CRITICAL — full session loss, zero trades executed
**Affected:** All 9 NY-session assets (ES, MES, NQ, MNQ, M2K, MYM, ZN, ZB + MGC LON breakout ignored)
**Instance:** Tower-1 (only running instance)

---

## Error

```
TypeError: can't subtract offset-naive and offset-aware datetimes
```

### Stack Trace (from Docker logs)

```
[ONLINE] 2026-04-14 09:25:02,286 ERROR captain_online.blocks.orchestrator:
  Session NY evaluation FAILED: can't subtract offset-naive and offset-aware datetimes

Traceback (most recent call last):
  File "/app/captain_online/blocks/orchestrator.py", line 247, in _run_session
    data = run_data_ingestion(session_id)
  File "/app/captain_online/blocks/b1_data_ingestion.py", line 830, in run_data_ingestion
    features = compute_all_features(assets, aim_states, locked_strategies)
  File "/app/captain_online/blocks/b1_features.py", line 608, in compute_all_features
    f["event_proximity"] = min_distance_to_event(f["events_today"], session_open or today)
  File "/app/captain_online/blocks/b1_features.py", line 177, in min_distance_to_event
    delta = (event_time - reference_time).total_seconds() / 60.0
TypeError: can't subtract offset-naive and offset-aware datetimes
```

---

## Root Cause

### The bug: `_load_economic_calendar()` ignored the timezone field

**File:** `captain-online/captain_online/blocks/b1_features.py`, function `_load_economic_calendar` (line 1054 pre-fix)

The economic calendar JSON (`config/economic_calendar_2026.json`) stores event times with a separate `"timezone"` field:

```json
{
  "name": "CPI",
  "date": "2026-04-14",
  "time": "08:30",
  "timezone": "America/New_York",
  "tier": 2,
  "scope": "ALL"
}
```

The loader parsed the time but **ignored the timezone field entirely**:

```python
# OLD CODE (line 1054)
"time": datetime.fromisoformat(f"{e['date']}T{e['time']}"),
# Produces: datetime(2026, 4, 14, 8, 30)  — no tzinfo (NAIVE)
```

This naive datetime was then subtracted from a timezone-aware reference in `min_distance_to_event` (line 177):

```python
# reference_time = session_open from _get_session_open_time()
#                = datetime(2026, 4, 14, 9, 30, tzinfo=ZoneInfo("America/New_York"))  — AWARE
delta = (event_time - reference_time).total_seconds() / 60.0
#        ^^^ NAIVE      ^^^ AWARE   → TypeError
```

### Why it was latent until today

This code path only executes when AIM-06 (Economic Calendar) is ACTIVE **and** there is a matching calendar event for the current date. April 14 had a CPI release at 08:30 ET — the first event to trigger the `min_distance_to_event` calculation in production. Days with no events return early from `min_distance_to_event` (`if not events: return None`) and never reach the subtraction.

### Why it killed the entire session

The two-phase pipeline architecture means Phase A (B1-B5C) must complete to populate `_pending_sessions`. Phase B (B6 signal output) only runs when `_pending_sessions` is non-empty:

```python
# orchestrator.py, line 131 — session loop
if self._pending_sessions and self._or_tracker:
    self._check_or_breakouts()
```

The Phase A crash at 09:25:02 meant `_pending_sessions` was never populated. When the OR tracker detected breakouts at 09:35:06 for all 9 NY assets, this guard silently evaluated to `False` and Phase B never ran. No signals were generated, no trades were placed.

---

## Timeline

| Time (ET) | Event |
|-----------|-------|
| 09:08:43 | Captain Online started — QuestDB, Redis, TopstepX all connected |
| 09:08:44 | MarketStream connected to 10 contracts |
| 09:25:00 | Session NY (1) detected — 5-minute window triggered Phase A |
| 09:25:01 | 10 assets registered with OR tracker; B1 ingestion started (8 NY-eligible) |
| 09:25:01 | MGC (LON) received quote, OR formed with 1 tick (outside LON window — expected) |
| 09:25:02 | `_get_session_open_time("ZN")` failed — registry path missing Docker fallback |
| **09:25:02** | **CRASH: `min_distance_to_event` — naive/aware datetime subtraction** |
| 09:25:02 | Session marked evaluated (`_session_evaluated_today[1] = today`) — no retry possible |
| 09:30:00 | OR tracker forms ORs for all 8 NY assets (MarketStream thread unaffected) |
| 09:35:00 | All 9 ORs complete |
| 09:35:06 | Breakouts detected: NQ, ES, MNQ, MES all LONG |
| 09:35:43 | MYM breakout LONG |
| 09:37:59 | ZN breakout LONG |
| 09:57:01 | ZB breakout LONG |
| 10:09:46 | M2K breakout LONG |
| All day | `_check_or_breakouts()` skipped on every loop iteration — `_pending_sessions` empty |

---

## Contributing Issue

### `_get_session_open_time()` — wrong Docker path

**File:** `captain-online/captain_online/blocks/b1_features.py`, function `_get_session_open_time` (line 1131 pre-fix)

This function only tried a relative path to `session_registry.json`:

```python
# OLD CODE
registry_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "session_registry.json"
)
# Resolves to /config/session_registry.json inside Docker (wrong)
# Actual location: /captain/config/session_registry.json
```

The OR tracker (`b8_or_tracker.py`) and session controller (`b9_session_controller.py`) both correctly try `/captain/config/` as a fallback — this function did not, causing the warning:

```
WARNING b1_features: Failed to load session open time for ZN, defaulting to 09:30 ET
```

The fallback (09:30 ET) happened to be correct for ZN (NY session), so this warning did not cause a functional error. However, for LON/APAC assets it would return the wrong session open time.

---

## Data Sources Involved

| Source | Path | Role |
|--------|------|------|
| Economic Calendar | `config/economic_calendar_2026.json` | CPI event at 08:30 triggered AIM-06 feature computation |
| Session Registry | `config/session_registry.json` | Session open times, asset-session mapping |
| Asset Universe | QuestDB `p3_d00_asset_universe` | 10 ACTIVE assets, 8 eligible for NY session |
| AIM Model States | QuestDB `p3_d01_aim_model_states` | AIM-06 status = ACTIVE triggered the calendar check |

---

## Fix

**Commit scope:** Single file — `captain-online/captain_online/blocks/b1_features.py`

### Change 1: `_load_economic_calendar` — read timezone from calendar JSON (CRITICAL)

Reads the `"timezone"` field from each calendar entry and applies it via `ZoneInfo`, making event datetimes timezone-aware.

```python
# BEFORE (line 1054)
"time": datetime.fromisoformat(f"{e['date']}T{e['time']}"),

# AFTER
"time": datetime.fromisoformat(f"{e['date']}T{e['time']}").replace(
    tzinfo=ZoneInfo(e.get("timezone", "America/New_York"))
),
```

**Result:** Event times are now `datetime(2026, 4, 14, 8, 30, tzinfo=America/New_York)` — compatible with all timezone-aware reference times in the system.

### Change 2: `_get_session_open_time` — add Docker path fallback

Searches `/captain/config/` first (Docker), then the resolved relative path (host), matching the pattern used by `b8_or_tracker.py` and `b9_session_controller.py`.

```python
# BEFORE
registry_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "session_registry.json"
)
with open(registry_path) as f:
    registry = _json.load(f)

# AFTER
registry = None
for p in [
    Path("/captain/config/session_registry.json"),
    Path(__file__).resolve().parent.parent.parent.parent / "config" / "session_registry.json",
]:
    if p.exists():
        with open(p) as f:
            registry = _json.load(f)
        break
if registry is None:
    raise FileNotFoundError("session_registry.json not found")
```

**Result:** Eliminates the "Failed to load session open time" warning for all assets inside Docker.

### Change 3: `min_distance_to_event` — defensive timezone normalization

Coerces both `reference_time` and `event_time` to ET-aware if naive, preventing any future naive/aware mismatch from any caller.

```python
# ADDED at function entry (after empty-events guard)
from zoneinfo import ZoneInfo
_ET = ZoneInfo("America/New_York")
if reference_time.tzinfo is None:
    reference_time = reference_time.replace(tzinfo=_ET)

# ADDED inside the per-event loop (before subtraction)
if hasattr(event_time, 'tzinfo') and event_time.tzinfo is None:
    event_time = event_time.replace(tzinfo=_ET)
```

**Result:** Even if a caller passes naive datetimes, the function handles them gracefully instead of crashing.

---

## Verification

- Reproduced the exact `TypeError` with old code, confirmed fix resolves it
- CPI at 08:30 correctly computes as -60.0 minutes from 09:30 session open
- 148/148 unit tests pass after fix

## Deploy

```bash
# On tower-1:
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-online
```

No data migration, bootstrap, or config changes required. Fix takes effect at next session open.
