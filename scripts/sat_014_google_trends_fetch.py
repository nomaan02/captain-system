"""SAT-014: Google Trends Attention Monitor
Source: Google Trends API (P-1371, P-1372, P-1375, P-1379)
Variable: V-073 (V_google_search_volume)
Integration: P2 regime feature, P3 AIM-R14

Fetches Google Trends search interest data for asset-specific and macro
sentiment terms. Computes a rolling z-score attention index and saves
outputs in three formats:

  1. captain-system/data/macro/google_trends_daily.csv
     Per-term daily raw/smoothed/z-score values.

  2. captain-system/data/macro/google_trends_aggregate.csv
     Aggregated daily attention signal bounded to [-1, 1] via tanh.

  3. captain-system/data/macro/google_trends_p2_feature.json
     P2-compatible JSON with feature metadata and {date, value} pairs.

Usage:
  python sat_014_google_trends_fetch.py
  python sat_014_google_trends_fetch.py --dry-run
  python sat_014_google_trends_fetch.py --no-cache

Google Trends notes:
  - Daily granularity is available only for windows <= 270 days.
    We request 90-day windows, which gives true daily values.
  - Values are normalised by Google to 0-100 within each request.
    Do NOT compare raw values across separate API calls; z-scoring
    normalises this within each term's own history.
  - The unofficial pytrends library enforces ~60 s cool-down between
    requests when rate-limited.  This script sleeps between requests
    as a precaution.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional dependency guard
# ---------------------------------------------------------------------------

try:
    from pytrends.request import TrendReq
except ImportError:
    print("pytrends not installed.  Run: pip install pytrends")
    sys.exit(1)

try:
    import pandas as pd
except ImportError:
    print("pandas not installed.  Run: pip install pandas")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# All terms we track, grouped by logical category.
# The asset-to-terms mapping drives per-asset relevance scoring.
TERMS_BY_ASSET: dict[str, list[str]] = {
    "ES": ["S&P 500"],
    "MES": ["S&P 500"],
    "NQ": ["Nasdaq"],
    "MNQ": ["Nasdaq"],
    "CL": ["oil price"],
    "MCL": ["oil price"],
    "GC": ["gold price"],
    "MGC": ["gold price"],
    "ZN": ["treasury bonds"],
    "ZB": ["treasury bonds"],
    "ZT": ["treasury bonds"],
}

MACRO_TERMS: list[str] = [
    "stock market crash",
    "recession",
    "market volatility",
]

# Deduplicated ordered list of all terms to fetch.
_ALL_ASSET_TERMS: list[str] = list(
    dict.fromkeys(term for terms in TERMS_BY_ASSET.values() for term in terms)
)
ALL_TERMS: list[str] = _ALL_ASSET_TERMS + MACRO_TERMS

# Rolling window parameters.
SMOOTH_WINDOW: int = 7   # 7-day mean for noise reduction.
ZSCORE_WINDOW: int = 30  # 30-day window for z-score baseline.

# pytrends request parameters.
LOOKBACK_DAYS: int = 90           # Maximum for daily granularity.
REQUEST_SLEEP_SECONDS: float = 5.0  # Polite delay between API calls.
RETRY_SLEEP_SECONDS: float = 65.0  # Sleep duration on rate-limit hit.
MAX_RETRIES: int = 3

# ---------------------------------------------------------------------------
# Path resolution — mirrors the convention in seed_real_asset.py
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent  # captain-system/

_DATA_CANDIDATES = [
    _PROJECT_ROOT / "data",
    Path("/captain/data"),
]


def _find_data_root() -> Path:
    """Return the first candidate data directory that exists.

    Returns:
        Path to the data root directory.

    Raises:
        RuntimeError: If no candidate directory can be found.
    """
    for candidate in _DATA_CANDIDATES:
        if candidate.is_dir():
            return candidate
    raise RuntimeError(
        f"Cannot locate data directory.  Tried: {[str(c) for c in _DATA_CANDIDATES]}"
    )


def _macro_dir() -> Path:
    """Resolve and create the macro output directory if needed.

    Returns:
        Path to captain-system/data/macro/ (or Docker equivalent).
    """
    macro = _find_data_root() / "macro"
    macro.mkdir(parents=True, exist_ok=True)
    return macro


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(macro_dir: Path) -> Path:
    """Return the path to the raw-fetch cache file.

    The cache stores the per-term raw DataFrames as a CSV so that re-runs
    within the same day do not hammer the Google Trends API.
    """
    return macro_dir / "google_trends_raw_cache.csv"


def _cache_is_fresh(cache_file: Path) -> bool:
    """Return True if the cache file was written today.

    Args:
        cache_file: Path to the cache CSV.

    Returns:
        True when the file exists and its modification date is today.
    """
    if not cache_file.exists():
        return False
    mtime = datetime.fromtimestamp(cache_file.stat().st_mtime).date()
    return mtime == date.today()


def _load_cache(cache_file: Path) -> pd.DataFrame:
    """Load the raw-fetch cache.

    Args:
        cache_file: Path to the cache CSV.

    Returns:
        DataFrame with columns [date, term, raw_volume].
    """
    df = pd.read_csv(cache_file, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _save_cache(df: pd.DataFrame, cache_file: Path) -> None:
    """Persist the raw DataFrame to the cache file.

    Args:
        df: DataFrame with columns [date, term, raw_volume].
        cache_file: Destination path.
    """
    df.to_csv(cache_file, index=False)


# ---------------------------------------------------------------------------
# Google Trends fetch
# ---------------------------------------------------------------------------

def _build_date_range() -> tuple[str, str]:
    """Compute the 90-day lookback window as pytrends date strings.

    Returns:
        Tuple of (start_date_str, end_date_str) in 'YYYY-MM-DD' format.
    """
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS - 1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _fetch_term_with_retry(
    pytrends: TrendReq,
    term: str,
    timeframe: str,
    dry_run: bool,
) -> pd.DataFrame | None:
    """Fetch interest-over-time for a single term with retry logic.

    Google Trends returns a DataFrame indexed by datetime with one column
    per term and an 'isPartial' column.  We extract only the term column
    and rename it to 'raw_volume'.

    Args:
        pytrends: Authenticated TrendReq instance.
        term: Single search term string.
        timeframe: pytrends timeframe string, e.g. '2025-01-01 2025-03-31'.
        dry_run: When True, skip the actual API call and return None.

    Returns:
        DataFrame with columns [date, raw_volume], or None on dry-run / failure.
    """
    if dry_run:
        print(f"  [dry-run] Would fetch: '{term}'")
        return None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pytrends.build_payload([term], cat=0, timeframe=timeframe, geo="US")
            raw = pytrends.interest_over_time()

            if raw.empty:
                print(f"  [warn] No data returned for term: '{term}'")
                return None

            # Drop the 'isPartial' metadata column.
            if "isPartial" in raw.columns:
                raw = raw.drop(columns=["isPartial"])

            df = raw[[term]].reset_index()
            df.columns = pd.Index(["date", "raw_volume"])
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df["term"] = term
            return df[["date", "term", "raw_volume"]]

        except Exception as exc:  # noqa: BLE001
            err_str = str(exc).lower()
            if "429" in err_str or "rate" in err_str or "too many" in err_str:
                if attempt < MAX_RETRIES:
                    print(
                        f"  [rate-limit] Sleeping {RETRY_SLEEP_SECONDS}s "
                        f"before retry {attempt + 1}/{MAX_RETRIES} for '{term}'"
                    )
                    time.sleep(RETRY_SLEEP_SECONDS)
                else:
                    print(f"  [error] Rate-limit exceeded for '{term}' after {MAX_RETRIES} retries.")
                    return None
            else:
                print(f"  [error] Unexpected error for '{term}' (attempt {attempt}): {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(REQUEST_SLEEP_SECONDS)
                else:
                    return None

    return None


def fetch_all_terms(dry_run: bool, use_cache: bool, macro_dir: Path) -> pd.DataFrame:
    """Fetch raw interest-over-time data for all configured terms.

    When use_cache is True and the cache is from today, the cached data
    is returned without making any API calls.

    Args:
        dry_run: Skip all API calls and return an empty DataFrame.
        use_cache: Whether to read from / write to the local cache file.
        macro_dir: Directory containing the cache file.

    Returns:
        DataFrame with columns [date, term, raw_volume].
        Returns an empty DataFrame if dry_run is True or all fetches fail.
    """
    cache_file = _cache_path(macro_dir)

    if use_cache and _cache_is_fresh(cache_file):
        print(f"[cache] Using fresh cache from today: {cache_file}")
        return _load_cache(cache_file)

    if dry_run:
        print(f"[dry-run] Would fetch {len(ALL_TERMS)} terms: {ALL_TERMS}")
        return pd.DataFrame(columns=["date", "term", "raw_volume"])

    start_str, end_str = _build_date_range()
    timeframe = f"{start_str} {end_str}"
    print(f"[fetch] Requesting {len(ALL_TERMS)} terms for {timeframe}")

    pytrends = TrendReq(hl="en-US", tz=300)  # tz=300 = US/Eastern offset
    frames: list[pd.DataFrame] = []

    for i, term in enumerate(ALL_TERMS, start=1):
        print(f"  [{i}/{len(ALL_TERMS)}] Fetching: '{term}'")
        df = _fetch_term_with_retry(pytrends, term, timeframe, dry_run=False)
        if df is not None:
            frames.append(df)
        if i < len(ALL_TERMS):
            time.sleep(REQUEST_SLEEP_SECONDS)

    if not frames:
        print("[warn] No data fetched from Google Trends.")
        return pd.DataFrame(columns=["date", "term", "raw_volume"])

    combined = pd.concat(frames, ignore_index=True)

    if use_cache:
        _save_cache(combined, cache_file)
        print(f"[cache] Saved raw data to {cache_file}")

    return combined


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def compute_per_term_signals(raw: pd.DataFrame) -> pd.DataFrame:
    """Add smoothed_volume and zscore columns to the per-term DataFrame.

    Processing per term:
      1. Sort chronologically.
      2. smoothed_volume = 7-day rolling mean of raw_volume.
      3. zscore = (smoothed_volume - 30d_mean) / 30d_std, using min_periods=2
         to avoid NaN on short series.

    Args:
        raw: DataFrame with columns [date, term, raw_volume].

    Returns:
        DataFrame with columns [date, term, raw_volume, smoothed_volume, zscore].
    """
    if raw.empty:
        return pd.DataFrame(
            columns=["date", "term", "raw_volume", "smoothed_volume", "zscore"]
        )

    results: list[pd.DataFrame] = []
    for term, group in raw.groupby("term"):
        g = group.sort_values("date").copy()
        g["smoothed_volume"] = (
            g["raw_volume"]
            .astype(float)
            .rolling(window=SMOOTH_WINDOW, min_periods=1)
            .mean()
        )
        rolling_mean = (
            g["smoothed_volume"]
            .rolling(window=ZSCORE_WINDOW, min_periods=2)
            .mean()
        )
        rolling_std = (
            g["smoothed_volume"]
            .rolling(window=ZSCORE_WINDOW, min_periods=2)
            .std()
        )
        g["zscore"] = (g["smoothed_volume"] - rolling_mean) / rolling_std.replace(0, float("nan"))
        results.append(g)

    return pd.concat(results, ignore_index=True).sort_values(["date", "term"])


def compute_aggregate_signal(per_term: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-term z-scores into a single daily attention signal.

    For each date:
      - aggregate_attention = equal-weight mean of all available term z-scores
        (NaN terms are excluded from the mean).
      - signal_value = tanh(aggregate_attention / 2), bounded in [-1, 1].
      - max_term = term with highest z-score that day.
      - max_zscore = that term's z-score.

    Args:
        per_term: Output of compute_per_term_signals().

    Returns:
        DataFrame with columns
        [date, aggregate_attention, signal_value, max_term, max_zscore].
    """
    if per_term.empty:
        return pd.DataFrame(
            columns=[
                "date", "aggregate_attention", "signal_value",
                "max_term", "max_zscore",
            ]
        )

    rows: list[dict[str, Any]] = []
    for date_val, group in per_term.groupby("date"):
        valid = group.dropna(subset=["zscore"])
        if valid.empty:
            rows.append(
                {
                    "date": date_val,
                    "aggregate_attention": float("nan"),
                    "signal_value": 0.0,
                    "max_term": "",
                    "max_zscore": float("nan"),
                }
            )
            continue

        agg_attention: float = float(valid["zscore"].mean())
        signal_value: float = math.tanh(agg_attention / 2.0)

        max_idx = int(valid["zscore"].idxmax())
        max_term: str = str(valid.loc[max_idx, "term"])
        max_zscore: float = float(valid.loc[max_idx, "zscore"])

        rows.append(
            {
                "date": date_val,
                "aggregate_attention": round(agg_attention, 6),
                "signal_value": round(signal_value, 6),
                "max_term": max_term,
                "max_zscore": round(max_zscore, 6),
            }
        )

    agg = pd.DataFrame(rows).sort_values("date")
    return agg


