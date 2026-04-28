# Auto-Trade Pipeline Fix Orchestrator

**Created:** 2026-04-12
**Source Audit:** Pre-Go-Live Trade Execution Pipeline Validation
**Validation Report:** `docs/audit/audit_runs/2026-04-12_audit/VALIDATION_REPORT.md`

---

## Purpose

This document is the master orchestrator for fixing all findings from the 2026-04-12 auto-trade pipeline audit. It contains 5 session prompts. Each session fixes one or more findings and updates the shared VALIDATION_REPORT.md with implementation details, before/after code, and verification.

**Rules for all sessions:**
1. Read the VALIDATION_REPORT.md at `docs/audit/audit_runs/2026-04-12_audit/VALIDATION_REPORT.md` before starting any work.
2. After completing the fix, update the VALIDATION_REPORT.md with: before code, after code, all verification checkboxes checked, status set to RESOLVED, fixed-by and date filled in.
3. Run relevant tests after each fix. If no test exists, write one.
4. Do NOT touch any file outside the scope of the assigned finding(s).
5. Do NOT change enum values, API URLs, or anything verified as PASS in the audit.

---

## Finding Summary

| ID | Severity | Title | Files | Session |
|----|----------|-------|-------|---------|
| C1 | CRITICAL | Token refresh reads `token` instead of `newToken` | `shared/topstep_client.py:128,133` | Session 1 |
| W3 | WARNING (HIGH) | No error checking on SL/TP order placement | `captain-command/.../b3_api_adapter.py:257-271` | Session 2 |
| W1 | WARNING | MGC contract J26 approaching April expiry | `config/contract_ids.json:55` | Session 3 |
| W2 | WARNING | `AUTO_EXECUTE` parsing inconsistency | `b12_compliance_gate.py:86`, `orchestrator.py:310` | Session 3 |
| W4 | WARNING | No crash recovery for pending Redis Stream messages | `shared/redis_client.py:119` | Session 4 |
| W5 | INFO | `AUTO_EXECUTE=false` in `.env` | `.env` | N/A (acknowledged) |

---

## Session 1: Fix C1 — Token Refresh Field Name (CRITICAL)

### Context

This is the single most dangerous bug in the pipeline. It WILL crash the system after approximately 20 hours of uptime.

The TopstepX `/Auth/validate` endpoint returns the refreshed JWT in a field named `newToken`, not `token`. The current code reads `resp["token"]`, which will raise a `KeyError` when the token refresh is attempted. Once this fails, the system loses API access and all subsequent order placements will fail with authentication errors.

### Prompt

```
You are fixing a CRITICAL bug in the Captain System auto-trade pipeline. This is the highest-priority fix — the system cannot go live until this is resolved.

## Bug: C1 — Token Refresh Field Name

**File:** `shared/topstep_client.py`
**Lines:** 128, 133

**Problem:** The `validate_token()` method reads `resp["token"]` but the TopstepX `/Auth/validate` API returns the refreshed JWT in a field named `newToken`. After approximately 20 hours of uptime (when the token needs its first refresh), this causes a `KeyError`, crashing token refresh and losing API access for all subsequent order placements.

**Current buggy code (lines 125-137):**

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

**What to fix:**
1. Line 128: Change `resp.get("token")` to `resp.get("newToken")` in the guard check.
2. Line 133: Change `resp["token"]` to `resp["newToken"]`.
3. Add a defensive check: if `resp.get("newToken")` is None/missing even on success, raise `AuthenticationError` with a clear message rather than proceeding with a None token.

**Official API spec for reference:**
- Endpoint: `POST https://api.topstepx.com/api/Auth/validate`
- Header: `Authorization: Bearer <current_JWT>`
- Response: `{"success": true, "errorCode": 0, "errorMessage": null, "newToken": "<new_JWT>"}`
- The field is `newToken`, NOT `token`.

**Verification checklist:**
- [ ] `resp["newToken"]` used on line 133 (not `resp["token"]`)
- [ ] Guard at line 128 checks `resp.get("newToken")`
- [ ] If `newToken` is missing from a successful response, `AuthenticationError` is raised
- [ ] No other code in this file reads `resp["token"]` from a validate response
- [ ] Grep the entire codebase for `resp["token"]` or `resp.get("token")` to ensure no other location has this bug
- [ ] Write a unit test that mocks the validate response with `{"success": true, "newToken": "abc123"}` and confirms the token is updated
- [ ] Write a unit test that confirms `{"success": true}` (missing newToken) raises AuthenticationError

