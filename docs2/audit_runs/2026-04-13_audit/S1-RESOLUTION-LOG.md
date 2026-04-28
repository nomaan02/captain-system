# Session 1 Resolution Log — 2026-04-13

**Session**: S1 — Redis Channel Consistency + Quick Config Fixes
**Issues**: C1, C3, C4, C5, H1, H3
**Date**: 2026-04-13
**Status**: COMPLETE

---

## Fix C3 — Contract ID H26 -> M26

**Severity**: CRITICAL
**Root cause**: Expired futures contract defaults (March 2026 H26) would cause TopstepX order rejections.

**Changes**:
| File | Line | Old | New |
|------|------|-----|-----|
| `captain-command/.../b2_gui_data_server.py` | 39 | `CON.F.US.EP.H26` | `CON.F.US.EP.M26` |
| `captain-command/.../b3_api_adapter.py` | 127 | `CON.F.US.EP.H26` | `CON.F.US.EP.M26` |
| `scripts/verify_topstep_integration.py` | 42,73,86 | `CON.F.US.EP.H26` | `CON.F.US.EP.M26` |
| `shared/topstep_client.py` | 193 | `CON.F.US.EP.H26` (docstring) | `CON.F.US.EP.M26` |

**Verification**: `grep -r "H26" captain-command/` returns 0 source matches (only stale .pyc in __pycache__).

**Escalation note**: H26 was also found outside captain-command/ in `scripts/verify_topstep_integration.py` and `shared/topstep_client.py` (docstring). Both were clearly contract ID references that needed updating, so they were fixed without escalation.

---

## Fix H3 — Session Window Minutes 2 -> 5

**Severity**: HIGH
**Root cause**: `b9_session_controller.py` defaults `SESSION_WINDOW_MINUTES` to 2, but `session_registry.json` defines `or_window_minutes: 5` for all sessions. A 2-minute window could miss session opens.

**Changes**:
| File | Line | Old | New |
|------|------|-----|-----|
| `captain-online/.../b9_session_controller.py` | 29 | `os.environ.get("SESSION_WINDOW_MINUTES", "2")` | `os.environ.get("SESSION_WINDOW_MINUTES", "5")` |

**Verification**: Default now matches config. Env var override mechanism preserved. No `.env` or `.env.template` override exists.

---

## Fix C1 — Redis Signal Publication Retry

**Severity**: CRITICAL
**Root cause**: `_publish_signals()` in b6_signal_output.py caught Redis exceptions, logged them, and returned normally. Caller assumed signals were published. No retry, no alert. Signals silently lost.

**Changes**:
| File | Change | Details |
|------|--------|---------|
| `captain-online/.../b6_signal_output.py` | Added `import time` | Line 24 |
| Same | Added `get_redis_client, CH_ALERTS` imports | Line 29 |
| Same | Rewrote `_publish_signals()` | 3-attempt retry, 100ms backoff, re-raises on final failure |
| Same | Added try/except in `run_signal_output()` caller | Catches re-raised exception, logs CRITICAL, publishes alert to CH_ALERTS |

**Retry behavior**: 3 attempts, 100ms sleep between retries. On success: return immediately. On final failure: log ERROR and raise. Caller catches and publishes CRITICAL alert via `CH_ALERTS` channel.

**Alert format**: Matches existing pattern from `b3_api_adapter.py` (fields: notif_id, priority, event_type, message, source, asset, timestamp).

**Verification**: `time.sleep(0.1)` at line 333, `max_attempts = 3` at line 317, CRITICAL alert at line 164-166.

**Note**: Other `publish_to_stream()` calls in b1_core_routing.py (4 calls) lack retry. b7_position_monitor and b7_shadow_monitor already have retry. The b1 calls could benefit from similar treatment in a future session.

---

## Fix C5 — Remove Duplicate HALT/RESUME Pub/Sub Publish

**Severity**: CRITICAL
**Root cause**: b1_core_routing.py line 288 published HALT/RESUME to `CH_COMMANDS` (pub/sub only). Online and Offline read from `STREAM_COMMANDS` and never saw these commands. The initial audit described this as a "duplicate" but investigation revealed HALT/RESUME was pub/sub ONLY — there was no stream path.

**Changes**:
| File | Change | Details |
|------|--------|---------|
| `captain-command/.../b1_core_routing.py` | Changed HALT/RESUME publish | From `redis_client.publish(CH_COMMANDS, json.dumps({...}))` to `publish_to_stream(STREAM_COMMANDS, {...})` |
| Same | Removed unused imports | `get_redis_client`, `get_redis_pubsub`, `CH_COMMANDS` |
| Same | Removed dead local variable | `redis_client = get_redis_client()` |

