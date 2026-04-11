#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# run_ux_audit.sh — Hands-free captain-gui UX audit (BATCH 0–11)
#
# Automates the full UX overhaul: runs 12 sequential Claude Code sessions,
# each invoking the correct skill + applying targeted fixes from FIX_PLAN.
#
# Usage:
#   cd ~/captain-system/captain-gui
#   bash src/_audit/run_ux_audit.sh              # Full run (batches 0–11)
#   bash src/_audit/run_ux_audit.sh --resume 5   # Resume from batch 5
#
# Prerequisites:
#   - claude CLI installed and authenticated
#   - baseline-ui and fixing-accessibility skills available
#   - Working directory: ~/captain-system/captain-gui
# ═══════════════════════════════════════════════════════════════════════════

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUI_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="$SCRIPT_DIR/ux_audit.log"
PROMPT_DIR="$SCRIPT_DIR/.prompts"
TOTAL=12

mkdir -p "$PROMPT_DIR"

# ─── Configuration ──────────────────────────────────────────────────────────
MODEL="claude-opus-4-6"
EFFORT="max"
ALLOWED_TOOLS="Read,Write,Edit,Glob,Grep,Bash,Skill"
# ────────────────────────────────────────────────────────────────────────────

BATCH_NAMES=(
  "Foundation"
  "App Shell"
  "Market + Chart"
  "Risk + Trade"
  "Position + AIM"
  "Modal + SysLog"
  "Signals + Dashboard"
  "Replay Controls"
  "Replay Panels"
  "Pages A"
  "Pages B"
  "Cleanup"
)

current_batch=0

# ═══════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" | tee -a "$LOG_FILE"
}

banner() {
  local n=$1 name=$2 total=$TOTAL
  local done_pct=$(( n * 100 / total ))
  local filled=$(( done_pct / 5 ))
  local empty=$(( 20 - filled ))

  local bar=""
  for ((i=0; i<filled; i++)); do bar+="█"; done
  for ((i=0; i<empty;  i++)); do bar+="░"; done

  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  printf "║  BATCH %d / %d  ─  %-48s  ║\n" "$n" "$((total - 1))" "$name"
  printf "║  Progress: [%s] %3d%%                                      ║\n" "$bar" "$done_pct"
  echo "╚══════════════════════════════════════════════════════════════════╝"
  echo ""
}

heartbeat() {
  local batch_n=$1 start_ts=$2
  while true; do
    sleep 30
    local elapsed=$(( $(date +%s) - start_ts ))
    local m=$((elapsed / 60)) s=$((elapsed % 60))
    printf '\r  ⏱  BATCH %d still running … %dm %02ds elapsed  \n' "$batch_n" "$m" "$s" >&2
  done
}

format_duration() {
  local secs=$1
  printf '%dm %02ds' $((secs / 60)) $((secs % 60))
}

# ═══════════════════════════════════════════════════════════════════════════
# BATCH RUNNER
# ═══════════════════════════════════════════════════════════════════════════

