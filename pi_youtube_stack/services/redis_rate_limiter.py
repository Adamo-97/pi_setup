# -*- coding: utf-8 -*-
"""
Redis Rate Limiter — "The Bouncer"
====================================
Enforces per-platform weekly API budgets via Redis.
Every paid API call (Gemini, ElevenLabs, RAWG, SerpAPI) must pass
through The Bouncer before execution.

Redis Key Schema:
    budget:{platform}:{api_name}:week:{iso_week}

TTL: 7 days (604800 seconds) — auto-resets weekly budgets.

Usage:
    bouncer = RedisRateLimiter(platform="youtube", redis_url="redis://localhost:6379")
    bouncer.set_budget_limit(2000)  # From budgets.json

    if bouncer.check_and_consume("gemini", units=50):
        # Make API call
    else:
        raise BudgetExhaustedError(...)
"""

import logging
from datetime import date, timedelta
from typing import Dict, Optional

try:
    import redis
except ImportError:
    redis = None  # Graceful degradation if redis not installed

logger = logging.getLogger(__name__)


class BudgetExhaustedError(Exception):
    """Raised when a platform's weekly budget has been exhausted."""

    def __init__(self, platform: str, api_name: str, requested: int, remaining: int):
        self.platform = platform
        self.api_name = api_name
        self.requested = requested
        self.remaining = remaining
        super().__init__(
            f"Budget exhausted for {platform}/{api_name}: "
            f"requested {requested} units, only {remaining} remaining this week."
        )


# -------------------------------------------------------------------------
# Default API cost table (overridden by budgets.json when available)
# -------------------------------------------------------------------------
DEFAULT_API_COSTS = {
    "gemini_script": 50,
    "gemini_validate": 30,
    "gemini_metadata": 20,
    "gemini_clip_plan": 15,
    "gemini_planner": 25,
    "gemini_embedding": 5,
    "elevenlabs_per_minute": 100,
    "rawg_fetch": 2,
    "serpapi_search": 10,
}

TTL_SECONDS = 604_800  # 7 days


