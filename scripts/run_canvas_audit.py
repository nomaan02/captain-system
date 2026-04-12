#!/usr/bin/env python3
"""
Canvas Cross-Validation Audit Runner
=====================================
Runs Sessions 2-6 of the spec-vs-code audit sequentially via Claude Code CLI.
Each session runs in Opus 4.6 / max effort / permissions bypassed.

Usage:
    python3 scripts/run_canvas_audit.py

Session 1 (Phase 0: Setup) was already completed manually.
"""

import subprocess
import sys
import signal
from pathlib import Path
from datetime import datetime

AUDIT_DIR = Path("/home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit")
PROJECT_DIR = Path("/home/nomaan/captain-system")

# ─── Session definitions ────────────────────────────────────────────────────

SESSIONS = [
    # ── Session 2: P3-Command ──────────────────────────────────────────────
    {
        "num": 2,
        "phase": 1,
        "name": "P3-Command",
        "output": "01-command-audit.md",
        "prompt": r"""Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. Phase 0 must be DONE before proceeding.

This is Phase 1: P3-Command cross-validation.

1. Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/00-spec-manifest.md -- extract only the P3-Command items (blocks, programs, data stores, modules)
2. Read the captain-command/ directory in the codebase -- list all Python files, classes, functions, routes
3. For each spec item, find its implementation:
   - Block -> corresponding module/function
   - PG-XX -> corresponding function or class method
   - P3-DXX -> corresponding Redis key or QuestDB query
   - Referenced .py filename -> actual file in codebase

4. Produce a report in /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/01-command-audit.md with:
   - COVERAGE: X of Y spec items have matching code
   - IMPLEMENTED: spec items fully matching code (brief list)
   - DIVERGENT: spec items where code exists but differs (detail the mismatch)
   - MISSING: spec items with no code at all
   - UNSPECCED: code that exists with no spec coverage
   - For each DIVERGENT or MISSING item, note severity (critical/medium/low)

5. Update ORCHESTRATOR.md Phase 1 status to DONE (change TODO to DONE with checkmark)

6. Append a session log entry to the Session Log section at the end of ORCHESTRATOR.md:
   ### Session 2 -- Phase 1: P3-Command (DONE)
   - **Completed:** [current date and time]
   - **Output:** `01-command-audit.md`
   - **Summary:** [2-3 sentence summary of key findings]
   - **Counts:** [X implemented, Y divergent, Z missing, W unspecced]

Do NOT make any code changes. Audit only.""",
    },
    # ── Session 3: P3-Offline ──────────────────────────────────────────────
    {
        "num": 3,
        "phase": 2,
        "name": "P3-Offline",
        "output": "02-offline-audit.md",
        "prompt": r"""Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. Phases 0 and 1 must be DONE before proceeding.

This is Phase 2: P3-Offline cross-validation.

1. Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/00-spec-manifest.md -- extract only the P3-Offline items (blocks B1-B9, programs, data stores, AIM modules)
2. Read the captain-offline/ directory in the codebase -- list all Python files, classes, functions
3. For each spec item, find its implementation:
   - Block -> corresponding module/function
   - PG-XX -> corresponding function or class method
   - P3-DXX data store -> corresponding Redis key or QuestDB query
   - AIM-XX -> corresponding AIM implementation class/function
   - Referenced .py filename -> actual file in codebase

4. Pay special attention to:
   - AIM registry completeness (all 16 AIMs + AIM-16 HMM)
   - Block execution order matching the spec pipeline
   - Pseudotrader implementation (B3 PG-09) matching doc 28
   - DMA/MoE meta-learning pipeline fidelity
   - Kelly EWMA and beta_b estimator (B8) accuracy

5. Produce a report in /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/02-offline-audit.md with same structure as 01-command-audit.md (COVERAGE, IMPLEMENTED, DIVERGENT, MISSING, UNSPECCED with severity)

6. Update ORCHESTRATOR.md Phase 2 status to DONE (change TODO to DONE with checkmark)

7. Append a session log entry to the Session Log section at the end of ORCHESTRATOR.md:
   ### Session 3 -- Phase 2: P3-Offline (DONE)
   - **Completed:** [current date and time]
   - **Output:** `02-offline-audit.md`
   - **Summary:** [2-3 sentence summary of key findings]
   - **Counts:** [X implemented, Y divergent, Z missing, W unspecced]

Do NOT make any code changes. Audit only.""",
    },
    # ── Session 4: P3-Online ───────────────────────────────────────────────
    {
        "num": 4,
        "phase": 3,
        "name": "P3-Online",
        "output": "03-online-audit.md",
        "prompt": r"""Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. Phases 0-2 must be DONE before proceeding.

This is Phase 3: P3-Online cross-validation.

1. Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/00-spec-manifest.md -- extract only the P3-Online items (blocks B1-B9, programs, data stores, AIM modules, circuit breaker)
2. Read the captain-online/ directory in the codebase -- list all Python files, classes, functions
3. For each spec item, find its implementation:
   - Block -> corresponding module/function
   - PG-XX -> corresponding function or class method
   - P3-DXX data store -> corresponding Redis key or QuestDB query
   - AIM-XX -> corresponding real-time AIM inference
   - Circuit breaker (CB) -> implementation location and logic for all 5 layers (L0-L4)
   - Signal distribution (PG-25D) -> matching doc 20 6-step pipeline
   - Kelly 7-layer sizing -> each layer L1-L7 implemented correctly

4. Pay special attention to:
   - Real-time vs batch boundaries (online should NOT duplicate offline work)
   - WebSocket/SignalR integration points
   - HMM regime detection (AIM-16) in the live pipeline
   - XGBoost classifier integration (doc 23)
   - Circuit breaker layer ordering and condition logic
   - Shared (B1-B3) vs per-user (B4-B9) split

5. Produce a report in /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/03-online-audit.md with same structure as previous audits (COVERAGE, IMPLEMENTED, DIVERGENT, MISSING, UNSPECCED with severity)

6. Update ORCHESTRATOR.md Phase 3 status to DONE (change TODO to DONE with checkmark)

7. Append a session log entry to the Session Log section at the end of ORCHESTRATOR.md:
   ### Session 4 -- Phase 3: P3-Online (DONE)
   - **Completed:** [current date and time]
   - **Output:** `03-online-audit.md`
   - **Summary:** [2-3 sentence summary of key findings]
   - **Counts:** [X implemented, Y divergent, Z missing, W unspecced]

Do NOT make any code changes. Audit only.""",
    },
    # ── Session 5: Data Layer ──────────────────────────────────────────────
    {
        "num": 5,
        "phase": 4,
        "name": "Data Layer",
        "output": "04-data-layer-audit.md",
        "prompt": r"""Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. Phases 0-3 must be DONE before proceeding.

This is Phase 4: Data Layer cross-validation.

1. Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/00-spec-manifest.md -- extract ALL data stores (P3-D00 through P3-D27), Redis key patterns, and QuestDB tables
2. Read the codebase across all three components for actual data access patterns:
   - Grep for all Redis key patterns (SET, GET, XADD, XREAD, PUBLISH, SUBSCRIBE, hset, hget, hgetall)
   - Grep for all QuestDB queries (INSERT, SELECT, CREATE TABLE)
   - Grep for all file I/O paths (open, json.load, joblib.load, torch.load)
   - Also check shared/ directory (redis_client.py, questdb_client.py) for connection patterns

3. Cross-reference:
   - Every P3-DXX in the spec must have a matching storage implementation
   - Every Redis key in code must map to a spec-defined data store
   - Every QuestDB table in code must map to a spec-defined schema
   - Check data flow direction: which component writes vs reads each store (must match spec)
   - Check for data stores that are read but never written (dead references)
   - Check for data stores that are written but never read (orphaned data)
   - Check the 6 feedback loops from the manifest: does data actually flow through each loop?

4. Also validate Docker Compose service boundaries:
   - Read docker-compose.yml and docker-compose.local.yml
   - Which services share which Redis streams/channels
   - Which services share QuestDB tables
   - Network isolation matches spec expectations

5. Produce a report in /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/04-data-layer-audit.md with:
   - DATA STORE COVERAGE: X of Y spec data stores have matching code
   - REDIS KEY AUDIT: spec keys vs code keys (matched, missing, extra)
   - QUESTDB TABLE AUDIT: spec tables vs code tables (matched, missing, extra)
   - FEEDBACK LOOP VALIDATION: each of 6 loops traced end-to-end
   - DOCKER BOUNDARY CHECK: isolation correctness
   - ORPHANED/DEAD references

6. Update ORCHESTRATOR.md Phase 4 status to DONE (change TODO to DONE with checkmark)

7. Append a session log entry to the Session Log section at the end of ORCHESTRATOR.md:
   ### Session 5 -- Phase 4: Data Layer (DONE)
   - **Completed:** [current date and time]
   - **Output:** `04-data-layer-audit.md`
   - **Summary:** [2-3 sentence summary of key findings]
   - **Counts:** [X data stores matched, Y Redis keys matched, Z QuestDB tables matched, W feedback loops validated]

Do NOT make any code changes. Audit only.""",
    },
    # ── Session 6: Synthesis ───────────────────────────────────────────────
    {
        "num": 6,
        "phase": 5,
        "name": "Synthesis",
        "output": "05-synthesis-report.md",
        "prompt": r"""Read /home/nomaan/captain-system/docs/audit/audit_runs/2026-04-12-canvas-audit/ORCHESTRATOR.md to check status. ALL phases 0-4 must be DONE before proceeding.

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
   - Code that exists without spec coverage -- is it needed? Experimental? Dead?

   E. PRIORITY ACTION PLAN
   - Ranked list of fixes, ordered by: critical gaps first, then data layer, then divergences
   - Estimated complexity per item (small/medium/large)
   - Suggested implementation order respecting dependencies

   F. SPEC FEEDBACK FOR ISAAC
   - Any spec ambiguities discovered during audit
   - Places where the spec may need updating based on implementation reality
   - Questions to resolve with Isaac before proceeding

3. Update ORCHESTRATOR.md Phase 5 status to DONE (change TODO to DONE with checkmark)

4. Append a session log entry to the Session Log section at the end of ORCHESTRATOR.md:
   ### Session 6 -- Phase 5: Synthesis (DONE)
   - **Completed:** [current date and time]
   - **Output:** `05-synthesis-report.md`
   - **Summary:** [2-3 sentence summary: overall coverage, critical gap count, top priority]
   - **Counts:** [Overall: X% coverage. Critical gaps: Y. Divergences: Z. Unspecced: W.]
   - **AUDIT COMPLETE**

Do NOT make any code changes. Audit only.""",
    },
]

