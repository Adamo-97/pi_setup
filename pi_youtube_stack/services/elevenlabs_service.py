# -*- coding: utf-8 -*-
"""
ElevenLabs TTS Service
========================
Wrapper for the ElevenLabs API to generate Arabic voiceovers
using a cloned voice. Outputs .wav files.

Features:
  - Streams audio to disk to handle large files on RPi
  - Configurable voice parameters (stability, similarity, style)
  - Retry logic for API reliability
"""

import logging
import time
import struct
import wave
from pathlib import Path
from typing import Optional

import requests

from config.settings import settings

logger = logging.getLogger(__name__)


class ElevenLabsService:
    """
    ElevenLabs TTS client for Arabic voiceover generation.

    Usage:
        service = ElevenLabsService()
        result = service.generate_voiceover(
            text="النص العربي هنا",
            output_path="/path/to/output.wav"
        )
    """

    BASE_URL = "https://api.elevenlabs.io/v1"
    MAX_RETRIES = 3
    BASE_DELAY = 3  # seconds
    CHUNK_SIZE = 4096  # bytes for streaming download

    def __init__(self):
        """Initialize with settings from .env configuration."""
        cfg = settings.elevenlabs
        self.api_key = cfg.api_key
        self.voice_id = cfg.voice_id
        self.model_id = cfg.model_id
        self.output_format = cfg.output_format
        self.stability = cfg.stability
        self.similarity_boost = cfg.similarity_boost
        self.style = cfg.style

        self.headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/wav",
        }
        logger.info(
            "ElevenLabsService initialized (voice_id=%s, model=%s, format=%s)",
            self.voice_id,
            self.model_id,
            self.output_format,
        )

    def generate_voiceover(
        self,
        text: str,
        output_path: str,
        voice_id: Optional[str] = None,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None,
        style: Optional[float] = None,
    ) -> dict:
        """
        Generate a voiceover from Arabic text and save as .wav file.

        Args:
            text: The Arabic script text to convert to speech.
            output_path: Full path where the .wav file will be saved.
            voice_id: Override the default voice ID.
            stability: Override voice stability (0-1).
            similarity_boost: Override similarity boost (0-1).
            style: Override style exaggeration (0-1).

        Returns:
            Dict with keys: file_path, file_size_bytes, duration_seconds, success.
        """
        vid = voice_id or self.voice_id
        url = f"{self.BASE_URL}/text-to-speech/{vid}"

        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": stability if stability is not None else self.stability,
                "similarity_boost": (
                    similarity_boost
                    if similarity_boost is not None
                    else self.similarity_boost
                ),
                "style": style if style is not None else self.style,
            },
        }

        # Add output format as query parameter
        params = {"output_format": self.output_format}

        # Ensure output directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(
                    "ElevenLabs TTS attempt %d/%d (text_len=%d, voice=%s)",
                    attempt,
                    self.MAX_RETRIES,
                    len(text),
                    vid,
                )

                response = requests.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    params=params,
                    stream=True,
                    timeout=300,  # 5 min timeout for long scripts
                )

                if response.status_code != 200:
                    error_msg = response.text[:500]
                    raise RuntimeError(
                        f"ElevenLabs API error {response.status_code}: {error_msg}"
                    )

                # Check if response is PCM format (needs WAV wrapping)
                if self.output_format.startswith("pcm_"):
                    # Stream raw PCM to temp, then wrap in WAV
                    pcm_path = str(output_file) + ".pcm"
                    total_bytes = 0
                    with open(pcm_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                total_bytes += len(chunk)

                    # Convert PCM to WAV
                    sample_rate = int(self.output_format.split("_")[1])
                    self._pcm_to_wav(pcm_path, str(output_file), sample_rate)

                    # Remove temp PCM file
                    Path(pcm_path).unlink(missing_ok=True)
                else:
                    # Direct WAV/MP3 stream to file
                    total_bytes = 0
                    with open(output_file, "wb") as f:
                        for chunk in response.iter_content(chunk_size=self.CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                total_bytes += len(chunk)

                # Calculate duration from file
                duration = self._get_wav_duration(str(output_file))
                file_size = output_file.stat().st_size

                logger.info(
                    "Voiceover generated: %s (%.1f KB, %.1f sec)",
                    output_file.name,
                    file_size / 1024,
                    duration,
                )

                return {
                    "file_path": str(output_file),
                    "file_size_bytes": file_size,
                    "duration_seconds": duration,
                    "success": True,
                }

            except Exception as exc:
                last_error = exc
                delay = self.BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "ElevenLabs attempt %d failed: %s — retrying in %ds...",
                    attempt,
                    str(exc)[:200],
                    delay,
                )
                time.sleep(delay)

        return {
            "file_path": str(output_file),
            "file_size_bytes": 0,
            "duration_seconds": 0,
            "success": False,
            "error": str(last_error),
        }

    @staticmethod
    def _pcm_to_wav(
        pcm_path: str,
        wav_path: str,
        sample_rate: int,
        channels: int = 1,
        sample_width: int = 2,
    ) -> None:
        """
        Wrap raw PCM audio data in a WAV container.

        Args:
            pcm_path: Path to the raw PCM file.
            wav_path: Path for the output WAV file.
            sample_rate: Sample rate in Hz (e.g., 44100).
            channels: Number of audio channels (1=mono).
            sample_width: Bytes per sample (2=16-bit).
        """
        with open(pcm_path, "rb") as pcm_file:
            pcm_data = pcm_file.read()

        with wave.open(wav_path, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)

        logger.debug(
            "Converted PCM→WAV: %s (rate=%d, ch=%d, width=%d)",
            wav_path,
            sample_rate,
            channels,
            sample_width,
        )

    @staticmethod
    def _get_wav_duration(wav_path: str) -> float:
        """
        Get the duration of a WAV file in seconds.

        Args:
            wav_path: Path to the WAV file.

        Returns:
            Duration in seconds.
        """
        try:
            with wave.open(wav_path, "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                return frames / float(rate) if rate > 0 else 0.0
        except Exception as exc:
            logger.warning("Could not determine WAV duration: %s", exc)
            return 0.0

    def get_voice_info(self) -> dict:
        """
        Retrieve information about the configured voice.

        Returns:
            Voice details from ElevenLabs API.
        """
        url = f"{self.BASE_URL}/voices/{self.voice_id}"
        try:
            response = requests.get(
                url,
                headers={"xi-api-key": self.api_key},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.error("Failed to get voice info: %s", exc)
            return {"error": str(exc)}

    def get_usage(self) -> dict:
        """
        Get current API usage/subscription info.

        Returns:
            Subscription and usage details.
        """
        url = f"{self.BASE_URL}/user/subscription"
        try:
            response = requests.get(
                url,
                headers={"xi-api-key": self.api_key},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.error("Failed to get usage info: %s", exc)
            return {"error": str(exc)}
