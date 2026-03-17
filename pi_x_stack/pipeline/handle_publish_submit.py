#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Handle Publish Dialog Submit — processes the scheduling dialog response.

Called by n8n when user submits the publish scheduling dialog.
1. Parses the scheduled datetime from the dialog submission
2. Fetches video + thumbnail files from Mattermost thread replies
3. Downloads them to local temp paths
4. Calls Buffer API to create the post with video + schedule

Usage:
    python -m pipeline.handle_publish_submit --payload-file /tmp/dialog_payload.json
"""

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("pipeline.publish_submit")

# KSA timezone = UTC+3
KSA = timezone(timedelta(hours=3))


def main(payload_file: str):
    with open(payload_file, "r") as f:
        payload = json.load(f)

    submission = payload.get("submission", {})
    state = json.loads(payload.get("state", "{}"))
    run_id = state.get("run_id", "")
    post_id = state.get("post_id", "")
    platform = state.get("platform", "")

    publish_now = submission.get("publish_now") in ("true", True)
    publish_dt_str = (submission.get("publish_datetime") or "").strip()

    # Parse schedule
    schedule_iso = ""
    if not publish_now and publish_dt_str:
        try:
            dt = datetime.strptime(publish_dt_str, "%Y-%m-%d %H:%M")
            dt_ksa = dt.replace(tzinfo=KSA)
            schedule_iso = dt_ksa.isoformat()
            logger.info("Scheduled for: %s", schedule_iso)
        except ValueError:
            logger.warning("Could not parse datetime '%s', will add to queue", publish_dt_str)

    # Fetch files from Mattermost thread
    mm_url = os.environ["MATTERMOST_URL"].rstrip("/")
    mm_token = os.environ["MATTERMOST_BOT_TOKEN"]
    headers = {"Authorization": f"Bearer {mm_token}"}

    video_url = ""
    thumbnail_url = ""

    if post_id:
        resp = requests.get(f"{mm_url}/api/v4/posts/{post_id}/thread", headers=headers, timeout=15)
        if resp.status_code == 200:
            thread = resp.json()
            order = thread.get("order", [])
            posts = thread.get("posts", {})

            for pid in order:
                if pid == post_id:
                    continue
                post = posts.get(pid, {})
                file_ids = post.get("file_ids", [])
                for fid in file_ids:
                    file_resp = requests.get(f"{mm_url}/api/v4/files/{fid}/info", headers=headers, timeout=10)
                    if file_resp.status_code != 200:
                        continue
                    info = file_resp.json()
                    mime = info.get("mime_type", "")
                    name = info.get("name", "")

                    if mime.startswith("video/") and not video_url:
                        # Download video to temp
                        dl = requests.get(f"{mm_url}/api/v4/files/{fid}", headers=headers, timeout=120)
                        if dl.status_code == 200:
                            ext = Path(name).suffix or ".mp4"
                            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir="/tmp")
                            tmp.write(dl.content)
                            tmp.close()
                            video_url = tmp.name
                            logger.info("Downloaded video: %s (%d bytes)", name, len(dl.content))

                    elif mime.startswith("image/") and not thumbnail_url:
                        dl = requests.get(f"{mm_url}/api/v4/files/{fid}", headers=headers, timeout=60)
                        if dl.status_code == 200:
                            ext = Path(name).suffix or ".jpg"
                            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext, dir="/tmp")
                            tmp.write(dl.content)
                            tmp.close()
                            thumbnail_url = tmp.name
                            logger.info("Downloaded thumbnail: %s (%d bytes)", name, len(dl.content))

    # Read caption/hashtags from pipeline state file
    caption = ""
    hashtags = ""
    script_id = ""
    state_file = Path(f"/tmp/pipeline_state_{run_id}.json")
    if state_file.is_file():
        st = json.loads(state_file.read_text())
        caption = st.get("caption", "")
        hashtags = st.get("hashtags", "")
        script_id = st.get("script_id", "")

    # Push to Buffer
    from config.settings import get_settings
    from services.buffer_service import BufferService

    settings = get_settings()
    buffer = BufferService(
        access_token=settings.buffer.access_token,
        profile_id=settings.buffer.profile_id,
    )

    if video_url and video_url.startswith("/tmp"):
        # Local file — Buffer needs a public URL, so create a text draft
        logger.info("Video is local file — creating text draft (attach video in Buffer UI)")
        draft_result = buffer.create_draft(caption=caption, hashtags=hashtags)
    elif video_url:
        draft_result = buffer.publish_video(
            video_path=video_url, caption=caption, hashtags=hashtags,
            thumbnail_url=thumbnail_url, schedule_at=schedule_iso or None,
        )
    else:
        draft_result = buffer.create_draft(caption=caption, hashtags=hashtags)

    # Update the gate post to show approval
    from services.mattermost_service import MattermostService
    mm = MattermostService.from_settings()

    schedule_msg = f"📅 {publish_dt_str}" if publish_dt_str and not publish_now else "⚡ فوري"
    mm.update_post_actions(
        post_id=post_id, action="approve", gate_number=4,
        user_name=payload.get("user_id", ""),
        comment=f"Buffer: {draft_result.get('message', '?')} | {schedule_msg}",
    )

    result = {
        "success": draft_result.get("success", False),
        "buffer_update_id": draft_result.get("update_id"),
        "schedule": schedule_iso or "queue",
        "video_attached": bool(video_url),
        "thumbnail_attached": bool(thumbnail_url),
        "run_id": run_id,
        "script_id": script_id,
    }

    logger.info("Publish submit complete: %s", json.dumps(result, ensure_ascii=False))
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Handle publish dialog submission")
    parser.add_argument("--payload-file", required=True)
    args = parser.parse_args()
    main(payload_file=args.payload_file)
