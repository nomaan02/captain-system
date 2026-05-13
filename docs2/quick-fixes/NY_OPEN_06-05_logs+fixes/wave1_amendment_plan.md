# Wave 1 Amendment Plan — 2026-05-06 NY-Open Blockers

**Status:** PLAN ONLY — no code or scripts executed yet.
**Author:** prepared 2026-05-07.
**Source:** `all_logs.md`, `all_logs_truncated_NY_open_2026-05-06.md`.

---

## Phase 0 — Diagnosis (already completed)

Both Wave 1 BLOCKING issues share a single underlying cause: **stale Python
`sys.modules` cache in the running `captain-offline` container.** The fix is
in two parts: an operational reset, then defensive code that prevents the same
class of failure from ever silently swallowing trade learning again.

### Bug 1 — `qexecute` ImportError

**Observed:**
```
ImportError: cannot import name 'qexecute' from 'shared.questdb_client'
  (/app/shared/questdb_client.py)
```

**Root cause (verified):**

| Commit | Date (BST) | What it added |
|---|---|---|
| `9aefcb5` | 2026-05-06 13:22 | `qexecute` helper in `shared/questdb_client.py` |
| `8e4064c` | 2026-05-06 13:50 | Decimal structural marker in `shared/decimal_json.py` |
| `710ccb6` | 2026-05-06     | 134 INSERT sites migrated to `qexecute` |

The `captain-offline` process on each tower started **before** these commits
landed on disk. `shared/` is bind-mounted (`./shared:/app/shared:ro` per
`docker-compose.yml` L56) so the file content WAS updated at the FS level
when the towers `git pull`-ed, but Python had already cached the old
`shared.questdb_client` module in `sys.modules`. When `_handle_signal_outcome`
performed its first deferred import of `b1_dma_update`, that submodule's
`from shared.questdb_client import get_cursor, qexecute` resolved against the
stale cached module → `ImportError`.

The `from shared.questdb_client import …` statement is at module top of:

- `captain-offline/captain_offline/blocks/b1_dma_update.py` L4
- `captain-offline/captain_offline/blocks/b1_aim16_hmm.py` L7
- `captain-offline/captain_offline/blocks/b8_kelly_update.py` L5
- (and several more `b*` blocks — ALL deferred-imported by the orchestrator)

The inner `try/except Exception` in `_handle_signal_outcome` (orchestrator.py
L373-473) catches the `ImportError`, logs `"Error processing signal outcome
for %s"`, and **then `_redis_listener` ACKs the message anyway** (L233).
That is why yesterday's lost learning is **NOT** in the Redis pending list —
the messages were acknowledged off the consumer group despite failing
processing.

### Bug 2 — `float() argument must be … not 'dict'`

**Observed:**
```
ERROR captain_offline.blocks.orchestrator:
  Stream listener error: float() argument must be a string or a real number,
  not 'dict' — reconnecting in 1s
```

**Root cause (verified):**

`commit 8e4064c` (2026-05-06 13:50 BST) introduced the structural marker:

```python
# shared/decimal_json.py L42-48
def default(self, obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return {"__type__": "Decimal", "value": format(obj, "f")}
```

