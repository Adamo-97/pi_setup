#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 1: Scrape News
===================
Scrapes trending gaming & hardware news from RSS, Google News, and Reddit.
Stores new articles in the database for script generation.

Usage:
    python -m pipeline.step1_scrape_news [--source all|rss|google|reddit]
"""

import argparse
import ast
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings
from database.connection import execute_query
from services.news_scraper import NewsScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pipeline.scrape_news")


def _parse_game_slugs(games: str) -> list[str]:
    """Parse game slugs from CSV, JSON list, or Python list repr."""
    text = (games or "").strip()
    if not text:
        return []

    raw_items = []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                raw_items = parsed
        except (ValueError, SyntaxError):
            raw_items = []

    if not raw_items:
        raw_items = text.split(",")

    normalized = []
    for item in raw_items:
        slug = str(item).strip().strip("'\"[](){}")
        slug = slug.lower().replace("_", "-")
        slug = re.sub(r"[^a-z0-9-]+", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")
        if slug:
            normalized.append(slug)

    return list(dict.fromkeys(normalized))


def main(source: str = "all", topic: str = "", games: str = "", angle: str = "") -> dict:
    """
    Scrape news from specified sources.

    Args:
        source: 'all', 'rss', 'google', or 'reddit'
        topic: optional topic to focus the scraping on
        games: optional comma-separated game slugs from Gate 0 plan

    Returns:
        dict with counts and status
    """
    settings = get_settings()
    scraper = NewsScraper()

    game_slugs = _parse_game_slugs(games)
    logger.info(
        "=== Step 1: Scrape News (source: %s, topic: %s, games: %s) ===",
        source,
        topic or "all",
        ",".join(game_slugs) if game_slugs else "none",
    )

    # Record pipeline run
    run_id = _start_pipeline_run("scrape_news")

    try:
        if source == "rss":
            articles = scraper.scrape_rss()
        elif source == "google":
            articles = scraper.scrape_google_news(query=f"{topic} gaming" if topic else "gaming hardware news")
        elif source == "reddit":
            articles = scraper.scrape_reddit()
        elif source == "rawg":
            articles = scraper.scrape_rawg(topic=topic, game_slugs=game_slugs)
        else:
            articles = scraper.scrape_all(topic=topic, game_slugs=game_slugs, angle=angle)

        # Store in database
        stored = scraper.store_articles(articles)

        # Count available unused articles
        unused = scraper.get_unused_articles(limit=100)

        # Build detailed article summaries for gate notification
        article_details = []
        for a in articles[:10]:
            article_details.append({
                "title": a.get("title", "N/A"),
                "source": a.get("source", "unknown"),
                "summary": (a.get("summary", "") or "")[:200],
                "source_url": a.get("source_url", ""),
            })

        result = {
            "scraped": len(articles),
            "stored": stored,
            "total_unused": len(unused),
            "articles": article_details,
            "source": source,
            "topic": topic,
            "game_slugs": game_slugs,
            "timestamp": datetime.now().isoformat(),
        }

        _finish_pipeline_run(run_id, "completed", result)
        logger.info(
            "Scraping complete: %d scraped, %d new, %d total unused",
            len(articles),
            stored,
            len(unused),
        )
        return result

    except Exception as e:
        _finish_pipeline_run(run_id, "failed", {"error": str(e)})
        logger.error("Scraping failed: %s", e)
        raise


def _start_pipeline_run(step: str) -> str:
    """Record pipeline run start."""
    import uuid

    run_id = str(uuid.uuid4())
    try:
        execute_query(
            """
            INSERT INTO pipeline_runs (id, content_type, status, step)
            VALUES (%s, 'trending_news', 'running', %s)
            """,
            (run_id, step),
        )
    except Exception:
        pass
    return run_id


def _finish_pipeline_run(run_id: str, status: str, details: dict = None):
    """Update pipeline run status."""
    try:
        execute_query(
            "UPDATE pipeline_runs SET status = %s, updated_at = NOW() WHERE id = %s",
            (status, run_id),
        )
    except Exception:
        pass


if __name__ == "__main__":
    import json as _json

    parser = argparse.ArgumentParser(description="Scrape gaming & hardware news")
    parser.add_argument(
        "--source",
        choices=["all", "rss", "google", "reddit", "rawg"],
        default="all",
        help="News source to scrape",
    )
    parser.add_argument("--run-id", default=None, help="n8n run ID (ignored, for tracking)")
    parser.add_argument("--topic", default="", help="Focus scraping on this topic")
    parser.add_argument("--games", default="", help="Comma-separated planned game slugs")
    parser.add_argument("--angle", default="", help="Planned content angle from planner")
    args = parser.parse_args()
    result = main(source=args.source, topic=args.topic, games=args.games, angle=args.angle)
    print(_json.dumps(result, ensure_ascii=False))