**After fixing, update the VALIDATION_REPORT.md:**
1. Open `docs/audit/audit_runs/2026-04-12_audit/VALIDATION_REPORT.md`
2. In the `### C1: Token Refresh Field Name` section:
   - Fill in the **Before:** block with the old code
   - Fill in the **After:** block with your new code
   - Check all verification checkboxes
   - Set **Status:** to `RESOLVED`
   - Set **Fixed By:** to your session identifier
   - Set **Date:** to today's date (2026-04-12)
3. In the summary table at the top, update C1's Status to `RESOLVED`

Do NOT touch any other file except `shared/topstep_client.py`, relevant test files, and the VALIDATION_REPORT.md.
```

---

## Session 2: Fix W3 — SL/TP Order Failure Detection (WARNING — HIGH RISK)

### Context

After a successful market entry order, the system places SL (stop loss) and TP (take profit) orders as separate API calls. Currently, neither response is checked for success. If SL placement fails (rate limit, API error, network timeout), the position is left completely unprotected — no stop loss means unlimited downside risk. No alert is sent to the operator.

This is classified as WARNING but carries HIGH operational risk because an unprotected position in live trading is extremely dangerous.

### Prompt

```
You are fixing a WARNING (HIGH RISK) bug in the Captain System auto-trade pipeline. This addresses unprotected positions when SL/TP order placement fails.

## Bug: W3 — SL/TP Order Failure Detection

**File:** `captain-command/captain_command/blocks/b3_api_adapter.py`
**Lines:** 257-280

**Problem:** After a successful market entry order, the SL and TP orders are placed without checking the API response for success. If either call fails (HTTP 429 rate limit, API error, network timeout), the position is left unprotected with no stop loss and/or no take profit. No alert is sent to the operator.

**Current code (lines 256-280):**

```python
            result = {
                "success": True,
                "entry_order_id": entry_oid,
                "sl_order_id": None,
                "tp_order_id": None,
            }

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

**What to fix:**
1. After `sl_resp` is received, check `sl_resp.get("success")`. If `False` or missing:
   - Set `result["sl_failed"] = True`
   - Set `result["sl_error"] = sl_resp.get("errorMessage", "SL placement failed")`
   - Send a CRITICAL alert via `publish_to_stream(STREAM_COMMANDS, {...})` or the existing alert mechanism — an unprotected position MUST alert the operator immediately
   - Log at CRITICAL level: "STOP LOSS PLACEMENT FAILED — position {entry_oid} is UNPROTECTED"
   - Do NOT cancel the entry order (the position already exists in the market, cancelling the order won't close it)

2. After `tp_resp` is received, check `tp_resp.get("success")`. If `False` or missing:
   - Set `result["tp_failed"] = True`
   - Set `result["tp_error"] = tp_resp.get("errorMessage", "TP placement failed")`
   - Send a WARNING alert — less critical than SL failure but still needs operator attention
   - Log at WARNING level

3. The `result` dict returned to the caller must include the failure status so upstream code (orchestrator) can react.

**Important constraints:**
- Do NOT cancel the entry order if SL fails. The entry is already filled — you can't "unfill" a market order. The operator must manually manage the position.
- Do NOT retry SL/TP here — the `place_stop_order` / `place_limit_order` methods already have retry logic with exponential backoff for 429s. If it still fails after retries, it's a real failure.
- The alert mechanism exists in `shared/redis_client.py` — use `publish_to_stream` with `STREAM_COMMANDS` or `CH_ALERTS` channel. Check how alerts are published elsewhere in the codebase for the correct format.

**Verification checklist:**
- [ ] `sl_resp.get("success")` is checked after SL placement
- [ ] `tp_resp.get("success")` is checked after TP placement
- [ ] CRITICAL alert sent if SL fails (via existing alert mechanism)
- [ ] WARNING alert sent if TP fails
- [ ] Entry order is NOT cancelled on SL failure
- [ ] Return dict includes `sl_failed` / `tp_failed` boolean flags
- [ ] Return dict includes error messages from failed responses
- [ ] Write a unit test: mock SL placement returning `{"success": false, "errorMessage": "rate limit"}` and verify alert is sent and result dict has `sl_failed=True`
- [ ] Write a unit test: mock successful entry + successful SL + failed TP and verify result dict is correct

**After fixing, update the VALIDATION_REPORT.md:**
1. Open `docs/audit/audit_runs/2026-04-12_audit/VALIDATION_REPORT.md`
2. In the `### W3: SL/TP Order Failure Detection` section:
   - Fill in the **Before:** block with the old code
   - Fill in the **After:** block with your new code
   - Check all verification checkboxes
   - Set **Status:** to `RESOLVED`
   - Set **Fixed By:** to your session identifier
   - Set **Date:** to today's date
