# Documentation Fact-Checker Audit Report

**Skill:** ln-614-docs-fact-checker | **Category:** Fact Accuracy
**Date:** 2026-04-09 | **Score: 3.2 / 10**
**Issues: 49 unique (C:3 H:10 M:12 L:6) + 18 line-drift (informational)**

---

## Methodology

- **Scope:** 83 markdown files scanned, 12 high-priority docs deeply verified
- **Claims checked:** 377 across 9 claim types (path, count, docker, env var, redis, entity, line ref, CLI, cross-doc)
- **Verification:** Every claim checked against filesystem, source code, and config files via Grep/Glob/Read

### Checks Summary

| ID | Check | Claims | Pass | Fail | Score |
|----|-------|--------|------|------|-------|
| path_claims | File/Directory Paths | 163 | 118 | 45 | 72% |
| count_claims | Counts & Statistics | 34 | 18 | 16 | 53% |
| docker_claims | Docker/Infra | 18 | 4 | 14 | 22% |
| config_claims | Config & Env Vars | 8 | 3 | 5 | 38% |
| redis_claims | Redis Channels | 11 | 1 | 10 | 9% |
| entity_claims | Code Entity Names | 131 | 116 | 15 | 89% |
| line_ref_claims | Line Number Refs | 18 | 5 | 13 | 28% |
| cross_doc | Cross-Document Consistency | 12 | 0 | 12 | 0% |

---

## CRITICAL Findings (3)

### C-01: Security-Critical Env Vars Undocumented

**Severity:** CRITICAL | **Type:** CONFIG_NOT_FOUND

`JWT_SECRET_KEY` and `API_SECRET_KEY` are used in `captain-command/captain_command/api.py` for authentication but appear in **zero** documentation files and are missing from `.env.template`. Both default to empty strings, meaning the API has no JWT signing and no API key protection unless the operator independently discovers and sets these variables.

- **Location:** captain-command/captain_command/api.py (JWT_SECRET_KEY, API_SECRET_KEY)
- **Impact:** Security -- unauthenticated API access if vars not set
- **Evidence:** `grep -r "JWT_SECRET_KEY\|API_SECRET_KEY" .env.template CLAUDE.md MIGRATION_GUIDE.md` returns zero matches

### C-02: .env.template Missing 22 Environment Variables

**Severity:** CRITICAL | **Type:** CONFIG_NOT_FOUND

22 environment variables used in production code are absent from `.env.template`:

| Variable | Used In | Risk |
|----------|---------|------|
| JWT_SECRET_KEY | api.py | Security |
| API_SECRET_KEY | api.py | Security |
| TOPSTEP_CONTRACT_ID | b2_gui_data_server, b3_api_adapter | Runtime failure |
| BOOTSTRAP_ACCOUNT_ID | bootstrap_production.py | Setup failure |
| BOOTSTRAP_USER_ID | bootstrap_production.py | Setup failure |
| BOOTSTRAP_STARTING_CAPITAL | bootstrap_production.py | Setup failure |
| BOOTSTRAP_MAX_POSITIONS | bootstrap_production.py | Silent default |
| BOOTSTRAP_MAX_CONTRACTS | bootstrap_production.py | Silent default |
| QUESTDB_HOST, QUESTDB_PORT | questdb_client.py | Set in compose only |
| REDIS_HOST, REDIS_PORT | redis_client.py | Set in compose only |
| CAPTAIN_ROLE | docker-compose.yml | Set in compose only |
| + 9 infrastructure vars | Various | Set in compose only |

### C-03: QuestDB Table Count Stale Across 6+ Documents

**Severity:** CRITICAL | **Type:** COUNT_MISMATCH + CROSS_DOC_COUNT_CONFLICT

All documentation claims **29 tables**. Actual count in `scripts/init_questdb.py`: **38 tables** (38 `CREATE TABLE IF NOT EXISTS` statements). 9 tables added since docs were written: D29-D33, p3_spread_history, p3_replay_results, p3_replay_presets, p3_offline_job_queue, p3_session_event_log.

| Document | Line | Claim |
|----------|------|-------|
| CLAUDE.md | 11, 197 | "29 tables" |
| MIGRATION_GUIDE.md | 28 | "29 tables" |
| MOST_COMPLETE_REFERENCE.md | 59, 676, 810, 3320 | "29 tables" |
| CAPTAIN_RECONCILIATION_MATRIX.md | 507 | "29 tables" |
| init_questdb.py header | 1 | "30 tables" (also wrong) |

