# -*- coding: utf-8 -*-
"""
Metadata Agent
================
Generates YouTube-optimized metadata for videos:
  - Titles (3 suggestions with SEO reasoning)
  - Description (with timestamps and keywords)
  - Tags (Arabic + English, 15-30 tags)
  - Hashtags
  - Game info cards (platforms, price, Arabic support, Game Pass, etc.)
  - Thumbnail suggestions

This agent runs after the script is validated and provides
all the SEO and metadata needed for YouTube upload.
"""

import json
import logging
import uuid
from typing import Optional

from agents.base_agent import BaseAgent
from config.prompts.metadata_prompts import (
    METADATA_SYSTEM_PROMPT,
    METADATA_GENERATION_PROMPT,
)
from config.settings import get_content_type
from database.connection import execute_query

logger = logging.getLogger(__name__)


class MetadataAgent(BaseAgent):
    """
    AI Metadata Agent — generates YouTube SEO metadata and game info cards.

    Usage:
        agent = MetadataAgent()
        result = agent.execute(
            script_id="uuid-here",
            script_text="السكريبت...",
            content_type="monthly_releases",
            games_data=[...],
        )
    """

    @property
    def agent_name(self) -> str:
        return "Metadata Agent"

    def execute(
        self,
        script_id: str,
        script_text: str,
        content_type: str,
        games_data: list[dict],
        preliminary_title: Optional[str] = None,
        pipeline_run_id: Optional[str] = None,
    ) -> dict:
        """
        Generate YouTube metadata for a validated script.

        Args:
            script_id: UUID of the validated script.
            script_text: The final script text.
            content_type: Content type ID.
            games_data: Game data used in the script.
            preliminary_title: Working title (from Writer Agent).
            pipeline_run_id: Optional pipeline run UUID.

        Returns:
            Dict with: metadata_id, titles, description, tags, hashtags,
            game_info_cards, thumbnail_suggestions.
        """
        logger.info(
            "[%s] Generating metadata: script_id=%s, type=%s",
            self.agent_name,
            script_id,
            content_type,
        )

        ct_config = get_content_type(content_type)

        # ------------------------------------------------------------------
        # Step 1: Prepare inputs
        # ------------------------------------------------------------------
        # Create a script summary (first 500 chars + key topics)
        script_summary = self._summarize_script(script_text)

        # Format games data
        formatted_games = self.format_games_data(games_data)

        # Get RAG context (past metadata for deduplication)
        rag_context = self.get_rag_context(
            f"YouTube metadata tags description {ct_config.display_name}",
            content_type,
        )

        # Build suggested keywords
        suggested_keywords = self._extract_keywords(games_data, content_type)

        # ------------------------------------------------------------------
        # Step 2: Build prompt
        # ------------------------------------------------------------------
        prompt = METADATA_GENERATION_PROMPT.format(
            content_type_name=ct_config.display_name,
            preliminary_title=preliminary_title or ct_config.display_name,
            script_summary=script_summary,
            games_data=formatted_games,
            suggested_keywords=", ".join(suggested_keywords),
            rag_context=rag_context,
        )

        # ------------------------------------------------------------------
        # Step 3: Generate metadata via Gemini
        # ------------------------------------------------------------------
        metadata_json = self.gemini.generate_json(
            prompt=prompt,
            system_prompt=METADATA_SYSTEM_PROMPT,
            temperature=0.4,
        )

        # ------------------------------------------------------------------
        # Step 4: Validate and structure the response
        # ------------------------------------------------------------------
        titles = metadata_json.get("titles", [])
        description = metadata_json.get("description", "")
        tags = metadata_json.get("tags", [])
        hashtags = metadata_json.get("hashtags", [])
        game_info_cards = metadata_json.get("game_info_cards", [])
        thumbnail_suggestions = metadata_json.get("thumbnail_suggestions", [])

        # Ensure we have at least some tags
        if len(tags) < 5:
            tags.extend(suggested_keywords[:10])
            tags = list(set(tags))  # Deduplicate

        # ------------------------------------------------------------------
        # Step 5: Store in database
        # ------------------------------------------------------------------
        metadata_id = str(uuid.uuid4())
        try:
            execute_query(
                """
                INSERT INTO metadata
                    (id, script_id, titles, description, tags, hashtags,
                     game_info_cards, thumbnail_suggestions)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    metadata_id,
                    script_id,
                    json.dumps(titles, ensure_ascii=False),
                    description,
                    json.dumps(tags, ensure_ascii=False),
                    json.dumps(hashtags, ensure_ascii=False),
                    json.dumps(game_info_cards, ensure_ascii=False),
                    json.dumps(thumbnail_suggestions, ensure_ascii=False),
                ),
                fetch=False,
            )
            logger.info("[%s] Metadata stored: id=%s", self.agent_name, metadata_id)
        except Exception as exc:
            logger.error("[%s] Failed to store metadata: %s", self.agent_name, exc)

        # ------------------------------------------------------------------
        # Output
        # ------------------------------------------------------------------
        result = {
            "metadata_id": metadata_id,
            "script_id": script_id,
            "titles": titles,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "game_info_cards": game_info_cards,
            "thumbnail_suggestions": thumbnail_suggestions,
            "pipeline_run_id": pipeline_run_id,
        }

        logger.info(
            "[%s] Metadata generated: %d titles, %d tags, %d game cards",
            self.agent_name,
            len(titles),
            len(tags),
            len(game_info_cards),
        )

        return result

    def _summarize_script(self, script_text: str, max_length: int = 800) -> str:
        """
        Create a summary of the script for the metadata prompt.

        Args:
            script_text: Full script text.
            max_length: Maximum summary length.

        Returns:
            Script summary string.
        """
        # Take the first section + last section as summary
        lines = script_text.split("\n")
        if len(lines) <= 10:
            return script_text[:max_length]

        # First 5 lines (hook + intro) + last 5 lines (conclusion)
        summary_parts = lines[:5] + ["...", "---"] + lines[-5:]
        summary = "\n".join(summary_parts)

        if len(summary) > max_length:
            summary = summary[:max_length] + "..."

        return summary

    def _extract_keywords(
        self,
        games_data: list[dict],
        content_type: str,
    ) -> list[str]:
        """
        Extract relevant keywords from game data for SEO.

        Args:
            games_data: List of game dicts.
            content_type: Content type ID.

        Returns:
            List of keyword strings.
        """
        keywords = set()

        # Add content type keywords
        type_keywords = {
            "monthly_releases": [
                "إصدارات الشهر",
                "ألعاب جديدة",
                "new games",
                "game releases",
                "إصدارات",
                "ألعاب",
            ],
            "aaa_review": [
                "مراجعة",
                "review",
                "تقييم",
                "game review",
                "ريفيو",
                "مراجعة لعبة",
            ],
            "upcoming_games": [
                "ألعاب قادمة",
                "upcoming games",
                "ألعاب منتظرة",
                "ألعاب جديدة",
                "ألعاب 2026",
            ],
        }
        keywords.update(type_keywords.get(content_type, []))

        # Add game-specific keywords
        for game in games_data:
            title = game.get("title", "")
            if title:
                keywords.add(title)
                keywords.add(f"لعبة {title}")

            # Add platform keywords
            platforms = game.get("platforms", [])
            if isinstance(platforms, str):
                try:
                    platforms = json.loads(platforms)
                except json.JSONDecodeError:
                    platforms = []
            keywords.update(platforms)

            # Add genre keywords
            genres = game.get("genres", [])
            if isinstance(genres, str):
                try:
                    genres = json.loads(genres)
                except json.JSONDecodeError:
                    genres = []
            keywords.update(genres)

        # Common gaming keywords
        keywords.update(
            [
                "PlayStation",
                "Xbox",
                "PC",
                "Nintendo",
                "Game Pass",
                "قيم باس",
                "PS5",
                "بلايستيشن",
            ]
        )

        return list(keywords)[:30]  # Cap at 30 keywords
