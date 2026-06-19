"""Optional hosted Claude provider for the "smart" role. Needs ANTHROPIC_API_KEY
and the `hosted` extra (`uv sync --extra hosted`). Imported lazily."""
from __future__ import annotations

import os


class AnthropicLLM:
    def __init__(self, model: str = "claude-opus-4-8", max_tokens: int = 2048):
        self.name = f"anthropic:{model}"
        self.model = model
        self.max_tokens = max_tokens
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        import anthropic  # lazy

        self._client = anthropic.Anthropic()

    def complete(
        self, prompt: str, *, system: str | None = None, temperature: float = 0.2
    ) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=temperature,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()
