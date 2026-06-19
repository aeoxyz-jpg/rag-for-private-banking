"""LLM synthesis of the unstructured layer (spec §3.4): per-client CRM documents
grounded on the client's real structured facts, plus a small global product/policy KB.

One LLM call per client returns a JSON array of 3-8 documents. Codex-generated style
seeds (cached) are injected as few-shot exemplars to fight the templating risk (spec §9).
Every doc is provenance-tagged with the facts it was conditioned on.
"""
from __future__ import annotations

import json
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .. import config, db
from ..models.factory import get_embedder
from ..models.ollama import OllamaLLM
from ..vectorstore.chroma_store import ChromaStore
from . import facts

SEEDS_PATH = Path(__file__).with_name("style_seeds.json")
KIND_TO_ITYPE = {"note": "review", "transcript": "service",
                 "brief": "prospecting", "complaint": "complaint"}

_SYS = (
    "You generate realistic private-banking CRM records for a synthetic dataset. "
    "Output ONLY a JSON array — no prose, no markdown fences."
)


def _load_seeds() -> str:
    if SEEDS_PATH.exists():
        seeds = json.loads(SEEDS_PATH.read_text())
        return "\n\n".join(f"[{s['kind']}] {s['text']}" for s in seeds)
    return ""


def _prompt(f: dict, k: int, seeds: str) -> str:
    parts = [
        f"Generate {k} varied CRM documents a relationship manager would have on file "
        f"for this client. Each must be CONSISTENT with the profile below — never invent "
        f"contradictory wealth, products, or life-stage.",
        "",
        "Rules:",
        "- Vary kind, voice, length, format and date (between client_since and 1998-12-31).",
        "- Reference concrete facts naturally (a holding class, a loan, pension income, a lead).",
        '- Each item: {"kind","date","title","text","sentiment","channel"}',
        "  kind in [note,transcript,brief,complaint]; sentiment in [positive,neutral,negative];",
        "  channel in [call,email,meeting,video].",
        "",
        "CLIENT PROFILE (ground truth):",
        json.dumps(f, default=str),
    ]
    if seeds:
        parts += ["", "STYLE EXEMPLARS (match this realism, not the content):", seeds]
    parts += ["", f"Return ONLY a JSON array of {k} documents."]
    return "\n".join(parts)


_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


def _parse_docs(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].lstrip("json").strip() if "```" in raw else raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = _JSON_ARRAY.search(raw)
        return json.loads(m.group(0)) if m else []


def _embed_and_store(embedder, store, ids, texts, metas) -> None:
    if ids:
        store.add(ids=ids, texts=texts, embeddings=embedder.embed(texts), metadatas=metas)


def _generate(cid: int, f: dict, k: int, seeds: str, llm, embedder) -> dict | None:
    """Worker: LLM call + parse + embed (the I/O-heavy parts). No DB/Chroma here so it
    runs concurrently. Returns a record bundle for the main thread to persist."""
    docs = _parse_docs(llm.complete(_prompt(f, k, seeds), system=_SYS, temperature=0.9))
    recs = []
    for i, d in enumerate(docs):
        if not isinstance(d, dict) or "text" not in d:
            continue
        recs.append({
            "doc_id": f"doc-{cid}-{i}",
            "kind": (d.get("kind") or "note").lower(),
            "ts": d.get("date") or facts.DATA_AS_OF,
            "text": (d.get("title", "") + "\n" + d["text"]).strip(),
            "sentiment": (d.get("sentiment") or "neutral").lower(),
            "channel": (d.get("channel") or "meeting").lower(),
        })
    if not recs:
        return None
    embs = embedder.embed([r["text"] for r in recs])
    return {"cid": cid, "provenance": json.dumps(f, default=str), "recs": recs, "embs": embs}


def run(limit: int | None = None, workers: int = 8) -> dict[str, int]:
    rng = random.Random(config.SEED)
    llm = OllamaLLM(config.SYNTH_MODEL)
    embedder = get_embedder()
    store = ChromaStore(collection="documents")
    store.reset()  # rebuild from scratch -> no orphan vectors
    seeds = _load_seeds()

    conn = db.connect()
    book = facts.active_book(conn, config.CORPUS_SUBSET)
    if limit:
        book = book[:limit]
    # k per client fixed in book order -> deterministic regardless of completion order
    plan = [(cid, facts.client_facts(conn, cid), rng.randint(*config.NOTES_PER_CLIENT))
            for cid in book]
    rm_of = {r["client_id"]: r["rm_id"]
             for r in conn.execute("SELECT client_id, rm_id FROM clients")}

    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM interactions")
    conn.commit()

    n_docs = n_done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_generate, cid, f, k, seeds, llm, embedder): cid
                   for cid, f, k in plan}
        for fut in as_completed(futures):
            cid = futures[fut]
            n_done += 1
            try:
                bundle = fut.result()
            except Exception as e:  # noqa: BLE001 - skip bad generation, keep going
                print(f"  client {cid}: failed ({e}); skipped")
                continue
            if not bundle:
                continue
            for r in bundle["recs"]:
                conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?)",
                             (r["doc_id"], cid, r["kind"], r["ts"], r["text"],
                              r["doc_id"], bundle["provenance"]))
                conn.execute(
                    "INSERT INTO interactions (client_id,rm_id,ts,channel,type,sentiment,summary_ref)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (cid, rm_of.get(cid), r["ts"], r["channel"],
                     KIND_TO_ITYPE.get(r["kind"], "review"), r["sentiment"], r["doc_id"]))
            store.add(ids=[r["doc_id"] for r in bundle["recs"]],
                      texts=[r["text"] for r in bundle["recs"]],
                      embeddings=bundle["embs"],
                      metadatas=[{"client_id": cid, "kind": r["kind"], "ts": r["ts"],
                                  "sentiment": r["sentiment"]} for r in bundle["recs"]])
            conn.commit()
            n_docs += len(bundle["recs"])
            if n_done % 50 == 0:
                print(f"  ...{n_done}/{len(plan)} clients, {n_docs} docs")

    conn.close()
    return {"clients": len(book), "documents": n_docs, "interactions": n_docs}


def synth_kb() -> int:
    """Generate the global product/policy KB (Q8). client_id is NULL for these."""
    llm = OllamaLLM(config.SYNTH_MODEL)
    embedder = get_embedder()
    store = ChromaStore(collection="documents")
    conn = db.connect()

    prompt = (
        f"Generate {config.N_KB_DOCS} concise product/policy knowledge-base articles for a "
        "private bank (e.g. structured-note eligibility, lombard lending terms, KYC refresh "
        "policy, discretionary mandate fees, FX execution, deposit protection). "
        'Each item: {"title","topic","text"} (text 80-160 words). Return ONLY a JSON array.'
    )
    docs = _parse_docs(llm.complete(prompt, system=_SYS, temperature=0.7))
    ids, texts, metas = [], [], []
    for i, d in enumerate(docs):
        if not isinstance(d, dict) or "text" not in d:
            continue
        doc_id = f"kb-{i}"
        text = (d.get("title", "") + "\n" + d["text"]).strip()
        conn.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?)",
                     (doc_id, None, "kb", facts.DATA_AS_OF, text, doc_id,
                      json.dumps({"topic": d.get("topic")})))
        ids.append(doc_id); texts.append(text)
        metas.append({"kind": "kb", "topic": d.get("topic") or ""})  # no None values
    _embed_and_store(embedder, store, ids, texts, metas)
    conn.commit()
    conn.close()
    return len(ids)
