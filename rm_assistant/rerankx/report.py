"""Aggregate rerankx records: MRR / recall@1 / recall@3 / mean-rank for RRF vs RRF+rerank, over the
full hard set and the actionable subset (gold in pool but not already rank-1), plus a pre-registered
verdict and the reranker's latency cost. Mechanical, not editorial (spec §7)."""
from __future__ import annotations

from ..eval.metrics import mean


def _ranks(records, arm):
    return [r[f"{arm}_rank"] for r in records]


def _recall_at(ranks, k):
    return round(mean([1.0 if r and r <= k else 0.0 for r in ranks]), 3) if ranks else 0.0


def _mrr(ranks):
    return round(mean([1.0 / r if r else 0.0 for r in ranks]), 3) if ranks else 0.0


def _arm(records, arm):
    ranks = _ranks(records, arm)
    inpool = [r for r in ranks if r]
    return {"mrr": _mrr(ranks), "recall@1": _recall_at(ranks, 1), "recall@3": _recall_at(ranks, 3),
            "mean_rank": round(mean(inpool), 2) if inpool else None}


def aggregate(records: list[dict]) -> dict:
    actionable = [r for r in records if r["in_pool"] and r["rrf_rank"] and r["rrf_rank"] > 1]
    return {
        "n": len(records),
        "pool_recall": round(mean([1.0 if r["in_pool"] else 0.0 for r in records]), 3) if records else 0.0,
        "actionable_n": len(actionable),
        "rerank_latency_s": round(mean([r["rerank_latency_s"] for r in records]), 2) if records else 0.0,
        "rrf": _arm(records, "rrf"),
        "rerank": _arm(records, "rerank"),
        "rrf_actionable": _arm(actionable, "rrf"),
        "rerank_actionable": _arm(actionable, "rerank"),
    }


def verdict(agg: dict) -> str:
    """Reranker justified iff it lifts ranking materially on the hard set (spec §7)."""
    mrr_lift = agg["rerank"]["mrr"] - agg["rrf"]["mrr"]
    r1_lift = agg["rerank"]["recall@1"] - agg["rrf"]["recall@1"]
    if mrr_lift >= 0.05 and r1_lift >= 0.10:
        return "justified"
    if mrr_lift <= 0.02 or r1_lift <= 0.03:
        return "not_justified"
    return "inconclusive"


def to_markdown(agg: dict, model: str) -> str:
    v = verdict(agg)
    a, b = agg["rrf"], agg["rerank"]
    L = ["# Reranking (RRF vs RRF + reranker) — hard-set validation", "",
         "Same RRF candidate pool, reordered by the reranker named below. Hard "
         "set = each question pinned to one note of a multi-note client, so the client's sibling notes "
         "are near-neighbour distractors. A reranker can only help where the gold is in the pool but "
         "not already rank-1.", "",
         f"Reranker: `{model}`. Pool recall (gold in pool): **{agg['pool_recall']:.0%}** "
         f"({agg['n']} questions; {agg['actionable_n']} actionable).", "",
         f"## Verdict: **{v.replace('_', ' ').upper()}**", "",
         "| arm | MRR | recall@1 | recall@3 | mean rank |",
         "|---|--:|--:|--:|--:|",
         f"| RRF | {a['mrr']} | {a['recall@1']} | {a['recall@3']} | {a['mean_rank']} |",
         f"| RRF + rerank | {b['mrr']} | {b['recall@1']} | {b['recall@3']} | {b['mean_rank']} |",
         "",
         f"Lift: MRR **{round(b['mrr'] - a['mrr'], 3)}**, recall@1 **{round(b['recall@1'] - a['recall@1'], 3)}**. "
         f"Reranker cost: **+{agg['rerank_latency_s']}s/query** (one model call per pooled candidate).", "",
         "## Actionable subset (gold in pool, RRF rank > 1)", "",
         "| arm | MRR | recall@1 | recall@3 | mean rank |",
         "|---|--:|--:|--:|--:|",
         f"| RRF | {agg['rrf_actionable']['mrr']} | {agg['rrf_actionable']['recall@1']} | {agg['rrf_actionable']['recall@3']} | {agg['rrf_actionable']['mean_rank']} |",
         f"| RRF + rerank | {agg['rerank_actionable']['mrr']} | {agg['rerank_actionable']['recall@1']} | {agg['rerank_actionable']['recall@3']} | {agg['rerank_actionable']['mean_rank']} |",
         "",
         "_Verdict rule: justified iff MRR lift >= 0.05 and recall@1 lift >= 0.10; not_justified iff "
         "MRR lift <= 0.02 or recall@1 lift <= 0.03; else inconclusive. If pool recall is low, the "
         "bottleneck is first-stage retrieval, not reranking._"]
    return "\n".join(L)
