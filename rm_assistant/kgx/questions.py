"""Template-derived NL question set from graph_truth.json (de-confounded: categories and gold
come from the data's ground truth, not from query-engine ability). Each question carries its
hop-depth for stratified scoring."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from .. import config


@dataclass
class Question:
    id: str
    category: str
    hop_depth: int
    question: str
    gold: list
    gold_kind: str
    params: dict = field(default_factory=dict)  # raw targets for oracle queries


def generate(truth_path: Path = config.WEALTH_TRUTH,
             n_per_category: int = config.KGX_N_PER_CATEGORY,
             seed: int = config.SEED) -> list[Question]:
    gt = json.loads(Path(truth_path).read_text())
    rng = random.Random(seed)
    out: list[Question] = []

    by_entity: dict[str, list[str]] = {}
    depth: dict[str, int] = {}
    for r in gt["ubo"]:
        by_entity.setdefault(r["entity_id"], []).append(r["person_id"])
        depth[r["entity_id"]] = max(depth.get(r["entity_id"], 1), len(r["path"]) - 1)
    for e in _sample(rng, sorted(by_entity), n_per_category):
        out.append(Question(f"ubo-{e}", "ubo", max(1, depth[e]),
                            f"Who are the ultimate beneficial owners of entity {e}?",
                            sorted(set(by_entity[e])), "set", {"entity": e}))

    for h in _sample(rng, sorted(gt["household_members"]), n_per_category):
        out.append(Question(f"hh-{h}", "household", 1,
                            f"Who are the members of household {h}?",
                            sorted(gt["household_members"][h]), "set", {"household": h}))

    parties = sorted(gt["k_hop"])
    for party in _sample(rng, parties, n_per_category):
        for k in (1, 2, 3):
            gold = gt["k_hop"][party].get(str(k), [])
            if gold:
                out.append(Question(f"khop-{party}-{k}", "k_hop", k,
                                    f"Which parties are exactly {k} relationship-hops from {party}?",
                                    sorted(gold), "set", {"party": party, "k": k}))

    for p in _sample(rng, sorted(gt["controls_entities"]), n_per_category):
        out.append(Question(f"ctrl-{p}", "controls", 2,
                            f"Which companies does person {p} ultimately control?",
                            sorted(gt["controls_entities"][p]), "set", {"person": p}))

    for i, sp in enumerate(_sample(rng, gt["shortest_paths"], n_per_category)):
        out.append(Question(f"path-{i}", "shortest_path", max(1, len(sp["path"]) - 1),
                            f"What is a shortest relationship path connecting {sp['a']} and {sp['b']}?",
                            list(sp["path"]), "path", {"a": sp["a"], "b": sp["b"]}))
    return out


def _sample(rng: random.Random, items: list, n: int) -> list:
    items = list(items)
    if len(items) <= n:
        return items
    return rng.sample(items, n)
