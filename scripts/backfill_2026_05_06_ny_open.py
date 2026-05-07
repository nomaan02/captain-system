#!/usr/bin/env python3
"""Backfill lost Category A/B trade learning from 2026-05-06 NY-Open.

WHAT THIS SCRIPT DOES
---------------------
On 2026-05-06 NY open, captain-offline had a stale `sys.modules` cache from
before commits 9aefcb5 (qexecute) and 8e4064c (Decimal marker). Two failure
modes silently dropped trade learning:

  1. SHADOW theoretical outcomes (4 per tower) — `_handle_signal_outcome`
     raised ImportError caught by the inner try/except → message ACKed →
     learning never ran. Tables affected: D02, D04, D05, D12.

  2. REAL trade outcomes (2 per tower) — `_handle_trade_outcome` crashed
     on `float({"__type__":"Decimal",…})` → escaped to `_redis_listener`'s
     outer except → message ACKed by xreadgroup-pending-list cleanup on
     reconnect → learning never ran. Tables affected: D02, D04, D05, D08,
     D12, D23 (CB params), D25.

  The D03 trade-outcome rows DO exist (resolve_position writes D03 BEFORE
  publishing to Redis). So real-trade backfill can recover full fidelity
  by reading D03. Shadow backfill is partial-fidelity (in-memory shadows
  with their AIM context were lost on container restart).

THIS SCRIPT IS DESIGNED TO BE FAIL-PROOF AT THE QUESTDB LAYER
-------------------------------------------------------------
It writes ZERO QuestDB rows directly. It feeds reconstructed payloads
through `OfflineOrchestrator._handle_trade_outcome` /
`_handle_signal_outcome`, which use the live `qexecute` + canonical
column-type coercion. Any QuestDB schema/decimal/wire-type quirk is
already battle-tested by the live code path. If the live path is sound
(verified by today's session running cleanly post-restart), this backfill
cannot fail at the QuestDB layer.

INVARIANTS / SAFETY GATES
-------------------------
  * `--dry-run` is the default.  `--apply` required to mutate state.
  * `--account <id>` mandatory; aborts if the running container's
    BOOTSTRAP_ACCOUNT_ID env var disagrees.
  * Refuses to run while NY/LON/APAC sessions are active.
  * Pre-flight: imports `qexecute`, round-trips a Decimal marker, and
    confirms the orchestrator's `_handle_*` symbols exist.
  * Idempotency: refuses to run if D02 already has rows newer than
    2026-05-07 00:00 UTC for the affected assets (means a previous
    backfill already happened — pass `--force` to override after manual
    cleanup).
  * Captures before/after counts on D02 / D04 / D05 / D12 / D23 and prints
    a delta report at the end.
  * Each outcome processed in its own try; failure halts with a clean
    --start-from-signal-id resume hint.

USAGE (run from inside captain-offline container via cap-run helper)
-------------------------------------------------------------------
    # Dry run — prints planned replays, writes nothing
    cap-run backfill_2026_05_06_ny_open.py --account 21855714 --dry-run

    # Once the dry-run output looks correct
    cap-run backfill_2026_05_06_ny_open.py --account 21855714 --apply

    # Resume after partial failure
    cap-run backfill_2026_05_06_ny_open.py --account 21855714 --apply \
            --start-from-signal-id SIG-75117AE16859

    # Real-trades-only (Category A+B from D03) or shadows-only
    cap-run backfill_2026_05_06_ny_open.py --account 21855714 --apply --only-real
    cap-run backfill_2026_05_06_ny_open.py --account 21855714 --apply --only-shadow

    # Override idempotency guard (only after manual review)
    cap-run backfill_2026_05_06_ny_open.py --account 21855714 --apply --force
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Constants — values pinned from `all_logs.md` line-by-line. Do not edit
# without reconciling against the original log lines.
# ---------------------------------------------------------------------------

NY_TZ = ZoneInfo("America/New_York")
SESSION_CLOSE_DATE = "2026-05-06"

# Per-tower shadow outcomes that were lost. Each entry is the minimal
# theoretical_outcome dict needed by `_handle_signal_outcome`.
#
# Direction inferred from "OR BREAKOUT LONG/SHORT: <asset>" log lines:
#   ZN  LONG  → +1
#   MNQ LONG  → +1
#   ZB  SHORT → -1
#   MES LONG  → +1
#
# Contracts inferred from "ON-B4: <asset> ac=<account> … → <N> contracts [TRADE]"
# lines in the Phase B Kelly-sizing block of each tower. Both towers reported
# identical sizes for ZN/ZB/MES (15) and MNQ (8) — Kelly inputs are
# identical because cap=150000 + AIM weights are synchronized.
SHADOW_OUTCOMES = {
    20258288: [  # Tower A — Isaac
        {"asset": "ZN",  "signal_id": "SIG-98FFF726C989", "pnl": -312.50, "contracts": 15, "direction":  1},
        {"asset": "MNQ", "signal_id": "SIG-4D524C4EAE13", "pnl": -629.33, "contracts":  8, "direction":  1},
        {"asset": "ZB",  "signal_id": "SIG-93D26B847466", "pnl": -937.50, "contracts": 15, "direction": -1},
        {"asset": "MES", "signal_id": "SIG-AD90E5324AE5", "pnl": -550.00, "contracts": 15, "direction":  1},
    ],
    21855714: [  # Tower B — Nomaan
        {"asset": "ZN",  "signal_id": "SIG-0ACBEC9745FE", "pnl": -312.50, "contracts": 15, "direction":  1},
        {"asset": "MNQ", "signal_id": "SIG-3FF4EE9A1B09", "pnl": -625.33, "contracts":  8, "direction":  1},
        {"asset": "ZB",  "signal_id": "SIG-75117AE16859", "pnl": -937.50, "contracts": 15, "direction": -1},
        {"asset": "MES", "signal_id": "SIG-98C6A745A630", "pnl": -643.75, "contracts": 15, "direction":  1},
    ],
}

# Real trade outcomes that were ACKed without learning. Recovered from D03.
# We just need to know which trade_ids we replay so the script knows what
# to query for. The actual outcome dict is reconstructed from D03 fields.
REAL_TRADE_IDS = {
    20258288: ["TRD-B873639F6F2D", "TRD-910AE8FDB95E"],
    21855714: ["TRD-17315DE23E16", "TRD-06D1A31AA9FC"],
}

# Tables we expect to see new rows in after a successful backfill.
WATCH_TABLES = [
    "p3_d02_aim_meta_weights",
    "p3_d04_decay_changepoints",
    "p3_d05_ewma_states",
    "p3_d08_tsm_state",
    "p3_d12_kelly_parameters",
    "p3_d23_circuit_breaker_intraday_state",
    "p3_d25_circuit_breaker",
]

# Shadow backfill assets — used in idempotency check.
AFFECTED_ASSETS = ("ZN", "MNQ", "ZB", "MES")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BACKFILL] %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("backfill_2026_05_06")


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

def _check_account_matches_container(account: int) -> None:
    """Abort if the script is being run against the wrong tower."""
    env_acct = os.environ.get("BOOTSTRAP_ACCOUNT_ID", "").strip()
    if env_acct and env_acct.isdigit() and int(env_acct) != account:
        raise SystemExit(
            f"ABORT: --account {account} but container's "
            f"BOOTSTRAP_ACCOUNT_ID={env_acct}. Wrong tower. "
            "Run on the matching tower or fix the env."
        )
    if not env_acct:
        logger.warning(
            "BOOTSTRAP_ACCOUNT_ID env var not set in container — "
            "cannot verify tower match. Proceeding on user's --account."
        )


def _check_not_in_active_session() -> None:
    """Refuse to run during NY / LON / APAC active windows.

    Replaying mid-session would inject parameter updates while the live
    pipeline is also writing — race conditions would corrupt state.
    """
    now = datetime.now(NY_TZ)
    h, m = now.hour, now.minute

    # NY: 09:30 - 16:00 ET, Mon-Fri
    weekday = now.weekday()  # 0 = Monday
    in_ny = (
        weekday < 5
        and (
            (h == 9 and m >= 30)
            or (10 <= h < 16)
        )
    )
    # LON: 03:00 - 11:00 ET, Mon-Fri
    in_lon = weekday < 5 and (3 <= h < 11)
    # APAC: 18:00 ET (prev day) - 02:00 ET, Sun-Thu
    in_apac = (
        (weekday < 5 and (18 <= h or h < 2))
        or (weekday == 6 and h >= 18)
    )

    if in_ny or in_lon or in_apac:
        raise SystemExit(
            f"ABORT: now={now.isoformat()} is inside an active session "
            f"(NY={in_ny} LON={in_lon} APAC={in_apac}). Wait for the "
            "session to close before running backfill."
        )


def _check_shared_freshness() -> None:
    """Confirm shared/ has qexecute + the marker decoder."""
    try:
        from shared.questdb_client import qexecute, get_cursor  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            f"ABORT: shared.questdb_client.qexecute missing ({e}). "
            "Recreate the captain-offline container with bind-mounted "
            "shared/, then retry."
        )
    try:
        from shared.decimal_json import dumps_decimal, loads_decimal
        sample = {"pnl": Decimal("12.34")}
        rt = loads_decimal(dumps_decimal(sample))
        if rt.get("pnl") != Decimal("12.34"):
            raise RuntimeError(f"marker round-trip broken: {sample!r} -> {rt!r}")
    except Exception as e:
        raise SystemExit(
            f"ABORT: shared.decimal_json marker decoder broken or absent ({e}). "
            "Recreate the captain-offline container, then retry."
        )
    logger.info("Pre-flight: shared.questdb_client.qexecute + decimal marker round-trip OK")


def _check_orchestrator_handlers() -> None:
    """Confirm the orchestrator we'll be calling exposes the expected handlers."""
    from captain_offline.blocks.orchestrator import OfflineOrchestrator
    for name in ("_handle_trade_outcome", "_handle_signal_outcome", "_stream_numeric_float"):
        if not hasattr(OfflineOrchestrator, name) and not hasattr(
            sys.modules["captain_offline.blocks.orchestrator"], name
        ):
            raise SystemExit(
                f"ABORT: OfflineOrchestrator missing required symbol '{name}'. "
                "shared/ may be stale or orchestrator.py was refactored — abort."
            )
    logger.info("Pre-flight: orchestrator handler symbols present")


