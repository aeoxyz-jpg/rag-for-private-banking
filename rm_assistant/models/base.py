"""Provider-agnostic interfaces for the LLM + embedding layer (spec §8).

Keeping retrieval/synthesis code behind these Protocols is what makes the
Phase-2 architecture comparison vendor-independent.
"""
from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable


@runtime_checkable
class LLM(Protocol):
    name: str

    def complete(
        self, prompt: str, *, system: str | None = None, temperature: float = 0.2
    ) -> str:
        """Return the model's text completion for a single prompt."""
        ...


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one dense vector per input text."""
        ...
