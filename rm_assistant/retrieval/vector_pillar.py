"""Pillar A — hybrid vector search (spec §4.1). Dense (Chroma/bge-m3) fused with lexical
BM25 (SQLite FTS5) via Reciprocal Rank Fusion, then a grounded LLM answer with citations.

Best for Q3 (fuzzy recall over notes) and Q8 (policy/product Q&A). A cross-encoder reranker
is a documented future extension (kept out for now to avoid a heavy torch dependency).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import config, db
from ..models.factory import get_embedder
from ..models.ollama import OllamaLLM
from ..vectorstore.chroma_store import ChromaStore

_WORD = re.compile(r"[A-Za-z0-9]+")


@dataclass
class Source:
    doc_id: str
    client_id: int | None
    kind: str
    text: str


@dataclass
class VectorResult:
    question: str
    answer: str = ""
    sources: list[Source] = field(default_factory=list)


def build_fts() -> int:
    """(Re)build the FTS5 lexical index over documents.text. Returns indexed row count."""
    conn = db.connect()
    conn.execute("DROP TABLE IF EXISTS documents_fts")
    conn.execute(
        "CREATE VIRTUAL TABLE documents_fts USING fts5("
        "text, doc_id UNINDEXED, kind UNINDEXED, client_id UNINDEXED)")
    conn.execute(
        "INSERT INTO documents_fts(text, doc_id, kind, client_id) "
        "SELECT text, doc_id, kind, COALESCE(client_id, -1) FROM documents")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM documents_fts").fetchone()[0]
    conn.close()
    return n


def _match_query(question: str) -> str:
    """NL -> safe FTS5 OR-query (quoted tokens, so punctuation can't break syntax)."""
    toks = {t.lower() for t in _WORD.findall(question) if len(t) > 2}
    return " OR ".join(f'"{t}"' for t in toks) or '"the"'


def _bm25(conn, question: str, k: int, kind: str | None, client_id: int | None) -> list[str]:
    sql = ("SELECT doc_id FROM documents_fts WHERE documents_fts MATCH ?")
    params: list = [_match_query(question)]
    if kind:
        sql += " AND kind = ?"; params.append(kind)
    if client_id is not None:
        sql += " AND client_id = ?"; params.append(client_id)
    sql += " ORDER BY bm25(documents_fts) LIMIT ?"; params.append(k)
    return [r[0] for r in conn.execute(sql, params)]


def _dense(embedder, store, question: str, k: int, kind, client_id) -> list[str]:
    where = {}
    if kind:
        where["kind"] = kind
    if client_id is not None:
        where["client_id"] = client_id
    hits = store.query(embedder.embed([question])[0], k=k, where=where or None)
    return [h.id for h in hits]


def _rrf(rank_lists: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for lst in rank_lists:
        for rank, doc_id in enumerate(lst):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)


def fused_candidates(question: str, pool: int = 20, kind: str | None = None,
                     client_id: int | None = None) -> list[str]:
    """The RRF-ordered candidate pool (doc_ids) before truncation — the input a reranker reorders."""
    embedder = get_embedder()
    store = ChromaStore(collection="documents")
    conn = db.connect(readonly=True)
    try:
        dense = _dense(embedder, store, question, pool, kind, client_id)
        lexical = _bm25(conn, question, pool, kind, client_id)
        return _rrf([dense, lexical])
    finally:
        conn.close()


def search(question: str, k: int = 8, kind: str | None = None,
           client_id: int | None = None, pool: int = 20) -> list[Source]:
    fused = fused_candidates(question, pool=pool, kind=kind, client_id=client_id)[:k]
    conn = db.connect(readonly=True)
    out: list[Source] = []
    try:
        for doc_id in fused:
            row = conn.execute(
                "SELECT doc_id, client_id, kind, text FROM documents WHERE doc_id=?",
                (doc_id,)).fetchone()
            if row:
                out.append(Source(row["doc_id"], row["client_id"], row["kind"], row["text"]))
    finally:
        conn.close()
    return out


def answer(question: str, k: int = 6, kind: str | None = None,
           client_id: int | None = None, model: str = config.REASON_MODEL) -> VectorResult:
    sources = search(question, k=k, kind=kind, client_id=client_id)
    ctx = "\n\n".join(f"[{s.doc_id}] ({s.kind}, client {s.client_id})\n{s.text}" for s in sources)
    prompt = (
        f"Question: {question}\n\nRetrieved documents:\n{ctx}\n\n"
        "Answer the question using ONLY the retrieved documents. Cite the document ids you "
        "used in square brackets. If the documents don't contain the answer, say so."
    )
    ans = OllamaLLM(model).complete(
        prompt, system="You answer private-banking questions grounded strictly in retrieved text.",
        temperature=0.2)
    return VectorResult(question=question, answer=ans, sources=sources)
