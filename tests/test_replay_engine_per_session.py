"""Phase 7: Replay engine per-session L1/L2/L3 isolation.

Verifies that compute_contracts in shared.replay_engine reads per-session
intraday accumulators (not the global ones), mirroring B5C Phase 4 behaviour
in production. Each session has its own L_t / n_t / l_b independently.
"""
from decimal import Decimal


def _base_config(c=1.0, e=0.01) -> dict:
    """Build a minimal config dict with per-session budget machinery primed."""
    user_capital = 150000.0
    cfg = {
        "user_capital": user_capital,
        "max_contracts": 15,
        "budget_divisor": 20,
        "risk_goal": "GROW_CAPITAL",
        "cb_enabled": True,
        "current_drawdown": 0.0,
        "daily_loss_used": 0.0,
        "mdd_limit": 4500.0,
        "mll_limit": None,
        "topstep_params": {"c": c, "e": e, "p": 0.005, "lambda": 0},
        "_tsm": {
            "fee_per_trade": 2.80,
            "scaling_plan_active": False,
            "account_id": "21855714",
        },
        "regime_probs": {"NKD": {"LOW_VOL": 0.5, "HIGH_VOL": 0.5}},
        "regime_uncertain": {},
        "_intraday_cumulative_pnl_per_session": {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0},
        "_intraday_trade_count_per_session": {1: 0, 2: 0, 3: 0, 4: 0},
        "_intraday_basket_pnl_per_session": {1: {}, 2: {}, 3: {}, 4: {}},
        "_session_shares": {
            1: Decimal("0.3333333333"),
            2: Decimal("0.3333333333"),
            3: Decimal("0.3333333333"),
            4: Decimal("0.3333333333"),
        },
    }
    # SOD per-session budget map: c * e * A * share
    cap = Decimal(str(user_capital))
    cfg["_session_budget_map"] = {
        sid: Decimal(str(c)) * Decimal(str(e)) * cap * cfg["_session_shares"][sid]
        for sid in (1, 2, 3, 4)
    }
    return cfg


def test_per_session_l1_isolated_lon_loss_does_not_block_apac_nkd():
    """Replicates Nomaan's 10-day NKD APAC scenario.

    Setup: c=1.0, e=0.01, A=$150K → L_halt_total=$1500.
    Equal HMM shares → per-session L_halt = $500 each.

    LON took $400 of cumulative |L_t|. Pre-fix: L1 would block APAC NKD
    because abs(400) + rho_NKD = 400 + tiny >= L_halt_global=$1500 was OK,
    BUT wait — pre-fix L_halt = c*e*A = 1500 → 400 + rho < 1500 still allowed.

    After per-session split: APAC sees its OWN L_halt=$500 with L_t=$0
    (because APAC's row hasn't been touched). 0 + small_rho_j << 500 → ALLOW.

    Post-fix invariant: APAC trade is allowed regardless of LON's loss.
    """
    from shared.replay_engine import compute_contracts

    cfg = _base_config()
    cfg["_intraday_cumulative_pnl_per_session"] = {
        1: 0.0,    # NY: untouched
        2: -400.0, # LON: lost $400
        3: 0.0,    # APAC: untouched
        4: 0.0,
    }
    # Pretend LON took 4 trades; APAC took none.
    cfg["_intraday_trade_count_per_session"] = {1: 0, 2: 4, 3: 0, 4: 0}

    spec = {"point_value": 5.0}  # NKD point value
    strategy = {"m": 6, "k": 6, "threshold": 6.0, "oo": 0.85}
    kelly_params = {("NKD", "LOW_VOL", 3): {"kelly_full": 0.05, "shrinkage_factor": 1.0},
                    ("NKD", "HIGH_VOL", 3): {"kelly_full": 0.05, "shrinkage_factor": 1.0}}
    ewma_states = {("NKD", "HIGH_VOL", 3): {"avg_loss": 30.0}}

    result = compute_contracts(
        asset_id="NKD",
        pnl_per_contract=100.0,
        spec=spec,
        kelly_params=kelly_params,
        ewma_states=ewma_states,
        config=cfg,
        strategy=strategy,
        session_id=3,  # APAC
        aim_modifier=1.0,
    )
    # APAC should NOT be blocked by L1 — its session L_t is 0.
    assert result["cb_blocked"] is False, (
        f"APAC L1 wrongly blocked despite session-isolated L_t=0; "
        f"l_t={result['cb_l1_l_t']} l_halt={result['cb_l1_halt']}"
    )
    # And the contract count is non-zero.
    assert result["contracts"] > 0


