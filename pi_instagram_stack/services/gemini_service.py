# -*- coding: utf-8 -*-
"""
Gemini Service
==============
Wrapper around Google Generative AI for text generation, JSON output,
and embedding creation.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from config.settings import settings

logger = logging.getLogger("instagram.gemini")


class GeminiService:
    """Google Gemini AI client for the Instagram Reels pipeline."""

    def __init__(self):
        cfg = settings.gemini
        genai.configure(api_key=cfg.api_key)
        self._model = genai.GenerativeModel(cfg.model)
        self._embed_model = cfg.embedding_model
        self._temperature = cfg.temperature
        self._max_tokens = cfg.max_output_tokens

    # ================================================================
    # Text generation
    # ================================================================

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: int = 2,
    ) -> str:
        """Generate text using Gemini."""
        temp = temperature or self._temperature
        config = genai.types.GenerationConfig(
            temperature=temp,
            max_output_tokens=self._max_tokens,
        )

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [system_prompt]})
            contents.append(
                {
                    "role": "model",
                    "parts": ["understood, I will follow these instructions."],
                }
            )
        contents.append({"role": "user", "parts": [prompt]})

        for attempt in range(max_retries + 1):
            try:
                response = self._model.generate_content(
                    contents,
                    generation_config=config,
                )
                return response.text
            except Exception as e:
                logger.warning("Gemini attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries:
                    time.sleep(2**attempt)
                else:
                    raise

    # ================================================================
    # JSON generation
    # ================================================================

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """Generate and parse JSON from Gemini."""
        raw = self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature or 0.3,
            max_retries=max_retries,
        )

        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        return json.loads(cleaned)

    # ================================================================
    # Embeddings
    # ================================================================

    def generate_embedding(self, text: str) -> List[float]:
        """Generate a single embedding vector."""
        result = genai.embed_content(
            model=self._embed_model,
            content=text,
            task_type="retrieval_document",
        )
        return result["embedding"]

    def generate_embeddings_batch(
        self, texts: List[str], batch_size: int = 20
    ) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            result = genai.embed_content(
                model=self._embed_model,
                content=batch,
                task_type="retrieval_document",
            )
            all_embeddings.extend(result["embedding"])
            if i + batch_size < len(texts):
                time.sleep(0.5)
        return all_embeddings
