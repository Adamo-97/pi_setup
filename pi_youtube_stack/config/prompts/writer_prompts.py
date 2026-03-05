# -*- coding: utf-8 -*-
"""Writer prompts — system from skills/writer.md, variants from skills/writer_*.md"""
from config.prompts.loader import skill

WRITER_SYSTEM_PROMPT: str = skill("writer", section="system")

WRITER_PROMPTS: dict[str, str] = {
    "monthly_releases": skill("writer_monthly_releases"),
    "aaa_review":       skill("writer_aaa_review"),
    "upcoming_games":   skill("writer_upcoming_games"),
}


def get_writer_prompt(content_type_id: str) -> str:
    """Return the writer prompt template for a given content type."""
    if content_type_id not in WRITER_PROMPTS:
        raise ValueError(
            f"No writer prompt for content type \'{content_type_id}\'. "
            f"Available: {list(WRITER_PROMPTS.keys())}"
        )
    return WRITER_PROMPTS[content_type_id]
