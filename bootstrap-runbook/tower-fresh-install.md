# Tower Fresh-Install Runbook — QuestDB Canonical Schema

**Audience:** Tower 1 (nomaan) and Tower 2 (isaac) operators.
**Branch:** `migration/fresh-start-bootstrap`
**Shell:** fish (Ubuntu).
**Assumption:** both towers already run Docker, Docker Compose v2, Python 3.10+, fish, and have a cloned checkout at `~/captain-system`.

This runbook wipes QuestDB + Redis state and rebuilds both from the canonical
schemas in `shared/canonical_schemas.py`. It is **identical** for both towers —
no hard-coded usernames or hostnames. Fish expands `(whoami)` / `(hostname)` at
run-time, so the same commands produce tower-appropriate paths.

**Pre-requisite:** Session D local validation has PASSED against
`captain-local-qdb` (see `.bootstrap-state.md § Local validation`). Do not run
this on a tower until the repo branch is merged.

---

## 0. Pre-flight (5 minutes)

Run every check; abort if anything fails.

```fish
cd ~/captain-system
git fetch --all
git checkout main                                # or migration/fresh-start-bootstrap before merge
git pull --ff-only
git log -1 --oneline                             # confirm expected commit

# Disk budget — need headroom for a fresh QuestDB volume + tarball
df -h /
df -h ~/captain-system                           # data volumes

# Required env vars present in .env
test -f .env; or echo "MISSING .env"
for v in TOPSTEP_USERNAME TOPSTEP_API_KEY TOPSTEP_ACCOUNT_NAME VAULT_MASTER_KEY \
         JWT_SECRET_KEY API_SECRET_KEY QUESTDB_USER QUESTDB_PASSWORD REDIS_PASSWORD \
         BOOTSTRAP_ACCOUNT_ID BOOTSTRAP_USER_ID BOOTSTRAP_STARTING_CAPITAL \
         CAPTAIN_COMPACTION_ENABLED
    grep -q "^$v=" .env; or echo "MISSING $v"
end

# Capture current crontab (restored at the end — NOT re-installed from deploy/)
crontab -l > /tmp/cron-(hostname)-pre.txt
wc -l /tmp/cron-(hostname)-pre.txt               # expect 3 non-comment lines

# Seed-file existence (abort if any fail — no fresh install without these)
set -l seed_files \
    data/seed/aim_data/ohlcv_combined.csv \
    data/seed/aim_data/es_iv_rv.csv \
    data/seed/aim_data/es_skew.csv \
    data/seed/aim_data/vix_daily.csv \
    data/seed/aim_data/vxv_daily.csv
for asset in ES MES NQ MNQ M2K MYM NKD MGC ZB ZN
    set seed_files $seed_files data/seed/aim_data/ohlcv_$asset.csv
    set seed_files $seed_files data/seed/or_volume_data/{$asset}_or_volume.csv
end
for f in $seed_files
    test -f $f; or echo "MISSING $f"
end

# Confirm P1/P2 research outputs still present (used by seed_all_assets.py)
test -d data/p1_outputs; or echo "MISSING data/p1_outputs"
test -d data/p2_outputs; or echo "MISSING data/p2_outputs"

# Tower cron service must be live before we finish — record current state
systemctl is-active cron
```

If any `MISSING …` line prints — STOP. Fix before proceeding.

---

## 1. Backup (2 minutes)

Snapshot QuestDB and Redis data volumes so the wipe is reversible for ~24 h.

```fish
set -l stamp (date +%Y%m%d-%H%M%S)
mkdir -p ~/backups
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
tar -czf ~/backups/questdb-preinstall-$stamp.tar.gz -C ~/captain-system questdb/
tar -czf ~/backups/redis-preinstall-$stamp.tar.gz -C ~/captain-system redis/
ls -lh ~/backups/ | tail -5
```

Confirm both archives exist and are non-empty.

### 1a. Export tower-collected live-table delta (1 minute)

