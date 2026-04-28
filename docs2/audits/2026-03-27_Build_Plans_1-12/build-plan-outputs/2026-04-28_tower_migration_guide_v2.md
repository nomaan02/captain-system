# Tower Migration & Implementation Guide (v2)

**Audience:** Operator deploying GitHub-pushed Captain System changes onto **two Linux towers** running **fish** shell.
**Scope:** Phases 1–11 cumulative changes — pull, rebuild, migrate QuestDB, verify, run pytest.
**Repo path assumed:** `~/captain-system`

> **Run every numbered step on Tower A first, then repeat on Tower B.**
> Both towers must end on the **same git SHA** (`git rev-parse HEAD`).

---

## TL;DR — happy path

```fish
cd ~/captain-system
git remote -v                                       # confirm remote name
bash scripts/captain-update.sh                      # pull + rebuild + init + seed
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/verify_schema_drift.py
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/verify_questdb_state.py
```

If both verifies exit clean, you're done. Otherwise jump to **§7 Troubleshooting**.

---

## 0. Quick reference

### 0.1 Compose command alias (paste once per fish session)

The full compose command is verbose. Define a shell-local function so the rest of the guide stays short:

```fish
function dco
    docker compose -f docker-compose.yml -f docker-compose.local.yml $argv
end
```

After this, `dco ps`, `dco logs -f captain-online`, `dco exec -T captain-offline ...` all work. The full form is shown the first time each command appears so you can copy verbatim if you skip this alias.

### 0.2 Container exec helper

Almost every script in this guide runs inside `captain-offline` with `PYTHONPATH=/app`. Define:

```fish
function cap-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/$script $rest
end
```

Now `cap-run init_questdb.py` is equivalent to the long form.

### 0.3 Why `/captain/scripts/...` and not `/app/scripts/...`?

`docker-compose.local.yml` bind-mounts `./scripts` → `/captain/scripts:ro` **only on `captain-offline`**. If you run compose **without** the local override file, that path won't exist. **Always pass both `-f` files** (or use the helpers above).

---

## 1. Pre-flight (run on each tower)

### 1.1 Confirm repo state

```fish
cd ~/captain-system
git status
git branch --show-current      # expect: main
git remote -v                  # note whether updates come from origin or multi-user
```

### 1.2 Confirm Docker

```fish
docker --version
docker compose version
```

### 1.3 Confirm `.env`

```fish
test -f .env; and echo ".env OK"; or echo "MISSING — run: bash scripts/captain-setup.sh"
grep INSTANCE_PARITY .env      # Tower A=0, Tower B=1
```

### 1.4 Free disk for QuestDB backup

`captain-update.sh` tars `questdb/db/` to `backups/questdb/`. Check there's room:

```fish
du -sh questdb/db/ 2>/dev/null
df -h .
```

---

## 2. Pull GitHub changes

### 2.1 If `origin` points at the GitHub repo

```fish
cd ~/captain-system
bash scripts/captain-update.sh
```

This script does **all of the following** in one shot:

1. `git pull origin main`
2. Warns about new vars in `.env.template`
3. Syncs `config/` into the three service build contexts
4. Backs up `questdb/db/` to `backups/questdb/questdb-pre-update-*.tar.gz`
5. `docker compose ... up -d --build`
6. Waits for QuestDB + Redis to be healthy
7. Runs `init_questdb.py` inside `captain-offline` (applies `CANONICAL_DDLS` + `CANONICAL_MIGRATIONS`)
8. Runs `seed_all_assets.py` and CSV seeds (idempotent)
9. Row-count integrity check via psycopg2
10. Prints container health

### 2.2 If the remote is `multi-user` (not `origin`)

`captain-update.sh` hard-codes `git pull origin main`. Pull manually first, then skip the script's pull step:

```fish
cd ~/captain-system
git pull multi-user main
bash scripts/captain-update.sh --skip-pull
```

### 2.3 What to watch for in the script output


| Message                                | Action                                                                                                             |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `New variables found in .env.template` | Open `.env.template`, copy any new keys into `.env`, then `dco up -d` to restart                                   |
| `DATA INTEGRITY CHECK FAILED`          | **Do not trade.** Restore from `backups/questdb/questdb-pre-update-*.tar.gz` per the script's printed instructions |
| `init_questdb.py [FAIL]` lines         | See §7.3                                                                                                           |


