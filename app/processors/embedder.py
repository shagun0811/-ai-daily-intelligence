"""Text embeddings for semantic duplicate detection. LLM is not used."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import numpy as np

from app.config.logging import STAGE_EMBED, get_logger, log_stage
from app.config.settings import get_settings

logger = get_logger(__name__)

HASH_MODEL_NAME = "hash-ngram-v1"
HASH_DIMENSION = 128


class Embedder(ABC):
    model_name: str

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an (n, d) float32 matrix. Rows are L2-normalized."""


class HashEmbedder(Embedder):
    """CPU-only stand-in. Enough for tests and when sentence-transformers is not installed."""

    model_name = HASH_MODEL_NAME

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, HASH_DIMENSION), dtype=np.float32)
        rows = [_hash_vector(text) for text in texts]
        return np.vstack(rows)


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        log_stage(logger, STAGE_EMBED, "loading model=%s", model_name)
        self._model = SentenceTransformer(model_name, device="cpu")

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, int(self._model.get_sentence_embedding_dimension())), dtype=np.float32)
        vectors = self._model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return np.asarray(vectors, dtype=np.float32)


def get_embedder() -> Embedder:
    settings = get_settings()
    provider = (settings.embedding_provider or "auto").lower()
    if provider == "mock":
        log_stage(logger, STAGE_EMBED, "using HashEmbedder provider=mock")
        return HashEmbedder()
    if provider == "sentence_transformers":
        return SentenceTransformerEmbedder(settings.embedding_model)
    try:
        import sentence_transformers  # noqa: F401

        return SentenceTransformerEmbedder(settings.embedding_model)
    except Exception as exc:  # noqa: BLE001
        log_stage(
            logger,
            STAGE_EMBED,
            "sentence-transformers unavailable (%s); using HashEmbedder",
            type(exc).__name__,
            level=30,
        )
        return HashEmbedder()


def cosine_similarity_matrix(vectors: np.ndarray) -> np.ndarray:
    if vectors.size == 0:
        return np.zeros((0, 0), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    normalized = vectors / np.clip(norms, 1e-12, None)
    return normalized @ normalized.T


def _hash_vector(text: str) -> np.ndarray:
    vec = np.zeros(HASH_DIMENSION, dtype=np.float32)
    tokens = [token for token in text.lower().split() if token]
    if not tokens:
        vec[0] = 1.0
        return vec
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "little") % HASH_DIMENSION
        vec[index] += 1.0
        if len(token) >= 3:
            for i in range(len(token) - 2):
                gram = token[i : i + 3]
                gdigest = hashlib.md5(gram.encode("utf-8")).digest()
                gindex = int.from_bytes(gdigest[:2], "little") % HASH_DIMENSION
                vec[gindex] += 0.25
    norm = float(np.linalg.norm(vec))
    if norm == 0:
        vec[0] = 1.0
        return vec
    return vec / norm