3. In the summary table at the top, update W3's Status to `RESOLVED`

Do NOT touch any file outside `captain-command/captain_command/blocks/b3_api_adapter.py`, relevant test files, and the VALIDATION_REPORT.md.
```

---

## Session 3: Fix W1 + W2 — MGC Contract Roll + AUTO_EXECUTE Parsing (Configuration Fixes)

### Context

Two configuration-level warnings bundled together because they are low-risk, non-overlapping changes.

**W1:** MGC is mapped to the April 2026 contract (`CON.F.US.MGC.J26`). April contracts expire around April 28. This must be rolled to the June contract (`CON.F.US.MGC.M26`) before expiry.

**W2:** The orchestrator accepts `("1", "true", "yes")` for `AUTO_EXECUTE`, but the compliance gate only accepts `"true"`. If someone sets `AUTO_EXECUTE=1` or `AUTO_EXECUTE=yes`, the orchestrator thinks auto-execute is on, but the compliance gate blocks it with `MANUAL` mode. This is a silent inconsistency that would be very confusing to debug.

### Prompt

```
You are fixing two WARNING-level findings in the Captain System auto-trade pipeline. These are configuration-level fixes that can be done together.

## Bug W1: MGC Contract Roll

**File:** `config/contract_ids.json`
**Line:** 55

**Problem:** MGC is mapped to `CON.F.US.MGC.J26` (April 2026). April contracts expire approximately April 28, 2026. This must be rolled to the June 2026 contract before expiry.

**Current code:**
```json
"MGC": {
    "contract_id": "CON.F.US.MGC.J26",
    "name": "MGCJ6",
    "description": "Micro Gold: April 2026",
    "tick_size": 0.1,
    "tick_value": 1.0
},
```

**What to fix:**
1. Change `contract_id` from `CON.F.US.MGC.J26` to `CON.F.US.MGC.M26`
2. Change `name` from `MGCJ6` to `MGCM6`
3. Change `description` from `"Micro Gold: April 2026"` to `"Micro Gold: June 2026"`
4. Leave `tick_size` and `tick_value` unchanged (these are contract-level constants, not month-specific)

**Contract month codes for reference:**
- H = March, J = April, K = May, M = June, N = July, Q = August, U = September, V = October, X = November, Z = December

**Verification:**
- [ ] MGC contract_id is `CON.F.US.MGC.M26`
- [ ] MGC name is `MGCM6`
- [ ] MGC description says "June 2026"
- [ ] Grep the entire codebase for `J26` — no other file should reference the April contract. If any do, flag them but do NOT change them (they may be in test fixtures or historical data).
- [ ] All other contracts in `contract_ids.json` are already on M26 (June) or later — verify this.

---

## Bug W2: AUTO_EXECUTE Parsing Inconsistency

**Files:**
- `captain-command/captain_command/blocks/orchestrator.py` line 310
- `captain-command/captain_command/blocks/b12_compliance_gate.py` line 86

**Problem:** The orchestrator and the compliance gate parse `AUTO_EXECUTE` differently:

Orchestrator (line 310):
```python
auto_execute = os.environ.get("AUTO_EXECUTE", "").lower() in ("1", "true", "yes")
```
Accepts: `"1"`, `"true"`, `"yes"`

Compliance gate (line 86):
```python
auto_execute = os.environ.get("AUTO_EXECUTE", "false").lower() == "true"
```
Accepts: only `"true"`

If `.env` has `AUTO_EXECUTE=1` or `AUTO_EXECUTE=yes`, the orchestrator thinks auto-execute is enabled, but the compliance gate returns `MANUAL` mode, silently blocking all trades. This is extremely confusing to debug.

**What to fix:**
Both paths must accept the same set of values. Standardize on the orchestrator's broader set: `("1", "true", "yes")`.

1. In `b12_compliance_gate.py` line 86, change:
   ```python
   auto_execute = os.environ.get("AUTO_EXECUTE", "false").lower() == "true"
   ```
   to:
   ```python
   auto_execute = os.environ.get("AUTO_EXECUTE", "false").lower() in ("1", "true", "yes")
   ```

2. Do NOT change the orchestrator — it already has the correct, broader set.

