# -*- coding: utf-8 -*-
"""
ElevenLabs Service
==================
Arabic TTS with word-level timestamps for subtitle generation.
"""

import io
import json
import logging
import struct
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from config.settings import settings

logger = logging.getLogger("tiktok.elevenlabs")


class ElevenLabsService:
    """Generates Arabic voiceovers via ElevenLabs API."""

    API_BASE = "https://api.elevenlabs.io/v1"

    def __init__(self):
        cfg = settings.elevenlabs
        self._api_key = cfg.api_key
        self._voice_id = cfg.voice_id
        self._model = cfg.model
        self._sample_rate = cfg.sample_rate

    def _headers(self) -> dict:
        return {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }

    # ---- Voiceover with timestamps ---------------------------------

    def generate_voiceover(
        self,
        text: str,
        output_path: str,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """
        Generate voiceover and return metadata including word timestamps.

        Returns:
            {
                "file_path": str,
                "duration": float,
                "word_timestamps": [{"word": str, "start": float, "end": float}]
            }
        """
        cfg = settings.elevenlabs
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        url = f"{self.API_BASE}/text-to-speech/{self._voice_id}/with-timestamps"

        payload = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.4,
            },
            "output_format": cfg.output_format,
        }

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers=self._headers(),
                    timeout=300,
                )
                resp.raise_for_status()
                result = resp.json()

                # Extract audio bytes
                audio_b64 = result.get("audio_base64", "")
                if audio_b64:
                    import base64

                    audio_bytes = base64.b64decode(audio_b64)
                else:
                    # Fallback: no timestamps endpoint, use streaming
                    return self._generate_voiceover_stream(text, output_path)

                # Write WAV
                self._pcm_to_wav(audio_bytes, str(output_file))

                # Extract word timestamps
                word_timestamps = []
                alignment = result.get("alignment", {})
                chars = alignment.get("characters", [])
                char_starts = alignment.get("character_start_times_seconds", [])
                char_ends = alignment.get("character_end_times_seconds", [])

                if chars and char_starts and char_ends:
                    word_timestamps = self._chars_to_words(
                        chars, char_starts, char_ends
                    )

                duration = self._get_wav_duration(str(output_file))
                logger.info(
                    "Voiceover generated: %.1fs, %d words, %s",
                    duration,
                    len(word_timestamps),
                    output_file.name,
                )

                return {
                    "file_path": str(output_file),
                    "duration": duration,
                    "word_timestamps": word_timestamps,
                }

            except Exception as exc:
                logger.warning(
                    "ElevenLabs attempt %d/%d failed: %s",
                    attempt,
                    max_retries,
                    exc,
                )
                if attempt < max_retries:
                    time.sleep(2**attempt)
                else:
                    raise

    def _generate_voiceover_stream(
        self,
        text: str,
        output_path: str,
    ) -> Dict[str, Any]:
        """Fallback: streaming without timestamps."""
        url = f"{self.API_BASE}/text-to-speech/{self._voice_id}/stream"
        payload = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.4,
            },
            "output_format": settings.elevenlabs.output_format,
        }

        resp = requests.post(
            url,
            json=payload,
            headers=self._headers(),
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()

        pcm_buffer = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=4096):
            if chunk:
                pcm_buffer.write(chunk)

        self._pcm_to_wav(pcm_buffer.getvalue(), output_path)
        duration = self._get_wav_duration(output_path)

        # Estimate timestamps without API support
        word_timestamps = self._estimate_timestamps(text, duration)

        return {
            "file_path": output_path,
            "duration": duration,
            "word_timestamps": word_timestamps,
        }

    # ---- Helpers ---------------------------------------------------

    @staticmethod
    def _chars_to_words(
        chars: List[str],
        starts: List[float],
        ends: List[float],
    ) -> List[Dict[str, Any]]:
        """Convert character-level timestamps to word-level."""
        words = []
        current_word = ""
        word_start = 0.0

        for i, char in enumerate(chars):
            if char == " " or i == len(chars) - 1:
                if i == len(chars) - 1 and char != " ":
                    current_word += char
                if current_word.strip():
                    words.append(
                        {
                            "word": current_word.strip(),
                            "start": round(word_start, 3),
                            "end": round(ends[i - 1] if char == " " else ends[i], 3),
                        }
                    )
                current_word = ""
                if i + 1 < len(starts):
                    word_start = starts[i + 1]
            else:
                if not current_word:
                    word_start = starts[i]
                current_word += char

        return words

    @staticmethod
    def _estimate_timestamps(text: str, duration: float) -> List[Dict[str, Any]]:
        """Estimate word timestamps based on even distribution."""
        words = text.split()
        if not words:
            return []
        word_duration = duration / len(words)
        result = []
        for i, word in enumerate(words):
            result.append(
                {
                    "word": word,
                    "start": round(i * word_duration, 3),
                    "end": round((i + 1) * word_duration, 3),
                }
            )
        return result

    def _pcm_to_wav(self, pcm_data: bytes, output_path: str) -> None:
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self._sample_rate)
            wf.writeframes(pcm_data)

    @staticmethod
    def _get_wav_duration(path: str) -> float:
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / wf.getframerate()

    def get_usage(self) -> Dict[str, Any]:
        resp = requests.get(
            f"{self.API_BASE}/user/subscription",
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "character_count": data.get("character_count", 0),
            "character_limit": data.get("character_limit", 0),
            "remaining": data.get("character_limit", 0)
            - data.get("character_count", 0),
        }
