"""Regression test for TopstepX account-name -> TSM stage classification.

PRODUCTION RISK (2026-05-01)
----------------------------
Pre-fix `_link_tsm_to_account` in captain-command/main.py used:
    if account_name.startswith("PRAC"):
        target_stage = "STAGE_1"
    elif "XFA" in account_name:
        target_stage = "XFA"
    else:
        target_stage = "LIVE"   # ← silent fall-through

This silently mis-classified Trading Combine accounts (e.g.
`150KTC-V2-551001-86041837`) as Live Funded, which would have:
  * Removed the trailing $4,500 MLL guard
  * Replaced it with $4,500 daily DD + auto-liquidate-and-halt-19EST
  * Used the wrong commission tiers ($1.40/contract vs $2.80)
  * Set overnight_allowed=False (live live default)

Mis-classification would have either let the eval account trade past the
trailing MLL until the broker rejected the order, OR triggered Captain's
auto-liquidate logic against rules that do not exist on the eval account.

FIX
---
`classify_topstep_account_stage()` now:
  1. Documents every known TopstepX naming pattern
  2. Returns "STAGE_1" / "XFA" / "LIVE" for known patterns
  3. Returns None for unknown patterns (FAIL CLOSED)
  4. `_link_tsm_to_account` refuses to link on None and emits a
     CRITICAL alert + Redis publish
"""
from __future__ import annotations

import pytest

from captain_command.main import classify_topstep_account_stage


# ---------------------------------------------------------------------------
# Trading Combine eval (the user's actual account pattern)
# ---------------------------------------------------------------------------

class TestTradingCombineEval:
    """The exact pattern that triggered this fix: 150KTC-V2-551001-86041837"""

    def test_users_actual_account(self):
        """The exact pattern that surfaced the bug."""
        assert classify_topstep_account_stage("150KTC-V2-551001-86041837") == "STAGE_1"

    def test_50k_combine(self):
        assert classify_topstep_account_stage("50KTC-V2-123456-78901234") == "STAGE_1"

    def test_100k_combine(self):
        assert classify_topstep_account_stage("100KTC-V2-555000-11111111") == "STAGE_1"

    def test_25k_combine(self):
        assert classify_topstep_account_stage("25KTC-V2-999999-99999999") == "STAGE_1"

    def test_legacy_tc_prefix(self):
        """Older Topstep accounts may use bare TC- prefix (no balance)."""
        assert classify_topstep_account_stage("TC-V2-100000-20000000") == "STAGE_1"

    def test_lowercase_input_normalised(self):
        """Function must be case-insensitive (Topstep dashboard occasionally
        emits mixed-case names depending on flow)."""
        assert classify_topstep_account_stage("150ktc-v2-551001-86041837") == "STAGE_1"


# ---------------------------------------------------------------------------
# Practice / paper accounts
# ---------------------------------------------------------------------------

class TestPracticeAccount:
    def test_standard_prac_pattern(self):
        assert classify_topstep_account_stage("PRAC-V2-551001-43861321") == "STAGE_1"

    def test_prac_lowercase(self):
        assert classify_topstep_account_stage("prac-v2-551001-43861321") == "STAGE_1"


# ---------------------------------------------------------------------------
# XFA (Express Funded Account) — must take priority over TC substring
# ---------------------------------------------------------------------------

class TestXFAAccount:
    def test_standard_xfa(self):
        assert classify_topstep_account_stage("XFA-V2-551001-86041837") == "XFA"

    def test_xfa_with_balance(self):
        """Some XFA accounts include balance prefix or suffix."""
        assert classify_topstep_account_stage("XFA-150K-V2-551001-86041837") == "XFA"
        assert classify_topstep_account_stage("150K-XFA-V2-551001") == "XFA"

    def test_xfa_takes_priority_over_substring(self):
        """If a name contains XFA AND TC, XFA must win (e.g. hypothetical
        XFA-150K-TC-V2-... — XFA stage rules apply)."""
        assert classify_topstep_account_stage("XFA-150K-TC-V2-001") == "XFA"


