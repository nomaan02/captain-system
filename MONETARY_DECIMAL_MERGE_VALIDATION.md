# Monetary Decimal Migration — Merge validation (Linux + fish)

**Purpose:** Step-by-step **fish shell** commands to pull the migration work, satisfy dependencies, run schema checks and tests, and interpret **exact outputs** before you merge to **`main`** and consider the migration **finalised**.

**Related guides:**

- Tower operations (compose, `cap-run`, host venv, troubleshooting):  
  `docs2/audits/2026-03-27_Build_Plans_1-12/build-plan-outputs/2026-04-28_tower_migration_guide_v2.md`
- Migration plan: `MONETARY_DECIMAL_MIGRATION_PLAN.md`
- Phase reports: `MONETARY_DECIMAL_PHASE_A_REPORT.md`, `MONETARY_DECIMAL_PHASE_B_REPORT.md`, `MONETARY_DECIMAL_PHASE_C_REPORT.md`

**Integration branch (all three phases):** `migration/decimal-phase-c`  
This branch was created on top of Phase B, which was on top of Phase A; **tip commit** should include **M010–M042** in `shared/canonical_schemas.py`. Always **verify the tip SHA** with `git log` before treating any hash in this document as authoritative.

---

## 1. Who this is for

- Operators on **Linux** using the **fish** shell (per tower guide).
- Two-tower deployment: run the same sequence on **Tower A**, then **Tower B**, and compare SHAs (see §8).

---

## 2. One-time fish helpers (copy per session)

These match the tower guide §0. They shorten Docker and script paths so you do not forget `-f docker-compose.local.yml` or `PYTHONPATH=/app`.

```fish
cd ~/captain-system

function dco
    docker compose -f docker-compose.yml -f docker-compose.local.yml $argv
end

function cap-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/$script $rest
end
```

**Why `/captain/scripts/`:** With `docker-compose.local.yml`, `./scripts` is mounted read-only at `/captain/scripts` **on `captain-offline`**. Always use **both** compose files for these commands.

---

## 3. Pull the migration branch to the repo

### 3.1 Preconditions

```fish
cd ~/captain-system
git status
```

**Safe to proceed** when `git status` shows a **clean** working tree (no unexpected modified tracked files). If you have local edits, stash or commit them first (tower guide §7.1 pattern):

```fish
git stash push -m "pre-decimal-merge local"
```

### 3.2 Fetch and check out the integration branch

**If the remote is `origin` (typical GitHub `captain-system`):**

```fish
cd ~/captain-system
git fetch origin
git checkout migration/decimal-phase-c
git pull origin migration/decimal-phase-c
```

**If your GitHub remote is named `multi-user` instead of `origin`:**

```fish
cd ~/captain-system
git fetch multi-user
git checkout migration/decimal-phase-c
git pull multi-user migration/decimal-phase-c
```

### 3.3 Confirm you are on the expected commit (both towers must match)

```fish
git branch --show-current    # expect: migration/decimal-phase-c
git rev-parse HEAD           # copy this SHA — Tower B must match before merge
git log --oneline -15        # expect migration(decimal) commits for phases A/B/C
```

**Pass criteria:** Branch name is **`migration/decimal-phase-c`**, and **`git rev-parse HEAD`** is the **same** on every machine that will vote on the merge.

---

## 4. Bring up Docker + apply schema (QuestDB must see M010–M042)

Migrations live in `shared/canonical_schemas.py` as `CANONICAL_MIGRATIONS`. They are applied by **`init_questdb.py`** (idempotent).

### 4.1 Full stack update (recommended on towers)

From repo root, if you use the project update script (pulls **main** by default — **skip** if you are only validating a feature branch without merging yet):

- For **validation-only** on the feature branch, **do not** run `captain-update.sh` unless you understand it may pull `main`. Prefer:

```fish
cd ~/captain-system
dco up -d --build
dco ps
```

Wait until **questdb** and **redis** are healthy (`dco ps` shows `Up` / `healthy`).

### 4.2 Apply DDL + migrations manually (required gate)

```fish
cap-run init_questdb.py
```

**Expected success output (representative):**

- No Python traceback.
- Log lines indicating tables / migrations processed; on re-run, idempotent “already exists” / skip behaviour is normal for QuestDB depending on version.

**Hard failure:** Lines containing `[FAIL]`, tracebacks, or migration SQL errors.  
→ See tower guide **§7.3**; fix DB or restore backup before merge.

### 4.3 Schema drift gate (exit code must be 0)

```fish
cap-run verify_schema_drift.py
echo $status
```

**Expected success (stdout, end of script):**

```text
PASS: all <N> canonical tables match live QuestDB schema
```

