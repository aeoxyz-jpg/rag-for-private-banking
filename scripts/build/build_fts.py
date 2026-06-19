"""Build the FTS5 lexical index for hybrid search (pillar A).
Run: `uv run scripts/build/build_fts.py`"""
from rm_assistant.retrieval import vector_pillar


def main() -> None:
    n = vector_pillar.build_fts()
    print(f"Indexed {n} documents into documents_fts (BM25).")


if __name__ == "__main__":
    main()
