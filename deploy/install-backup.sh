#!/bin/bash
# ================================================================
# Captain System — Install Daily Backup Cron
# Backs up QuestDB + Redis data daily at 2 AM ET.
# Keeps 14 days of backups.
#
# Usage:
#   ssh captain@<VPS_IP> 'bash -s' < deploy/install-backup.sh
# ================================================================
set -euo pipefail

BACKUP_DIR=/home/captain/backups
mkdir -p "${BACKUP_DIR}"

echo "→ Installing backup script..."

cat > /home/captain/backup.sh <<'BACKUP'
#!/bin/bash
# Daily backup: QuestDB data + Redis AOF + .env
# Runs at 2 AM ET (outside all trading sessions)

set -euo pipefail

BACKUP_DIR=/home/captain/backups
CAPTAIN_DIR=/home/captain/captain-system
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=14
LOG_PREFIX="$(date '+%Y-%m-%d %H:%M:%S')"

mkdir -p "${BACKUP_DIR}"

echo "${LOG_PREFIX} Starting backup..."

# QuestDB: snapshot while running (QuestDB supports hot backup via /exec endpoint)
echo "${LOG_PREFIX} Backing up QuestDB..."
tar czf "${BACKUP_DIR}/questdb_${TIMESTAMP}.tar.gz" -C "${CAPTAIN_DIR}" questdb/db 2>/dev/null || {
    echo "${LOG_PREFIX} WARNING: QuestDB backup failed — trying with container stop..."
    cd "${CAPTAIN_DIR}"
    docker compose stop questdb
    tar czf "${BACKUP_DIR}/questdb_${TIMESTAMP}.tar.gz" -C "${CAPTAIN_DIR}" questdb/db
    docker compose start questdb
}

# Redis AOF
echo "${LOG_PREFIX} Backing up Redis..."
if [ -f "${CAPTAIN_DIR}/redis/appendonly.aof" ]; then
    cp "${CAPTAIN_DIR}/redis/appendonly.aof" "${BACKUP_DIR}/redis_${TIMESTAMP}.aof"
fi

# .env backup (encrypted credentials)
cp "${CAPTAIN_DIR}/.env" "${BACKUP_DIR}/env_${TIMESTAMP}.bak"
chmod 600 "${BACKUP_DIR}/env_${TIMESTAMP}.bak"

# Cleanup old backups
find "${BACKUP_DIR}" -name "questdb_*.tar.gz" -mtime +${KEEP_DAYS} -delete
find "${BACKUP_DIR}" -name "redis_*.aof" -mtime +${KEEP_DAYS} -delete
find "${BACKUP_DIR}" -name "env_*.bak" -mtime +${KEEP_DAYS} -delete

SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
echo "${LOG_PREFIX} Backup complete: ${TIMESTAMP} (${SIZE} total)"
BACKUP

chmod +x /home/captain/backup.sh
echo "  backup.sh installed"

# Add to cron
echo "→ Adding backup cron job..."
crontab -l 2>/dev/null | grep -v 'backup.sh' > /tmp/backup_cron || true
echo "0 2 * * * /home/captain/backup.sh >> /home/captain/logs/backup.log 2>&1" >> /tmp/backup_cron
crontab /tmp/backup_cron
rm /tmp/backup_cron

echo "  Cron installed: 2 AM ET daily"
echo ""
echo "=== Backup cron complete ==="
echo "  Test now:   /home/captain/backup.sh"
echo "  Backups at: ${BACKUP_DIR}"
echo "  Log:        tail -f ~/logs/backup.log"
echo "  Retention:  14 days"
