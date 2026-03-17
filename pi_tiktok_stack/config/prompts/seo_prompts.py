# -*- coding: utf-8 -*-
"""SEO prompts — loads from skills/seo.md"""
from config.prompts.loader import skill

SEO_SYSTEM_PROMPT: str = skill("seo", section="system")


def get_seo_prompt(
    script_text: str,
    content_type: str,
    topics: str,
    duration_seconds: int,
    validation_score: int,
) -> str:
    return skill(
        "seo", section="user",
        script_text=script_text,
        content_type=content_type,
        topics=topics,
        duration_seconds=duration_seconds,
        validation_score=validation_score,
    )
