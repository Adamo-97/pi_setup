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


def main(
    script_id: str,
    auto_revise: bool = True,
    run_id: str = "",
) -> dict:
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
    news_articles = []
    if news_ids:
        try:
            news_rows = execute_query(
                "SELECT id, title, summary, source, source_url FROM news_articles WHERE id = ANY(%s)",
                (news_ids,),
                fetch=True,
            )
            if news_rows:
                news_summaries = "\n".join(f"- {r['title']}: {r['summary'][:200]}" for r in news_rows)
                news_articles = [
                    {
                        "id": str(r.get("id", "")),
                        "title": r.get("title", ""),
                        "summary": r.get("summary", ""),
                        "source": r.get("source", ""),
                        "source_url": r.get("source_url", ""),
                    }
                    for r in news_rows
                ]
        except Exception:
            pass

    state = _read_pipeline_state(run_id)
    target_duration = _safe_float(state.get("estimated_duration_seconds"), 45.0)
    planned_topic = state.get("proposed_topic", "")
    planned_angle = state.get("proposed_angle", "")
    planned_visual_hook = state.get("visual_hook", "")

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
            news_articles=news_articles,
            target_duration=target_duration,
            planned_topic=planned_topic,
            planned_angle=planned_angle,
            planned_visual_hook=planned_visual_hook,
        )
    else:
        result = validator.run(
            script_id=script_id,
            script_text=script_text,
            content_type=content_type,
            news_summaries=news_summaries,
            target_duration=target_duration,
            planned_topic=planned_topic,
            planned_angle=planned_angle,
            planned_visual_hook=planned_visual_hook,
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


def _read_pipeline_state(run_id: str) -> dict:
    if not run_id:
        return {}
    state_path = Path(f"/tmp/pipeline_state_{run_id}.json")
    if not state_path.is_file():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
    main(script_id=args.script_id, auto_revise=not args.no_revise, run_id=args.run_id or "")
