"""Force a Command Block 8 SOD recompute outside the 19:00 ET cron window.

Used during cutover of the per-session budget feature (2026-05-06) so towers
don't have to wait for the next 19:00 ET reconciliation to populate
``computed_sod.session.{NY,LON,APAC}`` per-session map.

USAGE
-----
    # Inside captain-command container:
    cmd-run force_sod_recompute.py

What it does:
    1. Iterates every account in P3-D08 with ``topstep_optimisation=true``.
    2. Calls ``_compute_sod_topstep_params`` directly (bypassing the
       19:00 ET trigger) so each account's ``topstep_state.computed_sod``
       gets the new ``session`` map written.
    3. Calls ``_reset_daily_counters`` to zero D08.daily_loss_used + write
       per-session zero rows in D23.
    4. Logs the resulting ``computed_sod.session.NY/LON/APAC.L_halt`` so
       you can eyeball that per-session budgets look reasonable.

Idempotent — running it twice produces a second SOD computation but no
trading-side effect (latest D08 row wins).

EXIT CODES
----------
    0  Success
    1  Unexpected exception (see traceback)
    2  No accounts with topstep_optimisation=true
"""
from __future__ import annotations

import logging
import sys

# Make sibling imports work when invoked as `cmd-run force_sod_recompute.py`.
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from shared.questdb_client import get_cursor


def _gui_push_stub(user_id, msg):
    """No-op GUI push — we don't want to spam the dashboard during a manual run."""
    pass


def _notify_stub(notif):
    """No-op telegram/notif route."""
    pass


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("force_sod_recompute")

    try:
        from captain_command.blocks.b8_reconciliation import (
            _compute_sod_topstep_params,
            _reset_daily_counters,
            _get_all_accounts,
        )
    except Exception as exc:
        logger.error("Failed to import b8_reconciliation: %s", exc, exc_info=True)
        return 1

    accounts = _get_all_accounts()
    if not accounts:
        logger.error("No accounts found in P3-D08")
        return 2

    topstep_accounts = [
        ac for ac in accounts if ac.get("topstep_optimisation")
    ]
    if not topstep_accounts:
        logger.warning("No accounts with topstep_optimisation=true — nothing to do")
        return 2

    logger.info(
        "Forcing SOD recompute for %d topstep-optimised account(s) "
        "out of %d total",
        len(topstep_accounts), len(accounts),
    )

    for ac in topstep_accounts:
        ac_id = ac["account_id"]
        user_id = ac["user_id"]
        logger.info("Recomputing SOD for account %s (user %s)", ac_id, user_id)
        try:
            _compute_sod_topstep_params(
                ac_id=ac_id,
                user_id=user_id,
                ac=ac,
                gui_push_fn=_gui_push_stub,
                notify_fn=_notify_stub,
            )
        except Exception as exc:
            logger.error(
                "_compute_sod_topstep_params failed for %s: %s",
                ac_id, exc, exc_info=True,
            )
            # Continue with the rest — partial success is better than aborting.

    logger.info("Resetting daily counters (D08 + per-session D23)")
    try:
        _reset_daily_counters()
    except Exception as exc:
        logger.error("_reset_daily_counters failed: %s", exc, exc_info=True)

    # Verification: dump computed_sod.session for each account.
    logger.info("Verifying per-session map in D08:")
    with get_cursor() as cur:
        cur.execute(
            """SELECT account_id, topstep_state
               FROM p3_d08_tsm_state
               LATEST ON last_updated PARTITION BY account_id"""
        )
        for row in cur.fetchall() or []:
            ac_id = row[0]
            ts_state_raw = row[1] or "{}"
            try:
                from shared.json_helpers import parse_json_decimal
                ts_state = parse_json_decimal(ts_state_raw, {})
                computed_sod = ts_state.get("computed_sod", {})
                sess = computed_sod.get("session", {})
                if not sess:
                    logger.warning(
                        "Account %s: computed_sod.session is EMPTY — "
                        "Phase 2 SOD recompute may have failed",
                        ac_id,
                    )
                    continue
                ny = sess.get("NY", {})
                lon = sess.get("LON", {})
                apac = sess.get("APAC", {})
                logger.info(
                    "Account %s session L_halt: NY=%s LON=%s APAC=%s "
                    "(source=%s)",
                    ac_id,
                    ny.get("L_halt"), lon.get("L_halt"), apac.get("L_halt"),
                    computed_sod.get("session_shares_source"),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to parse topstep_state for %s: %s",
                    ac_id, exc,
                )

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
