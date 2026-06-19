"""Role-based provider selection. Call these, never instantiate providers directly."""
from __future__ import annotations

from .. import config
from .base import Embedder, LLM
from .ollama import OllamaEmbedder, OllamaLLM


def get_fast_llm() -> LLM:
    """High-volume cheap work: local Ollama."""
    return OllamaLLM(config.FAST_LLM)


def get_smart_llm() -> LLM:
    """Low-volume high-quality work: codex (default) | anthropic | ollama."""
    provider = config.SMART_PROVIDER.lower()
    if provider == "codex":
        from .codex import CodexLLM

        return CodexLLM(config.SMART_MODEL)
    if provider == "anthropic":
        from .anthropic import AnthropicLLM

        return AnthropicLLM(config.SMART_MODEL or "claude-opus-4-8")
    if provider == "ollama":
        return OllamaLLM(config.SMART_MODEL or config.FAST_LLM)
    raise ValueError(f"unknown RM_SMART_PROVIDER: {config.SMART_PROVIDER}")


def get_embedder() -> Embedder:
    return OllamaEmbedder(config.EMBED_MODEL)
