# -*- coding: utf-8 -*-
"""Clip prompts — loads from skills/clip.md"""
from config.prompts.loader import skill

CLIP_SYSTEM_PROMPT: str = skill("clip", section="system")
CLIP_SELECTION_PROMPT: str = skill("clip", section="user")
