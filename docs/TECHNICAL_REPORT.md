# RM Copilot — A Routed-Hybrid RAG, and the Discipline That Makes Its Verdicts Trustworthy

_A wealth / private-banking Relationship-Manager Copilot. This report is organized by **technical
completeness** (does the architecture cover the retrieval design space, and where are its boundaries?)
and **experimental integrity** (what makes the conclusions — including the negative ones — trustworthy?),
not by phase chronology. Per-experiment scoreboards live in `docs/experiments/` (router_eval, scoreboard,
kg_experiment, kg_sensitivity, rerank_eval, rerank_sensitivity, semantic_eval, semantic_stability,
semrepr_eval, coverage_map). Methodology lessons: `docs/retros/`._

---

## 1. Framing: RAG retrieval is a *plural* search problem

It is tempting to call RAG "a search problem." The retrieval half is indeed information retrieval — but
this project is in large part a **counterexample to the single-search framing**, and the correction is
the whole thesis:

- **Retrieval is plural.** A wealth-RM question can be an exact aggregation over account data, a fuzzy
  recall over meeting notes, a governed-metric lookup, a multi-hop relationship traversal, or a global
  synthesis. The real problem is not "search better" — it is **recognizing when a question should not be
  treated as fuzzy search at all** and routing it to text-to-SQL, a governed metric, or graph traversal.
  Forcing these into an embedding index is exactly how naive vector RAG silently returns wrong numbers.
- **The binding constraint was not recall.** On these evals — single-run, on synthetic self-authored data,
  so directional rather than definitive — *search was the least binding constraint*: the hybrid vector
  pillar saturated at recall@5 0.96–1.00, and reranking moved the needle only on a deliberately hard
  distractor set — and there only with a *trained cross-encoder*, not a small LLM judge, which net-*hurt*
  (§3.2). The hard failures
  were elsewhere — governed-metric drift (~1 paraphrasing in 5, §3.3), a semantic layer that mis-routes
  ~75–80% of out-of-catalog questions (§3.3), traversal capability at depth (§3.4), and — above all —
  **trustworthy evaluation**. Reducing RAG to "search" would misallocate effort: over-invest in the
  embedding index (saturated here) and under-invest in governance and evaluation (where the value was).

**So: retrieval is a routed family of search/lookup/traversal modalities, and the production-binding
constraint is correctness/consistency + honest evaluation, not raw recall.** The recommended architecture
is therefore a **router** (F) over text-to-SQL (B) and hybrid vector (A), with a governed semantic layer
(E), a Customer-360 (D), and a graph engine admitted only where it earns its place (§3.4).

### 1.1 Which technology, for which data *and which business question*

"Structured vs unstructured" and "relationship-heavy vs independent entities" are necessary axes but not
sufficient. The axis that actually drove the design here is **error tolerance / consistency**, orthogonal
to data type:

| Axis | Low-tolerance end → | High-tolerance end → |
|---|---|---|
| **Error tolerance** (the decisive one) | a wrong AUM is unacceptable → governed SQL / metric layer | a missed note is fine → fuzzy hybrid vector |
| **Consistency** | same question must give the same number → governed metric (E) | one-off answer is fine → free generation |
| **Answer cardinality** | point fact / set aggregate / path / **global synthesis** | aggregation & global queries break flat RAG → SQL / graph |
| **Data structure** | structured warehouse → B/E | unstructured notes/KB → A |
| **Relational density** | dense inter-entity links → graph traversal (C) | independent individuals → per-entity lookup |
| **Temporality** | point-in-time / as-of / SCD | snapshot is fine |

The eight query archetypes that drive the build are this taxonomy made concrete:

| # | Archetype | Example | Decisive axis |
|---|---|---|---|
| Q1 | precise filter / aggregation | "clients with AUM > $1M, no contact in 90d" | error-tolerance (exact) |
| Q2 | single-entity fact | "balance + last txn for account 4521" | error-tolerance (exact) |
| Q3 | fuzzy semantic recall | "what did this client say about retirement?" | unstructured, tolerant |
| Q4 | cross-document synthesis | "summarize everything before the meeting" | mixed |
| Q5 | multi-hop relationship | "who is linked to Company X?" | relational density |
| Q6 | metric / KPI consistency | "AUM and churn-risk for my book" | consistency |
| Q7 | hybrid reasoning | "of clients who mentioned liquidity, who has a maturing deposit?" | unstructured → structured |
| Q8 | policy / product Q&A | "eligibility for the structured-note product?" | unstructured KB |