# ---------------------------------------------------------------------------
# Asset relevance scoring
# ---------------------------------------------------------------------------

def _build_asset_relevance(per_term: pd.DataFrame) -> dict[str, float]:
    """Compute per-asset relevance scores from the latest day's z-scores.

    Relevance is the mean z-score of terms mapped to that asset, normalised
    through tanh to [-1, 1].  Assets with no mapped terms receive 0.0.

    Args:
        per_term: Output of compute_per_term_signals().

    Returns:
        Dict mapping asset ticker string to relevance float in [-1, 1].
    """
    if per_term.empty:
        return {asset: 0.0 for asset in TERMS_BY_ASSET}

    latest_date = per_term["date"].max()
    latest = per_term[per_term["date"] == latest_date].dropna(subset=["zscore"])
    zscore_by_term: dict[str, float] = dict(
        zip(latest["term"].tolist(), latest["zscore"].tolist())
    )

    relevance: dict[str, float] = {}
    for asset, terms in TERMS_BY_ASSET.items():
        scores = [zscore_by_term[t] for t in terms if t in zscore_by_term]
        if scores:
            mean_z = sum(scores) / len(scores)
            relevance[asset] = round(math.tanh(mean_z / 2.0), 6)
        else:
            relevance[asset] = 0.0

    return relevance


