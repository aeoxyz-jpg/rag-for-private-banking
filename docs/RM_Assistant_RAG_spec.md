# Spec — RM Assistant (Wealth / Private-Banking RM Copilot) Prototype

> **Historical — the original Phase-0 design spec, kept for reference.** What was actually built and
> measured (and where it diverged from this spec) is in `docs/TECHNICAL_REPORT.md`.

> **Status:** Draft v1 · **Owner:** TBD · **Date:** 2026-06-15
> **Scope:** Private / wealth-management Relationship-Manager Copilot.
> **Language:** English-primary data & queries.
> **Deployment:** Unconstrained — this spec optimizes for *architecture comparison*, not a fixed stack.
> **Deliverable:** (1) a RAG design-decision framework with a recommendation, **and** (2) a runnable prototype with an evaluation baseline.

---

## 0. Why this spec exists

A wealth-RM Copilot has to answer questions that fall into **fundamentally different retrieval regimes** — precise aggregations over account data, fuzzy recall over meeting notes, multi-hop relationship reasoning, and "tell me everything about this client" summaries. The central design question is *not* "vector DB **or** text-to-SQL **or** knowledge graph" — it is **which query archetypes exist, and which retrieval strategy each one demands.** This spec makes that mapping explicit, then prescribes an incremental build that proves it.

**Two work streams, run in order:**
1. **Data foundation** — assemble a realistic "virtual private bank" spanning structured + unstructured + semantic-metadata layers.
2. **RAG architecture exploration** — implement candidate retrieval strategies against the same data + query set, measure, and converge on a recommended hybrid.

---

## 1. Goals & non-goals

### Goals
- Stand up a **reusable synthetic data底座** that mirrors what a real RM Copilot consumes (clients, accounts, holdings, transactions, interactions, meeting notes, leads).
- Build and **compare** the major RAG retrieval strategies on an apples-to-apples query set.
- Produce a **decision matrix** (query archetype → retrieval strategy) and a **recommended architecture** backed by eval numbers.
- Ship a **runnable prototype** (CLI or thin API) that answers the RM query set end-to-end.

### Non-goals
- Not production-hardening (no auth, multi-tenancy, real PII, or compliance gates).
- Not fine-tuning a domain LLM — use off-the-shelf models behind an abstraction.
- Not building a UI beyond a minimal demo surface.
- Not real-time streaming ingestion — batch-built corpus is fine.

---

## 2. Personas & query taxonomy (the design driver)

The RM Copilot serves a **relationship manager** preparing for and following up on client interactions. Enumerate the query archetypes first — **the architecture falls out of this table.**

| # | Query archetype | Example | Data regime | Natural retrieval strategy |
|---|---|---|---|---|
| Q1 | **Precise filter / aggregation** | "Which of my clients have AUM > $1M and no contact in 90 days?" | Structured | **Text-to-SQL** (vector search *cannot* do exact aggregation/joins) |
| Q2 | **Single-entity fact lookup** | "What's the current balance and last transaction for client #4521?" | Structured | Text-to-SQL / direct query |
| Q3 | **Fuzzy semantic recall** | "What did this client say about retirement concerns?" | Unstructured (notes, transcripts) | **Vector / hybrid search** |
| Q4 | **Cross-document synthesis** | "Summarize everything we know about client #4521 before the meeting." | Mixed | **Knowledge tree / precomputed Customer-360 doc** + retrieval |
| Q5 | **Multi-hop relationship** | "Which of my clients are in the same household or linked to Company X?" | Graph-shaped | **Knowledge graph** |
| Q6 | **Metric / KPI consistency** | "Show share-of-wallet and churn-risk for my book." | Structured + derived | **Semantic layer** (governed metric definitions over SQL) |
| Q7 | **Hybrid reasoning** | "Among clients who mentioned liquidity needs, who has a maturing deposit next month?" | Unstructured filter → structured filter | **Router / agent** chaining Q3 + Q1 |
| Q8 | **Policy / product Q&A** | "What's the eligibility for our structured-note product?" | Unstructured (knowledge base) | Vector / hybrid search (classic RAG) |