---

## 2. The evaluation program as one system

The experiments are one program because they share a foundation and a discipline — the B/A scoreboard,
text-to-SQL vs the semantic layer (3a) and its storage form (3b), reranking (3d), KG traversal, router
accuracy, and the two data-knob sensitivity sweeps. This section is the connective tissue; §3 hangs the
evidence on it.

### 2.1 The experiment is a guarded loop, not a straight line

The naive method — *business need → construct data → stress-test → conclude* — produces **uninterpretable**
results, as this program learned twice (the Phase-1 Q5 gate and the first KG run, §3.4). The disciplined
version adds guards:

> business need → **enumerate confounds, each tagged with the engine it favours** → construct data **+ gold
> whose authorship is decoupled from the technique under test** → **pre-register the verdict rule** → run →
> *(if uninterpretable: diagnose the confound, fix, re-run)* → conclude

…plus a **pre-gate**: before constructing anything, ask *"is a fair test even constructible on the available
substrate?"* If not, **defer** rather than build a test that can only be circular (§3.4, GraphRAG).

### 2.2 Constructing experimental data to approximate reality (no real wealth data available)

The program uses **three separate datasets** (entangling them would re-introduce circularity), built under
two contrasting philosophies whose contrast is itself the lesson:

- **Anchor on real data; synthesize only the gaps.** The Phase-1 warehouse starts from **Berka** — a real
  anonymized Czech retail bank (1993–1998), pulled from the CTU public MariaDB, ~1.08M rows — and synthesizes
  *only* what Berka lacks (a `holdings` wealth layer, leads, RMs, companies, relationship edges), each
  **grounded** on real structured facts. Unstructured notes are LLM-generated *conditioned on each client's
  real rows and provenance-tagged* with them.
- **When no real data exists, anchor on real *reference models* and *structural invariants*.** The Phase-2
  relationship graph is greenfield (Berka has no relationships) but grounded in **FIBO / BODS / ICIJ / FATF**
  for vocabulary and structure, and constrained by realism invariants — control-based UBO through majority
  >50% links, clean consumed ownership trees → **~1–2 UBOs per entity, not dozens**.

From these, five **principles for realistic synthetic data**:

1. **Anchor on the realest available substrate**, in priority order: real data > real reference
   models/standards > real structural invariants. Minimize synthetic surface area; ground each synthetic
   layer on a real anchor.
2. **Make realistic the dimension the technique is *sensitive to*, not realism in general.** text-to-SQL is
   sensitive to real distributions and the fan-out join hazard; the KG test to relationship *depth and
   cyclicity* (shallow → no test); reranking to *distractor density* (saturated → no headroom); GraphRAG to
   *cross-document entity structure* (absent → nothing to test). Design realism to expose the specific
   failure mode.
3. **Guard against answer-shaped data.** Synthetic data is dangerous precisely because the author knows the
   answer and the data drifts to flatter the system. Antidotes: emit ground truth as a generator byproduct
   *before any query exists*; decouple gold authorship from the technique; make the data *adversarial* to
   the hypothesis (hard distractors, deep chains, held-out entities) rather than convenient.
4. **Determinism + provenance = the trust substrate.** Seeded builds (two projections byte-consistent),
   provenance tags (which real fact grounded which synthetic note) → auditable, reproducible. Realism you
   cannot audit is not trustworthy.
5. **Label every divergence from reality.** USD with no FX; synthetic loan rates; `churn_risk` is a
   heuristic, not a real label; `share_of_wallet` is a documented proxy. Unmarked synthesis gets over-read.

**Where this discipline still has gaps (worth stating honestly):**
- **Distributional fidelity is asserted, not checked.** Realism is grounded in reference models, but the
  synthetic *output* is not systematically compared to published real stylized facts (wealth Pareto tails,
  transaction inter-arrival, household-size and ownership-chain-depth distributions). A "synthetic vs real
  distribution" check is missing.
- **Multi-*dataset* sensitivity — now run for the confound-exposed negatives.** The data-analog of the 3a
  insight (regenerate with different generator knobs — does the verdict hold?) was applied to the two
  negatives most at risk from a too-easy substrate: the reranker verdict across **distractor density** (§3.2)
  and the KG oracle verdict across **graph scale** (§3.4). Both survive — the KG verdict only cracks at the
  largest graph — so those conclusions are not artifacts of one generator setting. Still partial: the sweep
  covered the two load-bearing negatives, not every experiment.
