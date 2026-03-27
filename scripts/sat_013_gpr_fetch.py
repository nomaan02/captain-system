"""SAT-013: Geopolitical Risk Index Monitor

Source: Caldara-Iacoviello GPR (American Economic Review 2022)
  Caldara, D. and Iacoviello, M. (2022). "Measuring Geopolitical Risk."
  American Economic Review, 112(4), 1194-1225.
  Data: https://www.matteoiacoviello.com/gpr.htm

Variable: V-072 (V_geopolitical_risk_index)
Integration: P2 regime feature, P3 AIM-R13
Signal type: RISK
Update frequency: Daily
Data cost: Free

Usage:
    python sat_013_gpr_fetch.py             # Download / update + save outputs
    python sat_013_gpr_fetch.py --dry-run   # Preview what would be fetched
    python sat_013_gpr_fetch.py --force     # Re-download full history even if cache exists

Dependencies (standard + pandas + requests + one XLS engine):
    pip install pandas requests xlrd        # xlrd reads legacy .xls format
    # OR
    pip install pandas requests openpyxl    # openpyxl as fallback (may need file renamed)

The script auto-detects which XLS engine is available (xlrd preferred for .xls
files, openpyxl as fallback). If neither is installed it prints install
instructions and exits cleanly.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# XLS engine detection — xlrd handles legacy .xls; openpyxl handles .xlsx
# The GPR files are .xls (BIFF8) so xlrd is preferred.
# ---------------------------------------------------------------------------

def _detect_xls_engine() -> str:
    """Return the best available pandas Excel engine for reading .xls files.

    Tries xlrd first (correct for BIFF8 .xls), then openpyxl as a fallback.

    Returns:
        Engine name string ("xlrd" or "openpyxl").

    Raises:
        ImportError: If no supported engine is installed.
    """
    try:
        import xlrd  # noqa: F401
        return "xlrd"
    except ImportError:
        pass
    try:
        import openpyxl  # noqa: F401
        log.warning(
            "xlrd not found — using openpyxl as fallback. "
            "Install xlrd for correct .xls support: pip install xlrd"
        )
        return "openpyxl"
    except ImportError:
        raise ImportError(
            "No Excel engine found. Install one:\n"
            "    pip install xlrd        # preferred for .xls files\n"
            "    pip install openpyxl    # fallback"
        )

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("sat_013_gpr")

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent          # captain-system/
_MACRO_DIR = _PROJECT_ROOT / "data" / "macro"

# Output files
_CSV_PATH = _MACRO_DIR / "gpr_index_daily.csv"
_JSON_PATH = _MACRO_DIR / "gpr_p2_feature.json"

# ---------------------------------------------------------------------------
# Source URLs
# The historical file covers the full back-history (pre-2021).
# The recent file is updated more frequently and overlaps the historical series.
# We fetch both and merge, preferring recent values on overlap.
# ---------------------------------------------------------------------------

_URL_RECENT = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls"
_URL_HISTORICAL = "https://www.matteoiacoviello.com/gpr_files/data_gpr_daily.xls"

# Rolling window for z-score / percentile normalization (252 trading days ~ 1 year)
_ROLLING_WINDOW = 252

# Staleness threshold: warn if latest data is older than this many calendar days
_STALE_DAYS = 3

# Assets this silo is relevant for
_ASSET_RELEVANCE: dict[str, float] = {
    "ES": 1.0,
    "NQ": 1.0,
    "MES": 1.0,
    "MNQ": 1.0,
    "M2K": 0.9,
    "MYM": 0.9,
    "NKD": 0.8,
    "MGC": 0.9,
    "ZB": 0.85,
    "ZN": 0.85,
    "ZT": 0.80,
}

# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------


def _download_xls(url: str, timeout: int = 30) -> bytes:
    """Download a raw XLS file from url and return bytes.

    Args:
        url: Full URL to the .xls file.
        timeout: Request timeout in seconds.

    Returns:
        Raw bytes of the downloaded file.

    Raises:
        requests.RequestException: On any network or HTTP error.
    """
    log.info("Downloading: %s", url)
    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()
    content = response.content
    log.info("  Downloaded %.1f KB", len(content) / 1024)
    return content


def _parse_xls_to_df(raw_bytes: bytes) -> pd.DataFrame:
    """Parse raw XLS bytes into a normalised DataFrame.

    The Caldara-Iacoviello files consistently have:
    - A 'date' column (sometimes named 'DATE', 'Date', or similar)
    - A 'GPRD' or 'GPR' column for the composite daily index
    - Optional sub-index columns: GPRD_threats, GPRD_acts (or similar)

    Args:
        raw_bytes: Raw bytes of the downloaded XLS file.

    Returns:
        DataFrame with columns: date (datetime64), gpr_index (float),
        gpr_threats (float or NaN), gpr_acts (float or NaN).
    """
    import io

    engine = _detect_xls_engine()
    df = pd.read_excel(io.BytesIO(raw_bytes), engine=engine)

    # Normalise column names to lowercase for lookup
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Identify the date column
    date_col: str | None = None
    for candidate in ("date", "dates", "day"):
        if candidate in df.columns:
            date_col = candidate
            break
    if date_col is None:
        raise ValueError(
            f"Cannot find date column in XLS. Columns present: {list(df.columns)}"
        )

    # Identify the primary GPR index column
    # The composite daily index is usually 'gprd' or 'gpr'
    gpr_col: str | None = None
    for candidate in ("gprd", "gpr", "gpr_index", "gpr_index_daily"):
        if candidate in df.columns:
            gpr_col = candidate
            break
    if gpr_col is None:
        # Fallback: pick the first numeric column that is not the date
        for col in df.columns:
            if col != date_col and pd.api.types.is_numeric_dtype(df[col]):
                gpr_col = col
                log.warning("GPR column not found by name — using first numeric: '%s'", col)
                break
    if gpr_col is None:
        raise ValueError(
            f"Cannot find GPR index column. Columns present: {list(df.columns)}"
        )

    # Identify optional sub-index columns
    threats_col: str | None = None
    acts_col: str | None = None
    for col in df.columns:
        if "threat" in col:
            threats_col = col
        if "act" in col and "threat" not in col:
            acts_col = col

    # Parse dates
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])

    # Build clean output frame
    out = pd.DataFrame()
    out["date"] = df[date_col].dt.normalize()  # Strip time component
    out["gpr_raw"] = pd.to_numeric(df[gpr_col], errors="coerce")

    if threats_col:
        out["gpr_threats"] = pd.to_numeric(df[threats_col], errors="coerce")
    else:
        out["gpr_threats"] = float("nan")

    if acts_col:
        out["gpr_acts"] = pd.to_numeric(df[acts_col], errors="coerce")
    else:
        out["gpr_acts"] = float("nan")

    # Drop rows where gpr_raw is missing
    out = out.dropna(subset=["gpr_raw"])
    out = out.sort_values("date").reset_index(drop=True)

    return out


def _merge_frames(historical: pd.DataFrame, recent: pd.DataFrame) -> pd.DataFrame:
    """Merge historical and recent DataFrames, preferring recent values on overlap.

    Args:
        historical: Full history DataFrame from data_gpr_daily.xls.
        recent: Recent DataFrame from data_gpr_daily_recent.xls.

    Returns:
        Merged, deduplicated, sorted DataFrame.
    """
    # Drop from historical any dates that appear in recent
    recent_dates = set(recent["date"])
    hist_trimmed = historical[~historical["date"].isin(recent_dates)].copy()

    merged = pd.concat([hist_trimmed, recent], ignore_index=True)
    merged = merged.sort_values("date").reset_index(drop=True)
    merged = merged.drop_duplicates(subset=["date"], keep="last")

    return merged


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def _add_normalised_columns(df: pd.DataFrame, window: int = _ROLLING_WINDOW) -> pd.DataFrame:
    """Add z-score, percentile, and signal columns to the GPR DataFrame.

    Normalisation is rolling relative to a `window`-day lookback so the
    scores remain comparable as history grows and structural level-shifts
    (e.g., COVID shock, Ukraine invasion) do not permanently skew readings.

    Columns added:
        gpr_zscore    : (gpr_raw - rolling_mean) / rolling_std
        gpr_percentile: rolling percentile rank [0, 1]
        signal_value  : tanh(gpr_zscore / 2), clipped to [-1, 1]

    Args:
        df: DataFrame with at least 'date' and 'gpr_raw' columns.
        window: Rolling window size in trading days.

    Returns:
        DataFrame with three additional columns.
    """
    gpr = df["gpr_raw"]

    rolling_mean = gpr.rolling(window=window, min_periods=max(1, window // 4)).mean()
    rolling_std = gpr.rolling(window=window, min_periods=max(1, window // 4)).std()

    # Avoid division by zero when std == 0 (flat or very short series)
    rolling_std_safe = rolling_std.replace(0.0, float("nan"))

    df = df.copy()
    df["gpr_zscore"] = (gpr - rolling_mean) / rolling_std_safe

    # Rolling percentile rank: fraction of past `window` values that are <= current
    def _rolling_percentile(series: pd.Series, w: int) -> pd.Series:
        """Compute rolling percentile rank using expanding min-period guard."""
        result = series.copy().astype(float)
        arr = series.to_numpy(dtype=float)
        n = len(arr)
        min_periods = max(1, w // 4)
        for i in range(n):
            start = max(0, i - w + 1)
            window_vals = arr[start : i + 1]
            valid = window_vals[~pd.isna(window_vals)]
            if len(valid) < min_periods:
                result.iloc[i] = float("nan")
            else:
                current = arr[i]
                if pd.isna(current):
                    result.iloc[i] = float("nan")
                else:
                    result.iloc[i] = float((valid <= current).sum()) / float(len(valid))
        return result

    df["gpr_percentile"] = _rolling_percentile(gpr, window)

    # signal_value: tanh(z/2) maps the real line to (-1, 1)
    # z=0 -> 0, z=2 -> 0.76, z=-2 -> -0.76, z=4 -> 0.96
    df["signal_value"] = df["gpr_zscore"].apply(
        lambda z: math.tanh(z / 2.0) if pd.notna(z) else float("nan")
    )

    return df


# ---------------------------------------------------------------------------
# Incremental update
# ---------------------------------------------------------------------------


def _load_cached_df() -> pd.DataFrame | None:
    """Load the existing CSV cache if it exists.

    Returns:
        DataFrame with columns [date, gpr_raw, gpr_zscore, gpr_percentile,
        signal_value], or None if no cache exists.
    """
    if not _CSV_PATH.exists():
        return None

    try:
        df = pd.read_csv(_CSV_PATH, parse_dates=["date"])
        log.info("Loaded cached CSV: %d rows (%s to %s)",
                 len(df), df["date"].min().date(), df["date"].max().date())
        return df
    except Exception as exc:
        log.warning("Failed to load cached CSV: %s — will re-fetch", exc)
        return None


def _cache_is_stale(df: pd.DataFrame, stale_days: int = _STALE_DAYS) -> bool:
    """Return True if the latest row in the cache is older than stale_days.

    Args:
        df: Cached DataFrame.
        stale_days: Threshold in calendar days.

    Returns:
        True if data is stale.
    """
    if df is None or df.empty:
        return True
    latest = pd.to_datetime(df["date"]).max().date()
    age = (date.today() - latest).days
    return age > stale_days


# ---------------------------------------------------------------------------
# SiloSignal output
# ---------------------------------------------------------------------------


def get_latest_silo_signal(df: pd.DataFrame) -> dict[str, Any]:
    """Return the latest GPR reading formatted as a SiloSignal.

    A SiloSignal is the standard envelope used by Captain Command to
    consume macro satellite data into the regime pipeline.

    Confidence is derived from data freshness:
    - Same-day or 1-day old  -> 1.0
    - 2-3 days old           -> 0.8
    - 4-7 days old           -> 0.5
    - Older                  -> 0.2

    Args:
        df: Processed DataFrame with normalised columns.

    Returns:
        SiloSignal dict ready for JSON serialisation.
    """
    if df.empty:
        raise ValueError("Cannot generate SiloSignal: DataFrame is empty")

    latest = df.sort_values("date").iloc[-1]
    latest_date: date = pd.to_datetime(latest["date"]).date()
    age_days = (date.today() - latest_date).days

    if age_days <= 1:
        confidence = 1.0
    elif age_days <= 3:
        confidence = 0.8
    elif age_days <= 7:
        confidence = 0.5
    else:
        confidence = 0.2

    signal_value = latest["signal_value"] if pd.notna(latest["signal_value"]) else 0.0
    gpr_raw = latest["gpr_raw"] if pd.notna(latest["gpr_raw"]) else None
    gpr_zscore = latest["gpr_zscore"] if pd.notna(latest["gpr_zscore"]) else None
    gpr_percentile = latest["gpr_percentile"] if pd.notna(latest["gpr_percentile"]) else None

    return {
        "silo_id": "GPR_V1",
        "silo_domain": "GEOPOLITICAL_MACRO",
        "signal_type": "RISK",
        "signal_value": round(float(signal_value), 6),
        "confidence": confidence,
        "latency_class": "DAILY",
        "staleness_limit": "24h",
        "as_of_date": str(latest_date),
        "asset_relevance": _ASSET_RELEVANCE,
        "metadata": {
            "gpr_raw": round(float(gpr_raw), 4) if gpr_raw is not None else None,
            "gpr_zscore": round(float(gpr_zscore), 6) if gpr_zscore is not None else None,
            "gpr_percentile": round(float(gpr_percentile), 4) if gpr_percentile is not None else None,
            "rolling_window_days": _ROLLING_WINDOW,
            "age_days": age_days,
        },
    }


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def _save_csv(df: pd.DataFrame) -> None:
    """Write the processed DataFrame to the standard CSV output path.

    Args:
        df: DataFrame with all required columns.
    """
    _MACRO_DIR.mkdir(parents=True, exist_ok=True)

    output_cols = ["date", "gpr_raw", "gpr_zscore", "gpr_percentile", "signal_value"]
    out = df[output_cols].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")

    out.to_csv(_CSV_PATH, index=False, float_format="%.6f")
    log.info("Saved CSV: %s (%d rows)", _CSV_PATH, len(out))


def _save_p2_json(df: pd.DataFrame) -> None:
    """Write a P2-compatible JSON feature file.

    The JSON format is consumed by the P2 regime pipeline (and P3 AIM-R13)
    as the V-072 feature vector. Only the signal_value column is used as
    the feature value — it is already normalised to [-1, 1].

    Args:
        df: Processed DataFrame.
    """
    _MACRO_DIR.mkdir(parents=True, exist_ok=True)

    latest_date = pd.to_datetime(df["date"]).max().strftime("%Y-%m-%d")

    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        if pd.isna(row["signal_value"]):
            continue
        records.append({
            "date": pd.to_datetime(row["date"]).strftime("%Y-%m-%d"),
            "value": round(float(row["signal_value"]), 6),
        })

    payload: dict[str, Any] = {
        "feature_name": "GPR_INDEX",
        "variable_id": "V-072",
        "variable_name": "V_geopolitical_risk_index",
        "source": "Caldara-Iacoviello GPR",
        "reference": "Caldara & Iacoviello (2022), AER 112(4) 1194-1225",
        "update_frequency": "daily",
        "signal_type": "RISK",
        "normalisation": "tanh(rolling_252d_zscore / 2)",
        "last_updated": latest_date,
        "record_count": len(records),
        "data": records,
    }

    _JSON_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Saved P2 JSON: %s (%d feature records)", _JSON_PATH, len(records))


# ---------------------------------------------------------------------------
# Main fetch logic
# ---------------------------------------------------------------------------


def fetch_and_process(force: bool = False) -> pd.DataFrame:
    """Download, parse, normalise, and persist the GPR index.

    On first run (no cache) downloads full history from both URLs.
    On subsequent runs, only re-downloads if data is stale OR force=True.
    In either case normalisation is re-run over the full merged series.

    Args:
        force: If True, re-download even if cache is fresh.

    Returns:
        Processed DataFrame with all normalised columns.
    """
    cached = _load_cached_df()

    if cached is not None and not force and not _cache_is_stale(cached):
        log.info("Cache is fresh — skipping download. Use --force to override.")
        return cached

    if _cache_is_stale(cached) and cached is not None:
        log.warning(
            "Cached data may be stale (latest: %s). Attempting re-download.",
            pd.to_datetime(cached["date"]).max().date(),
        )

    # Download both files — try recent first, fall back to historical-only
    recent_df: pd.DataFrame | None = None
    historical_df: pd.DataFrame | None = None

    try:
        recent_bytes = _download_xls(_URL_RECENT)
        recent_df = _parse_xls_to_df(recent_bytes)
        log.info("Recent XLS: %d rows (%s to %s)",
                 len(recent_df), recent_df["date"].min().date(), recent_df["date"].max().date())
    except Exception as exc:
        log.error("Failed to download recent GPR data: %s", exc)
        if cached is not None:
            log.warning("Falling back to cached data for recent segment.")

    try:
        historical_bytes = _download_xls(_URL_HISTORICAL)
        historical_df = _parse_xls_to_df(historical_bytes)
        log.info("Historical XLS: %d rows (%s to %s)",
                 len(historical_df), historical_df["date"].min().date(),
                 historical_df["date"].max().date())
    except Exception as exc:
        log.error("Failed to download historical GPR data: %s", exc)

    # Merge what we have
    if recent_df is not None and historical_df is not None:
        merged = _merge_frames(historical_df, recent_df)
        log.info("Merged: %d rows (%s to %s)",
                 len(merged), merged["date"].min().date(), merged["date"].max().date())
    elif recent_df is not None:
        log.warning("Only recent data available — history may be incomplete.")
        merged = recent_df
    elif historical_df is not None:
        log.warning("Only historical data available — recent dates may be missing.")
        merged = historical_df
    elif cached is not None:
        log.error("All downloads failed — using cached data as-is.")
        return cached
    else:
        raise RuntimeError(
            "All downloads failed and no cache exists. Cannot produce GPR output."
        )

    # If we have a prior cache, also merge it in so we never lose rows
    # that may have been removed from upstream (upstream sometimes trims).
    if cached is not None:
        # Keep any cached rows not in the freshly downloaded set
        cached_dates = set(pd.to_datetime(cached["date"]))
        fresh_dates = set(merged["date"])
        legacy_only = cached[
            pd.to_datetime(cached["date"]).isin(cached_dates - fresh_dates)
        ][["date", "gpr_raw"]].copy()
        if not legacy_only.empty:
            legacy_only["date"] = pd.to_datetime(legacy_only["date"])
            # Re-merge: legacy rows fill any gaps in the download
            merged = pd.concat([legacy_only, merged], ignore_index=True)
            merged = merged.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
            log.info("After cache-fill: %d rows total", len(merged))

    # Normalise
    processed = _add_normalised_columns(merged)

    return processed


# ---------------------------------------------------------------------------
# Dry-run preview
# ---------------------------------------------------------------------------


def dry_run_preview() -> None:
    """Print what the fetch would do without downloading anything."""
    print()
    print("=" * 70)
    print("SAT-013 GPR FETCH — DRY RUN")
    print("=" * 70)
    print(f"  Output CSV : {_CSV_PATH}")
    print(f"  Output JSON: {_JSON_PATH}")
    print()
    print("  URLs to be fetched:")
    print(f"    [1] Recent  : {_URL_RECENT}")
    print(f"    [2] Historic: {_URL_HISTORICAL}")
    print()

    cached = _load_cached_df()
    if cached is not None:
        latest = pd.to_datetime(cached["date"]).max().date()
        age = (date.today() - latest).days
        stale = _cache_is_stale(cached)
        print(f"  Existing cache: {len(cached)} rows, latest {latest} ({age}d ago)")
        print(f"  Cache status  : {'STALE — would re-download' if stale else 'FRESH — would skip download'}")

        # Show latest signal
        try:
            # Need normalised columns for silo signal — recompute
            processed = _add_normalised_columns(cached.rename(
                columns={"gpr_zscore": "gpr_zscore_old"} if "gpr_zscore" in cached.columns else {}
            ))
        except Exception:
            processed = _add_normalised_columns(cached)

        try:
            sig = get_latest_silo_signal(processed)
            print()
            print("  Latest SiloSignal (from cache):")
            print(f"    as_of_date   : {sig['as_of_date']}")
            print(f"    signal_value : {sig['signal_value']:+.4f}  (tanh(z/2), range [-1,1])")
            print(f"    confidence   : {sig['confidence']:.1f}")
            meta = sig["metadata"]
            print(f"    gpr_raw      : {meta['gpr_raw']}")
            print(f"    gpr_zscore   : {meta['gpr_zscore']:+.4f}")
            print(f"    gpr_percentile: {meta['gpr_percentile']:.3f}")
        except Exception as exc:
            print(f"  [WARN] Could not compute SiloSignal from cache: {exc}")
    else:
        print("  No existing cache — full download would be performed.")

    print()
    print("  Normalisation: rolling 252-day z-score + tanh(z/2) signal")
    print("  Run without --dry-run to execute.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    """Parse arguments and run the GPR fetch pipeline.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="SAT-013: Download and normalise the Caldara-Iacoviello GPR index."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be fetched without downloading.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download full history even if cache is fresh.",
    )
    parser.add_argument(
        "--show-signal",
        action="store_true",
        help="Print the latest SiloSignal after processing.",
    )
    args = parser.parse_args()

    # Check XLS engine availability before doing any network work
    try:
        _detect_xls_engine()
    except ImportError as exc:
        log.error("Cannot proceed — missing Excel dependency:\n%s", exc)
        return 1

    if args.dry_run:
        dry_run_preview()
        return 0

    log.info("SAT-013 GPR Fetch starting (force=%s)", args.force)

    try:
        df = fetch_and_process(force=args.force)
    except RuntimeError as exc:
        log.error("Fatal: %s", exc)
        return 1
    except Exception as exc:
        log.error("Unexpected error during fetch/process: %s", exc, exc_info=True)
        return 1

    # Persist outputs
    try:
        _save_csv(df)
        _save_p2_json(df)
    except Exception as exc:
        log.error("Failed to save output files: %s", exc, exc_info=True)
        return 1

    # Report latest reading
    try:
        signal = get_latest_silo_signal(df)
        log.info("Latest SiloSignal:")
        log.info("  as_of_date   : %s", signal["as_of_date"])
        log.info("  signal_value : %+.4f  (RISK direction: positive = elevated risk)",
                 signal["signal_value"])
        log.info("  confidence   : %.1f", signal["confidence"])
        meta = signal["metadata"]
        log.info("  gpr_raw      : %.2f", meta["gpr_raw"] or 0)
        log.info("  gpr_zscore   : %+.4f", meta["gpr_zscore"] or 0)
        log.info("  gpr_percentile: %.3f", meta["gpr_percentile"] or 0)

        if args.show_signal:
            print()
            print(json.dumps(signal, indent=2))

        if signal["confidence"] < 0.5:
            log.warning(
                "Data is %d days old — confidence %.1f. "
                "Check upstream source for updates.",
                meta["age_days"],
                signal["confidence"],
            )
    except Exception as exc:
        log.warning("Could not generate SiloSignal summary: %s", exc)

    log.info("SAT-013 complete. Rows: %d, date range: %s to %s",
             len(df),
             pd.to_datetime(df["date"]).min().date(),
             pd.to_datetime(df["date"]).max().date())

    return 0


if __name__ == "__main__":
    sys.exit(main())
