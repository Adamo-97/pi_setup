#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Open Publish Dialog — opens a Mattermost interactive dialog for scheduling.

Called by n8n when user clicks "موافقة ونشر" on Gate 4.
Receives trigger_id from Mattermost button click, opens a dialog
with a datetime picker for scheduling the publish time.

Usage:
    python -m pipeline.open_publish_dialog --trigger-id <ID> \
        --run-id <UUID> --post-id <ID> --platform <name>
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("pipeline.publish_dialog")


def main(trigger_id: str, run_id: str, post_id: str, platform: str):
    mm_url = os.environ["MATTERMOST_URL"].rstrip("/")
    mm_token = os.environ["MATTERMOST_BOT_TOKEN"]
    n8n_base = os.environ.get("N8N_BASE_URL", "http://192.168.0.11:5678").rstrip("/")

    dialog_payload = {
        "trigger_id": trigger_id,
        "url": f"{n8n_base}/webhook/{platform}-publish-submit",
        "dialog": {
            "callback_id": f"publish_{platform}",
            "title": "جدولة النشر",
            "introduction_text": "اختر تاريخ ووقت النشر. تأكد من إرفاق الفيديو والصورة المصغرة كرد على رسالة النشر قبل الموافقة.",
            "elements": [
                {
                    "display_name": "تاريخ ووقت النشر",
                    "name": "publish_datetime",
                    "type": "text",
                    "subtype": "text",
                    "placeholder": "2026-03-20 14:00",
                    "help_text": "صيغة: YYYY-MM-DD HH:MM (توقيت السعودية)",
                    "optional": True,
                    "default": "",
                },
                {
                    "display_name": "نشر فوري؟",
                    "name": "publish_now",
                    "type": "bool",
                    "placeholder": "نشر الآن بدون جدولة",
                    "optional": True,
                    "default": "false",
                },
            ],
            "submit_label": "نشر 🚀",
            "notify_on_cancel": False,
            "state": json.dumps({"run_id": run_id, "post_id": post_id, "platform": platform}),
        },
    }

    resp = requests.post(
        f"{mm_url}/api/v4/actions/dialogs/open",
        json=dialog_payload,
        headers={"Authorization": f"Bearer {mm_token}", "Content-Type": "application/json"},
        timeout=10,
    )

    result = {"success": resp.status_code == 200, "status_code": resp.status_code}
    if resp.status_code != 200:
        result["error"] = resp.text[:500]
        logger.error("Failed to open dialog: %d %s", resp.status_code, resp.text[:200])
    else:
        logger.info("Publish dialog opened for run %s", run_id[:12])

    print(json.dumps(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Open publish scheduling dialog")
    parser.add_argument("--trigger-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--post-id", required=True)
    parser.add_argument("--platform", required=True)
    args = parser.parse_args()
    main(trigger_id=args.trigger_id, run_id=args.run_id, post_id=args.post_id, platform=args.platform)