- **The synthetic-data ceiling.** Some answers (true churn, real share-of-wallet, global-theme ground truth)
  cannot exist without real-world outcomes. The principle: **do not synthesize a ground truth you would need
  reality to know** — mark it out-of-scope rather than fake it with an LLM judge. (This is exactly why
  GraphRAG was deferred, §3.4.)

### 2.3 Gold construction (decoupling answer from system)

- **Structured/governed:** gold is a *verified reference query* (B) or the **canonical value computed once
  from `ontology.metric_sql`** (E, 3a) — never an engine's own output.
- **Unstructured:** gold is a *question reverse-generated from a known document* — recall then measures
  whether retrieval surfaces the source doc (40 vector queries; the 3d hard set, §3.2).
- **Relational:** gold is **generator-emitted** (`graph_truth.json`) as a byproduct of building the graph,
  before any query exists (§3.4).

### 2.4 Verdict discipline (shared across experiments)

Pre-registered falsifiable rule; confounds enumerated with their sign; **capability (an expert oracle)
kept separate from LLM-authoring skill**; **multi-run when a threshold straddles the measured value**;
report the **magnitude/distribution**, not just a binary label; and capture *what the engine did*, because
a pass/fail number can hide a worse failure mode.

---

## 3. Coverage by regime

For each regime: the strategy, what was validated, the boundary, and what stays open. Evidence is from the
eval scoreboards (`deepseek-v4-flash:cloud` reasoning, `bge-m3` embeddings; full tables in Appendix A).

### 3.1 Structured precision — text-to-SQL (B)

**Strategy.** NL→SQL over the warehouse, grounded in `ontology.yaml` (schema + glossary), read-only
guardrails, self-correction. Owns Q1/Q2/Q6, and Q5 via the `edges` table.
**Validated.** Owns structured precision: Q1 **value-recall 1.00** (exec 0.92), valid-SQL 1.0, avg attempts
1.0; B's number for "total AUM of UHNW" is the correct **$17.68M**. This is the regime where naive vector
RAG silently returns wrong aggregates; B owns it.
**Boundary & the pivotal bug.** The AUM metric joined `accounts` to raw `holdings` and **double-counted
balance once per holding**, inflating "clients > $1M" from the true **256 to 514**. The wrong formula sat in
the governed metric, the few-shot, *and* the gold simultaneously — yet eval caught it as a contradiction
between two paths that should agree. Fix (now an invariant): pre-aggregate holdings per account before the
join. This single bug is the entire argument for a governed semantic layer. (`exec_match` is also too brittle
at small n — swung Q2 1.0↔0.625 across runs — so `value_recall` is the steadier reported signal.)
**Open.** Point-in-time / SCD temporal SQL.

### 3.2 Semantic recall — hybrid vector (A) + reranking

**Strategy.** Dense (`bge-m3`/Chroma) + lexical BM25 (SQLite FTS5) fused by Reciprocal Rank Fusion, then a
grounded, cited answer. Owns Q3 (notes) and Q8 (policy/product KB).
**Validated.** **recall@5 0.975 / MRR 0.926** overall; Q8 perfect (recall@5 1.00, correctness 0.99). On this
eval set, search is saturated — though note the protocol is generous (questions reverse-generated from the
target doc); the hard-set pool recall of 0.86 below shows it is not literally "solved."
**Boundary — the reranker *method* decides the sign, not reranking per se.** Because the standard eval is
saturated, a fair rerank test needed a deliberately hard set: each question pinned to one note of a
multi-note client so the client's sibling notes are near-neighbour distractors. Two rerankers, same RRF
pool, opposite verdicts:
- A **small LLM-as-reranker** (`qwen2.5:3b`, P(yes) from yes/no logprobs — Ollama 0.30.8 has no rerank
  endpoint and the dedicated Qwen3-Reranker GGUFs were broken/embedding-only) **net-hurts**: MRR 0.62→0.51,
  recall@1 0.47→0.39 at +8.4s/query. It promotes a buried gold when one exists but more often reshuffles
  RRF's already-correct rank-1s down.
