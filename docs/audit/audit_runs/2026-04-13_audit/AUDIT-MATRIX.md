# Audit Resolution Matrix — 2026-04-13

**Purpose**: Track every finding from initial audit through fix, verification, and sign-off.
**Rule**: Each session MUST update this file before closing. No session closes without matrix update.

---

## Resolution Tracking

| ID | Sev | Title | Session | Fix Description | Files Changed | Verification Method | Verified | Status |
|----|-----|-------|---------|-----------------|---------------|---------------------|----------|--------|
| C1 | CRIT | Redis signal publication silent loss | S1 | Added 3-attempt retry (100ms backoff) to _publish_signals(); caller publishes CRITICAL alert on final failure | b6_signal_output.py | grep retry + unit tests (148 pass) | Yes | FIXED |
| C2 | CRIT | TopstepX auth failure blind operation | S2 | — | — | — | — | PENDING |
| C3 | CRIT | Contract ID H26 expired default | S1 | Changed all H26 defaults to M26 (June 2026) | b2_gui_data_server.py, b3_api_adapter.py, verify_topstep_integration.py, topstep_client.py | grep H26 = 0 source matches | Yes | FIXED |
| C4 | CRIT | B5 injection never reaches Offline | S1 | Changed b5_injection_flow from pub/sub CH_COMMANDS to publish_to_stream(STREAM_COMMANDS) | b5_injection_flow.py | grep CH_COMMANDS = 0 matches in b5 | Yes | FIXED |
| C5 | CRIT | Duplicate HALT/RESUME publish | S1 | Migrated HALT/RESUME from pub/sub to stream; removed CH_COMMANDS imports | b1_core_routing.py | grep CH_COMMANDS = 0 matches in b1; all 5 publishes use stream | Yes | FIXED |
| H1 | HIGH | Command orch on pub/sub not streams | S1 | Added _command_stream_reader() as 4th daemon thread; new GROUP_COMMAND_COMMANDS constant | orchestrator.py, shared/redis_client.py | grep STREAM_COMMANDS in orchestrator confirmed | Yes | FIXED |
| H2 | HIGH | QuestDB no retry on connection | S2 | — | — | — | — | PENDING |
| H3 | HIGH | Session window 2 vs 5 min | S1 | Changed default from "2" to "5" in b9_session_controller.py | b9_session_controller.py | grep confirms default="5"; matches session_registry.json | Yes | FIXED |
| H4 | HIGH | Redis healthcheck var not expanded | S3 | — | — | — | — | PENDING |
| M1 | MED | Zero-contract signals published | S3 | — | — | — | — | PENDING |
| M2 | MED | VIX provider returns None | S3 | — | — | — | — | PENDING |
| M3 | MED | journal.sqlite volume mount risk | S3 | — | — | — | — | PENDING |
| M4 | MED | Bootstrap vars missing from template | S3 | — | — | — | — | PENDING |
| M5 | MED | Memory limits low for production | S3 | — | — | — | — | PENDING |
| M6 | MED | No explicit Docker network | S3 | — | — | — | — | PENDING |
| M7 | MED | Unused table p3_d28 | S3 | — | — | — | — | PENDING |
| M8 | MED | No startup health gate for API | S3 | — | — | — | — | PENDING |

---

## Session Sign-Off Log

| Session | Date | Issues Fixed | Issues Deferred | Commit(s) | Signed Off |
|---------|------|-------------|-----------------|-----------|------------|
| S1 | 2026-04-13 | C1, C3, C4, C5, H1, H3 | 0 | (pending commit) | Yes |
| S2 | — | — | — | — | — |
| S3 | — | — | — | — | — |
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
