"""Seeded greenfield builder for the canonical wealth graph (entities in this module;
relationships/deep structures added in builder_relations via build_canonical)."""
from __future__ import annotations

import random

import networkx as nx
from faker import Faker

from .. import config
from . import model

_JURISDICTIONS = ["US", "UK", "CH", "SG", "JE", "KY", "LU"]
_SECTORS = ["Technology", "Manufacturing", "Real Estate", "Healthcare",
            "Energy", "Retail", "Logistics", "Financial Services"]
_PRODUCTS = ["Term Deposit", "Discretionary Mandate", "Lombard Loan",
             "Structured Note", "Mortgage", "FX Forward"]


def _entities(g, rng, fake):
    for i in range(1, config.WG["entities"] + 1):
        kind = rng.choices(model.ENTITY_KINDS, weights=[5, 3, 2, 1])[0]
        model.add_node(g, f"E{i}", "LegalEntity", name=fake.company(), kind=kind,
                       sector=rng.choice(_SECTORS), jurisdiction=rng.choice(_JURISDICTIONS))


def _trusts(g, rng, fake):
    kinds = ["discretionary", "fixed", "purpose"]
    for i in range(1, config.WG["trusts"] + 1):
        model.add_node(g, f"T{i}", "Trust", name=f"{fake.last_name()} Family Trust",
                       kind=rng.choice(kinds), jurisdiction=rng.choice(_JURISDICTIONS))


def _rms(g, fake):
    for i in range(1, config.WG["rms"] + 1):
        model.add_node(g, f"RM{i}", "RelationshipManager", name=fake.name(),
                       book_segment="private_wealth")


def _households_and_persons(g, rng, fake):
    """Each household has 2-3 generations; persons get banking segments."""
    pid = 0
    for h in range(1, config.WG["households"] + 1):
        hid = f"H{h}"
        model.add_node(g, hid, "Household", name=f"{fake.last_name()} Household")
        n_gens = rng.choice([2, 2, 3])
        members = []
        for gen in range(1, n_gens + 1):
            for _ in range(rng.randint(1, 2)):
                pid += 1
                segs = ["private_wealth"]
                segs += rng.sample(["consumer", "smb", "commercial"],
                                   k=rng.choice([0, 0, 1, 2]))
                model.add_node(g, f"P{pid}", "NaturalPerson", name=fake.name(),
                               generation=gen, household=hid,
                               segments=sorted(set(segs)),
                               pep_flag=rng.random() < 0.05)
                members.append((f"P{pid}", gen))
        g.nodes[hid]["members"] = [m for m, _ in members]


def _accounts_and_products(g, rng, fake):
    for i in range(1, 7):
        model.add_node(g, f"PROD{i}", "Product", name=_PRODUCTS[i - 1], category="banking")
    owners = [n for n, d in g.nodes(data=True)
              if d["label"] in ("NaturalPerson", "LegalEntity")]
    for i in range(1, config.WG["accounts"] + 1):
        owner = rng.choice(owners)
        model.add_node(g, f"A{i}", "Account", owner=owner, type="custody",
                       currency="USD", balance=round(rng.lognormvariate(12, 1.3), 2),
                       opened_at=f"{rng.randint(1995, 2024)}-01-01")


def build_entities(seed: int = config.SEED) -> nx.MultiDiGraph:
    rng = random.Random(seed)
    fake = Faker()
    Faker.seed(seed)
    g = model.new_graph()
    _rms(g, fake)
    _households_and_persons(g, rng, fake)
    _entities(g, rng, fake)
    _trusts(g, rng, fake)
    _accounts_and_products(g, rng, fake)
    return g


def build_canonical(seed: int = config.SEED) -> nx.MultiDiGraph:
    """Full canonical graph: entities + relationships + deliberate deep structures."""
    from . import relations
    g = build_entities(seed)
    relations.add_all(g, seed)
    return g
