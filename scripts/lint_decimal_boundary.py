#!/usr/bin/env python3
"""Lint guard against the falsy-zero antipattern on monetary fields.

Refuses new occurrences of `r[N] or 0.0` / `or 0` / `or 0.25` / `or 1.5`
in lines that mention any DECIMAL-typed monetary column or that live
inside the data-ingestion / silo / TSM-config code paths.

Background
----------
Phase A (2026-04-28) migrated D08, D16, D23, D25, D28, D03, D00, D30
monetary columns to DECIMAL. Decimal('0.00') is falsy in Python, so
`r[N] or 0.0` collapses zero-valued Decimals to float, producing
type-mixed dicts that trip TypeError on Decimal vs float arithmetic
(NY/APAC open 2026-04-30).

Suppression
-----------
Add `# decimal-boundary: ok` to a line for legitimate non-monetary
defaults (e.g. probability `or 0.5`, divisor `or 1`).

Exit codes
----------
0 = no findings
1 = at least one violation (CI fails)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Phase A/B/C DECIMAL column names — any line that references one of these
# AND uses the `or <number>` antipattern is a violation.
MONETARY_COLUMN_NAMES = {
    # D00
    "point_value", "tick_size", "margin_per_contract",
    # D03
    "entry_price", "signal_entry_price", "exit_price",
    "gross_pnl", "commission", "pnl", "slippage",
    # D08
    "starting_balance", "current_balance", "current_drawdown",
    "daily_loss_used", "profit_target", "max_drawdown_limit",
    "max_daily_loss", "commission_per_contract",
    # D16
    "starting_capital", "total_capital",
    # D23 / D25
    "l_t", "l_star",
    # D28
    "balance_at_event", "fee_charged", "payout_amount", "payout_net",
    "tradable_balance", "reserve_balance",
    # D30
    "open", "high", "low", "close",
}

# `or <number>` antipattern. Catches: `or 0`, `or 0.0`, `or 0.25`, `or 1.5`,
# `or 50.0`, `or 150000`, `or 4500`, etc. Excludes string boolean defaults
# like `or "[]"` and dict defaults `or {}`.
OR_NUMBER_RE = re.compile(r"\bor\s+\d+(?:\.\d+)?\b")

# No-op ternary antipattern (b9_diagnostic 2026-05-01 incident):
# `float(x) if not isinstance(x, T) else float(x)`
# `Decimal(x) if not isinstance(x, T) else Decimal(x)`
# Both branches identical and neither None-safe. Always replace with
# `to_float(x)` / `as_money(x)` from shared.decimal_boundary.
NOOP_TERNARY_RE = re.compile(
    r"(float|Decimal)\s*\(\s*([a-z_][a-z0-9_]*)\s*\)\s+if\s+not\s+isinstance\s*\(\s*\2\s*,\s*"
    r"(?:float|int|Decimal|\(.*?\))\s*\)\s+else\s+\1\s*\(\s*\2\s*\)",
    re.IGNORECASE,
)

SUPPRESSION_MARKER = "# decimal-boundary: ok"

# --------------------------------------------------------------------- #
# Phase 5 (2026-05) — qexecute() compliance check                        #
# --------------------------------------------------------------------- #
#
# Refuses any raw `cur.execute("INSERT INTO p[23]_…", …)` or
# `cur.execute("UPDATE p[23]_…", …)` site that is not routed through
# `qexecute()` from shared/questdb_client.py.
#
# The Phase 1-3 migration converted production INSERT call sites to
# qexecute and suppressed the remaining intentional bypasses (debug
# utilities, test fixtures that exercise the schema directly) with
# `# qexecute: ok`. This lint prevents new code from re-introducing the
# bypass.
#
# The matcher works line-by-line PLUS a 2-line lookahead, since SQL is
# usually on the line(s) following the `cur.execute(` call:
#
#   cur.execute(                         # candidate (line N)
#       """INSERT INTO p3_d03_trade_…    # match (line N+1)
#          VALUES (%s)""",
#       (…))
#
# Suppression: add `# qexecute: ok` to ANY of the 3 lookahead lines.
QEXECUTE_BYPASS_RE = re.compile(
    r"\b(?:cur|_cur|c|cursor)\.execute\s*\(",
)
QEXECUTE_TARGET_RE = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE)\s+p[23]_",
    re.IGNORECASE,
)
QEXECUTE_SUPPRESSION_MARKER = "# qexecute: ok"
QEXECUTE_LOOKAHEAD_LINES = 2

# TODO[Phase 5 follow-up]: Check 2 — bare-string Decimal in json.dumps.
# Heuristic-driven check refusing `json.dumps(..., str(decimal_var), ...)`.
# Deferred because the false-positive rate is high and Phase 4's marker
# rewrite already eliminates the silent precision-loss path. Re-evaluate
# once a regression appears.
_TODO_BARE_DECIMAL_DUMP = None  # noqa: F841 — placeholder anchor

# Files / directories to skip — lint script itself, tests of the boundary,
# canonical schema (DDL strings), and the migration docs.
SKIP_GLOBS = {
    "scripts/lint_decimal_boundary.py",
    "tests/test_decimal_boundary.py",
    "tests/test_decimal_boundary_lint.py",
    # Phase 5 meta-test contains literal `cur.execute(...)` strings inside
    # test-fixture source code; lint must not police its own self-tests.
    "tests/test_qexecute_lint.py",
    "shared/decimal_boundary.py",
    "shared/canonical_schemas.py",
    "MONETARY_DECIMAL_MIGRATION_PLAN.md",
    "MONETARY_DECIMAL_MERGE_VALIDATION.md",
}