Real-trade outcomes (`captain-online`'s `b7_position_monitor._publish_trade_outcome`)
emit `pnl: net_pnl` where `net_pnl` is a `Decimal` (from `resolve_position`).
Wire format becomes `{"__type__":"Decimal","value":"-618.90"}`. The matching
decoder is `_coerce_with_marker` in the same file (L93-139), introduced in the
same commit.

The `captain-offline` process had a stale-cached `shared.decimal_json` module
**from before this commit**, so `_coerce_with_marker` did not exist there —
the dict passed through unchanged. Then in `_handle_trade_outcome`:

```python
# captain-offline/.../orchestrator.py L264 — OUTSIDE the try/except
pnl = _stream_numeric_float(outcome.get("pnl", 0))
```

`_stream_numeric_float({"__type__":...})` → `float({...})` → `TypeError`.
Because this line is **before** the try/except, the exception escapes
`_handle_trade_outcome`, escapes `_redis_listener`'s inner per-message loop,
and is caught by the outer `except Exception` (L257) — which logs
`"Stream listener error"` and reconnects with backoff. Same root mechanism as
Bug 1, different symptom.

### Why a simple restart fixes both bugs

`shared/` is bind-mounted (not baked into the image). Restarting the container
forks a fresh Python process which loads the current on-disk
`shared/questdb_client.py` (with `qexecute`) and `shared/decimal_json.py`
(with `_coerce_with_marker`) into a fresh `sys.modules`. The
`docker-compose.local.yml` mounts also expose:

- `./captain-offline/captain_offline:/app/captain_offline:ro` (offline blocks)
- `./captain-online/captain_online:/app/captain_online:ro` (online blocks for pseudotrader replay)
- `./scripts:/captain/scripts:ro`

So **no `--build` is needed**. A `dco up -d --force-recreate captain-offline`
recycles the container with the latest code — that's it.

### Recovering yesterday's lost trade learning

The 4 SHADOW outcomes per tower were ACKed off the stream (the inner
try/except swallowed the ImportError, then the listener loop ACKed). They
**cannot be recovered from Redis** — the entries are gone. They are visible
only in `all_logs.md`.

The 2 REAL trade outcomes per tower **DID** write to D03 (P3-D03 row insertion
happens in `_write_trade_outcome` BEFORE the stream publish in
`resolve_position`). So D03 has the row but Category A+B learning never ran.
Recoverable from D03 with full fidelity (asset, pnl, contracts, regime,
aim_breakdown_at_entry are all in the row).

| Source | Fidelity | Path |
|---|---|---|
| Real trades  | FULL — query `p3_d03_trade_outcomes` for yesterday's rows | feeds `_handle_trade_outcome` |
| Shadow signals | PARTIAL — `aim_breakdown` not in logs, default modifier=1.0 used | feeds `_handle_signal_outcome` |

---

## Phase 1A — Operational Reset (zero-code, run first)

**Goal:** clear stale `sys.modules`, restore live processing of trade & signal
outcomes from this point forward. **Does NOT recover yesterday's data.**

**Pre-flight verification (run on the tower before recreating):**

```fish
# Helpers — paste once per shell session if not in funcsave
type -q dco; or function dco
    docker compose -f docker-compose.yml -f docker-compose.local.yml $argv
end
type -q cap-run; or function cap-run
    set -l script $argv[1]; set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/$script $rest
end

# Step 1 — git is up to date on both remotes
cd ~/captain-system
git fetch origin; and git fetch multi-user
test (git rev-parse HEAD) = (git rev-parse origin/main); \
    and test (git rev-parse HEAD) = (git rev-parse multi-user/main); \
    and echo "OK: HEAD synced with origin/main and multi-user/main"; \
    or echo "MISMATCH: pull/push before continuing"

# Step 2 — confirm the host file has qexecute and the marker decoder
grep -nE '^def qexecute' shared/questdb_client.py
grep -nE '_coerce_with_marker|"__type__": "Decimal"' shared/decimal_json.py
```

Both greps must return non-empty results. If they don't, the host code is
stale and a `git pull --ff-only` is needed first.

**The reset itself:**

```fish
# Step 3 — recreate captain-offline ONLY (does NOT touch QuestDB / Redis / Online / Command)
dco up -d --force-recreate --no-deps captain-offline

# Step 4 — confirm imports succeed in the fresh container
dco exec -T captain-offline python -c "
from shared.questdb_client import qexecute, get_cursor
from shared.decimal_json import dumps_decimal, loads_decimal
print('qexecute:', qexecute)
print('marker round-trip OK:',
      loads_decimal(dumps_decimal({'pnl': __import__('decimal').Decimal('1.23')}))['pnl'])
"
```

Expected output:

```
qexecute: <function qexecute at 0x…>
marker round-trip OK: 1.23
```

**Verification checklist:**

- [ ] `dco ps captain-offline` shows `Up <Xs>` (just-restarted)
- [ ] No `ImportError` in `dco logs --since 60s captain-offline`
- [ ] No `Stream listener error` in `dco logs --since 60s captain-offline`
- [ ] On the next live trade outcome (or live theoretical outcome from B7
      shadow), the offline log shows `Trade outcome received: <ASSET>
      pnl=<X.XX>` followed by individual block updates (DMA, BOCPD, Kelly)
      with **no** error.

**Anti-pattern guards:**

- Do NOT run `bash captain-start.sh --build` — that rebuilds ALL services and
  recopies `_config/`. We don't need a rebuild; bind-mount + recreate is
  sufficient and safer.
- Do NOT run `dco down && dco up -d` — that takes QuestDB down too, kills
  open psycopg2 sessions across all services, and is a 60s+ outage.
- Do NOT touch Online or Command containers in this step — only Offline had
  the stale-cache bug; recreating Online would discard the in-memory open
  position list, breaking live B7 monitoring of any open positions.

---

## Phase 1B — Defensive Code Amendments (3 small edits)

**Goal:** prevent the same failure pattern from ever again silently dropping
trade outcomes onto the floor. Each edit is small, self-contained, and
testable in isolation.

### Edit 1B-i — Harden `_stream_numeric_float`

**File:** `captain-offline/captain_offline/blocks/orchestrator.py`
**Lines:** 48-56 (replace whole function)

**Current:**

```48:56:captain-offline/captain_offline/blocks/orchestrator.py
def _stream_numeric_float(v) -> float:
    """Normalize Redis stream / D03 monetary values for float-only algorithms."""
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)
```

**Replace with:**

```python
def _stream_numeric_float(v) -> float:
    """Normalize Redis stream / D03 monetary values for float-only algorithms.

    Defensive: accepts Decimal, int, float, str, None, AND the structural
    Decimal marker dict ({"__type__": "Decimal", "value": "<digits>"}) — so
    a stale-cached `shared.decimal_json` decoder cannot crash the listener.
    Anything we cannot interpret is logged and returns 0.0 (worst case: one
    block update is a no-op; the trade outcome is still acknowledged).
    """
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and v.get("__type__") == "Decimal" and "value" in v:
        try:
            return float(Decimal(str(v["value"])))
        except (InvalidOperation, ValueError, TypeError):
            logger.warning("_stream_numeric_float: bad Decimal marker %r → 0.0", v)
            return 0.0
    if isinstance(v, str):
        try:
            return float(v)
        except (ValueError, TypeError):
            logger.warning("_stream_numeric_float: unparseable string %r → 0.0", v)
            return 0.0
    logger.warning("_stream_numeric_float: unexpected type %s value=%r → 0.0",
                   type(v).__name__, v)
    return 0.0
```

**Add at top of file (with the other imports — line 9 area):**

```python
from decimal import Decimal, InvalidOperation
```

(`Decimal` is already imported; just add `InvalidOperation`.)

### Edit 1B-ii — Move pnl coercion INSIDE the try/except

**File:** `captain-offline/captain_offline/blocks/orchestrator.py`

There are two near-identical handlers. Edit both.

**`_handle_trade_outcome` (currently L260-371):** move L262-266 *into* the
try block at L274.

```python
def _handle_trade_outcome(self, outcome: dict):
    """Process a trade outcome event."""
    asset_id = outcome.get("asset", "")
    write_checkpoint("OFFLINE", "TRADE_OUTCOME", "processing",
                     "dma_bocpd_cusum_kelly", {"asset": asset_id})
    try:
        pnl = _stream_numeric_float(outcome.get("pnl", 0))
        logger.info("Trade outcome received: %s pnl=%.2f", asset_id, pnl)
        self.plog.info(
            f"Trade outcome received: {asset_id} {'+' if pnl >= 0 else ''}"
            f"${pnl:.2f}",
            source="orchestrator",
        )
        # …rest of existing try-block body unchanged…
    except Exception as e:
        logger.error("Error processing trade outcome for %s: %s",
                     asset_id, e, exc_info=True)
    write_checkpoint("OFFLINE", "TRADE_OUTCOME_COMPLETE", "trade_processed", "waiting")
```

**`_handle_signal_outcome` (currently L373-473):** apply the same shape —
move L383-388 inside the try at L394.

```python
def _handle_signal_outcome(self, outcome: dict):
    """Process a THEORETICAL signal outcome (from shadow monitor)."""
    asset_id = outcome.get("asset", "")
    write_checkpoint("OFFLINE", "SIGNAL_OUTCOME", "processing",
                     "category_a_only", {"asset": asset_id, "theoretical": True})
    try:
        pnl = _stream_numeric_float(outcome.get("pnl", 0))
        logger.info("Theoretical signal outcome: %s pnl=%.2f (Category A learning)",
                     asset_id, pnl)
        # …rest of existing try-block body unchanged (DMA / BOCPD / CUSUM / Kelly)…
    except Exception as e:
        logger.error("Error processing signal outcome for %s: %s",
                     asset_id, e, exc_info=True)
    write_checkpoint("OFFLINE", "SIGNAL_OUTCOME_COMPLETE",
                     "theoretical_processed", "waiting")
```

**Why this matters:** with these edits, ANY future malformed payload (bad
Decimal, missing field, schema drift) is contained to a single ack-and-skip,
not a full listener crash with reconnect-with-backoff. The stream stays
flowing.

### Edit 1B-iii — Startup health check for critical shared symbols

**File:** `captain-offline/captain_offline/main.py`
**Where:** very early in `main()`, before `OfflineOrchestrator()` is
instantiated.

```python
def _verify_shared_freshness() -> None:
    """Fail fast at startup if shared/ symbols are missing or the marker
    decoder is stale. Prevents silent runtime ImportErrors from killing
    individual trade outcomes for an entire session.
    """
    from shared.questdb_client import qexecute, get_cursor  # noqa: F401
    from shared.decimal_json import dumps_decimal, loads_decimal
    from decimal import Decimal
    sample = {"pnl": Decimal("12.34")}
    rt = loads_decimal(dumps_decimal(sample))
    if rt.get("pnl") != Decimal("12.34"):
        raise RuntimeError(
            f"shared.decimal_json marker round-trip broken: "
            f"sent {sample} got {rt}. Recreate the container."
        )
    print("[OFFLINE] shared/ freshness check passed: qexecute + marker decoder live")

# in main():
#     _verify_shared_freshness()
#     orch = OfflineOrchestrator()
```

A failed check kills the container at startup with a clear error instead of
running for hours quietly losing trade outcomes.

### Verification (Phase 1B)

```bash
# Static checks (run on host before commit)
python -c "
import ast, sys
src = open('captain-offline/captain_offline/blocks/orchestrator.py').read()
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name in {'_handle_trade_outcome','_handle_signal_outcome'}:
        # find the Try block
        try_blocks = [n for n in node.body if isinstance(n, ast.Try)]
        assert try_blocks, f'{node.name}: no try block'
        # body assignments to pnl must live inside the try
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'pnl' for t in stmt.targets
            ):
                raise SystemExit(f'{node.name}: pnl assigned OUTSIDE try (line {stmt.lineno})')
print('OK: pnl coercion inside try in both handlers')
"

# Existing test suite
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
    python3 -B -m pytest tests/ -k "decimal or stream" -v
```

**Anti-pattern guards:**

- Don't broaden `_stream_numeric_float` so much that it accepts truly
  malformed data silently — every fallback **must log a warning** so the
  ops team sees it.
- Don't move the `write_checkpoint("…COMPLETE")` line inside the try (it must
  always run so journal stays consistent).
