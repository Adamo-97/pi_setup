#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 5b: Push Buffer Draft
===========================
After Gate 4 (Publish) approval, reads the caption and hashtags
from pipeline state and pushes a text-only draft to Buffer.

Usage:
    python -m pipeline.step5b_buffer_draft --script-id <UUID> --caption <text> --hashtags <text>
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings
from services.buffer_service import BufferService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("tiktok.buffer_draft")


def main(script_id: str, caption: str, hashtags: str) -> dict:
    logger.info("=== Step 5b: Push Buffer Draft (%s) ===", script_id[:8])

    settings = get_settings()
    buffer = BufferService(
        access_token=settings.buffer.access_token,
        profile_id=settings.buffer.profile_id,
    )
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
    parser.add_argument("--script-id", required=True, help="Script UUID")
    parser.add_argument("--caption", required=True, help="SEO caption")
    parser.add_argument("--hashtags", required=True, help="Hashtags for first comment")
    args = parser.parse_args()
    main(script_id=args.script_id, caption=args.caption, hashtags=args.hashtags)
