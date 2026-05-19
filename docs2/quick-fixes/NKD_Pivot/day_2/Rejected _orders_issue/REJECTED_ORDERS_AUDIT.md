# NKD Auto-Execution Audit — 2026-05-18 APAC Order Rejections

**Generated:** 2026-05-19 (post C14/C15/C16 deploy)
**Scope:** Captain System NKD pivot auto-execution path, end-to-end from B6 signal to TopstepX bracket placement, including the trailing-stop block.
**Source artefacts:**
- Order export CSV: `c:\Users\nomaa\Downloads\orders_export.csv` (Nomaan tower, account 21855714, parity 0, 8 orders 2026-05-18 23:08–23:22)
- User report: Isaac tower (parity 1) placed an *unprotected* SELL with no SL/TP bracket on the same APAC session.
- Code at HEAD (post C15 merged): `captain-online/captain_online/blocks/b6_signal_output.py`, `captain-online/captain_online/blocks/b7b_nkd_trail.py`, `captain-command/captain_command/blocks/b1_core_routing.py`, `captain-command/captain_command/blocks/orchestrator.py`, `captain-command/captain_command/blocks/b3_api_adapter.py`, `shared/topstep_client.py`, `shared/contract_resolver.py`, `config/contract_ids.json`, `scripts/bootstrap_production.py`.
- Day-2 plan & checklist: `docs2/quick-fixes/NKD_Pivot/day_2/PLAN.md`, `COMPLETION_CHECKLIST.md`.
- Memory anchors: #3343 (Isaac spec), #3362 (C15 fix landing), #3334 (NKD infra), #3367 (C15 commit sync).

**Status:** READ-ONLY AUDIT. No code changes have been made.

---

## 0. TL;DR

| Finding | Severity | Tonight's impact |
|---|---|---|
| **F1.** Both rejections last night were caused by the pre-C15 OR-range-derived SL collapsing to ≤1 NKD tick from entry during a quiet APAC open. The bracket rejected with `stop loss ticks (1)`, the fallback standalone STOP rejected with `price outside allowed range`, and B3 emergency-flattened the position for a $100 loss. | **RESOLVED** | C15 (deployed today) fixes both rejections by pinning the NKD SL at a fixed `$1,025` distance from entry = `41 ticks` for size=1, far above the 4-tick TopstepX minimum and far enough that realistic slippage cannot push the actual fill past the SL price. |
| **F2.** **`sanitise_for_api` does not forward the NKD trail-control fields** (`is_nkd_trail`, `tp_dollars`, `snapped_d_init`, `jitter_x`, `jitter_y`, `jitter_j`). They are stripped at the Command→API boundary in `b1_core_routing.py:131-153`, never reach `_auto_execute_signal`, never enter the TAKEN_SKIPPED stream message, and arrive at Online's `_handle_taken_skipped` as `None`. The Online orchestrator coerces `None → False` for `is_nkd_trail` (`orchestrator.py:1234`). `b7b_nkd_trail.scan_nkd_trails` then **silently skips every NKD position** at line 533: `if not pos.get("is_nkd_trail"): continue`. | **CRITICAL — BLOCKER for trail intent** | The bracket order will be placed correctly tonight (C15), but **the trailing-stop ratchet will NOT engage**. The SL will sit fixed at `entry ± $1,025` for the entire trade. No Phase A/B/C step-down, no profit lock-in, no D34 rows, no `modify_order` calls. If price reaches +$3,000 then reverses, the position loses the full $1,025 back. Isaac tower's TP jitter still works (sampled in B6), but the SL jitter never does. |
| **F3.** `route_command` for the TAKEN_SKIPPED branch (`b1_core_routing.py:204-229`) also doesn't forward NKD fields. This is a secondary path (GUI-initiated manual TAKEN), but it has the same gap as F2. | HIGH | Same as F2 — manual TAKEN of an NKD signal also results in `is_nkd_trail=False` in the position dict. |
| **F4.** B3's separate-orders fallback places the TP **unconditionally** even when the SL placement failed and the position was already emergency-flattened. This is what produced the orphan limit BUY at `60665` that the operator had to cancel manually at 23:22:43. | MEDIUM | Cosmetic — only fires on the rare bracket-failure + fallback-SL-failure path. C15 makes that path much less likely to fire, but if it ever does fire (e.g. extreme slippage), the orphan TP will reappear. |
| **F5.** Isaac-tower jitter is sampled **twice** in the post-C16 design — once in B6 for the TP bracket price (`b6_signal_output.py:158`), and again in `b7b_nkd_trail` on first poll (`b7b_nkd_trail.py:660`). These are independent random draws, violating Isaac's "one signed J per trade" spec. | LOW (moot tonight) | Doesn't cause rejections. Becomes a *real* spec violation only AFTER F2 is fixed and the trail block actually runs. For tonight (F2 unfixed), the trail block doesn't sample at all, so Isaac TP gets `J_a` and SL stays at the static `$1,025` bracket price. |

**Bottom line for tonight's APAC session:**

