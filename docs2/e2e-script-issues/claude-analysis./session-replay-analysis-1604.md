# Replay Pipeline E2E Analysis — 2026-04-16

Analysis of the five issues flagged in `session-replay-script-issues-1604.md`, mapped against the actual code paths invoked by `scripts/replay_full_pipeline.py`. For each issue I distinguish between:

- **REAL (live-impacting)** — will affect production trading.
- **REPLAY ARTIFACT** — exists only because the replay harness doesn't fully reproduce the live environment; live is unaffected.
- **COSMETIC / LATENT** — a bug exists but under current conditions it doesn't change trading behavior.

Severity rankings are my own — confirm against Isaac's spec before treating as final.

---

## ISSUE 1 — "Data for X missing timezone offset. Rejecting."

### What the code actually does

`captain-online/captain_online/blocks/b1_data_ingestion.py:444-451` calls `_has_valid_timestamp(asset_id)` inside the **Data Moderator**. The function (line 635-668) checks:

1. Does `quote_cache` have a quote for the asset's contract ID?
2. Does that quote have a `lastPrice`?
3. If there's a timestamp, is it within 5 minutes of now?

If any of those fail, the incident text says *"missing timezone offset. Rejecting."*

### Why it fires in the replay

The replay runs the host-side script. It never starts the MarketStream WebSocket, so `quote_cache` is empty for every asset. The check fails for all eight assets, and the incident text is emitted.

Importantly — read the loop: on failure the code does `flagged_count += 1; continue`. It **does NOT set `DATA_HOLD` or filter the asset out.** Only the subsequent `price_deviation > 5%` and explicit `DATA_HOLD` paths actually remove an asset. So every flagged asset still flows through B2→B6 in this run. That's why you see B4 Kelly sizing running on the same assets immediately after these incidents.

### Classification

- **REPLAY ARTIFACT** for the trigger. In live, MarketStream populates `quote_cache` on every tick; this check only fires when the feed has actually gone stale.
- **REAL cosmetic bug** — the incident message is wrong. The check has nothing to do with timezone offsets; it's an "is the MarketStream quote fresh" check. The message should say something like *"no fresh quote in cache (stale or missing)"*. This is creating misleading P3-D21 incidents.
- **LATENT concern** — the wording *"Rejecting"* implies the asset is dropped, but the code only logs an incident and continues. Either the message lies about intent, or the intended rejection logic is missing. Worth clarifying against the spec for the Data Moderator.

### Live-trading impact

Zero under normal conditions. Will fire correctly (and noisily) when the feed actually stalls > 5 min, and currently produces a misleading incident message.

---

## ISSUE 2 — Circuit Breaker Layer 1 blocking 4 assets

### What the code actually does

`captain-online/captain_online/blocks/b5c_circuit_breaker.py:263-293` — Layer 1 preemptive halt:

```
L_halt = c * e * A
rho_j  = contracts * (sl_distance * point_value + fee_per_trade)
BLOCK  iff |L_t| + rho_j >= L_halt
```

From `tsm.topstep_params` defaults: `c=0.5`, `e=0.01`.
Account balance `A = $150,000`.

So `L_halt = 0.5 × 0.01 × 150000 = $750`. That matches the log: `L_halt=750`.

The log rows from the replay:

| Asset | rho_j | Interpretation |
|-------|-------|----------------|
| MNQ   | $1,004 | ~70-80 micro contracts × (SL pts × $2/pt + fee) |
| MES   | $2,208 | ~80+ micro contracts × (SL pts × $5/pt + fee) |
| M2K   | $1,825 | similar |
| MYM   | $811   | similar |

### Classification

- **NOT a code bug.** The CB is behaving exactly per PG-27B spec.
- **REAL tuning concern.** `L_halt = 0.5% of balance` is intentionally conservative, but combined with Kelly sizing that produces 70-80+ micro contracts per asset, every micro gets blocked. Two candidate root causes:
  1. Kelly sizing output is oversized for micros because point values are small relative to the fraction. Needs review against PG-24 Kelly L6→L7 sizing rules.
  2. `c=0.5 × e=0.01` is too tight for a multi-asset portfolio — the preemptive layer was originally calibrated for a 1-2-asset flow.
- **REPLAY ARTIFACT contribution:** with OR range=0 (see Issue 3), `sl_distance` may be falling back to a non-zero default (typically 4 points), making rho_j reflect a worst-case SL. In a live breakout with a proper or_range, SL distance would scale with the actual OR and could be materially different.

### Live-trading impact

