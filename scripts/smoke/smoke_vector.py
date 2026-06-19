"""M0 smoke: embed a few docs with bge-m3, store in Chroma, run one semantic query.
The real unstructured corpus is synthesized in M1; these stand-in sentences just
prove the embed -> store -> retrieve path end to end.
Run: `uv run scripts/smoke/smoke_vector.py`"""
from rm_assistant.models.factory import get_embedder
from rm_assistant.vectorstore.chroma_store import ChromaStore

DOCS = [
    "Client raised concerns about retirement income and outliving their savings.",
    "Discussed refinancing the mortgage given the recent drop in rates.",
    "Client is interested in ESG and sustainable investment funds.",
    "Reviewed the structured-note product eligibility and capital protection terms.",
    "Client mentioned an upcoming liquidity need for a property purchase next quarter.",
]
QUERY = "What did the client say about retirement?"


def main() -> None:
    embedder = get_embedder()
    store = ChromaStore(collection="smoke")

    embs = embedder.embed(DOCS)
    store.add(
        ids=[f"doc{i}" for i in range(len(DOCS))],
        texts=DOCS,
        embeddings=embs,
        metadatas=[{"kind": "note"} for _ in DOCS],
    )
    print(f"embedder={embedder.name} dim={embedder.dim}  collection_count={store.count()}")

    qvec = embedder.embed([QUERY])[0]
    print(f"\nquery: {QUERY!r}")
    for h in store.query(qvec, k=3):
        print(f"  [{h.distance:.3f}] {h.text}")


if __name__ == "__main__":
    main()
