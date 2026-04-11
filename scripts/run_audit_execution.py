#!/usr/bin/env python3
"""
Captain System — Audit Execution Runner
========================================

Automated execution of gap-analysis fix sessions from EXECUTION_ORCHESTRATOR.md.
Each session runs as an independent Claude Code CLI invocation (Opus 4.6, MAX effort).

Supports two execution strategies:

  SEQUENTIAL (default)  — sessions run one after another on the current branch.
                          Simpler, no merge conflicts. 19 sessions wall time.

  PARALLEL (--parallel) — independent phases run simultaneously in git worktrees.
                          5 waves, ~11 sessions wall time (~42% faster).
                          Auto-merges worktrees after each wave.

State is checkpointed after every session. Resumable from any failure point.
Each session produces its own execution log .md file.

Usage
-----
    python3 scripts/run_audit_execution.py                  # Sequential, all pending
    python3 scripts/run_audit_execution.py --parallel       # Parallel waves
    python3 scripts/run_audit_execution.py --from 2.1       # Resume from session 2.1
    python3 scripts/run_audit_execution.py --only 3.1       # Run single session
    python3 scripts/run_audit_execution.py --status         # Show progress
    python3 scripts/run_audit_execution.py --dry-run        # Preview execution plan
    python3 scripts/run_audit_execution.py --unattended     # Auto-approve all tool calls
    python3 scripts/run_audit_execution.py --reset 2.1      # Reset a failed session

Environment
-----------
    ANTHROPIC_API_KEY    Must be set (or claude auth must be configured)
    CLAUDE_MODEL         Override model (default: opus)
    AUDIT_TIMEOUT        Per-session timeout in seconds (default: 1800 = 30min)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT / "docs" / "audit" / "audit_runs" / "2026-04-11_audit"
ORCHESTRATOR = AUDIT_DIR / "EXECUTION_ORCHESTRATOR.md"
LOGS_DIR = AUDIT_DIR / "execution_logs"
STATE_FILE = LOGS_DIR / "execution_state.json"
WORKTREE_DIR = ROOT / ".audit-worktrees"

# ── Session Definitions ─────────────────────────────────────────────────────

SESSION_ORDER = [
    "0.1",
    "1.1", "1.2", "1.3",
    "2.1", "2.2",
    "3.1", "3.2",
    "4.1", "4.2",
    "5.1", "5.2", "5.3",
    "6.1", "6.2",
    "7.1", "7.2",
    "8.1", "8.2",
]

SESSION_META = {
    "0.1": {"title": "Kelly L4 Formula Fix + GUI WebSocket Sanitization",       "phase": 0, "criticals": ["G-ONL-017", "G-ONL-028", "G-XCT-015"]},
    "1.1": {"title": "Pseudotrader Orchestrator Integration",                   "phase": 1, "criticals": ["G-OFF-015"]},
    "1.2": {"title": "Signal Replay Integration",                               "phase": 1, "criticals": ["G-OFF-016"]},
    "1.3": {"title": "Account-Aware Replay + Depth Fixes",                      "phase": 1, "criticals": []},
    "2.1": {"title": "Fill Slippage Monitor",                                   "phase": 2, "criticals": ["G-ONL-042"]},
    "2.2": {"title": "Data Feed Monitoring + Balance Incident",                 "phase": 2, "criticals": ["G-CMD-003", "G-CMD-004"]},
    "3.1": {"title": "Crash Recovery Branching",                                "phase": 3, "criticals": ["G-XCT-012"]},
    "3.2": {"title": "Shared Module Reliability",                               "phase": 3, "criticals": []},
    "4.1": {"title": "Sensitivity Fix + RPT-12",                                "phase": 4, "criticals": ["G-OFF-029", "G-CMD-002"]},
    "4.2": {"title": "Version Rollback",                                        "phase": 4, "criticals": ["G-OFF-046"]},
    "5.1": {"title": "Offline B1 AIM Block Fixes",                              "phase": 5, "criticals": []},
    "5.2": {"title": "Offline B2 Decay Detection Fixes",                        "phase": 5, "criticals": []},
    "5.3": {"title": "Offline B7-B9 Kelly/CB/Diagnostic Fixes",                 "phase": 5, "criticals": []},
    "6.1": {"title": "Online Sizing Pipeline Fixes",                            "phase": 6, "criticals": []},
    "6.2": {"title": "Online Circuit Breaker + Signal Output Fixes",            "phase": 6, "criticals": []},
    "7.1": {"title": "Command Notifications + Incidents Fixes",                 "phase": 7, "criticals": []},
    "7.2": {"title": "Command Compliance + API Fixes",                          "phase": 7, "criticals": []},
    "8.1": {"title": "Timezone + Heartbeat Cross-Cutting Sweep",                "phase": 8, "criticals": []},
    "8.2": {"title": "Primary User + LATEST ON Cross-Cutting Sweep",            "phase": 8, "criticals": []},
}

DEPENDENCIES = {
    "0.1": [],
    "1.1": [],
    "1.2": ["1.1"],
    "1.3": ["1.1", "1.2"],
    "2.1": [],
    "2.2": ["2.1"],
    "3.1": [],
    "3.2": ["3.1"],
    "4.1": ["0.1"],
    "4.2": ["1.1", "1.2", "1.3"],
    "5.1": ["1.1", "1.2", "1.3"],
    "5.2": [],
    "5.3": [],
    "6.1": ["0.1"],
    "6.2": [],
    "7.1": ["2.1", "2.2"],
    "7.2": [],
    "8.1": ["5.1", "5.2", "5.3", "6.1", "6.2", "7.1", "7.2"],
    "8.2": [],
}

# Findings resolved per session (from each passover prompt's "When Done" section)
SESSION_FINDINGS = {
    "0.1": ["G-ONL-017", "G-ONL-028", "G-XCT-015"],
    "1.1": ["G-OFF-015"],
    "1.2": ["G-OFF-016", "G-OFF-024"],
    "1.3": ["G-OFF-019", "G-OFF-020", "G-OFF-021", "G-OFF-022", "G-OFF-023"],
    "2.1": ["G-ONL-042", "G-ONL-043", "G-ONL-044"],
    "2.2": ["G-CMD-003", "G-CMD-004", "G-CMD-016", "G-CMD-017", "G-CMD-043"],
    "3.1": ["G-XCT-012", "G-SHR-018"],
    "3.2": ["G-SHR-002", "G-SHR-003", "G-SHR-004", "G-SHR-012", "G-SHR-015", "G-SHR-019", "G-SHR-020"],
    "4.1": ["G-OFF-029", "G-OFF-030", "G-CMD-002"],
    "4.2": ["G-OFF-046", "G-OFF-047", "G-OFF-048"],
    "5.1": ["G-OFF-002", "G-OFF-003", "G-OFF-004", "G-OFF-025", "G-OFF-032"],
    "5.2": ["G-OFF-009", "G-OFF-010", "G-OFF-011", "G-OFF-049"],
    "5.3": ["G-OFF-039", "G-OFF-040", "G-OFF-041", "G-OFF-033", "G-OFF-017", "G-OFF-018"],
    "6.1": ["G-ONL-004", "G-ONL-005", "G-ONL-006", "G-ONL-018", "G-ONL-019", "G-ONL-021", "G-ONL-013"],
    "6.2": ["G-ONL-024", "G-ONL-025", "G-ONL-029", "G-ONL-030", "G-ONL-032", "G-ONL-036", "G-ONL-048"],
    "7.1": ["G-CMD-010", "G-CMD-011", "G-CMD-012", "G-CMD-014", "G-CMD-015", "G-CMD-008", "G-CMD-013"],
    "7.2": ["G-CMD-009", "G-CMD-018", "G-CMD-019", "G-CMD-005", "G-CMD-006", "G-CMD-007", "G-CMD-016", "G-CMD-017"],
    "8.1": ["G-XCT-001", "G-XCT-002", "G-XCT-003", "G-XCT-004", "G-XCT-005", "G-XCT-006"],
    "8.2": ["G-XCT-007", "G-XCT-008", "G-XCT-009", "G-XCT-010", "G-XCT-011"],
}

# CRITICAL tracker row numbers (1-indexed) → finding ID
CRITICAL_TRACKER = {
    1: "G-ONL-017", 2: "G-ONL-028", 3: "G-OFF-015", 4: "G-OFF-016",
    5: "G-ONL-042", 6: "G-CMD-003", 7: "G-CMD-004", 8: "G-XCT-012",
    9: "G-OFF-029", 10: "G-CMD-002", 11: "G-OFF-046",
}

# Which session is the final one in each phase (triggers phase → COMPLETE)
PHASE_FINAL_SESSION = {
    0: "0.1", 1: "1.3", 2: "2.2", 3: "3.2", 4: "4.2",
    5: "5.3", 6: "6.2", 7: "7.2", 8: "8.2",
}

# ── Parallel Execution Waves ────────────────────────────────────────────────
#
# Wave 1:  [0.1]                                                   1 session
# Wave 2:  [1.1→1.2→1.3] || [2.1→2.2] || [3.1→3.2]               3 parallel tracks
# Wave 3:  [4.1→4.2]                                               1 track
# Wave 4:  [5.1→5.2→5.3] || [6.1→6.2] || [7.1→7.2]               3 parallel tracks
# Wave 5:  [8.1→8.2]                                               1 track
#
# Serial sessions: 1 + max(3,2,2) + 2 + max(3,2,2) + 2 = 11 vs 19 sequential

WAVES = [
    {
        "id": 1,
        "name": "Quick Wins",
        "tracks": [
            {"name": "phase-0", "sessions": ["0.1"]},
        ],
    },
    {
        "id": 2,
        "name": "Core Systems",
        "tracks": [
            {"name": "phase-1-pseudotrader", "sessions": ["1.1", "1.2", "1.3"]},
            {"name": "phase-2-monitoring",   "sessions": ["2.1", "2.2"]},
            {"name": "phase-3-recovery",     "sessions": ["3.1", "3.2"]},
        ],
    },
    {
        "id": 3,
        "name": "Remaining CRITICALs",
        "tracks": [
            {"name": "phase-4", "sessions": ["4.1", "4.2"]},
        ],
    },
    {
        "id": 4,
        "name": "HIGH Fixes",
        "tracks": [
            {"name": "phase-5-offline",  "sessions": ["5.1", "5.2", "5.3"]},
            {"name": "phase-6-online",   "sessions": ["6.1", "6.2"]},
            {"name": "phase-7-command",  "sessions": ["7.1", "7.2"]},
        ],
    },
    {
        "id": 5,
        "name": "Cross-Cutting Sweeps",
        "tracks": [
            {"name": "phase-8", "sessions": ["8.1", "8.2"]},
        ],
    },
]

# ── Thread-safe state lock ──────────────────────────────────────────────────

_state_lock = threading.Lock()

# ── Timezone helper ─────────────────────────────────────────────────────────

ET = timezone(timedelta(hours=-4))  # EDT


def now_et() -> datetime:
    return datetime.now(ET)


def fmt_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S ET")


def fmt_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"


# ── State management (thread-safe) ──────────────────────────────────────────

def load_state() -> dict:
    with _state_lock:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
        return {"created": fmt_time(now_et()), "last_updated": fmt_time(now_et()), "sessions": {}}


def save_state(state: dict) -> None:
    with _state_lock:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        state["last_updated"] = fmt_time(now_et())
        STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def get_session_state(state: dict, sid: str) -> str:
    return state.get("sessions", {}).get(sid, {}).get("status", "PENDING")


def set_session_state(state: dict, sid: str, status: str, **kwargs) -> None:
    with _state_lock:
        state.setdefault("sessions", {}).setdefault(sid, {})
        entry = state["sessions"][sid]
        entry["status"] = status
        for k, v in kwargs.items():
            if v is not None:
                entry[k] = v


# ── Prompt extraction ────────────────────────────────────────────────────────

def extract_prompts_from_orchestrator() -> dict[str, str]:
    if not ORCHESTRATOR.exists():
        print(f"ERROR: {ORCHESTRATOR} not found"); sys.exit(1)
    content = ORCHESTRATOR.read_text()
    prompts: dict[str, str] = {}
    parts = re.split(r"### Session (\d+\.\d+)\s*[—–-]", content)
    for i in range(1, len(parts) - 1, 2):
        sid = parts[i].strip()
        match = re.search(r"````\n(.*?)````", parts[i + 1], re.DOTALL)
        if match:
            prompts[sid] = match.group(1).strip()
    return prompts


# ── Git helpers ──────────────────────────────────────────────────────────────

def git_run(args: list[str], cwd: Path = None, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        capture_output=True, text=True, cwd=cwd or ROOT, timeout=30,
    )


def git_head_sha(cwd: Path = None) -> str:
    r = git_run(["rev-parse", "--short", "HEAD"], cwd=cwd)
    return r.stdout.strip() or "unknown"


def git_has_uncommitted(cwd: Path = None) -> bool:
    r = git_run(["status", "--porcelain"], cwd=cwd)
    return any(line and not line.startswith("??") for line in r.stdout.strip().splitlines())


def git_log_since(sha: str, cwd: Path = None) -> str:
    r = git_run(["log", "--oneline", f"{sha}..HEAD"], cwd=cwd)
    return r.stdout.strip()


def git_current_branch(cwd: Path = None) -> str:
    r = git_run(["branch", "--show-current"], cwd=cwd)
    return r.stdout.strip()


# ── Worktree management ─────────────────────────────────────────────────────

def create_worktree(track_name: str) -> Path:
    """Create a git worktree branching from current HEAD. Returns worktree path."""
    wt_path = WORKTREE_DIR / track_name
    branch = f"audit/{track_name}"

    # Clean up stale worktree if it exists
    if wt_path.exists():
        git_run(["worktree", "remove", "--force", str(wt_path)])
    r = git_run(["branch", "-D", branch])  # ignore error if branch doesn't exist

    wt_path.parent.mkdir(parents=True, exist_ok=True)
    r = git_run(["worktree", "add", "-b", branch, str(wt_path), "HEAD"])
    if r.returncode != 0:
        raise RuntimeError(f"Failed to create worktree: {r.stderr}")

    # Copy untracked config files that Claude/MCP need
    for filename in [".mcp.json", ".env", ".env.template"]:
        src = ROOT / filename
        if src.exists():
            shutil.copy2(src, wt_path / filename)

    return wt_path


def merge_worktree(track_name: str) -> tuple[bool, str]:
    """
    Merge a worktree branch back into the current branch.
    Returns (success, message).
    """
    branch = f"audit/{track_name}"
    r = git_run(["merge", branch, "--no-edit", "-m", f"merge: audit track {track_name}"])
    if r.returncode != 0:
        # Check if it's a merge conflict
        if "CONFLICT" in r.stdout or "CONFLICT" in r.stderr:
            # Attempt to auto-resolve doc conflicts (different-line changes in same file)
            git_run(["checkout", "--theirs", "--",
                     "docs/audit/audit_runs/2026-04-11_audit/GAP_ANALYSIS.md",
                     "docs/audit/audit_runs/2026-04-11_audit/EXECUTION_ORCHESTRATOR.md"])
            git_run(["add", "docs/audit/audit_runs/2026-04-11_audit/"])
            r2 = git_run(["commit", "--no-edit"])
            if r2.returncode == 0:
                return True, f"Merged with auto-resolved doc conflicts"
            else:
                git_run(["merge", "--abort"])
                return False, f"Merge conflict could not be auto-resolved: {r.stderr}"
        return False, f"Merge failed: {r.stderr}"
    return True, "Clean merge"


def cleanup_worktree(track_name: str) -> None:
    """Remove worktree and its branch."""
    wt_path = WORKTREE_DIR / track_name
    branch = f"audit/{track_name}"
    git_run(["worktree", "remove", "--force", str(wt_path)])
    git_run(["branch", "-D", branch])


def cleanup_all_worktrees() -> None:
    """Remove all audit worktrees."""
    if WORKTREE_DIR.exists():
        for child in WORKTREE_DIR.iterdir():
            if child.is_dir():
                cleanup_worktree(child.name)
        if WORKTREE_DIR.exists():
            shutil.rmtree(WORKTREE_DIR, ignore_errors=True)


# ── Execution log writer ────────────────────────────────────────────────────

class SessionLog:
    def __init__(self, sid: str):
        self.sid = sid
        self.meta = SESSION_META[sid]
        self.path = LOGS_DIR / f"session_{sid.replace('.', '_')}_log.md"
        self.start_time = now_et()
        self._lines: list[str] = []
        self._lock = threading.Lock()

    def write_header(self, prompt: str, cwd: Path = None) -> None:
        title = self.meta["title"]
        header = textwrap.dedent(f"""\
            # Execution Log — Session {self.sid}: {title}

            | Field | Value |
            |-------|-------|
            | **Phase** | {self.meta['phase']} |
            | **Started** | {fmt_time(self.start_time)} |
            | **CRITICALs** | {', '.join(self.meta['criticals']) or 'None'} |
            | **Git HEAD (before)** | `{git_head_sha(cwd)}` |
            | **Worktree** | `{cwd or ROOT}` |
            | **Status** | RUNNING |

            ---

            ## Passover Prompt

            <details>
            <summary>Click to expand ({len(prompt)} chars)</summary>

            ```
            {prompt}
            ```

            </details>

            ---

            ## Execution Output

            ```
        """)
        with self._lock:
            self._lines = [header]

    def append_output(self, text: str) -> None:
        with self._lock:
            self._lines.append(text)

    def write_footer(self, status: str, *, commit: str = None, error: str = None, cwd: Path = None) -> None:
        end_time = now_et()
        duration = fmt_duration((end_time - self.start_time).total_seconds())
        parts = [
            "\n```\n\n---\n",
            "## Post-Execution State\n",
            "| Field | Value |",
            "|-------|-------|",
            f"| **Status** | **{status}** |",
            f"| **Completed** | {fmt_time(end_time)} |",
            f"| **Duration** | {duration} |",
            f"| **Git HEAD (after)** | `{git_head_sha(cwd)}` |",
        ]
        if commit:
            parts.append(f"| **Commit** | `{commit}` |")
        if error:
            parts.append(f"| **Error** | {error} |")
        parts.append("")
        with self._lock:
            self._lines.append("\n".join(parts))

    def flush(self) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.path.write_text("".join(self._lines))


