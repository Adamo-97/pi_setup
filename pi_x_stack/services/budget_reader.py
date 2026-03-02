# -*- coding: utf-8 -*-
"""
Budget Reader
===============
Reads budgets.json from Nextcloud WebDAV with Redis cache and local fallback.

Load order:
  1. Redis cache (TTL 1 hour)
  2. Nextcloud WebDAV (remote fetch)
  3. Local file (config/budgets.json)

Usage:
    reader = BudgetReader(platform="youtube", redis_url="redis://localhost:6379")
    budget = reader.get_weekly_budget()      # → 2000
    cost   = reader.get_api_cost("gemini_script")  # → 50
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import redis as redis_lib
except ImportError:
    redis_lib = None

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Fallback budget config (used when Nextcloud + local file both unavailable)
# -------------------------------------------------------------------------
FALLBACK_CONFIG = {
    "version": 1,
    "total_weekly_units": 5000,
    "platforms": {
        "youtube": {"weekly_units": 2000, "priority": 1, "enabled": True},
        "tiktok": {"weekly_units": 1000, "priority": 2, "enabled": True},
        "instagram": {"weekly_units": 1000, "priority": 3, "enabled": True},
        "x": {"weekly_units": 1000, "priority": 4, "enabled": True},
    },
    "api_costs": {
        "gemini_script": 50,
        "gemini_validate": 30,
        "gemini_metadata": 20,
        "gemini_clip_plan": 15,
        "gemini_planner": 25,
        "gemini_embedding": 5,
        "elevenlabs_per_minute": 100,
        "rawg_fetch": 2,
        "serpapi_search": 10,
    },
    "alerts": {
        "warn_at_percent": 80,
        "critical_at_percent": 95,
    },
}

CACHE_KEY = "budgets:config:json"
CACHE_TTL = 3600  # 1 hour


class BudgetReader:
    """
    Reads budgets.json from Nextcloud WebDAV with Redis cache and local fallback.

    Attributes:
        platform: One of "youtube", "tiktok", "instagram", "x".
    """

    def __init__(
        self,
        platform: str,
        redis_url: str = "redis://localhost:6379",
        nextcloud_url: Optional[str] = None,
        nextcloud_user: Optional[str] = None,
        nextcloud_password: Optional[str] = None,
        local_path: Optional[str] = None,
    ):
        self.platform = platform.lower()

        # Redis client for caching
        self._redis = None
        if redis_lib is not None:
            try:
                self._redis = redis_lib.Redis.from_url(
                    redis_url, decode_responses=True, socket_timeout=5
                )
                self._redis.ping()
            except Exception:
                self._redis = None

        # Nextcloud WebDAV configuration
        self._nextcloud_url = (
            nextcloud_url
            or os.getenv("NEXTCLOUD_BUDGETS_URL")
            or "https://192.168.1.100:8443/remote.php/dav/files"
        )
        self._nextcloud_user = (
            nextcloud_user or os.getenv("NEXTCLOUD_USER", "admin")
        )
        self._nextcloud_password = (
            nextcloud_password or os.getenv("NEXTCLOUD_PASSWORD", "")
        )
        self._nextcloud_path = os.getenv(
            "NEXTCLOUD_BUDGETS_PATH", "pi_config/budgets.json"
        )

        # Local fallback path
        self._local_path = Path(
            local_path
            or os.getenv("BUDGETS_LOCAL_PATH", "")
            or (Path(__file__).resolve().parent.parent / "config" / "budgets.json")
        )

        self._config_cache: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        """
        Load budgets.json — tries Redis cache → Nextcloud → local file → fallback.

        Returns:
            Full budgets.json config dict.
        """
        if self._config_cache is not None:
            return self._config_cache

        config = self._load_from_redis()
        if config:
            self._config_cache = config
            return config

        config = self._load_from_nextcloud()
        if config:
            self._cache_to_redis(config)
            self._config_cache = config
            return config

        config = self._load_from_local()
        if config:
            self._cache_to_redis(config)
            self._config_cache = config
            return config

        logger.warning("All budget sources failed — using hardcoded fallback")
        self._config_cache = FALLBACK_CONFIG
        return FALLBACK_CONFIG

    def get_weekly_budget(self) -> int:
        """Get this platform's weekly budget in units."""
        config = self.load()
        platform_config = config.get("platforms", {}).get(self.platform, {})
        return platform_config.get("weekly_units", 1000)

    def get_api_cost(self, api_name: str) -> int:
        """Get the unit cost for a specific API call."""
        config = self.load()
        return config.get("api_costs", {}).get(api_name, 1)

    def get_api_costs(self) -> Dict[str, int]:
        """Get all API costs as a dict."""
        config = self.load()
        return dict(config.get("api_costs", {}))

    def is_platform_enabled(self) -> bool:
        """Check if this platform is enabled in the budget config."""
        config = self.load()
        platform_config = config.get("platforms", {}).get(self.platform, {})
        return platform_config.get("enabled", True)

    def get_alert_thresholds(self) -> Dict[str, int]:
        """Get alert percentage thresholds."""
        config = self.load()
        return config.get("alerts", {"warn_at_percent": 80, "critical_at_percent": 95})

    def reload(self) -> Dict[str, Any]:
        """Force reload from source (bypass cache)."""
        self._config_cache = None
        if self._redis:
            try:
                self._redis.delete(CACHE_KEY)
            except Exception:
                pass
        return self.load()

    # ------------------------------------------------------------------
    # Private loaders
    # ------------------------------------------------------------------

    def _load_from_redis(self) -> Optional[Dict[str, Any]]:
        """Try to load from Redis cache."""
        if self._redis is None:
            return None

        try:
            cached = self._redis.get(CACHE_KEY)
            if cached:
                config = json.loads(cached)
                logger.debug("budgets.json loaded from Redis cache")
                return config
        except Exception as exc:
            logger.debug("Redis cache miss: %s", exc)

        return None

    def _load_from_nextcloud(self) -> Optional[Dict[str, Any]]:
        """Try to load from Nextcloud WebDAV."""
        if requests is None or not self._nextcloud_password:
            return None

        url = (
            f"{self._nextcloud_url}/{self._nextcloud_user}/"
            f"{self._nextcloud_path}"
        )

        try:
            resp = requests.get(
                url,
                auth=(self._nextcloud_user, self._nextcloud_password),
                timeout=10,
                verify=False,  # Self-signed cert on local Pi
            )
            if resp.status_code == 200:
                config = resp.json()
                logger.info("budgets.json loaded from Nextcloud WebDAV")
                return config
            else:
                logger.debug(
                    "Nextcloud returned %d for budgets.json", resp.status_code
                )
        except Exception as exc:
            logger.debug("Nextcloud fetch failed: %s", exc)

        return None

    def _load_from_local(self) -> Optional[Dict[str, Any]]:
        """Try to load from local file."""
        if self._local_path.is_file():
            try:
                with open(self._local_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                logger.info("budgets.json loaded from local file: %s", self._local_path)
                return config
            except Exception as exc:
                logger.error("Failed to read local budgets.json: %s", exc)

        return None

    def _cache_to_redis(self, config: Dict[str, Any]) -> None:
        """Cache config in Redis with TTL."""
        if self._redis is None:
            return

        try:
            self._redis.setex(CACHE_KEY, CACHE_TTL, json.dumps(config))
            logger.debug("budgets.json cached in Redis (TTL=%ds)", CACHE_TTL)
        except Exception as exc:
            logger.debug("Failed to cache in Redis: %s", exc)