# ---------------------------------------------------------------------------
# SiloSignal output
# ---------------------------------------------------------------------------

def get_latest_silo_signal(
    agg: pd.DataFrame,
    per_term: pd.DataFrame,
) -> dict[str, Any]:
    """Build the SiloSignal dict from the latest aggregate row.

    Confidence is derived from how many terms contributed valid z-scores
    relative to the total term count.

    Args:
        agg: Output of compute_aggregate_signal().
        per_term: Output of compute_per_term_signals().

    Returns:
        SiloSignal dict compliant with the AIM-R14 interface spec.
    """
    if agg.empty:
        return {
            "silo_id": "GOOGLE_TRENDS_V1",
            "silo_domain": "ALTERNATIVE_SENTIMENT",
            "signal_type": "VOLATILITY",
            "signal_value": 0.0,
            "confidence": 0.0,
            "latency_class": "DAILY",
            "staleness_limit": "24h",
            "asset_relevance": {asset: 0.0 for asset in TERMS_BY_ASSET},
            "metadata": {
                "top_term": "",
                "top_zscore": float("nan"),
                "error": "no data available",
            },
        }

    latest = agg.iloc[-1]
    signal_value: float = float(latest["signal_value"]) if not pd.isna(latest["signal_value"]) else 0.0
    max_term: str = str(latest["max_term"])
    max_zscore: float = float(latest["max_zscore"]) if not pd.isna(latest["max_zscore"]) else float("nan")

    # Confidence: fraction of terms with valid z-scores on the latest date.
    if not per_term.empty:
        latest_date = per_term["date"].max()
        latest_row = per_term[per_term["date"] == latest_date]
        valid_count = int(latest_row["zscore"].notna().sum())
        confidence = round(valid_count / max(len(ALL_TERMS), 1), 4)
    else:
        confidence = 0.0

    asset_relevance = _build_asset_relevance(per_term)

    return {
        "silo_id": "GOOGLE_TRENDS_V1",
        "silo_domain": "ALTERNATIVE_SENTIMENT",
        "signal_type": "VOLATILITY",
        "signal_value": signal_value,
        "confidence": confidence,
        "latency_class": "DAILY",
        "staleness_limit": "24h",
        "asset_relevance": asset_relevance,
        "metadata": {
            "top_term": max_term,
            "top_zscore": max_zscore if not math.isnan(max_zscore) else None,
        },
    }


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_daily_csv(per_term: pd.DataFrame, macro_dir: Path) -> Path:
    """Write per-term daily data to google_trends_daily.csv.

    Columns: date, term, raw_volume, smoothed_volume, zscore.

    Args:
        per_term: Output of compute_per_term_signals().
        macro_dir: Target directory.

    Returns:
        Path to the written file.
    """
    out = macro_dir / "google_trends_daily.csv"
    if per_term.empty:
        print(f"[skip] No per-term data to write: {out}")
        return out

    df = per_term[["date", "term", "raw_volume", "smoothed_volume", "zscore"]].copy()
    df["date"] = df["date"].astype(str)
    df.to_csv(out, index=False, float_format="%.6f")
    print(f"[write] {out}  ({len(df)} rows)")
    return out