The committed seed CSVs under `data/seed/` are refreshed manually and lag the
live tables by ~3 weeks (the "seed frontier"). Every day between that frontier
and now has been written to QuestDB by `b1_features.py` and is NOT in any
committed file — the wipe would lose it. Dump the four live-written tables
to CSV so §6 can restore the delta after the seed chain finishes.

Host-side scripts need `psycopg2` + `redis` and the `.env` loaded into the
shell. Do this once per session (it also primes §5 / §6):

```fish
# One-time venv setup (first install only)
python3 -m venv ~/.venv-captain
~/.venv-captain/bin/pip install 'psycopg2-binary>=2.9' 'redis>=5.0'

# Per-session env load — .env into fish + point Python at the host QuestDB
cd ~/captain-system
for line in (grep -v '^#' .env | grep -v '^\s*$')
    set -l parts (string split -m 1 = $line)
    set -x $parts[1] $parts[2]
end
set -x QUESTDB_HOST 127.0.0.1
set -x QUESTDB_PORT 8812
set -x REDIS_HOST 127.0.0.1
set -x REDIS_PORT 6379
set -x PYTHONPATH ~/captain-system

# Sanity — must print "yes"
test -n "$QUESTDB_PASSWORD"; and echo "QUESTDB_PASSWORD: yes"; or echo "QUESTDB_PASSWORD: NO"
```

```fish
# While QuestDB is still running (before §3 teardown).
~/.venv-captain/bin/python3 scripts/backup_live_tables.py --backup-root ~/captain-backups
```

Expected output: `[OK] p3_d30_daily_ohlcv: N rows`, same for d29, d33,
spread_history. Record the `live-tables-<stamp>` directory name printed at
the top — §6 needs it. A fresh tower (no post-seed activity yet) will print
0 rows for every table; that is fine and the restore in §6 becomes a no-op.

---

## 2. Pause crons (30 seconds)

Prevent the 02:00 QuestDB-backup cron and the 22:00 VIX cron from firing into
a half-initialised system.

```fish
crontab -l | sed 's/^\([^#]\)/#\1/' | crontab -
crontab -l                                       # confirm every line is commented
```

---

## 3. Full stack teardown (1 minute)

```fish
cd ~/captain-system
docker compose -f docker-compose.yml -f docker-compose.local.yml down

# Wipe QuestDB state. Redis AOF is kept (non-destructive) unless the operator
# explicitly wants a full reset; Redis has no schema to drift.
sudo rm -rf questdb/db questdb/conf questdb/log questdb/public questdb/snapshot
mkdir -p questdb
```

Do NOT remove `questdb/` itself — the bind-mount points there; `rm -rf questdb/`
will break the mount until the directory is recreated.

---

## 4. Build + start infra-only (3–5 minutes)

Bring up QuestDB + Redis first; hold captain-* back until init_all succeeds.

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build questdb redis

# Wait for QuestDB HTTP to answer
set -l max 60
while test $max -gt 0
    curl -sf -o /dev/null "http://127.0.0.1:9000/exec?query=SELECT+1"; and break
    sleep 1
    set max (math $max - 1)
end
test $max -gt 0; or begin; echo "QuestDB never became ready"; exit 1; end

docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" ping
```

The captain-system-redis-1 container name follows Docker Compose's default
project-prefix rule; adjust if your project name differs (`docker compose ps`
shows the real names).

---

## 5. Initialise canonical schema + bootstrap (2 minutes)

Scripts run on the **host** (via the `~/.venv-captain` created in §1a), not
inside a container, because captain-command does not mount `./scripts`. If
you started a fresh fish session since §1a, re-run the env-load block from
there before continuing.

```fish
set -l py ~/.venv-captain/bin/python3
$py scripts/init_all.py                          # 39 canonical tables + SQLite journals + D17 + test seed
$py scripts/bootstrap_production.py              # D00 × 10, D16 silo, D02 × 60, D25 × 1
$py scripts/verify_schema_drift.py               # must print "PASS: all 39 canonical tables match"
$py scripts/verify_bootstrap.py                  # must print "PASS: D00 10 assets, D16 primary_user, D02 60 rows, D25 …"
$py scripts/health_smoke_test.py                 # must print "PASS: QuestDB reachable, 7 critical tables readable, scratch …"
```

Any non-PASS output — STOP, investigate, do not proceed to seeding.

---

## 6. Seed historical data (10–15 minutes)

Dependency order is fixed per `.seed-audit.md § 6`. Do not re-order.

```fish
set -l py ~/.venv-captain/bin/python3
$py scripts/seed_all_assets.py                   # D00 to 17 assets, D01/D04/D05/D12 from P1/P2
$py scripts/seed_ohlcv_from_qc.py                # D30 ≈ 2,829 rows
$py scripts/seed_iv_rv_from_extract.py           # D31 = 122 rows (ES only)
$py scripts/seed_skew_from_extract.py            # D32 = 81 rows  (ES only)
$py scripts/seed_or_volumes_from_qc.py           # D29 = 240 rows
$py scripts/seed_opening_vol_from_qc.py          # D33 = 240 rows
$py scripts/seed_system_params.py                # D17 = 43 rows
$py scripts/roll_calendar_update.py --update     # D00 roll_calendar + config/contract_ids.json
```

Row counts must land within ±5 % of the expected values above.

### 6a. Restore post-frontier delta from §1a backup (1 minute)

Re-inserts the rows the tower collected between the committed seed frontier
and the wipe. Filters §1a's CSVs per-asset against `data/seed/`'s max date and
INSERTs only the strictly-newer rows. `spread_history` has no committed seed
and is restored wholesale — DEDUP `UPSERT KEYS(timestamp, asset_id, session_id)`
naturally collapses duplicates. D29/D30 use the session/trade date as the ts,
making the restore idempotent under re-runs (DEDUP collapses on the stable key).

```fish
set -l py ~/.venv-captain/bin/python3
# Resolve the most-recent backup dir produced in §1a.
set -l backup_dir (ls -dt ~/captain-backups/live-tables-* | head -1)
echo "Restoring delta from: $backup_dir"

$py scripts/restore_live_delta.py --backup-dir $backup_dir --dry-run
$py scripts/restore_live_delta.py --backup-dir $backup_dir
```

Dry-run reports rows-that-would-insert per table. Live run prints the same
counts but actually writes. Zero inserts is valid on a tower whose §1a dump
was empty (fresh install with no collected data yet).

### Verify seeded state

```fish
~/.venv-captain/bin/python3 scripts/verify_questdb_state.py   # hard floors for D29/D30/D31/D32/D33
```

Seeding is idempotent for tables with session-date–designated timestamps
(D31, D32, D33). Tables with wall-clock `ts` (D29, D30) will double on a second
pass; re-run only after a full wipe.

---

## 7. Bring up full stack (3 minutes)

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

All 9 containers (questdb, redis, captain-offline, captain-online,
captain-command, captain-gui, gui-dist, nginx, vault-backup) must show healthy.

Then verify the app-layer health gate actually fires:

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-offline 2>&1 | grep -i "QuestDB.*ready\|wait_for_questdb"
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-online  2>&1 | grep -i "QuestDB.*ready\|wait_for_questdb"
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-command 2>&1 | grep -i "QuestDB.*ready\|wait_for_questdb"
```

Each process should log "QuestDB is ready" within 30 s of container start.

---

## 8. Restore crons + Defect 1 / Defect 6 guards (2 minutes)

Restore from the pre-wipe capture — **not** `deploy/install-vix-cron.sh`
(Defect 2 in `.seed-audit.md`).

```fish
crontab /tmp/cron-(hostname)-pre.txt
crontab -l                                       # all three entries uncommented
```

**Defect 1 guard (VIX log path):**

```fish
crontab -l | grep vix_update
```

The `>> …/vix_update.log` path MUST include `/home/(whoami)/captain-system/...`.
If it points at `/home/captain-system/...` or any other path that does not
contain the current user's home directory, fix it:

```fish
crontab -l | sed "s|/home/[^/]*/captain-system|/home/(whoami)/captain-system|g" | crontab -
```

