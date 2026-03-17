# -*- coding: utf-8 -*-
"""
Mattermost Service — YouTube
===============================
4-gate pipeline (Plan → News/Data → Script → Voiceover).
Audio delivery only — no publish gate, no metadata gate.
Each gate posts to its own dedicated channel.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("youtube.mattermost")

PLATFORM = "youtube"
PLATFORM_LABEL = "YouTube"


class MattermostService:
    """Mattermost REST API client for YouTube pipeline notifications."""

    def __init__(
        self,
        url: str = "",
        bot_token: str = "",
        channel_map: Optional[Dict[str, str]] = None,
        n8n_base_url: str = "",
    ):
        if not url or not bot_token:
            from config.settings import settings
            mm = settings.mattermost
            url = url or mm.url
            bot_token = bot_token or mm.bot_token
            channel_map = channel_map or {
                "plan": mm.channel_plan,
                "news": mm.channel_news,
                "script": mm.channel_script,
                "voiceover": mm.channel_voiceover,
            }
        self.base_url = url.rstrip("/")
        self.bot_token = bot_token
        self.channel_map: Dict[str, str] = channel_map or {}
        self.n8n_base_url = (n8n_base_url or os.environ.get("N8N_BASE_URL", "http://192.168.0.11:5678")).rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json",
        }

    # ================================================================
    # Channel routing
    # ================================================================

    GATE_CHANNELS = {0: "plan", 1: "news", 2: "script", 3: "voiceover"}

    GATE_LABELS = {
        0: ("\U0001f4cb", "Gate 0 — خطة المحتوى"),
        1: ("\U0001f4f0", "Gate 1 — جمع الأخبار والبيانات"),
        2: ("\U0001f4dd", "Gate 2 — السكريبت"),
        3: ("\U0001f399\ufe0f", "Gate 3 — التعليق الصوتي"),
    }

    def _resolve_channel(self, gate_number: Optional[int] = None, channel_key: Optional[str] = None) -> str:
        if channel_key and self.channel_map.get(channel_key):
            return self.channel_map[channel_key]
        if gate_number is not None:
            key = self.GATE_CHANNELS.get(gate_number, "plan")
            if self.channel_map.get(key):
                return self.channel_map[key]
        return self.channel_map.get("plan", "")

    @classmethod
    def from_settings(cls) -> "MattermostService":
        from config.settings import settings
        mm = settings.mattermost
        channel_map = {
            "plan": mm.channel_plan,
            "news": mm.channel_news,
            "script": mm.channel_script,
            "voiceover": mm.channel_voiceover,
        }
        return cls(
            url=mm.url,
            bot_token=mm.bot_token,
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
        target = channel_id or self._resolve_channel(0)
        payload: Dict[str, Any] = {"channel_id": target, "message": message}
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
                logger.info("Message sent -> channel %s (post %s)", target[:8], post_id[:8])
                return post_id
            logger.error("Send failed: %d %s", resp.status_code, resp.text[:200])
            return None
        except Exception as e:
            logger.error("Send error: %s", e)
            return None

    def _upload_file(self, file_path: str, channel_id: Optional[str] = None) -> Optional[str]:
        path = Path(file_path)
        if not path.is_file():
            logger.error("File not found: %s", file_path)
            return None
        target = channel_id or self._resolve_channel(0)
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"{self.base_url}/api/v4/files",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    files={"files": (path.name, f)},
                    data={"channel_id": target},
                    timeout=120,
                )
            if resp.status_code in (200, 201):
                file_id = resp.json()["file_infos"][0]["id"]
                logger.info("File uploaded: %s -> %s", path.name, file_id)
                return file_id
            logger.error("Upload failed: %d %s", resp.status_code, resp.text[:200])
            return None
        except Exception as e:
            logger.error("Upload error: %s", e)
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
                return [posts[pid] for pid in order if pid != post_id and pid in posts]
            return []
        except Exception as e:
            logger.error("get_post_thread error: %s", e)
            return []

    def get_file_url(self, file_id: str) -> str:
        return f"{self.base_url}/api/v4/files/{file_id}"

    # ================================================================
    # Action button builders
    # ================================================================

    def _build_approve_action(self, gate_number: int, run_id: str) -> dict:
        url = f"{self.n8n_base_url}/webhook/{PLATFORM}-approve?gate={gate_number}&run_id={run_id}&action=approve"
        return {
            "id": f"approveGate{gate_number}",
            "type": "button",
            "name": "\u2705 موافقة",
            "integration": {
                "url": url,
                "context": {"action": "approve", "gate": gate_number, "run_id": run_id, "platform": PLATFORM},
            },
        }

    def _build_reject_action(self, gate_number: int, run_id: str) -> dict:
        url = f"{self.n8n_base_url}/webhook/{PLATFORM}-reject?gate={gate_number}&run_id={run_id}&action=reject"
        return {
            "id": f"rejectGate{gate_number}",
            "type": "button",
            "name": "\u274c رفض",
            "style": "danger",
            "integration": {
                "url": url,
                "context": {"action": "reject", "gate": gate_number, "run_id": run_id, "platform": PLATFORM},
            },
        }

    def _build_comment_action(self, gate_number: int, run_id: str) -> dict:
        url = f"{self.n8n_base_url}/webhook/{PLATFORM}-comment"
        return {
            "id": f"commentGate{gate_number}",
            "type": "button",
            "name": "\U0001f4ac تعليق",
            "integration": {
                "url": url,
                "context": {"action": "comment", "gate": gate_number, "run_id": run_id, "platform": PLATFORM},
            },
        }

    # ================================================================
    # Gate message sender
    # ================================================================

    def send_gate_message(
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
        emoji, label_ar = self.GATE_LABELS.get(gate_number, ("\U0001f532", f"Gate {gate_number}"))

        # Extract script body from details if present
        display_details = dict(details or {})
        script_body = (
            display_details.pop("script_body", "")
            or display_details.pop("script_text", "")
            or display_details.pop("script", "")
        )

        # Build details table
        detail_block = ""
        if display_details:
            items = list(display_details.items())
            first_k, first_v = items[0]
            detail_block = f"| **{first_k}** | {first_v} |\n|:------|:------|\n"
            detail_block += "\n".join(f"| **{k}** | {v} |" for k, v in items[1:])
            detail_block += "\n\n"

        message = f"### {emoji} {label_ar}\n\n**Pipeline Run:** `{run_id[:12]}...`\n\n{detail_block}"

        if budget_status:
            message += f"**\U0001f4ca الميزانية:** {budget_status}\n\n"

        message += f"---\n\n{summary}\n\n"

        if script_body:
            message += f"### \U0001f4dd نص السكريبت\n\n\u200f{script_body}\n\n"

        # Upload attached files
        uploaded_file_ids = list(file_ids or [])
        if file_paths:
            for fp in file_paths:
                fid = self._upload_file(fp, channel_id=target_channel)
                if fid:
                    uploaded_file_ids.append(fid)

        # Build actions per gate
        actions = [self._build_approve_action(gate_number, run_id), self._build_reject_action(gate_number, run_id)]
        if gate_number == 2:
            actions.append(self._build_comment_action(gate_number, run_id))

        props = {"attachments": [{"color": "#2196F3", "actions": actions}]}

        return self._post_message(message, props=props, file_ids=uploaded_file_ids, channel_id=target_channel)

    # ================================================================
    # Comment dialog support
    # ================================================================

    def open_comment_dialog(self, trigger_id: str, gate_number: int, run_id: str) -> bool:
        """Open an interactive dialog for the user to enter a comment."""
        dialog = {
            "trigger_id": trigger_id,
            "url": f"{self.n8n_base_url}/webhook/{PLATFORM}-dialog-submit",
            "dialog": {
                "callback_id": f"comment_{gate_number}_{run_id}",
                "title": "تعليق على المحتوى",
                "submit_label": "إرسال",
                "elements": [
                    {
                        "display_name": "التعليق",
                        "name": "comment_text",
                        "type": "textarea",
                        "placeholder": "اكتب ملاحظاتك هنا...",
                    }
                ],
            },
        }
        try:
            resp = requests.post(
                f"{self.base_url}/api/v4/actions/dialogs/open",
                json=dialog, headers=self._headers, timeout=15,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error("open_comment_dialog error: %s", e)
            return False

    def handle_comment_submit(self, callback_id: str, submission: dict, user_name: str = "") -> bool:
        """Process a submitted comment dialog."""
        parts = callback_id.split("_", 2)
        if len(parts) < 3:
            return False
        gate_number = int(parts[1])
        run_id = parts[2]
        comment = submission.get("comment_text", "")
        if not comment:
            return False
        target_channel = self._resolve_channel(gate_number)
        msg = f"\U0001f4ac **تعليق** من {user_name}:\n> {comment}\n\n_Gate {gate_number} | Run `{run_id[:12]}...`_"
        return bool(self._post_message(msg, channel_id=target_channel))

    # ================================================================
    # Generation failed / retry
    # ================================================================

    def send_generation_failed(self, run_id: str, gate_number: int = 2, last_score: int = 0, attempts: int = 0) -> bool:
        target_channel = self._resolve_channel(gate_number)
        retry_url = f"{self.n8n_base_url}/webhook/{PLATFORM}-retry-script?run_id={run_id}&gate={gate_number}&action=retry"
        message = (
            f"### \u274c فشل توليد السكريبت\n\n"
            f"| التفاصيل | القيمة |\n|:------|:------|\n"
            f"| **آخر نتيجة** | {last_score}/100 |\n"
            f"| **عدد المحاولات** | {attempts} |\n"
            f"| **Run ID** | `{run_id[:12]}...` |\n"
        )
        props = {"attachments": [{"color": "#d00000", "actions": [{
            "id": "retryScript", "type": "button", "name": "\U0001f504 إعادة المحاولة",
            "integration": {"url": retry_url, "context": {"action": "retry", "gate": gate_number, "run_id": run_id, "platform": PLATFORM}},
        }]}]}
        return bool(self._post_message(message, props=props, channel_id=target_channel))

    # ================================================================
    # Post-action updates
    # ================================================================

    def update_post_actions(self, post_id: str, action: str, gate_number: int, user_name: str = "", comment: str = "") -> bool:
        if action == "approve":
            status_text = f"\u2705 **تمت الموافقة** بواسطة {user_name}" if user_name else "\u2705 **تمت الموافقة**"
            color = "#4CAF50"
        elif action == "reject":
            status_text = f"\u274c **تم الرفض** بواسطة {user_name}" if user_name else "\u274c **تم الرفض**"
            color = "#d00000"
        else:
            status_text = f"\U0001f4ac **تعليق** من {user_name}" if user_name else "\U0001f4ac **تعليق مُرسَل**"
            color = "#FF9800"
        if comment:
            status_text += f"\n> {comment}"
        try:
            resp = requests.get(f"{self.base_url}/api/v4/posts/{post_id}", headers=self._headers, timeout=15)
            if resp.status_code != 200:
                return False
            post_data = resp.json()
            update_payload = {
                "id": post_id,
                "message": post_data.get("message", ""),
                "props": {"attachments": [{"color": color, "text": status_text}]},
            }
            resp = requests.put(f"{self.base_url}/api/v4/posts/{post_id}", json=update_payload, headers=self._headers, timeout=15)
            return resp.status_code == 200
        except Exception as e:
            logger.error("Post update error: %s", e)
            return False

    # ================================================================
    # Status / error
    # ================================================================

    def send_status(self, message: str, level: str = "info", channel_key: Optional[str] = None) -> bool:
        emoji_map = {"info": ":information_source:", "success": ":white_check_mark:", "warning": ":warning:", "error": ":x:"}
        target = self._resolve_channel(channel_key=channel_key) if channel_key else self._resolve_channel(0)
        return bool(self._post_message(f"{emoji_map.get(level, ':information_source:')} **{PLATFORM_LABEL} Pipeline:** {message}", channel_id=target))

    def send_error(self, step: str, error: str) -> bool:
        target = self._resolve_channel(0)
        message = f"### :red_circle: {PLATFORM_LABEL} Pipeline Error\n\n**Step:** {step}\n\n**Error:**\n```\n{error}\n```"
        return bool(self._post_message(message, channel_id=target))
