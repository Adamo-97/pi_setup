# -*- coding: utf-8 -*-
"""
Slack Webhook Service
=======================
Handles all Slack interactions for the Human-in-the-Loop approval flow:
  - Sending script drafts for review
  - Sending generated audio for approval
  - Formatting rich messages with game data
  - Processing approval/rejection callbacks

Two-step approval flow:
  1. Script text → Slack → Human approves/rejects
  2. Generated audio → Slack → Human approves/rejects
"""

import json
import logging
from typing import Optional

import requests

from config.settings import settings

logger = logging.getLogger(__name__)


class SlackService:
    """
    Slack webhook client for human-in-the-loop approval.

    Usage:
        service = SlackService()
        service.send_script_for_approval(script_data, metadata)
    """

    TIMEOUT = 15  # seconds

    def __init__(self):
        """Initialize with Slack configuration."""
        cfg = settings.slack
        self.webhook_url = cfg.webhook_url
        self.channel = cfg.approval_channel
        self.bot_token = cfg.bot_token
        logger.info("SlackService initialized (channel=%s)", self.channel)

    def _send_webhook(self, payload: dict) -> bool:
        """
        Send a message via Slack incoming webhook.

        Args:
            payload: Slack message payload (blocks format).

        Returns:
            True if sent successfully.
        """
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.TIMEOUT,
            )

            if response.status_code == 200 and response.text == "ok":
                logger.info("Slack message sent successfully.")
                return True
            else:
                logger.error(
                    "Slack webhook failed: status=%d, body=%s",
                    response.status_code,
                    response.text[:200],
                )
                return False

        except requests.exceptions.RequestException as exc:
            logger.error("Slack webhook request failed: %s", exc)
            return False

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
        Send a generated script to Slack for human approval (Step 1).

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
        # Truncate script for Slack (3000 char limit per block)
        script_preview = script_text[:2800]
        if len(script_text) > 2800:
            script_preview += "\n\n... [النص مقتطع — السكريبت الكامل متوفر في النظام]"

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
            "🟢" if overall_score >= 80 else "🟡" if overall_score >= 60 else "🔴"
        )

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📝 سكريبت جديد للمراجعة — {title}",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*النوع:*\n{content_type}"},
                        {"type": "mrkdwn", "text": f"*عدد الألعاب:*\n{game_count}"},
                        {
                            "type": "mrkdwn",
                            "text": f"*تقييم الـ AI:*\n{score_emoji} {overall_score}/100",
                        },
                        {"type": "mrkdwn", "text": f"*الحالة:*\nبانتظار الموافقة"},
                    ],
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*ملخص المراجعة:*\n{validation_summary}",
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*السكريبت:*\n```{script_preview}```",
                    },
                },
                {"type": "divider"},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ موافقة",
                                "emoji": True,
                            },
                            "style": "primary",
                            "url": approve_url,
                            "action_id": "approve_script",
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "❌ رفض",
                                "emoji": True,
                            },
                            "style": "danger",
                            "url": reject_url,
                            "action_id": "reject_script",
                        },
                    ],
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Script ID: `{script_id}` | Pipeline: `{pipeline_run_id or 'N/A'}`",
                        }
                    ],
                },
            ]
        }

        return self._send_webhook(payload)

    def send_audio_for_approval(
        self,
        script_id: str,
        title: str,
        audio_duration: float,
        audio_file_path: str,
        pipeline_run_id: Optional[str] = None,
    ) -> bool:
        """
        Send generated audio notification to Slack for approval (Step 2).

        Note: Slack webhooks can't send files directly. This sends a notification
        with metadata. The actual .wav file can be accessed on the Pi filesystem
        or served via a simple HTTP endpoint.

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

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🎙️ تعليق صوتي جاهز — {title}",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*المدة:*\n{duration_min:.1f} دقيقة",
                        },
                        {"type": "mrkdwn", "text": f"*الملف:*\n`{audio_file_path}`"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "⚠️ *ملاحظة:* الملف الصوتي متوفر على الجهاز. "
                            "يمكنك تحميله من المسار أعلاه للمراجعة."
                        ),
                    },
                },
                {"type": "divider"},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ موافقة على الصوت",
                                "emoji": True,
                            },
                            "style": "primary",
                            "url": approve_url,
                            "action_id": "approve_audio",
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "❌ رفض — إعادة توليد",
                                "emoji": True,
                            },
                            "style": "danger",
                            "url": reject_url,
                            "action_id": "reject_audio",
                        },
                    ],
                },
            ]
        }

        return self._send_webhook(payload)

    def send_notification(self, text: str, emoji: str = "ℹ️") -> bool:
        """
        Send a simple text notification to Slack.

        Args:
            text: Message text.
            emoji: Emoji prefix.

        Returns:
            True if sent successfully.
        """
        payload = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} {text}",
                    },
                }
            ]
        }
        return self._send_webhook(payload)

    def send_error(self, error_message: str, context: str = "") -> bool:
        """
        Send an error notification to Slack.

        Args:
            error_message: The error description.
            context: Additional context (e.g., which step failed).

        Returns:
            True if sent successfully.
        """
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🚨 خطأ في نظام إنتاج المحتوى",
                        "emoji": True,
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*السياق:* {context}\n*الخطأ:* ```{error_message[:2500]}```",
                    },
                },
            ]
        }
        return self._send_webhook(payload)
