# Coverage Map — what this project tests vs. industry-common RAG types

_Date: 2026-06-17. Input to the P3b/P3c brainstorm. Companion to `docs/TECHNICAL_REPORT.md`
(Phase-1/2 results) and `HANDOFF.md` (roadmap). Purpose: make the design-space coverage explicit
and record which gaps are **in scope** vs **deliberately out**._

## What the project actually tests

This is a **"which query archetype demands which retrieval strategy"** comparison framework, not a
single architecture. Four layers under test:

1. **Retrieval architecture / pattern** — text-to-SQL (B), hybrid dense+sparse vector w/ RRF (A),
   governed semantic/metrics layer (E), Customer-360 synthesis (D-lite), agentic router + query
   decomposition (F), graph traversal Cypher-vs-recursive-SQL (C, Phase 2).
2. **Engine / platform** — SQLite+FTS5(BM25), Chroma (vector), KùzuDB (graph), NetworkX (canonical
   graph build), Ollama; models `bge-m3` (embed) / `deepseek-v4-flash:cloud` (reason) / Codex (seeds).
3. **KB / data design** — unified warehouse; `ontology.yaml` governed-metric backbone (3a tests its
   anti-drift value, 3b will test its storage representation); grounded+provenance-tagged corpus;
   relationship-rich graph dataset (UBO/household/employer).
4. **Evaluation methodology** — oracle vs LLM-authored separation, pre-registered falsifiable
   verdicts, signed confound enumeration, exec_match + value_recall dual metric. (Project's spine.)

## Industry coverage matrix

| Industry-common category | Status | Note |
|---|---|---|
| Dense vector RAG | ✅ | half of A |
| Hybrid (dense + sparse/BM25) | ✅ | RRF |
| **Reranking** (cross-encoder / late-interaction) | ✅ (Phase 3d) | LLM-as-reranker (qwen2.5:3b) net-hurt on the hard set (MRR 0.62→0.51); verdict not justified. Trained cross-encoder still untested (torch-free GGUFs broken on Ollama 0.30.8). `docs/rerank_eval.md` |
| Text-to-SQL / NL2SQL | ✅ | B |
| Semantic / metrics layer (dbt SL, Cube, LookML) | ✅ | E; 3a (value) + 3b (storage: all 3 reprs reproduce canonical numbers; dbt-style→migrate, RDF→keep — `docs/semrepr_eval.md`) |
| **GraphRAG / semantic-KG over unstructured text** | ⏸️ **DEFERRED (Phase 4)** | precondition probe: notes corpus has ~0 cross-document entity structure (0% mention a company, 1.3% mention another client) → GraphRAG has nothing to exploit here; fair test needs a purpose-built corpus. See below + `scripts/probe_corpus_entity_structure.py` |
| Graph traversal / multi-hop | ✅ | Phase 2: graph justified only for variable-length path-finding |
| Agentic router / query decomposition | ✅ | F |
| Multi-source synthesis / Customer-360 | ✅ | D |
| Embedding-model bake-off | ⛔ **OUT** | only `bge-m3` |
| Vector-DB bake-off (pgvector/Milvus/Weaviate/ES) | ⛔ **OUT** | only Chroma |
| Chunking-strategy study | ⛔ **OUT** | corpus notes are short; chunking not a variable |
| Long-context baseline / fine-tune vs RAG | ⛔ **OUT** | not a design question here |
| Evaluation rigor | ✅✅ | exceeds industry norm |

Production axes (temporal/SCD point-in-time, multi-tenant row-level isolation, latency/cost,
incremental index refresh, observability) remain out — already noted in `TECHNICAL_REPORT.md` §4/§5.

## In-scope additions (this decision)

### 1. Reranking experiment — extends pillar A ✅ DONE (Phase 3d)
- **Built:** `rm_assistant/rerankx/` — RRF vs RRF+reranker on a hard, distractor-rich set (each question
  pinned to one note of a multi-note client, so siblings are near-neighbour confusers). Metrics: MRR /
  recall@1/@3 / mean-rank, with the actionable subset (gold in pool, RRF rank > 1) reported separately.
- **Reranker pivot:** the dedicated Qwen3-Reranker GGUFs were broken (garbage output) or embedding-only
  ("does not support generate") on Ollama 0.30.8, which has no native rerank endpoint. Used an
  **LLM-as-reranker** (`qwen2.5:3b-instruct` pointwise relevance judge, P(yes) from logprobs) instead —
  no torch. A trained cross-encoder remains the untested comparison.
- **Result:** **not justified** — the LLM reranker net-hurt ranking (MRR 0.62→0.51, recall@1 0.47→0.39,
  +8.4s/query): it promotes buried golds (actionable subset MRR 0.38→0.58) but reshuffles RRF's correct
  rank-1s downward. Pool recall 0.86 (14% first-stage misses). `docs/rerank_eval.md`.

### 2. GraphRAG over unstructured text — DEFERRED to Phase 4 (precondition absent)
- **Distinct from Phase 2.** Phase 2 tested *traversal over the structured graph* (Cypher vs recursive
  SQL) and concluded "graph justified only for path-finding." That verdict says **nothing** about
  GraphRAG — keep them separate; do not let the Phase-2 result be read as "graph not useful for RAG."
- **Why deferred (evidence-based, 2026-06-18).** A precondition probe
  (`scripts/probe_corpus_entity_structure.py`) found the notes corpus has **near-zero cross-document
  entity structure**: of 1623 single-client notes, **0%** mention a company and **1.3%** mention another
  client. GraphRAG's mechanism (extract entities → link them *across documents* → traverse/aggregate)
  has nothing to bite on here. Worse, the relationships that *do* exist (household/employer/UBO) are
  already **structured** and were covered by Phase 2 — GraphRAG would re-extract (worse) what is already
  given. Building a graph on this shallow, self-authored corpus and authoring matching questions would
  **repeat the Phase-1 Q5 circular-gate mistake** (TECHNICAL_REPORT §3.4). The one regime GraphRAG would
  genuinely win — *global sensemaking* ("themes across my book") — has **no canonical gold**, so a
  verdict would rest on subjective LLM-judge scoring the project flags as noisy.
- **A fair test is a Phase-4 data-generation project**, not a retrieval experiment: synthesize a corpus
  with real cross-document entity structure + global-theme ground truth (analogous to how Phase 2 built
  deep relationship data before the KG test was fair). Until then, GraphRAG-over-unstructured stays
  deferred — neither adopted nor rejected.

## Out-of-scope (this decision)

- **Selection bake-offs** — embedding model, vector DB, chunking strategy. These are engineering
  selection, not architecture/design questions. Revisit only if a pillar underperforms on its archetype.
- Long-context baseline and fine-tune-vs-RAG: out for the same reason.