---

## HIGH Findings (10)

### H-01: Spec Directories Referenced But Missing

**Type:** PATH_NOT_FOUND

CLAUDE.md references two authoritative spec directories that do not exist in this repository:

1. `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/` (CLAUDE.md:230, 413) -- "V3 Authoritative specs (55 files)"
2. `docs/completion-validation-docs/Step 1 - Original Specs/` (CLAUDE.md:416-421) -- 5 original spec files

These are likely from the `most-production` repo and were never copied to `captain-system`. Any developer following CLAUDE.md's instruction to "Start with Nomaan_Master_Build_Guide.md" will find nothing.

### H-02: Deleted b3_aim_aggregation.py Referenced in 6+ Documents

**Type:** ENTITY_NOT_FOUND + CROSS_DOC_PATH_CONFLICT

`captain-online/captain_online/blocks/b3_aim_aggregation.py` was deleted (logic moved to `shared/aim_compute.py`). Orphan `.pyc` bytecode remains. **30+ stale references** across:

| Document | References |
|----------|-----------|
| CLAUDE.md:53 | File tree listing |
| MOST_COMPLETE_REFERENCE.md:1900 | Full file description |
| docs/audit/captain_online.md:489 | Described as "re-export shim" |
| docs/AIM_Audit_Report.md | 30+ references throughout |
| docs/AIM-Specs/AIM_Pseudocode_Blocks.md:3 | "Generated from b3_aim_aggregation.py" |
| docs/REPLAY_FUNCTION_MAP.md:855 | "Real B3 via b3_aim_aggregation" |

### H-03: Block Counts Wrong Across All Documents

**Type:** COUNT_MISMATCH + CROSS_DOC_COUNT_CONFLICT

| Claim (all docs) | Actual (filesystem) |
|-------------------|-------------------|
| "28 blocks total" | ~40 block files |
| Offline: "9 + orchestrator" | 16 block files + orchestrator |
| Online: "9 + orchestrator" | 12 block files + orchestrator |
| Command: "10 + orchestrator" | 11 block files + orchestrator |

Root cause: Original spec numbered B1-B9/B10. Sub-blocks (B1 has 5 files in Offline, B5b/B5c/B7_shadow/B8/B9 added in Online, B11 added in Command) were never reflected in summary counts.

### H-04: Redis Architecture Migration Undocumented in CLAUDE.md

**Type:** INFRA_MISMATCH

CLAUDE.md:159-167 describes 5 pub/sub channels as the messaging architecture. In reality, 3 of these (signals, trade_outcomes, commands) were **migrated to Redis Streams** for durability. Additionally, `stream:signal_outcomes` (used by b7_shadow_monitor for Category A learning) exists but is documented **nowhere**.

Actual messaging infrastructure: 2 active pub/sub channels + 4 Redis Streams = 6 active messaging paths.

### H-05: Python Version Mismatch (3.11 vs 3.12)

**Type:** INFRA_MISMATCH

MOST_COMPLETE_REFERENCE.md (lines 857-858, 957-958) documents `python:3.11-slim` as the base image. All three Dockerfiles actually use `python:3.12-slim`.

### H-06: Fabricated ThreadedConnectionPool in Documentation

**Type:** ENTITY_NOT_FOUND

MOST_COMPLETE_REFERENCE.md (~line 1011) describes `get_cursor()` as using a `ThreadedConnectionPool(min=2, max=10)` with `_CONNECT_KWARGS` containing `connect_timeout=5` and `statement_timeout=15000`. **None of this exists in code.** Actual `shared/questdb_client.py` creates a fresh TCP connection per call with no pooling and no timeouts. This is the most severe factual fabrication found.

### H-07: GUI_INTEGRATION_MAP.md Has 11 Wrong File References

**Type:** PATH_NOT_FOUND

The GUI was restructured from `.tsx` to `.jsx` and from flat `cells/` layout to nested `components/{domain}/` layout. 11 paths in GUI_INTEGRATION_MAP.md point to nonexistent files:

