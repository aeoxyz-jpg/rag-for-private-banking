"""Run the routing gold through router.classify(), recording expected vs predicted route. The
classify callable is injected (default: the real LLM classifier) so the aggregation is testable
network-free."""
from __future__ import annotations

import json
from pathlib import Path

from .. import config


def _default_classify(model: str):
    from ..retrieval import router
    return lambda q: router.classify(q, model)["route"]


def load_gold(path: Path = None) -> list[dict]:
    return json.loads(Path(path or config.ROUTING_GOLD).read_text())


def run(gold: list[dict], *, classify_fn=None, model: str = None) -> list[dict]:
    if classify_fn is None:
        classify_fn = _default_classify(model or config.REASON_MODEL)
    return [{"id": g["id"], "question": g["question"], "expected_route": g["expected_route"],
             "predicted_route": classify_fn(g["question"])} for g in gold]
