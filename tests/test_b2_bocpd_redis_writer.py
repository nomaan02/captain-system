# region imports
from AlgorithmImports import *
# endregion
"""F-07: Redis mirror for cp_prob after combined D04 persist."""

from unittest.mock import MagicMock, patch

import pytest

from captain_offline.blocks.b2_bocpd import BOCPDDetector, persist_combined_detector_state
from captain_offline.blocks.b2_cusum import CUSUMDetector


class _FakeRedis:
    """Minimal redis stub for cp_prob mirror tests."""

    def __init__(self):
        self._data = {}
        self._ttl = {}

    def set(self, name, value, ex=None):
        self._data[name] = value
        self._ttl[name] = ex

    def get(self, name):
        return self._data.get(name)

    def ttl(self, name):
        t = self._ttl.get(name)
        if t is None:
            return -2
        return int(t)


def _mock_cursor():
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    return cur


@patch("captain_offline.blocks.b2_bocpd.get_redis_client")
@patch("captain_offline.blocks.b2_bocpd.get_cursor")
def test_persist_writes_redis_cp_prob_matching_returned_prob(mock_get_cursor, mock_get_redis):
    fake = _FakeRedis()
    mock_get_redis.return_value = fake
    cur = _mock_cursor()
    mock_get_cursor.return_value = cur

    bocpd_det = BOCPDDetector()
    cp = bocpd_det.update(12.5)
    cusum_det = CUSUMDetector(allowance=0.3)
    cusum_det.update(0.0)

    persist_combined_detector_state("ES", bocpd_det, cusum_det)

    key = "captain:bocpd:ES"
    raw = fake.get(key)
    assert raw is not None
    assert float(raw) == pytest.approx(cp, abs=1e-6)
    ttl = fake.ttl(key)
    assert 0 < ttl <= 7 * 86400

    cur.execute.assert_called()
    args = cur.execute.call_args[0]
    row = args[1]
    assert row[2] == pytest.approx(float(cp), abs=1e-6)


@patch("captain_offline.blocks.b2_bocpd.get_redis_client")
@patch("captain_offline.blocks.b2_bocpd.get_cursor")
def test_redis_set_failure_does_not_raise_and_db_still_written(mock_get_cursor, mock_get_redis, caplog):
    mock_get_redis.return_value.set = MagicMock(side_effect=RuntimeError("redis down"))
    cur = _mock_cursor()
    mock_get_cursor.return_value = cur

    bocpd_det = BOCPDDetector()
    bocpd_det.update(0.5)
    cusum_det = CUSUMDetector(allowance=0.3)
    cusum_det.update(0.1)

    with caplog.at_level("ERROR"):
        persist_combined_detector_state("ES", bocpd_det, cusum_det)

    cur.execute.assert_called()
    assert any("Redis mirror failed" in r.message for r in caplog.records)