def test_per_session_l1_blocks_when_session_specific_loss_exceeds_halt():
    """Conversely: when APAC ITSELF has lost $400 (>$500-rho_j) it gets blocked."""
    from shared.replay_engine import compute_contracts

    cfg = _base_config()
    cfg["_intraday_cumulative_pnl_per_session"] = {
        1: 0.0, 2: 0.0,
        3: -480.0,  # APAC consumed $480 of its $500 budget
        4: 0.0,
    }
    spec = {"point_value": 5.0}
    strategy = {"m": 6, "k": 6, "threshold": 6.0}
    kelly_params = {
        ("NKD", "LOW_VOL", 3): {"kelly_full": 0.05, "shrinkage_factor": 1.0},
        ("NKD", "HIGH_VOL", 3): {"kelly_full": 0.05, "shrinkage_factor": 1.0},
    }
    ewma_states = {("NKD", "HIGH_VOL", 3): {"avg_loss": 30.0}}

    result = compute_contracts(
        asset_id="NKD",
        pnl_per_contract=100.0,
        spec=spec,
        kelly_params=kelly_params,
        ewma_states=ewma_states,
        config=cfg,
        strategy=strategy,
        session_id=3,
        aim_modifier=1.0,
    )
    # 480 + rho >= 500 → L1 blocks (or shrinks contracts to 0)
    # The exact condition: 480 + N*(30+2.80) >= 500 → N=1 trips immediately.
    assert result["cb_l1_l_t"] == Decimal("480.00")
    assert result["cb_l1_halt"] == Decimal("500.00")
    assert result["cb_blocked"] is True
    assert result["contracts"] == 0


def test_per_session_l3_basket_pnl_is_session_scoped():
    """Strategy m=6 traded NY profitably ($100). When considering NKD APAC
    using strategy m=6, L_b should be 0 (no APAC m=6 trades yet), NOT $100."""
    from shared.replay_engine import compute_contracts

    cfg = _base_config()
    cfg["_intraday_basket_pnl_per_session"] = {
        1: {"6": 100.0},  # NY:m6 profitable
        2: {},
        3: {},  # APAC has no m=6 trades yet
        4: {},
    }
    # CB params: trained beta_b=0.05 negative coupling, p<0.05, n=200
    cfg["cb_params"] = {
        ("21855714", "6"): {
            "r_bar": 5.0, "beta_b": -0.05,  # large negative L_b would push mu_b<0
            "p_value": 0.01, "n_observations": 200,
            "sigma": 50.0, "rho_bar": 0.1,
        }
    }
    spec = {"point_value": 5.0}
    strategy = {"m": 6, "k": 6, "threshold": 6.0}
    kelly_params = {
        ("NKD", "HIGH_VOL", 3): {"kelly_full": 0.1, "shrinkage_factor": 1.0},
        ("NKD", "LOW_VOL", 3): {"kelly_full": 0.1, "shrinkage_factor": 1.0},
    }
    ewma_states = {("NKD", "HIGH_VOL", 3): {"avg_loss": 30.0}}

    result = compute_contracts(
        asset_id="NKD",
        pnl_per_contract=100.0,
        spec=spec,
        kelly_params=kelly_params,
        ewma_states=ewma_states,
        config=cfg,
        strategy=strategy,
        session_id=3,  # APAC
        aim_modifier=1.0,
    )
    # APAC m=6 has no trades → L_b=0 → mu_b = 5 + (-0.05)*0 = 5 > 0 → ALLOW.
    # If L3 looked at NY's m=6 ($100) it would compute mu_b = 5 + (-0.05)*100 = 0
    # (boundary; might block depending on equality; either way different from 5).
    assert result["cb_l3_blocked"] is False
    # Sanity check that mu_b reflects APAC's empty basket, not NY's
    # mu_b = 5.0 (since L_b=0). Allow Decimal/float blend tolerance.
    assert result.get("cb_l3_mu_b") is not None
    assert abs(float(result["cb_l3_mu_b"]) - 5.0) < 0.0001
