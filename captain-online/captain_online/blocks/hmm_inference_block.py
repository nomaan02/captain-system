"""Online AIM-16 HMM: forward-filter + D26 inference row (Q-11).

Merges training columns from LATEST row; overwrites current_state_probs,
opportunity_weights, prior_alpha carry; advances last_updated."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from shared.aim16_observation_panel import OBS_SCHEMA_VERSION, build_single_observation_vector
from shared.hmm_online_inference import (
    emission_likelihoods,
    filtered_update,
    hmm_params_from_json,
    probs_to_ny_lon_apac,
    smooth_probability_vector,
)
from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")
SMOOTHING_ALPHA = 0.3


def persist_online_hmm_inference(session_id: int, asset_universe: list[str]) -> None:
    """One-step forward filter using latest trained ``hmm_params``; append D26 row."""
    if not asset_universe:
        asset_universe = []

    day = datetime.now(_ET).date()
    sid_int = min(max(int(session_id), 1), 4)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT hmm_params, training_window, n_observations, cold_start,
                   current_state_probs, opportunity_weights, prior_alpha, last_trained
              FROM p3_d26_hmm_opportunity_state
             ORDER BY last_updated DESC LIMIT 1
            """
        )
        row = cur.fetchone()

    if not row or not row[0]:
        logger.debug("[aim16-online] persist skipped — missing hmm_params snapshot")
        return

    hmm_blob, tw, n_obs_train, cold_train, csp_blob, ow_blob, prior_blob, last_train_ts = row
    tw = tw or 60
    n_obs_train = n_obs_train or 0

    if last_train_ts is None:
        last_train_ts = datetime.now()
    if not hp or "pi" not in hp:
        return
    try:
        pi0 = np.asarray(hp["pi"], dtype=float).reshape(-1)
        A = np.asarray(hp["A"], dtype=float)
        mu = np.asarray(hp["mu"], dtype=float)
        sg = np.asarray(hp["sigma"], dtype=float)
    except (ValueError, TypeError) as exc:
        logger.warning("[aim16-online] bad hmm_params: %s", exc)
        return

    pi0 /= pi0.sum() + 1e-18

    if csp_blob:
        raw = json.loads(csp_blob) if isinstance(csp_blob, str) else csp_blob
        pi_prev = np.asarray(raw, dtype=float).reshape(-1)
        pi_prev /= pi_prev.sum() + 1e-18
    else:
        pi_prev = pi0.copy()

    prior_dict: dict = {}
    if prior_blob:
        prior_dict = (
            json.loads(prior_blob)
            if isinstance(prior_blob, str)
            else (prior_blob if isinstance(prior_blob, dict) else {})
        )

    prev_smooth = prior_dict.get("smoothed_probs")
    if isinstance(prev_smooth, list) and len(prev_smooth) == 3:
        prev_smooth_vec = np.asarray(prev_smooth, dtype=float)
        prev_smooth_vec /= prev_smooth_vec.sum() + 1e-18
    else:
        prev_smooth_vec = None

    _prev_pnl_raw = prior_dict.get("last_session_slot_pnl", 0.0)
    prev_slot_pnl = float(_prev_pnl_raw) if _prev_pnl_raw is not None else 0.0
    x_vec = build_single_observation_vector(
        sess_date=day,
        session_int=sid_int,
        asset_universe=asset_universe,
        prev_session_pnl=prev_slot_pnl,
    )

    lik = emission_likelihoods(x_vec, mu, sg)
    post = filtered_update(pi_prev, A, lik)
    smoothed = smooth_probability_vector(post, prev_smooth_vec, smoothing=SMOOTHING_ALPHA)

    prior_dict["smoothed_probs"] = smoothed.round(12).tolist()
    prior_dict["last_session_slot_pnl"] = float(x_vec[4])
    prior_dict["obs_schema_version"] = OBS_SCHEMA_VERSION

    opp_weights = probs_to_ny_lon_apac(smoothed)

    csp_out = json.dumps(post.round(12).tolist())
    ow_out = json.dumps(opp_weights)
    pa_out = json.dumps(prior_dict)

    hmm_store = hmm_blob if isinstance(hmm_blob, str) else json.dumps(hp)

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO p3_d26_hmm_opportunity_state
            (hmm_params, current_state_probs, opportunity_weights,
             prior_alpha, last_trained, training_window, n_observations,
             cold_start, last_updated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
            """,
            (
                hmm_store,
                csp_out,
                ow_out,
                pa_out,
                last_train_ts,
                tw,
                n_obs_train,
                bool(cold_train) if cold_train is not None else True,
            ),
        )

    logger.info(
        "[aim16-online] D26 inference persist session_id=%s opp=%s schema=%s",
        session_id,
        opp_weights,
        OBS_SCHEMA_VERSION,
    )
