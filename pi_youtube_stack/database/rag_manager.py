# -*- coding: utf-8 -*-
"""
RAG (Retrieval-Augmented Generation) Manager
==============================================
Handles all RAG operations:
  - Storing text + embeddings in pgvector
  - Semantic similarity search for context retrieval
  - Deduplication checks for generated content
  - Feedback ingestion for learning from past mistakes

This module is the "memory" of the AI system. It ensures the AI:
  1. Never generates duplicate content.
  2. Learns from human feedback (approvals, rejections, edits).
  3. Has relevant context from past scripts when generating new ones.
"""

import json
import logging
import uuid
from typing import Optional

from database.connection import get_connection, execute_query

logger = logging.getLogger(__name__)


class RAGManager:
    """
    Manages the RAG embedding store in PostgreSQL (pgvector).

    All embedding generation is delegated to the EmbeddingService
    to keep this class focused on storage and retrieval.
    """

    def __init__(self, embedding_dimension: int = 768):
        """
        Args:
            embedding_dimension: Dimension of embedding vectors (must match model output).
        """
        self.embedding_dimension = embedding_dimension

    # ------------------------------------------------------------------
    # Store operations
    # ------------------------------------------------------------------

    def store_embedding(
        self,
        source_type: str,
        content_text: str,
        embedding: list[float],
        source_id: Optional[uuid.UUID] = None,
        content_summary: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> uuid.UUID:
        """
        Store a text and its embedding vector in the RAG database.

        Args:
            source_type: Category — "script", "feedback", "game", "validation".
            content_text: The original text that was embedded.
            embedding: The embedding vector (list of floats).
            source_id: Optional UUID linking to the source record.
            content_summary: Short summary for display in search results.
            metadata: Additional JSON metadata to store alongside.

        Returns:
            UUID of the newly created embedding record.
        """
        record_id = uuid.uuid4()

        # Validate embedding dimension
        if len(embedding) != self.embedding_dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.embedding_dimension}, "
                f"got {len(embedding)}"
            )

        query = """
            INSERT INTO rag_embeddings
                (id, source_type, source_id, content_text, content_summary, embedding, metadata)
            VALUES
                (%s, %s, %s, %s, %s, %s::vector, %s)
            RETURNING id
        """
        params = (
            str(record_id),
            source_type,
            str(source_id) if source_id else None,
            content_text,
            content_summary,
            f"[{','.join(str(x) for x in embedding)}]",
            json.dumps(metadata or {}, ensure_ascii=False),
        )

        execute_query(query, params, fetch=False)
        logger.info(
            "Stored RAG embedding: type=%s, id=%s, text_len=%d",
            source_type,
            record_id,
            len(content_text),
        )
        return record_id

    # ------------------------------------------------------------------
    # Search / retrieval operations
    # ------------------------------------------------------------------

    def search_similar(
        self,
        query_embedding: list[float],
        source_type: Optional[str] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
    ) -> list[dict]:
        """
        Find the most similar stored texts using cosine similarity.

        Args:
            query_embedding: The embedding vector of the search query.
            source_type: Optional filter by source type.
            top_k: Maximum number of results to return.
            similarity_threshold: Minimum cosine similarity (0-1) to include.

        Returns:
            List of dicts with keys: id, source_type, content_text,
            content_summary, metadata, similarity_score.
        """
        # Build query with optional source_type filter
        type_filter = ""
        params = [
            f"[{','.join(str(x) for x in query_embedding)}]",
        ]

        if source_type:
            type_filter = "AND source_type = %s"
            params.append(source_type)

        params.extend([similarity_threshold, top_k])

        query = f"""
            SELECT
                id,
                source_type,
                source_id,
                content_text,
                content_summary,
                metadata,
                1 - (embedding <=> %s::vector) AS similarity_score
            FROM rag_embeddings
            WHERE 1=1 {type_filter}
              AND 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        # We need the embedding param 3 times in this query
        # Rebuild params correctly
        emb_str = f"[{','.join(str(x) for x in query_embedding)}]"
        if source_type:
            query_params = (
                emb_str,
                source_type,
                emb_str,
                similarity_threshold,
                emb_str,
                top_k,
            )
            query = """
                SELECT
                    id, source_type, source_id, content_text,
                    content_summary, metadata,
                    1 - (embedding <=> %s::vector) AS similarity_score
                FROM rag_embeddings
                WHERE source_type = %s
                  AND 1 - (embedding <=> %s::vector) >= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
        else:
            query_params = (emb_str, emb_str, similarity_threshold, emb_str, top_k)
            query = """
                SELECT
                    id, source_type, source_id, content_text,
                    content_summary, metadata,
                    1 - (embedding <=> %s::vector) AS similarity_score
                FROM rag_embeddings
                WHERE 1 - (embedding <=> %s::vector) >= %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """

        results = execute_query(query, query_params)
        logger.info(
            "RAG search returned %d results (type_filter=%s, threshold=%.2f)",
            len(results) if results else 0,
            source_type,
            similarity_threshold,
        )
        return results or []

    def get_context_for_content_type(
        self,
        query_embedding: list[float],
        content_type: str,
        top_k: int = 5,
    ) -> str:
        """
        Build a formatted context string from RAG results for a specific content type.
        This is what gets injected into the Writer/Validator prompts.

        Args:
            query_embedding: Embedding of the current content query.
            content_type: The content type being generated.
            top_k: Number of similar items to retrieve.

        Returns:
            Formatted string of relevant past content and feedback.
        """
        results = self.search_similar(
            query_embedding=query_embedding,
            top_k=top_k,
            similarity_threshold=0.25,
        )

        if not results:
            return "لا يوجد سياق سابق متاح — هذا أول محتوى من هذا النوع."

        context_parts = []
        for i, result in enumerate(results, 1):
            source = result.get("source_type", "unknown")
            summary = result.get("content_summary", "")
            score = result.get("similarity_score", 0)
            text_preview = (result.get("content_text", ""))[:300]

            context_parts.append(
                f"### سياق #{i} (نوع: {source}, تشابه: {score:.2f})\n"
                f"**ملخص:** {summary}\n"
                f"**مقتطف:** {text_preview}...\n"
            )

        return "\n".join(context_parts)

    def get_previous_feedback(
        self,
        content_type: str,
        limit: int = 5,
    ) -> str:
        """
        Retrieve past feedback for a content type to help the AI learn.

        Args:
            content_type: The content type to get feedback for.
            limit: Maximum number of feedback entries.

        Returns:
            Formatted string of past feedback.
        """
        query = """
            SELECT
                fl.feedback_type, fl.feedback_text, fl.created_at,
                gs.title, gs.content_type
            FROM feedback_log fl
            LEFT JOIN generated_scripts gs ON fl.script_id = gs.id
            WHERE gs.content_type = %s OR gs.content_type IS NULL
            ORDER BY fl.created_at DESC
            LIMIT %s
        """
        results = execute_query(query, (content_type, limit))

        if not results:
            return "لا توجد ملاحظات سابقة — لم يتم إنتاج محتوى مشابه من قبل."

        feedback_parts = []
        for fb in results:
            fb_type = fb.get("feedback_type", "")
            fb_text = fb.get("feedback_text", "")
            fb_title = fb.get("title", "")
            feedback_parts.append(f"- [{fb_type}] عن '{fb_title}': {fb_text}")

        return "\n".join(feedback_parts)

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def check_duplicate(
        self,
        query_embedding: list[float],
        threshold: float = 0.85,
    ) -> Optional[dict]:
        """
        Check if highly similar content already exists (deduplication).

        Args:
            query_embedding: Embedding of the content to check.
            threshold: Similarity threshold above which content is considered duplicate.

        Returns:
            The duplicate record if found, else None.
        """
        results = self.search_similar(
            query_embedding=query_embedding,
            source_type="script",
            top_k=1,
            similarity_threshold=threshold,
        )

        if results:
            logger.warning(
                "Potential duplicate detected! Similarity: %.3f — ID: %s",
                results[0]["similarity_score"],
                results[0]["id"],
            )
            return results[0]
        return None

    # ------------------------------------------------------------------
    # Feedback ingestion
    # ------------------------------------------------------------------

    def store_feedback(
        self,
        script_id: uuid.UUID,
        feedback_type: str,
        feedback_text: str,
        embedding: list[float],
        source: str = "slack",
    ) -> uuid.UUID:
        """
        Store human feedback and its embedding for future learning.

        Args:
            script_id: UUID of the script being reviewed.
            feedback_type: "approval", "rejection", "edit", "note".
            feedback_text: The actual feedback content.
            embedding: Embedding of the feedback text.
            source: Where the feedback came from.

        Returns:
            UUID of the feedback record.
        """
        feedback_id = uuid.uuid4()

        # Store in feedback_log table
        fb_query = """
            INSERT INTO feedback_log (id, script_id, feedback_type, feedback_text, source)
            VALUES (%s, %s, %s, %s, %s)
        """
        execute_query(
            fb_query,
            (str(feedback_id), str(script_id), feedback_type, feedback_text, source),
            fetch=False,
        )

        # Store embedding for RAG retrieval
        self.store_embedding(
            source_type="feedback",
            content_text=feedback_text,
            embedding=embedding,
            source_id=feedback_id,
            content_summary=f"[{feedback_type}] {feedback_text[:100]}",
            metadata={
                "script_id": str(script_id),
                "feedback_type": feedback_type,
            },
        )

        logger.info("Stored feedback: type=%s, script=%s", feedback_type, script_id)
        return feedback_id
