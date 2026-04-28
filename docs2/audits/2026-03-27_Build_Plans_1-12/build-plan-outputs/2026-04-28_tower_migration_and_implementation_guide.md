# Tower migration and implementation guide (Phases 1–11)

**Audience:** Operators bringing **GitHub-pushed** Captain System changes onto **two Linux towers**, using **fish** as the login shell.

**Scope:** Summarises every execution report in this folder, then gives **step-by-step** commands (fish-friendly) for **Tower A** and **Tower B**, including **QuestDB** migrations, **verification scripts**, and **pytest** against a live QuestDB.

---

## Part A — Summary of build execution summaries

The following files live in `build-plan-outputs/`; together they describe Phases 1–11 (plus Phase 2 naming as `build-plan-outputs_2026-04-phase2_execution.md`).


| Document                                                      | Status                           | What landed (high level)                                                                                                                                                                                      |
| ------------------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **2026-04-27_phase1_schema_migrations_execution_report.md**   | Complete in repo                 | `CANONICAL_MIGRATIONS` + `P2_D07_REGIME_MODELS`, D03 `model_m`, D22b rerun status, D26 comment ratification; `init_questdb.py` runs migrations; writers + `tests/test_schema_migrations.py` (`real_questdb`). |
| **build-plan-outputs_2026-04-phase2_execution.md**            | Partial (phase tests green)      | Persistence: combined BOCPD+CUSUM D04, DECAY_ALERT fields, paper trader `publish_to_stream`, `AIM_LIFECYCLE` version snapshots; new unit tests (`test_b5_sensitivity`, `test_b2_decay`, etc.).                |
| **2026-04-27_phase3_orchestrator_wiring_execution_report.md** | Complete except B2 blocked       | `SESSION_CLOSE` online→offline, quarterly CUSUM in-memory refresh, L3 immediate `AIM14_EXPANSION` dispatch; drift AE `bootstrap_fit` + `TODO[F-13]`; **B2 blend_signal blocked on Q-04**.                     |
| **phase_4_execution.md**                                      | Complete except 4b blocked       | DMA ACTIVE filter, HDWM diversity, single-gate AIM lifecycle, Redis suppression counters; **4b D06 event log blocked on Q-26**.                                                                               |
| **phase_5_execution.md**                                      | Complete                         | Redis `captain:bocpd:{asset}`, Kelly `_get_cp_prob` Redis-first, L2 refire delta, CUSUM nested calibration.                                                                                                   |
| **phase_6_execution.md**                                      | Partial                          | AIM-01/03/04/07 canvas alignment tests; **6.4 blocked on Q-23**; `test_b3_aim.py` extended.                                                                                                                   |
| **phase_7_execution.md**                                      | Complete (deferrals noted)       | D03 `signal_id`, D11/D06 columns, `shared/online_replay.py`, PG-09/10/12/13 pseudotrader path, `backfill_d03_signal_ids.py`; large `replay_engine.py` delete deferred to Phase 12.                            |
| **phase_8_execution.md**                                      | Complete                         | TSM Monte Carlo path, D12 `sizing_override`, RPT-07 Redis, CB regression arrays / OLS behaviour.                                                                                                              |
| **phase_9_execution.md**                                      | Complete (B5 optional skipped)   | Block 9 diagnostic: D3 uses D22b not global injection history; D4 monthly from D03 only; D7 removed; equal-weight `overall_health`.                                                                           |
| **phase_10_execution.md**                                     | Partial (env-limited full suite) | AIM-16 observation panel, HMM training/online inference, D26 merge semantics, MoE skips AIM-16.                                                                                                               |
| **phase_11_execution_summary.md**                             | Complete (11.3 skipped)          | Two-phase rollback (`request_rollback` / `commit_rollback`) with Redis proposals; `rollback_to_version` stub deprecated.                                                                                      |
| **2026-04-28_execution_summaries_vs_offline_audit_report.md** | Meta-audit                       | Cross-phase findings; calls out QuestDB-down test skips, `init_questdb.py` header “39 vs 41 tables”, `compact_questdb_tables.py` not covering D03/D11/D06.                                                    |
| **2026-04-28_amendment_questionnaire.md**                     | Questionnaire                    | Not an execution summary; governance / spec follow-ups.                                                                                                                                                       |


**Cross-cutting risks called out in those reports**

- Many tests need **QuestDB** on `**localhost:8812`** (host pytest) or `**QUESTDB_HOST=questdb**` inside Compose.
- `tests/test_account_lifecycle.py` **breaks collection** for other tests if run in the same pytest process (mocks `sys.modules["shared"]`). **Always ignore** it unless fixed.
- Some tests need **scipy / hmmlearn / pysignalr** (offline/online stack).