# ─── Runner ─────────────────────────────────────────────────────────────────


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def check_prereqs():
    """Verify Phase 0 output exists before starting."""
    manifest = AUDIT_DIR / "00-spec-manifest.md"
    if not manifest.exists():
        log(f"FATAL: Phase 0 output missing: {manifest}")
        log("Run Session 1 manually first.")
        sys.exit(1)
    log(f"Phase 0 manifest found ({manifest.stat().st_size:,} bytes)")


def run_session(session):
    num = session["num"]
    start = datetime.now()

    log("=" * 70)
    log(f"  SESSION {num} | Phase {session['phase']}: {session['name']}")
    log(f"  Expected output: {session['output']}")
    log("=" * 70)

    cmd = [
        "claude",
        "-p",
        "--model", "claude-opus-4-6",
        "--effort", "max",
        "--dangerously-skip-permissions",
        "--name", f"canvas-audit-s{num}",
    ]

    proc = subprocess.run(
        cmd,
        input=session["prompt"],
        text=True,
        cwd=str(PROJECT_DIR),
    )

    elapsed = datetime.now() - start
    mins = int(elapsed.total_seconds() // 60)
    secs = int(elapsed.total_seconds() % 60)
    output_path = AUDIT_DIR / session["output"]

    if output_path.exists() and output_path.stat().st_size > 100:
        size = output_path.stat().st_size
        log(f"  SESSION {num} COMPLETE ({mins}m {secs}s) | {size:,} bytes written")
        return True
    else:
        log(f"  SESSION {num} FAILED — output file missing or empty!")
        log(f"  Expected: {output_path}")
        log(f"  Exit code: {proc.returncode}")
        log(f"  Elapsed: {mins}m {secs}s")
        log("")
        log("Stopping. Check the session output above for errors.")
        return False


def main():
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda s, f: (log("\nInterrupted by user."), sys.exit(130)))

    # Parse --from N to skip earlier sessions
    start_session = 2
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--from" and i < len(sys.argv) - 1:
            start_session = int(sys.argv[i + 1])
        elif arg.startswith("--from="):
            start_session = int(arg.split("=", 1)[1])

    sessions_to_run = [s for s in SESSIONS if s["num"] >= start_session]
    if not sessions_to_run:
        log(f"No sessions >= {start_session}. Valid range: 2-6.")
        sys.exit(1)

    print()
    log("Canvas Cross-Validation Audit Runner")
    log(f"Audit dir: {AUDIT_DIR}")
    log(f"Model: claude-opus-4-6 | Effort: max")
    log(f"Sessions to run: {sessions_to_run[0]['num']} -> {sessions_to_run[-1]['num']} ({len(sessions_to_run)} session(s))")
    print()

    check_prereqs()

    total_start = datetime.now()

    for session in sessions_to_run:
        print()
        success = run_session(session)
        if not success:
            sys.exit(1)

    total_elapsed = datetime.now() - total_start
    total_mins = int(total_elapsed.total_seconds() // 60)

    print()
    log("=" * 70)
    log(f"  ALL 5 SESSIONS COMPLETE ({total_mins} min total)")
    log(f"  Audit reports: {AUDIT_DIR}")
    log(f"  Final report:  {AUDIT_DIR}/05-synthesis-report.md")
    log("=" * 70)


if __name__ == "__main__":
    main()
