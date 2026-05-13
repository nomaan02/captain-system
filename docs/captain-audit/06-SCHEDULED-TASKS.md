# 06 — Scheduled tasks

**TL;DR**

- Offline uses an internal **sleep(30s) polling scheduler** — not APScheduler.
- Daily cutoff **≥16:00 ET**; weekly **Monday**; monthly **day==1**; quarterly **Jan/Apr/Jul/Oct day==1**.
- Companion Command reconciliation references **19:00 EST** — separate service ([06.3](#063-command--reconciliation)).

**Audit stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`

## 06.1 Offline orchestrator scheduler

**File:** `captain-offline/captain_offline/blocks/orchestrator.py`

| ID | Schedule | Handler | Primary actions | Log hint |
|----|----------|---------|-----------------|----------|
| H1 | Every ~30s | `_publish_heartbeat` ~1235 | Redis `CH_STATUS` publish | `"Heartbeat publish failed"` |
| D1 | Daily after **16:00 ET**, once/date | `_run_daily` ~1247 | AIM lifecycle, drift detection, warmup, transitions | `"Daily offline tasks"` ~1249 |
| W1 | **Monday** ≥00:00 ET, once/week | `_run_weekly` ~1300 | Tier-1 retrain, HDWM, diagnostic WEEKLY | `"Weekly offline tasks"` ~1303 |
| M1 | **1st** ≥00:00 ET | `_run_monthly` ~1329 | Tier 2/3 retrain, sensitivity scan, diagnostic MONTHLY | `"Monthly offline tasks"` ~1331 |
| Q1 | Quarter start months **1/4/7/10** day 1 | `_run_quarterly` ~1375 | CUSUM calibration persist + refresh detectors | `"Quarterly offline tasks"` ~1382 |
| C1 | Every **48h** wall (`CAPTAIN_COMPACTION_ENABLED`) | `_run_compaction` ~1429 | Runs `compact_questdb_tables.py` subprocess | `"QuestDB compaction"` |

Scheduler loop: `_run_scheduler` ~1188–1233.

Verify daily hook fired (presence of log line):

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-offline 2>&1 | grep -F "Daily offline tasks"
```

### 06.1.1 Failure modes

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| QuestDB down | Stack traces in `_run_daily` except ~1295 | Fix DB first |
| Missing assets query | Empty loop iterations | Check `p3_d00_asset_universe` statuses |
| Compaction subprocess fails | Warning ~1450 | Inspect stderr snippet in logs |

## 06.2 Online orchestrator

Online loop handles session opens (NY/LON/APAC) — see `captain-online/captain_online/main.py` & `blocks/orchestrator.py` (session-driven, not wall-clock table here). Validate session threads alive:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-online 2>&1 | grep ON-B1 | tail
```

## 06.3 Command — reconciliation

**File:** `captain-command/captain_command/blocks/b8_reconciliation.py`

Module header documents **19:00 EST** reconciliation cycle (~9, ~48).

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-command 2>&1 | grep -i reconcile | tail
```

## 06.4 Parameters

| name | value | file | line | source-of-truth | rationale |
|------|-------|------|------|-----------------|----------|
| Daily trigger hour | `>=16` | `captain-offline/.../orchestrator.py` | 1207 | Code | After cash equity tasks |
| Compaction interval | `48 * 3600` s | same | 1195 | Code | Limit QuestDB bloat |
| Compaction flag | `.env` `CAPTAIN_COMPACTION_ENABLED` default true | same | 1228 | Env | Pause during migrations |

Cross-links: architecture [01](01-ARCHITECTURE-OVERVIEW.md), ops [08](08-OPS-COMMANDS.md).
