# -*- coding: utf-8 -*-
"""
Buffer Service
==============
Publishes X/Twitter videos via Buffer API.
Handles video upload, update creation, and status checking.
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger("x.buffer")


class BufferService:
    """Buffer API client for X/Twitter auto-publishing."""

    API_BASE = "https://api.bufferapp.com/1"

    def __init__(self, access_token: str, profile_id: str):
        self.access_token = access_token
        self.profile_id = profile_id
        self.session = requests.Session()
        self.session.params = {"access_token": self.access_token}

    # ================================================================
    # Publish video
    # ================================================================

    def publish_video(
        self,
        video_path: str,
        caption: str,
        hashtags: Optional[str] = None,
        schedule_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publish a video to X/Twitter via Buffer.

        Args:
            video_path: Path to the rendered .mp4 file.
            caption: Tweet text (should be <280 chars).
            hashtags: Space-separated hashtag string.
            schedule_at: ISO 8601 schedule time, or None for next slot.

        Returns:
            dict with success, update_id, message
        """
        video_file = Path(video_path)
        if not video_file.is_file():
            raise FileNotFoundError(f"Video not found: {video_path}")

        file_size_mb = video_file.stat().st_size / (1024 * 1024)
        if file_size_mb > 500:
            raise ValueError(f"Video too large: {file_size_mb:.1f}MB (max 500MB)")

        # Build caption with hashtags
        full_text = caption
        if hashtags:
            full_text = f"{caption}\n\n{hashtags}"

        # Buffer API: create update with media
        url = f"{self.API_BASE}/updates/create.json"

        data = {
            "profile_ids[]": self.profile_id,
            "text": full_text,
            "now": "false" if schedule_at else "true",
        }

        if schedule_at:
            data["scheduled_at"] = schedule_at

        # Upload video as media attachment
        try:
            with open(video_path, "rb") as vf:
                files = {"media[video]": (video_file.name, vf, "video/mp4")}
                resp = self.session.post(url, data=data, files=files, timeout=120)

            resp_data = resp.json()

            if resp.status_code == 200 and resp_data.get("success"):
                update_id = resp_data.get("buffer_url", "")
                updates = resp_data.get("updates", [])
                if updates:
                    update_id = updates[0].get("id", update_id)

                logger.info("Buffer publish success: %s", update_id)
                return {
                    "success": True,
                    "update_id": update_id,
                    "message": "Video queued for X publishing",
                    "response": resp_data,
                }
            else:
                error_msg = resp_data.get("message", resp.text[:500])
                logger.error("Buffer publish failed: %s", error_msg)
                return {
                    "success": False,
                    "update_id": None,
                    "message": error_msg,
                    "response": resp_data,
                }

        except requests.Timeout:
            logger.error("Buffer upload timed out for %s", video_path)
            return {
                "success": False,
                "update_id": None,
                "message": "Upload timed out (120s)",
            }
        except Exception as e:
            logger.error("Buffer publish error: %s", e)
            return {
                "success": False,
                "update_id": None,
                "message": str(e),
            }

    # ================================================================
    # Check update status
    # ================================================================

    def get_update_status(self, update_id: str) -> Dict[str, Any]:
        """Check the status of a Buffer update."""
        url = f"{self.API_BASE}/updates/{update_id}.json"
        try:
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            return {
                "status": data.get("status", "unknown"),
                "sent_at": data.get("sent_at"),
                "text": data.get("text", ""),
                "statistics": data.get("statistics", {}),
            }
        except Exception as e:
            logger.error("Buffer status check failed: %s", e)
            return {"status": "error", "message": str(e)}

    # ================================================================
    # Check profile / quota
    # ================================================================

    def get_profile_info(self) -> Dict[str, Any]:
        """Get Buffer profile information and posting limits."""
        url = f"{self.API_BASE}/profiles/{self.profile_id}.json"
        try:
            resp = self.session.get(url, timeout=15)
            data = resp.json()
            return {
                "service": data.get("service", "unknown"),
                "formatted_service": data.get("formatted_service", ""),
                "counts": data.get("counts", {}),
                "schedules": data.get("schedules", []),
            }
        except Exception as e:
            logger.error("Buffer profile info failed: %s", e)
            return {"error": str(e)}

    def get_pending_count(self) -> int:
        """Get number of pending updates in the Buffer queue."""
        url = f"{self.API_BASE}/profiles/{self.profile_id}/updates/pending.json"
        try:
            resp = self.session.get(url, params={"count": 1}, timeout=15)
            data = resp.json()
            return data.get("total", 0)
        except Exception:
            return -1

    # ================================================================
    # Default hashtags
    # ================================================================

    @staticmethod
    def get_default_hashtags(content_type: str) -> str:
        """Get default Arabic gaming + X hashtags by content type."""
        base = "#قيمنق #ألعاب #gaming #gamer #X #تويتر #GamersUnite"
        type_tags = {
            "trending_news": "#أخبار_الألعاب #gaming_news #اخبار #BreakingGaming",
            "game_spotlight": "#مراجعة #review #جيم #GameReview",
            "controversial_take": "#رأي #نقاش #debate #HotTake #GamingDebate",
            "trailer_reaction": "#تريلر #trailer #ردة_فعل #reaction #NewGame",
        }
        return f"{base} {type_tags.get(content_type, '')}"
