# NY Open Error Log — 2026-05-05

Session: **NY Open, Monday May 5 2026**

---

## Resolution Tracker

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | [OCO Bracket Fail](#1-oco-bracket-order-failure) | HIGH | :white_check_mark: Resolved (mitigation + safety net) |
| 2 | [Pseudotrader Crash — missing `requests`](#2-pseudotrader-crash--missing-requests-module) | HIGH | :white_check_mark: Resolved |
| 3 | [Pseudotrader Rejections — zero sharpe_delta](#3-pseudotrader-rejections--zero-sharpe_delta) | MEDIUM | :white_check_mark: Resolved |
| 4 | [UserStream returning all Nones](#4-userstream-returning-all-nones) | HIGH | :mag: Audited — fix gated on Stage-A diagnostic |
| 5 | [Decimal → DOUBLE conversion error in B7](#5-decimal--double-conversion-error-in-b7-position-monitor) | HIGH | :white_check_mark: Resolved |
| 6 | [Remove ZB and ZN from NY session](#6-remove-zb-and-zn-from-ny-session) | MEDIUM | :x: Open |

> Update the **Status** column to `:white_check_mark: Resolved` and add a one-line note after each fix lands.

---

## 1. OCO Bracket Order Failure

**Summary:** Bracket order placement fails with "You must enable Auto OCO Brackets" despite Auto OCO being confirmed enabled on the TopstepX account side.

**Impact:** Bracket orders fall back to separate limit/stop orders, which are not atomically linked — risk of orphaned SL/TP if one leg fills and the other isn't cancelled.

**Logs:**

```
captain_command.blocks.b3_api_adapter: Bracket order: SELL MYM x4, SL=40 ticks, TP=81 ticks (tick_size=1.0, entry_est=49221)
captain-command-1  | [COMMAND] 2026-05-05 09:37:04,228 WARNING captain_command.blocks.b3_api_adapter:
    Bracket order FAILED: Brackets cannot be used with Position Brackets.
    You must enable Auto OCO Brackets. — falling back to separate orders
```

**Notes:** Auto OCO is enabled in TopstepX platform settings. Possible causes: API-side setting not syncing, or the account has "Position Brackets" mode active which conflicts with the API bracket payload format.

---

## 2. Pseudotrader Crash — missing `requests` module

**Summary:** The `captain-offline` container is missing the `requests` Python package, causing pseudotrader updates to crash for AIM_WEIGHT_CHANGE and KELLY_UPDATE events.

**Impact:** All offline learning updates (DMA weight changes, Kelly recalculation) are blocked. The system falls back to fail-safe (no update), meaning AIM weights and Kelly fractions are stale.

**Logs:**

```
09:37:44 [OFL] Pseudotrader CRASHED for MES [AIM_WEIGHT_CHANGE]:
    No module named 'requests' — update blocked (fail-safe)

09:37:44 [OFL] Pseudotrader CRASHED for MES [KELLY_UPDATE]:
    No module named 'requests' — update blocked (fail-safe)
```

**Notes:** `requests` likely needs adding to `captain-offline/requirements.txt` — or the code path importing it should be checked to see if it's a new dependency that wasn't present at build time.

---

## 3. Pseudotrader Rejections — zero sharpe_delta

**Summary:** Pseudotrader rejects AIM_WEIGHT_CHANGE for every asset because `sharpe_delta` is exactly 0.0000, which fails the minimum-impact gate.

**Impact:** No AIM weight updates are applied for any asset. DMA meta-weights remain frozen at bootstrap values.

**Logs:**

```
09:41:47 [OFL] Pseudotrader REJECTED AIM_WEIGHT_CHANGE for MNQ (sharpe_delta=0.0000)
```

(Repeated for every active asset.)

**Notes:** This may be downstream of Issue #2 — if the pseudotrader crashes before computing sharpe deltas, subsequent retries may produce zero deltas. Alternatively, the EWMA/Kelly state may not have enough history to produce a non-zero delta yet (cold-start condition). Investigate whether this is a data issue or a code bug.

---

## 4. UserStream Returning All Nones

**Summary:** The TopstepX UserStream WebSocket is delivering account, order, trade, and position updates where every field is `None`.

**Impact:** Captain Online cannot track real account balance, order status, fill prices, P&L, or position state. B7 position monitor and TSM state updates are blind.

**Logs:**

```
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

captain-online-1  | [ONLINE] 2026-05-05 09:38:23,167 INFO __main__:
    UserStream ACCOUNT: balance=None
```

**Notes:** Either the SignalR message schema has changed (field names shifted), the auth token is invalid/expired so the stream connects but returns empty payloads, or pysignalr is not parsing the hub response correctly. Check `shared/topstep_stream.py` message handler field mappings.

**Audit (2026-05-06):** See [`2026-05-06_issue4_userstream_none_root_cause_audit.md`](./2026-05-06_issue4_userstream_none_root_cause_audit.md). Root cause: TopstepX User Hub wraps each event in a `{"data": {...}, "action": 0/1/2}` envelope (per `admin.docs.projectx.com`) but `_normalize_hub_payload` reads the wrapper, never unwrapping to the inner entity — so every `data.get("balance")`, `.get("id")`, `.get("contractId")`, etc. returns `None`. The captain code was written against the Gateway-product docs which omit the envelope entirely. Two-stage remediation: **(A)** ship a one-shot raw-args logger to confirm the wire shape, **(B)** add an `{data, action}` unwrap branch in `_normalize_hub_payload` (~10 lines, two regression tests). Field-name aliasing (e.g. `positionSize`→`size`, `pnl`→`profitAndLoss`) gated on what Stage A captures. No code changes yet.

---

## 5. Decimal → DOUBLE Conversion Error in B7 Position Monitor

**Summary:** QuestDB rejects an INSERT into the trade outcome table because `aim_modifier_at_entry` is being cast as `DECIMAL(3,2)` but the column type is `DOUBLE`.

**Impact:** Trade outcomes (SL_HIT events) are not written to P3-D03. Downstream offline learning (DMA, BOCPD, EWMA, Kelly) never sees these outcomes — the feedback loop is broken.

**Logs:**

```
captain-online-1  | psycopg2.DatabaseError:
    inconvertible types: DECIMAL(3,2) -> DOUBLE [from=cast, to=aim_modifier_at_entry]
    LINE 8: ..., '2026-05-05T09:41:18.266392-04:00', 'HIGH_VOL', cast('0.96...
                                                                 ^

Traceback (most recent call last):
  File "/app/captain_online/blocks/orchestrator.py", line 178, in _session_loop
    self._run_position_monitor()
  File "/app/captain_online/blocks/orchestrator.py", line 778, in _run_position_monitor
    resolved = monitor_positions(self.open_positions, tsm_configs)
  File "/app/captain_online/blocks/b7_position_monitor.py", line 306, in monitor_positions
    resolve_position(pos, "SL_HIT", exit_px, tsm_configs)
  File "/app/captain_online/blocks/b7_position_monitor.py", line 380, in resolve_position
    _write_trade_outcome(
  File "/app/captain_online/blocks/b7_position_monitor.py", line 531, in _write_trade_outcome
    cur.execute(

captain-online-1  | [ONLINE] 2026-05-05 09:41:28,465 ERROR captain_online.blocks.orchestrator:
    Position monitor error: inconvertible types: DECIMAL(3,2) -> DOUBLE
    [from=cast, to=aim_modifier_at_entry]
```

**Notes:** The `_write_trade_outcome` SQL likely wraps `aim_modifier_at_entry` in `cast('0.96' AS DECIMAL(3,2))` but the QuestDB column is type DOUBLE. Fix: cast as DOUBLE instead, or pass a raw float without explicit cast. This is a known class of error — see `docs2/quick-fixes/fixing-decimal-errors/`.

---

## 6. Remove ZB and ZN from NY Session

**Summary:** ZB (30-Year T-Bond) and ZN (10-Year T-Note) should not be included in the NY open session roster.

**Impact:** The system is generating signals and potentially trading ZB/ZN during NY open when they should be excluded. This wastes signal slots and could trigger trades on assets not intended for this session.

**Action:** Update `config/session_registry.json` (or the relevant asset universe query) to remove ZB and ZN from the NY session, or set their `captain_status` to exclude them from NY signal generation.

---

## Resolution Log

> After each fix, add a dated entry below with the issue number and what was done.

| Date | Issue # | Resolution |
|------|---------|------------|
| 2026-05-06 | #1 | Three-layer mitigation. **Layer 2** (loud alarm): `b3_api_adapter.send_signal` now publishes a CRITICAL Telegram alert with full errorCode + errorMessage on every bracket rejection so we can never miss a recurrence. **Layer 3** (orphan-order safety net): plumbed `sl_order_id`/`tp_order_id` from B3 → command orchestrator → online orchestrator → position dict; new helper `_cancel_orphan_bracket_leg` in `b7_position_monitor` cancels the surviving SL/TP leg first thing in `resolve_position` whenever `bracket=False`, with CRITICAL alerting if the cancel itself fails. **Layer 1** (diagnosis): added `scripts/diagnose_bracket_settings.py` — read-only dump of every TopstepX account-level field for next-time investigation. The TopstepX account-side root cause (intermittent rejection while Auto OCO is enabled) is not yet identified — the safety net ensures the orphan-fallback can no longer cause unintended counter-positions. Requires container restart on captain-command + captain-online (no rebuild). |
| 2026-05-06 | #2 | Added `requests>=2.25.0` and `pysignalr>=1.0` to `captain-offline/requirements.txt`. Replay path imports `b1_data_ingestion` which triggers module-level imports of `topstep_client` (needs requests) and `topstep_stream` (needs pysignalr). Requires `--build` on next deploy. |
| 2026-05-06 | #3 | Cold-start bypass added in `_pseudotrader_gate` — auto-approves DMA/Kelly updates when asset has <5 D03 trades. Constant: `COLD_START_MIN_TRADES=5`. |
