# Issue 4 — UserStream Returns All Nones: Root Cause Audit

**Date:** 2026-05-06
**Audit author:** Cursor agent (Opus 4.7) for Nomaan
**Trigger:** NY-Open 2026-05-05 — every TopstepX User Hub event delivered to captain-online produced `id=None`, `balance=None`, `status=None`, `type=None`, `contractId=None`, `size=0`, `averagePrice=None`, `price=None`, `profitAndLoss=None`, `fees=None`.
**Status:** READ-ONLY audit. No code changes have been made. This document IS the diagnosis + remediation plan; execution is gated on Nomaan's approval.

---

## TL;DR

**The TopstepX SignalR User Hub delivers each event payload wrapped in a two-key envelope:**

```js
{
  "data": { /* the actual entity (id, balance, contractId, …) */ },
  "action": 0   // 0 = create, 1 = update, 2 = delete
}
```

Captain's `shared/topstep_stream.py` was written against the *short-form* example payloads in the public Gateway docs (`gateway.docs.projectx.com/docs/realtime/`), which show **only the inner entity** and never mention the envelope. As a result:

1. `_extract_dict()` correctly extracts the **outer envelope** dict from the SignalR `arguments` list.
2. `_normalize_hub_payload()` fold-cases its **outer** keys (`data`, `action`) — both already camelCase, so no-op.
3. The inner entity at `envelope["data"]` is **never unwrapped**, so the four downstream `_on_*_update` callbacks in `captain-online/.../main.py` read `data.get("balance")`, `data.get("id")`, `data.get("contractId")`, etc. on the **wrapper**, where those keys do not exist → all `None`.

**The fix is structural and tiny** (≈10 lines in `_normalize_hub_payload`): detect the `{data, action}` envelope and unwrap it before normalization. There is also a **secondary risk** that needs verification at deploy time: TopstepX may be sending the *Admin/S2F-product* schema (`positionSize`, `tradingAccountId`, `pnl`, `executedPrice`) rather than the Gateway-product schema (`size`, `accountId`, `profitAndLoss`, `filledPrice`) — see §4 below.

The remediation plan in §6 is two-stage: **(A)** fix the envelope unwrap and ship a 1-shot diagnostic logger so we can capture an actual broker payload, then **(B)** based on what we see, either declare done or add field-name aliasing.

---

## 1. The exact failure path

### 1.1 What captain-online logs

Every event arrives, the handler fires, the dict-typed guard passes, and the callback runs `data.get("…")` for known field names, all of which return `None`:

```log
captain-online-1  | [ONLINE] 2026-05-05 09:38:20,944 INFO __main__:
    UserStream ACCOUNT: balance=None
captain-online-1  | [ONLINE] 2026-05-05 09:38:22,275 INFO __main__:
    UserStream ORDER: id=None status=None type=None
captain-online-1  | [ONLINE] 2026-05-05 09:38:22,276 INFO __main__:
    UserStream TRADE: price=None pnl=None fees=None
captain-online-1  | [ONLINE] 2026-05-05 09:38:22,277 INFO __main__:
    UserStream TRADE: price=None pnl=None fees=None
captain-online-1  | [ONLINE] 2026-05-05 09:38:22,280 INFO __main__:
    UserStream POSITION: contract=None size=0 avgPrice=None
captain-online-1  | [ONLINE] 2026-05-05 09:38:22,287 INFO __main__:
    UserStream ACCOUNT: balance=None
```

### 1.2 The ten-line code path

Pysignalr → captain `_async_handle_*` → `_handle_*` → user `_on_*_update`:

`shared/topstep_stream.py:717-735` (handlers) +
`shared/topstep_stream.py:739-767` (`_handle_*`) +
`shared/topstep_stream.py:38-72` (`_extract_dict`, `_normalize_hub_payload`) +
`captain-online/captain_online/main.py:155-232` (the four `_on_*_update` user callbacks).

```717:735:shared/topstep_stream.py
    async def _async_handle_account(self, *args) -> None:
        data = args[0] if args else None
        if data is not None:
            self._handle_account(data)
```

