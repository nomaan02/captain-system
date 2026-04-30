# region imports
from AlgorithmImports import *
# endregion
"""Shared pytest fixtures and mocks for Captain regression tests.

Mocking strategy:
- DB helpers (get_cursor, QuestDB queries) are mocked at the module level
- Redis helpers (get_redis_client, publish) are mocked at the module level
- Pure computation functions are tested directly with synthetic dicts
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Host-test stubs: optional WebSocket deps that ship only inside the
# captain-offline / captain-online containers. Stub them so block modules
# that do `from shared.topstep_stream import quote_cache` (transitively
# importing pysignalr) can be loaded for unit tests on a bare host.
# ---------------------------------------------------------------------------

def _stub_module(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = MagicMock()


try:  # pragma: no cover — hand-rolled detection
    import pysignalr  # type: ignore  # noqa: F401
except Exception:
    _stub_module("pysignalr")
    _stub_module("pysignalr.client")
    _stub_module("pysignalr.messages")
    _stub_module("pysignalr.transport")
    _stub_module("pysignalr.transport.websocket_transport")

# Add captain-system paths so block imports work without Docker
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
sys.path.insert(0, str(_root / "captain-online"))
sys.path.insert(0, str(_root / "captain-offline"))
sys.path.insert(0, str(_root / "captain-command"))

from tests.fixtures.synthetic_data import (
    make_features, make_regime_model_binary, make_regime_model_neutral,
    make_locked_strategy, make_ewma_states, make_kelly_params, make_assets_detail,
)
from tests.fixtures.user_fixtures import (
    make_user_silo, make_tsm_config, make_tsm_configs,
    make_silo_drawdown_blocked, make_tsm_pass_eval, make_tsm_mdd_tight,
)
from tests.fixtures.aim_fixtures import (
    make_aim_states_all_active, make_aim_states_all_suppressed,
    make_aim_states_mixed, make_aim_weights, make_aim_weights_none_included,
)


# ---------------------------------------------------------------------------
# Mock the shared DB/Redis modules BEFORE any block imports
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_shared_db(request, monkeypatch):
    """Mock shared.questdb_client.get_cursor globally (skipped for @pytest.mark.real_questdb)."""
    if request.node.get_closest_marker("real_questdb"):
        return None

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []

    mock_get_cursor = MagicMock(return_value=mock_cursor)

    monkeypatch.setattr("shared.questdb_client.get_cursor", mock_get_cursor)
    return mock_cursor


@pytest.fixture(autouse=True)
def mock_shared_redis(monkeypatch):
    """Mock shared.redis_client globally."""
    mock_client = MagicMock()
    mock_client.publish = MagicMock(return_value=1)

    monkeypatch.setattr("shared.redis_client.get_redis_client", MagicMock(return_value=mock_client))
    return mock_client


# ---------------------------------------------------------------------------
# Convenience fixtures wrapping synthetic data factories
# ---------------------------------------------------------------------------

@pytest.fixture
def es_features():
    return make_features("ES")


@pytest.fixture
def es_regime_neutral():
    return make_regime_model_neutral("ES")


@pytest.fixture
def es_regime_binary():
    return make_regime_model_binary("ES", phi=0.20)


@pytest.fixture
def es_strategy():
    return make_locked_strategy("ES")


@pytest.fixture
def es_ewma():
    return make_ewma_states("ES")


@pytest.fixture
def es_kelly():
    return make_kelly_params("ES")


@pytest.fixture
def es_detail():
    return make_assets_detail("ES")


@pytest.fixture
def default_user_silo():
    return make_user_silo()


@pytest.fixture
def default_tsm_configs():
    return make_tsm_configs()
