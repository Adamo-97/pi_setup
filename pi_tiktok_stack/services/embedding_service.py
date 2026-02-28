# -*- coding: utf-8 -*-
"""
Embedding Service
=================
Thin convenience wrapper for embedding operations.
"""

from typing import List

_gemini = None


def _get_gemini():
    global _gemini
    if _gemini is None:
        from services.gemini_service import GeminiService

        _gemini = GeminiService()
    return _gemini


def embed_text(text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> List[float]:
    return _get_gemini().generate_embedding(text, task_type)


def embed_query(text: str) -> List[float]:
    return embed_text(text, task_type="RETRIEVAL_QUERY")


def embed_document(text: str) -> List[float]:
    return embed_text(text, task_type="RETRIEVAL_DOCUMENT")


def embed_batch(texts: List[str]) -> List[List[float]]:
    return _get_gemini().generate_embeddings_batch(texts)
