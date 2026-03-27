# Developer Workflow Guide

> Practical reference for day-to-day development on the Captain System.
> Environment: Windows 11 + WSL 2 (Ubuntu 24.04) + Docker Desktop.

---

## 1. Opening the Project

The captain-system project lives on the **WSL 2 native ext4 filesystem** at
`~/captain-system/`. Always use this path -- never the `/mnt/c/` cross-filesystem
mount, which is slow and causes file-watching, permission, and line-ending problems.

**VS Code**

```bash
# From a WSL terminal:
code ~/captain-system
```

Or from Windows: open VS Code, install the **Remote - WSL** extension, then
`Ctrl+Shift+P` > "WSL: Connect to WSL" and open `~/captain-system`.

**Cursor**

```bash
# From a WSL terminal:
cursor ~/captain-system
```

Same Remote-WSL approach works if launching from Windows.

**Terminal only**

```bash
cd ~/captain-system
```

> **IMPORTANT:** Never open or edit files from `C:\Users\nomaa\...` or `/mnt/c/...`
> paths. All edits must happen through the WSL native path (`~/captain-system/` or
> `/home/nomaan/captain-system/`). The `/mnt/c/` mount goes through the 9P filesystem
> bridge, which is orders of magnitude slower and can silently corrupt line endings.

---

## 2. Running Claude Code

```bash
cd ~/captain-system && claude
```

- Claude Code reads `CLAUDE.md` automatically from the project root.
- The project context (memory, session state, conversation history) is keyed to the
  WSL path `/home/nomaan/captain-system`, not the Windows-side path. Starting Claude
  from a different path creates a separate context.
- All file paths Claude operates on will be WSL-native paths.

---

## 3. Understanding Hot-Reload vs Rebuild

The Docker Compose setup volume-mounts `shared/` and `config/` into containers at
runtime. Changes to those directories are picked up on container restart without
rebuilding images. Changes to service-specific code (inside `captain-command/`,
`captain-online/`, `captain-offline/`, `captain-gui/`) are baked into the Docker
image at build time and require a rebuild.

| What changed | Action needed |
|---|---|
| `shared/*.py` | Just restart containers (volume-mounted `:ro`) |
| `config/*.json` | Just restart containers (volume-mounted) |
| `captain-command/captain_command/*.py` | Rebuild `captain-command` image |
| `captain-online/captain_online/*.py` | Rebuild `captain-online` image |
| `captain-offline/captain_offline/*.py` | Rebuild `captain-offline` image |
| `captain-gui/src/*.tsx` | Rebuild `captain-gui` image |
| Any `Dockerfile` | Rebuild that service's image |
| Any `requirements.txt` | Rebuild that service's image |
| `docker-compose.yml` | `docker compose up -d` (recreates containers) |
| `docker-compose.local.yml` | `docker compose up -d` (recreates containers) |
| `.env` | `docker compose up -d` (recreates containers reading new env) |
| `nginx/nginx-local.conf` | Just restart nginx (volume-mounted `:ro`) |

**Restart without rebuild** (for shared/ or config/ changes):

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml restart captain-command
```

---

## 4. Rebuilding a Single Container

To rebuild and restart a single service without disturbing the others:

```bash
# Rebuild the image
docker compose -f docker-compose.yml -f docker-compose.local.yml build captain-command

# Restart ONLY that container (no dependency restart)
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --no-deps captain-command
```

The `--no-deps` flag is critical: without it, Docker Compose would also restart
`questdb` and `redis` (declared as `depends_on`), which tears down every container
that depends on them and causes unnecessary downtime.

Replace `captain-command` with `captain-online`, `captain-offline`, `captain-gui`,
or `nginx` as needed.

**Rebuild everything** (after broad changes):

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml build
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

Or use the startup script with the `--build` flag:

```bash
bash captain-start.sh --build
```

---

## 5. Starting and Stopping

All compose commands **must** use both compose files for local development:

```
-f docker-compose.yml -f docker-compose.local.yml
```

The base file defines services and volumes. The local override adds memory limits,
localhost port bindings, HTTP-only nginx, and dev-specific mount paths. Never run the
base file alone.

**Full start (automated)**

```bash
bash captain-start.sh
```

This script:
1. Sets `vm.max_map_count` for QuestDB (may prompt for sudo)
2. Waits for Docker Desktop daemon
3. Validates project files exist (compose files, nginx config, `.env`)
4. Runs `docker compose up -d`
5. Waits for QuestDB SQL engine and Redis to be ready
6. Runs QuestDB table initialization (idempotent `CREATE IF NOT EXISTS`)
7. Health-checks all 6 containers (questdb, redis, captain-offline, captain-online, captain-command, nginx)
8. Verifies the Captain Command API responds

Pass `--build` to force an image rebuild:

```bash
bash captain-start.sh --build
```

**Full start (manual)**

```bash
cd ~/captain-system
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

