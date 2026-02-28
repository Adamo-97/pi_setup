# -*- coding: utf-8 -*-
"""
Gemini Service
==============
Wrapper for Google Gemini API: text generation, JSON generation, embeddings.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import google.generativeai as genai

from config.settings import settings

logger = logging.getLogger("tiktok.gemini")


class GeminiService:
    """Thin wrapper around the ``google-generativeai`` SDK."""

    def __init__(self):
        cfg = settings.gemini
        genai.configure(api_key=cfg.api_key)
        self._model_name = cfg.model
        self._embedding_model = cfg.embedding_model
        self._temperature = cfg.temperature
        self._max_tokens = cfg.max_output_tokens

    # ---- Text generation -------------------------------------------

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: int = 3,
    ) -> str:
        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
        )
        gen_config = genai.types.GenerationConfig(
            temperature=temperature or self._temperature,
            max_output_tokens=self._max_tokens,
        )

        for attempt in range(1, max_retries + 1):
            try:
                response = model.generate_content(prompt, generation_config=gen_config)
                return response.text
            except Exception as exc:
                logger.warning(
                    "Gemini attempt %d/%d failed: %s", attempt, max_retries, exc
                )
                if attempt < max_retries:
                    time.sleep(2**attempt)
                else:
                    raise

    # ---- JSON generation -------------------------------------------

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        raw = self.generate_text(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature or 0.3,
            max_retries=max_retries,
        )
        # Strip markdown code fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        return json.loads(cleaned)

    # ---- Embeddings ------------------------------------------------

    def generate_embedding(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[float]:
        result = genai.embed_content(
            model=self._embedding_model,
            content=text,
            task_type=task_type,
        )
        return result["embedding"]

    def generate_embeddings_batch(
        self,
        texts: List[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        embeddings = []
        for text in texts:
            embeddings.append(self.generate_embedding(text, task_type))
            time.sleep(0.5)  # rate-limit safety
        return embeddings
