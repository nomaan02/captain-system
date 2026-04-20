# Phase 0 Tower Steps — Safety Net

Run these commands on **each tower** (Tower 1 / Nomaan, Tower 2 / Isaac) in order.
Both towers must complete all steps before proceeding to Session 2.

---

## Prerequisites

- You are SSH'd into the tower (or running WSL2 locally)
- Docker Desktop / Docker Engine is running
- The Captain stack is currently **running** (normal operating state)

---

## Step 1 — Pull the branch

```bash
cd ~/captain-system
git fetch origin
git checkout migration/phase-0-safety-net
```

Confirm you are on the correct branch:

```bash
git branch --show-current
# Expected output: migration/phase-0-safety-net
```

---

## Step 2 — Disable compaction in .env

Open `.env` in your editor and add this line:

```bash
echo 'CAPTAIN_COMPACTION_ENABLED=false' >> ~/.env 2>/dev/null || \
echo 'CAPTAIN_COMPACTION_ENABLED=false' >> ~/captain-system/.env
```

Or open it manually:

```bash
nano ~/captain-system/.env
```

Add the line anywhere (suggested: near the bottom, before bootstrap section):

```
CAPTAIN_COMPACTION_ENABLED=false
```

Verify it was written:

```bash
grep CAPTAIN_COMPACTION_ENABLED ~/captain-system/.env
# Expected: CAPTAIN_COMPACTION_ENABLED=false
```

---

## Step 3 — Rebuild and restart captain-offline

Only captain-offline reads the compaction flag and uses the new `os` import:

```bash
cd ~/captain-system
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-offline
```

Wait ~60 seconds for the container to become healthy:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml ps captain-offline
# Expected: Status = healthy (or Up)
```

Confirm the health gate logged success:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=30 captain-offline | grep -E "reachable|QuestDB|CRITICAL"
# Expected: "[OFFLINE] ... QuestDB reachable (attempt N)"
# NOT expected: "QuestDB unreachable after 30s"
```

---

## Step 4 — Rebuild captain-online and captain-command

These already have the health gate from Session 1. Rebuild to pick up any
incidental changes from the branch:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-online captain-command
```

Wait for healthy:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
# All 3 captain services should show healthy
```

---

## Step 5 — Capture the schema snapshot

Run this command and paste the output into `.migration-state.md` under
"Current schema snapshot":

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec questdb \
  curl -s "http://localhost:9000/exec?query=SELECT+tableName%2C+partitionBy%2C+maxUncommittedRows%2C+walEnabled+FROM+tables%28%29+ORDER+BY+tableName" \
  | python3 -m json.tool
```

Save this output — it is the baseline for Session 2 schema drift detection.

Also capture column schemas for the most critical tables:

```bash
for tbl in p3_d00_asset_universe p3_d01_aim_model_states p3_d08_tsm_state p3_d12_kelly_params p3_d16_capital_silos p3_d25_circuit_breaker; do
  echo "=== $tbl ==="
  docker compose -f docker-compose.yml -f docker-compose.local.yml exec questdb \
    curl -s "http://localhost:9000/exec?query=SHOW+COLUMNS+FROM+$tbl" \
    | python3 -m json.tool
done
```

---

## Step 6 — Verify no compaction runs in logs

Confirm the flag is working by checking that no compaction line appears after
the restart:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-offline | grep -i compaction
# Expected: empty (no output) — compaction is disabled
```

---

## Step 7 — Update .migration-state.md

On your laptop, paste the schema snapshot from Step 5 into:

```
.migration-state.md → "## Current schema snapshot" section
```

Commit the updated state file:

```bash
git add .migration-state.md
git commit -m "chore: add tower schema snapshot (Session 1)"
git push origin migration/phase-0-safety-net
```

---

## Verification checklist

- [ ] Branch `migration/phase-0-safety-net` checked out on this tower
- [ ] `CAPTAIN_COMPACTION_ENABLED=false` present in `.env`
- [ ] `captain-offline` rebuilt and healthy
- [ ] `captain-online` rebuilt and healthy
- [ ] `captain-command` rebuilt and healthy
- [ ] Health gate log line confirmed (QuestDB reachable)
- [ ] No compaction log lines after restart
- [ ] Schema snapshot captured and pasted into `.migration-state.md`

---

## Rollback (if anything goes wrong)

### Health gate timeout (QuestDB not ready in 30s)

The container will exit with code 2. Fix: increase `restart: unless-stopped` will
cause Docker to retry. If QuestDB is genuinely slow, wait for it to become healthy
first, then `docker compose up -d captain-offline`.

### Revert to main branch

```bash
cd ~/captain-system
git checkout main
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-offline captain-online captain-command
```

### Restore QuestDB data (if data loss detected)

```bash
# Backup was taken 2026-04-20 before this migration:
tar -xzf ~/captain-backups/questdb-pre-migration-20260420-1528.tgz -C ~/captain-system
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d questdb
```

---

*Session 1 complete. Proceed to Session 2 (schema drift detection) once both towers pass the checklist.*
