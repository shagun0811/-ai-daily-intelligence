"""Build the configured LLM provider. Callers must not import Ollama directly."""

from __future__ import annotations

from app.config.settings import get_settings
from app.llm.base import LLMProvider
from app.llm.mock_provider import MockProvider
from app.llm.ollama_provider import OllamaProvider


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    name = settings.llm_provider.strip().lower()
    model = settings.llm_model
    if name == "mock":
        return MockProvider(model=model)
    if name == "ollama":
        return OllamaProvider(
            model=model,
            base_url=settings.ollama_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    raise ValueError(
        f"Unknown LLM_PROVIDER={name!r}. Use 'mock' or 'ollama'. "
        "OpenAI, Gemini, and Anthropic are not implemented."
    )
