# -*- coding: utf-8 -*-
"""
Gemini Service
==============
Direct REST wrapper for Google Gemini API.
Uses requests instead of the deprecated google.generativeai SDK
to avoid hangs on ARM/Pi with newer models (gemini-3.x).
"""

import json
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional

import requests

from config.settings import settings

logger = logging.getLogger("youtube.gemini")

_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiService:
    """Google Gemini AI client for the YouTube pipeline (REST)."""

    def __init__(self):
        cfg = settings.gemini
        self._api_key = cfg.api_key
        self._model = cfg.model
        self._embed_model = cfg.embedding_model
        self._temperature = cfg.temperature
        self._max_tokens = cfg.max_output_tokens
        self._timeout = 120  # seconds per API call

    # ================================================================
    # Text generation
    # ================================================================

    def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_retries: int = 5,
        model_override: Optional[str] = None,
    ) -> str:
        """Generate text using Gemini REST API."""
        temp = temperature if temperature is not None else self._temperature
        model = model_override or self._model

        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
            contents.append(
                {"role": "model", "parts": [{"text": "understood, I will follow these instructions."}]}
            )
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temp,
                "maxOutputTokens": self._max_tokens,
            },
        }

        url = f"{_BASE}/models/{model}:generateContent?key={self._api_key}"

        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self._timeout)
                if resp.status_code == 429 or resp.status_code == 503:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and resp.status_code == 429:
                        time.sleep(float(retry_after))
                    else:
                        time.sleep(2**attempt + random.uniform(0, 1))
                    if attempt < max_retries:
                        logger.warning("Gemini %d on attempt %d, retrying...", resp.status_code, attempt + 1)
                        continue
                    resp.raise_for_status()
                elif resp.status_code >= 400:
                    resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    err = data.get("error", {}).get("message", "No candidates returned")
                    raise RuntimeError(f"Gemini returned no candidates: {err}")
                finish_reason = candidates[0].get("finishReason", "STOP")
                text = candidates[0]["content"]["parts"][0]["text"]
                if finish_reason == "MAX_TOKENS" and attempt < max_retries:
                    logger.warning("Gemini response truncated (MAX_TOKENS) on attempt %d, retrying...", attempt + 1)
                    time.sleep(2**attempt + random.uniform(0, 1))
                    continue
                return text
            except requests.exceptions.HTTPError:
                raise
            except Exception as e:
                logger.warning("Gemini attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries:
                    time.sleep(2**attempt + random.uniform(0, 1))
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
        max_retries: int = 5,
        model_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate and parse JSON from Gemini."""
        raw = self.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature if temperature is not None else 0.3,
            max_retries=max_retries,
            model_override=model_override,
        )

        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw)
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        return json.loads(cleaned)

    # ================================================================
    # Embeddings
    # ================================================================

    def generate_embedding(self, text: str, max_retries: int = 5) -> List[float]:
        """Generate a single embedding vector via REST."""
        url = f"{_BASE}/{self._embed_model}:embedContent?key={self._api_key}"
        payload = {
            "model": self._embed_model,
            "content": {"parts": [{"text": text}]},
            "taskType": "RETRIEVAL_DOCUMENT",
        }
        for attempt in range(max_retries + 1):
            try:
                resp = requests.post(url, json=payload, timeout=self._timeout)
                if resp.status_code in (429, 503):
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after and resp.status_code == 429:
                        time.sleep(float(retry_after))
                    else:
                        time.sleep(2**attempt + random.uniform(0, 1))
                    if attempt < max_retries:
                        logger.warning("Embedding %d on attempt %d, retrying...", resp.status_code, attempt + 1)
                        continue
                    resp.raise_for_status()
                elif resp.status_code >= 400:
                    resp.raise_for_status()
                return resp.json()["embedding"]["values"]
            except requests.exceptions.HTTPError:
                raise
            except Exception as e:
                logger.warning("Embedding attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries:
                    time.sleep(2**attempt + random.uniform(0, 1))
                else:
                    raise

    def generate_embeddings_batch(
        self, texts: List[str], batch_size: int = 20, max_retries: int = 5
    ) -> List[List[float]]:
        """Generate embeddings for a batch of texts via REST."""
        url = f"{_BASE}/{self._embed_model}:batchEmbedContents?key={self._api_key}"
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            requests_list = [
                {
                    "model": self._embed_model,
                    "content": {"parts": [{"text": t}]},
                    "taskType": "RETRIEVAL_DOCUMENT",
                }
                for t in batch
            ]
            for attempt in range(max_retries + 1):
                try:
                    resp = requests.post(
                        url, json={"requests": requests_list}, timeout=self._timeout
                    )
                    if resp.status_code in (429, 503):
                        retry_after = resp.headers.get("Retry-After")
                        if retry_after and resp.status_code == 429:
                            time.sleep(float(retry_after))
                        else:
                            time.sleep(2**attempt + random.uniform(0, 1))
                        if attempt < max_retries:
                            logger.warning("Batch embedding %d on attempt %d, retrying...", resp.status_code, attempt + 1)
                            continue
                        resp.raise_for_status()
                    elif resp.status_code >= 400:
                        resp.raise_for_status()
                    for emb in resp.json()["embeddings"]:
                        all_embeddings.append(emb["values"])
                    break
                except requests.exceptions.HTTPError:
                    raise
                except Exception as e:
                    logger.warning("Batch embedding attempt %d failed: %s", attempt + 1, e)
                    if attempt < max_retries:
                        time.sleep(2**attempt + random.uniform(0, 1))
                    else:
                        raise
            if i + batch_size < len(texts):
                time.sleep(0.5)
        return all_embeddings
