"""The hard, distractor-rich rerank gold: each question is pinned to one note of a multi-note client,
so the client's sibling notes are natural near-neighbour distractors. Generated once by
scripts/gen_rerank_hardset.py and committed to rm_assistant/eval/gold/rerank_hard.json."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

GOLD_PATH = Path("rm_assistant/eval/gold/rerank_hard.json")


@dataclass(frozen=True)
class RerankQ:
    id: str
    question: str
    gold_doc_id: str
    client_id: int
    n_sibling_notes: int


def load(path: Path = GOLD_PATH) -> list[RerankQ]:
    raw = json.loads(Path(path).read_text())
    return [RerankQ(d["id"], d["question"], d["gold_doc_id"], d["client_id"], d["n_sibling_notes"])
            for d in raw]


def filter_by_density(pools: dict, min_notes: int) -> dict:
    """Keep only clients with >= min_notes notes; raising min_notes raises distractor density
    (more near-neighbour sibling notes per gold)."""
    return {c: notes for c, notes in pools.items() if len(notes) >= min_notes}
