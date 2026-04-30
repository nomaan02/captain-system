# Tower Test Runbook — Decimal Boundary Consolidation Pull

**Date:** 2026-04-30
**Shell:** fish (Linux towers)
**Branch:** `main`
**Commits being pulled:** `03de644 → 1910f71 → 9659b4c → 5681fb6 → dbe550b` (5 commits, fast-forward)

This runbook is what each tower runs after the agent pushes to both remotes. **Run on Tower A first, validate green, then Tower B.** Both towers must end on the same `git rev-parse HEAD` before market open.

---

## Section 0 — One-time fish setup (skip if already done before)

These two function definitions live in your shell session. You can paste them once per session, or add to `~/.config/fish/config.fish` to make them permanent.

```fish
cd ~/captain-system

function dco
    docker compose -f docker-compose.yml -f docker-compose.local.yml $argv
end

function cap-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/$script $rest
end
```

### One-time host venv setup (only if you do not already have `~/captain-system/.venv`)

```fish
cd ~/captain-system
python3 -m venv .venv
source .venv/bin/activate.fish
pip install --upgrade pip
pip install -r captain-offline/requirements.txt
pip install -r captain-online/requirements.txt
pip install -r captain-command/requirements.txt
pip install pytest pytest-asyncio psycopg2-binary
```

If you already have `~/captain-system/.venv` from previous work, **skip the create+install step** — just activate and set env vars per Section 2.

---

## Section 1 — Pull the changes

### 1.1 Pre-pull state check

```fish
cd ~/captain-system
git status
git branch --show-current
git rev-parse HEAD
```

**Expected before pull:**
- `On branch main`
- Working tree clean (or only untracked `claude-mem/`, `questdb-*.tar.gz` — those are local artefacts and stay).
- `git rev-parse HEAD` shows the commit you were on yesterday.

If `git status` shows **modified tracked files** you did not expect, stop and report — the deploy is not safe to proceed.

### 1.2 Pull from your tower's preferred remote

Most towers track `origin` (the `captain-system` repo). The agent pushed to **both** remotes, so either works:

```fish
git pull origin main --ff-only
```

OR if your tower tracks `multi-user`:

```fish
git pull multi-user main --ff-only
```

**Expected output:**
```
Updating <old>..dbe550b
Fast-forward
 [...several files listed...]
 23 files changed, ~1700 insertions(+), ~250 deletions(-)
```

### 1.3 Confirm both towers will end on the same commit

```fish
git rev-parse HEAD
```

**Pass:** prints `dbe550bb...` (the Phase 4 SHA). Compare against the other tower — must be identical.

**Fail:** different SHAs → one tower is behind. Re-run `git pull origin main --ff-only` on the lagging tower until both match.

---

## Section 2 — Run the static test gate (host venv, no Docker required)

### 2.1 Activate venv + set env

```fish
cd ~/captain-system
source .venv/bin/activate.fish
set -gx PYTHONPATH $PWD $PWD/captain-online $PWD/captain-offline $PWD/captain-command
set -gx QUESTDB_HOST 127.0.0.1
set -gx QUESTDB_PORT 8812
set -gx REDIS_HOST 127.0.0.1
set -gx REDIS_PORT 6379
```

**Sanity check:**
```fish
python -c "import shared; from shared.decimal_boundary import as_money, to_float; print('imports ok')"
```

**Expected:** `imports ok`

**Fail:** `ModuleNotFoundError: No module named 'shared'` → re-run the `set -gx PYTHONPATH ...` line.

### 2.2 Phase 1+2+3+4 regression suite (the meat)

```fish
python -B -m pytest \
    tests/test_decimal_boundary.py \
    tests/test_b6_decimal_d08_boundary.py \
    tests/test_reconciliation_decimal_boundary.py \
    tests/test_tsm_simulation_decimal_input.py \
    tests/test_kelly_fee_schedule_decimal.py \
    tests/test_decimal_boundary_lint.py \
    tests/test_b4_kelly.py \
    tests/test_b5c_circuit.py \
    tests/test_b7_pnl_per_symbol.py \
    -v
```