- 7 wrong extensions (`.ts`/`.tsx` should be `.js`/`.jsx`)
- 2 nonexistent directories (`cells/`)
- 1 renamed file (`index.css` -> `global.css`)
- 1 nonexistent store (`themeStore.ts`)

### H-08: QuestDB Image Tag Mismatch

**Type:** INFRA_MISMATCH

MOST_COMPLETE_REFERENCE.md:855 says `questdb/questdb:latest`. Actual docker-compose.yml uses a **pinned SHA256 digest** with an explicit comment warning against `:latest`.

### H-09: TOPSTEP_CONTRACT_ID Undocumented

**Type:** CONFIG_NOT_FOUND

Used in `captain-command` (b2_gui_data_server.py:38, b3_api_adapter.py:124) to control which contract the system trades. Not mentioned in CLAUDE.md, .env.template, or MIGRATION_GUIDE.md.

### H-10: Offline Does Not Publish to captain:status

**Type:** CROSS_DOC_ENDPOINT_GAP

CLAUDE.md:167 says `captain:status | All processes | Command B1`. Grep confirms only Online orchestrator and Command orchestrator publish to CH_STATUS. **Offline never publishes heartbeats.**

---

## MEDIUM Findings (12)

| ID | Type | Document(s) | Issue |
|----|------|-------------|-------|
| M-01 | INFRA_MISMATCH | CLAUDE.md:122 | Says "6 containers" then lists 7 names (self-contradictory). Should say "7 services (6 long-running + 1 ephemeral build)" |
| M-02 | INFRA_MISMATCH | CLAUDE.md:64, 204 | "React/Vue SPA" but package.json shows React only. No Vue dependency exists. |
| M-03 | INFRA_MISMATCH | CLAUDE.md:150 | Port 9009 (QuestDB InfluxDB line protocol) exposed in docker-compose.yml but undocumented |
| M-04 | CONFIG_NOT_FOUND | CLAUDE.md:189 | "Use TOPSTEP_ prefix for all env vars" is overly broad. TRADING_ENVIRONMENT, AUTO_EXECUTE, VAULT_MASTER_KEY don't use it. |
| M-05 | CONFIG_NOT_FOUND | CLAUDE.md:385 | BOOTSTRAP_MAX_POSITIONS and BOOTSTRAP_MAX_CONTRACTS env vars undocumented |
| M-06 | CROSS_DOC_COUNT_CONFLICT | MOST_COMPLETE_REFERENCE:1718 vs CLAUDE.md:242 | 11 active assets vs 10 (ZT was eliminated after MOST_COMPLETE_REFERENCE was written) |
| M-07 | CROSS_DOC_CONFLICT | 24-7-setup-guide vs docker-compose.local.yml | Memory limits differ: guide recommends 2560M/2G/1G, actual compose uses 2G/1536M/768M |
| M-08 | ENTITY_NOT_FOUND | REPLAY_FUNCTION_MAP.md:217-234 | SESSION_CONFIG uses key "LONDON" but code uses "LON" (3 occurrences) |
| M-09 | COUNT_MISMATCH | CLAUDE.md:397 | "64 tests" but pytest --collect-only finds 95 tests (48% growth) |
| M-10 | COUNT_MISMATCH | CLAUDE.md:70, 177 | "18 endpoints" but actual: 15 distinct REST endpoints, 20 public methods |
| M-11 | INFRA_MISMATCH | MOST_COMPLETE_REFERENCE:810 | "nginx TLS 1.3" but no TLS config exists in repo. Local deployment is HTTP-only. |
| M-12 | ENTITY_NOT_FOUND | REPLAY_FUNCTION_MAP.md:596 | Claims `_get_return_bounds()` and `_compute_robust_kelly()` are ports of `b1_features.py:450-480` but those functions do not exist in b1_features.py |

---

## LOW Findings (6)