---

## 3. QuestDB schema migrations

`captain-update.sh` already ran this. **You only need this section if you skipped the script** (e.g. ran `docker compose up -d --build` directly) or are recovering from a failure.

### 3.1 Apply DDLs + migrations manually

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/init_questdb.py
```

Or with the alias from §0.2: `cap-run init_questdb.py`

Idempotent — safe to re-run.

### 3.2 Backfill legacy D03 rows (Phase 7, **per-tower decision**)

If this tower wrote D03 trade rows **before** the `signal_id` column existed, run once:

```fish
# Dry run first
cap-run backfill_d03_signal_ids.py --dry-run

# Apply
cap-run backfill_d03_signal_ids.py
```

Sets `signal_id = LEGACY-<uuid>` on rows where it's NULL/empty. `captain-update.sh` does **not** do this automatically.

### 3.3 Compaction (ongoing maintenance — not part of Phase 7)

```fish
cap-run compact_questdb_tables.py
```

Compacts D01/D02/D05/D12/D25 only. **Does not touch** D03/D11/D06.

---

## 4. Verification (run after every update)

Run all three. Stop and triage if any of them flag CRITICAL.

### 4.1 Schema drift (CRITICAL gate)

```fish
cap-run verify_schema_drift.py
```

Exits non-zero if live QuestDB columns differ from `shared/canonical_schemas.py`. **Must pass before trading.**

### 4.2 Health audit

```fish
cap-run verify_questdb_state.py
# Optional flags:
cap-run verify_questdb_state.py --strict           # WARN→fail
cap-run verify_questdb_state.py --json
cap-run verify_questdb_state.py --report /tmp/health.md
```

### 4.3 Smoke test

```fish
cap-run health_smoke_test.py
```

Reads one row from each critical table and writes/reads a dedup row on `p3_smoke_scratch`.

### 4.4 (Optional) Eyeball columns in QuestDB console

Browser → `http://127.0.0.1:9000`:

```sql
SHOW COLUMNS FROM p3_d03_trade_outcome_log;   -- expect signal_id, model_m
SHOW COLUMNS FROM p2_d07_regime_models;
SHOW COLUMNS FROM p3_d22b_asset_rerun_status;
SHOW COLUMNS FROM p3_d26_hmm_opportunity_state;
```

---

## 5. Running pytest from the host

> **Why from the host?** Faster iteration than `dco exec`. But you need a Python venv with the project deps and QuestDB reachable on `127.0.0.1:8812`.

### 5.1 First-time host setup (skip if already done)

```fish
cd ~/captain-system
python3 -m venv .venv
source .venv/bin/activate.fish
pip install --upgrade pip
pip install -r captain-offline/requirements.txt
pip install -r captain-online/requirements.txt
pip install -r captain-command/requirements.txt
pip install pytest pytest-asyncio
```

If a single combined install fails on conflicting pins, install per-service into separate venvs (see §7.5).

### 5.2 Activate venv + set env (every fish session)

```fish
cd ~/captain-system
source .venv/bin/activate.fish
set -gx PYTHONPATH $PWD:$PWD/captain-online:$PWD/captain-offline:$PWD/captain-command
set -gx QUESTDB_HOST 127.0.0.1
set -gx QUESTDB_PORT 8812
set -gx REDIS_HOST 127.0.0.1
set -gx REDIS_PORT 6379
```

### 5.3 Fast gate (no heavy integration tests)

```fish
python -B -m pytest tests/ \
  --ignore=tests/test_integration_e2e.py \
  --ignore=tests/test_pipeline_e2e.py \
  --ignore=tests/test_pseudotrader_account.py \
  --ignore=tests/test_offline_feedback.py \
  --ignore=tests/test_stress.py \
  --ignore=tests/test_account_lifecycle.py \
  -q
```

> ⚠️ `tests/test_account_lifecycle.py` mocks `sys.modules["shared"]` and **breaks collection of every other test in the same process**. Always ignore it unless running solo.

### 5.4 Live QuestDB schema tests (Phase 1 + Phase 7)

QuestDB must be running with port 8812 published.

