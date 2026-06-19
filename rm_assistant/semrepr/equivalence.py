"""Equivalence gate (Phase-3b): a representation's compiled SQL must return the identical
client_id -> value set as ontology.metric_sql on data/rm.db. Float values compared at 6 decimals."""
from __future__ import annotations

import sqlite3

from .. import db, ontology
from . import dbt_repr, rdf_repr


def _result(conn, sql: str) -> dict:
    binds = ontology.metric_binds(sql)
    out = {}
    for row in conn.execute(sql, binds).fetchall():
        v = row[1]
        out[str(row[0])] = round(v, 6) if isinstance(v, float) else v
    return out


def same_result(conn, sql_a: str, sql_b: str) -> bool:
    return _result(conn, sql_a) == _result(conn, sql_b)


def _compiled(repr_name: str, name: str) -> str:
    return dbt_repr.compile_sql(name) if repr_name == "dbt" else rdf_repr.assemble_sql(name)


def check(repr_name: str, conn: sqlite3.Connection | None = None) -> dict:
    """Per metric: does `repr_name`'s SQL match the canonical ontology SQL? -> {metric: bool}."""
    close = conn is None
    conn = conn or db.connect(readonly=True)
    try:
        return {name: same_result(conn, ontology.metric_sql(name), _compiled(repr_name, name))
                for name in ontology.load()["metrics"]}
    finally:
        if close:
            conn.close()