# ── Post-session tracking doc reconciliation ────────────────────────────────

GAP_ANALYSIS = AUDIT_DIR / "GAP_ANALYSIS.md"


def reconcile_tracking_docs(sid: str, state: dict, *, cwd: Path = None) -> int:
    """
    Programmatically update GAP_ANALYSIS.md and EXECUTION_ORCHESTRATOR.md
    after a session completes. Returns number of changes made.

    This runs regardless of whether Claude remembered to do it, making the
    tracking tables reliable.
    """
    changes = 0

    # ── 1. GAP_ANALYSIS.md: mark session's findings as [RESOLVED] ──
    gap_path = GAP_ANALYSIS
    if cwd and cwd != ROOT:
        gap_path = cwd / GAP_ANALYSIS.relative_to(ROOT)

    if gap_path.exists():
        content = gap_path.read_text()
        findings = SESSION_FINDINGS.get(sid, [])
        for fid in findings:
            # Match table rows: | G-XXX-NNN | ... | `[GAP]` | ...
            pattern = rf"(\| {re.escape(fid)} \|[^|]*\|[^|]*\|[^|]*\| )`\[GAP\]`"
            replacement = rf"\1`[RESOLVED]`"
            new_content, n = re.subn(pattern, replacement, content)
            if n > 0:
                content = new_content
                changes += n
        if changes > 0:
            gap_path.write_text(content)
            print(f"  [reconcile] GAP_ANALYSIS.md: marked {changes} findings as [RESOLVED]")

    # ── 2. EXECUTION_ORCHESTRATOR.md: update phase status + CRITICAL tracker ──
    orch_path = ORCHESTRATOR
    if cwd and cwd != ROOT:
        orch_path = cwd / ORCHESTRATOR.relative_to(ROOT)

    if orch_path.exists():
        content = orch_path.read_text()
        orch_changes = 0

        # 2a. CRITICAL Resolution Tracker: PENDING → RESOLVED for this session's criticals
        criticals = SESSION_META.get(sid, {}).get("criticals", [])
        for crit_num, crit_fid in CRITICAL_TRACKER.items():
            if crit_fid in criticals:
                old = f"| {crit_num} | {crit_fid}"
                # Find the row and replace PENDING with RESOLVED
                pattern = rf"(\| {crit_num} \| {re.escape(crit_fid)}[^|]*\|[^|]*\|[^|]*\| )PENDING"
                replacement = rf"\1RESOLVED"
                content, n = re.subn(pattern, replacement, content)
                orch_changes += n

        # 2b. Phase Summary: mark phase COMPLETE if this is the final session
        phase = SESSION_META.get(sid, {}).get("phase")
        if phase is not None and PHASE_FINAL_SESSION.get(phase) == sid:
            # Check all sessions in this phase are completed
            phase_sessions = [s for s in SESSION_ORDER if SESSION_META[s]["phase"] == phase]
            all_done = all(get_session_state(state, s) == "COMPLETED" for s in phase_sessions)
            if all_done:
                # Match: | N | Title | ... | PENDING |
                pattern = rf"(\| {phase} \|[^|]*\|[^|]*\|[^|]*\|[^|]*\| )PENDING"
                replacement = rf"\1COMPLETE"
                content, n = re.subn(pattern, replacement, content)
                orch_changes += n
                if n > 0:
                    print(f"  [reconcile] Phase {phase} marked COMPLETE")

        if orch_changes > 0:
            orch_path.write_text(content)
            print(f"  [reconcile] EXECUTION_ORCHESTRATOR.md: {orch_changes} updates")
            changes += orch_changes

    return changes


