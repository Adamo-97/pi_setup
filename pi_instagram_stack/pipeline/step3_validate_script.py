#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 3: Validate Script
=======================
Runs the Validator to score and approve/reject the generated script.
Auto-revises up to 2 times if the script fails quality checks.

Usage:
    python -m pipeline.step3_validate_script --script-id <UUID>
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processors.validator import Validator
from processors.writer import Writer
from database.connection import execute_query

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pipeline.validate_script")


def main(script_id: str, auto_revise: bool = True) -> dict:
    """
    Validate an Instagram Reels script.

    Args:
        script_id: UUID of the script to validate
        auto_revise: Whether to auto-revise on failure

    Returns:
        dict with validation result
    """
    logger.info("=== Step 3: Validate Script (%s) ===", script_id[:8])

    # Fetch script from database
    rows = execute_query(
        "SELECT id, script_text, content_type, news_ids FROM generated_scripts WHERE id = %s",
        (script_id,),
        fetch=True,
    )
    if not rows:
        raise ValueError(f"Script not found: {script_id}")

    row = rows[0]
    script_text = row["script_text"]
    content_type = row["content_type"]
    news_ids = row["news_ids"]

    # Get news summaries for accuracy checking
    news_summaries = ""
    if news_ids:
        try:
            news_rows = execute_query(
                "SELECT title, summary FROM news_articles WHERE id = ANY(%s)",
                (news_ids,),
                fetch=True,
            )
            if news_rows:
                news_summaries = "\n".join(f"- {r['title']}: {r['summary'][:200]}" for r in news_rows)
        except Exception:
            pass

    # Run validation
    validator = Validator()

    if auto_revise:
        writer = Writer()
        result = validator.validate_with_revision(
            script_id=script_id,
            script_text=script_text,
            content_type=content_type,
            news_summaries=news_summaries,
            writer_agent=writer,
        )
    else:
        result = validator.run(
            script_id=script_id,
            script_text=script_text,
            content_type=content_type,
            news_summaries=news_summaries,
        )

    status = "APPROVED ✅" if result["approved"] else "REJECTED ❌"
    logger.info(
        "Validation %s: score %d/100, hook: %d",
        status,
        result["overall_score"],
        result["scores"].get("hook_strength", 0),
    )

    if result["critical_issues"]:
        for issue in result["critical_issues"]:
            logger.warning("  Issue: %s", issue)

    # Print for n8n
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate Instagram Reels script")
    parser.add_argument("--script-id", required=True, help="Script UUID")
    parser.add_argument(
        "--no-revise",
        action="store_true",
        help="Disable auto-revision",
    )
    parser.add_argument("--run-id", default=None, help="n8n run ID (ignored, for tracking)")
    args = parser.parse_args()
    main(script_id=args.script_id, auto_revise=not args.no_revise)
