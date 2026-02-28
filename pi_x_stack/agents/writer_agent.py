# -*- coding: utf-8 -*-
"""
Writer Agent
============
Generates X/Twitter video scripts in Arabic using Gemini.
Uses news data + RAG context + previous feedback to produce
provocative, debate-provoking scripts for 30-60 second vertical videos.
"""

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from config.prompts.writer_prompts import WRITER_PROMPTS, WRITER_SYSTEM_PROMPT
from database.connection import execute_query

logger = logging.getLogger("x.writer")


class WriterAgent(BaseAgent):
    """AI script writer for X/Twitter gaming content."""

    def __init__(self):
        super().__init__(name="X Video Writer")

    def run(
        self,
        content_type: str = "trending_news",
        news_articles: Optional[List[Dict[str, Any]]] = None,
        target_duration: float = 45.0,
        max_retries: int = 2,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Generate an X/Twitter video script with tweet caption.

        Args:
            content_type: trending_news | game_spotlight | controversial_take | trailer_reaction
            news_articles: List of news article dicts
            target_duration: Target video duration in seconds
            max_retries: Number of retry attempts

        Returns:
            dict with script_id, script_text, tweet_text, word_count,
                  estimated_duration, news_ids, content_type
        """
        logger.info(
            "Generating %s script (target: %.0fs)", content_type, target_duration
        )

        # Prepare context
        news_data = self._format_news(news_articles or [])
        news_ids = [str(a.get("id", "")) for a in (news_articles or []) if a.get("id")]

        rag_context = self.get_rag_context(
            query=news_data[:500] if news_data else content_type,
            content_type=content_type,
        )
        feedback = self.get_previous_feedback(content_type)
        target_words = self.target_word_count(target_duration)

        # Get prompt template
        prompt_template = WRITER_PROMPTS.get(
            content_type, WRITER_PROMPTS["trending_news"]
        )
        prompt = prompt_template.format(
            news_data=news_data,
            rag_context=rag_context,
            previous_feedback=feedback,
            target_duration=int(target_duration),
            word_count=target_words,
        )

        # Generate with retries
        script_text = None
        tweet_text = None
        for attempt in range(max_retries + 1):
            try:
                raw = self.gemini.generate_text(
                    prompt=prompt,
                    system_instruction=WRITER_SYSTEM_PROMPT,
                )
                cleaned = self.clean_script(raw)

                # Extract tweet caption after [تغريدة] marker
                script_text, tweet_text = self._extract_tweet(cleaned)

                # Validate length
                word_count = self.count_words(script_text)
                est_duration = self.estimate_duration(script_text)

                if word_count < 20:
                    logger.warning(
                        "Attempt %d: Script too short (%d words), retrying",
                        attempt + 1,
                        word_count,
                    )
                    continue

                # Check duplicate
                if self.check_duplicate(script_text):
                    logger.warning(
                        "Attempt %d: Duplicate detected, retrying", attempt + 1
                    )
                    prompt += "\n\nIMPORTANT: Generate a COMPLETELY different script. Previous attempt was too similar to existing content."
                    continue

                break  # Good script

            except Exception as e:
                logger.error("Attempt %d failed: %s", attempt + 1, e)
                if attempt == max_retries:
                    raise RuntimeError(
                        f"Writer failed after {max_retries + 1} attempts: {e}"
                    )

        if not script_text:
            raise RuntimeError("Writer produced no usable script")

        word_count = self.count_words(script_text)
        est_duration = self.estimate_duration(script_text)

        # Store in database
        script_id = self._store_script(
            script_text=script_text,
            tweet_text=tweet_text,
            content_type=content_type,
            news_ids=news_ids,
            trigger_source=kwargs.get("trigger_source", "auto"),
        )

        # Store in RAG
        self.store_to_rag(
            text=script_text,
            content_type=content_type,
            metadata={"script_id": script_id, "word_count": word_count},
        )

        result = {
            "script_id": script_id,
            "script_text": script_text,
            "tweet_text": tweet_text,
            "word_count": word_count,
            "estimated_duration": round(est_duration, 1),
            "target_duration": target_duration,
            "news_ids": news_ids,
            "content_type": content_type,
        }

        logger.info(
            "Script generated: %s (%d words, ~%.0fs)",
            script_id[:8],
            word_count,
            est_duration,
        )
        return result

    # ================================================================
    # Helpers
    # ================================================================

    @staticmethod
    def _extract_tweet(text: str) -> tuple:
        """
        Split script text and tweet caption at [تغريدة] marker.
        Returns (script_text, tweet_text).
        """
        marker = "[تغريدة]"
        if marker in text:
            parts = text.split(marker, 1)
            script_text = parts[0].strip()
            tweet_text = parts[1].strip()[:280]
            return script_text, tweet_text
        # Fallback: no marker found — no tweet
        return text.strip(), None

    @staticmethod
    def _format_news(articles: List[Dict[str, Any]]) -> str:
        """Format news articles for the prompt."""
        if not articles:
            return "No specific news articles provided. Generate based on general gaming trends."

        parts = []
        for i, a in enumerate(articles[:5], 1):
            parts.append(
                f"{i}. [{a.get('source', 'Unknown')}] {a.get('title', 'N/A')}\n"
                f"   {a.get('summary', 'No summary')[:300]}"
            )
        return "\n\n".join(parts)

    @staticmethod
    def _store_script(
        script_text: str,
        tweet_text: Optional[str],
        content_type: str,
        news_ids: List[str],
        trigger_source: str = "auto",
    ) -> str:
        """Store generated script in database, return script_id."""
        script_id = str(uuid.uuid4())

        # Convert news_ids to PostgreSQL UUID array
        news_ids_array = "{" + ",".join(news_ids) + "}" if news_ids else None

        execute_query(
            """
            INSERT INTO generated_scripts
                (id, content_type, script_text, tweet_text, news_ids, status, trigger_source)
            VALUES (%s, %s, %s, %s, %s, 'draft', %s)
            """,
            (
                script_id,
                content_type,
                script_text,
                tweet_text,
                news_ids_array,
                trigger_source,
            ),
        )

        return script_id
