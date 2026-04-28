# Pre-Market Readiness Fix Orchestrator — 2026-04-13

**Origin**: Circuit breaker table name mismatch blocked NY open on Apr 13. Deep audit uncovered 5 CRITICAL, 4 HIGH, 8 MEDIUM additional issues.
**Goal**: Systematically fix all findings so Captain can auto-trade at next market open with zero blocking errors.
**Method**: 4 fix sessions + 1 verification session, batched by coupling and risk to preserve context window.

---

## Session Architecture

```
S1: Redis Channel Fixes + Quick Config Fixes     (C1, C3, C4, C5, H1, H3)
    ↓ commit + matrix update
S2: Startup Resilience                            (C2, H2)
    ↓ commit + matrix update
S3: Docker & Medium Issues                        (H4, M1-M8)
    ↓ commit + matrix update
S4: Integration Verification & Regression         (full pipeline test)
    ↓ final matrix sign-off
```

### Why this grouping:

- **S1** bundles all Redis channel consistency issues together (C1/C4/C5/H1 are the same root cause: incomplete pub/sub→stream migration) plus two quick config fixes (C3 contract ID, H3 session window). These share code context in `shared/redis_client.py`, `b1_core_routing.py`, `b5_injection_flow.py`, and the command orchestrator.
- **S2** isolates startup resilience (C2 TopstepX, H2 QuestDB retry) because these touch `main.py` in all 3 processes and `shared/questdb_client.py` — different code surface than S1.
- **S3** handles Docker infra and lower-severity items that don't affect the signal-to-trade path directly.
- **S4** is pure verification — no code changes, just end-to-end testing.

---

## Session Contract

Every fix session MUST:

1. **Read first** — Read every file before modifying. No blind edits.
2. **Read the audit** — Start by reading `00-INITIAL-FINDINGS.md` and `AUDIT-MATRIX.md`
3. **Fix in order** — Work through assigned IDs sequentially
4. **Test each fix** — Run relevant unit tests or grep verification after each change
5. **Update the matrix** — Write resolution details to `AUDIT-MATRIX.md` before session ends
6. **Write session log** — Create `S{N}-RESOLUTION-LOG.md` with full details
7. **Commit** — Stage and commit all changes with descriptive message
8. **Escalate** — If a fix requires Nomaan's manual input (env vars, API keys, config decisions), document the question clearly, pause, and wait for confirmation

---

## SESSION 1: Redis Channel Consistency + Quick Config Fixes

**Issues**: C1, C3, C4, C5, H1, H3
**Estimated context**: ~15 files, well within window
**Risk level**: HIGH — these are the most likely to block trades

### Phase 0: Documentation Discovery

```
READ these files to understand current channel architecture:
- shared/redis_client.py                    (channel constants, publish_to_stream helper)
- shared/constants.py                       (any channel name constants)
- captain-online/captain_online/blocks/orchestrator.py   (stream reader ~line 792-802)
- captain-offline/captain_offline/blocks/orchestrator.py (stream reader ~line 184-213)
- captain-command/captain_command/blocks/orchestrator.py (pub/sub subscriber ~line 222)
- captain-command/captain_command/blocks/b1_core_routing.py (dual publish ~line 211, 288)
- captain-command/captain_command/blocks/b5_injection_flow.py (wrong channel ~line 176)
- captain-online/captain_online/blocks/b6_signal_output.py (signal publish ~line 287)
- captain-online/captain_online/blocks/b9_session_controller.py (session window ~line 29)
- config/session_registry.json              (session window values)
- captain-command/captain_command/blocks/b2_gui_data_server.py (contract ID ~line 39)
- captain-command/captain_command/blocks/b3_api_adapter.py (contract ID ~line 127)

EXTRACT:
- All STREAM_* and CH_* constant definitions
- The publish_to_stream() function signature and error handling
- How Online/Offline orchestrators create consumer groups and read streams
- How Command orchestrator currently subscribes
```