**Expected (last lines):**
```
============= 121 passed in ~3s =============
```

**Fail:** Any `FAILED` line → patch is not loaded. Re-run `git status` to confirm working tree is clean and `git rev-parse HEAD` matches `dbe550b...`. If both correct and tests still fail, see Section 5.

### 2.3 Lint gate alone (verify CI guard active)

```fish
python -B -m pytest tests/test_decimal_boundary_lint.py -v
```

**Expected:** `1 passed`

This means the lint script ran and found 0 violations across the whole repo. Future PRs that re-introduce the antipattern will fail this test.

### 2.4 Full fast gate (all unit tests, ~2 minutes)

```fish
python -B -m pytest tests/ -q \
    --ignore=tests/test_integration_e2e.py \
    --ignore=tests/test_pipeline_e2e.py \
    --ignore=tests/test_pseudotrader_account.py \
    --ignore=tests/test_offline_feedback.py \
    --ignore=tests/test_stress.py \
    --ignore=tests/test_account_lifecycle.py
```

**Expected (last line):** `~506 passed, ~23 failed, ~18 skipped`

The ~23 "failed" are pre-existing tests that need a **live QuestDB** (psycopg2 `OperationalError: connection refused`). They are not related to this work and were failing on the laptop before the changes too. As long as the count is ≤ 23 and the failure messages are all `psycopg2.OperationalError`, the gate is green.

**True regression:** Any non-`OperationalError` failure → stop and report.

---

## Section 3 — Bring up the stack + apply schema (Docker)

This re-applies any pending schema migrations and rebuilds the captain-online image so it picks up the patched `b1_data_ingestion.py` / `b6_signal_output.py` / `orchestrator.py`.

### 3.1 Restart the stack with the new code

```fish
cd ~/captain-system
dco up -d --build
sleep 10
dco ps
```

**Expected:** All 9 services show `Up` or `Up (healthy)`.

### 3.2 Apply schema (idempotent — should be a no-op since no DDL changes in these commits)

```fish
cap-run init_questdb.py
```

**Expected:** No traceback. "All tables created" or idempotent skip messages.

### 3.3 Verify schema drift gate still passes

```fish
cap-run verify_schema_drift.py
echo $status
```

**Expected:** `PASS: all <N> canonical tables match live QuestDB schema` and `0`.

---

## Section 4 — Live producer-side type-purity tests (against the actual tower QuestDB)

These three test files were marked `@pytest.mark.real_questdb` and skipped in the static gate above. With the live QuestDB up, run them now.

```fish
cd ~/captain-system
source .venv/bin/activate.fish
set -gx PYTHONPATH $PWD $PWD/captain-online $PWD/captain-offline $PWD/captain-command
set -gx QUESTDB_HOST 127.0.0.1
set -gx QUESTDB_PORT 8812

python -B -m pytest \
    tests/test_tsm_config_type_purity.py \
    tests/test_user_silo_type_purity.py \
    tests/test_active_assets_type_purity.py \
    -v
```

**Expected:** `3 passed` (or `3 skipped` if QuestDB on the host is unreachable from the venv — in that case run inside the container instead, see Section 5).

These tests insert a known-zero-drawdown row into D08, call `_load_tsm_configs`, and assert every monetary field comes back as `Decimal` (not float). Same for D16 and D00. If they pass, the production code path is type-pure end-to-end.

---

## Section 5 — Pre-market dry-run validation (the gold standard)

This exercises the full B1 → B5C pipeline against the live QuestDB without publishing signals. It would have caught both the 2026-04-29 B4 crash AND today's 2026-04-30 B6 crash had it been run before market open.

### 5.1 Run inside the captain-online container

```fish
dco exec -T -e PYTHONPATH=/app captain-online \
    python -u /app/dry_run_phase_a.py 1
```

(`1` = NY session. Use `2` for LON, `3` for APAC.)

