# -*- coding: utf-8 -*-
"""config/prompts — YouTube pipeline prompts."""
from .loader import skill, list_skills
from .planner_prompts import PLANNER_SYSTEM_PROMPT, get_planner_prompt
from .writer_prompts import WRITER_SYSTEM_PROMPT, WRITER_PROMPTS, get_writer_prompt
from .validator_prompts import VALIDATOR_SYSTEM_PROMPT, VALIDATOR_REVIEW_PROMPT
from .metadata_prompts import METADATA_SYSTEM_PROMPT, METADATA_GENERATION_PROMPT
