"""Phase 6: apply_hmm_session_allocation is observability-only — no mutation.

Confirms that contract counts pass through unchanged after the function call,
since per-session enforcement now lives in B4/B5C as a dollar budget.
"""
from unittest.mock import patch


def test_returns_final_contracts_unchanged_when_hmm_state_is_none():
    from captain_online.blocks.b5_trade_selection import apply_hmm_session_allocation

    final_contracts = {
        "ES":   {"21855714": 4},
        "NQ":   {"21855714": 2},
        "MES":  {"21855714": 6},
    }
    expected = {k: dict(v) for k, v in final_contracts.items()}

    with patch(
        "captain_online.blocks.b5_trade_selection._load_hmm_opportunity_state",
        return_value=None,
    ):
        result = apply_hmm_session_allocation(
            selected_trades=["ES", "NQ", "MES"],
            final_contracts=final_contracts,
            accounts=["21855714"],
            session_id=1,
        )

    assert result == expected, "function must not mutate contract counts"


def test_returns_final_contracts_unchanged_in_cold_start():
    from captain_online.blocks.b5_trade_selection import apply_hmm_session_allocation

    final_contracts = {"NKD": {"21855714": 5}}
    expected = {k: dict(v) for k, v in final_contracts.items()}

    with patch(
        "captain_online.blocks.b5_trade_selection._load_hmm_opportunity_state",
        return_value={
            "opportunity_weights": "{}",
            "n_observations": 5,
            "cold_start": True,
        },
    ):
        result = apply_hmm_session_allocation(
            selected_trades=["NKD"],
            final_contracts=final_contracts,
            accounts=["21855714"],
            session_id=3,  # APAC
        )

    # Pre-2026-05-06: this would have multiplied 5 × 1/3 = 1 (with floor).
    # Post-deprecation: stays at 5; per-session enforcement lives in B4/B5C.
    assert result["NKD"]["21855714"] == 5
    assert result == expected


def test_returns_final_contracts_unchanged_in_full_hmm():
    from captain_online.blocks.b5_trade_selection import apply_hmm_session_allocation

    final_contracts = {"ES": {"21855714": 10}}
    expected = {k: dict(v) for k, v in final_contracts.items()}

    with patch(
        "captain_online.blocks.b5_trade_selection._load_hmm_opportunity_state",
        return_value={
            "opportunity_weights": '{"NY": 0.62, "LON": 0.25, "APAC": 0.13}',
            "n_observations": 100,
            "cold_start": False,
        },
    ):
        result = apply_hmm_session_allocation(
            selected_trades=["ES"],
            final_contracts=final_contracts,
            accounts=["21855714"],
            session_id=1,  # NY
        )

    # Pre-2026-05-06: 10 * 0.62 = 6 contracts. Post: stays at 10.
    assert result["ES"]["21855714"] == 10
    assert result == expected
