# Captain System — Rebuild & Startup Guide

## Quick Reference

```bash
# Fish shell (both towers)
captain start              # Daily startup (light)
captain start --build      # Rebuild containers after code changes
captain rebuild            # Full heavy rebuild (nuclear option)
captain stop               # Stop containers (data preserved)
captain status             # Health check (read-only)
captain compact            # Compact QuestDB state tables
captain update             # Git pull + light rebuild
captain logs captain-online  # Tail specific service logs
captain restart captain-command  # Rebuild and restart one service
captain ps                 # Show container status

# Or use bash directly
bash captain-start.sh              # Light startup
bash captain-start.sh --build      # Light startup + rebuild images
bash captain-rebuild.sh            # Full heavy rebuild
bash captain-rebuild.sh --status   # Health check only
bash captain-rebuild.sh --compact  # Compact QuestDB only
```

---

## Terminal Commands (Copy-Paste Ready)

### Nomaan's Tower

```bash
# 1. Open WSL terminal (Windows Terminal → Ubuntu, or from PowerShell):
wsl -d Ubuntu

# 2. Navigate to project
cd ~/captain-system

# 3. Run whichever command you need:

# Daily startup (no code changes)
bash captain-start.sh

# Startup with image rebuild (after code changes)
bash captain-start.sh --build

# Full heavy rebuild (after major changes, broken state, or schema changes)
bash captain-rebuild.sh

# Health check only (read-only, changes nothing)
bash captain-rebuild.sh --status

# Compact QuestDB tables (fix bloat without restart)
bash captain-rebuild.sh --compact

# Git pull + light rebuild
bash scripts/captain-update.sh

# Stop everything (data preserved)
bash captain-stop.sh

# Stop and wipe all data (DESTRUCTIVE — asks for confirmation)
bash captain-stop.sh --wipe

# Rebuild a single service after a code change
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-online

# View logs for a specific service
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-command

# View last 50 lines of all logs
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail 50

# Check container status
docker compose -f docker-compose.yml -f docker-compose.local.yml ps

# Run bootstrap manually inside container
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -e PYTHONPATH=/app captain-offline python /captain/scripts/bootstrap_production.py

# Run compaction manually inside container
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -e PYTHONPATH=/app captain-offline python /captain/scripts/compact_questdb_tables.py

# Open QuestDB web console
# In browser: http://localhost:9000
```

### Isaac's Tower

```bash
# 1. Open WSL terminal (Windows Terminal → Ubuntu, or from PowerShell):
wsl -d Ubuntu

# 2. Navigate to project
cd ~/captain-system

# 3. Pull latest code from Nomaan
git pull origin main

# 4. Check if .env needs new variables (warnings will show if so)
bash scripts/captain-update.sh

# -- OR for a full rebuild after major changes: --
bash captain-rebuild.sh

# All other commands are identical to Nomaan's tower:
bash captain-start.sh              # Daily startup
bash captain-start.sh --build      # Rebuild after code changes
bash captain-rebuild.sh --status   # Health check
bash captain-rebuild.sh --compact  # Compact QuestDB
bash captain-stop.sh               # Stop
```

### Fish Shell (Both Towers)

If the Fish `captain` function is installed (see setup below), all commands become shorter:

```fish
# These work from any directory — no need to cd first
captain start              # Daily startup
captain start --build      # Rebuild images
captain rebuild            # Full heavy rebuild
captain status             # Health check
captain compact            # Compact QuestDB
captain update             # Git pull + light rebuild
captain stop               # Stop containers
captain logs captain-online  # Tail service logs
captain restart captain-command  # Rebuild one service
captain ps                 # Container status
```

#### Installing the Fish `captain` function

The function file needs to exist at `~/.config/fish/functions/captain.fish`. If it's missing on Isaac's tower, copy it from this repo:

```bash
# On Isaac's tower (one-time setup)
mkdir -p ~/.config/fish/functions ~/.config/fish/completions
cp ~/captain-system/docs/fish/captain.fish ~/.config/fish/functions/captain.fish
cp ~/captain-system/docs/fish/captain-completions.fish ~/.config/fish/completions/captain.fish

# Add CAPTAIN_DIR to Fish config (one-time)
echo 'set -gx CAPTAIN_DIR $HOME/captain-system' >> ~/.config/fish/config.fish
```

