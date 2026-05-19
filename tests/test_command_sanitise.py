# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""Tests for captain-command B1 `sanitise_for_gui`.

Pins the GUI payload shape:
  - GUI-safe fields nested inside `_context` are lifted to top level so the
    dashboard's Active Position + Signal Cards render entry_price,
    quality_score, confidence_tier without digging into `_context`.
  - `_context` itself is stripped so nested prohibited fields
    (aim_breakdown, combined_modifier, regime_probs, etc.) cannot leak via
    nested access.
  - Top-level PROHIBITED_EXTERNAL_FIELDS remain stripped (existing behavior).
  - Signals with no `_context` don't crash.
"""

from captain_command.blocks.b1_core_routing import sanitise_for_gui
from shared.constants import PROHIBITED_EXTERNAL_FIELDS


def _make_signal(**overrides):
    sig = {
        "signal_id": "SIG-TEST-ABCDEF123456",
        "asset": "ES",
        "direction": 1,
        "size": 2,
        "tp_level": 6443.20,
        "sl_level": 6460.53,
        "timestamp": "2026-04-14T09:35:00-04:00",
        "user_id": "primary_user",
        "session": 1,
        "per_account": {"20319784": {"contracts": 2, "recommendation": "TRADE"}},
        "_context": {
            "entry_price": 6454.75,
            "sl_method": "OR_RANGE",
            "entry_conditions": {},
            "aim_breakdown": {1: {"modifier": 1.1}},
            "combined_modifier": 1.05,
            "regime_state": "LOW_VOL",
            "regime_probs": {"LOW_VOL": 0.6, "HIGH_VOL": 0.4},
            "expected_edge": 0.02,
            "win_rate": 0.55,
            "payoff_ratio": 1.8,
            "user_total_capital": 150000.0,
            "user_daily_pnl": 0.0,
            "quality_score": 0.82,
            "quality_multiplier": 1.0,
            "data_maturity": 1.0,
            "confidence_tier": "HIGH",
        },
    }
    sig.update(overrides)
    return sig


def _make_nkd_signal(**overrides):
    """NKD signal with the 6 trail-control fields B6 lifts in via
    **nkd_trail_fields (see b6_signal_output.py:168-176, 196).
    """
    sig = _make_signal(
        asset="NKD",
        direction=-1,
        size=1,
        tp_level=60680,
        sl_level=61805,
        per_account={"21855714": {"contracts": 1, "recommendation": "TRADE"}},
    )
    sig["is_nkd_trail"] = True
    sig["tp_dollars"] = 4450
    sig["snapped_d_init"] = 1025.0
    sig["jitter_x"] = 0.5
    sig["jitter_y"] = 1
    sig["jitter_j"] = 10.0
    sig.update(overrides)
    return sig


class TestGuiLift:
    def test_entry_price_lifted(self):
        out = sanitise_for_gui(_make_signal())
        assert out["entry_price"] == 6454.75

    def test_quality_score_lifted(self):
        out = sanitise_for_gui(_make_signal())
        assert out["quality_score"] == 0.82

    def test_confidence_tier_lifted(self):
        out = sanitise_for_gui(_make_signal())
        assert out["confidence_tier"] == "HIGH"

    def test_context_stripped(self):
        out = sanitise_for_gui(_make_signal())
        assert "_context" not in out

    def test_top_level_fields_preserved(self):
        out = sanitise_for_gui(_make_signal())
        for f in ("signal_id", "asset", "direction", "size",
                  "tp_level", "sl_level", "timestamp",
                  "user_id", "session", "per_account"):
            assert f in out, f"Missing top-level field: {f}"


class TestProhibitedFieldsLeak:
    def test_no_top_level_prohibited(self):
        out = sanitise_for_gui(_make_signal())
        for f in PROHIBITED_EXTERNAL_FIELDS:
            assert f not in out, f"Top-level prohibited field leaked: {f}"

    def test_no_nested_prohibited_via_context(self):
        """Regression guard: prior implementation stripped top-level
        prohibited fields only, so nested prohibited via `_context` leaked."""
        out = sanitise_for_gui(_make_signal())
        assert "_context" not in out
        for f in PROHIBITED_EXTERNAL_FIELDS:
            for v in out.values():
                if isinstance(v, dict):
                    assert f not in v, (
                        f"Prohibited field {f!r} still reachable via nested "
                        f"dict: {v!r}"
                    )

    def test_top_level_prohibited_stripped_directly(self):
        sig = _make_signal()
        sig["aim_breakdown"] = {"leaked": True}
        sig["regime_probs"] = {"LOW_VOL": 0.5}
        out = sanitise_for_gui(sig)
        assert "aim_breakdown" not in out
        assert "regime_probs" not in out


class TestEdgeCases:
    def test_no_context_does_not_crash(self):
        sig = _make_signal()
        del sig["_context"]
        out = sanitise_for_gui(sig)
        assert "entry_price" not in out  # nothing to lift
        assert out["asset"] == "ES"

    def test_null_context_does_not_crash(self):
        sig = _make_signal()
        sig["_context"] = None
        out = sanitise_for_gui(sig)
        assert out["asset"] == "ES"

    def test_context_missing_gui_fields(self):
        sig = _make_signal()
        sig["_context"] = {"sl_method": "OR_RANGE"}  # no entry/quality/conf
        out = sanitise_for_gui(sig)
        assert "entry_price" not in out
        assert "quality_score" not in out
        assert "confidence_tier" not in out

    def test_top_level_gui_field_not_overwritten_by_context(self):
        sig = _make_signal()
        sig["entry_price"] = 9999.99  # pre-set at top level
        out = sanitise_for_gui(sig)
        assert out["entry_price"] == 9999.99


class TestSanitiseForApiNkdTrailFields:
    """Audit F2 fix: sanitise_for_api must forward all 6 NKD trail-control
    fields end-to-end. See REJECTED_ORDERS_AUDIT.md §4 + §7 Option B.
    """

    def test_sanitise_for_api_preserves_nkd_trail_fields(self):
        """Happy path: NKD signal in → all 6 NKD keys in the sanitised dict."""
        from captain_command.blocks.b1_core_routing import sanitise_for_api

        signal = _make_nkd_signal()
        result = sanitise_for_api(signal, "21855714", {"contracts": 1})

        assert result["is_nkd_trail"] is True
        assert result["tp_dollars"] == 4450
        assert result["snapped_d_init"] == 1025.0
        assert result["jitter_x"] == 0.5
        assert result["jitter_y"] == 1
        assert result["jitter_j"] == 10.0

    def test_sanitise_for_api_non_nkd_signals_preserve_original_13_fields(self):
        """Regression guard: non-NKD signal must still produce the original
        13 sanitised fields with unchanged values, with the 6 new NKD keys
        all defaulting to None (no behaviour change for ES/MES/etc.).
        """
        from captain_command.blocks.b1_core_routing import sanitise_for_api

        signal = _make_signal()  # ES signal, no NKD fields
        result = sanitise_for_api(signal, "20319784", {"contracts": 2})

        assert result["asset"] == "ES"
        assert result["direction"] == 1
        assert result["size"] == 2
        assert result["tp"] == 6443.20
        assert result["sl"] == 6460.53
        assert result["timestamp"] == "2026-04-14T09:35:00-04:00"
        assert result["signal_id"] == "SIG-TEST-ABCDEF123456"
        assert result["user_id"] == "primary_user"
        assert result["session"] == 1
        assert result["entry_price"] == 6454.75
        assert result["regime_state"] == "LOW_VOL"
        assert result["combined_modifier"] == 1.05
        assert result["aim_breakdown"] == {1: {"modifier": 1.1}}

        assert result["is_nkd_trail"] is None
        assert result["tp_dollars"] is None
        assert result["snapped_d_init"] is None
        assert result["jitter_x"] is None
        assert result["jitter_y"] is None
        assert result["jitter_j"] is None

    def test_sanitise_for_api_with_decimal_nkd_jitter(self):
        """B6 emits jitter_j as float on the in-memory signal, but the
        stream-roundtripped value is Decimal. Both must pass through
        unchanged at the sanitise hop (coercion happens in
        _handle_taken_skipped, not here).
        """
        from decimal import Decimal
        from captain_command.blocks.b1_core_routing import sanitise_for_api

        signal = _make_nkd_signal(
            jitter_j=Decimal("-10.0"),
            jitter_x=Decimal("0.5"),
            snapped_d_init=Decimal("1025.0"),
            tp_dollars=Decimal("4450"),
        )
        result = sanitise_for_api(signal, "21855714", {"contracts": 1})

        assert result["jitter_j"] == Decimal("-10.0")
        assert result["jitter_x"] == Decimal("0.5")
        assert result["snapped_d_init"] == Decimal("1025.0")
        assert result["tp_dollars"] == Decimal("4450")
        assert result["jitter_y"] == 1
