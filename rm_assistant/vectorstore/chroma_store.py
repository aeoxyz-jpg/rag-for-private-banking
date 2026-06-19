"""Persistent Chroma backend. We pass precomputed bge-m3 embeddings, so Chroma's
own embedding function is never used."""
from __future__ import annotations

import threading
from typing import Sequence

import chromadb

from .. import config
from .base import Hit

# One PersistentClient per path, shared across threads — creating multiple clients on the
# same path concurrently races on tenant init ("Could not connect to tenant default_tenant").
_CLIENTS: dict[str, "chromadb.ClientAPI"] = {}
_LOCK = threading.Lock()


def _client(persist_dir) -> "chromadb.ClientAPI":
    key = str(persist_dir)
    with _LOCK:
        if key not in _CLIENTS:
            persist_dir.mkdir(parents=True, exist_ok=True)
            _CLIENTS[key] = chromadb.PersistentClient(path=key)
        return _CLIENTS[key]


class ChromaStore:
    def __init__(self, collection: str = "documents", persist_dir=config.CHROMA_DIR):
        self._client = _client(persist_dir)
        self._col = self._client.get_or_create_collection(
            collection, metadata={"hnsw:space": "cosine"}
        )

    def add(
        self,
        ids: Sequence[str],
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[dict] | None = None,
    ) -> None:
        self._col.upsert(
            ids=list(ids),
            documents=list(texts),
            embeddings=[list(e) for e in embeddings],
            metadatas=list(metadatas) if metadatas else None,
        )

    def query(self, embedding: Sequence[float], k: int = 5,
              where: dict | None = None) -> list[Hit]:
        res = self._col.query(query_embeddings=[list(embedding)], n_results=k,
                              where=where or None)
        hits: list[Hit] = []
        for id_, doc, meta, dist in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            hits.append(Hit(id=id_, text=doc, metadata=meta or {}, distance=dist))
        return hits

    def count(self) -> int:
        return self._col.count()

    def reset(self) -> None:
        """Drop and recreate the collection (avoids orphan vectors on rebuild)."""
        name = self._col.name
        self._client.delete_collection(name)
        self._col = self._client.get_or_create_collection(
            name, metadata={"hnsw:space": "cosine"})