3. Add a brief inline comment on the compliance gate line referencing the orchestrator:
   ```python
   # Must match orchestrator.py accepted values: ("1", "true", "yes")
   auto_execute = os.environ.get("AUTO_EXECUTE", "false").lower() in ("1", "true", "yes")
   ```

**Verification:**
- [ ] Both files accept `("1", "true", "yes")` as truthy values for AUTO_EXECUTE
- [ ] Grep the entire codebase for `AUTO_EXECUTE` — identify every location that reads this env var and confirm they all use the same parsing logic
- [ ] Write a unit test (or add to existing) that verifies `AUTO_EXECUTE=1` passes both the orchestrator check and the compliance gate check
- [ ] Verify `AUTO_EXECUTE=false`, `AUTO_EXECUTE=no`, and `AUTO_EXECUTE=0` all result in MANUAL mode in both paths

---

**After fixing BOTH, update the VALIDATION_REPORT.md:**
1. Open `docs/audit/audit_runs/2026-04-12_audit/VALIDATION_REPORT.md`
2. In `### W1: MGC Contract Roll`:
   - Fill in Before/After with the JSON changes
   - Check all verification checkboxes
   - Set Status to RESOLVED, fill Fixed By and Date
3. In `### W2: AUTO_EXECUTE Parsing Inconsistency`:
   - Fill in Before/After with the Python code changes
   - Check all verification checkboxes
   - Set Status to RESOLVED, fill Fixed By and Date
4. Update the summary table for both W1 and W2

Do NOT touch any files outside `config/contract_ids.json`, `captain-command/captain_command/blocks/b12_compliance_gate.py`, relevant test files, and the VALIDATION_REPORT.md.
```

---

## Session 4: Fix W4 — Redis Stream PEL Recovery

### Context

Redis Streams use a Pending Entries List (PEL) to track messages that have been delivered to a consumer but not yet acknowledged (ACKed). If the process crashes between `XREADGROUP` (receiving a message) and `XACK` (acknowledging it), the message sits in the PEL. On restart, the current code always reads with ID `">"` which means "only new messages" — it never re-reads the pending entries. This means signal messages can be silently lost on crash.

This is a resilience issue. In normal operation with no crashes, there is no impact. But in a crash scenario during signal processing, a trade signal could be dropped.

### Prompt

```
You are fixing a WARNING-level resilience issue in the Captain System's Redis Stream transport layer. This addresses crash recovery for unacknowledged messages.

## Bug: W4 — Redis Stream PEL (Pending Entries List) Recovery

**File:** `shared/redis_client.py`
**Lines:** 110-131

**Problem:** The `read_stream()` function always reads with ID `">"`, which means "only new messages not yet delivered to this consumer group." If the process crashes between receiving a message via `XREADGROUP` and acknowledging it via `XACK`, the message enters the PEL but is never re-processed on restart. Signal messages could be silently lost.

**Current code:**
```python
def read_stream(stream: str, group: str, consumer: str,
                count: int = 10, block: int = 1000) -> list:
    """Read new messages from a stream consumer group.

    Returns list of (message_id, data_dict) tuples.
    block: milliseconds to wait for new messages (1000 = 1s).
    """
    client = get_redis_client()
    results = client.xreadgroup(
        group, consumer, {stream: ">"}, count=count, block=block,
    )
    if not results:
        return []
    # results = [(stream_name, [(msg_id, {field: value}), ...])]
    messages = []
    for msg_id, fields in results[0][1]:
        try:
            data = json.loads(fields.get("payload", "{}"))
        except (json.JSONDecodeError, TypeError):
            data = {}
        messages.append((msg_id, data))
    return messages
```

**What to fix:**

Add a new function `read_pending()` (or `claim_pending()`) that reads messages with ID `"0"` instead of `">"`. When you pass `"0"` to XREADGROUP, Redis returns all pending messages for that consumer that haven't been ACKed yet.

1. Add a new function `read_pending_stream()`:
```python
def read_pending_stream(stream: str, group: str, consumer: str,
                        count: int = 100) -> list:
    """Read pending (unacknowledged) messages from a stream consumer group.

    Called on startup to recover messages that were delivered but not ACKed
    before a crash. Uses ID "0" which returns all pending entries for this
    consumer. Does NOT block — returns immediately if no pending messages.

    Returns list of (message_id, data_dict) tuples.
    """
    client = get_redis_client()
    results = client.xreadgroup(
        group, consumer, {stream: "0"}, count=count,
    )
    if not results:
        return []
    messages = []
    for msg_id, fields in results[0][1]:
        try:
            data = json.loads(fields.get("payload", "{}"))
        except (json.JSONDecodeError, TypeError):
            data = {}
        messages.append((msg_id, data))
    return messages
```

