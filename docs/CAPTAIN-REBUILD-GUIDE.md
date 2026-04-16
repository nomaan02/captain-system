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
