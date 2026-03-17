# -*- coding: utf-8 -*-
"""Writer prompts — system from skills/writer.md, variants from skills/writer_*.md"""
from config.prompts.loader import skill

WRITER_SYSTEM_PROMPT: str = skill("writer", section="system")

WRITER_PROMPTS: dict[str, str] = {
    "upcoming_games":  skill("writer_upcoming_games"),
    "game_review":     skill("writer_game_review"),
    "industry_news":   skill("writer_industry_news"),
    "monthly_games":   skill("writer_monthly_games"),
}


def get_writer_prompt(content_type_id: str) -> str:
    """Return the writer prompt template for a given content type."""
    if content_type_id not in WRITER_PROMPTS:
        raise ValueError(
            f"No writer prompt for content type '{content_type_id}'. "
            f"Available: {list(WRITER_PROMPTS.keys())}"
        )
    return WRITER_PROMPTS[content_type_id]