```fish
python -B -m pytest tests/test_schema_migrations.py -v
python -B -m pytest tests/test_schema_d03_signal_id.py -v
```

Pytest may warn `real_questdb` is an unknown marker — informational only.

### 5.5 Phase-targeted suites

```fish
# Phase 9
python -B -m pytest tests/test_b9_diagnostic_phase9.py -v

# Phase 10 (HMM cluster)
python -B -m pytest tests/test_aim16_observation_panel.py tests/test_aim16_hmm_train.py \
                    tests/test_hmm_online_inference.py tests/test_d26_hmm_round_trip.py \
                    tests/test_hmm_phase10_e2e.py -q

# Phase 11 (rollback)
python -B -m pytest tests/test_version_rollback_two_phase.py tests/test_version_snapshot_coverage.py -q
```

### 5.6 Running pytest **inside** the container (no host venv needed)

If the host venv is broken or missing deps, run pytest where the deps already exist:

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T \
  -e PYTHONPATH=/app -e QUESTDB_HOST=questdb -e REDIS_HOST=redis \
  captain-offline python -B -m pytest /app/tests/test_schema_migrations.py -v
```

Note: `QUESTDB_HOST=questdb` (the compose service name) **inside** the container, not `127.0.0.1`.

The `tests/` directory is mounted into `captain-offline` at `/app/tests` via the local override — confirm with `dco exec captain-offline ls /app/tests | head` if unsure.

---

## 6. Both-towers checklist

Tick all on **each** tower:

- `git rev-parse HEAD` matches the intended commit
- `git remote -v` shows the right remote for this tower
- `bash scripts/captain-update.sh` finished without `DATA INTEGRITY CHECK FAILED`
- `.env` parity is `0` on Tower A, `1` on Tower B
- D03 backfill run (only if legacy rows existed)
- `verify_schema_drift.py` exit 0
- `verify_questdb_state.py` reviewed — no unexpected CRITICAL
- Fast pytest gate green (§5.3)
- Live schema pytest green (§5.4)
- One log line tailed per service: `dco logs --tail=20 captain-offline captain-online captain-command`

When **both towers** show the same `git rev-parse HEAD` and pass everything above, the rollout is aligned.

---

## 7. Troubleshooting

### 7.1 `git pull` fails (divergent history, conflict, dirty tree)

```fish
git status                              # see what's dirty
git stash push -m "pre-update local"    # park local edits
git pull origin main                    # or: git pull multi-user main
git stash pop                           # restore (resolve conflicts if any)
```

If the pull is blocked by a hook signature mismatch, fix the underlying issue — never use `--no-verify` on a tower.

### 7.2 Compose can't find `/captain/scripts/...`

Cause: ran compose without the local override file.

```fish
# Wrong (no local override):
docker compose exec captain-offline python /captain/scripts/init_questdb.py

