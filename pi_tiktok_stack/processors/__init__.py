# -*- coding: utf-8 -*-
"""
processors — LLM chain nodes for the Instagram Reels pipeline.

Each processor wraps a single Gemini call with RAG context:
  Planner      — content planning (gate 0)
  Writer       — script generation (gate 2)
  Validator    — quality scoring   (gate 2)
  ClipSelector — footage selection (gate 4)
  SEO          — caption & hashtags (gate 5)
"""
from .planner import Planner
from .writer import Writer
from .validator import Validator
from .clip import ClipSelector
from .seo import SEO

__all__ = ["Planner", "Writer", "Validator", "ClipSelector", "SEO"]
