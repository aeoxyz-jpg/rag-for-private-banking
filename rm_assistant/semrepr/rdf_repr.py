"""RDF/graph representation (Phase-3b). Metrics are m:Metric nodes with an m:sql literal body and
m:dependsOn edges; assemble_sql inlines each dependency's body at its `{local_name}` placeholder.
The dependency is modeled as a real triple (native lineage), but the metric logic stays a SQL literal —
RDF does not generate SQL from semantics."""
from __future__ import annotations

import functools
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import RDF

M = Namespace("http://rm/metric#")
SRC = Path(__file__).resolve().parent / "specs" / "metrics.ttl"


@functools.lru_cache(maxsize=1)
def _graph() -> Graph:
    g = Graph()
    g.parse(SRC, format="turtle")
    return g


def metrics() -> list[str]:
    g = _graph()
    return sorted(str(s).split("#")[1] for s in g.subjects(RDF.type, M.Metric))


def assemble_sql(name: str, _seen: frozenset[str] = frozenset()) -> str:
    if name in _seen:
        raise ValueError(f"dependsOn cycle through {name}")
    g = _graph()
    body = str(g.value(M[name], M.sql))
    for dep in g.objects(M[name], M.dependsOn):
        local = str(dep).split("#")[1]
        body = body.replace("{" + local + "}", assemble_sql(local, _seen | {name}))
    return body


def composition_kind(name: str) -> str:
    """native-edge if the metric has dependsOn triples (lineage modeled natively), else n/a."""
    g = _graph()
    return "native-edge" if list(g.objects(M[name], M.dependsOn)) else "n/a"
