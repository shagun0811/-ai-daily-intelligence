"""Collectors — RSS, arXiv, and webpage fetchers."""

from app.collectors.source_manager import CollectionSummary, SourceManager, collector_for

__all__ = ["CollectionSummary", "SourceManager", "collector_for"]
