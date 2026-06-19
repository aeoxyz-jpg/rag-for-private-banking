"""Pillar F — router / agent (spec §4.1, §4.3). The top-level entry point: classify each
query to the right pillar (B sql · E metric · A vector · A-kb · D c360), and for hybrid Q7
queries decompose into a vector-filter -> SQL-filter -> synthesize pipeline.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .. import config, db
from ..models.ollama import OllamaLLM
from . import c360, semantic, sql_pillar, vector_pillar

ROUTES = ("sql", "metric", "vector", "kb", "c360", "hybrid")
_JSON = re.compile(r"\{.*\}", re.DOTALL)

_CLASSIFY_SYS = "You route private-banking questions to a retrieval strategy. Output ONLY JSON."
_CLASSIFY = """Routes:
- sql: precise filter / lookup / aggregation over structured data (balances, accounts, loans,
  counts) — INCLUDING aggregates that filter or group by a client attribute like segment,
  district, or risk profile (e.g. "total AUM of UHNW clients" needs a join -> sql). [Q1/Q2]
- metric: a governed KPI reported per client or ranked/thresholded on the KPI itself — AUM,
  churn risk, days since contact, share of wallet, net new money (e.g. "churn risk of client X",
  "clients with AUM over 1M", "top clients by AUM"). NOT for aggregates over a segment. [Q6]
- vector: fuzzy recall over what clients SAID in notes/calls (concerns, preferences, mentions). [Q3]
- kb: product/policy/compliance knowledge (eligibility, fees, KYC rules). [Q8]
- c360: "summarize / tell me everything about / pre-meeting brief for" a SPECIFIC client. [Q4]
- hybrid: needs BOTH an unstructured filter (what clients said) AND a structured filter
  (a warehouse condition), e.g. "clients who mentioned liquidity who also have a maturing loan". [Q7]

Question: {q}

Return ONLY: {{"route":"<one route>","client_id":<int or null>}}"""

_DECOMPOSE_SYS = "You decompose a hybrid query. Output ONLY JSON."
_DECOMPOSE = """Split this question into two filters:
- semantic_filter: what the client SAID/expressed (for searching notes), as a short phrase.
- structured_filter: the structured condition over the warehouse, as a short phrase.

Question: {q}

Return ONLY: {{"semantic_filter":"...","structured_filter":"..."}}"""


@dataclass
class RouterResult:
    question: str
    route: str = ""
    answer: str = ""
    detail: dict = field(default_factory=dict)


def classify(question: str, model: str = config.REASON_MODEL) -> dict:
    raw = OllamaLLM(model).complete(_CLASSIFY.format(q=question), system=_CLASSIFY_SYS,
                                    temperature=0.0)
    m = _JSON.search(raw)
    d = json.loads(m.group(0)) if m else {}
    route = d.get("route")
    return {"route": route if route in ROUTES else "sql", "client_id": d.get("client_id")}


def _hybrid(question: str, model: str) -> RouterResult:
    raw = OllamaLLM(model).complete(_DECOMPOSE.format(q=question), system=_DECOMPOSE_SYS,
                                    temperature=0.0)
    plan = json.loads(_JSON.search(raw).group(0))
    sem, struct = plan["semantic_filter"], plan["structured_filter"]

    # step 1: vector-filter over client notes -> candidate client_ids
    sources = vector_pillar.search(sem, k=25)
    cands = sorted({s.client_id for s in sources if s.client_id is not None})

    # step 2: SQL-filter the structured condition, restricted to the candidates
    if cands:
        id_list = ",".join(str(c) for c in cands)
        sql_q = f"{struct}. Only consider clients whose client_id is in ({id_list})."
        sql_res = sql_pillar.answer(sql_q)
    else:
        sql_res = sql_pillar.SQLResult(question=struct, answer="(no candidates from note search)")

    # step 3: synthesize
    answer = OllamaLLM(model).complete(
        f"Question: {question}\n\nStep 1 (clients who {sem}): {cands}\n"
        f"Step 2 SQL: {sql_res.sql}\nStep 2 result rows: {[tuple(r) for r in sql_res.rows][:30]}\n"
        f"Step 2 summary: {sql_res.answer}\n\nGive the final answer to the original question.",
        system="You synthesize a two-step (notes + warehouse) answer for an RM.", temperature=0.2)
    return RouterResult(question=question, route="hybrid", answer=answer,
                        detail={"semantic_filter": sem, "structured_filter": struct,
                                "candidates": cands, "sql": sql_res.sql})


def _extract_client_id(question: str, given) -> int | None:
    if isinstance(given, int):
        return given
    m = re.search(r"\bclient\s*#?\s*(\d+)", question, re.IGNORECASE)
    return int(m.group(1)) if m else None


def ask(question: str, model: str = config.REASON_MODEL) -> RouterResult:
    cls = classify(question, model)
    route = cls["route"]

    if route == "hybrid":
        return _hybrid(question, model)
    if route == "metric":
        r = semantic.answer(question, model)
        if r.error:  # fall back to free text-to-SQL if no governed metric fit
            route = "sql"
        else:
            return RouterResult(question, "metric", r.answer, {"metric": r.metric})
    if route == "c360":
        cid = _extract_client_id(question, cls.get("client_id"))
        if cid is None:
            return RouterResult(question, "c360", "Need a specific client id for a 360 brief.", {})
        b = c360.build(cid, model)
        return RouterResult(question, "c360", b.narrative, {"client_id": cid})
    if route in ("vector", "kb"):
        r = vector_pillar.answer(question, kind="kb" if route == "kb" else None)
        return RouterResult(question, route, r.answer, {"sources": [s.doc_id for s in r.sources]})

    r = sql_pillar.answer(question)  # sql (default / fallback)
    return RouterResult(question, "sql", r.answer, {"sql": r.sql, "rows": len(r.rows)})
