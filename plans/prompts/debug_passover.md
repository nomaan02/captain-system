# Debug & Finalize: scripts/run_implementation.sh

You are picking up a partially-working automation script that orchestrates an ABC (Coordinator → Executor → Validator) implementation workflow for the Captain System trading platform. The script needs bug fixes before a clean full run.

## Context

This script automates 12 executor sessions across 7 phases. Each session:
1. Generates a prompt for Agent C (Executor) via `generate_session_NN()` functions
2. Runs `claude -p` with the prompt (executor implements code changes)
3. Runs pytest
4. Generates a validator prompt and runs `claude -p` (validator checks changes vs spec)
5. Shows a dashboard, then waits for human ENTER before next session

Session 01 already ran successfully — 6 critical gaps fixed, 95/95 tests passing. The validator also ran (3m14s). But the script has bugs that need fixing before doing a clean full run of sessions 02–12.

## Files to Read

1. `scripts/run_implementation.sh` — THE SCRIPT (1350+ lines). Read it all.
2. `plans/CAPTAIN_RECONCILIATION_MATRIX.md` — the matrix it tracks against. Skim §1 (gap entries) and §6 (dashboard).
3. `logs/implementation/` — check exec_01.log and validate_01.log for actual output from the first run
4. `plans/prompts/.passovers/session_01.txt` — passover from session 01 (if it exists)
5. `plans/prompts/.generated/` — generated prompts from first run

## Known Bugs to Fix

### Bug 1: Dashboard shows all zeros with broken formatting

The `dashboard()` function uses:
```bash
count=$(grep -c "Status: $status" "$MATRIX" 2>/dev/null || echo 0)
```

Two problems:
- **Wrong pattern**: Matrix format is `**Status:** UNRESOLVED` (markdown bold), not `Status: UNRESOLVED`
- **Double zero**: `grep -c` with no matches prints `0` to stdout AND exits code 1, so `|| echo 0` appends a second `0`. The variable becomes `"0\n0"` which breaks the printf table formatting.

Fix both: correct the grep pattern and handle the exit code properly. Something like:
```bash
count=$(grep -c '\*\*Status:\*\*.*'"$status" "$MATRIX" 2>/dev/null) || count=0
```

### Bug 2: Verify the sed fix actually works

The `run_validator()` function was rewritten to use a heredoc instead of sed for template substitution. Session 01 validator ran OK (3m14s), but verify no edge cases remain — e.g., passover content with backticks, dollar signs, or other shell-special characters that could break the unquoted heredoc.

### Bug 3: Audit for other potential issues

Before doing a full run, audit the entire script for:
- Any other `grep` patterns that assume plain text but the matrix uses markdown formatting
- Heredoc quoting issues in `generate_session_02()` through `generate_session_12()` — sessions 02+ use an unquoted heredoc for the passover block (`<<PASSOVER_BLOCK`) followed by a quoted heredoc for the body (`<< 'PROMPT'`). If a passover contains shell metacharacters (`$`, backticks, `\`), the unquoted heredoc will expand them.
- The `run_skill()` function — verify the skill invocation pattern works with `claude -p`
- Edge cases in `run_phase()` — the `skills=("$@")` after the `--` separator
- The `--session` CLI path — it calls `generate_session_${padded}` which works for `01`-`12` but would fail for `13` (verification-only session with no generate function)

## What a Successful Fix Looks Like

1. `bash scripts/run_implementation.sh --dashboard` shows correct counts (currently: 6 FIXED from session 01, 61 UNRESOLVED, 33 DEFERRED, etc.)
2. `bash scripts/run_implementation.sh --validate 01` runs cleanly with proper dashboard after
3. `bash scripts/run_implementation.sh --session 02` runs executor + pytest + validator for session 02 without errors
4. No shell expansion bugs in any generated prompt

## Current State

- **Branch:** `final_val_1.0`
- **Session 01:** COMPLETE (executor + pytest + validator all passed)
- **Sessions 02–12:** NOT YET RUN
- **Matrix decisions:** All 10 DEC-01 through DEC-10 RESOLVED
- **Matrix dashboard (§6):** Shows stale counts because executor updated status lines but dashboard grep can't read them

## Rules

1. Read the full script before making any changes
2. Fix all bugs, not just the known ones — do a thorough audit
3. Run `bash -n scripts/run_implementation.sh` after every edit to syntax-check
4. Test `--dashboard` after fixing the grep pattern
5. Do NOT run any executor sessions — only test infrastructure (dashboard, validate, prompt generation)
6. When done, show me the fixed dashboard output and confirm the script is ready for a clean `--phase2` through `--phase7` run
