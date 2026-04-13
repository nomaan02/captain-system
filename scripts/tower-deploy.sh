#!/usr/bin/env bash
# tower-deploy.sh — Automated deployment for Captain System on a Linux tower
#
# Reproduces the entire TOWER_DEPLOYMENT_GUIDE.md flow automatically:
#   Phase 1: System prerequisites (Docker, kernel params, directories)
#   Phase 2: Transfer bundle extraction
#   Phase 3: Environment (.env) setup with secret generation
#   Phase 4: Container build & launch (delegates to captain-start.sh)
#   Phase 5: Database bootstrap (conditional — skipped if data exists)
#   Phase 6: Automation (cron, healthcheck, systemd auto-start)
#   Phase 7: Final verification
#
# Usage:
#   bash scripts/tower-deploy.sh                  # Full deployment
#   bash scripts/tower-deploy.sh --from-phase 5   # Resume from phase 5
#   bash scripts/tower-deploy.sh --verify-only    # Just run verification
#
# Paths auto-detect from $HOME. No hardcoded usernames.

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTAIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.local.yml"
HOME_DIR="$HOME"
CURRENT_USER="$(whoami)"

# Bundle locations (placed in $HOME by file transfer)
SMALL_BUNDLE="$HOME_DIR/captain-transfer-small.tar.gz"
QDB_BUNDLE="$HOME_DIR/captain-transfer-questdb.tar.gz"

# Timeouts
INFRA_TIMEOUT=120
HEALTH_INTERVAL=5

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()    { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()   { echo -e "${YELLOW}[deploy]${NC} $*"; }
err()    { echo -e "${RED}[deploy]${NC} $*" >&2; }
info()   { echo -e "${CYAN}[deploy]${NC} $*"; }
header() {
    echo ""
    echo -e "${BOLD}================================================================${NC}"
    echo -e "${BOLD}  Phase $1: $2${NC}"
    echo -e "${BOLD}================================================================${NC}"
    echo ""
}

# ── Argument parsing ───────────────────────────────────────────────────────────
FROM_PHASE=1
VERIFY_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --from-phase)
            FROM_PHASE="${2:-1}"
            shift 2
            ;;
        --from-phase=*)
            FROM_PHASE="${1#*=}"
            shift
            ;;
        --verify-only)
            VERIFY_ONLY=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

if $VERIFY_ONLY; then
    exec bash "$SCRIPT_DIR/tower-verify.sh"
fi

cd "$CAPTAIN_DIR"

echo -e "\n${BOLD}Captain System — Tower Deployment${NC}"
echo "  User:      $CURRENT_USER"
echo "  Home:      $HOME_DIR"
echo "  Project:   $CAPTAIN_DIR"
echo "  Starting:  Phase $FROM_PHASE"
echo "  Time:      $(date '+%Y-%m-%d %H:%M:%S %Z')"

# Helper: run a compose command from the project directory
compose() {
    docker compose $COMPOSE_FILES "$@"
}

# Helper: run a python snippet inside captain-offline container
run_in_offline() {
    compose exec -T -e PYTHONPATH=/app captain-offline python "$@"
}

# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 1: SYSTEM PREREQUISITES
# ══════════════════════════════════════════════════════════════════════════════
if [ "$FROM_PHASE" -le 1 ]; then
    header 1 "System Prerequisites"

    # ── Required commands ──────────────────────────────────────────────────
    MISSING_CMDS=""
    for cmd in docker curl git python3 sudo; do
        if command -v "$cmd" &>/dev/null; then
            log "  $cmd: found"
        else
            MISSING_CMDS="$MISSING_CMDS $cmd"
            err "  $cmd: NOT FOUND"
        fi
    done

    if [ -n "$MISSING_CMDS" ]; then
        err ""
        err "Missing required commands:$MISSING_CMDS"
        err "Install them first: sudo apt update && sudo apt install -y docker.io curl git python3"
        exit 1
    fi

    # ── Docker Compose V2 ─────────────────────────────────────────────────
    if docker compose version &>/dev/null; then
        log "  Docker Compose V2: OK"
    else
        err "Docker Compose V2 not available."
        err "If using Docker Engine (not Desktop), install the compose plugin:"
        err "  sudo apt install docker-compose-plugin"
        exit 1
    fi

    # ── Docker daemon ─────────────────────────────────────────────────────
    if docker info >/dev/null 2>&1; then
        log "  Docker daemon: running"
    else
        warn "Docker daemon not running. Starting..."
        if sudo systemctl start docker 2>/dev/null; then
            log "  Docker daemon: started"
        else
            err "Cannot start Docker. Run: sudo systemctl start docker"
            exit 1
        fi
    fi

    # ── Kernel: vm.max_map_count (QuestDB requirement) ────────────────────
    REQUIRED_MMC=1048576
    current_mmc=$(cat /proc/sys/vm/max_map_count 2>/dev/null || echo "0")
    if [ "$current_mmc" -lt "$REQUIRED_MMC" ]; then
        info "Setting vm.max_map_count=$REQUIRED_MMC (QuestDB requirement)..."
        sudo sysctl -w vm.max_map_count=$REQUIRED_MMC >/dev/null 2>&1

        if ! grep -q "vm.max_map_count" /etc/sysctl.conf 2>/dev/null; then
            echo "vm.max_map_count=$REQUIRED_MMC" | sudo tee -a /etc/sysctl.conf >/dev/null
            log "  vm.max_map_count: set and persisted in /etc/sysctl.conf"
        else
            log "  vm.max_map_count: set (already persisted)"
        fi
    else
        log "  vm.max_map_count: OK ($current_mmc)"
    fi

    # ── Kernel: vm.overcommit_memory (Redis recommendation) ───────────────
    current_ocm=$(cat /proc/sys/vm/overcommit_memory 2>/dev/null || echo "0")
    if [ "$current_ocm" != "1" ]; then
        info "Setting vm.overcommit_memory=1 (Redis recommendation)..."
        sudo sysctl -w vm.overcommit_memory=1 >/dev/null 2>&1

        if ! grep -q "vm.overcommit_memory" /etc/sysctl.conf 2>/dev/null; then
            echo "vm.overcommit_memory=1" | sudo tee -a /etc/sysctl.conf >/dev/null
            log "  vm.overcommit_memory: set and persisted"
        fi
    else
        log "  vm.overcommit_memory: OK"
    fi

    # ── Required directories ──────────────────────────────────────────────
    mkdir -p questdb/db redis logs logs/incidents logs/crash_reports backups/questdb vault
    mkdir -p "$HOME_DIR/backups"
    log "  Directories: created"

    # ── SQLite journal files (must exist as FILES before Docker bind-mount) ─
    # Docker bind-mount of a non-existent path creates a directory, which
    # SQLite can't open. The *.sqlite files are gitignored, so fresh clones
    # don't have them.
    for svc in captain-offline captain-online captain-command; do
        journal="$CAPTAIN_DIR/$svc/journal.sqlite"
        if [ ! -f "$journal" ]; then
            touch "$journal"
        fi
    done
    log "  Journal files: ensured"

    log "Phase 1 complete."
