"""Phase 7 — Schema tests for D03 signal_id, D11 + D06 column completeness.

Two flavours of test live here:

1. Static tests (always run): assert canonical_schemas.py DDL strings carry
   the expected columns and CANONICAL_MIGRATIONS contains the Phase 7
   ALTER entries.
2. Real-QuestDB tests (marked ``real_questdb``): exercise the live schema
   round-trip + the legacy backfill script. Skipped when QuestDB is
   unavailable.
"""
from __future__ import annotations

import time
import uuid

import pytest

from shared import canonical_schemas


# --------------------------------------------------------------------------- #
# Static DDL tests — always run                                               #
# --------------------------------------------------------------------------- #


def test_d03_canonical_schema_includes_signal_id():
    ddl = canonical_schemas.D03_TRADE_OUTCOME_LOG
    assert "signal_id STRING" in ddl


def test_d11_canonical_schema_columns_complete():
    """O1 / Stage 1B Appendix B — D11 carries Sharpe baseline / updated /
    pair_series for PG-09 metric persistence."""
    ddl = canonical_schemas.D11_PSEUDOTRADER_RESULTS
    for col in ("sharpe_baseline DOUBLE", "sharpe_updated DOUBLE",
                "sharpe_improvement DOUBLE", "pbo DOUBLE", "dsr DOUBLE",
                "recommendation STRING", "pair_series STRING"):
        assert col in ddl, f"D11 missing column: {col}"


def test_d06_canonical_schema_columns_complete():
    """O1 / Stage 1B Appendix B — D06 carries pbo, dsr, transition_days,
    tracking_days, recommendation."""
    ddl = canonical_schemas.D06_INJECTION_HISTORY
    for col in ("expected_new DOUBLE", "expected_current DOUBLE",
                "recommendation STRING", "pbo DOUBLE", "dsr DOUBLE",
                "transition_days INT", "tracking_days INT"):
        assert col in ddl, f"D06 missing column: {col}"


def test_canonical_migrations_includes_phase7_entries():
    """Phase 7 migrations M002…M009 are present and apply to the right tables."""
    migrations = dict(canonical_schemas.CANONICAL_MIGRATIONS)
    expected = {
        "M002_d03_add_signal_id": "p3_d03_trade_outcome_log",
        "M003_d11_add_sharpe_baseline": "p3_d11_pseudotrader_results",
        "M004_d11_add_sharpe_updated": "p3_d11_pseudotrader_results",
        "M005_d11_add_pair_series": "p3_d11_pseudotrader_results",
        "M006_d06_add_pbo": "p3_d06_injection_history",
        "M007_d06_add_dsr": "p3_d06_injection_history",
        "M008_d06_add_transition_days": "p3_d06_injection_history",
        "M009_d06_add_tracking_days": "p3_d06_injection_history",
    }
    for mig_id, table in expected.items():
        assert mig_id in migrations, f"missing migration {mig_id}"
        assert table in migrations[mig_id], (
            f"migration {mig_id} doesn't reference {table}: {migrations[mig_id]}"
        )


# --------------------------------------------------------------------------- #
# Real-QuestDB tests — require a running QuestDB on the host                  #
# --------------------------------------------------------------------------- #


real_questdb = pytest.mark.real_questdb


@real_questdb
def test_d03_signal_id_column_exists_in_live_schema():
    from shared.questdb_client import get_cursor
    with get_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM p3_d03_trade_outcome_log")
        cols = {row[0]: row[1] for row in cur.fetchall()}
    assert "signal_id" in cols
    assert str(cols["signal_id"]).upper() == "STRING"


@real_questdb
def test_d03_signal_id_round_trip():
    from shared.questdb_client import get_cursor
    from tests._qdb_helpers import wait_for_row
    trade_id = f"TEST-SIGID-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    sig_id = f"SIG-{uuid.uuid4()}"
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d03_trade_outcome_log
               (trade_id, signal_id, user_id, account_id, asset, direction,
                outcome, ts)
               VALUES (%s, %s, 'test_user', 'test_acct', 'ES', 1,
                       'SYNTHETIC', now())""",
            (trade_id, sig_id),
        )
        row = wait_for_row(
            cur,
            "SELECT signal_id FROM p3_d03_trade_outcome_log "
            "WHERE trade_id = %s LATEST ON ts PARTITION BY trade_id",
            (trade_id,),
        )
    assert row is not None, "row not visible after WAL wait"
    assert row[0] == sig_id


@real_questdb
def test_d03_signal_id_nullable_for_legacy_rows():
    """Belt-and-braces: legacy writers that don't supply signal_id must still
    be insertable (column is nullable)."""
    from shared.questdb_client import get_cursor
    from tests._qdb_helpers import wait_for_row
    trade_id = f"LEGACY-NULL-SIG-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d03_trade_outcome_log
               (trade_id, user_id, account_id, asset, direction,
                outcome, ts)
               VALUES (%s, 'test_user', 'test_acct', 'ES', 1,
                       'SYNTHETIC', now())""",
            (trade_id,),
        )
        # Poll on trade_id (always set) so an absent NULL signal_id doesn't
        # keep us spinning until timeout.
        row = wait_for_row(
            cur,
            "SELECT trade_id, signal_id FROM p3_d03_trade_outcome_log "
            "WHERE trade_id = %s LATEST ON ts PARTITION BY trade_id",
            (trade_id,),
        )
    assert row is not None, "row not visible after WAL wait"
    assert row[0] == trade_id
    assert row[1] is None or row[1] == ""


