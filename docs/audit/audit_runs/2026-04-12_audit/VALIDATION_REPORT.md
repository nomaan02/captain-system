# Auto-Trade Pipeline Validation Report

**Audit Date:** 2026-04-12
**Audit Type:** Pre-Go-Live Trade Execution Pipeline Validation
**Auditor:** Claude (Nomaan-directed)
**Source of Truth:** ProjectX Gateway API spec (embedded in `.claude/skills/captain-trade-audit/SKILL.md`)
**Overall Status:** PENDING — awaiting fix sessions

---

## Summary

| ID | Severity | Title | Session | Status | Fixed By |
|----|----------|-------|---------|--------|----------|
| C1 | CRITICAL | Token refresh reads `token` instead of `newToken` | Session 1 | RESOLVED | Session 1 (2026-04-12) |
| W1 | WARNING | MGC contract J26 approaching April expiry | Session 3 | RESOLVED | Session 3 (2026-04-12) |
| W2 | WARNING | `AUTO_EXECUTE` parsing inconsistency (orchestrator vs compliance gate) | Session 3 | RESOLVED | Session 3 (2026-04-12) |
| W3 | WARNING | No error checking on SL/TP order placement after entry succeeds | Session 2 | RESOLVED | Session 2 (2026-04-12) |
| W4 | WARNING | No crash recovery for pending Redis Stream messages (PEL) | Session 4 | RESOLVED | Session 4 (2026-04-12) |
| W5 | INFO | `AUTO_EXECUTE=false` in `.env` (expected pre-go-live) | — | ACKNOWLEDGED | — |

---

## Enum Mapping Verification (Passed — No Fixes Required)

All enum values in `shared/topstep_client.py:54-83` match the official ProjectX Gateway API exactly:

| Internal Value | Expected API Value | Actual Code Value | File:Line | Status |
|---|---|---|---|---|
| direction=1 (LONG) entry | type=2, side=0 | `OrderType.MARKET=2`, `OrderSide.BUY=0` | topstep_client.py:55,62 | PASS |
| direction=-1 (SHORT) entry | type=2, side=1 | `OrderType.MARKET=2`, `OrderSide.SELL=1` | topstep_client.py:56,62 | PASS |
| SL order | type=4, stopPrice | `OrderType.STOP=4`, `payload["stopPrice"]` | topstep_client.py:64,228 | PASS |
| TP order | type=1, limitPrice | `OrderType.LIMIT=1`, `payload["limitPrice"]` | topstep_client.py:61,226 | PASS |

---

## Stage Verification Summary (Passed — No Fixes Required)

| Stage | Verdict | Key Evidence |
|-------|---------|--------------|
| Stage 3: Enum Mapping | PASS | All 8 enum classes match official spec verbatim |
| Stage 5: Redis Transport | PASS | XADD/XREADGROUP/XACK chain verified |
| Stage 6: Compliance Gate | PASS | 11/11 rts6_* flags checked, gate before API call |
| Stage 7: Parity Check | PASS | Atomic INCR, correct modular arithmetic, safe fallback |
| Stage 8: 6-Field Boundary | PASS | sanitise_for_api() returns exactly {asset, direction, size, tp, sl, timestamp} |
| Stage 9: GUI WebSocket | PASS | JWT validation, command_ack, error reporting |
| Stage 10: Position Monitor | PASS | TP/SL/Time logic, P&L formula, atomic D16+D23, 3x retry publish |
| SignalR Reconnection | PASS | on_open re-subscribes on both hubs |
| Quote Delta Merge | PASS | QuoteCache overlays non-null values only |

---

## Fix Log

Each session updates the section below with before/after code and verification.

---

### C1: Token Refresh Field Name

**File:** `shared/topstep_client.py`
**Lines:** 128, 133
**Severity:** CRITICAL
**Session:** 1

**Problem:** `validate_token()` reads `resp["token"]` but the `/Auth/validate` API returns the refreshed JWT in a field named `newToken`. After 20 hours of uptime, this causes a `KeyError`, crashing token refresh and losing API access for all subsequent order placements.

**Before:**
```python
def validate_token(self) -> str:
    """Refresh token via /Auth/validate. Returns new token."""
    resp = self._post("/Auth/validate", {}, skip_refresh=True)
    if not resp.get("success") and not resp.get("token"):
        raise AuthenticationError(
            f"Token validation failed: {resp.get('errorCode', 'unknown')}"
        )
    with self._lock:
        self._token = resp["token"]
        self._token_acquired_at = time.time()
    logger.debug("TopstepX token refreshed")
    return self._token
```

**After:**
```python
def validate_token(self) -> str:
    """Refresh token via /Auth/validate. Returns new token."""
    resp = self._post("/Auth/validate", {}, skip_refresh=True)
    if not resp.get("success") and not resp.get("newToken"):
        raise AuthenticationError(
            f"Token validation failed: {resp.get('errorCode', 'unknown')}"
        )
    new_token = resp.get("newToken")
    if new_token is None:
        raise AuthenticationError(
            "Token validation response missing 'newToken' field"
        )
    with self._lock:
        self._token = new_token
        self._token_acquired_at = time.time()
    logger.debug("TopstepX token refreshed")
    return self._token
```

