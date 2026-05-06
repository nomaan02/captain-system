"""Phase 4: B5C circuit breaker per-session layer reads.

Verifies L1, L2, L3 each read per-session L_halt / E / l_b correctly:
  1. effective_l_halt from intraday (Phase 3a-written) is preferred.
  2. Falls back to computed_sod.session.<KEY>.{L_halt,E_daily_exposure}.
  3. Falls back to flat computed_sod.{L_halt,E_daily_exposure} (legacy).
  4. Falls back to live c*e*A / e*A only if SOD has never run.

Crucial parity-skip property: when LON took $300 of L_t, NY's per-session
gate is unaffected (NY has its own L_t row).
"""
from decimal import Decimal

from shared.decimal_json import dumps_decimal


# ---------------------------------------------------------------------------
# Layer 1 — preemptive halt
# ---------------------------------------------------------------------------


class TestLayer1PerSession:
    def _tsm(self, computed_sod: dict, c: float = 1.0) -> dict:
        topstep_state = dumps_decimal({"computed_sod": computed_sod})
        return {
            "current_balance": Decimal("150000"),
            "account_id": "21855714",
            "topstep_state": topstep_state,
            "topstep_params": f'{{"c": {c}, "e": 0.01, "p": 0.005}}',
        }

    def test_uses_intraday_effective_l_halt_when_present(self):
        from captain_online.blocks.b5c_circuit_breaker import _layer1_preemptive_halt
        # Per-session intraday: NY has eff_L_halt=750, L_t=-700.
        intraday = {"l_t": Decimal("-700"), "effective_l_halt": Decimal("750")}
        # SOD computed with different value — must NOT be used since intraday wins.
        tsm = self._tsm({
            "L_halt": Decimal("1500"),
            "session": {"NY": {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500")}},
        })
        rho_j = Decimal("100")  # rho_j=100, |l_t|=700, projected=800 >= 750 → BLOCK
        msg = _layer1_preemptive_halt(intraday, tsm, rho_j, session_id=1)
        assert msg is not None
        assert "750" in msg

    def test_falls_back_to_computed_sod_session_when_intraday_empty(self):
        """orchestrator hook hasn't fired yet → intraday lacks effective_l_halt."""
        from captain_online.blocks.b5c_circuit_breaker import _layer1_preemptive_halt
        # No effective_l_halt in intraday.
        intraday = {"l_t": Decimal("0")}
        # SOD has per-session map: NY=500.
        tsm = self._tsm({
            "L_halt": Decimal("1500"),
            "session": {"NY": {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500")}},
        })
        # Trade with rho_j=600 → |0| + 600 = 600 < 500? NO 600 >= 500 → BLOCK.
        rho_j = Decimal("600")
        msg = _layer1_preemptive_halt(intraday, tsm, rho_j, session_id=1)
        assert msg is not None
        assert "500" in msg

    def test_falls_back_to_legacy_flat_when_session_map_missing(self):
        from captain_online.blocks.b5c_circuit_breaker import _layer1_preemptive_halt
        intraday = {"l_t": Decimal("0")}
        # No session map — only flat L_halt
        tsm = self._tsm({"L_halt": Decimal("1500")})
        rho_j = Decimal("100")  # 0 + 100 = 100 < 1500 → ALLOW
        msg = _layer1_preemptive_halt(intraday, tsm, rho_j, session_id=1)
        assert msg is None

    def test_lon_loss_does_not_pollute_ny_gate(self):
        """The flagship parity-isolation test.

        LON ran into a $300 loss but B5C is now evaluating an NY signal.
        With per-session intraday rows, NY's intraday.l_t is its own
        (possibly $0), not $-300.
        """
        from captain_online.blocks.b5c_circuit_breaker import _layer1_preemptive_halt
        # NY's intraday is FRESH (l_t=0); LON's row exists with l_t=-300 but
        # _load_intraday_state(session_id=1) only returned NY's row.
        intraday_for_ny = {
            "l_t": Decimal("0"),
            "effective_l_halt": Decimal("500"),
        }
        tsm = self._tsm({
            "L_halt": Decimal("1500"),
            "session": {"NY": {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500")}},
        })
        rho_j = Decimal("100")  # |0| + 100 = 100 < 500 → ALLOW
        assert _layer1_preemptive_halt(intraday_for_ny, tsm, rho_j, session_id=1) is None


class TestLayer2PerSession:
    def _tsm(self, computed_sod: dict) -> dict:
        topstep_state = dumps_decimal({"computed_sod": computed_sod})
        return {
            "current_balance": Decimal("150000"),
            "account_id": "21855714",
            "topstep_state": topstep_state,
            "topstep_params": '{"c": 1.0, "e": 0.01, "p": 0.005}',
        }

    def test_uses_intraday_effective_e_when_present(self):
        from captain_online.blocks.b5c_circuit_breaker import _layer2_budget
        intraday = {
            "l_t": Decimal("-300"),
            "effective_e_exposure": Decimal("500"),
        }
        tsm = self._tsm({"E_daily_exposure": Decimal("1500")})
        rho_j = Decimal("250")  # remaining = 500 - 300 = 200 < 250 → BLOCK
        msg = _layer2_budget(intraday, tsm, rho_j, session_id=1)
        assert msg is not None

    def test_session_map_fallback(self):
        from captain_online.blocks.b5c_circuit_breaker import _layer2_budget
        intraday = {"l_t": Decimal("0")}
        tsm = self._tsm({
            "E_daily_exposure": Decimal("1500"),
            "session": {"APAC": {"L_halt": Decimal("500"), "E_daily_exposure": Decimal("500")}},
        })
        # E=500, L_t=0, remaining=500. rho_j=600 → BLOCK
        msg = _layer2_budget(intraday, tsm, Decimal("600"), session_id=3)
        assert msg is not None


class TestLayer3PerSessionBasket:
    def test_prefers_session_scoped_basket_key(self):
        from captain_online.blocks.b5c_circuit_breaker import _layer3_basket_expectancy
        cb_param = {
            "r_bar": 10.0, "beta_b": 0.05, "p_value": 0.01, "n_observations": 200,
        }
        # Both keys present: bare "6" (legacy) and scoped "1:6" (Phase 3).
        # Scoped should win.
        intraday = {
            "l_b": {
                "6": Decimal("-100"),       # legacy: would give mu_b = 10 + 0.05*(-100) = 5
                "1:6": Decimal("-1000"),    # scoped (NY:6): mu_b = 10 + 0.05*(-1000) = -40 → BLOCK
            },
        }
        msg = _layer3_basket_expectancy(cb_param, intraday, "6", session_id=1)
        assert msg is not None
        # Confirm it used the scoped key
        assert "1:6" in msg

    def test_falls_back_to_bare_key_when_scoped_missing(self):
        from captain_online.blocks.b5c_circuit_breaker import _layer3_basket_expectancy
        cb_param = {
            "r_bar": 10.0, "beta_b": 0.05, "p_value": 0.01, "n_observations": 200,
        }
        # Only bare "6" present → fallback path
        intraday = {"l_b": {"6": Decimal("-1000")}}  # mu_b = 10 - 50 = -40
        msg = _layer3_basket_expectancy(cb_param, intraday, "6", session_id=1)
        assert msg is not None
