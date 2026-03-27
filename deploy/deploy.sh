#!/bin/bash
# ================================================================
# Captain System — Deploy to VPS
# Syncs captain-system code and starts all containers.
#
# Usage:
#   ./deploy/deploy.sh <VPS_IP> <ENV_FILE>
#   ./deploy/deploy.sh 1.2.3.4 .env.nomaan
#   ./deploy/deploy.sh 5.6.7.8 .env.isaac
# ================================================================
set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: $0 <VPS_IP> <ENV_FILE>"
    echo "  Example: $0 1.2.3.4 .env.nomaan"
    exit 1
fi

VPS_IP="$1"
ENV_FILE="$2"
REMOTE_USER=captain
REMOTE_DIR=/home/captain/captain-system

# Resolve script location to find captain-system root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ ! -f "$ENV_FILE" ] && [ -f "$PROJECT_DIR/$ENV_FILE" ]; then
    ENV_FILE="$PROJECT_DIR/$ENV_FILE"
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Environment file not found: $ENV_FILE"
    exit 1
fi

echo "=== Captain Deploy ==="
echo "  Target:  ${REMOTE_USER}@${VPS_IP}"
echo "  Env:     ${ENV_FILE}"
echo "  Source:  ${PROJECT_DIR}"
echo ""

# 1. Sync code
echo "→ Syncing captain-system..."
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

# 2. Copy environment file
echo "→ Copying environment file..."
scp "${ENV_FILE}" "${REMOTE_USER}@${VPS_IP}:${REMOTE_DIR}/.env"

# 3. Generate vault master key if not already set
echo "→ Checking VAULT_MASTER_KEY..."
if ! ssh "${REMOTE_USER}@${VPS_IP}" "grep -q 'VAULT_MASTER_KEY=.\+' ${REMOTE_DIR}/.env"; then
    echo "  WARNING: VAULT_MASTER_KEY is empty in .env"
    echo "  Generating one now..."
    KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    ssh "${REMOTE_USER}@${VPS_IP}" "sed -i 's|^VAULT_MASTER_KEY=.*|VAULT_MASTER_KEY=${KEY}|' ${REMOTE_DIR}/.env"
    echo "  VAULT_MASTER_KEY=${KEY}"
    echo "  SAVE THIS KEY — you need it to decrypt vault data."
fi

# 4. Create required directories
echo "→ Creating directories..."
ssh "${REMOTE_USER}@${VPS_IP}" "mkdir -p ${REMOTE_DIR}/questdb/db ${REMOTE_DIR}/redis ${REMOTE_DIR}/logs ${REMOTE_DIR}/vault"

# 5. Build and start
echo "→ Building containers (this takes a few minutes first time)..."
ssh "${REMOTE_USER}@${VPS_IP}" "cd ${REMOTE_DIR} && docker compose build --parallel"

echo "→ Starting containers..."
ssh "${REMOTE_USER}@${VPS_IP}" "cd ${REMOTE_DIR} && docker compose up -d"

# 6. Wait for health checks
echo "→ Waiting for services to stabilize (30s)..."
sleep 30

# 7. Show status
echo ""
echo "=== Container Status ==="
ssh "${REMOTE_USER}@${VPS_IP}" "cd ${REMOTE_DIR} && docker compose ps"

echo ""
echo "=== Quick Log Check ==="
for svc in captain-offline captain-online captain-command; do
    echo "--- ${svc} (last 3 lines) ---"
    ssh "${REMOTE_USER}@${VPS_IP}" "cd ${REMOTE_DIR} && docker compose logs --tail=3 ${svc} 2>/dev/null" || true
done

echo ""
echo "============================================"
echo "  Deployment complete: ${VPS_IP}"
echo "  GUI: https://${VPS_IP}"
echo "  API: https://${VPS_IP}/api/"
echo "============================================"
