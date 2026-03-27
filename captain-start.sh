#!/usr/bin/env bash
# captain-start.sh — WSL 2 startup script for Captain System
#
# Verifies prerequisites, starts Docker Compose, initialises QuestDB tables,
# and health-checks all containers.
#
# Usage:
#   bash captain-start.sh              # Normal daily start (skip rebuild)
#   bash captain-start.sh --build      # Force rebuild (after code changes)
#   CAPTAIN_DIR=/path bash captain-start.sh  # Custom project path
#
# Task Scheduler:
#   wsl.exe -d Ubuntu -- bash /home/nomaan/captain-system/captain-start.sh

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
CAPTAIN_DIR="${CAPTAIN_DIR:-/home/nomaan/captain-system}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.local.yml"
HEALTH_TIMEOUT=180          # seconds to wait for containers (first run builds images)
HEALTH_INTERVAL=5           # seconds between health polls
QUESTDB_INIT_TIMEOUT=60     # seconds to wait for QuestDB SQL engine
REQUIRED_VM_MAX_MAP_COUNT=1048576

# Parse arguments
BUILD_FLAG=""
for arg in "$@"; do
    case "$arg" in
        --build) BUILD_FLAG="--build" ;;
    esac
done

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[captain]${NC} $*"; }
warn() { echo -e "${YELLOW}[captain]${NC} $*"; }
err()  { echo -e "${RED}[captain]${NC} $*" >&2; }
info() { echo -e "${CYAN}[captain]${NC} $*"; }

# ── Timestamp ──────────────────────────────────────────────────────────────────
log "Captain System startup — $(date '+%Y-%m-%d %H:%M:%S %Z')"

# ── Step 1: vm.max_map_count (QuestDB needs >= 1048576) ───────────────────────
current_mmc=$(cat /proc/sys/vm/max_map_count 2>/dev/null || echo "0")
if [ "$current_mmc" -lt "$REQUIRED_VM_MAX_MAP_COUNT" ]; then
    warn "vm.max_map_count=$current_mmc (need $REQUIRED_VM_MAX_MAP_COUNT for QuestDB)"
    if sudo sysctl -w vm.max_map_count=$REQUIRED_VM_MAX_MAP_COUNT >/dev/null 2>&1; then
        log "vm.max_map_count set to $REQUIRED_VM_MAX_MAP_COUNT"
    else
        err "FATAL: Cannot set vm.max_map_count. Run: sudo sysctl -w vm.max_map_count=$REQUIRED_VM_MAX_MAP_COUNT"
        exit 1
    fi
else
    log "vm.max_map_count OK ($current_mmc)"
fi

# ── Step 2: Docker daemon ─────────────────────────────────────────────────────
DOCKER_WAIT=0
while ! docker info >/dev/null 2>&1; do
    if [ $DOCKER_WAIT -ge 60 ]; then
        err "Docker Desktop not available after 60s. Start it manually."
        exit 1
    fi
    if [ $DOCKER_WAIT -eq 0 ]; then
        warn "Waiting for Docker Desktop to start..."
    fi
    sleep 5
    DOCKER_WAIT=$((DOCKER_WAIT + 5))
done
log "Docker daemon OK"

# ── Step 3: Project directory validation ───────────────────────────────────────
cd "$CAPTAIN_DIR" 2>/dev/null || { err "Cannot cd to $CAPTAIN_DIR"; exit 1; }

missing=""
[ ! -f "docker-compose.yml" ]          && missing="$missing docker-compose.yml"
[ ! -f "docker-compose.local.yml" ]    && missing="$missing docker-compose.local.yml"
[ ! -f "nginx/nginx-local.conf" ]      && missing="$missing nginx/nginx-local.conf"
[ ! -f ".env" ]                        && missing="$missing .env"

if [ -n "$missing" ]; then
    err "Missing files in $CAPTAIN_DIR:$missing"
    exit 1
fi
log "Project files OK"

# ── Step 4: Start containers ──────────────────────────────────────────────────
if [ -n "$BUILD_FLAG" ]; then
    info "Starting with --build (rebuilding images)..."
else
    info "Starting containers (no rebuild — pass --build to force)..."
fi

docker compose $COMPOSE_FILES up -d $BUILD_FLAG 2>&1 | while IFS= read -r line; do
    echo "  $line"
done
RC=${PIPESTATUS[0]}
if [ "$RC" -ne 0 ]; then
    err "docker compose up failed (exit $RC). Check: docker compose $COMPOSE_FILES logs --tail 30"
    exit 1
fi

# ── Step 5: Wait for infrastructure (QuestDB + Redis) ─────────────────────────
info "Waiting for QuestDB and Redis..."

questdb_ready=false
redis_ready=false
elapsed=0

