# -*- coding: utf-8 -*-
"""Writer prompts — system from skills/writer.md, variants from skills/writer_*.md"""
from config.prompts.loader import skill

WRITER_SYSTEM_PROMPT: str = skill("writer", section="system")

WRITER_PROMPTS: dict[str, str] = {
    "trending_news":      skill("writer_trending_news"),
    "game_spotlight":     skill("writer_game_spotlight"),
    "controversial_take": skill("writer_controversial_take"),
    "trailer_reaction":   skill("writer_trailer_reaction"),
}