```739:746:shared/topstep_stream.py
    def _handle_account(self, data) -> None:
        data = _normalize_hub_payload(data)
        if isinstance(data, dict):
            with self._lock:
                self._account_cache = data
        if self._on_account_update:
            self._on_account_update(data)
```

```38:72:shared/topstep_stream.py
def _extract_dict(data) -> Any:
    """Extract a dict from SignalR message arguments (may be list of mixed types)."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                return item
        for item in data:
            if isinstance(item, str):
                try:
                    parsed = _json.loads(item)
                    if isinstance(parsed, dict):
                        return parsed
                except (ValueError, TypeError):
                    pass
    return data


def _normalize_hub_payload(data) -> Any:
    """Fold PascalCase Gateway keys (Id, AccountId) to camelCase for Python handlers."""
    extracted = _extract_dict(data)
    if not isinstance(extracted, dict):
        return extracted
    out: dict[str, Any] = {}
    for k, v in extracted.items():
        nk = k
        if len(k) >= 2 and k[0].isupper() and k[1].islower():
            nk = k[0].lower() + k[1:]
        out[nk] = v
    return out
```

```224:232:captain-online/captain_online/main.py
        def _on_account_update(data):
            if not isinstance(data, dict):
                return
            logger.info("UserStream ACCOUNT: balance=%s", data.get("balance"))
            try:
                redis.publish(CH_USER_EVENTS, json.dumps(
                    {"type": "account_update", "data": data}, default=str))
            except Exception as exc:
                logger.error("Failed to publish account event: %s", exc)
```

### 1.3 What pysignalr passes the handler

`pysignalr/client.py:347` calls each registered `on()` callback with the **entire** SignalR `arguments` list passed as a **single positional arg**:

```347:347:.venv/lib/python3.12/site-packages/pysignalr/client.py
                res = await callback(message.arguments)
```

So if TopstepX puts the wrapped envelope in `arguments[0]`:

```json
{
  "type": 1,
  "target": "GatewayUserAccount",
  "arguments": [
    { "data": { "id": 202, "balance": 147186.78, … }, "action": 0 }
  ]
}
```

Then `_async_handle_account` receives `args = ([{ "data": {…}, "action": 0 }],)`, `args[0] = [{ "data": {…}, "action": 0 }]`, `_extract_dict(args[0])` returns the **envelope dict** `{ "data": {…}, "action": 0 }`, and the four `data.get("balance" | "id" | "status" | …)` calls in main.py all read keys that exist only at `envelope["data"][…]` — never in the envelope itself. Hence every field is `None`, exactly as logged.

(This is also why the position cache key fall-out is silent: in `_handle_position`, `pos_id = str(data.get("id", ""))` becomes `""` — the cache mutation is a no-op rather than crashing.)

---

## 2. Source of truth for the wire format

### 2.1 The "Gateway-product" docs (gateway.docs.projectx.com)

The public TopstepX-facing Gateway docs at `https://gateway.docs.projectx.com/docs/realtime/` show this **inner**-only example payload for `GatewayUserAccount`:

```js
{ id: 123, name: "Main Trading Account", balance: 10000.50,
  canTrade: true, isVisible: true, simulated: false }
```

…and a JS handler:

```js
rtcConnection.on('GatewayUserAccount', (data) => { console.log(data); });
```

The captain code's field-name table lines up exactly with this product (`id`, `balance`, `contractId`, `averagePrice`, `size`, `status`, `type`, `price`, `profitAndLoss`, `fees`, `accountId`, `filledPrice`). **No envelope is mentioned.** This is the doc the captain code was written against — and the doc that's out-of-step with the actual wire format.

### 2.2 The "Admin/S2F-product" docs (admin.docs.projectx.com)

The internal/admin ProjectX docs at `https://admin.docs.projectx.com/docs/real-time-data/signalR-websocket/account-updates/` (and the `…/order-updates/`, `…/position-updates/`, `…/trade-updates/` siblings) show the **same SignalR User Hub events**, but with the envelope made explicit. Verbatim from the live Account Updates page:

