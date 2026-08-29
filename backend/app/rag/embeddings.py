"""Local embeddings via sentence-transformers (no API key, fully offline).

The model (default all-MiniLM-L6-v2 -> 384 dims) is loaded lazily and cached
for the process. Vectors are L2-normalized so cosine distance in pgvector is
well-behaved.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_model() -> Any:
    from sentence_transformers import SentenceTransformer

    logger.info("loading embedding model %s", settings.embedding_model)
    return SentenceTransformer(settings.embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts into normalized float vectors."""
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