This will apply identically in live. If Kelly sizing routinely emits dozens of micro contracts, L1 will block those signals on a $150k account. **This is either correct protective behavior or a symptom of oversized Kelly — needs decision from Isaac.**

### Follow-up action

Log a tuning investigation. Compare live Kelly sizing output for micros against the expected contracts count per PG-24. Confirm `c=0.5, e=0.01` is correct for the multi-asset configuration.

---

## ISSUE 3 — OR range = 0 for every asset  ***MOST CRITICAL IN THIS LOG***

### What the code actually does

`captain-online/captain_online/blocks/b8_or_tracker.py:255-287, 325-358`.

The OR state machine uses **`datetime.now(_ET)` — wall-clock time** — to gate state transitions:

1. First tick: if `now_time >= session.or_start` → `WAITING → FORMING`, seed `or_high = or_low = first_price`, `tick_count=1`.
2. Subsequent ticks in FORMING: if `now_time >= session.or_end` → **immediately** `FORMING → COMPLETE` and check that same tick for breakout.
3. In COMPLETE: check breakout on any tick that crosses or_high or or_low.

### Why the replay produces range=0

You ran the replay at **21:28 wall-clock ET on 2026-04-14**, feeding 1-min bars from the real 09:30 NY session. The OR window in `session_registry.json` is `09:30–09:35`. At 21:28 wall-clock:

- `now_time (21:28) >= or_start (09:30)` → true, so the first synthetic tick correctly enters FORMING.
- On the **very next synthetic tick in the same loop iteration**, `now_time (21:28) >= or_end (09:35)` → true, so FORMING → COMPLETE runs with only 1 tick recorded. At that moment `or_high == or_low == first_tick_price`, so `or_range = 0.0000`.
- The breakout check at the tail of that `_update_state` call then immediately flips to BREAKOUT_LONG / BREAKOUT_SHORT on the same tick because the price differs from the seeded high/low.

That's exactly what the log shows:

```
OR FORMING: ES — first tick 7070.5000 at 16:28:24.196678
OR COMPLETE: ES — high=7070.5000 low=7070.5000 range=0.0000 (1 ticks)
OR BREAKOUT SHORT: ES — price=7067.5000 < OR low=7070.5000, or_range=0.0000
```

### Classification

- **PURE REPLAY ARTIFACT for the range=0 outcome.** In live trading the clock advances continuously; during the 5-minute window 09:30–09:35 ET, `datetime.now(_ET)` is actually inside the window, and ticks accumulate into or_high/or_low as intended. Live OR will resolve correctly.
- **REAL concern for the replay harness itself.** Currently the replay does NOT validate OR tracking end-to-end. Any test of OR, SL/TP sizing via or_range, AIM-15 opening-volume contribution to the ratio, B5 quality gate based on expected edge, etc. is running on a meaningless `or_range = 0`. If your goal is "prove the full pipeline works before go-live," this is a hole — the OR path is effectively untested.

### Fix options (for the replay, not live)

Either of the below would make the replay honest:

1. **Inject a clock.** Refactor `b8_or_tracker` to accept a `clock_fn: Callable[[], datetime]` (default `lambda: datetime.now(_ET)`). The replay constructs an `ORTracker` whose clock follows `bar.timestamp` as ticks are fed.
2. **Monkey-patch `datetime.now` in the replay process.** Ugly but localized to the harness — zero live impact.

Option 1 is the clean path and would also unlock proper unit testing of the OR tracker.

### Live-trading impact

**Zero impact in live.** But the replay's assertion "signals would have fired correctly" is currently unverifiable for anything that depends on or_range. In live, the OR forms properly over the 5-minute window.

---

## ISSUE 4 — Signals publish with TP/SL as None

### What the code actually does

`captain-online/captain_online/blocks/b6_signal_output.py:216-257`:

```python
def _compute_tp(strategy, features, direction, asset_id):
    or_range = features.get("or_range")
    entry = features.get("entry_price")
    if or_range and entry:
        tp = entry + (tp_multiple * or_range) * direction
    else:
        tp = strategy.get("tp_level")   # fallback
    ...
```

Same pattern for SL. `0` is falsy, so when `or_range == 0.0` the `or_range and entry` guard takes the `else` branch, which reads `tp_level` / `sl_level` from the locked strategy dict.

The locked strategies (P2-D06 `locked_strategy` JSONs per asset) don't store hard-coded `tp_level` / `sl_level` — they store `(m, k, OO)` plus TP/SL *multiples*. So `strategy.get("tp_level")` returns `None`, and the signal is emitted with `tp_level=None`, `sl_level=None`.

### Classification