# Right:
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/init_questdb.py
```

Use the `dco` / `cap-run` helpers from §0 to make this impossible to forget.

### 7.3 `init_questdb.py` reports `[FAIL]` on a migration

1. Read the failing migration's SQL — it's in `shared/canonical_schemas.py` under `CANONICAL_MIGRATIONS`.
2. Check whether the column already exists with a different type:
  ```fish
   cap-run verify_schema_drift.py
  ```
3. If the table is broken beyond repair, restore the latest backup:
  ```fish
   ls -lah backups/questdb/
   docker compose -f docker-compose.yml -f docker-compose.local.yml down
   tar -xzf backups/questdb/questdb-pre-update-<TIMESTAMP>.tar.gz -C questdb/
   docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
   cap-run init_questdb.py
  ```

### 7.4 Pytest: `ModuleNotFoundError: No module named 'shared'` (or `captain_offline`, etc.)

`PYTHONPATH` not exported, or the venv is wrong. Re-run §5.2 in this fish session. Verify:

```fish
echo $PYTHONPATH
python -c "import shared, captain_offline, captain_online, captain_command; print('ok')"
```

### 7.5 Pytest: missing `scipy`, `hmmlearn`, `pysignalr`, `psycopg2`

These ship via the service `requirements.txt` files. Three options:

**Option A — install into host venv:**

```fish
source .venv/bin/activate.fish
pip install scipy hmmlearn pysignalr "psycopg2-binary>=2.9"
```

**Option B — split venvs per service** (avoids version conflicts):

```fish
python3 -m venv .venv-offline
source .venv-offline/bin/activate.fish
pip install -r captain-offline/requirements.txt pytest pytest-asyncio
# Repeat with .venv-online / .venv-command as needed
```

**Option C — run pytest inside the container** where the deps already exist (§5.6). This is the lowest-friction path on a fresh tower.

### 7.6 Pytest: `connection refused` on QuestDB

```fish
dco ps | grep questdb                    # is it Up?
dco logs --tail=50 questdb               # any startup error?
nc -zv 127.0.0.1 8812                    # port forwarded?
```

If running pytest inside the container, use `QUESTDB_HOST=questdb` (service name), not `127.0.0.1`.

### 7.7 Pytest: `tests/test_account_lifecycle.py` poisoned the run

Symptom: dozens of unrelated tests fail with import errors after that file is collected. **Always pass `--ignore=tests/test_account_lifecycle.py`** unless running it alone.

### 7.8 Fish: `command not found: source` for `activate`

You used the bash file. Fish needs the `.fish` variant:

```fish
source .venv/bin/activate.fish     # not activate
```

### 7.9 Fish: `Unknown command: set -gx VAR=value`

Fish syntax is space-separated, not `=`:

```fish
# Wrong (bash):     export VAR=value
# Wrong (fish):     set -gx VAR=value
# Right (fish):     set -gx VAR value
```

### 7.10 Container exits / unhealthy after rebuild

```fish
dco ps
dco logs --tail=100 captain-online
dco logs --tail=100 captain-offline
dco logs --tail=100 captain-command
```

Common causes: missing `.env` key (check §2.3), QuestDB not yet healthy when service started (`dco restart captain-online`), port already bound on host (`ss -lntp | grep 8000`).

### 7.11 Backfill ran but D03 still has NULL `signal_id`

```fish
cap-run backfill_d03_signal_ids.py --dry-run     # see what it *would* update
```

Confirm the rows actually have NULL/empty (not whitespace) and that QuestDB DEDUP keys match the script's expectation. The script docstring lists the WHERE clause it uses.

### 7.12 `verify_schema_drift.py` flags an unexpected column

Either:

- Code defines a column that wasn't migrated → run `cap-run init_questdb.py` again.
- Live DB has an extra column from a prior experiment → drop it manually via QuestDB console, or accept as benign and document.

---

## 8. Script catalog (most-used)


| Script                       | Purpose                                                        |
| ---------------------------- | -------------------------------------------------------------- |
| `init_questdb.py`            | Apply `CANONICAL_DDLS` + `CANONICAL_MIGRATIONS` (idempotent)   |
| `init_all.py`                | Full Phase-1 init: tables + SQLite journals + baseline seeds   |
| `backfill_d03_signal_ids.py` | Phase 7: assign `LEGACY-*` to old D03 rows                     |
| `compact_questdb_tables.py`  | Compact D01/D02/D05/D12/D25                                    |
| `verify_schema_drift.py`     | Diff live DB vs canonical DDLs (CRITICAL gate)                 |
| `verify_questdb_state.py`    | Full health audit (counts, freshness, liveness)                |
| `verify_questdb.py`          | Older smoke checklist for major P3 tables                      |
| `health_smoke_test.py`       | Connectivity + read + dedup scratch write                      |
| `seed_all_assets.py`         | Full multi-asset seed (called by `captain-update.sh`)          |
| `bootstrap_production.py`    | Populate D00/D16/D02/D25 from env-driven account/silo config   |
| `paper_trader.py`            | Simulated trading loop (writes D03 with `signal_id`/`model_m`) |
| `captain-update.sh`          | Pull → backup → rebuild → init → seed → integrity check        |
| `captain-setup.sh`           | Interactive first-machine setup                                |


Full list: see the original guide §I or `ls scripts/`.

---

## 9. References

- Architecture / ports / tests: `CLAUDE.md`
- Multi-instance parity: `CLAUDE.md` § Multi-Instance Deployment
- Canonical DDL/migrations: `shared/canonical_schemas.py`
- QuestDB env vars: `shared/questdb_client.py`
- Original (verbose) guide: `2026-04-28_tower_migration_and_implementation_guide.md` (this folder)

