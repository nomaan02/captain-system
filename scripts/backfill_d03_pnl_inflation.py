#!/usr/bin/env python3
"""Backfill D03 PnL inflation — Bug A historical correction (2026-04-29).

CONTEXT
-------
b7_position_monitor wrote inflated `gross_pnl` / `pnl` / `slippage` for every
non-ES asset because `pos.get("point_value", 50.0)` defaulted to ES's PV when
the upstream chain dropped the field. This script identifies every affected
D03 row and proposes corrected PnL using D00's authoritative point_value.

CHOSEN APPROACH (3.3-A from the Stage 3 plan): APPEND-CORRECTION
-----------------------------------------------------------------
For each affected `(trade_id, ts_original)` pair, append a NEW D03 row with:
  * same trade_id, signal_id, asset, direction, contracts, entry / exit prices
  * corrected gross_pnl / pnl / slippage computed from D00.point_value
  * outcome suffix "_CORRECTED" (e.g. "TP_HIT_CORRECTED")
  * tsm_used = "BUG_A_BACKFILL"
  * fresh ts (now())

Audit trail: original row preserved verbatim. Corrected row visible via
LATEST ON ts PARTITION BY trade_id.

BLOCKING SAFETY GATE — READ THIS BEFORE --apply
-----------------------------------------------
**Most D03 readers in the live codebase use raw SUM(pnl) / SELECT pnl, NOT
LATEST-ON.** Concretely (audited 2026-04-29):

    SUM(pnl) WITHOUT LATEST-ON (would double-count after this backfill):
        captain-online/.../b6_signal_output.py:441 (_get_daily_pnl)
        shared/aim16_observation_panel.py:93         (sum(pnl) per session)

    SELECT pnl WITHOUT LATEST-ON (would see both rows when ordering by ts):
        captain-online/.../b5c_circuit_breaker.py:599  (rolling returns)
        captain-command/.../b6_reports.py             (RPT-04 / RPT-12 etc.)
        captain-offline/.../orchestrator.py:746,911,972,1178,1220
        captain-offline/.../b8_cb_params.py:44        (β_b refit)
        captain-offline/.../b9_diagnostic.py:426
        captain-offline/.../b3_pseudotrader.py:706
        captain-command/.../b2_gui_data_server.py
        shared/trade_source.py:232,401,421
        shared/replay_engine.py

To run with `--apply`, you must pass `--readers-audited` to acknowledge that
EITHER:
    (a) Every reader above has been updated to LATEST-ON-trade_id semantics, OR
    (b) You have stopped all consumers and are only using D03 for offline
        analysis where double-counting is not in play.

Without `--readers-audited`, the script refuses to write.

ALTERNATIVE STRATEGIES (NOT IMPLEMENTED HERE — flag if you want either)
-----------------------------------------------------------------------
  3.3-D : UPSERT in place using same (ts, trade_id) — DEDUP keys collapse
          rows. Audit trail destroyed (originals overwritten). Cleanest for
          readers; worst for forensics.
  3.3-E : Same as 3.3-D plus a parallel `p3_d03_corrections_log` table
          recording original vs corrected. Best of both — readers untouched,
          audit trail preserved out-of-band. Recommended for production.

USAGE
-----
    # 1. Dry-run + diff report (default)
    python3 scripts/backfill_d03_pnl_inflation.py --user primary_user

    # 2. Dry-run, write proposal markdown only (review before applying)
    python3 scripts/backfill_d03_pnl_inflation.py --user primary_user \\
        --proposal-out backfill_proposal.md

    # 3. Apply — REQUIRES --readers-audited acknowledgement
    python3 scripts/backfill_d03_pnl_inflation.py --user primary_user \\
        --apply --readers-audited
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.questdb_client import get_cursor, qexecute  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_d03")


def _money(x: Any) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


# ---------------------------------------------------------------------------
# D00 lookup
# ---------------------------------------------------------------------------

def load_d00_point_values() -> dict[str, Decimal]:
    """Load LATEST point_value for every asset in D00."""
    pv_by_asset: dict[str, Decimal] = {}
    with get_cursor() as cur:
        cur.execute(
            """SELECT asset_id, point_value
               FROM p3_d00_asset_universe
               LATEST ON last_updated PARTITION BY asset_id"""
        )
        for asset_id, pv in cur.fetchall():
            if pv is None:
                continue
            pv_by_asset[asset_id] = _money(pv)
    return pv_by_asset


# ---------------------------------------------------------------------------
# D03 read — only LATEST per trade_id (so we don't re-correct existing
# corrections if the script is re-run)
# ---------------------------------------------------------------------------

D03_ROW_FIELDS = [
    "trade_id", "signal_id", "user_id", "account_id", "asset", "direction",
    "entry_price", "signal_entry_price", "exit_price", "contracts",
    "gross_pnl", "commission", "pnl", "slippage", "outcome",
    "entry_time", "exit_time", "regime_at_entry", "aim_modifier_at_entry",
    "aim_breakdown_at_entry", "session", "tsm_used", "model_m", "ts",
]


def fetch_d03_rows(user_id: str | None) -> list[dict]:
    where = "WHERE user_id = %s" if user_id else ""
    args = (user_id,) if user_id else ()
    with get_cursor() as cur:
        cur.execute(
            f"""SELECT {", ".join(D03_ROW_FIELDS)}
                FROM p3_d03_trade_outcome_log
                {where}
                LATEST ON ts PARTITION BY trade_id""",
            args,
        )
        rows = cur.fetchall()
    return [dict(zip(D03_ROW_FIELDS, r)) for r in rows]


# ---------------------------------------------------------------------------
# Per-row diff
# ---------------------------------------------------------------------------

def compute_correction(row: dict, pv_lookup: dict[str, Decimal]) -> dict | None:
    """Return correction dict if this row is mis-priced under Bug A, else None.

    Returns None for rows that are already correct (asset PV ≈ 50 OR row was
    already corrected — outcome ends with _CORRECTED).
    """
    asset = row["asset"]
    if not asset or row.get("outcome", "").endswith("_CORRECTED"):
        return None
    if asset not in pv_lookup:
        logger.warning(
            "D03 row %s references asset %s with no D00 entry — skipping",
            row["trade_id"], asset,
        )
        return None
    true_pv = pv_lookup[asset]
    direction = int(row["direction"] or 0)
    contracts = int(row["contracts"] or 0)
    entry = _money(row["entry_price"])
    exit_ = _money(row["exit_price"])

    # Recompute under correct PV
    corrected_gross = (
        (exit_ - entry) * Decimal(direction) * Decimal(contracts) * true_pv
    )
    commission = _money(row["commission"])
    corrected_pnl = corrected_gross - commission

    # Slippage — only if signal_entry_price differs from entry_price
    sig_entry = _money(row["signal_entry_price"])
    if sig_entry != Decimal("0") and sig_entry != entry:
        # original code computed slippage = (actual_entry - sig_entry) * dir * c * pv
        # but D03 stores entry_price = actual_entry (per resolve_position L222).
        # So slippage = (entry - sig_entry) * dir * contracts * true_pv
        corrected_slippage = (
            (entry - sig_entry) * Decimal(direction) * Decimal(contracts) * true_pv
        )
    else:
        corrected_slippage = Decimal("0")

    original_gross = _money(row["gross_pnl"])
    delta_gross = corrected_gross - original_gross
    if delta_gross == 0:
        # Row is already correct (e.g. ES, or contracts=0)
        return None

    return {
        "trade_id": row["trade_id"],
        "asset": asset,
        "true_pv": true_pv,
        "buggy_pv_implicit": Decimal("50"),
        "original_gross_pnl": original_gross,
        "corrected_gross_pnl": corrected_gross,
        "delta_gross_pnl": delta_gross,
        "original_pnl": _money(row["pnl"]),
        "corrected_pnl": corrected_pnl,
        "original_slippage": _money(row["slippage"]),
        "corrected_slippage": corrected_slippage,
        "row": row,
    }


# ---------------------------------------------------------------------------
# Append-correction writer (3.3-A)
# ---------------------------------------------------------------------------

def write_correction_row(correction: dict) -> None:
    src = correction["row"]
    new_outcome = (src.get("outcome") or "UNKNOWN") + "_CORRECTED"
    new_tsm_used = "BUG_A_BACKFILL"
    with get_cursor() as cur:
        qexecute(
            cur,
            """INSERT INTO p3_d03_trade_outcome_log (
                   trade_id, signal_id, user_id, account_id, asset, direction,
                   entry_price, signal_entry_price, exit_price, contracts,
                   gross_pnl, commission, pnl, slippage, outcome,
                   entry_time, exit_time, regime_at_entry, aim_modifier_at_entry,
                   aim_breakdown_at_entry, session, tsm_used, model_m, ts
               ) VALUES (%s, %s, %s, %s, %s, %s,
                         %s, %s, %s, %s,
                         %s, %s, %s, %s, %s,
                         %s, %s, %s, %s,
                         %s, %s, %s, %s, now())""",
            (
                src["trade_id"], src["signal_id"], src["user_id"],
                src["account_id"], src["asset"], src["direction"],
                src["entry_price"], src["signal_entry_price"],
                src["exit_price"], src["contracts"],
                correction["corrected_gross_pnl"], src["commission"],
                correction["corrected_pnl"], correction["corrected_slippage"],
                new_outcome,
                src["entry_time"], src["exit_time"], src["regime_at_entry"],
                src["aim_modifier_at_entry"], src["aim_breakdown_at_entry"],
                src["session"], new_tsm_used, src["model_m"],
            ),
        )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def write_proposal_markdown(corrections: list[dict], path: str) -> None:
    lines = [
        "# D03 PnL Inflation Backfill Proposal",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        f"Total affected rows: **{len(corrections)}**",
        "",
        "## Per-asset summary",
        "",
        "| Asset | true PV | Affected rows | Σ original gross | Σ corrected gross | Σ delta |",
        "|-------|---------|---------------|------------------|-------------------|---------|",
    ]
    by_asset: dict[str, list[dict]] = defaultdict(list)
    for c in corrections:
        by_asset[c["asset"]].append(c)
    for asset in sorted(by_asset):
        cs = by_asset[asset]
        sum_orig = sum((c["original_gross_pnl"] for c in cs), Decimal("0"))
        sum_corr = sum((c["corrected_gross_pnl"] for c in cs), Decimal("0"))
        delta = sum_corr - sum_orig
        lines.append(
            f"| {asset} | {cs[0]['true_pv']} | {len(cs)} | "
            f"${sum_orig:,.2f} | ${sum_corr:,.2f} | ${delta:,.2f} |"
        )
    sum_orig_all = sum((c["original_gross_pnl"] for c in corrections), Decimal("0"))
    sum_corr_all = sum((c["corrected_gross_pnl"] for c in corrections), Decimal("0"))
    lines.extend([
        "",
        f"**Total Σ original gross_pnl across affected rows:** ${sum_orig_all:,.2f}",
        f"**Total Σ corrected gross_pnl across affected rows:** ${sum_corr_all:,.2f}",
        f"**Net correction (target − current):** ${(sum_corr_all - sum_orig_all):,.2f}",
        "",
        "## Per-row detail (limit 200)",
        "",
        "| trade_id | asset | direction | contracts | entry | exit | "
        "orig gross | corrected gross | delta |",
        "|----------|-------|-----------|-----------|-------|------|"
        "-----------|----------------|-------|",
    ])
    for c in corrections[:200]:
        r = c["row"]
        lines.append(
            f"| {r['trade_id']} | {r['asset']} | {r['direction']} | "
            f"{r['contracts']} | {r['entry_price']} | {r['exit_price']} | "
            f"${c['original_gross_pnl']:,.2f} | "
            f"${c['corrected_gross_pnl']:,.2f} | "
            f"${c['delta_gross_pnl']:,.2f} |"
        )
    if len(corrections) > 200:
        lines.append(f"\n_({len(corrections) - 200} more rows truncated)_")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    logger.info("Proposal written to %s", path)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Backfill D03 PnL inflation (Bug A historical correction).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--user", default=None,
                   help="Restrict to this user_id (default: ALL users).")
    p.add_argument("--apply", action="store_true",
                   help="Actually write correction rows to D03.")
    p.add_argument("--readers-audited", action="store_true",
                   help="REQUIRED with --apply. Acknowledges that all D03 "
                        "readers have been updated to LATEST-ON-trade_id "
                        "semantics, OR all consumers are stopped.")
    p.add_argument("--proposal-out", default=None,
                   help="Path to write proposal markdown report.")
    p.add_argument("--limit", type=int, default=None,
                   help="Cap number of corrections (debugging only).")
    args = p.parse_args(argv)

    if args.apply and not args.readers_audited:
        logger.error(
            "Refusing to --apply without --readers-audited. Read the "
            "BLOCKING SAFETY GATE section of this script's docstring."
        )
        return 2

    mode = "APPLY" if args.apply else "DRY-RUN"
    logger.info("=" * 72)
    logger.info(" backfill_d03_pnl_inflation — %s", mode)
    logger.info(" filter: user_id=%s", args.user or "<ALL>")
    logger.info("=" * 72)

    pv_lookup = load_d00_point_values()
    logger.info("D00 point_value lookup loaded for %d assets: %s",
                len(pv_lookup),
                ", ".join(f"{a}={pv}" for a, pv in sorted(pv_lookup.items())))
    if not pv_lookup:
        logger.error("D00 has no point_value rows — cannot compute corrections.")
        return 3

    rows = fetch_d03_rows(args.user)
    logger.info("Fetched %d LATEST D03 rows for analysis.", len(rows))

    corrections = []
    for row in rows:
        c = compute_correction(row, pv_lookup)
        if c is not None:
            corrections.append(c)
        if args.limit and len(corrections) >= args.limit:
            break

    logger.info("Identified %d rows requiring correction.", len(corrections))

    if args.proposal_out:
        write_proposal_markdown(corrections, args.proposal_out)

    if not corrections:
        logger.info("Nothing to do.")
        return 0

    if not args.apply:
        # Show summary
        by_asset: dict[str, int] = defaultdict(int)
        delta_by_asset: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for c in corrections:
            by_asset[c["asset"]] += 1
            delta_by_asset[c["asset"]] += c["delta_gross_pnl"]
        for asset in sorted(by_asset):
            logger.info(
                "  %-4s  rows=%4d  Σ delta gross_pnl=%s",
                asset, by_asset[asset], f"${delta_by_asset[asset]:,.2f}",
            )
        logger.info(
            "Total Σ delta gross_pnl across all corrections: %s",
            f"${sum(delta_by_asset.values(), Decimal('0')):,.2f}",
        )
        logger.info("=" * 72)
        logger.info(" DRY-RUN complete. To apply: --apply --readers-audited")
        logger.info("=" * 72)
        return 0

    # Apply
    written = 0
    for c in corrections:
        try:
            write_correction_row(c)
            written += 1
            if written % 25 == 0:
                logger.info("  ... wrote %d / %d correction rows",
                            written, len(corrections))
        except Exception as exc:
            logger.error("FAILED to write correction for trade_id=%s: %s",
                         c["trade_id"], exc)
            return 4

    logger.info("=" * 72)
    logger.info(" APPLY complete: %d correction rows written to D03.", written)
    logger.info(" Verify with: SELECT trade_id, gross_pnl, outcome FROM "
                "p3_d03_trade_outcome_log WHERE outcome LIKE '%%_CORRECTED' "
                "LATEST ON ts PARTITION BY trade_id;")
    logger.info("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
