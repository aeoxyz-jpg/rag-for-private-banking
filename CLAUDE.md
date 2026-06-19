# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A prototype **wealth / private-banking Relationship-Manager (RM) Copilot** that compares RAG
retrieval strategies on a synthetic "virtual private bank" and converges on a recommended
hybrid architecture. `docs/RM_Assistant_RAG_spec.md` is the original spec; **all milestones M0–M6
are built**. Read `docs/TECHNICAL_REPORT.md` for the full write-up and `README.md` for commands.

## Build pipeline (data is gitignored — rebuild from these)

```
load_berka.py    → data/berka_raw.db   raw Berka, pulled from CTU public MariaDB (no Kaggle)
build_unified.py → data/rm.db          unified warehouse (§3.3), deterministic + seeded
synth_corpus.py  → documents + Chroma  LLM-synthesized notes (grounded, provenance-tagged)
build_fts.py     → documents_fts       BM25 lexical index
gen_vector_gold.py → eval/gold/vector.json   (one-time; committed)
```

`uv sync` then run the above in order. Tests: `uv run pytest -q` (network-free; skip cleanly
if the warehouse/Ollama aren't present).

## Architecture (the routed hybrid)

Top-level entry is the **router** (`retrieval/router.py`, pillar F): it classifies a query and
dispatches to one of:
- **B `sql_pillar.py`** — text-to-SQL over the warehouse (Q1/Q2; and Q5 multi-hop via the
  `edges` table). Grounded in `ontology.yaml`, read-only guardrails, self-correction.
- **A `vector_pillar.py`** — hybrid retrieval: dense (Chroma/bge-m3) + BM25 (FTS5) fused by RRF
  (Q3 notes; Q8 with `kind='kb'`).
- **E `semantic.py`** — serves *governed* metrics from `ontology.yaml` (Q6). The LLM picks the
  metric + filter; it never writes the formula. Boundary: E is for per-client / threshold /
  ranking KPIs; **segment- or attribute-aggregates go to B** (which joins `clients`).
- **D `c360.py`** — Customer-360 pre-meeting brief (Q4): deterministic profile + governed
  metrics + latest notes → LLM narrative.
- **Q7 hybrid** — router decomposes into vector-filter → SQL-filter (over the candidates) → synthesize.

`ontology.yaml` is the shared backbone (glossary + governed metric SQL + entity dictionary);
`ontology.py` renders it into prompts. The model layer (`models/`) is provider-agnostic:
`bge-m3` embeddings (local Ollama), `deepseek-v4-flash:cloud` reasoning, Codex optional —
selected by role in `config.py` / `.env`.

## Conventions that matter here

- **AUM and any per-client aggregate of holdings must pre-aggregate holdings per account before
  joining** — `accounts LEFT JOIN holdings` fans out and double-counts `balance` once per
  holding. The governed `aum` metric, the text-to-SQL few-shot, and the gold SQL all use the
  correct `LEFT JOIN (SELECT account_id, SUM(market_value) ... GROUP BY account_id)` form.
  This bug inflated "clients > $1M" from 256 to 514; don't reintroduce it.
- **Metric consistency is the point of E** — if you add a KPI, define it once in `ontology.yaml`
  and let B/E/c360 read it; never hard-code a second copy of a formula.
- **As-of date is 1998-12-31** (Berka corpus end) — used for recency/"today". Currency is
  labelled USD with no FX; the synthetic `holdings` layer supplies the HNW/UHNW tail.
- **Structured build is deterministic** (seed in `config.SEED`); the **LLM corpus is stochastic**
  (generated once, cached). Don't expect bit-reproducibility of notes.
- **Eval honesty:** strict `exec_match` is noisy (extra columns, small n); `value_recall` is the
  steadier signal — the scoreboard reports both. Gold SQL is hand-authored and verified; don't
  let an LLM write gold reference SQL.

## Knowledge graph (pillar C) is UNTESTED, not rejected

`edges` (household/employer/advisor) is projected into SQLite and text-to-SQL handled the Q5
queries we posed (value-recall 0.91) — but the Phase-1 relationship data is shallow by
construction (households are pairs, one employer per client, no referral chains) and the queries
were authored to match, so the M5 gate is **circular** (see `docs/TECHNICAL_REPORT.md` §6). Do
not cite "KG not needed" as a result. A fair test (deep relationship data + independent 3+ hop
queries, text-to-SQL vs NetworkX/Cypher) is the headline Phase-2 task (§10). Don't add a KG
speculatively either — build it as part of that experiment.

Phase-2 builds a deep, relationship-rich dataset for the fair KG test: `rm_assistant/wealthgraph/`
(canonical `networkx` graph → SQLite + JSONL/GraphML + `graph_truth.json`), via
`scripts/build/build_wealth_graph.py`. It is greenfield and independent of the Phase-1 Berka warehouse.
Two invariants keep UBO realistic (~1-2 owners/entity, not dozens): the builder must produce
**clean ownership trees** (holdco/opco pools are CONSUMED, each entity gets one majority parent —
do not reuse a holdco across many chains), and `ubo.derive_ubo` is **control-based** (control
propagates only through majority >50% links, not summed over every minority path).
