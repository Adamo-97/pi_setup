# -*- coding: utf-8 -*-
"""
Writer Agent
==============
Responsible for generating engaging Arabic YouTube scripts.
Uses Gemini with specialized Arabic prompts for each content type.

Workflow:
  1. Receives game data + content type from pipeline
  2. Retrieves RAG context (past scripts, feedback)
  3. Checks for duplicate content
  4. Generates the Arabic script via Gemini
  5. Stores the script in the database + RAG
  6. Returns structured output for the Validator Agent
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from agents.base_agent import BaseAgent
from config.prompts.writer_prompts import WRITER_SYSTEM_PROMPT, get_writer_prompt
from config.settings import get_content_type
from database.connection import execute_query

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    """
    AI Writer Agent — drafts Arabic YouTube scripts.

    Usage:
        agent = WriterAgent()
        result = agent.execute(
            content_type="monthly_releases",
            games_data=[...],
            target_duration=10,
        )
    """

    @property
    def agent_name(self) -> str:
        return "Writer Agent"

    def execute(
        self,
        content_type: str,
        games_data: list[dict],
        target_duration: float = 10.0,
        game_title: Optional[str] = None,
        trigger_source: str = "manual",
        pipeline_run_id: Optional[str] = None,
        max_retries: int = 2,
    ) -> dict:
        """
        Generate a YouTube script for the given content type and games.

        Args:
            content_type: Content type ID ("monthly_releases", "aaa_review", "upcoming_games").
            games_data: List of game dicts from the database.
            target_duration: Target video duration in minutes.
            game_title: For AAA reviews, the specific game title.
            trigger_source: What triggered this generation.
            pipeline_run_id: Optional pipeline run UUID.
            max_retries: Max generation attempts if duplicate detected.

        Returns:
            Dict with: script_id, title, script_text, word_count,
            estimated_duration, content_type, status, games_data.
        """
        logger.info(
            "[%s] Starting script generation: type=%s, games=%d, duration=%.1f min",
            self.agent_name,
            content_type,
            len(games_data),
            target_duration,
        )

        # Validate content type
        ct_config = get_content_type(content_type)

        # Calculate target word count (Arabic ~130 WPM for narration)
        target_word_count = int(target_duration * 130)

        # Get month/year for monthly releases
        now = datetime.now()
        month_name = self._get_arabic_month_name(now.month)

        # ------------------------------------------------------------------
        # Step 1: Gather RAG context
        # ------------------------------------------------------------------
        query_text = f"{ct_config.display_name} {ct_config.description}"
        if game_title:
            query_text += f" {game_title}"

        rag_context = self.get_rag_context(query_text, content_type)
        previous_feedback = self.get_previous_feedback(content_type)

        # ------------------------------------------------------------------
        # Step 2: Format game data for the prompt
        # ------------------------------------------------------------------
        formatted_games = self.format_games_data(games_data)

        # ------------------------------------------------------------------
        # Step 3: Build the prompt
        # ------------------------------------------------------------------
        prompt_template = get_writer_prompt(content_type)

        # Build prompt kwargs based on content type
        prompt_kwargs = {
            "rag_context": rag_context,
            "previous_feedback": previous_feedback,
            "target_duration": target_duration,
            "word_count": target_word_count,
        }

        if content_type == "monthly_releases":
            prompt_kwargs["month_name"] = month_name
            prompt_kwargs["year"] = now.year
            prompt_kwargs["games_data"] = formatted_games
        elif content_type == "aaa_review":
            prompt_kwargs["game_title"] = game_title or games_data[0].get(
                "title", "Unknown"
            )
            prompt_kwargs["game_data"] = formatted_games
        elif content_type == "upcoming_games":
            prompt_kwargs["games_data"] = formatted_games

        prompt = prompt_template.format(**prompt_kwargs)

        # ------------------------------------------------------------------
        # Step 4: Generate script with Gemini
        # ------------------------------------------------------------------
        script_text = None
        for attempt in range(1, max_retries + 1):
            logger.info(
                "[%s] Generation attempt %d/%d", self.agent_name, attempt, max_retries
            )

            script_text = self.gemini.generate_text(
                prompt=prompt,
                system_prompt=WRITER_SYSTEM_PROMPT,
            )

            # Check for duplicates
            duplicate = self.check_duplicate(script_text)
            if duplicate and attempt < max_retries:
                logger.warning(
                    "[%s] Duplicate detected (similarity=%.2f) — regenerating with more context.",
                    self.agent_name,
                    duplicate.get("similarity_score", 0),
                )
                # Add anti-duplication instruction to prompt
                prompt += (
                    "\n\n⚠️ تحذير: المحتوى السابق كان مشابهاً جداً لمحتوى موجود. "
                    "يرجى كتابة محتوى مختلف بشكل واضح مع زاوية جديدة ومقدمة مختلفة."
                )
                continue
            break

        if script_text is None:
            raise RuntimeError(
                f"[{self.agent_name}] Failed to generate script after {max_retries} attempts."
            )

        # ------------------------------------------------------------------
        # Step 5: Calculate metadata
        # ------------------------------------------------------------------
        word_count = self.count_arabic_words(script_text)
        estimated_duration = self.estimate_duration(word_count)

        # Build title
        if content_type == "monthly_releases":
            title = f"إصدارات شهر {month_name} {now.year} — أبرز الألعاب الجديدة"
        elif content_type == "aaa_review":
            title = f"مراجعة {game_title or 'لعبة'} — هل تستحق؟"
        elif content_type == "upcoming_games":
            title = f"ألعاب قادمة يجب أن تترقبوها — {month_name} {now.year}"
        else:
            title = f"{ct_config.display_name} — {now.strftime('%Y-%m')}"

        # ------------------------------------------------------------------
        # Step 6: Store in database
        # ------------------------------------------------------------------
        script_id = str(uuid.uuid4())
        game_ids = [str(g.get("id", "")) for g in games_data if g.get("id")]

        try:
            execute_query(
                """
                INSERT INTO generated_scripts
                    (id, content_type, title, script_text, word_count,
                     target_duration, game_ids, status, version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft', 1)
                """,
                (
                    script_id,
                    content_type,
                    title,
                    script_text,
                    word_count,
                    target_duration,
                    game_ids,
                ),
                fetch=False,
            )
            logger.info(
                "[%s] Script stored: id=%s, words=%d",
                self.agent_name,
                script_id,
                word_count,
            )
        except Exception as exc:
            logger.error("[%s] Failed to store script in DB: %s", self.agent_name, exc)

        # ------------------------------------------------------------------
        # Step 7: Store in RAG for future context
        # ------------------------------------------------------------------
        self.store_in_rag(
            text=script_text,
            source_type="script",
            source_id=uuid.UUID(script_id),
            summary=f"[{content_type}] {title} ({word_count} كلمة)",
            metadata={
                "content_type": content_type,
                "title": title,
                "word_count": word_count,
                "game_count": len(games_data),
            },
        )

        # ------------------------------------------------------------------
        # Output
        # ------------------------------------------------------------------
        result = {
            "script_id": script_id,
            "title": title,
            "script_text": script_text,
            "word_count": word_count,
            "estimated_duration": estimated_duration,
            "target_duration": target_duration,
            "content_type": content_type,
            "status": "draft",
            "game_count": len(games_data),
            "pipeline_run_id": pipeline_run_id,
        }

        logger.info(
            "[%s] Script generated successfully: '%s' (%d words, ~%.1f min)",
            self.agent_name,
            title,
            word_count,
            estimated_duration,
        )

        return result

    @staticmethod
    def _get_arabic_month_name(month: int) -> str:
        """Convert month number to Arabic month name."""
        months = {
            1: "يناير",
            2: "فبراير",
            3: "مارس",
            4: "أبريل",
            5: "مايو",
            6: "يونيو",
            7: "يوليو",
            8: "أغسطس",
            9: "سبتمبر",
            10: "أكتوبر",
            11: "نوفمبر",
            12: "ديسمبر",
        }
        return months.get(month, str(month))
