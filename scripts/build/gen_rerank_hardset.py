"""One-time: build the hard rerank gold. Sample clients with >=3 note-kind docs; for each, pick one
note as gold and reverse-generate a question pinned to its specifics. The client's sibling notes are
the distractors. Run: `uv run scripts/build/gen_rerank_hardset.py`. Output committed + reviewable."""
import json
import random
from pathlib import Path

from rm_assistant import config, db
from rm_assistant.models.ollama import OllamaLLM

OUT = Path("rm_assistant/eval/gold/rerank_hard.json")
_SYS = ("You write evaluation questions for a retrieval system. Given one CRM note, write ONE natural "
        "question a relationship manager would ask that THIS note specifically answers. Reference its "
        "specifics (the concern, product, or event) but do NOT quote it verbatim, and do NOT mention "
        "the client's name or id. Output ONLY the question.")


def _multi_note_clients(conn, min_notes: int):
    rows = conn.execute(
        "SELECT client_id, doc_id, text FROM documents "
        "WHERE kind != 'kb' AND client_id IS NOT NULL AND length(text) > 200").fetchall()
    by_client = {}
    for r in rows:
        by_client.setdefault(r["client_id"], []).append({"doc_id": r["doc_id"], "text": r["text"]})
    from rm_assistant.rerankx.hardset import filter_by_density
    return filter_by_density(by_client, min_notes)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-notes", type=int, default=config.RERANK_HARD_MIN_NOTES)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out_path = Path(args.out)
    conn = db.connect(readonly=True)
    pools = _multi_note_clients(conn, args.min_notes)
    conn.close()
    rng = random.Random(config.SEED)
    clients = sorted(pools)
    rng.shuffle(clients)
    clients = clients[:config.RERANK_HARD_N]
    llm = OllamaLLM(config.SYNTH_MODEL)
    gold = []
    for i, c in enumerate(clients):
        notes = pools[c]
        note = rng.choice(notes)
        q = llm.complete(f"Note:\n{note['text']}", system=_SYS, temperature=0.4).strip()
        gold.append({"id": f"rr-{i}", "question": q, "gold_doc_id": note["doc_id"],
                     "client_id": c, "n_sibling_notes": len(notes) - 1})
    out_path.write_text(json.dumps(gold, indent=1, ensure_ascii=False))
    sib = [g["n_sibling_notes"] for g in gold]
    print(f"Wrote {len(gold)} hard questions -> {out_path} "
          f"(sibling notes: min {min(sib)}, max {max(sib)}, mean {sum(sib)/len(sib):.1f})")


if __name__ == "__main__":
    main()
