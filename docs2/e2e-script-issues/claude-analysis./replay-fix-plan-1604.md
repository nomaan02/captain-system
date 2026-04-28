# Replay Harness Fix Plan — 2026-04-16

## Hard constraints

1. **No production/live code touched.** No edits to `captain-online/`, `captain-offline/`, `captain-command/`, `captain-gui/`, or `shared/`. Goal is a replay that accurately reflects what live blocks would do, without mutating them.
2. **Only file touched:** `scripts/replay_full_pipeline.py`.
3. Live code behavior remains exactly as Isaac specced it. If a bug exists in live code (e.g. B6 None TP/SL fallback), the replay must **expose it clearly** rather than paper over it.
4. All behavior observed in the replay must be traceable to block logic, not to harness deficiencies.

## Files touched vs. read-only

| File | Access | Purpose |
|------|--------|---------|
| `scripts/replay_full_pipeline.py` | **Write** | All edits go here. |
| `captain-online/captain_online/blocks/b8_or_tracker.py` | Read-only | Monkey-patch target (datetime). |
| `captain-online/captain_online/blocks/b1_data_ingestion.py` | Read-only | Read-only contract; we seed the upstream `quote_cache` it depends on. |
| `shared/topstep_stream.py` | Read-only | Exposes the `quote_cache` singleton we seed. |
| `captain-online/captain_online/blocks/b6_signal_output.py` | Read-only | We only observe its output; don't patch. |
| `captain-online/captain_online/blocks/b5c_circuit_breaker.py` | Read-only | We only surface its diagnostic output. |

---

## Phase 0 — Seams verified (done, no further discovery needed)

Discovery pass already complete. Anchors:

| Seam | Location | How the harness uses it |
|------|----------|-------------------------|
| `datetime.now(_ET)` call sites in OR tracker | `b8_or_tracker.py:227, 279, 299` | Monkey-patch `b8_or_tracker.datetime` in-module to a clock whose `.now` returns a harness-controlled time. |
| `_ET` constant | `b8_or_tracker.py:33` (`_ET = pytz.timezone("America/New_York")`) | Reuse: the harness clock returns bar-time in ET. |
| `quote_cache` singleton | `shared/topstep_stream.py:110` | The replay imports it and calls `quote_cache.update(contract_id, {...})` before `run_phase_a`. |
| `quote_cache.update(contract_id, quote)` | `shared/topstep_stream.py:81-89` | Accepts `{"lastPrice": float, "timestamp": iso8601}` dicts. |
| `_has_valid_timestamp` | `b1_data_ingestion.py:635-668` | Reads `quote_cache.get(contract_id)` and checks `lastPrice` plus `timestamp < 5 min old`. |
| Current replay entry point | `scripts/replay_full_pipeline.py:461-615` (`run_replay` / `main`) | Insertion points for cache seed + clock patch. |
| OR loop feed | `scripts/replay_full_pipeline.py:534-569` | Wrap in a clock-driver context manager. |
| Signal log line | `scripts/replay_full_pipeline.py:449-456` | Defensive format fix for None TP/SL. |

### Allowed APIs (from real code, not invented)

- `quote_cache.update(contract_id: str, quote: dict) -> None` — merges non-None fields onto existing entry.
- `quote_cache.get(contract_id: str) -> dict | None` — returns copy or None.
- `unittest.mock.patch` (stdlib) — correct tool for monkey-patching the `datetime` symbol in a module's namespace.

### Anti-patterns explicitly disallowed

- Do **not** add a `clock_fn` parameter to `ORTracker.__init__`. That's a production API change.
- Do **not** change `_has_valid_timestamp` or the incident message. That's production code.
- Do **not** modify `_compute_tp` / `_compute_sl`. The latent None-TP/SL bug stays a bug the replay must *reveal*, not fix.
- Do **not** patch `time.time()` globally or use `freezegun` at module level — blast radius is too wide; use a scoped `contextlib.contextmanager` around the tick loop only.
- Do **not** invent a method on `QuoteCache` that doesn't exist. Use `update()` / `get()` only.

---

## Phase 1 — Seed `quote_cache` before Phase A

**Objective:** Make `_has_valid_timestamp` pass for every session asset with a fresh synthetic quote, so the Data Moderator takes the same path it would take in live with a healthy MarketStream.

**Where to insert:** New helper `_seed_quote_cache(target_date, session_type)` in `scripts/replay_full_pipeline.py`, called from `run_replay` immediately after `client.authenticate()` (line 486) and before `run_phase_a(session_id)` (line 507).

**What it does:**

1. Imports `from shared.topstep_stream import quote_cache`.
2. Picks a reference price per asset — use the *first bar's close* (already fetched into `all_bars[asset]`), or a single fresh bar lookup if seeding must precede the bar fetch.
3. For each `(asset, contract_id)` from `CONTRACT_MAP`, calls:
   ```python
   quote_cache.update(contract_id, {
       "lastPrice": float(reference_price),
       "timestamp": datetime.now(timezone.utc).isoformat(),
   })
   ```
   Using *real wall-clock UTC* for the timestamp satisfies the `< 5 min` staleness check in `_has_valid_timestamp` (line 661). No need for bar-time here — the staleness check is about feed health, not bar time.