def reconcile_all_completed(state: dict) -> int:
    """Run reconciliation for ALL completed sessions. For retroactive fix-up."""
    total = 0
    for sid in SESSION_ORDER:
        if get_session_state(state, sid) == "COMPLETED":
            n = reconcile_tracking_docs(sid, state)
            total += n
    return total


# ── Session runner ───────────────────────────────────────────────────────────

def build_claude_command(prompt: str, *, unattended: bool = False, model: str = "opus") -> list[str]:
    cmd = ["claude", "-p", "--model", model, "--effort", "max", "--verbose"]
    if unattended:
        cmd.append("--dangerously-skip-permissions")
    else:
        cmd.extend(["--permission-mode", "acceptEdits"])
    cmd.append(prompt)
    return cmd


def run_session(
    sid: str,
    prompt: str,
    state: dict,
    *,
    unattended: bool = False,
    model: str = "opus",
    timeout_s: int = 1800,
    cwd: Path = None,
    label: str = "",
) -> bool:
    """Execute a single session. Returns True on success."""
    cwd = cwd or ROOT
    meta = SESSION_META[sid]
    log = SessionLog(sid)
    prefix = f"  [{label}] " if label else "  "

    print(f"\n{'='*72}")
    print(f"{prefix}SESSION {sid}: {meta['title']}")
    print(f"{prefix}Phase {meta['phase']} | CRITICALs: {', '.join(meta['criticals']) or 'None'}")
    print(f"{prefix}CWD: {cwd}")
    print(f"{prefix}Started: {fmt_time(now_et())}")
    print(f"{'='*72}\n")

    sha_before = git_head_sha(cwd)
    set_session_state(state, sid, "RUNNING",
                      started=fmt_time(now_et()),
                      log_file=str(log.path.relative_to(ROOT)))
    save_state(state)

    log.write_header(prompt, cwd)
    log.flush()

    cmd = build_claude_command(prompt, unattended=unattended, model=model)
    print(f"{prefix}Running: claude -p --model {model} --effort max ...")
    print(f"{prefix}Log: {log.path.relative_to(ROOT)}")
    print(f"{prefix}Timeout: {fmt_duration(timeout_s)}\n")

    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd,
            env={**os.environ, "CLAUDE_CODE_SIMPLE": "0"},
        )
        chunk_count = 0
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                log.append_output(line)
                chunk_count += 1
                if chunk_count % 50 == 0:
                    log.flush()

        proc.wait(timeout=timeout_s)
        exit_code = proc.returncode
        elapsed = time.monotonic() - start

    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait()
        elapsed = time.monotonic() - start
        err = f"Timed out after {fmt_duration(timeout_s)}"
        log.write_footer("FAILED (TIMEOUT)", error=err, cwd=cwd); log.flush()
        set_session_state(state, sid, "FAILED",
                          completed=fmt_time(now_et()), duration=fmt_duration(elapsed), error=err)
        save_state(state)
        print(f"\n{prefix}TIMEOUT after {fmt_duration(elapsed)}")
        return False

    except Exception as e:
        elapsed = time.monotonic() - start
        err = f"Process error: {e}"
        log.write_footer("FAILED (ERROR)", error=err, cwd=cwd); log.flush()
        set_session_state(state, sid, "FAILED",
                          completed=fmt_time(now_et()), duration=fmt_duration(elapsed), error=err)
        save_state(state)
        print(f"\n{prefix}ERROR: {e}")
        return False

    sha_after = git_head_sha(cwd)
    new_commits = git_log_since(sha_before, cwd) if sha_after != sha_before else ""

    if exit_code == 0:
        commit = sha_after if sha_after != sha_before else None
        log.write_footer("COMPLETED", commit=commit, cwd=cwd); log.flush()
        set_session_state(state, sid, "COMPLETED",
                          completed=fmt_time(now_et()), duration=fmt_duration(elapsed), commit=commit)
        save_state(state)
        print(f"\n{prefix}COMPLETED in {fmt_duration(elapsed)}")
        if new_commits:
            for line in new_commits.splitlines():
                print(f"{prefix}  {line}")
        else:
            print(f"{prefix}WARNING: No new commits detected")
        # Reconcile tracking docs (programmatic, not reliant on Claude)
        reconcile_tracking_docs(sid, state, cwd=cwd)
        return True
    else:
        err = f"Exit code {exit_code}"
        log.write_footer("FAILED", error=err, cwd=cwd); log.flush()
        set_session_state(state, sid, "FAILED",
                          completed=fmt_time(now_et()), duration=fmt_duration(elapsed), error=err)
        save_state(state)
        print(f"\n{prefix}FAILED (exit {exit_code}) after {fmt_duration(elapsed)}")
        return False


