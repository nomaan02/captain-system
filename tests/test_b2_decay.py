# region imports
from AlgorithmImports import *
# endregion
"""Decay level CH_ALERTS payload tests (Phase 2 B2-4)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from shared.redis_client import CH_ALERTS

from captain_offline.blocks.b2_level_escalation import (
    trigger_level2,
    trigger_level3,
)


@patch("captain_offline.blocks.b2_level_escalation.get_cursor")
@patch("captain_offline.blocks.b2_level_escalation.get_redis_client")
def test_decay_level2_alert_has_message(mock_get_redis, mock_get_cursor):
    mock_r = MagicMock()
    mock_get_redis.return_value = mock_r
    mock_c = MagicMock()
    mock_c.__enter__ = MagicMock(return_value=mock_c)
    mock_c.__exit__ = MagicMock(return_value=False)
    mock_get_cursor.return_value = mock_c

    trigger_level2("ES", severity=0.85, source="BOCPD")
    args = mock_r.publish.call_args[0]
    assert args[0] == CH_ALERTS
    payload = json.loads(args[1])
    assert "message" in payload
    assert "Level 2" in payload["message"]
    assert "ES" in payload["message"]
    assert "Sizing reduced" in payload["message"]
    assert payload["event_type"] == "DECAY_LEVEL_2"
    assert payload.get("notif_id")


@patch("shared.questdb_client.update_d00_fields")
@patch("captain_offline.blocks.b2_level_escalation.get_cursor")
@patch("captain_offline.blocks.b2_level_escalation.get_redis_client")
def test_decay_level3_alert_has_message(mock_get_redis, mock_get_cursor, _mock_d00):
    mock_r = MagicMock()
    mock_get_redis.return_value = mock_r
    mock_c = MagicMock()
    mock_c.__enter__ = MagicMock(return_value=mock_c)
    mock_c.__exit__ = MagicMock(return_value=False)
    mock_get_cursor.return_value = mock_c

    trigger_level3("ES", source="BOCPD_sustained")
    args = mock_r.publish.call_args[0]
    assert args[0] == CH_ALERTS
    payload = json.loads(args[1])
    assert "message" in payload
    assert "STRATEGY REVIEW" in payload["message"]
    assert "ES" in payload["message"]
    assert payload["event_type"] == "DECAY_LEVEL_3"
    assert payload["priority"] == "CRITICAL"
