"""Aggregate scored records into the dual metric (oracle capability vs LLM authoring) by
engine x category x hop-depth, and apply the falsifiable verdict — keyed on the ORACLE ceiling
(spec §12.2/§12.3). LLM accuracy is averaged over samples per question first. Mechanical, not editorial."""
from __future__ import annotations

from collections import defaultdict

from ..eval.metrics import mean


def _bucket(depth: int) -> str:
    return str(depth) if depth < 3 else "3+"


def _q_acc(records: list[dict]) -> dict:
    """(mode, engine, question_id) -> mean correctness over samples."""
    acc = defaultdict(list)
    for r in records:
        acc[(r["mode"], r["engine"], r["question_id"])].append(1.0 if r["correct"] else 0.0)
    return {k: mean(v) for k, v in acc.items()}


def aggregate(records: list[dict]) -> dict:
    qmeta = {r["question_id"]: (r["category"], r["hop_depth"]) for r in records}
    qacc = _q_acc(records)
    out: dict = {}
    for mode in ("oracle", "llm"):
        out[mode] = {}
        for eng in ("sql", "cypher"):
            items = [(qid, a) for (m, e, qid), a in qacc.items() if m == mode and e == eng]
            by_depth = {}
            for b in ("1", "2", "3+"):
                vals = [a for qid, a in items if _bucket(qmeta[qid][1]) == b]
                if vals:
                    by_depth[b] = round(mean(vals), 3)
            by_cat = {}
            for cat in sorted({qmeta[qid][0] for qid, _ in items}):
                by_cat[cat] = round(mean([a for qid, a in items if qmeta[qid][0] == cat]), 3)
            raw = [r for r in records if r["mode"] == mode and r["engine"] == eng]
            out[mode][eng] = {
                "by_depth": by_depth, "by_category": by_cat,
                "overall": round(mean([a for _, a in items]), 3) if items else 0.0,
                "valid": round(mean([1.0 if r["valid"] else 0.0 for r in raw]), 3) if raw else 0.0,
                "timeout": round(mean([1.0 if r["outcome"] == "timeout" else 0.0 for r in raw]), 3) if raw else 0.0,
            }
    return out


def verdict(agg: dict) -> str:
    """KG (traversal) justified iff the Cypher ORACLE materially out-answers the SQL ORACLE at
    depth>=3 (capability), not the LLM-authored numbers (which conflate dialect familiarity)."""
    sql = agg["oracle"]["sql"]["by_depth"].get("3+")
    cyp = agg["oracle"]["cypher"]["by_depth"].get("3+")
    if sql is None or cyp is None:
        return "inconclusive"
    if sql < 0.6 and (cyp - sql) > 0.2:
        return "justified"
    if sql >= 0.6 or (cyp - sql) <= 0.1:
        return "not_justified"
    return "inconclusive"


def _depth_row(label, d, overall, valid):
    return (f"| {label} | {d.get('1','-')} | {d.get('2','-')} | {d.get('3+','-')} | "
            f"{overall} | {valid} |")


def to_markdown(agg: dict, model: str) -> str:
    v = verdict(agg)
    L = ["# Knowledge-Graph Experiment v2 — pillar C (traversal) verdict", "",
         "**Scope (unchanged):** graph-DB + Cypher vs relational + recursive SQL over the SAME "
         "structured data, *traversal only* — NOT semantic-KG / ontology / GraphRAG. Numbers are about "
         "this synthetic graph.", "",
         f"Reason model: `{model}`. Symmetric prompting, temperature 0, uniform 30s budget. "
         "Two metrics, never collapsed: **oracle** = expert-written query (capability ceiling); "
         "**llm** = model-authored (practical). The gap = dialect-authoring tax.", "",
         f"## Verdict (keyed on the ORACLE ceiling): **{v.replace('_',' ').upper()}**", ""]
    for mode, title in (("oracle", "Capability ceiling (oracle queries)"),
                        ("llm", "LLM-authored accuracy")):
        L += [f"## {title}", "",
              "| engine | depth 1 | depth 2 | depth 3+ | overall | valid |",
              "|---|--:|--:|--:|--:|--:|"]
        for e in ("sql", "cypher"):
            m = agg[mode][e]
            L.append(_depth_row(e, m["by_depth"], m["overall"], m["valid"]))
        L += ["", "By category:", "", "| category | sql | cypher |", "|---|--:|--:|"]
        cats = sorted(set(agg[mode]["sql"]["by_category"]) | set(agg[mode]["cypher"]["by_category"]))
        for c in cats:
            L.append(f"| {c} | {agg[mode]['sql']['by_category'].get(c,'-')} | "
                     f"{agg[mode]['cypher']['by_category'].get(c,'-')} |")
        L.append("")
    L += ["_Verdict rule (oracle, depth 3+): justified iff SQL < 0.6 and (Cypher-SQL) > 0.2; "
          "not_justified iff SQL >= 0.6 or advantage <= 0.1; else inconclusive._"]
    return "\n".join(L)
