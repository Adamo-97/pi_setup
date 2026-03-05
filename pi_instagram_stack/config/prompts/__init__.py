# -*- coding: utf-8 -*-
"""
config/prompts — all pipeline prompts in one place.

Edit markdown files in skills/ to tune pipeline behaviour:
  skills/planner.md                — Gate 0: content planner (system + user)
  skills/writer.md                 — Gate 2: script writer persona
  skills/writer_trending_news.md   — Gate 2: trending news script
  skills/writer_game_spotlight.md  — Gate 2: single-game spotlight
  skills/writer_hardware_spotlight.md — Gate 2: hardware review
  skills/writer_trailer_reaction.md   — Gate 2: trailer reaction
  skills/validator.md              — Gate 2: scoring criteria + review template
  skills/clip.md                   — Gate 4: footage selection (system + user)
  skills/seo.md                    — Gate 5: SEO caption + hashtag (system + user)

Section markers: <!-- SYSTEM --> and <!-- USER --> split persona from task.
"""
from .loader import skill, list_skills
from .planner_prompts import PLANNER_SYSTEM_PROMPT, get_planner_prompt
from .writer_prompts import WRITER_SYSTEM_PROMPT, WRITER_PROMPTS
from .validator_prompts import VALIDATOR_SYSTEM_PROMPT, VALIDATOR_REVIEW_PROMPT
from .clip_prompts import CLIP_SYSTEM_PROMPT, CLIP_SELECTION_PROMPT
from .seo_prompts import SEO_SYSTEM_PROMPT, get_seo_prompt

__all__ = [
    "skill", "list_skills",
    "PLANNER_SYSTEM_PROMPT", "get_planner_prompt",
    "WRITER_SYSTEM_PROMPT", "WRITER_PROMPTS",
    "VALIDATOR_SYSTEM_PROMPT", "VALIDATOR_REVIEW_PROMPT",
    "CLIP_SYSTEM_PROMPT", "CLIP_SELECTION_PROMPT",
    "SEO_SYSTEM_PROMPT", "get_seo_prompt",
]
