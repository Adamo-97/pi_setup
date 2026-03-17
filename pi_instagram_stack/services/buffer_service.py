# -*- coding: utf-8 -*-
"""
Buffer Service (GraphQL API)
============================
Publishes content via Buffer's GraphQL API (api.buffer.com/graphql).
Supports text drafts, video posts with captions, and queue management.
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.buffer.com/graphql"


class BufferService:
    """Buffer GraphQL API client for pipeline auto-publishing."""

    def __init__(self, access_token: str, profile_id: str):
        self.access_token = access_token
        self.channel_id = profile_id  # Buffer calls them channels now
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        })

    # ================================================================
    # GraphQL helper
    # ================================================================

    def _gql(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query/mutation."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = self.session.post(GRAPHQL_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            msg = data["errors"][0].get("message", "Unknown GraphQL error")
            raise RuntimeError(f"Buffer GraphQL error: {msg}")
        return data.get("data", {})

    # ================================================================
    # Create draft (text-only, video attached manually in Buffer UI)
    # ================================================================

    def create_draft(self, caption: str, hashtags: str = "") -> Dict[str, Any]:
        """Create a text-only draft in Buffer queue."""
        text = caption.strip()
        if hashtags:
            text += "\n\n" + hashtags.strip()

        query = """
        mutation CreateDraft($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess { post { id text status } }
            ... on InvalidInputError { message }
            ... on UnexpectedError { message }
          }
        }
        """
        variables = {
            "input": {
                "channelId": self.channel_id,
                "text": text,
                "schedulingType": "automatic",
                "mode": "addToQueue",
                "saveToDraft": True,
            }
        }
        try:
            data = self._gql(query, variables)
            result = data.get("createPost", {})
            post = result.get("post")
            if post:
                logger.info("Buffer draft created: %s", post["id"])
                return {"success": True, "update_id": post["id"], "message": "Draft created"}
            return {"success": False, "update_id": None, "message": result.get("message", "Unknown error")}
        except Exception as e:
            logger.error("Buffer draft creation failed: %s", e)
            return {"success": False, "update_id": None, "message": str(e)}

    # ================================================================
    # Publish video (with caption)
    # ================================================================

    def publish_video(
        self,
        video_path: str,
        caption: str,
        hashtags: Optional[str] = None,
        schedule_at: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publish a video post to the channel via Buffer.

        The video must be uploaded to a public URL first (Buffer fetches it).
        For local files, this creates a draft — attach video in Buffer UI.
        """
        video_file = Path(video_path)
        text = caption.strip()
        if hashtags:
            text += "\n\n" + hashtags.strip()

        # Buffer GraphQL needs a public video URL — local files become drafts
        if video_file.is_file() and not video_path.startswith("http"):
            logger.warning("Local video file — creating draft (attach video in Buffer UI)")
            return self.create_draft(caption=text)

        query = """
        mutation PublishVideo($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess { post { id text status } }
            ... on InvalidInputError { message }
            ... on UnexpectedError { message }
            ... on LimitReachedError { message }
          }
        }
        """
        mode = "customScheduled" if schedule_at else "addToQueue"
        video_asset = {"url": video_path}
        if thumbnail_url:
            video_asset["thumbnailUrl"] = thumbnail_url

        variables = {
            "input": {
                "channelId": self.channel_id,
                "text": text,
                "schedulingType": "automatic",
                "mode": mode,
                "assets": {"videos": [video_asset]},
            }
        }
        if schedule_at:
            variables["input"]["dueAt"] = schedule_at

        try:
            data = self._gql(query, variables)
            result = data.get("createPost", {})
            post = result.get("post")
            if post:
                logger.info("Buffer video post created: %s (status: %s)", post["id"], post["status"])
                return {"success": True, "update_id": post["id"], "message": f"Post {post['status']}"}
            return {"success": False, "update_id": None, "message": result.get("message", "Unknown error")}
        except Exception as e:
            logger.error("Buffer publish failed: %s", e)
            return {"success": False, "update_id": None, "message": str(e)}

    # ================================================================
    # Profile / channel info
    # ================================================================

    def get_profile_info(self) -> Dict[str, Any]:
        """Get Buffer channel information."""
        query = """
        query GetChannel($input: ChannelInput!) {
          channel(input: $input) { id name service type }
        }
        """
        try:
            data = self._gql(query, {"input": {"id": self.channel_id}})
            return data.get("channel", {})
        except Exception as e:
            logger.error("Buffer profile info failed: %s", e)
            return {"error": str(e)}

    def get_pending_count(self) -> int:
        """Get number of pending posts (not directly available in GraphQL — returns -1)."""
        return -1

    # ================================================================
    # Default hashtags
    # ================================================================

    @staticmethod
    def get_default_hashtags(content_type: str) -> str:
        """Return default hashtags for a content type."""
        base = "#gaming #ألعاب #أخبار_الألعاب"
        extras = {
            "trending_news": "#أخبار #ترند #gaming_news",
            "game_spotlight": "#مراجعة #review #spotlight",
            "hardware_spotlight": "#هاردوير #GPU #تقنية",
            "trailer_reaction": "#تريلر #trailer #reaction",
            "controversial_take": "#رأي #hottake #debate",
        }
        return f"{base} {extras.get(content_type, '')}".strip()