1. **The two rejections from last night WILL NOT recur.** C15 is the correct, targeted fix and is now on both towers per [today's commit sync](#).
2. **But the trail block remains inert.** What you'll see tonight is: bracket placed correctly with `SL=entry ± $1,025` and `TP=entry ± $4,450` (`+J` on Isaac). The SL will hold static for the entire trade duration. No phase transitions, no GUI updates of `current_phase` / `current_buffer` / `current_stop_price`, no D34 rows.
3. The position **is still protected** by the broker-side OCO bracket — it just won't ratchet inward to lock in profit.

If the NKD pivot's value proposition depends on the trailing behaviour, F2 must be fixed before tonight's APAC window. Otherwise you can run tonight on the unprotected-trail behaviour and add F2 to tomorrow's day-3 patch.

---

## 1. Order-by-order CSV reconstruction (Nomaan tower, account 21855714)

The 8 rows in `orders_export.csv` reconstruct as the following timeline. Side maps `Ask → SELL`, `Bid → BUY`. NKD point value = `$5/point`, tick size = `5 points/tick`, tick value = `$25/tick`.

| # | Time (BST) | Order ID | Type | Side | Status | Price | Reason / Notes |
|---|---|---|---|---|---|---|---|
| 1 | 23:08:06 | `2994362515` | **Bracket Market** | SELL | **REJECTED** | — | `Invalid stop loss ticks (1). Price should be at least 4 ticks away.` |
| 2 | 23:08:06 | `2994362522` | Market | SELL | Filled | `61600` | Fallback entry from B3 separate-orders path (`b3_api_adapter.py:376`) |
| 3 | 23:08:07 | `2994362543` | Stop | BUY | **REJECTED** | stop `61575` | Fallback SL. `Order price is outside allowed range. Please set price above best bid.` |
| 4 | 23:08:07 | `2994362566` | Limit | BUY | Cancelled 23:22:43 | limit `60665` | Fallback TP — placed *after* SL failure, became orphan |
| 5 | 23:08:07 | `2994362558` | Market | BUY | Filled (Closing) | `61620` | Emergency flatten triggered by `b3_api_adapter.py:441-445`. Net loss `(61620-61600) × $5 = $100` |
| 6 | 23:10:01 | `2994376778` | Market | SELL | Filled (Opening) | `61565` | **Manual re-entry by operator** — Captain auto path was abandoned |
| 7 | 23:22:22 | `2994461213` | Stop | BUY | Filled 02:07:29 next morning | stop `60950`, exec `61000`, trig `60985` | Manual trailing-stop placed by operator (well below mark by then — trade was already deep ITM by ~$2,800) |
| 8 | 23:22:54 | `2994465264` | Limit | BUY | Cancelled 02:07:59 | limit `60675` | Manual TP placed by operator, cancelled after stop filled |

### Maps cleanly to `b3_api_adapter.send_signal()` flow

The chronology is a textbook execution of the code path at `captain-command/captain_command/blocks/b3_api_adapter.py` lines 271–518:

1. **Lines 282-333** (bracket attempt): `place_bracket_order(... sl_ticks=1, tp_ticks=N)` → broker returns `success=False, errorCode=2, errorMessage="Invalid stop loss ticks (1). Price should be at least 4 ticks away."` → order #1.
2. **Lines 376-385** (fallback entry): `place_market_order(SELL, NKDM6)` → filled at `61600` → order #2.
3. **Lines 400-411** (fallback SL): `place_stop_order(BUY, NKDM6, stop_price=61575)` → broker rejects because `61575 < best_bid ≈ 61620` (you cannot place a BUY STOP below the current bid; the broker would have to fill it instantly at market and that's not a stop, it's an immediate market order) → order #3.
4. **Lines 412-455** (SL-failure emergency flatten): `logger.critical("STOP LOSS PLACEMENT FAILED — position … is UNPROTECTED")` → `close_position(account_id, contract_id, size)` → market BUY at `61620` → order #5.
5. **Lines 474-510** (TP placement — **unconditional**, runs even after flatten): `place_limit_order(BUY, NKDM6, limit_price=60665)` → accepted as a working order with no underlying position → order #4. The operator had to cancel this manually 14 minutes later.

---

## 2. Why `sl_ticks = 1` was sent (pre-C15 root cause)

### 2.1 The arithmetic

B3's bracket-ticks computation (`b3_api_adapter.py:284-289`):

```279:289:captain-command/captain_command/blocks/b3_api_adapter.py
            if (sl_price is not None and tp_price is not None
                    and entry_est is not None and tick_size > 0):
                sl_ticks = max(1, int(round(
                    abs(float(entry_est) - float(sl_price)) / tick_size
                )))
                tp_ticks = max(1, int(round(
                    abs(float(tp_price) - float(entry_est)) / tick_size
                )))
```

For NKD `tick_size = 5.0` (from `config/contract_ids.json` row `NKD`). Any `|entry_est - sl_price| < 7.5 points` rounds to ≤1 tick, then `max(1, …)` floors it at 1. The broker minimum is 4 ticks (`= $100 risk per contract`), so anything tighter than 4 ticks is rejected with `errorCode=2`.

### 2.2 Where the bad `sl_price` came from

Pre-C15, `b6_signal_output._compute_sl` produced `sl_level` from OR-range × `sl_multiple`:

```393:412:captain-online/captain_online/blocks/b6_signal_output.py
def _compute_sl(strategy: dict, features: dict, direction: int, asset_id: str = "") -> float | None:
    """Compute stop-loss level from strategy params."""
    sl_multiple = strategy.get("sl_multiple", 0.35)
    or_range = features.get("or_range")
    entry = features.get("entry_price")

    if or_range and entry:
        sl_dist = sl_multiple * or_range
        sl = entry - (sl_dist * direction) if direction != 0 else None
    else:
        sl = strategy.get("sl_level")

    if sl is not None:
        tick = get_tick_size(asset_id)
        ndigits = max(0, len(str(tick).rstrip('0').split('.')[-1])) if '.' in str(tick) else 0
        if direction == 1:
            sl = round(math.ceil(sl / tick) * tick, ndigits)
        elif direction == -1:
            sl = round(math.floor(sl / tick) * tick, ndigits)
    return sl
```

`sl_multiple` defaults to `0.35` (the original ES-tuned value the bootstrap inherits for every asset). On a quiet APAC open NKD can produce a tiny OR range — your CSV implies `or_range ≈ 14 points` because:

- Signal `entry_price` ≈ `61570` (B6's pre-fill estimate from the OR breakout bar).
- `sl_dist = 0.35 × 14 = 4.9 points`.
- `sl_raw = 61570 + 4.9 = 61574.9` (SHORT, so SL above entry).
- `math.floor(61574.9 / 5) × 5 = 61570` after the SHORT-direction floor at b6:411 — **which means the snapped SL collapses back ONTO the entry price**.
- B3 then computes `abs(61570 - 61570) / 5 = 0`, but `max(1, 0) = 1` → `sl_ticks = 1` → broker rejects.

A second symptom of the same OR-range computation explains rejection #2: by the time the bracket reject came back (~1 second later) and the fallback market entry filled at `61600` (not `61570`), the standalone STOP placement still used B6's original `sl_price = 61575`. `61575` is *below* `best_bid ≈ 61620`, so a BUY STOP at that price is invalid — TopstepX returns `Order price is outside allowed range. Please set price above best bid.`

Both rejections share the **same single root cause**: the OR-range-derived SL was on the wrong order of magnitude for NKD's tick granularity. No directional error, no sign error, no per-account size bug. Just an SL distance that the SHORT-floor rounding collapsed to zero.

### 2.3 Why this hadn't been caught before

- NKD had not auto-traded prior to this session under the OR-range SL — the pivot to NKD trail (Day-1 commits C1–C13) shipped the same OR-range branch that all other assets use, without realising that NKD's `tick_size = 5.0` is **20× wider** than ES's `0.25`. ES never produces this collapse because `sl_multiple × or_range` for ES is almost always > 5 ticks.
- No existing unit test exercised the `entry_est` → `sl_ticks` rounding for a tight-OR NKD case. `test_b6_signal.py` and `test_b3_api_adapter.py` mock at higher boundaries.
- The Day-1 `NKD_PIVOT_AUDIT.md` §5.3 noted the need for `tick_snap_outward` for trail SLs but did not flag that the *initial* SL was still going through the inward floor in `_compute_sl`.

---

## 3. Does C15 fix it? Yes, with margin.

### 3.1 Post-C15 SL distance

After C15 (now on HEAD), the NKD branch in `b6_signal_output.py` lines 142-154 **overrides** the OR-range `sl_level` with a fixed-dollar value:

```142:154:captain-online/captain_online/blocks/b6_signal_output.py
        if strategy.get("is_nkd_trail"):
            point_value = float(asset_detail.get("point_value", 50.0))
            entry_price_raw = asset_features.get("entry_price")
            # Fixed dollar SL per Isaac spec — always $1025, never OR-range derived
            sl_dollars_fixed = float(strategy.get("sl_dollars_fixed", 1025))
            snapped_d_init = sl_dollars_fixed
            # Override sl_level used for the broker bracket with the fixed-dollar SL.
            # _sl_from_dollars snaps outward (wider) to the NKD tick grid.
            if entry_price_raw is not None:
                sl_level = _sl_from_dollars(
                    sl_dollars_fixed, float(entry_price_raw),
                    direction, point_value, total_size, u,
                )
```

`_sl_from_dollars` (b6 lines 330-350) uses `tick_snap_outward` so the result is *wider* than the dollar threshold, never tighter:

| Trade | entry | direction | size | sl_raw | sl_level (after `tick_snap_outward`) | B3 `sl_ticks` | $ risk per contract |
|---|---|---|---|---|---|---|---|
| SHORT 1× | `61600` | `-1` | 1 | `61805` | `61805` | `41` | `$1,025.00` |
| LONG  1× | `61600` | `+1` | 1 | `61395` | `61395` | `41` | `$1,025.00` |
| SHORT 1× | `61592` (non-aligned) | `-1` | 1 | `61797` | `61800` (`ceil`) | `42` | `$1,050.00` |
| SHORT 2× | `61600` | `-1` | 2 | `61702.5` | `61705` (`ceil`) | `21` | `$525.00` × 2 = `$1,050.00` |

All four cases produce `sl_ticks ≥ 4` (well above the broker minimum), and all four sit on the correct side of entry (above for SHORT, below for LONG). The `tick_snap_outward` ensures conservative widening when the raw price lands between ticks. This is what Isaac's spec requires (`docs2/quick-fixes/NKD_Pivot/day_2/PLAN.md §1`).

### 3.2 Bracket order shape sent to TopstepX

`place_bracket_order` in `shared/topstep_client.py:342-381` signs the ticks for you:

- SHORT 1× → `place_order(side=SELL, sl_bracket={ticks: +41, type: 4}, tp_bracket={ticks: -178, type: 1})` (positive SL ticks for SHORT = stop above fill; negative TP ticks for SHORT = limit below fill).
- LONG  1× → `place_order(side=BUY,  sl_bracket={ticks: -41, type: 4}, tp_bracket={ticks: +178, type: 1})`.

The 41-tick SL distance from fill is exactly `$1,025` per contract (`41 × $25/tick`). Realistic NKD slippage of ±5 ticks won't push the actual fill past the SL — even in a fast tape, you'd need >200 points (≈$1,000) of slippage in a single contract to invert the SL side, which doesn't happen on NKD's micro-second order matching window.

### 3.3 The fallback path is also fixed by C15

If the bracket call were to fail for some other reason (latency, exchange disconnect, etc.) and B3 fell through to the separate-orders branch at lines 376+:

- The fallback entry market order fills at some price `P`.
- The fallback standalone STOP is placed at `sl_price = sl_level = 61805` (for the SHORT case above).
- Even with slippage pushing `P` up to `61700` (100 points = ~$500 worse than the signal estimate), `sl_level = 61805` is still **105 points above** `P`. A BUY STOP at `61805` with `best_bid ≈ 61700` is *above* the bid → accepted by TopstepX.
- Only if slippage exceeded **205 points** (>$1,000 worse than the signal estimate, ~0.33% on NKD price) would the standalone SL go inverted. That's beyond any realistic single-bar slippage on a liquid futures contract.

### 3.4 What C15 does NOT fix

The fallback **TP** at `b3_api_adapter.py:474-510` is still placed unconditionally after a failed SL + emergency flatten (F4 in §0). It's a small bug — only fires on the rare bracket-failure + fallback-SL-failure path that C15 now makes much less likely — but it does still leak orphan limit orders that need manual cancellation. Worth catching in a day-3 patch but not blocking for tonight.

---

## 4. The new critical finding — trail block is inert (F2)

### 4.1 The proof

Trace one NKD signal from B6 to the trail block:

**Step 1.** B6 builds `signal["is_nkd_trail"] = True`, `signal["tp_dollars"] = 4450`, `signal["snapped_d_init"] = 1025.0`, `signal["jitter_j"] = J` etc. (post-C15/C16, `b6_signal_output.py:168-176`). The fields are at the **top level** of the signal dict via `**nkd_trail_fields`.

**Step 2.** Command receives the signal batch on stream `captain:signals:{user_id}` and calls `_handle_signal` → `route_signal_batch` → for each account, `sanitise_for_api(signal, ac_id, ac_detail)`:

```131:153:captain-command/captain_command/blocks/b1_core_routing.py
def sanitise_for_api(signal: dict, ac_id: str, ac_detail: dict) -> dict:
    """Return the 6-field sanitised order — nothing else leaves Captain.
    ...
    """
    ctx = signal.get("_context", {})
    return {
        "asset": signal.get("asset"),
        "direction": signal.get("direction"),
        "size": ac_detail.get("contracts", 0),
        "tp": signal.get("tp_level"),
        "sl": signal.get("sl_level"),
        "timestamp": signal.get("timestamp", now_et().isoformat()),
        "signal_id": signal.get("signal_id"),
        "user_id": signal.get("user_id"),
        "session": signal.get("session"),
        "entry_price": ctx.get("entry_price"),
        "regime_state": ctx.get("regime_state"),
        "combined_modifier": ctx.get("combined_modifier"),
        "aim_breakdown": ctx.get("aim_breakdown"),
    }
```

**This explicit allow-list does NOT include `is_nkd_trail`, `tp_dollars`, `snapped_d_init`, `jitter_x`, `jitter_y`, or `jitter_j`.** The fields are dropped on the floor.

**Step 3.** The sanitised dict is passed to `_auto_execute_signal(account_id, sanitised_order)`. That function attempts to forward the NKD fields on lines 701-703:

```697:704:captain-command/captain_command/blocks/orchestrator.py
                # NKD pivot: forward trail-control fields from the original signal
                # so the online orchestrator can wire them into the position dict.
                # Absent for all non-NKD assets (key not present → None → ignored).
                "is_nkd_trail": sanitised_order.get("is_nkd_trail"),
                "tp_dollars": sanitised_order.get("tp_dollars"),
                "snapped_d_init": sanitised_order.get("snapped_d_init"),
            })
```

But `sanitised_order.get("is_nkd_trail")` returns `None` (the field was never put into `sanitised_order`). So the TAKEN_SKIPPED message on `STREAM_COMMANDS` carries `is_nkd_trail=None, tp_dollars=None, snapped_d_init=None`.

**Step 4.** Online's `_handle_taken_skipped` reads the stream message and coerces:

```1234:1244:captain-online/captain_online/blocks/orchestrator.py
                # NKD pivot trail-control fields (None for all non-NKD assets).
                # Populated by B6 → Command orchestrator → here when is_nkd_trail=True.
                "is_nkd_trail": bool(data.get("is_nkd_trail", False)),
                "tp_dollars": as_money_or_none(data.get("tp_dollars")),
                "snapped_d_init": as_money_or_none(data.get("snapped_d_init")),
                # Trail state fields — None on entry; updated by b7b_nkd_trail on each poll.
                "jitter_x": None,
                "jitter_y": None,
                "jitter_j": None,
                "current_phase": None,
                "current_buffer": None,
                "current_stop_price": None,
                "modify_seq": 0,
            }
```

`bool(None)` is `False`. So the position dict has **`is_nkd_trail = False`** for every NKD trade (and `tp_dollars = None`, `snapped_d_init = None`).

**Step 5.** Every 10s, `_run_position_monitor` calls `scan_nkd_trails(self.open_positions, …)`. The first thing the per-position loop does:

```532:539:captain-online/captain_online/blocks/b7b_nkd_trail.py
    for pos in (open_positions or []):
        if not pos.get("is_nkd_trail"):
            continue
        sig_id = pos.get("signal_id")
        if sig_id is None:
            logger.warning("ON-B7B-NKD: skipping trail position with no signal_id")
            continue
        seen_signal_ids.add(sig_id)
```

**Every NKD position is silently skipped because `is_nkd_trail` is `False`.** No diagnostic row, no log line at WARNING or higher, no alert. The position monitor moves on as if no NKD trail were configured.

### 4.2 Why no test caught it

- `test_b7b_nkd_trail.py`, `test_b7b_isaac_jitter_stress.py`, `test_nkd_jitter_lifecycle.py`, `test_b7b_stale_quote_skips_modify.py`, `test_b7b_external_close.py`, `test_b7b_fast_crossing_multiple_boundaries.py` — all six trail tests inject the position dict **manually** into `scan_nkd_trails`, hand-setting `is_nkd_trail=True` (see `test_nkd_jitter_lifecycle.py:135-164`, the `_make_nkd_position_from_signal` helper). None of them exercise the `signal → sanitise_for_api → TAKEN_SKIPPED → _handle_taken_skipped → position dict` path with NKD fields.
- `test_decimal_e2e_flow.py` covers the full signal lifecycle but uses MES, not NKD — no `is_nkd_trail` field at all.
- `test_userstream_bracket_capture.py` covers C5 (UserStream bracket child capture) but doesn't assert NKD trail fields are present in the captured position.

In other words: **C6 was scored DONE in the day-1 checklist with the evidence "Command at command/orchestrator.py:701-704 — forwards fields", but the line that *populates* `sanitised_order` (the function whose output line 701-703 reads from) was never updated to include those fields.** The C6 commit added the *read* but not the matching *write*.

### 4.3 Empirical confirmation path

You can verify F2 in seconds tomorrow morning (before market open) without deploying anything:

```fish
# Manual signal → check what arrives at TAKEN_SKIPPED stream
dco exec -T captain-command python3 -c "
from captain_command.blocks.b1_core_routing import sanitise_for_api
signal = {
    'asset': 'NKD', 'direction': -1, 'size': 1,
    'tp_level': 60680, 'sl_level': 61805,
    'is_nkd_trail': True, 'tp_dollars': 4450, 'snapped_d_init': 1025.0,
    'jitter_x': 0.5, 'jitter_y': 1, 'jitter_j': 10.0,
    'signal_id': 'TEST', 'user_id': 'primary_user',
    '_context': {'entry_price': 61600},
    'per_account': {'21855714': {'contracts': 1}},
}
sanitised = sanitise_for_api(signal, '21855714', signal['per_account']['21855714'])
print('is_nkd_trail in sanitised?', 'is_nkd_trail' in sanitised)
print('tp_dollars in sanitised?', 'tp_dollars' in sanitised)
print('snapped_d_init in sanitised?', 'snapped_d_init' in sanitised)
print('jitter_j in sanitised?', 'jitter_j' in sanitised)
print('Keys:', sorted(sanitised.keys()))
"
```

Expected output (which demonstrates the bug):

```
is_nkd_trail in sanitised? False
tp_dollars in sanitised? False
snapped_d_init in sanitised? False
jitter_j in sanitised? False
Keys: ['aim_breakdown', 'asset', 'combined_modifier', 'direction', 'entry_price', 'regime_state', 'session', 'signal_id', 'size', 'sl', 'timestamp', 'tp', 'user_id']
```

If this runs and shows `False / False / False / False`, the bug is confirmed. The fix is mechanical (5 added keys in `sanitise_for_api`, 5 more in `route_command`'s TAKEN_SKIPPED branch, and an Online-side change to thread `jitter_*` into the position dict instead of forcing them to `None`).

---

## 5. Tonight's expected behaviour with current code (post-C15, pre-F2-fix)

### 5.1 What will work correctly

| Stage | Behaviour | Code reference |
|---|---|---|
| OR breakout & B6 signal | NKD signal built with `sl_level = entry ± $1,025` (fixed-dollar, outward-snapped), `tp_level = entry ± $4,450` (Nomaan) or `entry ± ($4,450 + J)` (Isaac), `is_nkd_trail=True`, `snapped_d_init=1025`, `jitter_*` populated. | `b6_signal_output.py:142-176` |
| Bracket placement (Command → B3 → TopstepX) | `sl_ticks = 41`, `tp_ticks = 178` (1× SHORT, entry ≈ 61600). Bracket accepted by exchange. SL fires at `entry + 41 ticks` if price moves up by $1,025. TP fires at `entry - 178 ticks` if price moves down by $4,450. OCO linkage on the exchange. | `b3_api_adapter.py:281-333` |
| UserStream bracket child capture (C5) | When the bracket fills, UserStream `_match_bracket_child` resolves the real SL and TP child order IDs and writes them to `bracket:children:{account_id}:{entry_order_id}`. Online consumes them on TAKEN. | `captain-online/main.py:180-289`, `online/orchestrator.py:1260-1290` |
| Position dict construction | `is_nkd_trail = False` (bug F2), all other fields correct. Position appears in `captain:open_positions` Redis hash, GUI Trade panel shows it. | `online/orchestrator.py:1184-1297` |
| B7 monitor_positions | Resolves TP_HIT and SL_HIT on fill (correct exit price from broker since `bracket=True`), writes P3-D03 trade outcome row, publishes to `captain:trade_outcomes`. NKD-specific TIME_EXIT exemption (C9) is in place at `b7_position_monitor.py:316-319` so a 22h+ position is not force-flattened mid-session. | `b7_position_monitor.py:316-319` |
| Offline learning loop | Trade outcome triggers DMA / BOCPD / EWMA / Kelly updates per Category A spec. Independent of trail behaviour. | n/a |

### 5.2 What will NOT work (F2 impact)

| Stage | Behaviour | Code that doesn't run | Visible effect |
|---|---|---|---|
| Trail block first poll | **Skipped** at `b7b_nkd_trail.py:533` because `is_nkd_trail=False`. No jitter sampling, no Phase A/B/C transition, no `modify_order` call. | `_scan_one_trail` (entire function body) | GUI `current_phase`, `current_buffer`, `current_stop_price`, `modify_seq` columns stay empty/null for the lifetime of the trade. |
| Phase A→B transition | Never happens. SL stays at static `entry ± $1,025`. | `compute_nkd_phase`, `apply_ratchet`, `compute_stop_price` (all unreached) | Position can earn unlimited theoretical profit, then give back the full $1,025 if it reverses. |
| Phase B/C step-down | Never happens. SL stays at static `entry ± $1,025`. | same | No `$1,000` step at +$2,000 profit, no `$450` tight trail at +$3,000 profit. |
| Isaac-tower jitter on SL | Never happens. Isaac's TP is at `4,450 + J` (B6 sampled), but the SL never trails so it doesn't have the matching `+J`. | `effective_buffer = max(buffer + jitter_j, _EFFECTIVE_BUFFER_FLOOR)` (`b7b_nkd_trail.py:685`) | Isaac tower has asymmetric J on broker prices — TP uses `J_a`, SL uses `0`. Violates Isaac's spec but doesn't cause rejections or losses. |
| D34 persistence | Never written. | `_persist_state_row` (unreached) | `p3_d34_nkd_trail_state` table stays empty for tonight's trade. Post-mortem analysis loses the per-poll snapshot trail. |
| Compliance modify check (C8) | Never called. | `compliance_modify_check` (unreached from trail) | Not an issue — there are no modify attempts to compliance-check. |
| MarketStream NKD subscription guard (C10) | Still works because `ensure_nkd_subscribed` is called early in `scan_nkd_trails` *before* the per-position `if not is_nkd_trail` filter. | `b7b_nkd_trail.py:522-526` | NKD WebSocket subscription persists through the 22h hold even though the trail logic doesn't engage. So this protects against subscription drops but only because of an accidental ordering. |

### 5.3 Risk-of-loss comparison

| Scenario | With trailing (intended) | Without trailing (tonight) |
|---|---|---|
| Price moves $-1,025 from entry | SL fills, lose $1,025 | SL fills, lose $1,025 (same) |
| Price moves $+2,000 then reverses to $0 | Phase B engages, SL ratchets to entry-side $1,000 → flat exit | SL fills at entry - $1,025 → lose $1,025 |
| Price moves $+3,000 then reverses to entry | Phase C engages, SL ratchets to mark - $450 → exit at +$2,550 | SL fills at entry - $1,025 → lose $1,025 |
| Price moves $+4,450 (TP hit) | TP fills, win $4,450 | TP fills, win $4,450 (same) |
| Price oscillates around +$2,500 for 4h | Phase B trails as mark climbs, locks in incremental gains | SL stays static at entry - $1,025; volatility doesn't matter |

The asymmetry is: **wins are unchanged, but losses on reversal are 100% of the initial risk** instead of being capped by the trail. For a strategy whose edge comes from the trailing capture (the explicit NKD pivot thesis), this nullifies most of the upside.

---

## 6. Why Isaac tower placed an unprotected SELL (hypothesis only)

I cannot fully diagnose Isaac tower's behaviour from Nomaan tower's CSV. Two plausible hypotheses, in order of likelihood:

1. **Both towers took the trade simultaneously due to parity-key drift, and Isaac tower's `_auto_execute_signal` hit a path where the bracket call raised an exception** (e.g. transient network blip) and the fallback path threw before placing SL/TP. The `except TopstepXClientError` at `b3_api_adapter.py:520-522` returns `{"order_id": None, "status": "ERROR"}` — the position is opened by the fallback entry but the SL/TP placement never runs, leaving the position unprotected.

   - Counter: the parity hash is content-deterministic, so this would only happen if the signal payload differed between towers (e.g. different signal_id, different timestamp due to clock drift, different sorted-asset-set).

2. **Isaac tower took the trade via a different code path** — possibly the manual /api/commands TAKEN endpoint hit by a stray GUI click. That path runs `route_command` → publishes TAKEN_SKIPPED → Online opens the position dict, but the actual broker-side bracket placement never happens because `_auto_execute_signal` was bypassed. Online's `_handle_taken_skipped` doesn't itself call the broker; it just records the position.

To verify which hypothesis is correct, you'd need Isaac tower's order CSV and the captain-command log for the same timestamp window. Both files would also confirm what `INSTANCE_PARITY` env var Isaac tower was actually running with.

In either case, F2 (sanitise_for_api gap) makes the trail block inert on Isaac tower too — so even after a hypothetical fix to the broker-side placement on Isaac, the trail still won't engage there either until F2 is patched.

---

## 7. Recommended actions before tonight's APAC window

### Option A (operator-conservative) — run tonight on static SL

**Decision rule:** if NKD's expected-value math is still positive without the trailing capture (i.e. you're comfortable taking pure breakout trades with `$1,025` risk and `$4,450` reward = roughly 4.3R), run as-is.

**Pre-market gate (5 minutes):**

1. Confirm C14/C15/C16 are on both towers via SHA parity check:
   ```fish
   git fetch origin; and git fetch multi-user
   test (git rev-parse HEAD) = (git rev-parse origin/main); and \
   test (git rev-parse HEAD) = (git rev-parse multi-user/main); \
       and echo "OK: both remotes synced" or echo "MISMATCH"
   ```
2. Confirm `bootstrap_production.py` has been re-run on both towers so the D00 NKD `locked_strategy` row has `sl_dollars_fixed: 1025`:
   ```fish
   command -v jq > /dev/null 2>&1; or sudo apt install -y jq
   curl -s -G "http://localhost:9000/exec" \
     --data-urlencode "query=SELECT locked_strategy FROM p3_d00_asset_universe WHERE asset_id='NKD' LATEST ON last_updated PARTITION BY asset_id" \
     | jq -r '.dataset[0][0]' \
     | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('sl_dollars_fixed=', d.get('sl_dollars_fixed'), '| is_nkd_trail=', d.get('is_nkd_trail'))"
   ```
   Expected: `sl_dollars_fixed= 1025 | is_nkd_trail= True`.
3. Confirm Isaac tower's `INSTANCE_PARITY` is `1`:
   ```fish
   # On Isaac tower:
   dco exec captain-online printenv INSTANCE_PARITY
   ```
   Expected: `1` (anything else means jitter won't apply on Isaac).
4. Acknowledge in the runbook (or in this audit) that the trail will not ratchet tonight, and that any position will sit at the initial `entry ± $1,025` SL. Plan to babysit the GUI Trade panel for the first NKD signal so you can verify visually that bracket placement succeeded (no rejection alerts in `captain:alerts`).

### Option B (cautious) — patch F2 before tonight

If you want the trail to actually run tonight, F2 is a 3-file, ~25-line fix and is low risk because non-NKD assets are unaffected (the fields just default to `None`/`False` and the trail block continues to skip them):

| File | Change | Lines |
|---|---|---|
| `captain-command/captain_command/blocks/b1_core_routing.py` | Add `is_nkd_trail`, `tp_dollars`, `snapped_d_init`, `jitter_x`, `jitter_y`, `jitter_j` to the dict returned by `sanitise_for_api`. | 131-153 |
| `captain-command/captain_command/blocks/b1_core_routing.py` | Add the same six keys to the TAKEN_SKIPPED publish in `route_command`. | 204-229 |
| `captain-online/captain_online/blocks/orchestrator.py` | Replace `"jitter_x": None, "jitter_y": None, "jitter_j": None` with the values from `data` (defence-in-depth defaults stay `None` so non-Isaac signals continue to work). | 1238-1240 |

After the patch:
- Re-run the full NKD validation suite from `PASSOVER_PROMPT.md` (11 test files).
- Add **two new end-to-end tests** that exercise the exact path that was broken:
  - `test_sanitise_for_api_preserves_nkd_trail_fields` — assert `sanitise_for_api(nkd_signal, ac, det)` returns a dict containing all six NKD keys with the right values.
  - `test_taken_skipped_threads_jitter_to_position_dict` — call `_handle_taken_skipped({...is_nkd_trail: True, jitter_j: 5.0, ...})` and assert `self.open_positions[-1]` has `is_nkd_trail=True` and `jitter_j=5.0`.
- Commit as C17 (new atomic commit), push to both remotes, verify SHA parity, then run the tower-side update sequence per `day_2/PLAN.md §4`.

**Risk of patching tonight:** very low. The change is purely additive (new keys on dicts). The b7b trail block's defensive first-poll re-sampling (`b7b_nkd_trail.py:660-669`) means even if Isaac tower's `jitter_j` doesn't quite thread through correctly, the trail still samples fresh and behaves sensibly (different J than the TP bracket, but no rejection).

**Risk of NOT patching tonight:** medium. The position will be protected by the broker-side OCO bracket SL at `entry ± $1,025`, but you lose all trailing benefit and the Isaac-tower jitter symmetry. If the strategy thesis depends on Phase B/C ratcheting, you're effectively running a static-SL ORB tonight.

### Option C (skip NKD tonight)

Disable NKD auto-execution for tonight while you patch F2 calmly:

```fish
# On both towers:
curl -s -G "http://localhost:9000/exec" \
  --data-urlencode "query=UPDATE p3_d00_asset_universe SET captain_status='PAUSED' WHERE asset_id='NKD'"
```

Use this if you'd rather not run *any* NKD trade until the trail is verified end-to-end.

---

## 8. Other items found during the audit (not blockers)

### 8.1 Fallback TP placed after SL failure → flatten (F4 elaborated)

`b3_api_adapter.py:474-510` (the separate-orders TP block) executes unconditionally after lines 400-455 (the SL block + emergency flatten). When the SL fails and the position is flattened by `close_position`, the TP is still placed against the now-flat position. The exchange accepts it (it's a working order with no underlying position requirement), and it sits there as an orphan until the operator cancels it.

Suggested fix: wrap lines 474-510 in `if not result.get("sl_failed"):` so the TP is only placed when the SL placement succeeded (or wasn't attempted because `sl_price` was None).

### 8.2 Jitter sampled twice on Isaac tower (F5 elaborated)

Per Isaac's spec (memory anchor #3343): "One signed J per trade, |J| ∈ [0.2, 20.0], added in dollars to BOTH the SL buffer AND the TP dollar target at broker-order time."

Current behaviour with F2 unfixed:
- B6 samples `J_a` and applies it to `tp_level = _tp_from_dollars(4450 + J_a, ...)` (`b6_signal_output.py:158-165`).
- Trail block never runs (F2), so the SL jitter `J_b` is never sampled.
- Net effect: TP uses `J_a`, SL uses `0`. Asymmetric, but no rejection.

Current behaviour after F2 is fixed:
- B6 samples `J_a` and applies to TP. Position dict carries `jitter_j = J_a`.
- Trail block first poll reads `pos.get("jitter_j")` (not None now), so it uses `J_a` for the SL too. ✓ Symmetric per-trade J.

The "defence-in-depth" first-poll sampling at `b7b_nkd_trail.py:658-669` only fires when `jitter_j` is `None`. Once F2 is fixed and the threading works, the defence-in-depth becomes a no-op for the normal path, and the trail correctly uses the same J as B6.

### 8.3 Trail block silently skips, no observability (related to F2)

`scan_nkd_trails:533` `continue`s without logging when `is_nkd_trail` is False. Combined with F2, this means a NKD trade with the trail "disabled" produces zero log lines from b7b. The empty D34 table is the only evidence.

Suggested improvement (independent of F2 fix): log INFO once per poll cycle if `scan_nkd_trails` saw NKD positions but skipped all of them due to `is_nkd_trail=False`. This would have flagged the bug on the first NKD trade.

### 8.4 `entry_price` in signal vs `actual_entry_price` from broker fill

For bracket orders, B3 sends `sl_ticks` and `tp_ticks` as *offsets from the actual fill price*, so the broker enforces the correct dollar distance regardless of signal-vs-fill slippage. ✓

For the separate-orders fallback path, B3 sends `sl_price = signal.sl_level` as an *absolute price*. If signal-vs-fill slippage exceeded the SL distance, the standalone STOP could land on the wrong side of the actual fill. With C15's `$1,025 = 205 NKD points` distance, this requires slippage > 205 points = ~0.33% of NKD price, which is extreme but not impossible during a flash event.

For robustness against extreme slippage, the fallback SL placement could be deferred until after `receive_fill` returns the actual fill price, then `sl_price` could be recomputed as `actual_fill ± $1,025 worth of points`. This is a small follow-up enhancement, not a blocker.

---

## 9. Decision matrix for tonight (yes/no on auto-execute NKD)

| Question | If YES | If NO |
|---|---|---|
| Will C15 prevent the two rejection messages from last night? | **Yes** — high confidence, traced end-to-end through code. | n/a |
| Will the bracket SL of `$1,025` be placed correctly? | **Yes** — `41 ticks` ≥ 4-tick minimum, on correct side of entry, slippage-tolerant. | n/a |
| Will the bracket TP of `$4,450` (Nomaan) or `$4,450 + J` (Isaac) be placed correctly? | **Yes** — verified in `_tp_from_dollars` + jitter sampling in B6. | n/a |
| Will the trailing-stop ratchet engage as the trade earns PnL? | **No** — F2 blocker. Position will sit at static `entry ± $1,025`. | If you want trailing tonight, patch F2 first (Option B above). |
| Will D34 record the per-poll snapshot of the trail state? | **No** — trail block doesn't run, so no rows written. | Post-trade analysis will rely on order log + B7 D03 outcome only. |
| Is the position protected against runaway loss? | **Yes** — broker-side OCO bracket SL fires at `entry ± $1,025`. | n/a |
| Will Isaac tower's TP have non-zero J? | **Yes on Nomaan** (J=0). **Yes on Isaac** (J ≠ 0, sampled in B6). | n/a |
| Will Isaac tower's SL have matching non-zero J? | **No** — trail block inert, SL stays at unjittered `$1,025`. | Asymmetric J between TP and SL, but no rejection. |

---

## 10. Tracking checklist for tomorrow morning (post-session review)

After the APAC window closes:

- [ ] Pull `orders_export.csv` from both towers for the NKD trade window.
- [ ] Confirm no `Invalid stop loss ticks` rejection (C15 working).
- [ ] Confirm no `Order price is outside allowed range` rejection (C15 working).
- [ ] Query D34 for the trade — expect **zero rows** (F2 unfixed) unless F2 was patched.
- [ ] Query D03 for the trade outcome — should be present from B7's monitor_positions.
- [ ] Confirm GUI Trade panel's `current_phase`, `current_buffer`, `current_stop_price`, `modify_seq` columns are empty for the NKD position (F2 unfixed) unless F2 was patched.
- [ ] If F2 was patched: confirm at least one `ON-B7B-NKD: modify OK signal=…` line in `captain-online` logs and at least one D34 row per phase transition.
- [ ] If Isaac tower placed orders this time, compare with Nomaan tower to confirm parity-key splitting worked correctly (only one tower took the trade).

---

## Appendix A — File references used in this audit

| File | Lines | Role |
|---|---|---|
| `captain-online/captain_online/blocks/b6_signal_output.py` | 100-220, 285-412 | NKD signal construction, fixed-$1025 SL, jitter sampling, _sl_from_dollars / _tp_from_dollars / _compute_sl / _compute_tp |
| `captain-online/captain_online/blocks/b7b_nkd_trail.py` | 62-148, 455-875 | Phase-A/B/C math, ratchet, compute_stop_price, scan_nkd_trails, _scan_one_trail, modify_order dispatch, D34 persistence |
| `captain-online/captain_online/blocks/orchestrator.py` | 1184-1297 | _handle_taken_skipped — position dict construction |
| `captain-command/captain_command/blocks/b1_core_routing.py` | 49-153, 195-229 | route_signal_batch, sanitise_for_api, route_command (TAKEN_SKIPPED branch) |
| `captain-command/captain_command/blocks/orchestrator.py` | 429-715 | _handle_signal, _check_parity_skip, _auto_execute_signal |
| `captain-command/captain_command/blocks/b3_api_adapter.py` | 230-522 | TopstepXAdapter.send_signal — bracket + fallback path |
| `shared/topstep_client.py` | 286-406 | place_order, place_bracket_order, modify_order |
| `shared/contract_resolver.py` | 100-137 | get_tick_size, tick_snap_outward |
| `config/contract_ids.json` | 47-53 | NKD `tick_size: 5.0`, `tick_value: 25.0` |
| `scripts/bootstrap_production.py` | 41-132 | NKD P2_STRATEGIES entry with `sl_dollars_fixed: 1025`, `is_nkd_trail: True` etc., `_build_locked_strategy` |
| `docs2/quick-fixes/NKD_Pivot/day_2/PLAN.md` | full | Authoritative C14/C15/C16 spec |
| `docs2/quick-fixes/NKD_Pivot/day_2/COMPLETION_CHECKLIST.md` | full | Day-1 status with spec deltas |

---

## Appendix B — Memory anchors

| ID | Date | Title |
|---|---|---|
| #3343 | 2026-05-19 | NKD Trading Specification Confirmed (Isaac spec) |
| #3342 | 2026-05-19 | NKD Trade Stop Loss and Trailing Stop Specification Confirmed |
| #3344 | 2026-05-19 | NKD Pivot Trading Logic Specification Clarified |
| #3362 | 2026-05-19 | NKD initial SL switched from OR-range derived to fixed $1025 with outward rounding (C15) |
| #3367 | 2026-05-19 | Commit C15 landed and synced: fixed $1025 SL with outward tick-snapping |
| #3361 | 2026-05-19 | Added _sl_from_dollars function for asymmetric outward stop-loss rounding |
| #3358 | 2026-05-19 | Commit C14 landed: NKD phase boundaries refactored to step-ladder architecture |
| #3391 | 2026-05-19 | Full NKD validation suite passes with 184/184 tests confirming C14-C16 implementation |
| #3380 | 2026-05-19 | Inverted Isaac jitter test to validate broker price divergence post-C16 |
| #3334 | 2026-05-18 | NKD Pivot Infrastructure Already Partially Implemented |
| #3331 | 2026-05-18 | System configured in MANUAL execution mode despite RTS6 compliance enabled |
| #3317 | 2026-05-18 | Commit e7bb969: C10 NKD Subscription Persistence Guard Deployed |

---

**End of audit.**
