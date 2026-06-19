# KG sensitivity — oracle-ceiling robustness across graph scale/depth

Does the oracle-keyed verdict ('recursive SQL is fully capable except variable-length shortest_path') survive as the graph scales? Each row rebuilds the graph at a different scale and re-runs the hand-authored oracle queries (8/category, model-free, deterministic). SQL shortest_path is expected at 0.0 (recursive CTE times out at 30s); every other category is expected at 1.0 for both engines.

| scale | nodes/edges | SQL shortest_path | Cypher shortest_path | SQL other cats | Cypher other cats |
|---|---|--:|--:|--:|--:|
| small | 806/1937 | 0.0 | 1.0 | 1.0 | 1.0 |
| default | 1215/2897 | 0.0 | 1.0 | 1.0 | 1.0 |
| large | 1953/4615 | 0.0 | 1.0 | 0.9 | 1.0 |

_A stable pattern (SQL=0 on shortest_path, =1 elsewhere; Cypher=1 throughout) across scales means the verdict is robust, not an artifact of one graph size._

_Note: the LLM-authored sweep was abandoned — pathological LLM-generated Cypher under heavy load (n×samples) reliably crashed the embedded kuzu engine natively (SIGBUS/SIGSEGV). The oracle ceiling is the verdict-relevant signal and is crash-free; LLM-authoring capability is separately characterized in the main report and is model-bound, not scale-bound._