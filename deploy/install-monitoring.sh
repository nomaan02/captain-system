#!/bin/bash
# ================================================================
# Captain System — Install Monitoring, Healthcheck & Auto-Start
# Run on the VPS as captain user (or root).
#
# Usage:
#   ssh captain@<VPS_IP> 'bash -s' < deploy/install-monitoring.sh
# ================================================================
set -euo pipefail

CAPTAIN_DIR=/home/captain/captain-system
LOG_DIR=/home/captain/logs

mkdir -p "${LOG_DIR}"

# ── 1. Systemd service (auto-start on reboot) ───────────────────
echo "→ Installing systemd service..."
sudo tee /etc/systemd/system/captain.service > /dev/null <<'UNIT'
[Unit]
Description=Captain Trading System
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=captain
WorkingDirectory=/home/captain/captain-system
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=180

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable captain.service
echo "  captain.service enabled (auto-start on boot)"

# ── 2. Healthcheck script ───────────────────────────────────────
echo "→ Installing healthcheck script..."
cat > /home/captain/healthcheck.sh <<'HEALTH'
#!/bin/bash
# Captain healthcheck — runs every 5 minutes via cron
# Restarts unhealthy containers, alerts via Telegram

set -euo pipefail
cd /home/captain/captain-system

# Load Telegram creds from .env
TELEGRAM_TOKEN=$(grep -oP 'TELEGRAM_BOT_TOKEN=\K.+' .env 2>/dev/null || echo "")
CHAT_ID=$(grep -oP 'TELEGRAM_CHAT_ID=\K.+' .env 2>/dev/null || echo "")
HOSTNAME=$(hostname)

send_alert() {
    if [ -n "$TELEGRAM_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        curl -sf -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
            -d "chat_id=${CHAT_ID}" \
            -d "text=CAPTAIN ${HOSTNAME}: $1" \
            --max-time 10 >/dev/null 2>&1 || true
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S') ALERT: $1"
}

FAILED=0

for svc in questdb redis captain-offline captain-online captain-command; do
    state=$(docker compose ps --format '{{.State}}' "${svc}" 2>/dev/null || echo "missing")

    if [ "$state" != "running" ]; then
        FAILED=$((FAILED + 1))
        send_alert "${svc} is ${state}. Restarting..."
        docker compose restart "${svc}" 2>/dev/null || true
        sleep 15

        new_state=$(docker compose ps --format '{{.State}}' "${svc}" 2>/dev/null || echo "missing")
        if [ "$new_state" = "running" ]; then
            send_alert "${svc} recovered after restart."
        else
            send_alert "${svc} FAILED TO RESTART (${new_state}). Manual intervention required."
        fi
    fi
done

if [ $FAILED -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') OK: all services running"
fi
HEALTH

chmod +x /home/captain/healthcheck.sh
echo "  healthcheck.sh installed"

# ── 3. Cron jobs ─────────────────────────────────────────────────
echo "→ Installing cron jobs..."

# Remove any existing captain crons, then add fresh
crontab -l 2>/dev/null | grep -v 'healthcheck.sh' | grep -v 'roll_calendar' > /tmp/captain_cron || true

# Healthcheck every 5 minutes
echo "*/5 * * * * /home/captain/healthcheck.sh >> /home/captain/logs/healthcheck.log 2>&1" >> /tmp/captain_cron

# Contract roll calendar check daily at 6 AM ET weekdays
echo "0 6 * * 1-5 cd /home/captain/captain-system && docker compose exec -T captain-command python -m scripts.roll_calendar_update --check --notify >> /home/captain/logs/roll-check.log 2>&1" >> /tmp/captain_cron

crontab /tmp/captain_cron
rm /tmp/captain_cron

echo "  Cron installed:"
echo "    - Healthcheck: every 5 min"
echo "    - Roll calendar check: 6 AM ET weekdays"

echo ""
echo "=== Monitoring setup complete ==="
echo "  Systemd: sudo systemctl status captain"
echo "  Healthcheck log: tail -f ~/logs/healthcheck.log"
echo "  Roll check log:  tail -f ~/logs/roll-check.log"
