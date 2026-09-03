"""Push the exported static site to Cloudflare Pages."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.config.logging import STAGE_REPORT, get_logger, log_stage
from app.config.settings import PROJECT_ROOT, get_settings
from app.site_export import SITE_DIR, ingest_live_archive

logger = get_logger(__name__)

_PAGES_URL = re.compile(r"https://[a-zA-Z0-9.-]+\.pages\.dev")


@dataclass
class SiteDeploySummary:
    skipped: bool = False
    deployed: bool = False
    url: str = ""
    detail: str = ""
    errors: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        if self.skipped:
            return self.detail or "Cloudflare auto-deploy skipped"
        if self.errors:
            lines = ["Cloudflare deploy failed:"]
            lines.extend(f"  - {error}" for error in self.errors)
            return "\n".join(lines)
        url = self.url or "https://ai-daily-intelligence.pages.dev"
        return f"Cloudflare deploy complete: {url}"


def deploy_public_site(site_dir: Path | None = None) -> SiteDeploySummary:
    """Upload site/ to Cloudflare Pages so the live URL shows today's briefing."""
    settings = get_settings()
    summary = SiteDeploySummary()
    if not settings.cloudflare_auto_deploy:
        summary.skipped = True
        summary.detail = "Cloudflare auto-deploy is off (CLOUDFLARE_AUTO_DEPLOY=false)"
        return summary

    root = Path(site_dir) if site_dir is not None else SITE_DIR
    if not (root / "index.html").is_file():
        summary.errors.append(f"missing index.html in {root}")
        return summary

    try:
        restored = ingest_live_archive(root)
        if restored:
            log_stage(logger, STAGE_REPORT, "merged live archive days=%s", ",".join(restored))
    except Exception as exc:  # noqa: BLE001
        log_stage(logger, STAGE_REPORT, "live archive merge skipped error=%s", exc, level=30)

    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        summary.errors.append("npx not found. Install Node.js, then run npx wrangler login once.")
        return summary

    project = settings.cloudflare_pages_project
    command = [
        npx,
        "--yes",
        "wrangler",
        "pages",
        "deploy",
        ".",
        "--project-name",
        project,
        "--commit-dirty=true",
        "--branch",
        "production",
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="adi-pages-") as tmp:
            bundle = Path(tmp) / "site"
            shutil.copytree(root, bundle, ignore=_ignore_cache)
            completed = subprocess.run(
                command,
                cwd=bundle,
                capture_output=True,
                text=True,
                timeout=settings.cloudflare_deploy_timeout_seconds,
                check=False,
            )
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        summary.detail = output
        match = _PAGES_URL.search(output)
        if match:
            summary.url = match.group(0)
        if completed.returncode != 0:
            summary.errors.append(output or f"wrangler exited {completed.returncode}")
            log_stage(logger, STAGE_REPORT, "cloudflare deploy failed code=%s", completed.returncode, level=40)
            return summary
        summary.deployed = True
        log_stage(logger, STAGE_REPORT, "cloudflare deploy ok url=%s", summary.url or project)
    except subprocess.TimeoutExpired:
        summary.errors.append("Cloudflare deploy timed out")
        log_stage(logger, STAGE_REPORT, "cloudflare deploy timed out", level=40)
    except Exception as exc:  # noqa: BLE001
        summary.errors.append(str(exc))
        log_stage(logger, STAGE_REPORT, "cloudflare deploy failed error=%s", exc, level=40)
    return summary


def _ignore_cache(path: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in {".wrangler", "node_modules"}:
            ignored.add(name)
    return ignored
