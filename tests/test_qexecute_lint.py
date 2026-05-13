"""Phase 5 meta-test: pin the new qexecute compliance check in
``scripts/lint_decimal_boundary.py``.

This test verifies:
  1. The lint flags a raw ``cur.execute("INSERT INTO p3_d… …")`` site.
  2. The ``# qexecute: ok`` suppression marker disables the flag.
  3. The lint passes for a ``qexecute(cur, …)`` call.
  4. The lint does NOT flag ``cur.execute("SELECT …")`` (only INSERT/UPDATE).
  5. Multi-line INSERTs are caught via the lookahead.
  6. Alternate cursor names (``cur``, ``_cur``, ``c``, ``cursor``) are caught.
  7. ``UPDATE p[23]_*`` is also policed.
  8. The actual repo is clean post Phase 3 + Phase 5 marker pass.

Each probe is staged as ``probe.py`` inside a pytest ``tmp_path`` and the
lint is invoked with that directory as its scan root (passed positionally
on argv). This isolates probes from the real repo so flagged-vs-clean
behaviour can be asserted deterministically.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_SCRIPT = REPO_ROOT / "scripts" / "lint_decimal_boundary.py"


def _run_lint_on(file_content: str, tmp_path: Path) -> tuple[int, str, str]:
    """Write ``file_content`` to ``tmp_path/probe.py``, then invoke the lint
    scoped to ``tmp_path`` (via positional argv). Returns
    ``(exit_code, stdout, stderr)``.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(file_content, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def test_lint_flags_raw_single_line_insert(tmp_path):
    code = (
        'def write_row(cur):\n'
        '    cur.execute("INSERT INTO p3_d03_trade_outcome_log (trade_id) VALUES (%s)", ("X",))\n'
    )
    rc, stdout, _ = _run_lint_on(code, tmp_path)
    assert rc == 1, f"expected lint to fail, got rc={rc} stdout:\n{stdout}"
    assert "probe.py" in stdout
    assert "execute" in stdout


def test_lint_flags_raw_multiline_insert(tmp_path):
    code = (
        'def write_row(cur):\n'
        '    cur.execute(\n'
        '        """INSERT INTO p3_d03_trade_outcome_log\n'
        '           (trade_id) VALUES (%s)""",\n'
        '        ("X",),\n'
        '    )\n'
    )
    rc, stdout, _ = _run_lint_on(code, tmp_path)
    assert rc == 1, f"expected lint to fail, got rc={rc} stdout:\n{stdout}"
    assert "probe.py" in stdout


def test_lint_passes_with_suppression_marker(tmp_path):
    code = (
        'def write_row(cur):\n'
        '    cur.execute(  # qexecute: ok\n'
        '        """INSERT INTO p3_d03_trade_outcome_log\n'
        '           (trade_id) VALUES (%s)""",\n'
        '        ("X",),\n'
        '    )\n'
    )
    rc, stdout, _ = _run_lint_on(code, tmp_path)
    assert rc == 0, f"expected lint to pass, got stdout:\n{stdout}"


def test_lint_passes_for_qexecute_call(tmp_path):
    code = (
        'from shared.questdb_client import qexecute\n'
        '\n'
        'def write_row(cur):\n'
        '    qexecute(\n'
        '        cur,\n'
        '        """INSERT INTO p3_d03_trade_outcome_log\n'
        '           (trade_id) VALUES (%s)""",\n'
        '        ("X",),\n'
        '    )\n'
    )
    rc, stdout, _ = _run_lint_on(code, tmp_path)
    assert rc == 0, f"expected lint to pass, got stdout:\n{stdout}"


def test_lint_passes_for_select(tmp_path):
    code = (
        'def read_row(cur):\n'
        '    cur.execute("SELECT * FROM p3_d03_trade_outcome_log WHERE asset = %s", ("MES",))\n'
    )
    rc, stdout, _ = _run_lint_on(code, tmp_path)
    assert rc == 0, f"expected lint to pass for SELECT, got stdout:\n{stdout}"


def test_lint_passes_for_unrelated_insert(tmp_path):
    """Only ``p3_*``/``p2_*`` tables are policed — INSERTs into unrelated
    tables (third-party SQLite, audit tables outside the canonical schema,
    etc.) are out of scope for this lint."""
    code = (
        'def write_row(cur):\n'
        '    cur.execute("INSERT INTO some_other_table (x) VALUES (%s)", ("X",))\n'
    )
    rc, stdout, _ = _run_lint_on(code, tmp_path)
    assert rc == 0, f"expected lint to pass for non-p3 INSERT, got stdout:\n{stdout}"


def test_lint_flags_alternate_cursor_names(tmp_path):
    """Catches ``cur``, ``_cur``, ``c``, and ``cursor`` as cursor variable
    names — this set was extracted from the Phase 0B inventory's special
    cases (e.g. ``shared/questdb_client.py`` uses ``c.execute``,
    ``captain-online/.../b1_features.py`` uses ``_cur.execute``)."""
    code_variants = [
        '    cur.execute("INSERT INTO p3_d03_x (a) VALUES (%s)", (1,))',
        '    _cur.execute("INSERT INTO p3_d03_x (a) VALUES (%s)", (1,))',
        '    c.execute("INSERT INTO p3_d03_x (a) VALUES (%s)", (1,))',
        '    cursor.execute("INSERT INTO p3_d03_x (a) VALUES (%s)", (1,))',
    ]
    for variant in code_variants:
        code = "def write_row(cur):\n" + variant + "\n"
        rc, stdout, _ = _run_lint_on(code, tmp_path)
        assert rc == 1, (
            f"expected variant to trip lint:\n{variant}\nstdout:\n{stdout}"
        )


def test_lint_flags_update_too(tmp_path):
    """``UPDATE p[23]_*`` must also route through ``qexecute`` even though
    Phase 0B inventory found 0 production UPDATEs today — ``qexecute``'s
    ``_UPDATE_RE`` is wired for the eventual case, and the lint should
    refuse a regression."""
    code = (
        'def update_row(cur):\n'
        '    cur.execute("UPDATE p3_d23_circuit_breaker_intraday SET l_t = %s", (0,))\n'
    )
    rc, stdout, _ = _run_lint_on(code, tmp_path)
    assert rc == 1, f"expected lint to fail on UPDATE, got rc={rc} stdout:\n{stdout}"


def test_lint_flags_p2_insert_too(tmp_path):
    """The lint policies ``p2_*`` as well as ``p3_*`` — the captain-system
    repo writes to ``p2_d07_regime_models`` for legacy regime data."""
    code = (
        'def write_row(cur):\n'
        '    cur.execute("INSERT INTO p2_d07_regime_models (asset) VALUES (%s)", ("ES",))\n'
    )
    rc, stdout, _ = _run_lint_on(code, tmp_path)
    assert rc == 1, f"expected lint to fail on p2 INSERT, got rc={rc} stdout:\n{stdout}"


def test_repo_is_clean_post_phase_3(tmp_path):
    """Run the lint on the actual repo to confirm Phase 3 + Phase 5 marker
    application left it clean. ``tmp_path`` is unused — kept so this
    matches the fixture signature of the rest of the file."""
    del tmp_path  # noqa: F841 — fixture intentionally ignored
    result = subprocess.run(
        [sys.executable, str(LINT_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"repo lint failed with violations:\n{result.stdout}"
    )
    assert "0 violations" in result.stdout