def _query_count(table: str, where_clause: str = "") -> int:
    """Return row count from a QuestDB table via the live pg-wire client."""
    from shared.questdb_client import get_cursor
    where = f" WHERE {where_clause}" if where_clause else ""
    with get_cursor() as cur:
        cur.execute(f"SELECT count() FROM {table}{where}")
        row = cur.fetchone()
        return int(row[0] if row else 0)


def _check_idempotency(force: bool) -> None:
    """Abort if a previous backfill already touched the same window.

    Specifically: any D02 row for the 4 affected assets dated >= 2026-05-07
    00:00 UTC indicates either a prior backfill or live processing today.
    Either way, replaying on top is unsafe — abort.
    """
    if force:
        logger.warning("Pre-flight: --force given, skipping idempotency guard")
        return
    asset_list = ",".join(f"'{a}'" for a in AFFECTED_ASSETS)
    where = (
        f"asset_id IN ({asset_list}) "
        f"AND ts >= cast('2026-05-07T00:00:00.000000Z' AS timestamp)"
    )
    n = _query_count("p3_d02_aim_meta_weights", where)
    if n > 0:
        raise SystemExit(
            f"ABORT: D02 already has {n} rows for {AFFECTED_ASSETS} dated >= "
            "2026-05-07 UTC. A prior backfill or today's live processing "
            "may have already covered this. Re-running would compound DMA "
            "weight updates. Pass --force to override AFTER you've verified "
            "the situation."
        )
    logger.info("Pre-flight: idempotency guard PASSED (no D02 rows for affected assets after 2026-05-07)")


