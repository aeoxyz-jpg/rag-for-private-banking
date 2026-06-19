"""Network-free checks for the Phase-2 wealth-graph dataset."""
import networkx as nx
from rm_assistant import config
from rm_assistant.wealthgraph import model


def test_add_typed_node_and_edge():
    g = model.new_graph()
    model.add_node(g, "P1", "NaturalPerson", name="Ada", segments=["private_wealth"])
    model.add_node(g, "E1", "LegalEntity", name="Acme", kind="opco")
    model.add_edge(g, "P1", "E1", "owns_shares_in", percent=0.6)
    assert g.nodes["P1"]["label"] == "NaturalPerson"
    assert g.nodes["P1"]["name"] == "Ada"
    types = [d["type"] for _, _, d in g.edges("P1", data=True)]
    assert types == ["owns_shares_in"]
    assert model.edges_of_type(g, "owns_shares_in")[0][2]["percent"] == 0.6


def test_vocab_constants_are_disjoint_and_complete():
    assert "private_wealth" in model.SEGMENTS
    assert {"settlor_of", "beneficiary_of"} <= set(model.REL_TYPES)
    assert set(model.TRUST_ROLES) <= set(model.REL_TYPES)
    assert "NaturalPerson" in model.NODE_LABELS and "Trust" in model.NODE_LABELS


from rm_assistant.wealthgraph import builder


def _labels(g):
    from collections import Counter
    return Counter(d["label"] for _, d in g.nodes(data=True))


def test_builder_is_deterministic_and_populated():
    g1 = builder.build_canonical(seed=42)
    g2 = builder.build_canonical(seed=42)
    assert set(g1.nodes) == set(g2.nodes)
    assert g1.number_of_edges() == g2.number_of_edges()
    counts = _labels(g1)
    assert counts["RelationshipManager"] == 8
    assert counts["Household"] == 120
    assert counts["LegalEntity"] == 200
    assert counts["Trust"] == 40
    assert counts["NaturalPerson"] >= 240
    assert counts["Account"] == 400


def test_persons_have_segments_and_generation():
    g = builder.build_canonical(seed=42)
    persons = [d for _, d in g.nodes(data=True) if d["label"] == "NaturalPerson"]
    assert all(p["segments"] for p in persons)
    assert any(p["generation"] == 3 for p in persons)
    assert all(set(p["segments"]) <= set(model.SEGMENTS) for p in persons)


def test_relationships_have_depth_and_cycles():
    g = builder.build_canonical(seed=42)
    own = model.edges_of_type(g, "owns_shares_in")
    assert own, "ownership edges exist"
    sub = nx.DiGraph()
    for u, v, d in g.edges(data=True):
        if d["type"] in ("owns_shares_in", "controls") and u.startswith(("P", "E")) and v.startswith("E"):
            sub.add_edge(u, v)
    longest = max((len(p) for p in _all_simple_chain_lengths(sub)), default=0)
    assert longest >= 4, f"expected a 3+ hop chain (>=4 nodes), got {longest}"
    assert any(True for _ in nx.simple_cycles(sub)), "expected at least one ownership cycle"
    for rt in ("settlor_of", "beneficiary_of", "parent_of", "advises", "prospecting_target", "supplier_of"):
        assert model.edges_of_type(g, rt), f"missing {rt} edges"


def _all_simple_chain_lengths(dg):
    roots = [n for n in dg if dg.in_degree(n) == 0]
    leaves = [n for n in dg if dg.out_degree(n) == 0]
    for r in roots:
        for lf in leaves:
            if r != lf and nx.has_path(dg, r, lf):
                yield nx.shortest_path(dg, r, lf)


from rm_assistant.wealthgraph import ubo


def test_ubo_is_cycle_safe_and_thresholded():
    g = model.new_graph()
    for n, lab in [("P1", "NaturalPerson"), ("E1", "LegalEntity"),
                   ("E2", "LegalEntity"), ("E3", "LegalEntity")]:
        model.add_node(g, n, lab, name=n)
    model.add_edge(g, "P1", "E1", "owns_shares_in", percent=0.8)
    model.add_edge(g, "E1", "E3", "owns_shares_in", percent=0.5)
    model.add_edge(g, "E1", "E2", "owns_shares_in", percent=0.2)
    model.add_edge(g, "E2", "E1", "owns_shares_in", percent=0.2)
    rows = ubo.derive_ubo(g, threshold=0.25)
    by_entity = {(r["entity_id"], r["person_id"]): r for r in rows}
    assert ("E1", "P1") in by_entity
    e3 = by_entity[("E3", "P1")]
    assert abs(e3["effective_pct"] - 0.4) < 1e-9
    assert e3["path"][0] == "P1" and e3["path"][-1] == "E3"