**Verification**: `grep CH_COMMANDS captain-command/captain_command/blocks/b1_core_routing.py` returns 0 matches. All 5 publish calls now use `publish_to_stream(STREAM_COMMANDS, ...)`.

**Surprise**: The audit described C5 as "duplicate" (published to BOTH stream and pub/sub). Investigation found HALT/RESUME was pub/sub ONLY. The actual bug was worse than reported — HALT/RESUME was invisible to Online/Offline entirely.

---

## Fix C4 — B5 Injection Decisions to Stream

**Severity**: CRITICAL
**Root cause**: `b5_injection_flow.py` published ADOPT_STRATEGY/PARALLEL_TRACK/REJECT_STRATEGY to `CH_COMMANDS` (pub/sub). Offline reads from `STREAM_COMMANDS` and never received injection decisions.

**Changes**:
| File | Change | Details |
|------|--------|---------|
| `captain-command/.../b5_injection_flow.py` | Changed import | From `get_redis_client, CH_COMMANDS` to `publish_to_stream, STREAM_COMMANDS` |
| Same | Changed publish call | From `redis_client.publish(CH_COMMANDS, json.dumps({...}))` to `publish_to_stream(STREAM_COMMANDS, {...})` |
| Same | Removed `get_redis_client()` call | No longer needed |

**Verification**: `grep CH_COMMANDS captain-command/captain_command/blocks/b5_injection_flow.py` returns 0 matches. `publish_to_stream(STREAM_COMMANDS, ...)` confirmed at line 175.

---

## Fix H1 — Command Orchestrator Stream Migration

**Severity**: HIGH
**Root cause**: Command orchestrator read commands via `CH_COMMANDS` pub/sub (non-durable). Online and Offline use `STREAM_COMMANDS` (durable). After C5 migrated HALT/RESUME to stream, Command needed a stream reader or it would miss all commands.

**Approach**: Option A (minimal change) — added STREAM_COMMANDS reader as 4th daemon thread alongside existing pub/sub listener. Pub/sub listener retained for CH_ALERTS and CH_STATUS (backward compat).

**Changes**:
| File | Change | Details |
|------|--------|---------|
| `shared/redis_client.py` | Added `GROUP_COMMAND_COMMANDS = "command_commands"` | Line 84, new consumer group constant |
| `captain-command/.../orchestrator.py` | Added `STREAM_COMMANDS`, `GROUP_COMMAND_COMMANDS` imports | Lines 41-43 |
| Same | Added `_command_stream_reader()` method | Follows `_signal_stream_reader()` pattern: ensure_consumer_group, PEL recovery, blocking read loop, ack, exponential backoff reconnect |
| Same | Added 4th daemon thread `cmd-commands` in `start()` | Line 138 |
| Same | Updated `_redis_listener()` docstring | Notes commands now primarily come via stream |

**Verification**: `grep STREAM_COMMANDS captain-command/captain_command/blocks/orchestrator.py` shows stream reader at lines 219-252. Thread started at line 138.

---

## Test Results

**148 tests passed** in 0.72s (all unit tests excluding integration/stress/lifecycle).

## Grep Verification Summary

| Check | Result |
|-------|--------|
| `CH_COMMANDS` in b1_core_routing.py | 0 matches (clean) |
| `CH_COMMANDS` in b5_injection_flow.py | 0 matches (clean) |
| `publish_to_stream.*STREAM_COMMANDS` in b1_core_routing.py | 5 calls (correct) |
| `STREAM_COMMANDS` in Command orchestrator | Present in new stream reader |
| `H26` in captain-command/ source | 0 matches (only stale .pyc) |
| `SESSION_WINDOW_MINUTES` default | "5" (matches config) |
| Retry logic in b6_signal_output.py | 3 attempts, 100ms backoff |
| CRITICAL alert in b6_signal_output.py | Publishes to CH_ALERTS |

## Files Modified (8 total)

1. `captain-command/captain_command/blocks/b2_gui_data_server.py` (C3)
2. `captain-command/captain_command/blocks/b3_api_adapter.py` (C3)
3. `scripts/verify_topstep_integration.py` (C3)
4. `shared/topstep_client.py` (C3 — docstring only)
5. `captain-online/captain_online/blocks/b9_session_controller.py` (H3)
6. `captain-online/captain_online/blocks/b6_signal_output.py` (C1)
7. `captain-command/captain_command/blocks/b1_core_routing.py` (C5)
8. `captain-command/captain_command/blocks/b5_injection_flow.py` (C4)
9. `shared/redis_client.py` (H1 — new GROUP_COMMAND_COMMANDS constant)
10. `captain-command/captain_command/blocks/orchestrator.py` (H1)
