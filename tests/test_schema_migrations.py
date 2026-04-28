"""Schema migration tests for Phase 1."""
import time
from datetime import datetime

import pytest
from psycopg2 import OperationalError
from shared.questdb_client import get_cursor

pytestmark = pytest.mark.real_questdb


def _skip_if_no_questdb():
    """CI / local host may not run QuestDB; skip instead of failing."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    except OperationalError:
        pytest.skip("QuestDB not reachable")


def test_b1_p2_d07_table_exists():
    """Schema integrity: p2_d07_regime_models table is created."""
    with get_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM p2_d07_regime_models")
        cols = {row[0] for row in cur.fetchall()}
    assert "asset" in cols
    assert "model_type" in cols
    assert "pettersson_threshold" in cols
    assert "last_updated" in cols


def test_b1_p2_d07_round_trip():
    """Round-trip: insert one row, read it back, verify shape."""
    now_ts = datetime.utcnow().isoformat()
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p2_d07_regime_models
               (asset, model_type, feature_list, pettersson_threshold,
                regime_label, n_training_obs, cv_score, trained_at, last_updated)
               VALUES ('ES', 'BINARY_ONLY', '["f1","f2"]', 0.55,
                       'REGIME_NEUTRAL', 100, 0.62, %s, %s)""",
            (now_ts, now_ts),
        )
        cur.execute(
            "SELECT asset, model_type FROM p2_d07_regime_models "
            "WHERE asset = 'ES' LATEST ON last_updated PARTITION BY asset"
        )
        row = cur.fetchone()
    assert row[0] == "ES"
    assert row[1] == "BINARY_ONLY"


def test_b1_p2_d07_backwards_compat():
    """Backwards compat: table starts empty and SELECT does not raise."""
    with get_cursor() as cur:
        cur.execute("SELECT count() FROM p2_d07_regime_models")
        row = cur.fetchone()
    assert row[0] >= 0  # any non-negative count is acceptable


def test_b2_d03_model_m_column_exists():
    """Schema integrity: model_m INT column present in p3_d03_trade_outcome_log."""
    with get_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM p3_d03_trade_outcome_log")
        cols = {row[0]: row[1] for row in cur.fetchall()}
    assert "model_m" in cols
    assert str(cols["model_m"]).upper() == "INT"


def test_b2_d03_model_m_round_trip():
    """Round-trip: insert a row with model_m, read it back, verify value."""
    trade_id = f"TEST-MODELM-{int(time.time())}"
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d03_trade_outcome_log
               (trade_id, user_id, account_id, asset, direction,
                outcome, model_m, ts)
               VALUES (%s, 'test_user', 'test_acct', 'ES', 1,
                       'SYNTHETIC', 7, now())""",
            (trade_id,),
        )
        cur.execute(
            "SELECT model_m FROM p3_d03_trade_outcome_log "
            "WHERE trade_id = %s LATEST ON ts PARTITION BY trade_id",
            (trade_id,),
        )
        row = cur.fetchone()
    assert row[0] == 7


def test_b2_d03_model_m_backwards_compat():
    """Backwards compat: existing rows without model_m return NULL gracefully."""
    trade_id = f"LEGACY-ROW-{int(time.time())}"
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d03_trade_outcome_log
               (trade_id, user_id, account_id, asset, direction,
                outcome, ts)
               VALUES (%s, 'test_user', 'test_acct', 'ES', 1,
                       'SYNTHETIC', now())""",
            (trade_id,),
        )
        cur.execute(
            "SELECT model_m FROM p3_d03_trade_outcome_log "
            "WHERE trade_id = %s LATEST ON ts PARTITION BY trade_id",
            (trade_id,),
        )
        row = cur.fetchone()
    # model_m is nullable — NULL is the correct value for legacy rows
    assert row[0] is None


def test_b3_d22b_table_exists():
    """Schema integrity: p3_d22b_asset_rerun_status table exists with correct columns."""
    with get_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM p3_d22b_asset_rerun_status")
        cols = {row[0] for row in cur.fetchall()}
    assert "asset" in cols
    assert "last_p1p2_rerun_ts" in cols
    assert "rerun_trigger" in cols
    assert "last_updated" in cols


def test_b3_d22b_round_trip():
    """Round-trip: upsert two rows for same asset, LATEST ON reads most recent."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d22b_asset_rerun_status
               (asset, last_p1p2_rerun_ts, rerun_trigger, last_updated)
               VALUES ('ES', now(), 'TEST_RUN_1', now())"""
        )
        time.sleep(0.01)
        cur.execute(
            """INSERT INTO p3_d22b_asset_rerun_status
               (asset, last_p1p2_rerun_ts, rerun_trigger, last_updated)
               VALUES ('ES', now(), 'TEST_RUN_2', now())"""
        )
        cur.execute(
            "SELECT rerun_trigger FROM p3_d22b_asset_rerun_status "
            "LATEST ON last_updated PARTITION BY asset WHERE asset = 'ES'"
        )
        row = cur.fetchone()
    assert row[0] == "TEST_RUN_2"


def test_b3_compute_d3_empty_table_graceful():
    """Backwards compat: empty-table SELECT for D22b does not raise."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT asset, last_p1p2_rerun_ts FROM p3_d22b_asset_rerun_status "
            "LATEST ON last_updated PARTITION BY asset"
        )
        rows = cur.fetchall()
    assert isinstance(rows, list)  # empty list is valid


def test_b4_d26_column_set_ratification():
    """Ratification: p3_d26_hmm_opportunity_state has exactly the 9 ratified columns."""
    _skip_if_no_questdb()
    expected = {
        "hmm_params", "current_state_probs", "opportunity_weights",
        "prior_alpha", "last_trained", "training_window",
        "n_observations", "cold_start", "last_updated",
    }
    with get_cursor() as cur:
        cur.execute("SHOW COLUMNS FROM p3_d26_hmm_opportunity_state")
        actual = {row[0] for row in cur.fetchall()}
    assert actual == expected, f"Column drift: extra={actual-expected}, missing={expected-actual}"