fi


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 2: TRANSFER BUNDLE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════
if [ "$FROM_PHASE" -le 2 ]; then
    header 2 "Transfer Bundle Extraction"

    small_found=false
    qdb_found=false

    [ -f "$SMALL_BUNDLE" ] && small_found=true
    [ -f "$QDB_BUNDLE" ]   && qdb_found=true

    if $small_found; then
        info "Found: $SMALL_BUNDLE ($(du -h "$SMALL_BUNDLE" | cut -f1))"
    fi
    if $qdb_found; then
        info "Found: $QDB_BUNDLE ($(du -h "$QDB_BUNDLE" | cut -f1))"
    fi

    # ── No bundles? ───────────────────────────────────────────────────────
    if ! $small_found && ! $qdb_found; then
        warn "No transfer bundles found at:"
        warn "  $SMALL_BUNDLE"
        warn "  $QDB_BUNDLE"
        echo ""
        echo "These bundles are pre-built on the development laptop at:"
        echo "  Windows: \\\\wsl.localhost\\Ubuntu\\home\\nomaan\\captain-transfer-small.tar.gz"
        echo "  Windows: \\\\wsl.localhost\\Ubuntu\\home\\nomaan\\captain-transfer-questdb.tar.gz"
        echo ""
        echo "Transfer them to $HOME_DIR/ via AnyDesk file transfer or SCP, then re-run."
        echo ""
        echo -n "Or continue without bundles? (will bootstrap QuestDB from scratch) (y/N): "
        read -r answer
        if [[ ! "$answer" =~ ^[yY] ]]; then
            info "Transfer the bundles, then re-run:"
            info "  bash scripts/tower-deploy.sh --from-phase 2"
            exit 0
        fi
        warn "Continuing without bundles. Phase 5 will bootstrap from scratch."
    fi

    # ── Extract small bundle (VIX, macro, certs — NOT .env) ───────────────
    if $small_found; then
        info "Extracting small bundle (VIX data, macro data, TLS certs)..."
        # Extract everything except .env — .env is handled in Phase 3
        # (the bundle may contain another user's credentials)
        tar xzf "$SMALL_BUNDLE" --exclude='.env' 2>/dev/null || {
            # Older tar may not support --exclude; extract all then handle .env in Phase 3
            warn "  --exclude not supported; extracting all files"
            tar xzf "$SMALL_BUNDLE" 2>/dev/null
        }

        # Report what was extracted
        [ -d "data/vix" ]     && log "  data/vix/: $(ls data/vix/ 2>/dev/null | wc -l) files"
        [ -d "data/macro" ]   && log "  data/macro/: present"
        [ -d "nginx/certs" ]  && log "  nginx/certs/: present"
        log "  Small bundle extracted."
    fi

    # ── Extract QuestDB bundle ────────────────────────────────────────────
    if $qdb_found; then
        info "Extracting QuestDB bundle (may require sudo for file ownership)..."

        # Back up existing QuestDB data if present
        if [ -d "questdb/db" ] && [ "$(ls -A questdb/db 2>/dev/null)" ]; then
            warn "  Existing questdb/db/ found — backing up first..."
            mkdir -p backups/questdb
            tar czf "backups/questdb/questdb-pre-deploy-$(date '+%Y%m%d-%H%M%S').tar.gz" \
                questdb/db/ 2>/dev/null || true
            log "  Existing data backed up."
        fi

        sudo rm -rf questdb/db
        sudo tar xzf "$QDB_BUNDLE"
        log "  QuestDB bundle extracted ($(sudo du -sh questdb/db/ 2>/dev/null | cut -f1))"
    fi

    log "Phase 2 complete."
