"""Run both engines in two modes over every question, score each, emit flat records (spec §12.2):
  - mode='llm'    : the injected LLM authors the query, sampled `samples` times.
  - mode='oracle' : a hand-written idiomatic query (capability ceiling), run via a fixed-query stub.
Both modes go through the SAME solver execute/guardrail/timeout path and the SAME scorer."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .. import config
from . import oracles, score
from .questions import Question
from .solvers import CypherSolver, SqlSolver


class _FixedLLM:
    """Returns a fixed query (used to run an oracle query through the normal solver path)."""
    name = "oracle"

    def __init__(self, query: str):
        self.query = query

    def complete(self, prompt, system=None, temperature=0.0):
        return self.query


def _outcome(res) -> str:
    if getattr(res, "timed_out", False):
        return "timeout"
    if not res.valid:
        return "invalid"
    return "ok"


def _record(q: Question, res, mode: str, sample: int, id_map: dict) -> dict:
    correct = score.is_correct(q, res.rows, id_map) if res.valid else False
    return {"mode": mode, "engine": res.engine, "sample": sample, "question_id": q.id,
            "category": q.category, "hop_depth": q.hop_depth, "valid": res.valid,
            "correct": correct, "outcome": _outcome(res), "attempts": res.attempts,
            "latency_s": res.latency_s, "query": res.query, "error": res.error}


def run(questions: list[Question], *, sql_llm, cypher_llm,
        db_path=config.WEALTH_DB, kuzu_path=config.WEALTH_KUZU,
        samples: int = 3, workers: int = 4, id_map: dict | None = None) -> list[dict]:
    id_map = id_map if id_map is not None else score.build_id_map(db_path)
    sql_solver = SqlSolver(sql_llm, db_path=db_path)
    cypher_solver = CypherSolver(cypher_llm, db_path=kuzu_path)

    tasks: list[tuple] = []
    for s in range(samples):
        for q in questions:
            tasks.append(("llm", sql_solver, q, s))
            tasks.append(("llm", cypher_solver, q, s))
    for q in questions:
        tasks.append(("oracle", "sql", q, 0))
        tasks.append(("oracle", "cypher", q, 0))

    def _run(task):
        mode, who, q, s = task
        if mode == "llm":
            return _record(q, who.solve(q), "llm", s, id_map)
        if who == "sql":
            r = SqlSolver(_FixedLLM(oracles.sql_oracle(q)), db_path=db_path).solve(q)
        else:
            r = CypherSolver(_FixedLLM(oracles.cypher_oracle(q)), db_path=kuzu_path).solve(q)
        return _record(q, r, "oracle", 0, id_map)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_run, tasks))
