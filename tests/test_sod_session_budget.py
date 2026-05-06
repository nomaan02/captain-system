"""Unit tests for shared.sod_session_budget helpers.

No QuestDB dependency — pure Python logic tests for:
  - session_budget_shares (HMM cold-start / blended / full)
  - get_session_l_halt / get_session_e_exposure (lookup + fallback)
  - compute_session_carryover (the parity-skip-driven carryover formula)
  - sessions_earlier_in_day / sessions_remaining_in_day (trading-day order)
"""

from decimal import Decimal

import pytest

from shared.sod_session_budget import (
    EQUAL_SHARE,
    SESSION_WEIGHT_FLOOR,
    TRADING_DAY_SESSION_ORDER,
    compute_session_carryover,
    get_session_e_exposure,
    get_session_l_halt,
    get_session_n_max_trades,
    session_budget_shares,
    session_key_for,
    sessions_earlier_in_day,
    sessions_remaining_in_day,
)


# ---------------------------------------------------------------------------
# session_key_for / trading-day ordering
# ---------------------------------------------------------------------------


class TestSessionKeyMapping:
    def test_known_session_ids_map_to_canonical_keys(self):
        assert session_key_for(1) == "NY"
        assert session_key_for(2) == "LON"
        assert session_key_for(3) == "APAC"
        assert session_key_for(4) == "NY_PRE"

    def test_unknown_session_id_defaults_to_ny(self):
        assert session_key_for(99) == "NY"


class TestTradingDayOrder:
    def test_canonical_order_is_lon_ny_apac(self):
        # v1: HMM provides 3 sessions only. NY_PRE excluded — see module docstring.
        # LON 03:00 → NY 09:30 → APAC 18:00 (then 19:00 SOD reset)
        assert TRADING_DAY_SESSION_ORDER == (2, 1, 3)

    def test_sessions_earlier_at_lon_open_is_empty(self):
        assert sessions_earlier_in_day(2) == ()  # LON is first

    def test_sessions_earlier_at_ny_includes_lon(self):
        assert sessions_earlier_in_day(1) == (2,)

    def test_sessions_earlier_at_apac_includes_lon_and_ny(self):
        assert sessions_earlier_in_day(3) == (2, 1)

    def test_sessions_remaining_at_lon_open_is_full_day(self):
        assert sessions_remaining_in_day(2) == (2, 1, 3)

    def test_sessions_remaining_at_ny_open_is_ny_and_apac(self):
        assert sessions_remaining_in_day(1) == (1, 3)

    def test_sessions_remaining_at_apac_is_just_apac(self):
        assert sessions_remaining_in_day(3) == (3,)

    def test_unknown_session_id_returns_empty_earlier_and_self_remaining(self):
        # NY_PRE (session_id=4) is not in TRADING_DAY_SESSION_ORDER for v1.
        assert sessions_earlier_in_day(4) == ()
        assert sessions_remaining_in_day(4) == (4,)


# ---------------------------------------------------------------------------
# session_budget_shares (cold-start / blended / full HMM)
# ---------------------------------------------------------------------------


