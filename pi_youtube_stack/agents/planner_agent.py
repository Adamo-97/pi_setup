# -*- coding: utf-8 -*-
"""
Planner Agent — YouTube
=========================
Platform-specific content planner for YouTube long-form videos.
Reads shared RAWG PostgreSQL cache + local RAG context to propose
content ideas tailored for 10-15 minute Arabic gaming videos.

Workflow:
  1. Query trending/new games from shared RAWG cache (port 5433)
  2. Check what topics have been covered recently (RAG)
  3. Check remaining weekly budget via Redis Bouncer
  4. Generate a content plan via Gemini
  5. Return plan for Gate 0 approval in Mattermost

Usage:
    agent = PlannerAgent()
    plan = agent.execute()
"""

import json
import logging
import os
import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from agents.base_agent import BaseAgent
from services.redis_rate_limiter import RedisRateLimiter, BudgetExhaustedError
from services.budget_reader import BudgetReader

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Planner prompts
# -------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """أنت مُخطط محتوى احترافي لقناة يوتيوب عربية متخصصة في الألعاب.
مهمتك اقتراح فكرة فيديو واحدة مُحكمة بناءً على:
- الألعاب الرائجة والجديدة
- ما تم تغطيته سابقاً (لتجنب التكرار)
- الميزانية المتبقية للأسبوع

يجب أن يكون اقتراحك بصيغة JSON فقط."""


def _get_planner_prompt(
    trending_games: str,
    covered_topics: str,
    remaining_budget: int,
    current_date: str,
) -> str:
    return f"""التاريخ: {current_date}
الميزانية المتبقية: {remaining_budget} وحدة

--- الألعاب الرائجة والجديدة ---
{trending_games}

--- المواضيع المغطاة سابقاً ---
{covered_topics}

---

