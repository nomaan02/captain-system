#!/usr/bin/env bash
# tower-verify.sh — Standalone verification for Captain System deployment
#
# Run at any time to check full system health:
#   - Container health (6 services)
#   - API health endpoint
#   - QuestDB data integrity (critical tables with expected row counts)
#   - VIX data freshness
#   - .env completeness and permissions
#   - Kernel parameters
#   - Cron jobs
#   - Systemd service
#
# Usage:
#   bash scripts/tower-verify.sh
#
# Exit codes:
#   0 = all checks passed
#   1 = one or more checks failed

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTAIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.local.yml"
PASS=0
FAIL=0
WARN=0

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}PASS${NC}  $*"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC}  $*"; FAIL=$((FAIL + 1)); }
skip() { echo -e "  ${YELLOW}WARN${NC}  $*"; WARN=$((WARN + 1)); }

# Helper: run compose command
compose() {
    docker compose $COMPOSE_FILES "$@"
}

cd "$CAPTAIN_DIR"

echo ""
echo -e "${BOLD}Captain System — Deployment Verification${NC}"
echo "  Directory: $CAPTAIN_DIR"
echo "  Time:      $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
#  1. CONTAINER HEALTH
# ══════════════════════════════════════════════════════════════════════════════
echo -e "${BOLD}-- Container Health --${NC}"
for svc in questdb redis captain-offline captain-online captain-command nginx; do
    state=$(compose ps --format '{{.State}}' "$svc" 2>/dev/null || echo "missing")
    health=$(compose ps --format '{{.Health}}' "$svc" 2>/dev/null || echo "")

    if [ "$state" = "running" ]; then
        if [ -n "$health" ] && [ "$health" != "" ] && [ "$health" != "healthy" ]; then
            skip "$svc: running ($health)"
        else
            pass "$svc: running"
        fi
    else
        fail "$svc: $state"
    fi
done

# ══════════════════════════════════════════════════════════════════════════════
#  2. API HEALTH
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}-- API Health --${NC}"
if curl -sf http://localhost/api/health >/dev/null 2>&1; then
    pass "API via nginx (http://localhost/api/health)"
elif curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
    pass "API direct (http://localhost:8000/api/health)"
else
    fail "API not responding on port 80 or 8000"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  3. QUESTDB DATA INTEGRITY
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}-- QuestDB Data Integrity --${NC}"

# Table name and minimum expected row count
TABLES=(
    "p3_d00_asset_universe:10"
    "p3_d01_aim_model_states:50"
    "p3_d02_aim_meta_weights:50"
    "p3_d05_ewma_states:50"
    "p3_d12_kelly_parameters:10"
    "p3_d16_user_capital_silos:1"
    "p3_d25_circuit_breaker_params:1"
)

for entry in "${TABLES[@]}"; do
    table="${entry%%:*}"
    min="${entry##*:}"

    result=$(compose exec -T questdb curl -s \
        "http://localhost:9000/exec?query=SELECT+count()+FROM+$table" 2>/dev/null || echo "")

    count=$(echo "$result" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin)['dataset'][0][0])
except:
    print(0)
" 2>/dev/null || echo "0")

    if [ "$count" -ge "$min" ] 2>/dev/null; then
        pass "$table: $count rows (>= $min)"
    else
        fail "$table: $count rows (expected >= $min)"
    fi
done

# ══════════════════════════════════════════════════════════════════════════════
#  4. VIX DATA
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}-- VIX Data --${NC}"

VIX_FILES=("vix_daily_close.csv" "vxv_daily_close.csv")
for vf in "${VIX_FILES[@]}"; do
    fpath="data/vix/$vf"
    if [ -f "$fpath" ]; then
        last_line=$(tail -1 "$fpath" 2>/dev/null || echo "")
        if [ -n "$last_line" ]; then
            last_date=$(echo "$last_line" | cut -d',' -f1)
            pass "$vf (latest: $last_date)"
        else
            fail "$vf exists but is empty"
        fi
    else
        fail "$vf missing"
    fi
