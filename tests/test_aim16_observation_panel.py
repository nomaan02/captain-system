"""AIM-16 observation panel — deterministic paths."""

import numpy as np

from shared.aim16_observation_panel import OBS_SCHEMA_VERSION, build_observation_panel


def test_obs_schema_version_positive():
    assert OBS_SCHEMA_VERSION >= 1


def test_build_observation_panel_empty_on_questdb_failure(monkeypatch):
    """If QuestDB unreachable, helper returns cold-start-compatible empty arrays."""

    class _BoomCm:
        def __enter__(self):
            raise RuntimeError("questdb unreachable in test")

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

    monkeypatch.setattr(
        "shared.aim16_observation_panel.get_cursor",
        lambda: _BoomCm(),
    )
    obs, pnls, nd = build_observation_panel([], closed_at="2026-04-28T16:00:00-04:00", lookback_days=60)
    assert obs.shape == (0, 7)
    assert pnls.shape == (0,)
    assert nd == 0
