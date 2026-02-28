# -*- coding: utf-8 -*-
"""
Base Agent
===========
Abstract base class for all AI agents in the stack.
Provides shared functionality:
  - Gemini service integration
  - RAG context retrieval
  - Logging setup
  - JSON output formatting
  - Error handling patterns
"""

import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from services.gemini_service import GeminiService
from services.embedding_service import embed_query
from database.rag_manager import RAGManager
from database.connection import execute_query

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all AI agents.

    Subclasses must implement:
        - execute(**kwargs) -> dict: The core agent logic.
        - agent_name (property): Human-readable agent name.
    """

    def __init__(self):
        """Initialize shared services."""
        self.gemini = GeminiService()
        self.rag = RAGManager()
        self._run_id: Optional[str] = None

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable name for this agent."""
        ...

    @abstractmethod
    def execute(self, **kwargs) -> dict:
        """
        Execute the agent's core task.

        Returns:
            Dict containing the agent's output data.
        """
        ...

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

    def get_rag_context(
        self,
        query_text: str,
        content_type: Optional[str] = None,
        top_k: int = 5,
    ) -> str:
        """
        Retrieve relevant RAG context for the given query.

        Args:
            query_text: Text to search for similar content.
            content_type: Optional content type filter.
            top_k: Number of results to retrieve.

        Returns:
            Formatted context string for injection into prompts.
        """
        try:
            query_embedding = embed_query(query_text)
            context = self.rag.get_context_for_content_type(
                query_embedding=query_embedding,
                content_type=content_type or "",
                top_k=top_k,
            )
            return context
        except Exception as exc:
            logger.warning(
                "[%s] RAG context retrieval failed: %s — using empty context.",
                self.agent_name,
                exc,
            )
            return "لا يوجد سياق متاح حالياً."

    def get_previous_feedback(self, content_type: str) -> str:
        """
        Get past feedback for a content type from the RAG DB.

        Args:
            content_type: Content type ID.

        Returns:
            Formatted feedback string.
        """
        try:
            return self.rag.get_previous_feedback(content_type)
        except Exception as exc:
            logger.warning("[%s] Feedback retrieval failed: %s", self.agent_name, exc)
            return "لا توجد ملاحظات سابقة."

    def check_duplicate(self, text: str) -> Optional[dict]:
        """
        Check if content is too similar to existing content.

        Args:
            text: The generated text to check.

        Returns:
            Duplicate record if found, else None.
        """
        try:
            from services.embedding_service import embed_document

            embedding = embed_document(text)
            return self.rag.check_duplicate(embedding)
        except Exception as exc:
            logger.warning("[%s] Duplicate check failed: %s", self.agent_name, exc)
            return None

    def store_in_rag(
        self,
        text: str,
        source_type: str,
        source_id: Optional[uuid.UUID] = None,
        summary: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Store generated content in the RAG database for future reference.

        Args:
            text: The text content to store.
            source_type: "script" | "validation" | "feedback".
            source_id: UUID of the source record.
            summary: Short summary for display.
            metadata: Additional metadata dict.
        """
        try:
            from services.embedding_service import embed_document

            embedding = embed_document(text)
            self.rag.store_embedding(
                source_type=source_type,
                content_text=text,
                embedding=embedding,
                source_id=source_id,
                content_summary=summary,
                metadata=metadata,
            )
            logger.info(
                "[%s] Stored content in RAG (type=%s, len=%d)",
                self.agent_name,
                source_type,
                len(text),
            )
        except Exception as exc:
            logger.error("[%s] Failed to store in RAG: %s", self.agent_name, exc)

    def format_games_data(self, games: list[dict]) -> str:
        """
        Format game data into a readable string for prompt injection.

        Args:
            games: List of game dicts from the database.

        Returns:
            Formatted string with game details.
        """
        if not games:
            return "لا توجد بيانات ألعاب متوفرة."

        parts = []
        for i, game in enumerate(games, 1):
            platforms = game.get("platforms", [])
            if isinstance(platforms, str):
                try:
                    platforms = json.loads(platforms)
                except json.JSONDecodeError:
                    platforms = [platforms]

            genres = game.get("genres", [])
            if isinstance(genres, str):
                try:
                    genres = json.loads(genres)
                except json.JSONDecodeError:
                    genres = [genres]

            arabic = game.get("arabic_support", {})
            if isinstance(arabic, str):
                try:
                    arabic = json.loads(arabic)
                except json.JSONDecodeError:
                    arabic = {}

            part = (
                f"### {i}. {game.get('title', 'Unknown')}\n"
                f"- **تاريخ الإصدار:** {game.get('release_date', 'غير محدد')}\n"
                f"- **المنصات:** {', '.join(platforms) if platforms else 'غير محدد'}\n"
                f"- **النوع:** {', '.join(genres) if genres else 'غير محدد'}\n"
                f"- **التقييم:** {game.get('rating', 'N/A')}/5 | Metacritic: {game.get('metacritic', 'N/A')}\n"
                f"- **Game Pass:** {'نعم ✅' if game.get('gamepass') else 'لا ❌'}\n"
                f"- **دعم العربية:** {'نعم' if arabic.get('has_arabic') else 'لا'}"
                f"{' (' + arabic.get('arabic_type', '') + ')' if arabic.get('has_arabic') else ''}\n"
                f"- **السعر:** {game.get('price', 'غير متوفر')}\n"
                f"- **الوصف:** {(game.get('description', '') or '')[:200]}\n"
            )
            parts.append(part)

        return "\n".join(parts)

    def count_arabic_words(self, text: str) -> int:
        """Count words in Arabic text (approximate)."""
        return len(text.split())

    def estimate_duration(self, word_count: int, wpm: int = 130) -> float:
        """
        Estimate video duration from word count.
        Arabic reading speed is ~130 words per minute for narration.

        Args:
            word_count: Number of words.
            wpm: Words per minute (default: 130 for Arabic narration).

        Returns:
            Estimated duration in minutes.
        """
        return round(word_count / wpm, 1)

    def log_run(
        self,
        content_type: str,
        trigger_source: str = "manual",
    ) -> str:
        """
        Create a pipeline run record in the database.

        Args:
            content_type: Content type being produced.
            trigger_source: "schedule" | "manual" | "n8n".

        Returns:
            Pipeline run UUID string.
        """
        run_id = str(uuid.uuid4())
        try:
            execute_query(
                """
                INSERT INTO pipeline_runs (id, content_type, trigger_source, status)
                VALUES (%s, %s, %s, 'started')
                """,
                (run_id, content_type, trigger_source),
                fetch=False,
            )
            self._run_id = run_id
        except Exception as exc:
            logger.error("Failed to log pipeline run: %s", exc)
        return run_id

    def update_run_status(
        self, run_id: str, status: str, error: Optional[str] = None
    ) -> None:
        """Update the status of a pipeline run."""
        try:
            if status in ("completed", "failed"):
                execute_query(
                    """
                    UPDATE pipeline_runs
                    SET status = %s, error_message = %s, completed_at = NOW()
                    WHERE id = %s
                    """,
                    (status, error, run_id),
                    fetch=False,
                )
            else:
                execute_query(
                    "UPDATE pipeline_runs SET status = %s WHERE id = %s",
                    (status, run_id),
                    fetch=False,
                )
        except Exception as exc:
            logger.error("Failed to update run status: %s", exc)