**Expected (final lines):**
```
================================================================
DRY RUN COMPLETE: PASS
================================================================
silo_<user_id>: PASS
b1_<asset>: PASS  (×10 assets)
b2: PASS
b3: PASS
b4: PASS                    ← 2026-04-29 B4 crash site (fixed in 4c225c0)
b5: PASS
b5b: PASS
b5c: PASS
================================================================
```

**Fail diagnostics:**

| Output line | Cause | Fix |
|---|---|---|
| `b4: FAIL` with `TypeError: ... 'decimal.Decimal' and 'float'` | Phase 1 patch not loaded | `git pull` + `dco up -d --build` again |
| `b1_<asset>: FAIL` with `Decimal('0.00') was returned as float` | Producer-side fix not loaded | Same |
| `silo_<user>: FAIL` with `NoneType` on `total_capital` | D16 capital silo not bootstrapped | `cap-run bootstrap_production.py` |
| `b1_<asset>: WARN  data_quality_flag != CLEAN` | Acceptable for warm-up assets — not blocking |

### 5.2 Run for all three sessions

```fish
for s in 1 2 3
    echo "=== Session $s ==="
    dco exec -T -e PYTHONPATH=/app captain-online \
        python -u /app/dry_run_phase_a.py $s
end
```

All three should print `DRY RUN COMPLETE: PASS`.

---

## Section 6 — Cross-tower SHA parity check

Before market open, **both towers must show the same `git rev-parse HEAD`**.

On Tower A:
```fish
cd ~/captain-system
git rev-parse HEAD
```

On Tower B:
```fish
cd ~/captain-system
git rev-parse HEAD
```

**Pass:** Both print `dbe550b...` (or the same later SHA if more was pushed).

**Fail:** Different SHAs → one tower lagging. `git pull origin main --ff-only` on the laggard.

---

## Section 7 — Production smoke after market open (first trade outcome)

After the first signal triggers a trade outcome, verify reconciliation no longer silently fails:

```fish
dco logs --tail=200 captain-command | grep -E "RECONCIL|CRITICAL"
```

**Expected:** No CRITICAL reconciliation failures. If broker balance vs system balance ever diverges by > $1, you should see a `RECONCILIATION` notification in the GUI (priority MEDIUM) — never silent.

If you see `CRITICAL reconciliation failure for account X: <error>`, that means the new loud-failure path triggered — investigate the underlying error. Previously this was hidden by the bare `except`.

---

## Section 8 — Quick troubleshooting

| Symptom | Action |
|---------|--------|
| `git pull` rejects with "diverged" | `git status` to inspect. If the local commits are old/untracked artefacts, stash or discard them. Never force-push to main from a tower. |
| Tests fail with `ModuleNotFoundError: shared` | Re-run `set -gx PYTHONPATH ...` from Section 2.1. |
| `dco up -d --build` hangs on `captain-online` | Check `dco logs captain-online`. Likely Python import error from a half-applied patch — re-checkout main and rebuild. |
| `cap-run init_questdb.py` says `[FAIL]` | See `docs2/audits/2026-03-27_Build_Plans_1-12/build-plan-outputs/2026-04-28_tower_migration_guide_v2.md` §7.3. |
| Lint test fails locally on tower | Should never happen — the lint passed at commit time. If it does, `python scripts/lint_decimal_boundary.py` to see file:line. |
| `dry_run_phase_a.py` crashes at B6 | Phase 1 patch not loaded. `git rev-parse HEAD` should equal `dbe550b...` or later. |

---

## Definition of done

Tower is ready for market open when **all five** of these are green:

1. `git rev-parse HEAD` matches the other tower
2. `git rev-parse HEAD` is `dbe550b...` or later
3. `cap-run verify_schema_drift.py` exit `0` with `PASS: all ...`
4. Section 2.2 regression suite: `121 passed`
5. Section 5.1 dry run: `DRY RUN COMPLETE: PASS` for sessions 1, 2, 3

If any of those five is red, **do not enable AUTO_EXECUTE** for the next session.