### Phase 1: Fix C3 — Contract ID H26 → M26 (2-line fix)

```
CHANGE in b2_gui_data_server.py:39:
  FROM: default "CON.F.US.EP.H26"
  TO:   default "CON.F.US.EP.M26"

CHANGE in b3_api_adapter.py:127:
  FROM: default "CON.F.US.EP.H26"
  TO:   default "CON.F.US.EP.M26"

VERIFY: grep -r "H26" captain-command/ — should return 0 matches
VERIFY: grep -r "CON.F.US.EP" captain-command/ — all should show M26
```

**ESCALATION POINT**: If you find H26 referenced anywhere OUTSIDE captain-command, pause and ask Nomaan whether those references should also update.

### Phase 2: Fix H3 — Session Window Minutes

```
READ b9_session_controller.py:29 to understand how SESSION_WINDOW_MINUTES is used
READ config/session_registry.json to see what values exist

DETERMINE: Does the code load from the config file, or does it use the hardcoded default?
- If code loads from config: the default=2 is just a fallback, verify config loads correctly
- If code uses hardcoded default: change to match config (5 min) or load from config

VERIFY: trace the session_window_minutes variable through b9 to confirm it's used correctly
```

### Phase 3: Fix C1 — Redis Signal Publication Retry

```
READ b6_signal_output.py fully (especially _publish_signals and its callers)
READ shared/redis_client.py publish_to_stream() implementation

ADD retry logic to _publish_signals():
- 3 attempts, 100ms backoff between retries
- If all retries fail: raise exception (don't swallow)
- Caller in orchestrator should catch and publish CRITICAL alert

VERIFY: the retry doesn't break the normal success path
VERIFY: grep for other publish_to_stream() calls that might need same treatment
```

### Phase 4: Fix C5 — Remove Duplicate HALT Publish

```
READ b1_core_routing.py lines 200-300 to understand both publish paths

REMOVE the pub/sub duplicate at line 288:
  redis_client.publish(CH_COMMANDS, {...})
  
The stream publish at line 211 is the durable, correct path.

VERIFY: all HALT/RESUME commands now only go through STREAM_COMMANDS
VERIFY: no other block relies on receiving HALT via CH_COMMANDS pub/sub
```

### Phase 5: Fix C4 — B5 Injection to Stream

```
READ b5_injection_flow.py fully to understand the publish at line 176

CHANGE: redis_client.publish(CH_COMMANDS, {...})
TO:     publish_to_stream(STREAM_COMMANDS, {...})

Ensure the import for publish_to_stream exists. Match the message format
used by other STREAM_COMMANDS publishers (b1_core_routing.py:178,211,235,275).

VERIFY: Offline orchestrator stream reader (line 209) will receive these message types
VERIFY: message format matches what Offline expects (check _handle_command() method)
```

### Phase 6: Fix H1 — Command Orchestrator Stream Migration

```
This is the largest change in S1. Read carefully before modifying.

READ captain-command/captain_command/blocks/orchestrator.py fully
UNDERSTAND: how it currently subscribes to CH_COMMANDS via pub/sub (line 222)
UNDERSTAND: how it processes incoming commands in its main loop

OPTION A (PREFERRED — minimal change):
  Add a STREAM_COMMANDS reader alongside the existing pub/sub subscriber.
  Process messages from both. This ensures backward compatibility.

OPTION B (CLEAN — larger change):
  Fully migrate Command to stream reader like Online/Offline.
  Remove pub/sub subscription for CH_COMMANDS entirely.

DETERMINE: which commands does Command need that only come via stream?
  If Command only needs HALT/RESUME (which now only publish to stream after C5 fix),
  then it MUST read from stream or it will never see halt commands.

VERIFY: after this change, a HALT command published to STREAM_COMMANDS reaches
  all three processes (Online, Offline, AND Command)
```

**ESCALATION POINT**: If the Command orchestrator's main loop architecture makes stream reading difficult (e.g., it uses a blocking pub/sub listener), pause and describe the architecture to Nomaan before choosing an approach.