# ---------------------------------------------------------------------------
# Live funded
# ---------------------------------------------------------------------------

class TestLiveFundedAccount:
    def test_live_prefix(self):
        assert classify_topstep_account_stage("LIVE-V2-551001-86041837") == "LIVE"

    def test_fund_substring(self):
        assert classify_topstep_account_stage("150KFUND-V2-551001-86041837") == "LIVE"

    def test_live_lowercase(self):
        assert classify_topstep_account_stage("live-v2-551001") == "LIVE"


# ---------------------------------------------------------------------------
# UNKNOWN patterns must FAIL CLOSED (return None) — pre-fix would have
# defaulted to LIVE and silently mis-classified
# ---------------------------------------------------------------------------

class TestUnknownPatternsFailClosed:
    def test_empty_name(self):
        assert classify_topstep_account_stage("") is None

    def test_none_name(self):
        assert classify_topstep_account_stage(None) is None

    def test_garbage_pattern(self):
        assert classify_topstep_account_stage("RANDOM-12345") is None

    def test_numeric_only(self):
        assert classify_topstep_account_stage("551001-86041837") is None

    def test_almost_pattern_but_not_quite(self):
        """e.g. an account that mentions TC but not as the recognised
        pattern (TC-V2 anchor avoids substring false positives)."""
        assert classify_topstep_account_stage("ACCOUNT-MTCM-V2-001") is None

    def test_funded_substring_alone_is_live(self):
        """We accept 'FUND' as a LIVE marker — verified by IsLiveFundedAccount."""
        # This is documented behaviour, not a bug. Ensure it doesn't slip into None.
        assert classify_topstep_account_stage("MYFUNDACCOUNT") == "LIVE"


# ---------------------------------------------------------------------------
# Integration: _link_tsm_to_account refuses to link unknown patterns
# ---------------------------------------------------------------------------

