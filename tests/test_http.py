"""HTTP helper tests. No live websites."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from app.utils.http import HttpError, fetch_url


def test_fetch_url_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.utils.http.sleep", lambda *_args, **_kwargs: None)
    calls = {"n": 0}

    def fake_get(url: str, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return SimpleNamespace(
                url=url,
                status_code=503,
                text="unavailable",
                encoding="utf-8",
                headers={},
            )
        return SimpleNamespace(
            url=url,
            status_code=200,
            text="ok body",
            encoding="utf-8",
            headers={"Content-Type": "text/plain"},
        )

    monkeypatch.setattr("app.utils.http.requests.get", fake_get)
    response = fetch_url("https://example.com/feed", timeout=1, max_retries=2)
    assert response.text == "ok body"
    assert response.status_code == 200
    assert calls["n"] == 2


def test_fetch_url_raises_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.utils.http.sleep", lambda *_args, **_kwargs: None)

    def fake_get(url: str, headers=None, timeout=None):
        raise requests.Timeout("slow")

    monkeypatch.setattr("app.utils.http.requests.get", fake_get)
    with pytest.raises(HttpError, match="Timeout"):
        fetch_url("https://example.com/feed", timeout=1, max_retries=1)
