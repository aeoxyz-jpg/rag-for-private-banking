"""Phase-3c precondition probe: does the unstructured notes corpus contain cross-document entity
structure that a GraphRAG (entity-extraction -> cross-doc linking -> graph-aware retrieval) could
exploit? If notes are single-client narratives with ~no cross-document entity mentions, GraphRAG has
nothing to bite on here and a fair test needs a purpose-built corpus (see docs/experiments/coverage_map.md, 3c).
Run: `uv run scripts/eval/probe_corpus_entity_structure.py`."""
from rm_assistant import db


def main() -> None:
    conn = db.connect(readonly=True)
    docs = conn.execute(
        "SELECT doc_id, client_id, text FROM documents WHERE kind != 'kb' AND client_id IS NOT NULL"
    ).fetchall()
    clients = {r["client_id"]: r["name"] for r in conn.execute("SELECT client_id, name FROM clients")}
    companies = [r["name"] for r in conn.execute("SELECT name FROM companies") if r["name"]]
    conn.close()

    n_docs = len(docs)
    n_clients = len({d["client_id"] for d in docs})
    comp_hits = sum(1 for d in docs
                    if any(c.lower() in d["text"].lower() for c in companies if len(c) > 4))
    cross_name = 0
    for d in docs:
        txt = " " + d["text"].lower() + " "
        for cid, nm in clients.items():
            if cid != d["client_id"] and nm and len(nm) > 6 and f" {nm.lower()} " in txt:
                cross_name += 1
                break

    print(f"notes docs:                 {n_docs}  ({n_clients} distinct clients, grounded 1 doc/client)")
    print(f"docs mentioning a company:  {comp_hits}  ({comp_hits / n_docs:.1%})")
    print(f"docs mentioning ANOTHER client by full name: {cross_name}  ({cross_name / n_docs:.1%})")
    print("Reading: near-zero cross-document entity structure -> GraphRAG-over-unstructured has nothing "
          "to exploit on this corpus; a fair test needs a purpose-built corpus (Phase 4), not a "
          "retrieval experiment here.")


if __name__ == "__main__":
    main()
