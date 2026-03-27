#!/bin/bash
# ================================================================
# Captain System — Push Code Updates to VPS
# Syncs local changes and rebuilds containers.
#
# Usage:
#   ./deploy/update.sh <VPS_IP>           # Update one VPS
#   ./deploy/update.sh all                # Update both (set IPs below)
# ================================================================
set -euo pipefail

# ── Configure your VPS IPs here after provisioning ──
NOMAAN_IP="${CAPTAIN_NOMAAN_IP:-}"
ISAAC_IP="${CAPTAIN_ISAAC_IP:-}"

REMOTE_USER=captain
REMOTE_DIR=/home/captain/captain-system

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

update_vps() {
    local VPS_IP="$1"
    echo ""
    echo "=== Updating ${VPS_IP} ==="

    rsync -avz --progress \
        --exclude '.git' \
        --exclude '__pycache__' \
        --exclude '*.pyc' \
        --exclude '.env' \
        --exclude '.env.*' \
        --exclude 'questdb/db' \
        --exclude 'redis' \
        --exclude 'journal.sqlite' \
        --exclude 'deploy/' \
        --exclude 'node_modules' \
        --exclude '.env.template' \
        "${PROJECT_DIR}/" "${REMOTE_USER}@${VPS_IP}:${REMOTE_DIR}/"

    echo "→ Rebuilding changed containers..."
    ssh "${REMOTE_USER}@${VPS_IP}" "cd ${REMOTE_DIR} && docker compose up -d --build"

    echo "→ Status:"
    ssh "${REMOTE_USER}@${VPS_IP}" "cd ${REMOTE_DIR} && docker compose ps"

    echo "=== ${VPS_IP} updated ==="
}

if [ $# -lt 1 ]; then
    echo "Usage: $0 <VPS_IP|all>"
    echo ""
    echo "  $0 1.2.3.4       Update one VPS"
    echo "  $0 all            Update both (set CAPTAIN_NOMAAN_IP and CAPTAIN_ISAAC_IP)"
    exit 1
fi

if [ "$1" = "all" ]; then
    if [ -z "$NOMAAN_IP" ] || [ -z "$ISAAC_IP" ]; then
        echo "ERROR: Set CAPTAIN_NOMAAN_IP and CAPTAIN_ISAAC_IP env vars, or edit this script."
        exit 1
    fi
    update_vps "$NOMAAN_IP"
    update_vps "$ISAAC_IP"
else
    update_vps "$1"
fi