# ── Track runner (sequential sessions within one track) ─────────────────────

def run_track(
    track: dict,
    prompts: dict[str, str],
    state: dict,
    *,
    unattended: bool,
    model: str,
    timeout_s: int,
    cwd: Path = None,
) -> tuple[str, bool, list[str]]:
    """
    Run all sessions in a track sequentially.
    Returns (track_name, success, list_of_completed_session_ids).
    """
    name = track["name"]
    completed = []
    cwd = cwd or ROOT

    for sid in track["sessions"]:
        if get_session_state(state, sid) == "COMPLETED":
            completed.append(sid)
            continue
        if sid not in prompts:
            print(f"  [{name}] SKIP {sid}: no prompt found")
            continue

        success = run_session(
            sid, prompts[sid], state,
            unattended=unattended, model=model, timeout_s=timeout_s,
            cwd=cwd, label=name,
        )
        if success:
            completed.append(sid)
        else:
            return name, False, completed

    return name, True, completed


# ── Parallel wave runner ────────────────────────────────────────────────────

def run_wave_parallel(
    wave: dict,
    prompts: dict[str, str],
    state: dict,
    *,
    unattended: bool,
    model: str,
    timeout_s: int,
) -> bool:
    """
    Execute a wave. Single-track waves run on main branch.
    Multi-track waves use git worktrees for parallel execution.
    Returns True if all tracks succeeded.
    """
    tracks = wave["tracks"]
    wave_name = f"Wave {wave['id']}: {wave['name']}"

    # Check if entire wave is already done
    all_sessions = [s for t in tracks for s in t["sessions"]]
    if all(get_session_state(state, s) == "COMPLETED" for s in all_sessions):
        print(f"\n  {wave_name} — all sessions complete, skipping")
        return True

    print(f"\n{'#'*72}")
    print(f"  {wave_name}")
    track_labels = " || ".join(
        "→".join(t["sessions"]) for t in tracks
    )
    print(f"  Tracks: {track_labels}")
    print(f"{'#'*72}")

    # ── Single track: run directly on main branch ──
    if len(tracks) == 1:
        _, success, _ = run_track(
            tracks[0], prompts, state,
            unattended=unattended, model=model, timeout_s=timeout_s,
        )
        return success

    # ── Multiple tracks: parallel execution with worktrees ──
    print(f"\n  Creating {len(tracks)} worktrees for parallel execution...")
    worktrees: dict[str, Path] = {}
    try:
        for track in tracks:
            wt_path = create_worktree(track["name"])
            worktrees[track["name"]] = wt_path
            print(f"    {track['name']}: {wt_path}")
    except RuntimeError as e:
        print(f"\n  ERROR creating worktrees: {e}")
        print(f"  Falling back to sequential execution for this wave.")
        # Fallback: run tracks sequentially on main branch
        for track in tracks:
            _, success, _ = run_track(
                track, prompts, state,
                unattended=unattended, model=model, timeout_s=timeout_s,
            )
            if not success:
                return False
        return True

    # Run tracks in parallel threads
    print(f"\n  Launching {len(tracks)} parallel tracks...")
    results: dict[str, tuple[bool, list[str]]] = {}

    with ThreadPoolExecutor(max_workers=len(tracks)) as executor:
        futures = {}
        for track in tracks:
            future = executor.submit(
                run_track, track, prompts, state,
                unattended=unattended, model=model, timeout_s=timeout_s,
                cwd=worktrees[track["name"]],
            )
            futures[future] = track["name"]

        for future in as_completed(futures):
            track_name = futures[future]
            try:
                _, success, completed = future.result()
                results[track_name] = (success, completed)
                status = "OK" if success else "FAILED"
                print(f"\n  Track {track_name}: {status} (completed: {', '.join(completed)})")
            except Exception as e:
                results[track_name] = (False, [])
                print(f"\n  Track {track_name}: EXCEPTION — {e}")

    # Merge successful tracks back into main branch
    print(f"\n  Merging worktree branches...")
    all_ok = True
    for track in tracks:
        name = track["name"]
        success, _ = results.get(name, (False, []))
        if success:
            merged, msg = merge_worktree(name)
            if merged:
                print(f"    {name}: {msg}")
            else:
                print(f"    {name}: MERGE FAILED — {msg}")
                print(f"    Worktree preserved at: {worktrees[name]}")
                print(f"    Branch: audit/{name}")
                print(f"    Resolve manually, then: git worktree remove {worktrees[name]}")
                all_ok = False
                continue
        else:
            print(f"    {name}: skipped merge (track failed)")
            all_ok = False

        # Cleanup successful/failed worktrees (but not merge-failed ones)
        if success or not results.get(name, (False, []))[0]:
            cleanup_worktree(name)

    return all_ok