---

## Part B — Tower identity before you start

Do this mentally (and in `.env`) for **each** machine:


|                                      | Tower A (example)                                                                                                           | Tower B (example)    |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| **Role**                             | Primary / parity 0                                                                                                          | Secondary / parity 1 |
| `**INSTANCE_PARITY` in `.env`**      | `0`                                                                                                                         | `1`                  |
| **Trades**                           | Odd-indexed signal pattern per CLAUDE multi-instance                                                                        | Even-indexed         |
| **Git remote for “receive updates”** | Often `origin` on `captain-system`; client towers may use `multi-user` remote — **verify with `git remote -v`** on that box | Same                 |


**Rule:** Every command sequence below must be run **on Tower A**, then **repeated on Tower B** (or vice versa). Do not skip a tower unless it is intentionally out of service.

---

## Part C — One-time assumptions (fish shell, repo path)

The examples assume:

- Default shell is **fish**.
- Repository path is `~/captain-system` (adjust if yours differs).

**fish** syntax reminders used below:

```fish
# Persist env vars for the current shell session
set -gx VAR value

# Go to repo
cd ~/captain-system

# Run the project’s bash update script from fish (recommended)
bash scripts/captain-update.sh
```

If a step must be pure fish, it is written with `set` / `cd`; operational scripts shipped in-repo are **bash** (`captain-update.sh`, `captain-start.sh`) — call them with `bash ...` from fish.

---

## Part D — Pre-flight on each tower (every deployment)

Run **on Tower A**, then **on Tower B**.

### D1. Confirm you are in the right repo and branch

```fish
cd ~/captain-system
git status
git branch --show-current
git remote -v
```

**What this does:** Ensures you are on the intended branch (usually `main`) and shows whether `origin` or `multi-user` (or both) points at the GitHub repo you actually push to.

### D2. Confirm Docker and Compose work

```fish
docker --version
docker compose version
```

**What this does:** `captain-update.sh` uses `docker compose -f docker-compose.yml -f docker-compose.local.yml`.

**Mount detail (affects every `/captain/scripts/...` path):** In `docker-compose.local.yml`, `**./scripts` is bind-mounted read-only on `captain-offline` only** (`./scripts:/captain/scripts:ro`). That is why `captain-update.sh`, `captain-start.sh`, and this guide run `**init_questdb.py` / seeds / verify helpers via `docker compose ... exec captain-offline python /captain/scripts/...`**. If you ever run Compose **without** the local override, those paths may **not exist** inside the container — always use **both** compose files on the towers unless you have a documented production override that mounts `scripts/` the same way.

### D3. Confirm `.env` exists and parity is correct

```fish
test -f .env; and echo ".env: OK"; or echo ".env: MISSING — run bash scripts/captain-setup.sh"
grep INSTANCE_PARITY .env
```

**What this does:** `.env` is gitignored; without it, updates fail. `INSTANCE_PARITY` must differ between the two towers for alternate-signal routing.

---

## Part E — Pull GitHub changes and apply them (recommended path)

The repo ships `**scripts/captain-update.sh`**. It:

1. `git pull origin main` (see **E0** if your remote is not `origin`).
2. Warns if `.env.template` added new variables you must copy into `.env`.
3. Syncs `config/` into `captain-offline`, `captain-online`, `captain-command` `_config/` build contexts.
4. **Backs up** `questdb/db/` to `backups/questdb/questdb-pre-update-*.tar.gz`.
5. `docker compose ... up -d --build`.
6. Waits for QuestDB + Redis.
7. Runs `**init_questdb.py` inside `captain-offline`** (creates tables + **applies `CANONICAL_MIGRATIONS`** idempotently).
8. Runs `**seed_all_assets.py**` and the standard CSV seed scripts (idempotent append pattern).
9. Runs a **minimal row-count integrity** check via `psycopg2`.
10. Prints container health.

### E0. If your tower tracks `multi-user` instead of `origin`

`captain-update.sh` hard-codes `git pull origin main`. Before relying on it, run:

```fish
cd ~/captain-system
git remote -v
```

- If updates come from `**multi-user**`, either:
  - **Option 1 (quick):** temporarily run  
  `git pull multi-user main`  
  yourself, then run the update script with pull skipped:  
  `bash scripts/captain-update.sh --skip-pull`
  - **Option 2:** add `origin` as an alias URL pointing at the same GitHub repo as `multi-user`, or edit the script once locally (not ideal for drift).