def write_aggregate_csv(agg: pd.DataFrame, macro_dir: Path) -> Path:
    """Write aggregate daily signal to google_trends_aggregate.csv.

    Columns: date, aggregate_attention, signal_value, max_term, max_zscore.

    Args:
        agg: Output of compute_aggregate_signal().
        macro_dir: Target directory.

    Returns:
        Path to the written file.
    """
    out = macro_dir / "google_trends_aggregate.csv"
    if agg.empty:
        print(f"[skip] No aggregate data to write: {out}")
        return out

    df = agg.copy()
    df["date"] = df["date"].astype(str)
    df.to_csv(out, index=False, float_format="%.6f")
    print(f"[write] {out}  ({len(df)} rows)")
    return out


def write_p2_feature_json(agg: pd.DataFrame, macro_dir: Path) -> Path:
    """Write P2-compatible feature JSON to google_trends_p2_feature.json.

    The JSON structure contains feature metadata plus a list of
    {date, value} objects where value = signal_value (tanh-bounded).

    Args:
        agg: Output of compute_aggregate_signal().
        macro_dir: Target directory.

    Returns:
        Path to the written file.
    """
    out = macro_dir / "google_trends_p2_feature.json"

    if agg.empty:
        data_records: list[dict[str, Any]] = []
        last_updated = date.today().strftime("%Y-%m-%d")
    else:
        data_records = [
            {
                "date": str(row["date"]),
                "value": float(row["signal_value"]) if not pd.isna(row["signal_value"]) else None,
            }
            for _, row in agg.iterrows()
        ]
        last_updated = str(agg["date"].max())

    payload: dict[str, Any] = {
        "feature_name": "GOOGLE_TRENDS_ATTENTION",
        "source": "Google Trends API via pytrends",
        "update_frequency": "daily",
        "last_updated": last_updated,
        "terms_tracked": ALL_TERMS,
        "data": data_records,
    }

    with out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    print(f"[write] {out}  ({len(data_records)} records)")
    return out


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(agg: pd.DataFrame, silo: dict[str, Any]) -> None:
    """Print a human-readable summary of the latest signal state.

    Args:
        agg: Output of compute_aggregate_signal().
        silo: Output of get_latest_silo_signal().
    """
    print()
    print("=" * 60)
    print("SAT-014 Google Trends Attention Monitor — Summary")
    print("=" * 60)

    if agg.empty:
        print("No data available.")
        return

    latest = agg.iloc[-1]
    print(f"  Date             : {latest['date']}")
    print(f"  Aggregate attn.  : {latest['aggregate_attention']:.4f}")
    print(f"  Signal value     : {latest['signal_value']:.4f}  (tanh bounded)")
    print(f"  Top term         : '{latest['max_term']}' (z={latest['max_zscore']:.2f})")
    print(f"  Confidence       : {silo['confidence']:.2%}")
    print(f"  Silo ID          : {silo['silo_id']}")
    print(f"  Signal type      : {silo['signal_type']}")
    print()

    # Show last 7 days of aggregate.
    print("  Recent signal history (last 7 days):")
    recent = agg.tail(7)
    for _, row in recent.iterrows():
        bar_width = int(abs(float(row["signal_value"])) * 20) if not pd.isna(row["signal_value"]) else 0
        direction = "+" if float(row["signal_value"]) >= 0 else "-"
        bar = direction * bar_width
        print(
            f"    {row['date']}  {float(row['signal_value']):+.4f}  {bar:<20}  "
            f"top: '{row['max_term']}'"
        )
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SAT-014: Fetch Google Trends attention data for MOST system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be fetched without making API calls.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Force re-fetch from Google Trends even if a fresh cache exists.",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for SAT-014 data fetch."""
    args = _parse_args()

    dry_run: bool = args.dry_run
    use_cache: bool = not args.no_cache

    if dry_run:
        print("[dry-run] SAT-014 — no API calls will be made.")

    macro_dir = _macro_dir()
    print(f"[init] Output directory: {macro_dir}")
    print(f"[init] Terms to fetch  : {ALL_TERMS}")
    print(f"[init] Lookback        : {LOOKBACK_DAYS} days")
    print(f"[init] Cache           : {'enabled' if use_cache else 'disabled'}")
    print()

    # Step 1: Fetch raw data from Google Trends.
    raw = fetch_all_terms(dry_run=dry_run, use_cache=use_cache, macro_dir=macro_dir)

    if dry_run:
        print()
        print("[dry-run] Skipping compute and write steps.")
        print(f"[dry-run] Would write:")
        print(f"          {macro_dir / 'google_trends_daily.csv'}")
        print(f"          {macro_dir / 'google_trends_aggregate.csv'}")
        print(f"          {macro_dir / 'google_trends_p2_feature.json'}")
        return

    # Step 2: Compute per-term rolling signals.
    print()
    print("[compute] Applying smoothing and z-score normalisation...")
    per_term = compute_per_term_signals(raw)

    # Step 3: Compute aggregate signal.
    agg = compute_aggregate_signal(per_term)

    # Step 4: Build silo signal dict (for summary — not written to disk here,
    # but available for import by AIM-R14).
    silo = get_latest_silo_signal(agg, per_term)

    # Step 5: Write outputs.
    print()
    print("[write] Saving outputs...")
    write_daily_csv(per_term, macro_dir)
    write_aggregate_csv(agg, macro_dir)
    write_p2_feature_json(agg, macro_dir)

    # Step 6: Print human-readable summary.
    print_summary(agg, silo)


if __name__ == "__main__":
    main()
