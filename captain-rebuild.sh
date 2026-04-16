#!/usr/bin/env bash
# captain-rebuild.sh — Heavy rebuild pipeline for Captain System
#
# Use this after major code changes, schema updates, or when the system is in
# a bad state (QuestDB bloat, Redis corruption, bootstrap failures).
#
# For lightweight daily starts, use captain-start.sh instead.
#
# Usage:
#   bash captain-rebuild.sh              # Full rebuild (stop → clean → init → bootstrap → start → verify)
#   bash captain-rebuild.sh --compact    # Compact QuestDB state tables only (no restart)
#   bash captain-rebuild.sh --status     # Health check only (no changes)
#   bash captain-rebuild.sh --help       # Show this help
#
# Works on any tower — auto-detects paths from script location.
# Both Nomaan's and Isaac's towers use this same script.

set -euo pipefail

# ── Path auto-detection (no hardcoded paths) ─────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTAIN_DIR="${CAPTAIN_DIR:-$SCRIPT_DIR}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.local.yml"

# ── Timeouts ─────────────────────────────────────────────────────────────────
INFRA_TIMEOUT="${INFRA_TIMEOUT:-90}"        # seconds for QuestDB + Redis
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-240}"     # seconds for all containers
HEALTH_INTERVAL=5
REQUIRED_VM_MAX_MAP_COUNT=1048576

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}[rebuild]${NC} $*"; }
warn() { echo -e "${YELLOW}[rebuild]${NC} $*"; }
err()  { echo -e "${RED}[rebuild]${NC} $*" >&2; }
info() { echo -e "${CYAN}[rebuild]${NC} $*"; }
step() { echo -e "\n${BOLD}── $* ──${NC}"; }

# ── Parse arguments ──────────────────────────────────────────────────────────
MODE="rebuild"    # rebuild | compact | status
for arg in "$@"; do
    case "$arg" in
        --compact) MODE="compact" ;;
        --status)  MODE="status" ;;
        --help|-h)
            echo "captain-rebuild.sh — Heavy rebuild pipeline for Captain System"
            echo ""
            echo "Usage:"
            echo "  bash captain-rebuild.sh              Full rebuild (stop → clean → init → bootstrap → start → verify)"
            echo "  bash captain-rebuild.sh --compact    Compact QuestDB state tables only (no restart)"
            echo "  bash captain-rebuild.sh --status     Health check only (read-only, no changes)"
            echo "  bash captain-rebuild.sh --help       Show this help"
            echo ""
            echo "Environment:"
            echo "  CAPTAIN_DIR      Project root (default: auto-detect from script location)"
            echo "  INFRA_TIMEOUT    Seconds to wait for QuestDB+Redis (default: 90)"
            echo "  HEALTH_TIMEOUT   Seconds to wait for all containers (default: 240)"
            exit 0
            ;;
        *)
            err "Unknown argument: $arg"
            err "Use --help for usage."
            exit 1
            ;;
    esac
done

# ── Helpers ──────────────────────────────────────────────────────────────────
compose() {
    docker compose $COMPOSE_FILES "$@"
}

wait_for_infra() {
    # Wait for QuestDB SQL engine + Redis PONG
    local elapsed=0
    local qdb_ok=false redis_ok=false
    local redis_pw
    redis_pw=$(grep -oP '^REDIS_PASSWORD=\K.*' "$CAPTAIN_DIR/.env" 2>/dev/null || echo "")

    while [ $elapsed -lt "$INFRA_TIMEOUT" ]; do
        if ! $qdb_ok; then
            if compose exec -T questdb curl -sf "http://localhost:9000/exec?query=SELECT%201" >/dev/null 2>&1; then
                log "  QuestDB SQL engine: ready"
                qdb_ok=true
            fi
        fi
        if ! $redis_ok; then
            if compose exec -T redis redis-cli ${redis_pw:+-a "$redis_pw"} ping 2>/dev/null | grep -q PONG; then
                log "  Redis: PONG"
                redis_ok=true
            fi
        fi
        if $qdb_ok && $redis_ok; then return 0; fi
        sleep $HEALTH_INTERVAL
        elapsed=$((elapsed + HEALTH_INTERVAL))
    done

    # Partial readiness
    if ! $qdb_ok; then err "QuestDB not ready after ${INFRA_TIMEOUT}s"; fi
    if ! $redis_ok; then
        if compose ps 2>/dev/null | grep -q "redis.*healthy"; then
            warn "Redis script-level ping failed, but Docker healthcheck healthy — continuing."
            return 0
        fi
        err "Redis not ready after ${INFRA_TIMEOUT}s"
    fi
    $qdb_ok  # return 0 if at least QuestDB is up (Redis fallback handled above)
}