fi


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 3: ENVIRONMENT SETUP (.env)
# ══════════════════════════════════════════════════════════════════════════════
if [ "$FROM_PHASE" -le 3 ]; then
    header 3 "Environment Setup"

    create_env=false

    if [ -f ".env" ]; then
        warn ".env already exists."
        warn "(If this came from a transfer bundle, it may contain another user's credentials.)"
        echo -n "Create fresh .env for this tower? (Y/n): "
        read -r answer
        if [[ "$answer" =~ ^[nN] ]]; then
            log "Keeping existing .env."
        else
            create_env=true
        fi
    else
        create_env=true
    fi

    if $create_env; then
        info "Collecting credentials..."
        echo ""

        echo "TopstepX email (userName):"
        read -r INPUT_USERNAME
        [ -z "$INPUT_USERNAME" ] && { err "Username required."; exit 1; }

        echo "TopstepX API key:"
        read -rs INPUT_API_KEY
        echo "(hidden)"
        [ -z "$INPUT_API_KEY" ] && { err "API key required."; exit 1; }

        echo "TopstepX account name (e.g. 150KTC-V2-551001-19064435):"
        read -r INPUT_ACCOUNT_NAME
        [ -z "$INPUT_ACCOUNT_NAME" ] && { err "Account name required."; exit 1; }

        echo "TopstepX account ID (numeric, from dashboard):"
        read -r INPUT_ACCOUNT_ID
        [ -z "$INPUT_ACCOUNT_ID" ] && { err "Account ID required."; exit 1; }

        echo "Starting capital (default: 150000):"
        read -r INPUT_CAPITAL
        INPUT_CAPITAL="${INPUT_CAPITAL:-150000}"

        echo "Trading environment — PAPER or LIVE (default: PAPER):"
        read -r INPUT_TRADE_ENV
        INPUT_TRADE_ENV="${INPUT_TRADE_ENV:-PAPER}"

        echo "Auto-execute signals? true/false (default: false):"
        read -r INPUT_AUTO_EXEC
        INPUT_AUTO_EXEC="${INPUT_AUTO_EXEC:-false}"

        echo ""
        echo "Multi-instance parity (for dual-account trade splitting):"
        echo "  0 = take odd signals (1st, 3rd, 5th...)"
        echo "  1 = take even signals (2nd, 4th, 6th...)"
        echo "  [blank] = take all signals (single instance)"
        echo "Enter parity (0, 1, or blank):"
        read -r INPUT_PARITY

        echo ""
        echo "Telegram Bot Token (optional — press Enter to skip):"
        read -r INPUT_TG_TOKEN
        INPUT_TG_CHAT=""
        if [ -n "$INPUT_TG_TOKEN" ]; then
            echo "Telegram Chat ID:"
            read -r INPUT_TG_CHAT
        fi

        # ── Generate all cryptographic secrets ────────────────────────────
        info "Generating cryptographic secrets..."
        GEN_VAULT=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
        GEN_JWT=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        GEN_API=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
        GEN_QDB=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
        GEN_REDIS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

        # ── Write .env ────────────────────────────────────────────────────
        cat > .env << ENVEOF
# Captain System — Generated by tower-deploy.sh
# Machine: $(hostname) | User: $CURRENT_USER | Date: $(date '+%Y-%m-%d %H:%M:%S')

# ── TOPSTEP AUTHENTICATION ──────────────────────────────────────
TOPSTEP_USERNAME=${INPUT_USERNAME}
TOPSTEP_API_KEY=${INPUT_API_KEY}
TOPSTEP_ACCOUNT_NAME=${INPUT_ACCOUNT_NAME}
TRADING_ENVIRONMENT=${INPUT_TRADE_ENV}
AUTO_EXECUTE=${INPUT_AUTO_EXEC}

# ── MULTI-INSTANCE TRADE ALTERNATION ───────────────────────────
INSTANCE_PARITY=${INPUT_PARITY}

# ── VAULT ENCRYPTION ───────────────────────────────────────────
VAULT_MASTER_KEY=${GEN_VAULT}

# ── BOOTSTRAP CONFIG ───────────────────────────────────────────
BOOTSTRAP_ACCOUNT_ID=${INPUT_ACCOUNT_ID}
BOOTSTRAP_USER_ID=primary_user
BOOTSTRAP_STARTING_CAPITAL=${INPUT_CAPITAL}

# ── TELEGRAM NOTIFICATIONS ─────────────────────────────────────
TELEGRAM_BOT_TOKEN=${INPUT_TG_TOKEN}
TELEGRAM_CHAT_ID=${INPUT_TG_CHAT}

# ── JWT AUTHENTICATION ─────────────────────────────────────────
JWT_SECRET_KEY=${GEN_JWT}
API_SECRET_KEY=${GEN_API}
JWT_EXPIRY_HOURS=24

# ── QUESTDB AUTHENTICATION ─────────────────────────────────────
QUESTDB_USER=captain
QUESTDB_PASSWORD=${GEN_QDB}