- The **textbook trained cross-encoder** (`bge-reranker-v2-m3`, same family as the `bge-m3` embeddings)
  **net-helps, materially**: MRR 0.62→0.74, recall@1 0.47→0.69 at +2.45s/query (cheaper than the LLM arm,
  no network). On the actionable subset (gold in pool but RRF rank > 1) it lifts recall@1 from **0.0 to
  0.71**. And the help is **robust to distractor density** — a sensitivity sweep over the hard-set knob
  (min notes/client 3/5/7) keeps the verdict `justified` at every density (MRR lift +0.17/+0.13/+0.10),
  the lift shrinking only because RRF itself strengthens as distractors thicken.

So the earlier "reranking net-hurts" was an artifact of a *weak* reranker; the correct reading is that the
reranker method is the lever. Pool recall 0.86 → 14% are first-stage misses no reranker can fix (a real but
secondary ceiling). Engineering note: torch + FlagEmbedding (the cross-encoder stack) cannot share a process
with the embedded KùzuDB used by the KG experiment — under load it crashes natively — so the cross-encoder
ships as an optional `rerank` extra, run separately (Appendix C).
**Open / honest scope.** Late-interaction (ColBERT-style) reranking, chunking strategy, and
embedding/vector-DB bake-offs remain unexplored.

### 3.3 Governed metrics — the semantic layer (E): does it earn its keep, and where should it live?

**Strategy.** E serves *governed* metric SQL from `ontology.yaml`; the LLM picks the metric + filter and
**never writes the formula**. Owns Q6. Boundary with B: E answers per-client / threshold / ranking KPIs;
segment- or attribute-aggregates need a join and belong to B (which reuses E's formula).
**Validated — value (3a).** Across paraphrasings of the same KPI, free text-to-SQL drifts off the canonical
number while E is exact by construction. But the headline finding is the *fragility of the binary verdict*:
single runs landed at 0.173 (inconclusive) and 0.208 (justified), and a **5-run stability pass** pins B's
drift at **0.20 ± 0.009** (range 0.185–0.214) — sitting almost exactly on the pre-registered 0.2 cutoff, so
the binary label flips on run noise. **The magnitude (~1 in 5 paraphrasings off, concentrated in composite
KPIs `churn_risk`/`days_since_contact`) is the result, not the label.**
**Validated — boundary cost.** Recording *which* metric E picked turned a benign-looking "abstains on 30% of
out-of-catalog probes" into the real behaviour: E **mis-routes ~75–80%** (75% single-run; mean 0.78 across
the 5-run pass, itself run-noisy at 0.65–0.90) — it silently answers an ungoverned
question with a nearby wrong metric, arguably worse than B, which at least attempts the real question. A
pass/fail number had hidden the worse mode.
**Validated — storage (3b).** Porting the 5 metrics to a dbt/Cube-style declarative spec and an RDF graph,
all three (incl. baseline YAML+hand-SQL) reproduce the canonical numbers (hard equivalence gate). The
declarative form expresses `share_of_wallet` as a **native ratio reference** to `aum` (vs the baseline's
`{{ref}}` string-substitution) and *generates* SQL → verdict **migrate**; RDF models composition as
`dependsOn` lineage but keeps SQL literals (same substitution mechanically) → **keep**. Limit: `churn_risk`'s
clamped weighted sum needs a raw-SQL **escape hatch** in every representation.
**Precondition for the positive verdict (not optional).** Catalog-gated abstention to eliminate the
~75–80% mis-route (separable from where the metric lives). Without it, on a query mix where out-of-catalog
questions are common, the mis-route mode above makes E plausibly **net-negative**. The positive verdict
therefore holds *conditional on* this gate plus a query mix where out-of-catalog is rare.
**Open.** Whether to actually migrate the production layer to the declarative form.

### 3.4 Relationship / multi-hop — graph traversal (C), and the GraphRAG frontier

