# -*- coding: utf-8 -*-
"""
processors — LLM chain nodes for the TikTok pipeline.

  Planner      — content planning (gate 0)
  Writer       — script generation (gate 2)
  Validator    — quality scoring   (gate 2)
  ClipSelector — footage selection (gate 4)
"""
from .planner import Planner
from .writer import Writer
from .validator import Validator
from .clip import ClipSelector

__all__ = ["Planner", "Writer", "Validator", "ClipSelector"]
