# Reranking (RRF vs RRF + reranker) — hard-set validation

Same RRF candidate pool, reordered by the reranker named below. Hard set = each question pinned to one note of a multi-note client, so the client's sibling notes are near-neighbour distractors. A reranker can only help where the gold is in the pool but not already rank-1.

Reranker: `BAAI/bge-reranker-v2-m3`. Pool recall (gold in pool): **86%** (36 questions; 14 actionable).

## Verdict: **JUSTIFIED**

| arm | MRR | recall@1 | recall@3 | mean rank |
|---|--:|--:|--:|--:|
| RRF | 0.621 | 0.472 | 0.75 | 2.06 |
| RRF + rerank | 0.739 | 0.694 | 0.75 | 1.71 |

Lift: MRR **0.118**, recall@1 **0.222**. Reranker cost: **+2.45s/query** (one model call per pooled candidate).

## Actionable subset (gold in pool, RRF rank > 1)

| arm | MRR | recall@1 | recall@3 | mean rank |
|---|--:|--:|--:|--:|
| RRF | 0.383 | 0.0 | 0.714 | 3.36 |
| RRF + rerank | 0.787 | 0.714 | 0.786 | 2.21 |

_Verdict rule: justified iff MRR lift >= 0.05 and recall@1 lift >= 0.10; not_justified iff MRR lift <= 0.02 or recall@1 lift <= 0.03; else inconclusive. If pool recall is low, the bottleneck is first-stage retrieval, not reranking._