2. Key design decisions:
   - `read_pending_stream()` does NOT block (no `block` parameter) — it returns immediately
   - It uses a higher default `count` (100) since we want to drain all pending messages at startup
   - The caller (orchestrator) is responsible for calling this once at startup, processing and ACKing each message, then switching to the normal `read_stream()` loop with `">"`

3. Now find where the consumer startup happens. Check:
   - `captain-command/captain_command/blocks/orchestrator.py` — look for the `_signal_stream_reader()` method that reads from `STREAM_SIGNALS`. This is the primary consumer that needs PEL recovery.
   - At the START of the stream reader loop (before entering the `while True` loop), add a PEL drain phase:
     ```python
     # Drain pending messages from previous crash (PEL recovery)
     pending = read_pending_stream(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS, consumer_name)
     for msg_id, data in pending:
         logger.info("Recovering pending signal: %s", msg_id)
         self._handle_signal(data)
         ack_message(STREAM_SIGNALS, GROUP_COMMAND_SIGNALS, msg_id)
     if pending:
         logger.info("Recovered %d pending signals from PEL", len(pending))
     ```

4. Consider idempotency: the signal might have been partially processed before the crash. Check if `_handle_signal()` is naturally idempotent (e.g., does it check for duplicate trade IDs?). If not, add a comment noting this as a future improvement, but do NOT block this fix on implementing full idempotency — the risk of re-processing a signal (worst case: duplicate trade attempt, which the compliance gate or API would likely reject) is much lower than the risk of losing a signal entirely.

**Verification checklist:**
- [ ] New function `read_pending_stream()` exists in `shared/redis_client.py`
- [ ] It uses ID `"0"` (not `">"`)
- [ ] It does NOT block (no `block` parameter)
- [ ] It is called on startup in the orchestrator's stream reader, BEFORE the main `while True` loop
- [ ] Each recovered message is processed and then ACKed
- [ ] A log line indicates how many pending messages were recovered
- [ ] Write a unit test: publish a message to a stream, XREADGROUP it (creating a PEL entry), do NOT XACK it, then call `read_pending_stream()` and verify the message is returned
- [ ] Write a unit test: call `read_pending_stream()` when PEL is empty, verify empty list returned

**After fixing, update the VALIDATION_REPORT.md:**
1. Open `docs/audit/audit_runs/2026-04-12_audit/VALIDATION_REPORT.md`
2. In `### W4: Redis Stream PEL Recovery`:
   - Fill in Before/After blocks
   - Check all verification checkboxes
   - Set Status to RESOLVED, fill Fixed By and Date
3. Update the summary table for W4

Files you may touch: `shared/redis_client.py`, `captain-command/captain_command/blocks/orchestrator.py` (startup section only), relevant test files, and the VALIDATION_REPORT.md.
```

---

## Session 5: Validation Sweep — Final Verification and Sign-Off

### Context

This session runs AFTER Sessions 1-4 are all complete. Its purpose is to verify every fix, run the full test suite, and sign off the VALIDATION_REPORT.md.

### Prompt

```
You are the final validation session for the Captain System auto-trade pipeline audit (2026-04-12). Sessions 1-4 have fixed the following findings:

- C1: Token refresh field name (`shared/topstep_client.py`)
- W3: SL/TP order failure detection (`captain-command/.../b3_api_adapter.py`)
- W1: MGC contract roll (`config/contract_ids.json`)
- W2: AUTO_EXECUTE parsing consistency (`b12_compliance_gate.py`)
- W4: Redis Stream PEL recovery (`shared/redis_client.py`, `orchestrator.py`)

Your job is to independently verify every fix and sign off the validation report. Do NOT trust that the previous sessions did their job correctly — verify everything yourself.

## Step 1: Read the Validation Report

Read `docs/audit/audit_runs/2026-04-12_audit/VALIDATION_REPORT.md` in full. Confirm all 5 findings show Status: RESOLVED with filled-in before/after code.

## Step 2: Verify C1 — Token Refresh

1. Read `shared/topstep_client.py` and find the `validate_token()` method
2. Confirm it reads `resp["newToken"]` (not `resp["token"]`)
3. Confirm the guard check uses `resp.get("newToken")`
4. Grep the entire codebase for `resp["token"]` — it should NOT appear in any validate-related context
5. Run the C1 unit tests

