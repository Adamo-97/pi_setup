#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 5: Download Footage
========================
Uses ClipAgent to plan footage selection, then VideoDownloader
to download gameplay/trailer clips from YouTube or local library.

Usage:
    python -m pipeline.step5_download_footage --script-id <UUID>
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.clip_agent import ClipAgent
from database.connection import execute_query
from services.video_downloader import VideoDownloader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pipeline.download_footage")


def main(script_id: str) -> dict:
    """
    Download footage for a script.

    Args:
        script_id: UUID of the voiced script

    Returns:
        dict with footage_id, file_path, source, game_title, duration
    """
    logger.info("=== Step 5: Download Footage (%s) ===", script_id[:8])

    # Fetch script
    rows = execute_query(
        "SELECT id, script_text, content_type FROM generated_scripts WHERE id = %s",
        (script_id,),
        fetch=True,
    )
    if not rows:
        raise ValueError(f"Script not found: {script_id}")

    script_text = rows[0][1]
    content_type = rows[0][2]

    # Get voiceover duration
    vo_rows = execute_query(
        "SELECT duration FROM voiceovers WHERE script_id = %s ORDER BY created_at DESC LIMIT 1",
        (script_id,),
        fetch=True,
    )
    target_duration = vo_rows[0][0] if vo_rows else 45.0

    # Use ClipAgent to plan footage
    clip_agent = ClipAgent()
    game_titles = clip_agent.extract_game_titles(script_text)
    clip_plan = clip_agent.run(
        script_text=script_text,
        content_type=content_type,
        duration=target_duration,
        game_titles=game_titles,
    )

    # Download footage using primary search query
    downloader = VideoDownloader()
    search_queries = clip_plan.get("search_queries", [])
    primary_game = clip_plan.get("primary_game", "gaming")

    footage_result = None
    for query in search_queries[:3]:  # Try up to 3 queries
        logger.info("Trying download: %s", query)
        result = downloader.get_footage(
            search_query=query,
            game_title=primary_game,
        )
        if result and Path(result.get("file_path", "")).is_file():
            footage_result = result
            break

    if not footage_result:
        # Last resort: generic gaming footage
        logger.warning("All queries failed. Trying generic search.")
        footage_result = downloader.get_footage(
            search_query=f"{primary_game} gameplay montage",
            game_title=primary_game,
        )

    if not footage_result or not Path(footage_result.get("file_path", "")).is_file():
        raise RuntimeError("Failed to download any usable footage")

    # Store footage info in database
    footage_id = downloader.store_footage(
        source=footage_result.get("source", "youtube"),
        source_url=footage_result.get("source_url", ""),
        file_path=footage_result["file_path"],
        game_title=primary_game,
        clip_type=clip_plan.get("clips", [{}])[0].get("clip_type", "gameplay"),
    )

    output = {
        "footage_id": footage_id,
        "script_id": script_id,
        "file_path": footage_result["file_path"],
        "source": footage_result.get("source", "youtube"),
        "game_title": primary_game,
        "clip_plan": clip_plan,
        "duration": footage_result.get("duration", 0),
    }

    logger.info(
        "Footage ready: %s (%s, %s) → %s",
        footage_id[:8],
        footage_result.get("source", "?"),
        primary_game,
        Path(footage_result["file_path"]).name,
    )

    print(json.dumps(output, ensure_ascii=False, default=str))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download footage")
    parser.add_argument("--script-id", required=True, help="Script UUID")
    args = parser.parse_args()
    main(script_id=args.script_id)
