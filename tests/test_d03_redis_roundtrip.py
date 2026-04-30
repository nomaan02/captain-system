"""Phase B: trade outcome stream payload preserves Decimal monetary fields."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from shared.decimal_json import loads_decimal
from shared.redis_client import publish_to_stream


def test_publish_trade_outcome_stream_roundtrip_monetary():
    fake = MagicMock()
    with patch("shared.redis_client.get_redis_client", return_value=fake):
        publish_to_stream(
            "stream:trade_outcomes",
            {
                "user_id": "u1",
                "asset": "ES",
                "pnl": Decimal("123.45"),
                "commission": Decimal("2.80"),
                "direction": 1,
                "contracts": 2,
            },
        )
    raw = fake.xadd.call_args[0][1]["payload"]
    data = loads_decimal(raw, coerce_json_int=False)
    assert data["pnl"] == Decimal("123.45")
    assert data["commission"] == Decimal("2.80")
    assert data["direction"] == 1
    assert data["contracts"] == 2