run_batch() {
  local n=$1
  local name="${BATCH_NAMES[$n]}"
  local prompt_file="$PROMPT_DIR/batch_$(printf '%02d' "$n").txt"

  banner "$n" "$name"
  log "START  batch $n — $name"

  if [[ ! -f "$prompt_file" ]]; then
    log "ERROR  prompt file missing: $prompt_file"
    return 1
  fi

  local start_ts
  start_ts=$(date +%s)

  # Heartbeat — prints elapsed time every 30s
  heartbeat "$n" "$start_ts" &
  local hb_pid=$!

  # Run Claude session
  cd "$GUI_DIR"
  claude -p "$(cat "$prompt_file")" \
    --model "$MODEL" \
    --effort "$EFFORT" \
    --allowedTools "$ALLOWED_TOOLS" \
    --output-format text \
    2>&1 | tee -a "$LOG_FILE"
  local exit_code=${PIPESTATUS[0]}

  # Stop heartbeat
  kill "$hb_pid" 2>/dev/null; wait "$hb_pid" 2>/dev/null || true

  local elapsed=$(( $(date +%s) - start_ts ))
  local dur
  dur=$(format_duration "$elapsed")

  if [[ $exit_code -ne 0 ]]; then
    log "FAIL   batch $n — $name  (exit $exit_code, $dur)"
    return 1
  fi

  # Git commit (only src/ changes)
  cd "$GUI_DIR"
  if ! git diff --quiet -- src/ || \
     ! git diff --cached --quiet -- src/ || \
     [[ -n "$(git ls-files --others --exclude-standard -- src/)" ]]; then
    git add -A -- src/
    git commit -m "ux-audit: batch $n — $(echo "$name" | tr '[:upper:]' '[:lower:]')" || true
    log "COMMIT batch $n"
  else
    log "SKIP   batch $n — no src/ changes detected"
  fi

  log "DONE   batch $n — $name  ($dur)"
  return 0
}

# ═══════════════════════════════════════════════════════════════════════════
# PROMPT GENERATION
# ═══════════════════════════════════════════════════════════════════════════