**Verification:**
- [x] `resp["newToken"]` used on line 133 (via `resp.get("newToken")` with defensive check)
- [x] Guard at line 128 checks `resp.get("newToken")`
- [x] Unit test confirms token refresh path (4 tests in `tests/test_topstep_token_refresh.py`)
- [x] No other code reads `resp["token"]` from validate response (grep confirmed; `authenticate()` reads `data["token"]` from `/Auth/loginKey` which is correct)

**Status:** RESOLVED
**Fixed By:** Session 1
**Date:** 2026-04-12

---

### W3: SL/TP Order Failure Detection

**File:** `captain-command/captain_command/blocks/b3_api_adapter.py`
**Lines:** 257-271
**Severity:** WARNING (HIGH risk — unprotected position)
**Session:** 2

**Problem:** After a successful market entry order, the SL and TP orders are placed without checking the response for success. If either fails (rate limit, API error, network), the position is left unprotected with no stop loss and/or no take profit. No alert is sent.

**Before:**
```python
# Stop loss
sl_price = order.get("sl")
if sl_price is not None:
    sl_resp = self._client.place_stop_order(
        self._account_id, contract_id, exit_side, size,
        float(sl_price),
    )
    result["sl_order_id"] = sl_resp.get("orderId")

# Take profit
tp_price = order.get("tp")
if tp_price is not None:
    tp_resp = self._client.place_limit_order(
        self._account_id, contract_id, exit_side, size,
        float(tp_price),
    )
    result["tp_order_id"] = tp_resp.get("orderId")
```

**After:**
```python
# Stop loss
sl_price = order.get("sl")
if sl_price is not None:
    sl_resp = self._client.place_stop_order(
        self._account_id, contract_id, exit_side, size,
        float(sl_price),
    )
    if sl_resp.get("success"):
        result["sl_order_id"] = sl_resp.get("orderId")
    else:
        result["sl_failed"] = True
        result["sl_error"] = sl_resp.get("errorMessage", "SL placement failed")
        logger.critical(
            "STOP LOSS PLACEMENT FAILED -- position %s is UNPROTECTED. Error: %s",
            entry_oid, result["sl_error"],
        )
        # Publish CRITICAL alert via CH_ALERTS
        get_redis_client().publish(CH_ALERTS, json.dumps({
            "priority": "CRITICAL",
            "event_type": "SL_PLACEMENT_FAILED",
            "message": f"STOP LOSS FAILED for entry {entry_oid} -- position is UNPROTECTED.",
            ...
        }))

# Take profit
tp_price = order.get("tp")
if tp_price is not None:
    tp_resp = self._client.place_limit_order(
        self._account_id, contract_id, exit_side, size,
        float(tp_price),
    )
    if tp_resp.get("success"):
        result["tp_order_id"] = tp_resp.get("orderId")
    else:
        result["tp_failed"] = True
        result["tp_error"] = tp_resp.get("errorMessage", "TP placement failed")
        logger.warning(
            "Take profit placement failed for entry %s. Error: %s",
            entry_oid, result["tp_error"],
        )
        # Publish HIGH alert via CH_ALERTS
        get_redis_client().publish(CH_ALERTS, json.dumps({
            "priority": "HIGH",
            "event_type": "TP_PLACEMENT_FAILED",
            "message": f"Take profit failed for entry {entry_oid}.",
            ...
        }))
```

Also added `from shared.redis_client import get_redis_client, CH_ALERTS` to imports.

**Verification:**
- [x] `sl_resp.get("success")` checked after SL placement
- [x] `tp_resp.get("success")` checked after TP placement
- [x] CRITICAL alert sent if SL fails (via `CH_ALERTS` Redis pub/sub)
- [x] HIGH alert sent if TP fails (via `CH_ALERTS` Redis pub/sub)
- [x] Entry order not cancelled on SL failure (position exists, alert operator)
- [x] Return dict includes `sl_failed`/`tp_failed` boolean flags and `sl_error`/`tp_error` messages
- [x] 5 unit tests pass (`tests/test_b3_api_adapter_sltp.py`): SL failure + alert, no entry cancel, TP failure + alert, both fail, happy path

**Status:** RESOLVED
**Fixed By:** Session 2
**Date:** 2026-04-12

---

### W1: MGC Contract Roll

**File:** `config/contract_ids.json`
**Line:** 55
**Severity:** WARNING
**Session:** 3

**Problem:** MGC is mapped to `CON.F.US.MGC.J26` (April 2026). April contracts expire ~April 28. Must be rolled to June (M26) before expiry.

**Before:**
```json
"MGC": {
    "contract_id": "CON.F.US.MGC.J26",
    "name": "MGCJ6",
    "description": "Micro Gold: April 2026",
    "tick_size": 0.1,
    "tick_value": 1.0
}
```

