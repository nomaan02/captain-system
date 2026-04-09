#!/bin/bash
# run_implementation.sh — Phase 3: ABC Implementation Workflow
#
# Automates the Agent A → Agent C (Executor) → Agent B (Validator) cycle
# for resolving all gaps in the Captain System reconciliation matrix.
#
# Usage:
#   cd ~/captain-system
#   bash scripts/run_implementation.sh              # Full run (all phases)
#   bash scripts/run_implementation.sh --phase1     # Single phase
#   bash scripts/run_implementation.sh --session 05 # Single session
#   bash scripts/run_implementation.sh --validate 05 # Validator only for session 05
#   bash scripts/run_implementation.sh --dashboard   # Show current dashboard
#   bash scripts/run_implementation.sh --final       # Final validation only
#
# Prerequisites:
#   - claude CLI installed and authenticated
#   - codebase-audit-suite plugin installed
#   - Obsidian vault accessible at /mnt/c/Users/nomaa/Documents/Quant_Project/
#   - plans/CAPTAIN_RECONCILIATION_MATRIX.md populated (Agent A output)
#   - Working directory: ~/captain-system

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# ─── Paths ──────────────────────────────────────────────────────────────────
MATRIX="plans/CAPTAIN_RECONCILIATION_MATRIX.md"
PROMPTS_DIR="plans/prompts"
PROMPT_GEN_DIR="$PROMPTS_DIR/.generated"
LOGS_DIR="logs/implementation"
PASS_DIR="$PROMPTS_DIR/.passovers"
SPEC_REF="docs/audit/spec_reference.md"
GAP_FILE="docs/audit/master_gap_analysis.md"
VAL_LOG="docs/audit/validation_progress_log.md"
VAULT="/mnt/c/Users/nomaa/Documents/Quant_Project"

# ─── Configuration ──────────────────────────────────────────────────────────
MODEL="claude-opus-4-6"
EFFORT="max"
EXECUTOR_TOOLS="Read,Write,Edit,Glob,Grep,Bash,Skill"
VALIDATOR_TOOLS="Read,Glob,Grep,Write,Skill"

mkdir -p "$PROMPT_GEN_DIR" "$LOGS_DIR" "$PASS_DIR"

# ═══════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOGS_DIR/run.log"; }

banner() {
  local msg="$1"
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "  $msg"
  echo "════════════════════════════════════════════════════════════════"
  echo ""
}

dashboard() {
  echo ""
  echo "┌─────────────────────────────────────────┐"
  echo "│           RECONCILIATION DASHBOARD       │"
  echo "├──────────────┬──────────────────────────┤"
  for status in UNRESOLVED DECISION_NEEDED DEFERRED FIXED VERIFIED RESOLVED; do
    local count
    count=$(grep -c '\*\*Status:\*\* '"$status" "$MATRIX" 2>/dev/null) || count=0
    printf "│ %-12s │ %24s │\n" "$status" "$count"
  done
  echo "├──────────────┼──────────────────────────┤"
  local total
  total=$(grep -c '\*\*Status:\*\*' "$MATRIX" 2>/dev/null) || total=0
  printf "│ %-12s │ %24s │\n" "TOTAL" "$total"
  echo "└──────────────┴──────────────────────────┘"
  echo ""
}

human_gate() {
  local msg="${1:-Press ENTER to continue, Ctrl+C to stop}"
  if [[ "${NO_GATE:-}" == "1" ]]; then
    log "(auto) $msg"
    return 0
  fi
  echo ""
  echo ">>> $msg"
  read -r
}

run_pytest() {
  log "Running pytest..."
  local log_file="$LOGS_DIR/pytest_session_${1}.log"
  PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
    python3 -B -m pytest tests/ \
    --ignore=tests/test_integration_e2e.py \
    --ignore=tests/test_pipeline_e2e.py \
    --ignore=tests/test_pseudotrader_account.py \
    --ignore=tests/test_offline_feedback.py \
    --ignore=tests/test_stress.py \
    --ignore=tests/test_account_lifecycle.py \
    -v --tb=short 2>&1 | tee "$log_file"
  local exit_code=${PIPESTATUS[0]}
  if [[ $exit_code -ne 0 ]]; then
    log "WARNING: pytest returned exit code $exit_code"
    if [[ "${NO_GATE:-}" == "1" ]]; then
      echo ""
      echo "╔══════════════════════════════════════════════════════════════╗"
      echo "║  PYTEST FAILED — SESSION $(printf '%02d' "$1")                            ║"
      echo "╠══════════════════════════════════════════════════════════════╣"
      echo "║  Log: $log_file"
      echo "║  Debug:   Review failing tests, fix, then resume:"
      echo "║  Resume:  bash scripts/run_implementation.sh --session $(printf '%02d' "$1")"
      echo "╚══════════════════════════════════════════════════════════════╝"
      exit 1
    fi
    echo ""
    echo ">>> Tests failed. Review $log_file"
    echo ">>> Press ENTER to continue to validation anyway, Ctrl+C to stop"
    read -r
  else
    log "pytest PASSED"
  fi
}