- Don't refactor the import of `Decimal` into the function body — module-top
  import only.

---

## Phase 1C — Backfill Lost Learning from 2026-05-06 NY Session

**Goal:** recover the trade learning that was silently dropped yesterday.
The script lives at `scripts/backfill_2026_05_06_ny_open.py` (see separate
file delivered in this set).

**Hardening principles baked into the script:**

| Concern | Mitigation |
|---|---|
| QuestDB schema drift / DECIMAL adapter | Script writes ZERO QuestDB rows directly. It feeds reconstructed payloads through `OfflineOrchestrator._handle_trade_outcome` / `_handle_signal_outcome`, which use the live `qexecute` + canonical column-type coercion path. |
| Idempotency | `--dry-run` is the default; `--apply` is required. Pre-flight check refuses to run if today's D02/D04/D05/D12 already shows updates dated >= 2026-05-06 14:30 UTC for the affected assets. |
| Partial failure | Each outcome is processed in a single function call inside its own try/except — a failure on outcome N halts the script with a precise error and a list of remaining outcomes; you can resume by passing `--start-from-signal-id <SIG-…>`. |
| Wrong tower | Mandatory `--account` argument; the script aborts if the running container's `BOOTSTRAP_ACCOUNT_ID` env var doesn't match. |
| Replay during a live session | Refuses to run if `now_et()` is within the NY/LON/APAC active session window. |
| Stale captain-offline | Imports `qexecute` and round-trips a Decimal marker before doing any work; aborts if either fails. |
| Silent learning corruption | Captures D02/D05/D12 row counts before & after; final report shows exact deltas for review. |

