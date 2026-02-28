# -*- coding: utf-8 -*-
"""
Slack Service
=============
Sends Instagram Reel previews and scripts to Slack for approval.
Rich Block Kit messages with approve/reject action buttons.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("instagram.slack")


class SlackService:
    """Slack notifications with Block Kit for Instagram Reels pipeline."""

    def __init__(self, webhook_url: str, n8n_base_url: str = "http://localhost:5680"):
        self.webhook_url = webhook_url
        self.n8n_base_url = n8n_base_url.rstrip("/")

    # ================================================================
    # Send approval request
    # ================================================================

    def send_approval_request(
        self,
        script_id: str,
        video_id: str,
        script_text: str,
        content_type: str,
        validation_score: float,
        video_path: str,
        duration: float,
        news_titles: Optional[List[str]] = None,
    ) -> bool:
        """
        Send a rich Slack message for Reel approval.

        Includes:
          - Script preview (first 500 chars)
          - Validation score
          - Video metadata
          - News sources used
          - Approve / Reject action buttons (→ n8n webhooks)
        """
        approve_url = f"{self.n8n_base_url}/webhook/instagram-approve"
        reject_url = f"{self.n8n_base_url}/webhook/instagram-reject"

        # Truncate script for preview
        script_preview = script_text[:500]
        if len(script_text) > 500:
            script_preview += "..."

        # Score emoji
        score_emoji = (
            "🟢" if validation_score >= 80 else "🟡" if validation_score >= 70 else "🔴"
        )

        blocks: List[Dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📸 Instagram Reel Ready — {content_type.replace('_', ' ').title()}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Score:* {score_emoji} {validation_score:.0f}/100",
                    },
                    {"type": "mrkdwn", "text": f"*Duration:* {duration:.1f}s"},
                    {"type": "mrkdwn", "text": f"*Type:* {content_type}"},
                    {"type": "mrkdwn", "text": f"*Video ID:* `{video_id[:8]}...`"},
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*📝 Script Preview:*\n```{script_preview}```",
                },
            },
        ]

        # Add news sources if available
        if news_titles:
            sources_text = "\n".join(f"• {t}" for t in news_titles[:5])
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*📰 News Sources:*\n{sources_text}",
                    },
                }
            )

        # Action buttons
        blocks.extend(
            [
                {"type": "divider"},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Approve & Publish",
                            },
                            "style": "primary",
                            "url": f"{approve_url}?video_id={video_id}&script_id={script_id}",
                            "action_id": "approve_instagram",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "❌ Reject"},
                            "style": "danger",
                            "url": f"{reject_url}?video_id={video_id}&script_id={script_id}",
                            "action_id": "reject_instagram",
                        },
                    ],
                },
            ]
        )

        payload = {"blocks": blocks}
        return self._send(payload)

    # ================================================================
    # Status notifications
    # ================================================================

    def send_status(self, message: str, level: str = "info") -> bool:
        """Send a simple status message."""
        emoji = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}.get(
            level, "ℹ️"
        )
        payload = {"text": f"{emoji} *Instagram Reels Pipeline:* {message}"}
        return self._send(payload)

    def send_publish_confirmation(
        self,
        video_id: str,
        buffer_update_id: str,
        title: str,
    ) -> bool:
        """Send confirmation that Reel was published to Instagram via Buffer."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚀 Published to Instagram!"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Title:* {title}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Buffer ID:* `{buffer_update_id[:12]}...`",
                    },
                    {"type": "mrkdwn", "text": f"*Video:* `{video_id[:8]}...`"},
                ],
            },
        ]
        return self._send({"blocks": blocks})

    def send_error(self, step: str, error: str) -> bool:
        """Send pipeline error alert."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🔴 Instagram Pipeline Error"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Step:* {step}"},
                    {"type": "mrkdwn", "text": f"*Error:*\n```{error[:500]}```"},
                ],
            },
        ]
        return self._send({"blocks": blocks})

    # ================================================================
    # Internal
    # ================================================================

    def _send(self, payload: Dict[str, Any]) -> bool:
        """Send payload to Slack webhook."""
        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=15,
            )
            if resp.status_code == 200:
                logger.info("Slack message sent")
                return True
            else:
                logger.error("Slack send failed: %d %s", resp.status_code, resp.text)
                return False
        except Exception as e:
            logger.error("Slack send error: %s", e)
            return False
