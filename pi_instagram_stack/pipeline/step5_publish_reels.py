#!/usr/bin/env python3
"""
Step 5: Generate Publish Package (Instagram)
==========================================
Generates SEO-optimised caption + hashtags via Gemini, then outputs
JSON for the n8n workflow to post to the #tiktok-publish channel.
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_settings
from database.connection import execute_query
from processors.seo import SEO
from services.buffer_service import BufferService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("instagram.publish")


def main(script_id: str) -> dict:
    logger.info("=== Step 5: Generate Publish Package (%s) ===", script_id[:8])

    rows = execute_query(
        """SELECT gs.id, gs.script_text, gs.content_type, vo.duration
           FROM generated_scripts gs
           LEFT JOIN voiceovers vo ON vo.script_id = gs.id
           WHERE gs.id = %s ORDER BY vo.created_at DESC LIMIT 1""",
        (script_id,), fetch=True,
    )
    if not rows:
        raise ValueError(f"Script not found: {script_id}")

    row = rows[0]
    script_text = row["script_text"]
    content_type = row["content_type"]
    duration = row["duration"] or 45

    try:
        seo = SEO()
        seo_result = seo.run(
            script_text=script_text, content_type=content_type,
            topics=content_type.replace("_", " "),
            duration_seconds=int(duration), script_id=script_id,
        )
        caption = seo_result["full_caption"]
        hashtags = seo_result["hashtags_first_comment"]
        caption_en = seo_result.get("caption_en", "")
        best_post_time = seo_result.get("best_post_time", "")
        logger.info("SEO agent produced caption (%d chars)", len(caption))
    except Exception as exc:
        logger.warning("SEO agent failed (%s) — falling back", exc)
        clean_text = re.sub(r"\[.*?\]", "", script_text)
        caption = clean_text[:150].strip() + ("..." if len(clean_text) > 150 else "")
        hashtags = BufferService.get_default_hashtags(content_type)
        caption_en = ""
        best_post_time = ""
        seo_result = {}

    result = {
        "script_id": script_id,
        "success": True,
        "caption": caption,
        "caption_en": caption_en,
        "hashtags": hashtags,
        "best_post_time": best_post_time,
        "seo_id": seo_result.get("seo_id"),
    }

    logger.info("Publish package ready — caption %d chars", len(caption))
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate publish package (SEO)")
    parser.add_argument("--script-id", required=True, help="Script UUID")
    args = parser.parse_args()
    main(script_id=args.script_id)
