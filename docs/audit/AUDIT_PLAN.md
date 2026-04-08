# Captain System — Codebase Audit Plan

**Date:** 2026-04-08
**Scope:** Full codebase audit of `captain-system/` — 6-container Docker Compose trading system

---

## Codebase Inventory

| Service | Python Files | LOC | Largest File (LOC) |
|---------|-------------|-----|---------------------|
| captain-online | 18 | 6,633 | b1_features.py (1,368) |
| captain-offline | 22 | 6,949 | b3_pseudotrader.py (1,431) |
| captain-command | 17 | 8,789 | b2_gui_data_server.py (1,484) |
| shared | 18 | 6,887 | replay_engine.py (2,065) |
| scripts | 33 | 10,740 | init_questdb.py (798) |
| tests | 23 | 4,952 | test_account_lifecycle.py (960) |
| **Total** | **131** | **44,950** | |

## Docker Architecture

6 containers: QuestDB, Redis, captain-offline, captain-online, captain-command, captain-gui + nginx

| Container | Ports | Memory Limit | Key Mounts |
|-----------|-------|-------------|------------|
| questdb | 9000, 8812, 9009 | 2G | ./questdb/db |
| redis | 6379 | 256M | ./redis |
| captain-offline | — | 1.5G | shared:ro, data:ro, logs, journal |
| captain-online | — | 2G | shared:ro, data:ro, logs, vault:ro, journal |
| captain-command | 8000 | 768M | shared:ro, data:ro, logs, vault:ro, journal, docker.sock, repo |
| captain-gui | — | — | gui-dist volume |
| nginx | 80 | 128M | gui-dist:ro, nginx-local.conf |

Key: captain-command has Docker socket + full repo mount (self-update capability).

## Execution Sessions

| Session | Target | Files | Skills | Output | Dependencies |
|---------|--------|-------|--------|--------|-------------|
| EXEC-01 | Online: Core & Ingestion | 5 | ln-629, ln-628 | captain_online.md §1 | — |
| EXEC-02 | Online: AIMs & Regime | 4 | ln-624, ln-626 | captain_online.md §2 | EXEC-01 passover |
| EXEC-03 | Online: Kelly → Signal | 9 | ln-623, ln-627 | captain_online.md §3 | EXEC-02 passover |
| EXEC-04a | Offline: Orch + B1-B2 | 12 | ln-629, ln-626 | captain_offline.md §1 | — |
| EXEC-04b | Offline: B3-B9 | 8 | ln-625, ln-624 | captain_offline.md §2 | EXEC-04a passover |
| EXEC-05a | Command: Core + API | 7 | ln-621, ln-628 | captain_command.md §1 | — |
| EXEC-05b | Command: Reports → Replay | 8 | ln-621, ln-627 | captain_command.md §2 | EXEC-05a passover |
| EXEC-06 | Cross-Cutting: Shared + Config | 17 | ln-622, ln-627, ln-621 | cross_cutting.md | All prior |

## Execution Order

```
Phase 1 (sequential):  EXEC-01 → EXEC-02 → EXEC-03
Phase 2 (parallel):    EXEC-04a/04b ‖ EXEC-05a/05b
Phase 3 (final):       EXEC-06 (aggregates cross-service data)
```

Checkpoint: Review `captain_online.md` after Phase 1 before proceeding.

## Tracking

After each session:
- [ ] All listed files covered?
- [ ] All extraction criteria met?
- [ ] Passover summary provided for next session?
- [ ] If gaps found → generate EXEC-XX-PATCH prompt
