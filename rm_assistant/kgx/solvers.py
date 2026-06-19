"""Symmetric LLM-query solvers: SQL (recursive CTE over wealth.db) and Cypher (over KùzuDB).
Same shape — schema + few-shot + question, read-only guardrails, self-correction, uniform timeout
— so the comparison is fair (spec §12). The llm is injected (testable with a stub).

v2 fairness: the SQL schema does NOT expose the precomputed `ubo` table (both engines must
traverse); both few-shots are UNDIRECTED (matching the undirected gold); the SQL few-shot has a
cycle guard (the graph is cyclic); the Cypher few-shot uses verified KùzuDB dialect; both engines
get a uniform wall-clock budget and a `timed_out` outcome distinct from an error."""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass, field

from .. import config, db
from . import kuzu_loader
from .questions import Question

_ROW_CAP = 500
_SQL_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum)\b", re.I)
_CYPHER_FORBIDDEN = re.compile(r"\b(create|merge|set|delete|remove|drop|copy|alter)\b", re.I)

_SQL_SCHEMA = (
    "Relational schema (SQLite). nodes(node_id, label, name, props_json); "
    "relationships(src_id, dst_id, rel_type, attrs_json). Edges are stored DIRECTED but treat "
    "traversal as UNDIRECTED unless the question implies direction (join on id IN (src_id,dst_id)). "
    "rel_type values include owns_shares_in, controls, member_of_household, parent_of, spouse_of, "
    "beneficiary_of, trustee_of, settlor_of, director_of, advises, supplier_of. Ownership percent is "
    "in attrs_json: CAST(json_extract(attrs_json,'$.percent') AS REAL). Always return node_id (not "
    "name). Multi-hop needs WITH RECURSIVE with a CYCLE GUARD (track a path string, exclude visited "
    "ids) — the graph is cyclic and will loop forever otherwise.")
_SQL_FEWSHOT = (
    "Example (parties exactly 2 undirected hops from P1):\n"
    "WITH RECURSIVE bfs(id,d,path) AS (\n"
    "  SELECT 'P1',0,'|P1|'\n  UNION\n"
    "  SELECT CASE WHEN r.src_id=b.id THEN r.dst_id ELSE r.src_id END, b.d+1,\n"
    "         b.path||(CASE WHEN r.src_id=b.id THEN r.dst_id ELSE r.src_id END)||'|'\n"
    "  FROM relationships r JOIN bfs b ON b.id IN (r.src_id,r.dst_id)\n"
    "  WHERE b.d<2 AND b.path NOT LIKE '%|'||(CASE WHEN r.src_id=b.id THEN r.dst_id ELSE r.src_id END)||'|%')\n"
    "SELECT DISTINCT id FROM bfs WHERE d=2 AND id NOT IN (SELECT id FROM bfs WHERE d<2);")

_CYPHER_SCHEMA = (
    "Graph schema (KùzuDB 0.11). Node(id, label, name); Rel(FROM Node TO Node, type, percent). "
    "Edges are stored DIRECTED; for relationship-hop questions traverse UNDIRECTED with "
    "(a)-[:Rel*m..n]-(b) (no arrow). Rel type values include owns_shares_in, controls, "
    "member_of_household, parent_of, spouse_of, beneficiary_of, trustee_of, settlor_of, director_of, "
    "advises, supplier_of. For SHORTEST path use (a)-[:Rel* SHORTEST]-(b) — NOT shortestPath(). To "
    "predicate on edge properties along a variable-length path, NAME it: MATCH p=(a)-[:Rel*1..6]->(b) "
    "then use relationships(p) inside ALL(...). Always RETURN ids (e.g. n.id).")
_CYPHER_FEWSHOT = (
    "Example 1 (parties exactly 2 undirected hops from P1):\n"
    "MATCH (a:Node {id:'P1'})-[:Rel*1..1]-(near:Node)\n"
    "WITH COLLECT(near.id)+['P1'] AS seen\n"
    "MATCH (a:Node {id:'P1'})-[:Rel*2..2]-(b:Node) WHERE NOT b.id IN seen RETURN DISTINCT b.id;\n\n"
    "Example 2 (a shortest path between P1 and E1):\n"
    "MATCH p = (a:Node {id:'P1'})-[:Rel* SHORTEST]-(b:Node {id:'E1'}) RETURN properties(nodes(p),'id') LIMIT 1;\n\n"
    "Example 3 (entities P1 controls via majority ownership):\n"
    "MATCH p = (x:Node {id:'P1'})-[:Rel*1..6]->(e:Node) WHERE e.label='LegalEntity'\n"
    "AND ALL(rel IN relationships(p) WHERE rel.percent>0.5) RETURN DISTINCT e.id;")

_SYS = "You write ONE read-only query that answers the question. Output ONLY the query, no prose, no fences."


@dataclass
class SolveResult:
    engine: str
    question_id: str
    query: str = ""
    rows: list = field(default_factory=list)
    valid: bool = False
    attempts: int = 0
    latency_s: float = 0.0
    error: str | None = None
    timed_out: bool = False


