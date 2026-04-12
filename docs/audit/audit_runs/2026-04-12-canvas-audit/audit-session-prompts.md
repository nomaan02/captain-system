# Cross-Validation Audit — Session Prompts

Copy-paste each prompt into a fresh Claude Code session in ~/captain-system/

Audit directory: /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/

---

## SESSION 1 — Setup & Spec Manifest

```
Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to understand the full audit plan.

This is Phase 0: Setup. Your job is to extract a complete manifest of everything the specs define.

1. Read ~/obsidian-spec/_claude/SPEC_INDEX.md
2. Read all .md files in ~/obsidian-spec/System 1/Backend/
3. Extract and catalogue:
   - Every block (B1, B2, B3...) per component (command, offline, online)
   - Every program (PG-XX) with its name and which component it belongs to
   - Every data store (P3-DXX) with its description and which component reads/writes it
   - Every AIM module (AIM-01 through AIM-16) with its name
   - Every Python module filename referenced in the specs
   - Every Redis key pattern referenced
   - Every QuestDB table referenced

4. Write the complete manifest to /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/00-spec-manifest.md in a structured format that subsequent sessions can reference without needing to re-read the vault

5. Update ORCHESTRATOR.md Phase 0 status to ✅ DONE

Do NOT read any Captain codebase files in this session. Spec extraction only.
```

---

## SESSION 2 — P3-Command Audit

```
Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. Phase 0 must be ✅ DONE before proceeding.

This is Phase 1: P3-Command cross-validation.

1. Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/00-spec-manifest.md — extract only the P3-Command items (blocks, programs, data stores, modules)
2. Read the captain-command/ directory in the codebase — list all Python files, classes, functions, routes
3. For each spec item, find its implementation:
   - Block → corresponding module/function
   - PG-XX → corresponding function or class method
   - P3-DXX → corresponding Redis key or QuestDB query
   - Referenced .py filename → actual file in codebase

4. Produce a report in /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/01-command-audit.md with:
   - COVERAGE: X of Y spec items have matching code
   - IMPLEMENTED: spec items fully matching code (brief list)
   - DIVERGENT: spec items where code exists but differs (detail the mismatch)
   - MISSING: spec items with no code at all
   - UNSPECCED: code that exists with no spec coverage
   - For each DIVERGENT or MISSING item, note severity (critical/medium/low)

5. Update ORCHESTRATOR.md Phase 1 status to ✅ DONE

Do NOT make any code changes. Audit only.
```

---

## SESSION 3 — P3-Offline Audit

```
Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. Phases 0 and 1 must be ✅ DONE before proceeding.

This is Phase 2: P3-Offline cross-validation.

1. Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/00-spec-manifest.md — extract only the P3-Offline items (blocks B1-B9, programs, data stores, AIM modules)
2. Read the captain-offline/ directory in the codebase — list all Python files, classes, functions
3. For each spec item, find its implementation:
   - Block → corresponding module/function
   - PG-XX → corresponding function or class method
   - P3-DXX data store → corresponding Redis key or QuestDB query
   - AIM-XX → corresponding AIM implementation class/function
   - Referenced .py filename → actual file in codebase

4. Pay special attention to:
   - AIM registry completeness (all 16 AIMs + AIM-16 HMM)
   - Block execution order matching the spec pipeline
   - Pseudotrader implementation (B3 PG-09) matching doc 28

5. Produce a report in /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/02-offline-audit.md with same structure as 01-command-audit.md

6. Update ORCHESTRATOR.md Phase 2 status to ✅ DONE

Do NOT make any code changes. Audit only.
```

---

## SESSION 4 — P3-Online Audit