**What this does:** Guarantees the working tree matches GitHub **before** images rebuild.

### E1. Standard update (both towers)

```fish
cd ~/captain-system
bash scripts/captain-update.sh
```

Watch for:

- `**New variables found in .env.template**` — merge those keys into `.env`, then re-run or restart services if needed.
- `**DATA INTEGRITY CHECK FAILED**` — do **not** trade; follow the script’s printed restore steps from `backups/questdb/`.

### E2. Alternative: `captain-start.sh` (local dev parity)

`bash captain-start.sh --build` is documented in `CLAUDE.md` for WSL-style dev; towers may still prefer `captain-update.sh` because it bundles pull, backup, init, and seeding.

---

## Part F — QuestDB migration mechanics (what actually applies schema)


| Mechanism                         | What it does                                                                                                                                        |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `**shared/canonical_schemas.py`** | Single source of truth: `CANONICAL_DDLS` (CREATE TABLE) + `**CANONICAL_MIGRATIONS**` (ALTER / additive).                                            |
| `**scripts/init_questdb.py**`     | Creates missing tables from `CANONICAL_DDLS`, then runs each `**CANONICAL_MIGRATIONS**` entry with idempotent `[OK]` / `[SKIP]` / `[FAIL]` logging. |
| `**scripts/captain-update.sh**`   | After rebuild, runs `init_questdb.py` **inside** the `captain-offline` container with `PYTHONPATH=/app`.                                            |


**Important:** `init_all.py` also creates tables (used in manual Phase-1 style setups); `captain-update.sh` uses `**init_questdb.py`** directly for routine updates.

### F1. Manual migration run (if you did not use `captain-update.sh`)

```fish
cd ~/captain-system
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline \
  python /captain/scripts/init_questdb.py
```

**What this does:** Same as the update script’s Step 6 — safe to run multiple times.

**Host alternative (no container path):** from repo root, with QuestDB port `8812` published and `pip install -r …` deps available:

```fish
cd ~/captain-system
set -gx PYTHONPATH $PWD:$PWD/captain-offline
set -gx QUESTDB_HOST 127.0.0.1
set -gx QUESTDB_PORT 8812
python scripts/init_questdb.py
```

**What this does:** Same Python entrypoint as the container; uses `shared.questdb_client` against the host-mapped port.

### F2. Legacy D03 rows: `signal_id` backfill (Phase 7)

If this tower had **trade rows written before `signal_id` existed**, run **once** after migrations (idempotent):

```fish
cd ~/captain-system
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline \
  python /captain/scripts/backfill_d03_signal_ids.py
```

**What this does:** For each D03 row with NULL/empty `signal_id`, re-inserts the row with `LEGACY-<uuid>` via QuestDB DEDUP upsert semantics (see script docstring).

Dry-run:

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline \
  python /captain/scripts/backfill_d03_signal_ids.py --dry-run
```

`captain-update.sh` does **not** invoke this automatically — **you** decide per tower based on history.

### F3. Compaction (ongoing ops, not Phase 7 DDL)

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline \
  python /captain/scripts/compact_questdb_tables.py
```

**What it does:** Trims append-only bloat for **D01, D02, D05, D12, D25** only — **not** D03/D11/D06 (Phase 7 execution summary: migrations handle those).

---

## Part G — Verify QuestDB and “system ready” after an update

Run these **on each tower** after a successful compose cycle.

### G1. Schema vs canonical code (drift check)

```fish
cd ~/captain-system
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline \
  python /captain/scripts/verify_schema_drift.py
```

**What it does:** Compares live QuestDB columns to `CANONICAL_DDLS` in code; exits `1` on mismatch.

### G2. Bootstrap / production health report

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline \
  python /captain/scripts/verify_questdb_state.py
```

**What it does:** Large structured audit (counts, freshness, loop liveness). Use `--json` or `--report file.md` as needed. `--strict` fails on WARN.

### G3. Legacy table/column smoke (`verify_questdb.py`)

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline \
  python /captain/scripts/verify_questdb.py
```

**What it does:** Older “expected columns” checklist for major tables — useful smoke test; may be less complete than `verify_schema_drift.py` for new Phase 1/7 columns.

### G3b. Connectivity + scratch write test

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline \
  python /captain/scripts/health_smoke_test.py
```

**What it does:** Wait for DB, read one row from critical tables, run a dedup replace on `p3_smoke_scratch`.

### G4. Optional SQL eyeballs (QuestDB console)

Open `http://127.0.0.1:9000` on the tower (if bound locally) and run examples from Phase 1 report:

