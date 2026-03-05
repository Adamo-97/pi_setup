# -*- coding: utf-8 -*-
"""Metadata prompts — loads from skills/metadata.md"""
from config.prompts.loader import skill

METADATA_SYSTEM_PROMPT: str = skill("metadata", section="system")
METADATA_GENERATION_PROMPT: str = skill("metadata", section="user")
