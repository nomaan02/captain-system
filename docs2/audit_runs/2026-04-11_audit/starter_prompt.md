/mem-search

Gap Analysis Orchestrator — Captain System vs Obsidian Spec
Create ~/captain-system/docs/audit/audit_runs/2026-04-11_audit/ORCHESTRATOR.md as the session controller for this multi-session audit. Then execute Session 1 only.
Structure ORCHESTRATOR.md with the following sessions. Each session ends with a checkpoint commit and a summary written to ORCHESTRATOR.md under that session's heading so the next session has full context without needing memory.

Session 1 — Index & Scaffold (run now)

Create directory structure: 2026-04-11_audit/ with findings/, validation/, amendments/
Run git log --since="2025-04-09" --until="2025-04-11" --oneline --stat to capture every file changed in the April 9-10 audit
Run mem-search for context on what was done and why
Write the full file index (files touched, components affected, what changed) into ORCHESTRATOR.md under ## Session 1 — Index
Create GAP_ANALYSIS.md with sections per program (P3-Offline, P3-Online, P3-Command), status columns: [GAP], [VALID], [AMENDED], [BLOCKED]
Commit: "audit: session 1 — scaffold and index"
STOP. Print the prompt for Session 2.

Session 2 — Spec Extraction

Read ORCHESTRATOR.md Session 1 output for the file index
Use mcp-obsidian to search vault by tags: #P3-offline, #P3-online, #P3-command
For each tagged doc: read full content, follow wikilinks to referenced data stores (doc 24 schemas), pseudocode docs, AIM definitions
Write a consolidated spec summary per component into ORCHESTRATOR.md under ## Session 2 — Spec Map
Map each spec requirement to the corresponding code file(s) from the Session 1 index
Commit: "audit: session 2 — spec extraction and mapping"
STOP. Print the prompt for Session 3.

Session 3 — P3-Offline Audit

Read ORCHESTRATOR.md Sessions 1-2 for index and spec map
Audit every P3-Offline component: compare spec requirements against code implementation
For each finding, create {component}_{type}.md in the appropriate subdirectory (findings/, validation/, amendments/)
Each file: spec reference (doc + section), code file + line range, status, description, severity (critical/moderate/minor)
Update GAP_ANALYSIS.md P3-Offline section
Commit: "audit: session 3 — P3-Offline audit complete"
STOP. Print the prompt for Session 4.

Session 4 — P3-Online Audit

Same pattern as Session 3 for all P3-Online components
Include all AIM validations (AIMs 1-16), WebSocket handlers, data flow paths
Update GAP_ANALYSIS.md P3-Online section
Commit: "audit: session 4 — P3-Online audit complete"
STOP. Print the prompt for Session 5.

Session 5 — P3-Command Audit

Same pattern as Session 3 for all P3-Command components (FastAPI routes, Telegram, GUI integration points)
Update GAP_ANALYSIS.md P3-Command section
Commit: "audit: session 5 — P3-Command audit complete"
STOP. Print the prompt for Session 6.

Session 6 — Cross-Verification & Verdict

Read full GAP_ANALYSIS.md and all finding files
Verify April 9-10 amendments haven't introduced regressions
Run a grep pass for any unaudited files in the codebase that should have been checked
Write final rollup in GAP_ANALYSIS.md: total gaps, total validated, total amendments, READY / NOT READY per program
List all [BLOCKED] items requiring Isaac's input
Commit: "audit: session 6 — final verdict"
STOP. Print summary to terminal.

Constraints across all sessions:

Obsidian vault is the single source of truth — if code contradicts spec, code is wrong
Do not modify any source code — findings only
Every session must read ORCHESTRATOR.md first for prior session context
Every session must write its output back to ORCHESTRATOR.md before stopping
Every session ends with a git commit before printing the next prompt