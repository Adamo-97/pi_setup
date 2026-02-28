#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update RAG
============
Processes new feedback and content into the RAG database.
Should be run periodically or after each approval/rejection cycle.

This script:
  1. Finds unprocessed feedback entries
  2. Generates embeddings for each
  3. Stores them in the RAG vector store
  4. Marks feedback as processed

Usage (n8n Execute Command):
    python3 scripts/update_rag.py
    python3 scripts/update_rag.py --feedback-text "النص كان طويل جداً" --script-id <uuid> --type rejection

Output (stdout JSON):
    {
        "success": true,
        "processed_count": 3,
        "message": "RAG database updated successfully."
    }
"""

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database.connection import execute_query
from database.rag_manager import RAGManager
from services.embedding_service import embed_document

# ---------------------------------------------------------------------------
# Logging — stderr only
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("update_rag")


def process_unprocessed_feedback() -> int:
    """
    Find and process all feedback entries not yet added to RAG.

    Returns:
        Number of entries processed.
    """
    rag = RAGManager()
    count = 0

    # Get unprocessed feedback
    feedback_entries = execute_query(
        """
        SELECT fl.*, gs.title as script_title, gs.content_type
        FROM feedback_log fl
        LEFT JOIN generated_scripts gs ON fl.script_id = gs.id
        WHERE fl.applied = FALSE
        ORDER BY fl.created_at ASC
        """
    )

    if not feedback_entries:
        logger.info("No unprocessed feedback found.")
        return 0

    for entry in feedback_entries:
        try:
            feedback_text = entry.get("feedback_text", "")
            if not feedback_text:
                continue

            # Build context-rich text for better embeddings
            context_text = (
                f"[{entry.get('feedback_type', 'unknown')}] "
                f"على '{entry.get('script_title', 'N/A')}' "
                f"(نوع: {entry.get('content_type', 'N/A')}): "
                f"{feedback_text}"
            )

            # Generate embedding and store in RAG
            embedding = embed_document(context_text)
            rag.store_embedding(
                source_type="feedback",
                content_text=context_text,
                embedding=embedding,
                source_id=uuid.UUID(str(entry["id"])),
                content_summary=f"[{entry.get('feedback_type', '')}] {feedback_text[:100]}",
                metadata={
                    "script_id": str(entry.get("script_id", "")),
                    "feedback_type": entry.get("feedback_type", ""),
                    "content_type": entry.get("content_type", ""),
                },
            )

            # Mark as processed
            execute_query(
                "UPDATE feedback_log SET applied = TRUE WHERE id = %s",
                (str(entry["id"]),),
                fetch=False,
            )

            count += 1
            logger.info(
                "Processed feedback: %s (%s)",
                str(entry["id"])[:8],
                entry.get("feedback_type", ""),
            )

        except Exception as exc:
            logger.error(
                "Failed to process feedback %s: %s",
                str(entry.get("id", "?"))[:8],
                exc,
            )

    return count


def add_manual_feedback(
    feedback_text: str,
    script_id: str,
    feedback_type: str = "note",
) -> bool:
    """
    Manually add a feedback entry and process it into RAG immediately.

    Args:
        feedback_text: The feedback content.
        script_id: UUID of the related script.
        feedback_type: "approval", "rejection", "edit", "note".

    Returns:
        True if successfully added and processed.
    """
    rag = RAGManager()

    try:
        # Generate embedding
        embedding = embed_document(feedback_text)

        # Store feedback with embedding
        rag.store_feedback(
            script_id=uuid.UUID(script_id),
            feedback_type=feedback_type,
            feedback_text=feedback_text,
            embedding=embedding,
            source="manual",
        )

        logger.info("Manual feedback added and processed: type=%s", feedback_type)
        return True

    except Exception as exc:
        logger.error("Failed to add manual feedback: %s", exc)
        return False


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Update the RAG database with new feedback and content."
    )
    parser.add_argument(
        "--feedback-text",
        type=str,
        help="Manual feedback text to add.",
    )
    parser.add_argument(
        "--script-id",
        type=str,
        help="Script UUID for manual feedback.",
    )
    parser.add_argument(
        "--type",
        type=str,
        default="note",
        choices=["approval", "rejection", "edit", "note"],
        help="Feedback type (default: note).",
    )

    args = parser.parse_args()

    try:
        if args.feedback_text:
            # Manual feedback mode
            if not args.script_id:
                print(
                    json.dumps(
                        {
                            "success": False,
                            "error": "--script-id is required with --feedback-text.",
                        }
                    )
                )
                sys.exit(1)

            success = add_manual_feedback(
                feedback_text=args.feedback_text,
                script_id=args.script_id,
                feedback_type=args.type,
            )

            result = {
                "success": success,
                "processed_count": 1 if success else 0,
                "message": (
                    "Manual feedback added." if success else "Failed to add feedback."
                ),
            }

        else:
            # Batch processing mode — process all unprocessed feedback
            count = process_unprocessed_feedback()
            result = {
                "success": True,
                "processed_count": count,
                "message": f"RAG database updated: {count} feedback entries processed.",
            }

    except Exception as exc:
        logger.exception("Fatal error in update_rag")
        result = {"success": False, "error": str(exc)}

    # Print clean JSON to stdout for n8n
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