4. Logs a single summary line: `Seeded quote_cache for 8/8 assets`.

**Order consideration:** Currently bars are fetched before Phase A. Either:
- (A) move the seed call AFTER the bar fetch and use the first bar's close — simplest; or
- (B) do a dedicated `client.fetch_last_bar(contract_id)` call. (A) is cleaner and avoids an extra API roundtrip.

**Verification:**
- Run replay; grep logs for `INC-` — should see **zero** `missing timezone offset` incidents.
- `docker exec captain-system-questdb-1 curl -s "http://localhost:9000/exec?query=SELECT+count(*)+FROM+p3_d21_incidents+WHERE+incident_type='DATA_QUALITY'+AND+created_at+>+systimestamp()-5m"` → 0.

---

## Phase 2 — Clock injection for the OR tracker (monkey-patch, scoped)

**Objective:** Make `b8_or_tracker` state transitions advance with the synthetic bar time, so OR high/low accumulate across all ticks in the 09:30–09:35 window instead of collapsing to one tick.

**Implementation approach:** Use `unittest.mock.patch.object` on the `datetime` symbol imported into the `b8_or_tracker` module, scoped to a context manager around the tick-feed loop only.

**Where to implement:** A new context manager `_replay_clock(initial: datetime)` in `scripts/replay_full_pipeline.py`, wrapping the `for ts, asset, cid, bar in merged_bars` loop (currently lines 543-569).

**Sketch:**

```python
import contextlib
from unittest.mock import patch
from captain_online.blocks import b8_or_tracker

class _FrozenDatetime:
    """Stand-in for `datetime` where .now(tz) returns a harness-set time.
    All other datetime classmethods delegate to the real class."""
    _current: datetime | None = None

    @classmethod
    def set(cls, t: datetime) -> None:
        cls._current = t

    @classmethod
    def now(cls, tz=None):
        if cls._current is None:
            return datetime.now(tz)
        return cls._current.astimezone(tz) if tz else cls._current

    @classmethod
    def combine(cls, *a, **kw):
        return datetime.combine(*a, **kw)

    # delegate fromisoformat, strptime, etc. to real datetime as needed

@contextlib.contextmanager
def _replay_clock():
    with patch.object(b8_or_tracker, "datetime", _FrozenDatetime):
        yield _FrozenDatetime
```

In the tick loop:

```python
with _replay_clock() as clk:
    for ts, asset, cid, bar in merged_bars:
        clk.set(ts)              # advance harness clock to bar time
        # ... feed high/low/close ticks ...
        tracker.check_expirations()
```

Also advance the clock before the `tracker.register_asset(asset, session_date=target_date)` calls on lines 518-520 so the initial state construction sees a time consistent with bar-feed time (set clk to `or_start - 1 minute` of `target_date`).

**Important:** `patch.object(b8_or_tracker, "datetime", ...)` only affects the `datetime` name inside `b8_or_tracker`'s module namespace. It does NOT monkeypatch the global `datetime` module. The replay process exits when done; no cross-process, no cross-module leakage.

**Minimum datetime surface to satisfy b8_or_tracker:**

Re-reading `b8_or_tracker.py`: it calls `datetime.now(_ET)` on three lines and `datetime.combine(...)` on line 72. Those are the only `datetime.*` classmethods. The `_FrozenDatetime` shim only needs `now` and `combine` — everything else untouched.

**Verification:**
- Log should show `OR COMPLETE: ES — high=X low=Y range=Z` with `Z > 0` and `tick_count > 1` for every asset that gets bar data.
- Breakout prices should be strictly outside `[or_low, or_high]` with non-zero penetration.
- No regression to production `b8_or_tracker` tests (this is a harness-only change — no production tests run against the replay).

---

## Phase 3 — Diagnostic summary output

**Objective:** Make Issue 2 (CB blocks) and Issue 4 (None TP/SL) legible without digging through logs.

**Where:** New `_print_replay_summary(phase_a, signals_by_asset)` function called at the end of `run_replay` (after the existing "REPLAY COMPLETE" block, lines 590-601).

**Three tables:**

### Table A — Kelly sizing → CB gate per (asset, account)

Columns: `asset | account | kelly_f | rg_adj | raw_contracts | final_contracts | rho_j | L_halt | CB_reason`.

Source: `phase_a["b4"]` (Kelly output), `phase_a["b5c"]` (CB block reasons — already captured in `block_reason` per-account). If `b5c` doesn't expose `rho_j` currently, derive it in the summary from `final_contracts * (sl_distance * point_value + fee)` using existing strategy and assets_detail already in `phase_a`.

### Table B — Signal outcomes per asset

Columns: `asset | direction | entry | tp | sl | tp_valid | sl_valid | confidence | skipped_reason`.

