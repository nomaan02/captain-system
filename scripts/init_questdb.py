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
            if "already exists" in str(exc).lower() or "duplicate" in str(exc).lower():
                print(f"  [SKIP] {migration_id} (column already present)")
            else:
                print(f"  [FAIL] {migration_id}: {exc}")
                ok = False

    return ok


if __name__ == "__main__":
    sys.exit(0 if init_questdb() else 1)