- `SHOW COLUMNS FROM p2_d07_regime_models;`
- `SHOW COLUMNS FROM p3_d03_trade_outcome_log;` — expect `signal_id`, `model_m`
- `SHOW COLUMNS FROM p3_d22b_asset_rerun_status;`
- `SHOW COLUMNS FROM p3_d26_hmm_opportunity_state;`

---

## Part H — Pytest from the Linux host (QuestDB + PYTHONPATH)

On the **host** (not inside the container), QuestDB is usually reachable at `**127.0.0.1:8812`** when port-forwarded by Compose.

### H1. Activate venv and set `PYTHONPATH` (fish)

```fish
cd ~/captain-system
source .venv/bin/activate.fish   # if your venv is .venv
set -gx PYTHONPATH $PWD:$PWD/captain-online:$PWD/captain-offline:$PWD/captain-command
set -gx QUESTDB_HOST 127.0.0.1
set -gx QUESTDB_PORT 8812
```

**What this does:** Matches `CLAUDE.md` test layout; `questdb_client` reads `QUESTDB_`*.

### H2. Fast gate (no full DB, avoids known poisoned test)

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

**What this does:** CLAUDE “block-level” recommendation; exercises most logic without the heaviest integration tests.

### H3. Live QuestDB schema tests (`real_questdb`)

With QuestDB **running** and ports exposed:

```fish
python -B -m pytest tests/test_schema_migrations.py -v
python -B -m pytest tests/test_schema_d03_signal_id.py -v
```

**What this does:** Phase 1 / Phase 7 DDL + migration checks. Tests marked `real_questdb` talk to the real DB (`conftest` disables cursor mocks for them).

**Note:** Pytest may warn `real_questdb` is unknown unless registered in config — warnings only unless you promote them to errors.

### H4. Phase-targeted suites (from execution reports)

```fish
# Phase 9 diagnostics
python -B -m pytest tests/test_b9_diagnostic_phase9.py -v

# Phase 10 HMM / observation panel cluster
python -B -m pytest tests/test_aim16_observation_panel.py tests/test_aim16_hmm_train.py \
  tests/test_hmm_online_inference.py tests/test_d26_hmm_round_trip.py tests/test_hmm_phase10_e2e.py -q

# Phase 11 rollback
python -B -m pytest tests/test_version_rollback_two_phase.py tests/test_version_snapshot_coverage.py -q
```

### H5. Redis-dependent runtime

Several batches (BOCPD mirror, rollback proposals, Kelly) need **Redis** at `127.0.0.1:6379` for full behaviour; integration tests may still skip or mock. Ensure the `redis` service from Compose is up when running broader suites.

---

## Part I — Script catalog (`scripts/*.py`): what each script does


