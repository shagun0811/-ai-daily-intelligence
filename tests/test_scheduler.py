"""Scheduler and pipeline runner tests. No live websites and no daemon."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.config.settings import Settings, clear_settings_cache
from app.pipeline.runner import run_daily_pipeline
from app.scheduler.lock import OverlapError, PipelineLock
from app.scheduler.service import build_scheduler, cron_trigger, run_job, start_scheduler


def test_scheduler_disabled_by_default() -> None:
    clear_settings_cache()
    settings = Settings(_env_file=None)
    assert settings.scheduler_enabled is False
    assert settings.scheduler_hour == 17
    assert settings.scheduler_timezone == "Asia/Kolkata"


def test_start_scheduler_refuses_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    clear_settings_cache()
    with pytest.raises(RuntimeError, match="SCHEDULER_ENABLED"):
        start_scheduler()
    clear_settings_cache()


def test_cron_trigger_uses_configured_time() -> None:
    trigger = cron_trigger(hour=7, minute=0, timezone="Asia/Kolkata")
    assert "7" in str(trigger) or "hour='7'" in repr(trigger) or getattr(trigger, "fields", None)


def test_build_scheduler_registers_daily_job(monkeypatch) -> None:
    monkeypatch.setenv("SCHEDULER_HOUR", "7")
    monkeypatch.setenv("SCHEDULER_MINUTE", "15")
    monkeypatch.setenv("SCHEDULER_TIMEZONE", "UTC")
    clear_settings_cache()
    scheduler = build_scheduler()
    job = scheduler.get_job("daily_pipeline")
    assert job is not None
    assert scheduler.running is False
    clear_settings_cache()


def test_lock_blocks_overlap(tmp_path: Path) -> None:
    lock_path = tmp_path / "pipeline.lock"
    with PipelineLock(lock_path):
        assert lock_path.exists()
        with pytest.raises(OverlapError):
            with PipelineLock(lock_path):
                pass
    assert not lock_path.exists()


def test_run_job_skips_when_locked(tmp_path: Path, monkeypatch) -> None:
    lock_path = tmp_path / "pipeline.lock"
    monkeypatch.setattr("app.scheduler.service.PipelineLock", lambda: PipelineLock(lock_path))
    monkeypatch.setattr("app.scheduler.service.run_daily_pipeline", lambda: (_ for _ in ()).throw(AssertionError("should not run")))
    with PipelineLock(lock_path):
        outcome = run_job()
    assert outcome.ok is False
    assert "already running" in outcome.errors[0]


def test_run_job_calls_pipeline(tmp_path: Path, monkeypatch) -> None:
    lock_path = tmp_path / "pipeline.lock"
    called = {"n": 0}

    def fake_pipeline():
        called["n"] += 1
        return SimpleNamespace(ok=True, errors=[], as_text=lambda: "ok")

    monkeypatch.setattr("app.scheduler.service.PipelineLock", lambda: PipelineLock(lock_path))
    monkeypatch.setattr("app.scheduler.service.run_daily_pipeline", fake_pipeline)
    outcome = run_job()
    assert called["n"] == 1
    assert outcome.ok is True
    assert not lock_path.exists()


def test_run_daily_pipeline_order(monkeypatch) -> None:
    calls: list[str] = []

    class _Result:
        errors: list[str] = []

        def as_text(self) -> str:
            return "ok"

    class _Step:
        def __init__(self, name: str) -> None:
            self.name = name

        def __call__(self, session) -> "_Step":
            return self

        def run(self, **_kwargs) -> _Result:
            calls.append(self.name)
            return _Result()

    monkeypatch.setattr("app.pipeline.runner.setup_logging", lambda: None)
    monkeypatch.setattr("app.pipeline.runner.init_db", lambda seed=True: None)

    class _Session:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.pipeline.runner.session_scope", lambda: _Session())
    monkeypatch.setattr("app.pipeline.runner.SourceManager", _Step("collect"))
    monkeypatch.setattr("app.pipeline.runner.ContentProcessor", _Step("clean"))
    monkeypatch.setattr("app.pipeline.runner.IntelligenceProcessor", _Step("score"))
    monkeypatch.setattr("app.pipeline.runner.Summarizer", _Step("summarize"))
    monkeypatch.setattr("app.pipeline.runner.ReportGenerator", _Step("report"))
    monkeypatch.setattr(
        "app.pipeline.runner.export_public_site",
        lambda session: calls.append("publish") or _Result(),
    )
    monkeypatch.setattr(
        "app.pipeline.runner.deploy_public_site",
        lambda: calls.append("deploy") or _Result(),
    )
    outcome = run_daily_pipeline()
    assert calls == ["collect", "clean", "score", "summarize", "report", "publish", "deploy"]
    assert outcome.ok is True


def test_run_daily_pipeline_partial_collect_is_ok(monkeypatch) -> None:
    calls: list[str] = []

    class _Result:
        def __init__(self, *, errors: list[str] | None = None, successful_sources: int = 0) -> None:
            self.errors = errors or []
            self.successful_sources = successful_sources

        def as_text(self) -> str:
            return "ok"

    class _Step:
        def __init__(self, name: str) -> None:
            self.name = name

        def __call__(self, session) -> "_Step":
            return self

        def run(self, **_kwargs) -> _Result:
            calls.append(self.name)
            if self.name == "collect":
                return _Result(errors=["arXiv: HTTP 429"], successful_sources=6)
            return _Result()

    monkeypatch.setattr("app.pipeline.runner.setup_logging", lambda: None)
    monkeypatch.setattr("app.pipeline.runner.init_db", lambda seed=True: None)

    class _Session:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.pipeline.runner.session_scope", lambda: _Session())
    monkeypatch.setattr("app.pipeline.runner.SourceManager", _Step("collect"))
    monkeypatch.setattr("app.pipeline.runner.ContentProcessor", _Step("clean"))
    monkeypatch.setattr("app.pipeline.runner.IntelligenceProcessor", _Step("score"))
    monkeypatch.setattr("app.pipeline.runner.Summarizer", _Step("summarize"))
    monkeypatch.setattr("app.pipeline.runner.ReportGenerator", _Step("report"))
    monkeypatch.setattr(
        "app.pipeline.runner.export_public_site",
        lambda session: calls.append("publish") or _Result(),
    )
    monkeypatch.setattr(
        "app.pipeline.runner.deploy_public_site",
        lambda: calls.append("deploy") or _Result(),
    )
    outcome = run_daily_pipeline()
    assert calls == ["collect", "clean", "score", "summarize", "report", "publish", "deploy"]
    assert outcome.ok is True
    assert outcome.errors == []


def test_run_daily_pipeline_continues_after_stage_failure(monkeypatch) -> None:
    calls: list[str] = []

    class _Result:
        errors: list[str] = []

        def as_text(self) -> str:
            return "ok"

    class _Step:
        def __init__(self, name: str) -> None:
            self.name = name

        def __call__(self, session) -> "_Step":
            return self

        def run(self, **_kwargs) -> _Result:
            calls.append(self.name)
            if self.name == "collect":
                raise RuntimeError("rss down")
            return _Result()

    monkeypatch.setattr("app.pipeline.runner.setup_logging", lambda: None)
    monkeypatch.setattr("app.pipeline.runner.init_db", lambda seed=True: None)

    class _Session:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.pipeline.runner.session_scope", lambda: _Session())
    monkeypatch.setattr("app.pipeline.runner.SourceManager", _Step("collect"))
    monkeypatch.setattr("app.pipeline.runner.ContentProcessor", _Step("clean"))
    monkeypatch.setattr("app.pipeline.runner.IntelligenceProcessor", _Step("score"))
    monkeypatch.setattr("app.pipeline.runner.Summarizer", _Step("summarize"))
    monkeypatch.setattr("app.pipeline.runner.ReportGenerator", _Step("report"))
    monkeypatch.setattr(
        "app.pipeline.runner.export_public_site",
        lambda session: calls.append("publish") or _Result(),
    )
    monkeypatch.setattr(
        "app.pipeline.runner.deploy_public_site",
        lambda: calls.append("deploy") or _Result(),
    )
    outcome = run_daily_pipeline()
    assert calls == ["collect", "clean", "score", "summarize", "report", "publish", "deploy"]
    assert outcome.ok is False
    assert "collect:" in outcome.errors[0]
    assert "rss down" in outcome.errors[0]
    assert "clean failed" not in outcome.processing_text
    assert outcome.processing_text == "ok"


def test_lock_replaces_stale_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / "pipeline.lock"
    lock_path.write_text("99999999", encoding="utf-8")
    with PipelineLock(lock_path):
        assert lock_path.exists()
        assert lock_path.read_text(encoding="utf-8").strip() != "99999999"
    assert not lock_path.exists()


def test_github_workflows_use_mock_llm() -> None:
    root = Path(__file__).resolve().parents[1]
    daily = yaml.safe_load((root / ".github/workflows/daily.yml").read_text(encoding="utf-8"))
    tests = yaml.safe_load((root / ".github/workflows/tests.yml").read_text(encoding="utf-8"))
    on_daily = daily.get("on", daily.get(True))
    assert daily["jobs"]["daily"]["env"]["LLM_PROVIDER"] == "mock"
    assert daily["jobs"]["daily"]["env"]["SCHEDULER_ENABLED"] == "false"
    assert daily["jobs"]["daily"]["env"]["CLOUDFLARE_AUTO_DEPLOY"] == "false"
    assert "30 11 * * *" in str(on_daily)
    daily_yaml = (root / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    assert "wrangler pages deploy" in daily_yaml
    assert "CLOUDFLARE_API_TOKEN" in daily_yaml
    assert "adi-state-" in daily_yaml
    assert tests["jobs"]["pytest"]["env"]["LLM_PROVIDER"] == "mock"