wait_for_all_services() {
    local expected="questdb redis captain-offline captain-online captain-command nginx"
    local elapsed=0

    while [ $elapsed -lt "$HEALTH_TIMEOUT" ]; do
        local all_up=true status_line=""
        for svc in $expected; do
            if compose ps --status running 2>/dev/null | grep -q "$svc"; then
                status_line="$status_line ${GREEN}$svc${NC}"
            else
                status_line="$status_line ${RED}$svc${NC}"
                all_up=false
            fi
        done

        if $all_up; then
            echo ""
            log "All containers running:$status_line"
            return 0
        fi

        printf "\r  [%3ds]%b " "$elapsed" "$status_line"
        sleep $HEALTH_INTERVAL
        elapsed=$((elapsed + HEALTH_INTERVAL))
    done

    echo ""
    err "TIMEOUT: Not all containers running after ${HEALTH_TIMEOUT}s"
    compose ps
    return 1
}

verify_api() {
    info "Verifying Captain Command API..."
    for _ in $(seq 1 12); do
        if curl -sf http://localhost/api/health >/dev/null 2>&1; then
            log "  API via nginx: OK"
            return 0
        elif curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
            log "  API direct: OK"
            return 0
        fi
        sleep 5
    done
    warn "  API not responding yet — may still be initializing"
    return 1
}

# ══════════════════════════════════════════════════════════════════════════════
# MODE: --status (read-only health check)
# ══════════════════════════════════════════════════════════════════════════════
if [ "$MODE" = "status" ]; then
    step "Captain System Health Check"
    cd "$CAPTAIN_DIR" 2>/dev/null || { err "Cannot cd to $CAPTAIN_DIR"; exit 1; }

    # Docker
    if docker info >/dev/null 2>&1; then
        log "Docker daemon: OK"
    else
        err "Docker daemon: NOT RUNNING"
        exit 1
    fi

    # Container status
    echo ""
    compose ps 2>/dev/null || { err "No containers found"; exit 1; }

    # QuestDB data integrity
    echo ""
    info "QuestDB data integrity:"
    compose exec -T -e PYTHONPATH=/app captain-offline python -c "
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('QUESTDB_HOST','questdb'), port=int(os.environ.get('QUESTDB_PORT','8812')), user=os.environ.get('QUESTDB_USER','captain'), password=os.environ.get('QUESTDB_PASSWORD',''), dbname='qdb')
conn.autocommit = True
cur = conn.cursor()
tables = {'p3_d00_asset_universe': 10, 'p3_d01_aim_model_states': 50, 'p3_d02_aim_meta_weights': 50, 'p3_d12_kelly_parameters': 10, 'p3_d16_user_capital_silos': 1, 'p3_d25_circuit_breaker_params': 1}
for t, need in tables.items():
    try:
        cur.execute(f'SELECT count() FROM {t}')
        n = cur.fetchone()[0]
        status = 'OK' if n >= need else 'LOW'
        print(f'  {t}: {n} rows ({status}, need >= {need})')
    except:
        print(f'  {t}: MISSING')
cur.close(); conn.close()
" 2>&1 | while IFS= read -r line; do echo "  $line"; done

    # API health
    echo ""
    if curl -sf http://localhost/api/health >/dev/null 2>&1; then
        log "API health: OK"
        curl -s http://localhost/api/health 2>/dev/null | python3 -m json.tool 2>/dev/null | head -20
    else
        warn "API health: NOT RESPONDING"
    fi

    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# MODE: --compact (compact QuestDB only, no restart)
# ══════════════════════════════════════════════════════════════════════════════
if [ "$MODE" = "compact" ]; then
    step "QuestDB State Table Compaction"
    cd "$CAPTAIN_DIR" 2>/dev/null || { err "Cannot cd to $CAPTAIN_DIR"; exit 1; }

    # Verify containers are running
    if ! compose ps --status running 2>/dev/null | grep -q "captain-offline"; then
        err "captain-offline container is not running. Start it first:"
        err "  bash captain-start.sh"
        exit 1
    fi

    info "Running compaction (D01, D02, D05, D12, D25)..."
    if compose exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/compact_questdb_tables.py 2>&1 | while IFS= read -r line; do echo "  $line"; done
    then
        log "Compaction complete"
    else
        err "Compaction failed"
        exit 1
    fi
    exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════