**After:**
```json
"MGC": {
    "contract_id": "CON.F.US.MGC.M26",
    "name": "MGCM6",
    "description": "Micro Gold: June 2026",
    "tick_size": 0.1,
    "tick_value": 1.0
}
```

Also updated header note from `"MGC uses April expiry (J26), all others June (M26)."` to `"All contracts use June expiry (M26)."`.

**Verification:**
- [x] MGC contract_id updated to `CON.F.US.MGC.M26`
- [x] MGC name updated to `MGCM6`
- [x] MGC description updated to reflect June 2026
- [x] No other config files reference J26 (remaining J26 references are in docs/audit files only — historical context, not active config)

**Status:** RESOLVED
**Fixed By:** Session 3
**Date:** 2026-04-12

---

### W2: AUTO_EXECUTE Parsing Inconsistency

**Files:** `captain-command/captain_command/blocks/b12_compliance_gate.py:86`, `captain-command/captain_command/blocks/orchestrator.py:310`
**Severity:** WARNING
**Session:** 3

**Problem:** The orchestrator accepts `("1", "true", "yes")` for `AUTO_EXECUTE`, but the compliance gate only accepts `"true"`. If `.env` has `AUTO_EXECUTE=1` or `AUTO_EXECUTE=yes`, orders silently get `MANUAL_PENDING` status.

**Before:**
```python
# b12_compliance_gate.py:86
auto_execute = os.environ.get("AUTO_EXECUTE", "false").lower() == "true"
```

**After:**
```python
# b12_compliance_gate.py:86-87
# Must match orchestrator.py accepted values: ("1", "true", "yes")
auto_execute = os.environ.get("AUTO_EXECUTE", "false").lower() in ("1", "true", "yes")
```

**Verification:**
- [x] Both paths accept the same set of values: `("1", "true", "yes")`
- [x] `AUTO_EXECUTE=true`, `AUTO_EXECUTE=1`, and `AUTO_EXECUTE=yes` all work end-to-end
- [x] Documented which values are accepted (inline comment referencing orchestrator.py)
- [x] Codebase grep confirmed only two files read `AUTO_EXECUTE` as runtime env var: `orchestrator.py:310` and `b12_compliance_gate.py:87` — both now use identical parsing
- [x] 36 unit tests pass (`tests/test_auto_execute_parsing.py`): truthy values (true/1/yes, case-insensitive), falsy values (false/0/no/empty), and integration tests against `check_compliance_gate()`

**Status:** RESOLVED
**Fixed By:** Session 3
**Date:** 2026-04-12

---

### W4: Redis Stream PEL Recovery

**File:** `shared/redis_client.py`
**Line:** 119
**Severity:** WARNING
**Session:** 4

**Problem:** `read_stream()` always reads with ID `">"` (new messages only). If the process crashes between `xreadgroup` and `xack`, the message enters the Pending Entries List (PEL) but is never re-processed on restart. Signal messages could be lost.

**Before:**
```python
# shared/redis_client.py — only read_stream() existed, always using ID ">"
def read_stream(stream, group, consumer, count=10, block=1000):
    results = client.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block)
    ...

# orchestrator.py — no PEL drain on startup
ensure_consumer_group(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS)
while self.running:
    for msg_id, data in read_stream(...):
        ...
```

**After:**
```python
# shared/redis_client.py — new read_pending_stream() uses ID "0" (non-blocking)
def read_pending_stream(stream, group, consumer, count=100):
    results = client.xreadgroup(group, consumer, {stream: "0"}, count=count)
    # Skips empty-field sentinel entries from already-ACKed messages
    ...

# orchestrator.py — PEL drain before main loop
ensure_consumer_group(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS)
pending = read_pending_stream(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS, "command_1")
for msg_id, data in pending:
    logger.info("Recovering pending signal: %s", msg_id)
    self._handle_signal(data)
    ack_message(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS, msg_id)
if pending:
    logger.info("Recovered %d pending signal(s) from PEL", len(pending))
while self.running:
    for msg_id, data in read_stream(...):
        ...
```

**Verification:**
- [x] New function `read_pending_stream()` exists in `shared/redis_client.py`
- [x] Uses ID `"0"` (not `">"`)
- [x] Does not block (no `block` parameter)
- [x] Called on startup before switching to `">"` reads
- [x] Pending messages are processed and ACKed
- [x] Idempotency note: compliance gate + brokerage API reject duplicate orders; full idempotency is a future improvement
- [x] 8 unit tests pass (`tests/test_redis_pel_recovery.py`)

**Status:** RESOLVED
**Fixed By:** Session 4
**Date:** 2026-04-12

---

## Final Sign-Off

- [ ] All CRITICAL findings resolved
- [ ] All WARNING findings resolved or acknowledged with mitigation
- [ ] Unit tests pass
- [ ] `.env` updated with `AUTO_EXECUTE=true` (when ready)
- [ ] Contract IDs current for active trading month

**Go-Live Decision:** PENDING
**Signed Off By:** —
**Date:** —
