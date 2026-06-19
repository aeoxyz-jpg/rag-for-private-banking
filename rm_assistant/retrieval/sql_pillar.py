"""Pillar B — text-to-SQL (spec §4.1). NL -> SQL over the unified warehouse, grounded
in the ontology schema/glossary/metrics, with read-only guardrails and self-correction.

Best for Q1/Q2/Q6 (exact filters, aggregations, joins) — the regime where vector RAG
silently returns wrong numbers.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from .. import config, db, ontology
from ..models.ollama import OllamaLLM

_SYS = (
    "You are a careful analytics engineer for a private bank. Translate the user's question "
    "into exactly ONE read-only SQLite SELECT query over the given schema. Use the governed "
    "metric formulas verbatim where relevant. Prefer explicit JOINs. Always add a LIMIT unless "
    "the query is a single aggregate. Output ONLY the SQL — no prose, no markdown fences."
)

# Few-shot exemplars grounded in this schema (anchor metric usage + the as-of date).
_FEWSHOT = [
    ("Which of my clients have AUM over 1 million and no contact in the last 90 days?",
     """WITH aum AS (
  SELECT a.client_id, SUM(a.balance+COALESCE(h.mv,0)) AS aum
  FROM accounts a LEFT JOIN (SELECT account_id, SUM(market_value) mv FROM holdings GROUP BY account_id) h
    ON h.account_id=a.account_id GROUP BY a.client_id),
contact AS (
  SELECT c.client_id, CAST(julianday('1998-12-31')-julianday(MAX(i.ts)) AS INT) AS days
  FROM clients c LEFT JOIN interactions i ON i.client_id=c.client_id GROUP BY c.client_id)
SELECT cl.client_id, cl.name, aum.aum, contact.days
FROM clients cl JOIN aum ON aum.client_id=cl.client_id
LEFT JOIN contact ON contact.client_id=cl.client_id
WHERE aum.aum > 1000000 AND (contact.days IS NULL OR contact.days > 90)
ORDER BY aum.aum DESC LIMIT 50;"""),
    ("What's the current balance and date of the last transaction for account 1787?",
     """SELECT a.account_id, a.balance, MAX(t.ts) AS last_transaction
FROM accounts a LEFT JOIN transactions t ON t.account_id=a.account_id
WHERE a.account_id=1787 GROUP BY a.account_id;"""),
    ("How many clients are in each wealth segment?",
     "SELECT segment, COUNT(*) AS clients FROM clients GROUP BY segment ORDER BY clients DESC;"),
]

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex)\b",
    re.IGNORECASE)
_ROW_CAP = 200


@dataclass
class SQLResult:
    question: str
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    answer: str = ""
    attempts: int = 0
    error: str | None = None


def _clean(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1] if "```" in raw[3:] else raw.strip("`")
        raw = raw[3:].lstrip() if raw.lower().startswith("sql") else raw
    return raw.strip().rstrip(";").strip()


def validate(sql: str) -> str | None:
    low = sql.lower().lstrip("(")
    if not (low.startswith("select") or low.startswith("with")):
        return "query must start with SELECT or WITH"
    if ";" in sql:
        return "only a single statement is allowed"
    if _FORBIDDEN.search(sql):
        return "only read-only SELECT queries are allowed"
    return None


def _gen_prompt(question: str, schema: str, metrics: str, prev_sql: str = "",
                prev_err: str = "") -> str:
    shots = "\n\n".join(f"Q: {q}\nSQL:\n{s}" for q, s in _FEWSHOT)
    parts = [
        "SCHEMA:", schema, "", metrics, "", "EXAMPLES:", shots, "",
        f"Q: {question}", "SQL:",
    ]
    if prev_err:
        parts.insert(0, f"Your previous SQL failed with: {prev_err}\nPrevious SQL:\n{prev_sql}\n"
                        f"Fix it and return corrected SQL only.\n")
    return "\n".join(parts)


def answer(question: str, max_retries: int = 2, model: str = config.REASON_MODEL) -> SQLResult:
    llm = OllamaLLM(model)
    conn = db.connect(readonly=True)
    schema = ontology.schema_prompt(conn)
    metrics = ontology.metrics_prompt()
    res = SQLResult(question=question)
    prev_sql = prev_err = ""

    for attempt in range(max_retries + 1):
        res.attempts = attempt + 1
        sql = _clean(llm.complete(_gen_prompt(question, schema, metrics, prev_sql, prev_err),
                                  system=_SYS, temperature=0.0))
        res.sql = sql
        err = validate(sql)
        if err:
            prev_sql, prev_err = sql, err
            continue
        try:
            cur = conn.execute(sql)
            res.columns = [d[0] for d in cur.description]
            res.rows = cur.fetchmany(_ROW_CAP)
            res.error = None
            break
        except sqlite3.Error as e:
            prev_sql, prev_err = sql, str(e)
            res.error = str(e)
    conn.close()

    if res.error is None:
        res.answer = _summarize(llm, question, res)
    return res


def _summarize(llm: OllamaLLM, question: str, res: SQLResult) -> str:
    preview = [dict(zip(res.columns, r)) for r in res.rows[:30]]
    prompt = (
        f"Question: {question}\n\nSQL result columns: {res.columns}\n"
        f"Rows (up to 30 of {len(res.rows)}): {preview}\n\n"
        "Answer the question concisely for a relationship manager, citing the concrete "
        "numbers. If there are no rows, say so plainly."
    )
    return llm.complete(prompt, system="You summarize query results for a private-banking RM.",
                        temperature=0.2)