**Expected exit code:** `0` (in fish, `echo $status` prints `0` after success).

**Failure patterns (do not merge):**

- `MISSING (... tables not in QuestDB)`
- `DRIFT (... tables differ from canonical)`
- `FAIL: ... missing, ... drifted`

### 4.4 Health audit + smoke (recommended)

```fish
cap-run verify_questdb_state.py
cap-run health_smoke_test.py
```

**Pass criteria:**

- `verify_questdb_state.py`: **no unexpected CRITICAL** rows for your environment (review full output). Use `--strict` only if you intend WARN to fail: `cap-run verify_questdb_state.py --strict`.
- `health_smoke_test.py`: completes without traceback; exit code `0`.

---

## 5. Host-side Python: venv, `PYTHONPATH`, and missing dependencies (fish)

Host pytest is **faster** than `docker exec` but needs a venv and correct `PYTHONPATH` (tower guide §5 + §7.4–§7.5).

### 5.1 Create venv (first time only)

```fish
cd ~/captain-system
python3 -m venv .venv
source .venv/bin/activate.fish
```

**Fish note:** Use **`activate.fish`**, not `source .venv/bin/activate` (bash). If you see `command not found: source`, you are not in fish.

```fish
pip install --upgrade pip
pip install -r captain-offline/requirements.txt
pip install -r captain-online/requirements.txt
pip install -r captain-command/requirements.txt
pip install pytest pytest-asyncio psycopg2-binary
```

If **`pip install` fails** due to conflicting pins between services, use tower guide **§7.5**:

- **Option A:** Install missing wheels explicitly, e.g.  
  `pip install scipy hmmlearn pysignalr`
- **Option B:** Separate venvs per service (`/.venv-offline`, etc.).
- **Option C:** Skip host venv and run pytest **inside** `captain-offline` (§6).

### 5.2 Every new fish session (before `pytest`)

```fish
cd ~/captain-system
source .venv/bin/activate.fish
set -gx PYTHONPATH $PWD $PWD/captain-online $PWD/captain-offline $PWD/captain-command
set -gx QUESTDB_HOST 127.0.0.1
set -gx QUESTDB_PORT 8812
set -gx REDIS_HOST 127.0.0.1
set -gx REDIS_PORT 6379
```

**Fish note:** `set -gx VAR value` uses **spaces**, not `=`. Wrong: `set -gx PYTHONPATH=$PWD` (fish does not treat that like bash).

**Sanity check:**

```fish
echo $PYTHONPATH
python -c "import shared; import captain_online; import captain_offline; import captain_command; print('imports ok')"
```

**If `ModuleNotFoundError: No module named 'shared'`:** `PYTHONPATH` is wrong or venv not activated — re-run §5.2.

**If QuestDB connection errors during tests:** ensure Docker publishes **8812** to the host and questdb is `Up` (`dco ps`). For pytest **inside** the container, use **`QUESTDB_HOST=questdb`** (service name), not `127.0.0.1` (tower guide §7.6 / §5.6).

---

## 6. Pytest: two ways to run (host vs container)

### 6.1 Host (after §5.2)

From `~/captain-system` with venv + env vars:

**A. Fast gate (excludes heavy / fragile collectors — same spirit as tower guide §5.3)**

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

**B. Monetary migration–focused (unit + pure tests, no live DB for most)**

```fish
python -B -m pytest \
  tests/test_decimal_json.py \
  tests/test_phase_c_capital_history_json_roundtrip.py \
  tests/test_phase_c_e2e_pnl_precision.py \
  tests/test_circuit_breaker_decimal.py \
  tests/test_basket_pnl_precision.py \
  tests/test_d03_redis_roundtrip.py \
  tests/test_topstep_state_json_roundtrip.py \
  -v
```

**C. Live QuestDB tests (`real_questdb` — require QuestDB reachable on `QUESTDB_HOST`/`QUESTDB_PORT`)**

```fish
python -B -m pytest \
  tests/test_schema_migrations.py \
  tests/test_schema_d03_signal_id.py \
  tests/test_d08_decimal_roundtrip.py \
  tests/test_d23_d25_decimal_roundtrip.py \
  tests/test_d03_pnl_sum_precision.py \
  tests/test_phase_c_decimal_roundtrip.py \
  -v
```

**D. Kelly / B5C regression (validates Decimal silo + CB integration)**

```fish
python -B -m pytest tests/test_b4_kelly.py tests/test_b5c_circuit.py -v
```

### 6.2 Inside `captain-offline` (no host venv)

Use when host deps are painful (tower guide §5.6). **Note:** `QUESTDB_HOST` must be the **service name** `questdb`.

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T \
  -e PYTHONPATH=/app \
  -e QUESTDB_HOST=questdb \
  -e REDIS_HOST=redis \
  captain-offline \
  python -B -m pytest /app/tests/test_schema_migrations.py -v