```js
{
  "data": {
    "id": 202,
    "accountName": "TEST_ACCOUNT",
    "nickname": null,
    "balance": 147186.78,
    "unrealizedPnl": -840.00,
    "highestUnrealizedBalance": 151014.10,
    "highestRealizedBalance": 150371.90,
    "realizedDayPnl": -2454.20,
    "status": 0,
    "lockoutExpiration": null,
    "lockoutReason": null,
    "dailyTradeLimit": null,
    "weeklyTradeLimit": null,
    "latestTradeDateTime": null,
    "ineligible": false,
    "maximumLossLimit": 145714.50,
    "dailyLossLimit": 3000.00,
    "updatedAt": "2025-02-25T14:41:35.2143684+00:00"
  },
  "action": 0   //  0 = create, 1 = update, 2 = delete/remove
}
```

Position Updates, same envelope:

```js
{
  "data": {
    "id": 4231,
    "symbolId": "F.US.BP6",
    "openPnl": -18.75,
    "positionSize": 0,
    "averagePrice": 1.2665,
    "contract": "6BH5",
    "contractId": null,
    "contractGroup": "/6B",
    "tradingAccountId": 233,
    …
  },
  "action": 0
}
```

Order Updates, same envelope (note the field **executedPrice**, not `filledPrice`, and **positionSize**, not `size`):

```js
{
  "data": {
    "id": 19900,
    "limitPrice": 21381.25,
    "stopPrice": null,
    "executedPrice": null,
    "contractGroup": "/NQ",
    "contract": "NQH5",
    "positionSize": -1,
    "type": 1,
    "status": 6,
    "timestamp": "2025-02-25T14:40:04.2256702+00:00",
    "createdAt": "2025-02-25T14:40:04.1823356+00:00",
    "filledAt": null,
    "cancelledAt": null,
    "tradingAccountId": 202
  },
  "action": 0
}
```

Trade Updates, same envelope (note **lots**, not `size`, and **pnl**, not `profitAndLoss`):

```js
{
  "data": {
    "id": 8508,
    "contractGroupId": "F.US.MES",
    …
    "price": 5975.500000000,
    "fees": 0.3700,
    "action": 1,
    "lots": 1,
    "status": 1,
    "pnl": 0.000000000,
    "tradingAccountId": 213,
    "orderId": 14117,
    "enteredAt": "2025-01-15T17:35:58.566225+00:00",
    "exitedAt": null,
    "entryPrice": 5975.500000000,
    "exitPrice": null,
    …
  },
  "action": 0
}
```

### 2.3 Which schema does TopstepX actually emit?

This is the open question. There are two candidates:

| Hypothesis | Envelope | Inner field names |
|------------|----------|-------------------|
| **A — Gateway envelope** | `{data: {…}, action: 0/1/2}` (admin doc) | Gateway-doc names: `size`, `accountId`, `profitAndLoss`, `filledPrice`, `averagePrice`, `balance` |
| **B — Admin envelope** | `{data: {…}, action: 0/1/2}` (admin doc) | Admin-doc names: `positionSize`, `tradingAccountId`, `pnl`, `executedPrice`, `averagePrice`, `balance` |

We **know** the envelope is wrapped (the admin docs are explicit, and the all-`None` symptoms are the exact fingerprint of a missed unwrap). We **don't know** whether the inner schema is Gateway-doc or Admin-doc.

Some fields agree across both schemas (`id`, `contractId`, `averagePrice`, `balance`, `price`, `fees`, `status`, `type`) so a Gateway-flavoured handler will pick those up regardless. The fields that **differ** are exactly the ones that would still read `None` after the envelope fix:

| What captain reads | Gateway alias | Admin alias |
|--------------------|---------------|-------------|
| Position `size` | `size` | `positionSize` |
| Position `accountId` | `accountId` | `tradingAccountId` |
| Trade `profitAndLoss` | `profitAndLoss` | `pnl` |
| Trade `size` | `size` | `lots` |
| Trade `accountId` | `accountId` | `tradingAccountId` |
| Order `accountId` | `accountId` | `tradingAccountId` |
| Order `filledPrice` | `filledPrice` | `executedPrice` |
| Order `size` | `size` | `positionSize` |
| Order `symbolId` | `symbolId` | `contractGroupId` |