# Column-name search is per-line — a line that mentions e.g. `"current_drawdown"`
# OR has `r[6]` (typical TSM_state column index for current_drawdown) is in scope.
# Index check is heuristic but catches the b1_data_ingestion regression shape.
INGESTION_PATH_RE = re.compile(
    r"(_load_tsm_configs|_load_active_assets|_load_user_silo|"
    r"specs\[.*\]\s*=|tsm\s*=\s*\{|kelly_params\[.*\]\s*=|"
    r"ewma_states\[.*\]\s*=)"
)

# Bug C extension: position-monitor inner-loop functions where Decimal
# (from Redis state) commonly mixes with float (from live quote stream).
# Any new arithmetic in these functions should use _money_d / as_money
# coercion, not raw operator math.
POSITION_MONITOR_FUNCTIONS = {
    "monitor_positions",         # b7_position_monitor
    "monitor_shadow_positions",  # b7_shadow_monitor
    "_handle_taken_skipped",     # online orchestrator
    "_publish_trade_outcome",    # b7_position_monitor
}


def _line_in_scope(line: str) -> bool:
    """A line is in scope if it mentions a known monetary column name OR
    sits inside a known data-ingestion construct."""
    if any(col in line for col in MONETARY_COLUMN_NAMES):
        return True
    return bool(INGESTION_PATH_RE.search(line))


def lint_file(path: Path) -> list[tuple[int, str]]:
    findings = []
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return findings

    lines = content.splitlines()
    for idx, line in enumerate(lines):
        line_num = idx + 1
        if SUPPRESSION_MARKER in line:
            continue
        # No-op ternary check is universally bad (no scope filter needed)
        if NOOP_TERNARY_RE.search(line):
            findings.append((line_num, line.rstrip()))
            continue

        # qexecute compliance check: candidate `cur.execute(` line + a
        # 2-line lookahead window so multi-line INSERTs are caught at the
        # call site (line N), not at the SQL string (line N+1). The
        # suppression marker may appear on any of those 3 lines.
        if QEXECUTE_BYPASS_RE.search(line):
            window = lines[idx : idx + 1 + QEXECUTE_LOOKAHEAD_LINES]
            window_text = "\n".join(window)
            if (
                QEXECUTE_TARGET_RE.search(window_text)
                and QEXECUTE_SUPPRESSION_MARKER not in window_text
            ):
                findings.append((line_num, line.rstrip()))
                # Don't `continue` — the same line may also match the
                # falsy-zero antipattern, and we want both findings.

        if not _line_in_scope(line):
            continue
        if OR_NUMBER_RE.search(line):
            findings.append((line_num, line.rstrip()))
    return findings


# Directory names skipped at every depth. Covers all common Python venv
# layouts (`.venv` on most setups, `venv` on Isaac's tower, `env`/`.env`
# on legacy installs), build/cache artefacts, vendored MCP / git worktrees,
# and `site-packages` regardless of which venv name nests it.
_SKIP_DIRNAMES = frozenset({
    ".git", ".venv", "venv", "env", ".env", ".tox",
    "__pycache__", "node_modules", ".pytest_cache", ".cache",
    "build", "dist", "htmlcov", "site-packages",
    "questdb", "redis", "claude-mem",
    ".audit-worktrees", "voicetree-10-4",
})


def iter_python_files(root: Path):
    skip = {str(root / s) for s in SKIP_GLOBS}
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip caches / vendored / venv / git / git worktrees at every depth.
        # `site-packages` is included so the lint never wanders into installed
        # third-party packages (numpy/websockets/uvicorn etc) regardless of
        # which venv directory name nests them.
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRNAMES]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = Path(dirpath) / fn
            rel = str(full)
            if any(rel == s or rel.startswith(s + os.sep) for s in skip):
                continue
            yield full


def main(argv: list[str] | None = None) -> int:
    """Run the lint over the repo (default) or a caller-supplied root.

    The optional positional argument lets the Phase 5 meta-test point the
    scanner at `tmp_path` instead of the actual repo root, so test
    probes are evaluated in isolation. With no argv the script behaves
    exactly like before — scans `REPO_ROOT`.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        root = Path(argv[0]).resolve()
    else:
        root = REPO_ROOT

    total = 0
    files_with_findings = 0
    for fp in iter_python_files(root):
        findings = lint_file(fp)
        if not findings:
            continue
        files_with_findings += 1
        try:
            rel = fp.relative_to(root)
        except ValueError:
            rel = fp
        for lineno, snippet in findings:
            print(f"{rel}:{lineno}: {snippet}")
            total += 1

    if total == 0:
        print("decimal-boundary lint: 0 violations")
        return 0

    print()
    print(f"decimal-boundary lint: {total} violation(s) "
          f"across {files_with_findings} file(s)")
    print()
    print("FIX OPTIONS:")
    print("  1. `r[N] or 0.0` antipattern — replace with "
          "`shared.decimal_boundary.as_money(r[N])` for monetary fields.")
    print("  2. `float(x) if not isinstance(x, T) else float(x)` no-op ternary — "
          "replace with `shared.decimal_boundary.to_float(x)` "
          "(None-safe). Same shape with Decimal — use `as_money(x)`.")
    print("  3. raw `cur.execute(\"INSERT INTO p3_…\", …)` — replace with "
          "`qexecute(cur, sql, params)` from shared.questdb_client. The "
          "helper auto-coerces Decimal params to the right Python type for "
          "DOUBLE / SYMBOL / INT columns. For test fixtures or debug-only "
          "utilities, suppress with `# qexecute: ok` on the call line "
          "or any of the 2 following lines.")
    print()
    print("For legitimate non-monetary defaults (probability, divisor, "
          "dimensionless ratio) add suffix marker:")
    print(f"    {SUPPRESSION_MARKER}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
