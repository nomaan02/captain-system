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