get_passover() {
  local file="$1"
  if [[ -f "$file" ]]; then
    cat "$file"
  else
    echo "(passover not available — first session)"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
# EXECUTOR — Run Agent C for a session
# ═══════════════════════════════════════════════════════════════════════════

run_executor() {
  local n="$1"
  local padded
  padded=$(printf "%02d" "$n")
  local prompt_file="$PROMPT_GEN_DIR/session_${padded}_prompt.txt"
  local log_file="$LOGS_DIR/exec_${padded}.log"
  local passover_out="$PASS_DIR/session_${padded}.txt"

  # Generate prompt dynamically
  "generate_session_${padded}"

  banner "EXECUTOR SESSION ${padded} START"
  log "Executor session $padded — prompt: $prompt_file"
  local start_ts
  start_ts=$(date +%s)

  claude -p "$(cat "$prompt_file")" \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --dangerously-skip-permissions \
    --output-format text \
    2>&1 | tee -a "$log_file"

  local exit_code=${PIPESTATUS[0]}
  local elapsed=$(( $(date +%s) - start_ts ))
  local mins=$(( elapsed / 60 ))
  local secs=$(( elapsed % 60 ))

  if [[ $exit_code -ne 0 ]]; then
    log "EXECUTOR $padded FAILED (exit $exit_code, ${mins}m${secs}s)"
    if [[ "${NO_GATE:-}" == "1" ]]; then
      echo ""
      echo "╔══════════════════════════════════════════════════════════════╗"
      echo "║  EXECUTOR FAILED — SESSION $padded                            ║"
      echo "╠══════════════════════════════════════════════════════════════╣"
      echo "║  Log: $log_file"
      echo "║  Resume:  bash scripts/run_implementation.sh --session $padded"
      echo "╚══════════════════════════════════════════════════════════════╝"
      exit 1
    fi
    echo ">>> Executor failed. Review log: $log_file"
    echo ">>> Press ENTER to continue anyway, Ctrl+C to abort"
    read -r
  else
    log "EXECUTOR $padded DONE (${mins}m${secs}s)"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
# VALIDATOR — Run Agent B for a session
# ═══════════════════════════════════════════════════════════════════════════

run_validator() {
  local n="$1"
  local padded
  padded=$(printf "%02d" "$n")
  local cycle_prompt="$PROMPT_GEN_DIR/agent_b_cycle_${padded}.txt"
  local log_file="$LOGS_DIR/validate_${padded}.log"

  # Build validator prompt from template + passover
  local passover_file="$PASS_DIR/session_${padded}.txt"
  local passover_content
  passover_content=$(get_passover "$passover_file")

  # Build validator prompt — write directly to avoid sed multiline issues
  cat > "$cycle_prompt" <<VALBLOCK
# Agent B — Validation Cycle for Session ${padded}

You are **Agent B (Validator)**. This is validation cycle ${padded}.
**You NEVER write implementation code.**

## Re-read Now
- \`plans/CAPTAIN_RECONCILIATION_MATRIX.md\` — re-read in full before validating

## What Changed (Session ${padded})

${passover_content}

## Validation Steps

For EACH finding marked \`FIXED\` in the matrix from session ${padded}:

1. **Read the changed file(s)** — examine the actual diff
2. **Read the spec reference** — find the §N section in \`docs/audit/spec_reference.md\`
3. **Cross-reference** with Obsidian vault at \`/mnt/c/Users/nomaa/Documents/Quant_Project/\` if spec_reference.md is ambiguous
4. **Confirm alignment**: \`ALIGNED\` / \`PARTIAL\` / \`DIVERGENT\`
5. **Check for regressions** against adjacent gaps
6. **Log** to \`docs/audit/validation_progress_log.md\`

## Post-Validation Skills

Run these on each changed file:
- \`/ln-641-pattern-analyzer\` — pattern compliance
- \`/ln-614-docs-fact-checker\` — table name and constant verification

## Report Format

After validation, output:

\`\`\`
=== VALIDATION CYCLE ${padded} REPORT ===
Findings validated: N
  ALIGNED:   N
  PARTIAL:   N
  DIVERGENT: N
Cumulative: N / 67 total
Open concerns: [list or "none"]
\`\`\`

## Matrix Updates

For each validated finding:
- \`ALIGNED\` → update matrix status to \`VERIFIED\`
- \`PARTIAL\` → keep \`FIXED\`, add note with remaining delta
- \`DIVERGENT\` → revert to \`UNRESOLVED\`, add regression note

Update the §6 Dashboard counts after all updates.

## Rules
1. Never write implementation code
2. Always read actual files — never trust summaries
3. Always read the spec section — compare against §N
4. Re-read matrix before starting — executor may have changed it
VALBLOCK

  banner "VALIDATOR CYCLE ${padded} START"
  log "Validator cycle $padded — prompt: $cycle_prompt"
  local start_ts
  start_ts=$(date +%s)

  claude -p "$(cat "$cycle_prompt")" \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --allowedTools "$VALIDATOR_TOOLS" \
    --output-format text \
    2>&1 | tee -a "$log_file"

  local exit_code=${PIPESTATUS[0]}
  local elapsed=$(( $(date +%s) - start_ts ))
  local mins=$(( elapsed / 60 ))
  local secs=$(( elapsed % 60 ))

  if [[ $exit_code -ne 0 ]]; then
    log "VALIDATOR $padded FAILED (exit $exit_code, ${mins}m${secs}s)"
    if [[ "${NO_GATE:-}" == "1" ]]; then
      echo ""
      echo "╔══════════════════════════════════════════════════════════════╗"
      echo "║  VALIDATOR FAILED — SESSION $padded                           ║"
      echo "╠══════════════════════════════════════════════════════════════╣"
      echo "║  Log: $log_file"
      echo "║  Executor already passed — re-run validator only:"
      echo "║  Resume:  bash scripts/run_implementation.sh --validate $padded"
      echo "╚══════════════════════════════════════════════════════════════╝"
      exit 1
    fi
  else
    log "VALIDATOR $padded DONE (${mins}m${secs}s)"
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
# SKILL RUNNER
# ═══════════════════════════════════════════════════════════════════════════

run_skill() {
  local skill="$1"
  local log_file="$LOGS_DIR/skill_${skill}_$(date +%s).log"
  log "Running skill: $skill"

  claude -p "Run the audit skill /${skill} against the full codebase. Output findings." \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --allowedTools "$VALIDATOR_TOOLS" \
    --output-format text \
    2>&1 | tee -a "$log_file"

  log "Skill $skill complete"
}

# ═══════════════════════════════════════════════════════════════════════════
# PHASE RUNNER
# ═══════════════════════════════════════════════════════════════════════════

run_phase() {
  local name="$1"; shift
  local sessions=() skills=()

  # Parse: sessions... -- skills...
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--" ]]; then shift; break; fi
    sessions+=("$1"); shift
  done
  skills=("$@")

  banner "PHASE: ${name}"
  log "Sessions: ${sessions[*]} | Skills: ${skills[*]:-none}"

  for s in "${sessions[@]}"; do
    run_executor "$s"
    run_pytest "$s"
    run_validator "$s"
    printf "%02d" "$s" > "$LOGS_DIR/.last_complete"
    log "Session $s complete (progress saved)"
    dashboard
    human_gate "Session ${s} complete. ENTER for next session, Ctrl+C to stop."
  done

  if [[ ${#skills[@]} -gt 0 ]]; then
    log "Running phase-end skills: ${skills[*]}"
    for skill in "${skills[@]}"; do
      run_skill "$skill"
    done
  fi

  log "Phase '${name}' complete."
}

# ═══════════════════════════════════════════════════════════════════════════
# SESSION PROMPT GENERATORS
#
# Each function writes a self-contained prompt for Agent C (Executor).
# Pattern: passover from prior session (unquoted heredoc for variable
# expansion) + main body (quoted heredoc for literal content).
# ═══════════════════════════════════════════════════════════════════════════

generate_session_01() {
  local out="$PROMPT_GEN_DIR/session_01_prompt.txt"
  cat > "$out" << 'PROMPT'
# Agent C — Executor Session 01: Critical Fixes

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.
Previous session: First session — no passover.

Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-004 | CRITICAL | Telegram Bot Table Names
**File:** captain-command/captain_command/telegram_bot.py
**Lines:** 102, 112, 160
**Fix:** Replace `p3_d00_asset_registry` → `p3_d00_asset_universe` and `p3_d03_trade_outcomes` → `p3_d03_trade_outcome_log`
**Spec:** §9 D00, D03 table names

### 2. G-005 | CRITICAL | Replay Engine CB Table Name
**File:** shared/replay_engine.py
**Line:** 289
**Fix:** Replace `p3_d25_circuit_breaker` → `p3_d25_circuit_breaker_params`
**Spec:** §9 D25 table name

### 3. G-017 | HIGH | Session Name Mismatch
**Files:** shared/constants.py, config/session_registry.json
**Fix:** Reconcile `LON` vs `LONDON` naming. Use `LON` per spec §1. Add `NY_PRE` to SESSION_IDS if needed.
**Spec:** §1 Session Definitions
**Note:** Blocked by DEC-07 (ZN/ZB mapping) — if DEC-07 is UNRESOLVED, fix LON→LON naming only and flag ZN/ZB for later.

### 4. G-001 | CRITICAL | CB Layer 4 Correlation Broken
**File:** captain-offline/captain_offline/blocks/b8_cb_params.py
**Lines:** 119-120
**Fix:** Replace `np.corrcoef` on 2-element array with proper OLS sliding window per spec §6 CB Layer 4: `beta_b = OLS(loss_sequence)` with minimum window size.
**Spec:** §6 CB Layer 4

### 5. G-013 | HIGH | CB Per-Model Filtering Missing
**File:** captain-offline/captain_offline/blocks/b8_cb_params.py
**Lines:** 40-54
**Fix:** Add `model_m` filter to SQL query so CB params are estimated per-model, not globally.
**Spec:** §6 CB per-model parameter estimation
**Deps:** G-001 (fix first)

### 6. G-027 | HIGH | Data Moderator Disabled
**File:** captain-online/captain_online/blocks/b1_data_ingestion.py
**Lines:** 574, 578
**Fix:** Implement actual data quality checks (stale data, bad timestamps) instead of unconditional `return True`. Set DATA_HOLD flag when checks fail.
**Spec:** §2 B1 REQ-3

## Post-Fix

After ALL items:
1. Run `/ln-614-docs-fact-checker` targeting table name changes
2. Run `/ln-624-code-quality-auditor` targeting b8_cb_params.py

## Rules

1. **ONE ITEM AT A TIME.** After each: show the diff, run `python3 -B -m pytest tests/ --ignore=tests/test_integration_e2e.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py --ignore=tests/test_account_lifecycle.py -v --tb=short 2>&1 | head -80` to check for breakage.
2. After each item: update the matrix row status from UNRESOLVED → FIXED.
3. New issues discovered → add as G-NEW-XXX, flag, do NOT fix without approval.
4. After all items: update §6 Dashboard counts.
5. Git commit after completing all items in this session.

## Passover

When session is complete, write to `plans/prompts/.passovers/session_01.txt`:
```
Session 01 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_02() {
  local out="$PROMPT_GEN_DIR/session_02_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_01.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 02: Learning Loops (A)

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-009 | HIGH | AIM Lifecycle Stale Query
**File:** captain-offline/captain_offline/blocks/b1_aim_lifecycle.py
**Line:** 55
**Fix:** Replace `ORDER BY timestamp DESC LIMIT 1` with QuestDB `LATEST ON timestamp PARTITION BY aim_id` for correct latest-state retrieval.
**Spec:** §3 AIM Lifecycle, §9 QuestDB append-only semantics

### 2. G-010 | HIGH | DMA Update Stale Query
**File:** captain-offline/captain_offline/blocks/b1_dma_update.py
**Lines:** 43-56
**Fix:** Replace `ORDER BY` pattern with `LATEST ON timestamp PARTITION BY` for D02 meta-weight reads.
**Spec:** §4 Offline B1, §9 QuestDB semantics
**Deps:** G-009 pattern established first

### 3. G-070 | MEDIUM | Systematic LATEST ON Migration
**Files:** ~10 blocks across all processes
**Fix:** Grep for `ORDER BY.*DESC LIMIT 1` and convert to `LATEST ON` where the intent is "most recent row per partition". Use `grep -rn "ORDER BY.*DESC LIMIT 1" captain-*/` to find all sites.
**Spec:** §9 QuestDB append-only; LATEST ON for dedup
**Deps:** G-009, G-010 patterns established

### 4. G-008 | HIGH | Drift Detection Empty Dict
**File:** captain-offline/captain_offline/orchestrator.py
**Line:** 572
**Fix:** Pass actual AIM feature dict (from D01 latest state) instead of `{}` to `run_drift_detection()`.
**Spec:** §4 Offline B9 — ADWIN on AIM features

### 5. G-047 | MEDIUM | river Library Missing
**File:** captain-offline/requirements.txt
**Fix:** Add `river` to requirements.txt for ADWIN drift detection.
**Spec:** §4 Offline B9 — uses `river` library
**Deps:** G-008

### 6. G-048 | MEDIUM | ADWIN State Persistence
**File:** captain-offline/captain_offline/blocks/b1_drift_detection.py (or wherever drift detection lives)
**Lines:** 115-116
**Fix:** Persist ADWIN/autoencoder state to SQLite journal or QuestDB instead of module-level dicts. State must survive container restarts.
**Spec:** §4 Offline B9 — persistent ADWIN state
**Deps:** G-047

## Post-Fix
1. Run `/ln-624-code-quality-auditor` targeting changed files
2. Run `/ln-625-dependencies-auditor` to verify river is properly declared

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. New issues → G-NEW-XXX, flag, do NOT fix.
3. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_02.txt`:
```
Session 02 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_03() {
  local out="$PROMPT_GEN_DIR/session_03_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_02.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 03: Learning Loops (B)

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-011 | HIGH | CB Level 2 No Cooldown
**File:** captain-offline/captain_offline/blocks/b2_level_escalation.py
**Line:** 186
**Fix:** Add cooldown/debounce: Level 2 fires ONCE per changepoint event, not every trade while cp_prob > 0.8. Track last_cp_event timestamp.
**Spec:** §6 CB Level 2 — once per changepoint event; debounced

### 2. G-012 | HIGH | Level 2/3 Mutual Exclusivity
**File:** captain-offline/captain_offline/blocks/b2_level_escalation.py
**Lines:** 186-197
**Fix:** Add `elif` or early `return` between Level 2 and Level 3 checks so they are mutually exclusive escalation tiers.
**Spec:** §6 CB — Level 2 and Level 3 are mutually exclusive
**Deps:** G-011

### 3. G-028 | HIGH | Redis Publish No Retry
**File:** captain-online/captain_online/blocks/b7_position_monitor.py
**Lines:** 336-360
**Fix:** Add retry logic (3 attempts, exponential backoff) for Redis publish of trade outcomes. Log on final failure.
**Spec:** §11 Feedback Loop 1 — trade outcome must reliably reach Offline via Redis

### 4. G-006 | HIGH | Position List Race Condition
**File:** captain-online/captain_online/orchestrator.py
**Lines:** 61-62, 762, 769
**Fix:** Add threading.Lock for position list mutations. Both the main thread and WebSocket callback must acquire lock before read/write.
**Spec:** §2 B7, §11 Loop 1 — correct trade outcome delivery

### 5. G-044 | MEDIUM | Offline Shutdown Thread Join
**File:** captain-offline/captain_offline/orchestrator.py
**Line:** 69
**Fix:** In `stop()`, join the Redis listener thread with timeout before exiting. Ensures in-flight outcomes are flushed.
**Spec:** §12 Lifecycle — graceful shutdown joins all threads

### 6. G-014 | HIGH | MC/GA Deterministic Seeds
**Files:** captain-offline/captain_offline/blocks/b7_tsm_simulation.py:118, b6_auto_expansion.py:230
**Fix:** Replace `SEED=42` with `np.random.default_rng()` (no fixed seed) or seed from current timestamp. MC and GA must produce different outputs each run.
**Spec:** §4 B6 — stochastic GA exploration

## Post-Fix
1. Run `/ln-628-concurrency-auditor` targeting orchestrator.py and b7_position_monitor.py
2. Run `/ln-629-lifecycle-auditor` targeting offline orchestrator shutdown

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. New issues → G-NEW-XXX, flag, do NOT fix.
3. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_03.txt`:
```
Session 03 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_04() {
  local out="$PROMPT_GEN_DIR/session_04_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_03.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 04: Security Hardening

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

## Resolved Decisions
Check matrix for DEC-01 and DEC-02 resolutions before starting.

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-002 | CRITICAL | No API Authentication
**File:** captain-command/captain_command/api.py
**Fix:** Implement authentication middleware per DEC-01 resolution. If DEC-01 = "API key from .env": add middleware that checks `X-API-Key` header against `API_SECRET_KEY` env var. Exempt health/status endpoints.
**Spec:** §10 — authenticated REST and WebSocket endpoints
**Deps:** DEC-01 must be RESOLVED

### 2. G-003 | CRITICAL | RCE via git-pull Endpoint
**File:** captain-command/captain_command/api.py
**Fix:** Per DEC-02 resolution. If DEC-02 = "Remove endpoint": delete the `/system/git-pull` route entirely.
**Spec:** §10 — secure remote update mechanism
**Deps:** G-002, DEC-02 must be RESOLVED

### 3. G-021 | HIGH | SQL Injection in Notifications
**File:** captain-command/captain_command/blocks/b7_notifications.py
**Lines:** 433-436
**Fix:** Replace f-string SQL interpolation in `_get_users_by_roles()` with parameterized query. Use `$1, $2, ...` placeholders.
**Spec:** §10 — parameterized SQL queries

### 4. G-055 | MEDIUM | WebSocket User Impersonation
**File:** captain-command/captain_command/api.py (WebSocket endpoint)
**Fix:** Verify `user_id` from WebSocket query param against the authenticated session token (from G-002 auth). Reject mismatches.
**Spec:** §8 — user_id verified against session token
**Deps:** G-002

### 5. G-020 | HIGH | Docker Socket Access
**File:** captain-command/Dockerfile
**Lines:** 9-14
**Fix:** Remove Docker CLI installation. Remove Docker socket mount from docker-compose.yml if present.
**Spec:** §10 — minimal container attack surface
**Deps:** G-003 (git-pull removed, so Docker CLI no longer needed)

### 6. G-089 | MEDIUM | Containers Run as Root
**Files:** captain-command/Dockerfile, captain-online/Dockerfile, captain-offline/Dockerfile, captain-gui/Dockerfile
**Fix:** Add `USER appuser` directive after installing dependencies. Create non-root user in each Dockerfile.
**Spec:** §10 — containers run as non-root

### 7. G-056 | MEDIUM | Stack Traces in API Responses
**Files:** captain-command/captain_command/api.py, captain-command/captain_command/blocks/b6_reports.py:137,396
**Fix:** Replace `str(exc)` in HTTP responses with generic error messages. Log the full exception server-side.
**Spec:** §10 — generic error responses

## Post-Fix
1. Run `/ln-621-security-auditor` — full security assessment post-hardening
2. Run `/ln-643-api-contract-auditor` — verify API contracts

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. If DEC-01 or DEC-02 are still UNRESOLVED, skip dependent items and flag in passover.
3. New issues → G-NEW-XXX, flag, do NOT fix.
4. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_04.txt`:
```
Session 04 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Decisions still needed: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_05() {
  local out="$PROMPT_GEN_DIR/session_05_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_04.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 05: Timezone + Session Infrastructure

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

## Resolved Decisions
Check matrix for DEC-07 (ZN/ZB session mapping) resolution.

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-024 | HIGH | Offline Scheduler Wrong Timezone
**File:** captain-offline/captain_offline/orchestrator.py
**Line:** 529
**Fix:** Replace `datetime.now()` with `datetime.now(ZoneInfo("America/New_York"))`. Import ZoneInfo from zoneinfo stdlib.
**Spec:** §1 REQ-4 — timezone is always America/New_York

### 2. G-029 | MEDIUM | Online datetime.now() Without ET
**Files:** captain-online/captain_online/blocks/b1_data_ingestion.py:436,642; b1_features.py:546
**Fix:** Replace all `datetime.now()` with ET-aware version in these 3 locations.
**Spec:** §1 REQ-4

### 3. G-051 | MEDIUM | Offline datetime.now() Throughout
**Files:** ~20 sites across captain-offline orchestrator + B3-B9
**Fix:** Grep for `datetime.now()` in captain-offline/ and replace with ET-aware version. Consider creating a helper `now_et()` in shared/constants.py if not already present.
**Spec:** §1 REQ-4
**Deps:** G-024

### 4. G-036 | MEDIUM | Session Open Time Always 9:30
**File:** captain-online/captain_online/blocks/b1_features.py
**Lines:** 1073-1082
**Fix:** `_get_session_open_time()` must return per-session open times: NY=09:30, LON=03:00, APAC=18:00 ET. Read from session_registry.json or constants.
**Spec:** §1 per-session open times
**Deps:** G-017 (session names fixed)

### 5. G-065 | MEDIUM | ZN/ZB Session Mapping Conflict
**File:** config/session_registry.json
**Fix:** Per DEC-07 resolution. If UNRESOLVED, flag and skip.
**Spec:** §1 session mapping
**Deps:** DEC-07

### 6. G-007 | HIGH | AIM-03 GEX Hardcoded Multiplier
**File:** captain-online/captain_online/blocks/b1_features.py
**Lines:** 955-956
**Fix:** Replace hardcoded `50.0` (ES multiplier) with per-asset contract multiplier from D00 (`p3_d00_asset_universe`). Query the `contract_multiplier` column.
**Spec:** §3 AIM-03 — per-asset contract multiplier from D00

## Post-Fix
1. Run `/ln-647-env-config-auditor` — timezone and config alignment
2. Run `/ln-641-pattern-analyzer` — session_match compliance

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. If DEC-07 is UNRESOLVED, skip G-065 and flag.
3. New issues → G-NEW-XXX, flag, do NOT fix.
4. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_05.txt`:
```
Session 05 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_06() {
  local out="$PROMPT_GEN_DIR/session_06_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_05.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 06: Online Reliability

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-023 | HIGH | Data Ingestion Sequential REST
**File:** captain-online/captain_online/blocks/b1_data_ingestion.py
**Lines:** 497-558
**Fix:** Convert sequential REST calls to concurrent using `asyncio.gather()` or `concurrent.futures.ThreadPoolExecutor`. Target: <9s latency for 10 assets.
**Spec:** §1 — B1 latency budget <9s; parallel asset data fetch

### 2. G-018 | HIGH | TopstepX Client No Timeout/Rate Limit
**File:** shared/topstep_client.py
**Fix:** Add `timeout=10` to all `requests.post()` calls. Add 429 rate-limit handling with exponential backoff.
**Spec:** §10 — graceful rate limiting and timeout

### 3. G-030 | MEDIUM | Position Monitor Stub Checks
**File:** captain-online/captain_online/blocks/b7_position_monitor.py
**Lines:** 419-427
**Fix:** Implement VIX spike check (from vix_provider), regime shift check (from latest regime state), and API commission check (from D17 params) instead of stubs returning True/None.
**Spec:** §2 B7 monitoring checks

### 4. G-031 | MEDIUM | Shadow Monitor Hardcoded Point Values
**File:** captain-online/captain_online/blocks/b7_shadow_monitor.py
**Lines:** 217-221
**Fix:** Replace hardcoded POINT_VALUES dict with D00 lookup (`contract_multiplier` or `point_value` column).
**Spec:** §2 B7 — per-asset point values from D00

### 5. G-032 | MEDIUM | Shadow Monitor No TIMEOUT Outcome
**File:** captain-online/captain_online/blocks/b7_shadow_monitor.py
**Lines:** 87-93
**Fix:** When expired shadow positions are found, publish TIMEOUT outcome to Redis `captain:trade_outcomes` instead of silently dropping.
**Spec:** §2 B7 — expired shadows publish TIMEOUT outcome

### 6. G-033 | MEDIUM | Non-Atomic Capital/CB Updates
**File:** captain-online/captain_online/blocks/b7_position_monitor.py
**Lines:** 279-296
**Fix:** Wrap D16 (capital silo) and D23 updates in a single transaction or use optimistic locking to prevent concurrent close races.
**Spec:** §11 Loop 5 — atomic capital/CB state updates

## Post-Fix
1. Run `/ln-653-runtime-performance-auditor` if available, else `/ln-629-lifecycle-auditor`
2. Run `/ln-629-lifecycle-auditor` targeting b7 monitor lifecycle

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. New issues → G-NEW-XXX, flag, do NOT fix.
3. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_06.txt`:
```
Session 06 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_07() {
  local out="$PROMPT_GEN_DIR/session_07_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_06.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 07: AIM Implementation

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

## Resolved Decisions
Check matrix for DEC-08 (COT Data Feed for AIM-07) resolution.

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-075 | MEDIUM | AIM-12 Missing spread_history Table
**File:** scripts/init_questdb.py
**Fix:** Add `CREATE TABLE IF NOT EXISTS p3_spread_history (...)` with columns matching what b1_features.py:700-706 writes. Also verify b1_features.py reads/writes correctly.
**Spec:** §3 AIM-12, §9 dataset schemas

### 2. G-069 | MEDIUM | Undocumented p3_spread_history Table
**File:** scripts/init_questdb.py
**Fix:** Same table as G-075. Ensure it's documented in init script comments.
**Spec:** §9 — all tables created by init scripts

### 3. G-073 | MEDIUM | AIM-07 COT Data Unavailable
**File:** captain-online/captain_online/blocks/b1_features.py (COT section)
**Fix:** Per DEC-08 resolution. If DEC-08 = "Disable AIM-07": add `is_active: false` guard in AIM-07 dispatch. If "Stub": add documented placeholder. If UNRESOLVED: skip.
**Spec:** §3 AIM-07 — COT Sentiment
**Deps:** DEC-08

### 4. G-074 | MEDIUM | AIM-01/02 ES-Only Features
**Files:** shared/aim_compute.py, captain-online/captain_online/blocks/b1_features.py
**Fix:** Generalize AIM-01/02 feature computation to work with all 10 assets, not just ES. Use per-asset parameters from D00.
**Spec:** §3 AIM-01/02 — applicable to multiple assets

### 5. G-076 | MEDIUM | AIM-13 Modifier Type Wrong
**File:** captain-offline/captain_offline/blocks/b5_sensitivity.py
**Lines:** 232-238
**Fix:** Write modifier as plain float to D01, not JSON dict `{"asset_id": val}`.
**Spec:** §3 AIM-13 — modifier is a float written to D01

### 6. G-077 | MEDIUM | AIM-08 CORR_STRESS Math Wrong
**File:** shared/aim_feature_loader.py
**Line:** 193
**Fix:** Compute actual z-score of rolling correlation (subtract mean, divide by std) instead of using raw Pearson r as proxy.
**Spec:** §3 AIM-08 — CORR_STRESS = z-score of rolling correlation

## Post-Fix
1. Run `/ln-614-docs-fact-checker` targeting init_questdb.py table names
2. Run `/ln-641-pattern-analyzer` targeting AIM feature computation

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. If DEC-08 is UNRESOLVED, skip G-073 and flag.
3. New issues → G-NEW-XXX, flag, do NOT fix.
4. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_07.txt`:
```
Session 07 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_08() {
  local out="$PROMPT_GEN_DIR/session_08_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_07.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 08: Offline Pipeline Alignment

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

## Resolved Decisions
Check matrix for DEC-05 (hmmlearn vs hand-rolled Baum-Welch) resolution.

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-045 | MEDIUM | Bootstrap Single-Session Filtering
**File:** captain-offline/captain_offline/bootstrap.py
**Line:** 122
**Fix:** Apply regime filtering to ALL sessions in multi-session bootstrap, not just `default_session`.
**Spec:** §4 Offline Orch — multi-session bootstrap

### 2. G-046 | MEDIUM | AIM-16 HMM Implementation Choice
**File:** captain-offline/captain_offline/blocks/b1_aim16_hmm.py
**Fix:** Per DEC-05 resolution. If DEC-05 = "Switch to hmmlearn": refactor to use `hmmlearn.hmm.GaussianHMM`. If "Keep hand-rolled": remove hmmlearn from requirements.txt. If UNRESOLVED: skip.
**Spec:** §3 AIM-16
**Deps:** DEC-05

### 3. G-049 | MEDIUM | Sensitivity Modifier Type (Offline Side)
**File:** captain-offline/captain_offline/blocks/b5_sensitivity.py
**Lines:** 232-238
**Fix:** Same as G-076 (session 07). Verify the fix from session 07 covers this; if not, apply here.
**Spec:** §3 AIM-13
**Deps:** G-076

### 4. G-050 | MEDIUM | Unbounded Action Queue
**File:** captain-offline/captain_offline/blocks/b9_diagnostic.py
**Lines:** 833-882
**Fix:** Add max size cap to the action queue (e.g., 1000 entries). When queue exceeds cap, drop oldest entries.
**Spec:** §4 B9 — bounded action queue

### 5. G-052 | MEDIUM | Kelly Shrinkage Join Undocumented
**File:** captain-offline/captain_offline/blocks/b8_kelly_update.py
**Lines:** 179-205
**Fix:** Add clear docstring documenting the join strategy between D12 kelly_params and the online consumer. Include the key fields used for matching.
**Spec:** §5 Kelly — shrinkage row linkage

### 6. G-034 | MEDIUM | AIM Aggregation Dead Shim
**File:** captain-online/captain_online/blocks/b3_aim_aggregation.py
**Fix:** If this is truly a pass-through shim to aim_compute with no added logic: either inline the call at the call site and remove the file, OR add the aggregation logic the spec requires (§2 B3).
**Spec:** §2 B3 — AIM aggregation block

## Post-Fix
1. Run `/ln-625-dependencies-auditor` to verify hmmlearn status
2. Run `/ln-626-dead-code-auditor` to check for remaining dead code

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. If DEC-05 is UNRESOLVED, skip G-046 and flag.
3. New issues → G-NEW-XXX, flag, do NOT fix.
4. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_08.txt`:
```
Session 08 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_09() {
  local out="$PROMPT_GEN_DIR/session_09_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_08.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 09: Command Pipeline + QuestDB

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-022 | HIGH | Reconciliation Never Writes D08 Correction
**File:** captain-command/captain_command/blocks/b8_reconciliation.py
**Lines:** 483-515
**Fix:** When broker balance diverges from D08, actually write the corrected balance to D08 (QuestDB append). Currently only logs.
**Spec:** §7 Command B8 — reconciliation corrects D08

### 2. G-019 | HIGH | Hardcoded f_target_max
**File:** captain-command/captain_command/blocks/b8_reconciliation.py
**Line:** 336
**Fix:** Read `f_target_max` from D17 `p3_d17_system_params` instead of hardcoded `0.03`.
**Spec:** §7 B8 — payout MDD threshold from D17

### 3. G-054 | MEDIUM | Replay Session Memory Leak
**File:** captain-command/captain_command/blocks/b11_replay_runner.py
**Lines:** 206-218
**Fix:** Remove completed sessions from `_active_sessions` dict on completion.
**Spec:** §7 B11 — replay sessions cleaned up

### 4. G-057 | MEDIUM | Notifications Not on Redis Alerts
**File:** captain-command/captain_command/blocks/b7_notifications.py
**Line:** 7 (CH_ALERTS imported but unused)
**Fix:** Publish notifications to `captain:alerts` Redis channel in addition to (or instead of) current delivery method.
**Spec:** §7 B7 — publishes to `captain:alerts`

### 5. G-058 | MEDIUM | Incident Response NameError
**File:** captain-command/captain_command/blocks/b9_incident_response.py
**Line:** 257
**Fix:** Fix `exc` NameError — either move the reference inside the try/except block or remove the dead code path.
**Spec:** §7 B9 — incident response handler must not crash

### 6. G-059 | MEDIUM | Telegram Token in Logs
**File:** captain-command/captain_command/telegram_bot.py
**Line:** 600
**Fix:** Replace bot token in URL strings with masked version for logging. Use `TELEGRAM_BOT_TOKEN` env var reference, not literal token value in constructed URLs.
**Spec:** §10 — secrets not in logs

## Post-Fix
1. Run `/ln-643-api-contract-auditor` targeting command pipeline contracts
2. Run `/ln-654-resource-lifecycle-auditor` if available, else `/ln-629-lifecycle-auditor`

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. New issues → G-NEW-XXX, flag, do NOT fix.
3. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_09.txt`:
```
Session 09 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_10() {
  local out="$PROMPT_GEN_DIR/session_10_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_09.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 10: Concurrency + CB + Feedback

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

## Resolved Decisions
Check matrix for DEC-03 (CB layer count) and DEC-06 (AIM-16 dispatch) resolutions.

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-015 | HIGH | GUI Data Server No Locks
**File:** captain-command/captain_command/blocks/b2_gui_data_server.py
**Fix:** Add threading.Lock around all global state mutations. Ensure financial snapshots are atomically updated for concurrent GUI clients.
**Spec:** §7 B2 — real-time GUI data to multiple concurrent clients

### 2. G-016 | HIGH | WebSocket Connections Dict Race
**File:** captain-command/captain_command/api.py (`_active_connections`)
**Fix:** Use `threading.Lock` or switch to `asyncio`-safe structure. Don't mutate dict during iteration on trade notification path.
**Spec:** §7 B2 — broadcast trade notifications
**Deps:** G-015

### 3. G-078 | MEDIUM | AIM-16 Dead Dispatch Function
**File:** shared/aim_compute.py
**Lines:** 637-649
**Fix:** Per DEC-06 resolution. If "Re-add to dispatch": wire `_aim16_hmm()` into the dispatch table. If "Remove": delete dead function. If UNRESOLVED: skip.
**Spec:** §3 AIM-16
**Deps:** DEC-06

### 4. G-079 | MEDIUM | 7 AIM Features Missing in Replay
**File:** shared/aim_feature_loader.py
**Fix:** Add fallback/stub values for replay mode for: pcr_z, gex, cot_smi, cot_speculator_z, event_proximity, events_today, cl_basis. Document which are stubs.
**Spec:** §3 — all 16 AIMs functional in replay
**Deps:** G-073, G-074

### 5. G-080 | MEDIUM | CB Layer Count Mismatch
**File:** captain-online/captain_online/blocks/b5c_circuit_breaker.py
**Line:** 11
**Fix:** Per DEC-03 resolution. If "Keep 7, document": add V3 amendment comment. If "Remove L5/L6": strip safety layers. If UNRESOLVED: skip.
**Spec:** §6 CB layers
**Deps:** DEC-03

### 6. G-081 | MEDIUM | Kelly Helper Duplicated 3x
**Files:** captain-online/captain_online/blocks/b4_kelly_sizing.py:292, b5_trade_selection.py:192, b6_signal_output.py:310
**Fix:** Extract `_get_ewma_for_regime()` to shared/statistics.py (or similar). Import from single source in all 3 files.
**Spec:** DRY principle

## Post-Fix
1. Run `/ln-628-concurrency-auditor` targeting b2_gui_data_server.py and api.py
2. Run `/ln-641-pattern-analyzer` targeting AIM dispatch and CB layers

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. If DEC-03, DEC-06 are UNRESOLVED, skip dependent items and flag.
3. New issues → G-NEW-XXX, flag, do NOT fix.
4. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_10.txt`:
```
Session 10 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_11() {
  local out="$PROMPT_GEN_DIR/session_11_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_10.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 11: Code Quality + Remaining

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

## Resolved Decisions
Check matrix for DEC-04 (Pseudotrader refactor scope) resolution.

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-025 | HIGH | Pseudotrader God Module
**File:** captain-offline/captain_offline/blocks/b3_pseudotrader.py (1,432 lines)
**Fix:** Per DEC-04 resolution. If "Defer": mark DEFERRED in matrix, skip. If "Extract 3": split out the 3 biggest concerns into separate modules. If UNRESOLVED: skip.
**Spec:** §4 B3 — single-responsibility
**Deps:** DEC-04

### 2. G-026 | HIGH | Multi-User Hardcoded primary_user
**File:** captain-command/captain_command/main.py
**Line:** 131
**Fix:** Replace hardcoded `primary_user` with dynamic user resolution from the request context or env var. TSM linking must work for any user_id.
**Spec:** §1 REQ-6 — multi-user from day one

### 3. G-035 | MEDIUM | _parse_json Duplicated 6x
**Files:** b4_kelly_sizing.py:461 + 5 others
**Fix:** Extract `_parse_json()` to shared utility (e.g., shared/utils.py or shared/json_helpers.py). Import in all 6 blocks.
**Spec:** DRY principle

### 4. G-037 | MEDIUM | Regime Classifier 50/50 for C1-C3
**File:** captain-online/captain_online/blocks/b2_regime_probability.py
**Lines:** 150-154
**Fix:** Implement actual regime probability computation for classifier tiers C1, C2, C3 instead of returning [0.5, 0.5].
**Spec:** §2 B2 — regime probabilities per asset

### 5. G-038 | MEDIUM | Capacity Evaluator N+1 Query
**File:** captain-online/captain_online/blocks/b9_capacity_evaluation.py
**Lines:** 108-117
**Fix:** Batch D00 query to fetch all assets at once instead of per-asset in loop.
**Spec:** §2 B9 — efficient data access

### 6. G-039 | MEDIUM | Capacity Evaluator Full Table Load
**File:** captain-online/captain_online/blocks/b9_capacity_evaluation.py
**Lines:** 160-177
**Fix:** Add WHERE clause to D17 session_log query to fetch only current session, not entire table.
**Spec:** §2 B9 — efficient data access

### 7. G-040 | MEDIUM | Capacity Evaluator Inconsistent API
**File:** captain-online/captain_online/blocks/b9_capacity_evaluation.py
**Line:** 124
**Fix:** Change `"detail"` key to `"message"` to match the pattern used by other constraint responses.
**Spec:** Consistent constraint API

## Post-Fix
1. Run `/ln-623-code-quality-auditor` if available, else `/ln-624-code-quality-auditor`
2. Run `/ln-651-runtime-performance-auditor` if available

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. If DEC-04 is UNRESOLVED, skip G-025 and flag.
3. New issues → G-NEW-XXX, flag, do NOT fix.
4. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_11.txt`:
```
Session 11 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

generate_session_12() {
  local out="$PROMPT_GEN_DIR/session_12_prompt.txt"
  local prev_passover
  prev_passover=$(get_passover "$PASS_DIR/session_11.txt")

  cat > "$out" <<PASSOVER_BLOCK
# Agent C — Executor Session 12: Session Infrastructure + Naming

You are AGENT C (Executor). You implement code changes.
You do NOT plan future sessions or make architectural decisions.

## Previous Session Passover
${prev_passover}

## Resolved Decisions
Check matrix for DEC-09 (Session Controller) and DEC-10 (Compliance Gate) resolutions.

PASSOVER_BLOCK

  cat >> "$out" << 'PROMPT'
Read `plans/CAPTAIN_RECONCILIATION_MATRIX.md` in full before starting.

## Assignment (in order)

### 1. G-066 | MEDIUM | Session Controller Block Missing
**Fix:** Per DEC-09 resolution. If "Document that orchestrator handles this": add comment in orchestrator documenting session trigger logic and rename gap to "naming only" in matrix. If "Create block": create b9_session_controller.py. If UNRESOLVED: skip.
**Spec:** §2 — B9 session controller
**Deps:** DEC-09

### 2. G-067 | MEDIUM | OR Tracker Naming
**File:** captain-online/captain_online/blocks/or_tracker.py (no block prefix)
**Fix:** Rename to `b8_or_tracker.py` per spec naming convention. Update all imports.
**Spec:** §2 — B8 OR tracker naming

### 3. G-068 | MEDIUM | Compliance Gate No Runtime Enforcement
**Fix:** Per DEC-10 resolution. If "Document that compliance checks exist in other blocks": verify and document where compliance_gate.json is enforced. If "Create block": create compliance gate enforcement. If UNRESOLVED: skip.
**Spec:** §2 — compliance gate block
**Deps:** DEC-10

## Post-Fix
1. Run `/ln-629-lifecycle-auditor` targeting session and block naming
2. Run `/ln-641-pattern-analyzer` to verify naming conventions

## Rules
1. ONE ITEM AT A TIME. After each: show diff, run pytest, update matrix.
2. If DEC-09/DEC-10 are UNRESOLVED, skip dependent items and flag.
3. New issues → G-NEW-XXX, flag, do NOT fix.
4. After all items: update §6 Dashboard, git commit.

## Passover
Write to `plans/prompts/.passovers/session_12.txt`:
```
Session 12 Passover
Items completed: [list]
Items remaining: [list or "none"]
New findings: [list or "none"]
Test status: [pass/fail count]
Audit skill results: [summary]
Notes: [anything for next session]
```
PROMPT
}

# ═══════════════════════════════════════════════════════════════════════════
# PHASE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

phase1() { run_phase "1: Critical Fixes" 1 -- ln-614-docs-fact-checker ln-624-code-quality-auditor; }
phase2() { run_phase "2: Learning Loops" 2 3 -- ln-624-code-quality-auditor ln-628-concurrency-auditor ln-629-lifecycle-auditor; }
phase3() { run_phase "3: Security Hardening" 4 -- ln-621-security-auditor ln-643-api-contract-auditor; }
phase4() { run_phase "4: Timezone + Online" 5 6 -- ln-647-env-config-auditor ln-641-pattern-analyzer ln-629-lifecycle-auditor; }
phase5() { run_phase "5: AIM + Offline" 7 8 -- ln-614-docs-fact-checker ln-641-pattern-analyzer ln-625-dependencies-auditor; }
phase6() { run_phase "6: Command + CB" 9 10 -- ln-643-api-contract-auditor ln-628-concurrency-auditor ln-641-pattern-analyzer; }
phase7() { run_phase "7: Quality + Verify" 11 12 -- ln-624-code-quality-auditor ln-629-lifecycle-auditor ln-641-pattern-analyzer; }

final_validation() {
  banner "FINAL VALIDATION SWEEP (Session 13)"
  local prompt="$PROMPTS_DIR/final_validation.md"
  local log_file="$LOGS_DIR/final_validation.log"

  log "Running final validation sweep..."

  claude -p "$(cat "$prompt")" \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --allowedTools "$VALIDATOR_TOOLS,Skill" \
    --output-format text \
    2>&1 | tee -a "$log_file"

  log "Final validation complete. Report: docs/audit/FINAL_VALIDATION_REPORT.md"
  dashboard
}

# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

run_all() {
  local total_start
  total_start=$(date +%s)

  banner "ABC IMPLEMENTATION — FULL RUN"
  log "Starting full implementation run at $(date -Iseconds)"
  log "Matrix: $MATRIX"
  log "Logs: $LOGS_DIR"
  dashboard

  human_gate "Review dashboard above. ENTER to begin Phase 1."

  phase1
  phase2
  phase3
  phase4
  phase5
  phase6
  phase7

  banner "ALL IMPLEMENTATION PHASES COMPLETE"
  human_gate "ENTER to run final validation sweep."

  final_validation

  local total_elapsed=$(( $(date +%s) - total_start ))
  local total_mins=$(( total_elapsed / 60 ))
  local total_secs=$(( total_elapsed % 60 ))

  banner "ABC IMPLEMENTATION COMPLETE"
  log "Total time: ${total_mins}m${total_secs}s"
  log "Final report: docs/audit/FINAL_VALIDATION_REPORT.md"
  log "Validation log: $VAL_LOG"
  log "Full run log: $LOGS_DIR/run.log"
  dashboard
}

# ─── CLI Dispatch ───────────────────────────────────────────────────────────

case "${1:---all}" in
  --phase1)     phase1 ;;
  --phase2)     phase2 ;;
  --phase3)     phase3 ;;
  --phase4)     phase4 ;;
  --phase5)     phase5 ;;
  --phase6)     phase6 ;;
  --phase7)     phase7 ;;
  --session)
    [[ -z "${2:-}" ]] && { echo "Usage: $0 --session NN"; exit 1; }
    padded=$(printf "%02d" "$2")
    if ! declare -f "generate_session_${padded}" >/dev/null 2>&1; then
      echo "Error: No generate function for session $padded (valid: 01-12)"
      exit 1
    fi
    "generate_session_${padded}"
    run_executor "$2"
    run_pytest "$2"
    run_validator "$2"
    dashboard
    ;;
  --validate)
    [[ -z "${2:-}" ]] && { echo "Usage: $0 --validate NN"; exit 1; }
    run_validator "$2"
    dashboard
    ;;
  --dashboard)  dashboard ;;
  --final)      final_validation ;;
  --all)        run_all ;;
  *)
    echo "Usage: $0 [--all|--phase1..7|--session NN|--validate NN|--dashboard|--final]"
    exit 1
    ;;
esac
