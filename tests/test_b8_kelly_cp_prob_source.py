# region imports
from AlgorithmImports import *
# endregion
"""Kelly L1 cp_prob source — Redis primary, QuestDB fallback (Q-07)."""

from unittest.mock import MagicMock, patch

import pytest

from captain_offline.blocks.b8_kelly_update import _get_cp_prob


def _fake_cursor(row):
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = row
    return cur


@patch("captain_offline.blocks.b8_kelly_update.get_cursor")
@patch("captain_offline.blocks.b8_kelly_update.get_redis_client")
def test_redis_hit_skips_questdb(mock_get_redis, mock_get_cursor):
    mock_get_redis.return_value.get.return_value = "0.74"
    cp = _get_cp_prob("ES")
    assert cp == pytest.approx(0.74, abs=1e-9)
    mock_get_cursor.assert_not_called()


@patch("captain_offline.blocks.b8_kelly_update.get_cursor")
@patch("captain_offline.blocks.b8_kelly_update.get_redis_client")
def test_redis_miss_falls_back_to_questdb(mock_get_redis, mock_get_cursor):
    mock_get_redis.return_value.get.return_value = None
    cur = _fake_cursor((0.62,))
    mock_get_cursor.return_value = cur
    assert _get_cp_prob("NQ") == pytest.approx(0.62, abs=1e-9)


@patch("captain_offline.blocks.b8_kelly_update.get_cursor")
@patch("captain_offline.blocks.b8_kelly_update.get_redis_client")
def test_redis_miss_questdb_miss_returns_default(mock_get_redis, mock_get_cursor):
    mock_get_redis.return_value.get.return_value = None
    cur = _fake_cursor(None)
    mock_get_cursor.return_value = cur
    assert _get_cp_prob("CL") == pytest.approx(0.1, abs=1e-9)


@patch("captain_offline.blocks.b8_kelly_update.get_cursor")
@patch("captain_offline.blocks.b8_kelly_update.get_redis_client")
def test_redis_raises_falls_back_to_questdb(mock_get_redis, mock_get_cursor, caplog):
    mock_get_redis.side_effect = RuntimeError("redis down")
    cur = _fake_cursor((0.55,))
    mock_get_cursor.return_value = cur
    with caplog.at_level("WARNING"):
        assert _get_cp_prob("ES") == pytest.approx(0.55, abs=1e-9)
    assert any("Redis read failed" in r.message for r in caplog.records)


@patch("captain_offline.blocks.b8_kelly_update.get_cursor")
@patch("captain_offline.blocks.b8_kelly_update.get_redis_client")
def test_redis_malformed_float_falls_back_to_questdb(mock_get_redis, mock_get_cursor, caplog):
    mock_get_redis.return_value.get.return_value = "NaN"
    cur = _fake_cursor((0.41,))
    mock_get_cursor.return_value = cur
    with caplog.at_level("WARNING"):
        assert _get_cp_prob("ES") == pytest.approx(0.41, abs=1e-9)