class TestSessionBudgetShares:
    def test_no_hmm_state_returns_equal_thirds(self):
        shares = session_budget_shares(None)
        for k in ("NY", "LON", "APAC"):
            assert shares[k] == EQUAL_SHARE

    def test_cold_start_flag_returns_equal_thirds(self):
        shares = session_budget_shares({"cold_start": True, "n_observations": 1000})
        for k in ("NY", "LON", "APAC"):
            assert shares[k] == EQUAL_SHARE

    def test_low_n_obs_returns_equal_thirds(self):
        shares = session_budget_shares({"cold_start": False, "n_observations": 19})
        for k in ("NY", "LON", "APAC"):
            assert shares[k] == EQUAL_SHARE

    def test_blended_zone_mixes_equal_and_hmm_50_50(self):
        # n_obs=30 is in the blended zone (20 <= n < 60)
        hmm_state = {
            "cold_start": False,
            "n_observations": 30,
            "opportunity_weights": {"NY": 0.6, "LON": 0.3, "APAC": 0.1},
        }
        shares = session_budget_shares(hmm_state)
        # Pre-floor weights: 0.5 * 1/3 + 0.5 * w_HMM
        # NY: 0.5 * 0.333 + 0.5 * 0.6 = 0.4667
        # LON: 0.5 * 0.333 + 0.5 * 0.3 = 0.3167
        # APAC: 0.5 * 0.333 + 0.5 * 0.1 = 0.2167
        # Sum = 1.0 (already normalised), all > floor 0.05, so unchanged
        assert shares["NY"] > shares["LON"] > shares["APAC"]
        total = shares["NY"] + shares["LON"] + shares["APAC"]
        assert abs(total - Decimal("1")) < Decimal("0.0001")

    def test_full_hmm_uses_pure_weights_with_floor(self):
        hmm_state = {
            "cold_start": False,
            "n_observations": 100,
            "opportunity_weights": {"NY": 0.95, "LON": 0.04, "APAC": 0.01},
        }
        shares = session_budget_shares(hmm_state)
        # APAC was 0.01, floored to 0.05; LON was 0.04, floored to 0.05.
        # NY stays 0.95. Pre-renormalise sum = 0.95 + 0.05 + 0.05 = 1.05.
        # After renormalise: NY=0.9048, LON=APAC=0.0476.
        # Each share must be >= floor (0.05) post-floor but renormalisation
        # may push the smallest below floor; key invariant is sum=1.
        total = shares["NY"] + shares["LON"] + shares["APAC"]
        assert abs(total - Decimal("1")) < Decimal("0.0001")
        assert shares["NY"] > shares["LON"]
        assert shares["NY"] > shares["APAC"]

    def test_missing_session_in_hmm_weights_falls_back_to_equal(self):
        # HMM state only has NY and LON; APAC missing
        hmm_state = {
            "cold_start": False,
            "n_observations": 100,
            "opportunity_weights": {"NY": 0.5, "LON": 0.3},
        }
        shares = session_budget_shares(hmm_state)
        # APAC should use EQUAL_SHARE fallback before normalisation
        total = shares["NY"] + shares["LON"] + shares["APAC"]
        assert abs(total - Decimal("1")) < Decimal("0.0001")


# ---------------------------------------------------------------------------
# get_session_l_halt / get_session_e_exposure / get_session_n_max_trades
# ---------------------------------------------------------------------------


class TestSessionLookups:
    def test_per_session_l_halt_returned_when_nested_present(self):
        computed_sod = {
            "L_halt": "750.00",  # legacy total
            "E_daily_exposure": "1500.00",
            "N_max_trades": 54,
            "session": {
                "NY": {"L_halt": Decimal("465"), "E_daily_exposure": Decimal("930"),
                       "N_max_trades": 33},
                "LON": {"L_halt": Decimal("187.50"), "E_daily_exposure": Decimal("375"),
                        "N_max_trades": 13},
                "APAC": {"L_halt": Decimal("97.50"), "E_daily_exposure": Decimal("195"),
                         "N_max_trades": 7},
            },
        }
        assert get_session_l_halt(computed_sod, 1) == Decimal("465")
        assert get_session_l_halt(computed_sod, 2) == Decimal("187.50")
        assert get_session_l_halt(computed_sod, 3) == Decimal("97.50")
        assert get_session_e_exposure(computed_sod, 1) == Decimal("930")
        assert get_session_n_max_trades(computed_sod, 1) == 33

    def test_falls_back_to_legacy_flat_when_session_map_missing(self):
        computed_sod = {
            "L_halt": Decimal("750"),
            "E_daily_exposure": Decimal("1500"),
            "N_max_trades": 54,
        }
        # No session map — readers should return the flat scalar so the system
        # still runs pre-Phase-2 with single-budget semantics.
        assert get_session_l_halt(computed_sod, 1) == Decimal("750")
        assert get_session_e_exposure(computed_sod, 1) == Decimal("1500")
        assert get_session_n_max_trades(computed_sod, 1) == 54

    def test_returns_zero_when_no_computed_sod(self):
        assert get_session_l_halt(None, 1) == Decimal("0")
        assert get_session_l_halt({}, 1) == Decimal("0")
        assert get_session_e_exposure({}, 1) == Decimal("0")

    def test_n_max_trades_defaults_to_999_unbounded(self):
        assert get_session_n_max_trades(None, 1) == 999
        assert get_session_n_max_trades({}, 1) == 999


# ---------------------------------------------------------------------------
# compute_session_carryover — the parity-skip core formula
# ---------------------------------------------------------------------------