class RedisRateLimiter:
    """
    The Bouncer — enforces per-platform weekly API budgets via Redis.

    Attributes:
        platform: One of "youtube", "tiktok", "instagram", "x".
        redis: Redis client instance.
        _budget_limit: Weekly budget in units (set from budgets.json).
    """

    def __init__(
        self,
        platform: str,
        redis_url: str = "redis://localhost:6379",
        budget_limit: Optional[int] = None,
    ):
        if redis is None:
            raise ImportError(
                "redis package is required. Install with: pip install redis"
            )

        self.platform = platform.lower()
        self._budget_limit = budget_limit
        self._api_costs = dict(DEFAULT_API_COSTS)

        try:
            self._redis = redis.Redis.from_url(
                redis_url, decode_responses=True, socket_timeout=5
            )
            self._redis.ping()
            logger.info(
                "Redis Bouncer initialized for '%s' at %s", self.platform, redis_url
            )
        except redis.ConnectionError as exc:
            logger.error(
                "Redis connection failed: %s — Bouncer running in PERMISSIVE mode", exc
            )
            self._redis = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_budget_limit(self, weekly_units: int) -> None:
        """Set the weekly budget for this platform (from budgets.json)."""
        self._budget_limit = weekly_units
        logger.info("Budget limit set: %s = %d units/week", self.platform, weekly_units)

    def set_api_costs(self, costs: Dict[str, int]) -> None:
        """Override default API cost table (from budgets.json)."""
        self._api_costs.update(costs)

    def get_api_cost(self, api_name: str) -> int:
        """Get the unit cost for a specific API operation."""
        return self._api_costs.get(api_name, 1)

    # ------------------------------------------------------------------
    # Budget enforcement
    # ------------------------------------------------------------------

    def check_and_consume(self, api_name: str, units: Optional[int] = None) -> bool:
        """
        Check if budget allows consumption and atomically increment.

        Args:
            api_name: API operation name (e.g., "gemini_script", "elevenlabs_per_minute").
            units: Number of units to consume. If None, uses default cost from table.

        Returns:
            True if budget allows and units were consumed.
            False if budget would be exceeded (no units consumed).

        Note:
            If Redis is unavailable, returns True (permissive mode) with a warning.
        """
        if units is None:
            units = self.get_api_cost(api_name)

        if self._redis is None:
            logger.warning(
                "Redis unavailable — PERMISSIVE mode: allowing %s/%s (%d units)",
                self.platform,
                api_name,
                units,
            )
            return True

        week_key = self._week_key()
        total_key = f"budget:{self.platform}:total:week:{week_key}"
        api_key = f"budget:{self.platform}:{api_name}:week:{week_key}"

        try:
            # Check total budget first
            if self._budget_limit is not None:
                current_total = int(self._redis.get(total_key) or 0)
                if (current_total + units) > self._budget_limit:
                    logger.warning(
                        "BUDGET DENIED: %s/%s — requested %d, used %d/%d",
                        self.platform,
                        api_name,
                        units,
                        current_total,
                        self._budget_limit,
                    )
                    return False

            # Atomically increment both keys
            pipe = self._redis.pipeline()
            pipe.incrby(total_key, units)
            pipe.expire(total_key, TTL_SECONDS)
            pipe.incrby(api_key, units)
            pipe.expire(api_key, TTL_SECONDS)
            pipe.execute()

            new_total = int(self._redis.get(total_key) or 0)
            logger.info(
                "BUDGET OK: %s/%s consumed %d units (total: %d/%s)",
                self.platform,
                api_name,
                units,
                new_total,
                self._budget_limit or "unlimited",
            )
            return True

        except Exception as exc:
            logger.error("Redis error during budget check — PERMISSIVE: %s", exc)
            return True

    def check_budget(self, api_name: str, units: Optional[int] = None) -> bool:
        """
        Check if budget allows consumption WITHOUT consuming.
        Dry-run version of check_and_consume().
        """
        if units is None:
            units = self.get_api_cost(api_name)

        if self._redis is None or self._budget_limit is None:
            return True

        try:
            week_key = self._week_key()
            total_key = f"budget:{self.platform}:total:week:{week_key}"
            current_total = int(self._redis.get(total_key) or 0)
            return (current_total + units) <= self._budget_limit
        except Exception:
            return True

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_remaining(self) -> int:
        """Get remaining budget units for this week."""
        if self._redis is None or self._budget_limit is None:
            return self._budget_limit or 0

        try:
            week_key = self._week_key()
            total_key = f"budget:{self.platform}:total:week:{week_key}"
            used = int(self._redis.get(total_key) or 0)
            return max(0, self._budget_limit - used)
        except Exception:
            return self._budget_limit or 0

    def get_used(self) -> int:
        """Get total units used this week."""
        if self._redis is None:
            return 0

        try:
            week_key = self._week_key()
            total_key = f"budget:{self.platform}:total:week:{week_key}"
            return int(self._redis.get(total_key) or 0)
        except Exception:
            return 0

    def get_usage_report(self) -> Dict[str, int]:
        """
        Get detailed usage report broken down by API.

        Returns:
            Dict mapping API name to units consumed this week.
        """
        report = {}
        if self._redis is None:
            return report

        try:
            week_key = self._week_key()
            for api_name in self._api_costs:
                key = f"budget:{self.platform}:{api_name}:week:{week_key}"
                used = int(self._redis.get(key) or 0)
                if used > 0:
                    report[api_name] = used

            total_key = f"budget:{self.platform}:total:week:{week_key}"
            report["_total"] = int(self._redis.get(total_key) or 0)
            report["_limit"] = self._budget_limit or 0
            report["_remaining"] = max(0, (self._budget_limit or 0) - report["_total"])
        except Exception as exc:
            logger.error("Failed to generate usage report: %s", exc)

        return report

    def format_budget_status(self) -> str:
        """Format a human-readable budget status string for Mattermost."""
        report = self.get_usage_report()
        total = report.get("_total", 0)
        limit = report.get("_limit", 0)
        remaining = report.get("_remaining", 0)

        if limit == 0:
            return f"📊 **{self.platform.title()}** budget: unlimited"

        pct = (total / limit * 100) if limit > 0 else 0
        bar_filled = int(pct / 10)
        bar_empty = 10 - bar_filled
        bar = "█" * bar_filled + "░" * bar_empty

        emoji = "🟢" if pct < 80 else "🟡" if pct < 95 else "🔴"

        return (
            f"{emoji} **{self.platform.title()}** budget: "
            f"{total}/{limit} units [{bar}] {pct:.0f}% — "
            f"{remaining} remaining"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _week_key() -> str:
        """Return ISO week identifier, e.g., '2025-W28'."""
        today = date.today()
        iso = today.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
