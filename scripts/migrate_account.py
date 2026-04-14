#!/usr/bin/env python3
"""Migrate QuestDB tables from one TopstepX account ID to another.

Updates D16 (capital silo), D08 (TSM state), and D25 (circuit breaker)
by inserting new rows with the new account ID, preserving all other config.

Usage (inside any captain container with QuestDB access):
  python3 /app/scripts/migrate_account.py OLD_ID NEW_ID NEW_NAME

Example:
  python3 /app/scripts/migrate_account.py 20319811 20260837 "150KTC-V2-551001-19064435"
"""

import json
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="[MIGRATE] %(message)s")
logger = logging.getLogger("migrate")


def main():
    if len(sys.argv) < 4:
        print("Usage: migrate_account.py OLD_ID NEW_ID NEW_NAME")
        print("Example: migrate_account.py 20319811 20260837 '150KTC-V2-551001-19064435'")
        sys.exit(1)

    old_id = sys.argv[1]
    new_id = sys.argv[2]
    new_name = sys.argv[3]

    logger.info("=" * 60)
    logger.info("ACCOUNT MIGRATION: %s → %s (%s)", old_id, new_id, new_name)
    logger.info("=" * 60)

    from shared.questdb_client import get_cursor

    # ── D16: Capital silo ──
    logger.info("")
    logger.info("D16: Capital silo...")
    with get_cursor() as cur:
        cur.execute(
            """SELECT user_id, starting_capital, total_capital, accounts,
                      max_simultaneous_positions, max_portfolio_risk_pct,
                      correlation_threshold, user_kelly_ceiling
               FROM p3_d16_user_capital_silos
               LATEST ON last_updated PARTITION BY user_id"""
        )
        row = cur.fetchone()

    if not row:
        logger.error("  No existing D16 row found — cannot migrate")
        return False

    user_id = row[0]
    old_accounts = json.loads(row[3]) if row[3] else []
    new_accounts = json.dumps([new_id])

    logger.info("  Old accounts: %s", old_accounts)
    logger.info("  New accounts: [%s]", new_id)

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d16_user_capital_silos (
                user_id, starting_capital, total_capital, accounts,
                max_simultaneous_positions, max_portfolio_risk_pct,
                correlation_threshold, user_kelly_ceiling, last_updated
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (user_id, row[1], row[2], new_accounts,
             row[4], row[5], row[6], row[7]),
        )
    logger.info("  D16: OK")

    # ── D08: TSM state ──
    logger.info("")
    logger.info("D08: TSM state...")
    with get_cursor() as cur:
        cur.execute(
            """SELECT account_id, user_id, name, classification,
                      starting_balance, current_balance, current_drawdown, daily_loss_used,
                      profit_target, max_drawdown_limit, max_daily_loss, max_contracts,
                      commission_per_contract, instrument_permissions,
                      overnight_allowed, margin_buffer_pct,
                      topstep_optimisation, scaling_plan_active, scaling_tier_micros
               FROM p3_d08_tsm_state
               WHERE account_id = %s
               ORDER BY last_updated DESC
               LIMIT 1""",
            (old_id,),
        )
        tsm_row = cur.fetchone()

    if not tsm_row:
        logger.error("  No D08 row for account %s — cannot migrate", old_id)
        return False

    logger.info("  Old: account=%s, name=%s, balance=$%.2f", tsm_row[0], tsm_row[2], tsm_row[5])

    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO p3_d08_tsm_state (
                account_id, user_id, name, classification,
                starting_balance, current_balance, current_drawdown, daily_loss_used,
                profit_target, max_drawdown_limit, max_daily_loss, max_contracts,
                commission_per_contract, instrument_permissions,
                overnight_allowed, margin_buffer_pct,
                topstep_optimisation, scaling_plan_active, scaling_tier_micros,
                last_updated
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
            (new_id, tsm_row[1], new_name, tsm_row[3],
             tsm_row[4], tsm_row[4],  # reset current_balance to starting
             0.0, 0.0,  # reset drawdown and daily loss
             tsm_row[8], tsm_row[9], tsm_row[10], tsm_row[11],
             tsm_row[12], tsm_row[13], tsm_row[14], tsm_row[15],
             tsm_row[16], tsm_row[17], tsm_row[18]),
        )
    logger.info("  New: account=%s, name=%s, balance=$%.2f", new_id, new_name, tsm_row[4])
    logger.info("  D08: OK")

    # ── D25: Circuit breaker ──
    logger.info("")
    logger.info("D25: Circuit breaker...")
    with get_cursor() as cur:
        cur.execute(
            """SELECT account_id, model_m, r_bar, beta_b, sigma, rho_bar,
                      n_observations, p_value, l_star, cold_start
               FROM p3_d25_circuit_breaker_params
               WHERE account_id = %s
               ORDER BY last_updated DESC
               LIMIT 1""",
            (old_id,),
        )
        cb_row = cur.fetchone()

    if not cb_row:
        logger.warning("  No D25 row for account %s — inserting cold-start defaults", old_id)
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d25_circuit_breaker_params (
                    account_id, model_m, r_bar, beta_b, sigma, rho_bar,
                    n_observations, p_value, l_star, cold_start, last_updated
                ) VALUES (%s, 20, 0.0, 0.0, 1.0, 0.0, 0, 1.0, 0.0, true, now())""",
                (new_id,),
            )
    else:
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO p3_d25_circuit_breaker_params (
                    account_id, model_m, r_bar, beta_b, sigma, rho_bar,
                    n_observations, p_value, l_star, cold_start, last_updated
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())""",
                (new_id, cb_row[1], cb_row[2], cb_row[3],
                 cb_row[4], cb_row[5], cb_row[6], cb_row[7],
                 cb_row[8], cb_row[9]),
            )
    logger.info("  D25: OK")

    # ── Verify ──
    logger.info("")
    logger.info("Verifying...")
    with get_cursor() as cur:
        cur.execute(
            """SELECT accounts FROM p3_d16_user_capital_silos
               LATEST ON last_updated PARTITION BY user_id"""
        )
        d16 = cur.fetchone()
        d16_accounts = json.loads(d16[0]) if d16 and d16[0] else []

        cur.execute(
            """SELECT account_id, name FROM p3_d08_tsm_state
               ORDER BY last_updated DESC LIMIT 1"""
        )
        d08 = cur.fetchone()

        cur.execute(
            """SELECT account_id, cold_start FROM p3_d25_circuit_breaker_params
               ORDER BY last_updated DESC LIMIT 1"""
        )
        d25 = cur.fetchone()

    logger.info("  D16 accounts: %s %s", d16_accounts,
                "OK" if new_id in d16_accounts else "MISMATCH")
    logger.info("  D08 account:  %s (%s) %s", d08[0] if d08 else "?",
                d08[1] if d08 else "?",
                "OK" if d08 and d08[0] == new_id else "MISMATCH")
    logger.info("  D25 account:  %s %s", d25[0] if d25 else "?",
                "OK" if d25 and d25[0] == new_id else "MISMATCH")

    logger.info("")
    logger.info("=" * 60)
    logger.info("MIGRATION COMPLETE")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Update .env: TOPSTEP_ACCOUNT_NAME=%s", new_name)
    logger.info("  2. Restart containers: docker compose ... up -d")
    return True


if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except Exception as e:
        logger.error("MIGRATION FAILED: %s", e, exc_info=True)
        sys.exit(1)
