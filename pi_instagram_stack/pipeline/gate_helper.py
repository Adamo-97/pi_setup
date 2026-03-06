#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gate helper — sends Mattermost gate approval messages.

Usage (called by n8n Execute Command nodes):
  cd /home/node/instagram_stack && python -m pipeline.gate_helper \
      --gate 0 --title "خطة Reel جديدة" --data-file /tmp/gate_0.json

The --data-file contains the gate's context data as JSON (topic, type, etc.)
This avoids shell escaping issues when Arabic or special chars are in the data.
"""

import argparse
import json
import os
import sys

GATE_TITLES = {
    0: "خطة Reel جديدة",
    1: "الأخبار جاهزة",
    2: "السكريبت جاهز",
    3: "الصوت جاهز",
    4: "الفيديو جاهز",
    5: "جاهز للنشر — أرفق الصورة المصغرة",
}


def main():
    parser = argparse.ArgumentParser(description="Send gate approval to Mattermost")
    parser.add_argument("--gate", type=int, required=True, help="Gate number (0-5)")
    parser.add_argument("--data-file", type=str, required=True, help="Path to JSON file with gate data")
    parser.add_argument("--run-id", type=str, required=True, help="Pipeline run ID")
    args = parser.parse_args()

    title = GATE_TITLES.get(args.gate, f"Gate {args.gate}")

    # Load data from file
    with open(args.data_file, "r", encoding="utf-8") as f:
        gate_data = json.load(f)

    # Send to Mattermost
    from services.mattermost_service import MattermostService

    mm = MattermostService(
        os.environ["MATTERMOST_URL"],
        os.environ["MATTERMOST_BOT_TOKEN"],
        os.environ["MATTERMOST_CHANNEL_ID"],
    )
    mm.send_gate_approval(
        gate_number=args.gate,
        summary=title,
        details=gate_data,
        run_id=args.run_id,
    )
    print(json.dumps({"status": "sent", "gate": args.gate}))


if __name__ == "__main__":
    main()
