"""Trade data source for pseudotrader replay.

Two modes:
    "synthetic" — Converts P1 backtest trade logs (d22_trade_log_*.json) into
                  the pseudotrader trade format. Uses real historical P&L from
                  P1 screening. Available immediately without live trading.

    "questdb"  — Reads actual trade outcomes from P3-D03 (populated by Online B7
                  during live/paper trading). Switch to this once the system is
                  producing real trades.

Both return list[dict] with identical keys:
    day, pnl, contracts, ts, model, asset, direction, regime

Usage:
    from shared.trade_source import load_trades

    # Synthetic (from P1 backtest data)
    trades = load_trades(source="synthetic", asset="ES")

    # Real trades (from P3-D03)
    trades = load_trades(source="questdb", asset="ES", account_id="acct-001")
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Default data directory (relative to captain-system root)
_DATA_DIR = Path(__file__).parent.parent / "data"
_P1_OUTPUTS_DIR = _DATA_DIR / "p1_outputs"


def load_trades(source: str = "synthetic",
                asset: str = "ES",
                account_id: str | None = None,
                user_id: str | None = None,
                start_date: str | None = None,
                end_date: str | None = None,
                data_dir: str | None = None,
                or_range_points: float | None = None) -> list[dict]:
    """Load trades from the specified source.

    Args:
        source: "synthetic" or "questdb"
        asset: Asset symbol (e.g. "ES", "NQ", "MES")
        account_id: Account filter (questdb only)
        user_id: User filter (questdb only)
        start_date: ISO date string filter (inclusive)
        end_date: ISO date string filter (inclusive)
        data_dir: Override data directory (for testing)
        or_range_points: Override avg opening range in points (synthetic only)

    Returns:
        List of trade dicts with keys: day, pnl, contracts, ts, model,
        asset, direction, regime
    """
    if source == "synthetic":
        return _load_synthetic(asset, start_date, end_date, data_dir,
                               or_range_points)
    elif source == "questdb":
        return _load_from_d03(asset, account_id, user_id, start_date, end_date)
    else:
        raise ValueError(f"Unknown trade source: {source!r}. Use 'synthetic' or 'questdb'.")


# ---------------------------------------------------------------------------
# Synthetic: P1 backtest trade logs
# ---------------------------------------------------------------------------

def _load_synthetic(asset: str,
                    start_date: str | None = None,
                    end_date: str | None = None,
                    data_dir: str | None = None,
                    or_range_points: float | None = None) -> list[dict]:
    """Convert P1 d22 trade log into pseudotrader replay format.

    P1 trade log format (d22_trade_log_*.json):
        trade_date: "2024-01-05"
        m: int (model index)
        k: int (feature index)
        s: int (sample period)
        x_mik: float (feature value / signal strength)
        r_mi: float (return in OR-range multiples, can be negative)
        regime_tag: float (regime label from P2)
        i: int (trade index)

    Conversion:
        day = trade_date
        pnl = r_mi * point_value * contracts (using OR-range convention)
        direction = 1 if r_mi > 0 else -1
        model = m
        contracts = 1 (P1 is always 1 contract)
    """
    base_dir = Path(data_dir) if data_dir else _P1_OUTPUTS_DIR
    asset_dir = base_dir / asset.upper()

    # Find the trade log file
    candidates = [
        asset_dir / f"d22_trade_log_{asset.lower()}.json",
        asset_dir / f"d22_trade_log_{asset.upper()}.json",
        asset_dir / "d22_trade_log.json",
        # Also check s1 (strategy 1) naming convention
        asset_dir / "s1_trade_log.json",
    ]

    trade_log_path = None
    for p in candidates:
        if p.exists():
            trade_log_path = p
            break

    if trade_log_path is None:
        logger.warning("No P1 trade log found for asset %s in %s", asset, asset_dir)
        return []

    with open(trade_log_path) as f:
        raw_trades = json.load(f)

    logger.info("Loaded %d raw P1 trades from %s", len(raw_trades), trade_log_path)

    # Point values for futures contracts (dollars per point)
    point_values = {
        "ES": 50.0, "MES": 5.0,
        "NQ": 20.0, "MNQ": 2.0,
        "M2K": 5.0, "MYM": 0.50,
        "NKD": 5.0, "MGC": 10.0,
        "ZB": 1000.0, "ZN": 1000.0, "ZT": 2000.0,
        "CL": 1000.0, "MCL": 100.0,
    }
    pv = point_values.get(asset.upper(), 50.0)

    # Average opening range in points (r_mi is in OR-range multiples).
    # pnl = r_mi * or_range * point_value * contracts
    # These are empirical averages — override with or_range_points param.
    default_or_ranges = {
        "ES": 4.0, "MES": 4.0,
        "NQ": 15.0, "MNQ": 15.0,
        "M2K": 8.0, "MYM": 40.0,
        "NKD": 100.0, "MGC": 3.0,
        "ZB": 0.25, "ZN": 0.15, "ZT": 0.08,
        "CL": 0.50, "MCL": 0.50,
    }
    or_range = or_range_points or default_or_ranges.get(asset.upper(), 4.0)

    trades = []
    for raw in raw_trades:
        trade_date = raw.get("trade_date", "")

        # Date filtering
        if start_date and trade_date < start_date:
            continue
        if end_date and trade_date > end_date:
            continue

        r_mi = raw.get("r_mi", 0.0)

        # r_mi is return in OR-range multiples.
        # pnl = r_mi * or_range_points * point_value * contracts
        pnl = r_mi * or_range * pv

        trades.append({
            "day": trade_date,
            "pnl": round(pnl, 2),
            "contracts": 1,
            "ts": f"{trade_date}T10:00:00",
            "model": raw.get("m", 0),
            "asset": asset.upper(),
            "direction": 1 if r_mi > 0 else (-1 if r_mi < 0 else 0),
            "regime": raw.get("regime_tag", 0.0),
            "feature_k": raw.get("k", 0),
            "sample_s": raw.get("s", 0),
            "raw_r_mi": r_mi,
        })

    # Sort by date
    trades.sort(key=lambda t: t["day"])

    logger.info("Converted %d trades for %s (%s to %s), pv=%.1f",
                len(trades), asset,
                trades[0]["day"] if trades else "N/A",
                trades[-1]["day"] if trades else "N/A",
                pv)

    return trades


# ---------------------------------------------------------------------------
# QuestDB: real trades from P3-D03
# ---------------------------------------------------------------------------

def _load_from_d03(asset: str,
                   account_id: str | None = None,
                   user_id: str | None = None,
                   start_date: str | None = None,
                   end_date: str | None = None) -> list[dict]:
    """Read trade outcomes from P3-D03 (populated by Online B7).

    This is the production path — used once the system is live trading.
    """
    from shared.questdb_client import get_cursor

    conditions = ["asset = %s"]
    params = [asset.upper()]

    if account_id:
        conditions.append("account_id = %s")
        params.append(account_id)
    if user_id:
        conditions.append("user_id = %s")
        params.append(user_id)
    if start_date:
        conditions.append("ts >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("ts <= %s")
        params.append(end_date)

    where_clause = " AND ".join(conditions)

    with get_cursor() as cur:
        cur.execute(
            f"""SELECT trade_id, pnl, contracts, entry_time, direction,
                       regime_at_entry, session, account_id, model_m
                FROM p3_d03_trade_outcome_log
                WHERE {where_clause}
                ORDER BY ts ASC""",
            tuple(params),
        )
        rows = cur.fetchall()

    trades = []
    for row in rows:
        trade_id, pnl, contracts, entry_time, direction, regime, session, acct, model_m = row

        # Extract day from entry_time
        if isinstance(entry_time, datetime):
            day = entry_time.strftime("%Y-%m-%d")
            ts = entry_time.isoformat()
        elif isinstance(entry_time, str):
            day = entry_time[:10]
            ts = entry_time
        else:
            day = str(entry_time)[:10]
            ts = str(entry_time)

        trades.append({
            "day": day,
            "pnl": float(pnl) if pnl else 0.0,
            "contracts": int(contracts) if contracts else 1,
            "ts": ts,
            "model": int(model_m) if model_m is not None else 4,
            "asset": asset.upper(),
            "direction": int(direction) if direction else 0,
            "regime": regime or "",
        })

    logger.info("Loaded %d trades from P3-D03 for %s (account=%s)",
                len(trades), asset, account_id or "all")

    return trades


# ---------------------------------------------------------------------------
# Convenience: load and immediately seed P3-D03 with synthetic data
# ---------------------------------------------------------------------------

def seed_d03_from_synthetic(asset: str = "ES",
                            user_id: str = "system",
                            account_id: str = "pseudo-eval-001",
                            start_date: str | None = None,
                            end_date: str | None = None) -> int:
    """Load synthetic trades and write them to P3-D03 for testing.

    This populates the same table that Online B7 writes to in production.
    Useful for testing the full pipeline without live trading.

    Returns:
        Number of trades written.
    """
    from shared.questdb_client import get_cursor

    trades = _load_synthetic(asset, start_date, end_date)
    if not trades:
        logger.warning("No synthetic trades to seed for %s", asset)
        return 0

    import uuid as _uuid
    with get_cursor() as cur:
        for i, t in enumerate(trades):
            cur.execute(
                """INSERT INTO p3_d03_trade_outcome_log
                   (trade_id, signal_id, user_id, account_id, asset, direction,
                    entry_price, signal_entry_price, exit_price, contracts,
                    gross_pnl, commission, pnl, slippage, outcome,
                    entry_time, regime_at_entry, aim_modifier_at_entry,
                    aim_breakdown_at_entry, session, tsm_used, model_m, ts)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                (
                    f"SYN-{asset}-{i:06d}",
                    f"LEGACY-{_uuid.uuid4()}",
                    user_id, account_id, asset.upper(),
                    t["direction"],
                    0.0, 0.0, 0.0,  # prices not available from P1 data
                    t["contracts"],
                    t["pnl"], 0.0, t["pnl"], 0.0,  # gross=net for synthetic
                    "SYNTHETIC",
                    t["ts"],
                    str(t.get("regime", "")),
                    1.0, None, 1,  # aim_modifier=1, session=NY
                    "SYNTHETIC",
                    t.get("model_m"),
                ),
            )

    logger.info("Seeded %d synthetic trades to P3-D03 for %s (account=%s)",
                len(trades), asset, account_id)
    return len(trades)


