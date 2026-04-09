# Final Validation — Captain System Implementation Audit

You are performing the **final validation sweep** after all implementation sessions are complete.

## Read These Files

1. `docs/audit/validation_progress_log.md` — all validation cycle results
2. `docs/audit/master_gap_analysis.md` — original 100 gaps
3. `plans/CAPTAIN_RECONCILIATION_MATRIX.md` — final matrix state
4. `docs/audit/spec_reference.md` — authoritative spec (13 sections)

## Task 1: Produce Final Validation Report

Create `docs/audit/FINAL_VALIDATION_REPORT.md` with:

### §1 — Per-Gap Status Table

| Gap ID | Severity | Component | Final Status | Validation Ref | Spec Alignment | Notes |
|--------|----------|-----------|--------------|----------------|----------------|-------|
| G-001  | CRITICAL | Offline B8 | RESOLVED/PARTIAL/UNRESOLVED/DEFERRED | Cycle N | §6 | ... |

For EVERY gap (G-001 through G-100):
- **RESOLVED** — code now matches spec; validated by Agent B
- **PARTIAL** — partially addressed; document remaining delta
- **UNRESOLVED** — not fixed or fix reverted
- **DEFERRED** — intentionally deferred (LOW severity or blocked by decision)

### §2 — Summary Statistics

| Metric | Count |
|--------|-------|
| Total gaps | 100 |
| Fully resolved | N |
| Partially resolved | N |
| Deferred (LOW) | 33 |
| Unresolved | N |

### §3 — Per-Component Compliance

| Component | Requirements | Met | Partial | Unmet | Compliance % |
|-----------|-------------|-----|---------|-------|-------------|
| Online Pipeline | N | N | N | N | N% |
| Offline Pipeline | N | N | N | N | N% |
| Command Pipeline | N | N | N | N | N% |
| Cross-Cutting | N | N | N | N | N% |
| QuestDB/Schema | N | N | N | N | N% |
| AIM System | N | N | N | N | N% |
| Kelly/CB | N | N | N | N | N% |
| Security | N | N | N | N | N% |

### §4 — Decision Register Final State

For each DEC-01 through DEC-10: resolution, implementation status, and any remaining risk.

### §5 — Risk Assessment

Document any remaining risks that need monitoring:
- Unresolved CRITICAL/HIGH gaps
- PARTIAL fixes with known limitations
- Deferred items that may need attention before live trading

## Task 2: Run Full Audit Suite

Execute these audit skills against the completed codebase:

1. `/ln-620-codebase-auditor` — full structural audit vs Phase 1 baseline
2. `/ln-621-security-auditor` — security posture after hardening
3. `/ln-630-test-auditor` — test coverage assessment
4. `/ln-628-concurrency-auditor` — thread safety after concurrency fixes
5. `/ln-625-dependencies-auditor` — dependency health
6. `/ln-626-dead-code-auditor` — dead code after cleanup
7. `/ln-629-lifecycle-auditor` — startup/shutdown compliance
8. `/ln-614-docs-fact-checker` — table names and constants final check

Append results summary to the report under:

### §6 — Final Audit Skill Results

| Skill | Scope | Key Findings | Status |
|-------|-------|-------------|--------|
| ln-620 | Full codebase | ... | PASS/WARN/FAIL |

## Rules
1. Read every file referenced — do not rely on memory
2. Compare against spec_reference.md for every gap
3. Be honest about PARTIAL — do not upgrade to RESOLVED without evidence
4. Flag any NEW issues discovered during the sweep
