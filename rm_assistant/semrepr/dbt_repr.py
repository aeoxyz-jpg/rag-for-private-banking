"""dbt/Cube-style declarative representation (Phase-3b). Simple metrics generate SQL from
{source, joins, measure, group_by, where?}; a `ratio` composite references another metric by name
(native composition — its compiled SQL is inlined); an `expr` composite is a raw-SQL escape hatch."""
from __future__ import annotations

import functools
from pathlib import Path

import yaml

SRC = Path(__file__).resolve().parent / "specs" / "metrics.dbt.yml"


@functools.lru_cache(maxsize=1)
def load() -> dict:
    return yaml.safe_load(Path(SRC).read_text())["metrics"]


def compile_sql(name: str, specs: dict | None = None) -> str:
    specs = specs or load()
    s = specs[name]
    if "ratio" in s:
        r = s["ratio"]
        base = compile_sql(r["of"], specs)
        joins = "\n".join(r.get("extra_joins", []))
        return (f"SELECT m.client_id, m.{r['of']} / ({r['over_expr']}) AS {name}\n"
                f"FROM ( {base} ) m\n{joins}")
    if "expr" in s:
        out = s["expr"]
        for key, ref in s.get("expr_refs", {}).items():
            out = out.replace("{" + key + "}", compile_sql(ref, specs))
        return out
    joins = "\n".join(s.get("joins", []))
    where = f"WHERE {s['where']}\n" if s.get("where") else ""
    return (f"SELECT {s['entity']} AS client_id, {s['measure']} AS {name}\n"
            f"FROM {s['source']}\n{joins}\n{where}GROUP BY {s['group_by']}")


def composition_kind(name: str, specs: dict | None = None) -> str:
    """How a metric expresses composition: native typed reference, raw-SQL escape, or n/a (simple)."""
    specs = specs or load()
    s = specs[name]
    if "ratio" in s:
        return "native"
    if "expr" in s:
        return "escape"
    return "n/a"
