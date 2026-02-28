# -*- coding: utf-8 -*-
"""
News Scraper Service
====================
Multi-source gaming & hardware news aggregation: RSS, Google News (SerpApi), Reddit.
Deduplicates via URL uniqueness and RAG similarity.
"""

import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from config.settings import settings
from database.connection import execute_query

logger = logging.getLogger("instagram.scraper")


class NewsScraper:
    """Aggregates gaming & hardware news from multiple sources."""

    def __init__(self):
        self._cfg = settings.news

    # ================================================================
    # RSS Feeds
    # ================================================================

    def scrape_rss(self, max_per_feed: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scrape all configured RSS feeds for gaming & hardware news."""
        max_items = max_per_feed or self._cfg.max_articles_per_source
        all_articles = []

        for feed_url in self._cfg.rss_feeds:
            try:
                articles = self._parse_rss_feed(feed_url, max_items)
                all_articles.extend(articles)
                logger.info("RSS: %d articles from %s", len(articles), feed_url[:50])
            except Exception as exc:
                logger.warning("RSS feed failed (%s): %s", feed_url[:40], exc)
            time.sleep(1)  # polite delay

        return all_articles

    def _parse_rss_feed(self, feed_url: str, max_items: int) -> List[Dict[str, Any]]:
        resp = requests.get(
            feed_url,
            timeout=15,
            headers={
                "User-Agent": self._cfg.reddit_user_agent,
            },
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        articles = []

        # Handle both RSS 2.0 and Atom feeds
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._cfg.max_age_hours)

        for item in items[:max_items]:
            try:
                title = self._get_text(item, "title", ns)
                link = self._get_text(item, "link", ns) or self._get_attr(
                    item, "link", "href", ns
                )
                description = self._get_text(item, "description", ns) or self._get_text(
                    item, "atom:summary", ns
                )
                pub_date = self._get_text(item, "pubDate", ns) or self._get_text(
                    item, "atom:updated", ns
                )

                if not title or not link:
                    continue

                parsed_date = self._parse_date(pub_date) if pub_date else None
                if parsed_date and parsed_date < cutoff:
                    continue

                articles.append(
                    {
                        "source": "rss",
                        "source_url": link,
                        "title": title.strip(),
                        "summary": self._clean_html(description or ""),
                        "category": "gaming",
                        "published_at": parsed_date,
                        "metadata": {"feed_url": feed_url},
                    }
                )
            except Exception:
                continue

        return articles

    # ================================================================
    # Google News (SerpApi)
    # ================================================================

    def scrape_google_news(
        self, query: str = "gaming hardware news", max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch gaming & hardware news via SerpApi Google News engine."""
        api_key = self._cfg.serpapi_key
        if not api_key:
            logger.info("SerpApi key not set — skipping Google News.")
            return []

        max_items = max_results or self._cfg.max_articles_per_source
        articles = []

        try:
            resp = requests.get(
                "https://serpapi.com/search.json",
                params={
                    "engine": "google_news",
                    "q": query,
                    "api_key": api_key,
                    "gl": "us",
                    "hl": "en",
                },
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("news_results", [])[:max_items]:
                articles.append(
                    {
                        "source": "google_news",
                        "source_url": item.get("link", ""),
                        "title": item.get("title", ""),
                        "summary": item.get("snippet", ""),
                        "category": "gaming",
                        "published_at": self._parse_date(item.get("date", "")),
                        "metadata": {
                            "source_name": item.get("source", {}).get("name", ""),
                            "thumbnail": item.get("thumbnail", ""),
                        },
                    }
                )

            logger.info("Google News: %d articles for '%s'", len(articles), query)
        except Exception as exc:
            logger.warning("Google News scrape failed: %s", exc)

        return articles

    # ================================================================
    # Reddit
    # ================================================================

    def scrape_reddit(self, max_per_sub: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scrape trending posts from gaming & hardware subreddits."""
        max_items = max_per_sub or self._cfg.max_articles_per_source
        all_articles = []

        for sub in self._cfg.reddit_subreddits:
            try:
                articles = self._scrape_subreddit(sub, max_items)
                all_articles.extend(articles)
                logger.info("Reddit r/%s: %d posts", sub, len(articles))
            except Exception as exc:
                logger.warning("Reddit r/%s failed: %s", sub, exc)
            time.sleep(2)  # Reddit rate limit

        return all_articles

    def _scrape_subreddit(self, subreddit: str, limit: int) -> List[Dict[str, Any]]:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        resp = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": self._cfg.reddit_user_agent,
            },
            params={"limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()

        articles = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._cfg.max_age_hours)

        for post in data.get("data", {}).get("children", []):
            d = post.get("data", {})
            if d.get("stickied"):
                continue

            created = datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc)
            if created < cutoff:
                continue

            articles.append(
                {
                    "source": "reddit",
                    "source_url": f"https://reddit.com{d.get('permalink', '')}",
                    "title": d.get("title", ""),
                    "summary": (d.get("selftext", "") or "")[:500],
                    "category": "gaming",
                    "published_at": created,
                    "metadata": {
                        "subreddit": subreddit,
                        "score": d.get("score", 0),
                        "num_comments": d.get("num_comments", 0),
                        "url": d.get("url", ""),
                    },
                }
            )

        # Sort by score (most trending first)
        articles.sort(key=lambda a: a["metadata"].get("score", 0), reverse=True)
        return articles

    # ================================================================
    # Aggregate + Store
    # ================================================================

    def scrape_all(self) -> List[Dict[str, Any]]:
        """Scrape all sources and return combined, deduplicated articles."""
        rss_articles = self.scrape_rss()
        google_articles = self.scrape_google_news()
        reddit_articles = self.scrape_reddit()

        all_articles = rss_articles + google_articles + reddit_articles
        deduplicated = self._deduplicate(all_articles)

        logger.info(
            "Total scraped: %d (RSS=%d, Google=%d, Reddit=%d) → %d after dedup",
            len(all_articles),
            len(rss_articles),
            len(google_articles),
            len(reddit_articles),
            len(deduplicated),
        )
        return deduplicated

    def store_articles(self, articles: List[Dict[str, Any]]) -> int:
        """Store articles in DB. Returns count of newly inserted."""
        count = 0
        for article in articles:
            try:
                rows = execute_query(
                    """
                    INSERT INTO news_articles (source, source_url, title, summary, category, published_at, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_url) DO NOTHING
                    RETURNING id
                    """,
                    (
                        article["source"],
                        article["source_url"],
                        article["title"],
                        article.get("summary", ""),
                        article.get("category", "gaming"),
                        article.get("published_at"),
                        json.dumps(article.get("metadata", {})),
                    ),
                )
                if rows:
                    count += 1
            except Exception as exc:
                logger.warning("Failed to store article: %s", exc)
        logger.info("Stored %d new articles", count)
        return count

    def get_unused_articles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get articles not yet used in any script."""
        return (
            execute_query(
                """
            SELECT * FROM news_articles
            WHERE used = FALSE
            ORDER BY published_at DESC NULLS LAST
            LIMIT %s
            """,
                (limit,),
            )
            or []
        )

    def mark_articles_used(self, article_ids: List[str]) -> None:
        """Mark articles as used."""
        if not article_ids:
            return
        execute_query(
            "UPDATE news_articles SET used = TRUE WHERE id = ANY(%s)",
            (article_ids,),
            fetch=False,
        )

    # ================================================================
    # Utilities
    # ================================================================

    @staticmethod
    def _deduplicate(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_urls = set()
        seen_titles = set()
        result = []
        for a in articles:
            url = a.get("source_url", "")
            title_key = a.get("title", "").lower().strip()[:80]
            if url in seen_urls or title_key in seen_titles:
                continue
            seen_urls.add(url)
            seen_titles.add(title_key)
            result.append(a)
        return result

    @staticmethod
    def _clean_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text).strip()

    @staticmethod
    def _get_text(elem, tag, ns=None):
        child = elem.find(tag, ns) if ns else elem.find(tag)
        return child.text if child is not None and child.text else None

    @staticmethod
    def _get_attr(elem, tag, attr, ns=None):
        child = elem.find(tag, ns) if ns else elem.find(tag)
        return child.get(attr) if child is not None else None

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return None
