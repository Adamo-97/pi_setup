#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 2: Generate Script
=======================
Uses the WriterAgent to generate an Instagram Reels script from scraped news.
Picks top unused articles and generates an Arabic gaming/hardware script.

Usage:
    python -m pipeline.step2_generate_script [--type trending_news]
                                              [--duration 45]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.writer_agent import WriterAgent
from database.connection import execute_query
from services.news_scraper import NewsScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pipeline.generate_script")


def main(content_type: str = "trending_news", duration: float = 45.0) -> dict:
    """
    Generate an Instagram Reels script.

    Args:
        content_type: trending_news | game_spotlight | hardware_spotlight | trailer_reaction
        duration: Target video duration in seconds

    Returns:
        dict with script_id, script_text, word_count, etc.
    """
    logger.info("=== Step 2: Generate Script (%s, %.0fs) ===", content_type, duration)

    # Get unused news articles
    scraper = NewsScraper()
    articles = scraper.get_unused_articles(limit=5)

    if not articles and content_type == "trending_news":
        logger.warning(
            "No unused articles found. Run step1 first or switching to general."
        )

    # Convert to dicts for writer
    article_dicts = [
        {
            "id": str(a.get("id", "")),
            "title": a.get("title", ""),
            "summary": a.get("summary", ""),
            "source": a.get("source", ""),
            "source_url": a.get("source_url", ""),
        }
        for a in articles
    ]

    # Generate script
    writer = WriterAgent()
    result = writer.run(
        content_type=content_type,
        news_articles=article_dicts,
        target_duration=duration,
        trigger_source="pipeline",
    )

    # Mark used articles
    if article_dicts:
        article_ids = [a["id"] for a in article_dicts if a["id"]]
        if article_ids:
            scraper.mark_articles_used(article_ids)

    # Save script to file for reference
    output_dir = Path("output/scripts")
    output_dir.mkdir(parents=True, exist_ok=True)
    script_file = output_dir / f"{result['script_id'][:8]}.txt"
    script_file.write_text(result["script_text"], encoding="utf-8")

    logger.info(
        "Script generated: %s (%d words, ~%.0fs) → %s",
        result["script_id"][:8],
        result["word_count"],
        result["estimated_duration"],
        script_file.name,
    )

    # Print for n8n to capture
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Instagram Reels script")
    parser.add_argument("--type", default="trending_news", help="Content type")
    parser.add_argument(
        "--duration", type=float, default=45.0, help="Target duration (s)"
    )
    args = parser.parse_args()
    main(content_type=args.type, duration=args.duration)