**Stop (preserve data)**

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml down
```

Containers stop, but QuestDB data (`questdb/db/`), Redis AOF (`redis/`), SQLite
journals, and named volumes (`gui-dist`, `vault-backup`) are preserved.

**Stop and remove volumes**

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml down -v
```

> **WARNING:** This destroys the `gui-dist` and `vault-backup` named volumes. QuestDB
> and Redis data are bind-mounted to `./questdb/db/` and `./redis/` respectively, so
> they survive `-v`, but the GUI will need a rebuild and the vault backup is gone.

---

## 6. Viewing Logs

**All services (follow mode, last 50 lines per service)**

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f --tail=50
```

**Single service**

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-command
```

**Filter for errors**

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-command 2>&1 | grep -iE "error|fail|exception|disconnect"
```

**Since a specific time**

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --since="2026-03-26T09:00:00" captain-online
```

**Shorthand:** If typing the double `-f` flags gets tedious, set a shell alias:

```bash
# Add to ~/.bashrc or ~/.zshrc
alias dc='docker compose -f docker-compose.yml -f docker-compose.local.yml'
```

Then: `dc logs -f captain-command`, `dc up -d`, `dc down`, etc.

---

## 7. Git Workflow

Git is initialized in `~/captain-system/` with the remote at
`https://github.com/nomaan02/MOST-Production.git`.

**Standard workflow**

```bash
cd ~/captain-system

# Create a feature branch
git checkout -b feature/my-change

# Make changes, then stage and commit
git add shared/topstep_stream.py
git commit -m "Fix reconnection logic in topstep stream"

# Push and create PR
git push -u origin feature/my-change
```

**What is not tracked (via .gitignore)**

- `.env` -- secrets and API keys, never committed
- `questdb/db/` -- runtime database files
- `redis/` -- Redis AOF persistence
- `*.sqlite`, `*.sqlite-wal`, `*.sqlite-shm` -- crash recovery journals
- `vault/keys.vault` -- encrypted API key vault
- `data/market/`, `data/vix/`, `data/p1_outputs/`, `data/p2_outputs/` -- external data
- `logs/incidents/*`, `logs/crash_reports/*` -- runtime log content

**Line endings**

Ensure WSL git is configured to avoid Windows-style line endings:

```bash
git config --global core.autocrlf input
```

This converts CRLF to LF on commit but does not modify files on checkout (since
you are already working on the Linux filesystem).

---

## 8. Key Gotchas

### Filesystem

- **Never edit from `/mnt/c/` or Windows Explorer.** The 9P cross-filesystem bridge
  is slow (~10x), breaks inotify (no file-watching), and can introduce CRLF line
  endings. Always use the WSL native path: `~/captain-system/`.
- **File permissions:** Docker containers run as root, so files they create (e.g.,
  `journal.sqlite`, log files) will be root-owned. If you need to edit them from your
  WSL user:
  ```bash
  sudo chown -R $(id -u):$(id -g) logs/ captain-command/journal.sqlite
  ```

### Docker

- **Compose files are always paired.** Every `docker compose` command in local dev
  needs both files:
  ```
  -f docker-compose.yml -f docker-compose.local.yml
  ```
  Running with only `docker-compose.yml` will fail (nginx has no port mapping, no
  memory limits, no local nginx config).
- **Memory limits** are set in `docker-compose.local.yml` to stay within the WSL 2
  allocation. If containers get OOM-killed, increase the limit in `.wslconfig`:
  ```ini
  # %UserProfile%\.wslconfig
  [wsl2]
  memory=8GB
  ```
  Then restart WSL: `wsl --shutdown` from PowerShell, then reopen the terminal.

### Services and Ports

| Service | URL | Purpose |
|---|---|---|
| QuestDB console | http://localhost:9000 | SQL query interface, table browser |
| Captain API (direct) | http://localhost:8000/api/health | FastAPI health check (bypasses nginx) |
| Captain API (via nginx) | http://localhost/api/health | Production-like path through nginx |
| GUI | http://localhost | Captain dashboard SPA |
| Redis | localhost:6379 | Connect via `redis-cli` from WSL |
| QuestDB PostgreSQL wire | localhost:8812 | Connect via `psql -h localhost -p 8812 -U admin -d qdb` |

### QuestDB

- QuestDB requires `vm.max_map_count >= 1048576`. The startup script sets this
  automatically, but it resets on WSL restart. To make it permanent:
  ```bash
  echo "vm.max_map_count=1048576" | sudo tee -a /etc/sysctl.conf
  sudo sysctl -p
  ```
- The web console at http://localhost:9000 is the easiest way to inspect tables and
  run ad-hoc queries.

### Timezone

All Captain processes run in `America/New_York` (set via `TZ` environment variable in
compose). QuestDB stores timestamps as UTC. Keep this in mind when comparing log
timestamps (container local time) with database timestamps (UTC).
