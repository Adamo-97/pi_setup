# -*- coding: utf-8 -*-
"""
Planner Agent — TikTok
========================
Platform-specific content planner for TikTok short-form videos.
Reads shared RAWG PostgreSQL cache + local RAG context to propose
content ideas tailored for 30-60 second Arabic gaming TikToks.

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

from agents.base_agent import BaseAgent
from services.redis_rate_limiter import RedisRateLimiter, BudgetExhaustedError
from services.budget_reader import BudgetReader

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Planner prompts — TikTok-specific
# -------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """أنت مُخطط محتوى لحساب تيك توك عربي متخصص في أخبار الألعاب.
المحتوى يجب أن يكون:
- سريع الإيقاع (30-60 ثانية)
- يبدأ بخطاف قوي (hook) في أول 3 ثوانِ
- يركز على أخبار رائجة أو لحظات فيروسية
- مناسب لجمهور عربي شاب

أجب بصيغة JSON فقط."""


def _get_planner_prompt(
    trending_games: str,
    covered_topics: str,
    remaining_budget: int,
    current_date: str,
) -> str:
    return f"""التاريخ: {current_date}
الميزانية المتبقية: {remaining_budget} وحدة

--- الألعاب الرائجة ---
{trending_games}

--- المواضيع المغطاة ---
{covered_topics}

---

اقترح فكرة تيك توك واحدة بصيغة JSON:
{{
  "content_type": "trending_news | game_spotlight | trailer_reaction",
  "topic": "عنوان الموضوع",
  "angle": "الزاوية — ما الخطاف؟ لماذا سيتوقف المشاهد؟",
  "hook_text": "أول جملة يقولها الراوي (3 ثوانِ max)",
  "game_slugs": ["slug-1"],
  "estimated_duration_seconds": 45,
  "estimated_cost_units": 180,
  "reasoning": "لماذا هذا الموضوع رائج الآن؟"
}}"""


class PlannerAgent(BaseAgent):
    """
    TikTok Content Planner — proposes short-form video ideas.
    """

    PLATFORM = "tiktok"

    def __init__(self):
        super().__init__(name="Planner Agent (TikTok)")
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

        # 5. Generate plan
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
                    "topic": "أخبار رائجة — خطة احتياطية",
                    "angle": "تغطية سريعة لآخر الأخبار",
                    "hook_text": "خبر عاجل في عالم الألعاب!",
                    "game_slugs": [],
                    "estimated_duration_seconds": 45,
                    "estimated_cost_units": 180,
                    "reasoning": "خطة احتياطية",
                }

        result = {
            "plan_id": plan_id,
            "platform": self.PLATFORM,
            "proposed_content_type": plan.get("content_type", "trending_news"),
            "proposed_topic": plan.get("topic", ""),
            "proposed_angle": plan.get("angle", ""),
            "hook_text": plan.get("hook_text", ""),
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

    def _get_trending_games(self) -> str:
        """Query shared RAWG cache."""
        try:
            conn = psycopg2.connect(**self._shared_rawg_config)
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
                platforms = g.get("platforms", "")
                if isinstance(platforms, list):
                    platforms = ", ".join(platforms)
                parts.append(
                    f"- {g['title']} ({g.get('release_date', '?')}) "
                    f"| تقييم: {g.get('rating', 'N/A')}"
                )
            return "\n".join(parts)

        except Exception as exc:
            logger.warning("RAWG cache query failed: %s", exc)
            return f"خطأ: {exc}"

    def _get_covered_topics(self) -> str:
        """Get recently covered topics."""
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
            return "\n".join(f"- [{r[0]}] ({r[1]})" for r in recent)
        except Exception as exc:
            logger.warning("Covered topics query failed: %s", exc)
            return "خطأ في استرجاع المواضيع."