### Phase 7: Session Closeout

```
1. Run unit tests: PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
   python3 -B -m pytest tests/ --ignore=tests/test_integration_e2e.py \
   --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py \
   --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py \
   --ignore=tests/test_account_lifecycle.py -v

2. Update AUDIT-MATRIX.md — fill in all S1 rows (C1, C3, C4, C5, H1, H3)

3. Write S1-RESOLUTION-LOG.md with:
   - Each fix: what was changed, why, exact lines
   - Each verification: what was checked, result
   - Any surprises or secondary issues discovered
   - Any escalations raised

4. Commit all changes:
   fix: redis channel consistency + expired contract ID + session window

   - C1: Add retry to B6 signal publication
   - C3: Update contract ID defaults from H26 to M26
   - C4: Migrate B5 injection from pub/sub to stream
   - C5: Remove duplicate HALT/RESUME pub/sub publish
   - H1: Add stream reader to Command orchestrator
   - H3: Fix session window minutes default
```

---

## SESSION 2: Startup Resilience

**Issues**: C2, H2
**Estimated context**: ~8 files
**Risk level**: HIGH — prevents crash-on-startup scenarios

### Phase 0: Documentation Discovery

```
READ these files:
- captain-online/captain_online/main.py     (TopstepX auth flow, lines 43-77)
- captain-offline/captain_offline/main.py   (QuestDB connection, lines 109-113)
- captain-command/captain_command/main.py    (QuestDB connection, lines 43-51)
- shared/questdb_client.py                  (get_connection implementation)
- shared/topstep_client.py                  (authenticate method)
- shared/topstep_stream.py                  (MarketStream class)

EXTRACT:
- Current error handling in each main.py
- How get_connection() works (single attempt? pool?)
- What TopstepX auth failure looks like (exception type, message)
```

### Phase 1: Fix H2 — QuestDB Connection Retry

```
MODIFY shared/questdb_client.py get_connection() (or _connect):
- Add exponential backoff: 3 attempts, delays [1s, 2s, 4s]
- Log each retry attempt with attempt number
- Raise on final failure (don't swallow)

This single change fixes all 3 processes since they all use shared/questdb_client.py.

VERIFY: import and call get_connection() in a quick script to confirm retry works
VERIFY: existing callers don't break (they expect Exception on failure)
```

### Phase 2: Fix C2 — TopstepX Auth Failure Must Be Fatal

```
READ captain-online/captain_online/main.py lines 43-77 carefully.

The current flow:
  market_stream = _start_market_streams()
  if market_stream:
      # great
  else:
      plog.warn(...)  # just a warning!
  orchestrator.start()  # runs WITHOUT data!

CHANGE: Make TopstepX auth failure FATAL for captain-online:
  if not market_stream:
      logger.critical("TopstepX authentication failed — cannot trade without market data")
      sys.exit(1)

ADD retry to _start_market_streams():
  3 attempts, 5s delay between retries (API may be temporarily down)
  If all 3 fail: return None (which now triggers exit)

VERIFY: captain-offline and captain-command do NOT need TopstepX auth at startup
  (Online is the only process that streams market data)
```

**ESCALATION POINT**: If TopstepX auth is known to fail outside market hours (e.g., weekends), making it fatal would prevent the system from starting on Saturday for pre-market setup. Ask Nomaan: "Should TopstepX auth failure be fatal even outside market hours, or should it retry on a timer?"

### Phase 3: Session Closeout

```
1. Run unit tests (same command as S1)
2. Update AUDIT-MATRIX.md — fill in S2 rows (C2, H2)
3. Write S2-RESOLUTION-LOG.md
4. Commit:
   fix: startup resilience — QuestDB retry + TopstepX auth fatal

   - C2: Make TopstepX auth failure fatal in captain-online
   - H2: Add exponential backoff retry to QuestDB get_connection()
```

---

