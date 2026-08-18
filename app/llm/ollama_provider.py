"""Ollama backend. Application code must not import this module except via factory."""

from __future__ import annotations

from time import sleep
from typing import Any

import requests

from app.config.logging import STAGE_SUMMARIZE, get_logger, log_stage
from app.llm.base import LLMError, LLMProvider

logger = get_logger(__name__)
_RETRY_STATUS = {429, 500, 502, 503, 504}


class OllamaProvider(LLMProvider):
    provider_name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        timeout_seconds: int,
        max_retries: int,
    ) -> None:
        super().__init__(model)
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        url = f"{self.base_url}/api/chat"
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(url, json=payload, timeout=self.timeout_seconds)
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    log_stage(
                        logger,
                        STAGE_SUMMARIZE,
                        "ollama retry error=%s attempt=%s",
                        type(exc).__name__,
                        attempt + 1,
                        level=30,
                    )
                    sleep(min(2**attempt, 4))
                    continue
                raise LLMError(f"Ollama unreachable at {self.base_url}: {exc}") from exc

            if response.status_code in _RETRY_STATUS and attempt < self.max_retries:
                log_stage(
                    logger,
                    STAGE_SUMMARIZE,
                    "ollama retry status=%s attempt=%s",
                    response.status_code,
                    attempt + 1,
                    level=30,
                )
                sleep(min(2**attempt, 4))
                continue
            if response.status_code >= 400:
                raise LLMError(f"Ollama HTTP {response.status_code} at {url}")

            try:
                data = response.json()
            except ValueError as exc:
                raise LLMError("Ollama returned non-JSON") from exc
            content = _message_content(data)
            if not content:
                raise LLMError("Ollama returned an empty message")
            return content

        raise LLMError(str(last_error) if last_error else "Ollama request failed")


def _message_content(data: dict[str, Any]) -> str:
    message = data.get("message") or {}
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"])
    if data.get("response"):
        return str(data["response"])
    return ""
