#!/usr/bin/env bash
# captain-update.sh — Pull latest code and rebuild Captain System containers.
#
# Preserves: .env, vault/, questdb/db/, redis/ (all gitignored)
# Updates:   all code, Docker images, QuestDB schema (idempotent)
#
# Usage:
#   bash scripts/captain-update.sh           # Pull + rebuild
#   bash scripts/captain-update.sh --skip-pull  # Rebuild only (no git pull)

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[update]${NC} $*"; }
warn() { echo -e "${YELLOW}[update]${NC} $*"; }
err()  { echo -e "${RED}[update]${NC} $*" >&2; }
info() { echo -e "${CYAN}[update]${NC} $*"; }

CAPTAIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$CAPTAIN_DIR"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.local.yml"

SKIP_PULL=false
for arg in "$@"; do
    case "$arg" in
        --skip-pull) SKIP_PULL=true ;;
    esac
done

echo ""
log "Captain System — Update ($(date '+%Y-%m-%d %H:%M:%S'))"
echo ""

# ── Step 1: Git Pull ──────────────────────────────────────────────────────
if [ "$SKIP_PULL" = "false" ]; then
    info "Pulling latest changes..."

    # Check for uncommitted changes
    if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
        warn "You have uncommitted local changes:"
        git status --short
        echo ""
        warn "These will be preserved. Only tracked files are updated."
    fi

    git pull origin main 2>&1 | while IFS= read -r line; do echo "  $line"; done
    log "Git pull: complete"
else
    info "Skipping git pull (--skip-pull)"
fi

# ── Step 2: Check for .env.template changes ───────────────────────────────
info "Checking for new environment variables..."

if [ -f ".env" ] && [ -f ".env.template" ]; then
    # Extract variable names from template (lines with = that aren't comments)
    template_vars=$(grep -E '^[A-Z_]+=' .env.template | cut -d= -f1 | sort)
    env_vars=$(grep -E '^[A-Z_]+=' .env | cut -d= -f1 | sort)

    new_vars=$(comm -23 <(echo "$template_vars") <(echo "$env_vars") 2>/dev/null || true)

    if [ -n "$new_vars" ]; then
        warn "New variables found in .env.template that are missing from your .env:"
        echo ""
        for var in $new_vars; do
            # Get the line from template for context
            template_line=$(grep "^${var}=" .env.template || echo "${var}=")
            echo -e "  ${YELLOW}${template_line}${NC}"
        done
        echo ""
        warn "Add these to your .env file. Check .env.template for descriptions."
        echo ""
    else
        log ".env variables: up to date"
    fi
else
    if [ ! -f ".env" ]; then
        err ".env not found! Run: bash scripts/captain-setup.sh"
        exit 1
    fi
fi

# ── Step 3: Sync Config ──────────────────────────────────────────────────
info "Syncing config into build contexts..."
for svc in captain-offline captain-online captain-command; do
    rm -rf "$CAPTAIN_DIR/$svc/_config"
    cp -r "$CAPTAIN_DIR/config" "$CAPTAIN_DIR/$svc/_config"
done
log "Config synced"

# ── Step 3b: Backup QuestDB data before rebuild ──────────────────────────
BACKUP_DIR="$CAPTAIN_DIR/backups/questdb"
QDB_DATA="$CAPTAIN_DIR/questdb/db"

if [ -d "$QDB_DATA" ] && [ "$(ls -A "$QDB_DATA" 2>/dev/null)" ]; then
    mkdir -p "$BACKUP_DIR"
    BACKUP_FILE="$BACKUP_DIR/questdb-pre-update-$(date '+%Y%m%d-%H%M%S').tar.gz"
    info "Backing up QuestDB data → $BACKUP_FILE"
    tar czf "$BACKUP_FILE" -C "$CAPTAIN_DIR" questdb/db/ 2>/dev/null && \
        log "  QuestDB backup complete ($(du -h "$BACKUP_FILE" | cut -f1))" || \
        warn "  QuestDB backup failed (non-fatal, continuing)"

    # Keep only the 7 most recent backups (pre-update + daily)
    ls -t "$BACKUP_DIR"/questdb-*.tar.gz 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null
else
    info "No existing QuestDB data to back up (fresh install)"
fi

# ── Step 4: Rebuild and Restart ───────────────────────────────────────────
info "Rebuilding and restarting containers..."
$COMPOSE up -d --build 2>&1 | while IFS= read -r line; do echo "  $line"; done
log "Containers rebuilt"

# ── Step 5: Wait for Infrastructure ───────────────────────────────────────
info "Waiting for QuestDB + Redis..."
elapsed=0
while [ $elapsed -lt 60 ]; do
    qdb=$(docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T questdb \
        curl -sf "http://localhost:9000/exec?query=SELECT%201" 2>/dev/null && echo "ok" || echo "")
    rds=$(docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T redis \
        redis-cli ping 2>/dev/null || echo "")
    if [ -n "$qdb" ] && echo "$rds" | grep -q PONG; then
        break
    fi
    sleep 5
    elapsed=$((elapsed + 5))
