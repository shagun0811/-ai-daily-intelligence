"""Logging helpers must not leak secret field names as values."""

from __future__ import annotations

import logging

from app.config.logging import log_stage


def test_log_stage_strips_secret_kwargs(caplog) -> None:
    logger = logging.getLogger("tests.logging")
    logger.propagate = True
    with caplog.at_level(logging.INFO, logger="tests.logging"):
        log_stage(
            logger,
            "COLLECT",
            "fetched source=%s",
            "Google AI Blog",
            api_key="should-not-appear",
            items=3,
        )
    text = caplog.text
    assert "[COLLECT]" in text
    assert "Google AI Blog" in text
    assert "items=3" in text
    assert "should-not-appear" not in text
    assert "api_key" not in text