def _clean(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[3:].lstrip() if raw[:3].lower() in ("sql", "cyp") else raw
    return raw.strip().rstrip(";").strip()


def _flatten(rows: list) -> list:
    """Normalize a result table to a flat list of ids. A single list-valued cell (a returned path)
    becomes that list; a single comma-joined string (a SQL path) is split; otherwise take the first
    column of every row."""
    if len(rows) == 1 and rows[0] and isinstance(rows[0][0], list):
        return [str(x) for x in rows[0][0]]
    out = [str(r[0]) for r in rows if r]
    return out[0].split(",") if len(out) == 1 and "," in out[0] else out


class SqlSolver:
    engine = "sql"

    def __init__(self, llm, db_path=config.WEALTH_DB, max_retries=config.KGX_MAX_RETRIES,
                 timeout_s: float = 30.0):
        self.llm, self.db_path, self.max_retries = llm, db_path, max_retries
        self.timeout_s = timeout_s

    def _validate(self, q: str) -> str | None:
        low = q.lower().lstrip("(")
        if not (low.startswith("select") or low.startswith("with")):
            return "must start with SELECT or WITH"
        if ";" in q:
            return "single statement only"
        if _SQL_FORBIDDEN.search(q):
            return "read-only queries only"
        return None

    def _prompt(self, question, prev_q="", prev_err=""):
        p = [_SQL_SCHEMA, "", _SQL_FEWSHOT, "", f"Question: {question}", "SQL:"]
        if prev_err:
            p.insert(0, f"Your previous query failed: {prev_err}\nPrevious: {prev_q}\nFix it.\n")
        return "\n".join(p)

    def solve(self, q: Question) -> SolveResult:
        res = SolveResult(self.engine, q.id)
        t0 = time.perf_counter()
        prev_q = prev_err = ""
        for attempt in range(self.max_retries + 1):
            res.attempts = attempt + 1
            try:
                res.query = _clean(self.llm.complete(self._prompt(q.question, prev_q, prev_err),
                                                     system=_SYS, temperature=0.0))
            except Exception as e:  # noqa: BLE001 - LLM/network failure: count as a failed attempt
                prev_q, prev_err = "", f"llm error: {e}"
                res.error, res.valid = prev_err, False
                continue
            err = self._validate(res.query)
            if err:
                prev_q, prev_err, res.error, res.valid = res.query, err, err, False
                continue
            conn = db.connect(self.db_path, readonly=True)
            deadline = time.perf_counter() + self.timeout_s
            conn.set_progress_handler(lambda: 1 if time.perf_counter() > deadline else 0, 1000)
            try:
                cur = conn.execute(res.query)
                res.rows = _flatten(cur.fetchmany(_ROW_CAP))
                res.valid, res.error, res.timed_out = True, None, False
                break
            except sqlite3.Error as e:
                res.timed_out = "interrupt" in str(e).lower()
                prev_q, prev_err, res.error, res.valid = res.query, str(e), str(e), False
            finally:
                conn.close()
        res.latency_s = round(time.perf_counter() - t0, 2)
        return res


class CypherSolver:
    engine = "cypher"

    def __init__(self, llm, db_path=config.WEALTH_KUZU, max_retries=config.KGX_MAX_RETRIES,
                 timeout_s: float = 30.0):
        self.llm, self.db_path, self.max_retries = llm, db_path, max_retries
        self.timeout_s = timeout_s

    def _validate(self, q: str) -> str | None:
        if "match" not in q.lower():
            return "must be a MATCH ... RETURN read query"
        if _CYPHER_FORBIDDEN.search(q):
            return "read-only queries only"
        return None

    def _prompt(self, question, prev_q="", prev_err=""):
        p = [_CYPHER_SCHEMA, "", _CYPHER_FEWSHOT, "", f"Question: {question}", "Cypher:"]
        if prev_err:
            p.insert(0, f"Your previous query failed: {prev_err}\nPrevious: {prev_q}\nFix it.\n")
        return "\n".join(p)

    def solve(self, q: Question) -> SolveResult:
        res = SolveResult(self.engine, q.id)
        t0 = time.perf_counter()
        prev_q = prev_err = ""
        for attempt in range(self.max_retries + 1):
            res.attempts = attempt + 1
            try:
                res.query = _clean(self.llm.complete(self._prompt(q.question, prev_q, prev_err),
                                                     system=_SYS, temperature=0.0))
            except Exception as e:  # noqa: BLE001 - LLM/network failure: count as a failed attempt
                prev_q, prev_err = "", f"llm error: {e}"
                res.error, res.valid = prev_err, False
                continue
            err = self._validate(res.query)
            if err:
                prev_q, prev_err, res.error, res.valid = res.query, err, err, False
                continue
            try:
                conn = kuzu_loader.connect(self.db_path)
                try:
                    conn.set_query_timeout(int(self.timeout_s * 1000))  # uniform budget (symmetry)
                except Exception:  # noqa: BLE001 - older kuzu without the method
                    pass
                qr = conn.execute(res.query)
                rows = []
                while qr.has_next():
                    rows.append(qr.get_next())
                res.rows = _flatten(rows)
                res.valid, res.error, res.timed_out = True, None, False
                break
            except Exception as e:  # noqa: BLE001 - kuzu raises RuntimeError on bad/slow Cypher
                res.timed_out = "timeout" in str(e).lower() or "interrupt" in str(e).lower()
                prev_q, prev_err, res.error, res.valid = res.query, str(e), str(e), False
        res.latency_s = round(time.perf_counter() - t0, 2)
        return res
