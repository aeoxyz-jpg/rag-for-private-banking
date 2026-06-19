# Retro — substrate validation, gap-closing & repo reorg (2026-06-19)

**Project in one line:** Closed the three load-bearing evaluation gaps a critique flagged (router
accuracy unmeasured; reranker tested only as a weak LLM; negatives not stress-tested for the
too-easy-substrate confound), reframed the E verdict as conditional, then reorganized the repo
around one two-layer narrative. Merged to `main` (20 commits).

## Outcomes (what the experiments actually said)

- **Router (F)** — new `rm_assistant/routerx/` (confusion-matrix `report.py` + injectable
  `runner.py`) over a hand-labeled `rm_assistant/eval/gold/routing.json` (28 q, all 6 routes incl.
  Q4/Q7 + E↔B boundary). deepseek **100%**, glm-5.2 **96%** — the one miss is the canonical
  count-aggregate-of-a-metric boundary ("clients with AUM>1M" → metric instead of sql).
- **Reranker** — added `CrossEncoderReranker` (`bge-reranker-v2-m3`) to `rm_assistant/rerankx/`.
  **Flipped the headline**: small LLM reranker net-hurts (MRR 0.62→0.51) but the trained
  cross-encoder net-helps (0.62→0.74; actionable recall@1 0→0.71), robust across distractor
  density. The earlier "reranking net-hurts" was an artifact of a weak reranker.
- **KG** — `scripts/eval/sweep_kg.py` re-runs the oracle ceiling at 3 graph scales. Verdict
  ("recursive SQL capable except shortest_path") holds, with the first crack at the largest graph
  (SQL non-path categories 1.0→0.90).
- **E** — verdict reframed to "Yes, *conditional on* catalog-gated abstention + out-of-catalog
  rare"; abstention promoted from Open to a stated precondition.

## Technical lessons (this codebase)

### 1. torch/FlagEmbedding and embedded KùzuDB cannot share a process
The `rerank` extra (torch + FlagEmbedding) destabilizes the KG experiment: a full
`run_kg_experiment.py` run crashes natively (SIGSEGV/SIGBUS, exit 138/139, **no Python
traceback**) once the `rerank` stack is installed — even after uninstalling torch the crash
persisted, so the trigger is **load**, not torch per se (see #2). Mitigation now baked in:
- `pyproject.toml` keeps the cross-encoder behind the optional `rerank` extra; Appendix C installs
  it only for the rerank steps and `uv sync`s it away before KG.
- `CrossEncoderReranker.__init__` imports FlagEmbedding **lazily** so the core package stays
  torch-free (and the unit test uses `__new__` to skip the model load — passes without torch).

### 2. The KG crash is load-dependent, and the verdict doesn't need the crashing path
`n=1, samples=1` runs clean; `n=20, samples=3` crashes. The crash is on **LLM-generated** Cypher
under volume (a pathological-but-valid query trips kuzu natively). The fix wasn't to fight the
crash — the KG verdict is **oracle-keyed** (capability ceiling), and `runner.run(..., samples=0)`
produces oracle-only records with **zero LLM queries**. So `sweep_kg.py` runs oracle-only:
crash-free *and* the methodologically correct test. (`rm_assistant/kgx/runner.py:50` — the
`for s in range(samples)` loop is empty at samples=0.)
- kgx record schema: `mode∈{oracle,llm}`, `engine∈{sql,cypher}`, `category` (incl. `shortest_path`),
  boolean `correct`, `hop_depth`. SQL `shortest_path` oracle = 0.0 by design (recursive CTE hits
  the 30s timeout in `solvers.py`).

### 3. FlagEmbedding 1.4.0 needs transformers < 5
The `rerank` extra first resolved transformers 5.12.1; FlagEmbedding 1.4.0 calls
`tokenizer.prepare_for_model(...)`, removed in transformers 5.x → `AttributeError` at score time
(unit test still passes because it stubs the model). Pinned `transformers<5` in the extra.

### 4. semrepr artifacts are tracked SOURCE — don't move them into `data/`
The plan said relocate the dbt/ttl specs to `data/semrepr/`, but `data/` is gitignored → that
would silently drop committed source. Moved to `rm_assistant/semrepr/specs/` instead, with
`SRC = Path(__file__).resolve().parent / "specs" / ...` (CWD-robust). Read-before-move caught it.

### 5. Key files added/changed
- `rm_assistant/routerx/{report,runner}.py` · `rm_assistant/eval/gold/routing.json`
- `rm_assistant/rerankx/reranker.py` (`CrossEncoderReranker`) · `hardset.py` (`filter_by_density`)
- `scripts/eval/{run_router_eval,sweep_rerank,sweep_kg}.py`
- scripts regrouped into `scripts/{build,eval,ask,smoke}/`; two `sweep_*` subprocess paths point at
  `scripts/build/...` (must track if scripts move again).
- `config.py`: `RERANK_HARD_MIN_NOTES` (renamed from `…MIN_SIBLINGS` — the knob filters note count,
  siblings = notes−1; the old name mislabeled the sweep axis).

## What went sideways (honest)
- Both the torch-is-the-cause hypothesis (mine) and "uninstall it" (user's) were **wrong** — but
  acting on it cleanly **ruled torch out** and pointed at load/LLM-query. A wrong hypothesis that
  produces a decisive experiment is still progress.
- The first KG sweep was dispatched to a subagent, which **backgrounded the long job and ended its
  turn**, losing the child process. Long deterministic jobs belong in a controller-run background
  Bash with polling, not a subagent.
- Plan granularity: most tasks shipped verbatim code, so controller diff-verification (not two
  review subagents per task) was the right call; the one independent final review still earned its
  keep (caught the `min-siblings` mislabel).
