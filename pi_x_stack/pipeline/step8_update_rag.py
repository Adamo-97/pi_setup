#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 8: Update RAG
==================
Stores completed pipeline artifacts into the RAG system for future
context. Records feedback and updates embeddings.

Usage:
    python -m pipeline.step8_update_rag --video-id <UUID> [--feedback <text>]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import execute_query
from database.rag_manager import RAGManager
from services.embedding_service import embed_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pipeline.update_rag")


def main(
    video_id: str,
    feedback: str = "",
    feedback_type: str = "auto",
) -> dict:
    """
    Update RAG with completed pipeline data.

    Args:
        video_id: UUID of the published/completed video
        feedback: Optional user feedback text
        feedback_type: positive | negative | neutral | auto

    Returns:
        dict with rag update status
    """
    logger.info("=== Step 8: Update RAG (%s) ===", video_id[:8])

    rag = RAGManager()

    # Fetch all related data
    rows = execute_query(
        """
        SELECT rv.id, rv.script_id, rv.status,
               gs.script_text, gs.content_type,
               v.overall_score, v.scores
        FROM rendered_videos rv
        JOIN generated_scripts gs ON rv.script_id = gs.id
        LEFT JOIN validations v ON v.script_id = gs.id
        WHERE rv.id = %s
        ORDER BY v.created_at DESC
        LIMIT 1
        """,
        (video_id,),
        fetch=True,
    )

    if not rows:
        raise ValueError(f"Video not found: {video_id}")

    row = rows[0]
    script_id = str(row[1])
    video_status = row[2]
    script_text = row[3]
    content_type = row[4]
    overall_score = row[5] or 0
    scores = row[6] or {}

    # Parse scores if string
    if isinstance(scores, str):
        try:
            scores = json.loads(scores)
        except json.JSONDecodeError:
            scores = {}

    updates_done = []

    # 1. Store script embedding for future context
    try:
        embedding = embed_text(script_text[:2000])
        rag.store_embedding(
            text=script_text[:2000],
            embedding=embedding,
            content_type=content_type,
            metadata={
                "script_id": script_id,
                "video_id": video_id,
                "overall_score": overall_score,
                "status": video_status,
            },
        )
        updates_done.append("script_embedding")
        logger.info("Stored script embedding")
    except Exception as e:
        logger.warning("Script embedding failed: %s", e)

    # 2. Store feedback if provided
    if feedback:
        try:
            rag.store_feedback(
                script_id=script_id,
                video_id=video_id,
                feedback_text=feedback,
                feedback_type=feedback_type,
                content_type=content_type,
            )
            updates_done.append("feedback")
            logger.info("Stored feedback: %s (%s)", feedback[:50], feedback_type)
        except Exception as e:
            logger.warning("Feedback storage failed: %s", e)

    # 3. Auto-generate performance feedback based on validation scores
    if overall_score > 0:
        auto_feedback = _generate_auto_feedback(overall_score, scores, content_type)
        try:
            rag.store_feedback(
                script_id=script_id,
                video_id=video_id,
                feedback_text=auto_feedback,
                feedback_type="auto",
                content_type=content_type,
            )
            updates_done.append("auto_feedback")
        except Exception as e:
            logger.warning("Auto feedback storage failed: %s", e)

    # 4. Update pipeline run record
    try:
        execute_query(
            """
            UPDATE pipeline_runs
            SET status = 'completed',
                video_id = %s,
                updated_at = NOW()
            WHERE script_id = %s AND status = 'running'
            """,
            (video_id, script_id),
        )
        updates_done.append("pipeline_run")
    except Exception:
        pass

    result = {
        "video_id": video_id,
        "script_id": script_id,
        "content_type": content_type,
        "updates_done": updates_done,
        "overall_score": overall_score,
    }

    logger.info("RAG updated: %s (%d updates)", video_id[:8], len(updates_done))
    print(json.dumps(result, ensure_ascii=False))
    return result


def _generate_auto_feedback(
    overall_score: float,
    scores: dict,
    content_type: str,
) -> str:
    """Generate automatic feedback based on validation scores."""
    parts = [f"Auto-analysis for {content_type} (score: {overall_score:.0f}/100):"]

    # Identify strengths and weaknesses
    if isinstance(scores, dict):
        strong = [
            (k, v) for k, v in scores.items() if isinstance(v, (int, float)) and v >= 80
        ]
        weak = [
            (k, v) for k, v in scores.items() if isinstance(v, (int, float)) and v < 60
        ]

        if strong:
            parts.append("Strengths: " + ", ".join(f"{k}({v})" for k, v in strong))
        if weak:
            parts.append("Weaknesses: " + ", ".join(f"{k}({v})" for k, v in weak))

    if overall_score >= 85:
        parts.append("High quality — maintain this approach.")
    elif overall_score >= 70:
        parts.append("Acceptable quality — focus on improving weak areas.")
    else:
        parts.append("Below threshold — significant improvements needed.")

    return " ".join(parts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Update RAG system for X/Twitter pipeline"
    )
    parser.add_argument("--video-id", required=True, help="Video UUID")
    parser.add_argument("--feedback", default="", help="Optional feedback text")
    parser.add_argument(
        "--feedback-type",
        choices=["positive", "negative", "neutral", "auto"],
        default="auto",
        help="Feedback type",
    )
    args = parser.parse_args()
    main(
        video_id=args.video_id,
        feedback=args.feedback,
        feedback_type=args.feedback_type,
    )