**Scope of the backfill (verified by line-by-line scan of `all_logs.md`):**

Tower A — **Isaac**, account `20258288`:

| Type | Asset | signal_id | pnl | contracts | direction |
|---|---|---|---|---|---|
| SHADOW | ZN  | SIG-98FFF726C989 | -312.50 | 15 | +1 |
| SHADOW | MNQ | SIG-4D524C4EAE13 | -629.33 | 8  | +1 |
| SHADOW | ZB  | SIG-93D26B847466 | -937.50 | 15 | -1 |
| SHADOW | MES | SIG-AD90E5324AE5 | -550.00 | 15 | +1 |
| REAL   | (recover from D03 by querying `account=20258288 AND ts IN '2026-05-06T13:30..16:00@America/New_York'`) | TRD-B873639F6F2D, TRD-910AE8FDB95E | from D03 | from D03 | from D03 |

Tower B — **Nomaan**, account `21855714`:

| Type | Asset | signal_id | pnl | contracts | direction |
|---|---|---|---|---|---|
| SHADOW | ZN  | SIG-0ACBEC9745FE | -312.50 | 15 | +1 |
| SHADOW | MNQ | SIG-3FF4EE9A1B09 | -625.33 | 8  | +1 |
| SHADOW | ZB  | SIG-75117AE16859 | -937.50 | 15 | -1 |
| SHADOW | MES | SIG-98C6A745A630 | -643.75 | 15 | +1 |
| REAL   | (recover from D03 by querying `account=21855714 AND ts IN '2026-05-06T13:30..16:00@America/New_York'`) | TRD-17315DE23E16, TRD-06D1A31AA9FC | from D03 | from D03 | from D03 |

