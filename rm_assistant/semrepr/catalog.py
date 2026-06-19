"""Uniform machine-queryable catalog over the three representations (Phase-3b). Each answers: which
governed metrics exist and how each expresses composition. All three are programmatically queryable
(a guard could enumerate the governed set to gate abstention) — the differentiator is HOW composition
is modeled, not whether the catalog exists."""
from __future__ import annotations

from .. import ontology
from . import dbt_repr, rdf_repr


def _baseline_composition(name: str) -> str:
    sql = ontology.load()["metrics"][name]["sql"]
    return "string-substitution" if "{{" in sql else "n/a"


def catalog(repr_name: str) -> dict:
    if repr_name == "baseline":
        names = sorted(ontology.load()["metrics"])
        comp = {n: _baseline_composition(n) for n in names}
    elif repr_name == "dbt":
        names = sorted(dbt_repr.load())
        comp = {n: dbt_repr.composition_kind(n) for n in names}
    elif repr_name == "rdf":
        names = rdf_repr.metrics()
        comp = {n: rdf_repr.composition_kind(n) for n in names}
    else:
        raise ValueError(f"unknown representation: {repr_name}")
    return {"metrics": names, "composition": comp, "queryable": "yes"}