while [ $elapsed -lt $QUESTDB_INIT_TIMEOUT ]; do
    if ! $questdb_ready; then
        if docker compose $COMPOSE_FILES exec -T questdb curl -sf "http://localhost:9000/exec?query=SELECT%201" >/dev/null 2>&1; then
            log "  QuestDB SQL engine: ready"
            questdb_ready=true
        fi
    fi

    if ! $redis_ready; then
        if docker compose $COMPOSE_FILES exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
            log "  Redis: PONG"
            redis_ready=true
        fi
    fi

    if $questdb_ready && $redis_ready; then
        break
    fi

    sleep $HEALTH_INTERVAL
    elapsed=$((elapsed + HEALTH_INTERVAL))
done

if ! $questdb_ready; then
    err "QuestDB not ready after ${QUESTDB_INIT_TIMEOUT}s"
    err "Check: docker compose $COMPOSE_FILES logs questdb --tail 30"
    exit 1
fi
if ! $redis_ready; then
    err "Redis not ready after ${QUESTDB_INIT_TIMEOUT}s"
    exit 1
fi

# ── Step 6: Initialise QuestDB tables (idempotent — CREATE IF NOT EXISTS) ─────
info "Ensuring QuestDB tables exist..."
# scripts/ is mounted at /captain/scripts in captain-offline (via local override)
if docker compose $COMPOSE_FILES exec -T -e PYTHONPATH=/app captain-offline \
    python /captain/scripts/init_questdb.py 2>&1 | while IFS= read -r line; do echo "  $line"; done
then
    log "  QuestDB table init complete"
else
    # Fallback: check if tables already exist (init may fail on re-run but tables are there)
    if docker compose $COMPOSE_FILES exec -T captain-offline \
        python -c "
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('QUESTDB_HOST','questdb'), port=int(os.environ.get('QUESTDB_PORT','8812')), user='admin', password='quest', dbname='qdb')
conn.autocommit = True
cur = conn.cursor()
cur.execute('SELECT count() FROM p3_d00_asset_universe')
print('QuestDB tables already exist (verified p3_d00_asset_universe)')
cur.close(); conn.close()
" 2>&1 | while IFS= read -r line; do echo "  $line"; done
    then
        log "  QuestDB tables verified"
    else
        warn "  QuestDB table init needs manual run: docker compose $COMPOSE_FILES exec captain-offline python /captain/scripts/init_questdb.py"
    fi
fi

# ── Step 7: Wait for all 6 services to be running ─────────────────────────────
EXPECTED="questdb redis captain-offline captain-online captain-command nginx"
elapsed=0

info "Waiting for all containers (timeout: ${HEALTH_TIMEOUT}s)..."

while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
    all_up=true
    status=""

    for svc in $EXPECTED; do
        if docker compose $COMPOSE_FILES ps --status running 2>/dev/null | grep -q "$svc"; then
            status="$status ${GREEN}$svc${NC}"
        else
            status="$status ${RED}$svc${NC}"
            all_up=false
        fi
    done

    if $all_up; then
        echo ""
        log "All containers running:$status"
        break
    fi

    printf "\r  [%3ds]%b " "$elapsed" "$status"
    sleep $HEALTH_INTERVAL
    elapsed=$((elapsed + HEALTH_INTERVAL))
done

if [ $elapsed -ge $HEALTH_TIMEOUT ]; then
    echo ""
    err "TIMEOUT: Not all containers running after ${HEALTH_TIMEOUT}s"
    docker compose $COMPOSE_FILES ps
    err "Check: docker compose $COMPOSE_FILES logs --tail 30"
    exit 1
fi

# ── Step 8: Verify Captain Command API ─────────────────────────────────────────
info "Verifying Captain Command API..."
api_ready=false
for i in $(seq 1 12); do
    if curl -sf http://localhost/api/health >/dev/null 2>&1; then
        log "  API via nginx: OK (http://localhost/api/health)"
        api_ready=true
        break
    elif curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
        log "  API direct: OK (http://localhost:8000/api/health)"
        api_ready=true
        break
    fi
    sleep 5
done

if ! $api_ready; then
    warn "  Captain Command API not responding yet — may still be initializing"
    warn "  Check: docker compose $COMPOSE_FILES logs captain-command --tail 20"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
log "========================================="
log "  Captain System running (local mode)"
log "  GUI:  http://localhost"
log "  API:  http://localhost/api/health"
log "  Time: $(TZ=America/New_York date '+%H:%M:%S %Z')"
log "========================================="
echo ""
info "Commands:"
info "  Stop:    cd $CAPTAIN_DIR && docker compose $COMPOSE_FILES down"
info "  Logs:    cd $CAPTAIN_DIR && docker compose $COMPOSE_FILES logs -f"
info "  Rebuild: bash $0 --build"
