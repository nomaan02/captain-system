# Coordinator-Executor Workflow Specification

**Origin:** AIM Reconciliation project, Captain System (March-April 2026)
**Scale:** 50 findings across 16 AIMs, resolved over 5 executor sessions spanning ~4 hours
**Result:** 32 FIXED, 1 VERIFIED, 9 CODE_AUTHORITATIVE, 8 DEFERRED, 95/95 tests passing

---

## 1. Workflow Overview

### What It Is

A dual-agent pattern where a human operates two Claude Code terminal sessions simultaneously:

- **Coordinator** — a persistent session that plans, tracks progress, and drafts handoff prompts
- **Executor** — a disposable session that receives a structured prompt, implements work, and updates a shared state file

The coordinator never touches code. The executor never plans beyond its current scope. A shared `.md` file on disk is the only communication channel between them.

### When to Use It

- The total work exceeds a single Claude Code context window (~200k tokens of useful context before compression degrades precision)
- The work is sequential and checkpoint-able — each unit can be validated before the next begins
- Decisions from the human gate progress (the human is the bridge between sessions)
- There is a spec-vs-implementation reconciliation, audit remediation, migration, or multi-step refactor

### Why It Works

Claude Code sessions are stateless between conversations. The shared `.md` file provides durable state that survives session boundaries. The coordinator retains strategic context (what decisions were made, why, what's left) while executors get fresh context windows focused entirely on implementation. This avoids the primary failure mode of long conversations: context compression losing critical details from early in the chat.

---

## 2. Architecture

```
┌─────────────────────┐          ┌──────────────────────┐
│   COORDINATOR        │          │    EXECUTOR           │
│   (Terminal 1)       │          │    (Terminal 2)       │
│                      │          │                       │
│  - Plans work        │          │  - Receives prompt    │
│  - Reads matrix      │  ┌────┐ │  - Implements changes │
│  - Drafts prompts    │◄─┤ .md├─►│  - Updates matrix     │
│  - Tracks progress   │  └────┘ │  - Runs tests         │
│  - Never writes code │          │  - Reports results    │
│                      │          │                       │
│  Persistent session  │          │  Disposable session   │
└─────────────────────┘          └──────────────────────┘
         ▲                                  ▲
         │            ┌──────┐              │
         └────────────┤ USER ├──────────────┘
                      └──────┘
                  Decision gate
                  Approval gate
                  Session lifecycle
```

**Communication flow:**
1. Coordinator reads the matrix, drafts a prompt
2. User copies the prompt to a new executor session
3. Executor implements, updates the matrix, reports results
4. User returns to coordinator, asks it to read updated matrix
5. Coordinator assesses progress, drafts next prompt
6. Repeat until complete

The user is the message bus. The `.md` file is the shared memory.

---

## 3. Coordinator Role

The coordinator is a strategic planner that never writes implementation code. Its responsibilities:

### Task Decomposition
- Read the audit/spec/requirements and decompose into individually-addressable findings
- Assign severity, categorize, identify dependencies between findings
- Group findings into phases with clear entry/exit criteria

### Decision Facilitation
- Identify decisions that require human input before implementation can proceed
- Present decisions with options, trade-offs, and a default recommendation
- Record decisions with rationale for future reference

### Session-Split Planning
- Estimate how many findings fit in a single executor session before context degrades
- Pre-plan the session boundaries based on logical groupings (not arbitrary counts)
- Front-load decisions to minimize blocking in later sessions

### Prompt Drafting
- Write self-contained prompts that give the executor everything it needs
- Include: what's done, what decisions were made, what to do, in what order, when to stop
- Reference the matrix file so the executor reads current state, not stale summaries

### Progress Tracking
- After each executor session completes, read the updated matrix
- Assess what's done, what's new (findings discovered during implementation), what shifted
- Adjust the remaining plan based on actual progress

### What the Coordinator Does NOT Do
- Write or edit implementation code
- Read source files for implementation detail (that's the executor's job)
- Make decisions on behalf of the human
- Assume previous executor context — always re-read the matrix

---

## 4. Executor Role

The executor is a focused implementer that receives a structured prompt and works within a single session. Its responsibilities:

### Receiving Context
- Read the shared state file in full at session start
- Understand what's done, what decisions apply, what to implement
- Verify pre-conditions (dependency findings resolved) before starting each item

### Implementation
- Work through the assigned items in the specified order
- Follow the exact values/logic from the resolved decisions — do not re-decide
- Stop after each item for human validation (the "checkpoint" pattern)

### Matrix Updates
- After implementing each fix: update finding row to FIXED, fill "Resolved By" with file:line
- After human approval: update to VERIFIED if applicable
- Update per-item dashboard cards, appendix tallies, and changelog
- If a fix reveals a NEW finding: add it to the matrix with full citation, flag for discussion

### Testing
- Run the test suite after every change
- Report exact test counts and any regressions
- Add new test cases where the matrix or prompt specifies them

### What the Executor Does NOT Do
- Plan future sessions or estimate remaining work
- Make architectural decisions without human input
- Skip the stop-and-validate checkpoint between items
- Modify the matrix's decision register (that's the coordinator's domain via human)

---

## 5. Shared State File

The `.md` file is the entire system's memory. Both agents read and write it. It must be self-contained — any agent reading it cold should understand the full project state.

### Template Structure

```markdown
# [Project] Reconciliation Matrix — Live Scoreboard

**Created:** [date]
**Source:** [audit report or requirements doc]
**Purpose:** Single source of truth for [what]. Update rows as work progresses.

---

# Section 1 — Finding-Level Matrix

Status Key:
- UNRESOLVED — confirmed, no decision made
- DECISION_NEEDED — requires human input (see Decision Register)
- SPEC_AUTHORITATIVE — spec wins, code must change
- CODE_AUTHORITATIVE — code wins, spec must be amended
- DEFERRED — intentionally deferred, not blocking
- FIXED — code or spec amended
- VERIFIED — fix confirmed by test or review

### F1.1 — [Finding title]

| Field | Value |
|-------|-------|
| Item(s) | [what's affected] |
| Category | [type of issue] |
| Spec Says | `file:line` — [verbatim quote] |
| Code Does | `file:line` — [verbatim quote] |
| Delta | [specific difference] |
| Resolution Status | [status] |
| Resolution Decision | [what was decided, or —] |
| Resolved By | [commit/file:line, or —] |
| Verified | [date, or —] |

[...repeat for all findings...]

---

# Section 2 — Per-Item Status Dashboard

### ITEM-XX: [Name]
- Overall Status: [BLOCKED | DIVERGED | ALIGNED | DEFERRED]
- Open Findings: [list of Finding IDs]
- Dependencies: [what must resolve first]
- Blocking: [what this blocks]

[...repeat for all items...]

---

# Section 3 — Resolution Dependency Graph

## Phase 0: Decisions (require human input)
[DAG of decisions → findings they unblock]

## Phase 1: Authority Resolutions
[pre-resolved items, no code changes needed]

## Phase 2: Code Corrections
[ordered implementation list with dependencies]

## Phase 3: Missing Specifications
[documentation/spec gaps]

## Phase 4: Verification
[test coverage gaps, edge cases]

---

# Section 4 — Decision Register

### DEC-01: [Decision Title] — [PENDING | RESOLVED]
- Findings affected: [list]
- Option A: [description + trade-offs]
- Option B: [description + trade-offs]
- Option C: [description + trade-offs]
- DEFAULT recommendation: [which option + why]
- Decision: [what was chosen, by whom, when]
- Impact: [what changes in the matrix]

---

# Appendix — Summary

| Status | Count |
|--------|-------|
| DECISION_NEEDED | X |
| UNRESOLVED | X |
| FIXED | X |
| VERIFIED | X |
| CODE_AUTHORITATIVE | X |
| DEFERRED | X |

**Changelog:**
- [date]: [what happened, which findings, test results]
```

### Key Design Principles

1. **Every claim has a file:line citation.** No summaries from memory — both agents verify by reading source.
2. **The changelog is the session resume point.** A new executor reads the last few changelog entries to know where to pick up.
3. **Tallies are always current.** After every matrix update, recount the status totals. A coordinator reading the file should see accurate numbers without re-counting.
4. **New findings get added during execution.** The matrix is a living document — if step 5 reveals something step 1 missed, add F6.x.

---

## 6. Session Splitting Logic

### Signals That a New Session Is Needed

1. **Phase boundary.** Phase 0 (decisions) is a natural split from Phase 2 (implementation). Don't mix planning and coding in one session.
2. **~4-6 implementation items per session.** In the AIM project, each AIM fix involved reading spec + code, modifying 1-2 files, adding ~10 test cases, updating the matrix. 4-6 of these consumed roughly 60-80% of useful context.
3. **Decision gates.** If the executor surfaces a new decision that requires human input, finish the current batch and split. Don't have the executor idle while waiting.
4. **Diminishing precision.** If the executor starts making errors on matrix updates (wrong tallies, forgetting to update dashboard cards), context is degrading — wrap up and split.

### Pre-Planned Splits (AIM Project)

| Session | Content | Rationale |
|---------|---------|-----------|
| 1 | Phase 0: 6 architectural decisions | Decisions are discussion, not code — lightweight context |
| 2 | Phase 2: 13 code corrections (AIM-04 through AIM-16) | Heavy implementation — one session with stop-validate checkpoints |
| 3 | Phase 2 deferred: F6.1-F6.5 | Small batch discovered during session 2 |
| 4 | Phase 3: specs + Phase 4: verification tests | Documentation + test writing — different cognitive mode than implementation |
| 5 | Verification sweep + deployment | Final validation pass |

Session 2 was the longest (~2.5 hours). In retrospect, splitting at AIM-08 (midpoint) would have been safer. The executor maintained precision throughout only because the stop-validate checkpoints forced it to re-read relevant matrix sections.

### Planning Splits in the Coordinator

When drafting the session plan, the coordinator should:
1. List ALL items in execution order
2. Estimate relative effort (quick fix vs refactor vs architectural change)
3. Draw split lines where: effort accumulates past ~60% context, OR a phase boundary occurs, OR a decision gate appears
4. Write each session's prompt before the first session starts (the coordinator has the full picture; prompts degrade if written session-by-session as context accumulates)

---

## 7. Handoff Protocol

### The Pickup Prompt Formula

Every executor prompt follows this structure:

```
1. ANCHOR: "Read [matrix file] in full."
2. CONTEXT: 2-3 sentences on what's already done (reference the matrix, don't re-explain)
3. DECISIONS: Bullet list of resolved decisions that affect this session's work
4. SCOPE: Numbered list of exactly what to implement, in order
5. PROTOCOL: How to work (stop-validate, matrix updates, test requirements)
6. ENTRY POINT: "Start with [specific item]."
```

### What Makes a Good Pickup Prompt

**Anchor to the file, not to conversation history.** The executor has no memory of prior sessions. The matrix file IS the memory. Every prompt starts with "Read the matrix."

**State decisions as facts, not discussions.** Don't say "we discussed whether to use z-scores and decided..." Say "DEC-01 resolved: spec authoritative (z-score thresholds). All handlers use z-scored inputs." The executor needs the conclusion, not the debate.

**Be explicit about execution order.** Number the items. Say which is first. The executor should never have to infer priority.

**Include the stop condition.** "After each AIM, STOP. Show the diff, test results, and proposed matrix updates. Wait for my approval." Without this, the executor will batch everything and you lose the checkpoint advantage.

**Reference specific file:line ranges.** "Read `b3_aim_aggregation.py:219-235` and implement the merged 5-zone structure" is better than "fix the IVTS thresholds." The executor shouldn't spend context searching for code the coordinator already located.

### Anti-Patterns

- **Re-explaining the full project** — the matrix has this; pointing to it is sufficient
- **Including decision rationale** — the executor doesn't need to know WHY, just WHAT was decided
- **Open-ended instructions** — "fix whatever seems wrong" gives the executor no stopping criteria
- **Assuming prior session context** — never reference "what we did last time" — reference the matrix changelog

---

## 8. What Worked

### The Matrix as Single Source of Truth
Every finding had one canonical location. No "I think we fixed that" — either the row says FIXED or it doesn't. The changelog told any agent exactly where the project stood. This eliminated the #1 failure mode of multi-session work: losing track of what's done.

### Stop-Validate-Update Checkpoints
Forcing the executor to stop after every AIM and present diff + tests + proposed matrix updates caught issues early. It also forced the executor to re-read the relevant matrix section, refreshing its context on what the correct behavior should be.

### Decision Gates Front-Loaded in Phase 0
All 6 architectural decisions were resolved before any code was written. This meant the executor sessions had zero blocking decisions — pure implementation. No "I need to ask the human and wait" interruptions mid-session.

### Phase-Based Splitting
Separating decisions (Phase 0), implementation (Phase 2), deferrals (Phase 2+), specs (Phase 3), and verification (Phase 4) into distinct sessions matched the cognitive mode of each phase. Decision-making uses different context than code-writing.

### Discovered Findings During Execution (F6.x Series)
The protocol for "if you find something new, add it to the matrix as F6.x and flag it" worked well. 5 new findings were discovered during Phase 2 and tracked properly. This prevented scope creep (they were deferred) while ensuring nothing was lost.

### Dual Warm-Up Gate Pattern
The most sophisticated decision (DEC-05) produced a dual-gate model that neither spec nor code had alone. This emerged because the coordinator presented both sides clearly and the human could see the synthesis. Single-session work tends to pick one source as "right" rather than finding the merge.

### The Coordinator Never Touching Code
Keeping the coordinator role purely strategic meant it never consumed context on implementation details. It could read the full matrix and reason about the project holistically, while executors burned their context on file reads and code edits.

---

## 9. What I'd Improve

### Session 2 Was Too Long
13 AIM corrections in a single executor session worked but was risky. The executor maintained precision because checkpoints forced re-reading, but at AIM-12 the changelog entries were getting slightly less detailed. A mid-session split at AIM-07 or AIM-08 would have been safer.

**Recommendation:** Cap executor sessions at 6-8 implementation items for code-heavy work.

### No Automated Matrix Validation
The matrix tallies (FIXED: 27, DEFERRED: 8, etc.) were manually maintained. Twice the executor updated the tallies incorrectly and had to be corrected. A simple script that parses the matrix and counts statuses would eliminate this.

**Recommendation:** Add a `scripts/validate_matrix.py` that reads the `.md` file, counts statuses, and flags discrepancies with the stated totals.

### Verification Was a Separate Pass
All 32 FIXED findings needed a verification sweep at the end. It would have been more efficient to verify each AIM immediately after fixing it, rather than batching verification into Phase 4.

**Recommendation:** Change the protocol to FIXED → VERIFIED within the same checkpoint, not in a separate phase. The executor already runs tests — adding a "confirm pseudocode matches code" step at each checkpoint is marginal cost.

### Coordinator Could Have Pre-Written All Prompts
The coordinator wrote each prompt after the previous session completed and the matrix was updated. But the session plan was largely predictable from Phase 0. Pre-writing all 5 prompts (with placeholders for decision outcomes) would have reduced coordinator overhead.

**Recommendation:** After Phase 0 decisions resolve, the coordinator should draft ALL remaining prompts in one batch, stored as `.workflows/session_N_prompt.md` files. Each references the matrix for current state but has the structure pre-built.

### Matrix File Grew Large
By the end, the matrix was ~1350 lines. Executors reading it in full consumed significant context. The changelog alone was ~40 entries. Future projects should consider separating the changelog into its own file, or archiving resolved findings.

**Recommendation:** After a phase completes, collapse resolved findings into a summary section and move detailed rows to an archive file. Keep only UNRESOLVED/DEFERRED/IN-PROGRESS in the active matrix.

---

## 10. Step-by-Step Reproduction Guide

### Prerequisites
- Two terminal sessions with Claude Code access
- A codebase with an identifiable set of issues to resolve (audit report, migration checklist, spec/implementation gap analysis)

### Step 1: Produce the Audit

In Terminal 1 (future coordinator), have Claude Code analyze the codebase and produce a findings report. This is the raw material.

```
Prompt: "Read [spec files] and [implementation files]. Produce an audit report 
documenting every discrepancy between spec and implementation. For each finding: 
ID, severity, what spec says (with file:line), what code does (with file:line), 
the delta. Save to docs/[PROJECT]_Audit_Report.md"
```

### Step 2: Build the Matrix

In Terminal 1, have Claude Code transform the audit into the shared state file.

```
Prompt: "Read docs/[PROJECT]_Audit_Report.md. Build a reconciliation matrix at 
plans/[PROJECT]_RECONCILIATION_MATRIX.md with these sections:
1. Finding-level matrix (every finding with Spec Says / Code Does / Delta / Status)
2. Per-item status dashboard
3. Resolution dependency graph (which findings block which)
4. Decision register (decisions requiring human input, with options and recommendations)

Pre-populate by reading the actual source files — verify every file:line citation. 
Do NOT copy from the audit summary alone. Do NOT propose code changes."
```

### Step 3: Resolve Decisions (Session 1)

Terminal 1 becomes the coordinator. Open Terminal 2 as the first executor.

```
Coordinator drafts → Executor prompt for Phase 0:
"Read [matrix file]. Present decisions DEC-01 through DEC-N one at a time. 
For each: state the options, trade-offs, and recommendation. Wait for my input. 
After each decision, update the matrix: change finding statuses, fill Resolution 
Decision, cascade to downstream findings. Start with DEC-01."
```

User copies this prompt to Terminal 2. Works through all decisions. Matrix gets updated on disk.

### Step 4: Plan Execution Sessions

Back in Terminal 1, the coordinator reads the updated matrix and plans the implementation sessions.

```
Prompt to coordinator: "Read [matrix file] to see the resolved decisions. 
Draft me the executor prompt for Phase 2 implementation."
```

The coordinator produces a prompt with:
- Resolved decision summary (bullet points, not full discussion)
- Numbered execution order from the matrix's Phase 2 section
- Stop-validate protocol
- Matrix upkeep rules
- Entry point

### Step 5: Execute Implementation (Sessions 2-N)

For each executor session:
1. User opens a fresh Terminal 2 session
2. User pastes the coordinator-drafted prompt
3. Executor reads matrix, implements items, stops at checkpoints
4. User approves at each checkpoint
5. Executor updates matrix
6. When session scope is complete, user returns to Terminal 1

### Step 6: Handle Discovered Findings

If the executor finds new issues during implementation:
1. Executor adds F(N+1).x to the matrix with full citation
2. Executor flags it: "New finding — implement now or defer?"
3. User decides (often: defer to end of current phase)
4. Coordinator picks these up when drafting the next session's prompt

### Step 7: Iterate Until Complete

After each executor session:
1. Return to coordinator (Terminal 1)
2. Ask it to read the updated matrix
3. Coordinator assesses: what's done, what's new, what's next
4. Coordinator drafts the next executor prompt
5. Repeat

### Step 8: Verification Sweep

Final executor session:
1. Read matrix, walk through all FIXED findings
2. Confirm implementation matches spec/pseudocode
3. Run full test suite
4. Promote FIXED → VERIFIED
5. Update final tallies

### Step 9: Archive

Update the matrix with a final summary section. The completed matrix serves as the permanent record of what was found, what was decided, what was changed, and why.

---

## Appendix: Quick Reference

### Coordinator Commands
```
"Read [matrix file] and draft me the next executor prompt"
"Read [matrix file] — where do we stand?"
"Read [matrix file] — what's left after this session?"
```

### Executor Prompt Template
```
Read [matrix file] in full. [Phase X] is complete. [Summary of resolved decisions].

You are executing [Phase Y]. Items in order:
1. [Item] (Finding IDs) — [brief description]
2. ...

Rules:
- ONE ITEM AT A TIME. After each: show diff, test results, proposed matrix updates.
- Wait for my approval before proceeding.
- Update matrix after each approval: finding → FIXED, dashboard card, tallies, changelog.
- If you discover a new issue: add as F(N+1).x, flag it, do not fix without approval.

Start with item 1.
```

### Matrix Status Lifecycle
```
UNRESOLVED → DECISION_NEEDED → SPEC/CODE_AUTHORITATIVE → FIXED → VERIFIED
                                                    └→ DEFERRED (with justification)
```
