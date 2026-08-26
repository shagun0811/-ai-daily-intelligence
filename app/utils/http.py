"""HTTP fetch with timeouts and limited retries. No secrets are logged."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic, sleep

import requests

from app.config.logging import STAGE_COLLECT, get_logger, log_stage
from app.config.settings import get_settings

logger = get_logger(__name__)

DEFAULT_USER_AGENT = (
    "AIDailyIntelligenceAggregator/0.1 "
    "(+https://ai-daily-intelligence.pages.dev)"
)
_RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpError(Exception):
    """Raised when a source URL cannot be fetched."""

    def __init__(self, message: str, *, status_code: int | None = None, url: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status_code: int
    text: str
    elapsed_ms: int
    content_type: str | None = None


def fetch_url(
    url: str,
    *,
    timeout: int | None = None,
    max_retries: int | None = None,
) -> HttpResponse:
    """GET a URL. Retries transient errors; raises HttpError on failure."""
    settings = get_settings()
    timeout = timeout if timeout is not None else settings.http_timeout_seconds
    retries = max_retries if max_retries is not None else 3
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        started = monotonic()
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            elapsed_ms = int((monotonic() - started) * 1000)
            if response.status_code in _RETRY_STATUS and attempt < retries:
                log_stage(
                    logger,
                    STAGE_COLLECT,
                    "retry url=%s status=%s attempt=%s",
                    url,
                    response.status_code,
                    attempt + 1,
                    level=30,
                )
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    sleep(min(int(retry_after), 20))
                elif response.status_code == 429:
                    sleep(min(8 * (attempt + 1), 20))
                else:
                    sleep(min(2 ** attempt, 4))
                continue
            if response.status_code >= 400:
                raise HttpError(
                    f"HTTP {response.status_code} for {url}",
                    status_code=response.status_code,
                    url=url,
                )
            response.encoding = response.encoding or "utf-8"
            return HttpResponse(
                url=str(response.url),
                status_code=response.status_code,
                text=response.text,
                elapsed_ms=elapsed_ms,
                content_type=response.headers.get("Content-Type"),
            )
        except HttpError:
            raise
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries:
                log_stage(
                    logger,
                    STAGE_COLLECT,
                    "retry url=%s error=%s attempt=%s",
                    url,
                    type(exc).__name__,
                    attempt + 1,
                    level=30,
                )
                sleep(min(2 ** attempt, 4))
                continue
            raise HttpError(f"{type(exc).__name__}: {exc}", url=url) from exc

    raise HttpError(str(last_error or "request failed"), url=url)
