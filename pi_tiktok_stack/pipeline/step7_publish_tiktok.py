#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 7: Publish to TikTok
=========================
Sends video to Mattermost for approval, then publishes to TikTok via Buffer.
Can run in two modes:
  - 'notify': Send Mattermost approval request (default from pipeline)
  - 'publish': Actually publish to Buffer (called by n8n after approval)

Usage:
    python -m pipeline.step7_publish_tiktok --video-id <UUID> [--mode notify|publish]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings
from database.connection import execute_query
from services.buffer_service import BufferService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pipeline.publish")


def main(video_id: str, mode: str = "notify") -> dict:
    """
    Publish TikTok video or send for approval.

    Args:
        video_id: UUID of the rendered video
        mode: 'notify' (Mattermost approval) or 'publish' (Buffer upload)

    Returns:
        dict with status and details
    """
    logger.info("=== Step 7: Publish (%s, mode=%s) ===", video_id[:8], mode)

    settings = get_settings()

    # Fetch video info
    rows = execute_query(
        """
        SELECT rv.id, rv.script_id, rv.file_path, rv.duration, rv.status,
               gs.script_text, gs.content_type
        FROM rendered_videos rv
        JOIN generated_scripts gs ON rv.script_id = gs.id
        WHERE rv.id = %s
        """,
        (video_id,),
        fetch=True,
    )
    if not rows:
        raise ValueError(f"Video not found: {video_id}")

    row = rows[0]
    script_id = row[1]
    video_path = row[2]
    duration = row[3]
    video_status = row[4]
    script_text = row[5]
    content_type = row[6]

    if not Path(video_path).is_file():
        raise FileNotFoundError(f"Video file missing: {video_path}")

    if mode == "notify":
        # Gate 5 approval is now handled by n8n workflow (6-Gate HITL).
        # In notify mode, just output video info for n8n to parse.
        result = {
            "video_id": video_id,
            "mode": "notify",
            "video_path": video_path,
            "duration": duration,
            "content_type": content_type,
            "ready_for_approval": True,
        }
        print(json.dumps(result, ensure_ascii=False))
        return result
    elif mode == "publish":
        return _publish_to_buffer(
            video_id=video_id,
            video_path=video_path,
            script_text=script_text,
            content_type=content_type,
            settings=settings,
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")


def _publish_to_buffer(
    video_id: str,
    video_path: str,
    script_text: str,
    content_type: str,
    settings,
) -> dict:
    """Publish video to TikTok via Buffer."""
    buffer = BufferService(
        access_token=settings.buffer.access_token,
        profile_id=settings.buffer.profile_id,
    )

    # Build caption (first 150 chars of script + hashtags)
    import re

    clean_text = re.sub(r"\[.*?\]", "", script_text)
    caption = clean_text[:150].strip()
    if len(clean_text) > 150:
        caption += "..."

    hashtags = BufferService.get_default_hashtags(content_type)

    pub_result = buffer.publish_video(
        video_path=video_path,
        caption=caption,
        hashtags=hashtags,
    )

    # Update database
    if pub_result["success"]:
        execute_query(
            """
            UPDATE rendered_videos
            SET status = 'published',
                buffer_update_id = %s,
                published_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (pub_result.get("update_id", ""), video_id),
        )
    else:
        execute_query(
            "UPDATE rendered_videos SET status = 'publish_failed', updated_at = NOW() WHERE id = %s",
            (video_id,),
        )

    result = {
        "video_id": video_id,
        "mode": "publish",
        "success": pub_result["success"],
        "buffer_update_id": pub_result.get("update_id"),
        "message": pub_result.get("message", ""),
    }

    logger.info("Buffer publish: %s", "✅" if pub_result["success"] else "❌")
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish TikTok video")
    parser.add_argument("--video-id", required=True, help="Video UUID")
    parser.add_argument(
        "--mode",
        choices=["notify", "publish"],
        default="notify",
        help="notify=Mattermost approval, publish=Buffer upload",
    )
    args = parser.parse_args()
    main(video_id=args.video_id, mode=args.mode)