```

Adjust the test path / list as needed. Confirm tests are mounted:  
`dco exec captain-offline ls /app/tests | head`.

---

## 7. Exact outputs that must look “green” before merge

### 7.1 `verify_schema_drift.py`

| Check | Pass | Fail |
|-------|------|------|
| Last line | `PASS: all <N> canonical tables match live QuestDB schema` | `FAIL:` or `DRIFT` or `MISSING` |
| Exit code | `0` | non-zero |

```fish
cap-run verify_schema_drift.py; echo $status
```

### 7.2 `init_questdb.py`

| Check | Pass | Fail |
|-------|------|------|
| Process | Completes, no Python traceback | `[FAIL]` on migration / traceback |

### 7.3 `pytest` (host or container)

| Check | Pass | Fail |
|-------|------|------|
| Summary line | `=== ... passed ... in ...` (e.g. `50 passed`) | `FAILED`, `ERROR`, exit non-zero |
| Exit code | `0` | `1`–`5` etc. |

Example passing tail:

```text
======================== 50 passed in 2.34s ========================
```

**Known harmless warning:** `PytestUnknownMarkWarning: Unknown pytest.mark.real_questdb` — informational if you have not registered the mark in `pytest.ini` (tower guide §5.4).

### 7.4 Optional SQL eyeball (QuestDB web console or `dco exec` + `psql` if you use it)

In **Web Console** (e.g. `http://127.0.0.1:9000`), run:

```sql
SHOW COLUMNS FROM p3_d08_tsm_state;
SHOW COLUMNS FROM p3_d03_trade_outcome_log;
SHOW COLUMNS FROM p3_d16_user_capital_silos;
SHOW COLUMNS FROM p3_d00_asset_universe;
SHOW COLUMNS FROM p3_d30_daily_ohlcv;
```

**Pass criteria (examples):** Monetary columns show **`DECIMAL`** with expected precision (e.g. `DECIMAL(18,2)`, `DECIMAL(14,4)`) per `MONETARY_DECIMAL_MIGRATION_PLAN.md` matrices — not legacy `DOUBLE` for those fields.

---

## 8. Two-tower parity before merging to `main`

Per tower guide §6:

| Step | Tower A | Tower B |
|------|---------|---------|
| Same branch | `migration/decimal-phase-c` | same |
| Same SHA | `git rev-parse HEAD` | **must match** A |
| Drift | `cap-run verify_schema_drift.py` → PASS | same |
| State audit | `cap-run verify_questdb_state.py` reviewed | same |
| Tests | At minimum §6.1 **B** + **C** + drift gate; add **A** for full regression | same |

When **both** towers show the **same `git rev-parse HEAD`** and all chosen gates pass, the rollout is aligned and you may proceed with the **human** merge approval process.

---

## 9. Merge to `main` (human decision — not automated here)

1. Ensure **CI** (if any) passes on the PR for `migration/decimal-phase-c`.
2. Complete **code review** and **sign-off** per your process.
3. Merge via GitHub **PR** (recommended) or:

```fish
git checkout main
git pull origin main
git merge --no-ff migration/decimal-phase-c
# resolve conflicts if any, then:
git push origin main
```

4. After merge, tag or document the **merge commit SHA** for production rollouts.

**Do not merge** if any of the following are true:

- `verify_schema_drift.py` does not print **`PASS: all ...`** or exits non-zero.
- `init_questdb.py` fails on **M010–M042** (or any migration) against a DB that should be migratable.
- Required pytest suites show **FAILED** / **ERROR**.
- Towers **A** and **B** are not on the **same** commit for the validated branch.

---

## 10. Quick troubleshooting pointer

| Symptom | See |
|---------|-----|
| `/captain/scripts/...` not found | Tower guide §7.2 — use **both** compose `-f` files |
| `shared` import error on host | §5.2 `PYTHONPATH` + `activate.fish` |
| `scipy` / `psycopg2` missing | §5.1 and tower guide §7.5 |
| QuestDB connection refused on host tests | §5.2 hosts/ports; use `questdb` inside container |
| `test_account_lifecycle.py` poisons collection | tower guide §7.7 — `--ignore=tests/test_account_lifecycle.py` |
| Migration `[FAIL]` | tower guide §7.3 |

---

## 11. Document history

| Item | Value |
|------|--------|
| Created for | Monetary DECIMAL migration merge validation |
| Fish + tower patterns | From `2026-04-28_tower_migration_guide_v2.md` |
| Branch | `migration/decimal-phase-c` (integration) |

---

*End of merge validation guide.*
