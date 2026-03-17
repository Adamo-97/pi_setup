# -*- coding: utf-8 -*-
"""
SEO Processor — Instagram Caption & Hashtag Generation
===================================================
Generates an optimised Instagram caption, stratified hashtag sets,
alt text, and posting-time recommendations for each approved Reel.

Runs after script validation (gate 3) and before video assembly,
so the caption is ready when the Reel is published in step 7.

Prompt skills:
    config/prompts/skills/seo.md (SYSTEM section)   — persona & SEO rules
    config/prompts/skills/seo.md (USER section)  — user prompt template
"""

import json
import logging
import uuid
from typing import Optional

from processors.base import BaseProcessor
from config.settings import settings
from config.prompts.seo_prompts import SEO_SYSTEM_PROMPT, get_seo_prompt

logger = logging.getLogger("tiktok.seo_agent")


class SEO(BaseProcessor):
    """
    Generates Instagram-optimised captions and hashtag strategy via Gemini.

    Output schema (all fields returned in the result dict):
        caption              — Arabic caption text (no hashtags)
        caption_en           — Optional English caption
        hashtags_caption     — 3-5 hashtags to embed in the caption itself
        hashtags_first_comment — 15-20 hashtags for the first comment
        keywords_used        — list of SEO keywords used
        alt_text             — accessibility description of the video
        best_post_time       — suggested posting time (KSA timezone)
        content_labels       — content category labels
        seo_id               — unique ID for this SEO result
    """

    def __init__(self):
        super().__init__(name="SEO Processor (TikTok)")
        self._task_model = settings.gemini.model_writer

    def run(
        self,
        script_text: str,
        content_type: str,
        topics: str,
        duration_seconds: int,
        validation_score: int = 80,
        script_id: Optional[str] = None,
    ) -> dict:
        """
        Generate SEO caption and hashtags for an approved script.

        Args:
            script_text:      The voiceover script (used for topic extraction).
            content_type:     Pipeline content type (trending_news, game_spotlight, etc.).
            topics:           Comma-separated game/topic names from the plan.
            duration_seconds: Target Reel duration in seconds.
            validation_score: Script quality score from the validator (0-100).
            script_id:        UUID of the validated script (for logging).

        Returns:
            dict with seo_id, caption, hashtags_caption, hashtags_first_comment,
            alt_text, best_post_time, keywords_used, content_labels.
        """
        seo_id = str(uuid.uuid4())
        logger.info(
            "SEO generation — content_type=%s topics=%s script_id=%s",
            content_type, topics, script_id,
        )

        prompt = get_seo_prompt(
            script_text=script_text,
            content_type=content_type,
            topics=topics,
            duration_seconds=duration_seconds,
            validation_score=validation_score,
        )

        raw = self.gemini.generate_json(
            prompt=prompt,
            system_prompt=SEO_SYSTEM_PROMPT,
            model_override=self._task_model,
        )

        # Sanitise / provide defaults for any missing keys
        result = {
            "seo_id": seo_id,
            "script_id": script_id,
            "caption": raw.get("caption", ""),
            "caption_en": raw.get("caption_en", ""),
            "hashtags_caption": raw.get("hashtags_caption", ""),
            "hashtags_first_comment": raw.get("hashtags_first_comment", ""),
            "keywords_used": raw.get("keywords_used", []),
            "alt_text": raw.get("alt_text", ""),
            "best_post_time": raw.get("best_post_time", "19:00 KSA"),
            "content_labels": raw.get("content_labels", ["Gaming", "Arabic", "Reels"]),
        }

        # Build the full caption text Buffer will receive
        result["full_caption"] = (
            result["caption"].strip()
            + ("\n\n" + result["hashtags_caption"] if result["hashtags_caption"] else "")
        )

        logger.info(
            "SEO complete — caption_len=%d hashtags_in_caption=%d",
            len(result["caption"]),
            len(result["hashtags_caption"].split()),
        )
        return result