@real_questdb
def test_legacy_backfill_assigns_legacy_prefix():
    """Backfill: rows missing signal_id receive ``LEGACY-<uuid>`` IDs."""
    from shared.questdb_client import get_cursor
    from tests._qdb_helpers import wait_for_row
    from scripts.backfill_d03_signal_ids import backfill

    seeded_ids: list[str] = []
    with get_cursor() as cur:
        for i in range(5):
            tid = f"BACKFILL-TEST-{int(time.time())}-{i}-{uuid.uuid4().hex[:6]}"
            seeded_ids.append(tid)
            cur.execute(
                """INSERT INTO p3_d03_trade_outcome_log
                   (trade_id, user_id, account_id, asset, direction,
                    outcome, ts) VALUES (%s, 'backfill_test', 'acct', 'ES', 1,
                                         'SYNTHETIC', now())""",
                (tid,),
            )

    # Make sure all seeded rows are visible to the backfill SELECT before
    # we run it — otherwise the backfill sees zero target rows.
    with get_cursor() as cur:
        for tid in seeded_ids:
            row = wait_for_row(
                cur,
                "SELECT trade_id FROM p3_d03_trade_outcome_log "
                "WHERE trade_id = %s LATEST ON ts PARTITION BY trade_id",
                (tid,),
            )
            assert row is not None, f"seeded row not visible for {tid}"

    backfill(dry_run=False)

    with get_cursor() as cur:
        for tid in seeded_ids:
            row = wait_for_row(
                cur,
                "SELECT signal_id FROM p3_d03_trade_outcome_log "
                "WHERE trade_id = %s AND signal_id IS NOT NULL "
                "LATEST ON ts PARTITION BY trade_id",
                (tid,),
            )
            assert row is not None, f"row missing or signal_id NULL for {tid}"
            assert row[0].startswith("LEGACY-"), (
                f"expected LEGACY- prefix on backfilled row {tid}, got {row[0]!r}"
            )

    assigned_ids = []
    with get_cursor() as cur:
        for tid in seeded_ids:
            cur.execute(
                "SELECT signal_id FROM p3_d03_trade_outcome_log "
                "WHERE trade_id = %s LATEST ON ts PARTITION BY trade_id",
                (tid,),
            )
            assigned_ids.append(cur.fetchone()[0])
    assert len(set(assigned_ids)) == len(assigned_ids), (
        "backfill must produce unique IDs"
    )


@real_questdb
def test_d11_pair_series_round_trip():
    """D11 sharpe_baseline / sharpe_updated / pair_series writeable."""
    from shared.questdb_client import get_cursor
    from tests._qdb_helpers import wait_for_row
    rid = f"TEST-D11-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    pair = '[{"signal_id": "SIG-1", "pnl": 12.5}]'
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d11_pseudotrader_results
               (result_id, update_type, sharpe_baseline, sharpe_updated,
                sharpe_improvement, drawdown_change, winrate_delta, pbo, dsr,
                recommendation, pair_series, ts)
               VALUES (%s, 'AIM_WEIGHT', 0.5, 1.5, 1.0, 0.0, 0.05, 0.3, 0.7,
                       'ADOPT', %s, now())""",
            (rid, pair),
        )
        row = wait_for_row(
            cur,
            "SELECT sharpe_baseline, sharpe_updated, pair_series "
            "FROM p3_d11_pseudotrader_results "
            "WHERE result_id = %s LATEST ON ts PARTITION BY result_id",
            (rid,),
        )
    assert row is not None, "row not visible after WAL wait"
    assert row[0] == 0.5
    assert row[1] == 1.5
    assert row[2] == pair


@real_questdb
def test_d06_phase7_columns_round_trip():
    from shared.questdb_client import get_cursor
    from tests._qdb_helpers import wait_for_row
    iid = f"TEST-D06-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d06_injection_history
               (injection_id, asset, candidate, current_strategy, expected_new,
                expected_current, pseudo_results, recommendation, status,
                injection_type, outcome, pbo, dsr, transition_days,
                tracking_days, ts)
               VALUES (%s, 'ES', '{}', '{}', 1.0, 0.5, '{}', 'ADOPT',
                       'PENDING', 'NEW', 'OPEN', 0.4, 0.6, 7, 14, now())""",
            (iid,),
        )
        row = wait_for_row(
            cur,
            "SELECT pbo, dsr, transition_days, tracking_days "
            "FROM p3_d06_injection_history "
            "WHERE injection_id = %s LATEST ON ts PARTITION BY injection_id",
            (iid,),
        )
    assert row is not None, "row not visible after WAL wait"
    assert row[0] == 0.4
    assert row[1] == 0.6
    assert row[2] == 7
    assert row[3] == 14