`tp_valid` / `sl_valid` are booleans: `False` when None or ≤ 0. **Flag loudly** (print a red `!! ISSUE 4 !!` marker after the table) if any signal has `tp_valid=False` or `sl_valid=False`. This is the Issue 4 exposure mechanism.

### Table C — OR per asset

Columns: `asset | or_high | or_low | or_range | tick_count | direction | entry_price`.

From `tracker.get_state(asset).to_dict()`. `or_range == 0` flags as `!! ISSUE 3 (harness clock failure) !!` so a regression is obvious.

**Verification:**
- Run replay; summary tables print.
- On first run (pre-Phase-2 fix), Table C shows or_range=0 for every asset with a loud ISSUE 3 marker. On post-Phase-2 run, or_range > 0.
- If Issue 4 still triggers post-fix, Table B flags it loudly and we know it's not harness-induced.

---

## Phase 4 — Defensive logging for the signal log line

**Objective:** Stop the traceback from spewing while still reporting anomalies.

**Where:** `scripts/replay_full_pipeline.py:449-456`.

**Current (buggy):**

```python
logger.info("  SIGNAL: %s %s x%s — TP=%.2f SL=%.2f confidence=%s",
             sig.get("direction"), sig.get("asset"),
             sig.get("per_account", {}).get(
                 list(sig.get("per_account", {}).keys())[0] if sig.get("per_account") else "?", {}
             ).get("contracts", "?"),
             sig.get("tp_level", 0), sig.get("sl_level", 0),
             sig.get("confidence_tier", "?"))
```

**Replacement:**

```python
tp = sig.get("tp_level")
sl = sig.get("sl_level")
per_acc = sig.get("per_account") or {}
contracts = next(iter(per_acc.values()), {}).get("contracts", "?") if per_acc else "?"
logger.info(
    "  SIGNAL: %s %s x%s — TP=%s SL=%s confidence=%s",
    sig.get("direction"), sig.get("asset"), contracts,
    f"{tp:.2f}" if isinstance(tp, (int, float)) else "None",
    f"{sl:.2f}" if isinstance(sl, (int, float)) else "None",
    sig.get("confidence_tier", "?"),
)
```

This preserves readability for valid signals and prints a literal `None` for broken ones — which Table B in Phase 3 already flags.

**Verification:**
- No `--- Logging error ---` blocks on stderr, regardless of TP/SL values.

---

## Phase 5 — Verification pass

Run sequence:

1. `cd ~/captain-system && source .venv/bin/activate.fish`
2. `set -x PYTHONPATH .:captain-online:captain-command`
3. `python3 scripts/replay_full_pipeline.py --date 2026-04-14 --session NY`

Expected outcome:

| Signal | What to check |
|--------|---------------|
| Quote cache seeding worked | No `DATA_QUALITY — missing timezone offset` incidents. |
| OR clock patch worked | Every asset's `OR COMPLETE` log has `range > 0` and `tick_count > 10` (at least 2 ticks per minute × 5 min). |
| CB decisions intelligible | Table A prints all 8 assets × 1 account with block reasons. |
| Issue 4 exposed honestly | Table B flags any signal where TP or SL is None. |
| No stderr traces | `--- Logging error ---` absent from full run. |

After Phase 5 passes, Isaac decisions remain outstanding:

- **Issue 2 (Kelly/CB tuning):** requires spec-level decision on whether `c=0.5 × e=0.01 = 0.5%` is correct for this multi-asset portfolio, or Kelly output is oversizing micros. Not a harness fix — flag for separate conversation.
- **Issue 4 latent real bug:** even when OR forms cleanly, ensure no code path produces None TP/SL. If Table B is clean after Phase 2, the replay doesn't trigger it — but the spec review (separate from this plan) should decide whether B6 needs a defensive floor.

---

## Execution checklist (what I'll do when you green-light)

1. ☐ Add `_seed_quote_cache` helper + call in `run_replay` (Phase 1).
2. ☐ Add `_FrozenDatetime` shim + `_replay_clock` context manager, wrap tick loop (Phase 2).
3. ☐ Add `_print_replay_summary` with Tables A/B/C (Phase 3).
4. ☐ Fix signal log line (Phase 4).
5. ☐ Commit once with a single message describing harness-only changes.
6. ☐ Push to both `origin` and `multi-user` remotes.
7. ☐ Ask you to rerun on the tower and share output; I analyze.

Nothing above modifies live code. Nothing above changes block behavior. Every fix is contained to the replay harness so future runs present an accurate picture of whether the live blocks are correctly seeded and behaving for market open.

---

## Open questions for you before execution

1. Are you OK with the replay using real wall-clock UTC for quote timestamps (Phase 1), or do you want bar-time? *Recommendation: wall-clock — the staleness check is about feed health, not historical bar recency.*
2. Any objection to writing all three summary tables (A/B/C) rather than one? *Recommendation: keep all three — each one targets a different flagged issue.*
3. Confirm the one commit + push-to-both-remotes flow matches what you want for this change.
