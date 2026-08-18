"""Shared pytest fixtures. Tests never hit the network."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from app.config.settings import clear_settings_cache
from app.config.yaml_loader import clear_yaml_cache
from app.config.taxonomy import clear_taxonomy_cache
from app.database.database import init_db, reset_engine, session_scope


@pytest.fixture(autouse=True)
def disable_cloudflare_deploy(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Tests never push to the live Cloudflare site unless they opt in."""
    monkeypatch.setenv("CLOUDFLARE_AUTO_DEPLOY", "false")
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("EXTRACT_FULL_TEXT", "false")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    clear_settings_cache()
    clear_yaml_cache()
    clear_taxonomy_cache()
    reset_engine()
    init_db(seed=True)
    yield db_path
    reset_engine()
    clear_settings_cache()
    clear_yaml_cache()
    clear_taxonomy_cache()


@pytest.fixture()
def db_session(isolated_db: Path) -> Generator:
    with session_scope() as session:
        yield session
