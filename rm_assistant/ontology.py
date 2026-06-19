"""Load ontology.yaml and render the prompt fragments the retrieval pillars share:
a compact schema+glossary block (the backbone that makes text-to-SQL reliable, spec §4.1/§3.5)
and the governed metric definitions."""
from __future__ import annotations

import functools
import sqlite3
from pathlib import Path

import yaml

from . import config

_PATH = Path(__file__).resolve().parent.parent / "ontology.yaml"


@functools.lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load(_PATH.read_text())


def as_of() -> str:
    return load()["as_of_date"]


def schema_prompt(conn: sqlite3.Connection) -> str:
    """Per-table: real column types (PRAGMA) annotated with glossary descriptions.
    Only tables present in the glossary are exposed to the model."""
    o = load()
    lines: list[str] = []
    for table, gloss in o["glossary"].items():
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not cols:
            continue
        lines.append(f"TABLE {table}  -- {gloss.get('_desc', '')}")
        for c in cols:
            desc = gloss.get(c[1], "")
            lines.append(f"  {c[1]} {c[2]}" + (f"  -- {desc}" if desc else ""))
    return "\n".join(lines)


def metrics_prompt() -> str:
    o = load()
    out = [f"As-of date (use for recency / 'today'): {o['as_of_date']}",
           "Governed metric definitions (use these exact formulas for consistency):"]
    for name, m in o["metrics"].items():
        out.append(f"\n# {name} — {m['label']}: {m['desc'].strip()}")
        out.append(m["sql"].strip())
    return "\n".join(out)


def metric_sql(name: str) -> str:
    """Return a metric's SQL with any {{ref}} placeholders expanded to nested subqueries."""
    o = load()
    sql = o["metrics"][name]["sql"]
    for ref in o["metrics"]:
        sql = sql.replace(f"{{{{{ref}}}}}", o["metrics"][ref]["sql"].strip())
    return sql


def metric_binds(sql: str, **extra) -> dict:
    """Named-param bindings a metric SQL needs (:as_of, :start), filtered to those present."""
    o = load()
    avail = {"as_of": o["as_of_date"], "start": "1900-01-01", **extra}
    return {k: v for k, v in avail.items() if f":{k}" in sql}
