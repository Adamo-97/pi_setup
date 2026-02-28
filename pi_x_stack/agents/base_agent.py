# -*- coding: utf-8 -*-
"""
Base Agent
==========
Abstract base class for all X/Twitter pipeline agents.
Provides RAG context retrieval, word counting, and script helpers.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from database.rag_manager import RAGManager
from services.gemini_service import GeminiService
from services.embedding_service import embed_text

logger = logging.getLogger("x.agent")


class BaseAgent(ABC):
    """Abstract agent with shared RAG + Gemini utilities."""

    # Fast, punchy delivery: ~180 words per minute
    WORDS_PER_MINUTE = 180

    def __init__(self, name: str):
        self.name = name
        self.gemini = GeminiService()
        self.rag = RAGManager()
        logger.info("Agent initialized: %s", self.name)

    # ================================================================
    # Abstract
    # ================================================================

    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the agent's main task. Subclasses must implement."""
        ...

    # ================================================================
    # RAG helpers
    # ================================================================

    def get_rag_context(
        self,
        query: str,
        content_type: str,
        top_k: int = 3,
    ) -> str:
        """Retrieve relevant RAG context for the query."""
        try:
            results = self.rag.get_context_for_content_type(
                query=query,
                content_type=content_type,
                top_k=top_k,
            )
            if not results:
                return "No previous context available."

            context_parts = []
            for r in results:
                context_parts.append(
                    f"[{r.get('content_type', 'unknown')}] "
                    f"(score: {r.get('similarity', 0):.2f}) "
                    f"{r.get('text', '')[:300]}"
                )
            return "\n---\n".join(context_parts)

        except Exception as e:
            logger.warning("RAG context retrieval failed: %s", e)
            return "RAG context unavailable."

    def get_previous_feedback(self, content_type: str, limit: int = 3) -> str:
        """Get previous feedback for this content type."""
        try:
            feedback = self.rag.get_previous_feedback(
                content_type=content_type, limit=limit
            )
            if not feedback:
                return "No previous feedback."
            parts = [
                f"- [{fb.get('feedback_type', '')}] {fb.get('feedback_text', '')[:200]}"
                for fb in feedback
            ]
            return "\n".join(parts)
        except Exception as e:
            logger.warning("Feedback retrieval failed: %s", e)
            return "Feedback unavailable."

    def check_duplicate(self, text: str, threshold: float = 0.85) -> bool:
        """Check if content is too similar to existing entries."""
        try:
            return self.rag.check_duplicate(text=text, threshold=threshold)
        except Exception as e:
            logger.warning("Duplicate check failed: %s", e)
            return False

    # ================================================================
    # Script helpers
    # ================================================================

    @classmethod
    def estimate_duration(cls, text: str) -> float:
        """
        Estimate voiceover duration from Arabic text.
        Arabic words are typically longer, so slightly slower pacing.
        """
        word_count = cls.count_words(text)
        return (word_count / cls.WORDS_PER_MINUTE) * 60

    @staticmethod
    def count_words(text: str) -> int:
        """Count words, ignoring stage directions like [قطع]."""
        import re

        # Remove stage directions
        clean = re.sub(r"\[.*?\]", "", text)
        # Remove extra whitespace
        words = clean.split()
        return len(words)

    @classmethod
    def target_word_count(cls, duration_seconds: float) -> int:
        """Calculate target word count for a given duration."""
        return int((duration_seconds / 60) * cls.WORDS_PER_MINUTE)

    @staticmethod
    def clean_script(text: str) -> str:
        """Clean script output from LLM — remove markdown, extra whitespace."""
        import re

        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"#+\s", "", text)
        text = re.sub(r"\*{1,2}(.*?)\*{1,2}", r"\1", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # ================================================================
    # Store to RAG
    # ================================================================

    def store_to_rag(
        self,
        text: str,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store generated content in RAG for future reference."""
        try:
            embedding = embed_text(text[:2000])
            self.rag.store_embedding(
                text=text[:2000],
                embedding=embedding,
                content_type=content_type,
                metadata=metadata or {},
            )
            logger.info("Stored to RAG: %s (%d chars)", content_type, len(text))
        except Exception as e:
            logger.warning("RAG store failed: %s", e)
