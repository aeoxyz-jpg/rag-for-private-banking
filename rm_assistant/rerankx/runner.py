"""Run the hard set through pillar A's RRF pool and the reranker, recording the gold doc's rank under
each arm. Pool-fetch / rerank / doc-text callables are injected (default: the real implementations)."""
from __future__ import annotations

import time

from .. import config, db
from . import reranker as _rk
from .hardset import RerankQ


def _default_pool(question: str):
    from ..retrieval import vector_pillar
    return vector_pillar.fused_candidates(question, pool=config.RERANK_POOL)


def _default_doc_text(doc_id: str) -> str:
    conn = db.connect(readonly=True)
    try:
        row = conn.execute("SELECT text FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


def _rank(ordered_ids: list[str], gold: str):
    return ordered_ids.index(gold) + 1 if gold in ordered_ids else None


def run(questions: list[RerankQ], *, pool_fn=_default_pool, rerank_fn=None,
        doc_text=_default_doc_text, pool: int = config.RERANK_POOL) -> list[dict]:
    if rerank_fn is None:
        rk = _rk.Reranker()
        rerank_fn = lambda question, cands: rk.rerank(question, cands)
    recs = []
    for q in questions:
        t0 = time.perf_counter()
        pool_ids = pool_fn(q.question)[:pool]
        rrf_rank = _rank(pool_ids, q.gold_doc_id)
        cands = [(d, doc_text(d)) for d in pool_ids]
        t1 = time.perf_counter()
        reranked = rerank_fn(q.question, cands)
        rerank_latency = time.perf_counter() - t1
        recs.append({"question_id": q.id, "gold_doc_id": q.gold_doc_id,
                     "in_pool": rrf_rank is not None, "pool_size": len(pool_ids),
                     "rrf_rank": rrf_rank, "rerank_rank": _rank(reranked, q.gold_doc_id),
                     "rerank_latency_s": round(rerank_latency, 2),
                     "latency_s": round(time.perf_counter() - t0, 2)})
    return recs