## SESSION 3: Docker Infrastructure + Medium Issues

**Issues**: H4, M1-M8
**Estimated context**: ~12 files
**Risk level**: MEDIUM — improves reliability, not trade-blocking

### Phase 0: Documentation Discovery

```
READ these files:
- docker-compose.yml                        (healthchecks, volumes, networks)
- docker-compose.local.yml                  (memory limits, overrides)
- captain-start.sh                          (startup workarounds)
- .env.template                             (current env var documentation)
- scripts/bootstrap_production.py:72-76     (BOOTSTRAP_* variable usage)
- captain-online/captain_online/blocks/b6_signal_output.py:70 (zero-contract check)
- captain-online/captain_online/blocks/b5c_circuit_breaker.py:417 (VIX None)
- captain-command/captain_command/main.py:340+ (health gate)
- scripts/init_questdb.py:628               (unused table)
```

### Phase 1: Fix H4 — Redis Healthcheck

```
CHANGE docker-compose.yml Redis healthcheck from CMD array to CMD-SHELL:
  test: ["CMD-SHELL", "redis-cli -a $$REDIS_PASSWORD ping | grep PONG"]

CMD-SHELL evaluates environment variables. $$ escapes to $ in compose.

VERIFY: docker compose config shows correct healthcheck
```

### Phase 2: Fix M1 — Zero-Contract Signal Guard

```
ADD early return in b6_signal_output.py before signal creation:
  if total_size <= 0:
      logger.debug("ON-B6: Skipping %s — zero contracts after filtering", asset)
      continue

VERIFY: no downstream code depends on receiving zero-size signals
```

### Phase 3: Fix M2 — VIX None Logging

```
ADD info-level log when VIX is None in b5c_circuit_breaker.py Layer 5:
  if vix is None:
      logger.info("ON-B5C: VIX unavailable — Layer 5 skipped")

This is observability only. The None handling is already safe.

VERIFY: no functional change to circuit breaker logic
```

### Phase 4: Fix M3 — journal.sqlite Documentation

```
ADD comment to docker-compose.yml at each journal.sqlite volume mount:
  # REQUIRES: touch captain-offline/journal.sqlite before first run
  # captain-start.sh creates this automatically; manual docker compose does not

This is documentation, not a code fix. The startup script handles it.
```

### Phase 5: Fix M4 — .env.template Bootstrap Variables

```
ADD to .env.template (new section):

# --- Bootstrap Configuration ---
# Used by scripts/bootstrap_production.py for initial data seeding
# BOOTSTRAP_ACCOUNT_ID=20319811
# BOOTSTRAP_USER_ID=primary_user
# BOOTSTRAP_STARTING_CAPITAL=150000
# BOOTSTRAP_MAX_POSITIONS=5
# BOOTSTRAP_MAX_CONTRACTS=15
```

### Phase 6: Fix M5 — Memory Limits Comment

```
ADD comment to docker-compose.local.yml at memory limits:
  # WARNING: These are WSL2 dev limits. Production should use 4G/2G minimum.
  # Monitor with: docker stats --no-stream

Do NOT change the actual limits (that's a production decision for Nomaan).
```

**ESCALATION POINT**: Ask Nomaan if he wants the limits increased now or if this should wait for a dedicated production config.

### Phase 7: Fix M6 — Explicit Docker Network

```
ADD to docker-compose.yml:

networks:
  captain:
    driver: bridge

ADD to each service:
  networks:
    - captain

VERIFY: docker compose config shows all services on captain network
```

### Phase 8: Fix M7 — Unused Table Decision

```
Do NOT delete p3_d28_account_lifecycle from init_questdb.py.

ADD comment above the CREATE TABLE:
  # NOTE: Table defined for future account_lifecycle.py integration.
  # Not currently referenced by any block. See 2026-04-13 audit.

VERIFY: no code references this table (already confirmed by QuestDB audit)
```

### Phase 9: Fix M8 — API Health Gate

