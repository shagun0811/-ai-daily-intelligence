"""Central configuration. Values come from environment, .env, and YAML files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime settings. Secrets belong in .env; tunables may also live in YAML."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE if ENV_FILE.exists() else PROJECT_ROOT / ".env.example",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "sqlite:///./data/aggregator.db"

    llm_provider: str = "mock"
    llm_model: str = "qwen3:4b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_timeout_seconds: int = 120
    llm_max_retries: int = 2

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_provider: str = "auto"

    semantic_duplicate_threshold: float = Field(default=0.88, ge=0.0, le=1.0)
    title_similarity_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    max_articles_per_source: int = Field(default=40, ge=1)
    max_llm_items: int = Field(default=30, ge=1)
    report_max_items: int = Field(default=15, ge=1)
    http_timeout_seconds: int = Field(default=20, ge=1)
    extract_full_text: bool = True
    min_cleaned_text_chars: int = Field(default=400, ge=0)
    max_full_text_extracts: int = Field(default=25, ge=0)

    log_level: str = "INFO"
    scheduler_enabled: bool = False
    scheduler_hour: int = Field(default=17, ge=0, le=23)
    scheduler_minute: int = Field(default=0, ge=0, le=59)
    scheduler_timezone: str = "Asia/Kolkata"
    cloudflare_auto_deploy: bool = False
    cloudflare_pages_project: str = "ai-daily-intelligence"
    cloudflare_deploy_timeout_seconds: int = Field(default=300, ge=30)

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def config_dir(self) -> Path:
        return CONFIG_DIR

    @property
    def data_dir(self) -> Path:
        return DATA_DIR

    def resolved_database_url(self) -> str:
        """Make relative SQLite URLs absolute so scripts work from any cwd."""
        url = self.database_url
        prefix = "sqlite:///./"
        if url.startswith(prefix):
            relative = url[len(prefix) :]
            absolute = (PROJECT_ROOT / relative).resolve()
            absolute.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{absolute.as_posix()}"
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            rest = url[len("sqlite:///") :]
            path = Path(rest)
            if not path.is_absolute():
                absolute = (PROJECT_ROOT / path).resolve()
                absolute.parent.mkdir(parents=True, exist_ok=True)
                return f"sqlite:///{absolute.as_posix()}"
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
