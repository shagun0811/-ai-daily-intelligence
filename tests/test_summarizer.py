"""Summarizer tests. Mock LLM only; no network."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.config.settings import clear_settings_cache
from app.database.enums import ClusterMemberRole, ProcessingStatus
from app.database.models import LLMCache, ProcessingResult
from app.database.repository import Repository
from app.llm.mock_provider import MockProvider
from app.processors.intelligence import IntelligenceProcessor
from app.processors.summarizer import Summarizer
from app.utils.hashing import content_hash


class CountingMock(MockProvider):
    def __init__(self) -> None:
        super().__init__("qwen3:4b")
        self.calls = 0

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        return super().generate(prompt, system=system)


def _article(db_session, *, source_name: str, title: str, url: str, text: str, **fields):
    repo = Repository(db_session)
    source = repo.get_source_by_name(source_name)
    assert source is not None
    article = repo.create_article(
        source=source,
        title=title,
        url=url,
        cleaned_text=text,
        description=text,
        content_hash=content_hash(text, url),
        published_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
        **fields,
    )
    article.processing_status = ProcessingStatus.DEDUPLICATED.value
    db_session.flush()
    db_session.refresh(article)
    return article


def test_summarizer_skips_irrelevant_and_supporting(db_session) -> None:
    primary = _article(
        db_session,
        source_name="Google AI Blog",
        title="Official large language model release with open weights",
        url="https://blog.google/llm-primary",
        text="Google released an open-weights large language model checkpoint on Hugging Face.",
    )
    supporting = _article(
        db_session,
        source_name="TechCrunch AI",
        title="Official large language model release with open weights",
        url="https://techcrunch.com/llm-support",
        text="Coverage of the open-weights large language model release.",
    )
    fluff = _article(
        db_session,
        source_name="Google AI Blog",
        title="Host a dinner party seating chart",
        url="https://blog.google/party-sum",
        text="Cookie banner and newsletter seating chart.",
    )
    repo = Repository(db_session)
    cluster = repo.create_story_cluster(
        event_title="LLM release",
        primary_article=primary,
        cluster_date=datetime.now(timezone.utc),
    )
    repo.add_cluster_member(cluster, primary, ClusterMemberRole.PRIMARY)
    repo.add_cluster_member(cluster, supporting, ClusterMemberRole.SUPPORTING)

    IntelligenceProcessor(db_session).run()
    provider = CountingMock()
    summary = Summarizer(db_session, provider=provider).run()

    db_session.refresh(primary)
    db_session.refresh(supporting)
    db_session.refresh(fluff)
    assert primary.processing_status == ProcessingStatus.SUMMARIZED.value
    assert supporting.processing_status == ProcessingStatus.SCORED.value
    assert fluff.processing_status == ProcessingStatus.SCORED.value
    assert summary.summarized == 1
    assert summary.skipped_supporting >= 1
    assert summary.skipped_irrelevant >= 1
    assert provider.calls == 1

    result = db_session.scalar(
        select(ProcessingResult).where(
            ProcessingResult.article_id == primary.id,
            ProcessingResult.stage == "SUMMARIZE",
        )
    )
    assert result is not None
    assert result.output_json["provenance"]["source_url"] == primary.url
    assert result.output_json["schema"] in {"news", "company"}


def test_summarizer_updates_research_paper_fields(db_session) -> None:
    paper_article = _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="A retrieval method for agentic RAG systems",
        url="https://arxiv.org/abs/2608.09901",
        text=(
            "We propose a retrieval method for agentic RAG. "
            "Previous pipelines miss multi-hop evidence. "
            "Results improve recall on a public benchmark. Limitations include English-only data."
        ),
        item_kind="research_paper",
    )
    repo = Repository(db_session)
    repo.ensure_research_paper(
        paper_article,
        arxiv_id="2608.09901",
        abstract=paper_article.cleaned_text,
        authors_json=["Ada"],
        categories_json=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/2608.09901",
    )
    IntelligenceProcessor(db_session).run()
    Summarizer(db_session, provider=CountingMock()).run()
    db_session.refresh(paper_article)
    assert paper_article.processing_status == ProcessingStatus.SUMMARIZED.value
    assert paper_article.research_paper is not None
    assert paper_article.research_paper.key_contribution
    assert paper_article.research_paper.methodology
    assert paper_article.research_paper.research_significance


def test_cache_avoids_second_llm_call(db_session) -> None:
    article = _article(
        db_session,
        source_name="Google AI Blog",
        title="Open weights large language model for on-device inference",
        url="https://blog.google/cache-sum",
        text="Google released an open-weights large language model for on-device inference.",
    )
    IntelligenceProcessor(db_session).run()
    provider = CountingMock()
    first = Summarizer(db_session, provider=provider).run()
    assert first.summarized == 1
    assert provider.calls == 1

    db_session.execute(
        delete(ProcessingResult).where(
            ProcessingResult.article_id == article.id,
            ProcessingResult.stage == "SUMMARIZE",
        )
    )
    db_session.refresh(article)
    article.processing_status = ProcessingStatus.SCORED.value
    db_session.flush()

    second = Summarizer(db_session, provider=provider).run()
    assert second.cache_hits == 1
    assert second.summarized == 1
    assert provider.calls == 1
    assert db_session.scalar(select(LLMCache)) is not None


def test_processing_result_skips_unchanged_hash(db_session) -> None:
    article = _article(
        db_session,
        source_name="Google AI Blog",
        title="Open weights large language model checkpoint",
        url="https://blog.google/hash-sum",
        text="Announcement of an open-weights large language model checkpoint.",
    )
    IntelligenceProcessor(db_session).run()
    provider = CountingMock()
    Summarizer(db_session, provider=provider).run()
    db_session.refresh(article)
    article.processing_status = ProcessingStatus.SCORED.value
    db_session.flush()

    again = Summarizer(db_session, provider=provider).run()
    assert again.summarized == 0
    assert again.skipped_already >= 1
    assert provider.calls == 1


def test_max_llm_items_cap(db_session, monkeypatch) -> None:
    monkeypatch.setenv("MAX_LLM_ITEMS", "1")
    clear_settings_cache()
    _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="Paper one on large language models",
        url="https://arxiv.org/abs/2608.11111",
        text="A large language model paper with transformer training results and inference benchmarks.",
        item_kind="research_paper",
    )
    _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="Paper two on retrieval augmented generation",
        url="https://arxiv.org/abs/2608.22222",
        text="A retrieval-augmented generation paper with agent benchmarks.",
        item_kind="research_paper",
    )
    IntelligenceProcessor(db_session).run()
    summary = Summarizer(db_session, provider=CountingMock()).run()
    assert summary.summarized == 1
    assert summary.skipped_cap == 1
    clear_settings_cache()


def test_max_llm_items_prefers_news_over_papers(db_session, monkeypatch) -> None:
    monkeypatch.setenv("MAX_LLM_ITEMS", "1")
    clear_settings_cache()
    news = _article(
        db_session,
        source_name="Google AI Blog",
        title="Google announces a new model release with open weights",
        url="https://blog.google/news-first-sum",
        text="Google released an open-weights large language model checkpoint on Hugging Face.",
    )
    _article(
        db_session,
        source_name="arXiv cs.AI / cs.LG / cs.CL",
        title="A retrieval method for agentic RAG systems",
        url="https://arxiv.org/abs/2608.12121",
        text="We propose a retrieval method for agentic RAG with transformer training results.",
        item_kind="research_paper",
    )
    IntelligenceProcessor(db_session).run()
    summary = Summarizer(db_session, provider=CountingMock()).run()
    db_session.refresh(news)
    assert summary.summarized == 1
    assert summary.skipped_cap == 1
    assert news.processing_status == ProcessingStatus.SUMMARIZED.value
    clear_settings_cache()


def test_ollama_failure_keeps_scored_status(db_session) -> None:
    from app.llm.base import LLMError
    from app.llm.ollama_provider import OllamaProvider

    _article(
        db_session,
        source_name="Google AI Blog",
        title="Open weights large language model for developers",
        url="https://blog.google/ollama-down",
        text="Google released an open-weights large language model for developers.",
    )
    IntelligenceProcessor(db_session).run()

    class Boom(OllamaProvider):
        def generate(self, prompt: str, *, system: str | None = None) -> str:
            raise LLMError("Ollama unreachable at http://127.0.0.1:11434")

    provider = Boom(
        "qwen3:4b",
        base_url="http://127.0.0.1:11434",
        timeout_seconds=1,
        max_retries=0,
    )
    summary = Summarizer(db_session, provider=provider).run()
    assert summary.summarized == 0
    assert summary.errors
    scored = Repository(db_session).list_articles_by_status([ProcessingStatus.SCORED.value])
    assert scored
    assert all(item.processing_status == ProcessingStatus.SCORED.value for item in scored)
    assert all(item.processing_error for item in scored)
