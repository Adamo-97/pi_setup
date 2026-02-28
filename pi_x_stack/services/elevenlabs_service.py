# -*- coding: utf-8 -*-
"""
ElevenLabs TTS Service
======================
Arabic voiceover generation with word-level timestamps for subtitle sync.
"""

import logging
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config.settings import settings

logger = logging.getLogger("x.elevenlabs")


class ElevenLabsService:
    """ElevenLabs text-to-speech with word-level timestamps."""

    API_BASE = "https://api.elevenlabs.io/v1"

    def __init__(self):
        cfg = settings.elevenlabs
        self._api_key = cfg.api_key
        self._voice_id = cfg.voice_id
        self._model = cfg.model
        self._output_format = cfg.output_format
        self._sample_rate = cfg.sample_rate

    def _headers(self) -> Dict[str, str]:
        return {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
        }

    # ================================================================
    # Main entry — generate voiceover with timestamps
    # ================================================================

    def generate_voiceover(
        self,
        text: str,
        output_path: str,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Generate Arabic voiceover with word-level timestamps.

        Returns:
            dict with file_path, duration, word_timestamps
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(max_retries + 1):
            try:
                result = self._generate_with_timestamps(text, output_path)
                if result:
                    return result
            except Exception as e:
                logger.warning("TTS attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries:
                    time.sleep(2**attempt)

        # Fallback: stream without timestamps
        logger.warning("Falling back to stream-based TTS (no timestamps)")
        return self._generate_voiceover_stream(text, output_path)

    # ================================================================
    # With-timestamps endpoint
    # ================================================================

    def _generate_with_timestamps(
        self, text: str, output_path: str
    ) -> Optional[Dict[str, Any]]:
        url = (
            f"{self.API_BASE}/text-to-speech/{self._voice_id}"
            f"/with-timestamps?output_format={self._output_format}"
        )
        payload = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.3,
            },
        }

        resp = requests.post(url, json=payload, headers=self._headers(), timeout=120)
        resp.raise_for_status()
        data = resp.json()

        # Decode audio
        import base64

        audio_b64 = data.get("audio_base64", "")
        if not audio_b64:
            return None

        audio_bytes = base64.b64decode(audio_b64)
        self._pcm_to_wav(audio_bytes, output_path)

        duration = self._get_wav_duration(output_path)

        # Extract character-level alignment → word-level
        alignment = data.get("alignment", {})
        chars = alignment.get("characters", [])
        starts = alignment.get("character_start_times_seconds", [])
        ends = alignment.get("character_end_times_seconds", [])

        word_timestamps = self._chars_to_words(chars, starts, ends)

        logger.info(
            "Voiceover generated: %.1fs, %d words", duration, len(word_timestamps)
        )

        return {
            "file_path": output_path,
            "duration": duration,
            "word_timestamps": word_timestamps,
            "sample_rate": self._sample_rate,
        }

    # ================================================================
    # Stream fallback
    # ================================================================

    def _generate_voiceover_stream(self, text: str, output_path: str) -> Dict[str, Any]:
        url = (
            f"{self.API_BASE}/text-to-speech/{self._voice_id}"
            f"/stream?output_format={self._output_format}"
        )
        payload = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        resp = requests.post(
            url, json=payload, headers=self._headers(), stream=True, timeout=120
        )
        resp.raise_for_status()

        pcm_data = b""
        for chunk in resp.iter_content(chunk_size=8192):
            pcm_data += chunk

        self._pcm_to_wav(pcm_data, output_path)
        duration = self._get_wav_duration(output_path)
        word_timestamps = self._estimate_timestamps(text, duration)

        return {
            "file_path": output_path,
            "duration": duration,
            "word_timestamps": word_timestamps,
            "sample_rate": self._sample_rate,
        }

    # ================================================================
    # Utilities
    # ================================================================

    @staticmethod
    def _chars_to_words(
        chars: List[str], starts: List[float], ends: List[float]
    ) -> List[Dict[str, Any]]:
        """Convert character-level alignment to word-level timestamps."""
        if not chars or len(chars) != len(starts) or len(chars) != len(ends):
            return []

        words = []
        current_word = ""
        word_start = 0.0

        for i, char in enumerate(chars):
            if char == " ":
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

        # Last word
        if current_word.strip():
            words.append(
                {
                    "word": current_word.strip(),
                    "start": round(word_start, 3),
                    "end": round(ends[-1], 3),
                }
            )

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
