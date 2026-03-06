# -*- coding: utf-8 -*-
"""
Mattermost Service
====================
Sends Instagram Reel previews and scripts to Mattermost for approval.
Rich Markdown messages with interactive approve/reject/comment action buttons
routed to n8n webhooks. Each gate posts to its own dedicated channel.

Mattermost API Reference:
  - POST /api/v4/posts   — Create post (up to 16,383 chars)
  - POST /api/v4/files   — Upload files (up to 100 MB)
  - Authorization: Bearer TOKEN
"""

import logging
import os
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
        n8n_base_url: str = "",
        channel_map: Optional[Dict[str, str]] = None,
    ):
        self.base_url = url.rstrip("/")
        self.bot_token = bot_token
        self.channel_id = channel_id  # legacy fallback
        # Per-gate channel routing (gate_name -> channel_id)
        self.channel_map: Dict[str, str] = channel_map or {}
        # Allow override via N8N_BASE_URL env var; fallback to Pi's shared n8n
        resolved = n8n_base_url or os.environ.get("N8N_BASE_URL", "http://192.168.0.11:5678")
        self.n8n_base_url = resolved.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

    # ================================================================
    # Channel routing
    # ================================================================

    GATE_CHANNEL_KEYS = {
        0: "plan",
        1: "news",
        2: "script",
        3: "voiceover",
        4: "footage",
        5: "video",
        6: "publish",
    }

    def _resolve_channel(self, gate_number: Optional[int] = None, channel_key: Optional[str] = None) -> str:
        """Resolve the correct channel ID for a gate number or channel key."""
        if channel_key and channel_key in self.channel_map:
            resolved = self.channel_map[channel_key]
            if resolved:
                return resolved
        if gate_number is not None:
            key = self.GATE_CHANNEL_KEYS.get(gate_number, "plan")
            if key in self.channel_map and self.channel_map[key]:
                return self.channel_map[key]
        return self.channel_id

    @classmethod
    def from_settings(cls) -> "MattermostService":
        """Factory: create from config/settings.py environment."""
        from config.settings import get_settings
        s = get_settings()
        mm = s.mattermost
        channel_map = {
            "plan": mm.channel_plan,
            "news": mm.channel_news,
            "script": mm.channel_script,
            "voiceover": mm.channel_voiceover,
            "footage": mm.channel_footage,
            "video": mm.channel_video,
            "publish": mm.channel_publish,
        }
        return cls(
            url=mm.url,
            bot_token=mm.bot_token,
            channel_id=mm.channel_id,
            channel_map=channel_map,
        )

    # ================================================================
    # Core API helpers
    # ================================================================

    def _post_message(
        self,
        message: str,
        props: Optional[dict] = None,
        file_ids: Optional[list] = None,
        channel_id: Optional[str] = None,
    ) -> Optional[str]:
        """Create a post in a Mattermost channel. Returns post_id on success, None on failure."""
        target_channel = channel_id or self.channel_id
        payload: Dict[str, Any] = {
            "channel_id": target_channel,
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
                post_id = resp.json().get("id", "")
                logger.info("Mattermost message sent -> channel %s (post %s)", target_channel[:8], post_id[:8])
                return post_id
            else:
                logger.error(
                    "Mattermost send failed: %d %s", resp.status_code, resp.text[:200]
                )
                return None
        except Exception as e:
            logger.error("Mattermost send error: %s", e)
            return None

    def _upload_file(self, file_path: str, channel_id: Optional[str] = None) -> Optional[str]:
        """Upload a file and return its Mattermost file ID."""
        path = Path(file_path)
        if not path.is_file():
            logger.error("File not found for upload: %s", file_path)
            return None

        target_channel = channel_id or self.channel_id
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{self.base_url}/api/v4/files",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    files={"files": (path.name, f)},
                    data={"channel_id": target_channel},
                    timeout=120,
                )
            if resp.status_code in (200, 201):
                file_id = resp.json()["file_infos"][0]["id"]
                logger.info("File uploaded: %s -> %s", path.name, file_id)
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
    # Universal Gate Approval (Human-in-the-Loop)
    # ================================================================

    GATE_LABELS = {
        0: ("\U0001f4cb", "Gate 0 \u2014 \u062e\u0637\u0629 \u0627\u0644\u0645\u062d\u062a\u0648\u0649", "Plan Approval"),
        1: ("\U0001f4f0", "Gate 1 \u2014 \u062c\u0645\u0639 \u0627\u0644\u0623\u062e\u0628\u0627\u0631", "Scrape Approval"),
        2: ("\U0001f4dd", "Gate 2 \u2014 \u0627\u0644\u0633\u0643\u0631\u064a\u0628\u062a", "Script Approval"),
        3: ("\U0001f399\ufe0f", "Gate 3 \u2014 \u0627\u0644\u062a\u0639\u0644\u064a\u0642 \u0627\u0644\u0635\u0648\u062a\u064a", "Voiceover Approval"),
        4: ("\U0001f3a5", "Gate 4 \u2014 \u0645\u0631\u0627\u062c\u0639\u0629 \u0627\u0644\u0644\u0642\u0637\u0627\u062a", "Footage Review"),
        5: ("\U0001f3ac", "Gate 5 \u2014 \u062a\u062c\u0645\u064a\u0639 \u0627\u0644\u0641\u064a\u062f\u064a\u0648", "Video Assembly Approval"),
        6: ("\U0001f680", "Gate 6 \u2014 \u0627\u0644\u0646\u0634\u0631 \u0627\u0644\u0646\u0647\u0627\u0626\u064a", "Final Publish"),
    }

    def send_gate_approval(
        self,
        gate_number: int,
        summary: str,
        details: dict,
        run_id: str,
        file_ids: Optional[list] = None,
        budget_status: str = "",
        file_paths: Optional[List[str]] = None,
    ) -> bool:
        """
        Universal approval gate for Human-in-the-Loop flow.

        Routes to the correct Mattermost channel based on gate_number.
        Sends a structured Mattermost message with Approve/Reject/Comment buttons
        that trigger n8n webhooks.
        """
        target_channel = self._resolve_channel(gate_number)

        emoji, label_ar, label_en = self.GATE_LABELS.get(
            gate_number, ("\U0001f532", f"Gate {gate_number}", f"Gate {gate_number}")
        )

        approve_url = (
            f"{self.n8n_base_url}/webhook/instagram-approve"
            f"?gate={gate_number}&run_id={run_id}&action=approve"
        )
        reject_url = (
            f"{self.n8n_base_url}/webhook/instagram-reject"
            f"?gate={gate_number}&run_id={run_id}&action=reject"
        )
        comment_url = (
            f"{self.n8n_base_url}/webhook/instagram-comment"
        )

        table_rows = "\n".join(f"| **{k}** | {v} |" for k, v in details.items())

        message = (
            f"### {emoji} {label_ar}\n\n"
            f"**Pipeline Run:** `{run_id[:12]}...`\n\n"
            f"| \u0627\u0644\u062d\u0642\u0644 | \u0627\u0644\u0642\u064a\u0645\u0629 |\n"
            f"|:------|:------|\n"
            f"{table_rows}\n\n"
        )

        if budget_status:
            message += f"**\U0001f4ca \u0627\u0644\u0645\u064a\u0632\u0627\u0646\u064a\u0629:** {budget_status}\n\n"

        message += f"---\n\n{summary}\n\n"

        if gate_number == 6:
            message += (
                "---\n\n"
                "### \U0001f5bc\ufe0f \u062a\u062d\u0645\u064a\u0644 \u0627\u0644\u0635\u0648\u0631\u0629 \u0627\u0644\u0645\u0635\u063a\u0631\u0629\n\n"
                "**\u0644\u0625\u0636\u0627\u0641\u0629 \u0627\u0644\u0635\u0648\u0631\u0629 \u0627\u0644\u0645\u0635\u063a\u0631\u0629 (Thumbnail):**\n"
                "1. \u0627\u0636\u063a\u0637 **\u0631\u062f** (Reply) \u0639\u0644\u0649 \u0647\u0630\u0647 \u0627\u0644\u0631\u0633\u0627\u0644\u0629\n"
                "2. \u0623\u0631\u0641\u0642 \u0635\u0648\u0631\u0629 PNG \u0623\u0648 JPEG (1080\u00d71920 \u0645\u062b\u0627\u0644\u064a)\n"
                "3. \u062b\u0645 \u0627\u0636\u063a\u0637 **\u0645\u0648\u0627\u0641\u0642\u0629** \u0623\u062f\u0646\u0627\u0647\n\n"
                "n8n \u0633\u064a\u0623\u062e\u0630 \u0627\u0644\u0635\u0648\u0631\u0629 \u0627\u0644\u0645\u0631\u0641\u0642\u0629 \u062a\u0644\u0642\u0627\u0626\u064a\u0627\u064b \u0645\u0646 \u0627\u0644\u0631\u062f.\n\n"
            )

        # Upload any attached files (audio, video, etc.)
        uploaded_file_ids = list(file_ids or [])
        if file_paths:
            for fp in file_paths:
                fid = self._upload_file(fp, channel_id=target_channel)
                if fid:
                    uploaded_file_ids.append(fid)

        # Comment instructions
        message += (
            "\n\U0001f4ac **\u0644\u0644\u062a\u0639\u0644\u064a\u0642:** \u0623\u0631\u0633\u0644 \u0631\u062f (Reply) \u0639\u0644\u0649 \u0647\u0630\u0647 \u0627\u0644\u0631\u0633\u0627\u0644\u0629 \u0628\u0645\u0644\u0627\u062d\u0638\u0627\u062a\u0643.\n"
            "\u0627\u0644\u062a\u0639\u0644\u064a\u0642\u0627\u062a \u062a\u064f\u062d\u0641\u0638 \u0641\u064a RAG \u0648\u064a\u062a\u0639\u0644\u0645 \u0645\u0646\u0647\u0627 \u0627\u0644\u0646\u0638\u0627\u0645.\n\n"
        )

        props = {
            "attachments": [
                {
                    "color": "#2196F3" if gate_number < 6 else "#4CAF50",
                    "actions": [
                        {
                            "id": f"approve_gate_{gate_number}",
                            "type": "button",
                            "name": "\u2705 \u0645\u0648\u0627\u0641\u0642\u0629",
                            "integration": {
                                "url": approve_url,
                                "context": {
                                    "action": "approve",
                                    "gate": gate_number,
                                    "run_id": run_id,
                                    "platform": "instagram",
                                },
                            },
                        },
                        {
                            "id": f"reject_gate_{gate_number}",
                            "type": "button",
                            "name": "\u274c \u0631\u0641\u0636",
                            "style": "danger",
                            "integration": {
                                "url": reject_url,
                                "context": {
                                    "action": "reject",
                                    "gate": gate_number,
                                    "run_id": run_id,
                                    "platform": "instagram",
                                },
                            },
                        },
                        {
                            "id": f"comment_gate_{gate_number}",
                            "type": "button",
                            "name": "\U0001f4ac \u062a\u0639\u0644\u064a\u0642",
                            "integration": {
                                "url": comment_url,
                                "context": {
                                    "action": "comment",
                                    "gate": gate_number,
                                    "run_id": run_id,
                                    "platform": "instagram",
                                },
                            },
                        },
                    ],
                }
            ]
        }

        return self._post_message(message, props=props, file_ids=uploaded_file_ids, channel_id=target_channel)

    # ================================================================
    # Post-action updates (visual feedback after button click)
    # ================================================================

    def update_post_actions(
        self,
        post_id: str,
        action: str,
        gate_number: int,
        user_name: str = "",
        comment: str = "",
    ) -> bool:
        """
        Replace the interactive buttons on a gate message with a status banner.

        Called by n8n after the user clicks Approve/Reject. This ensures:
        - Buttons are removed (prevents double-click)
        - Visual feedback shows what happened and who did it
        """
        if action == "approve":
            status_text = f"✅ **تمت الموافقة** بواسطة {user_name}" if user_name else "✅ **تمت الموافقة**"
            color = "#4CAF50"
        elif action == "reject":
            status_text = f"❌ **تم الرفض** بواسطة {user_name}" if user_name else "❌ **تم الرفض**"
            color = "#d00000"
        else:
            status_text = f"💬 **تعليق** من {user_name}" if user_name else "💬 **تعليق مُرسَل**"
            color = "#FF9800"

        if comment:
            status_text += f"\n> {comment}"

        try:
            # First, get the current post to preserve the message
            resp = requests.get(
                f"{self.base_url}/api/v4/posts/{post_id}",
                headers=self._headers,
                timeout=15,
            )
            if resp.status_code != 200:
                logger.error("Failed to get post %s for update: %d", post_id[:8], resp.status_code)
                return False

            post_data = resp.json()

            # Replace actions with a static status attachment (no buttons)
            updated_props = {
                "attachments": [
                    {
                        "color": color,
                        "text": status_text,
                    }
                ]
            }

            # Update the post props to remove buttons
            update_payload = {
                "id": post_id,
                "message": post_data.get("message", ""),
                "props": updated_props,
            }

            resp = requests.put(
                f"{self.base_url}/api/v4/posts/{post_id}",
                json=update_payload,
                headers=self._headers,
                timeout=15,
            )
            if resp.status_code == 200:
                logger.info("Post %s updated: %s gate %d", post_id[:8], action, gate_number)
                return True
            else:
                logger.error("Failed to update post %s: %d %s", post_id[:8], resp.status_code, resp.text[:200])
                return False
        except Exception as e:
            logger.error("Post update error: %s", e)
            return False

    # ================================================================
    # Send approval request (legacy - kept for compatibility)
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
        """Send a rich Mattermost message for Reel approval."""
        target_channel = self._resolve_channel(channel_key="video")
        approve_url = f"{self.n8n_base_url}/webhook/instagram-approve"
        reject_url = f"{self.n8n_base_url}/webhook/instagram-reject"

        score_emoji = (
            ":large_green_circle:"
            if validation_score >= 80
            else ":large_yellow_circle:" if validation_score >= 70 else ":red_circle:"
        )

        message = (
            f"### :camera: Instagram Reel Ready \u2014 {content_type.replace('_', ' ').title()}\n\n"
            f"| Field | Value |\n"
            f"|:------|:------|\n"
            f"| **Score** | {score_emoji} {validation_score:.0f}/100 |\n"
            f"| **Duration** | {duration:.1f}s |\n"
            f"| **Type** | {content_type} |\n"
            f"| **Video ID** | `{video_id[:8]}...` |\n\n"
            f"---\n\n"
            f"**:memo: Script:**\n```\n{script_text}\n```\n"
        )

        if news_titles:
            sources_text = "\n".join(f"- {t}" for t in news_titles[:5])
            message += f"\n**:newspaper: News Sources:**\n{sources_text}\n"

        file_ids = []
        if video_path and Path(video_path).is_file():
            file_id = self._upload_file(video_path, channel_id=target_channel)
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
                            "type": "button",
                            "name": "\u2705 Approve & Publish",
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
                            "type": "button",
                            "name": "\u274c Reject",
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

        return bool(self._post_message(message, props=props, file_ids=file_ids, channel_id=target_channel))

    # ================================================================
    # Status notifications
    # ================================================================

    def send_status(self, message: str, level: str = "info", channel_key: Optional[str] = None) -> bool:
        """Send a simple status message to a specific channel."""
        emoji = {
            "info": ":information_source:",
            "success": ":white_check_mark:",
            "warning": ":warning:",
            "error": ":x:",
        }.get(level, ":information_source:")
        target = self._resolve_channel(channel_key=channel_key) if channel_key else self.channel_id
        return bool(self._post_message(
            f"{emoji} **Instagram Reels Pipeline:** {message}",
            channel_id=target,
        ))

    def send_publish_confirmation(
        self,
        video_id: str,
        buffer_update_id: str,
        title: str,
    ) -> bool:
        """Send confirmation that Reel was published to Instagram via Buffer."""
        target_channel = self._resolve_channel(channel_key="publish")
        message = (
            f"### :rocket: Published to Instagram!\n\n"
            f"| Field | Value |\n"
            f"|:------|:------|\n"
            f"| **Title** | {title} |\n"
            f"| **Buffer ID** | `{buffer_update_id[:12]}...` |\n"
            f"| **Video** | `{video_id[:8]}...` |\n"
        )
        return bool(self._post_message(message, channel_id=target_channel))

    def send_error(self, step: str, error: str) -> bool:
        """Send pipeline error alert to the plan channel."""
        target_channel = self._resolve_channel(channel_key="plan")
        message = (
            f"### :red_circle: Instagram Pipeline Error\n\n"
            f"**Step:** {step}\n\n"
            f"**Error:**\n```\n{error}\n```"
        )
        return bool(self._post_message(message, channel_id=target_channel))
