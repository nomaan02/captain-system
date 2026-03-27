"""VIX/VXV/IVTS data provider: loads historical daily closes from CSV.

Provides accessor functions consumed by:
  - B1 features AIM-04: IVTS = VIX/VXV (stress detection filter)
  - B1 features AIM-11: VIX z-scores (regime warning)
  - B5C circuit breaker: VIX > threshold session halt

Data loaded once on first access, cached in memory.
For production, extend with a daily update mechanism.

Data sources (bundled CSVs):
  - vix_daily_close.csv: Cboe VIX (2009-2026, ~4356 rows)
  - vxv_daily_close.csv: Cboe VXV 3-month vol (2009-2026, ~4151 rows)
"""

import csv
import logging
import os
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Configurable paths — default to bundled CSVs
_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "vix"
_VIX_CSV_PATH = os.environ.get("VIX_CSV_PATH", str(_DATA_DIR / "vix_daily_close.csv"))
_VXV_CSV_PATH = os.environ.get("VXV_CSV_PATH", str(_DATA_DIR / "vxv_daily_close.csv"))

# Cached data: list of (date, close) sorted ascending
_vix_data: list[tuple[date, float]] = []
_vxv_data: list[tuple[date, float]] = []
_loaded = False
_lock = threading.Lock()


def _ensure_loaded():
    """Load CSVs on first access (lazy, thread-safe)."""
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        _load_all()
        _loaded = True


def _load_all():
    """Parse VIX and VXV CSVs."""
    global _vix_data, _vxv_data
    _vix_data = _load_single_csv(_VIX_CSV_PATH, "vix_close", "VIX")
    _vxv_data = _load_single_csv(_VXV_CSV_PATH, "vxv_close", "VXV")


def _load_single_csv(path_str: str, value_col: str, label: str) -> list[tuple[date, float]]:
    """Load a date,value CSV into a sorted list."""
    path = Path(path_str)
    if not path.exists():
        logger.warning("%s CSV not found at %s — %s features disabled", label, path, label)
        return []

    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                d = _parse_date(row["date"])
                close = float(row[value_col])
                rows.append((d, close))
            except (KeyError, ValueError, TypeError):
                continue

    rows.sort(key=lambda x: x[0])
    if rows:
        logger.info("%s provider: loaded %d daily closes (%s to %s)",
                    label, len(rows), rows[0][0], rows[-1][0])
    return rows


def _parse_date(s: str) -> date:
    """Parse date string (YYYY-MM-DD)."""
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# VIX accessors
# ---------------------------------------------------------------------------

def get_latest_vix_close() -> Optional[float]:
    """Most recent VIX close (typically yesterday's close).

    Used by: B1 features (AIM-04 IVTS, AIM-11 vix_z), B5C circuit breaker.
    """
    _ensure_loaded()
    if not _vix_data:
        return None
    return _vix_data[-1][1]


def get_latest_vix_date() -> Optional[date]:
    """Date of the most recent VIX close."""
    _ensure_loaded()
    if not _vix_data:
        return None
    return _vix_data[-1][0]


def get_trailing_vix_closes(lookback: int = 252) -> Optional[list[float]]:
    """Last N VIX daily closes (ascending order).

    Used by: AIM-11 vix_z (252-day z-score).
    """
    _ensure_loaded()
    if not _vix_data:
        return None
    if len(_vix_data) < lookback:
        return [row[1] for row in _vix_data]
    return [row[1] for row in _vix_data[-lookback:]]


def get_trailing_vix_daily_changes(lookback: int = 60) -> Optional[list[float]]:
    """Last N absolute daily VIX changes.

    Used by: AIM-11 vix_daily_change_z.
    """
    _ensure_loaded()
    if not _vix_data or len(_vix_data) < 2:
        return None
    needed = lookback + 1
    closes = [row[1] for row in _vix_data[-needed:]]
    changes = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    return changes if len(changes) >= lookback else changes


def get_vix_change_latest() -> Optional[float]:
    """Most recent daily VIX change (close[t] - close[t-1]).

    Used by: AIM-11 vix_daily_change_z.
    """
    _ensure_loaded()
    if not _vix_data or len(_vix_data) < 2:
        return None
    return _vix_data[-1][1] - _vix_data[-2][1]


# ---------------------------------------------------------------------------
# VXV accessors
# ---------------------------------------------------------------------------

def get_latest_vxv_close() -> Optional[float]:
    """Most recent VXV (Cboe 3-month vol) close.

    Used by: B1 features AIM-04 IVTS = VIX / VXV.
    """
    _ensure_loaded()
    if not _vxv_data:
        return None
    return _vxv_data[-1][1]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def reload():
    """Force reload of all CSVs (e.g., after daily update)."""
    global _loaded
    with _lock:
        _loaded = False
        _vix_data.clear()
        _vxv_data.clear()
    _ensure_loaded()
