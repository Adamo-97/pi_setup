# -*- coding: utf-8 -*-
"""
RAG Manager
===========
Vector search, deduplication, and feedback storage for the X/Twitter pipeline.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from database.connection import execute_query

logger = logging.getLogger("x.rag")


class RAGManager:
    """Manages all RAG operations against the rag_embeddings table."""

    EMBEDDING_DIM = 768

    # ---- Store --------------------------------------------------------

    def store_embedding(
        self,
        source_type: str,
        content_text: str,
        embedding: List[float],
        source_id: Optional[uuid.UUID] = None,
        content_summary: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if len(embedding) != self.EMBEDDING_DIM:
            logger.error(
                "Embedding dim mismatch: got %d, expected %d",
                len(embedding),
                self.EMBEDDING_DIM,
            )
            return None

        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        rows = execute_query(
            """
            INSERT INTO rag_embeddings
                (source_type, source_id, content_text, content_summary, embedding, metadata)
            VALUES (%s, %s, %s, %s, %s::vector, %s)
            RETURNING id
            """,
            (
                source_type,
                str(source_id) if source_id else None,
                content_text,
                content_summary,
                vec_str,
                json.dumps(metadata or {}),
            ),
        )
        if rows:
            logger.info(
                "Stored RAG embedding: %s / %s", source_type, str(rows[0]["id"])[:8]
            )
            return str(rows[0]["id"])
        return None

    # ---- Search -------------------------------------------------------

    def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        threshold: float = 0.3,
        source_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        if source_type:
            params = [vec_str, source_type, vec_str, threshold, vec_str, top_k]
            sql = """
                SELECT id, source_type, source_id, content_text, content_summary, metadata,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM rag_embeddings
                WHERE source_type = %s
                  AND 1 - (embedding <=> %s::vector) > %s
                ORDER BY embedding <=> %s::vector ASC
                LIMIT %s
            """
        else:
            params = [vec_str, vec_str, threshold, vec_str, top_k]
            sql = """
                SELECT id, source_type, source_id, content_text, content_summary, metadata,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM rag_embeddings
                WHERE 1 - (embedding <=> %s::vector) > %s
                ORDER BY embedding <=> %s::vector ASC
                LIMIT %s
            """

        rows = execute_query(sql, tuple(params))
        return rows or []

    # ---- Context helpers -----------------------------------------------

    def get_context_for_content_type(
        self,
        query_embedding: List[float],
        content_type: str,
        top_k: int = 3,
    ) -> str:
        results = self.search_similar(
            query_embedding,
            top_k=top_k,
            source_type="script",
        )
        if not results:
            return "لا يوجد سياق سابق."

        context_parts = []
        for r in results:
            context_parts.append(
                f"- [{r.get('content_summary', 'N/A')}] (تشابه: {r['similarity']:.2f})"
            )
        return "\n".join(context_parts)

    def get_previous_feedback(
        self, content_type: Optional[str] = None, limit: int = 5
    ) -> str:
        sql = """
            SELECT fl.feedback_text, fl.feedback_type, gs.content_type
            FROM feedback_log fl
            LEFT JOIN generated_scripts gs ON fl.script_id = gs.id
            WHERE fl.feedback_text IS NOT NULL
        """
        params: list = []
        if content_type:
            sql += " AND gs.content_type = %s"
            params.append(content_type)
        sql += " ORDER BY fl.created_at DESC LIMIT %s"
        params.append(limit)

        rows = execute_query(sql, tuple(params))
        if not rows:
            return "لا توجد ملاحظات سابقة."

        parts = []
        for r in rows:
            parts.append(f"- [{r['feedback_type']}] {r['feedback_text']}")
        return "\n".join(parts)

    # ---- Dedup ---------------------------------------------------------

    def check_duplicate(
        self,
        query_embedding: List[float],
        threshold: float = 0.85,
    ) -> bool:
        results = self.search_similar(query_embedding, top_k=1, threshold=threshold)
        return len(results) > 0

    # ---- Feedback ------------------------------------------------------

    def store_feedback(
        self,
        script_id: uuid.UUID,
        feedback_type: str,
        feedback_text: str,
        embedding: List[float],
        source: str = "slack",
        video_id: Optional[uuid.UUID] = None,
    ) -> None:
        execute_query(
            """
            INSERT INTO feedback_log (script_id, video_id, feedback_type, feedback_text, source, applied)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            """,
            (
                str(script_id),
                str(video_id) if video_id else None,
                feedback_type,
                feedback_text,
                source,
            ),
            fetch=False,
        )
        self.store_embedding(
            source_type="feedback",
            content_text=feedback_text,
            embedding=embedding,
            source_id=script_id,
            content_summary=f"[{feedback_type}] {feedback_text[:100]}",
        )
        logger.info("Stored feedback for script %s", str(script_id)[:8])
