"""CI gate: scripts/lint_decimal_boundary.py finds zero violations.

Pytest wrapper around the standalone lint script. Runs on every PR via
the same fast-gate that catches every other regression.

If this fails, the lint script's stdout (printed via captsys) names the
file:line for every violation. Either:

  * Replace `... or 0.0` (or `or 0`, `or 0.25`, etc.) with the
    appropriate `shared.decimal_boundary` helper:
        as_money(value)              -- non-nullable monetary field
        as_money_or_none(value)      -- nullable monetary field
        to_float(value, default=...) -- explicit boundary into sizing math

  * Or, for legitimate non-monetary defaults (probability, divisor,
    dimensionless ratio, counter), add the suppression marker:
        # decimal-boundary: ok

See also: docs2/quick-fixes/fixing-decimal-errors/ for the full audit.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_SCRIPT = REPO_ROOT / "scripts" / "lint_decimal_boundary.py"


def test_decimal_boundary_lint_clean(capsys):
    """Refuses regressions to the falsy-zero antipattern on monetary fields."""
    assert LINT_SCRIPT.is_file(), f"lint script missing: {LINT_SCRIPT}"

    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Re-emit the lint output so failure messages name file:line directly
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    assert result.returncode == 0, (
        f"decimal-boundary lint found violations (exit {result.returncode}). "
        f"See stdout above for file:line. Apply shared.decimal_boundary helpers "
        "or add `# decimal-boundary: ok` for legitimate non-monetary defaults."
    )