# MODE: full rebuild
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  CAPTAIN SYSTEM — Full Rebuild${NC}"
echo -e "${BOLD}  $(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
echo -e "${BOLD}══════════════════════════════════════════════════════════${NC}"
echo ""

# ── Phase 1: Pre-flight checks ──────────────────────────────────────────────
step "Phase 1: Pre-flight checks"

# 1a. Docker daemon
if ! docker info >/dev/null 2>&1; then
    DOCKER_WAIT=0
    warn "Waiting for Docker daemon..."
    while ! docker info >/dev/null 2>&1; do
        if [ $DOCKER_WAIT -ge 60 ]; then
            err "Docker not available after 60s. Start Docker Desktop manually."
            exit 1
        fi
        sleep 5
        DOCKER_WAIT=$((DOCKER_WAIT + 5))
    done
fi
log "Docker daemon: OK"

# 1b. Project directory
cd "$CAPTAIN_DIR" 2>/dev/null || { err "Cannot cd to $CAPTAIN_DIR"; exit 1; }

missing=""
[ ! -f "docker-compose.yml" ]          && missing="$missing docker-compose.yml"
[ ! -f "docker-compose.local.yml" ]    && missing="$missing docker-compose.local.yml"
[ ! -f "nginx/nginx-local.conf" ]      && missing="$missing nginx/nginx-local.conf"
if [ -n "$missing" ]; then
    err "Missing files in $CAPTAIN_DIR:$missing"
    exit 1
fi
log "Project files: OK"

# 1c. .env validation
if [ ! -f ".env" ]; then
    err "Missing .env file. Copy from template and fill in credentials:"
    err "  cp .env.template .env && nano .env"
    exit 1
fi

# Check for required variables
env_missing=""
for var in TOPSTEP_USERNAME TOPSTEP_API_KEY REDIS_PASSWORD; do
    if ! grep -q "^${var}=" .env 2>/dev/null || [ -z "$(grep -oP "^${var}=\K.+" .env 2>/dev/null)" ]; then
        env_missing="$env_missing $var"
    fi
done
if [ -n "$env_missing" ]; then
    err "Missing or empty in .env:$env_missing"
    err "Fill these before rebuilding."
    exit 1
fi
log ".env validated: OK"

# 1d. Check .env.template for new variables
if [ -f ".env.template" ]; then
    new_vars=""
    while IFS= read -r line; do
        var=$(echo "$line" | grep -oP '^\w+(?==)' 2>/dev/null || true)
        if [ -n "$var" ] && ! grep -q "^${var}=" .env 2>/dev/null; then
            new_vars="$new_vars $var"
        fi
    done < .env.template
    if [ -n "$new_vars" ]; then
        warn ".env.template has new variables not in your .env:$new_vars"
        warn "Add them to .env if needed (check .env.template for defaults)."
    fi
fi

# 1e. vm.max_map_count
current_mmc=$(cat /proc/sys/vm/max_map_count 2>/dev/null || echo "0")
if [ "$current_mmc" -lt "$REQUIRED_VM_MAX_MAP_COUNT" ]; then
    if sudo sysctl -w vm.max_map_count=$REQUIRED_VM_MAX_MAP_COUNT >/dev/null 2>&1; then
        log "vm.max_map_count: set to $REQUIRED_VM_MAX_MAP_COUNT"
    else
        err "Cannot set vm.max_map_count. Run: sudo sysctl -w vm.max_map_count=$REQUIRED_VM_MAX_MAP_COUNT"
        exit 1
    fi
else
    log "vm.max_map_count: OK ($current_mmc)"
fi

# ── Phase 2: Stop everything ────────────────────────────────────────────────
step "Phase 2: Stopping all containers"

if compose ps -q 2>/dev/null | grep -q .; then
    compose down 2>&1 | while IFS= read -r line; do echo "  $line"; done
    log "All containers stopped"
else
    log "No containers running (clean start)"
fi

# ── Phase 3: Pre-start repairs ──────────────────────────────────────────────
step "Phase 3: Pre-start repairs"

