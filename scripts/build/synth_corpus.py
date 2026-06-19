"""M1: synthesize the unstructured corpus (client notes + global KB) and embed it.
Run: `uv run scripts/build/synth_corpus.py [--limit N] [--kb-only]`"""
import argparse

from rm_assistant import config
from rm_assistant.synth import notes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap clients (for testing)")
    ap.add_argument("--kb-only", action="store_true", help="only (re)build the global KB")
    args = ap.parse_args()

    print(f"Synthesis model: {config.SYNTH_MODEL}  embed: {config.EMBED_MODEL}")
    if not args.kb_only:
        r = notes.run(limit=args.limit)
        print(f"client corpus: {r['documents']} docs / {r['interactions']} interactions "
              f"over {r['clients']} clients")
    n_kb = notes.synth_kb()
    print(f"KB: {n_kb} policy/product docs")


if __name__ == "__main__":
    main()
