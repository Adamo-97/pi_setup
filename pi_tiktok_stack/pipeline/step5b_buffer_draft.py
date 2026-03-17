#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 5b: Push Buffer Draft (with optional video + schedule)
============================================================
After Gate 4 (Publish) approval, pushes content to Buffer.
Supports:
  - Text-only draft (X/Twitter)
  - Video + thumbnail (TikTok, Instagram)
  - Scheduled publishing (custom date/time from Mattermost dialog)

Usage:
    python -m pipeline.step5b_buffer_draft --script-id <UUID> \
        --caption <text> --hashtags <text> \
        [--video-url <url>] [--thumbnail-url <url>] [--schedule-at <ISO8601>]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings
from services.buffer_service import BufferService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("tiktok.buffer_draft")


def main(script_id: str, caption: str, hashtags: str,
         video_url: str = "", thumbnail_url: str = "", schedule_at: str = "") -> dict:
    logger.info("=== Step 5b: Push Buffer Draft (%s) ===", script_id[:8])

    settings = get_settings()
    buffer = BufferService(
        access_token=settings.buffer.access_token,
        profile_id=settings.buffer.profile_id,
    )

    if video_url:
        draft_result = buffer.publish_video(
            video_path=video_url,
            caption=caption,
            hashtags=hashtags,
            thumbnail_url=thumbnail_url or None,
            schedule_at=schedule_at or None,
        )
    else:
        draft_result = buffer.create_draft(caption=caption, hashtags=hashtags)

    result = {
        "script_id": script_id,
        "success": draft_result["success"],
        "buffer_update_id": draft_result.get("update_id"),
        "message": draft_result.get("message", ""),
    }

    logger.info("Buffer draft: %s", "\u2705" if draft_result["success"] else "\u274c")
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Push draft to Buffer")
    parser.add_argument("--script-id", required=True)
    parser.add_argument("--caption", required=True)
    parser.add_argument("--hashtags", required=True)
    parser.add_argument("--video-url", default="")
    parser.add_argument("--thumbnail-url", default="")
    parser.add_argument("--schedule-at", default="")
    args = parser.parse_args()
    main(
        script_id=args.script_id, caption=args.caption, hashtags=args.hashtags,
        video_url=args.video_url, thumbnail_url=args.thumbnail_url,
        schedule_at=args.schedule_at,
    )
