"""Score a solver result against a question's gold. Sets: order-insensitive exact match (reusing
eval.metrics.exec_match). Paths: length + endpoints match. Projection-invariant: an optional
name->id map lets a query that returned names still score (spec §12.1 #4)."""
from __future__ import annotations

from collections import Counter

from .. import config, db
from ..eval import metrics
from .questions import Question


def build_id_map(db_path=config.WEALTH_DB) -> dict:
    """name -> node_id for UNIQUELY-named nodes, so a query returning names still scores."""
    conn = db.connect(db_path, readonly=True)
    try:
        rows = conn.execute("SELECT node_id, name FROM nodes").fetchall()
    finally:
        conn.close()
    counts = Counter(r[1] for r in rows if r[1])
    return {r[1]: r[0] for r in rows if r[1] and counts[r[1]] == 1}


def is_correct(q: Question, pred: list, id_map: dict | None = None) -> bool:
    pred = [str(x) for x in pred]
    if id_map:
        pred = [id_map.get(x, x) for x in pred]
    gold = [str(x) for x in q.gold]
    if q.gold_kind == "set":
        return metrics.exec_match([(g,) for g in gold], [(p,) for p in pred])
    return (len(pred) == len(gold) and bool(pred)
            and pred[0] == gold[0] and pred[-1] == gold[-1])


def exact_path(q: Question, pred: list) -> bool:
    return [str(x) for x in pred] == [str(x) for x in q.gold]