# ---------------------------------------------------------------------------
# Phase 7 — actual_trade_outcome (PG-09 line 357)
# ---------------------------------------------------------------------------

from dataclasses import dataclass
from datetime import date as _date, datetime as _dt, time as _time, timedelta
from zoneinfo import ZoneInfo


_ET = ZoneInfo("America/New_York")


@dataclass
class RealisedOutcome:
    """A realised D03 outcome row, as returned by ``actual_trade_outcome``.

    ``pnl`` is the net P&L (already minus commission). ``gross_pnl`` and
    ``commission`` are split out for reporting. When the helper aggregates
    multiple D03 rows for the same (user, asset, day), ``trade_id`` and
    ``signal_id`` reflect the first row in the day's series.
    """
    signal_id: str
    trade_id: str
    pnl: float
    gross_pnl: float
    commission: float
    contracts: int
    entry_price: float | None
    exit_price: float | None
    entry_time: _dt | None
    exit_time: _dt | None
    direction: int
    regime_at_entry: str | None


def actual_trade_outcome(
    d: _date,
    *,
    user_id: str,
    asset: str | None = None,
    signal_id: str | None = None,
) -> "RealisedOutcome | None":
    """Doc 32 PG-09 line 357 — realised P&L from D03 for session day ``d``.

    If ``signal_id`` is supplied, returns the matching trade (or ``None`` if
    not found). Otherwise returns the aggregate outcome for ``(user_id,
    asset)`` on day ``d`` as a single composite — sums pnl/gross_pnl/
    commission/contracts, takes first entry / last exit, first regime.

    The query window is the calendar day in America/New_York.
    """
    from shared.questdb_client import get_cursor

    et_start = _dt.combine(d, _time.min).replace(tzinfo=_ET)
    et_end = et_start + timedelta(days=1)

    if signal_id is not None:
        with get_cursor() as cur:
            cur.execute(
                """SELECT trade_id, signal_id, pnl, gross_pnl, commission,
                          contracts, entry_price, exit_price, entry_time,
                          exit_time, direction, regime_at_entry
                   FROM p3_d03_trade_outcome_log
                   WHERE signal_id = %s AND user_id = %s
                     AND entry_time >= %s AND entry_time < %s""",
                (signal_id, user_id, et_start.isoformat(), et_end.isoformat()),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_outcome(row)

    if asset is None:
        raise ValueError(
            "actual_trade_outcome requires either signal_id or asset"
        )

    with get_cursor() as cur:
        cur.execute(
            """SELECT trade_id, signal_id, pnl, gross_pnl, commission,
                      contracts, entry_price, exit_price, entry_time,
                      exit_time, direction, regime_at_entry
               FROM p3_d03_trade_outcome_log
               WHERE user_id = %s AND asset = %s
                 AND entry_time >= %s AND entry_time < %s
               ORDER BY entry_time ASC""",
            (user_id, asset, et_start.isoformat(), et_end.isoformat()),
        )
        rows = cur.fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return _row_to_outcome(rows[0])
    return _aggregate_outcomes(rows)


def _row_to_outcome(row: tuple) -> RealisedOutcome:
    (trade_id, signal_id, pnl, gross_pnl, commission, contracts,
     entry_price, exit_price, entry_time, exit_time, direction,
     regime_at_entry) = row
    return RealisedOutcome(
        signal_id=signal_id,
        trade_id=trade_id,
        pnl=float(pnl) if pnl is not None else 0.0,
        gross_pnl=float(gross_pnl) if gross_pnl is not None else 0.0,
        commission=float(commission) if commission is not None else 0.0,
        contracts=int(contracts) if contracts is not None else 0,
        entry_price=float(entry_price) if entry_price is not None else None,
        exit_price=float(exit_price) if exit_price is not None else None,
        entry_time=entry_time,
        exit_time=exit_time,
        direction=int(direction) if direction is not None else 0,
        regime_at_entry=regime_at_entry,
    )


def _aggregate_outcomes(rows: list[tuple]) -> RealisedOutcome:
    """Combine multiple D03 rows into one composite outcome (PG-09 daily)."""
    first = _row_to_outcome(rows[0])
    last_outcome = _row_to_outcome(rows[-1])
    total_pnl = sum(_safe_float(r[2]) for r in rows)
    total_gross = sum(_safe_float(r[3]) for r in rows)
    total_commission = sum(_safe_float(r[4]) for r in rows)
    total_contracts = sum(int(r[5] or 0) for r in rows)
    return RealisedOutcome(
        signal_id=first.signal_id,
        trade_id=first.trade_id,
        pnl=total_pnl,
        gross_pnl=total_gross,
        commission=total_commission,
        contracts=total_contracts,
        entry_price=first.entry_price,
        exit_price=last_outcome.exit_price,
        entry_time=first.entry_time,
        exit_time=last_outcome.exit_time,
        direction=first.direction,
        regime_at_entry=first.regime_at_entry,
    )


def _safe_float(v: object) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