# 3a. SQLite journal files (Docker bind-mount creates dirs for missing files)
for svc in captain-offline captain-online captain-command; do
    journal="$CAPTAIN_DIR/$svc/journal.sqlite"
    if [ -d "$journal" ]; then
        warn "  $svc/journal.sqlite was a directory (Docker artifact) — removing"
        rm -rf "$journal"
    fi
    if [ ! -f "$journal" ]; then
        touch "$journal"
        log "  Created $svc/journal.sqlite"
    fi
done

# 3b. Redis AOF repair
REDIS_AOF_DIR="$CAPTAIN_DIR/redis"
if [ -d "$REDIS_AOF_DIR" ]; then
    # Look for corrupted AOF files
    aof_files=$(find "$REDIS_AOF_DIR" -name "*.aof" 2>/dev/null || true)
    if [ -n "$aof_files" ] && command -v redis-check-aof >/dev/null 2>&1; then
        while IFS= read -r aof; do
            [ -f "$aof" ] || continue
            if ! redis-check-aof "$aof" >/dev/null 2>&1; then
                warn "  Corrupted AOF detected: $(basename "$aof")"
                if redis-check-aof --fix "$aof" >/dev/null 2>&1; then
                    log "  Repaired: $(basename "$aof")"
                else
                    warn "  Could not repair $(basename "$aof") — will flush Redis"
                fi
            fi
        done <<< "$aof_files"
    fi
fi
log "Pre-start repairs: done"

# 3c. Sync config into build contexts
for svc in captain-offline captain-online captain-command; do
    rm -rf "$CAPTAIN_DIR/$svc/_config"
    cp -r "$CAPTAIN_DIR/config" "$CAPTAIN_DIR/$svc/_config"
done
log "Config synced into build contexts"

# ── Phase 4: Build and start infrastructure ─────────────────────────────────
step "Phase 4: Build images and start infrastructure"

info "Building and starting all containers..."
compose up -d --build 2>&1 | while IFS= read -r line; do echo "  $line"; done
RC=${PIPESTATUS[0]}
if [ "$RC" -ne 0 ]; then
    err "docker compose up --build failed (exit $RC)"
    err "Check: docker compose $COMPOSE_FILES logs --tail 30"
    exit 1
fi

info "Waiting for QuestDB + Redis..."
if ! wait_for_infra; then
    err "Infrastructure not ready. Check logs:"
    err "  docker compose $COMPOSE_FILES logs questdb --tail 20"
    err "  docker compose $COMPOSE_FILES logs redis --tail 20"
    exit 1
fi

# ── Phase 5: Flush Redis ────────────────────────────────────────────────────
step "Phase 5: Flush Redis state"

REDIS_PW=$(grep -oP '^REDIS_PASSWORD=\K.*' "$CAPTAIN_DIR/.env" 2>/dev/null || echo "")
if compose exec -T redis redis-cli ${REDIS_PW:+-a "$REDIS_PW"} FLUSHALL 2>/dev/null | grep -q OK; then
    log "Redis FLUSHALL: OK"
else
    warn "Redis FLUSHALL failed — continuing (may have stale keys)"
fi

# ── Phase 6: Initialize QuestDB tables ──────────────────────────────────────
step "Phase 6: Initialize QuestDB tables"

info "Running init_questdb.py (CREATE IF NOT EXISTS)..."
if compose exec -T -e PYTHONPATH=/app captain-offline \
    python /captain/scripts/init_questdb.py 2>&1 | while IFS= read -r line; do echo "  $line"; done
then
    log "QuestDB table init: complete"
else
    warn "QuestDB table init returned non-zero — checking tables exist..."
    if compose exec -T captain-offline python -c "
import psycopg2, os
conn = psycopg2.connect(host=os.environ.get('QUESTDB_HOST','questdb'), port=int(os.environ.get('QUESTDB_PORT','8812')), user=os.environ.get('QUESTDB_USER','captain'), password=os.environ.get('QUESTDB_PASSWORD',''), dbname='qdb')
conn.autocommit = True; cur = conn.cursor()
cur.execute('SELECT count() FROM p3_d00_asset_universe')
print(f'Tables exist (d00 has {cur.fetchone()[0]} rows)')
cur.close(); conn.close()
" 2>&1; then
        log "QuestDB tables: verified"
    else
        err "QuestDB tables missing and init failed. Check logs."
        exit 1
    fi
fi

# ── Phase 7: Compact state tables ───────────────────────────────────────────
step "Phase 7: Compact QuestDB state tables"

info "Compacting D01, D02, D05, D12, D25..."
if compose exec -T -e PYTHONPATH=/app captain-offline \
    python /captain/scripts/compact_questdb_tables.py 2>&1 | while IFS= read -r line; do echo "  $line"; done
