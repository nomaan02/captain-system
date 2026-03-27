# region imports
from AlgorithmImports import *
# endregion
"""AIM state and DMA weight fixtures for regression tests."""


def make_aim_states_all_active(asset_id="ES", aim_ids=None):
    """All specified AIMs ACTIVE for an asset."""
    if aim_ids is None:
        aim_ids = [1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16]  # excl 4(IVTS stub), 5(DEFERRED), 14(always 1.0)
    by_asset_aim = {}
    for aid in aim_ids:
        by_asset_aim[(asset_id, aid)] = {
            "status": "ACTIVE",
            "warmup_progress": 1.0,
            "zero_weight_trades": 0,
        }
    return {"by_asset_aim": by_asset_aim, "global": {}}


def make_aim_states_all_suppressed(asset_id="ES", aim_ids=None):
    """All AIMs SUPPRESSED for an asset."""
    if aim_ids is None:
        aim_ids = [1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16]
    by_asset_aim = {}
    for aid in aim_ids:
        by_asset_aim[(asset_id, aid)] = {
            "status": "SUPPRESSED",
            "warmup_progress": 1.0,
            "zero_weight_trades": 25,
        }
    return {"by_asset_aim": by_asset_aim, "global": {}}


def make_aim_states_mixed(asset_id="ES"):
    """3 ACTIVE (1,2,3), rest SUPPRESSED."""
    by_asset_aim = {}
    active_ids = [1, 2, 3]
    suppressed_ids = [6, 7, 8, 9, 10, 11, 12, 13, 15, 16]
    for aid in active_ids:
        by_asset_aim[(asset_id, aid)] = {"status": "ACTIVE", "warmup_progress": 1.0, "zero_weight_trades": 0}
    for aid in suppressed_ids:
        by_asset_aim[(asset_id, aid)] = {"status": "SUPPRESSED", "warmup_progress": 1.0, "zero_weight_trades": 25}
    return {"by_asset_aim": by_asset_aim, "global": {}}


def make_aim_weights(asset_id="ES", aim_ids=None, uniform=True, custom_weights=None):
    """DMA weights for AIMs. Uniform or custom."""
    if aim_ids is None:
        aim_ids = [1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16]
    n = len(aim_ids)
    weights = {}
    for i, aid in enumerate(aim_ids):
        if custom_weights and aid in custom_weights:
            w = custom_weights[aid]
        elif uniform:
            w = 1.0 / n
        else:
            w = 0.0
        weights[(asset_id, aid)] = {
            "inclusion_probability": w,
            "inclusion_flag": w > 0.02,
            "recent_effectiveness": 0.5,
            "days_below_threshold": 0,
        }
    return weights


def make_aim_weights_none_included(asset_id="ES", aim_ids=None):
    """All AIMs have inclusion_flag=False."""
    if aim_ids is None:
        aim_ids = [1, 2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16]
    weights = {}
    for aid in aim_ids:
        weights[(asset_id, aid)] = {
            "inclusion_probability": 0.01,
            "inclusion_flag": False,
            "recent_effectiveness": 0.0,
            "days_below_threshold": 30,
        }
    return weights
