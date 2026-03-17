# -*- coding: utf-8 -*-
"""
News Scraper Service
====================
Multi-source gaming & hardware news aggregation: RSS, Google News (SerpApi), Reddit.
Deduplicates via URL uniqueness and RAG similarity.
"""

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

logger = logging.getLogger("tiktok.scraper")


class NewsScraper:
    """Aggregates gaming & hardware news from multiple sources."""

    def __init__(self):
        self._cfg = settings.news
        self._rawg_key = getattr(settings, "rawg", None) and settings.rawg.api_key or ""

    # ================================================================
    # RAWG.io — Game Database
    # ================================================================

    def scrape_rawg(
        self,
        topic: str = "",
        game_slugs: Optional[List[str]] = None,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Fetch recent/relevant games from RAWG.io matching the topic."""
        if not self._rawg_key:
            logger.info("RAWG API key not set — skipping RAWG.")
            return []

        articles = []
        normalized_slugs = [slug.strip() for slug in (game_slugs or []) if slug.strip()]

        if normalized_slugs:
            return self._scrape_rawg_by_slugs(normalized_slugs, max_results=max_results)

        params: Dict[str, Any] = {
            "key": self._rawg_key,
            "page_size": max_results,
            "ordering": "-added",
        }
        if topic:
            params["search"] = topic

        try:
            resp = requests.get(
                "https://api.rawg.io/api/games",
                params=params,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            for game in data.get("results", [])[:max_results]:
                genres = ", ".join(g["name"] for g in game.get("genres", []))
                platforms = ", ".join(
                    p["platform"]["name"]
                    for p in game.get("platforms", [])
                    if p.get("platform", {}).get("name")
                )
                summary = (
                    f"Rating: {game.get('rating', 'N/A')}/5 | "
                    f"Genres: {genres or 'N/A'} | "
                    f"Platforms: {platforms or 'N/A'}"
                )
                articles.append(
                    {
                        "source": "rawg",
                        "source_url": f"https://rawg.io/games/{game.get('slug', '')}",
                        "title": game.get("name", ""),
                        "summary": summary,
                        "category": "gaming",
                        "published_at": self._parse_date(game.get("released", "")),
                        "metadata": {
                            "rawg_id": game.get("id"),
                            "rating": game.get("rating"),
                            "ratings_count": game.get("ratings_count"),
                            "genres": genres,
                            "platforms": platforms,
                            "background_image": game.get("background_image", ""),
                        },
                    }
                )

            logger.info("RAWG: %d games for '%s'", len(articles), topic or "trending")
        except Exception as exc:
            logger.warning("RAWG scrape failed: %s", exc)

        return articles

    def _scrape_rawg_by_slugs(
        self,
        game_slugs: List[str],
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Fetch exact games from RAWG by known slugs to avoid off-topic results."""
        if not self._rawg_key:
            logger.info("RAWG API key not set — skipping RAWG.")
            return []

        articles: List[Dict[str, Any]] = []
        for slug in game_slugs[:max_results]:
            try:
                resp = requests.get(
                    f"https://api.rawg.io/api/games/{slug}",
                    params={"key": self._rawg_key},
                    timeout=20,
                )
                resp.raise_for_status()
                game = resp.json()

                genres = ", ".join(g["name"] for g in game.get("genres", []))
                platforms = ", ".join(
                    p["platform"]["name"]
                    for p in game.get("platforms", [])
                    if p.get("platform", {}).get("name")
                )
                summary = (
                    f"Rating: {game.get('rating', 'N/A')}/5 | "
                    f"Genres: {genres or 'N/A'} | "
                    f"Platforms: {platforms or 'N/A'}"
                )
                articles.append(
                    {
                        "source": "rawg",
                        "source_url": f"https://rawg.io/games/{game.get('slug', slug)}",
                        "title": game.get("name", slug.replace("-", " ").title()),
                        "summary": summary,
                        "category": "gaming",
                        "published_at": self._parse_date(game.get("released", "")),
                        "metadata": {
                            "rawg_id": game.get("id"),
                            "rating": game.get("rating"),
                            "ratings_count": game.get("ratings_count"),
                            "genres": genres,
                            "platforms": platforms,
                            "background_image": game.get("background_image", ""),
                            "game_slug": slug,
                        },
                    }
                )
            except Exception as exc:
                logger.warning("RAWG slug fetch failed (%s): %s", slug, exc)

        logger.info("RAWG by slugs: %d games for %s", len(articles), ",".join(game_slugs))
        return articles

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

    def scrape_all(self, topic: str = "", game_slugs: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Scrape all sources and return combined, deduplicated articles.
        
        If topic is provided, Google News searches for that topic specifically
        and RSS/Reddit results are filtered to only include relevant articles.
        """
        game_slugs = [slug.strip() for slug in (game_slugs or []) if slug.strip()]
        strict_game_mode = bool(game_slugs)
        base_query = " ".join(slug.replace("-", " ") for slug in game_slugs) if strict_game_mode else topic
        google_query = f"{base_query} gaming" if base_query else "gaming hardware news"
        rss_articles = self.scrape_rss()
        google_articles = self.scrape_google_news(query=google_query)
        reddit_articles = self.scrape_reddit()
        rawg_articles = self.scrape_rawg(topic=topic, game_slugs=game_slugs)

        if base_query:
            keywords = self._topic_keywords(base_query)
            rss_articles = self._filter_by_topic(rss_articles, keywords)
            google_articles = self._filter_by_topic(google_articles, keywords)
            reddit_articles = self._filter_by_topic(reddit_articles, keywords)

            # In strict game mode, do not keep non-matching data.
            if strict_game_mode:
                rawg_articles = self._filter_by_topic(rawg_articles, keywords)

        all_articles = rawg_articles + google_articles + rss_articles + reddit_articles
        deduplicated = self._deduplicate(all_articles)

        if strict_game_mode:
            deduplicated = self._filter_by_game_slugs(deduplicated, game_slugs)

        logger.info(
            "Total scraped: %d (RAWG=%d, Google=%d, RSS=%d, Reddit=%d, strict=%s) → %d after dedup",
            len(all_articles),
            len(rawg_articles),
            len(google_articles),
            len(rss_articles),
            len(reddit_articles),
            strict_game_mode,
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

    def get_unused_articles_for_topic(self, topic: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get unused articles ranked by match quality for a target topic."""
        articles = self.get_unused_articles(limit=100)
        if not topic:
            return articles[:limit]

        keywords = self._topic_keywords(topic)
        if not keywords:
            return articles[:limit]

        scored: List[tuple[int, Dict[str, Any]]] = []
        for article in articles:
            haystack = f"{article.get('title', '')} {article.get('summary', '')}".lower()
            score = sum(1 for kw in keywords if kw in haystack)
            if score > 0:
                scored.append((score, article))

        if not scored:
            return articles[:limit]

        scored.sort(
            key=lambda item: (
                item[0],
                item[1].get("published_at") or item[1].get("scraped_at") or "",
            ),
            reverse=True,
        )
        return [article for _, article in scored[:limit]]

    def mark_articles_used(self, article_ids: List[str]) -> None:
        """Mark articles as used."""
        if not article_ids:
            return
        execute_query(
            "UPDATE news_articles SET used = TRUE WHERE id = ANY(%s::uuid[])",
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
    def _filter_by_topic(
        articles: List[Dict[str, Any]], keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """Keep only articles whose title or summary contains at least one keyword."""
        filtered = []
        for a in articles:
            text = (a.get("title", "") + " " + a.get("summary", "")).lower()
            if any(kw in text for kw in keywords):
                filtered.append(a)
        return filtered

    @staticmethod
    def _topic_keywords(topic: str) -> List[str]:
        """Build robust keyword set from topic text/slugs for strict matching."""
        raw_tokens = re.split(r"[\s,;|/_-]+", topic.lower())
        keywords = [tok for tok in raw_tokens if len(tok.strip()) > 2]
        return list(dict.fromkeys(keywords))

    @classmethod
    def _filter_by_game_slugs(
        cls,
        articles: List[Dict[str, Any]],
        game_slugs: List[str],
    ) -> List[Dict[str, Any]]:
        """Keep only items that strongly match at least one planned game slug."""
        filtered: List[Dict[str, Any]] = []
        for article in articles:
            if cls._matches_any_game_slug(article, game_slugs):
                filtered.append(article)
        return filtered

    @staticmethod
    def _matches_any_game_slug(article: Dict[str, Any], game_slugs: List[str]) -> bool:
        text = (
            f"{article.get('title', '')} "
            f"{article.get('summary', '')} "
            f"{article.get('source_url', '')}"
        ).lower()
        normalized_text = re.sub(r"[^a-z0-9\s-]+", " ", text)

        for slug in game_slugs:
            normalized_slug = slug.strip().lower()
            if not normalized_slug:
                continue

            phrase = normalized_slug.replace("-", " ")
            tokens = [t for t in normalized_slug.split("-") if len(t) > 2]

            # Strong match: full slug/phrase found in article text.
            if normalized_slug in normalized_text or phrase in normalized_text:
                return True

            # Secondary match: at least 2 meaningful game tokens in the same article.
            token_hits = sum(1 for token in tokens if token in normalized_text)
            if token_hits >= 2:
                return True

        return False

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
