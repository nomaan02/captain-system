# region imports
from AlgorithmImports import *
# endregion
"""Paper trader trade outcome transport (Phase 2 B2-5)."""

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shared.redis_client import STREAM_TRADE_OUTCOMES

_root = Path(__file__).resolve().parent.parent
if str(_root / "scripts") not in sys.path:
    sys.path.insert(0, str(_root / "scripts"))

_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", _dotenv)
_ws = types.ModuleType("websocket")
sys.modules.setdefault("websocket", _ws)

_pys = types.ModuleType("pysignalr")
_pys_client = types.ModuleType("pysignalr.client")


class _DummySignalRClient:
    pass


_pys_client.SignalRClient = _DummySignalRClient
sys.modules.setdefault("pysignalr", _pys)
sys.modules.setdefault("pysignalr.client", _pys_client)

paper_trader = importlib.import_module("paper_trader")


@patch("paper_trader.publish_to_stream")
@patch("paper_trader.get_cursor")
@patch("paper_trader.get_redis_client")
def test_paper_trader_publishes_to_stream(
    mock_get_redis, mock_get_cursor, mock_publish_to_stream
):
    """paper_trader must publish trade outcomes to STREAM_TRADE_OUTCOMES, not pub/sub."""
    mock_c = MagicMock()
    mock_c.__enter__ = MagicMock(return_value=mock_c)
    mock_c.__exit__ = MagicMock(return_value=False)
    mock_get_cursor.return_value = mock_c

    mock_r = MagicMock()
    mock_r.publish = MagicMock()
    mock_get_redis.return_value = mock_r

    pt = paper_trader.PaperTrader()
    pos = paper_trader.Position(
        trade_id="t1",
        signal_id="s1",
        direction=1,
        entry_price=5000.0,
        contracts=1,
        tp=5100.0,
        sl=4900.0,
    )
    pos.status = "TP"
    pt.positions["t1"] = pos

    pt._close_position("t1", "TP", 5099.0)

    mock_publish_to_stream.assert_called_once()
    stream_name, payload = mock_publish_to_stream.call_args[0]
    assert stream_name == STREAM_TRADE_OUTCOMES
    assert payload.get("trade_id") == "t1"
    for c in mock_r.publish.call_args_list:
        assert c[0][0] != "captain:trade_outcomes", "pub/sub trade_outcomes deprecated"
