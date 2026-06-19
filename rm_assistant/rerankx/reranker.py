"""LLM-as-reranker served by local Ollama (Phase-3d). Scores a (query, doc) pair as a pointwise
relevance judge — a 1-token completion read as P(yes) from the yes/no token logprobs — then reorders
candidates by that score. No torch. (Dedicated Qwen3-Reranker GGUFs are broken/embedding-only on
Ollama 0.30.8, see spec §3; a general instruct model backs the same scoring contract.)"""
from __future__ import annotations

import math

import httpx

from .. import config

_SYSTEM = "You judge whether a document is relevant to a question. Answer with only 'yes' or 'no'."


def _user(query: str, doc: str) -> str:
    return (f"Question: {query}\nDocument: {doc}\n\n"
            "Is this document relevant to the question? Answer yes or no:")


def score_from_logprobs(top_logprobs: list[dict]) -> float:
    """P(yes) = softmax over the yes/no token logprobs among the first token's candidates. Missing
    'no' -> 1.0; missing 'yes' (or neither) -> 0.0."""
    yes = no = None
    for e in top_logprobs:
        t = e["token"].strip().lower()
        if t == "yes" and yes is None:
            yes = e["logprob"]
        elif t == "no" and no is None:
            no = e["logprob"]
    if yes is None:
        return 0.0
    if no is None:
        return 1.0
    ey, en = math.exp(yes), math.exp(no)
    return ey / (ey + en)


class Reranker:
    def __init__(self, model: str = config.RERANK_MODEL, host: str = config.OLLAMA_HOST):
        self.model = model
        self._host = host.rstrip("/")

    def score(self, query: str, doc: str) -> float:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": _user(query, doc)}],
            "max_tokens": 1, "temperature": 0, "logprobs": True, "top_logprobs": 20,
        }
        r = httpx.post(f"{self._host}/v1/chat/completions", json=payload, timeout=120)
        r.raise_for_status()
        content = r.json()["choices"][0]["logprobs"]["content"]
        return score_from_logprobs(content[0]["top_logprobs"] if content else [])

    def rerank(self, query: str, candidates: list[tuple[str, str]], score_fn=None) -> list[str]:
        sf = score_fn or self.score
        scored = [(doc_id, sf(query, text)) for doc_id, text in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [doc_id for doc_id, _ in scored]


class CrossEncoderReranker:
    """Trained cross-encoder (default bge-reranker-v2-m3) via FlagEmbedding — the textbook reranker.
    Same rerank(query, candidates) -> ordered doc_ids contract as the LLM Reranker. Requires the
    'rerank' extra (torch + FlagEmbedding); imported lazily so the core package stays torch-free."""

    def __init__(self, model: str = None):
        from FlagEmbedding import FlagReranker  # lazy: only when the extra is installed
        from .. import config
        self._model = FlagReranker(model or config.RERANK_CE_MODEL, use_fp16=True)

    def rerank(self, query: str, candidates: list[tuple[str, str]], score_fn=None) -> list[str]:
        scores = self._model.compute_score([[query, text] for _, text in candidates], normalize=True)
        if not isinstance(scores, list):
            scores = [scores]
        ranked = sorted(zip((d for d, _ in candidates), scores), key=lambda x: x[1], reverse=True)
        return [doc_id for doc_id, _ in ranked]
