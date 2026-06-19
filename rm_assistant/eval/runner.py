"""Eval runner: execute the gold set through both pillars, score, and emit a scoreboard
(spec §5). Pillar B -> SQL execution accuracy + answer judge; pillar A -> recall@k/MRR +
answer judge. Every query is timed.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import db
from ..retrieval import sql_pillar, vector_pillar
from . import judge, metrics

_GOLD = Path(__file__).with_name("gold")
RECALL_POOL = 10


def _gold_rows(reference_sql: str) -> list[tuple]:
    conn = db.connect(readonly=True)
    try:
        return [tuple(r) for r in conn.execute(reference_sql).fetchall()]
    finally:
        conn.close()


def _eval_sql(item: dict, do_judge: bool) -> dict:
    t0 = time.perf_counter()
    res = sql_pillar.answer(item["question"])
    latency = time.perf_counter() - t0
    gold = _gold_rows(item["reference_sql"])
    pred = [tuple(r) for r in res.rows]
    valid = res.error is None
    rec = {
        "id": item["id"], "archetype": item["archetype"], "pillar": "B",
        "question": item["question"], "valid_sql": valid, "attempts": res.attempts,
        "exec_match": valid and metrics.exec_match(gold, pred),
        "value_recall": metrics.value_recall(gold, pred) if valid else 0.0,
        "gold_n": len(gold), "pred_n": len(pred), "latency_s": round(latency, 2),
        "sql": res.sql,
    }
    if do_judge and valid:
        ref = f"reference rows: {gold[:20]}"
        j = judge.judge(item["question"], res.answer, ref, evidence=f"query rows: {pred[:20]}")
        rec["faithfulness"], rec["correctness"] = j["faithfulness"], j["correctness"]
    return rec


def _eval_vector(item: dict, do_judge: bool) -> dict:
    kind = item.get("kind")
    t0 = time.perf_counter()
    sources = vector_pillar.search(item["question"], k=RECALL_POOL, kind=kind)
    retrieved = [s.doc_id for s in sources]
    res = vector_pillar.answer(item["question"], kind=kind)
    latency = time.perf_counter() - t0
    gold_ids = item["gold_doc_ids"]
    rec = {
        "id": item["id"], "archetype": item["archetype"], "pillar": "A",
        "question": item["question"],
        "recall@5": metrics.recall_at_k(gold_ids, retrieved, 5),
        "recall@10": metrics.recall_at_k(gold_ids, retrieved, 10),
        "mrr": round(metrics.mrr(gold_ids, retrieved), 3),
        "gold": gold_ids, "retrieved": retrieved[:5], "latency_s": round(latency, 2),
    }
    if do_judge:
        src = next((s.text for s in res.sources if s.doc_id in gold_ids), "")
        ev = "\n".join(s.text for s in res.sources)
        j = judge.judge(item["question"], res.answer, src or ev, evidence=ev)
        rec["faithfulness"], rec["correctness"] = j["faithfulness"], j["correctness"]
    return rec


def run(limit: int | None = None, workers: int = 8, do_judge: bool = True) -> list[dict]:
    sql_gold = json.loads((_GOLD / "sql.json").read_text())
    sql_gold += json.loads((_GOLD / "q5.json").read_text())  # Q5 multi-hop, also via pillar B
    vec_gold = json.loads((_GOLD / "vector.json").read_text())
    if limit:
        sql_gold, vec_gold = sql_gold[:limit], vec_gold[:limit]
    tasks = [("sql", g) for g in sql_gold] + [("vec", g) for g in vec_gold]

    def _run(t):
        kind, item = t
        fn = _eval_sql if kind == "sql" else _eval_vector
        try:
            return fn(item, do_judge)
        except Exception as e:  # noqa: BLE001
            return {"id": item["id"], "pillar": "B" if kind == "sql" else "A",
                    "archetype": item["archetype"], "error": str(e)}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_run, tasks))
