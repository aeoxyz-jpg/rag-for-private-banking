"""Pillar E — semantic layer (spec §4.1). Serves the governed metric definitions from
ontology.yaml so every KPI returns one consistent number, regardless of who asks. This is
what removes the "the LLM invented a different AUM formula" failure mode.

A metric question is answered by selecting a governed metric and executing its vetted SQL —
the LLM never writes the formula, only picks which metric and (optionally) the filter.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .. import config, db, ontology
from ..models.ollama import OllamaLLM


@dataclass
class MetricResult:
    question: str
    metric: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    answer: str = ""
    error: str | None = None


def available() -> dict[str, str]:
    o = ontology.load()
    return {name: m["label"] for name, m in o["metrics"].items()}


def run_metric(name: str, where: str | None = None, order_desc: bool = True,
               limit: int = 5000) -> tuple[list[str], list[tuple]]:
    """Execute a governed metric, optionally filtered/sorted. The metric SQL is the single
    source of truth — only the wrapper (filter/sort/limit) is dynamic."""
    base = ontology.metric_sql(name)
    sql = f"SELECT * FROM (\n{base}\n)"
    if where:
        sql += f" WHERE {where}"
    sql += f" ORDER BY 2 {'DESC' if order_desc else 'ASC'} LIMIT {limit}"
    conn = db.connect(readonly=True)
    try:
        cur = conn.execute(sql, ontology.metric_binds(sql))
        return [d[0] for d in cur.description], [tuple(r) for r in cur.fetchall()]
    finally:
        conn.close()


_JSON = re.compile(r"\{.*\}", re.DOTALL)


def select_metric(question: str, model: str = config.REASON_MODEL) -> dict:
    """NL -> {metric, where}. `where` is an optional SQL predicate over the metric's output
    columns (client_id and the metric value), or null."""
    o = ontology.load()
    catalog = "\n".join(f"- {n}: {m['label']} — {m['desc'].strip()} "
                        f"(columns: client_id, {n})" for n, m in o["metrics"].items())
    prompt = (
        f"Available governed metrics:\n{catalog}\n\n"
        f"As-of date: {o['as_of_date']}\n\nQuestion: {question}\n\n"
        "Pick the single best metric to answer it. Optionally give a SQL `where` predicate "
        "over the metric output columns (client_id, <metric>), e.g. \"aum > 1000000\". "
        'Return ONLY JSON: {"metric": "<name>", "where": "<predicate or null>"}')
    raw = OllamaLLM(model).complete(prompt, system="Output ONLY JSON.", temperature=0.0)
    m = _JSON.search(raw)
    return json.loads(m.group(0)) if m else {"metric": "", "where": None}


def answer(question: str, model: str = config.REASON_MODEL) -> MetricResult:
    res = MetricResult(question=question)
    sel = select_metric(question, model)
    res.metric = sel.get("metric", "")
    if res.metric not in available():
        res.error = f"no governed metric matched ({res.metric!r})"
        return res
    where = sel.get("where") or None
    try:
        res.columns, res.rows = run_metric(res.metric, where=where)
    except Exception as e:  # noqa: BLE001
        res.error = str(e)
        return res
    preview = [dict(zip(res.columns, r)) for r in res.rows[:30]]
    res.answer = OllamaLLM(model).complete(
        f"Question: {question}\nGoverned metric: {res.metric}\n"
        f"Rows (up to 30 of {len(res.rows)}): {preview}\n\n"
        "Answer concisely for a relationship manager, citing the numbers.",
        system="You summarize governed-metric results for a private-banking RM.",
        temperature=0.2)
    return res
