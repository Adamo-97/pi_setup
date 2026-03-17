#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update Gate Post — removes buttons and adds a status banner after user action.

Usage (called by n8n after approval/rejection webhook fires):
  cd /home/node/x_stack && python -m pipeline.update_gate_post \
      --post-id <mm_post_id> --gate 0 --action approve --user "adam"

This ensures:
  - Buttons are replaced with a static ✅/❌ status banner
  - Double-click is prevented (buttons are gone)
  - The user who acted is recorded
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description="Update a Mattermost gate post after action")
    parser.add_argument("--post-id", type=str, required=True, help="Mattermost post ID")
    parser.add_argument("--gate", type=int, required=True, help="Gate number (0-6)")
    parser.add_argument("--action", type=str, required=True, choices=["approve", "reject", "comment"])
    parser.add_argument("--user", type=str, default="", help="Username who performed the action")
    parser.add_argument("--comment", type=str, default="", help="Optional comment text")
    args = parser.parse_args()

    from services.mattermost_service import MattermostService

    channel_map = {
        "plan": os.environ.get("MATTERMOST_CHANNEL_PLAN_ID", ""),
        "news": os.environ.get("MATTERMOST_CHANNEL_NEWS_ID", ""),
        "script": os.environ.get("MATTERMOST_CHANNEL_SCRIPT_ID", ""),
        "voiceover": os.environ.get("MATTERMOST_CHANNEL_VOICEOVER_ID", ""),
        "footage": os.environ.get("MATTERMOST_CHANNEL_FOOTAGE_ID", ""),
        "video": os.environ.get("MATTERMOST_CHANNEL_VIDEO_ID", ""),
        "publish": os.environ.get("MATTERMOST_CHANNEL_PUBLISH_ID", ""),
    }

    mm = MattermostService(
        url=os.environ["MATTERMOST_URL"],
        bot_token=os.environ["MATTERMOST_BOT_TOKEN"],
        channel_id=os.environ.get("MATTERMOST_CHANNEL_ID", ""),
        channel_map=channel_map,
    )

    ok = mm.update_post_actions(
        post_id=args.post_id,
        action=args.action,
        gate_number=args.gate,
        user_name=args.user,
        comment=args.comment,
    )

    print(json.dumps({"status": "updated" if ok else "failed", "post_id": args.post_id, "action": args.action}))


if __name__ == "__main__":
    main()
