"""D26 offline save merges prior inference JSON columns (Q-11)."""

import json
from unittest.mock import MagicMock

import pytest

pytest.importorskip("numpy")


def test_save_hmm_state_reuses_prior_inference_json_columns(monkeypatch):
    pytest.importorskip("hmmlearn")
    from captain_offline.blocks import b1_aim16_hmm

    prior_cs = json.dumps([0.1, 0.2, 0.7])
    prior_ow = json.dumps({"NY": 0.4, "LON": 0.3, "APAC": 0.3})

    cur_sel = MagicMock()
    cur_sel.fetchone.return_value = (prior_cs, prior_ow, "{}")

    cur_ins = MagicMock()

    ctx_sel = MagicMock(__enter__=MagicMock(return_value=cur_sel), __exit__=MagicMock())
    ctx_ins = MagicMock(__enter__=MagicMock(return_value=cur_ins), __exit__=MagicMock())

    gc = MagicMock(side_effect=[ctx_sel, ctx_ins])
    monkeypatch.setattr(b1_aim16_hmm, "get_cursor", gc)

    training = {
        "hmm_params": {
            "pi": [1 / 3, 1 / 3, 1 / 3],
            "A": [[1 / 3] * 3] * 3,
            "mu": [[0.0] * 7] * 3,
            "sigma": [[1.0] * 7] * 3,
        },
        "current_state_probs": [1 / 3] * 3,
        "opportunity_weights": {},
        "prior_alpha": {},
        "training_window": 60,
        "n_observations": 10,
        "cold_start": False,
    }

    b1_aim16_hmm.save_hmm_state(training)

    assert cur_ins.execute.called
    args = cur_ins.execute.call_args[0][1]
    assert args[1] == prior_cs
    assert args[2] == prior_ow