Direction sourced from the same-line `OR BREAKOUT LONG/SHORT: <asset>` log
entry. Contracts sourced from `ON-B4: <asset> ac=<account> … → <N>
contracts [TRADE]` from the matching tower.

**How the script runs (per tower):**

```fish
# Tower A (Isaac):
cd ~/captain-system
git pull --ff-only origin main          # pull the Wave 1B amendments first
dco up -d --force-recreate --no-deps captain-offline

# Dry run first — shows what would be replayed, writes nothing
cap-run backfill_2026_05_06_ny_open.py --account 20258288 --dry-run

# Once the dry-run output looks correct:
cap-run backfill_2026_05_06_ny_open.py --account 20258288 --apply

# Tower B (Nomaan):
# (same, with --account 21855714)
```

**Verification checklist (post-`--apply`):**

```fish
# Confirm new D02 rows were written for the 4 shadow assets, dated today
curl -s -G "http://localhost:9000/exec" \
  --data-urlencode "query=SELECT asset_id, count() FROM p3_d02_aim_meta_weights \
                    WHERE ts > '2026-05-07' AND asset_id IN ('ZN','MNQ','ZB','MES') \
                    GROUP BY asset_id ORDER BY asset_id" | jq '.dataset'

# Confirm D12 Kelly params were updated
curl -s -G "http://localhost:9000/exec" \
  --data-urlencode "query=SELECT asset_id, regime, count() FROM p3_d12_kelly_parameters \
                    WHERE ts > '2026-05-07' AND asset_id IN ('ZN','MNQ','ZB','MES') \
                    GROUP BY asset_id, regime ORDER BY asset_id" | jq '.dataset'

# Confirm BOCPD detector state advanced
curl -s -G "http://localhost:9000/exec" \
  --data-urlencode "query=SELECT asset_id, count() FROM p3_d04_decay_changepoints \
                    WHERE ts > '2026-05-07' AND asset_id IN ('ZN','MNQ','ZB','MES') \
                    GROUP BY asset_id ORDER BY asset_id" | jq '.dataset'
```