# ── Sequential mode runner ──────────────────────────────────────────────────

def run_sequential(
    sessions: list[str],
    prompts: dict[str, str],
    state: dict,
    *,
    unattended: bool,
    model: str,
    timeout_s: int,
) -> None:
    """Run sessions sequentially on main branch."""
    total = len(sessions)
    for i, sid in enumerate(sessions, 1):
        if sid not in prompts:
            print(f"\n  SKIP {sid}: no prompt found")
            continue

        # Dependency check (interactive)
        unmet = [d for d in DEPENDENCIES.get(sid, []) if get_session_state(state, d) != "COMPLETED"]
        if unmet:
            print(f"\n  WARNING: Session {sid} has unmet deps: {', '.join(unmet)}")
            resp = input(f"  Continue anyway? [y/N] ").strip().lower()
            if resp != "y":
                print(f"  Stopped. Resume: python3 scripts/run_audit_execution.py --from {sid}")
                break

        print(f"\n  [{i}/{total}] Preparing session {sid}...")
        success = run_session(
            sid, prompts[sid], state,
            unattended=unattended, model=model, timeout_s=timeout_s,
        )

        if success:
            print(f"  [{i}/{total}] Session {sid} COMPLETED")
            if i < total:
                time.sleep(5)
        else:
            print(f"  [{i}/{total}] Session {sid} FAILED")
            entry = state.get("sessions", {}).get(sid, {})
            print(f"  Log: {entry.get('log_file', '?')}")
            remaining = sessions[i:]
            if remaining:
                print(f"  Retry:    python3 scripts/run_audit_execution.py --only {sid}")
                print(f"  Skip:     python3 scripts/run_audit_execution.py --from {remaining[0]}")
            break


