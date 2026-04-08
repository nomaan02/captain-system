#!/bin/bash
# run_audit.sh — Hands-free Captain System codebase audit (EXEC-01 through EXEC-06)
#
# Automates Phase 1B of the audit workflow: runs each executor session via
# claude -p with skill invocations, passover chaining, and output validation.
#
# Usage:
#   cd ~/captain-system
#   bash docs/audit/run_audit.sh            # Full run EXEC-01 → EXEC-06
#   bash docs/audit/run_audit.sh exec_01    # Single session
#   bash docs/audit/run_audit.sh exec_04a exec_05a   # Parallel pair
#
# Prerequisites:
#   - claude CLI installed and authenticated
#   - codebase-audit-suite plugin installed
#   - Working directory: ~/captain-system

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

AUDIT_DIR="docs/audit"
PASS_DIR="$AUDIT_DIR/.passovers"
PROMPT_DIR="$AUDIT_DIR/.prompts"
LOG_FILE="$AUDIT_DIR/audit.log"

mkdir -p "$PASS_DIR" "$PROMPT_DIR"

# ─── Configuration ──────────────────────────────────────────────────────────
MODEL="claude-opus-4-6"
EFFORT="max"
ALLOWED_TOOLS="Read,Write,Edit,Glob,Grep,Bash,Skill"
# ────────────────────────────────────────────────────────────────────────────

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG_FILE"
}

# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVE OLD FILES
# ═══════════════════════════════════════════════════════════════════════════