- **REPLAY ARTIFACT trigger** — or_range=0 only because Issue 3.
- **REAL latent bug** — regardless of the trigger, any path where or_range is absent, zero, or falsy produces a signal with None TP/SL. B6 should either:
  - Compute TP/SL from an absolute `SL points × tick` default floor when or_range is unusable, **or**
  - Refuse to publish the signal and log a proper B6 skip reason (mirror the `or_direction=None` skip that already exists on line 71 of the log for ES).

In live this would fire if:
- A breakout happens within the very first tick of OR close (tick_count=1 edge),
- MarketStream delivers a glitched or_high == or_low,
- Any future bug upstream lets or_range leak through as 0.

And the signal would propagate to `captain-command B3 api adapter`, where a bracket order with `null` TP/SL would either crash the order builder or — worse — place an order with unbounded downside.

### Live-trading impact

Latent but real. **Fixable independently of the OR replay issue** and should be fixed before live — it's a defense-in-depth concern.

### Fix sketch

In `_compute_tp` / `_compute_sl`:

```python
if or_range and or_range > 0 and entry:
    ...
else:
    tp = strategy.get("tp_level")
if tp is None:
    return None  # let caller skip the signal
```

And in the caller (`_build_signal` or wherever `tp_level=None` lands): skip publishing and log a `MISSING_TP_SL` skip reason against the per-account state, same pattern as `or_direction=None`.

---

## ISSUE 5 — Recurring `TypeError: must be real number, not NoneType` in logging

### What the code actually does

`scripts/replay_full_pipeline.py:450`:

```python
logger.info("  SIGNAL: %s %s x%s — TP=%.2f SL=%.2f confidence=%s",
            sig.get("direction"), sig.get("asset"), ...,
            sig.get("tp_level", 0), sig.get("sl_level", 0), ...)
```

The default `0` in `sig.get("tp_level", 0)` **only** kicks in if the key is missing. If the key exists but the value is `None` (which is exactly what Issue 4 produces), `.get()` returns `None`, and `%.2f % None` raises.

### Classification

- **COSMETIC** — the `Logging error` traceback is emitted to stderr but `logger.info` swallows it; the `REPLAY COMPLETE` section still runs.
- Downstream of Issue 4 — will disappear once TP/SL are never None.

### Fix

Two options:

1. Fix the root cause (Issue 4) — the `None` values stop existing, and this log line works.
2. Defensive formatting for readability during debugging:
   ```python
   tp = sig.get("tp_level")
   sl = sig.get("sl_level")
   logger.info("  SIGNAL: %s %s x%s — TP=%s SL=%s confidence=%s",
               sig.get("direction"), sig.get("asset"), contracts,
               f"{tp:.2f}" if tp is not None else "None",
               f"{sl:.2f}" if sl is not None else "None",
               sig.get("confidence_tier", "?"))
   ```

Both fixes are independent and compatible. Recommend doing the defensive logging regardless — the replay is a diagnostic harness; it should never throw while reporting an anomaly.

---

## Summary table

| # | Short name                         | Classification                 | Live impact?      | Priority |
|---|------------------------------------|--------------------------------|-------------------|----------|
| 1 | "missing timezone offset" incident | Replay artifact + cosmetic msg | No (misleading)   | Low      |
| 2 | CB L1 blocking micro signals       | Spec-correct; possible tuning  | Yes               | **High (decision needed from Isaac)** |
| 3 | OR range = 0                       | Pure replay artifact           | No (live fine)    | **High — blocks meaningful e2e replay** |
| 4 | Signals with None TP/SL            | Latent real bug (Issue 3 exposed it) | Yes (edge cases) | **High — pre-live fix**  |
| 5 | Logging TypeError on None          | Cosmetic; downstream of #4     | No                | Low      |

---

## What I need from you next

Confirm the classifications above, then I propose we work through them in this order:

1. **Issue 3** — add clock-injection to `b8_or_tracker.ORTracker` so the replay advances time from bar timestamps. Without this fix, Issues 2 and 4 can't be accurately diagnosed in the replay.
2. **Issue 4** — make B6's TP/SL compute robust to missing/zero or_range and refuse to emit signals with None pricing.
3. **Issue 5** — defensive logger format (tiny; bundle with #4).
4. **Issue 2** — rerun the replay after #1 fixes OR. If L1 still blocks most micros with realistic SL distances, escalate to a Kelly/CB tuning conversation with Isaac.
5. **Issue 1** — fix the misleading incident message; decide whether the "rejection" wording implies missing filter logic or just a misnomer.

None of these are blocking the system from compiling or running; #3 + #4 are the only two that can actually matter pre-launch, and #4 is the only one that will matter once live.
