# -*- coding: utf-8 -*-
"""
processors — LLM chain nodes for the YouTube pipeline.

  Planner   — content planning  (gate 0)
  Writer    — script generation (gate 2)
  Validator — quality scoring   (gate 2)
  Metadata  — YouTube SEO       (gate 3)
"""
from .planner import Planner
from .writer import Writer
from .validator import Validator
from .metadata import Metadata

__all__ = ["Planner", "Writer", "Validator", "Metadata"]
