"""Auto-construct the vector gold set: sample known documents and reverse-generate a
natural question each answers (gold = the source doc_id). Reliable by construction —
recall/MRR measure whether retrieval surfaces the doc the question came from.
Q3 from client notes, Q8 from the policy KB. Run once; output is committed + reviewable.
Run: `uv run scripts/build/gen_vector_gold.py`"""
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rm_assistant import config, db
from rm_assistant.models.ollama import OllamaLLM

OUT = Path("rm_assistant/eval/gold/vector.json")
N_Q3 = 24
_SYS = ("You write evaluation questions for a retrieval system. Given one CRM document, "
        "write ONE natural question a relationship manager would ask that THIS document "
        "specifically answers. Reference its specifics (the concern, product, event, or "
        "policy) but do NOT quote it verbatim. Output ONLY the question.")


def _sample(conn) -> list[dict]:
    rng = random.Random(config.SEED)
    notes = conn.execute(
        "SELECT doc_id, client_id, kind, text FROM documents "
        "WHERE client_id IS NOT NULL AND length(text) > 200").fetchall()
    rng.shuffle(notes)
    picked, seen = [], set()
    for r in notes:  # spread across distinct clients
        if r["client_id"] in seen:
            continue
        seen.add(r["client_id"])
        picked.append({"archetype": "Q3", **dict(r)})
        if len(picked) >= N_Q3:
            break
    kb = conn.execute("SELECT doc_id, client_id, kind, text FROM documents WHERE kind='kb'")
    picked += [{"archetype": "Q8", **dict(r)} for r in kb]
    return picked


def _make(item: dict, llm: OllamaLLM) -> dict:
    q = llm.complete(f"Document:\n{item['text']}", system=_SYS, temperature=0.4).strip()
    return {"id": f"vec-{item['archetype'].lower()}-{item['doc_id']}",
            "archetype": item["archetype"], "question": q,
            "gold_doc_ids": [item["doc_id"]], "source_doc_id": item["doc_id"],
            "kind": "kb" if item["archetype"] == "Q8" else None}


def main() -> None:
    conn = db.connect(readonly=True)
    items = _sample(conn)
    conn.close()
    llm = OllamaLLM(config.SYNTH_MODEL)
    with ThreadPoolExecutor(max_workers=8) as ex:
        gold = list(ex.map(lambda it: _make(it, llm), items))
    OUT.write_text(json.dumps(gold, indent=1, ensure_ascii=False))
    print(f"Wrote {len(gold)} vector gold queries "
          f"({sum(g['archetype']=='Q3' for g in gold)} Q3 / {sum(g['archetype']=='Q8' for g in gold)} Q8) -> {OUT}")


if __name__ == "__main__":
    main()
