# -*- coding: utf-8 -*-
"""
Video Downloader Service
========================
Downloads gameplay/trailer footage via yt-dlp with local fallback.
"""

import json
import logging
import os
import random
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import settings
from database.connection import execute_query

logger = logging.getLogger("tiktok.downloader")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class VideoDownloader:
    """Downloads video footage from YouTube or picks from local library."""

    def __init__(self):
        self._cfg = settings.video
        self._footage_dir = PROJECT_ROOT / self._cfg.local_footage_dir
        self._clips_dir = PROJECT_ROOT / settings.paths.output_clips
        self._clips_dir.mkdir(parents=True, exist_ok=True)

    # ================================================================
    # YouTube download (yt-dlp)
    # ================================================================

    def download_youtube(
        self,
        search_query: str,
        output_name: Optional[str] = None,
        max_duration: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Search and download a video from YouTube.

        Args:
            search_query: e.g. "Elden Ring gameplay trailer"
            output_name: filename without extension
            max_duration: max video length in seconds

        Returns:
            dict with file_path, duration, title, source_url or None
        """
        max_dur = max_duration or self._cfg.max_download_duration
        output_name = output_name or search_query.replace(" ", "_")[:50]
        output_path = self._clips_dir / f"{output_name}.mp4"

        if output_path.exists():
            logger.info("Video already exists: %s", output_path.name)
            return self._get_video_info(str(output_path))

        cmd = [
            "yt-dlp",
            f"ytsearch1:{search_query}",
            "-f",
            self._cfg.yt_dlp_format,
            "--merge-output-format",
            "mp4",
            "--max-downloads",
            "1",
            "--match-filter",
            f"duration<={max_dur}",
            "-o",
            str(output_path),
            "--no-playlist",
            "--print-json",
            "--no-warnings",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )

            if result.returncode != 0:
                logger.warning("yt-dlp failed: %s", result.stderr[:300])
                return None

            # Parse metadata from yt-dlp JSON output
            meta = {}
            for line in result.stdout.strip().split("\n"):
                try:
                    meta = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

            info = {
                "source": "youtube",
                "source_url": meta.get("webpage_url", ""),
                "file_path": str(output_path),
                "title": meta.get("title", search_query),
                "duration": meta.get("duration", 0),
                "width": meta.get("width", 1920),
                "height": meta.get("height", 1080),
            }

            logger.info(
                "Downloaded: %s (%.0fs)",
                info["title"][:60],
                info["duration"],
            )
            return info

        except subprocess.TimeoutExpired:
            logger.error("yt-dlp timed out for: %s", search_query)
            return None
        except FileNotFoundError:
            logger.error("yt-dlp not installed. Run: pip install yt-dlp")
            return None

    # ================================================================
    # Local footage fallback
    # ================================================================

    def get_local_footage(
        self,
        game_title: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Pick a random local footage file, optionally filtered by game title."""
        if not self._footage_dir.exists():
            logger.warning("Footage directory not found: %s", self._footage_dir)
            return None

        video_exts = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
        files = [
            f for f in self._footage_dir.iterdir() if f.suffix.lower() in video_exts
        ]

        if game_title:
            # Try to find matching footage
            match = [f for f in files if game_title.lower() in f.stem.lower()]
            if match:
                files = match

        if not files:
            logger.warning("No local footage found.")
            return None

        chosen = random.choice(files)
        info = self._get_video_info(str(chosen))
        if info:
            info["source"] = "local"
            logger.info("Local footage: %s", chosen.name)
        return info

    # ================================================================
    # Combined: download with fallback
    # ================================================================

    def get_footage(
        self,
        search_query: str,
        game_title: Optional[str] = None,
        max_duration: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Try YouTube first, fall back to local library."""
        # Try YouTube
        result = self.download_youtube(search_query, max_duration=max_duration)
        if result:
            return result

        # Fallback to local
        logger.info("YouTube failed, trying local footage...")
        return self.get_local_footage(game_title)

    # ================================================================
    # Store footage record in DB
    # ================================================================

    def store_footage(self, info: Dict[str, Any]) -> Optional[str]:
        """Store footage metadata in the video_footage table."""
        rows = execute_query(
            """
            INSERT INTO video_footage (source, source_url, file_path, title, duration, width, height, game_title, clip_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                info.get("source", "youtube"),
                info.get("source_url", ""),
                info["file_path"],
                info.get("title", ""),
                info.get("duration", 0),
                info.get("width"),
                info.get("height"),
                info.get("game_title"),
                info.get("clip_type", "gameplay"),
            ),
        )
        return str(rows[0]["id"]) if rows else None

    # ================================================================
    # Utilities
    # ================================================================

    @staticmethod
    def _get_video_info(path: str) -> Optional[Dict[str, Any]]:
        """Get basic video info via ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return {"file_path": path}

            data = json.loads(result.stdout)
            fmt = data.get("format", {})
            video_stream = next(
                (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
                {},
            )

            return {
                "file_path": path,
                "duration": float(fmt.get("duration", 0)),
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "title": Path(path).stem,
            }
        except Exception:
            return {"file_path": path}
