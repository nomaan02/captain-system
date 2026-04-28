# region imports
from AlgorithmImports import *
# endregion
"""Two-phase version rollback (Phase 11 / F-08 / doc 32 Version Snapshot Policy)."""

from unittest.mock import patch

import pytest

import captain_offline.blocks.version_snapshot as vs


class _FakeRedis:
    """Minimal Redis stub for proposal keys (set/get + pub/sub)."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def set(self, key, val, ex=None):
        self.store[key] = val
        return True

    def get(self, key):
        return self.store.get(key)

    def publish(self, *_a, **_k):
        return 1


def _d01_state(rows):
    return {"component": "P3-D01", "rows": rows}


def _d01_row(**kw):
    base = {
        "aim_id": 1,
        "asset_id": "ES",
        "status": "ACTIVE",
        "model_object": "{}",
        "warmup_progress": 1.0,
        "current_modifier": None,
        "last_retrained": None,
        "missing_data_rate_30d": 0.0,
    }
    base.update(kw)
    return base


@pytest.fixture
def fake_redis(monkeypatch):
    fr = _FakeRedis()
    monkeypatch.setattr(vs, "get_redis_client", lambda: fr)
    return fr


@patch.object(vs, "snapshot_before_update")
@patch.object(vs, "_run_rollback_comparison")
@patch.object(vs, "_get_version")
@patch.object(vs, "get_current_state")
def test_request_reject_does_not_persist_proposal(
    mock_gcs, mock_gv, mock_cmp, _snap, fake_redis,
):
    vid = "00000000-0000-0000-0000-000000000001"
    mock_gv.return_value = {
        "version_id": vid,
        "component": "P3-D01",
        "state": _d01_state([_d01_row()]),
    }
    mock_gcs.return_value = _d01_state([_d01_row(missing_data_rate_30d=0.5)])
    mock_cmp.return_value = {"recommendation": "REJECT", "reason": "no"}

    out = vs.request_rollback("P3-D01", vid, "admin-a")
    assert out["status"] == "REJECTED"
    assert len(fake_redis.store) == 0


@patch.object(vs, "snapshot_before_update")
@patch.object(vs, "_run_rollback_comparison")
@patch.object(vs, "_get_version")
@patch.object(vs, "get_current_state")
def test_request_adopt_does_not_call_snapshot_before_commit(
    mock_gcs, mock_gv, mock_cmp, mock_snap, fake_redis,
):
    vid = "00000000-0000-0000-0000-000000000002"
    tgt = _d01_state([_d01_row()])
    mock_gv.return_value = {
        "version_id": vid,
        "component": "P3-D01",
        "state": tgt,
    }
    mock_gcs.return_value = _d01_state([_d01_row(missing_data_rate_30d=0.1)])
    mock_cmp.return_value = {"recommendation": "ADOPT", "reason": "ok"}

    out = vs.request_rollback("P3-D01", vid, "admin-a")
    assert out["status"] == "PENDING_APPROVAL"
    assert "rollback_request_id" in out
    assert "approval_token" in out
    mock_snap.assert_not_called()


@patch.object(vs, "_run_regression_tests", return_value=True)
@patch.object(vs, "_restore_state")
@patch.object(vs, "snapshot_before_update", return_value="undo-v1")
@patch.object(vs, "get_current_state")
@patch.object(vs, "_get_version")
@patch.object(vs, "_run_rollback_comparison")
def test_commit_wrong_token(
    mock_cmp, mock_gv, mock_gcs, _snap, _rest, _reg, fake_redis,
):
    vid = "00000000-0000-0000-0000-000000000003"
    tgt = _d01_state([_d01_row()])
    mock_gv.return_value = {
        "version_id": vid,
        "component": "P3-D01",
        "state": tgt,
    }
    mock_gcs.return_value = _d01_state([_d01_row(missing_data_rate_30d=0.2)])
    mock_cmp.return_value = {"recommendation": "ADOPT", "reason": "ok"}

    req = vs.request_rollback("P3-D01", vid, "admin-a")
    rid = req["rollback_request_id"]
    bad = vs.commit_rollback(rid, "admin-b", "wrong-token")
    assert bad["status"] == "REJECTED"
    assert bad["reason"] == "INVALID_APPROVAL_PROOF"


@patch.object(vs, "_run_regression_tests", return_value=True)
@patch.object(vs, "_restore_state")
@patch.object(vs, "snapshot_before_update", return_value="undo-v1")
@patch.object(vs, "get_current_state")
@patch.object(vs, "_get_version")
@patch.object(vs, "_run_rollback_comparison")
def test_commit_success_and_idempotent(
    mock_cmp, mock_gv, mock_gcs, mock_snap, mock_rest, _reg, fake_redis,
):
    vid = "00000000-0000-0000-0000-000000000004"
    tgt = _d01_state([_d01_row()])
    mock_gv.return_value = {
        "version_id": vid,
        "component": "P3-D01",
        "state": tgt,
    }
    mock_gcs.return_value = _d01_state([_d01_row(missing_data_rate_30d=0.05)])
    mock_cmp.return_value = {"recommendation": "ADOPT", "reason": "ok"}

    req = vs.request_rollback("P3-D01", vid, "admin-a")
    tok = req["approval_token"]
    rid = req["rollback_request_id"]

    c1 = vs.commit_rollback(rid, "admin-b", tok)
    assert c1["status"] == "COMPLETED"
    assert c1["undo_version_id"] == "undo-v1"
    mock_snap.assert_called_once()
    assert mock_rest.called

    mock_snap.reset_mock()
    mock_rest.reset_mock()
    c2 = vs.commit_rollback(rid, "admin-b", tok)
    assert c2["status"] == "ALREADY_COMPLETED"
    mock_snap.assert_not_called()
    mock_rest.assert_not_called()


@patch.object(vs, "_run_regression_tests", return_value=True)
@patch.object(vs, "_restore_state")
@patch.object(vs, "snapshot_before_update", return_value="undo-v1")
@patch.object(vs, "get_current_state")
@patch.object(vs, "_get_version")
@patch.object(vs, "_run_rollback_comparison")
def test_two_distinct_requests_distinct_ids(
    mock_cmp, mock_gv, mock_gcs, _snap, _rest, _reg, fake_redis,
):
    vid = "00000000-0000-0000-0000-000000000005"
    tgt = _d01_state([_d01_row()])
    mock_gv.return_value = {
        "version_id": vid,
        "component": "P3-D01",
        "state": tgt,
    }
    mock_gcs.return_value = _d01_state([_d01_row(missing_data_rate_30d=0.0)])
    mock_cmp.return_value = {"recommendation": "ADOPT", "reason": "ok"}

    a = vs.request_rollback("P3-D01", vid, "admin-a")
    b = vs.request_rollback("P3-D01", vid, "admin-a")
    assert a["rollback_request_id"] != b["rollback_request_id"]
    assert a["approval_token"] != b["approval_token"]


def test_rollback_to_version_raises():
    with pytest.raises(NotImplementedError):
        vs.rollback_to_version("P3-D01", "x", "admin")