# ── Parallel mode runner ────────────────────────────────────────────────────

def run_parallel(
    prompts: dict[str, str],
    state: dict,
    *,
    unattended: bool,
    model: str,
    timeout_s: int,
) -> None:
    """Run sessions using wave-based parallelization."""
    print(f"\n  PARALLEL MODE — 5 waves, ~11 serial sessions")
    print(f"  Worktree dir: {WORKTREE_DIR}\n")

    for wave in WAVES:
        success = run_wave_parallel(
            wave, prompts, state,
            unattended=unattended, model=model, timeout_s=timeout_s,
        )
        if not success:
            wave_sessions = [s for t in wave["tracks"] for s in t["sessions"]]
            failed = [s for s in wave_sessions if get_session_state(state, s) == "FAILED"]
            print(f"\n  Wave {wave['id']} incomplete. Failed sessions: {', '.join(failed)}")
            print(f"  Fix the issues, then re-run with --parallel to continue.")
            break


# ── Display helpers ──────────────────────────────────────────────────────────

STATUS_SYMBOLS = {"PENDING": "  ", "RUNNING": ">>", "COMPLETED": "OK", "FAILED": "XX"}


def print_status(state: dict) -> None:
    completed = sum(1 for s in SESSION_ORDER if get_session_state(state, s) == "COMPLETED")
    total = len(SESSION_ORDER)

    print(f"\n  Audit Execution Status — {completed}/{total} sessions complete")
    print(f"  Last updated: {state.get('last_updated', 'never')}\n")
    print(f"  {'Sess':>5}  {'St':>2}  {'Phase':>5}  {'Title':<52}  {'Duration':>10}  {'Commit':>8}")
    print(f"  {'─'*5}  {'─'*2}  {'─'*5}  {'─'*52}  {'─'*10}  {'─'*8}")

    current_phase = -1
    for sid in SESSION_ORDER:
        meta = SESSION_META[sid]
        status = get_session_state(state, sid)
        entry = state.get("sessions", {}).get(sid, {})
        if meta["phase"] != current_phase:
            if current_phase >= 0:
                print()
            current_phase = meta["phase"]
        crit = "*" if meta["criticals"] else " "
        print(
            f"  {sid:>5}  {STATUS_SYMBOLS.get(status, '??'):>2}  "
            f"P{meta['phase']:<4}  {crit}{meta['title']:<51}  "
            f"{entry.get('duration', ''):>10}  "
            f"{(entry.get('commit', '') or '')[:7]:>8}"
        )

    print()
    failed = [s for s in SESSION_ORDER if get_session_state(state, s) == "FAILED"]
    if failed:
        print(f"  FAILED: {', '.join(failed)}")
        print(f"  Resume: python3 scripts/run_audit_execution.py --from {failed[0]}")
    elif completed < total:
        pending = [s for s in SESSION_ORDER if get_session_state(state, s) == "PENDING"]
        if pending:
            print(f"  Next: {pending[0]}")
    else:
        print(f"  ALL SESSIONS COMPLETE")
    print()