# ---------------------------------------------------------------------------
# D03 → outcome dict reconstruction
# ---------------------------------------------------------------------------

def _load_real_trade_outcomes(account: int, trade_ids: Iterable[str]) -> list[dict]:
    """Fetch the D03 row for each trade_id and convert to a outcome dict."""
    from shared.questdb_client import get_cursor

    ids = list(trade_ids)
    if not ids:
        return []
    placeholders = ",".join(f"'{tid}'" for tid in ids)
    sql = (
        "SELECT trade_id, signal_id, user_id, account_id, asset, direction, "
        "       entry_price, exit_price, contracts, pnl, commission, "
        "       slippage, outcome, regime_at_entry, aim_modifier, "
        "       aim_breakdown, session, tsm_used, ts "
        "FROM p3_d03_trade_outcomes "
        f"WHERE trade_id IN ({placeholders}) AND account_id = %s "
        "LATEST ON ts PARTITION BY trade_id"
    )
    outcomes: list[dict] = []
    with get_cursor() as cur:
        cur.execute(sql, (str(account),))
        cols = [d[0] for d in cur.description]
        for row in cur.fetchall():
            r = dict(zip(cols, row))
            # Normalize types — `_handle_trade_outcome` expects pnl as Decimal/float,
            # contracts as int, account as str (matches resolve_position normalization).
            outcome = {
                "trade_id":   r["trade_id"],
                "signal_id":  r.get("signal_id"),
                "user_id":    r.get("user_id"),
                "asset":      r.get("asset"),
                "direction":  int(r.get("direction") or 1),
                "entry_price": r.get("entry_price"),
                "exit_price": r.get("exit_price"),
                "contracts":  int(r.get("contracts") or 1),
                "pnl":        r.get("pnl"),         # Decimal from psycopg2
                "commission": r.get("commission"),
                "slippage":   r.get("slippage"),
                "outcome":    r.get("outcome"),
                "regime_at_entry": r.get("regime_at_entry"),
                "aim_modifier_at_entry": r.get("aim_modifier"),
                "aim_breakdown_at_entry": _maybe_json(r.get("aim_breakdown")),
                "session":    r.get("session"),
                "account":    str(account),
                "tsm_used":   r.get("tsm_used"),
                "_replay_marker": "BACKFILL-2026-05-06",
            }
            outcomes.append(outcome)
    return outcomes


