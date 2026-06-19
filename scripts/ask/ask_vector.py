"""A smoke: hybrid retrieve + grounded answer. `--kb` restricts to the policy KB (Q8).
Run: `uv run scripts/ask/ask_vector.py "what did clients say about retirement?"`"""
import argparse

from rm_assistant.retrieval import vector_pillar


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="+")
    ap.add_argument("--kb", action="store_true", help="restrict to policy/product KB (Q8)")
    ap.add_argument("--client", type=int, default=None, help="restrict to one client")
    args = ap.parse_args()

    r = vector_pillar.answer(" ".join(args.question),
                             kind="kb" if args.kb else None, client_id=args.client)
    print(f"Q: {r.question}\n")
    print("Sources (RRF-fused dense + BM25):")
    for s in r.sources:
        print(f"  [{s.doc_id}] {s.kind} client={s.client_id}  {s.text[:80].strip()}")
    print(f"\nAnswer:\n{r.answer}")


if __name__ == "__main__":
    main()
