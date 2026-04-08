#!/bin/bash
# run_spec_audit.sh — Phase 2: Spec Consolidation + Master Gap Analysis
#
# Automates 7 sequential Claude sessions that extract spec content from
# Obsidian vault + V3 repo docs into a consolidated spec_reference.md,
# then runs a master gap analysis comparing spec vs code.
#
# Usage:
#   cd ~/captain-system
#   bash docs/audit/run_spec_audit.sh                # Full run EXEC-01 → 07
#   bash docs/audit/run_spec_audit.sh spec_exec_01   # Single session
#   bash docs/audit/run_spec_audit.sh checkpoint      # Run checkpoint only
#
# Prerequisites:
#   - claude CLI installed and authenticated
#   - codebase-audit-suite plugin installed (for EXEC-07)
#   - Obsidian vault accessible at /mnt/c/Users/nomaa/Documents/Quant_Project/
#   - Working directory: ~/captain-system

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

# ─── Paths ──────────────────────────────────────────────────────────────────
AUDIT_DIR="docs/audit"
PASS_DIR="$AUDIT_DIR/.passovers"
PROMPT_DIR="$AUDIT_DIR/.prompts"
LOG_FILE="$AUDIT_DIR/spec_audit.log"
SPEC_REF="$AUDIT_DIR/spec_reference.md"
GAP_FILE="$AUDIT_DIR/master_gap_analysis.md"
VAULT="/mnt/c/Users/nomaa/Documents/Quant_Project"
VAULT_DI="$VAULT/Direct Information"
V3_DIR="docs/AIM-Specs/new-aim-specs"

# ─── Configuration ──────────────────────────────────────────────────────────
MODEL="claude-opus-4-6"
EFFORT="max"
ALLOWED_TOOLS="Read,Write,Edit,Glob,Grep,Bash,Skill"

mkdir -p "$PASS_DIR" "$PROMPT_DIR"

# ═══════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG_FILE"
}