Each query must return one row per replayed asset. Counts >= 1 for D02 and
D12. D04 may show counts 0 or 1 per asset (changepoint detection is
incremental, not per-trade).

---

## Phase 1D — Final Verification

1. `dco logs --since 5m captain-offline` — no `ImportError`, no `Stream
   listener error`, no `Error processing signal outcome`.
2. Replay the static check from Phase 1B (no `pnl` assignment outside try).
3. Ad-hoc smoke: publish a synthetic test signal outcome onto Redis and
   confirm captain-offline processes it end-to-end:

   ```fish
   cap-run inject_test_signal.py --type signal_outcome --asset ZN --pnl -100 --contracts 1
   sleep 5
   dco logs --since 30s captain-offline | grep -E "Theoretical|DMA|Kelly"
   ```

4. Cross-tower diff: after both towers run the backfill, the row counts in
   `p3_d02_aim_meta_weights` and `p3_d12_kelly_parameters` should match
   (Category A is meant to be synchronized across instances). A ±1 row
   diff is fine (timing of compaction); a >5 diff means re-run the
   backfill on the lagging tower.

---

## Open questions (please answer before I execute Phase 1A)

1. **Backfill scope.** The plan covers BOTH (a) the 4 shadow signal outcomes
   per tower and (b) the 2 real trade outcomes per tower. Is that what you
   want, or only the shadows? (Real trades already wrote to D03; only
   Category A+B *learning* was lost.)

2. **Shadow-fidelity loss.** Shadow positions are in-memory only; we do NOT
   have `aim_breakdown_at_entry` / `combined_modifier` for yesterday's
   shadows. The replay must use `modifier=1.0` per AIM as a default. This
   means the DMA update for those four signals will treat all AIMs as
   uniformly weighted — a small fidelity loss vs the live path. **OK to
   proceed with this default, or skip shadow backfill entirely?**

3. **Tower coverage.** Should we run on **Nomaan's tower only** (account
   21855714), or **both towers** (Isaac's 20258288 and Nomaan's 21855714)?
   If both, you'll run the backfill independently on each.

4. **Restart strategy.** Confirm the lighter-weight `dco up -d
   --force-recreate --no-deps captain-offline` is acceptable, vs running
   `bash captain-start.sh` (which also rebuilds, re-bootstraps, runs schema
   init, etc.). The lighter approach is safer and faster but skips the
   periodic compaction + integrity check.

5. **AIM-16 HMM training dispatch.** Yesterday's `[pg01c] training dispatch
   failed: cannot import name 'qexecute'` left the HMM training un-run for
   the 2026-05-06 session_close. After Phase 1A's restart, do you want me
   to manually re-dispatch via a one-line `cap-run` invocation of
   `_run_aim16_hmm_training(session_id=<id>, closed_at='…')`? It's safe to
   re-run (idempotent on D26 by `(session_id, ts)`).