def print_dry_run_parallel() -> None:
    print(f"\n  PARALLEL DRY RUN — 5 waves:\n")
    for wave in WAVES:
        n_tracks = len(wave["tracks"])
        parallel = " (PARALLEL)" if n_tracks > 1 else ""
        print(f"  Wave {wave['id']}: {wave['name']}{parallel}")
        for track in wave["tracks"]:
            sessions = track["sessions"]
            crits = []
            for s in sessions:
                crits.extend(SESSION_META[s].get("criticals", []))
            crit_str = f"  [{', '.join(crits)}]" if crits else ""
            print(f"    Track {track['name']:.<30} {'→'.join(sessions)}{crit_str}")
        print()
    print(f"  Serial sessions: 1 + 3 + 2 + 3 + 2 = 11  (vs 19 sequential)")
    print(f"  Estimated speedup: ~42%\n")


def print_summary(state: dict) -> None:
    completed = [s for s in SESSION_ORDER if get_session_state(state, s) == "COMPLETED"]
    failed = [s for s in SESSION_ORDER if get_session_state(state, s) == "FAILED"]
    pending = [s for s in SESSION_ORDER if get_session_state(state, s) == "PENDING"]
    all_criticals = [c for s in completed for c in SESSION_META[s].get("criticals", [])]

    print(f"\n{'='*72}")
    print(f"  EXECUTION SUMMARY")
    print(f"{'='*72}")
    print(f"  Completed: {len(completed)}/{len(SESSION_ORDER)} | Failed: {len(failed)} | Pending: {len(pending)}")
    print(f"  CRITICALs resolved: {len(all_criticals)}/11")
    if all_criticals:
        print(f"    {', '.join(all_criticals)}")
    if failed:
        print(f"\n  Failed:")
        for sid in failed:
            entry = state.get("sessions", {}).get(sid, {})
            print(f"    {sid}: {entry.get('error', 'unknown')}")
    print(f"{'='*72}\n")


