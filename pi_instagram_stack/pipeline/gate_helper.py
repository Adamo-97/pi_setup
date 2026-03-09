#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gate helper — sends Mattermost gate approval messages to the correct channel.

Usage (called by n8n Execute Command nodes):
  cd /home/node/instagram_stack && python -m pipeline.gate_helper \
      --gate 0 --title "خطة Reel جديدة" --data-file /tmp/gate_0.json

The --data-file contains the gate's context data as JSON (topic, type, etc.)
This avoids shell escaping issues when Arabic or special chars are in the data.

Each gate routes to a dedicated Mattermost channel via channel_map.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GATE_TITLES = {
    0: "خطة Reel جديدة",
    1: "الأخبار جاهزة",
    2: "السكريبت جاهز",
    3: "الصوت جاهز — استمع للتعليق الصوتي",
}


def main():
    parser = argparse.ArgumentParser(description="Send gate approval to Mattermost")
    parser.add_argument("--gate", type=int, required=True, help="Gate number (0-5)")
    parser.add_argument("--data-file", type=str, required=True, help="Path to JSON file with gate data")
    parser.add_argument("--run-id", type=str, required=True, help="Pipeline run ID")
    parser.add_argument("--file-paths", type=str, nargs="*", default=[], help="File paths to attach (audio, video, etc.)")
    args = parser.parse_args()

    title = GATE_TITLES.get(args.gate, f"Gate {args.gate}")

    with open(args.data_file, "r", encoding="utf-8") as f:
        gate_data = json.load(f)

    # Build channel map from environment variables
    channel_map = {
        "plan": os.environ.get("MATTERMOST_CHANNEL_PLAN_ID", ""),
        "news": os.environ.get("MATTERMOST_CHANNEL_NEWS_ID", ""),
        "script": os.environ.get("MATTERMOST_CHANNEL_SCRIPT_ID", ""),
        "voiceover": os.environ.get("MATTERMOST_CHANNEL_VOICEOVER_ID", ""),
        "footage": os.environ.get("MATTERMOST_CHANNEL_FOOTAGE_ID", ""),
        "video": os.environ.get("MATTERMOST_CHANNEL_VIDEO_ID", ""),
        "publish": os.environ.get("MATTERMOST_CHANNEL_PUBLISH_ID", ""),
    }

    from services.mattermost_service import MattermostService
    mm = MattermostService(
        url=os.environ["MATTERMOST_URL"],
        bot_token=os.environ["MATTERMOST_BOT_TOKEN"],
        channel_id=os.environ.get("MATTERMOST_CHANNEL_ID", ""),
        channel_map=channel_map,
    )

    # Extract file_paths from gate_data if present (for voiceover, video, etc.)
    file_paths = args.file_paths or []
    if "file_path" in gate_data and gate_data["file_path"]:
        fp = gate_data["file_path"]
        if Path(fp).is_file() and fp not in file_paths:
            file_paths.append(fp)
    if "output_path" in gate_data and gate_data["output_path"]:
        fp = gate_data["output_path"]
        if Path(fp).is_file() and fp not in file_paths:
            file_paths.append(fp)

    # Remove file_path/output_path from details table (already attached)
    display_data = {k: v for k, v in gate_data.items()
                    if k not in ("file_path", "output_path", "word_timestamps")}

    post_id = mm.send_gate_approval(
        gate_number=args.gate,
        summary=title,
        details=display_data,
        run_id=args.run_id,
        file_paths=file_paths,
    )
    channel = channel_map.get(mm.GATE_CHANNEL_KEYS.get(args.gate, "plan"), "")
    result = {"status": "sent" if post_id else "failed", "gate": args.gate, "channel": channel}
    if post_id:
        result["post_id"] = post_id
    print(json.dumps(result))


if __name__ == "__main__":
    main()
