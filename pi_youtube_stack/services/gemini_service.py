# -*- coding: utf-8 -*-
"""
Gemini API Service
====================
Wrapper for Google's Gemini API, handling:
  - Text generation (for Writer, Validator, Metadata agents)
  - Embedding generation (for RAG storage & retrieval)
  - Retry logic with exponential backoff
  - Clean error handling

Uses the google-generativeai SDK.
"""

import json
import logging
import time
from typing import Optional

import google.generativeai as genai

from config.settings import settings

logger = logging.getLogger(__name__)


class GeminiService:
    """
    Google Gemini API client for text generation and embeddings.

    Usage:
        service = GeminiService()
        response = service.generate_text("Your prompt here", system_prompt="...")
        embedding = service.generate_embedding("Text to embed")
    """

    # Retry configuration
    MAX_RETRIES = 3
    BASE_DELAY = 2  # seconds

    def __init__(self):
        """Initialize the Gemini client with API key from settings."""
        cfg = settings.gemini
        genai.configure(api_key=cfg.api_key)

        # Configure the generative model
        self.model = genai.GenerativeModel(
            model_name=cfg.model,
            generation_config=genai.GenerationConfig(
                temperature=cfg.temperature,
                max_output_tokens=cfg.max_output_tokens,
                top_p=cfg.top_p,
                top_k=cfg.top_k,
            ),
        )
        self.model_name = cfg.model
        logger.info("GeminiService initialized with model: %s", cfg.model)

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Generate text using the Gemini model.

        Args:
            prompt: The user/generation prompt.
            system_prompt: Optional system instruction to set agent behavior.
            temperature: Override default temperature for this call.
            max_tokens: Override default max tokens for this call.

        Returns:
            The generated text string.

        Raises:
            RuntimeError: If all retries are exhausted.
        """
        # Build generation config overrides if provided
        gen_config_overrides = {}
        if temperature is not None:
            gen_config_overrides["temperature"] = temperature
        if max_tokens is not None:
            gen_config_overrides["max_output_tokens"] = max_tokens

        # Build the model with system instruction if provided
        model = self.model
        if system_prompt:
            cfg = settings.gemini
            model = genai.GenerativeModel(
                model_name=cfg.model,
                system_instruction=system_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=temperature or cfg.temperature,
                    max_output_tokens=max_tokens or cfg.max_output_tokens,
                    top_p=cfg.top_p,
                    top_k=cfg.top_k,
                ),
            )

        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.debug(
                    "Gemini generate attempt %d/%d (prompt_len=%d)",
                    attempt,
                    self.MAX_RETRIES,
                    len(prompt),
                )

                response = model.generate_content(prompt)

                # Check for blocked content
                if not response.candidates:
                    raise RuntimeError(
                        "Gemini returned no candidates — content may have been blocked. "
                        f"Prompt feedback: {response.prompt_feedback}"
                    )

                text = response.text.strip()
                logger.info(
                    "Gemini generated %d chars on attempt %d.", len(text), attempt
                )
                return text

            except Exception as exc:
                last_error = exc
                delay = self.BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Gemini attempt %d failed: %s — retrying in %ds...",
                    attempt,
                    str(exc)[:200],
                    delay,
                )
                time.sleep(delay)

        raise RuntimeError(
            f"Gemini generation failed after {self.MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> dict:
        """
        Generate text and parse it as JSON.
        Handles cases where the model wraps JSON in markdown code fences.

        Args:
            prompt: The generation prompt (should ask for JSON output).
            system_prompt: Optional system instruction.
            temperature: Override temperature.

        Returns:
            Parsed JSON as a Python dict.

        Raises:
            ValueError: If the response cannot be parsed as JSON.
        """
        raw_text = self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature or 0.3,  # Lower temp for structured output
        )

        # Strip markdown code fences if present
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error(
                "Failed to parse Gemini JSON response. Raw text:\n%s", raw_text[:500]
            )
            raise ValueError(
                f"Gemini returned invalid JSON: {exc}. "
                f"Response preview: {raw_text[:200]}"
            ) from exc

    def generate_embedding(
        self,
        text: str,
        task_type: str = "retrieval_document",
    ) -> list[float]:
        """
        Generate an embedding vector for the given text.

        Args:
            text: The text to embed.
            task_type: Embedding task type. Options:
                - "retrieval_document" — for storing documents
                - "retrieval_query" — for search queries
                - "semantic_similarity" — for comparing texts

        Returns:
            List of floats representing the embedding vector.
        """
        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = genai.embed_content(
                    model="models/embedding-001",
                    content=text,
                    task_type=task_type,
                )
                embedding = result["embedding"]
                logger.debug(
                    "Generated embedding: dim=%d, text_len=%d",
                    len(embedding),
                    len(text),
                )
                return embedding

            except Exception as exc:
                last_error = exc
                delay = self.BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Embedding attempt %d failed: %s — retrying in %ds...",
                    attempt,
                    str(exc)[:200],
                    delay,
                )
                time.sleep(delay)

        raise RuntimeError(
            f"Embedding generation failed after {self.MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    def generate_embeddings_batch(
        self,
        texts: list[str],
        task_type: str = "retrieval_document",
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.
            task_type: Embedding task type.

        Returns:
            List of embedding vectors (one per input text).
        """
        embeddings = []
        for i, text in enumerate(texts):
            logger.debug("Batch embedding %d/%d...", i + 1, len(texts))
            emb = self.generate_embedding(text, task_type)
            embeddings.append(emb)
            # Small delay to avoid rate limits on Pi
            if i < len(texts) - 1:
                time.sleep(0.5)
        return embeddings