archive_old_files() {
  log "Archiving previous audit outputs..."
  local count=0
  for f in "$AUDIT_DIR"/captain_online.md \
           "$AUDIT_DIR"/captain_offline.md \
           "$AUDIT_DIR"/captain_command.md \
           "$AUDIT_DIR"/cross_cutting.md; do
    if [[ -f "$f" ]]; then
      local base="${f%.md}"
      mv "$f" "${base}_old.md"
      log "  Renamed $(basename "$f") → $(basename "${base}_old.md")"
      ((count++)) || true
    fi
  done
  # Clean passover files from prior run
  rm -f "$PASS_DIR"/exec_*.txt
  if [[ $count -eq 0 ]]; then
    log "  No previous output files to archive."
  else
    log "  Archived $count file(s)."
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════

run_exec() {
  local name="$1"
  local prompt_file="$2"
  local expected_output="$3"

  log "===== $name START ====="
  local start_ts
  start_ts=$(date +%s)

  claude -p "$(cat "$prompt_file")" \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --allowedTools "$ALLOWED_TOOLS" \
    --output-format text \
    2>&1 | tee -a "$LOG_FILE"

  local exit_code=${PIPESTATUS[0]}
  local elapsed=$(( $(date +%s) - start_ts ))

  if [[ $exit_code -ne 0 ]]; then
    log "===== $name FAILED (exit $exit_code, ${elapsed}s) ====="
    return 1
  fi

  if [[ -f "$expected_output" ]] && [[ -s "$expected_output" ]]; then
    local lines
    lines=$(wc -l < "$expected_output")
    log "===== $name DONE (${lines} lines, ${elapsed}s) ====="
  else
    log "===== $name WARNING — output not found (${elapsed}s) ====="
  fi
  return 0
}

get_passover() {
  local file="$1"
  if [[ -f "$file" ]]; then
    cat "$file"
  else
    echo "(passover not available)"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
# PROMPT GENERATION — aligned with Phase 1B executor template
# ═══════════════════════════════════════════════════════════════════════════

generate_exec_01() {
  cat > "$PROMPT_DIR/exec_01.txt" << 'PROMPT'
You are auditing Captain system. Session 1 of 8.

## Skills — Invoke FIRST
Call these skills using the Skill tool before reading any files:
1. Skill(skill: "codebase-audit-suite:ln-629-lifecycle-auditor")
2. Skill(skill: "codebase-audit-suite:ln-628-concurrency-auditor")
After loading both skills, apply their audit checklists to the files below.

## Scope
Captain Online — Core & Ingestion: Startup, session management, data ingestion, bar aggregation, WebSocket handling, Opening Range tracking.

## Files
1. captain-online/captain_online/main.py
2. captain-online/captain_online/blocks/orchestrator.py
3. captain-online/captain_online/blocks/or_tracker.py
4. captain-online/captain_online/blocks/b1_data_ingestion.py
5. captain-online/captain_online/blocks/b1_features.py

## Per-File Extraction Format
For each file, use this structure:

### File: [path]
- **Purpose:** [one line]
- **Key functions/classes:** [with line numbers]
- **Session/schedule refs:** [session_id, market_open, cron, session registry refs]
- **QuestDB:** [table, operation, fields, line number]
- **Redis:** [channel, pub/sub, payload shape, line number]
- **Stubs/TODOs:** [with line numbers]
- **Notable:** [anything unexpected, risky, or smell-worthy]

Additionally for this session, extract:
- Startup/shutdown sequence and initialization order
- Async patterns: asyncio.create_task, await, locks, shared mutable state
- WebSocket connections: lifecycle, reconnection, error handling
- Data flow: market open → quote ingestion → bar formation
- Opening Range tracking: how OR window is defined, tracked, completed

## Output
Write to: docs/audit/captain_online.md — under heading "# Captain Online Audit" then "## Part 1: Core & Ingestion"

## Passover
End with:
## Session 1 Summary
- **Files audited:** [count]
- **Key findings:** [count and brief list]
- **Stub count:** [count]
- **Cross-service deps:** [Redis channels, QuestDB tables, shared modules discovered]

Also write ONLY the passover summary to: docs/audit/.passovers/exec_01.txt
PROMPT
}

generate_exec_02() {
  local passover
  passover="$(get_passover "$PASS_DIR/exec_01.txt")"

  cat > "$PROMPT_DIR/exec_02.txt" << PROMPT
You are auditing Captain system. Session 2 of 8.

## Skills — Invoke FIRST
Call these skills using the Skill tool before reading any files:
1. Skill(skill: "codebase-audit-suite:ln-624-code-quality-auditor")
2. Skill(skill: "codebase-audit-suite:ln-626-dead-code-auditor")
After loading both skills, apply their audit checklists to the files below.

## Previous Session Summary
$passover

## Scope
Captain Online — AIMs & Regime: AIM computation, regime probability classification, AIM aggregation via DMA weights (Blocks 2-3).

## Files
1. captain-online/captain_online/blocks/b2_regime_probability.py
2. captain-online/captain_online/blocks/b3_aim_aggregation.py
3. shared/aim_compute.py
4. shared/aim_feature_loader.py

## Per-File Extraction Format
For each file:

### File: [path]
- **Purpose:** [one line]
- **Key functions/classes:** [with line numbers]
- **Session/schedule refs:** [any triggers, session refs]
- **QuestDB:** [table, operation, fields, line number]
- **Redis:** [channel, pub/sub, line number]
- **Stubs/TODOs:** [with line numbers]
- **Notable:** [anything unexpected]

Additionally for this session, extract:
- AIM inventory: which AIMs are implemented vs stubbed (ID, name, status)
- Feature computation: what features are calculated, from which data sources
- Regime classifier: method (HMM/threshold/rule-based), input features, output states
- MoE/DMA aggregation: how AIM weights are loaded and applied, forgetting factor
- Code quality: cyclomatic complexity hotspots, magic numbers, nested logic
- Dead code: unused imports, unreachable branches, commented-out blocks

## Output
APPEND to: docs/audit/captain_online.md — under heading "## Part 2: AIMs & Regime"
(Part 1 already exists — do NOT overwrite it)

## Passover
End with:
## Session 2 Summary
- **Files audited:** [count]
- **Key findings:** [count and brief list]
- **Stub count:** [count]
- **AIM inventory:** [ID → status for each AIM]
- **Cross-service deps:** [QuestDB tables, input contract for Kelly sizing]

Also write ONLY the passover summary to: docs/audit/.passovers/exec_02.txt
PROMPT
}

generate_exec_03() {
  local passover
  passover="$(get_passover "$PASS_DIR/exec_02.txt")"

  cat > "$PROMPT_DIR/exec_03.txt" << PROMPT
You are auditing Captain system. Session 3 of 8.

## Skills — Invoke FIRST
Call these skills using the Skill tool before reading any files:
1. Skill(skill: "codebase-audit-suite:ln-623-code-principles-auditor")
2. Skill(skill: "codebase-audit-suite:ln-627-observability-auditor")
After loading both skills, apply their audit checklists to the files below.

## Previous Session Summary
$passover

## Scope
Captain Online — Kelly to Signal Output: Kelly sizing (7 layers), trade selection, quality gate, circuit breaker (4 layers), signal output, position monitoring, shadow monitoring, concentration, capacity (Blocks 4-9).

## Files
1. captain-online/captain_online/blocks/b4_kelly_sizing.py
2. captain-online/captain_online/blocks/b5_trade_selection.py
3. captain-online/captain_online/blocks/b5b_quality_gate.py
4. captain-online/captain_online/blocks/b5c_circuit_breaker.py
5. captain-online/captain_online/blocks/b6_signal_output.py
6. captain-online/captain_online/blocks/b7_position_monitor.py
7. captain-online/captain_online/blocks/b7_shadow_monitor.py
8. captain-online/captain_online/blocks/b8_concentration_monitor.py
9. captain-online/captain_online/blocks/b9_capacity_evaluation.py

## Per-File Extraction Format
For each file:

### File: [path]
- **Purpose:** [one line]
- **Key functions/classes:** [with line numbers]
- **Session/schedule refs:** [any triggers, session refs]
- **QuestDB:** [table, operation, fields, line number]
- **Redis:** [channel, pub/sub, payload shape, line number]
- **Stubs/TODOs:** [with line numbers]
- **Notable:** [anything unexpected]

Additionally for this session, extract:
- Kelly layers: enumerate all 7 steps. Which are implemented?
- Circuit breaker layers: enumerate L1-L4. Trigger conditions? Recovery logic?
- Signal output: exact Redis payload published to captain:signals:{user_id}
- Position monitoring: how B7 tracks TP/SL, what triggers close
- Shadow monitoring: how B7_shadow tracks theoretical parity-skipped outcomes
- DRY violations: repeated logic across B5/B5b/B5c
- Observability: structured logging, log levels, health metrics

## Output
APPEND to: docs/audit/captain_online.md — under heading "## Part 3: Kelly to Signal Output"
(Parts 1-2 already exist — do NOT overwrite)

## Passover
End with:
## Session 3 Summary
- **Files audited:** [count]
- **Key findings:** [count and brief list]
- **Stub count:** [count]
- **Kelly layers:** [step → status inventory]
- **CB layers:** [L1-L4 → status inventory]
- **Redis channels (Online total):** [complete list]
- **QuestDB tables (Online total):** [complete list]
- **Signal contract:** [fields published to Redis]

Also write ONLY the passover summary to: docs/audit/.passovers/exec_03.txt
PROMPT
}

generate_exec_04a() {
  cat > "$PROMPT_DIR/exec_04a.txt" << 'PROMPT'
You are auditing Captain system. Session 4a of 8.

## Skills — Invoke FIRST
Call these skills using the Skill tool before reading any files:
1. Skill(skill: "codebase-audit-suite:ln-620-codebase-auditor")
2. Skill(skill: "codebase-audit-suite:ln-625-dependencies-auditor")
After loading both skills, apply their audit checklists to the files below.

## Scope
Captain Offline — Orchestrator + B1-B2: Strategic brain process. Event-driven + scheduled tasks for AIM lifecycle, DMA weight updates, BOCPD changepoint detection, drift detection. Category A learning uses ALL signals; Category B uses own trades only.

## Files
1. captain-offline/captain_offline/main.py
2. captain-offline/captain_offline/blocks/orchestrator.py
3. captain-offline/captain_offline/blocks/bootstrap.py
4. captain-offline/captain_offline/blocks/version_snapshot.py
5. captain-offline/captain_offline/blocks/b1_aim_lifecycle.py
6. captain-offline/captain_offline/blocks/b1_aim16_hmm.py
7. captain-offline/captain_offline/blocks/b1_dma_update.py
8. captain-offline/captain_offline/blocks/b1_drift_detection.py
9. captain-offline/captain_offline/blocks/b1_hdwm_diversity.py
10. captain-offline/captain_offline/blocks/b2_bocpd.py
11. captain-offline/captain_offline/blocks/b2_cusum.py
12. captain-offline/captain_offline/blocks/b2_level_escalation.py

## Per-File Extraction Format
For each file:

### File: [path]
- **Purpose:** [one line]
- **Key functions/classes:** [with line numbers]
- **Session/schedule refs:** [cron, interval, event triggers]
- **QuestDB:** [table, operation, fields, line number]
- **Redis:** [channel, pub/sub, line number]
- **Stubs/TODOs:** [with line numbers]
- **Notable:** [anything unexpected]

Additionally for this session, extract:
- Scheduled tasks: what runs on schedule? Cron expression or interval?
- Event handlers: what Redis messages trigger what actions?
- Category A vs B learning: does this block learn from ALL signals or own trades only?
- Startup sequence: initialization order, dependencies, health checks
- Dead code: unused functions, unreachable branches

## Output
Write to: docs/audit/captain_offline.md — under heading "# Captain Offline Audit" then "## Part 1: Orchestrator + B1-B2"

## Passover
End with:
## Session 4a Summary
- **Files audited:** [count]
- **Key findings:** [count and brief list]
- **Stub count:** [count]
- **Scheduled tasks:** [task → timing inventory]
- **Event handlers:** [channel → handler inventory]
- **Cross-service deps:** [QuestDB tables, Redis channels]

Also write ONLY the passover summary to: docs/audit/.passovers/exec_04a.txt
PROMPT
}

generate_exec_04b() {
  local passover
  passover="$(get_passover "$PASS_DIR/exec_04a.txt")"

  cat > "$PROMPT_DIR/exec_04b.txt" << PROMPT
You are auditing Captain system. Session 4b of 8.

## Skills — Invoke FIRST
Call these skills using the Skill tool before reading any files:
1. Skill(skill: "codebase-audit-suite:ln-620-codebase-auditor")
2. Skill(skill: "codebase-audit-suite:ln-625-dependencies-auditor")
After loading both skills, apply their audit checklists to the files below.

## Previous Session Summary
$passover

## Scope
Captain Offline — B3-B9: Pseudotrader simulation, AIM injection, parameter sensitivity, asset expansion, TSM simulation, CB param recalibration, Kelly update, system diagnostics.

## Files
1. captain-offline/captain_offline/blocks/b3_pseudotrader.py
2. captain-offline/captain_offline/blocks/b4_injection.py
3. captain-offline/captain_offline/blocks/b5_sensitivity.py
4. captain-offline/captain_offline/blocks/b6_auto_expansion.py
5. captain-offline/captain_offline/blocks/b7_tsm_simulation.py
6. captain-offline/captain_offline/blocks/b8_cb_params.py
7. captain-offline/captain_offline/blocks/b8_kelly_update.py
8. captain-offline/captain_offline/blocks/b9_diagnostic.py

## Per-File Extraction Format
For each file:

### File: [path]
- **Purpose:** [one line]
- **Key functions/classes:** [with line numbers]
- **Session/schedule refs:** [any triggers]
- **QuestDB:** [table, operation, fields, line number]
- **Redis:** [channel, pub/sub, line number]
- **Stubs/TODOs:** [with line numbers]
- **Notable:** [anything unexpected]

Additionally for this session, extract:
- Pseudotrader: how B3 simulates trades, data sources, outcome reporting
- Kelly update: which of 7 steps are recalibrated, from what data
- CB params: which CB layers updated, beta_b recalibration logic
- Code quality: complexity hotspots, god functions, magic numbers
- External dependencies: numpy, scipy, pandas usage

## Output
APPEND to: docs/audit/captain_offline.md — under heading "## Part 2: B3-B9"
(Part 1 already exists — do NOT overwrite)

## Passover
End with:
## Session 4b Summary
- **Files audited:** [count]
- **Key findings:** [count and brief list]
- **Stub count:** [count]
- **QuestDB tables (Offline total):** [complete list]
- **Redis channels (Offline total):** [complete list]
- **External deps:** [package inventory]
- **Cross-service deps:** [what Offline expects from Online/Command]

Also write ONLY the passover summary to: docs/audit/.passovers/exec_04b.txt
PROMPT
}

generate_exec_05a() {
  cat > "$PROMPT_DIR/exec_05a.txt" << 'PROMPT'
You are auditing Captain system. Session 5a of 8.

## Skills — Invoke FIRST
Call these skills using the Skill tool before reading any files:
1. Skill(skill: "codebase-audit-suite:ln-621-security-auditor")
2. Skill(skill: "codebase-audit-suite:ln-628-concurrency-auditor")
After loading both skills, apply their audit checklists to the files below.

## Scope
Captain Command — Core + API: Always-on FastAPI linking layer. Routes signals from Redis to GUI/TopstepX, serves WebSocket to GUI, exposes REST API, manages TSM.

SECURITY NOTE: This service has Docker socket (/var/run/docker.sock) and vault access. Pay close attention to input validation, auth, and privilege escalation.

## Files
1. captain-command/captain_command/main.py
2. captain-command/captain_command/api.py
3. captain-command/captain_command/blocks/orchestrator.py
4. captain-command/captain_command/blocks/b1_core_routing.py
5. captain-command/captain_command/blocks/b2_gui_data_server.py
6. captain-command/captain_command/blocks/b3_api_adapter.py
7. captain-command/captain_command/blocks/b4_tsm_manager.py

## Per-File Extraction Format
For each file:

### File: [path]
- **Purpose:** [one line]
- **Key functions/classes:** [with line numbers]
- **Session/schedule refs:** [any triggers]
- **QuestDB:** [table, operation, fields, line number]
- **Redis:** [channel, pub/sub, line number]
- **Stubs/TODOs:** [with line numbers]
- **Notable:** [anything unexpected]

Additionally for this session, extract:
- API endpoints: method, path, auth required?, input validation?, line number
- WebSocket connections: to GUI, from Redis; lifecycle, reconnection, error handling
- Security: Docker socket usage, vault access, sanitization, CORS, auth
- Parity filter: _check_parity_skip implementation, daily counter
- Async patterns: shared state access, locks, race conditions

## Output
Write to: docs/audit/captain_command.md — under heading "# Captain Command Audit" then "## Part 1: Core + API"

## Passover
End with:
## Session 5a Summary
- **Files audited:** [count]
- **Key findings:** [count and brief list]
- **Stub count:** [count]
- **API endpoints:** [method + path inventory]
- **WebSocket connections:** [inventory]
- **Security concerns:** [ranked by severity]

Also write ONLY the passover summary to: docs/audit/.passovers/exec_05a.txt
PROMPT
}

generate_exec_05b() {
  local passover
  passover="$(get_passover "$PASS_DIR/exec_05a.txt")"

  cat > "$PROMPT_DIR/exec_05b.txt" << PROMPT
You are auditing Captain system. Session 5b of 8.

## Skills — Invoke FIRST
Call these skills using the Skill tool before reading any files:
1. Skill(skill: "codebase-audit-suite:ln-621-security-auditor")
2. Skill(skill: "codebase-audit-suite:ln-628-concurrency-auditor")
After loading both skills, apply their audit checklists to the files below.

## Previous Session Summary
$passover

## Scope
Captain Command — Reports to Replay: Injection flow, report generation, Telegram notifications, trade reconciliation, incident response, data validation, session replay, Telegram bot remote control (Blocks 5-11).

## Files
1. captain-command/captain_command/blocks/b5_injection_flow.py
2. captain-command/captain_command/blocks/b6_reports.py
3. captain-command/captain_command/blocks/b7_notifications.py
4. captain-command/captain_command/blocks/b8_reconciliation.py
5. captain-command/captain_command/blocks/b9_incident_response.py
6. captain-command/captain_command/blocks/b10_data_validation.py
7. captain-command/captain_command/blocks/b11_replay_runner.py
8. captain-command/captain_command/blocks/telegram_bot.py

## Per-File Extraction Format
For each file:

### File: [path]
- **Purpose:** [one line]
- **Key functions/classes:** [with line numbers]
- **Session/schedule refs:** [any triggers]
- **QuestDB:** [table, operation, fields, line number]
- **Redis:** [channel, pub/sub, line number]
- **Stubs/TODOs:** [with line numbers]
- **Notable:** [anything unexpected]

Additionally for this session, extract:
- Telegram bot: commands exposed, auth checks, rate limiting, sensitive data?
- Notifications: triggers, priority levels, delivery guarantees
- Reconciliation: what compared (signal vs execution), frequency, mismatch handling
- Replay: how B11 invokes shared/replay_engine.py, inputs/outputs
- Security: Telegram token handling, external API auth, injection vectors

## Output
APPEND to: docs/audit/captain_command.md — under heading "## Part 2: Reports to Replay"
(Part 1 already exists — do NOT overwrite)

## Passover
End with:
## Session 5b Summary
- **Files audited:** [count]
- **Key findings:** [count and brief list]
- **Stub count:** [count]
- **QuestDB tables (Command total):** [complete list]
- **Redis channels (Command total):** [complete list]
- **External integrations:** [Telegram, TopstepX endpoints]
- **Notification inventory:** [alert types and triggers]

Also write ONLY the passover summary to: docs/audit/.passovers/exec_05b.txt
PROMPT
}

generate_exec_06() {
  local pass_03 pass_04b pass_05b
  pass_03="$(get_passover "$PASS_DIR/exec_03.txt")"
  pass_04b="$(get_passover "$PASS_DIR/exec_04b.txt")"
  pass_05b="$(get_passover "$PASS_DIR/exec_05b.txt")"

  cat > "$PROMPT_DIR/exec_06.txt" << PROMPT
You are auditing Captain system. Session 6 of 8 (FINAL).

## Skills — Invoke FIRST
Call these skills using the Skill tool before reading any files:
1. Skill(skill: "codebase-audit-suite:ln-622-build-auditor")
2. Skill(skill: "codebase-audit-suite:ln-627-observability-auditor")
After loading both skills, apply their audit checklists to the files below.

## Previous Session Summaries

### Online (Sessions 1-3):
$pass_03

### Offline (Sessions 4a-4b):
$pass_04b

### Command (Sessions 5a-5b):
$pass_05b

## Scope
Cross-Cutting: Shared library (mounted read-only into all containers), config files, Dockerfiles, requirements, QuestDB schemas. Produce cross-service aggregation tables.

## Files — Shared Library
1. shared/questdb_client.py
2. shared/redis_client.py
3. shared/topstep_client.py
4. shared/topstep_stream.py
5. shared/constants.py
6. shared/vault.py
7. shared/journal.py
8. shared/account_lifecycle.py
9. shared/contract_resolver.py
10. shared/bar_cache.py
11. shared/statistics.py
12. shared/vix_provider.py
13. shared/replay_engine.py (large — skim for structure and QuestDB usage)
14. shared/trade_source.py
15. shared/signal_replay.py

## Files — Config & Build
16. scripts/init_questdb.py (QuestDB table schemas)
17. config/session_registry.json
18. config/compliance_gate.json
19. config/contract_ids.json
20. captain-online/Dockerfile
21. captain-offline/Dockerfile
22. captain-command/Dockerfile
23. captain-online/requirements.txt
24. captain-offline/requirements.txt
25. captain-command/requirements.txt

## Per-File Extraction
For shared files:
- **Purpose:** [one line]
- **Key functions/classes:** [with line numbers]
- **Used by:** [Online, Offline, Command, or all]
- **Security:** [secrets handling, encryption, token storage]
- **Error handling:** [retries, timeouts, failure modes]

For Dockerfiles:
- Base image + version, multi-stage?, running as root?, layer efficiency

For requirements.txt:
- Pinned versions?, vulnerable packages?, duplicates across services

For init_questdb.py:
- Complete table inventory with column definitions

## Aggregation Tables
Build from ALL session summaries plus this session's files:

### Table 1: QuestDB Table Registry
| Table | Owner (writes) | Readers | Key Columns | Schema Source |

### Table 2: Redis Channel Registry
| Channel Pattern | Publisher | Subscriber(s) | Payload Shape | Purpose |

### Table 3: Trigger/Schedule Registry
| Trigger | Type | Service | Handler | Timing |

### Table 4: External Integration Registry
| Integration | Service | Auth Method | Endpoints |

### Table 5: Dependency Matrix
| Package | Online | Offline | Command | Version(s) |

## Output
Write ALL findings and tables to: docs/audit/cross_cutting.md

Include at the end:
## Audit Summary
- Total files audited across all 8 sessions
- Top findings ranked by severity (CRITICAL > HIGH > MEDIUM > LOW)
- Cross-service consistency issues (channel name mismatches, schema drift)
- Recommended priority fixes

Also write final summary to: docs/audit/.passovers/exec_06.txt
PROMPT
}

# ═══════════════════════════════════════════════════════════════════════════
# EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

run_all() {
  archive_old_files
  log ""

  # ── Phase 1: Online pipeline (sequential: 01 → 02 → 03) ──
  log "Phase 1: Online pipeline (EXEC-01 → 02 → 03)"

  generate_exec_01
  run_exec "EXEC-01" "$PROMPT_DIR/exec_01.txt" "$AUDIT_DIR/captain_online.md"

  generate_exec_02
  run_exec "EXEC-02" "$PROMPT_DIR/exec_02.txt" "$AUDIT_DIR/captain_online.md"

  generate_exec_03
  run_exec "EXEC-03" "$PROMPT_DIR/exec_03.txt" "$AUDIT_DIR/captain_online.md"

  log "Phase 1 complete."
  log ""

  # ── Phase 2: Offline + Command in parallel ──
  log "Phase 2: Offline (04a→04b) || Command (05a→05b)"

  (
    generate_exec_04a
    run_exec "EXEC-04a" "$PROMPT_DIR/exec_04a.txt" "$AUDIT_DIR/captain_offline.md"
    generate_exec_04b
    run_exec "EXEC-04b" "$PROMPT_DIR/exec_04b.txt" "$AUDIT_DIR/captain_offline.md"
  ) &
  local pid_offline=$!

  (
    generate_exec_05a
    run_exec "EXEC-05a" "$PROMPT_DIR/exec_05a.txt" "$AUDIT_DIR/captain_command.md"
    generate_exec_05b
    run_exec "EXEC-05b" "$PROMPT_DIR/exec_05b.txt" "$AUDIT_DIR/captain_command.md"
  ) &
  local pid_command=$!

  local offline_ok=0 command_ok=0
  wait $pid_offline || offline_ok=1
  wait $pid_command || command_ok=1

  [[ $offline_ok -ne 0 ]] && log "WARNING: Offline pipeline had failures"
  [[ $command_ok -ne 0 ]] && log "WARNING: Command pipeline had failures"

  log "Phase 2 complete."
  log ""

  # ── Phase 3: Cross-cutting (EXEC-06) ──
  log "Phase 3: Cross-cutting aggregation (EXEC-06)"

  generate_exec_06
  run_exec "EXEC-06" "$PROMPT_DIR/exec_06.txt" "$AUDIT_DIR/cross_cutting.md"

  log ""
  log "═══════════════════════════════════════════════════"
  log "  AUDIT COMPLETE"
  log "  Output files:"
  for f in captain_online.md captain_offline.md captain_command.md cross_cutting.md; do
    if [[ -f "$AUDIT_DIR/$f" ]]; then
      log "    $AUDIT_DIR/$f  ($(wc -l < "$AUDIT_DIR/$f") lines)"
    else
      log "    $AUDIT_DIR/$f  (MISSING)"
    fi
  done
  log "  Full log: $LOG_FILE"
  log "═══════════════════════════════════════════════════"
}

run_single() {
  for session in "$@"; do
    case "$session" in
      exec_01)
        generate_exec_01
        run_exec "EXEC-01" "$PROMPT_DIR/exec_01.txt" "$AUDIT_DIR/captain_online.md"
        ;;
      exec_02)
        generate_exec_02
        run_exec "EXEC-02" "$PROMPT_DIR/exec_02.txt" "$AUDIT_DIR/captain_online.md"
        ;;
      exec_03)
        generate_exec_03
        run_exec "EXEC-03" "$PROMPT_DIR/exec_03.txt" "$AUDIT_DIR/captain_online.md"
        ;;
      exec_04a)
        generate_exec_04a
        run_exec "EXEC-04a" "$PROMPT_DIR/exec_04a.txt" "$AUDIT_DIR/captain_offline.md"
        ;;
      exec_04b)
        generate_exec_04b
        run_exec "EXEC-04b" "$PROMPT_DIR/exec_04b.txt" "$AUDIT_DIR/captain_offline.md"
        ;;
      exec_05a)
        generate_exec_05a
        run_exec "EXEC-05a" "$PROMPT_DIR/exec_05a.txt" "$AUDIT_DIR/captain_command.md"
        ;;
      exec_05b)
        generate_exec_05b
        run_exec "EXEC-05b" "$PROMPT_DIR/exec_05b.txt" "$AUDIT_DIR/captain_command.md"
        ;;
      exec_06)
        generate_exec_06
        run_exec "EXEC-06" "$PROMPT_DIR/exec_06.txt" "$AUDIT_DIR/cross_cutting.md"
        ;;
      *)
        log "Unknown: $session (valid: exec_01..exec_06, exec_04a/b, exec_05a/b)"
        exit 1
        ;;
    esac
  done
}

# ── Entry point ──
if [[ $# -eq 0 ]]; then
  run_all
else
  run_single "$@"
fi