```
READ captain-command/captain_command/main.py and api.py to find /api/health endpoint

ADD readiness check:
  The orchestrator should expose an is_ready flag.
  /api/health should return 503 until orchestrator reports ready.

VERIFY: curl http://localhost:8000/api/health returns 503 before orchestrator starts
```

### Phase 10: Session Closeout

```
1. Run unit tests
2. Validate docker compose config: docker compose -f docker-compose.yml -f docker-compose.local.yml config --quiet
3. Update AUDIT-MATRIX.md — fill in all S3 rows
4. Write S3-RESOLUTION-LOG.md
5. Commit:
   fix: docker infra hardening + medium issue cleanup

   - H4: Fix Redis healthcheck variable expansion
   - M1-M8: Zero-contract guard, VIX logging, env template, Docker network, health gate
```

---

## SESSION 4: Integration Verification & Regression

**Issues**: None (pure verification)
**Goal**: Prove the entire system works end-to-end after S1-S3 fixes

### Phase 1: Static Verification

```
1. grep -r "CH_COMMANDS" captain-command/ — should only appear in orchestrator subscriber
2. grep -r "STREAM_COMMANDS" — should appear in all 3 orchestrators + b1 + b5
3. grep -r "H26" — should return 0 matches
4. grep -r "publish_to_stream" — every call should have retry or be non-critical
5. docker compose config --quiet — valid compose
```

### Phase 2: Unit Tests

```
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/ \
  --ignore=tests/test_integration_e2e.py \
  --ignore=tests/test_pipeline_e2e.py \
  --ignore=tests/test_pseudotrader_account.py \
  --ignore=tests/test_offline_feedback.py \
  --ignore=tests/test_stress.py \
  --ignore=tests/test_account_lifecycle.py \
  -v
```

### Phase 3: Container Build & Start

```
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
# All 9 containers should be healthy
```

### Phase 4: Runtime Verification

```
1. Redis stream test:
   docker exec captain-redis redis-cli -a $REDIS_PASSWORD XADD stream:test '*' key value
   docker exec captain-redis redis-cli -a $REDIS_PASSWORD XLEN stream:test

2. QuestDB test:
   curl "http://localhost:9000/exec?query=SELECT+count()+FROM+p3_d00_asset_universe"

3. API test:
   curl http://localhost:8000/api/health
   # Should return 200 with orchestrator ready

4. GUI test:
   curl -s -o /dev/null -w "%{http_code}" http://localhost:80
   # Should return 200

5. Log inspection:
   docker compose logs captain-online --tail 50 | grep -i "error\|fatal\|critical"
   docker compose logs captain-command --tail 50 | grep -i "error\|fatal\|critical"
   docker compose logs captain-offline --tail 50 | grep -i "error\|fatal\|critical"
```

### Phase 5: Final Matrix Sign-Off

```
1. Update AUDIT-MATRIX.md — mark all rows as VERIFIED or DEFERRED
2. Fill in Post-Fix Regression Checklist
3. Write S4-VERIFICATION-LOG.md with all test results
4. Final commit:
   docs: complete 2026-04-13 audit — all findings resolved and verified
```

---

## Escalation Protocol

When a fix requires Nomaan's manual input:

1. **STOP** — do not attempt the fix
2. **Document** in the session resolution log:
   - What the issue is
   - What decision is needed
   - What the options are (with tradeoffs)
   - What you recommend
3. **Update AUDIT-MATRIX.md** status to `ESCALATED`
4. **Ask Nomaan** clearly: "I need your input on [X]. Options are [A] or [B]. I recommend [A] because [reason]. Please confirm."
5. **Wait** for response before proceeding
6. **Log** Nomaan's decision in the Escalation Log table

### Known Escalation Points

| Session | Issue | Question |
|---------|-------|----------|
| S1 | C3 | Are there H26 references outside captain-command that need updating? |
| S1 | H1 | If Command orchestrator uses blocking pub/sub listener, which migration approach? |
| S2 | C2 | Should TopstepX auth failure be fatal outside market hours (weekends)? |
| S3 | M5 | Increase memory limits now or defer to production config? |

