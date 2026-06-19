"""Eval metrics: SQL execution accuracy (result-set match) and retrieval recall@k / MRR."""
from __future__ import annotations

from typing import Sequence


def _norm_row(row: Sequence) -> tuple:
    out = []
    for v in row:
        if isinstance(v, float):
            out.append(round(v, 2))
        else:
            out.append(v)
    return tuple(out)


def _multiset(rows: Sequence[Sequence]) -> list[tuple]:
    return sorted((_norm_row(r) for r in rows), key=repr)


def exec_match(gold_rows: Sequence[Sequence], pred_rows: Sequence[Sequence]) -> bool:
    """Order-insensitive exact match of the two result sets (Spider-style)."""
    return _multiset(gold_rows) == _multiset(pred_rows)


def value_recall(gold_rows: Sequence[Sequence], pred_rows: Sequence[Sequence]) -> float:
    """Lenient: fraction of gold first-column values present anywhere in pred (tolerates
    extra columns the model selected). 1.0 if gold is empty and pred is empty."""
    gold_keys = {_norm_row([r[0]])[0] for r in gold_rows}
    if not gold_keys:
        return 1.0 if len(pred_rows) == 0 else 0.0
    pred_vals = {_norm_row([v])[0] for r in pred_rows for v in r}
    return len(gold_keys & pred_vals) / len(gold_keys)


def recall_at_k(gold_ids: Sequence[str], retrieved: Sequence[str], k: int) -> float:
    return 1.0 if set(gold_ids) & set(retrieved[:k]) else 0.0


def mrr(gold_ids: Sequence[str], retrieved: Sequence[str]) -> float:
    gold = set(gold_ids)
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in gold:
            return 1.0 / rank
    return 0.0


def mean(xs: Sequence[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0
