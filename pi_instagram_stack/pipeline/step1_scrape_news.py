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
import logging
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


def main(source: str = "all") -> dict:
    """
    Scrape news from specified sources.

    Args:
        source: 'all', 'rss', 'google', or 'reddit'

    Returns:
        dict with counts and status
    """
    settings = get_settings()
    scraper = NewsScraper()

    logger.info("=== Step 1: Scrape News (source: %s) ===", source)

    # Record pipeline run
    run_id = _start_pipeline_run("scrape_news")

    try:
        if source == "rss":
            articles = scraper.scrape_rss()
        elif source == "google":
            articles = scraper.scrape_google_news()
        elif source == "reddit":
            articles = scraper.scrape_reddit()
        else:
            articles = scraper.scrape_all()

        # Store in database
        stored = scraper.store_articles(articles)

        # Count available unused articles
        unused = scraper.get_unused_articles(limit=100)

        result = {
            "scraped": len(articles),
            "stored": stored,
            "total_unused": len(unused),
            "source": source,
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
    parser = argparse.ArgumentParser(description="Scrape gaming & hardware news")
    parser.add_argument(
        "--source",
        choices=["all", "rss", "google", "reddit"],
        default="all",
        help="News source to scrape",
    )
    args = parser.parse_args()
    main(source=args.source)
