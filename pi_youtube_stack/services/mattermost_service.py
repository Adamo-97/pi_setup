# -*- coding: utf-8 -*-
"""
Mattermost Service
====================
Handles all Mattermost interactions for the Human-in-the-Loop approval flow:
  - Sending script drafts for review (full text — no truncation needed)
  - Uploading generated audio files directly for approval
  - Formatting rich messages with game data
  - Interactive approve/reject buttons via n8n webhooks

Two-step approval flow:
  1. Script text → Mattermost → Human approves/rejects
  2. Generated audio → Mattermost (file attached) → Human approves/rejects

Mattermost API Reference:
  - POST /api/v4/posts          — Create a post (up to 16,383 chars)
  - POST /api/v4/files          — Upload files (up to 100 MB)
  - Authorization: Bearer TOKEN — Bot Personal Access Token
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import requests

from config.settings import settings

logger = logging.getLogger(__name__)


class MattermostService:
    """
    Mattermost REST API client for human-in-the-loop approval.

    Usage:
        service = MattermostService()
        service.send_script_for_approval(script_data, metadata)
    """

    TIMEOUT = 30  # seconds (higher than Slack — supports file uploads)

    def __init__(self):
        """Initialize with Mattermost configuration."""
        cfg = settings.mattermost
        self.base_url = cfg.url.rstrip("/")
        self.bot_token = cfg.bot_token
        self.channel_id = cfg.channel_id
        self._headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }
        logger.info("MattermostService initialized (channel_id=%s)", self.channel_id)

    # ------------------------------------------------------------------
    # Core API helpers
    # ------------------------------------------------------------------

    def _post_message(
        self,
        message: str,
        props: Optional[dict] = None,
        file_ids: Optional[list] = None,
    ) -> bool:
        """
        Create a post in the configured Mattermost channel.

        Args:
            message: Markdown-formatted message text (up to 16,383 chars).
            props: Optional props dict (attachments, etc.).
            file_ids: Optional list of uploaded file IDs to attach.

        Returns:
            True if sent successfully.
        """
        payload = {
            "channel_id": self.channel_id,
            "message": message,
        }
        if props:
            payload["props"] = props
        if file_ids:
            payload["file_ids"] = file_ids

        try:
            response = requests.post(
                f"{self.base_url}/api/v4/posts",
                json=payload,
                headers=self._headers,
                timeout=self.TIMEOUT,
            )

            if response.status_code in (200, 201):
                logger.info("Mattermost message sent successfully.")
                return True
            else:
                logger.error(
                    "Mattermost post failed: status=%d, body=%s",
                    response.status_code,
                    response.text[:200],
                )
                return False

        except requests.exceptions.RequestException as exc:
            logger.error("Mattermost post request failed: %s", exc)
            return False

    def _upload_file(self, file_path: str) -> Optional[str]:
        """
        Upload a file to Mattermost and return its file ID.

        Args:
            file_path: Absolute path to the file on disk.

        Returns:
            File ID string, or None on failure.
        """
        path = Path(file_path)
        if not path.is_file():
            logger.error("File not found for upload: %s", file_path)
            return None

        try:
            with open(file_path, "rb") as f:
                response = requests.post(
                    f"{self.base_url}/api/v4/files",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    files={"files": (path.name, f)},
                    data={"channel_id": self.channel_id},
                    timeout=120,  # generous timeout for large files
                )

            if response.status_code in (200, 201):
                file_info = response.json()
                file_id = file_info["file_infos"][0]["id"]
                logger.info("File uploaded to Mattermost: %s → %s", path.name, file_id)
                return file_id
            else:
                logger.error(
                    "Mattermost file upload failed: status=%d, body=%s",
                    response.status_code,
                    response.text[:200],
                )
                return None

        except requests.exceptions.RequestException as exc:
            logger.error("Mattermost file upload request failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Script approval (Step 1)
    # ------------------------------------------------------------------

    def send_script_for_approval(
        self,
        script_id: str,
        content_type: str,
        title: str,
        script_text: str,
        validation_summary: str,
        overall_score: int,
        game_count: int = 0,
        pipeline_run_id: Optional[str] = None,
    ) -> bool:
        """
        Send a generated script to Mattermost for human approval (Step 1).

        Unlike Slack (3,000 char limit), Mattermost supports up to 16,383 chars
        per post — the FULL Arabic script is sent without truncation.

        Args:
            script_id: UUID of the script record.
            content_type: Content type ID.
            title: Script title.
            script_text: The full Arabic script text.
            validation_summary: Validator Agent's summary.
            overall_score: Validation score (0-100).
            game_count: Number of games covered.
            pipeline_run_id: Pipeline run UUID for callback.

        Returns:
            True if sent successfully.
        """
        # Build n8n callback URLs
        n8n_cfg = settings.n8n
        approve_url = (
            f"{n8n_cfg.base_url}{n8n_cfg.webhook_path_approve_script}"
            f"?script_id={script_id}&action=approve"
            f"&pipeline_run_id={pipeline_run_id or ''}"
        )
        reject_url = (
            f"{n8n_cfg.base_url}{n8n_cfg.webhook_path_approve_script}"
            f"?script_id={script_id}&action=reject"
            f"&pipeline_run_id={pipeline_run_id or ''}"
        )

        # Score emoji
        score_emoji = (
            ":large_green_circle:"
            if overall_score >= 80
            else ":large_yellow_circle:" if overall_score >= 60 else ":red_circle:"
        )

        # Full script — no truncation needed (Mattermost supports 16,383 chars)
        message = (
            f"### :memo: سكريبت جديد للمراجعة — {title}\n\n"
            f"| الحقل | القيمة |\n"
            f"|:------|:------|\n"
            f"| **النوع** | {content_type} |\n"
            f"| **عدد الألعاب** | {game_count} |\n"
            f"| **تقييم الـ AI** | {score_emoji} {overall_score}/100 |\n"
            f"| **الحالة** | بانتظار الموافقة |\n\n"
            f"---\n\n"
            f"**ملخص المراجعة:**\n{validation_summary}\n\n"
            f"---\n\n"
            f"**السكريبت:**\n```\n{script_text}\n```\n\n"
            f"---\n\n"
            f"_Script ID: `{script_id}` | Pipeline: `{pipeline_run_id or 'N/A'}`_"
        )

        props = {
            "attachments": [
                {
                    "color": (
                        "#36a64f"
                        if overall_score >= 80
                        else "#daa038" if overall_score >= 60 else "#d00000"
                    ),
                    "actions": [
                        {
                            "id": "approve_script",
                            "name": "✅ موافقة",
                            "integration": {
                                "url": approve_url,
                                "context": {
                                    "action": "approve",
                                    "script_id": script_id,
                                    "pipeline_run_id": pipeline_run_id or "",
                                },
                            },
                        },
                        {
                            "id": "reject_script",
                            "name": "❌ رفض",
                            "style": "danger",
                            "integration": {
                                "url": reject_url,
                                "context": {
                                    "action": "reject",
                                    "script_id": script_id,
                                    "pipeline_run_id": pipeline_run_id or "",
                                },
                            },
                        },
                    ],
                }
            ]
        }

        return self._post_message(message, props=props)

    # ------------------------------------------------------------------
    # Audio approval (Step 2)
    # ------------------------------------------------------------------

    def send_audio_for_approval(
        self,
        script_id: str,
        title: str,
        audio_duration: float,
        audio_file_path: str,
        pipeline_run_id: Optional[str] = None,
    ) -> bool:
        """
        Upload generated audio and send approval message (Step 2).

        Unlike Slack (can't send files via webhooks), Mattermost supports
        direct file uploads up to 100 MB via the REST API.

        Args:
            script_id: UUID of the script record.
            title: Script title.
            audio_duration: Duration in seconds.
            audio_file_path: Path to the .wav file on disk.
            pipeline_run_id: Pipeline run UUID.

        Returns:
            True if sent successfully.
        """
        # Build n8n callback URLs
        n8n_cfg = settings.n8n
        approve_url = (
            f"{n8n_cfg.base_url}{n8n_cfg.webhook_path_approve_audio}"
            f"?script_id={script_id}&action=approve"
            f"&pipeline_run_id={pipeline_run_id or ''}"
        )
        reject_url = (
            f"{n8n_cfg.base_url}{n8n_cfg.webhook_path_approve_audio}"
            f"?script_id={script_id}&action=reject"
            f"&pipeline_run_id={pipeline_run_id or ''}"
        )

        duration_min = audio_duration / 60

        # Upload audio file directly to Mattermost
        file_ids = []
        file_id = self._upload_file(audio_file_path)
        if file_id:
            file_ids.append(file_id)

        message = (
            f"### :studio_microphone: تعليق صوتي جاهز — {title}\n\n"
            f"| الحقل | القيمة |\n"
            f"|:------|:------|\n"
            f"| **المدة** | {duration_min:.1f} دقيقة |\n"
            f"| **الملف** | `{audio_file_path}` |\n\n"
        )

        if file_ids:
            message += ":white_check_mark: **الملف الصوتي مرفق أعلاه — يمكنك تشغيله مباشرة في Mattermost.**\n\n"
        else:
            message += ":warning: **لم يتم رفع الملف — يمكنك تحميله من المسار أعلاه للمراجعة.**\n\n"

        props = {
            "attachments": [
                {
                    "color": "#2196F3",
                    "actions": [
                        {
                            "id": "approve_audio",
                            "name": "✅ موافقة على الصوت",
                            "integration": {
                                "url": approve_url,
                                "context": {
                                    "action": "approve",
                                    "script_id": script_id,
                                    "pipeline_run_id": pipeline_run_id or "",
                                },
                            },
                        },
                        {
                            "id": "reject_audio",
                            "name": "❌ رفض — إعادة توليد",
                            "style": "danger",
                            "integration": {
                                "url": reject_url,
                                "context": {
                                    "action": "reject",
                                    "script_id": script_id,
                                    "pipeline_run_id": pipeline_run_id or "",
                                },
                            },
                        },
                    ],
                }
            ]
        }

        return self._post_message(message, props=props, file_ids=file_ids)

    # ------------------------------------------------------------------
    # Simple notifications
    # ------------------------------------------------------------------

    def send_notification(self, text: str, emoji: str = ":information_source:") -> bool:
        """
        Send a simple text notification to Mattermost.

        Args:
            text: Message text.
            emoji: Emoji prefix (Mattermost emoji syntax).

        Returns:
            True if sent successfully.
        """
        return self._post_message(f"{emoji} {text}")

    def send_error(self, error_message: str, context: str = "") -> bool:
        """
        Send an error notification to Mattermost.

        Args:
            error_message: The error description.
            context: Additional context (e.g., which step failed).

        Returns:
            True if sent successfully.
        """
        message = (
            f"### :rotating_light: خطأ في نظام إنتاج المحتوى\n\n"
            f"**السياق:** {context}\n\n"
            f"**الخطأ:**\n```\n{error_message}\n```"
        )
        return self._post_message(message)
