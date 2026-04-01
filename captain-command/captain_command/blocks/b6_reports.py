# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Captain Command — Block 6: Discretionary Reports (P3-PG-36).

11 report types (RPT-01 through RPT-11).  RPT-01/07 render in-app;
others are downloadable CSV/JSON.

Spec: Program3_Command.md lines 558-616
"""

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from shared.questdb_client import get_cursor
from shared.journal import write_checkpoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Report registry
# ---------------------------------------------------------------------------

REPORT_TYPES = {
    "RPT-01": {"name": "Pre-Session Signal Report", "trigger": "pre_session", "render": "in_app"},
    "RPT-02": {"name": "Weekly Performance Review", "trigger": "end_of_week", "render": "csv"},
    "RPT-03": {"name": "Monthly Decay & Warm-Up Report", "trigger": "first_of_month", "render": "csv"},
    "RPT-04": {"name": "AIM Effectiveness Report", "trigger": "monthly", "render": "csv"},
    "RPT-05": {"name": "Strategy Comparison Report", "trigger": "on_p1p2_run", "render": "csv"},
    "RPT-06": {"name": "Regime Change Report", "trigger": "regime_change", "render": "csv"},
    "RPT-07": {"name": "Daily Prop Account Report", "trigger": "daily", "render": "in_app"},
    "RPT-08": {"name": "Regime Calibration Report", "trigger": "monthly", "render": "csv"},
    "RPT-09": {"name": "Parameter Change Audit", "trigger": "on_demand", "render": "csv"},
    "RPT-10": {"name": "Annual Performance Report", "trigger": "annually", "render": "csv"},
    "RPT-11": {"name": "Financial Summary Export", "trigger": "monthly", "render": "csv"},
}


def generate_report(report_type: str, user_id: str, params: dict | None = None) -> dict:
    """Generate a report by type.

    Parameters
    ----------
    report_type : str
        One of RPT-01 through RPT-11.
    user_id : str
        The requesting user.
    params : dict or None
        Optional parameters (date range, asset filter, etc.).

    Returns
    -------
    dict
        ``{report_id, report_type, name, format, data, generated_at}``
        For CSV reports, ``data`` is a CSV string.
        For in-app reports, ``data`` is a dict for rendering.
    """
    if report_type not in REPORT_TYPES:
        return {"error": f"Unknown report type: {report_type}"}

    params = params or {}
    report_id = f"RPT-{uuid.uuid4().hex[:12].upper()}"
    meta = REPORT_TYPES[report_type]

    write_checkpoint("COMMAND", f"REPORT_{report_type}", "generating", "complete",
                     {"report_id": report_id, "user_id": user_id})

    generators = {
        "RPT-01": _rpt01_pre_session,
        "RPT-02": _rpt02_weekly_performance,
        "RPT-03": _rpt03_monthly_decay,
        "RPT-04": _rpt04_aim_effectiveness,
        "RPT-05": _rpt05_strategy_comparison,
        "RPT-06": _rpt06_regime_change,
        "RPT-07": _rpt07_daily_prop,
        "RPT-08": _rpt08_regime_calibration,
        "RPT-09": _rpt09_parameter_audit,
        "RPT-10": _rpt10_annual_performance,
        "RPT-11": _rpt11_financial_export,
    }

    gen_fn = generators.get(report_type)
    data = gen_fn(user_id, params) if gen_fn else {}

    result = {
        "report_id": report_id,
        "report_type": report_type,
        "name": meta["name"],
        "format": meta["render"],
        "data": data,
        "generated_at": datetime.now().isoformat(),
    }

    _archive_report(report_id, report_type, user_id, result)
    return result


# ---------------------------------------------------------------------------
# RPT-01: Pre-Session Signal Report (in-app)
# ---------------------------------------------------------------------------


def _rpt01_pre_session(user_id: str, params: dict) -> dict:
    """Signal details, AIM breakdown, Kelly, TSM status, regime."""
    try:
        with get_cursor() as cur:
            # Latest signals for this user
            cur.execute(
                """SELECT event_id, asset, details, ts
                   FROM p3_session_event_log
                   WHERE user_id = %s AND event_type = 'SIGNAL_RECEIVED'
                   ORDER BY ts DESC LIMIT 10""",
                (user_id,),
            )
            signals = []
            for r in cur.fetchall():
                detail = json.loads(r[2]) if r[2] else {}
                signals.append({"signal_id": r[0], "asset": r[1], "timestamp": r[3], **detail})

            # Regime state
            cur.execute(
                "SELECT asset_id, captain_status FROM p3_d00_asset_universe WHERE captain_status = 'ACTIVE'"
            )
            assets = [{"asset_id": r[0], "status": r[1]} for r in cur.fetchall()]

            return {"signals": signals, "active_assets": assets}
    except Exception as exc:
        logger.error("RPT-01 failed: %s", exc, exc_info=True)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# RPT-02: Weekly Performance Review (CSV)
# ---------------------------------------------------------------------------


def _rpt02_weekly_performance(user_id: str, params: dict) -> str:
    """Win/loss by asset, actual vs predicted edge, AIM contribution."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset, direction, outcome, pnl, expected_edge,
                          combined_modifier, regime_state, timestamp
                   FROM p3_d03_trade_outcome_log
                   WHERE user_id = %s AND timestamp > dateadd('d', -7, now())
                   ORDER BY timestamp""",
                (user_id,),
            )
            rows = cur.fetchall()
            return _to_csv(
                ["asset", "direction", "outcome", "pnl", "expected_edge",
                 "combined_modifier", "regime_state", "timestamp"],
                rows,
            )
    except Exception as exc:
        logger.error("RPT-02 failed: %s", exc, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# RPT-03: Monthly Decay & Warm-Up Report (CSV)
# ---------------------------------------------------------------------------


def _rpt03_monthly_decay(user_id: str, params: dict) -> str:
    """BOCPD/CUSUM state, AIM warm-up, meta-weights, TSM tracking."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset, cp_prob, cusum_stat, level, timestamp
                   FROM p3_d04_decay_detector_states
                   ORDER BY timestamp DESC LIMIT 50"""
            )
            rows = cur.fetchall()
            return _to_csv(["asset", "cp_prob", "cusum_stat", "level", "timestamp"], rows)
    except Exception as exc:
        logger.error("RPT-03 failed: %s", exc, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# RPT-04: AIM Effectiveness Report (CSV)
# ---------------------------------------------------------------------------


def _rpt04_aim_effectiveness(user_id: str, params: dict) -> str:
    """RPT-04: AIM Effectiveness Report — P3-RPT-04 generation spec.

    Reads:
      - P3-D01 (aim_model_states): current status, last_retrained per AIM×asset
      - P3-D02 (aim_meta_weights): inclusion_probability trajectory, days_below_threshold
      - P3-D03 (trade_outcome_log): aim_breakdown_at_entry, pnl per trade (last N days)

    Computes per AIM×asset:
      1. Current DMA weight (inclusion_probability from latest D02 row)
      2. Weight trend: compare current weight to weight 30 days ago (rising/falling/stable)
      3. Modifier accuracy: for trades where this AIM was active, compare modifier
         direction (>1.0 = size up, <1.0 = size down) against trade outcome (win/loss)
         — accuracy = correct_calls / total_calls
      4. PnL contribution: sum of (pnl × aim_weight / total_weight) for trades
         where this AIM was active
      5. Days suppressed: days_below_threshold from D02

    Output: CSV with columns per AIM×asset row.
    Trigger: Monthly (Offline orchestrator _run_monthly) or on-demand via GUI.
    """
    days = params.get("days", 30)
    try:
        rows = []
        with get_cursor() as cur:
            # 1. Current AIM states + DMA weights
            cur.execute(
                """SELECT d1.aim_id, d1.asset_id, d1.status, d1.last_retrained,
                          d2.inclusion_probability, d2.inclusion_flag,
                          d2.days_below_threshold, d2.recent_effectiveness
                   FROM p3_d01_aim_model_states d1
                   LEFT JOIN p3_d02_aim_meta_weights d2
                     ON d1.aim_id = d2.aim_id AND d1.asset_id = d2.asset_id
                   ORDER BY d1.asset_id, d1.aim_id"""
            )
            aim_rows = cur.fetchall()

            # 2. Trade outcomes with AIM breakdowns for modifier accuracy
            cur.execute(
                """SELECT asset, pnl, aim_breakdown_at_entry, aim_modifier_at_entry, ts
                   FROM p3_d03_trade_outcome_log
                   WHERE ts > dateadd('d', -%s, now())
                   ORDER BY ts""",
                (days,),
            )
            trades = cur.fetchall()

        # Parse AIM breakdowns from trades to compute per-AIM accuracy
        aim_stats = {}  # (aim_id, asset) -> {correct: int, total: int, pnl_contribution: float}
        for asset, pnl, breakdown_raw, combined_mod, ts in trades:
            breakdown = json.loads(breakdown_raw) if breakdown_raw else {}
            total_weight = sum(
                v.get("dma_weight", 0) for v in breakdown.values()
                if isinstance(v, dict)
            )
            for aim_id_str, aim_data in breakdown.items():
                if not isinstance(aim_data, dict):
                    continue
                try:
                    aid = int(aim_id_str)
                except (ValueError, TypeError):
                    continue
                key = (aid, asset)
                if key not in aim_stats:
                    aim_stats[key] = {"correct": 0, "total": 0, "pnl_contribution": 0.0}

                mod = aim_data.get("modifier", 1.0)
                weight = aim_data.get("dma_weight", 0)
                aim_stats[key]["total"] += 1

                # Accuracy: modifier > 1.0 predicted "size up" — correct if pnl > 0
                #           modifier < 1.0 predicted "size down" — correct if pnl < 0
                if (mod > 1.0 and pnl > 0) or (mod < 1.0 and pnl < 0):
                    aim_stats[key]["correct"] += 1
                elif abs(mod - 1.0) < 0.01:
                    # Neutral modifier — count as correct (no prediction made)
                    aim_stats[key]["correct"] += 1

                # PnL contribution (weighted share of trade PnL)
                if total_weight > 0 and weight > 0:
                    aim_stats[key]["pnl_contribution"] += pnl * (weight / total_weight)

        # Build output rows
        for aim_id, asset_id, status, last_retrained, inc_prob, inc_flag, days_below, effectiveness in aim_rows:
            key = (aim_id, asset_id)
            stats = aim_stats.get(key, {"correct": 0, "total": 0, "pnl_contribution": 0.0})
            accuracy = (stats["correct"] / stats["total"] * 100) if stats["total"] > 0 else None

            rows.append((
                aim_id, asset_id, status,
                round(inc_prob, 4) if inc_prob else None,
                inc_flag,
                days_below or 0,
                round(effectiveness, 4) if effectiveness else None,
                stats["total"],
                round(accuracy, 1) if accuracy is not None else None,
                round(stats["pnl_contribution"], 2),
                str(last_retrained) if last_retrained else None,
            ))

        return _to_csv(
            ["aim_id", "asset_id", "status", "dma_weight", "included",
             "days_below_threshold", "recent_effectiveness", "trade_count",
             "accuracy_pct", "pnl_contribution", "last_retrained"],
            rows,
        )
    except Exception as exc:
        logger.error("RPT-04 failed: %s", exc, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# RPT-05: Strategy Comparison Report (CSV)
# ---------------------------------------------------------------------------


def _rpt05_strategy_comparison(user_id: str, params: dict) -> str:
    """Current vs proposed strategy comparison from P3-D06/D11."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT candidate_id, asset, recommendation, sharpe_current,
                          sharpe_proposed, drawdown_current, drawdown_proposed,
                          timestamp
                   FROM p3_d06_injection_history
                   ORDER BY timestamp DESC LIMIT 20"""
            )
            rows = cur.fetchall()
            return _to_csv(
                ["candidate_id", "asset", "recommendation", "sharpe_current",
                 "sharpe_proposed", "drawdown_current", "drawdown_proposed", "timestamp"],
                rows,
            )
    except Exception as exc:
        logger.error("RPT-05 failed: %s", exc, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# RPT-06: Regime Change Report (CSV)
# ---------------------------------------------------------------------------


def _rpt06_regime_change(user_id: str, params: dict) -> str:
    """Detection method, transition direction, edge impact, AIM states."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT event_id, asset, details, ts
                   FROM p3_session_event_log
                   WHERE event_type = 'REGIME_CHANGE'
                   ORDER BY ts DESC LIMIT 20"""
            )
            rows = cur.fetchall()
            return _to_csv(["event_id", "asset", "details", "timestamp"], rows)
    except Exception as exc:
        logger.error("RPT-06 failed: %s", exc, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# RPT-07: Daily Prop Account Report (in-app)
# ---------------------------------------------------------------------------


def _rpt07_daily_prop(user_id: str, params: dict) -> dict:
    """Drawdown vs MDD, pass probability, risk budget, sizing recommendations."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT account_id, tsm_name, current_balance, starting_balance,
                          max_drawdown_limit, max_daily_loss, daily_loss_used,
                          pass_probability
                   FROM p3_d08_tsm_state
                   WHERE user_id = %s""",
                (user_id,),
            )
            accounts = []
            for r in cur.fetchall():
                bal = r[2] or 0
                start = r[3] or 0
                mdd = r[4] or 0
                mll = r[5] or 0
                daily_used = r[6] or 0
                drawdown = start - bal if start and bal else 0

                accounts.append({
                    "account_id": r[0],
                    "tsm_name": r[1],
                    "balance": bal,
                    "drawdown": round(drawdown, 2),
                    "mdd_limit": mdd,
                    "mdd_remaining": round(mdd - drawdown, 2),
                    "mdd_pct_used": round(drawdown / mdd * 100, 1) if mdd > 0 else 0,
                    "daily_loss_limit": mll,
                    "daily_loss_used": daily_used,
                    "daily_budget_remaining": round(mll - daily_used, 2),
                    "pass_probability": r[7],
                })
            return {"accounts": accounts}
    except Exception as exc:
        logger.error("RPT-07 failed: %s", exc, exc_info=True)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# RPT-08: Regime Calibration Report (CSV)
# ---------------------------------------------------------------------------


def _rpt08_regime_calibration(user_id: str, params: dict) -> str:
    """Regime probability calibration, expected vs actual edge by decile."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset, direction, outcome, expected_edge,
                          regime_state, regime_prob, timestamp
                   FROM p3_d03_trade_outcome_log
                   WHERE timestamp > dateadd('d', -30, now())
                   ORDER BY timestamp"""
            )
            rows = cur.fetchall()
            return _to_csv(
                ["asset", "direction", "outcome", "expected_edge",
                 "regime_state", "regime_prob", "timestamp"],
                rows,
            )
    except Exception as exc:
        logger.error("RPT-08 failed: %s", exc, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# RPT-09: Parameter Change Audit (CSV)
# ---------------------------------------------------------------------------


def _rpt09_parameter_audit(user_id: str, params: dict) -> str:
    """Parameter change history with context and counterfactual analysis."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT event_id, event_type, details, ts, user_id
                   FROM p3_session_event_log
                   WHERE event_type IN ('PARAM_CHANGE', 'TSM_SWITCH',
                                        'MANUAL_PAUSE', 'MANUAL_RESUME')
                   ORDER BY ts DESC LIMIT 100"""
            )
            rows = cur.fetchall()
            return _to_csv(
                ["event_id", "event_type", "details", "timestamp", "user_id"],
                rows,
            )
    except Exception as exc:
        logger.error("RPT-09 failed: %s", exc, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# RPT-10: Annual Performance Report (CSV)
# ---------------------------------------------------------------------------


def _rpt10_annual_performance(user_id: str, params: dict) -> str:
    """Full-year performance, AIM value-add, decay events, injection history."""
    year = params.get("year", datetime.now().year)
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT asset, direction, outcome, pnl, expected_edge,
                          combined_modifier, regime_state, account_id, timestamp
                   FROM p3_d03_trade_outcome_log
                   WHERE user_id = %s
                     AND timestamp >= %s AND timestamp < %s
                   ORDER BY timestamp""",
                (user_id, f"{year}-01-01", f"{year + 1}-01-01"),
            )
            rows = cur.fetchall()
            return _to_csv(
                ["asset", "direction", "outcome", "pnl", "expected_edge",
                 "combined_modifier", "regime_state", "account_id", "timestamp"],
                rows,
            )
    except Exception as exc:
        logger.error("RPT-10 failed: %s", exc, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# RPT-11: Financial Summary Export (CSV, ADMIN only)
# ---------------------------------------------------------------------------


def _rpt11_financial_export(user_id: str, params: dict) -> str:
    """Trade log (gross/net PnL, commission, slippage), account history."""
    days = params.get("days", 30)
    try:
        with get_cursor() as cur:
            cur.execute(
                """SELECT signal_id, asset, direction, outcome, pnl,
                          commission, slippage, account_id, entry_price,
                          exit_price, contracts, timestamp
                   FROM p3_d03_trade_outcome_log
                   WHERE user_id = %s
                     AND timestamp > dateadd('d', -%s, now())
                   ORDER BY timestamp""",
                (user_id, days),
            )
            rows = cur.fetchall()
            return _to_csv(
                ["signal_id", "asset", "direction", "outcome", "pnl",
                 "commission", "slippage", "account_id", "entry_price",
                 "exit_price", "contracts", "timestamp"],
                rows,
            )
    except Exception as exc:
        logger.error("RPT-11 failed: %s", exc, exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_csv(headers: list[str], rows: list[tuple]) -> str:
    """Convert query results to a CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def _archive_report(report_id: str, report_type: str, user_id: str, result: dict):
    """Store report metadata in P3-D09 report_archive."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d09_report_archive(
                       timestamp, report_id, report_type, user_id,
                       name, format, generated_at
                   ) VALUES(%s, %s, %s, %s, %s, %s, %s)""",
                (
                    datetime.now().isoformat(),
                    report_id,
                    report_type,
                    user_id,
                    result.get("name", ""),
                    result.get("format", "csv"),
                    result.get("generated_at", ""),
                ),
            )
    except Exception as exc:
        logger.error("Report archive insert failed: %s", exc, exc_info=True)
