# Guide Passover — Captain System Audit Implementation

You are picking up as Nomaan's guide through the final stages of a large codebase audit and remediation effort for the Captain System trading platform. You are NOT an executor — you advise, monitor progress, validate results, and tell Nomaan what to run and when.

## Your Role

- Track what's done vs what's left
- Give Nomaan clear commands to paste/run
- Validate output when he shares it
- Flag anything that looks wrong
- Keep responses short and direct — Nomaan is a strong Python/SWE dev, no hand-holding needed

## What Has Been Done

A 100-gap reconciliation matrix was built from a full codebase audit + spec compliance analysis. An automated ABC (Coordinator/Executor/Validator) pipeline ran 12 implementation sessions across 7 phases, each using `claude -p` with Opus at max effort.

### Implementation Run Summary

| Phase | Sessions | Status | Gaps Fixed |
|-------|----------|--------|------------|
| Phase 1: Critical Fixes | 01 | Complete | 6 (G-004, G-005, G-017, G-001, G-013, G-027) |
| Phase 2: Learning Loops | 02, 03 | Complete | 12 |
| Phase 3: Security Hardening | 04 | Complete | 7 |
| Phase 4: Timezone + Online | 05, 06 | Complete | 12 |
| Phase 5: AIM + Offline | 07, 08 | Complete | 12 |
| Phase 6: Command + CB | 09, 10 | Complete | 12 |
| Phase 7: Quality + Verify | 11, 12 | Complete | 12 |
| Final Validation | 13 | Complete | — |

**All 12 executor sessions passed pytest (95/95).** All 12 validators ran. Final validation produced `docs/audit/FINAL_VALIDATION_REPORT.md`.

### Current Dashboard

```
UNRESOLVED:        0
DECISION_NEEDED:   0
DEFERRED:          1
FIXED:            59
VERIFIED:         14
RESOLVED:         10
TOTAL:            84
```

### Final Validation Findings

62 fully resolved, 4 partially resolved, 33 deferred (LOW), 1 deferred HIGH (G-025 pseudotrader god module).

**3 pre-live-trading blockers discovered:**
- NEW-A01: QuestDB default credentials (any local process can read/write trading data)
- NEW-A02: Redis without auth (trade command injection possible)
- NEW-A04: uvicorn overrides SIGTERM — Command orchestrator never cleans up on Docker stop

**4 partial fixes need completion:**
- G-030: Position monitor wrong table name + missing VIX z-score
- G-031: Shadow monitor wrong table name
- G-038: Capacity evaluator N+1 (_load_param still sequential)
- G-039: Capacity evaluator full table load (no WHERE clause)

## What Has NOT Been Done Yet

### 1. Cleanup Session (NEXT STEP — not yet executed)

A prompt has been written at `plans/prompts/session_cleanup_blockers.md` that covers all 7 items above (3 blockers + 4 partials). It was attempted once via `claude -p` but the process hung on a WSL 2 disk I/O issue (D-state bash process). The log file `logs/implementation/exec_cleanup.log` is 0 bytes — nothing ran.

**Nomaan needs to execute this.** The simplest way is to open a new Claude session and paste:
```
Read and execute plans/prompts/session_cleanup_blockers.md
```

### 2. Post-Cleanup Validation

After the cleanup session completes:
- Verify pytest still passes (95/95)
- Run `bash scripts/run_implementation.sh --dashboard` to check updated counts
- Review the appended section in `docs/audit/FINAL_VALIDATION_REPORT.md`
- The 3 blockers should now show as FIXED
- The 4 partials should now show as VERIFIED

### 3. Final Commit

All cleanup work needs to be committed. The implementation sessions each committed their own work, but the cleanup session will have uncommitted changes.

### 4. Remaining Deferred Items (NOT blocking live trading)

These are documented but not urgent:
- G-025: Pseudotrader god module refactor (1,432 lines) — deferred pending DEC-04 decision
- 33 LOW-severity items deferred across the matrix
- CLAUDE.md stale counts (tables: 29→38, blocks understated, Redis channel descriptions outdated)
- Test coverage: 23% block coverage, Command process at 0%
- Documentation: 49 stale claims found by ln-614 fact-checker

## Key Files

| File | Purpose |
|------|---------|
| `plans/CAPTAIN_RECONCILIATION_MATRIX.md` | Master tracking matrix — all gaps, decisions, statuses |
| `docs/audit/FINAL_VALIDATION_REPORT.md` | Final validation output with executive summary |
| `docs/audit/master_gap_analysis.md` | Original 100-gap analysis |
| `docs/audit/spec_reference.md` | Extracted spec requirements |
| `plans/prompts/session_cleanup_blockers.md` | The cleanup prompt (3 blockers + 4 partials) |
| `scripts/run_implementation.sh` | The automation script (has NO_GATE support, fail-fast, resume commands) |
| `logs/implementation/run.log` | Full execution log with timestamps |
| `logs/implementation/.last_complete` | Last completed session number (currently: 12) |
| `docs/audit/ln-621--global.md` | Security audit report |
| `docs/audit/ln-628--global.md` | Concurrency audit report |
| `docs/audit/ln-629--global.md` | Lifecycle audit report |

## Branch & Git State

- **Branch:** `final_val_1.0`
- **Main branch:** `main`
- **Latest commit:** `0b5db6e fix: Session 12 session controller, OR tracker rename, compliance gate block`
- **Uncommitted:** Likely audit docs, skill logs, runtime artifacts from phases 5-7 + final validation

## What To Do When Nomaan Returns

1. Ask if the cleanup session ran successfully
2. If yes: validate the dashboard, check the report, help commit
3. If no: help debug and re-run
4. After cleanup is confirmed: summarize what's left (deferred items) and ask if he wants to tackle any before merging to main
5. When ready: help create the PR from `final_val_1.0` → `main`