banner() {
  log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  log "  $1"
  log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

show_progress() {
  if [[ -f "$SPEC_REF" ]]; then
    local lines
    lines=$(wc -l < "$SPEC_REF")
    local sections
    sections=$(grep -c "^## §" "$SPEC_REF" 2>/dev/null || echo 0)
    log "  spec_reference.md: ${lines} lines, ${sections}/13 sections"
  else
    log "  spec_reference.md: not yet created"
  fi
}

preflight() {
  log "Pre-flight checks..."
  local fail=0

  if ! command -v claude &>/dev/null; then
    log "  FAIL: claude CLI not found in PATH"
    fail=1
  else
    log "  OK: claude CLI found"
  fi

  if [[ ! -d "$VAULT_DI" ]]; then
    log "  FAIL: Obsidian vault not accessible at $VAULT_DI"
    log "        Ensure Windows filesystem is mounted in WSL2"
    fail=1
  else
    local vault_count
    vault_count=$(ls "$VAULT_DI"/*.md 2>/dev/null | wc -l)
    log "  OK: Obsidian vault ($vault_count .md files)"
  fi

  if [[ ! -d "$V3_DIR" ]]; then
    log "  FAIL: V3 specs not found at $V3_DIR"
    fail=1
  else
    local v3_count
    v3_count=$(ls "$V3_DIR"/*.md 2>/dev/null | wc -l)
    log "  OK: V3 repo specs ($v3_count .md files)"
  fi

  if [[ $fail -ne 0 ]]; then
    log "Pre-flight FAILED — fix the above and retry"
    exit 1
  fi
  log "Pre-flight passed."
}

# ═══════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════

run_exec() {
  local name="$1"
  local prompt_file="$2"
  local expected_output="$3"

  banner "$name START"
  local start_ts
  start_ts=$(date +%s)

  # Backup spec_reference.md before append sessions
  if [[ -f "$SPEC_REF" && "$name" != "SPEC-EXEC-01" ]]; then
    cp "$SPEC_REF" "${SPEC_REF}.bak"
    log "  Backed up spec_reference.md"
  fi

  claude -p "$(cat "$prompt_file")" \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --allowedTools "$ALLOWED_TOOLS" \
    --output-format text \
    2>&1 | tee -a "$LOG_FILE"

  local exit_code=${PIPESTATUS[0]}
  local elapsed=$(( $(date +%s) - start_ts ))
  local mins=$(( elapsed / 60 ))
  local secs=$(( elapsed % 60 ))

  if [[ $exit_code -ne 0 ]]; then
    log "$name FAILED (exit $exit_code, ${mins}m${secs}s)"
    return 1
  fi

  if [[ -f "$expected_output" ]] && [[ -s "$expected_output" ]]; then
    local lines
    lines=$(wc -l < "$expected_output")
    log "$name DONE (${lines} lines in output, ${mins}m${secs}s)"
  else
    log "$name WARNING — expected output not found (${mins}m${secs}s)"
  fi

  show_progress
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
# CHECKPOINT — Validate all 13 sections exist
# ═══════════════════════════════════════════════════════════════════════════

check_sections() {
  banner "CHECKPOINT — Validating spec_reference.md"

  if [[ ! -f "$SPEC_REF" ]]; then
    log "  FAIL: spec_reference.md does not exist"
    return 1
  fi

  local missing=0
  local present=0
  local total_lines
  total_lines=$(wc -l < "$SPEC_REF")

  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13; do
    if grep -q "§${i}[^0-9]" "$SPEC_REF" 2>/dev/null; then
      log "  OK: §$i found"
      ((present++)) || true
    else
      log "  MISSING: §$i"
      ((missing++)) || true
    fi
  done

  log ""
  log "  Sections: $present/13 present"
  log "  Total lines: $total_lines"
  log ""

  if [[ $missing -gt 0 ]]; then
    log "CHECKPOINT FAILED: $missing section(s) missing"
    log "Review $SPEC_REF, run patch sessions, then rerun:"
    log "  bash docs/audit/run_spec_audit.sh spec_exec_07"
    return 1
  fi

  log "CHECKPOINT PASSED: all 13 sections present"
  return 0
}

# ═══════════════════════════════════════════════════════════════════════════
# ARCHIVE — Back up previous Phase 2 outputs
# ═══════════════════════════════════════════════════════════════════════════

archive_old_files() {
  log "Archiving previous Phase 2 outputs..."
  local count=0
  for f in "$SPEC_REF" "$GAP_FILE"; do
    if [[ -f "$f" ]]; then
      local base="${f%.md}"
      mv "$f" "${base}_old.md"
      log "  Renamed $(basename "$f") -> $(basename "${base}_old.md")"
      ((count++)) || true
    fi
  done
  rm -f "$PASS_DIR"/spec_exec_*.txt
  rm -f "$PROMPT_DIR"/spec_exec_*.txt
  if [[ $count -eq 0 ]]; then
    log "  No previous output files to archive."
  else
    log "  Archived $count file(s)."
  fi
}

# ═══════════════════════════════════════════════════════════════════════════
# PROMPT GENERATORS
# ═══════════════════════════════════════════════════════════════════════════

generate_spec_exec_01() {
  cat > "$PROMPT_DIR/spec_exec_01.txt" << 'PROMPT'
You are extracting spec content for the Captain System consolidated spec reference. Session 1 of 7.

## Source Priority
V3 repo specs (docs/AIM-Specs/new-aim-specs/) SUPERSEDE Obsidian vault originals where content conflicts. Include Obsidian-only content absent from V3 and tag as [SOURCE: Obsidian doc NN].

## Documents to Read
PRIMARY (V3 — authoritative):
- docs/AIM-Specs/new-aim-specs/Program3_Online.md (~1756 lines)

SUPPLEMENTARY (Obsidian vault — original Isaac specs):
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/33_P3_Online_Full_Pseudocode.md (~475 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/30_P1_Consolidated_Config.md (~89 lines)

## What to Extract

### §1 — Session Definitions
Extract ALL of:
- Session type enum (NY, LON, APAC) with numeric IDs
- session_match() logic: how assets map to sessions
- Per-session open times (ET timezone) — exact times for NY open, LON open, APAC open
- Per-session asset mapping: which of the 10 active assets trade in which session(s)
- Opening Range (OR) parameters: duration, calculation method
- Session-related config constants or thresholds

### §2 — Online Blocks 1–9
For EACH block (B1 through B9), use this structure:

### Block N: [Name]
- **PG ID:** P3-ON-BN (or whatever the spec assigns)
- **Purpose:** (one line)
- **Trigger:** (what starts this block)
- **Inputs:** Datasets (QuestDB tables read with key fields) | Redis keys consumed | Upstream blocks
- **Outputs:** Datasets (QuestDB tables written with key fields) | Redis keys published | Downstream blocks
- **Key Logic:** (summarised — formulas, thresholds, decision points)
- **Shared vs Per-User:** (global or per-user?)
- **Error Handling:** (what happens on failure)

## Output
CREATE the file docs/audit/spec_reference.md with this structure:

# Captain System — Consolidated Spec Reference

Generated by Phase 2 Spec Extraction
Source priority: V3 repo specs supersede Obsidian originals.

---

## §1 — Session Definitions

[your content]

---

## §2 — Online Blocks 1–9

[your content]

Also write ONLY the passover summary to: docs/audit/.passovers/spec_exec_01.txt

## Passover Format (write at END of spec_reference.md AND to the passover file)
---
## Session 1 Summary
- **Docs read:** [list with source type]
- **Sections written:** §1, §2
- **Key spec requirements:** [3–5 most critical requirements found]
- **Items for next sessions:** [things referenced but not yet extracted]

## Rules
- Extract what the spec SAYS, not what code DOES — do NOT read any code files
- Include exact thresholds, formulas, enum values when the spec provides them
- Ambiguous points: tag as [SPEC AMBIGUOUS: ...]
- Obsidian-only content: tag as [SOURCE: Obsidian doc NN]
PROMPT
}

generate_spec_exec_02() {
  local passover
  passover=$(get_passover "$PASS_DIR/spec_exec_01.txt")

  cat > "$PROMPT_DIR/spec_exec_02.txt" << PASSOVER_BLOCK
## Previous Session Summary
$passover

PASSOVER_BLOCK

  cat >> "$PROMPT_DIR/spec_exec_02.txt" << 'PROMPT'
You are extracting spec content for the Captain System consolidated spec reference. Session 2 of 7.

## Source Priority
V3 repo specs SUPERSEDE Obsidian vault originals. The V3 AIM_Extractions.md is ~5x longer than the Obsidian equivalent — it is the authoritative source.

## Documents to Read
PRIMARY (V3 — authoritative):
- docs/AIM-Specs/new-aim-specs/AIM_Extractions.md (~3723 lines) — Detailed AIM paper extractions
- docs/AIM-Specs/new-aim-specs/HMM_Opportunity_Regime_Spec.md (~578 lines) — AIM-16 HMM

SUPPLEMENTARY (Obsidian vault):
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/31_AIM_Individual_Specifications.md (~767 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/22_HMM_Opportunity_Regime.md (~151 lines)

## What to Extract

### §3 — AIM System (AIMs 1–16)

First extract the AIM system overview:
- Total AIM count and tier structure (Tier 1, Tier 2, Tier 3)
- AIM aggregation method (DMA/MoE meta-learning)
- Lifecycle states (COLD, WARMING, WARM, ACTIVE, DECAYED, etc.)
- HDWM seed type taxonomy overview

Then for EACH AIM (AIM-1 through AIM-16):

### AIM-N: [Name]
- **Tier:** [1/2/3]
- **Paper/Source:** [academic source]
- **Data Sources:** [market data consumed]
- **Modifier Output:** [what the AIM produces — value range, interpretation]
- **Thresholds:** [key thresholds, cutoffs, decision boundaries]
- **Warm-Up Requirements:** [minimum data/time before active]
- **QuestDB Datasets:** [tables R/W, key fields]
- **Lifecycle States:** [transitions]
- **HDWM Seed Type:** [diversity category]
- **Key Formula:** [primary formula if spec provides it]

Special attention for AIM-16 (HMM):
- HMM state count and transition logic
- Budget allocation weights per regime state
- Cold-start blending formula
- Integration with session budgeting (Offline Block 5)

## Output
Read the existing docs/audit/spec_reference.md (has §1–2 from Session 1).
APPEND §3 to the end of the file. Do NOT delete existing content.
Also write ONLY the passover to: docs/audit/.passovers/spec_exec_02.txt

## Passover Format (append at end of spec_reference.md AND write to passover file)
---
## Session 2 Summary
- **Docs read:** [list]
- **Sections written:** §3
- **AIM count confirmed:** [N AIMs extracted]
- **Key spec requirements:** [3–5 critical]
- **Items for next sessions:** [referenced but not extracted]

## Rules
- Extract what the spec SAYS — do NOT read code files
- Include exact formulas when provided (LaTeX notation if helpful)
- AIM_Extractions.md is large — read it in chunks but extract ALL 16 AIMs
- Underspecified AIMs: tag as [UNDERSPECIFIED: ...]
- Obsidian-only content: tag as [SOURCE: Obsidian doc NN]
PROMPT
}

generate_spec_exec_03() {
  local passover
  passover=$(get_passover "$PASS_DIR/spec_exec_02.txt")

  cat > "$PROMPT_DIR/spec_exec_03.txt" << PASSOVER_BLOCK
## Previous Session Summary
$passover

PASSOVER_BLOCK

  cat >> "$PROMPT_DIR/spec_exec_03.txt" << 'PROMPT'
You are extracting spec content for the Captain System consolidated spec reference. Session 3 of 7.

## Source Priority
V3 repo specs SUPERSEDE Obsidian vault originals.

## Documents to Read
PRIMARY (V3 — authoritative):
- docs/AIM-Specs/new-aim-specs/Program3_Offline.md (~1729 lines)
- docs/AIM-Specs/new-aim-specs/DMA_MoE_Implementation_Guide.md (~339 lines)

SUPPLEMENTARY (Obsidian vault):
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/32_P3_Offline_Full_Pseudocode.md (~782 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/21_Implementation_Guides.md (~205 lines)

## What to Extract

### §4 — Offline Blocks 1–9
For EACH block (B1 through B9), same structure as §2:

### Block N: [Name]
- **PG ID:** P3-OFF-BN
- **Purpose:** (one line)
- **Trigger:** (event-driven, scheduled, or upstream)
- **Inputs:** Datasets (QuestDB R) | Redis keys | Upstream blocks
- **Outputs:** Datasets (QuestDB W) | Redis keys | Downstream
- **Key Logic:** (algorithms, formulas, thresholds)
- **Shared vs Per-User** | **Error Handling**

### §5 — Kelly 7-Layer Pipeline
Extract the COMPLETE Kelly sizing pipeline, layer by layer:

### Layer N: [Name]
- **Purpose:** (one line)
- **Inputs:** [datasets, parameters]
- **Formula:** [exact formula from spec]
- **Output:** [what this layer produces]
- **Dataset Refs:** [QuestDB tables — D12, etc.]
- **Constraints:** [caps, floors, bounds]

Include: raw Kelly fraction, shrinkage, regime adjustment, CB interaction, basket allocation, account cap, final position size.

### §6 — Circuit Breaker 5 Layers

### Layer N: [Name]
- **Condition:** [trigger]
- **Action:** [reduce size, pause trading, alert, etc.]
- **Dataset Refs:** [D25, etc.]
- **Parameters:** [thresholds, beta_b, correlation windows]
- **Recovery:** [how trading resumes]

Include per-asset vs account-level vs system-level distinctions.

## Output
Read the existing docs/audit/spec_reference.md (has §1–3 from Sessions 1–2).
APPEND §4, §5, §6 to the end. Do NOT delete existing content.
Also write passover to: docs/audit/.passovers/spec_exec_03.txt

## Passover Format
---
## Session 3 Summary
- **Docs read:** [list]
- **Sections written:** §4, §5, §6
- **Kelly layers confirmed:** [N]
- **CB layers confirmed:** [N]
- **Key spec requirements:** [3–5 critical]
- **Items for next sessions:** [referenced but not extracted]

## Rules
- Extract what the spec SAYS — do NOT read code files
- Include EXACT formulas for Kelly and CB — most audit-critical sections
- Note where DMA_MoE guide adds detail beyond main Offline spec
- Obsidian-only content: tag as [SOURCE: Obsidian doc NN]
PROMPT
}

generate_spec_exec_04() {
  local passover
  passover=$(get_passover "$PASS_DIR/spec_exec_03.txt")

  cat > "$PROMPT_DIR/spec_exec_04.txt" << PASSOVER_BLOCK
## Previous Session Summary
$passover

PASSOVER_BLOCK

  cat >> "$PROMPT_DIR/spec_exec_04.txt" << 'PROMPT'
You are extracting spec content for the Captain System consolidated spec reference. Session 4 of 7.

## Source Priority
No dedicated V3 doc exists for Command — Obsidian vault docs are PRIMARY for this session. Use V3 Nomaan_Edits_P3.md for amendments (tag as [V3 AMENDMENT] where it overrides Obsidian).

## Documents to Read
PRIMARY (Obsidian — no V3 Command equivalent):
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/34_P3_Command_Full_Pseudocode.md (~380 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/18_GUI_Dashboard.md (~149 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/26_Notification_System.md (~159 lines)

SUPPLEMENTARY (V3 amendments):
- docs/AIM-Specs/new-aim-specs/Nomaan_Edits_P3.md (~275 lines)

ADDITIONAL (if needed for RBAC context):
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/19_User_Management.md (~158 lines)

## What to Extract

### §7 — Command Blocks 1–10
For EACH block (B1 through B10):

### Block N: [Name]
- **PG ID:** P3-CMD-BN
- **Purpose:** (one line)
- **Trigger:** (always-on, event-driven, API call)
- **Inputs:** Datasets (QuestDB R) | Redis keys | API endpoints consumed
- **Outputs:** Datasets (QuestDB W) | Redis keys | API responses
- **Key Logic:** (routing rules, TAKEN/SKIPPED, parity filter, etc.)
- **Shared vs Per-User**

### §8 — GUI Panels + Security
- All GUI panels/tabs (name, purpose, data sources)
- Autonomy tiers (manual, semi-auto, full-auto) — what each controls
- Security model: the "6 outbound fields only" rule — what are the 6 fields?
- WebSocket channels for real-time GUI updates
- Notification system: event types, priority levels (CRITICAL/HIGH/MEDIUM/LOW), quiet hours
- Telegram bot integration points

## Output
Read the existing docs/audit/spec_reference.md (has §1–6 from Sessions 1–3).
APPEND §7, §8 to the end. Do NOT delete existing content.
Also write passover to: docs/audit/.passovers/spec_exec_04.txt

## Passover Format
---
## Session 4 Summary
- **Docs read:** [list]
- **Sections written:** §7, §8
- **Command blocks confirmed:** [N]
- **GUI panels confirmed:** [N]
- **Key spec requirements:** [3–5 critical]
- **Items for next sessions:** [referenced but not extracted]

## Rules
- Extract what the spec SAYS — do NOT read code files
- Flag areas where original spec may be outdated vs V3
- If Nomaan_Edits contradicts Obsidian, prefer Nomaan_Edits and tag [V3 AMENDMENT]
- Pay special attention to "6 outbound fields" security rule — this is critical
PROMPT
}

generate_spec_exec_05() {
  local passover
  passover=$(get_passover "$PASS_DIR/spec_exec_04.txt")

  cat > "$PROMPT_DIR/spec_exec_05.txt" << PASSOVER_BLOCK
## Previous Session Summary
$passover

PASSOVER_BLOCK

  cat >> "$PROMPT_DIR/spec_exec_05.txt" << 'PROMPT'
You are extracting spec content for the Captain System consolidated spec reference. Session 5 of 7.

## Source Priority
V3 P3_Dataset_Schemas.md supersedes Obsidian doc 24 for schema definitions. Other supporting specs are Obsidian-only.

## Documents to Read
PRIMARY (V3 for schemas):
- docs/AIM-Specs/new-aim-specs/P3_Dataset_Schemas.md (~565 lines)

PRIMARY (Obsidian for supporting systems):
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/24_P3_Dataset_Schemas.md (~265 lines) — supplementary to V3
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/25_Fee_Payout_System.md (~143 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/20_Signal_Distribution.md (~108 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/27_Contract_Rollover.md (~79 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/28_Pseudotrader_System.md (~121 lines)

## What to Extract

### §9 — QuestDB Dataset Master List (D00–D27)
For EVERY P3 dataset (D00 through D27):

### D[NN]: [table_name]
- **Purpose:** (one line)
- **Key Fields:** [field names and types from V3 spec]
- **Writer:** [which process/block writes]
- **Reader:** [which process/block reads]
- **Write Frequency:** [per-tick, per-session, daily, on-event]
- **Retention:** [partition, TTL if specified]
- **Notes:** [constraints, multi-user implications]

If a dataset is referenced in earlier sections but not defined here, note as [REFERENCED BUT UNDEFINED].

### §10 — Supporting Systems

**Fee Resolution:** formula, per-asset fees, payout rules, TopstepX handling
**Signal Distribution:** format, fields, Redis channel, anti-copy measures, multi-user routing
**Contract Rollover:** detection logic, ID resolution, timeline per asset, data continuity
**Pseudotrader:** account-aware simulation, shadow positions, theoretical outcomes, parity interaction

## Output
Read the existing docs/audit/spec_reference.md (has §1–8 from Sessions 1–4).
APPEND §9, §10 to the end. Do NOT delete existing content.
Also write passover to: docs/audit/.passovers/spec_exec_05.txt

## Passover Format
---
## Session 5 Summary
- **Docs read:** [list]
- **Sections written:** §9, §10
- **Datasets cataloged:** [N out of 28]
- **Key spec requirements:** [3–5 critical]
- **Items for next sessions:** [referenced but not extracted]

## Rules
- Extract what the spec SAYS — do NOT read code files
- Be EXHAUSTIVE for §9 — every dataset the spec mentions must appear
- V3 P3_Dataset_Schemas.md has field-level detail Obsidian lacks — prefer V3 fields
- Sparsely defined datasets: include with [SCHEMA INCOMPLETE]
PROMPT
}

generate_spec_exec_06() {
  local passover
  passover=$(get_passover "$PASS_DIR/spec_exec_05.txt")

  cat > "$PROMPT_DIR/spec_exec_06.txt" << PASSOVER_BLOCK
## Previous Session Summary
$passover

PASSOVER_BLOCK

  cat >> "$PROMPT_DIR/spec_exec_06.txt" << 'PROMPT'
You are extracting spec content for the Captain System consolidated spec reference. Session 6 of 7.

## Documents to Read
CANVAS FILES (JSON — parse node/edge structure):
- /mnt/c/Users/nomaa/Documents/Quant_Project/Functional/Programs 1-2-3.canvas — System flow across all 3 processes
- /mnt/c/Users/nomaa/Documents/Quant_Project/Functional/AIM System.canvas — AIM data flow
- /mnt/c/Users/nomaa/Documents/Quant_Project/Backend/VALIDATE Programs 1-2-3.canvas — Validation flow

OBSIDIAN DOCS:
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/15_Model_Definitions.md (~188 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/16_Strategy_Type_Registry.md (~42 lines)
- /mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/29_Operational_Policies.md (~199 lines)

V3 SUPPLEMENTARY:
- docs/AIM-Specs/new-aim-specs/Cross_Reference_PreDeploy_vs_V3.md (~367 lines)

## Canvas File Parsing
Canvas files are JSON:
```json
{"nodes": [{"id":"..","type":"text","text":"..","x":N,"y":N}], "edges": [{"id":"..","fromNode":"..","toNode":"..","label":".."}]}
```
Extract: node text content, edge labels (data flow), overall flow topology. Nodes near each other are related.

## What to Extract

### §11 — Feedback Loops (all 6)
Identify ALL feedback loops from canvas files. For each:

### Loop N: [Name]
- **Trigger:** [what initiates — trade outcome, EOD, decay, etc.]
- **Data Flow:** [step-by-step: process/block produces -> consumes -> updates]
- **Datasets Involved:** [QuestDB tables R/W]
- **Latency:** [real-time, per-session, daily, event-driven]
- **Cross-Process:** [which processes — Online, Offline, Command]

Look for these 6 loops:
1. Trade outcome -> Offline learning (DMA, EWMA, Kelly, BOCPD)
2. Decay detection -> Strategy injection
3. AIM lifecycle changes -> Online aggregation weights
4. Circuit breaker trigger -> Position sizing reduction
5. Reconciliation -> Account state update
6. Pseudotrader/shadow -> Theoretical outcome learning

### §12 — Daily Lifecycle
Complete daily timeline (all times ET):
- 19:00 SOD reset (what resets, what persists)
- Pre-session activities
- Session open -> OR calculation -> signal generation
- Trading window -> active monitoring
- Session close -> EOD procedures
- Post-session -> reconciliation, learning updates
- Weekend/holiday/rollover handling

### §13 — Strategy Types + Exit Grid
- Strategy types ST-01 through ST-06 (or however many defined)
- Per type: entry logic, exit grid, variant count
- Exit grid structure: TP levels, SL levels, trailing stop logic
- Strategy type mapping to (m,k) pairs from P2

## Output
Read the existing docs/audit/spec_reference.md (has §1–10 from Sessions 1–5).
APPEND §11, §12, §13 to the end. Do NOT delete existing content.
Also write passover to: docs/audit/.passovers/spec_exec_06.txt

## Passover Format
---
## Session 6 Summary
- **Docs read:** [list]
- **Sections written:** §11, §12, §13
- **Feedback loops confirmed:** [N]
- **Strategy types confirmed:** [N]
- **Key spec requirements:** [3–5 critical]
- **ALL 13 SECTIONS SHOULD NOW BE COMPLETE**

## Rules
- Extract what the spec SAYS — do NOT read code files
- Canvas files need structural parsing — interpret the flow, don't dump raw JSON
- Inferred loops: tag as [INFERRED FROM CANVAS]
- Cross-reference canvas flows against §2, §4, §7 block definitions — note inconsistencies
PROMPT
}

generate_spec_exec_07() {
  local passover
  passover=$(get_passover "$PASS_DIR/spec_exec_06.txt")

  cat > "$PROMPT_DIR/spec_exec_07.txt" << PASSOVER_BLOCK
## Previous Session Summary
$passover

PASSOVER_BLOCK

  cat >> "$PROMPT_DIR/spec_exec_07.txt" << 'PROMPT'
You are performing the Master Gap Analysis for the Captain System. Session 7 of 7 — FINAL.

## Skills — Invoke FIRST
Call these skills using the Skill tool before any analysis:
1. Skill(skill: "codebase-audit-suite:ln-620-codebase-auditor")
2. Skill(skill: "codebase-audit-suite:ln-623-code-principles-auditor")
3. Skill(skill: "codebase-audit-suite:ln-627-observability-auditor")
4. Skill(skill: "codebase-audit-suite:ln-629-lifecycle-auditor")
After loading all 4 skills, apply their checklists during the gap analysis below.

## Documents to Read
SPEC REFERENCE (completed by Sessions 1–6):
- docs/audit/spec_reference.md — All 13 sections (§1–§13)

PHASE 1 CODE AUDIT REPORTS:
- docs/audit/captain_online.md — Online pipeline audit
- docs/audit/captain_offline.md — Offline pipeline audit
- docs/audit/captain_command.md — Command interface audit
- docs/audit/cross_cutting.md — Shared library/config audit

## What to Produce
Write docs/audit/master_gap_analysis.md with this structure:

### Header
# Captain System — Master Gap Analysis
Generated: [date]
Spec source: docs/audit/spec_reference.md (13 sections)
Code source: docs/audit/ (4 Phase 1 reports) + codebase verification
Methodology: Spec-to-code cross-reference

### Part 1 — Summary Statistics
| Metric | Count |
|--------|-------|
| Total spec components | N |
| Aligned (code matches spec) | N |
| Divergent (code differs) | N |
| Stubbed (TODO/placeholder) | N |
| Missing (spec requires, code absent) | N |

### Part 2 — Critical Gaps
For EACH gap:

### G-XXX: [Title]
- **Severity:** CRITICAL / HIGH / MEDIUM / LOW
- **Spec Ref:** [section:block:PG] — what spec requires
- **Code Ref:** [file:line] — what code does (or "ABSENT")
- **Gap:** [one-line divergence description]
- **Impact:** [what breaks — session trading, learning, risk, etc.]
- **Dependencies:** [other gaps that must be fixed together]
- **Complexity:** S / M / L / XL

### Part 3 — Sections
1. Online Pipeline Gaps (B1–B9)
2. Offline Pipeline Gaps (B1–B9)
3. Command Pipeline Gaps (B1–B10)
4. Session/Trigger Gaps (multi-session, timing)
5. QuestDB Schema Gaps (tables, fields)
6. AIM Implementation Gaps (per-AIM)
7. Kelly/Circuit Breaker Gaps (layer-by-layer)
8. Feedback Loop Gaps (which of 6 are broken/missing)
9. GUI/Security Gaps (panels, security model)

### Part 4 — Recommended Implementation Order
Dependency-sorted, critical-first:
| Priority | Gap IDs | Description | Blocked By | Complexity |

## How to Find Gaps
For each spec component in spec_reference.md:
1. Check if Phase 1 audit already identified a finding — cite it
2. If not covered, search the codebase: use Grep to find implementation, compare against spec
3. Categorize: ALIGNED, DIVERGENT, STUBBED, or MISSING
4. Note exact file:line for code references

## Rules
- Every gap MUST have BOTH spec citation AND code citation (file:line or "ABSENT")
- Do NOT propose fixes — only document gaps. Fixes come in Phase 3.
- Phase 1 findings that aren't spec divergences should be excluded
- Be exhaustive — better to document a minor gap than miss a critical one
- Gap IDs: G-001 through G-NNN, sequential within each section
PROMPT
}

# ═══════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════

run_all() {
  local total_start
  total_start=$(date +%s)

  archive_old_files
  log ""

  # ── Phase 1: Foundation (EXEC-01) ──
  banner "PHASE 1 — Foundation (SPEC-EXEC-01)"
  log "Creates spec_reference.md with §1 (Sessions) and §2 (Online Blocks)"
  log ""

  generate_spec_exec_01
  run_exec "SPEC-EXEC-01" "$PROMPT_DIR/spec_exec_01.txt" "$SPEC_REF"
  log ""

  # ── Phase 2: Sequential extraction (EXEC-02 through 06) ──
  banner "PHASE 2 — Sequential Extraction (SPEC-EXEC-02 through 06)"

  local session_info=(
    "02:§3 (AIM System — 16 AIMs)"
    "03:§4-6 (Offline Blocks + Kelly + Circuit Breaker)"
    "04:§7-8 (Command Blocks + GUI)"
    "05:§9-10 (QuestDB Schemas + Supporting Systems)"
    "06:§11-13 (Feedback Loops + Lifecycle + Strategy Types)"
  )

  for entry in "${session_info[@]}"; do
    local num="${entry%%:*}"
    local desc="${entry#*:}"
    log ""
    log "--- SPEC-EXEC-$num: $desc ---"

    "generate_spec_exec_$num"
    run_exec "SPEC-EXEC-$num" "$PROMPT_DIR/spec_exec_$num.txt" "$SPEC_REF"
  done
  log ""

  # ── Checkpoint ──
  if ! check_sections; then
    log ""
    log "Stopping before EXEC-07. Fix missing sections and rerun:"
    log "  bash docs/audit/run_spec_audit.sh spec_exec_07"
    local elapsed=$(( $(date +%s) - total_start ))
    log "Elapsed: $(( elapsed / 60 ))m$(( elapsed % 60 ))s"
    exit 1
  fi
  log ""

  # ── Phase 3: Master Gap Analysis (EXEC-07) ──
  banner "PHASE 3 — Master Gap Analysis (SPEC-EXEC-07)"
  log "Loads 4 audit skills, cross-references spec vs code"
  log ""

  generate_spec_exec_07
  run_exec "SPEC-EXEC-07" "$PROMPT_DIR/spec_exec_07.txt" "$GAP_FILE"

  # ── Summary ──
  local total_elapsed=$(( $(date +%s) - total_start ))
  local total_mins=$(( total_elapsed / 60 ))
  local total_secs=$(( total_elapsed % 60 ))
  log ""
  banner "SPEC AUDIT COMPLETE"
  log "  Total time: ${total_mins}m${total_secs}s"
  log ""
  log "  Output files:"
  for f in "$SPEC_REF" "$GAP_FILE"; do
    if [[ -f "$f" ]]; then
      log "    $f  ($(wc -l < "$f") lines)"
    else
      log "    $f  (MISSING)"
    fi
  done
  log ""
  log "  Full log: $LOG_FILE"
  log ""
  log "  Next: Review master_gap_analysis.md, then begin Phase 3 (implementation)"
}

run_single() {
  local session="$1"

  case "$session" in
    spec_exec_01)
      generate_spec_exec_01
      run_exec "SPEC-EXEC-01" "$PROMPT_DIR/spec_exec_01.txt" "$SPEC_REF"
      ;;
    spec_exec_02)
      generate_spec_exec_02
      run_exec "SPEC-EXEC-02" "$PROMPT_DIR/spec_exec_02.txt" "$SPEC_REF"
      ;;
    spec_exec_03)
      generate_spec_exec_03
      run_exec "SPEC-EXEC-03" "$PROMPT_DIR/spec_exec_03.txt" "$SPEC_REF"
      ;;
    spec_exec_04)
      generate_spec_exec_04
      run_exec "SPEC-EXEC-04" "$PROMPT_DIR/spec_exec_04.txt" "$SPEC_REF"
      ;;
    spec_exec_05)
      generate_spec_exec_05
      run_exec "SPEC-EXEC-05" "$PROMPT_DIR/spec_exec_05.txt" "$SPEC_REF"
      ;;
    spec_exec_06)
      generate_spec_exec_06
      run_exec "SPEC-EXEC-06" "$PROMPT_DIR/spec_exec_06.txt" "$SPEC_REF"
      ;;
    spec_exec_07)
      generate_spec_exec_07
      run_exec "SPEC-EXEC-07" "$PROMPT_DIR/spec_exec_07.txt" "$GAP_FILE"
      ;;
    checkpoint)
      check_sections
      ;;
    *)
      log "Unknown session: $session"
      log "Valid: spec_exec_01..07, checkpoint"
      exit 1
      ;;
  esac
}

# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

: > "$LOG_FILE"
log "Phase 2: Spec Consolidation + Master Gap Analysis"
log "Model: $MODEL | Effort: $EFFORT"
log ""

preflight
log ""

if [[ $# -eq 0 ]]; then
  run_all
else
  for session in "$@"; do
    run_single "$session"
  done
fi