class TestCarryover:
    def setup_method(self):
        # 150K combine, c=1.0, e=0.01 → L_halt_total=$1500, E_total=$1500
        # (with c=1.0; note this differs from current c=0.5 production until
        # Phase 2 bumps it). Equal HMM shares (cold start).
        self.l_halt_total = Decimal("1500")
        self.e_total = Decimal("1500")
        self.shares = {
            "NY": EQUAL_SHARE,
            "LON": EQUAL_SHARE,
            "APAC": EQUAL_SHARE,
        }

    def test_lon_open_no_prior_sessions_uses_pure_sod_share(self):
        # LON is first session of the day; no carryover possible.
        # remaining_session_ids = (LON, NY, APAC) per v1 TRADING_DAY_SESSION_ORDER.
        eff_l, eff_e = compute_session_carryover(
            sod_l_halt_total=self.l_halt_total,
            sod_e_total=self.e_total,
            shares=self.shares,
            completed_sessions_state={},
            target_session_id=2,
            remaining_session_ids=(2, 1, 3),
        )
        assert eff_l == self.l_halt_total / Decimal("3")
        assert eff_e == self.e_total / Decimal("3")

    def test_ny_open_after_lon_skipped_inherits_lons_full_share(self):
        """The flagship parity-skip case from Nomaan's intent.

        Scenario: Tower A's parity excludes LON's only signal, so LON closes
        with l_t_final=0 (zero realized consumption). NY opens — how much
        budget should it have?

        Formula B (Isaac's "available × share / remaining"):
          consumed_so_far = 0 (LON skipped)
          available = sod_total - 0 = 1500
          remaining = NY + APAC, share_sum = 1/3 + 1/3 = 2/3
          effective_NY = 1500 × (1/3) / (2/3) = 750

        Compare to no-skip (LON also opened): NY's own bare SOD share = 500.
        Skip uplift = 750 - 500 = 250. ✓ NY gets MORE budget when LON skipped.
        """
        completed_state = {
            "LON": {
                "effective_l_halt": self.l_halt_total / Decimal("3"),
                "effective_e_exposure": self.e_total / Decimal("3"),
                "l_t_final": Decimal("0"),  # skipped, no trades
            },
        }
        eff_l, eff_e = compute_session_carryover(
            sod_l_halt_total=self.l_halt_total,
            sod_e_total=self.e_total,
            shares=self.shares,
            completed_sessions_state=completed_state,
            target_session_id=1,  # NY
            remaining_session_ids=(1, 3),  # NY + APAC remain
        )
        assert eff_l == Decimal("750")
        assert eff_e == Decimal("750")

    def test_apac_open_after_lon_skipped_ny_traded_and_lost(self):
        """APAC opens last; LON skipped, NY traded with $300 loss.

        consumed_so_far = abs(0) + abs(-300) = 300
        available = 1500 - 300 = 1200
        remaining = APAC only, share_sum = 1/3
        effective_APAC = 1200 × (1/3) / (1/3) = 1200

        Total day usage if APAC uses all 1200 = 300 (NY) + 1200 (APAC) = 1500 ✓
        """
        completed_state = {
            "LON": {
                "effective_l_halt": self.l_halt_total / Decimal("3"),
                "effective_e_exposure": self.e_total / Decimal("3"),
                "l_t_final": Decimal("0"),
            },
            "NY": {
                "effective_l_halt": self.l_halt_total / Decimal("3"),
                "effective_e_exposure": self.e_total / Decimal("3"),
                "l_t_final": Decimal("-300"),
            },
        }
        eff_l, eff_e = compute_session_carryover(
            sod_l_halt_total=self.l_halt_total,
            sod_e_total=self.e_total,
            shares=self.shares,
            completed_sessions_state=completed_state,
            target_session_id=3,
            remaining_session_ids=(3,),
        )
        assert eff_l == Decimal("1200")
        assert eff_e == Decimal("1200")

    def test_apac_inherits_only_own_share_when_prior_sessions_consumed_max(self):
        """If LON and NY together consumed $1000, APAC sees available = $500.

        consumed_so_far = abs(-500) + abs(-500) = 1000
        available = 1500 - 1000 = 500
        remaining = APAC only, share_sum = 1/3
        effective_APAC = 500 × (1/3) / (1/3) = 500
        """
        completed_state = {
            "LON": {
                "effective_l_halt": self.l_halt_total / Decimal("3"),
                "effective_e_exposure": self.e_total / Decimal("3"),
                "l_t_final": Decimal("-500"),
            },
            "NY": {
                "effective_l_halt": self.l_halt_total / Decimal("3"),
                "effective_e_exposure": self.e_total / Decimal("3"),
                "l_t_final": Decimal("-500"),
            },
        }
        eff_l, eff_e = compute_session_carryover(
            sod_l_halt_total=self.l_halt_total,
            sod_e_total=self.e_total,
            shares=self.shares,
            completed_sessions_state=completed_state,
            target_session_id=3,
            remaining_session_ids=(3,),
        )
        assert eff_l == Decimal("500")
        assert eff_e == Decimal("500")

    def test_apac_inherits_zero_when_prior_sessions_consumed_full_day_budget(self):
        """If consumption reaches $1500 (the full day budget), APAC gets $0."""
        completed_state = {
            "LON": {
                "effective_l_halt": self.l_halt_total / Decimal("3"),
                "effective_e_exposure": self.e_total / Decimal("3"),
                "l_t_final": Decimal("-750"),
            },
            "NY": {
                "effective_l_halt": self.l_halt_total / Decimal("3"),
                "effective_e_exposure": self.e_total / Decimal("3"),
                "l_t_final": Decimal("-750"),
            },
        }
        eff_l, eff_e = compute_session_carryover(
            sod_l_halt_total=self.l_halt_total,
            sod_e_total=self.e_total,
            shares=self.shares,
            completed_sessions_state=completed_state,
            target_session_id=3,
            remaining_session_ids=(3,),
        )
        assert eff_l == Decimal("0")
        assert eff_e == Decimal("0")

    def test_full_day_no_consumption_apac_gets_full_day_budget(self):
        """When no prior session consumed anything, APAC (last) sees full day budget.

        Walk through each session-open in canonical order:

        LON open : completed={}     → available=1500, remaining=(LON,NY,APAC),
                   eff_lon = 1500 × (1/3)/(1) = 500  (matches own SOD share)
        NY open  : completed={LON l_t=0}  → available=1500,
                   remaining=(NY,APAC), eff_ny = 1500 × (1/3)/(2/3) = 750
        APAC open: completed={LON,NY l_t=0,0} → available=1500,
                   remaining=(APAC,), eff_apac = 1500 × (1/3)/(1/3) = 1500

        APAC sees the full day budget if nothing was consumed earlier.
        """
        l_total = self.l_halt_total
        # NB: TRADING_DAY_SESSION_ORDER excludes NY_PRE for v1 — see module
        # docstring. Tests use the production 3-session order.
        eff_lon, _ = compute_session_carryover(
            sod_l_halt_total=l_total,
            sod_e_total=self.e_total,
            shares=self.shares,
            completed_sessions_state={},
            target_session_id=2,
            remaining_session_ids=(2, 1, 3),
        )
        assert eff_lon == Decimal("500")
        eff_ny, _ = compute_session_carryover(
            sod_l_halt_total=l_total,
            sod_e_total=self.e_total,
            shares=self.shares,
            completed_sessions_state={
                "LON": {
                    "effective_l_halt": eff_lon,
                    "effective_e_exposure": eff_lon,
                    "l_t_final": Decimal("0"),
                },
            },
            target_session_id=1,
            remaining_session_ids=(1, 3),
        )
        assert eff_ny == Decimal("750")
        eff_apac, _ = compute_session_carryover(
            sod_l_halt_total=l_total,
            sod_e_total=self.e_total,
            shares=self.shares,
            completed_sessions_state={
                "LON": {
                    "effective_l_halt": eff_lon,
                    "effective_e_exposure": eff_lon,
                    "l_t_final": Decimal("0"),
                },
                "NY": {
                    "effective_l_halt": eff_ny,
                    "effective_e_exposure": eff_ny,
                    "l_t_final": Decimal("0"),
                },
            },
            target_session_id=3,
            remaining_session_ids=(3,),
        )
        assert eff_apac == l_total

    def test_carryover_with_non_uniform_shares(self):
        """HMM weights {NY: 0.6, LON: 0.3, APAC: 0.1}; LON skip; check NY carryover."""
        l_total = Decimal("1500")
        shares = {"NY": Decimal("0.6"), "LON": Decimal("0.3"), "APAC": Decimal("0.1")}

        completed = {
            "LON": {
                "effective_l_halt": l_total * shares["LON"],  # 450
                "effective_e_exposure": l_total * shares["LON"],
                "l_t_final": Decimal("0"),  # skipped
            },
        }
        eff_l, _ = compute_session_carryover(
            sod_l_halt_total=l_total,
            sod_e_total=l_total,
            shares=shares,
            completed_sessions_state=completed,
            target_session_id=1,  # NY
            remaining_session_ids=(1, 3),  # NY + APAC remain
        )
        # NY own = 1500 * 0.6 = 900
        # Unused pool (from LON) = 450
        # NY's slice = 450 * (0.6 / (0.6 + 0.1)) = 450 * 6/7 ≈ 385.71
        # NY effective ≈ 900 + 385.71 = 1285.71
        expected = Decimal("900") + Decimal("450") * (Decimal("0.6") / Decimal("0.7"))
        assert abs(eff_l - expected) < Decimal("0.01")