**Strategy & verdict (traversal).** On a deep synthetic graph (1,215 nodes / 2,897 edges; §2.2), LLM→Cypher
over embedded KùzuDB vs LLM→recursive-SQL over SQLite, scored by hop-depth against generator ground truth.
A graph engine is justified **only for variable-length path-finding** — recursive-CTE shortest-path on a
cyclic graph is exponential and times out, while native `-[:Rel* SHORTEST]-` is trivial — but for every
fixed-depth pattern (k-hop, household, UBO, control chains) **recursive SQL is fully capable** at the oracle
ceiling (SQL fails only `shortest_path`: 0.0 vs Cypher 1.0; all other categories 1.0/1.0).
**Robustness — verdict holds across graph scale, with the first crack at the top end.** A sensitivity sweep
rebuilt the graph at three scales (806 / 1,215 / 1,953 nodes) and re-ran the oracle ceiling at each (the
verdict is oracle-keyed, so this is the right knob to vary). The pattern is stable — SQL stays at 0.0 on
`shortest_path` and Cypher at 1.0 throughout — but at the **largest** graph SQL's *other* categories slip
from 1.0 to **0.90**: as the graph grows, recursive-CTE capability begins to degrade beyond just
`shortest_path`, which a single-scale test could not have shown and which *strengthens* the case for a graph
engine at scale (`docs/experiments/kg_sensitivity.md`).
**The integrity story (why this verdict is believable).** The Phase-1 version of this question was a
**circular gate** — shallow self-authored data + queries written to match + one author for data/queries/system.
Even the rebuilt experiment's *first* run was **rigged in both directions** (a 3-reviewer panel found it
uninterpretable): a precomputed `ubo` table let SQL read the answer, while Neo4j-dialect few-shots KùzuDB
rejects sabotaged Cypher. The pre-registered fix separated an **expert oracle** (capability) from
**LLM-authored** accuracy — and that gap is the real finding: LLM-authored accuracy (SQL 0.51 / Cypher 0.55)
sits far below both oracle ceilings, so the practical bottleneck is the model writing a correct deep query,
not the engine, and much of the gap is that LLMs have seen far more SQLite than Kùzu-Cypher.
**Frontier — GraphRAG over unstructured text: deferred on evidence.** Before building an
entity-extraction-and-graph pipeline, a precondition probe asked whether the notes corpus even has the
cross-document entity structure GraphRAG needs: of **1,623 single-client notes, 0% mention a company, 1.3%
mention another client** — near-zero. The relationships that exist are already structured (settled above);
building here and authoring matching questions would re-run the circular gate, and the one regime GraphRAG
wins (global sensemaking) has no canonical gold. **Deferred to a Phase-4 purpose-built-corpus project** —
neither adopted nor rejected. (This is principle 2.2-5 in action: don't synthesize a ground truth you'd need
reality to know.)

### 3.5 Orchestration & synthesis — router (F) + Customer-360 (D)

