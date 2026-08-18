"""Five-level duplicate grouping. Matches are clustered, not deleted."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

import numpy as np

from app.config.logging import STAGE_DEDUP, get_logger, log_stage
from app.database.enums import ClusterMemberRole, CredibilityTier
from app.database.models import Article
from app.processors.embedder import cosine_similarity_matrix
from app.processors.normalizer import normalize_title_for_dedup
from app.utils.urls import canonicalize_url

logger = get_logger(__name__)

_TIER_RANK = {
    CredibilityTier.TIER_1.value: 0,
    CredibilityTier.TIER_2.value: 1,
    CredibilityTier.TIER_3.value: 2,
}


@dataclass(frozen=True)
class DuplicatePair:
    left_id: int
    right_id: int
    reason: str
    score: float


class UnionFind:
    def __init__(self, ids: list[int]) -> None:
        self.parent = {item: item for item in ids}

    def find(self, item: int) -> int:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left

    def components(self) -> dict[int, list[int]]:
        groups: dict[int, list[int]] = defaultdict(list)
        for item in self.parent:
            groups[self.find(item)].append(item)
        return dict(groups)


def title_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def choose_primary(articles: list[Article]) -> Article:
    """Prefer higher-credibility sources; do not assume tier 1 is always most important."""

    def sort_key(article: Article) -> tuple:
        tier = _TIER_RANK.get(getattr(article.source, "credibility_tier", ""), 9)
        kind_rank = 0 if article.item_kind == "research_paper" else 1
        length = -len(article.cleaned_text or "")
        return (tier, kind_rank, length, article.id)

    return sorted(articles, key=sort_key)[0]


def find_duplicate_pairs(
    articles: list[Article],
    *,
    vectors: np.ndarray | None,
    title_threshold: float,
    semantic_threshold: float,
) -> list[DuplicatePair]:
    """Level 1 exact URL, 2 canonical URL, 3 title, 4 title similarity, 5 semantic cosine."""
    pairs: list[DuplicatePair] = []
    seen: set[tuple[int, int]] = set()

    def add(left: Article, right: Article, reason: str, score: float) -> None:
        key = (min(left.id, right.id), max(left.id, right.id))
        if key in seen or left.id == right.id:
            return
        seen.add(key)
        pairs.append(DuplicatePair(left.id, right.id, reason, score))

    by_url: dict[str, list[Article]] = defaultdict(list)
    by_canonical: dict[str, list[Article]] = defaultdict(list)
    by_title: dict[str, list[Article]] = defaultdict(list)
    for article in articles:
        by_url[article.url].append(article)
        canonical = article.canonical_url or canonicalize_url(article.url)
        if canonical:
            by_canonical[canonical].append(article)
        title_key = article.normalized_title or normalize_title_for_dedup(article.title)
        if title_key:
            by_title[title_key].append(article)

    for group in by_url.values():
        _all_pairs(group, "exact_url", 1.0, add)
    for group in by_canonical.values():
        _all_pairs(group, "canonical_url", 1.0, add)
    for group in by_title.values():
        _all_pairs(group, "normalized_title", 1.0, add)

    n = len(articles)
    for i in range(n):
        left_title = articles[i].normalized_title or normalize_title_for_dedup(articles[i].title)
        for j in range(i + 1, n):
            right_title = articles[j].normalized_title or normalize_title_for_dedup(articles[j].title)
            ratio = title_similarity(left_title, right_title)
            if ratio >= title_threshold:
                add(articles[i], articles[j], "title_similarity", ratio)

    if vectors is not None and len(vectors) == n and n > 1:
        matrix = cosine_similarity_matrix(vectors)
        for i in range(n):
            for j in range(i + 1, n):
                score = float(matrix[i, j])
                if score >= semantic_threshold:
                    add(articles[i], articles[j], "semantic", score)

    log_stage(logger, STAGE_DEDUP, "pairs=%s articles=%s", len(pairs), n)
    return pairs


def cluster_articles(articles: list[Article], pairs: list[DuplicatePair]) -> list[list[Article]]:
    if not articles:
        return []
    by_id = {article.id: article for article in articles}
    forest = UnionFind([article.id for article in articles])
    for pair in pairs:
        forest.union(pair.left_id, pair.right_id)
    clusters: list[list[Article]] = []
    for members in forest.components().values():
        clusters.append([by_id[item_id] for item_id in members])
    return clusters


def _all_pairs(group: list[Article], reason: str, score: float, add) -> None:
    for i, left in enumerate(group):
        for right in group[i + 1 :]:
            add(left, right, reason, score)