---

## Session Prompts

### Starting a Session

Copy-paste the appropriate prompt below into a new Claude Code session.

### S1 Prompt
```
I'm running Session 1 of the 2026-04-13 pre-market readiness fix plan.

READ FIRST:
- docs/audit/audit_runs/2026-04-13_audit/ORCHESTRATOR.md (full plan — find SESSION 1)
- docs/audit/audit_runs/2026-04-13_audit/00-INITIAL-FINDINGS.md (issue details)
- docs/audit/audit_runs/2026-04-13_audit/AUDIT-MATRIX.md (tracking matrix)

Your job: Fix issues C1, C3, C4, C5, H1, H3 following the SESSION 1 phases exactly.
Follow the session contract. Read every file before modifying. Test after each fix.
Write S1-RESOLUTION-LOG.md and update AUDIT-MATRIX.md before closing.
If you hit an escalation point, stop and ask me.
Commit when done.
```

### S2 Prompt
```
I'm running Session 2 of the 2026-04-13 pre-market readiness fix plan.

READ FIRST:
- docs/audit/audit_runs/2026-04-13_audit/ORCHESTRATOR.md (full plan — find SESSION 2)
- docs/audit/audit_runs/2026-04-13_audit/00-INITIAL-FINDINGS.md (issue details)
- docs/audit/audit_runs/2026-04-13_audit/AUDIT-MATRIX.md (tracking matrix)
- docs/audit/audit_runs/2026-04-13_audit/S1-RESOLUTION-LOG.md (what S1 changed)

Your job: Fix issues C2 and H2 following the SESSION 2 phases exactly.
Follow the session contract. Read every file before modifying. Test after each fix.
Write S2-RESOLUTION-LOG.md and update AUDIT-MATRIX.md before closing.
If you hit an escalation point, stop and ask me.
Commit when done.
```

### S3 Prompt
```
I'm running Session 3 of the 2026-04-13 pre-market readiness fix plan.

READ FIRST:
- docs/audit/audit_runs/2026-04-13_audit/ORCHESTRATOR.md (full plan — find SESSION 3)
- docs/audit/audit_runs/2026-04-13_audit/00-INITIAL-FINDINGS.md (issue details)
- docs/audit/audit_runs/2026-04-13_audit/AUDIT-MATRIX.md (tracking matrix)
- docs/audit/audit_runs/2026-04-13_audit/S1-RESOLUTION-LOG.md (what S1 changed)
- docs/audit/audit_runs/2026-04-13_audit/S2-RESOLUTION-LOG.md (what S2 changed)

Your job: Fix issues H4, M1-M8 following the SESSION 3 phases exactly.
Follow the session contract. Read every file before modifying. Test after each fix.
Write S3-RESOLUTION-LOG.md and update AUDIT-MATRIX.md before closing.
If you hit an escalation point, stop and ask me.
Commit when done.
```

### S4 Prompt
```
I'm running Session 4 (final verification) of the 2026-04-13 pre-market readiness fix plan.

READ FIRST:
- docs/audit/audit_runs/2026-04-13_audit/ORCHESTRATOR.md (full plan — find SESSION 4)
- docs/audit/audit_runs/2026-04-13_audit/AUDIT-MATRIX.md (tracking matrix)
- docs/audit/audit_runs/2026-04-13_audit/S1-RESOLUTION-LOG.md
- docs/audit/audit_runs/2026-04-13_audit/S2-RESOLUTION-LOG.md
- docs/audit/audit_runs/2026-04-13_audit/S3-RESOLUTION-LOG.md

Your job: Run the full integration verification from SESSION 4.
No code changes — only testing, validation, and documentation.
Write S4-VERIFICATION-LOG.md and do final sign-off on AUDIT-MATRIX.md.
Commit the docs when done.
```