class TestLinkTsmRefusesUnknownPatterns:
    """Verify the auto-link function calls our classifier and FAILS CLOSED."""

    def test_refuses_to_link_unknown_pattern(self, monkeypatch, caplog):
        """When classify returns None, _link_tsm_to_account must:
        1. NOT write to D08
        2. Log CRITICAL
        3. Try to publish a Redis alert"""
        import logging
        from captain_command import main as cmd_main

        # Stub the D08 write path so we can detect if it's called
        write_called = []
        from captain_command.blocks import b4_tsm_manager
        monkeypatch.setattr(
            b4_tsm_manager, "_store_tsm_in_d08",
            lambda ac_id, tsm: write_called.append((ac_id, tsm)),
        )

        # Stub Redis client (count alert publishes)
        published = []
        class _StubRedis:
            def publish(self, channel, payload):
                published.append((channel, payload))

        from shared import redis_client
        monkeypatch.setattr(
            redis_client, "get_redis_client", lambda: _StubRedis(),
        )

        # Stub get_cursor for the existing-row check
        class _StubCursor:
            def execute(self, *args, **kwargs):
                pass
            def fetchone(self):
                return (0,)  # no existing D08 row
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        from shared import questdb_client
        monkeypatch.setattr(
            questdb_client, "get_cursor", lambda: _StubCursor(),
        )

        # Invoke with an unknown pattern
        with caplog.at_level(logging.CRITICAL):
            cmd_main._link_tsm_to_account(
                tsm_results=[],
                account={"id": 999999, "name": "TOTALLY-UNKNOWN-PATTERN"},
            )

        # 1. D08 write NOT called
        assert write_called == [], "Should not write D08 for unknown pattern"

        # 2. CRITICAL log emitted
        critical_records = [r for r in caplog.records if r.levelno >= logging.CRITICAL]
        assert any(
            "cannot auto-classify TSM stage" in r.message for r in critical_records
        ), f"Expected CRITICAL log, got: {[r.message for r in caplog.records]}"

        # 3. Alert publish attempted
        assert len(published) == 1
        channel, payload = published[0]
        assert "alert" in channel.lower() or channel.startswith("captain:")
        assert "TSM_AUTO_LINK_REFUSED" in payload
        assert "TOTALLY-UNKNOWN-PATTERN" in payload

    def test_links_known_combine_pattern(self, monkeypatch):
        """The user's actual 150KTC-V2-... pattern must successfully link
        to the STAGE_1 (eval) TSM JSON."""
        from captain_command import main as cmd_main

        write_called = []
        from captain_command.blocks import b4_tsm_manager
        monkeypatch.setattr(
            b4_tsm_manager, "_store_tsm_in_d08",
            lambda ac_id, tsm: write_called.append((ac_id, tsm)),
        )

        class _StubCursor:
            def execute(self, *args, **kwargs): pass
            def fetchone(self): return (0,)
            def __enter__(self): return self
            def __exit__(self, *args): pass

        from shared import questdb_client
        monkeypatch.setattr(
            questdb_client, "get_cursor", lambda: _StubCursor(),
        )

        # Build a tsm_results list containing the eval TSM
        tsm_results = [
            {
                "validation": {"valid": True},
                "tsm": {
                    "name": "Topstep 150K Trading Combine",
                    "classification": {
                        "provider": "TopstepX",
                        "category": "PROP_EVAL",
                        "stage": "STAGE_1",
                        "risk_goal": "PASS_EVAL",
                    },
                    "starting_balance": 150000,
                },
            },
            {
                "validation": {"valid": True},
                "tsm": {
                    "name": "Topstep 150K Live Funded",
                    "classification": {
                        "provider": "TopstepX",
                        "category": "PROP_FUNDED",
                        "stage": "LIVE",
                        "risk_goal": "GROW_CAPITAL",
                    },
                    "starting_balance": None,
                },
            },
        ]

        cmd_main._link_tsm_to_account(
            tsm_results=tsm_results,
            account={
                "id": 86041837,
                "name": "150KTC-V2-551001-86041837",
                "balance": 150000,
            },
        )

        # Should pick the STAGE_1 TSM (NOT the LIVE one)
        assert len(write_called) == 1
        ac_id, tsm = write_called[0]
        assert ac_id == "86041837"
        assert tsm["classification"]["stage"] == "STAGE_1"
        assert tsm["classification"]["category"] == "PROP_EVAL"
        assert tsm["name"] == "Topstep 150K Trading Combine"


# ---------------------------------------------------------------------------
# Documentation reference — every documented Topstep naming convention
# ---------------------------------------------------------------------------

DOCUMENTED_PATTERNS = [
    # (account_name, expected_stage, description)
    ("PRAC-V2-551001-43861321", "STAGE_1", "Practice (paper) account"),
    ("150KTC-V2-551001-86041837", "STAGE_1", "150K Trading Combine eval"),
    ("50KTC-V2-100000-20000000", "STAGE_1", "50K Trading Combine eval"),
    ("100KTC-V2-300000-40000000", "STAGE_1", "100K Trading Combine eval"),
    ("XFA-V2-551001-86041837", "XFA", "Express Funded Account"),
    ("XFA-150K-V2-551001-86041837", "XFA", "Express Funded with balance prefix"),
    ("LIVE-V2-551001-86041837", "LIVE", "Live Funded Account"),
    ("150KFUND-V2-551001-86041837", "LIVE", "Funded variant naming"),
]


@pytest.mark.parametrize("name,expected,desc", DOCUMENTED_PATTERNS)
def test_documented_pattern(name, expected, desc):
    """Single source of truth for every Topstep account naming convention
    Captain currently knows about. New patterns from TopstepX must be added
    here AND to classify_topstep_account_stage() simultaneously."""
    assert classify_topstep_account_stage(name) == expected, (
        f"Pattern {name!r} ({desc}) classified incorrectly"
    )
