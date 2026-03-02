# -*- coding: utf-8 -*-
"""
Planner Agent — Instagram
===========================
Platform-specific content planner for Instagram Reels.
Reads shared RAWG PostgreSQL cache + local RAG context to propose
content ideas tailored for 30-60 second Arabic gaming Reels with
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

from agents.base_agent import BaseAgent
from services.redis_rate_limiter import RedisRateLimiter, BudgetExhaustedError
from services.budget_reader import BudgetReader

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Planner prompts — Instagram-specific
# -------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """أنت مُخطط محتوى لحساب انستغرام عربي متخصص في محتوى الألعاب.
المحتوى يجب أن يكون:
- جذاب بصرياً (Reels 30-60 ثانية)
- يحتوي لقطات مميزة من الألعاب (highlights, أمور مذهلة, لحظات epic)
- نص قصير يناسب تجربة صامتة مع ترجمة
- مناسب لجمهور عربي يتصفح بسرعة

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

اقترح فكرة Reel واحدة بصيغة JSON:
{{
  "content_type": "game_highlights | visual_showcase | tips_tricks",
  "topic": "عنوان الموضوع",
  "angle": "الزاوية البصرية — ما الذي يجعل هذا مذهلاً بصرياً؟",
  "visual_hook": "وصف المشهد الافتتاحي (أول ثانيتين)",
  "game_slugs": ["slug-1"],
  "estimated_duration_seconds": 45,
  "estimated_cost_units": 180,
  "reasoning": "لماذا هذا الموضوع سيحقق تفاعل؟"
}}"""


class PlannerAgent(BaseAgent):
    """
    Instagram Content Planner — proposes Reels ideas.
    """

    PLATFORM = "instagram"

    def __init__(self):
        super().__init__(name="Planner Agent (Instagram)")
        self._shared_rawg_config = {
            "host": os.getenv("SHARED_RAWG_HOST", "192.168.1.100"),
            "port": int(os.getenv("SHARED_RAWG_PORT", "5433")),
            "dbname": os.getenv("SHARED_RAWG_DB", "youtube_rag"),
            "user": os.getenv("SHARED_RAWG_USER", "yt_readonly"),
            "password": os.getenv("SHARED_RAWG_PASSWORD", "readonly_pass_2025"),
        }

    def run(self, **kwargs) -> dict:
        """Generate a content plan for Instagram Reels."""
        plan_id = str(uuid.uuid4())
        logger.info("[%s] Starting plan generation: %s", self.name, plan_id[:8])

        # 1. Load budget
        reader = BudgetReader(
            platform=self.PLATFORM,
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6381"),
        )
        weekly_budget = reader.get_weekly_budget()

        bouncer = RedisRateLimiter(
            platform=self.PLATFORM,
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6381"),
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
                    "content_type": "game_highlights",
                    "topic": "لقطات مميزة — خطة احتياطية",
                    "angle": "أفضل لحظات الأسبوع",
                    "visual_hook": "هذا المشهد غير حقيقي...",
                    "game_slugs": [],
                    "estimated_duration_seconds": 45,
                    "estimated_cost_units": 180,
                    "reasoning": "خطة احتياطية",
                }

        result = {
            "plan_id": plan_id,
            "platform": self.PLATFORM,
            "proposed_content_type": plan.get("content_type", "game_highlights"),
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

    def _get_trending_games(self) -> str:
        """Query shared RAWG cache for visually impressive games."""
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
            return "\n".join(f"- [{r[0]}] ({r[1]})" for r in recent)
        except Exception as exc:
            logger.warning("Covered topics query failed: %s", exc)
            return "خطأ في استرجاع المواضيع."