**Takeaway baked into the spec:** Q1/Q2/Q6 are *structured* and are exactly where naive vector RAG fails (it retrieves "similar text," not *correct aggregates*). Q3/Q8 are where vector RAG shines. Q5 needs graph traversal. Q7 needs orchestration. **No single index wins → the answer is a routed hybrid.** Phase 2 must *prove* this, not assume it.

---

## 3. Phase 1 — Data foundation

### 3.1 Layered data model

| Layer | Content | Backing store | Purpose |
|---|---|---|---|
| **Structured core** | clients, accounts, dispositions, transactions, loans, cards, holdings/portfolio, leads | Relational DB (Postgres or SQLite) | Q1, Q2, Q6, joins |
| **Unstructured corpus** | meeting notes, call/Zoom transcripts, pre-meeting briefs, complaint records, product/policy KB | Document store + vector index | Q3, Q4, Q8 |
| **Relationship layer** | household links, client↔company, RM↔client, referral edges | Graph (or edge table projected to graph) | Q5 |
| **Semantic metadata** | ontology / glossary, column descriptions, metric definitions, entity dictionary | YAML / semantic-layer config | Reliable text-to-SQL, governed metrics, KG schema |

### 3.2 Source datasets (assemble, don't build from scratch)

**Structured backbone — recommended primary:**
- **Berka / PKDD'99 Czech bank** — 8 relational tables (client, account, disposition, transaction ~1M, loan, card, order, district), ~5,300 clients. The single best ready-made *relational* banking dataset. → https://www.kaggle.com/datasets/marceloventura/the-berka-dataset
- **Bank Customer Churn** — adds churn labels + product counts for Q6/NBA targets. → https://www.kaggle.com/datasets/radheshyamkollipara/bank-customer-churn
- **Bank Marketing (UCI)** — term-deposit campaign responses → lead-scoring / NBA labels. → https://hf.co/datasets/Andyrasika/banking-marketing

**Transaction depth / volume (optional, if Berka volume is insufficient):**
- **PaySim** (6M mobile-money txns) → https://www.kaggle.com/datasets/ealaxi/paysim1
- **IBM TabFormer** (24M card txns, time-series) → https://github.com/IBM/TabFormer
- **Sparkov generator** (parametric txn generator, Faker-based) → https://github.com/namebrandon/Sparkov_Data_Generation

**Interaction / intent / sentiment:**
- **PolyAI/banking77** — 13,083 queries × 77 intents → https://hf.co/datasets/PolyAI/banking77
- **bitext retail-banking chatbot** — synthetic banking dialogue → https://hf.co/datasets/bitext/Bitext-retail-banking-llm-chatbot-training-dataset
- **talkmap conversation corpus** — 300k synthetic multi-turn service convos → https://hf.co/datasets/talkmap/banking-conversation-corpus

**Meeting notes / advisor transcripts — ⚠️ the real gap (privacy-bound, almost no open data):**
- Closest references: **Fin-Vault** (~1,417 advisory convos, arXiv 2509.24342), **Fin-APT** (470 advisor videos + Whisper transcripts, arXiv 2509.20961).
- **Decision:** *synthesize* this layer with an LLM (see 3.4). This is the highest-value synthetic component because it's what the Copilot's pre-brief / minutes features actually operate on.

### 3.3 Target unified schema (the "virtual private bank")

Define an explicit entity model (this doubles as the **ontology** in 3.5). Minimum entities:

```
RelationshipManager(rm_id, name, book_segment)
Client(client_id, rm_id, name, segment, risk_profile, kyc_status, household_id, since)
Account(account_id, client_id, type, currency, balance, opened_at)
Holding(holding_id, account_id, instrument, asset_class, market_value, qty)
Transaction(txn_id, account_id, ts, amount, type, counterparty, channel)
Loan(loan_id, client_id, principal, rate, status, maturity)
Lead(lead_id, client_id, product, score, status, created_at)
Interaction(interaction_id, client_id, rm_id, ts, channel, type, sentiment, summary_ref)
Document(doc_id, client_id, kind{note|transcript|brief|complaint|kb}, ts, text, embedding_ref)
Edge(src_id, dst_id, rel_type{household|employer|referral|advisor})  # graph projection
```

Map each source dataset's columns onto this schema in an ETL step; fill gaps with synthesis.

