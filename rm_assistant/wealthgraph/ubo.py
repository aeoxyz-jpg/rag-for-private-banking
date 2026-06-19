"""Control-based ultimate-beneficial-owner derivation over owns_shares_in chains (FATF-style).

A natural person is a UBO of an entity when they either (a) directly own >= threshold of it, or
(b) sit atop a *majority control chain* (every intermediate link > `control`) that reaches a
company directly owning >= threshold of it. Control only propagates through majority-owned links —
a minority stake does not let you attribute the subsidiary's holdings to yourself. This is far
stricter (and more realistic: ~1-4 UBOs per entity) than summing effective ownership over every
path, which over-attributes through long minority chains."""
from __future__ import annotations

import networkx as nx


def _ownership_digraph(g: nx.MultiDiGraph) -> nx.DiGraph:
    dg = nx.DiGraph()
    for u, v, d in g.edges(data=True):
        if d["type"] == "owns_shares_in":
            pct = float(d.get("percent", 0.0))
            if dg.has_edge(u, v):
                dg[u][v]["percent"] = max(dg[u][v]["percent"], pct)
            else:
                dg.add_edge(u, v, percent=pct)
    return dg


def derive_ubo(g: nx.MultiDiGraph, threshold: float = 0.25, control: float = 0.5) -> list[dict]:
    """Return UBO rows {entity_id, person_id, effective_pct, path}. `control` is the majority
    threshold for propagating control through an intermediate link. Cycle-safe."""
    dg = _ownership_digraph(g)
    maj = nx.DiGraph()  # control subgraph: only majority (> control) ownership links
    for u, v, d in dg.edges(data=True):
        if d["percent"] > control:
            maj.add_edge(u, v, percent=d["percent"])

    persons = [n for n, d in g.nodes(data=True) if d["label"] == "NaturalPerson" and n in dg]
    rows: list[dict] = []
    for p in persons:
        controlled = nx.descendants(maj, p) if p in maj else set()  # entities P controls (cycle-safe)
        best: dict[str, tuple] = {}
        for x in {p} | controlled:
            if x == p:
                ctrl_pct, ctrl_path = 1.0, [p]
            else:
                ctrl_path = nx.shortest_path(maj, p, x)
                ctrl_pct = 1.0
                for a, b in zip(ctrl_path, ctrl_path[1:]):
                    ctrl_pct *= maj[a][b]["percent"]
            for _, e, ed in dg.edges(x, data=True):
                if g.nodes[e]["label"] != "LegalEntity" or ed["percent"] < threshold:
                    continue
                eff = ctrl_pct * ed["percent"]
                path = ctrl_path if ctrl_path[-1] == e else ctrl_path + [e]
                if e not in best or eff > best[e][0]:
                    best[e] = (eff, path)
        for e, (eff, path) in best.items():
            rows.append({"entity_id": e, "person_id": p,
                         "effective_pct": round(eff, 6), "path": path})
    return rows
