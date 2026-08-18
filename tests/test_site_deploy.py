"""Cloudflare Pages auto-deploy tests. No live network."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.config.settings import clear_settings_cache
from app.site_deploy import deploy_public_site


def test_deploy_skipped_when_disabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLOUDFLARE_AUTO_DEPLOY", "false")
    clear_settings_cache()
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    summary = deploy_public_site(site_dir=tmp_path)
    assert summary.skipped is True
    assert summary.deployed is False
    clear_settings_cache()


def test_deploy_uploads_with_wrangler(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLOUDFLARE_AUTO_DEPLOY", "true")
    monkeypatch.setenv("CLOUDFLARE_PAGES_PROJECT", "ai-daily-intelligence")
    clear_settings_cache()
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "dashboard.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "app.site_deploy.shutil.which",
        lambda name: "npx" if name in {"npx", "npx.cmd"} else None,
    )

    def fake_run(command, *, cwd, capture_output, text, timeout, check):
        assert command[0] == "npx"
        assert "--project-name" in command
        assert "ai-daily-intelligence" in command
        assert (Path(cwd) / "index.html").is_file()
        assert (Path(cwd) / "data" / "dashboard.json").is_file()
        return SimpleNamespace(
            returncode=0,
            stdout="Deployment complete! Take a peek over at https://abc.ai-daily-intelligence.pages.dev\n",
            stderr="",
        )

    monkeypatch.setattr("app.site_deploy.subprocess.run", fake_run)
    summary = deploy_public_site(site_dir=tmp_path)
    assert summary.deployed is True
    assert summary.url == "https://abc.ai-daily-intelligence.pages.dev"
    assert not summary.errors
    clear_settings_cache()