### 3.4 Synthetic generation plan
- **Relational fill / scale-up:** use **SDV** (multi-table, preserves cross-table relationships) to extend Berka while keeping referential integrity, or **Faker/Sparkov** for greenfield rows. → https://sdv.dev/
- **Unstructured generation (LLM):** for each client, generate (a) 3–8 dated meeting notes / call transcripts grounded in that client's *actual* structured facts (holdings, recent txns, life-stage), (b) a pre-meeting brief, (c) some complaints/sentiment. Ground the prompt on the row data so notes are *consistent* with the warehouse (critical for Q7 hybrid queries and for honest eval).
- **Provenance:** tag every synthetic doc with the structured facts it was conditioned on → enables gold-answer construction for eval.

### 3.5 Semantic metadata / ontology
- **Glossary + column descriptions** (YAML): human-readable meaning of every table/column → fed into the text-to-SQL prompt and used as KG schema.
- **Metric definitions** (semantic layer): `AUM`, `share_of_wallet`, `churn_risk`, `days_since_contact`, `net_new_money` — defined *once* as SQL/templates so every path returns identical numbers.
- **Entity dictionary**: canonical names/synonyms (e.g., "book" = an RM's client set) to disambiguate NL queries.

### 3.6 Phase-1 deliverables
- [ ] ETL scripts: source datasets → unified relational DB.
- [ ] LLM synthesis pipeline for the unstructured layer (grounded on structured rows).
- [ ] Edge/graph projection table.
- [ ] `ontology.yaml` (glossary + metrics + entity dictionary).
- [ ] A **seeded, reproducible** build (fixed RNG seed) + a data dictionary doc.

---

## 4. Phase 2 — RAG architecture exploration (the core)

Implement each candidate against the *same* data and the *same* query set (Section 5), measure, then converge.

### 4.1 Candidate strategies

**A. Vector DB — semantic / hybrid search**
- *What:* embed the unstructured corpus; retrieve by dense similarity, optionally fused with BM25 (hybrid) + reranker.
- *Best for:* Q3, Q8 (fuzzy recall, policy Q&A).
- *Fails at:* Q1/Q2/Q6 — cannot aggregate, filter precisely, or join. Returns plausible text, not correct numbers.
- *Build:* Chroma / LanceDB / pgvector + an English embedding model (e.g., `bge`/`gte` class) + hybrid (BM25 + dense) + cross-encoder rerank.

**B. Relational DB + Text-to-SQL**
- *What:* LLM translates NL → SQL over the schema; DB executes; results summarized.
- *Best for:* Q1, Q2 — exact filters, aggregations, joins, "as of" dates.
- *Fails at:* Q3/Q8 (no semantics over free text), brittle on ambiguous schema → **this is why the ontology/glossary (3.5) matters**.
- *Build:* schema + glossary in prompt; guardrails (read-only, row limits, query validation); self-correction on SQL errors; few-shot exemplars.

**C. Knowledge Graph / ontology**
- *What:* nodes = entities, edges = relationships; answer via traversal / graph queries (Cypher) or GraphRAG-style retrieval.
- *Best for:* Q5 (multi-hop: households, employer links, referral chains).
- *Cost:* highest build/maintenance; only pays off if multi-hop relationship queries are genuinely frequent.
- *Build:* project `Edge` + entities into Neo4j / NetworkX; optionally LLM-extract relationships from notes to enrich edges.

**D. Knowledge tree (hierarchical summarization, RAPTOR-style)**
- *What:* cluster + recursively summarize a client's documents into a tree; retrieve at the right abstraction level.
- *Best for:* Q4 ("summarize everything about this client"), long-context pre-briefs.
- *Alternative/cheaper:* a **precomputed Customer-360 document** per client (deterministic template filled from structured + latest notes) — often beats a tree for this specific use case.

**E. Semantic layer (metrics layer over SQL)**
- *What:* governed metric definitions (dbt-metrics / Cube-style); NL → metric selection → templated SQL.
- *Best for:* Q6 — consistent KPIs across every question and surface. Removes the "LLM invented a different AUM formula" failure mode.
- *Relation to B:* sits *above* text-to-SQL; constrains it to vetted metrics for the numbers that must be exact.

**F. Router / agent (orchestration)**
- *What:* a classifier/agent routes each query to A–E (or decomposes Q7 into a pipeline: vector-filter → SQL-filter → synthesize).
- *Best for:* Q7 and as the **top-level architecture** that makes A–E coexist.
- *Build:* intent/route classifier (LLM or small model) + tool-calling agent with the above as tools.

### 4.2 Decision matrix (hypothesis to validate)

| Query archetype | A Vector | B Text-SQL | C Graph | D Tree/360 | E Semantic | F Router |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Q1 filter/agg | ✗ | ✅ | ○ | ✗ | ✅ | via B/E |
| Q2 entity fact | ○ | ✅ | ○ | ○ | ○ | via B |
| Q3 fuzzy recall | ✅ | ✗ | ○ | ○ | ✗ | via A |
| Q4 synthesis | ○ | ○ | ○ | ✅ | ○ | via D |
| Q5 multi-hop | ✗ | ○ | ✅ | ✗ | ✗ | via C |
| Q6 metrics | ✗ | ○ | ✗ | ✗ | ✅ | via E |
| Q7 hybrid | ✗ | ✗ | ○ | ○ | ○ | ✅ |
| Q8 policy Q&A | ✅ | ✗ | ✗ | ○ | ✗ | via A |

✅ strong · ○ partial · ✗ wrong tool

### 4.3 Recommended architecture (to validate, not assume)

> **A router/agent (F) over two pillars — hybrid vector search (A) and text-to-SQL (B) — with a thin semantic layer (E) governing exact metrics, a precomputed Customer-360 doc (D-lite) for pre-briefs, and a knowledge graph (C) added only if Q5-type queries prove frequent. The ontology/glossary (3.5) is the shared backbone that makes B, C, and E reliable.**

Rationale: structured-precision questions (Q1/Q2/Q6) dominate an RM's day and are exactly where vector-only RAG silently returns wrong numbers; semantic recall (Q3/Q8) genuinely needs embeddings; everything else is composition. KG and full RAPTOR trees are *additive* — justify them with the eval, don't pay their cost upfront.

### 4.4 Build order (de-risk cheaply first)
1. **B (text-to-SQL) + ontology** → covers the highest-frequency, highest-value queries; cheapest to stand up.
2. **A (hybrid vector)** over the synthetic notes → covers recall/Q&A.
3. **F (router)** to dispatch between A and B + handle Q7 decomposition.
4. **E (semantic layer)** for metric consistency.
5. **D-lite Customer-360 doc** for pre-briefs (template first; only escalate to a RAPTOR tree if it underperforms).
6. **C (knowledge graph)** *only if* Q5 eval shows A/B can't cover multi-hop.

---

## 5. Evaluation harness (makes the comparison honest)

### 5.1 Query test set
- ~60–100 NL questions spanning Q1–Q8, each with a **gold answer** (and gold SQL where applicable). Gold answers are constructable because synthetic notes are provenance-tagged (3.4).
- Include adversarial cases: ambiguous entities, "as of last quarter", empty-result, multi-hop.

### 5.2 Metrics
- **Retrieval:** recall@k, MRR, nDCG (for A/C/D).
- **Text-to-SQL:** execution accuracy (result-set match), valid-SQL rate, self-correction count (for B/E).
- **Answer quality:** faithfulness / groundedness, answer-correctness, citation accuracy (RAGAS-style or LLM-judge).
- **Routing:** route-classification accuracy (for F).
- **Ops:** latency, token cost, build cost per strategy.

### 5.3 Tooling
- RAGAS / TruLens / DeepEval for answer-level metrics; custom harness for SQL exec-accuracy; LLM-as-judge with a fixed rubric for synthesis quality. Log every run to a comparable scoreboard.

---

## 6. Architecture (textual)

```
                ┌──────────────────────────────────────────────┐
   NL query ──▶ │  Router / Agent (F)                          │
                │   route + (optional) decompose                │
                └───┬───────────┬───────────┬───────────┬──────┘
                    │           │           │           │
              ┌─────▼────┐ ┌────▼─────┐ ┌───▼────┐ ┌────▼─────┐
              │ Text-SQL │ │ Hybrid   │ │ KG (C) │ │ 360 doc  │
              │  (B)     │ │ vector(A)│ │ traverse│ │ (D-lite) │
              └────┬─────┘ └────┬─────┘ └───┬────┘ └────┬─────┘
                   │            │           │           │
          ┌────────▼───┐  ┌─────▼─────┐  ┌──▼───┐  ┌────▼─────┐
          │ Semantic   │  │ Vector idx │  │ Graph│  │ Doc store│
          │ layer (E)  │  │ + reranker │  │ store│  │          │
          └────┬───────┘  └───────────┘  └──────┘  └──────────┘
               │
          ┌────▼─────────┐
          │ Relational DB │◀── ontology.yaml (glossary · metrics · entities)
          └──────────────┘
                   ▲
                   └── Phase-1 ETL + LLM synthesis (provenance-tagged)
```

---

## 7. Milestones

| Phase | Output | Exit criterion |
|---|---|---|
| **M0** Scaffolding | repo, env, model abstraction, DB up | Berka loaded; one trivial SQL + one vector query run |
| **M1** Data foundation | unified DB + synthetic unstructured corpus + ontology.yaml | reproducible seeded build; data dictionary written |
| **M2** Pillars | B (text-to-SQL) + A (hybrid vector) working | both pass smoke tests on the query set |
| **M3** Eval harness | query set + gold answers + scoreboard | baseline numbers for A and B |
| **M4** Composition | F router + E semantic layer + D-lite 360 | Q7 end-to-end; metric consistency verified |
| **M5** (conditional) | C knowledge graph | only if M3 shows Q5 gap |
| **M6** Synthesis | decision report + recommended arch + prototype demo | scoreboard-backed recommendation; demo answers Q1–Q8 |

---

## 8. Tech-stack options (deployment-agnostic; pick at M0)

| Component | Lightweight / local | Managed / cloud |
|---|---|---|
| LLM | Ollama (local) | hosted API (Claude/GPT class) |
| Embeddings | `bge`/`gte` local | hosted embedding API |
| Relational DB | SQLite / Postgres | managed Postgres |
| Vector index | Chroma / LanceDB / pgvector | Pinecone / Weaviate |
| Graph | NetworkX / SQLite edges | Neo4j |
| Semantic layer | dbt-metrics / hand-rolled templates | Cube |
| Eval | RAGAS / DeepEval + custom | same |

Abstract the LLM + embedding + vector-store behind interfaces so the comparison isn't locked to one vendor.

---

## 9. Risks & open questions

- **Synthetic-note realism** — if generated notes are too templated, Q3/Q7 eval is unrealistic. Mitigate: ground on real row data, vary persona/voice, sample real phrasing from banking77/bitext.
- **Text-to-SQL brittleness** — schema ambiguity tanks accuracy. Mitigate: invest in ontology/glossary early; few-shot; self-correction.
- **Metric drift** — without the semantic layer, every path computes KPIs differently. Decide early which numbers *must* be governed.
- **KG ROI** — easy to over-invest. Gate it behind eval evidence.
- **Eval gold-answer cost** — provenance tagging in synthesis is what makes this affordable; don't skip it.
- **Open:** Does the RM book need temporal/"as-of" queries (point-in-time balances)? If yes, model slowly-changing dimensions in Phase 1.
- **Open:** Multi-tenant RM isolation (each RM sees only their book) — out of scope for prototype, but note where row-level filters would go.

---

## 10. References (datasets & tools)
- Berka PKDD'99 — https://www.kaggle.com/datasets/marceloventura/the-berka-dataset
- Bank Customer Churn — https://www.kaggle.com/datasets/radheshyamkollipara/bank-customer-churn
- Bank Marketing — https://hf.co/datasets/Andyrasika/banking-marketing
- PaySim — https://www.kaggle.com/datasets/ealaxi/paysim1 · IBM TabFormer — https://github.com/IBM/TabFormer · Sparkov — https://github.com/namebrandon/Sparkov_Data_Generation
- banking77 — https://hf.co/datasets/PolyAI/banking77 · bitext — https://hf.co/datasets/bitext/Bitext-retail-banking-llm-chatbot-training-dataset · talkmap — https://hf.co/datasets/talkmap/banking-conversation-corpus
- SDV — https://sdv.dev/ · Evidently synthetic data — https://www.evidentlyai.com/blog/synthetic-data-generator-python
- Advisor-convo references — Fin-Vault (arXiv 2509.24342), Fin-APT (arXiv 2509.20961)
- RAPTOR (knowledge tree) — arXiv 2401.18059 · GraphRAG — Microsoft GraphRAG
