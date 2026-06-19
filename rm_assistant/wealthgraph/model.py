"""Canonical-graph vocabulary + typed helpers over a networkx.MultiDiGraph.

One in-memory MultiDiGraph is the single source of truth; every projector (relational,
graph export, ground truth) reads from it. Node attr `label`; edge attr `type`."""
from __future__ import annotations

import networkx as nx

NODE_LABELS = ("NaturalPerson", "Household", "LegalEntity", "Trust",
               "Account", "Product", "Prospect", "RelationshipManager")
SEGMENTS = ("consumer", "smb", "commercial", "private_wealth")
ENTITY_KINDS = ("opco", "holdco", "spv", "foundation")
TRUST_ROLES = ("settlor_of", "trustee_of", "beneficiary_of", "protector_of", "other_control_of")
REL_TYPES = (
    "spouse_of", "parent_of", "sibling_of", "member_of_household",
    *TRUST_ROLES,
    "owns_shares_in", "controls", "director_of", "authorized_signer_of",
    "ultimate_beneficial_owner_of",
    "owns_account", "holds_product",
    "supplier_of", "competitor_of", "partner_with", "same_family_enterprise",
    "advises", "referred_by", "prospecting_target", "introduced_to",
)


def new_graph() -> nx.MultiDiGraph:
    return nx.MultiDiGraph()


def add_node(g: nx.MultiDiGraph, node_id: str, label: str, **props) -> str:
    assert label in NODE_LABELS, f"unknown label {label}"
    g.add_node(node_id, label=label, **props)
    return node_id


def add_edge(g: nx.MultiDiGraph, src: str, dst: str, rel_type: str, **props) -> None:
    assert rel_type in REL_TYPES, f"unknown rel_type {rel_type}"
    g.add_edge(src, dst, type=rel_type, **props)


def edges_of_type(g: nx.MultiDiGraph, rel_type: str) -> list[tuple[str, str, dict]]:
    return [(u, v, d) for u, v, d in g.edges(data=True) if d.get("type") == rel_type]
