#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comment Handler — processes human comments from Mattermost and stores in RAG.

Usage (called by n8n when the comment webhook fires):
  cd /home/node/instagram_stack && python -m pipeline.comment_handler \
      --run-id <UUID> --gate <N> --comment "your comment text"

The comment is:
  1. Stored in the feedback_log table
  2. Embedded and stored in RAG for future AI learning
  3. Associated with the current pipeline run's script_id (if available)
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
logger = logging.getLogger("pipeline.comment_handler")


def main(run_id: str, gate: int, comment: str, feedback_type: str = "comment") -> dict:
    """
    Process a human comment and store it in the RAG system.

    Args:
        run_id: Pipeline run ID
        gate: Gate number where the comment was made
        comment: The comment text
        feedback_type: Type of feedback (comment, correction, suggestion)

    Returns:
        dict with status and details
    """
    logger.info("=== Comment Handler (run=%s, gate=%d) ===", run_id[:8], gate)
    logger.info("Comment: %s", comment[:100])

    gate_names = {
        0: "plan", 1: "news", 2: "script", 3: "voiceover",
        4: "footage", 5: "video", 6: "publish",
    }
    gate_name = gate_names.get(gate, f"gate_{gate}")

    # Try to find the script_id and video_id from the pipeline state
    script_id = None
    video_id = None
    try:
        state_file = Path(f"/tmp/pipeline_state_{run_id}.json")
        if state_file.is_file():
            state = json.loads(state_file.read_text())
            script_id = state.get("script_id")
            video_id = state.get("video_id")
    except Exception as e:
        logger.warning("Could not read pipeline state: %s", e)

    # Store in feedback_log
    try:
        execute_query(
            """INSERT INTO feedback_log
                (script_id, video_id, feedback_type, feedback_text, source, applied)
            VALUES (%s, %s, %s, %s, 'mattermost', FALSE)""",
            (script_id, video_id, feedback_type, comment),
            fetch=False,
        )
        logger.info("Stored comment in feedback_log")
    except Exception as e:
        logger.warning("Failed to store in feedback_log: %s", e)

    # Embed and store in RAG for future learning
    rag = RAGManager()
    enriched_comment = (
        f"[{feedback_type}] [gate:{gate_name}] [run:{run_id[:8]}] "
        f"{comment}"
    )

    try:
        embedding = embed_text(enriched_comment[:500])
        rag.store_embedding(
            source_type="feedback",
            content_text=enriched_comment,
            embedding=embedding,
            metadata={
                "run_id": run_id,
                "gate": gate,
                "gate_name": gate_name,
                "script_id": script_id,
                "video_id": video_id,
                "feedback_type": feedback_type,
                "source": "mattermost_comment",
            },
            content_summary=f"[{feedback_type}] {comment[:100]}",
        )
        logger.info("Stored comment embedding in RAG")
    except Exception as e:
        logger.warning("Failed to store RAG embedding: %s", e)

    result = {
        "status": "stored",
        "run_id": run_id,
        "gate": gate,
        "gate_name": gate_name,
        "comment_length": len(comment),
        "script_id": script_id,
        "video_id": video_id,
    }

    logger.info("Comment processed: gate=%s, length=%d", gate_name, len(comment))
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process human comment from Mattermost")
    parser.add_argument("--run-id", required=True, help="Pipeline run ID")
    parser.add_argument("--gate", type=int, required=True, help="Gate number (0-6)")
    parser.add_argument("--comment", required=True, help="Comment text")
    parser.add_argument(
        "--feedback-type",
        choices=["comment", "correction", "suggestion", "instruction"],
        default="comment",
    )
    args = parser.parse_args()
    main(
        run_id=args.run_id,
        gate=args.gate,
        comment=args.comment,
        feedback_type=args.feedback_type,
    )