# ── REDIS AUTHENTICATION ───────────────────────────────────────
REDIS_PASSWORD=${GEN_REDIS}
ENVEOF

        chmod 600 .env
        log ".env created (permissions: 600)"

        echo ""
        warn "======================================================="
        warn "  SAVE YOUR VAULT_MASTER_KEY — losing it means all"
        warn "  encrypted vault data becomes unrecoverable:"
        warn ""
        warn "  ${GEN_VAULT}"
        warn "======================================================="
        echo ""
    fi

    # ── Validate .env completeness ────────────────────────────────────────
    info "Validating .env..."
    MISSING_VARS=""
    for var in TOPSTEP_USERNAME TOPSTEP_API_KEY VAULT_MASTER_KEY JWT_SECRET_KEY \
               API_SECRET_KEY QUESTDB_PASSWORD REDIS_PASSWORD; do
        val=$(grep -oP "^${var}=\K.+" .env 2>/dev/null || echo "")
        if [ -z "$val" ]; then
            MISSING_VARS="$MISSING_VARS $var"
        fi
    done

    if [ -n "$MISSING_VARS" ]; then
        err "Missing required .env variables:$MISSING_VARS"
        err "Edit .env manually or re-run this phase:"
        err "  bash scripts/tower-deploy.sh --from-phase 3"
        exit 1
    fi
    log ".env validated — all required variables present."

    log "Phase 3 complete."
fi


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 4: BUILD & LAUNCH CONTAINERS
# ══════════════════════════════════════════════════════════════════════════════
if [ "$FROM_PHASE" -le 4 ]; then
    header 4 "Build & Launch Containers"

    # Delegate to captain-start.sh which handles:
    #   - QuestDB backup, config sync, Docker build
    #   - Infrastructure readiness (QuestDB + Redis)
    #   - Table init (CREATE IF NOT EXISTS)
    #   - Data integrity check
    #   - VIX/VXV update
    #   - Service health check
    info "Running captain-start.sh --build ..."
    info "(First build takes ~5 minutes — downloads images, compiles deps, builds GUI)"
    echo ""

    # Export CAPTAIN_DIR so captain-start.sh uses the right path
    export CAPTAIN_DIR="$CAPTAIN_DIR"

    if bash "$CAPTAIN_DIR/captain-start.sh" --build; then
        log "Phase 4 complete — containers launched."
    else
        RC=$?
        err ""
        err "captain-start.sh exited with code $RC."
        err "Check the output above for specific errors."
        err ""
        err "Common fixes:"
        err "  Port conflict:  sudo lsof -i :9000   (then stop the other process)"
        err "  Docker issue:   docker info           (check daemon is running)"
        err "  Memory:         free -h               (need >= 4 GB free)"
        err ""
        err "After fixing, resume: bash scripts/tower-deploy.sh --from-phase 4"
        exit 1
    fi
