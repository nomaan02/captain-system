#!/usr/bin/env python3
"""verify_questdb_state.py — Captain System QuestDB readiness & health audit.

Checks every table in the Captain System QuestDB schema against the expected
production state (bootstrap counts, field population, daily data freshness,
feedback-loop liveness, schema drift) and emits a structured report that
surfaces everything that would degrade trade signals or sizing.

USAGE
-----
    python scripts/verify_questdb_state.py                # stdout text report
    python scripts/verify_questdb_state.py --report out.md
    python scripts/verify_questdb_state.py --json         # machine-readable
    python scripts/verify_questdb_state.py --strict       # exit 1 on any WARN

EXIT CODES
----------
    0 = no CRITICAL findings (ready to trade, modulo warnings)
    1 = CRITICAL findings present (or any WARN if --strict)
    2 = could not connect to QuestDB

DESIGN
------
Every check is wrapped so one bad query cannot mask the rest of the report.
Each finding has: section, check, status (OK|INFO|WARN|CRITICAL), detail,
and optionally the affected table / suggested fix.

Expected state is derived from:
  - CLAUDE.md (10 assets, 6 Tier-1 AIMs, 3 sessions, $150K capital)
  - scripts/init_questdb.py (schema — source of truth)
  - scripts/bootstrap_production.py (bootstrap row values)
  - Obsidian specs docs 24/31/32/33/34
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.questdb_client import get_connection, get_cursor  # noqa: E402


# ---------------------------------------------------------------------------
# Expected state
# ---------------------------------------------------------------------------

EXPECTED_ASSETS = ["ES", "MES", "NQ", "MNQ", "M2K", "MYM", "NKD", "MGC", "ZB", "ZN"]
TIER1_AIMS = [4, 6, 8, 11, 12, 15]
REGIMES = ["LOW_VOL", "HIGH_VOL"]
# Session IDs are 1-indexed in live DB: 1=APAC, 2=LON, 3=NY (verified against
# p3_d05_ewma_states contents — bootstrap produces all 3 sessions per asset).
SESSIONS = [1, 2, 3]

# Required locked_strategy keys (subset — must at minimum identify the strategy)
LOCKED_STRATEGY_REQUIRED = {"model", "feature", "OO"}
# Optional but expected for risk management
LOCKED_STRATEGY_OPTIONAL = {"regime_class", "regime_method", "tp_mult", "sl_mult",
                            "accuracy_OOS", "confidence_flag", "source"}

# Valid enum values
VALID_CAPTAIN_STATUS = {"ACTIVE", "WARM_UP", "DECAYED", "HALTED", "PAUSED"}
VALID_AIM_STATUS = {"INSTALLED", "BOOTSTRAPPED", "ACTIVE", "COLLECTING",
                    "TRAINED", "WARMUP", "DECAY_L1", "DECAY_L2", "DECAY_L3"}
ELIMINATED_STATUS = {"P1_ELIMINATED", "P2_ELIMINATED"}
VALID_RISK_GOALS = {"GROW_CAPITAL", "PRESERVE_CAPITAL", "PASS_EVAL"}

# Bootstrap row counts (distinct-key basis, after LATEST ON resolution)
EXPECTED_BOOTSTRAP_ROWS = {
    "p3_d00_asset_universe":        (10, "asset_id"),
    "p3_d01_aim_model_states":      (60, "aim_id,asset_id"),
    "p3_d02_aim_meta_weights":      (60, "aim_id,asset_id"),
    "p3_d04_decay_detector_states": (10, "asset_id"),
    "p3_d05_ewma_states":           (60, "asset_id,regime,session"),
    "p3_d12_kelly_parameters":      (60, "asset_id,regime,session"),
    "p3_d16_user_capital_silos":    (1,  "user_id"),
    # D26 HMM opportunity state is written by captain-offline b1_aim16_hmm at
    # runtime (Baum-Welch EM on ≥20 days of session observations). On a fresh
    # install there is no history, so the row legitimately does not exist —
    # the dedicated check_d26() emits WARN with the correct remediation.
}

# All tables that init_questdb.py creates. Missing tables are CRITICAL.
REQUIRED_TABLES = [
    "p3_d00_asset_universe",
    "p3_d01_aim_model_states",
    "p3_d02_aim_meta_weights",
    "p3_d03_trade_outcome_log",
    "p3_d04_decay_detector_states",
    "p3_d05_ewma_states",
    "p3_d06_injection_history",
    "p3_d06b_active_transitions",
    "p3_d07_correlation_model_states",
    "p3_d08_tsm_state",
    "p3_d09_report_archive",
    "p3_d10_notification_log",
    "p3_d11_pseudotrader_results",
    "p3_d12_kelly_parameters",
    "p3_d13_sensitivity_scan_results",
    "p3_d14_api_connection_states",
    "p3_d15_user_session_data",
    "p3_d16_user_capital_silos",
    "p3_d17_system_monitor_state",
    "p3_d18_version_history",
    "p3_d19_reconciliation_log",
    "p3_d21_incident_log",
    "p3_d22_system_health_diagnostic",
    "p3_d23_circuit_breaker_intraday",
    "p3_d25_circuit_breaker_params",
    "p3_d26_hmm_opportunity_state",
    "p3_d27_pseudotrader_forecasts",
    "p3_d28_account_lifecycle",
    "p3_d29_opening_volumes",
    "p3_d30_daily_ohlcv",
    "p3_d31_implied_vol",
    "p3_d32_options_skew",
    "p3_d33_opening_volatility",
    "p3_spread_history",
    "p3_session_event_log",
    "p3_offline_job_queue",
    "p3_replay_results",
    "p3_replay_presets",
    "p3_audit_log",
]

# Column set per init_questdb.py:89-97 (authoritative D02 schema)
D02_EXPECTED_COLS = {
    "aim_id", "asset_id", "inclusion_probability", "inclusion_flag",
    "recent_effectiveness", "days_below_threshold", "last_updated",
}

# Freshness SLA: max hours since last append. WARN if exceeded.
FRESHNESS_SLA_HOURS = {
    "p3_d17_system_monitor_state":     2,   # heartbeat
    "p3_d22_system_health_diagnostic": 48,
    "p3_d30_daily_ohlcv":              72,
    "p3_d29_opening_volumes":          72,
    "p3_d33_opening_volatility":       72,
    "p3_d31_implied_vol":              96,
    "p3_d32_options_skew":             96,
    "p3_spread_history":               72,
}


# ---------------------------------------------------------------------------
# Report scaffolding
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    section: str
    check: str
    status: str          # OK | INFO | WARN | CRITICAL
    detail: str = ""
    table: str = ""
    fix: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add(self, section: str, check: str, status: str,
            detail: str = "", table: str = "", fix: str = "") -> None:
        self.findings.append(Finding(section, check, status, detail, table, fix))

    def counts(self) -> dict[str, int]:
        c = {"OK": 0, "INFO": 0, "WARN": 0, "CRITICAL": 0}
        for f in self.findings:
            c[f.status] = c.get(f.status, 0) + 1
        return c

    def critical(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "CRITICAL"]

    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == "WARN"]


# ---------------------------------------------------------------------------
# Query helpers (all tolerant — failures become WARN, never crash)
# ---------------------------------------------------------------------------

def _fetchall(cur, sql: str, args: tuple = ()) -> list[tuple]:
    cur.execute(sql, args)
    return cur.fetchall()


def _scalar(cur, sql: str, args: tuple = ()):
    cur.execute(sql, args)
    row = cur.fetchone()
    return row[0] if row else None


def list_tables(cur) -> set[str]:
    for sql in ("SELECT table_name FROM tables()",
                "SELECT name FROM tables()",
                "SHOW TABLES"):
        try:
            return {r[0] for r in _fetchall(cur, sql)}
        except Exception:
            continue
    return set()


def show_columns(cur, table: str) -> set[str]:
    try:
        return {r[0] for r in _fetchall(cur, f"SHOW COLUMNS FROM {table}")}
    except Exception:
        return set()


def raw_count(cur, table: str) -> int:
    try:
        return int(_scalar(cur, f"SELECT count() FROM {table}") or 0)
    except Exception:
        return -1


def latest_distinct_count(cur, table: str, ts_col: str, key_cols: str) -> int:
    """Count distinct-key rows after LATEST ON resolution."""
    try:
        sql = (
            f"SELECT count() FROM ("
            f"  SELECT {key_cols} FROM {table} "
            f"  LATEST ON {ts_col} PARTITION BY {key_cols}"
            f")"
        )
        return int(_scalar(cur, sql) or 0)
    except Exception:
        # Fallback: grouped count
        try:
            sql = f"SELECT count() FROM (SELECT {key_cols} FROM {table} GROUP BY {key_cols})"
            return int(_scalar(cur, sql) or 0)
        except Exception:
            return -1


def max_timestamp(cur, table: str, ts_col: str) -> datetime | None:
    try:
        v = _scalar(cur, f"SELECT max({ts_col}) FROM {table}")
        if v is None:
            return None
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return None
    except Exception:
        return None


def age_hours(ts: datetime | None) -> float | None:
    if ts is None:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0


def fmt_age(ts: datetime | None) -> str:
    h = age_hours(ts)
    if h is None:
        return "never"
    if h < 1:
        return f"{int(h * 60)}m ago"
    if h < 48:
        return f"{h:.1f}h ago"
    return f"{h/24:.1f}d ago"


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------

def check_connectivity(report: Report) -> bool:
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        host = os.environ.get("QUESTDB_HOST", "localhost")
        port = os.environ.get("QUESTDB_PORT", "8812")
        report.add("Connectivity", "PostgreSQL wire connect", "OK",
                   f"{host}:{port} db={os.environ.get('QUESTDB_DB', 'qdb')}")
        return True
    except Exception as e:
        report.add("Connectivity", "PostgreSQL wire connect", "CRITICAL",
                   str(e), fix="Start QuestDB: bash captain-start.sh")
        return False


def check_tables_exist(cur, report: Report) -> set[str]:
    live = list_tables(cur)
    missing = [t for t in REQUIRED_TABLES if t not in live]
    present = [t for t in REQUIRED_TABLES if t in live]
    if missing:
        for t in missing:
            report.add("Schema", f"missing table: {t}", "CRITICAL",
                       table=t, fix="python scripts/init_questdb.py")
    report.add("Schema", "required tables present",
               "OK" if not missing else "CRITICAL",
               f"{len(present)}/{len(REQUIRED_TABLES)} present")
    extras = sorted(t for t in live - set(REQUIRED_TABLES)
                    if not t.startswith("sys.") and t not in {"telemetry", "telemetry_config"})
    if extras:
        report.add("Schema", "unexpected tables", "INFO", ", ".join(extras))
    return live


def check_d02_schema(cur, report: Report) -> None:
    cols = show_columns(cur, "p3_d02_aim_meta_weights")
    if not cols:
        return  # missing-table finding already raised
    missing = D02_EXPECTED_COLS - cols
    if missing:
        report.add(
            "Schema drift", "D02 column mismatch", "CRITICAL",
            f"missing columns: {sorted(missing)}. "
            f"compact_questdb_tables.py likely regenerated the table with the wrong DDL.",
            table="p3_d02_aim_meta_weights",
            fix="Re-run: python scripts/init_questdb.py "
                "(and patch compact_questdb_tables.py to mirror init schema)",
        )
    else:
        report.add("Schema drift", "D02 columns match spec", "OK",
                   table="p3_d02_aim_meta_weights")


def check_bootstrap_counts(cur, report: Report) -> None:
    for table, (expected, key) in EXPECTED_BOOTSTRAP_ROWS.items():
        if key == "(singleton)":
            actual = raw_count(cur, table)
            actual = min(actual, 1) if actual >= 1 else actual
        else:
            actual = latest_distinct_count(cur, table, "last_updated", key)
        if actual < 0:
            report.add("Bootstrap", f"count {table}", "WARN",
                       "query failed — table may be missing or unreadable",
                       table=table)
            continue
        if actual == 0:
            report.add("Bootstrap", f"count {table}", "CRITICAL",
                       f"0 rows (expected {expected} by {key})", table=table,
                       fix="python scripts/bootstrap_production.py")
        elif actual < expected:
            report.add("Bootstrap", f"count {table}", "CRITICAL",
                       f"{actual}/{expected} distinct {key}", table=table,
                       fix="python scripts/bootstrap_production.py")
        elif actual > expected:
            report.add("Bootstrap", f"count {table}", "WARN",
                       f"{actual}/{expected} — more keys than expected "
                       f"(stale/extra assets or duplicate inserts)", table=table)
        else:
            report.add("Bootstrap", f"count {table}", "OK",
                       f"{actual} distinct {key}", table=table)


# -- D00 asset universe ----------------------------------------------------

def check_d00_fields(cur, report: Report) -> None:
    try:
        rows = _fetchall(cur, """
            SELECT asset_id, captain_status, warm_up_progress, locked_strategy,
                   point_value, tick_size, margin_per_contract, exchange_timezone
            FROM p3_d00_asset_universe
            LATEST ON last_updated PARTITION BY asset_id
        """)
    except Exception as e:
        report.add("D00 asset_universe", "read", "CRITICAL", str(e),
                   table="p3_d00_asset_universe")
        return

    seen = {r[0] for r in rows}
    for a in EXPECTED_ASSETS:
        if a not in seen:
            report.add("D00 asset_universe", f"missing asset {a}", "CRITICAL",
                       "no row for this asset — signals cannot use locked strategy",
                       table="p3_d00_asset_universe",
                       fix="python scripts/bootstrap_production.py")

    for asset_id, status, warmup, locked, pv, tick, margin, tz in rows:
        if asset_id not in EXPECTED_ASSETS:
            sev = "INFO" if status in ELIMINATED_STATUS else "WARN"
            report.add("D00 asset_universe", f"extra asset {asset_id}", sev,
                       f"status={status} (not in the 10 active trading assets)",
                       table="p3_d00_asset_universe")
            continue
        if status not in VALID_CAPTAIN_STATUS:
            report.add("D00 asset_universe", f"{asset_id}.captain_status",
                       "CRITICAL", f"value={status!r}", table="p3_d00_asset_universe")
        elif status == "WARM_UP":
            report.add("D00 asset_universe", f"{asset_id}.captain_status",
                       "WARN", "WARM_UP — signals will be skipped until ACTIVE",
                       table="p3_d00_asset_universe",
                       fix="Wait for warmup, or trigger offline B1 training")
        elif status != "ACTIVE":
            report.add("D00 asset_universe", f"{asset_id}.captain_status",
                       "WARN", f"status={status} (not ACTIVE)",
                       table="p3_d00_asset_universe")
        if warmup is None:
            report.add("D00 asset_universe", f"{asset_id}.warm_up_progress",
                       "WARN", "NULL", table="p3_d00_asset_universe")
        elif warmup < 1.0:
            sev = "WARN" if warmup >= 0.5 else "CRITICAL"
            report.add("D00 asset_universe", f"{asset_id}.warm_up_progress",
                       sev, f"{warmup} < 1.0 — AIM warmup incomplete",
                       table="p3_d00_asset_universe")
        # locked_strategy JSON validity
        if not locked or locked.strip() in ("", "{}"):
            report.add("D00 asset_universe", f"{asset_id}.locked_strategy",
                       "CRITICAL", "empty or {} — signals cannot run",
                       table="p3_d00_asset_universe",
                       fix="python scripts/bootstrap_production.py "
                           "(or scripts/fix_locked_strategies.py)")
        else:
            try:
                parsed = json.loads(locked)
                if not isinstance(parsed, dict) or not parsed:
                    report.add("D00 asset_universe",
                               f"{asset_id}.locked_strategy", "CRITICAL",
                               "empty object", table="p3_d00_asset_universe")
                else:
                    missing_req = LOCKED_STRATEGY_REQUIRED - set(parsed.keys())
                    if missing_req:
                        report.add("D00 asset_universe",
                                   f"{asset_id}.locked_strategy keys",
                                   "CRITICAL",
                                   f"missing required: {sorted(missing_req)}",
                                   table="p3_d00_asset_universe")
                    missing_opt = LOCKED_STRATEGY_OPTIONAL - set(parsed.keys())
                    # Only warn about tp_mult/sl_mult (directly used by sizing)
                    risk_missing = {"tp_mult", "sl_mult"} & missing_opt
                    if risk_missing:
                        report.add("D00 asset_universe",
                                   f"{asset_id}.locked_strategy TP/SL",
                                   "WARN",
                                   f"missing {sorted(risk_missing)} — "
                                   "sizing will use fallback defaults",
                                   table="p3_d00_asset_universe")
            except Exception as e:
                report.add("D00 asset_universe",
                           f"{asset_id}.locked_strategy JSON",
                           "CRITICAL", f"invalid JSON: {e}",
                           table="p3_d00_asset_universe")
        if not pv or pv <= 0:
            report.add("D00 asset_universe", f"{asset_id}.point_value",
                       "CRITICAL", f"{pv} — sizing will break",
                       table="p3_d00_asset_universe")
        if not tick or tick <= 0:
            report.add("D00 asset_universe", f"{asset_id}.tick_size",
                       "CRITICAL", f"{tick} — TP/SL alignment will break",
                       table="p3_d00_asset_universe")
        if not margin or margin <= 0:
            report.add("D00 asset_universe", f"{asset_id}.margin_per_contract",
                       "WARN", f"{margin}", table="p3_d00_asset_universe")
        if tz != "America/New_York" and tz not in ("America/Chicago", "Asia/Tokyo", "Europe/London"):
            report.add("D00 asset_universe", f"{asset_id}.exchange_timezone",
                       "WARN", f"unusual tz={tz!r}",
                       table="p3_d00_asset_universe")


# -- D01 AIM model states --------------------------------------------------

def check_d01_aim_states(cur, report: Report) -> None:
    try:
        rows = _fetchall(cur, """
            SELECT aim_id, asset_id, status, warmup_progress, model_object
            FROM p3_d01_aim_model_states
            LATEST ON last_updated PARTITION BY aim_id, asset_id
        """)
    except Exception as e:
        report.add("D01 aim_states", "read", "CRITICAL", str(e),
                   table="p3_d01_aim_model_states")
        return

    seen = {(r[0], r[1]) for r in rows}
    for a in EXPECTED_ASSETS:
        for aim in TIER1_AIMS:
            if (aim, a) not in seen:
                report.add("D01 aim_states",
                           f"missing AIM-{aim}/{a}", "CRITICAL",
                           "no model state — this AIM will not contribute",
                           table="p3_d01_aim_model_states",
                           fix="python scripts/bootstrap_production.py")

    for aim_id, asset_id, status, warmup, model in rows:
        if aim_id not in TIER1_AIMS or asset_id not in EXPECTED_ASSETS:
            continue
        if not model:
            # Tier 1 AIMs are statistical/rule-based and do not serialize a
            # model blob. `_save_model_object()` in b1_aim_lifecycle.py is a
            # placeholder (commented out) until individual AIM trainers are
            # wired, so this column is never populated on a fresh install.
            # Downgraded from CRITICAL to INFO so the report reflects real
            # readiness blockers.
            report.add("D01 aim_states",
                       f"AIM-{aim_id}/{asset_id}.model_object",
                       "INFO", "empty — expected for Tier 1 AIMs "
                               "(b1_aim_lifecycle._save_model_object is a placeholder)",
                       table="p3_d01_aim_model_states")
        if warmup is None or warmup < 0.8:
            report.add("D01 aim_states",
                       f"AIM-{aim_id}/{asset_id}.warmup_progress",
                       "WARN", f"{warmup} < 0.8 — AIM not yet live",
                       table="p3_d01_aim_model_states")
        if status not in VALID_AIM_STATUS:
            report.add("D01 aim_states",
                       f"AIM-{aim_id}/{asset_id}.status",
                       "WARN", f"unknown status={status!r}",
                       table="p3_d01_aim_model_states")


# -- D02 AIM meta weights --------------------------------------------------

def check_d02_weights(cur, report: Report) -> None:
    try:
        rows = _fetchall(cur, """
            SELECT aim_id, asset_id, inclusion_probability, inclusion_flag,
                   recent_effectiveness, days_below_threshold
            FROM p3_d02_aim_meta_weights
            LATEST ON last_updated PARTITION BY aim_id, asset_id
        """)
    except Exception:
        return  # schema check already raised CRITICAL

    # Per-asset sum of inclusion probabilities should be meaningful (>0)
    by_asset: dict[str, float] = {}
    per_asset_count: dict[str, int] = {}
    for aim_id, asset_id, prob, flag, eff, dbt in rows:
        if asset_id not in EXPECTED_ASSETS:
            continue
        by_asset[asset_id] = by_asset.get(asset_id, 0.0) + (prob or 0.0)
        per_asset_count[asset_id] = per_asset_count.get(asset_id, 0) + 1

        if prob is None:
            report.add("D02 meta_weights",
                       f"AIM-{aim_id}/{asset_id}.inclusion_probability",
                       "CRITICAL", "NULL — AIM won't contribute",
                       table="p3_d02_aim_meta_weights")
        elif prob < 0 or prob > 1:
            report.add("D02 meta_weights",
                       f"AIM-{aim_id}/{asset_id}.inclusion_probability",
                       "CRITICAL", f"{prob} outside [0,1]",
                       table="p3_d02_aim_meta_weights")

    for a in EXPECTED_ASSETS:
        if per_asset_count.get(a, 0) < len(TIER1_AIMS):
            report.add("D02 meta_weights", f"{a} AIM coverage", "CRITICAL",
                       f"only {per_asset_count.get(a, 0)}/{len(TIER1_AIMS)} AIMs have weights",
                       table="p3_d02_aim_meta_weights")
        total = by_asset.get(a, 0.0)
        if total <= 0:
            report.add("D02 meta_weights", f"{a} total weight", "CRITICAL",
                       f"sum(inclusion_probability)={total} — no AIM contributes to signal",
                       table="p3_d02_aim_meta_weights",
                       fix="bootstrap_production.py sets 1/6 equal weights")
        elif total < 0.1:
            report.add("D02 meta_weights", f"{a} total weight", "WARN",
                       f"sum={total:.3f} — signal modifier will be near-zero",
                       table="p3_d02_aim_meta_weights")


# -- D04 decay detector ----------------------------------------------------

def check_d04_decay(cur, report: Report) -> None:
    try:
        rows = _fetchall(cur, """
            SELECT asset_id, bocpd_cp_probability, current_changepoint_probability
            FROM p3_d04_decay_detector_states
            LATEST ON last_updated PARTITION BY asset_id
        """)
    except Exception as e:
        report.add("D04 decay", "read", "CRITICAL", str(e),
                   table="p3_d04_decay_detector_states")
        return
    seen = {r[0] for r in rows}
    for a in EXPECTED_ASSETS:
        if a not in seen:
            report.add("D04 decay", f"missing {a}", "WARN",
                       "no detector state — decay loop 2 will not flag this asset",
                       table="p3_d04_decay_detector_states")
    for asset, cp, cur_cp in rows:
        if cp is not None and cp > 0.8:
            report.add("D04 decay", f"{asset} high cp_prob", "WARN",
                       f"bocpd_cp_probability={cp:.3f} — L3 halt may trigger",
                       table="p3_d04_decay_detector_states")


# -- D05 EWMA & D12 Kelly --------------------------------------------------

def _expected_arsession_combos() -> set[tuple[str, str, int]]:
    # Full coverage: every asset × every regime × every session = 60 rows
    return {(a, r, s) for a in EXPECTED_ASSETS for r in REGIMES for s in SESSIONS}


def check_d05_ewma(cur, report: Report) -> None:
    try:
        rows = _fetchall(cur, """
            SELECT asset_id, regime, session, win_rate, avg_win, avg_loss, n_trades
            FROM p3_d05_ewma_states
            LATEST ON last_updated PARTITION BY asset_id, regime, session
        """)
    except Exception as e:
        report.add("D05 ewma", "read", "CRITICAL", str(e), table="p3_d05_ewma_states")
        return

    seen = {(r[0], r[1], r[2]) for r in rows}
    required = _expected_arsession_combos()
    missing = required - seen
    for (a, r, s) in sorted(missing):
        report.add("D05 ewma", f"missing {a}/{r}/sess{s}", "CRITICAL",
                   "EWMA row missing — Kelly sizing falls back to defaults",
                   table="p3_d05_ewma_states",
                   fix="python scripts/bootstrap_production.py")

    for asset, regime, sess, wr, aw, al, n in rows:
        if asset not in EXPECTED_ASSETS:
            continue
        label = f"{asset}/{regime}/sess{sess}"
        if wr is None or not (0.0 <= wr <= 1.0):
            report.add("D05 ewma", f"{label}.win_rate", "CRITICAL",
                       f"value={wr}", table="p3_d05_ewma_states")
        if aw is None or aw <= 0:
            report.add("D05 ewma", f"{label}.avg_win", "CRITICAL",
                       f"{aw} — Kelly numerator broken", table="p3_d05_ewma_states")
        if al is None or al <= 0:
            report.add("D05 ewma", f"{label}.avg_loss", "CRITICAL",
                       f"{al} — Kelly denominator broken", table="p3_d05_ewma_states")
        if n is None or n < 20:
            report.add("D05 ewma", f"{label}.n_trades", "WARN",
                       f"n_trades={n} < 20 — sample too small for reliable Kelly",
                       table="p3_d05_ewma_states")


def check_d12_kelly(cur, report: Report) -> None:
    try:
        rows = _fetchall(cur, """
            SELECT asset_id, regime, session, kelly_full, shrinkage_factor,
                   sizing_override
            FROM p3_d12_kelly_parameters
            LATEST ON last_updated PARTITION BY asset_id, regime, session
        """)
    except Exception as e:
        report.add("D12 kelly", "read", "CRITICAL", str(e),
                   table="p3_d12_kelly_parameters")
        return

    seen = {(r[0], r[1], r[2]) for r in rows}
    required = _expected_arsession_combos()
    missing = required - seen
    for (a, r, s) in sorted(missing):
        report.add("D12 kelly", f"missing {a}/{r}/sess{s}", "CRITICAL",
                   "Kelly params missing — position size will default to 0 or skip",
                   table="p3_d12_kelly_parameters",
                   fix="python scripts/bootstrap_production.py")

    for asset, regime, sess, kf, shrink, override in rows:
        if asset not in EXPECTED_ASSETS:
            continue
        label = f"{asset}/{regime}/sess{sess}"
        if kf is None or (isinstance(kf, float) and (math.isnan(kf) or math.isinf(kf))):
            report.add("D12 kelly", f"{label}.kelly_full", "CRITICAL",
                       f"value={kf} — sizing will error or skip",
                       table="p3_d12_kelly_parameters")
        elif kf < 0:
            report.add("D12 kelly", f"{label}.kelly_full", "WARN",
                       f"{kf:.4f} negative edge — no trades expected",
                       table="p3_d12_kelly_parameters")
        elif kf > 1:
            report.add("D12 kelly", f"{label}.kelly_full", "WARN",
                       f"{kf:.4f} > 1 (unusual — extreme edge)",
                       table="p3_d12_kelly_parameters")
        if shrink is not None and not (0.0 <= shrink <= 1.0):
            report.add("D12 kelly", f"{label}.shrinkage_factor", "WARN",
                       f"{shrink} outside [0,1]",
                       table="p3_d12_kelly_parameters")


# -- D08 TSM state ---------------------------------------------------------

def check_d08_tsm(cur, report: Report) -> None:
    try:
        rows = _fetchall(cur, """
            SELECT account_id, user_id, starting_balance, current_balance,
                   max_daily_loss, max_drawdown_limit, max_contracts, risk_goal,
                   pass_probability
            FROM p3_d08_tsm_state
            LATEST ON last_updated PARTITION BY account_id, user_id
        """)
    except Exception as e:
        report.add("D08 tsm_state", "read", "CRITICAL", str(e),
                   table="p3_d08_tsm_state")
        return

    if not rows:
        report.add("D08 tsm_state", "empty", "CRITICAL",
                   "no account rows — Kelly/TSM sizing cannot run",
                   table="p3_d08_tsm_state",
                   fix="python scripts/bootstrap_production.py")
        return

    for acct, user, sb, cb, mdl, mdd, mc, goal, pp in rows:
        label = f"{acct}/{user}"
        if not sb or sb <= 0:
            report.add("D08 tsm_state", f"{label}.starting_balance",
                       "CRITICAL", f"{sb}", table="p3_d08_tsm_state")
        if cb is None or cb <= 0:
            report.add("D08 tsm_state", f"{label}.current_balance",
                       "CRITICAL", f"{cb}", table="p3_d08_tsm_state")
        if not mdl or mdl <= 0:
            report.add("D08 tsm_state", f"{label}.max_daily_loss",
                       "CRITICAL", f"{mdl} — daily CB layer will not halt",
                       table="p3_d08_tsm_state")
        if not mdd or mdd <= 0:
            report.add("D08 tsm_state", f"{label}.max_drawdown_limit",
                       "CRITICAL", f"{mdd}", table="p3_d08_tsm_state")
        if not mc or mc <= 0:
            report.add("D08 tsm_state", f"{label}.max_contracts",
                       "CRITICAL", f"{mc}", table="p3_d08_tsm_state")
        if goal not in VALID_RISK_GOALS:
            report.add("D08 tsm_state", f"{label}.risk_goal",
                       "CRITICAL",
                       f"{goal!r} not in {sorted(VALID_RISK_GOALS)} — "
                       "Kelly cannot pick scaling factor",
                       table="p3_d08_tsm_state",
                       fix="Set via bootstrap_production.py or UPDATE query "
                           "(e.g. 'PASS_EVAL' for Trading Combine)")
        if pp is None or not (0.0 <= pp <= 1.0):
            report.add("D08 tsm_state", f"{label}.pass_probability",
                       "WARN", f"{pp} — MC sim may not have run yet",
                       table="p3_d08_tsm_state")


# -- D16 capital silos -----------------------------------------------------

def check_d16_capital(cur, report: Report) -> None:
    try:
        rows = _fetchall(cur, """
            SELECT user_id, starting_capital, total_capital, accounts,
                   max_simultaneous_positions, user_kelly_ceiling
            FROM p3_d16_user_capital_silos
            LATEST ON last_updated PARTITION BY user_id
        """)
    except Exception as e:
        report.add("D16 capital", "read", "CRITICAL", str(e),
                   table="p3_d16_user_capital_silos")
        return

    if not rows:
        report.add("D16 capital", "empty", "CRITICAL",
                   "no capital silo — DMA step cannot run",
                   table="p3_d16_user_capital_silos",
                   fix="python scripts/bootstrap_production.py")
        return

    for user, start, total, accounts, mp, ceil in rows:
        if not start or start <= 0:
            report.add("D16 capital", f"{user}.starting_capital",
                       "CRITICAL", f"{start}", table="p3_d16_user_capital_silos")
        if not total or total <= 0:
            report.add("D16 capital", f"{user}.total_capital",
                       "CRITICAL", f"{total}", table="p3_d16_user_capital_silos")
        if not accounts:
            report.add("D16 capital", f"{user}.accounts",
                       "CRITICAL", "empty — no account linkage",
                       table="p3_d16_user_capital_silos")
        else:
            try:
                acct_list = json.loads(accounts) if isinstance(accounts, str) else accounts
                if not acct_list:
                    report.add("D16 capital", f"{user}.accounts",
                               "CRITICAL", "empty list",
                               table="p3_d16_user_capital_silos")
            except Exception:
                report.add("D16 capital", f"{user}.accounts",
                           "WARN", f"not parseable JSON: {accounts!r}",
                           table="p3_d16_user_capital_silos")
        if not mp or mp <= 0:
            report.add("D16 capital", f"{user}.max_simultaneous_positions",
                       "CRITICAL", f"{mp}", table="p3_d16_user_capital_silos")
        if ceil is not None and (ceil <= 0 or ceil > 1):
            report.add("D16 capital", f"{user}.user_kelly_ceiling",
                       "WARN", f"{ceil} — expected fraction in (0,1]",
                       table="p3_d16_user_capital_silos")


# -- D25 circuit breaker params -------------------------------------------

def check_d25_cb(cur, report: Report) -> None:
    cols = show_columns(cur, "p3_d25_circuit_breaker_params")
    if not cols:
        return

    expected = {"account_id", "model_m", "r_bar", "beta_b", "sigma", "rho_bar",
                "n_observations", "p_value", "l_star", "cold_start", "last_updated"}
    missing = expected - cols
    if missing:
        report.add("Schema drift", "D25 column mismatch", "CRITICAL",
                   f"missing columns: {sorted(missing)} — live table was created "
                   "with an older schema",
                   table="p3_d25_circuit_breaker_params",
                   fix="DROP TABLE p3_d25_circuit_breaker_params; "
                       "python scripts/init_questdb.py; "
                       "python scripts/bootstrap_production.py")

    has_cold = "cold_start" in cols
    select_cols = "account_id, beta_b, n_observations, p_value"
    if has_cold:
        select_cols += ", cold_start"
    try:
        rows = _fetchall(cur, f"""
            SELECT {select_cols} FROM p3_d25_circuit_breaker_params
            LATEST ON last_updated PARTITION BY account_id
        """)
    except Exception as e:
        report.add("D25 cb_params", "read", "CRITICAL", str(e),
                   table="p3_d25_circuit_breaker_params")
        return

    if not rows:
        report.add("D25 cb_params", "empty", "CRITICAL",
                   "no CB params — circuit breaker L3/L4 disabled",
                   table="p3_d25_circuit_breaker_params",
                   fix="python scripts/bootstrap_production.py")
        return

    for row in rows:
        if has_cold:
            acct, beta, n, pval, cold = row
        else:
            acct, beta, n, pval = row
            cold = None
        if n is None:
            report.add("D25 cb_params", f"{acct}.n_observations",
                       "WARN", "NULL", table="p3_d25_circuit_breaker_params")
        elif has_cold and n >= 30 and cold:
            report.add("D25 cb_params", f"{acct}.cold_start stuck", "WARN",
                       f"n_observations={n} >= 30 but cold_start=true — "
                       "offline B8 has not fit beta_b",
                       table="p3_d25_circuit_breaker_params",
                       fix="Trigger offline B8 beta-fit job")
        if has_cold and not cold and (beta is None or beta == 0):
            report.add("D25 cb_params", f"{acct}.beta_b", "WARN",
                       f"cold_start=false but beta_b={beta}",
                       table="p3_d25_circuit_breaker_params")


# -- D26 HMM --------------------------------------------------------------

def check_d26_hmm(cur, report: Report) -> None:
    try:
        rows = _fetchall(cur, """
            SELECT hmm_params, opportunity_weights, n_observations, cold_start
            FROM p3_d26_hmm_opportunity_state
            ORDER BY last_updated DESC LIMIT 1
        """)
    except Exception as e:
        report.add("D26 hmm", "read", "WARN", str(e),
                   table="p3_d26_hmm_opportunity_state")
        return
    if not rows:
        report.add("D26 hmm", "empty", "WARN",
                   "no HMM state — AIM-16 opportunity weighting disabled",
                   table="p3_d26_hmm_opportunity_state",
                   fix="Train HMM via offline B1 (PG-01C)")
        return
    params, weights, n, cold = rows[0]
    if weights:
        try:
            json.loads(weights)
        except Exception as e:
            report.add("D26 hmm", "opportunity_weights JSON", "WARN",
                       str(e), table="p3_d26_hmm_opportunity_state")


# -- Daily-data freshness --------------------------------------------------

def check_freshness(cur, report: Report) -> None:
    for table, sla in FRESHNESS_SLA_HOURS.items():
        ts_col = "last_updated"
        # Some tables use 'ts' or 'trade_date' / 'session_date' / 'timestamp'
        if table in ("p3_d22_system_health_diagnostic",):
            ts_col = "ts"
        elif table == "p3_d30_daily_ohlcv":
            ts_col = "ts"
        elif table == "p3_d29_opening_volumes":
            ts_col = "ts"
        elif table == "p3_d33_opening_volatility":
            ts_col = "session_date"
        elif table == "p3_d31_implied_vol":
            ts_col = "trade_date"
        elif table == "p3_d32_options_skew":
            ts_col = "trade_date"
        elif table == "p3_spread_history":
            ts_col = "timestamp"

        ts = max_timestamp(cur, table, ts_col)
        rc = raw_count(cur, table)
        if rc == 0:
            # Two runtime-populated tables (D22 captain-offline diagnostic,
            # D17 monitor heartbeat) are legitimately empty on a fresh install
            # until the containers complete their first cycle — downgrade
            # those to WARN. Everything else in this map is seedable external
            # data, so 0 rows is still a blocker.
            runtime_populated = {
                "p3_d22_system_health_diagnostic",
                "p3_d17_system_monitor_state",
            }
            level = "WARN" if table in runtime_populated else "CRITICAL"
            msg = ("0 rows — will populate once captain-offline writes its "
                   "first cycle" if table in runtime_populated
                   else "0 rows — external data not seeded")
            report.add("Freshness", table, level, msg,
                       table=table,
                       fix={
                           "p3_d30_daily_ohlcv":
                               "python scripts/seed_ohlcv_from_qc.py",
                           "p3_d29_opening_volumes":
                               "python scripts/seed_or_volumes_from_qc.py",
                           "p3_d33_opening_volatility":
                               "python scripts/seed_opening_vol_from_qc.py",
                           "p3_d31_implied_vol":
                               "python scripts/seed_iv_rv_from_extract.py",
                           "p3_d32_options_skew":
                               "python scripts/seed_skew_from_extract.py",
                           "p3_spread_history":
                               "Auto-populated by Online B1; will fill on session open",
                           "p3_d22_system_health_diagnostic":
                               "Ensure captain-offline container is running",
                           "p3_d17_system_monitor_state":
                               "Ensure captain-online/offline/command containers heartbeat",
                       }.get(table, ""))
            continue
        h = age_hours(ts)
        if h is None:
            report.add("Freshness", table, "WARN", "ts is NULL", table=table)
        elif h > sla:
            report.add("Freshness", table, "WARN",
                       f"last row {fmt_age(ts)} > {sla}h SLA",
                       table=table)
        else:
            report.add("Freshness", table, "OK",
                       f"last row {fmt_age(ts)}", table=table)


def check_d03_trade_log(cur, report: Report) -> None:
    rc = raw_count(cur, "p3_d03_trade_outcome_log")
    ts = max_timestamp(cur, "p3_d03_trade_outcome_log", "ts")
    if rc == 0:
        report.add("D03 trade_log", "empty", "INFO",
                   "no trades recorded yet — expected for a fresh bootstrap",
                   table="p3_d03_trade_outcome_log")
    elif ts is None:
        report.add("D03 trade_log", "latest trade", "WARN",
                   f"{rc} rows but max(ts) is NULL",
                   table="p3_d03_trade_outcome_log")
    else:
        age_d = age_hours(ts) / 24
        if age_d > 14:
            report.add("D03 trade_log", "latest trade", "WARN",
                       f"{rc} rows, last trade {fmt_age(ts)} — no trades in 2+ weeks",
                       table="p3_d03_trade_outcome_log")
        else:
            report.add("D03 trade_log", "latest trade", "OK",
                       f"{rc} rows, last trade {fmt_age(ts)}",
                       table="p3_d03_trade_outcome_log")


# -- Feedback-loop liveness ------------------------------------------------

def check_feedback_loop(cur, report: Report) -> None:
    """After each new trade in D03, D02/D04/D05/D12/D25 should update."""
    last_trade = max_timestamp(cur, "p3_d03_trade_outcome_log", "ts")
    if last_trade is None:
        report.add("Feedback loop", "D03 latest", "INFO",
                   "no trades yet — feedback checks skipped")
        return
    for table in ["p3_d02_aim_meta_weights", "p3_d04_decay_detector_states",
                  "p3_d05_ewma_states", "p3_d12_kelly_parameters",
                  "p3_d25_circuit_breaker_params"]:
        ts = max_timestamp(cur, table, "last_updated")
        if ts is None:
            report.add("Feedback loop", f"{table} vs D03", "WARN",
                       "no last_updated", table=table)
            continue
        lag_h = (last_trade - ts).total_seconds() / 3600.0
        if lag_h > 24:
            report.add("Feedback loop", f"{table} vs D03", "WARN",
                       f"table is {lag_h:.1f}h behind most recent trade — "
                       "offline orchestrator may not be processing outcomes",
                       table=table,
                       fix="Check captain-offline container logs for outcome events")
        else:
            report.add("Feedback loop", f"{table} vs D03", "OK",
                       f"updated within {max(lag_h, 0):.1f}h of last trade",
                       table=table)


# -- Append-only bloat -----------------------------------------------------

def check_bloat(cur, report: Report) -> None:
    """Flag tables where total rows >> distinct-key rows (compaction overdue)."""
    targets = [
        ("p3_d01_aim_model_states",     "aim_id,asset_id",             60),
        ("p3_d02_aim_meta_weights",     "aim_id,asset_id",             60),
        ("p3_d04_decay_detector_states", "asset_id",                   10),
        ("p3_d05_ewma_states",          "asset_id,regime,session",     60),
        ("p3_d12_kelly_parameters",     "asset_id,regime,session",     60),
        ("p3_d25_circuit_breaker_params", "account_id",                1),
    ]
    for table, key, expected in targets:
        total = raw_count(cur, table)
        distinct = latest_distinct_count(cur, table, "last_updated", key)
        if total <= 0 or distinct <= 0:
            continue
        ratio = total / distinct
        if ratio > 10:
            report.add("Bloat", table, "WARN",
                       f"{total} total / {distinct} distinct keys (×{ratio:.1f}) "
                       "— compaction overdue",
                       table=table,
                       fix="python scripts/compact_questdb_tables.py")
        else:
            report.add("Bloat", table, "OK",
                       f"{total} total / {distinct} distinct (×{ratio:.1f})",
                       table=table)


# -- Orphans / known-unused -----------------------------------------------

def check_orphan_tables(cur, report: Report) -> None:
    for t in ["p3_d28_account_lifecycle", "p3_audit_log"]:
        n = raw_count(cur, t)
        if n < 0:
            continue
        if n == 0:
            report.add("Orphans", t, "INFO",
                       "defined but unused (0 rows) — expected", table=t)
        else:
            report.add("Orphans", t, "INFO",
                       f"{n} rows — previously marked unused, verify intent",
                       table=t)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

STATUS_EMOJI = {"OK": "[OK]", "INFO": "[i] ", "WARN": "[!]", "CRITICAL": "[X]"}


def render_text(report: Report) -> str:
    out: list[str] = []
    c = report.counts()
    out.append("=" * 78)
    out.append(f" Captain System — QuestDB Verification Report")
    out.append(f" Run: {report.started_at.isoformat()}")
    out.append(f" OK={c['OK']}  INFO={c['INFO']}  WARN={c['WARN']}  CRITICAL={c['CRITICAL']}")
    out.append("=" * 78)
    out.append("")

    ready = not report.critical()
    if ready:
        out.append(" >> READINESS: READY (no CRITICAL findings)" if not report.warnings()
                   else " >> READINESS: READY WITH WARNINGS")
    else:
        out.append(" >> READINESS: NOT READY — CRITICAL findings must be fixed before trading")
    out.append("")

    # Group by section
    sections: dict[str, list[Finding]] = {}
    for f in report.findings:
        sections.setdefault(f.section, []).append(f)

    # CRITICAL & WARN summary first
    if report.critical():
        out.append("## CRITICAL (blocks trading)")
        for f in report.critical():
            out.append(f"  [X] {f.section} :: {f.check}")
            if f.detail:
                out.append(f"        {f.detail}")
            if f.fix:
                out.append(f"        fix: {f.fix}")
        out.append("")
    if report.warnings():
        out.append("## WARNINGS (may degrade signal quality)")
        for f in report.warnings():
            out.append(f"  [!] {f.section} :: {f.check}")
            if f.detail:
                out.append(f"        {f.detail}")
            if f.fix:
                out.append(f"        fix: {f.fix}")
        out.append("")

    out.append("## Full results by section")
    for section, items in sections.items():
        out.append(f"\n### {section}")
        for f in items:
            prefix = STATUS_EMOJI.get(f.status, f.status)
            line = f"  {prefix} {f.check}"
            if f.detail:
                line += f" — {f.detail}"
            out.append(line)
    out.append("")
    out.append("-" * 78)
    out.append(" Next steps: patch CRITICALs, then re-run this script. "
               "Repeat on each machine.")
    out.append("-" * 78)
    return "\n".join(out)


def render_markdown(report: Report) -> str:
    c = report.counts()
    lines: list[str] = []
    lines.append(f"# QuestDB Verification Report")
    lines.append("")
    lines.append(f"- Run: `{report.started_at.isoformat()}`")
    lines.append(f"- OK: **{c['OK']}** · INFO: **{c['INFO']}** · "
                 f"WARN: **{c['WARN']}** · CRITICAL: **{c['CRITICAL']}**")
    lines.append("")
    if report.critical():
        lines.append("> **NOT READY** — CRITICAL findings block trading")
    elif report.warnings():
        lines.append("> **READY WITH WARNINGS** — review below before live trading")
    else:
        lines.append("> **READY**")
    lines.append("")

    if report.critical():
        lines.append("## CRITICAL")
        lines.append("| Section | Check | Detail | Fix |")
        lines.append("|---|---|---|---|")
        for f in report.critical():
            lines.append(f"| {f.section} | `{f.check}` | {f.detail} | {f.fix} |")
        lines.append("")
    if report.warnings():
        lines.append("## WARNING")
        lines.append("| Section | Check | Detail | Fix |")
        lines.append("|---|---|---|---|")
        for f in report.warnings():
            lines.append(f"| {f.section} | `{f.check}` | {f.detail} | {f.fix} |")
        lines.append("")

    sections: dict[str, list[Finding]] = {}
    for f in report.findings:
        sections.setdefault(f.section, []).append(f)
    lines.append("## Full results")
    for section, items in sections.items():
        lines.append(f"\n### {section}")
        lines.append("| Status | Check | Detail |")
        lines.append("|---|---|---|")
        for f in items:
            lines.append(f"| {f.status} | `{f.check}` | {f.detail} |")
    return "\n".join(lines)


def render_json(report: Report) -> str:
    return json.dumps({
        "run_at": report.started_at.isoformat(),
        "counts": report.counts(),
        "critical": bool(report.critical()),
        "findings": [asdict(f) for f in report.findings],
    }, indent=2, default=str)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--report", type=Path, help="Write markdown report to path")
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on any WARN (not just CRITICAL)")
    args = parser.parse_args()

    report = Report()

    if not check_connectivity(report):
        print(render_text(report))
        return 2

    try:
        with get_cursor() as cur:
            check_tables_exist(cur, report)
            check_d02_schema(cur, report)
            check_bootstrap_counts(cur, report)
            check_d00_fields(cur, report)
            check_d01_aim_states(cur, report)
            check_d02_weights(cur, report)
            check_d04_decay(cur, report)
            check_d05_ewma(cur, report)
            check_d12_kelly(cur, report)
            check_d08_tsm(cur, report)
            check_d16_capital(cur, report)
            check_d25_cb(cur, report)
            check_d26_hmm(cur, report)
            check_d03_trade_log(cur, report)
            check_freshness(cur, report)
            check_feedback_loop(cur, report)
            check_bloat(cur, report)
            check_orphan_tables(cur, report)
    except Exception as e:
        report.add("Runner", "unexpected error", "CRITICAL", str(e))

    if args.json:
        print(render_json(report))
    else:
        print(render_text(report))

    if args.report:
        args.report.write_text(render_markdown(report))
        print(f"\nMarkdown report written to {args.report}")

    if report.critical():
        return 1
    if args.strict and report.warnings():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
