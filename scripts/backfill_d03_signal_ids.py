#!/usr/bin/env python3
"""Phase 7 — Backfill ``signal_id`` for legacy D03 rows.

Per Stage 1B §0 D12 / §5.4: rows written before Phase 7 lacked a
``signal_id`` column. The schema was extended via M002 to add the column;
this script assigns a synthetic ``LEGACY-<uuid>`` to every row whose
``signal_id`` is currently NULL.

QuestDB note
============
QuestDB does not support generic ``UPDATE`` on WAL-partitioned tables.
DEDUP UPSERT KEYS makes per-row INSERTs idempotent: re-inserting a
``(ts, trade_id)`` key replaces the existing row. This script reads every
row with ``signal_id IS NULL`` and re-inserts the same row with a freshly
allocated synthetic signal_id.

Idempotent — re-running after partial completion finishes the remainder.
"""

import argparse
import logging
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.questdb_client import get_cursor, qexecute

logger = logging.getLogger(__name__)


SELECT_LEGACY_SQL = """
SELECT trade_id, user_id, account_id, asset, direction, entry_price,
       signal_entry_price, exit_price, contracts, gross_pnl, commission,
       pnl, slippage, outcome, entry_time, exit_time, regime_at_entry,
       aim_modifier_at_entry, aim_breakdown_at_entry, session, tsm_used,
       model_m, ts
FROM p3_d03_trade_outcome_log
WHERE signal_id IS NULL OR signal_id = ''
"""


REINSERT_SQL = """
INSERT INTO p3_d03_trade_outcome_log
    (trade_id, signal_id, user_id, account_id, asset, direction,
     entry_price, signal_entry_price, exit_price, contracts,
     gross_pnl, commission, pnl, slippage, outcome,
     entry_time, exit_time, regime_at_entry, aim_modifier_at_entry,
     aim_breakdown_at_entry, session, tsm_used, model_m, ts)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s)
"""


def backfill(dry_run: bool = False) -> int:
    """Assign ``LEGACY-<uuid>`` to every D03 row missing ``signal_id``.

    Returns the number of rows that received a new ``signal_id``.
    """
    with get_cursor() as cur:
        cur.execute(SELECT_LEGACY_SQL)
        rows = cur.fetchall()

    if not rows:
        logger.info("No legacy D03 rows missing signal_id.")
        return 0

    logger.info("Found %d D03 rows missing signal_id.", len(rows))
    if dry_run:
        return len(rows)

    with get_cursor() as cur:
        for row in rows:
            new_id = f"LEGACY-{uuid.uuid4()}"
            qexecute(
                cur,
                REINSERT_SQL,
                (
                    row[0],   # trade_id  (DEDUP key — re-insert replaces)
                    new_id,   # signal_id (LEGACY-…)
                    *row[1:],
                ),
            )

    logger.info("Backfilled %d rows with LEGACY- signal_ids.", len(rows))
    return len(rows)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count legacy rows but make no changes.",
    )
    args = parser.parse_args()
    n = backfill(dry_run=args.dry_run)
    logger.info("Done. %d rows %s.", n, "would be backfilled" if args.dry_run else "backfilled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
