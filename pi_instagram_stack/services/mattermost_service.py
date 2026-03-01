# -*- coding: utf-8 -*-
"""
Mattermost Service
====================
Sends Instagram Reel previews and scripts to Mattermost for approval.
Rich Markdown messages with interactive approve/reject action buttons
routed to n8n webhooks.

Mattermost API Reference:
  - POST /api/v4/posts   — Create post (up to 16,383 chars)
  - POST /api/v4/files   — Upload files (up to 100 MB)
  - Authorization: Bearer TOKEN
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("instagram.mattermost")


class MattermostService:
    """Mattermost REST API client for Instagram Reels pipeline notifications."""

    def __init__(
        self,
        url: str,
        bot_token: str,
        channel_id: str,
        n8n_base_url: str = "http://localhost:5680",
    ):
        self.base_url = url.rstrip("/")
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.n8n_base_url = n8n_base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

    # ================================================================
    # Core API helpers
    # ================================================================

    def _post_message(
        self,
        message: str,
        props: Optional[dict] = None,
        file_ids: Optional[list] = None,
    ) -> bool:
        """Create a post in the configured Mattermost channel."""
        payload: Dict[str, Any] = {
            "channel_id": self.channel_id,
            "message": message,
        }
        if props:
            payload["props"] = props
        if file_ids:
            payload["file_ids"] = file_ids

        try:
            resp = requests.post(
                f"{self.base_url}/api/v4/posts",
                json=payload,
                headers=self._headers,
                timeout=30,
            )
            if resp.status_code in (200, 201):
                logger.info("Mattermost message sent")
                return True
            else:
                logger.error(
                    "Mattermost send failed: %d %s", resp.status_code, resp.text[:200]
                )
                return False
        except Exception as e:
            logger.error("Mattermost send error: %s", e)
            return False

    def _upload_file(self, file_path: str) -> Optional[str]:
        """Upload a file and return its Mattermost file ID."""
        path = Path(file_path)
        if not path.is_file():
            logger.error("File not found for upload: %s", file_path)
            return None

        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{self.base_url}/api/v4/files",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    files={"files": (path.name, f)},
                    data={"channel_id": self.channel_id},
                    timeout=120,
                )
            if resp.status_code in (200, 201):
                file_id = resp.json()["file_infos"][0]["id"]
                logger.info("File uploaded: %s → %s", path.name, file_id)
                return file_id
            else:
                logger.error(
                    "File upload failed: %d %s", resp.status_code, resp.text[:200]
                )
                return None
        except Exception as e:
            logger.error("File upload error: %s", e)
            return None

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
        Send a rich Mattermost message for Reel approval.

        Full script text is included — no truncation needed
        (Mattermost supports 16,383 chars vs Slack's 3,000).

        Includes:
          - Full script text
          - Validation score
          - Video metadata
          - News sources used
          - Video file attached directly
          - Approve / Reject action buttons (→ n8n webhooks)
        """
        approve_url = f"{self.n8n_base_url}/webhook/instagram-approve"
        reject_url = f"{self.n8n_base_url}/webhook/instagram-reject"

        # Score emoji
        score_emoji = (
            ":large_green_circle:"
            if validation_score >= 80
            else ":large_yellow_circle:" if validation_score >= 70 else ":red_circle:"
        )

        # Build message — full script, no truncation
        message = (
            f"### :camera: Instagram Reel Ready — {content_type.replace('_', ' ').title()}\n\n"
            f"| Field | Value |\n"
            f"|:------|:------|\n"
            f"| **Score** | {score_emoji} {validation_score:.0f}/100 |\n"
            f"| **Duration** | {duration:.1f}s |\n"
            f"| **Type** | {content_type} |\n"
            f"| **Video ID** | `{video_id[:8]}...` |\n\n"
            f"---\n\n"
            f"**:memo: Script:**\n```\n{script_text}\n```\n"
        )

        # Add news sources if available
        if news_titles:
            sources_text = "\n".join(f"- {t}" for t in news_titles[:5])
            message += f"\n**:newspaper: News Sources:**\n{sources_text}\n"

        # Upload video file if it exists
        file_ids = []
        if video_path and Path(video_path).is_file():
            file_id = self._upload_file(video_path)
            if file_id:
                file_ids.append(file_id)

        props = {
            "attachments": [
                {
                    "color": (
                        "#36a64f"
                        if validation_score >= 80
                        else "#daa038" if validation_score >= 70 else "#d00000"
                    ),
                    "actions": [
                        {
                            "id": "approve_instagram",
                            "name": "✅ Approve & Publish",
                            "integration": {
                                "url": approve_url,
                                "context": {
                                    "action": "approve",
                                    "video_id": video_id,
                                    "script_id": script_id,
                                },
                            },
                        },
                        {
                            "id": "reject_instagram",
                            "name": "❌ Reject",
                            "style": "danger",
                            "integration": {
                                "url": reject_url,
                                "context": {
                                    "action": "reject",
                                    "video_id": video_id,
                                    "script_id": script_id,
                                },
                            },
                        },
                    ],
                }
            ]
        }

        return self._post_message(message, props=props, file_ids=file_ids)

    # ================================================================
    # Status notifications
    # ================================================================

    def send_status(self, message: str, level: str = "info") -> bool:
        """Send a simple status message."""
        emoji = {
            "info": ":information_source:",
            "success": ":white_check_mark:",
            "warning": ":warning:",
            "error": ":x:",
        }.get(level, ":information_source:")
        return self._post_message(f"{emoji} **Instagram Reels Pipeline:** {message}")

    def send_publish_confirmation(
        self,
        video_id: str,
        buffer_update_id: str,
        title: str,
    ) -> bool:
        """Send confirmation that Reel was published to Instagram via Buffer."""
        message = (
            f"### :rocket: Published to Instagram!\n\n"
            f"| Field | Value |\n"
            f"|:------|:------|\n"
            f"| **Title** | {title} |\n"
            f"| **Buffer ID** | `{buffer_update_id[:12]}...` |\n"
            f"| **Video** | `{video_id[:8]}...` |\n"
        )
        return self._post_message(message)

    def send_error(self, step: str, error: str) -> bool:
        """Send pipeline error alert."""
        message = (
            f"### :red_circle: Instagram Pipeline Error\n\n"
            f"**Step:** {step}\n\n"
            f"**Error:**\n```\n{error}\n```"
        )
        return self._post_message(message)
