# -*- coding: utf-8 -*-
"""Planner prompts — loads from skills/planner.md"""
from config.prompts.loader import skill

PLANNER_SYSTEM_PROMPT: str = skill("planner", section="system")


def get_planner_prompt(
    trending_games: str,
    covered_topics: str,
    remaining_budget: int,
    current_date: str,
    news_data: str = "",
) -> str:
    return skill(
        "planner", section="user",
        trending_games=trending_games,
        covered_topics=covered_topics,
        remaining_budget=remaining_budget,
        current_date=current_date,
        news_data=news_data,
    )
