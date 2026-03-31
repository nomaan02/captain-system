# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Generate P2-D02 regime labels JSON from transition boundaries.

The regime labels (LOW/HIGH vol state) were extracted from QC Object Store
key 'pipeline_p2_d02_SPY.json' on 2026-03-16. Original: 4568 total days,
4268 valid (300 warm-up null excluded). Date range: 2009-03-12 to 2026-02-27.

This script encodes the data compactly as transition boundaries rather than
4268 individual entries. Run once to generate the JSON file.

Usage: python scripts/generate_d02_regime_labels.py
"""

import json
import os
from datetime import datetime, timedelta

# Regime transitions: (start_date, end_date, label)
# Extracted from P2 Block 1 Pettersson Vol State output
# Each range is inclusive on both ends
TRANSITIONS = [
    ("2009-03-12", "2010-05-06", "LOW"),
    ("2010-05-07", "2010-09-08", "HIGH"),
    ("2010-09-09", "2011-06-23", "LOW"),
    ("2011-06-24", "2011-07-06", "HIGH"),
    ("2011-07-07", "2011-07-14", "LOW"),
    ("2011-07-15", "2011-12-29", "HIGH"),
    ("2011-12-30", "2013-06-05", "LOW"),
    ("2013-06-06", "2013-08-09", "HIGH"),
    ("2013-08-12", "2014-02-05", "LOW"),
    ("2014-02-06", "2014-02-14", "HIGH"),
    ("2014-02-18", "2014-02-18", "LOW"),  # single day
    ("2014-02-19", "2014-02-19", "LOW"),  # continuation
    ("2014-02-20", "2014-06-03", "HIGH"),
    ("2014-06-04", "2014-10-09", "LOW"),
    ("2014-10-10", "2015-03-30", "HIGH"),
    ("2015-03-31", "2015-08-24", "LOW"),
    ("2015-08-25", "2016-04-04", "HIGH"),
    ("2016-04-05", "2017-12-04", "LOW"),
    ("2017-12-05", "2017-12-12", "HIGH"),
    ("2017-12-13", "2018-01-24", "LOW"),
    ("2018-01-25", "2018-07-01", "HIGH"),
    ("2018-07-02", "2018-10-23", "LOW"),
    ("2018-10-24", "2019-03-17", "HIGH"),
    ("2019-03-18", "2020-02-26", "LOW"),
    ("2020-02-27", "2020-07-16", "HIGH"),
    ("2020-07-17", "2021-12-01", "LOW"),
    ("2021-12-02", "2022-08-16", "HIGH"),
    ("2022-08-17", "2022-10-13", "LOW"),
    ("2022-10-14", "2022-11-24", "HIGH"),
    ("2022-11-25", "2024-05-01", "LOW"),
    ("2024-05-02", "2024-05-09", "HIGH"),
    ("2024-05-10", "2024-07-31", "LOW"),
    ("2024-08-01", "2024-11-12", "HIGH"),
    ("2024-11-13", "2025-01-12", "LOW"),
    ("2025-01-13", "2025-01-21", "HIGH"),
    ("2025-01-22", "2025-02-03", "LOW"),
    ("2025-02-04", "2025-02-17", "HIGH"),
    ("2025-02-18", "2025-02-26", "LOW"),
    ("2025-02-27", "2025-07-16", "HIGH"),
    ("2025-07-17", "2026-02-27", "LOW"),
]

# US market holidays (approximate — doesn't need to be perfect for regime labels)
# The regime labels are keyed by trading days only
US_HOLIDAYS_APPROX = set()  # not needed — we generate all weekdays, matching is by date


def generate_trading_days(start: str, end: str):
    """Generate weekday dates between start and end (inclusive)."""
    current = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    while current <= end_dt:
        if current.weekday() < 5:  # Mon-Fri
            yield current.strftime("%Y-%m-%d")
        current += timedelta(days=1)


def generate_regime_labels() -> dict:
    """Generate the full regime labels dict from transitions."""
    labels = {}
    for start, end, label in TRANSITIONS:
        for date in generate_trading_days(start, end):
            labels[date] = label
    return labels


if __name__ == "__main__":
    labels = generate_regime_labels()
    print(f"Generated {len(labels)} regime labels")
    print(f"Date range: {min(labels.keys())} to {max(labels.keys())}")

    low = sum(1 for v in labels.values() if v == "LOW")
    high = sum(1 for v in labels.values() if v == "HIGH")
    print(f"LOW: {low}, HIGH: {high}")

    out_path = os.path.join(os.path.dirname(__file__),
                            "..", "data", "p2_outputs", "ES",
                            "p2_d02_regime_labels.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(labels, f, indent=2)
    print(f"Written to {out_path}")