generate_prompts() {

# ── BATCH 0 — Foundation ─────────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_00.txt" << 'BATCH_END'
You are executing BATCH 0 — Foundation of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "baseline-ui"
  args: "review src/components/shared/"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic: monospace fonts, near-black backgrounds (#0a0e17, #111827), 1px solid borders (#1e293b), Lucide icons
- DO NOT change layout structure, component hierarchy, or routing
- DO NOT add new dependencies

### Fixes

1. src/global.css (FIX-145):
   Add a global `*:focus-visible` ring style: `outline: 2px solid #3b82f6; outline-offset: 2px`. This cascades app-wide.

2. src/components/shared/StatusDot.jsx (FIX-146):
   Accept a `label` prop, render `role="status"` and `aria-label={label}`. Add sr-only text span.

3. src/components/shared/CollapsiblePanel.jsx (FIX-074..078):
   - Add `aria-expanded={isOpen}` on toggle button
   - Add `aria-controls` pointing to panel id
   - Generate unique `id` on content panel
   - Wrap chevron chars in `aria-hidden="true"`
   - Add `focus-visible` ring on toggle

4. src/components/shared/DataTable.jsx (FIX-131..132):
   - Add `aria-label` on search input
   - Add a subtle gradient fade or shadow on the scroll edge as scroll affordance

5. src/components/shared/StatusBadge.jsx (FIX-147):
   Bump `text-[10px]` to `text-[11px]`.

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 1 — App Shell ──────────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_01.txt" << 'BATCH_END'
You are executing BATCH 1 — App Shell of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "fixing-accessibility"
  args: "src/components/layout/TopBar.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/App.jsx (FIX-143..144):
   - FIX-143: In RequireAuth, replace `return null` during loading with a centered spinner or skeleton matching the dark theme
   - FIX-144: Set document.title per route

2. src/api/client.js (FIX-148):
   Replace `window.location.href = "/login"` with a soft redirect approach — store a flag or use an event the AuthContext can listen to, avoiding hard nav that kills Zustand state.

3. src/auth/AuthContext.jsx (FIX-149):
   Ensure the loading state is consumed by App.jsx's RequireAuth spinner.

4. src/components/layout/TopBar.jsx (FIX-012..022):
   - Increase "Last tick" timestamp from text-[6.4px] to min text-[10px]
   - Increase health dots from 5.5px to min 8px
   - Add sr-only text to each status dot (e.g., "API: connected")
   - Implement ARIA dropdown on account selector: aria-expanded, aria-haspopup="listbox", role="listbox" on menu, arrow-key navigation, Escape to close
   - Increase account dropdown and Git Pull buttons to min h-[32px]
   - Increase nav tab text to min text-[10px] with min px-[10px] py-[6px]
   - Add focus-visible styling on all interactive elements
   - Wrap decorative Unicode (▼, ↻, ⚙, ✓, ✗, ↓) in aria-hidden="true"
   - Round h-[36.6px] to h-[36px] or h-9

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 2 — Market + Chart ─────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_02.txt" << 'BATCH_END'
You are executing BATCH 2 — Market + Chart of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "baseline-ui"
  args: "review src/components/layout/MarketTicker.jsx src/components/chart/ChartPanel.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/components/layout/MarketTicker.jsx (FIX-039..046):
   - FIX-039 CRITICAL: The 9 hardcoded tickers must show real data or "---" when no data. Check the liveMarket store — wire all tickers to it the same way MES is wired. If the store only supports one asset currently, show "---" for unconnected tickers and add a TODO comment.
   - FIX-040: Increase change % text from text-[7.5px] to min text-[10px]
   - FIX-041 CRITICAL: Convert ticker divs from `<div onClick>` to `<button>`. Add tabIndex, onKeyDown (Enter/Space).
   - FIX-042: Add sr-only text to green status dots
   - FIX-043: Increase ticker prices to min text-[10px], names to min text-[10px]
   - FIX-044: Add scroll shadow/fade indicator on overflow-x-auto
   - FIX-045: Add aria-current="true" on selected ticker
   - FIX-046: Increase status dots from 4.5px to min 6px

2. src/components/chart/ChartPanel.jsx (FIX-068..073):
   - FIX-068 CRITICAL: Increase system info footer from text-[6.3px] to min text-[10px]
   - FIX-069: Make price display responsive — use clamp() or responsive text classes instead of fixed text-[45.8px]
   - FIX-070: Round fractional sizes (21.2 → 21 or text-xl, 15.2 → 15 or text-sm)
   - FIX-071: Add overflow-hidden and text-ellipsis on OHLC + Bid/Ask row
   - FIX-072: Differentiate "---" states (OR not formed vs no data)
   - FIX-073: Add visually-hidden h1 for page context

3. Delete dead chart files (FIX-154..156):
   Delete these files — they are unused:
   - src/components/chart/CandlestickChart.jsx
   - src/components/chart/ChartOverlayToggles.jsx
   - src/components/chart/TimeframeSelector.jsx
   Remove any imports referencing them in ChartPanel.jsx.

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 3 — Risk + Trade ───────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_03.txt" << 'BATCH_END'
You are executing BATCH 3 — Risk + Trade of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "baseline-ui"
  args: "review src/components/risk/RiskPanel.jsx src/components/trading/TradeLog.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/components/risk/RiskPanel.jsx (FIX-001..011) — most complex component:
   - FIX-001 CRITICAL: Replace fixed `w-[42.7px]` drawdown bar segments with flex percentages so they don't overflow
   - FIX-002 CRITICAL: Replace ALL fractional pixel values (text-[10.7px], leading-[16.1px], gap-[9.1px] etc.) with nearest Tailwind scale values. These are Figma auto-export artifacts.
   - FIX-003..004 CRITICAL: Add `role="progressbar"`, `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax="100"` on MDD and Daily DD drawdown bars
   - FIX-005: Replace Payout cards fixed `w-[201px]` with responsive grid (e.g., grid-cols-2 md:grid-cols-3)
   - FIX-006: Replace `min-w-[112px] max-w-[149px]` on risk param cards with flex-wrap-friendly sizing
   - FIX-007: Replace `font-['JetBrains_Mono']` with `font-mono`
   - FIX-008: Fix footer label clipping
   - FIX-009: Add `role="progressbar"` on payout target bar
   - FIX-010: Replace `mq450`/`mq750`/`mq1025` with Tailwind sm:/md:/lg:
   - FIX-011: Replace `pb-[29px]` with nearest Tailwind spacing (pb-7 = 28px)

2. src/components/trading/TradeLog.jsx (FIX-106..109):
   - FIX-106: Increase column headers from text-[8.6px] to min text-[10px]
   - FIX-107: Replace fixed `gap-[33px]` with a proper table layout or auto grid
   - FIX-108: Convert div grid to semantic `<table>` with `<thead>`/`<tbody>`/`<th>`/`<td>` so screen readers can navigate it as tabular data
   - FIX-109: Increase total footer text slightly

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 4 — Position + AIM ─────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_04.txt" << 'BATCH_END'
You are executing BATCH 4 — Position + AIM of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "baseline-ui"
  args: "review src/components/trading/ActivePosition.jsx src/components/aim/AimRegistryPanel.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/components/trading/ActivePosition.jsx (FIX-079..083):
   - FIX-079 CRITICAL: Replace hardcoded `pl-[346px] pr-[265px]` on SL/TP bar with percentage-based or flex positioning that adapts to container width
   - FIX-080 CRITICAL: Increase ENTRY/CURRENT/SL/TP labels from text-[7.2px] to min text-[10px]
   - FIX-081: Round text-[18.4px] to text-lg or text-[18px]
   - FIX-082: Increase direction badge/contracts/order info from text-[8.2px] to min text-[10px]
   - FIX-083: Replace mq450/mq750/mq1025 with Tailwind sm:/md:/lg:

2. src/components/aim/AimRegistryPanel.jsx (FIX-031..038):
   - FIX-031 CRITICAL: Increase Activate/Deactivate buttons from py-0.5 text-[9px] to min h-[32px] text-[11px]
   - FIX-032 CRITICAL: Convert AimCard from `<div onClick>` to proper `<button>` or add `role="button"`, `tabIndex={0}`, `onKeyDown` (Enter/Space)
   - FIX-033: Increase tier badge from text-[8px] to min text-[10px]
   - FIX-034: Increase AIM card content from text-[10px] to text-[11px], increase padding from p-2 to p-3
   - FIX-035..036: Add `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax` on weight and warmup bars
   - FIX-037: Fix tier badge overlap with status badge — adjust positioning
   - FIX-038: Clean up redundant grid breakpoints (grid-cols-4 2xl:grid-cols-4 xl:grid-cols-4 → just grid-cols-4)

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 5 — Modal + SysLog ─────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_05.txt" << 'BATCH_END'
You are executing BATCH 5 — Modal + SysLog of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "fixing-accessibility"
  args: "src/components/aim/AimDetailModal.jsx src/components/system/SystemLog.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/components/aim/AimDetailModal.jsx (FIX-047..053):
   - FIX-047 CRITICAL: Add `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to the modal title
   - FIX-048 CRITICAL: Implement focus trap. On open, cycle Tab within modal. On close, return focus to trigger. Use a useEffect with keydown listener — no new deps needed.
   - FIX-049 CRITICAL: On mount, auto-focus the close button or first focusable element inside modal
   - FIX-050 CRITICAL: Add `aria-label="Close"` on close button
   - FIX-051: Increase close button to min w-[32px] h-[32px]
   - FIX-052: Increase body text from text-[10px] to text-[11px]
   - FIX-053: Add `aria-label` or `role="img"` with alt text to CheckIcon ✓/✗

2. src/components/system/SystemLog.jsx (FIX-061..067):
   - FIX-061 CRITICAL: Implement proper ARIA tablist: role="tablist" on tab container, role="tab" on each tab button, role="tabpanel" on content, aria-selected on active tab, arrow-key navigation between tabs
   - FIX-062 CRITICAL: Add `aria-pressed={isActive}` on filter buttons (ALL/Errors/Signals/Orders)
   - FIX-063: Increase filter button text from text-[8.6px] to min text-[10px]
   - FIX-064: Increase category labels from fontSize: "8px" to min 10px, convert from inline style to Tailwind
   - FIX-065: Convert all remaining inline styles to Tailwind classes
   - FIX-066: Increase log entry text from text-[9.7px] to text-[11px], increase leading from leading-[13.6px] to leading-relaxed
   - FIX-067: Add focus-visible styling on tab switching buttons

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 6 — Signals + Dashboard ────────────────────────────────────────
cat > "$PROMPT_DIR/batch_06.txt" << 'BATCH_END'
You are executing BATCH 6 — Signals + Dashboard of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "baseline-ui"
  args: "review src/components/signals/ src/pages/DashboardPage.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/components/signals/SignalCards.jsx (FIX-098..101):
   - Increase direction badges from text-[8px] to min text-[10px]
   - Increase confidence tier badge from text-[7px] to min text-[10px]
   - Increase clear button from text-[8px] px-[6px] py-[1px] to min h-[28px] px-[8px] text-[10px]
   - Normalize font sizes: collapse the 5-size range (11/10/9/8/7px) to 2-3 sizes max (11/10px)

2. src/components/signals/SignalExecutionBar.jsx (FIX-102..105):
   - Replace fixed `w-[558.7px]` with `w-full` or `max-w-xl` flex layout
   - Add `aria-current="step"` on active pipeline stage pill
   - Round text-[12.1px] to text-xs (12px)
   - Replace mq750/mq450 with Tailwind sm:/md:

3. src/pages/DashboardPage.jsx (FIX-089..093):
   - FIX-089 CRITICAL: Gate mock data injection behind `import.meta.env.VITE_DEV_MOCK === 'true'` instead of blanket `import.meta.env.DEV`
   - Increase ResizeHandle from 5px to 8px with visible drag indicator (3 dots or line)
   - Raise panel minSize from 5 to 15
   - Add a loading skeleton or spinner for initial API data fetch
   - Add visually-hidden h1 for screen reader landmarks

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 7 — Replay Controls ────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_07.txt" << 'BATCH_END'
You are executing BATCH 7 — Replay Controls of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "fixing-accessibility"
  args: "src/components/replay/PlaybackControls.jsx src/components/replay/ReplayConfigPanel.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/components/replay/PlaybackControls.jsx (FIX-023..030):
   - FIX-023..024 CRITICAL: Add aria-label="Play"/"Pause"/"Skip" on Unicode button elements
   - Increase Play/Pause from 24px to min 32px
   - Increase speed pills from text-[8px] to min text-[10px] with min h-[28px]
   - Increase progress bar from h-[3px] to h-[6px]
   - Add aria-pressed on active speed button
   - Add role="progressbar", aria-valuenow/min/max on progress bar
   - FIX-030 LOW: Add Space for play/pause keyboard shortcut if feasible

2. src/components/replay/ReplayConfigPanel.jsx (FIX-054..060):
   - Increase labels from text-[8px] to min text-[10px]
   - Increase toggle switches from h-[16px] w-[32px] to h-[20px] w-[40px]
   - Increase Run Replay button to min h-[36px] text-[12px]
   - Fix Label components: add htmlFor + matching id on inputs
   - Add aria-label on toggle switches
   - Add aria-label on preset select
   - Add aria-label on preset name input

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 8 — Replay Panels ──────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_08.txt" << 'BATCH_END'
You are executing BATCH 8 — Replay Panels of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "baseline-ui"
  args: "review src/components/replay/PipelineStepper.jsx src/components/replay/BatchPnlReport.jsx src/components/replay/AssetCard.jsx src/components/replay/BlockDetail.jsx src/components/replay/ReplaySummary.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/components/replay/PipelineStepper.jsx (FIX-094..097):
   - Convert stage divs to `<button>`
   - Add aria-expanded on expandable stages
   - Add sr-only text to circle indicators
   - Increase circle size to min 20px

2. src/components/replay/BatchPnlReport.jsx (FIX-084..088):
   - Add aria-pressed on Daily/Overall toggle
   - Add role="progressbar" on batch progress bar
   - Increase toggle text to min 10px
   - Style scrollbar for visibility (dark theme scrollbar)
   - Add descriptive aria-label on CSV export button

3. src/components/replay/AssetCard.jsx (FIX-129..130):
   - Increase direction badge to min text-[10px]
   - Increase session badge to min text-[8px]
   - Add aria-busy="true" during loading shimmer

4. src/components/replay/BlockDetail.jsx (FIX-133..134):
   - Flatten nested scroll to single scroll container
   - Add title attribute or tooltip on truncated reason column

5. src/components/replay/ReplaySummary.jsx (FIX-135..136):
   - Increase button touch targets to min h-[32px]
   - Increase trades table max-h from 160px to 240px

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 9 — Pages A ────────────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_09.txt" << 'BATCH_END'
You are executing BATCH 9 — Pages A of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "fixing-accessibility"
  args: "src/pages/HistoryPage.jsx src/pages/LoginPage.jsx src/pages/ReplayPage.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/pages/HistoryPage.jsx (FIX-110..113):
   - Add role="tablist" on tab container
   - Add role="tab" + aria-selected on tab buttons
   - Add role="tabpanel" on content area
   - Increase tab button padding to min py-2 px-4

2. src/pages/LoginPage.jsx (FIX-114..116):
   - Increase submit button to min h-[44px]
   - Add aria-describedby linking error message to input
   - Add role="alert" on error div
   - Remove autoFocus (or gate behind desktop check)

3. src/pages/ModelsPage.jsx (FIX-117..119):
   - Add TODO comment about independent data fetch for direct nav
   - Increase grid to grid-cols-2 md:grid-cols-3

4. src/pages/ReplayPage.jsx (FIX-120..122):
   - Add responsive breakpoint on 3-col grid (stack on narrow)
   - Increase drag handle to h-[8px]
   - Add role="separator" + aria-label on drag handle

5. src/components/replay/WhatIfComparison.jsx (FIX-137..138):
   - Increase max-h from 120px to 200px on contracts scroll
   - Add responsive handling for 4-col grid overflow

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 10 — Pages B ───────────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_10.txt" << 'BATCH_END'
You are executing BATCH 10 — Pages B of the captain-gui UX audit.

## Step 1 — Invoke Skill
Use the Skill tool FIRST, before making any manual changes:
  skill: "baseline-ui"
  args: "review src/pages/ReportsPage.jsx src/pages/SystemOverviewPage.jsx src/pages/ProcessesPage.jsx"
Wait for the skill to complete, then proceed to Step 2.

## Step 2 — Apply Targeted Fixes
Read each file before editing. Minimal changes only.

### Rules
- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/pages/ReportsPage.jsx (FIX-123..125):
   - Add responsive breakpoint (grid-cols-1 md:grid-cols-3)
   - Replace magic 140px in max-h calc with a CSS variable or comment explaining the value
   - Add aria-current="true" on selected report type

2. src/pages/SystemOverviewPage.jsx (FIX-126..128):
   - Increase text sizes from text-[10px] to text-[11px]
   - Improve stub section messages: replace "available via RPT-XX" with clearer "Coming soon — data source not yet connected"
   - Add aria-label on radar chart SVG container

3. src/pages/ProcessesPage.jsx (FIX-139..140):
   - Increase badge text to min text-[10px]
   - Increase file path text to min text-[10px]

4. src/pages/ConfigPage.jsx (FIX-150):
   Improve stub messaging — add a meaningful placeholder explaining what will go here.

5. src/pages/SettingsPage.jsx (FIX-151):
   Add aria-pressed or aria-checked on theme toggle button.

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

# ── BATCH 11 — Cleanup ───────────────────────────────────────────────────
cat > "$PROMPT_DIR/batch_11.txt" << 'BATCH_END'
You are executing BATCH 11 — Cleanup of the captain-gui UX audit.
This batch is store logic and JS only — no UI skill needed.

Read each file before editing. Minimal changes only.

### Rules
- DO NOT change layout structure, routing, or add new dependencies

### Fixes

1. src/stores/dashboardStore.js (FIX-141..142):
   - Add explicit fallback for unknown direction values (0, null, "BUY" → map to normalized "LONG"/"SHORT"/"UNKNOWN")
   - Cap localStorage signal archive at 500 entries with FIFO pruning

2. src/stores/notificationStore.js (FIX-153):
   Add max-size cap of 500 notifications. When adding beyond cap, shift oldest off the array.

3. src/ws/useWebSocket.js (FIX-152):
   On eviction (4001) or auth failure (4003) close codes, push a visible notification via notificationStore (e.g., "WebSocket disconnected: session evicted" or "WebSocket disconnected: authentication failed").

4. src/components/chart/TradingViewWidget.jsx (FIX-157):
   Add min-height (e.g., min-h-[200px]) or a guard that checks parent height > 0 before rendering the widget to prevent zero-height flash.

## Output
List what you changed (one line per fix). Flag anything you couldn't fix and why.
Do NOT create git commits — the orchestrator handles that.
BATCH_END

  log "Generated ${TOTAL} prompt files in $PROMPT_DIR"
}

# ═══════════════════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════════════════

cleanup() {
  local pids
  pids=$(jobs -p 2>/dev/null) || true
  if [[ -n "$pids" ]]; then
    echo "$pids" | xargs -r kill 2>/dev/null || true
  fi
}
trap cleanup EXIT

trap_interrupt() {
  echo ""
  log "INTERRUPTED at batch $current_batch"
  echo ""
  echo "  Resume with:  bash $0 --resume $current_batch"
  echo ""
  cleanup
  exit 130
}
trap trap_interrupt INT TERM

# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

START_BATCH=0
if [[ "${1:-}" == "--resume" ]]; then
  START_BATCH="${2:-0}"
  if [[ "$START_BATCH" -lt 0 || "$START_BATCH" -ge "$TOTAL" ]]; then
    echo "Error: --resume value must be 0–$((TOTAL - 1))"
    exit 1
  fi
fi

echo ""
echo "  ╔═══════════════════════════════════════════════════════════╗"
echo "  ║          captain-gui  UX  AUDIT  ORCHESTRATOR            ║"
echo "  ║                                                          ║"
echo "  ║  Batches: 0–11  (12 total)                               ║"
echo "  ║  Model:   $MODEL                              ║"
echo "  ║  Effort:  $EFFORT                                            ║"
echo "  ║  Log:     src/_audit/ux_audit.log                        ║"
echo "  ╚═══════════════════════════════════════════════════════════╝"
echo ""

if [[ $START_BATCH -gt 0 ]]; then
  log "RESUMING from batch $START_BATCH"
fi

log "═══ UX AUDIT START ═══"

# Verify claude CLI exists
if ! command -v claude &>/dev/null; then
  echo "Error: 'claude' CLI not found in PATH"
  exit 1
fi

# Generate all prompts
generate_prompts

# Track timing
run_start=$(date +%s)
passed=0
failed=0

for i in $(seq "$START_BATCH" $((TOTAL - 1))); do
  current_batch=$i
  if run_batch "$i"; then
    passed=$((passed + 1))
  else
    failed=$((failed + 1))
    log "STOPPING — batch $i failed"
    echo ""
    echo "  Resume with:  bash $0 --resume $i"
    echo ""
    break
  fi
done

run_elapsed=$(( $(date +%s) - run_start ))
run_dur=$(format_duration "$run_elapsed")

# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

echo ""
echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                      UX AUDIT SUMMARY                           ║"
echo "╠═══════════════════════════════════════════════════════════════════╣"
printf "║  Batches passed:  %-3d / %-3d                                    ║\n" "$passed" "$TOTAL"
printf "║  Batches failed:  %-3d                                          ║\n" "$failed"
printf "║  Total time:      %-10s                                     ║\n" "$run_dur"
echo "║  Log file:        src/_audit/ux_audit.log                       ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo ""

log "═══ UX AUDIT END — passed=$passed failed=$failed time=$run_dur ═══"

if [[ $failed -gt 0 ]]; then
  exit 1
fi
