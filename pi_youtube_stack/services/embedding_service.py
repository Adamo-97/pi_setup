# -*- coding: utf-8 -*-
"""
Embedding Service
==================
Thin convenience wrapper around GeminiService.generate_embedding().
Provides a clean interface for RAG operations to generate embeddings
without importing the full Gemini service directly.
"""

import logging
from typing import Optional

from services.gemini_service import GeminiService

logger = logging.getLogger(__name__)

# Module-level singleton
_gemini_service: Optional[GeminiService] = None


def _get_service() -> GeminiService:
    """Lazy-initialize the Gemini service singleton."""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service


def embed_text(text: str, task_type: str = "retrieval_document") -> list[float]:
    """
    Generate an embedding vector for the given text.

    Args:
        text: Text to embed.
        task_type: "retrieval_document" for storing, "retrieval_query" for searching.

    Returns:
        List of floats (embedding vector).
    """
    return _get_service().generate_embedding(text, task_type)


def embed_query(text: str) -> list[float]:
    """
    Generate an embedding optimized for search queries.

    Args:
        text: The search query text.

    Returns:
        Embedding vector.
    """
    return embed_text(text, task_type="retrieval_query")


def embed_document(text: str) -> list[float]:
    """
    Generate an embedding optimized for document storage.

    Args:
        text: The document text.

    Returns:
        Embedding vector.
    """
    return embed_text(text, task_type="retrieval_document")


def embed_batch(
    texts: list[str], task_type: str = "retrieval_document"
) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.

    Args:
        texts: List of texts.
        task_type: Embedding task type.

    Returns:
        List of embedding vectors.
    """
    return _get_service().generate_embeddings_batch(texts, task_type)