fi


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 5: DATABASE BOOTSTRAP (conditional)
# ══════════════════════════════════════════════════════════════════════════════
if [ "$FROM_PHASE" -le 5 ]; then
    header 5 "Database Bootstrap"

    # Guard: containers must be running (needed when resuming with --from-phase 5)
    if ! docker info >/dev/null 2>&1; then
        err "Docker daemon not running. Start Docker first."
        exit 1
    fi
    if ! compose ps --status running 2>/dev/null | grep -q "captain-offline"; then
        err "captain-offline container not running."
        err "Start containers first: bash captain-start.sh"
        err "Then resume: bash scripts/tower-deploy.sh --from-phase 5"
        exit 1
    fi

    info "Checking data integrity to determine if bootstrap is needed..."

    # Run integrity check inside the container
    INTEGRITY_RESULT=$(compose exec -T -e PYTHONPATH=/app captain-offline python -c "
import psycopg2, os, sys
conn = psycopg2.connect(
    host=os.environ.get('QUESTDB_HOST','questdb'),
    port=int(os.environ.get('QUESTDB_PORT','8812')),
    user=os.environ.get('QUESTDB_USER','captain'), password=os.environ.get('QUESTDB_PASSWORD',''), dbname='qdb'
)
conn.autocommit = True
cur = conn.cursor()
critical = {
    'p3_d00_asset_universe': 10,
    'p3_d01_aim_model_states': 50,
    'p3_d02_aim_meta_weights': 50,
    'p3_d12_kelly_parameters': 10,
    'p3_d16_user_capital_silos': 1
}
ok = True
for table, min_rows in critical.items():
    try:
        cur.execute(f'SELECT count() FROM {table}')
        count = cur.fetchone()[0]
        status = 'OK' if count >= min_rows else 'LOW'
        if count < min_rows:
            ok = False
        print(f'  {status}: {table} = {count} rows (need >= {min_rows})')
    except Exception as e:
        print(f'  MISSING: {table} ({e})')
        ok = False
cur.close(); conn.close()
print('INTEGRITY_OK' if ok else 'INTEGRITY_FAIL')
" 2>&1) || true

    echo "$INTEGRITY_RESULT"

    if echo "$INTEGRITY_RESULT" | grep -q "INTEGRITY_OK"; then
        log "Data integrity OK — QuestDB has valid data (likely from transfer bundle)."
        log "Skipping bootstrap."
    else
        warn "Data integrity check failed — running full bootstrap from scratch."
        echo ""

        # ── Schema fixes (required before bootstrap) ─────────────────────
        info "Applying schema fixes (l_star, cold_start columns)..."
        for query in \
            "ALTER+TABLE+p3_d25_circuit_breaker_params+ADD+COLUMN+l_star+DOUBLE" \
            "ALTER+TABLE+p3_d25_circuit_breaker_params+ADD+COLUMN+cold_start+BOOLEAN"; do
            result=$(compose exec -T questdb curl -s "http://localhost:9000/exec?query=$query" 2>/dev/null || echo "{}")
            if echo "$result" | grep -q '"ddl":"OK"'; then
                log "  Column added."
            elif echo "$result" | grep -q "duplicate column"; then
                log "  Column already exists (OK)."
            else
                warn "  Unexpected response: $result"
            fi
        done

        # ── Step 1: Seed all assets (D00, D01, D05, D12) ────────────────
        info "Seeding assets (D00 base rows, D01 AIM states, D05 EWMA, D12 Kelly)..."
        if run_in_offline /captain/scripts/seed_all_assets.py 2>&1 | \
            tail -5 | while IFS= read -r line; do echo "  $line"; done; then
            log "  Asset seeding: complete"
        else
            err "  seed_all_assets.py failed. Check container logs."
            err "  Resume after fixing: bash scripts/tower-deploy.sh --from-phase 5"
            exit 1
        fi

        # ── Step 2: Bootstrap production config (D00 strategies, D02, D16, D25)
        info "Bootstrapping production config..."
        BOOT_ACCOUNT=$(grep -oP '^BOOTSTRAP_ACCOUNT_ID=\K.+' .env 2>/dev/null || echo "20319811")
        BOOT_USER=$(grep -oP '^BOOTSTRAP_USER_ID=\K.+' .env 2>/dev/null || echo "primary_user")
        BOOT_CAPITAL=$(grep -oP '^BOOTSTRAP_STARTING_CAPITAL=\K.+' .env 2>/dev/null || echo "150000")

        if compose exec -T -e PYTHONPATH=/app \
            -e BOOTSTRAP_ACCOUNT_ID="$BOOT_ACCOUNT" \
            -e BOOTSTRAP_USER_ID="$BOOT_USER" \
            -e BOOTSTRAP_STARTING_CAPITAL="$BOOT_CAPITAL" \
            captain-offline \
            python /captain/scripts/bootstrap_production.py 2>&1 | \
            tail -5 | while IFS= read -r line; do echo "  $line"; done; then
            log "  Production bootstrap: complete"
        else
            err "  bootstrap_production.py failed."
            err "  If column errors, schema fixes may not have applied. Check output."
            err "  Resume: bash scripts/tower-deploy.sh --from-phase 5"
            exit 1
        fi

        # ── Step 3: Seed AIM historical data (D29-D33) ──────────────────
        info "Seeding AIM historical data (D29-D33)..."
        SEED_FAILED=false
        for seed_script in \
            seed_iv_rv_from_extract.py \
            seed_skew_from_extract.py \
            seed_ohlcv_from_qc.py \
            seed_or_volumes_from_qc.py \
            seed_opening_vol_from_qc.py; do

            if run_in_offline "/captain/scripts/$seed_script" 2>&1 | \
                tail -1 | while IFS= read -r line; do echo "  $line"; done; then
                true  # success
            else
                warn "  $seed_script had errors (non-fatal, continuing)"
                SEED_FAILED=true
            fi
        done

        if $SEED_FAILED; then
            warn "Some historical seeders had errors. Non-critical — system can still operate."
        fi
        log "  Historical seeding: complete"

        # ── Verify bootstrap results ─────────────────────────────────────
        info "Verifying bootstrap results..."
        compose exec -T -e PYTHONPATH=/app captain-offline python -c "
import psycopg2, os
conn = psycopg2.connect(
    host=os.environ.get('QUESTDB_HOST','questdb'),
    port=int(os.environ.get('QUESTDB_PORT','8812')),
    user=os.environ.get('QUESTDB_USER','captain'), password=os.environ.get('QUESTDB_PASSWORD',''), dbname='qdb'
)
conn.autocommit = True
cur = conn.cursor()
tables = [
    'p3_d00_asset_universe', 'p3_d01_aim_model_states',
    'p3_d02_aim_meta_weights', 'p3_d05_ewma_states',
    'p3_d12_kelly_parameters', 'p3_d16_user_capital_silos',
    'p3_d25_circuit_breaker_params'
]
for t in tables:
    try:
        cur.execute(f'SELECT count() FROM {t}')
        print(f'  {t}: {cur.fetchone()[0]} rows')
    except Exception as e:
        print(f'  {t}: ERROR ({e})')
cur.close(); conn.close()
" 2>&1 || true
    fi

    log "Phase 5 complete."
fi


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 6: AUTOMATION (Cron, Healthcheck, Systemd)
# ══════════════════════════════════════════════════════════════════════════════
if [ "$FROM_PHASE" -le 6 ]; then
    header 6 "Automation Setup"

    # ── 6a: Healthcheck script ────────────────────────────────────────────
    info "Creating healthcheck script..."
    # Write with unquoted heredoc for CAPTAIN_DIR expansion, escape all runtime vars
    cat > "$HOME_DIR/healthcheck.sh" << HEALTHEOF
#!/bin/bash
# Captain healthcheck — runs every 5 min via cron
# Restarts dead containers and sends Telegram alerts
cd ${CAPTAIN_DIR} || exit 1

TELEGRAM_TOKEN=\$(grep -oP 'TELEGRAM_BOT_TOKEN=\K.+' .env 2>/dev/null || echo "")
CHAT_ID=\$(grep -oP 'TELEGRAM_CHAT_ID=\K.+' .env 2>/dev/null || echo "")

send_alert() {
    if [ -n "\$TELEGRAM_TOKEN" ] && [ -n "\$CHAT_ID" ]; then
        curl -sf -X POST "https://api.telegram.org/bot\${TELEGRAM_TOKEN}/sendMessage" \\
            -d "chat_id=\${CHAT_ID}" -d "text=CAPTAIN \$(hostname): \$1" --max-time 10 >/dev/null 2>&1
    fi
    echo "\$(date '+%Y-%m-%d %H:%M:%S') \$1"
}

for svc in questdb redis captain-offline captain-online captain-command nginx; do
    state=\$(docker compose -f docker-compose.yml -f docker-compose.local.yml \\
        ps --format '{{.State}}' "\$svc" 2>/dev/null)
    if [ "\$state" != "running" ]; then
        send_alert "\$svc is \$state — restarting..."
        docker compose -f docker-compose.yml -f docker-compose.local.yml \\
            restart "\$svc" 2>/dev/null
        sleep 15
        new_state=\$(docker compose -f docker-compose.yml -f docker-compose.local.yml \\
            ps --format '{{.State}}' "\$svc" 2>/dev/null)
        if [ "\$new_state" = "running" ]; then
            send_alert "\$svc recovered after restart."
        else
            send_alert "\$svc FAILED TO RESTART (\$new_state). Manual intervention required."
        fi
    fi
done
HEALTHEOF
    chmod +x "$HOME_DIR/healthcheck.sh"
    log "  healthcheck.sh: $HOME_DIR/healthcheck.sh"

    # ── 6b: Cron jobs ────────────────────────────────────────────────────
    info "Installing cron jobs..."
    mkdir -p "$HOME_DIR/backups"

    # Use printf to avoid heredoc escaping issues with crontab
    printf '%s\n' \
        "# Captain System cron jobs — installed by tower-deploy.sh ($(date '+%Y-%m-%d'))" \
        "" \
        "# VIX/VXV daily data update — weekdays 10 PM" \
        "0 22 * * 1-5 ${CAPTAIN_DIR}/scripts/update_vix_data.sh >> ${CAPTAIN_DIR}/logs/vix_update.log 2>&1" \
        "" \
        "# Container health monitoring — every 5 minutes" \
        "*/5 * * * * ${HOME_DIR}/healthcheck.sh >> ${CAPTAIN_DIR}/logs/healthcheck.log 2>&1" \
        "" \
        "# Daily QuestDB backup — 2 AM, 14-day retention" \
        "0 2 * * * cd ${CAPTAIN_DIR} && tar czf ${HOME_DIR}/backups/questdb-\$(date +\\%Y\\%m\\%d).tar.gz questdb/db/ 2>/dev/null && find ${HOME_DIR}/backups/ -name \"questdb-*.tar.gz\" -mtime +14 -delete" \
        | crontab -

    log "  Cron jobs installed:"
    log "    VIX update:   weekdays 10 PM"
    log "    Healthcheck:  every 5 minutes"
    log "    QuestDB backup: daily 2 AM (14-day retention)"

    # ── 6c: Systemd service (auto-start on boot) ─────────────────────────
    info "Creating systemd service..."

    sudo tee /etc/systemd/system/captain.service > /dev/null << SVCEOF
[Unit]
Description=Captain Trading System
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=${CURRENT_USER}
WorkingDirectory=${CAPTAIN_DIR}
ExecStart=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.local.yml down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
SVCEOF

    sudo systemctl daemon-reload
    sudo systemctl enable captain.service >/dev/null 2>&1
    log "  captain.service: enabled (auto-start on boot)"

    log "Phase 6 complete."
fi


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 7: FINAL VERIFICATION
# ══════════════════════════════════════════════════════════════════════════════
if [ "$FROM_PHASE" -le 7 ]; then
    header 7 "Final Verification"

    if [ -x "$SCRIPT_DIR/tower-verify.sh" ]; then
        bash "$SCRIPT_DIR/tower-verify.sh"
    else
        # Inline basic verification if tower-verify.sh isn't available yet
        info "Running basic checks..."

        for svc in questdb redis captain-offline captain-online captain-command nginx; do
            state=$(compose ps --format '{{.State}}' "$svc" 2>/dev/null || echo "missing")
            if [ "$state" = "running" ]; then
                log "  $svc: running"
            else
                err "  $svc: $state"
            fi
        done

        if curl -sf http://localhost/api/health >/dev/null 2>&1; then
            log "  API: healthy"
        else
            warn "  API: not responding (may still be initializing)"
        fi

        cron_count=$(crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | wc -l)
        log "  Cron entries: $cron_count"
    fi
fi


# ══════════════════════════════════════════════════════════════════════════════
#  DONE
# ══════════════════════════════════════════════════════════════════════════════
TOWER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo ""
echo -e "${BOLD}================================================================${NC}"
echo -e "${BOLD}  Captain System — Tower Deployment Complete${NC}"
echo -e "${BOLD}================================================================${NC}"
echo ""
echo "  GUI:       http://$TOWER_IP"
echo "  QuestDB:   http://$TOWER_IP:9000"
echo "  API:       http://$TOWER_IP/api/health"
echo "  Time:      $(TZ=America/New_York date '+%H:%M:%S %Z')"
echo ""
echo "  Daily operations:"
echo "    Start:        bash captain-start.sh"
echo "    Rebuild:      bash captain-start.sh --build"
echo "    Stop:         docker compose $COMPOSE_FILES down"
echo "    Logs:         docker compose $COMPOSE_FILES logs -f"
echo "    Pull updates: bash scripts/captain-update.sh"
echo "    Re-verify:    bash scripts/tower-verify.sh"
echo ""