The remediation plan in §6 handles this with a Stage-A diagnostic dump that prints `repr(args)` once per event type — so we can read what TopstepX is actually putting on the wire and then either declare done or add Stage-B aliasing.

---

## 3. Why the prior PascalCase fix didn't catch this

`_normalize_hub_payload` was added on 2026-04-28 (`62484c6`) to handle a *different* defect: TopstepX's C#-POCO JSON serializer was emitting `Id`/`AccountId`/`Balance` (PascalCase) where the captain code expected `id`/`accountId`/`balance` (camelCase). The fix folds PascalCase to camelCase only at the **top level of whatever dict it gets** — which today happens to be the envelope, not the inner entity.

Two structural reasons it can't have caught the envelope problem:

1. The fix's unit test (`tests/test_trade_closed_pipeline.py:9-22`) asserts on the *flat* PascalCase shape — exactly the shape the Gateway public docs document. The test would still pass after the wire format wrapped, because the test never sees an envelope.
2. `_extract_dict` is asymmetric — it pulls the **first** dict it finds in a list, which is the envelope dict, not the inner entity. There's no recursive descent and no awareness of the `{data, action}` schema.

The 2026-04-28 quick-fix doc even hedged: *"After the PascalCase fix, `id` / `status` / `type` should often be non-null when the hub sends full objects (still subject to TopstepX delta messages)."* That hedge is now retroactively explained — the times "id was non-null" coincided with messages where the `{data: {...}}` wrapper happened to lift a top-level `id` (e.g. when the entity itself is one level shallower because of how the broker re-encodes some events). The all-`None` failure on 2026-05-05 is the steady-state behaviour for fully-wrapped messages.

---

## 4. Downstream blast radius — what's blind right now

The four user callbacks in `captain-online/.../main.py` each do **two** things: (a) emit an INFO log, and (b) `redis.publish(CH_USER_EVENTS, …)` so other processes can subscribe.

| Event | Used by (today) | What it does (today) | What's broken |
|-------|----------------|---------------------|---------------|
| `account_update` | Logged + `CH_USER_EVENTS` (no live consumer in captain-command yet — see §6.1 of `docs2/major-issues/15-04-26/2026-04-15-fix-session-c-log.md`). Also `_account_cache` on the UserStream itself. | Future: feed real-time balance into B2 GUI panel + B8 reconciliation. | Real balance never flows into Redis. The system is using REST-pulled balance only (which is correct as of last poll, but stale). The `_account_cache` lookup in `b2_gui_data_server` is empty for the same reason. |
| `order_update` | Logged (rejection alert: `if status in (6, "REJECTED")`), `CH_USER_EVENTS`. | Detect bracket/SL/TP rejections; flag stuck orders. | **Status-6 rejection alarms never fire.** Bracket rejection diagnosis (Issue 1) loses one of its detection paths. |
| `position_update` | Logged, **enriches `captain:open_positions`** with brokerage `averagePrice` if `size > 0` (lines 162-189 of main.py), `CH_USER_EVENTS`. | Patches the position dict B7 monitors with the real fill price. | The whole "GUI shows entry_price = '—'" defect chain (`docs2/major-issues/15-04-26/2026-04-15-NKD-account-failure.md` Issue 2A) regresses — the fix relied on a working `data.get("averagePrice")`. Today the position dict is never enriched, so B7 falls back to whatever `actual_entry_price` was set by `b3_api_adapter.receive_fill()` at order time (which mostly works, but when REST `receive_fill` returns `None`, there is no fallback). |
| `trade_update` | Logged, `CH_USER_EVENTS`. | Future: real-time P&L feed into D03 / GUI / Telegram. | Captain-command's GUI trade-log path uses the QuestDB-backed B7 outcome write, not UserStream — so this is observability-only loss today, but future work depending on it (per-fill commissions, partial fills) is blocked. |