def _maybe_json(v):
    """D03's aim_breakdown column is VARCHAR holding a JSON string."""
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return {}
    return {}


# ---------------------------------------------------------------------------
# Build shadow outcome payload
# ---------------------------------------------------------------------------

def _build_shadow_outcome(account: int, raw: dict) -> dict:
    """Build the dict that `_handle_signal_outcome` expects.

    Mirrors `b7_shadow_monitor._resolve_shadow`'s `theoretical_outcome` shape.
    Note: we DO NOT have aim_breakdown_at_entry / regime_at_entry from logs
    (those live in-memory in the shadow position dict, lost on restart).
    Defaults: `regime_at_entry=None` (b1_dma_update falls back to LOW_VOL),
    `aim_breakdown_at_entry={}` (b1_dma_update uses modifier=1.0 per AIM).
    """
    return {
        "trade_id":   f"BACKFILL-{raw['signal_id'].replace('SIG-', '')}",
        "signal_id":  raw["signal_id"],
        "user_id":    "primary_user",
        "asset":      raw["asset"],
        "direction":  raw["direction"],
        "entry_price": None,      # not in logs; not used by Category A learning
        "exit_price":  None,      # not in logs; not used
        "contracts":  raw["contracts"],
        "pnl":        raw["pnl"],
        "commission": 0,
        "slippage":   None,
        "outcome":    "SL_HIT",   # all 8 yesterday's shadows were SL_HIT
        "regime_at_entry":      None,  # default in run_dma_update -> "LOW_VOL"
        "aim_modifier_at_entry": 1.0,  # neutral
        "aim_breakdown_at_entry": {},  # neutral — modifier=1.0 used per AIM
        "session":    1,          # NY
        "account":    str(account),
        "theoretical": True,
        "_replay_marker": "BACKFILL-2026-05-06",
    }


# ---------------------------------------------------------------------------
# The replay
# ---------------------------------------------------------------------------

def _snapshot_counts(account: int) -> dict[str, int]:
    """Capture row counts for each watched table BEFORE replay."""
    snap = {}
    for tbl in WATCH_TABLES:
        try:
            snap[tbl] = _query_count(tbl)
        except Exception as e:
            logger.warning("snapshot_counts: skipping %s (%s)", tbl, e)
            snap[tbl] = -1
    return snap


def _print_delta(before: dict[str, int], after: dict[str, int]) -> None:
    print("\n=== Backfill row-count deltas ===", file=sys.stderr)
    for tbl in WATCH_TABLES:
        b, a = before.get(tbl, -1), after.get(tbl, -1)
        if b < 0 or a < 0:
            print(f"  {tbl:<45} (skipped)", file=sys.stderr)
            continue
        print(f"  {tbl:<45} before={b}  after={a}  Δ={a - b:+d}",
              file=sys.stderr)


