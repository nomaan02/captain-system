# region imports
from AlgorithmImports import *
# endregion
"""
Task 1.9: P1/P2 Data Loader — Seeds P3-D00 with at least 1 test asset (ES).

Reads P1/P2 output references and creates the asset_universe_register entry.
Also creates a primary user (ADMIN) in P3-D15 and an initial capital silo in P3-D16.

Usage: python scripts/seed_test_asset.py
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.questdb_client import get_cursor


def seed_es_asset():
    """Insert ES (E-mini S&P 500) as the initial test asset in P3-D00."""
    session_hours = json.dumps({
        "NY": {"open": "09:30", "close": "16:00"},
        "LON": None,
        "APAC": None,
    })
    session_schedule = json.dumps(["NY"])
    data_sources = json.dumps({
        "price_feed": {
            "adapter": "FILE",
            "endpoint": "/captain/data/market/ES/",
            "frequency": "DAILY_FILE",
            "auth_ref": None,
        },
        "vix_feed": {
            "adapter": "FILE",
            "endpoint": "/captain/data/vix/vix_daily.csv",
            "frequency": "DAILY_PRE_SESSION",
            "auth_ref": None,
            "provides": ["VIX_CLOSE"],
        },
    })
    locked_strategy = json.dumps({
        "model": 4,
        "feature": 17,
        "regime_class": "REGIME_NEUTRAL",
        "source": "P2-D06",
    })

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d00_asset_universe (
                asset_id, p1_status, p2_status, captain_status,
                warm_up_progress, aim_warmup_progress, locked_strategy,
                roll_calendar, exchange_timezone, point_value, tick_size,
                margin_per_contract, session_hours, session_schedule,
                p1_data_path, p2_data_path, data_sources, data_quality_flag,
                created, last_updated
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                now(), now()
            )""",
            (
                "ES", "VALIDATED", "VALIDATED", "WARM_UP",
                0.0, json.dumps({}), locked_strategy,
                json.dumps({"current_contract": "ESH6", "next_contract": "ESM6", "next_roll_date": "2026-06-19", "roll_confirmed": False}),
                "America/New_York", 50.0, 0.25,
                12650.0, session_hours, session_schedule,
                "/captain/data/p1_outputs/ES/", "/captain/data/p2_outputs/ES/",
                data_sources, "CLEAN",
            ),
        )
        print("  [OK] P3-D00: ES asset inserted (captain_status=WARM_UP)")


def seed_primary_user():
    """Insert the primary admin user in P3-D15."""
    preferences = json.dumps({
        "display_timezone": "America/New_York",
        "notification_channels": ["gui", "telegram"],
        "quiet_hours": {"start": "22:00", "end": "06:00"},
        "theme": "dark",
    })

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d15_user_session_data (
                user_id, display_name, auth_token, role, tags,
                device_sessions, preferences, created, last_active
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, now(), now()
            )""",
            (
                "primary_user", "Nomaan", None, "ADMIN",
                json.dumps(["ADMIN", "DEV"]),
                json.dumps([]), preferences,
            ),
        )
        print("  [OK] P3-D15: primary_user created (role=ADMIN)")


def seed_capital_silo():
    """Insert initial capital silo for primary_user in P3-D16."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d16_user_capital_silos (
                user_id, status, role,
                starting_capital, total_capital, accounts,
                max_simultaneous_positions, max_portfolio_risk_pct,
                correlation_threshold, user_kelly_ceiling,
                capital_history, telegram_chat_id, created, last_updated
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, now(), now()
            )""",
            (
                "primary_user", "ACTIVE", "ADMIN",
                0.0, 0.0, json.dumps([]),
                0, 0.10, 0.70, 1.0,
                json.dumps([]), None,
            ),
        )
        print("  [OK] P3-D16: primary_user capital silo created")


if __name__ == "__main__":
    print("=" * 60)
    print("CAPTAIN FUNCTION — Test Asset & User Seed")
    print("=" * 60)
    seed_es_asset()
    seed_primary_user()
    seed_capital_silo()
    print("\nSeed complete.")