def write_summary_file(state: dict) -> None:
    completed = [s for s in SESSION_ORDER if get_session_state(state, s) == "COMPLETED"]
    all_criticals = [c for s in completed for c in SESSION_META[s].get("criticals", [])]

    lines = [
        "# Audit Execution Summary\n",
        f"**Generated:** {fmt_time(now_et())}",
        f"**Completed:** {len(completed)}/{len(SESSION_ORDER)} sessions",
        f"**CRITICALs resolved:** {len(all_criticals)}/11\n",
        "## Session Results\n",
        "| Session | Title | Status | Duration | Commit |",
        "|---------|-------|--------|----------|--------|",
    ]
    for sid in SESSION_ORDER:
        meta = SESSION_META[sid]
        entry = state.get("sessions", {}).get(sid, {})
        status = get_session_state(state, sid)
        dur = entry.get("duration", "-")
        commit = f"`{entry['commit'][:7]}`" if entry.get("commit") else "-"
        crit = f" ({', '.join(meta['criticals'])})" if meta["criticals"] else ""
        lines.append(f"| {sid} | {meta['title']}{crit} | {status} | {dur} | {commit} |")
    lines.append("")

    path = LOGS_DIR / "EXECUTION_SUMMARY.md"
    path.write_text("\n".join(lines))
    print(f"  Summary: {path.relative_to(ROOT)}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Captain System — Audit Execution Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python3 scripts/run_audit_execution.py                 # Sequential
              python3 scripts/run_audit_execution.py --parallel      # Parallel waves
              python3 scripts/run_audit_execution.py --from 2.1      # Resume from 2.1
              python3 scripts/run_audit_execution.py --only 3.1      # Single session
              python3 scripts/run_audit_execution.py --status        # Progress
              python3 scripts/run_audit_execution.py --dry-run       # Preview
              python3 scripts/run_audit_execution.py --unattended    # Auto-approve
              python3 scripts/run_audit_execution.py --reset 2.1     # Reset failed
        """),
    )
    parser.add_argument("--parallel", action="store_true",
                        help="Run independent phases in parallel using git worktrees (~42%% faster)")
    parser.add_argument("--from", dest="from_session", metavar="SID",
                        help="Resume from this session (e.g. 2.1)")
    parser.add_argument("--only", metavar="SID",
                        help="Run only this single session")
    parser.add_argument("--status", action="store_true",
                        help="Show current execution status")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview execution plan without running")
    parser.add_argument("--unattended", action="store_true",
                        help="Auto-approve all tool calls (--dangerously-skip-permissions)")
    parser.add_argument("--reset", metavar="SID",
                        help="Reset a session to PENDING for re-run")
    parser.add_argument("--reconcile", action="store_true",
                        help="Update tracking docs for all completed sessions (retroactive fix)")
    parser.add_argument("--cleanup-worktrees", action="store_true",
                        help="Remove all audit worktrees and exit")
    parser.add_argument("--model", default=os.environ.get("CLAUDE_MODEL", "opus"),
                        help="Claude model (default: opus)")
    parser.add_argument("--timeout", type=int,
                        default=int(os.environ.get("AUDIT_TIMEOUT", "1800")),
                        help="Per-session timeout in seconds (default: 1800)")
    args = parser.parse_args()

    if not ORCHESTRATOR.exists():
        print(f"ERROR: {ORCHESTRATOR} not found")
        sys.exit(1)

    state = load_state()

    # ── Simple commands ──
    if args.status:
        print_status(state); return

    if args.reset:
        if args.reset not in SESSION_META:
            print(f"ERROR: Unknown session '{args.reset}'"); sys.exit(1)
        set_session_state(state, args.reset, "PENDING")
        save_state(state)
        print(f"  Session {args.reset} reset to PENDING"); return

    if args.reconcile:
        print(f"  Reconciling tracking docs for all completed sessions...")
        n = reconcile_all_completed(state)
        if n > 0:
            print(f"  Total: {n} updates applied")
        else:
            print(f"  Tracking docs already up to date")
        return

    if args.cleanup_worktrees:
        print(f"  Cleaning up worktrees...")
        cleanup_all_worktrees()
        print(f"  Done."); return

    # ── Extract prompts ──
    print(f"\n  Extracting prompts from {ORCHESTRATOR.name}...")
    prompts = extract_prompts_from_orchestrator()
    print(f"  Found {len(prompts)} session prompts")

    missing = [s for s in SESSION_ORDER if s not in prompts]
    if missing:
        print(f"  WARNING: Missing prompts: {', '.join(missing)}")

    # ── Dry run ──
    if args.dry_run:
        if args.parallel:
            print_dry_run_parallel()
        else:
            sessions = _resolve_sessions(args, state)
            print(f"\n  SEQUENTIAL DRY RUN — {len(sessions)} sessions:\n")
            for sid in sessions:
                meta = SESSION_META[sid]
                deps = DEPENDENCIES.get(sid, [])
                unmet = [d for d in deps if get_session_state(state, d) != "COMPLETED"]
                dep_str = f" (deps: {', '.join(deps)})" if deps else ""
                warn = f" [UNMET: {', '.join(unmet)}]" if unmet else ""
                crit = f" [CRITICALs: {', '.join(meta['criticals'])}]" if meta["criticals"] else ""
                print(f"    {sid:>5}  P{meta['phase']}  {meta['title']}{dep_str}{warn}{crit}")
            print()
        print(f"  Model: {args.model} | Effort: max | Timeout: {fmt_duration(args.timeout)}")
        mode = "UNATTENDED" if args.unattended else "SUPERVISED"
        print(f"  Mode: {mode}\n")
        return

    # ── Pre-flight checks ──
    if args.parallel and args.from_session:
        print("ERROR: --parallel and --from cannot be combined. Use --parallel to run all pending.")
        sys.exit(1)
    if args.parallel and args.only:
        print("ERROR: --parallel and --only cannot be combined.")
        sys.exit(1)

    # ── Confirm ──
    if args.parallel:
        print(f"\n  PARALLEL MODE — 5 waves, 3 concurrent tracks max")
    elif args.only:
        print(f"\n  Running single session: {args.only}")
    else:
        sessions = _resolve_sessions(args, state)
        if not sessions:
            print(f"\n  All sessions COMPLETED.")
            print_status(state); return
        print(f"\n  SEQUENTIAL — {len(sessions)} sessions: {', '.join(sessions)}")

    print(f"  Model: {args.model} | Effort: max | Timeout: {fmt_duration(args.timeout)}/session")
    mode = "UNATTENDED (auto-approve all)" if args.unattended else "SUPERVISED (auto-approve edits)"
    print(f"  Mode: {mode}")

    if git_has_uncommitted():
        print(f"\n  WARNING: Uncommitted changes in working tree.")
        resp = input(f"  Continue? [y/N] ").strip().lower()
        if resp != "y":
            return
    print()
    resp = input(f"  Start? [Y/n] ").strip().lower()
    if resp == "n":
        return

    # ── Execute ──
    if args.parallel:
        run_parallel(
            prompts, state,
            unattended=args.unattended, model=args.model, timeout_s=args.timeout,
        )
    elif args.only:
        if args.only not in prompts:
            print(f"ERROR: No prompt for session {args.only}"); sys.exit(1)
        run_session(
            args.only, prompts[args.only], state,
            unattended=args.unattended, model=args.model, timeout_s=args.timeout,
        )
    else:
        sessions = _resolve_sessions(args, state)
        run_sequential(
            sessions, prompts, state,
            unattended=args.unattended, model=args.model, timeout_s=args.timeout,
        )

    # ── Summary ──
    print_summary(state)
    write_summary_file(state)
    print_status(state)


def _resolve_sessions(args, state) -> list[str]:
    """Determine which sessions to run based on args."""
    if args.only:
        return [args.only]
    if args.from_session:
        if args.from_session not in SESSION_META:
            print(f"ERROR: Unknown session '{args.from_session}'"); sys.exit(1)
        idx = SESSION_ORDER.index(args.from_session)
        return [s for s in SESSION_ORDER[idx:] if get_session_state(state, s) != "COMPLETED"]
    return [s for s in SESSION_ORDER if get_session_state(state, s) != "COMPLETED"]


if __name__ == "__main__":
    main()
