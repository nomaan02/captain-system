# Audit Initiation Template

Paste this entire file into a Claude Code session to generate a full audit-to-implementation pipeline for any codebase target.

---

## 1. Configuration (EDIT THESE)

### Audit Identity
```
AUDIT_LABEL: my-audit-name
```
> This becomes the output directory name under `scripts/audits/<AUDIT_LABEL>/`. Use lowercase-kebab-case.

### Target Directory
```
TARGET_DIR: captain-online/captain_online/blocks/
```
> Relative to project root. Can be a single directory, a process root, or the entire repo (`.`).

### Spec Files (paths relative to project root)
```
SPEC_FILES:
  - docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/Nomaan_Master_Build_Guide.md
  - docs/completion-validation-docs/Step 1 - Original Specs/05_Program3_Online.md
```
> List every spec file the code should be compared against. More specs = more thorough gap analysis.

### Obsidian Vault (optional — for cross-referencing ambiguous specs)
```
OBSIDIAN_VAULT: /mnt/c/Users/nomaa/Documents/Quant_Project/
```
> Set to `NONE` if not applicable.

### Scope & Focus (optional — narrow the audit)
```
SCOPE_NOTES: |
  Focus on data ingestion and regime detection blocks.
  Exclude test files and scripts/.
  Pay special attention to timezone handling and QuestDB query patterns.
```
> Leave blank for a full audit with no exclusions.

### Model Settings
```
MODEL: claude-opus-4-6
EFFORT: max
```

---

## 2. Instructions for Claude

When I paste this template into a Claude Code session, execute the following phases in order. Do not skip phases. Ask me before proceeding to Phase 3 (implementation).

### Phase 1: Codebase Audit

1. Create the output directory: `scripts/audits/{AUDIT_LABEL}/`
2. Create subdirectories: `prompts/`, `prompts/.generated/`, `prompts/.passovers/`, `logs/`, `output/`
3. Read every Python file in `{TARGET_DIR}` — build a function map (file, function name, line number, purpose)
4. Run these audit skills against `{TARGET_DIR}`, saving each report to `output/`:
   - `/ln-624-code-quality-auditor` — complexity, nesting, god classes
   - `/ln-621-security-auditor` — secrets, injection, input validation
   - `/ln-628-concurrency-auditor` — races, deadlocks, blocking I/O
   - `/ln-629-lifecycle-auditor` — startup, shutdown, health checks
   - `/ln-626-dead-code-auditor` — unused imports, functions, dead paths
   - `/ln-625-dependencies-auditor` — outdated deps, CVEs, unused packages
5. Compile all findings into `output/codebase_audit.md` with severity counts

### Phase 2: Spec Compliance & Gap Analysis

1. Read each file in `{SPEC_FILES}`
2. Extract all requirements (numbered or bulleted) into `output/spec_reference.md` — each requirement gets a section ID (S1, S2, ...) with the source file noted
3. For each requirement, grep the codebase for its implementation
4. Cross-reference audit findings (Phase 1) against spec requirements
5. Produce `output/master_gap_analysis.md`:
   - Each gap gets an ID (G-001, G-002, ...)
   - Fields: ID, Severity (CRITICAL/HIGH/MEDIUM/LOW), Title, File(s), Line(s), Spec Reference, Description, Suggested Fix
6. Produce `output/decision_log.md` for any ambiguous items needing human input:
   - Each decision gets an ID (DEC-01, DEC-02, ...)
   - Fields: ID, Question, Options, Impact, Recommendation

### Phase 3: Reconciliation Matrix & Implementation Plan

1. Build `output/RECONCILIATION_MATRIX.md` from the gap analysis:
   - One entry per gap with: ID, Severity, Session assignment, Dependencies, Status (UNRESOLVED)
   - One entry per decision with: ID, Question, Status (DECISION_NEEDED)
   - Group gaps into sessions (max 6-7 items per session) ordered by dependency and severity
   - Group sessions into phases (2-3 sessions per phase)
   - Add a dashboard section (same format as captain-system matrix)
   - Add a changelog section
2. Present the matrix to me for review
3. Wait for me to resolve any DECISION_NEEDED items before proceeding

### Phase 4: Generate Implementation Script

Generate `scripts/audits/{AUDIT_LABEL}/run_implementation.sh` following the exact pattern of `scripts/run_implementation.sh` in the captain-system root:

- `dashboard()` reading from the matrix with correct `**Status:**` grep pattern
- `run_executor()` calling `claude -p` with `--dangerously-skip-permissions`
- `run_validator()` generating validator prompts from template + passover
- `run_pytest()` (adapt test command to target — or skip if no tests)
- `generate_session_NN()` for each session from the matrix
- `run_phase()` grouping sessions with phase-end audit skills
- `human_gate()` with `NO_GATE` support for hands-free runs
- Fail-fast with resume commands when `NO_GATE=1`
- Progress tracking to `logs/.last_complete`
- CLI: `--dashboard`, `--session NN`, `--validate NN`, `--phase1..N`, `--final`, `--all`

Each session prompt must include:
- Role assignment (executor or validator)
- The specific gap IDs and files to fix
- Spec references for each item
- Post-fix audit skill invocations
- Passover write instructions
- Matrix update instructions

### Phase 5: Dry Run Verification

1. Run `bash -n scripts/audits/{AUDIT_LABEL}/run_implementation.sh` — syntax check
2. Run `--dashboard` — verify counts match matrix
3. Generate session 01 prompt — verify it references correct files and spec sections
4. Report readiness to me

---

## 3. Resume / Re-entry Points

If a session fails mid-run:

| Situation | Command |
|-----------|---------|
| Re-audit from scratch | Paste this template again |
| Re-run gap analysis only | Ask Claude to re-run Phase 2 using existing `output/codebase_audit.md` |
| Resume implementation | `bash scripts/audits/{AUDIT_LABEL}/run_implementation.sh --session NN` |
| Re-validate only | `bash scripts/audits/{AUDIT_LABEL}/run_implementation.sh --validate NN` |
| Check progress | `bash scripts/audits/{AUDIT_LABEL}/run_implementation.sh --dashboard` |
| Full hands-free run | `NO_GATE=1 bash scripts/audits/{AUDIT_LABEL}/run_implementation.sh --all` |

---

## 4. Output Structure

After all phases complete, the audit directory will contain:

```
scripts/audits/{AUDIT_LABEL}/
  run_implementation.sh          # The generated implementation script
  prompts/
    .generated/                  # Session prompts (auto-generated)
    .passovers/                  # Session passovers (written by executors)
  logs/
    run.log                      # Execution log
    exec_NN.log                  # Per-session executor logs
    validate_NN.log              # Per-session validator logs
    pytest_session_NN.log        # Test logs
    .last_complete               # Last completed session number
  output/
    codebase_audit.md            # Phase 1 findings
    spec_reference.md            # Extracted spec requirements
    master_gap_analysis.md       # Phase 2 gaps
    decision_log.md              # Items needing human input
    RECONCILIATION_MATRIX.md     # Phase 3 tracking matrix
    FINAL_VALIDATION_REPORT.md   # Phase 5 final report
    ln-621--security.md          # Individual skill reports
    ln-624--quality.md
    ln-628--concurrency.md
    ln-629--lifecycle.md
    ln-625--dependencies.md
    ln-626--dead-code.md
```