def _replay_one(orch, outcome: dict, kind: str, dry_run: bool) -> None:
    """Replay a single outcome through the live handler."""
    asset = outcome.get("asset")
    sig = outcome.get("signal_id") or outcome.get("trade_id")
    pnl = outcome.get("pnl")
    contracts = outcome.get("contracts")
    logger.info("REPLAY [%s] %s sig=%s pnl=%s contracts=%s%s",
                kind, asset, sig, pnl, contracts,
                " (DRY-RUN)" if dry_run else "")
    if dry_run:
        return
    if kind == "REAL":
        orch._handle_trade_outcome(outcome)
    elif kind == "SHADOW":
        orch._handle_signal_outcome(outcome)
    else:
        raise ValueError(f"unknown kind: {kind}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--account", type=int, required=True,
                   choices=list(SHADOW_OUTCOMES.keys()),
                   help="Tower account ID — must match the running container")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Default. Print planned replays, write nothing.")
    mode.add_argument("--apply", action="store_true",
                      help="Actually mutate state via live handlers.")
    p.add_argument("--only-real", action="store_true",
                   help="Only replay real trade outcomes (Category A+B from D03)")
    p.add_argument("--only-shadow", action="store_true",
                   help="Only replay shadow theoretical outcomes (Category A only)")
    p.add_argument("--start-from-signal-id", default=None,
                   help="Resume from this signal_id/trade_id (skips earlier ones)")
    p.add_argument("--force", action="store_true",
                   help="Bypass idempotency guard (use with caution)")
    args = p.parse_args()

    if args.apply:
        args.dry_run = False

    if args.only_real and args.only_shadow:
        raise SystemExit("ABORT: --only-real and --only-shadow are mutually exclusive")

    print(f"=== Backfill 2026-05-06 NY-Open — account {args.account} ===",
          file=sys.stderr)
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN (default)'}",
          file=sys.stderr)
    print("", file=sys.stderr)

    # ── Pre-flight gauntlet ────────────────────────────────────────────
    _check_account_matches_container(args.account)
    if args.apply:
        _check_not_in_active_session()
    _check_shared_freshness()
    _check_orchestrator_handlers()
    if args.apply:
        _check_idempotency(force=args.force)

    # Build replay queue
    queue: list[tuple[str, dict]] = []
    if not args.only_shadow:
        real = _load_real_trade_outcomes(args.account, REAL_TRADE_IDS[args.account])
        if not real:
            logger.warning("No D03 rows found for trade_ids %s on account %d. "
                           "Real-trade backfill SKIPPED.",
                           REAL_TRADE_IDS[args.account], args.account)
        for o in real:
            queue.append(("REAL", o))
    if not args.only_real:
        for raw in SHADOW_OUTCOMES[args.account]:
            queue.append(("SHADOW", _build_shadow_outcome(args.account, raw)))

    # Optional resume
    if args.start_from_signal_id:
        before_len = len(queue)
        skipped = []
        while queue:
            sid = queue[0][1].get("signal_id") or queue[0][1].get("trade_id")
            if sid == args.start_from_signal_id:
                break
            skipped.append(queue.pop(0))
        logger.info("--start-from-signal-id %s: skipped %d entries before resume "
                    "(remaining %d of %d)",
                    args.start_from_signal_id, len(skipped),
                    len(queue), before_len)

    if not queue:
        logger.warning("Replay queue is empty. Nothing to do.")
        return 0

    print(f"\n--- Replay queue ({len(queue)} entries) ---", file=sys.stderr)
    for kind, o in queue:
        sid = o.get("signal_id") or o.get("trade_id")
        print(f"  [{kind}] {o.get('asset')}  sid={sid}  pnl={o.get('pnl')}  "
              f"contracts={o.get('contracts')}", file=sys.stderr)
    print("", file=sys.stderr)

    # Snapshot before
    before = _snapshot_counts(args.account) if args.apply else {}

    # Execute
    from captain_offline.blocks.orchestrator import OfflineOrchestrator
    orch = OfflineOrchestrator()

    failed_at: tuple[str, str] | None = None
    for i, (kind, o) in enumerate(queue):
        sid = o.get("signal_id") or o.get("trade_id")
        try:
            _replay_one(orch, o, kind, dry_run=args.dry_run)
        except Exception as e:
            logger.exception("REPLAY FAILED at #%d (%s %s): %s", i, kind, sid, e)
            failed_at = (kind, sid)
            break

    # Snapshot after + delta
    if args.apply:
        after = _snapshot_counts(args.account)
        _print_delta(before, after)

    if failed_at:
        kind, sid = failed_at
        print(f"\nBACKFILL HALTED at [{kind}] sid={sid}.", file=sys.stderr)
        print(f"To resume after fixing the cause, rerun with: "
              f"--start-from-signal-id {sid}", file=sys.stderr)
        return 1

    print("\nBACKFILL COMPLETE." if args.apply else "\nDRY-RUN COMPLETE — pass --apply to execute.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