Or just add it directly in the Fish shell:

```fish
# This persists across sessions via Fish universal variable
set -U CAPTAIN_DIR ~/captain-system
```

---

## When to Use What

| Scenario | Command | Time | What happens |
|----------|---------|------|-------------|
| **Daily startup** (no code changes) | `captain start` | ~30s | Starts containers, checks health |
| **Python code change** (single service) | `captain restart captain-online` | ~30s | Rebuilds one container only |
| **Code changes** (multiple files) | `captain start --build` | ~2min | Rebuilds all images, starts |
| **Git pull** with minor changes | `captain update` | ~2min | Pulls, checks .env, rebuilds, re-inits |
| **Schema changes** (new QuestDB table) | `captain update` | ~2min | Includes idempotent table init |
| **QuestDB bloated / slow** | `captain compact` | ~1min | Compacts 5 state tables (D01,D02,D05,D12,D25) |
| **Major refactor / breaking changes** | `captain rebuild` | ~5min | Full stop → clean → init → bootstrap → start → verify |
| **System acting weird** | `captain rebuild` | ~5min | Resets Redis, compacts QuestDB, re-bootstraps |
| **Fresh install / total reset** | `captain rebuild` | ~5min | Works from clean state |
| **Check health without changing anything** | `captain status` | ~5s | Read-only health check |

### Decision Tree

```
Did you change code?
├── No → captain start
├── Yes, Python only (one service) → captain restart captain-online
├── Yes, Python only (multiple services) → captain start --build
├── Yes, Dockerfile/compose changes → captain rebuild
├── Yes, QuestDB schema changes → captain rebuild
└── Yes, pulled from git → captain update
```

---

## Full Rebuild Flow (`captain rebuild`)

The heavy rebuild runs 12 phases in order:

```
Phase 1:  Pre-flight checks
          ├── Docker daemon running?
          ├── Project files exist?
          ├── .env validated (required vars present)?
          ├── .env.template new vars check
          └── vm.max_map_count >= 1048576?

Phase 2:  Stop all containers (docker compose down)

Phase 3:  Pre-start repairs
          ├── Fix journal.sqlite files (rm directories, touch files)
          ├── Detect and repair corrupted Redis AOF
          └── Sync config/ into build contexts

Phase 4:  Build images + start all containers (docker compose up -d --build)
          └── Wait for QuestDB + Redis ready

Phase 5:  Flush Redis (FLUSHALL — clears stale keys)

Phase 6:  Initialize QuestDB tables (CREATE IF NOT EXISTS — idempotent)

Phase 7:  Compact state tables (D01, D02, D05, D12, D25)

Phase 8:  Bootstrap production data (idempotent — skips existing rows)

Phase 9:  Update VIX/VXV data (non-fatal)

Phase 10: Wait for all 6 services healthy

Phase 11: Verify API endpoint

Phase 12: Data integrity verification (row count checks)
```

---

## Light Startup Flow (`captain start`)

```
Step 1: vm.max_map_count check
Step 2: Docker daemon check
Step 3: Project file validation + QuestDB backup
Step 4: Config sync + journal.sqlite pre-creation
Step 5: docker compose up -d [--build]
Step 5: Wait for QuestDB + Redis
Step 6: Init tables + integrity check + compaction + VIX update
Step 7: Wait for all services
Step 8: Verify API
```

---

## Tower-Specific Notes

Both towers use **the same scripts** — no separate Isaac/Nomaan variants needed. Paths are auto-detected from the script's location.

| | Nomaan's Tower | Isaac's Tower |
|---|---|---|
| **Path** | `/home/nomaan/captain-system` | `/home/isaac/captain-system` |
| **Shell** | Fish | Fish |
| **Platform** | WSL2 on Windows | WSL2 on Windows |
| **INSTANCE_PARITY** | `0` (takes odd signals) | `1` (takes even signals) |
| **Account** | Set in `.env` | Set in `.env` |

### Pushing updates to Isaac's tower

```bash
# On Nomaan's machine
git push multi-user main

# On Isaac's machine
captain update
# Or: bash scripts/captain-update.sh
```

