"""LLM provider abstraction. Application code talks to this, not to Ollama."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.llm.json_parse import parse_json_object


class LLMError(Exception):
    """Provider failed after retries. The summarizer continues with other items."""


class LLMProvider(ABC):
    provider_name: str

    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Return raw model text. Must not log secrets."""

    def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_retries: int = 2,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        current = prompt
        for _attempt in range(max_retries + 1):
            raw = self.generate(current, system=system)
            try:
                return parse_json_object(raw)
            except (ValueError, TypeError) as exc:
                last_error = exc
                current = (
                    prompt
                    + "\n\nYour previous reply was not valid JSON. "
                    "Reply with a single JSON object only."
                )
        raise LLMError(str(last_error) if last_error else "JSON generation failed")
