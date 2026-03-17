# -*- coding: utf-8 -*-
"""
Mattermost Service
====================
Sends TikTok pipeline previews and scripts to Mattermost for approval.
Rich Markdown messages with interactive approve/reject/comment action buttons
routed to n8n webhooks. Each gate posts to its own dedicated channel.

Gate 4 (Publish) opens an interactive dialog for scheduling date/time,
and instructs the user to upload video + thumbnail as a reply before approving.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("tiktok.mattermost")

PLATFORM = "tiktok"
PLATFORM_LABEL = "TikTok"


class MattermostService:
    """Mattermost REST API client for TikTok pipeline notifications."""

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
        self.channel_id = channel_id
        self.channel_map: Dict[str, str] = channel_map or {}
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
        4: "publish",
    }

    def _resolve_channel(self, gate_number: Optional[int] = None, channel_key: Optional[str] = None) -> str:
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
        from config.settings import get_settings
        s = get_settings()
        mm = s.mattermost
        channel_map = {
            "plan": mm.channel_plan,
            "news": mm.channel_news,
            "script": mm.channel_script,
            "voiceover": mm.channel_voiceover,
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
        target_channel = channel_id or self.channel_id
        payload: Dict[str, Any] = {"channel_id": target_channel, "message": message}
        if props:
            payload["props"] = props
        if file_ids:
            payload["file_ids"] = file_ids
        try:
            resp = requests.post(
                f"{self.base_url}/api/v4/posts", json=payload,
                headers=self._headers, timeout=30,
            )
            if resp.status_code in (200, 201):
                post_id = resp.json().get("id", "")
                logger.info("Mattermost message sent -> channel %s (post %s)", target_channel[:8], post_id[:8])
                return post_id
            logger.error("Mattermost send failed: %d %s", resp.status_code, resp.text[:200])
            return None
        except Exception as e:
            logger.error("Mattermost send error: %s", e)
            return None

    def _upload_file(self, file_path: str, channel_id: Optional[str] = None) -> Optional[str]:
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
            logger.error("File upload failed: %d %s", resp.status_code, resp.text[:200])
            return None
        except Exception as e:
            logger.error("File upload error: %s", e)
            return None

    def get_post_thread(self, post_id: str) -> List[dict]:
        """Get all replies to a post (for fetching uploaded files)."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/v4/posts/{post_id}/thread",
                headers=self._headers, timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                order = data.get("order", [])
                posts = data.get("posts", {})
                # Return replies only (skip the root post)
                return [posts[pid] for pid in order if pid != post_id and pid in posts]
            return []
        except Exception as e:
            logger.error("get_post_thread error: %s", e)
            return []

    def get_file_url(self, file_id: str) -> str:
        """Get the public download URL for a Mattermost file."""
        return f"{self.base_url}/api/v4/files/{file_id}"

    # ================================================================
    # Universal Gate Approval (Human-in-the-Loop)
    # ================================================================

    GATE_LABELS = {
        0: ("\U0001f4cb", "Gate 0 — خطة المحتوى"),
        1: ("\U0001f4f0", "Gate 1 — جمع الأخبار"),
        2: ("\U0001f4dd", "Gate 2 — السكريبت"),
        3: ("\U0001f399\ufe0f", "Gate 3 — التعليق الصوتي"),
        4: ("\U0001f680", "Gate 4 — النشر"),
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
    ) -> Optional[str]:
        target_channel = self._resolve_channel(gate_number)

        emoji, label_ar = self.GATE_LABELS.get(
            gate_number, ("\U0001f532", f"Gate {gate_number}")
        )

        def rtl(text: str) -> str:
            cleaned = (text or "").strip()
            if not cleaned:
                return ""
            return "\n".join(f"\u200f{line}" for line in cleaned.splitlines())

        display_details = dict(details or {})
        script_body = (
            display_details.pop("script_body", "")
            or display_details.pop("script_text", "")
            or display_details.pop("script", "")
        )

        detail_block = ""
        if display_details:
            items = list(display_details.items())
            first_k, first_v = items[0]
            body_rows = "\n".join(f"| **{k}** | {v} |" for k, v in items[1:])
            detail_block = f"| **{first_k}** | {first_v} |\n|:------|:------|\n"
            if body_rows:
                detail_block += f"{body_rows}\n"
            detail_block += "\n"

        message = (
            f"### {emoji} {label_ar}\n\n"
            f"**Pipeline Run:** `{run_id[:12]}...`\n\n"
            f"{detail_block}"
        )

        if budget_status:
            message += f"**\U0001f4ca الميزانية:** {budget_status}\n\n"

        if gate_number == 0:
            message += f"---\n\n{rtl(summary)}\n\n"
        else:
            message += f"---\n\n{summary}\n\n"

        if script_body:
            message += f"### \U0001f4dd نص السكريبت\n\n{rtl(script_body)}\n\n"

        # Gate 4: publish instructions
        if gate_number == 4:
            message += (
                "---\n\n"
                "### \U0001f4e4 تعليمات النشر\n\n"
                "\u200f1. **أرفق الفيديو والصورة المصغرة** — اضغط رد (Reply) على هذه الرسالة وأرفق الملفات\n"
                "\u200f2. **اضغط موافقة** — ستظهر نافذة لاختيار تاريخ ووقت النشر\n"
                "\u200f3. أدخل التاريخ والوقت بصيغة `YYYY-MM-DD HH:MM` (توقيت السعودية)\n\n"
            )

        # Upload attached files
        uploaded_file_ids = list(file_ids or [])
        if file_paths:
            for fp in file_paths:
                fid = self._upload_file(fp, channel_id=target_channel)
                if fid:
                    uploaded_file_ids.append(fid)

        message += (
            "\n"
            f"{rtl('💬 **للتعليق:** أرسل رد (Reply) على هذه الرسالة بملاحظاتك.')}\n"
            f"{rtl('التعليقات تُحفظ في RAG ويتعلم منها النظام.')}\n\n"
        )

        # Build action buttons
        if gate_number == 4:
            # Publish gate: approve opens a dialog for scheduling
            actions = self._build_publish_actions(gate_number, run_id)
        else:
            actions = self._build_standard_actions(gate_number, run_id)

        props = {
            "attachments": [{
                "color": "#2196F3",
                "actions": actions,
            }]
        }

        return self._post_message(message, props=props, file_ids=uploaded_file_ids, channel_id=target_channel)

    def _build_standard_actions(self, gate_number: int, run_id: str) -> list:
        approve_url = f"{self.n8n_base_url}/webhook/{PLATFORM}-approve?gate={gate_number}&run_id={run_id}&action=approve"
        reject_url = f"{self.n8n_base_url}/webhook/{PLATFORM}-reject?gate={gate_number}&run_id={run_id}&action=reject"
        comment_url = f"{self.n8n_base_url}/webhook/{PLATFORM}-comment"

        actions = [
            {
                "id": f"approveGate{gate_number}",
                "type": "button",
                "name": "\u2705 موافقة",
                "integration": {
                    "url": approve_url,
                    "context": {"action": "approve", "gate": gate_number, "run_id": run_id, "platform": PLATFORM},
                },
            },
            {
                "id": f"rejectGate{gate_number}",
                "type": "button",
                "name": "\u274c رفض",
                "style": "danger",
                "integration": {
                    "url": reject_url,
                    "context": {"action": "reject", "gate": gate_number, "run_id": run_id, "platform": PLATFORM},
                },
            },
        ]
        if gate_number in (0, 1, 2, 4):
            actions.append({
                "id": f"commentGate{gate_number}",
                "type": "button",
                "name": "\U0001f4ac تعليق",
                "integration": {
                    "url": comment_url,
                    "context": {"action": "comment", "gate": gate_number, "run_id": run_id, "platform": PLATFORM},
                },
            })
        return actions

    def _build_publish_actions(self, gate_number: int, run_id: str) -> list:
        """Build Gate 4 actions: approve opens a scheduling dialog."""
        dialog_url = f"{self.n8n_base_url}/webhook/{PLATFORM}-publish-dialog"
        reject_url = f"{self.n8n_base_url}/webhook/{PLATFORM}-reject?gate={gate_number}&run_id={run_id}&action=reject"

        return [
            {
                "id": "publishApprove",
                "type": "button",
                "name": "\U0001f680 موافقة ونشر",
                "integration": {
                    "url": dialog_url,
                    "context": {
                        "action": "publish_dialog",
                        "gate": gate_number,
                        "run_id": run_id,
                        "platform": PLATFORM,
                    },
                },
            },
            {
                "id": f"rejectGate{gate_number}",
                "type": "button",
                "name": "\u274c رفض",
                "style": "danger",
                "integration": {
                    "url": reject_url,
                    "context": {"action": "reject", "gate": gate_number, "run_id": run_id, "platform": PLATFORM},
                },
            },
        ]

    # ================================================================
    # Post-action updates
    # ================================================================

    def update_post_actions(
        self,
        post_id: str,
        action: str,
        gate_number: int,
        user_name: str = "",
        comment: str = "",
    ) -> bool:
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
            resp = requests.get(
                f"{self.base_url}/api/v4/posts/{post_id}",
                headers=self._headers, timeout=15,
            )
            if resp.status_code != 200:
                return False
            post_data = resp.json()
            update_payload = {
                "id": post_id,
                "message": post_data.get("message", ""),
                "props": {"attachments": [{"color": color, "text": status_text}]},
            }
            resp = requests.put(
                f"{self.base_url}/api/v4/posts/{post_id}",
                json=update_payload, headers=self._headers, timeout=15,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("Post update error: %s", e)
            return False

    # ================================================================
    # Generation failed
    # ================================================================

    def send_generation_failed(
        self, run_id: str, gate_number: int = 2, last_score: int = 0, attempts: int = 0
    ) -> bool:
        target_channel = self._resolve_channel(gate_number)
        retry_url = f"{self.n8n_base_url}/webhook/{PLATFORM}-retry-script?run_id={run_id}&gate={gate_number}&action=retry"
        message = (
            f"### ❌ فشل توليد السكريبت\n\n"
            f"| التفاصيل | القيمة |\n|:------|:------|\n"
            f"| **آخر نتيجة** | {last_score}/100 |\n"
            f"| **عدد المحاولات** | {attempts} |\n"
            f"| **Run ID** | `{run_id[:12]}...` |\n"
        )
        props = {"attachments": [{"color": "#d00000", "actions": [{
            "id": "retryScript", "type": "button", "name": "🔄 إعادة المحاولة",
            "integration": {"url": retry_url, "context": {"action": "retry", "gate": gate_number, "run_id": run_id, "platform": PLATFORM}},
        }]}]}
        return bool(self._post_message(message, props=props, channel_id=target_channel))

    # ================================================================
    # Status / error / confirmation
    # ================================================================

    def send_status(self, message: str, level: str = "info", channel_key: Optional[str] = None) -> bool:
        emoji_map = {"info": ":information_source:", "success": ":white_check_mark:", "warning": ":warning:", "error": ":x:"}
        target = self._resolve_channel(channel_key=channel_key) if channel_key else self.channel_id
        return bool(self._post_message(f"{emoji_map.get(level, ':information_source:')} **{PLATFORM_LABEL} Pipeline:** {message}", channel_id=target))

    def send_publish_confirmation(self, video_id: str, buffer_update_id: str, title: str) -> bool:
        target_channel = self._resolve_channel(channel_key="publish")
        message = (
            f"### :rocket: Published to {PLATFORM_LABEL}!\n\n"
            f"| Field | Value |\n|:------|:------|\n"
            f"| **Title** | {title} |\n"
            f"| **Buffer ID** | `{buffer_update_id[:12]}...` |\n"
            f"| **Video** | `{video_id[:8]}...` |\n"
        )
        return bool(self._post_message(message, channel_id=target_channel))

    def send_error(self, step: str, error: str) -> bool:
        target_channel = self._resolve_channel(channel_key="plan")
        message = f"### :red_circle: {PLATFORM_LABEL} Pipeline Error\n\n**Step:** {step}\n\n**Error:**\n```\n{error}\n```"
        return bool(self._post_message(message, channel_id=target_channel))
