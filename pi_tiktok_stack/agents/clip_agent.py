# -*- coding: utf-8 -*-
"""
Clip Agent
==========
AI-driven clip/footage selection agent.
Analyzes scripts to determine optimal search queries and clip types
for downloading relevant gameplay/trailer footage.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from services.gemini_service import GeminiService

logger = logging.getLogger("tiktok.clip_agent")

CLIP_SYSTEM_PROMPT = """أنت خبير في اختيار مقاطع الفيديو لمنصة TikTok Gaming.
مهمتك: تحليل النص واقتراح أفضل مقاطع فيديو لمرافقة التعليق الصوتي.

Rules:
- Suggest 2-4 clip segments per script
- Each clip = search query + type + approximate timestamp
- Clip types: gameplay, trailer, cinematic, montage
- Think about visual pacing — cuts every 3-5 seconds
- Match clips to the script's energy beats and stage directions

Output ONLY valid JSON."""

CLIP_SELECTION_PROMPT = """Analyze this TikTok script and recommend video clips:

SCRIPT:
{script_text}

CONTENT TYPE: {content_type}
DURATION: {duration}s

Games/topics mentioned: {game_titles}

Respond with JSON:
{{
    "clips": [
        {{
            "search_query": "specific YouTube search query for this clip",
            "game_title": "game name or topic",
            "clip_type": "gameplay|trailer|cinematic|montage",
            "start_seconds": 0,
            "duration_seconds": 10,
            "description": "what this clip should show",
            "energy": "high|medium|low"
        }}
    ],
    "pacing_notes": "brief notes on visual pacing strategy",
    "primary_game": "main game featured"
}}"""


class ClipAgent(BaseAgent):
    """AI clip selection and footage planning."""

    def __init__(self):
        super().__init__(name="TikTok Clip Selector")

    def run(
        self,
        script_text: str,
        content_type: str = "trending_news",
        duration: float = 45.0,
        game_titles: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Analyze script and recommend video clips.

        Args:
            script_text: The approved script text
            content_type: Content type for context
            duration: Target video duration
            game_titles: Known game titles in the script

        Returns:
            dict with clips list, pacing_notes, primary_game, search_queries
        """
        logger.info("Analyzing script for clip selection (%.0fs)", duration)

        titles_str = (
            ", ".join(game_titles) if game_titles else "Unknown / general gaming"
        )

        prompt = CLIP_SELECTION_PROMPT.format(
            script_text=script_text[:1500],
            content_type=content_type,
            duration=int(duration),
            game_titles=titles_str,
        )

        try:
            raw = self.gemini.generate_json(
                prompt=prompt,
                system_instruction=CLIP_SYSTEM_PROMPT,
            )
            result = json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Clip selection JSON failed: %s. Using fallback.", e)
            result = self._fallback_clips(
                script_text, content_type, duration, game_titles
            )

        # Extract search queries for video downloader
        clips = result.get("clips", [])
        search_queries = [c["search_query"] for c in clips if "search_query" in c]

        # Validate and clean
        for clip in clips:
            clip.setdefault("clip_type", "gameplay")
            clip.setdefault("duration_seconds", 10)
            clip.setdefault("energy", "medium")

        result["search_queries"] = search_queries
        result["clip_count"] = len(clips)

        logger.info(
            "Clip plan: %d clips, primary game: %s",
            len(clips),
            result.get("primary_game", "unknown"),
        )
        return result

    # ================================================================
    # Extract game titles from script
    # ================================================================

    def extract_game_titles(self, script_text: str) -> List[str]:
        """Use Gemini to extract game titles mentioned in the script."""
        prompt = (
            "Extract ALL video game titles mentioned in this Arabic gaming script. "
            'Return ONLY a JSON array of strings. Example: ["GTA VI", "Elden Ring"]\n\n'
            f"SCRIPT:\n{script_text[:1000]}"
        )

        try:
            raw = self.gemini.generate_json(prompt=prompt)
            titles = json.loads(raw)
            if isinstance(titles, list):
                return [str(t) for t in titles if t]
        except Exception as e:
            logger.warning("Game title extraction failed: %s", e)

        return []

    # ================================================================
    # Fallback
    # ================================================================

    @staticmethod
    def _fallback_clips(
        script_text: str,
        content_type: str,
        duration: float,
        game_titles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate basic clip plan without AI."""
        primary_game = game_titles[0] if game_titles else "gaming"

        # Default: 3 segments covering the duration
        segment_dur = duration / 3
        clips = [
            {
                "search_query": f"{primary_game} gameplay trailer 2024",
                "game_title": primary_game,
                "clip_type": "trailer",
                "start_seconds": 0,
                "duration_seconds": int(segment_dur),
                "description": "Opening hook — exciting trailer moment",
                "energy": "high",
            },
            {
                "search_query": f"{primary_game} gameplay footage",
                "game_title": primary_game,
                "clip_type": "gameplay",
                "start_seconds": int(segment_dur),
                "duration_seconds": int(segment_dur),
                "description": "Main content — gameplay showcase",
                "energy": "medium",
            },
            {
                "search_query": f"{primary_game} cinematic best moments",
                "game_title": primary_game,
                "clip_type": "cinematic",
                "start_seconds": int(segment_dur * 2),
                "duration_seconds": int(segment_dur),
                "description": "Closing — cinematic or highlight reel",
                "energy": "high",
            },
        ]

        return {
            "clips": clips,
            "pacing_notes": "Default 3-segment pacing: hook → content → close",
            "primary_game": primary_game,
        }