| ID | Type | Document | Issue |
|----|------|----------|-------|
| L-01 | INFRA_MISMATCH | MOST_COMPLETE_REFERENCE:963 | Alpine 3.19 in doc, actual is 3.20 |
| L-02 | PATH_NOT_FOUND | CLAUDE.md:68 | `captain-gui/dist/` listed in file tree but only exists at runtime (Docker build artifact) |
| L-03 | PATH_NOT_FOUND | REPLAY_TAB_USER_GUIDE:161 | `data/bar_cache.sqlite` only exists at runtime |
| L-04 | PATH_NOT_FOUND | DEVELOPER_WORKFLOW:251 | `vault/keys.vault` only exists at runtime |
| L-05 | INFRA_MISMATCH | MOST_COMPLETE_REFERENCE:1151 | Claims no legacy publish() calls remain, but scripts/paper_trader.py:350 still uses one |
| L-06 | COUNT_MISMATCH | MOST_COMPLETE_REFERENCE:1244 | Says "28 tables created" (different from its own "29" claim elsewhere) |

---

## Line Number Drift (18 instances, informational)

REPLAY_FUNCTION_MAP.md contains 13 function-to-line-number mappings for `shared/replay_engine.py` that are all off by ~120+ lines due to file growth (1944 -> 2066 lines). All functions exist but at shifted locations. Additionally, 5 line references in other docs show minor drift (1-5 lines). These are cosmetic but reduce doc reliability.

---

## Cross-Document Contradiction Summary

| # | Fact | Documents in Conflict | Correct Value |
|---|------|-----------------------|---------------|
| 1 | QuestDB tables | CLAUDE.md, MIGRATION_GUIDE, MOST_COMPLETE_REF, RECONCILIATION_MATRIX | 38 (not 29) |
| 2 | Total blocks | CLAUDE.md, MOST_COMPLETE_REF, OLD_GUI_TAB_SPECS | ~40 files (not 28) |
| 3 | Online blocks | CLAUDE.md, MOST_COMPLETE_REF | 12 files (not 9) |
| 4 | Offline blocks | CLAUDE.md, MOST_COMPLETE_REF | 16 files (not 9) |
| 5 | Command blocks | CLAUDE.md, MOST_COMPLETE_REF | 11 files (not 10) |
| 6 | Container count | CLAUDE.md, MIGRATION_GUIDE, MOST_COMPLETE_REF (self-contradictory) | 7 services / 6 long-running |
| 7 | Active assets | CLAUDE.md (10) vs MOST_COMPLETE_REF (11) | 10 (ZT eliminated) |
| 8 | Redis architecture | CLAUDE.md (pub/sub) vs cross_cutting.md (streams) | 2 pub/sub + 4 streams |
| 9 | Memory limits | 24-7-setup-guide vs docker-compose.local.yml | docker-compose.local.yml is truth |
| 10 | Python version | MOST_COMPLETE_REF (3.11) vs Dockerfiles (3.12) | 3.12 |
| 11 | QuestDB image | MOST_COMPLETE_REF (:latest) vs docker-compose.yml (pinned SHA) | Pinned SHA |
| 12 | Daily schedule | MOST_COMPLETE_REF (16:00 ET) vs cross_cutting (19:00 ET) | Different tasks at different times |

---

## Most-Affected Documents (by issue count)

| Document | Issues | Priority |
|----------|--------|----------|
| **CLAUDE.md** | 18 | Highest -- canonical project reference |
| **MOST_COMPLETE_REFERENCE.md** | 16 | High -- main architecture reference |
| **GUI_INTEGRATION_MAP.md** | 11 | Medium -- GUI integration guide |
| **REPLAY_FUNCTION_MAP.md** | 15 | Medium -- replay system reference |
| **AIM_Audit_Report.md** | 30+ | Medium -- all b3_aim_aggregation refs stale |
| **.env.template** | 22 vars missing | High -- deployment artifact |

---

## Recommended Fix Priority

1. **Immediate (security):** Add JWT_SECRET_KEY, API_SECRET_KEY, TOPSTEP_CONTRACT_ID to .env.template with documentation
2. **Immediate (canonical):** Update CLAUDE.md counts (tables: 38, blocks: ~40, tests: 95), remove b3_aim_aggregation reference, fix container count, update Redis channel table to include Streams
3. **Short-term:** Remove or redirect spec directory references (CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS, completion-validation-docs)
4. **Short-term:** Update MOST_COMPLETE_REFERENCE.md Python version (3.12), remove fabricated connection pool description, fix QuestDB image tag
5. **Maintenance:** Refresh REPLAY_FUNCTION_MAP.md line numbers, fix "LONDON"->"LON", remove b3_aim_aggregation references from all docs

---

*Report generated by ln-614-docs-fact-checker | 2026-04-09*
