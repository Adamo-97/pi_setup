# -*- coding: utf-8 -*-
"""Validator prompts — loads from skills/validator.md"""
from config.prompts.loader import skill

VALIDATOR_SYSTEM_PROMPT: str = skill("validator", section="system")
VALIDATOR_REVIEW_PROMPT: str = skill("validator", section="user")