then
    log "Compaction: complete"
else
    warn "Compaction failed (non-fatal — tables may already be compact)"
fi

# ── Phase 8: Bootstrap production data ──────────────────────────────────────
step "Phase 8: Bootstrap production data (idempotent)"

info "Running bootstrap_production.py..."
if compose exec -T -e PYTHONPATH=/app captain-offline \
    python /captain/scripts/bootstrap_production.py 2>&1 | while IFS= read -r line; do echo "  $line"; done
then
    log "Bootstrap: complete"
else
    warn "Bootstrap returned non-zero — check output above"
    warn "This may be OK if data already exists (idempotent guards skip existing rows)"
fi

# ── Phase 9: Update VIX data ────────────────────────────────────────────────
step "Phase 9: Update VIX/VXV data"

if compose exec -T -e PYTHONPATH=/app captain-command \
    python /captain/scripts/update_vix_daily.py 2>&1 | while IFS= read -r line; do echo "  $line"; done
then
    log "VIX/VXV update: complete"
else
    warn "VIX/VXV update failed (non-fatal — stale data still usable)"
fi

# ── Phase 10: Wait for all services ─────────────────────────────────────────
step "Phase 10: Wait for all services"

if ! wait_for_all_services; then
    err "Not all services came up. Check logs:"
    err "  docker compose $COMPOSE_FILES logs --tail 30"
    exit 1
fi

# ── Phase 11: Verify API ────────────────────────────────────────────────────
step "Phase 11: Verify API"
verify_api || true

# ── Phase 12: Final integrity check ─────────────────────────────────────────
step "Phase 12: Data integrity verification"

compose exec -T -e PYTHONPATH=/app captain-offline python -c "
import psycopg2, os, sys
conn = psycopg2.connect(host=os.environ.get('QUESTDB_HOST','questdb'), port=int(os.environ.get('QUESTDB_PORT','8812')), user=os.environ.get('QUESTDB_USER','captain'), password=os.environ.get('QUESTDB_PASSWORD',''), dbname='qdb')
conn.autocommit = True
cur = conn.cursor()
tables = {
    'p3_d00_asset_universe': 10,
    'p3_d01_aim_model_states': 50,
    'p3_d02_aim_meta_weights': 50,
    'p3_d05_ewma_states': 10,
    'p3_d12_kelly_parameters': 10,
    'p3_d16_user_capital_silos': 1,
    'p3_d25_circuit_breaker_params': 1,
}
failed = []
for t, need in tables.items():
    try:
        cur.execute(f'SELECT count() FROM {t}')
        n = cur.fetchone()[0]
        status = 'OK' if n >= need else 'LOW'
        print(f'  {t}: {n} rows ({status})')
        if n < need:
            failed.append(f'{t}: {n} < {need}')
    except Exception as e:
        print(f'  {t}: MISSING ({e})')
        failed.append(f'{t}: MISSING')
cur.close(); conn.close()
if failed:
    print(f'INTEGRITY_FAIL: {len(failed)} table(s) below threshold')
    sys.exit(1)
else:
    print('INTEGRITY_OK: all tables have sufficient data')
" 2>&1 | while IFS= read -r line; do echo "  $line"; done

if [ "${PIPESTATUS[0]}" -ne 0 ]; then
    err ""
    err "DATA INTEGRITY CHECK FAILED — some tables are below minimum row counts."
    err "The system is running but may not trade correctly."
    err "Check the output above and re-run bootstrap if needed:"
    err "  docker compose $COMPOSE_FILES exec captain-offline python /captain/scripts/bootstrap_production.py"
    err ""
else
    log "Data integrity: PASS"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}══════════════════════════════════════════════════════════${NC}"
log "  Captain System rebuild COMPLETE"
log "  GUI:    http://localhost"
log "  API:    http://localhost/api/health"
log "  QDB:    http://localhost:9000"
log "  Time:   $(TZ=America/New_York date '+%H:%M:%S %Z')"
echo -e "${BOLD}══════════════════════════════════════════════════════════${NC}"
echo ""
info "Quick commands:"
info "  Status:    bash captain-rebuild.sh --status"
info "  Compact:   bash captain-rebuild.sh --compact"
info "  Logs:      docker compose $COMPOSE_FILES logs -f [service]"
info "  Stop:      bash captain-stop.sh"
info "  Light start: bash captain-start.sh"