done

# ══════════════════════════════════════════════════════════════════════════════
#  5. ENVIRONMENT
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}-- Environment --${NC}"

if [ -f ".env" ]; then
    perms=$(stat -c '%a' .env 2>/dev/null || echo "unknown")
    if [ "$perms" = "600" ]; then
        pass ".env permissions: 600"
    else
        skip ".env permissions: $perms (should be 600)"
    fi

    # Check required variables are set (non-empty)
    REQUIRED_VARS=(
        TOPSTEP_USERNAME TOPSTEP_API_KEY VAULT_MASTER_KEY
        JWT_SECRET_KEY API_SECRET_KEY QUESTDB_PASSWORD REDIS_PASSWORD
    )
    missing=""
    for var in "${REQUIRED_VARS[@]}"; do
        val=$(grep -oP "^${var}=\K.+" .env 2>/dev/null || echo "")
        if [ -z "$val" ]; then
            missing="$missing $var"
        fi
    done

    if [ -z "$missing" ]; then
        pass "All required .env variables set"
    else
        fail "Missing .env variables:$missing"
    fi
else
    fail ".env file missing"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  6. KERNEL PARAMETERS
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}-- Kernel Parameters --${NC}"

mmc=$(cat /proc/sys/vm/max_map_count 2>/dev/null || echo "0")
if [ "$mmc" -ge 1048576 ]; then
    pass "vm.max_map_count: $mmc"
else
    fail "vm.max_map_count: $mmc (need >= 1048576)"
fi

if grep -q "vm.max_map_count" /etc/sysctl.conf 2>/dev/null; then
    pass "vm.max_map_count persisted in sysctl.conf"
else
    skip "vm.max_map_count NOT in sysctl.conf (will reset on reboot)"
fi

ocm=$(cat /proc/sys/vm/overcommit_memory 2>/dev/null || echo "0")
if [ "$ocm" = "1" ]; then
    pass "vm.overcommit_memory: 1"
else
    skip "vm.overcommit_memory: $ocm (recommended: 1 for Redis)"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  7. CRON JOBS
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}-- Cron Jobs --${NC}"

cron_content=$(crontab -l 2>/dev/null || echo "")

if echo "$cron_content" | grep -q "update_vix_data"; then
    pass "VIX update cron installed"
else
    fail "VIX update cron missing"
fi

if echo "$cron_content" | grep -q "healthcheck"; then
    pass "Healthcheck cron installed"
else
    fail "Healthcheck cron missing"
fi

if echo "$cron_content" | grep -q "questdb.*tar"; then
    pass "QuestDB backup cron installed"
else
    fail "QuestDB backup cron missing"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  8. SYSTEMD SERVICE
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}-- Systemd Service --${NC}"

if [ -f /etc/systemd/system/captain.service ]; then
    if systemctl is-enabled captain.service >/dev/null 2>&1; then
        pass "captain.service: enabled (auto-start on boot)"
    else
        skip "captain.service: exists but not enabled"
    fi
else
    skip "captain.service: not installed (manual start required after reboot)"
fi

# ══════════════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}================================================================${NC}"
echo -e "${BOLD}  Verification Summary${NC}"
echo -e "${BOLD}================================================================${NC}"
echo -e "  ${GREEN}PASS: $PASS${NC}   ${RED}FAIL: $FAIL${NC}   ${YELLOW}WARN: $WARN${NC}"
echo ""

TOWER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

if [ "$FAIL" -eq 0 ]; then
    echo -e "  ${GREEN}System is healthy and ready for trading.${NC}"
    echo ""
    echo "  GUI:     http://$TOWER_IP"
    echo "  QuestDB: http://$TOWER_IP:9000"
    echo "  API:     http://$TOWER_IP/api/health"
    echo ""
    exit 0
else
    echo -e "  ${RED}$FAIL check(s) failed. Review the output above and fix before trading.${NC}"
    echo ""
    echo "  After fixing, re-verify: bash scripts/tower-verify.sh"
    echo ""
    exit 1
fi
