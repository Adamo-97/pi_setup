# -*- coding: utf-8 -*-
"""config/prompts — X/Twitter pipeline prompts."""
from .loader import skill, list_skills
from .planner_prompts import PLANNER_SYSTEM_PROMPT, get_planner_prompt
from .writer_prompts import WRITER_SYSTEM_PROMPT, WRITER_PROMPTS
from .validator_prompts import VALIDATOR_SYSTEM_PROMPT, VALIDATOR_REVIEW_PROMPT
from .clip_prompts import CLIP_SYSTEM_PROMPT, CLIP_SELECTION_PROMPT