done
log "Infrastructure: ready"

# ── Step 6: Re-run Init (idempotent) ─────────────────────────────────────
info "Ensuring QuestDB tables are up to date..."
$COMPOSE exec -T -e PYTHONPATH=/app captain-offline \
    python /captain/scripts/init_questdb.py 2>&1 | tail -5 | while IFS= read -r line; do echo "  $line"; done
log "Schema: up to date"

# ── Step 6a: Seed data (idempotent — safe to re-run) ────────────────────
# These scripts INSERT new rows; QuestDB's append-only model + LATEST ON
# queries means re-running is harmless (duplicate inserts are superseded).
info "Seeding data (idempotent)..."

# Core asset bootstrap (reads git-tracked P1/P2 data)
$COMPOSE exec -T -e PYTHONPATH=/app captain-offline \
    python /captain/scripts/seed_all_assets.py 2>&1 | tail -3 | while IFS= read -r line; do echo "  $line"; done

# AIM historical data (reads git-tracked data/seed/ CSVs)
for seed_script in \
    seed_iv_rv_from_extract.py \
    seed_skew_from_extract.py \
    seed_ohlcv_from_qc.py \
    seed_or_volumes_from_qc.py \
    seed_opening_vol_from_qc.py; do
    $COMPOSE exec -T -e PYTHONPATH=/app captain-offline \
        python "/captain/scripts/$seed_script" 2>&1 | tail -1 | while IFS= read -r line; do echo "  $line"; done
done

log "Data seeding: complete"

# ── Step 6b: Data Integrity Check ────────────────────────────────────────
info "Verifying QuestDB data integrity..."
DATA_OK=true
$COMPOSE exec -T -e PYTHONPATH=/app captain-offline python -c "
import psycopg2, os, sys
conn = psycopg2.connect(host=os.environ.get('QUESTDB_HOST','questdb'), port=int(os.environ.get('QUESTDB_PORT','8812')), user='admin', password='quest', dbname='qdb')
conn.autocommit = True
cur = conn.cursor()
critical = {
    'p3_d00_asset_universe': 10,   # 10 active assets
    'p3_d01_aim_model_states': 50, # ~270 rows
    'p3_d02_aim_meta_weights': 50, # 60 rows
    'p3_d12_kelly_parameters': 10, # 60 rows
    'p3_d16_user_capital_silos': 1 # at least 1 silo
}
empty = []
for table, min_rows in critical.items():
    try:
        cur.execute(f'SELECT count() FROM {table}')
        count = cur.fetchone()[0]
        if count < min_rows:
            empty.append(f'{table}: {count} rows (expected >= {min_rows})')
    except Exception as e:
        empty.append(f'{table}: MISSING ({e})')
cur.close(); conn.close()
if empty:
    print('INTEGRITY_FAIL')
    for e in empty:
        print(f'  EMPTY: {e}')
    sys.exit(1)
else:
    print('INTEGRITY_OK')
" 2>&1 | while IFS= read -r line; do echo "  $line"; done

if [ "${PIPESTATUS[0]}" -ne 0 ]; then
    DATA_OK=false
    err ""
    err "DATA INTEGRITY CHECK FAILED — critical tables are empty or missing."
    err "This usually means QuestDB data was wiped during the update."
    err ""
    if ls "$BACKUP_DIR"/questdb-*.tar.gz >/dev/null 2>&1; then
        latest_backup=$(ls -t "$BACKUP_DIR"/questdb-*.tar.gz | head -1)
        err "A backup exists: $latest_backup"
        err "To restore:"
        err "  1. docker compose -f docker-compose.yml -f docker-compose.local.yml down"
        err "  2. rm -rf questdb/db/*"
        err "  3. tar xzf $latest_backup -C $CAPTAIN_DIR"
        err "  4. docker compose -f docker-compose.yml -f docker-compose.local.yml up -d"
    else
        err "No backups found in $BACKUP_DIR"
    fi
    err ""
    err "Containers are running but DATA IS MISSING. DO NOT TRADE until resolved."
    err ""
else
    log "Data integrity: OK"
fi

# ── Step 7: Health Check ─────────────────────────────────────────────────
info "Health check..."
EXPECTED="questdb redis captain-offline captain-online captain-command nginx"
all_up=true
for svc in $EXPECTED; do
    if $COMPOSE ps --status running 2>/dev/null | grep -q "$svc"; then
        log "  $svc: running"
    else
        err "  $svc: NOT running"
        all_up=false
    fi
done

echo ""
if $all_up; then
    log "Update complete — all containers running"
else
    warn "Update complete — some containers may still be starting"
    warn "Check: $COMPOSE logs --tail 20"
fi
echo ""