If the update includes schema changes or new .env variables, Isaac should run `captain rebuild` instead.

---

## Common Issues & Fixes

### Redis AOF corruption

**Symptom:** Redis container unhealthy, all captain services fail to start.

**Cause:** WSL2's 9P filesystem causes transient I/O errors during Redis AOF writes.

**Fix:** `captain rebuild` auto-detects and repairs corrupted AOF files. For manual repair:
```bash
# Find and fix corrupted AOF
redis-check-aof --fix redis/appendonlydir/*.aof
# Then restart
captain start
```

### QuestDB OOM / table bloat

**Symptom:** captain-command crashes, QuestDB using excessive memory, slow queries.

**Cause:** QuestDB append-only tables accumulate rows forever. D01 alone grew to 8M+ rows.

**Fix:**
```bash
captain compact   # Quick fix — compacts 5 state tables
captain rebuild   # Full fix if compaction alone doesn't help
```

**Prevention:** The offline orchestrator now runs compaction automatically every 48 hours.

### Redis auth failure (containers won't start)

**Symptom:** "dependency failed to start: container captain-system-redis-1 is unhealthy"

**Cause:** `REDIS_PASSWORD` missing or incorrect in `.env`.

**Fix:** Check `.env` has a valid `REDIS_PASSWORD` value, then restart:
```bash
grep REDIS_PASSWORD .env    # Verify it's set
captain start
```

### journal.sqlite is a directory

**Symptom:** SQLite error "unable to open database file" in container logs.

**Cause:** Docker bind-mount creates a directory when the file doesn't exist (gitignored).

**Fix:** `captain rebuild` handles this automatically. For manual fix:
```bash
rm -rf captain-offline/journal.sqlite captain-online/journal.sqlite captain-command/journal.sqlite
touch captain-offline/journal.sqlite captain-online/journal.sqlite captain-command/journal.sqlite
captain start
```

### Bootstrap fails on empty D00

**Symptom:** `ValueError: Asset ES not found in p3_d00_asset_universe`

**Cause:** Tables were truncated but bootstrap was run before init populated D00.

**Fix:** `captain rebuild` runs init before bootstrap. The bootstrap script is now idempotent — it inserts base rows if missing and skips existing data.

### Health check timeout

**Symptom:** "TIMEOUT: Not all containers running after 240s"

**Fix:** Increase timeout via environment variable:
```bash
HEALTH_TIMEOUT=360 captain rebuild
```

Or check which service is failing:
```bash
captain ps
captain logs captain-command
```

### .env template has new variables

**Symptom:** Warning about missing variables after git pull.

**Fix:** Check `.env.template` for new variables and add them to `.env`:
```bash
diff <(grep -oP '^\w+(?==)' .env.template | sort) <(grep -oP '^\w+(?==)' .env | sort)
```

---

## Runtime Compaction

The captain-offline orchestrator runs QuestDB compaction automatically every 48 hours during normal operation. This prevents the table bloat issue without requiring manual intervention or restarts.

**Tables compacted:** D01 (aim_model_states), D02 (aim_meta_weights), D05 (ewma_states), D12 (kelly_parameters), D25 (circuit_breaker_params)

**Algorithm:** For each table, keep only the latest row per logical key (e.g., per aim_id+asset_id for D02). All older rows are dropped.

To run compaction manually at any time:
```bash
captain compact
```

---

## File Reference

| File | Purpose |
|------|---------|
| `captain-start.sh` | Light daily startup (the "default" script) |
| `captain-rebuild.sh` | Heavy rebuild with full init/bootstrap chain |
| `captain-stop.sh` | Safe shutdown (preserves data) |
| `scripts/captain-update.sh` | Git pull + light rebuild |
| `scripts/captain-setup.sh` | Interactive first-time setup wizard |
| `scripts/init_all.py` | Create QuestDB tables + seed initial data |
| `scripts/bootstrap_production.py` | Seed production data (idempotent) |
| `scripts/compact_questdb_tables.py` | Compact 5 append-only state tables |
| `~/.config/fish/functions/captain.fish` | Fish shell `captain` command |
| `~/.config/fish/completions/captain.fish` | Tab completions for `captain` |