| Script                                                    | Purpose                                                                                                             |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `init_questdb.py`                                         | Apply `CANONICAL_DDLS` + `**CANONICAL_MIGRATIONS`**.                                                                |
| `init_all.py`                                             | Wait for QuestDB/Redis, create tables (DDL loop), SQLite journals, seed baseline paths — “full Phase 1” style init. |
| `init_sqlite.py`                                          | Create per-process SQLite WAL journals (imported by `init_all`).                                                    |
| `backfill_d03_signal_ids.py`                              | Assign `LEGACY-*` `signal_id` to old D03 rows (Phase 7).                                                            |
| `compact_questdb_tables.py`                               | Compact D01/D02/D05/D12/D25 append-only history.                                                                    |
| `verify_schema_drift.py`                                  | Diff live QuestDB vs canonical DDLs; fail on drift.                                                                 |
| `verify_questdb.py`                                       | Legacy column smoke test for major P3 tables.                                                                       |
| `verify_questdb_state.py`                                 | Full readiness / health audit report (CLI args for JSON/report/strict).                                             |
| `health_smoke_test.py`                                    | Connectivity + read + dedup scratch write.                                                                          |
| `verify_bootstrap.py`                                     | Session C bootstrap verification helper.                                                                            |
| `bootstrap_production.py`                                 | Populate D00/D16/D02/D25 style gaps from env-driven account/silo config.                                            |
| `bootstrap_opening_volumes.py`                            | Fill D29 from Topstep historical bars.                                                                              |
| `seed_all_assets.py`                                      | Full multi-asset seed orchestration (used by `captain-update.sh`).                                                  |
| `seed_system_params.py`                                   | D17 and related parameter seed.                                                                                     |
| `seed_test_asset.py`                                      | Minimal test asset seed.                                                                                            |
| `seed_real_asset.py`                                      | Seed one real asset from packaged data bridges.                                                                     |
| `seed_ohlcv_from_qc.py`                                   | D30 daily OHLCV from QC CSV extracts.                                                                               |
| `seed_iv_rv_from_extract.py`                              | D31 IV/RV features.                                                                                                 |
| `seed_skew_from_extract.py`                               | D32 skew.                                                                                                           |
| `seed_opening_vol_from_qc.py`                             | D33 opening vol.                                                                                                    |
| `seed_or_volumes_from_qc.py`                              | D29 opening volumes from QC 1m extracts.                                                                            |
| `paper_trader.py`                                         | Simulated trading loop; writes D03 with `signal_id` / `model_m`; publishes stream outcomes.                         |
| `patch_tp_sl_multiple.py`                                 | Per-tower D00 TP/SL multiple patch (README in file).                                                                |
| `fix_locked_strategies.py`                                | Repair corrupted `locked_strategy` JSON in D00.                                                                     |
| `fix_bootstrap_data.py`                                   | Correct bootstrap data anomalies (see file header).                                                                 |
| `load_p2_multi_asset.py`                                  | Stage P2 multi-asset artefacts into `data/`.                                                                        |
| `restore_live_delta.py`                                   | Re-apply tower-captured deltas atop committed seeds.                                                                |
| `backup_live_tables.py`                                   | CSV export of live-written market tables before destructive ops.                                                    |
| `aim_ab_test.py`                                          | AIM A/B replay statistics harness.                                                                                  |
| `replay_session.py`                                       | CLI helper around replay session driver.                                                                            |
| `replay_full_pipeline.py`                                 | Full pipeline replay entry.                                                                                         |
| `run_pseudotrader_backtest.py`                            | Pseudotrader backtest driver.                                                                                       |
| `generate_d22_trades.py`                                  | Build D-22 JSON from QC extracts.                                                                                   |
| `generate_d02_regime_labels.py`                           | Build regime labels JSON.                                                                                           |
| `update_vix_daily.py`                                     | Refresh VIX/VXV CSVs from Yahoo.                                                                                    |
| `roll_calendar_update.py`                                 | Contract roll calendar maintenance.                                                                                 |
| `verify_topstep_integration.py`                           | REST/WebSocket integration smoke for TopstepX.                                                                      |
| `test_bracket_order.py`                                   | Live bracket order placement test (real broker risk).                                                               |
| `inject_test_signal.py`                                   | Inject synthetic signal via Redis.                                                                                  |
| `run_canvas_audit.py`                                     | Canvas/spec audit helper.                                                                                           |
| `run_audit_execution.py`                                  | Audit execution runner.                                                                                             |
| `extract_vix_vxv_cell.py` / `decode_vix_vxv.py`           | VIX cell extraction helpers.                                                                                        |
| `sat_013_gpr_fetch.py` / `sat_014_google_trends_fetch.py` | SAT data fetch scripts.                                                                                             |


**Shell wrappers (same folder):**


| Script              | Purpose                                                                                            |
| ------------------- | -------------------------------------------------------------------------------------------------- |
| `captain-update.sh` | Pull (if not skipped), backup QuestDB, rebuild compose, `init_questdb.py`, seeds, integrity check. |
| `captain-setup.sh`  | Interactive first-machine setup (`CLAUDE.md`).                                                     |


---

## Part J — Checklist: “both towers done”

For **each** tower, tick all:

1. [ ] `git pull` from the correct remote/branch (or `captain-update.sh` with matching remote behaviour — **E0**).
2. [ ] `bash scripts/captain-update.sh` completed without integrity failure — or manual compose + `init_questdb.py` equivalent.
3. [ ] `.env` parity (`0` vs `1`) verified.
4. [ ] Optional: `backfill_d03_signal_ids.py` if legacy D03 exists.
5. [ ] `verify_schema_drift.py` **exit 0**.
6. [ ] `verify_questdb_state.py` reviewed (no unexpected CRITICAL).
7. Host pytest: at least **CLAUDE.md** ignore list (**H2**); add **H3** when QuestDB up.
8. [ ] Spot-check GUI/API and one Captain log line per process after restart.

When both towers pass the checklist with the **same commit SHA** (`git rev-parse HEAD`), the rollout is aligned.

---

## References in-repo

- Architecture, ports, test invocation: `CLAUDE.md`
- Multi-instance parity and `captain-update.sh` / `multi-user` remote: `CLAUDE.md` § Multi-Instance Deployment
- Canonical DDL/migrations: `shared/canonical_schemas.py`
- Connection env vars: `shared/questdb_client.py`

