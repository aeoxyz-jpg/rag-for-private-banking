"""Local Ollama provider: fast LLM + bge-m3 embeddings. No API key required."""
from __future__ import annotations

from typing import Sequence

import httpx

from .. import config


class OllamaLLM:
    def __init__(self, model: str = config.FAST_LLM, host: str = config.OLLAMA_HOST):
        self.name = f"ollama:{model}"
        self.model = model
        self._host = host.rstrip("/")

    def complete(
        self, prompt: str, *, system: str | None = None, temperature: float = 0.2
    ) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system
        r = httpx.post(f"{self._host}/api/generate", json=payload, timeout=300)
        r.raise_for_status()
        return r.json()["response"].strip()


class OllamaEmbedder:
    def __init__(self, model: str = config.EMBED_MODEL, host: str = config.OLLAMA_HOST):
        self.name = f"ollama:{model}"
        self.model = model
        self.dim = config.EMBED_DIM
        self._host = host.rstrip("/")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        r = httpx.post(
            f"{self._host}/api/embed",
            json={"model": self.model, "input": list(texts)},
            timeout=300,
        )
        r.raise_for_status()
        embs = r.json()["embeddings"]
        self.dim = len(embs[0])  # trust the model's actual dim
        return embs