**Defect 6 guard (cron service active):**

```fish
systemctl is-active cron
# If inactive:
#   sudo systemctl enable --now cron
```

**Prime VIX immediately** so AIM-04 / AIM-11 do not start on a stale snapshot:

```fish
bash ~/captain-system/scripts/update_vix_data.sh
tail -3 ~/captain-system/data/vix/vix_daily_close.csv
tail -3 ~/captain-system/data/vix/vxv_daily_close.csv
```

Today's date must appear in both files.

**Healthcheck + backup dir sanity:**

```fish
test -x ~/healthcheck.sh; or echo "MISSING ~/healthcheck.sh"
test -w ~/backups;         or echo "~/backups not writable"
```

---

## 9. Multi-instance parity check

`INSTANCE_PARITY` must be set on exactly one tower (0 or 1); leave it empty on
single-instance installs. Refer to `CLAUDE.md § Multi-Instance Deployment`.

```fish
grep -E '^INSTANCE_PARITY=' .env
```

- Tower 1 (nomaan, primary account): `INSTANCE_PARITY=0`
- Tower 2 (isaac, client account):   `INSTANCE_PARITY=1`
- Single-instance:                    `INSTANCE_PARITY=` (empty)

---

## 10. Cross-tower equivalence gate

Run the following on BOTH towers and diff the output. Any D-table divergence is
a red flag — stop and investigate before enabling AUTO_EXECUTE.

```fish
# Capture
crontab -l                                        > /tmp/post-(hostname)-cron.txt
ls data/ | sort                                   > /tmp/post-(hostname)-data.txt
tail -1 data/vix/vix_daily_close.csv              > /tmp/post-(hostname)-vix.txt
python3 scripts/verify_questdb_state.py           > /tmp/post-(hostname)-qdb.txt 2>&1
```

Then, from Tower 1 (or any machine with SSH access to both):

```fish
# Replace hosts with your tower SSH aliases
scp tower1:/tmp/post-tower1-cron.txt .
scp tower2:/tmp/post-tower2-cron.txt .
diff /tmp/post-tower1-cron.txt /tmp/post-tower2-cron.txt   # schedules identical, paths differ by /home/$USER

diff (scp tower1:/tmp/post-tower1-data.txt /dev/stdout | psub) \
     (scp tower2:/tmp/post-tower2-data.txt /dev/stdout | psub)

diff (scp tower1:/tmp/post-tower1-qdb.txt  /dev/stdout | psub) \
     (scp tower2:/tmp/post-tower2-qdb.txt  /dev/stdout | psub)
```

Expected diff scope:

- `cron`: paths differ only by the `/home/USER/` prefix; schedules identical.
- `data/`: directory listing identical (same files).
- `vix`: both towers must show **today's** date on a weekday, previous Friday
  on a Monday morning. Any lag > 1 business day is Defect 6 reoccurring.
- `verify_questdb_state`: all D-table row counts must match exactly; live
  L-tables may diverge (expected).

---

## 11. Roll-back (if anything after step 3 fails catastrophically)

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml down
sudo rm -rf questdb/*
tar -xzf ~/backups/questdb-preinstall-$stamp.tar.gz -C ~/captain-system
crontab /tmp/cron-(hostname)-pre.txt
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
```

Roll-back time budget: ~5 minutes.

---

## Notes

- Scripts run on the **host**, not inside containers. The container runtime has
  historically drifted (captain-command does not mount `./scripts`).
- `CAPTAIN_COMPACTION_ENABLED=true` is the default and must remain so until at
  least two weeks of production monitoring on the canonical DDL. Compaction is
  the primary dedup mechanism for state tables whose writers use `now()` for
  the designated timestamp (see `.bootstrap-state.md § DEDUP Behaviour Notes`).
- `roll_calendar_update.py --update` does not call TopstepX despite the header
  comment — it is safe to run offline during a fresh install.
- `data/qdb_export/` is **not** a seed source. Prior-state dumps only; ignore.
