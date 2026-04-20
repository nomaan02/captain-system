#!/usr/bin/env python3
"""Session C — verify_schema_drift.py

Compares every table in canonical_schemas.py against the live QuestDB schema.
Exits 0 if all tables match; exits 1 and prints a readable diff on any drift.

Usage (locally):
    python scripts/verify_schema_drift.py

Usage (inside container):
    python /captain/scripts/verify_schema_drift.py
"""
import re
import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, "/app")

from shared.canonical_schemas import CANONICAL_DDLS, table_name_of
from shared.questdb_client import get_cursor

# QuestDB may use slightly different type names for the same underlying type.
# Normalise both sides before comparing.
_TYPE_ALIASES = {
    "BOOL": "BOOLEAN",
    "VARCHAR": "STRING",
    "BIGINT": "LONG",
    "INTEGER": "INT",
    "REAL": "FLOAT",
    "INT4": "INT",
    "INT8": "LONG",
    "FLOAT4": "FLOAT",
    "FLOAT8": "DOUBLE",
}


def _normalise(type_name: str) -> str:
    t = type_name.strip().upper()
    return _TYPE_ALIASES.get(t, t)


def _parse_ddl_columns(ddl: str) -> dict:
    """Extract {col_name: normalised_type} from a CREATE TABLE DDL string.

    Walks only the top-level parenthesised block so nested items (e.g. future
    complex types) don't confuse the parser.
    """
    # Find the top-level ( ... ) column block
    depth = 0
    start = ddl.index("(")
    end = start
    for i, ch in enumerate(ddl[start:], start):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i
                break

    col_block = ddl[start + 1 : end]
    columns = {}
    for raw_line in col_block.split("\n"):
        line = raw_line.strip().rstrip(",")
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            col_name = parts[0]
            col_type = _normalise(parts[1])
            columns[col_name] = col_type
    return columns


def _live_columns(table_name: str):
    """Return {col_name: normalised_type} from QuestDB, or None if table absent."""
    try:
        with get_cursor() as cur:
            cur.execute(
                f"SELECT columnName, columnType FROM table_columns('{table_name}')"
            )
            rows = cur.fetchall()
        if not rows:
            return None
        return {row[0]: _normalise(row[1]) for row in rows}
    except Exception:
        return None


def main():
    missing_tables = []
    drifted_tables = []

    for ddl in CANONICAL_DDLS:
        tname = table_name_of(ddl)
        expected = _parse_ddl_columns(ddl)
        actual = _live_columns(tname)

        if actual is None:
            missing_tables.append(tname)
            continue

        exp_set = set(expected)
        act_set = set(actual)

        extra_cols = act_set - exp_set
        absent_cols = exp_set - act_set
        type_mismatches = {
            col: (expected[col], actual[col])
            for col in exp_set & act_set
            if expected[col] != actual[col]
        }

        if extra_cols or absent_cols or type_mismatches:
            drifted_tables.append(
                {
                    "table": tname,
                    "extra": sorted(extra_cols),
                    "absent": sorted(absent_cols),
                    "types": type_mismatches,
                }
            )

    total = len(CANONICAL_DDLS)

    if missing_tables:
        print(f"MISSING ({len(missing_tables)} tables not in QuestDB):")
        for t in missing_tables:
            print(f"  - {t}")

    if drifted_tables:
        print(f"DRIFT ({len(drifted_tables)} tables differ from canonical):")
        for d in drifted_tables:
            print(f"  {d['table']}:")
            if d["absent"]:
                print(f"    absent cols (in DDL, not in DB): {d['absent']}")
            if d["extra"]:
                print(f"    extra cols (in DB, not in DDL):  {d['extra']}")
            for col, (exp, act) in sorted(d["types"].items()):
                print(f"    type mismatch {col}: DDL={exp}, DB={act}")

    if missing_tables or drifted_tables:
        print(
            f"\nFAIL: {len(missing_tables)} missing, {len(drifted_tables)} drifted"
            f" (of {total} canonical tables)"
        )
        sys.exit(1)
    else:
        print(f"PASS: all {total} canonical tables match live QuestDB schema")
        sys.exit(0)


if __name__ == "__main__":
    main()
