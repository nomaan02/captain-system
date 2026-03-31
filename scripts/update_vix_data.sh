#!/bin/bash
# Daily VIX/VXV data update from CBOE
# Run via cron: 0 18 * * 1-5 /path/to/update_vix_data.sh

set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)/data/vix"

curl -sf -o "$DIR/VIX_History_raw.csv" "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
curl -sf -o "$DIR/VIX3M_History_raw.csv" "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv"

# Convert CBOE format (DATE MM/DD/YYYY, CLOSE) to vix_provider format (date YYYY-MM-DD, vix_close)
python3 -c "
import csv, sys
from datetime import datetime

for src, dst, col in [
    ('$DIR/VIX_History_raw.csv', '$DIR/vix_daily_close.csv', 'vix_close'),
    ('$DIR/VIX3M_History_raw.csv', '$DIR/vxv_daily_close.csv', 'vxv_close'),
]:
    with open(src) as f, open(dst, 'w', newline='') as out:
        reader = csv.DictReader(f)
        writer = csv.writer(out)
        writer.writerow(['date', col])
        for row in reader:
            d = datetime.strptime(row['DATE'], '%m/%d/%Y').strftime('%Y-%m-%d')
            writer.writerow([d, f\"{float(row['CLOSE']):.2f}\"])
"

echo "$(date): VIX/VXV updated. VIX last: $(tail -1 $DIR/vix_daily_close.csv), VXV last: $(tail -1 $DIR/vxv_daily_close.csv)"
