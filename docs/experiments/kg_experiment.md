# Knowledge-Graph Experiment v2 — pillar C (traversal) verdict

**Scope (unchanged):** graph-DB + Cypher vs relational + recursive SQL over the SAME structured data, *traversal only* — NOT semantic-KG / ontology / GraphRAG. Numbers are about this synthetic graph.

Reason model: `deepseek-v4-flash:cloud`. Symmetric prompting, temperature 0, uniform 30s budget. Two metrics, never collapsed: **oracle** = expert-written query (capability ceiling); **llm** = model-authored (practical). The gap = dialect-authoring tax.

## Verdict (keyed on the ORACLE ceiling): **JUSTIFIED**

## Capability ceiling (oracle queries)

| engine | depth 1 | depth 2 | depth 3+ | overall | valid |
|---|--:|--:|--:|--:|--:|
| sql | 1.0 | 1.0 | 0.579 | 0.857 | 0.857 |
| cypher | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 |

By category:

| category | sql | cypher |
|---|--:|--:|
| controls | 1.0 | 1.0 |
| household | 1.0 | 1.0 |
| k_hop | 1.0 | 1.0 |
| shortest_path | 0.0 | 1.0 |
| ubo | 1.0 | 1.0 |

## LLM-authored accuracy

| engine | depth 1 | depth 2 | depth 3+ | overall | valid |
|---|--:|--:|--:|--:|--:|
| sql | 0.759 | 0.386 | 0.386 | 0.506 | 0.857 |
| cypher | 0.741 | 0.333 | 0.579 | 0.548 | 0.958 |

By category:

| category | sql | cypher |
|---|--:|--:|
| controls | 0.0 | 0.375 |
| household | 0.75 | 0.875 |
| k_hop | 0.931 | 0.528 |
| shortest_path | 0.0 | 1.0 |
| ubo | 0.0 | 0.0 |

_Verdict rule (oracle, depth 3+): justified iff SQL < 0.6 and (Cypher-SQL) > 0.2; not_justified iff SQL >= 0.6 or advantage <= 0.1; else inconclusive._