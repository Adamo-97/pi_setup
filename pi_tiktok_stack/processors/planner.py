# -*- coding: utf-8 -*-
"""
Planner Processor — TikTok
===========================
Platform-specific content planner for TikTok.
Reads shared RAWG PostgreSQL cache + local RAG context to propose
content ideas tailored for 30-60 second Arabic gaming videos with
high visual impact and aesthetic appeal.

Workflow:
  1. Query trending/new games from shared RAWG cache (port 5433)
  2. Check recently covered topics (local RAG)
  3. Check remaining weekly budget via Redis Bouncer
  4. Generate content plan via Gemini
  5. Return plan for Gate 0 approval in Mattermost
"""

import json
import logging
import os
import uuid
from datetime import date
from typing import Dict, List, Optional

import psycopg2
import psycopg2.extras

from processors.base import BaseProcessor
from config.settings import settings
from services.redis_rate_limiter import RedisRateLimiter, BudgetExhaustedError
from services.budget_reader import BudgetReader
from config.prompts.planner_prompts import PLANNER_SYSTEM_PROMPT, get_planner_prompt

logger = logging.getLogger(__name__)


class Planner(BaseProcessor):
    """
    TikTok Content Planner — proposes video ideas.
    """

    PLATFORM = "tiktok"

    def __init__(self):
        super().__init__(name="Planner Processor (TikTok)")
        self._task_model = settings.gemini.model_planner
        self._shared_rawg_config = {
            "host": os.getenv("SHARED_RAWG_HOST", "192.168.1.100"),
            "port": int(os.getenv("SHARED_RAWG_PORT", "5433")),
            "dbname": os.getenv("SHARED_RAWG_DB", "youtube_rag"),
            "user": os.getenv("SHARED_RAWG_USER", "yt_readonly"),
            "password": os.getenv("SHARED_RAWG_PASSWORD", "readonly_pass_2025"),
        }

    def run(self, **kwargs) -> dict:
        """Generate a content plan for TikTok."""
        plan_id = str(uuid.uuid4())
        logger.info("[%s] Starting plan generation: %s", self.name, plan_id[:8])

        # 1. Load budget
        reader = BudgetReader(
            platform=self.PLATFORM,
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6380"),
        )
        weekly_budget = reader.get_weekly_budget()

        bouncer = RedisRateLimiter(
            platform=self.PLATFORM,
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6380"),
            budget_limit=weekly_budget,
        )
        bouncer.set_api_costs(reader.get_api_costs())

        # 2. Check budget
        if not bouncer.check_and_consume("gemini_planner"):
            raise BudgetExhaustedError(
                self.PLATFORM,
                "gemini_planner",
                bouncer.get_api_cost("gemini_planner"),
                bouncer.get_remaining(),
            )

        remaining = bouncer.get_remaining()

        # 3. Get trending games
        trending_games = self._get_trending_games()

        # 4. Get covered topics
        covered_topics = self._get_covered_topics()

        # 4b. Get recent scraped news
        news_data = self._get_recent_news()

        # 5. Generate plan
        prompt = get_planner_prompt(
            trending_games=trending_games,
            covered_topics=covered_topics,
            remaining_budget=remaining,
            current_date=date.today().isoformat(),
            news_data=news_data,
        )

        response = self.gemini.generate_text(
            prompt=prompt,
            system_prompt=PLANNER_SYSTEM_PROMPT,
            model_override=self._task_model,
        )

        # 6. Parse response
        try:
            plan = json.loads(response)
        except json.JSONDecodeError:
            import re

            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
            if match:
                plan = json.loads(match.group(1))
            else:
                plan = {
                    "content_type": "trending_news",
                    "topic": "لقطات مميزة — خطة احتياطية",
                    "angle": "أفضل لحظات الأسبوع",
                    "visual_hook": "هذا المشهد غير حقيقي...",
                    "game_slugs": [],
                    "estimated_duration_seconds": 45,
                    "estimated_cost_units": 180,
                    "reasoning": "خطة احتياطية",
                }

        normalized_type = self._normalize_content_type(
            plan.get("content_type", "trending_news")
        )

        result = {
            "plan_id": plan_id,
            "platform": self.PLATFORM,
            "proposed_content_type": normalized_type,
            "raw_content_type": plan.get("content_type", ""),
            "proposed_topic": plan.get("topic", ""),
            "proposed_angle": plan.get("angle", ""),
            "visual_hook": plan.get("visual_hook", ""),
            "game_slugs": plan.get("game_slugs", []),
            "estimated_duration_seconds": plan.get("estimated_duration_seconds", 45),
            "estimated_cost_units": plan.get("estimated_cost_units", 180),
            "reasoning": plan.get("reasoning", ""),
            "budget_remaining": remaining,
            "budget_total": weekly_budget,
            "budget_status": bouncer.format_budget_status(),
        }

        logger.info(
            "[%s] Plan: '%s' (cost ~%d units)",
            self.name,
            result["proposed_topic"],
            result["estimated_cost_units"],
        )
        return result

    @staticmethod
    def _normalize_content_type(raw_type: str) -> str:
        """Map planner labels into writer-supported content types."""
        normalized = (raw_type or "").strip().lower()
        aliases = {
            "trending_news": "trending_news",
            "game_spotlight": "game_spotlight",
            "hardware_spotlight": "hardware_spotlight",
            "trailer_reaction": "trailer_reaction",
            "game_highlights": "trending_news",
            "visual_showcase": "game_spotlight",
            "tips_tricks": "trending_news",
        }
        return aliases.get(normalized, "trending_news")

    def _get_trending_games(self) -> str:
        """Query shared RAWG cache for visually impressive games."""
        try:
            conn = psycopg2.connect(**self._shared_rawg_config, connect_timeout=5)
            conn.set_client_encoding("UTF8")
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT title, slug, release_date, rating, metacritic,
                       platforms, genres, gamepass
                FROM games
                WHERE release_date >= CURRENT_DATE - INTERVAL '30 days'
                   OR release_date > CURRENT_DATE
                ORDER BY rating DESC NULLS LAST
                LIMIT 15
            """
            )
            games = cur.fetchall()
            cur.close()
            conn.close()

            if not games:
                return "لا توجد ألعاب رائجة."

            parts = []
            for g in games:
                parts.append(
                    f"- {g['title']} ({g.get('release_date', '?')}) "
                    f"| تقييم: {g.get('rating', 'N/A')}"
                )
            return "\n".join(parts)

        except Exception as exc:
            logger.warning("RAWG cache query failed: %s", exc)
            return f"خطأ: {exc}"

    def _get_covered_topics(self) -> str:
        """Get recently covered topics from local DB."""
        try:
            from database.connection import execute_query

            recent = execute_query(
                """SELECT content_type, created_at
                   FROM generated_scripts
                   WHERE created_at >= CURRENT_DATE - INTERVAL '14 days'
                   ORDER BY created_at DESC LIMIT 10""",
                fetch=True,
            )
            if not recent:
                return "لا توجد مواضيع مغطاة."
            return "\n".join(f"- [{r['content_type']}] ({r['created_at']})" for r in recent)
        except Exception as exc:
            logger.warning("Covered topics query failed: %s", exc)
            return "خطأ في استرجاع المواضيع."

    def _get_recent_news(self) -> str:
        """Get recent unused news articles from local DB (scraped by Step 1)."""
        try:
            from database.connection import execute_query

            articles = execute_query(
                """SELECT source, title, summary
                   FROM news_articles
                   WHERE used = FALSE
                     AND scraped_at >= NOW() - INTERVAL '48 hours'
                   ORDER BY published_at DESC NULLS LAST
                   LIMIT 10""",
                fetch=True,
            )
            if not articles:
                return "لا توجد أخبار حديثة."

            parts = []
            for i, a in enumerate(articles, 1):
                summary = (a.get("summary") or "")[:200]
                parts.append(
                    f"{i}. [{a['source']}] {a['title']}\n"
                    f"   {summary}"
                )
            return "\n\n".join(parts)
        except Exception as exc:
            logger.warning("Recent news query failed: %s", exc)
            return "خطأ في استرجاع الأخبار."