def test_ubo_runs_on_full_graph():
    g = builder.build_canonical(seed=42)
    rows = ubo.derive_ubo(g, threshold=config.WG_UBO_THRESHOLD)
    assert isinstance(rows, list) and rows
    assert all(r["entity_id"].startswith("E") and r["person_id"].startswith("P") for r in rows)


def test_ubo_is_realistic_per_entity():
    """Control-based UBO + clean ownership trees -> ~1-2 ultimate owners per entity, not dozens
    (regression guard against the hub-reuse / sum-over-all-paths inflation)."""
    import statistics
    from collections import Counter
    g = builder.build_canonical(seed=42)
    per_entity = Counter(r["entity_id"] for r in ubo.derive_ubo(g, threshold=0.25))
    assert per_entity
    assert max(per_entity.values()) <= 4, f"too many UBOs on one entity: {max(per_entity.values())}"
    assert statistics.mean(per_entity.values()) <= 2.0


from rm_assistant.wealthgraph import relational


def test_relational_projection_round_trips(tmp_path):
    g = builder.build_canonical(seed=42)
    dbp = tmp_path / "wealth.db"
    relational.project_relational(g, dbp)
    from rm_assistant import db
    conn = db.connect(dbp, readonly=True)
    try:
        n_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        n_rels = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        n_ubo = conn.execute("SELECT COUNT(*) FROM ubo").fetchone()[0]
        n_bi = conn.execute("SELECT COUNT(*) FROM banking_identities").fetchone()[0]
        labels = {r[0] for r in conn.execute("SELECT DISTINCT label FROM nodes")}
    finally:
        conn.close()
    assert n_nodes == g.number_of_nodes()
    assert n_rels == g.number_of_edges()
    assert n_ubo > 0 and n_bi > 0
    assert {"NaturalPerson", "Trust", "LegalEntity"} <= labels


from rm_assistant.wealthgraph import graph_export
import json as _json


def test_graph_export_matches_relational(tmp_path):
    g = builder.build_canonical(seed=42)
    out = tmp_path / "wg"
    res = graph_export.export_graph(g, out)
    nodes = (out / "nodes.jsonl").read_text().strip().splitlines()
    edges = (out / "edges.jsonl").read_text().strip().splitlines()
    assert len(nodes) == g.number_of_nodes() == res["nodes"]
    assert len(edges) == g.number_of_edges() == res["edges"]
    assert (out / "graph.graphml").exists()
    first = _json.loads(nodes[0])
    assert {"id", "label"} <= set(first)
    fe = _json.loads(edges[0])
    assert {"src", "dst", "type"} <= set(fe)


from rm_assistant.wealthgraph import ground_truth


def test_ground_truth_shape(tmp_path):
    g = builder.build_canonical(seed=42)
    out = tmp_path / "graph_truth.json"
    gt = ground_truth.emit_ground_truth(g, out, threshold=config.WG_UBO_THRESHOLD)
    assert out.exists()
    for key in ("ubo", "household_members", "k_hop", "controls_entities", "shortest_paths"):
        assert key in gt
    hh = next(iter(gt["household_members"]))
    assert gt["household_members"][hh]
    sample_party = next(iter(gt["k_hop"]))
    assert set(gt["k_hop"][sample_party]) == {"1", "2", "3"}


def test_end_to_end_build_is_consistent(tmp_path):
    g = builder.build_canonical(seed=42)
    from rm_assistant.wealthgraph import relational, graph_export, ground_truth
    rel = relational.project_relational(g, tmp_path / "w.db")
    exp = graph_export.export_graph(g, tmp_path / "wg")
    gt = ground_truth.emit_ground_truth(g, tmp_path / "wg" / "graph_truth.json")
    assert rel["nodes"] == exp["nodes"] == g.number_of_nodes()
    assert rel["relationships"] == exp["edges"] == g.number_of_edges()
    assert len(gt["ubo"]) == rel["ubo"]