**Strategy & validated.** F classifies each query and dispatches to B/A/E/D, or for Q7 decomposes
vector-filter → SQL-filter-over-candidates → synthesize (validated end-to-end). D-lite assembles a
deterministic profile + governed metrics + latest notes into an LLM pre-meeting brief (Q4) — no RAPTOR needed.
**Validated — routing accuracy (the thesis's load-bearing step).** F is now measured directly against a
hand-labeled routing gold (28 questions, all six routes, including Q4/Q7 and deliberate **E↔B boundary**
cases — segment-aggregate → B vs per-client KPI → E). `deepseek-v4-flash` routes **100%** correctly
(fully diagonal confusion matrix); `glm-5.2` routes **96%**, its single miss landing exactly on the hardest
boundary item ("how many clients have AUM over 1M" — a count-aggregate it sent to the metric layer instead
of SQL). So the routed-hybrid's load-bearing step holds, and the one observed failure mode is the predicted E↔B
ambiguity, not a systematic collapse (`docs/experiments/router_eval.md`).
**Boundary.** Multi-tenant RM row-level isolation is open.

### 3.6 Cross-cutting read — how much does LLM capability matter?

Reading the regimes together answers a question the §1 thesis raises: if the binding constraint was not
recall, was it the **LLM's raw capability**? The honest answer is two-sided, and it inverts with how much
the architecture constrains the model: **LLM capability matters precisely where the design fails to
constrain it — and the project's central move is to minimize reliance on it for anything that must be
correct.**

**Where capability *was* the binding constraint (and the source of failure):**
- **Deep query authoring (KG, §3.4) is the clearest case.** The expert oracle clears every fixed-depth
  category (1.0), while the LLM-authored query reaches only **0.51 (SQL) / 0.55 (Cypher)** — the entire gap
  *is* the model, and much of it is dialect familiarity (it has seen far more SQLite than Kùzu-Cypher). A
  stronger model would lift this ceiling directly.
- **Reranking judgment (§3.2):** a 3B model as a relevance judge *net-hurt*, while a purpose-trained
  cross-encoder *net-helped* on the identical pool — the clearest case that the *method/capability* of the
  reranker, not reranking itself, decides the sign.
- **Metric selection (§3.3):** even confined to *picking* a governed formula rather than writing one, the LLM
  mis-routes ~75–80% of out-of-catalog questions — the "pick" step is itself capability-bound.
- **LLM-as-judge** for evaluation is noisy enough that the program deliberately routes around it (canonical
  gold, reverse-generated gold, generator-emitted truth).

**Where capability was *not* the lever (grounding/design carried it):**
- **Text-to-SQL precision (§3.1):** valid-SQL **1.0**, avg attempts **1.0** — self-correction was essentially
  never needed, because the ontology/schema grounding did the work, not raw model intelligence.
- **Semantic recall (§3.2):** recall saturated on `bge-m3` + RRF, independent of the reasoning model.
- **Governed-metric exactness (§3.3):** E is exact *by construction* (the LLM never writes the formula),
  while the more LLM-reliant free SQL (B) drifts ~20% — a direct demonstration that constraining the model
  beats relying on it.

Notably, the reasoning model throughout is a **mid-tier fast cloud model** (`deepseek-v4-flash:cloud`), and
it sufficed for every *validated* regime — itself evidence that raw capability was not the binding constraint
where the architecture did its job. **Implication:** a stronger model helps most in the *unconstrained / open*
regimes (deep-query authoring, reranking, metric selection) — but the recommended path is to *shrink* those
regimes, not to bet on a better model. **Caveat, now partly tested.** These conclusions sit on synthetic,
self-authored, often tractable data; on harder real data (messier notes, larger schemas, genuinely hard
text-to-SQL) the balance shifts back toward model capability — so "capability is not binding" is partly a
property of the data's difficulty, not a universal law. Two **data-knob sensitivity sweeps** now put numbers
on the most confound-exposed negatives rather than leaving this as a hedge: the rerank verdict survives
varying distractor density (§3.2), and the KG oracle verdict survives graph scale but shows its first crack
at the largest graph (§3.4) — i.e. the substrate is harder to fool than a single run suggests, but it is not
infinitely robust, and that boundary is exactly where difficulty starts to bind. Distributional fidelity of
the synthetic data against published real stylized facts remains the one substrate check not yet run (§2.2).

---

## 4. Completeness audit — covered vs industry-common (and the deliberate gaps)

Technical completeness means covering the design space *and* bounding it honestly (`docs/experiments/coverage_map.md`):

| Industry-common technique | Status here |
|---|---|
| Dense vector RAG · hybrid (dense+sparse, RRF) | ✅ pillar A |
| Text-to-SQL / NL2SQL | ✅ pillar B |
| Semantic / metrics layer (dbt SL, Cube, LookML) | ✅ E — value (3a) + storage comparison (3b) |
| Agentic router / query decomposition · multi-source synthesis | ✅ F, D |
| Graph traversal / multi-hop | ✅ justified only for path-finding |
| **Reranking** (cross-encoder / late-interaction) | ✅ LLM reranker (net-hurts) **and** trained cross-encoder (net-helps, robust to density); late-interaction untested |
| **GraphRAG over unstructured text** | ⏸️ **deferred** — corpus precondition absent (needs Phase-4 corpus) |
| Embedding-model / vector-DB / chunking bake-offs | ⛔ out of scope (engineering selection, not a design question) |
| Long-context baseline / fine-tune vs RAG | ⛔ out of scope |
| Evaluation rigor | ✅✅ exceeds the industry norm — the program's distinguishing feature |

Production axes (point-in-time/SCD, multi-tenant isolation, latency/cost, incremental refresh, observability)
are acknowledged out of scope.

---

## 5. Bottom line

| Question | Verdict | Confidence |
|---|---|---|
| Which strategy per archetype? | Routed hybrid (B+A+E+D+F); no single index wins | High direction; Phase-1 numbers are single-run on synthetic self-authored data |
| Is a knowledge graph worth adding? | Only for variable-length **path-finding**; fixed-depth = recursive SQL — robust across graph scale, with SQL's first non-path crack at the largest graph | High *within scope*; oracle verdict survives a 3-scale sensitivity sweep |
| Does the semantic layer earn its keep? | **Yes, conditional on** catalog-gated abstention + a query mix where out-of-catalog is rare (~20% drift eliminated, composite KPIs); the ~75–80% mis-route cost flips the sign without abstention | High on magnitude; the binary verdict is noise-dominated |
| Where should the semantic layer live? | A declarative (dbt-style) metrics layer is worth adopting; RDF stays | High (equivalence independently re-verified) |
| Does a reranker help? | The **method** decides the sign: a small LLM reranker **net-hurts**, the trained cross-encoder **net-helps** (MRR 0.62→0.74, robust to distractor density) | High for both arms; late-interaction open |
| GraphRAG over unstructured? | **Deferred** — precondition absent on this corpus | Triaged out before building |

**The program's real product** is the discipline that makes the *negative* results (KG only for
path-finding, a weak reranker net-hurts, GraphRAG deferred) trustworthy — and, just as important, that
catches when a negative is an artifact: a fairer comparison (the trained cross-encoder) **flipped** the
reranker verdict, and data-knob sensitivity sweeps turned the "the substrate might be too easy" hedge into
measured robustness with a located breaking point. The recurring lessons: circular self-evaluation is the
enemy; separate capability from LLM-authoring skill; pre-register the verdict and report the distribution
when it straddles; a pass/fail metric can hide a worse mode; vary the data knob, not just the seed; spike
the crux and smoke external integrations during planning; relabel everywhere when a pivot changes what you
measured; and the best outcome of a feasibility check can be "don't build it."

