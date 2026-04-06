#!/usr/bin/env bash
# captain-stop.sh — Safe shutdown for Captain System
#
# Stops containers WITHOUT removing volumes (data is preserved).
# Use --wipe to explicitly remove volumes (requires confirmation).
#
# Usage:
#   bash captain-stop.sh              # Safe stop (preserves data)
#   bash captain-stop.sh --wipe       # Stop + remove volumes (DESTRUCTIVE)

set -euo pipefail

CAPTAIN_DIR="${CAPTAIN_DIR:-/home/nomaan/captain-system}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.local.yml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[captain]${NC} $*"; }
warn() { echo -e "${YELLOW}[captain]${NC} $*"; }
err()  { echo -e "${RED}[captain]${NC} $*" >&2; }

cd "$CAPTAIN_DIR" 2>/dev/null || { err "Cannot cd to $CAPTAIN_DIR"; exit 1; }

WIPE=false
for arg in "$@"; do
    case "$arg" in
        --wipe) WIPE=true ;;
        -v)
            err "BLOCKED: 'docker compose down -v' deletes ALL data (QuestDB, Redis)."
            err "If you really mean it, use: bash captain-stop.sh --wipe"
            exit 1
            ;;
    esac
done

if [ "$WIPE" = true ]; then
    echo ""
    err "═══════════════════════════════════════════════════════════"
    err "  DESTRUCTIVE OPERATION — This will DELETE all QuestDB data"
    err "  including seeded AIM data, trade history, and config."
    err "═══════════════════════════════════════════════════════════"
    echo ""

    # Show what will be lost
    QDB_SIZE=$(du -sh "$CAPTAIN_DIR/questdb/db/" 2>/dev/null | cut -f1 || echo "unknown")
    REDIS_SIZE=$(du -sh "$CAPTAIN_DIR/redis/" 2>/dev/null | cut -f1 || echo "unknown")
    warn "  QuestDB data: $QDB_SIZE"
    warn "  Redis data:   $REDIS_SIZE"
    echo ""

    # Auto-backup before wipe
    BACKUP_DIR="$CAPTAIN_DIR/backups/questdb"
    QDB_DATA="$CAPTAIN_DIR/questdb/db"
    if [ -d "$QDB_DATA" ] && [ "$(ls -A "$QDB_DATA" 2>/dev/null)" ]; then
        mkdir -p "$BACKUP_DIR"
        BACKUP_FILE="$BACKUP_DIR/questdb-prewipe-$(date '+%Y%m%d-%H%M%S').tar.gz"
        log "Auto-backup before wipe → $BACKUP_FILE"
        tar czf "$BACKUP_FILE" -C "$CAPTAIN_DIR" questdb/db/ 2>/dev/null && \
            log "  Backup complete ($(du -h "$BACKUP_FILE" | cut -f1))" || \
            warn "  Backup failed — proceeding anyway"
    fi

    read -p "Type YES to confirm data wipe: " confirm
    if [ "$confirm" != "YES" ]; then
        log "Cancelled."
        exit 0
    fi

    log "Stopping containers and removing volumes..."
    docker compose $COMPOSE_FILES down -v
    log "Done. All volumes removed. Run captain-start.sh --build to rebuild."
else
    log "Stopping containers (data preserved)..."
    docker compose $COMPOSE_FILES down
    log "Done. QuestDB and Redis data intact. Run captain-start.sh to restart."
fi
