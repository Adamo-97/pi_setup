# -*- coding: utf-8 -*-
"""
Embedding Service
=================
Thin wrapper around Gemini embeddings for the Instagram Reels pipeline.
"""

import logging
from typing import List

logger = logging.getLogger("instagram.embedding")

_gemini = None


def _get_gemini():
    global _gemini
    if _gemini is None:
        from services.gemini_service import GeminiService

        _gemini = GeminiService()
    return _gemini


def embed_text(text: str) -> List[float]:
    """Generate embedding for a text string."""
    return _get_gemini().generate_embedding(text)


def embed_query(text: str) -> List[float]:
    """Alias for embed_text — semantic clarity for search queries."""
    return embed_text(text)


def embed_document(text: str) -> List[float]:
    """Alias for embed_text — semantic clarity for documents."""
    return embed_text(text)


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a batch of texts."""
    return _get_gemini().generate_embeddings_batch(texts)