**Open / Phase-4.** A purpose-built corpus for a fair GraphRAG test; catalog-gated abstention for E
(the precondition of its positive verdict); late-interaction (ColBERT-style) reranking; point-in-time/SCD;
multi-tenant isolation; and the one remaining substrate check — distributional fidelity of the synthetic
data against published real stylized facts (§2.2; the multi-dataset-sensitivity check is now done, §3.2/§3.4).

---

## Appendix A — Evaluation scoreboards

**B — text-to-SQL** (72-query gold set; `exec_acc` = exact result-set match, `value_recall` = lenient key-value overlap)

| Set | n | exec_acc | value_recall | valid_sql | attempts | faithful | correct | latency_s |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| ALL | 32 | 0.719 | 0.858 | 1.0 | 1.0 | 0.969 | 0.812 | 26.5 |
| Q1 | 12 | 0.917 | **1.00** | 1.0 | 1.0 | 1.0 | 1.0 | 22.3 |
| Q2 | 8 | 0.625 | 0.75 | 1.0 | 1.0 | 1.0 | 0.75 | 32.9 |
| Q5 | 6 | 0.50 | 0.911 | 1.0 | 1.0 | 0.833 | 0.667 | 28.5 |
| Q6 | 6 | 0.667 | 0.667 | 1.0 | 1.0 | 1.0 | 0.667 | 24.6 |

**A — hybrid vector**

| Set | n | recall@5 | MRR | faithful | correct | latency_s |
|---|--:|--:|--:|--:|--:|--:|
| ALL | 40 | **0.975** | 0.926 | 0.993 | 0.96 | 16.7 |
| Q3 | 24 | 0.958 | 0.897 | 1.0 | 0.938 | 16.6 |
| Q8 | 16 | **1.00** | 0.969 | 0.981 | 0.994 | 16.8 |

**C — KG traversal (oracle ceiling, accuracy by hop-depth)**

| engine | depth 1 | depth 2 | depth 3+ | by-category gap |
|---|--:|--:|--:|---|
| SQL (recursive CTE) | 1.0 | 1.0 | 0.58 | fails only `shortest_path` (0.0) |
| Cypher (KùzuDB) | 1.0 | 1.0 | 1.0 | all categories 1.0 |

