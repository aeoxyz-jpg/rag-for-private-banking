"""SQLite connection helper for the structured core (spec §3.1)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config


def connect(path: Path = config.DB_PATH, *, readonly: bool = False) -> sqlite3.Connection:
    path = Path(path)
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