بناءً على البيانات أعلاه، اقترح فكرة فيديو واحدة بصيغة JSON:
{{
  "content_type": "monthly_releases | aaa_review | upcoming_games",
  "topic": "عنوان الموضوع بالعربي",
  "angle": "الزاوية الفريدة للفيديو — ما الذي يميزه؟",
  "game_slugs": ["slug-1", "slug-2"],
  "estimated_duration_minutes": 10,
  "estimated_cost_units": 250,
  "reasoning": "لماذا هذا الموضوع الآن؟"
}}"""


class PlannerAgent(BaseAgent):
    """
    YouTube Content Planner — proposes long-form video ideas.

    Reads:
      - Shared RAWG PostgreSQL cache (YouTube DB at port 5433)
      - Local RAG context (recently covered topics)
      - Redis budget remaining
    """

    PLATFORM = "youtube"

    @property
    def agent_name(self) -> str:
        return "Planner Agent (YouTube)"

    def __init__(self):
        super().__init__()
        self._shared_rawg_config = {
            "host": os.getenv("SHARED_RAWG_HOST", "192.168.1.100"),
            "port": int(os.getenv("SHARED_RAWG_PORT", "5433")),
            "dbname": os.getenv("SHARED_RAWG_DB", "youtube_rag"),
            "user": os.getenv("SHARED_RAWG_USER", "yt_readonly"),
            "password": os.getenv("SHARED_RAWG_PASSWORD", "readonly_pass_2025"),
        }

    def execute(self, **kwargs) -> dict:
        """
        Generate a content plan for YouTube.

        Returns:
            dict with plan details for Gate 0 approval.
        """
        plan_id = str(uuid.uuid4())
        logger.info("[%s] Starting plan generation: %s", self.agent_name, plan_id[:8])

        # 1. Load budget
        reader = BudgetReader(
            platform=self.PLATFORM,
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
        )
        weekly_budget = reader.get_weekly_budget()

        bouncer = RedisRateLimiter(
            platform=self.PLATFORM,
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
            budget_limit=weekly_budget,
        )
        bouncer.set_api_costs(reader.get_api_costs())

        # 2. Check budget for planner call
        if not bouncer.check_and_consume("gemini_planner"):
            raise BudgetExhaustedError(
                self.PLATFORM,
                "gemini_planner",
                bouncer.get_api_cost("gemini_planner"),
                bouncer.get_remaining(),
            )

        remaining = bouncer.get_remaining()

        # 3. Get trending games from shared RAWG cache
        trending_games = self._get_trending_games()

        # 4. Get recently covered topics from RAG
        covered_topics = self._get_covered_topics()

        # 5. Generate plan via Gemini
        prompt = _get_planner_prompt(
            trending_games=trending_games,
            covered_topics=covered_topics,
            remaining_budget=remaining,
            current_date=date.today().isoformat(),
        )

        response = self.gemini.generate(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=prompt,
        )

        # 6. Parse Gemini response
        try:
            plan = json.loads(response)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code block
            import re

            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
            if match:
                plan = json.loads(match.group(1))
            else:
                logger.error("Failed to parse planner response as JSON")
                plan = {
                    "content_type": "monthly_releases",
                    "topic": "خطة افتراضية — مراجعة إصدارات الشهر",
                    "angle": "تغطية شاملة لأبرز الإصدارات",
                    "game_slugs": [],
                    "estimated_duration_minutes": 10,
                    "estimated_cost_units": 250,
                    "reasoning": "فشل في تحليل استجابة Gemini — خطة احتياطية",
                }

        # 7. Build result
        result = {
            "plan_id": plan_id,
            "platform": self.PLATFORM,
            "proposed_content_type": plan.get("content_type", "monthly_releases"),
            "proposed_topic": plan.get("topic", ""),
            "proposed_angle": plan.get("angle", ""),
            "game_slugs": plan.get("game_slugs", []),
            "estimated_duration_minutes": plan.get("estimated_duration_minutes", 10),
            "estimated_cost_units": plan.get("estimated_cost_units", 250),
            "reasoning": plan.get("reasoning", ""),
            "budget_remaining": remaining,
            "budget_total": weekly_budget,
            "budget_status": bouncer.format_budget_status(),
        }

        logger.info(
            "[%s] Plan generated: %s — '%s' (cost: ~%d units)",
            self.agent_name,
            result["proposed_content_type"],
            result["proposed_topic"],
            result["estimated_cost_units"],
        )

        return result

    # ------------------------------------------------------------------
    # Data access helpers
    # ------------------------------------------------------------------

    def _get_trending_games(self) -> str:
        """Query shared RAWG PostgreSQL cache for trending/recent games."""
        try:
            conn = psycopg2.connect(**self._shared_rawg_config)
            conn.set_client_encoding("UTF8")
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Get games released in the last 60 days + upcoming
            cursor.execute(
                """
                SELECT title, slug, release_date, rating, metacritic,
                       platforms, genres, gamepass
                FROM games
                WHERE release_date >= CURRENT_DATE - INTERVAL '60 days'
                   OR release_date > CURRENT_DATE
                ORDER BY release_date DESC
                LIMIT 20
            """
            )
            games = cursor.fetchall()
            cursor.close()
            conn.close()

            if not games:
                return "لا توجد ألعاب جديدة في قاعدة البيانات."

            parts = []
            for g in games:
                platforms = g.get("platforms", "")
                if isinstance(platforms, list):
                    platforms = ", ".join(platforms)
                parts.append(
                    f"- {g['title']} ({g.get('release_date', '?')}) "
                    f"| تقييم: {g.get('rating', 'N/A')} "
                    f"| Metacritic: {g.get('metacritic', 'N/A')} "
                    f"| المنصات: {platforms} "
                    f"| Game Pass: {'نعم' if g.get('gamepass') else 'لا'}"
                )
            return "\n".join(parts)

        except Exception as exc:
            logger.warning("Failed to query shared RAWG cache: %s", exc)
            return f"خطأ في الوصول لقاعدة بيانات RAWG: {exc}"

    def _get_covered_topics(self) -> str:
        """Get recently covered topics from local RAG."""
        try:
            from database.connection import execute_query

            recent = execute_query(
                """SELECT title, content_type, created_at
                   FROM generated_scripts
                   WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
                   ORDER BY created_at DESC
                   LIMIT 10"""
            )
            if not recent:
                return "لا توجد مواضيع مغطاة حديثاً."

            parts = []
            for r in recent:
                parts.append(
                    f"- [{r.get('content_type', '?')}] {r.get('title', 'بدون عنوان')} "
                    f"({r.get('created_at', '?')})"
                )
            return "\n".join(parts)

        except Exception as exc:
            logger.warning("Failed to get covered topics: %s", exc)
            return "خطأ في الوصول للمواضيع المغطاة."