```
Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. Phases 0-2 must be ✅ DONE before proceeding.

This is Phase 3: P3-Online cross-validation.

1. Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/00-spec-manifest.md — extract only the P3-Online items (blocks B1-B9, programs, data stores, AIM modules, circuit breaker)
2. Read the captain-online/ directory in the codebase — list all Python files, classes, functions
3. For each spec item, find its implementation:
   - Block → corresponding module/function
   - PG-XX → corresponding function or class method
   - P3-DXX data store → corresponding Redis key or QuestDB query
   - AIM-XX → corresponding real-time AIM inference
   - Circuit breaker (CB) → implementation location and logic
   - Signal distribution (PG-25D) → matching doc 20

4. Pay special attention to:
   - Real-time vs batch boundaries (online should NOT duplicate offline work)
   - WebSocket/SignalR integration points
   - HMM regime detection (AIM-16) in the live pipeline
   - XGBoost classifier integration (doc 23)

5. Produce a report in /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/03-online-audit.md with same structure as previous audits

6. Update ORCHESTRATOR.md Phase 3 status to ✅ DONE

Do NOT make any code changes. Audit only.
```

---

## SESSION 5 — Data Layer Audit

```
Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. Phases 0-3 must be ✅ DONE before proceeding.

This is Phase 4: Data Layer cross-validation.

1. Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/00-spec-manifest.md — extract ALL data stores (P3-D00 through P3-D27), Redis key patterns, and QuestDB tables
2. Read the codebase across all three components for actual data access patterns:
   - Grep for all Redis key patterns (SET, GET, XADD, XREAD, PUBLISH, SUBSCRIBE)
   - Grep for all QuestDB queries (INSERT, SELECT, CREATE TABLE)
   - Grep for all file I/O paths

3. Cross-reference:
   - Every P3-DXX in the spec must have a matching storage implementation
   - Every Redis key in code must map to a spec-defined data store
   - Every QuestDB table in code must map to a spec-defined schema
   - Check data flow direction: which component writes vs reads each store (must match spec)
   - Check for data stores that are read but never written (dead references)
   - Check for data stores that are written but never read (orphaned data)

4. Also validate Docker Compose service boundaries:
   - Which services share which Redis streams/channels
   - Which services share QuestDB tables
   - Network isolation matches spec expectations

5. Produce a report in /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/04-data-layer-audit.md

6. Update ORCHESTRATOR.md Phase 4 status to ✅ DONE

Do NOT make any code changes. Audit only.
```

---

## SESSION 6 — Synthesis Report

```
Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. ALL phases 0-4 must be ✅ DONE before proceeding.

This is Phase 5: Synthesis. Combine all audit results into a single actionable report.

1. Read all audit files from /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/:
   - 00-spec-manifest.md
   - 01-command-audit.md
   - 02-offline-audit.md
   - 03-online-audit.md
   - 04-data-layer-audit.md

2. Produce /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/05-synthesis-report.md with:

   A. EXECUTIVE SUMMARY
   - Overall coverage percentage (spec items implemented / total spec items)
   - Per-component coverage (command, offline, online)
   - Data layer health score

   B. CRITICAL GAPS (must fix before go-live)
   - Missing implementations that block core functionality
   - Data layer mismatches that would cause runtime failures
   - Spec items marked critical that are MISSING or DIVERGENT

   C. DIVERGENCE LOG
   - Every place where code differs from spec, grouped by severity
   - For each: what the spec says, what the code does, recommended fix

   D. UNSPECCED CODE
   - Code that exists without spec coverage — is it needed? Experimental? Dead?

   E. PRIORITY ACTION PLAN
   - Ranked list of fixes, ordered by: critical gaps first, then data layer, then divergences
   - Estimated complexity per item (small/medium/large)
   - Suggested implementation order respecting dependencies

   F. SPEC FEEDBACK FOR ISAAC
   - Any spec ambiguities discovered during audit
   - Places where the spec may need updating based on implementation reality
   - Questions to resolve with Isaac before proceeding

3. Update ORCHESTRATOR.md Phase 5 status to ✅ DONE

Do NOT make any code changes. Audit only.
```