## Step 3: Verify W3 — SL/TP Failure Detection

1. Read `captain-command/captain_command/blocks/b3_api_adapter.py` and find the SL/TP placement section
2. Confirm `sl_resp.get("success")` is checked
3. Confirm `tp_resp.get("success")` is checked
4. Confirm alerts are sent on failure
5. Confirm the result dict includes failure flags
6. Run the W3 unit tests

## Step 4: Verify W1 — MGC Contract

1. Read `config/contract_ids.json`
2. Confirm MGC uses `CON.F.US.MGC.M26`, name `MGCM6`, description "June 2026"
3. Grep for `J26` — should not appear in any active configuration (historical/test data is OK)

## Step 5: Verify W2 — AUTO_EXECUTE Parsing

1. Read `b12_compliance_gate.py` line 86 — confirm it accepts `("1", "true", "yes")`
2. Read `orchestrator.py` line 310 — confirm it accepts `("1", "true", "yes")`
3. Grep the entire codebase for `AUTO_EXECUTE` — every location that reads this env var must use the same parsing logic
4. Run the W2 unit tests

## Step 6: Verify W4 — Redis PEL Recovery

1. Read `shared/redis_client.py` — confirm `read_pending_stream()` exists and uses ID `"0"`
2. Read `captain-command/captain_command/blocks/orchestrator.py` — confirm PEL drain runs at startup before the main loop
3. Run the W4 unit tests

## Step 7: Run Full Test Suite

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/ \
  --ignore=tests/test_integration_e2e.py \
  --ignore=tests/test_pipeline_e2e.py \
  --ignore=tests/test_pseudotrader_account.py \
  --ignore=tests/test_offline_feedback.py \
  --ignore=tests/test_stress.py \
  --ignore=tests/test_account_lifecycle.py \
  -v
```

All tests must pass. If any test fails, investigate whether it's related to the audit fixes or a pre-existing issue. Pre-existing failures should be noted but do not block sign-off.

## Step 8: Update the Validation Report

1. In the **Final Sign-Off** section of VALIDATION_REPORT.md:
   - Check: `[x] All CRITICAL findings resolved`
   - Check: `[x] All WARNING findings resolved or acknowledged with mitigation`
   - Check: `[x] Unit tests pass` (note any pre-existing failures)
   - Note: `AUTO_EXECUTE=false` in `.env` is expected pre-go-live (W5 acknowledged)
   - Note: Contract IDs current for active trading month (after W1 fix)
   - Set **Go-Live Decision:** to `APPROVED` (if all checks pass) or `BLOCKED` (with reason)
   - Set **Signed Off By:** to your session identifier
   - Set **Date:** to today's date

2. Update the **Overall Status** at the top of the report from `PENDING` to `PASS` or `PASS WITH WARNINGS`.

If ANY fix is incomplete, incorrect, or introduces a regression: set Go-Live Decision to BLOCKED, document exactly what is wrong, and specify which session needs to be re-run.
```

---

## Execution Order

```
Session 1 (C1 — CRITICAL token fix)     ← Run FIRST, alone
    |
Session 2 (W3 — SL/TP detection)        ← Can run after Session 1
    |
Session 3 (W1 + W2 — config fixes)      ← Can run in parallel with Session 2
    |
Session 4 (W4 — Redis PEL recovery)     ← Can run in parallel with Sessions 2-3
    |
Session 5 (Validation sweep)            ← Run LAST, after all others complete
```

Sessions 2, 3, and 4 are independent of each other and can run in parallel after Session 1. Session 5 must run last.

---

## File Ownership per Session

| Session | May Modify | Must Update |
|---------|-----------|-------------|
| 1 | `shared/topstep_client.py`, `tests/test_topstep_client.py` (or new) | VALIDATION_REPORT.md |
| 2 | `captain-command/.../b3_api_adapter.py`, `tests/test_b3_*.py` (or new) | VALIDATION_REPORT.md |
| 3 | `config/contract_ids.json`, `captain-command/.../b12_compliance_gate.py`, `tests/test_b12_*.py` (or new) | VALIDATION_REPORT.md |
| 4 | `shared/redis_client.py`, `captain-command/.../orchestrator.py`, `tests/test_redis_*.py` (or new) | VALIDATION_REPORT.md |
| 5 | VALIDATION_REPORT.md only (read-only verification of all other files) | VALIDATION_REPORT.md |

No two sessions modify the same source file. This eliminates merge conflicts.
