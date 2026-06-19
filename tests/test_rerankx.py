"""Network-free checks for the rerankx (reranking) harness. DB/Ollama-dependent paths are exercised
by scripts/eval/run_rerank_eval.py, not here."""
import pytest


def test_score_from_logprobs():
    from rm_assistant.rerankx import reranker
    # both tokens present -> softmax over yes/no
    tl = [{"token": "yes", "logprob": 0.0}, {"token": "no", "logprob": -1.0}]
    s = reranker.score_from_logprobs(tl)
    assert 0.7 < s < 0.74                      # exp(0)/(exp(0)+exp(-1)) = 0.731
    # only "yes" present -> 1.0 ; only "no" -> 0.0 ; neither -> 0.0
    assert reranker.score_from_logprobs([{"token": "Yes", "logprob": -0.2}]) == 1.0
    assert reranker.score_from_logprobs([{"token": " no", "logprob": -0.2}]) == 0.0
    assert reranker.score_from_logprobs([{"token": "maybe", "logprob": -0.2}]) == 0.0


def test_rerank_orders_by_injected_score():
    from rm_assistant.rerankx import reranker
    rk = reranker.Reranker()
    cands = [("a", "text-a"), ("b", "text-b"), ("c", "text-c")]
    scores = {"text-a": 0.2, "text-b": 0.9, "text-c": 0.5}
    out = rk.rerank("q", cands, score_fn=lambda query, doc: scores[doc])
    assert out == ["b", "c", "a"]


def test_fused_candidates_returns_rrf_order(monkeypatch):
    from rm_assistant.retrieval import vector_pillar as vp

    class _Conn:
        def close(self):
            pass

    monkeypatch.setattr(vp, "get_embedder", lambda: object())
    monkeypatch.setattr(vp, "ChromaStore", lambda collection: object())
    monkeypatch.setattr(vp.db, "connect", lambda readonly=False: _Conn())
    monkeypatch.setattr(vp, "_dense", lambda *a, **k: ["d1", "d2", "d3"])
    monkeypatch.setattr(vp, "_bm25", lambda *a, **k: ["d3", "d4"])
    out = vp.fused_candidates("q", pool=10)
    assert out == vp._rrf([["d1", "d2", "d3"], ["d3", "d4"]])
    assert out[0] == "d3"   # appears in both lists -> highest RRF score


def test_hardset_load(tmp_path):
    import json
    from rm_assistant.rerankx import hardset
    p = tmp_path / "rerank_hard.json"
    p.write_text(json.dumps([
        {"id": "rr-1", "question": "What did client 7 say about estate planning?",
         "gold_doc_id": "doc-7a", "client_id": 7, "n_sibling_notes": 4},
    ]))
    qs = hardset.load(p)
    assert len(qs) == 1
    q = qs[0]
    assert q.id == "rr-1" and q.gold_doc_id == "doc-7a"
    assert q.client_id == 7 and q.n_sibling_notes == 4
    assert q.question


def test_runner_with_stubs():
    from rm_assistant.rerankx import runner, hardset
    q = hardset.RerankQ("rr-1", "q?", "gold", 7, 3)
    # RRF puts gold at rank 3; rerank lifts it to rank 1
    pool_fn = lambda question: ["x", "y", "gold", "z"]
    rerank_fn = lambda question, cands: ["gold", "x", "y", "z"]
    recs = runner.run([q], pool_fn=pool_fn, rerank_fn=rerank_fn, doc_text=lambda d: d, pool=4)
    assert len(recs) == 1
    r = recs[0]
    assert r["in_pool"] is True and r["rrf_rank"] == 3 and r["rerank_rank"] == 1
    assert r["question_id"] == "rr-1" and r["gold_doc_id"] == "gold"
    assert "rerank_latency_s" in r


def test_aggregate_and_verdict():
    from rm_assistant.rerankx import report
    # 4 questions, all gold in pool; rerank lifts every gold to rank 1, RRF had them at 3
    recs = [{"question_id": f"q{i}", "gold_doc_id": "g", "in_pool": True, "pool_size": 5,
             "rrf_rank": 3, "rerank_rank": 1, "rerank_latency_s": 0.5, "latency_s": 0.6}
            for i in range(4)]
    agg = report.aggregate(recs)
    assert agg["pool_recall"] == 1.0 and agg["actionable_n"] == 4
    assert agg["rrf"]["recall@1"] == 0.0 and agg["rerank"]["recall@1"] == 1.0
    assert agg["rerank"]["mrr"] == 1.0
    assert report.verdict(agg) == "justified"
    # rerank changes nothing -> not justified
    flat = [{"question_id": f"q{i}", "gold_doc_id": "g", "in_pool": True, "pool_size": 5,
             "rrf_rank": 1, "rerank_rank": 1, "rerank_latency_s": 0.5, "latency_s": 0.6}
            for i in range(4)]
    assert report.verdict(report.aggregate(flat)) == "not_justified"


def test_pool_recall_and_missing():
    from rm_assistant.rerankx import report
    recs = [{"question_id": "q0", "gold_doc_id": "g", "in_pool": False, "pool_size": 5,
             "rrf_rank": None, "rerank_rank": None, "rerank_latency_s": 0.5, "latency_s": 0.6},
            {"question_id": "q1", "gold_doc_id": "g", "in_pool": True, "pool_size": 5,
             "rrf_rank": 2, "rerank_rank": 1, "rerank_latency_s": 0.5, "latency_s": 0.6}]
    agg = report.aggregate(recs)
    assert agg["pool_recall"] == 0.5
    assert agg["rrf"]["mrr"] == round((0 + 0.5) / 2, 3)   # missing gold contributes 0


def test_rerankx_modules_import():
    from rm_assistant.rerankx import reranker, hardset, runner, report  # noqa: F401


def test_cross_encoder_orders_by_injected_score(monkeypatch):
    from rm_assistant.rerankx import reranker
    ce = reranker.CrossEncoderReranker.__new__(reranker.CrossEncoderReranker)  # skip model load
    ce._model = type("M", (), {"compute_score": lambda self, pairs, **k: [0.2, 0.9, 0.5]})()
    out = ce.rerank("q", [("a", "ta"), ("b", "tb"), ("c", "tc")])
    assert out == ["b", "c", "a"]


def test_min_siblings_filter():
    from rm_assistant.rerankx import hardset
    pools = {1: ["n"] * 3, 2: ["n"] * 6, 3: ["n"] * 2}  # client->notes
    kept = hardset.filter_by_density(pools, min_notes=4)
    assert set(kept) == {2}   # only client 2 has >=4 notes


def test_cross_encoder_scalar_score():
    # FlagReranker returns a bare float for a single pair; rerank must coerce to a list
    from rm_assistant.rerankx import reranker
    ce = reranker.CrossEncoderReranker.__new__(reranker.CrossEncoderReranker)
    ce._model = type("M", (), {"compute_score": lambda self, pairs, **k: 0.7})()
    assert ce.rerank("q", [("a", "ta")]) == ["a"]


def test_cross_encoder_empty_candidates():
    from rm_assistant.rerankx import reranker
    ce = reranker.CrossEncoderReranker.__new__(reranker.CrossEncoderReranker)
    ce._model = type("M", (), {"compute_score": lambda self, pairs, **k: []})()
    assert ce.rerank("q", []) == []
