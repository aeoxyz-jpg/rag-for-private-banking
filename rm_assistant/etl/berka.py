"""Berka ETL: CTU public MariaDB (relational.fel.cvut.cz) -> local SQLite.

Loads the raw 8-table Berka schema verbatim. Mapping onto the unified
"virtual private bank" schema (spec §3.3) happens in M1, not here. Idempotent:
each table is dropped and recreated, so re-running gives a clean reproducible load.
"""
from __future__ import annotations

import datetime
import sqlite3
from decimal import Decimal

import pymysql

from .. import config, db

_BATCH = 5000

# PyMySQL yields Decimal/date/datetime; sqlite3 binds only str/int/float/bytes/None.
sqlite3.register_adapter(Decimal, float)
sqlite3.register_adapter(datetime.date, lambda d: d.isoformat())
sqlite3.register_adapter(datetime.datetime, lambda d: d.isoformat())


def _copy_table(src: pymysql.connections.Connection, dst: sqlite3.Connection, table: str) -> int:
    scur = src.cursor()
    scur.execute(f"SELECT * FROM `{table}`")
    cols = [d[0] for d in scur.description]
    col_defs = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(["?"] * len(cols))

    dst.execute(f'DROP TABLE IF EXISTS "{table}"')
    dst.execute(f'CREATE TABLE "{table}" ({col_defs})')

    total = 0
    while True:
        rows = scur.fetchmany(_BATCH)
        if not rows:
            break
        dst.executemany(
            f'INSERT INTO "{table}" ({col_defs}) VALUES ({placeholders})', rows
        )
        total += len(rows)
    dst.commit()
    return total


def load(tables: list[str] = config.BERKA_TABLES) -> dict[str, int]:
    """Pull `tables` from the CTU Berka DB into the raw SQLite mirror. Returns row counts."""
    src = pymysql.connect(connect_timeout=30, **config.BERKA)
    dst = db.connect(config.BERKA_RAW_DB)
    try:
        counts: dict[str, int] = {}
        for t in tables:
            counts[t] = _copy_table(src, dst, t)
            print(f"  loaded {t:10} {counts[t]:>9,} rows")
        return counts
    finally:
        src.close()
        dst.close()
