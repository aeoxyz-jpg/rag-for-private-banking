"""Aggregate eval records into a comparable scoreboard (spec §5.3)."""
from __future__ import annotations

from .metrics import mean


def _avg(rows, key):
    vals = [r[key] for r in rows if key in r and isinstance(r[key], (int, float, bool))]
    return round(mean([float(v) for v in vals]), 3) if vals else None


def _group(records, pillar):
    rows = [r for r in records if r.get("pillar") == pillar and "error" not in r]
    groups = {"ALL": rows}
    for r in rows:
        groups.setdefault(r["archetype"], []).append(r)
    return groups


def aggregate(records: list[dict]) -> dict:
    out = {"sql": {}, "vector": {}, "errors": [r["id"] for r in records if "error" in r]}
    for label, rows in _group(records, "B").items():
        out["sql"][label] = {
            "n": len(rows), "exec_accuracy": _avg(rows, "exec_match"),
            "value_recall": _avg(rows, "value_recall"), "valid_sql_rate": _avg(rows, "valid_sql"),
            "avg_attempts": _avg(rows, "attempts"), "faithfulness": _avg(rows, "faithfulness"),
            "correctness": _avg(rows, "correctness"), "latency_s": _avg(rows, "latency_s"),
        }
    for label, rows in _group(records, "A").items():
        out["vector"][label] = {
            "n": len(rows), "recall@5": _avg(rows, "recall@5"),
            "recall@10": _avg(rows, "recall@10"), "mrr": _avg(rows, "mrr"),
            "faithfulness": _avg(rows, "faithfulness"), "correctness": _avg(rows, "correctness"),
            "latency_s": _avg(rows, "latency_s"),
        }
    return out


def _row(label, d, cols):
    cells = " | ".join(str(d.get(c, "-")) for c in cols)
    return f"| {label} | {d['n']} | {cells} |"


def to_markdown(agg: dict, model: str) -> str:
    L = ["# Eval Scoreboard (M3 baseline)", "",
         f"Reason model: `{model}`. Embeddings: `bge-m3`. "
         "SQL = pillar B (text-to-SQL); Vector = pillar A (hybrid dense+BM25 RRF).", ""]

    L += ["## B — Text-to-SQL (Q1/Q2/Q6)", "",
          "| Set | n | exec_acc | value_recall | valid_sql | avg_attempts | faithful | correct | latency_s |",
          "|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
    sc = ["exec_accuracy", "value_recall", "valid_sql_rate", "avg_attempts",
          "faithfulness", "correctness", "latency_s"]
    for label in ["ALL"] + sorted(k for k in agg["sql"] if k != "ALL"):
        L.append(_row(label, agg["sql"][label], sc))

    L += ["", "## A — Hybrid vector (Q3/Q8)", "",
          "| Set | n | recall@5 | recall@10 | MRR | faithful | correct | latency_s |",
          "|---|--:|--:|--:|--:|--:|--:|--:|"]
    vc = ["recall@5", "recall@10", "mrr", "faithfulness", "correctness", "latency_s"]
    for label in ["ALL"] + sorted(k for k in agg["vector"] if k != "ALL"):
        L.append(_row(label, agg["vector"][label], vc))

    if agg["errors"]:
        L += ["", f"**Errored queries:** {', '.join(agg['errors'])}"]
    L += ["", "_exec_acc = exact result-set match; value_recall = lenient key-value overlap._"]
    return "\n".join(L)
