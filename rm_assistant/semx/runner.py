"""Run B and E over every question x `samples` times, extract a comparable answer, score against
the canonical gold. Engine callables are injected (default: the real pillars) for testability.
B = sql_pillar.answer (free text-to-SQL); E = semantic.answer (governed metric)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from .. import config
from . import extract
from .questions import MetricQ


def _default_b(question):
    from ..retrieval import sql_pillar
    return sql_pillar.answer(question)


def _default_e(question):
    from ..retrieval import semantic
    return semantic.answer(question)


def _score(q: MetricQ, res) -> dict:
    if q.gold_kind == "probe":
        # E either cleanly abstains (no governed metric matched) or MIS-ROUTES: it silently picks a
        # nearby governed metric and answers an ungoverned question with the wrong metric. Capture the
        # chosen metric so mis-routes are visible (B has no governed metric, so chosen_metric is None).
        abstain = bool(res.error) and "governed metric" in str(res.error).lower()
        return {"valid": res.error is None, "abstain": abstain, "answer": None, "correct": None,
                "chosen_metric": getattr(res, "metric", None) or None}
    if res.error is not None:
        return {"valid": False, "abstain": False, "answer": None, "correct": False}
    ans = extract.extract(res.rows, q.gold_kind)
    correct = ans == q.gold
    answer_repr = sorted(ans) if isinstance(ans, frozenset) else ans
    return {"valid": True, "abstain": False, "answer": answer_repr, "correct": correct}


def run(questions: list[MetricQ], *, b_fn=_default_b, e_fn=_default_e,
        samples: int = config.SEMX_SAMPLES, workers: int = 4) -> list[dict]:
    tasks = []
    for s in range(samples):
        for q in questions:
            tasks.append(("B", b_fn, q, s))
            tasks.append(("E", e_fn, q, s))

    def _run(task):
        engine, fn, q, s = task
        t0 = time.perf_counter()
        try:
            res = fn(q.question)
            sc = _score(q, res)
        except Exception as e:  # noqa: BLE001 - an engine/LLM failure is a failed run, not a crash
            sc = {"valid": False, "abstain": False, "answer": None,
                  "correct": (None if q.gold_kind == "probe" else False), "error": str(e)}
        rec = {"engine": engine, "sample": s, "question_id": q.id, "metric": q.metric,
               "variant": q.variant, "gold_kind": q.gold_kind,
               "latency_s": round(time.perf_counter() - t0, 2)}
        rec.update(sc)
        return rec

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_run, tasks))
