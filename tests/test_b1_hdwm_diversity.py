# region imports
from AlgorithmImports import *
# endregion
"""F-10: HDWM diversity recovery per PG-03 (trigger, argmax set, active count)."""

from unittest.mock import MagicMock, patch

from captain_offline.blocks.b1_hdwm_diversity import (
    _count_active_aims,
    run_hdwm_diversity_check,
)


def test_hdwm_recovers_when_no_active_in_type_even_without_suppressed():
    """Recovery when no AIM in type is ACTIVE (e.g. all WARM_UP / ELIGIBLE)."""
    with patch(
        "captain_offline.blocks.b1_hdwm_diversity._count_active_aims",
        return_value=2,
    ), patch(
        "captain_offline.blocks.b1_hdwm_diversity._get_aim_status",
        return_value="WARM_UP",
    ), patch(
        "captain_offline.blocks.b1_hdwm_diversity._get_recent_effectiveness",
        side_effect=lambda aid, asset: {1: 0.1, 2: 0.5, 3: 0.2}.get(aid, 0.0),
    ), patch(
        "captain_offline.blocks.b1_hdwm_diversity._reactivate_aim",
    ) as mock_react:
        run_hdwm_diversity_check("ES")
    mock_react.assert_called()
    # options group [1,2,3] — highest effectiveness is AIM-2
    calls = [c[0] for c in mock_react.call_args_list]
    assert any(c[0] == 2 and c[1] == "ES" for c in calls)


def test_hdwm_argmax_over_full_seed_set():
    """Argmax includes non-SUPPRESSED AIMs; best score may be WARM_UP."""
    def status_fn(aid, _asset):
        return {1: "SUPPRESSED", 2: "WARM_UP", 3: "ELIGIBLE"}.get(aid, "WARM_UP")

    def eff_fn(aid, _asset):
        return {1: 0.9, 2: 0.95, 3: 0.8}.get(aid, 0.0)

    with patch(
        "captain_offline.blocks.b1_hdwm_diversity._count_active_aims",
        return_value=1,
    ), patch(
        "captain_offline.blocks.b1_hdwm_diversity._get_aim_status",
        side_effect=status_fn,
    ), patch(
        "captain_offline.blocks.b1_hdwm_diversity._get_recent_effectiveness",
        side_effect=eff_fn,
    ), patch(
        "captain_offline.blocks.b1_hdwm_diversity._reactivate_aim",
    ) as mock_react:
        run_hdwm_diversity_check("ES")

    assert mock_react.called
    first_reactivated = mock_react.call_args_list[0][0][0]
    assert first_reactivated == 2


def test_hdwm_skips_when_one_active_in_type():
    """macro_event: one ACTIVE → no recovery for that type."""
    def status_fn(aid, _asset):
        if aid == 6:
            return "ACTIVE"
        if aid == 7:
            return "SUPPRESSED"
        return "WARM_UP"

    with patch(
        "captain_offline.blocks.b1_hdwm_diversity._count_active_aims",
        return_value=5,
    ), patch(
        "captain_offline.blocks.b1_hdwm_diversity._get_aim_status",
        side_effect=status_fn,
    ), patch(
        "captain_offline.blocks.b1_hdwm_diversity._get_recent_effectiveness",
        return_value=0.5,
    ), patch(
        "captain_offline.blocks.b1_hdwm_diversity._reactivate_aim",
    ) as mock_react:
        run_hdwm_diversity_check("NQ")

    for call in mock_react.call_args_list:
        args, _kwargs = call
        assert args[0] not in (6, 7)


@patch("captain_offline.blocks.b1_hdwm_diversity.get_cursor")
def test_count_active_aims_dedupes_history(mock_get_cursor):
    """Latest D01 row per AIM only — ACTIVE then SUPPRESSED → count as not active."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchall.return_value = [(1, "SUPPRESSED")]
    mock_get_cursor.return_value = cur

    assert _count_active_aims("ES") == 0
