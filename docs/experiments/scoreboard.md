# Eval Scoreboard (M3 baseline)

Reason model: `deepseek-v4-flash:cloud`. Embeddings: `bge-m3`. SQL = pillar B (text-to-SQL); Vector = pillar A (hybrid dense+BM25 RRF).

## B — Text-to-SQL (Q1/Q2/Q6)

| Set | n | exec_acc | value_recall | valid_sql | avg_attempts | faithful | correct | latency_s |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| ALL | 32 | 0.719 | 0.858 | 1.0 | 1.0 | 0.969 | 0.812 | 26.528 |
| Q1 | 12 | 0.917 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 22.261 |
| Q2 | 8 | 0.625 | 0.75 | 1.0 | 1.0 | 1.0 | 0.75 | 32.874 |
| Q5 | 6 | 0.5 | 0.911 | 1.0 | 1.0 | 0.833 | 0.667 | 28.535 |
| Q6 | 6 | 0.667 | 0.667 | 1.0 | 1.0 | 1.0 | 0.667 | 24.597 |

## A — Hybrid vector (Q3/Q8)

| Set | n | recall@5 | recall@10 | MRR | faithful | correct | latency_s |
|---|--:|--:|--:|--:|--:|--:|--:|
| ALL | 40 | 0.975 | 0.975 | 0.926 | 0.993 | 0.96 | 16.654 |
| Q3 | 24 | 0.958 | 0.958 | 0.897 | 1.0 | 0.938 | 16.552 |
| Q8 | 16 | 1.0 | 1.0 | 0.969 | 0.981 | 0.994 | 16.806 |

_exec_acc = exact result-set match; value_recall = lenient key-value overlap._