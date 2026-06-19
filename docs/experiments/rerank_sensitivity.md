# Rerank sensitivity — cross-encoder across distractor densities

Does the reranking verdict survive a harder/easier hard set? Model-free cross-encoder; only the data knob (min notes per client) varies.

| min notes/client | n | RRF MRR | +CE MRR | RRF r@1 | +CE r@1 | verdict |
|--:|--:|--:|--:|--:|--:|---|
| 3 | 36 | 0.654 | 0.824 | 0.556 | 0.778 | justified |
| 5 | 36 | 0.717 | 0.847 | 0.639 | 0.75 | justified |
| 7 | 36 | 0.746 | 0.844 | 0.694 | 0.806 | justified |

_A verdict that flips across densities is fragile; a stable sign is robust._