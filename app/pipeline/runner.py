"""Shared daily pipeline. Used by the CLI, APScheduler, and GitHub Actions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.collectors.source_manager import SourceManager
from app.config.logging import STAGE_COLLECT, STAGE_REPORT, get_logger, log_stage, setup_logging
from app.database.database import init_db, session_scope
from app.processors.intelligence import IntelligenceProcessor
from app.processors.pipeline import ContentProcessor
from app.processors.summarizer import Summarizer
from app.report.generator import ReportGenerator
from app.site_deploy import deploy_public_site
from app.site_export import export_public_site

logger = get_logger(__name__)

_StageFn = Callable[[Session], object]


@dataclass
class PipelineOutcome:
    collection_text: str = ""
    processing_text: str = ""
    intelligence_text: str = ""
    summarize_text: str = ""
    report_text: str = ""
    site_text: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_text(self) -> str:
        blocks = [
            self.collection_text,
            self.processing_text,
            self.intelligence_text,
            self.summarize_text,
            self.report_text,
            self.site_text,
        ]
        body = "\n\n".join(block for block in blocks if block)
        if self.errors:
            body += "\n\nErrors:\n" + "\n".join(f"  - {error}" for error in self.errors)
        return body


def run_daily_pipeline() -> PipelineOutcome:
    """Collect → clean → score → summarize → report.

    Each stage commits on its own so a later failure does not undo earlier work.
    """
    setup_logging()
    init_db(seed=True)
    outcome = PipelineOutcome()
    stages: tuple[tuple[str, str, _StageFn], ...] = (
        ("collect", "collection_text", lambda session: SourceManager(session).run(enabled_only=True)),
        ("clean", "processing_text", lambda session: ContentProcessor(session).run()),
        ("score", "intelligence_text", lambda session: IntelligenceProcessor(session).run()),
        ("summarize", "summarize_text", lambda session: Summarizer(session).run()),
        ("report", "report_text", lambda session: ReportGenerator(session).run()),
        ("publish", "site_text", _publish_site),
    )
    for name, field_name, fn in stages:
        _run_stage(outcome, name=name, field_name=field_name, fn=fn)
    return outcome


def _run_stage(outcome: PipelineOutcome, *, name: str, field_name: str, fn: _StageFn) -> None:
    stage_label = STAGE_COLLECT if name == "collect" else STAGE_REPORT if name == "report" else name.upper()
    try:
        with session_scope() as session:
            result = fn(session)
        text = result.as_text() if hasattr(result, "as_text") else str(result)
        setattr(outcome, field_name, text)
        stage_errors = list(getattr(result, "errors", []) or []) if hasattr(result, "errors") else []
        # One RSS/arXiv outage must not fail the job if other sources produced items.
        collect_partial = name == "collect" and getattr(result, "successful_sources", 0) > 0
        if stage_errors and not collect_partial:
            outcome.errors.extend(stage_errors)
        log_stage(logger, stage_label, "stage done")
    except Exception as exc:  # noqa: BLE001
        message = f"{name}: {exc}"
        outcome.errors.append(message)
        setattr(outcome, field_name, f"{name} failed: {exc}")
        log_stage(logger, stage_label, "stage failed error=%s", exc, level=40)
        logger.exception("Pipeline stage %s failed", name)


def _publish_site(session: Session) -> object:
    export = export_public_site(session)
    deploy = deploy_public_site()

    class _Combined:
        def __init__(self) -> None:
            self.errors = list(getattr(export, "errors", []) or []) + list(
                getattr(deploy, "errors", []) or []
            )

        def as_text(self) -> str:
            return "\n".join(part for part in (export.as_text(), deploy.as_text()) if part)

    return _Combined()
