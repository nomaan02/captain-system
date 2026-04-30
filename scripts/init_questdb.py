"""QuestDB schema initialization — creates all 39 canonical tables.

Delegates every CREATE TABLE to shared.canonical_schemas, the single
source of truth.  Run directly or via init_all.py.

Usage (inside container):
    python3 /app/scripts/init_questdb.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.canonical_schemas import CANONICAL_DDLS, CANONICAL_MIGRATIONS, table_name_of


def init_questdb() -> bool:
    from shared.questdb_client import get_cursor

    print(f"  Creating {len(CANONICAL_DDLS)} tables from canonical schemas...")
    ok = True
    for ddl in CANONICAL_DDLS:
        table = table_name_of(ddl)
        try:
            with get_cursor() as cur:
                cur.execute(ddl)
            print(f"  [OK] {table}")
        except Exception as exc:
            print(f"  [FAIL] {table}: {exc}")
            ok = False

    if ok:
        print(f"  {len(CANONICAL_DDLS)} tables created/verified.")

    print(f"  Applying {len(CANONICAL_MIGRATIONS)} additive migrations...")
    for migration_id, alter_sql in CANONICAL_MIGRATIONS:
        try:
            with get_cursor() as cur:
                cur.execute(alter_sql)
            print(f"  [OK] {migration_id}")
        except Exception as exc:
            msg = str(exc).lower()
            # Idempotent paths — script is safe to re-run on a tower
            # whose schema already matches the canonical state.
            if "already exists" in msg or "duplicate" in msg:
                # ADD COLUMN that already ran on a previous deploy.
                print(f"  [SKIP] {migration_id} (column already present)")
            elif "type is already" in msg:
                # ALTER COLUMN ... TYPE ... that already ran. QuestDB
                # rejects the no-op rather than treating it as a SKIP,
                # so detect the message string and translate.
                # Phase A migrations M010-M042 (DECIMAL re-types) hit
                # this every time the script is re-run on a tower whose
                # DECIMAL state is already in place.
                print(f"  [SKIP] {migration_id} (column type already correct)")
            else:
                print(f"  [FAIL] {migration_id}: {exc}")
                ok = False

    return ok


if __name__ == "__main__":
    sys.exit(0 if init_questdb() else 1)