**Severity reassessment vs. the table in `NY_open_errors_2026-05-05.md`:** the original "HIGH" rating is correct *operationally* (all four streams are silently degraded) but Issue 4 is not on the critical path for the immediate-trade-loss class of bugs (Issues 1, 2, 5). It is on the critical path for:

- **Bracket-reject diagnosis** (Issue 1's L2 alarm has a parallel detection path that depends on order_update — fixing it adds defence in depth).
- **Position price reconciliation** (the 2026-04-15 NKD fix relied on this stream).
- **Real-time GUI / Telegram fidelity** (account balance + trade-feed surfaces look frozen mid-session).

---

## 5. Verifying the diagnosis live

Before changing any handler logic, the tower should capture **one** real payload from each User Hub event. The cleanest way without rebuilding the image is a 5-line diagnostic that logs the raw `args` once per event-type per session.

The patch is one block in `shared/topstep_stream.py` that wraps each `_async_handle_*` with a "first-of-kind" debug logger — e.g.:

```python
_LOGGED_FIRST: dict[str, bool] = {"account": False, "order": False,
                                  "position": False, "trade": False}

async def _async_handle_account(self, *args) -> None:
    if not _LOGGED_FIRST["account"]:
        logger.warning("UserStream RAW account args=%r type=%s",
                       args, type(args[0]).__name__ if args else "empty")
        _LOGGED_FIRST["account"] = True
    data = args[0] if args else None
    if data is not None:
        self._handle_account(data)
```

(Repeat for `order`, `position`, `trade`.)

This is **zero-risk**, observability-only, and a single deploy + first-fill is enough to disambiguate Hypothesis A vs B in §2.3. The runbook in §6 below sequences this as Stage A (deploy diag → capture → choose B-A or B-B fix).

Note: if Stage A confirms a different shape (e.g. flat dict but with `Data`/`Action` PascalCase outer keys, or a 2-arg call where `args[0]=tradingAccountId` and `args[1]=entity` — the pattern `ChristianJStarr/projectx-sdk-python/projectx_sdk/realtime/user_hub.py` handles), the §6 fix changes accordingly. The diagnostic is the only way to be **certain** without operating blind.

---

## 6. Remediation plan

### Stage A — capture the raw wire shape (zero-risk, ship today)

| Step | What | Where |
|------|------|-------|
| A.1 | Add `_LOGGED_FIRST` flag + raw-args `WARNING` log in each of the four `_async_handle_*` methods | `shared/topstep_stream.py:717-735` |
| A.2 | Deploy to tower, restart `captain-online` only | `dco up -d captain-online` (helper from `.cursor/rules/captain-deploy-and-tower-discipline.mdc`) |
| A.3 | Wait for first event of each kind during a live session, copy the four lines out of `captain-online` logs | `dco logs captain-online -f \| grep "UserStream RAW"` |
| A.4 | Decide Stage B-1 vs B-2 vs B-3 based on the shape (see decision matrix below) | — |

**Decision matrix from observed shape:**

| Observed shape of `args[0]` | Diagnosis | Apply Stage |
|-----------------------------|-----------|-------------|
| `{"data": {…}, "action": 0}` with Gateway field names inside | Wrapped, schema A | **B-1** (envelope unwrap only) |
| `{"data": {…}, "action": 0}` with Admin field names inside | Wrapped, schema B | **B-1** + **B-2** (unwrap + alias) |
| `{"Id": …, "Balance": …}` flat PascalCase | Old wire shape; something else broke | **B-3** (root-cause something else; envelope is irrelevant) |
| `[tradingAccountId, {…}]` two-element list | Two-arg pattern (ChristianJStarr style) | **B-1'** (extract inner dict from `args[0][1]`) |

### Stage B-1 — fix the envelope unwrap (5-line change)

Add a single early-return branch to `_normalize_hub_payload` that detects the `{data, action}` wrapper and unwraps it before fold-casing. The patch is fully local and behaviour-preserving for the unwrapped case:

```python
def _normalize_hub_payload(data) -> Any:
    extracted = _extract_dict(data)
    if not isinstance(extracted, dict):
        return extracted

    # NEW: detect ProjectX/TopstepX User Hub envelope and unwrap to the
    # inner entity. Per admin.docs.projectx.com the envelope is always
    # {"data": <entity>, "action": int (0=create|1=update|2=delete)}.
    inner = extracted.get("data") or extracted.get("Data")
    action = extracted.get("action", extracted.get("Action"))
    if isinstance(inner, dict) and isinstance(action, (int, str)):
        extracted = inner

    out: dict[str, Any] = {}
    for k, v in extracted.items():
        nk = k
        if len(k) >= 2 and k[0].isupper() and k[1].islower():
            nk = k[0].lower() + k[1:]
        out[nk] = v
    return out
```

The guard is conservative: it only unwraps when **both** `data` (or `Data`) is a dict AND `action` (or `Action`) is present and integer/string. This means the existing flat-PascalCase test fixture (`tests/test_trade_closed_pipeline.py:9-22`) still passes (no `action` key → no unwrap → existing behaviour).

Add a regression test in the same file:

```python
def test_normalize_hub_payload_unwraps_action_data_envelope():
    raw = {"data": {"id": 1, "balance": 99.5}, "action": 0}
    out = _normalize_hub_payload(raw)
    assert out == {"id": 1, "balance": 99.5}
    assert "action" not in out and "data" not in out

def test_normalize_hub_payload_unwraps_pascal_envelope():
    raw = {"Data": {"Id": 1, "Balance": 99.5}, "Action": 1}
    out = _normalize_hub_payload(raw)
    assert out["id"] == 1
    assert out["balance"] == 99.5
```

### Stage B-2 — field-name aliasing (only if A confirms Admin schema)

Map the inner-schema differences to a canonical Gateway-style shape. Cleanest place is right after the unwrap, still inside `_normalize_hub_payload`, behind a dispatch on the calling event so we don't mis-rename for the wrong event. Two implementation options:

- **Inline in `_normalize_hub_payload`**: requires plumbing the event name through. Avoid — leaks coupling.
- **Per-handler alias function**: `_alias_position`, `_alias_order`, `_alias_trade`, `_alias_account` called from `_handle_*` after `_normalize_hub_payload` returns. Cleanest. Each function is a `dict.setdefault` chain — e.g.

  ```python
  def _alias_position(data: dict) -> dict:
      if "size" not in data and "positionSize" in data:
          data["size"] = data["positionSize"]
      if "accountId" not in data and "tradingAccountId" in data:
          data["accountId"] = data["tradingAccountId"]
      return data
  ```

This is purely additive (preserves originals, adds canonical aliases), so even if some events come in mixed-schema we're forward-compatible.

### Stage C — close the loop on observability

After Stage B-1 lands and the system stops emitting `=None` for known fields:

1. Remove the Stage-A diagnostic logger (or leave it as a one-shot session-startup confirmation).
2. Add a `tests/test_userstream_envelope.py` regression test that mounts a fake pysignalr message through `_async_handle_account` and asserts the downstream callback sees `data["balance"] == 147186.78` etc.
3. Update `docs2/major-issues/15-04-26/2026-04-15-fix-session-c-log.md` "What we still don't know" section — the position-enrichment path is once again live and the envelope unwrap is documented as a permanent layer.
4. Re-evaluate the `_account_cache` consumer in `b2_gui_data_server` — now that real balance updates arrive, the GUI Account panel should actually move during a session. Smoke test on tower.

---

## 7. Verification gates (before declaring Issue 4 closed)

A1. **Diagnostic confirms envelope.** Tower captures a `UserStream RAW account args=([{'data': {'id': …, 'balance': …}, 'action': 0}],) type=list` line — shape is the wrapped envelope.

A2. **Post-fix log lines show real values.** After Stage B-1 deploys, `UserStream ACCOUNT: balance=147186.78`, `UserStream ORDER: id=19900 status=6 type=1`, `UserStream POSITION: contract=CON.F.US.MES.M26 size=4 avgPrice=5975.5`, `UserStream TRADE: price=5975.5 pnl=… fees=0.37` (or equivalent, with non-null values).

A3. **Position-enrichment regression check.** A taken signal where REST `receive_fill` returns `None` but UserStream sees `averagePrice` should result in `actual_entry_price` being patched into the `captain:open_positions` Redis hash within 1 second of fill — visible via `redis-cli -a "$REDIS_PASSWORD" HGETALL captain:open_positions | grep actual_entry_price`.

A4. **Order-rejection alarm fires.** Force a tick-misaligned SL via `cmd-run dry_run_command.py` and verify the captain-online log shows `UserStream ORDER REJECTED: id=… data=…` with a non-empty data dict (this also re-arms the Layer-2 alarm path discussed in Issue 1's resolution).

A5. **Pre-existing tests still green.** `pytest tests/test_trade_closed_pipeline.py` continues to pass (the existing PascalCase-flat test must not regress).

A6. **No silent regressions in MarketStream.** `_normalize_hub_payload` is User Hub-only; verify by grep that MarketStream does not call it.

---

## 8. What this audit explicitly does NOT cover

- **Bracket rejection root cause** (Issue 1) — the new alarm path lights up after this fix, but does not change brokerage-side behaviour.
- **TopstepX account-side state** — if the `canTrade=false` or lockout flags appear in `account_update` payloads after the fix, that's an account-readiness signal worth surfacing in the GUI, but it's a separate body of work.
- **Pysignalr internal contract** — we treat `message.arguments` as a list-of-arguments and `args[0]` as the first arg. If pysignalr ever changes this contract, multiple things break; out of scope.
- **The 2-arg `(tradingAccountId, entity)` pattern** seen in `ChristianJStarr/projectx-sdk-python` — Stage A confirms or rules this out; the audit's Stage B-1' is a contingency, not a primary plan.
- **Field-by-field schema mapping for every Admin-doc key** — only the ones captain reads today are aliased. New keys (e.g. `unrealizedPnl`, `maximumLossLimit`, `dailyLossLimit`) become available after the unwrap but are not consumed yet; consuming them is a feature task, not a defect.

---

## 9. Where the docs disagree (for future-readers)

| Doc | URL | What it says about wire format |
|-----|-----|--------------------------------|
| **Gateway public** | gateway.docs.projectx.com/docs/realtime/ | Flat dict; no envelope. Gateway field names. Aligned with the captain code's read-side. |
| **Admin/S2F** | admin.docs.projectx.com/docs/real-time-data/signalR-websocket/{account,order,position,trade}-updates/ | `{data: {…}, action: 0/1/2}` envelope. Admin field names (`positionSize`, `tradingAccountId`, `pnl`, `executedPrice`). Matches the all-`None` fingerprint observed on 2026-05-05. |
| **`ChristianJStarr/projectx-sdk-python/projectx_sdk/realtime/user_hub.py`** | github.com/ChristianJStarr/projectx-sdk-python | Two-arg pattern `(account_id, data)` for Order/Position/Trade. Single-arg `(data)` for Account. Suggests **some** ProjectX hosts route account_id as a separate arg. Not what the admin docs document; a defensive fallback only. |
| **`TexasCoding/project-x-py/src/project_x_py/realtime/event_handling.py`** | github.com/TexasCoding/project-x-py | "User events — single data payload like sync version" → `args[0]`. Treats the SignalR arg as the entity. Matches captain's code, also misses the envelope. Confirms our bug is widespread in the ProjectX Python ecosystem. |

The takeaway: the **Gateway** and **third-party-Python-SDK** sources all describe the *Gateway-product* contract — flat dict, Gateway names. Real on-the-wire TopstepX traffic on 2026-05-05 is the **Admin-product** contract — wrapped envelope, possibly Admin names. We need Stage A to know which is canonical for the live `rtc.topstepx.com/hubs/user` host; we need Stage B-1 minimum and possibly B-2 to fix it.
