#!/bin/bash
# ================================================================
# Captain System — Install VIX/VXV Daily Data Update Cron
# Fetches closing data from CBOE at 6:30 PM ET weekdays.
#
# Usage:
#   ssh captain@<VPS_IP> 'bash -s' < deploy/install-vix-cron.sh
# ================================================================
set -euo pipefail

echo "→ Installing VIX/VXV update script..."

cat > /home/captain/update-vix-data.sh <<'VIXSCRIPT'
#!/bin/bash
# Fetch VIX/VXV daily close from CBOE and append to captain data CSVs.
# Runs at 6:30 PM ET weekdays (after CBOE publishes closing data).

set -euo pipefail

DATA_DIR=/home/captain/captain-system/data/vix
TODAY=$(date +%Y-%m-%d)
LOG_PREFIX="$(date '+%Y-%m-%d %H:%M:%S')"

cd /home/captain/captain-system

# Load Telegram creds
TELEGRAM_TOKEN=$(grep -oP 'TELEGRAM_BOT_TOKEN=\K.+' .env 2>/dev/null || echo "")
CHAT_ID=$(grep -oP 'TELEGRAM_CHAT_ID=\K.+' .env 2>/dev/null || echo "")

send_msg() {
    if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
            -d "chat_id=${CHAT_ID}" -d "text=$1" --max-time 10 >/dev/null 2>&1 || true
    fi
    echo "${LOG_PREFIX} $1"
}

# Download full CSVs from CBOE
VIX_URL="https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
VXV_URL="https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv"

VIX_CLOSE=$(curl -sf "$VIX_URL" | tail -1 | cut -d',' -f5)
VXV_CLOSE=$(curl -sf "$VXV_URL" | tail -1 | cut -d',' -f5)

if [ -z "$VIX_CLOSE" ] || [ -z "$VXV_CLOSE" ]; then
    send_msg "VIX/VXV data fetch FAILED for ${TODAY}"
    exit 1
fi

# Append to CSVs (idempotent)
if ! grep -q "$TODAY" "$DATA_DIR/vix_daily_close.csv" 2>/dev/null; then
    echo "${TODAY},${VIX_CLOSE}" >> "$DATA_DIR/vix_daily_close.csv"
fi

if ! grep -q "$TODAY" "$DATA_DIR/vxv_daily_close.csv" 2>/dev/null; then
    echo "${TODAY},${VXV_CLOSE}" >> "$DATA_DIR/vxv_daily_close.csv"
fi

# Compute IVTS ratio
IVTS=$(python3 -c "print(round(${VIX_CLOSE}/${VXV_CLOSE}, 6))")
if ! grep -q "$TODAY" "$DATA_DIR/ivts_daily.csv" 2>/dev/null; then
    echo "${TODAY},${VIX_CLOSE},${VXV_CLOSE},${IVTS}" >> "$DATA_DIR/ivts_daily.csv"
fi

send_msg "VIX data updated: VIX=${VIX_CLOSE}, VXV=${VXV_CLOSE}, IVTS=${IVTS}"
VIXSCRIPT

chmod +x /home/captain/update-vix-data.sh
echo "  update-vix-data.sh installed"

# Add to cron (avoid duplicates)
echo "→ Adding VIX cron job..."
crontab -l 2>/dev/null | grep -v 'update-vix-data' > /tmp/vix_cron || true
echo "30 18 * * 1-5 /home/captain/update-vix-data.sh >> /home/captain/logs/vix-update.log 2>&1" >> /tmp/vix_cron
crontab /tmp/vix_cron
rm /tmp/vix_cron

echo "  Cron installed: 6:30 PM ET weekdays"
echo ""
echo "=== VIX update cron complete ==="
echo "  Test now: /home/captain/update-vix-data.sh"
echo "  Log:      tail -f ~/logs/vix-update.log"