LLM-authored: SQL 0.51 / Cypher 0.55 overall — far below both ceilings (the dialect-authoring tax).
**Scale sensitivity (oracle):** SQL `shortest_path` 0.0 and Cypher 1.0 at all three scales (806/1,215/1,953
nodes); SQL other-category accuracy 1.0/1.0/**0.90** — first crack at the largest graph.

**F — routing accuracy** (28-question hand-labeled gold; all six routes incl. Q4/Q7 + E↔B boundary)

| classifier | accuracy | misroutes |
|---|--:|---|
| `deepseek-v4-flash:cloud` | **100%** | none (diagonal) |
| `glm-5.2:cloud` | **96%** | 1 — count-aggregate "clients with AUM>1M" → metric instead of sql (the E↔B boundary) |

**E / reranking / storage** — 3a (5-run stability pass): B drift 0.20±0.009 (range 0.185–0.214) vs E 0.0, E mis-routes ~75–80% of probes (range 0.65–0.90) · 3d (RRF pool recall 0.86; same pool both arms): LLM reranker MRR 0.62→0.51, recall@1 0.47→0.39, +8.4s/q (**net-hurts**); cross-encoder `bge-reranker-v2-m3` MRR 0.62→0.74, recall@1 0.47→0.69, +2.45s/q (**net-helps**; actionable recall@1 0.0→0.71); density sweep (min-notes 3/5/7) `justified` at all three · 3b: dbt-style → migrate (1/2 native, 1.26×,
generates), RDF → keep (0/2 native, 1.12×, locked).

## Appendix B — Data foundations

**Phase-1 warehouse** (`data/rm.db`, deterministic, seed 42): clients 5,369 · accounts 4,500 · holdings
~8,800 · transactions ~1.06M · loans 682 · documents 1,639 (incl. 16 KB) · edges ~7,900. 256 clients with
AUM > $1M. Segments AUM-derived (Mass Affluent <100k → UHNW ≥5M). 🟦 Berka (CTU public MariaDB) · 🟨 seeded
synthesis + LLM corpus (grounded, provenance-tagged). As-of date **1998-12-31**; USD, no FX.

**Phase-2 wealth graph** (`data/wealth_graph/`, seeded): 1,215 nodes / 2,897 edges (natural persons,
households, legal entities {opco/holdco/spv/foundation}, trusts, accounts, RMs). One NetworkX canonical →
SQLite relational projection + JSONL/GraphML export + `graph_truth.json`. Grounded in FIBO/BODS/ICIJ/FATF;
control-based UBO, clean ownership trees (~1–2 UBOs/entity).

**Phase-3 derived sets:** 3a paraphrase set (templated, canonical gold from `ontology.metric_sql`); 3d
rerank hard set (`eval/gold/rerank_hard.json`, reverse-generated from multi-note clients); 3b ports
(`rm_assistant/semrepr/specs/metrics.dbt.yml`, `rm_assistant/semrepr/specs/metrics.ttl`).

## Appendix C — Reproducibility

```bash
uv sync
uv run scripts/build/load_berka.py && uv run scripts/build/build_unified.py \
  && uv run scripts/build/synth_corpus.py && uv run scripts/build/build_fts.py   # Phase-1 warehouse + corpus
uv run scripts/build/build_wealth_graph.py                                # Phase-2 graph layer
uv run scripts/eval/run_eval.py                                          # B/A scoreboard
uv run scripts/eval/run_router_eval.py                                   # F routing accuracy (glm-5.2 + deepseek)
uv run scripts/eval/run_kg_experiment.py                                 # KG traversal (long)
uv run scripts/eval/sweep_kg.py                                          # KG oracle sensitivity across scale
uv run scripts/eval/run_semantic_eval.py && uv run scripts/eval/run_semx_stability.py   # 3a
uv run scripts/eval/run_semrepr_eval.py                                  # 3b (network-free)
uv run scripts/eval/probe_corpus_entity_structure.py                     # 3c precondition probe
uv sync --extra rerank                                                   # cross-encoder stack (torch + FlagEmbedding)
uv run scripts/eval/run_rerank_eval.py                                   # 3d (LLM + cross-encoder arms)
uv run scripts/eval/sweep_rerank.py                                      # 3d distractor-density sensitivity
uv sync                                                                  # drop the rerank extra again (see caveat)
uv run pytest -q                                                         # full suite
```

Structured builds are deterministic (seed in `config.SEED`); the LLM corpus is stochastic (generated once,
cached). Routing, KG, 3a, and 3d make real LLM calls; the KG/rerank sweeps and 3b/3c are network-free or
near it. **Reproducibility caveat — keep the cross-encoder and KG stacks separate:** the `rerank` extra
(torch + FlagEmbedding) and the embedded KùzuDB used by the KG experiment cannot share one Python
environment — under load the KG run crashes natively (SIGBUS/SIGSEGV) — so install the extra only for the
rerank steps and `uv sync` it away before running KG. The KG sensitivity sweep is **oracle-only** (model-free)
precisely so it is crash-free; LLM-authored KG numbers come from the single `run_kg_experiment.py` run.
