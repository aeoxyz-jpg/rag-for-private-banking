"""VectorStore interface so the Phase-2 pillar-A index can be swapped
(Chroma / LanceDB / pgvector) without touching retrieval code."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass
class Hit:
    id: str
    text: str
    metadata: dict
    distance: float


class VectorStore(Protocol):
    def add(
        self,
        ids: Sequence[str],
        texts: Sequence[str],
        embeddings: Sequence[Sequence[float]],
        metadatas: Sequence[dict] | None = None,
    ) -> None: ...

    def query(self, embedding: Sequence[float], k: int = 5) -> list[Hit]: ...

    def count(self) -> int: ...
