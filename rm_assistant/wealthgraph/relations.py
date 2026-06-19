"""Layer relationships + deliberate deep structures onto the entity graph."""
from __future__ import annotations

import random

import networkx as nx

from .. import config
from . import model


def _nodes(g, label):
    return [n for n, d in g.nodes(data=True) if d["label"] == label]


def _family(g, rng):
    for h in _nodes(g, "Household"):
        members = list(g.nodes[h]["members"])
        for m in members:
            model.add_edge(g, m, h, "member_of_household")
        by_gen = {}
        for m in members:
            by_gen.setdefault(g.nodes[m]["generation"], []).append(m)
        for gen, ppl in by_gen.items():
            if len(ppl) >= 2:
                model.add_edge(g, ppl[0], ppl[1], "spouse_of")
            for child in by_gen.get(gen + 1, []):
                model.add_edge(g, ppl[0], child, "parent_of")


def _ownership_chains(g, rng):
    """Build clean ownership trees: holdcos/SPVs and opcos are CONSUMED (each entity gets one
    majority parent), so a control-based UBO walk attributes ~one ultimate owner per entity
    instead of dozens. Multi-layer chains give 3-5 hop depth; minority cross-holdings add cycles."""
    holdcos = [n for n in _nodes(g, "LegalEntity") if g.nodes[n]["kind"] in ("holdco", "spv")]
    opcos = [n for n in _nodes(g, "LegalEntity") if g.nodes[n]["kind"] == "opco"]
    persons = _nodes(g, "NaturalPerson")
    rng.shuffle(holdcos)
    rng.shuffle(opcos)
    mids = list(holdcos)   # consumable intermediate layers
    leaves = list(opcos)   # consumable operating leaves

    def _maj():
        return round(rng.uniform(0.55, 1.0), 2)  # comfortably > 0.5 -> control propagates

    while leaves:
        chain = [rng.choice(persons)]
        for _ in range(rng.randint(1, 3)):        # intermediate holdco layers (consumed globally)
            if not mids:
                break
            chain.append(mids.pop())
        for a, b in zip(chain, chain[1:]):         # majority control links down the chain
            model.add_edge(g, a, b, "owns_shares_in", percent=_maj())
        parent = chain[-1]
        for _ in range(rng.randint(1, 3)):         # operating companies under this chain
            if not leaves:
                break
            model.add_edge(g, parent, leaves.pop(), "owns_shares_in", percent=_maj())

    for h in mids:                                  # any holdco not used as a layer: one owner
        model.add_edge(g, rng.choice(persons), h, "owns_shares_in", percent=_maj())

    for _ in range(max(2, len(opcos) // 20)):       # minority cross-holdings -> cycles, no control
        a, b = rng.sample(opcos, 2)
        model.add_edge(g, a, b, "owns_shares_in", percent=round(rng.uniform(0.1, 0.3), 2))
        model.add_edge(g, b, a, "owns_shares_in", percent=round(rng.uniform(0.1, 0.3), 2))

    for e in _nodes(g, "LegalEntity"):              # directors / non-ownership control
        if rng.random() < 0.5:
            model.add_edge(g, rng.choice(persons), e, "director_of")
        if rng.random() < 0.2:
            model.add_edge(g, rng.choice(persons), e, "controls")


def _trusts(g, rng):
    persons = _nodes(g, "NaturalPerson")
    entities = _nodes(g, "LegalEntity")
    for t in _nodes(g, "Trust"):
        model.add_edge(g, rng.choice(persons), t, "settlor_of")
        trustee = rng.choice(persons + entities)
        model.add_edge(g, trustee, t, "trustee_of")
        for b in rng.sample(persons, k=rng.randint(1, 3)):
            model.add_edge(g, b, t, "beneficiary_of")
        if rng.random() < 0.3:
            model.add_edge(g, rng.choice(persons), t, "protector_of")
        holdcos = [n for n in entities if g.nodes[n]["kind"] == "holdco"]
        if holdcos and rng.random() < 0.6:
            model.add_edge(g, t, rng.choice(holdcos), "owns_shares_in",
                           percent=round(rng.uniform(0.5, 1.0), 2))


def _banking(g, rng):
    products = _nodes(g, "Product")
    for a in _nodes(g, "Account"):
        owner = g.nodes[a]["owner"]
        model.add_edge(g, owner, a, "owns_account")
        for p in rng.sample(products, k=rng.randint(0, 3)):
            model.add_edge(g, a, p, "holds_product")


def _inter_client_and_advisory(g, rng):
    opcos = [n for n in _nodes(g, "LegalEntity") if g.nodes[n]["kind"] == "opco"]
    for e in opcos:
        if rng.random() < 0.4:
            model.add_edge(g, e, rng.choice(opcos), "supplier_of", weight=round(rng.random(), 2))
        if rng.random() < 0.2:
            model.add_edge(g, e, rng.choice(opcos), "competitor_of")
        if rng.random() < 0.15:
            model.add_edge(g, e, rng.choice(opcos), "partner_with")
    rms = _nodes(g, "RelationshipManager")
    for p in _nodes(g, "NaturalPerson"):
        model.add_edge(g, rng.choice(rms), p, "advises")
        if rng.random() < 0.1:
            model.add_edge(g, rng.choice(_nodes(g, "NaturalPerson")), p, "referred_by")


def _prospects(g, rng, fake=None):
    from faker import Faker
    fk = fake or Faker()
    rms = _nodes(g, "RelationshipManager")
    opcos = [n for n in _nodes(g, "LegalEntity") if g.nodes[n]["kind"] == "opco"]
    for i in range(1, config.WG["prospects"] + 1):
        pr = f"PR{i}"
        model.add_node(g, pr, "Prospect", name=fk.name(),
                       source_segment=rng.choice(["consumer", "smb", "commercial"]),
                       score=round(rng.random(), 2), stage=rng.choice(["new", "qualified", "engaged"]))
        model.add_edge(g, rng.choice(rms), pr, "prospecting_target")
        if opcos and rng.random() < 0.5:
            model.add_edge(g, pr, rng.choice(opcos), "supplier_of", weight=round(rng.random(), 2))


def add_all(g, seed: int = config.SEED):
    rng = random.Random(seed + 1)
    _family(g, rng)
    _ownership_chains(g, rng)
    _trusts(g, rng)
    _banking(g, rng)
    _inter_client_and_advisory(g, rng)
    _prospects(g, rng)
    return g
