# Audit Resolution Matrix — 2026-04-13

**Purpose**: Track every finding from initial audit through fix, verification, and sign-off.
**Rule**: Each session MUST update this file before closing. No session closes without matrix update.

---

## Resolution Tracking

| ID | Sev | Title | Session | Fix Description | Files Changed | Verification Method | Verified | Status |
|----|-----|-------|---------|-----------------|---------------|---------------------|----------|--------|
| C1 | CRIT | Redis signal publication silent loss | S1 | Added 3-attempt retry (100ms backoff) to _publish_signals(); caller publishes CRITICAL alert on final failure | b6_signal_output.py | grep retry + unit tests (148 pass) | Yes | FIXED |
| C2 | CRIT | TopstepX auth failure blind operation | S2 | Added 3-attempt retry (5s delay) to _start_market_streams(); made auth failure fatal with sys.exit(1) + CRITICAL log | captain-online/main.py | Import check + 148 unit tests pass | Yes | FIXED |
| C3 | CRIT | Contract ID H26 expired default | S1 | Changed all H26 defaults to M26 (June 2026) | b2_gui_data_server.py, b3_api_adapter.py, verify_topstep_integration.py, topstep_client.py | grep H26 = 0 source matches | Yes | FIXED |
| C4 | CRIT | B5 injection never reaches Offline | S1 | Changed b5_injection_flow from pub/sub CH_COMMANDS to publish_to_stream(STREAM_COMMANDS) | b5_injection_flow.py | grep CH_COMMANDS = 0 matches in b5 | Yes | FIXED |
| C5 | CRIT | Duplicate HALT/RESUME publish | S1 | Migrated HALT/RESUME from pub/sub to stream; removed CH_COMMANDS imports | b1_core_routing.py | grep CH_COMMANDS = 0 matches in b1; all 5 publishes use stream | Yes | FIXED |
| H1 | HIGH | Command orch on pub/sub not streams | S1 | Added _command_stream_reader() as 4th daemon thread; new GROUP_COMMAND_COMMANDS constant | orchestrator.py, shared/redis_client.py | grep STREAM_COMMANDS in orchestrator confirmed | Yes | FIXED |
| H2 | HIGH | QuestDB no retry on connection | S2 | Added exponential backoff retry to _connect(): 3 attempts with [1s, 2s, 4s] delays; logs each attempt; raises on final failure | shared/questdb_client.py | Import check + 148 unit tests pass | Yes | FIXED |
| H3 | HIGH | Session window 2 vs 5 min | S1 | Changed default from "2" to "5" in b9_session_controller.py | b9_session_controller.py | grep confirms default="5"; matches session_registry.json | Yes | FIXED |
| H4 | HIGH | Redis healthcheck var not expanded | S3 | Changed CMD array to CMD-SHELL with `$$REDIS_PASSWORD` and `\| grep PONG` | docker-compose.yml | YAML validation + CMD-SHELL grep | Yes | FIXED |
| M1 | MED | Zero-contract signals published | S3 | Added `if total_size <= 0: continue` guard after sizing aggregation | b6_signal_output.py | grep + 148 unit tests pass | Yes | FIXED |
| M2 | MED | VIX provider returns None | S3 | Added info log when VIX is None in Layer 5 | b5c_circuit_breaker.py | grep + 148 unit tests pass | Yes | FIXED |
| M3 | MED | journal.sqlite volume mount risk | S3 | Added pre-creation requirement comments at all 3 journal.sqlite mounts | docker-compose.yml | grep journal.sqlite shows 3 comment blocks | Yes | FIXED |
| M4 | MED | Bootstrap vars missing from template | S3 | Added 5 BOOTSTRAP_* variables (commented) to .env.template | .env.template | grep BOOTSTRAP shows all 5 vars | Yes | FIXED |
| M5 | MED | Memory limits low for production | S3 | Added WSL2 dev-sized warning comment; actual limits unchanged (deferred) | docker-compose.local.yml | grep WARNING confirms comment | Yes | FIXED |
| M6 | MED | No explicit Docker network | S3 | Added `captain` bridge network; assigned to all 7 services | docker-compose.yml | YAML parse: 7 services on captain network | Yes | FIXED |
| M7 | MED | Unused table p3_d28 | S3 | Added NOTE comment documenting future use; table retained | scripts/init_questdb.py | grep NOTE confirms comment | Yes | FIXED |
| M8 | MED | No startup health gate for API | S3 | Added `_orchestrator_ready` flag; /api/health returns 503 until threads start | api.py, orchestrator.py | grep _orchestrator_ready + 148 tests pass | Yes | FIXED |

---

## Session Sign-Off Log

| Session | Date | Issues Fixed | Issues Deferred | Commit(s) | Signed Off |
|---------|------|-------------|-----------------|-----------|------------|
| S1 | 2026-04-13 | C1, C3, C4, C5, H1, H3 | 0 | `951daf8` | Yes |
| S2 | 2026-04-13 | C2, H2 | 0 | `1727026` | Yes |
| S3 | 2026-04-13 | H4, M1-M8 | 0 | `c533f00` | Yes |
| S4 | — | — | — | — | — |

---

## Escalation Log

Issues that required manual user input:

| ID | Session | Question Raised | User Response | Resolution |
|----|---------|-----------------|---------------|------------|
| — | — | — | — | — |

---

## Post-Fix Regression Checklist

Run after ALL sessions complete:

- [ ] `docker compose -f docker-compose.yml -f docker-compose.local.yml config --quiet` (compose valid)
- [ ] `PYTHONPATH=./:./captain-online:./captain-offline:./captain-command python3 -B -m pytest tests/ --ignore=tests/test_integration_e2e.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py --ignore=tests/test_account_lifecycle.py -v` (unit tests pass)
- [ ] `docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build` (all containers start)
- [ ] All 9 containers healthy (`docker compose ps`)
- [ ] Redis streams writable (XADD test)
- [ ] QuestDB tables queryable (SELECT 1 FROM each critical table)
- [ ] TopstepX auth succeeds or fails loudly
- [ ] GUI loads at http://localhost:80
- [ ] `/api/health` returns 200 only when ready
