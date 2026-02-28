#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch Game Data
=================
Fetches game data from RAWG.io and stores it in the local PostgreSQL database.
Designed to be called by n8n before script generation.

Usage (n8n Execute Command):
    python3 /path/to/scripts/fetch_game_data.py --type monthly_releases --year 2026 --month 3
    python3 /path/to/scripts/fetch_game_data.py --type upcoming_games
    python3 /path/to/scripts/fetch_game_data.py --type aaa_review --game-slug elden-ring

Output (stdout JSON):
    {
        "success": true,
        "game_count": 15,
        "content_type": "monthly_releases",
        "games": [...]
    }
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.rawg_service import RAWGService

# ---------------------------------------------------------------------------
# Logging — send to stderr only, keep stdout clean for JSON
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("fetch_game_data")


def fetch_monthly_releases(year: int, month: int, max_pages: int = 3) -> dict:
    """
    Fetch and store all game releases for a given month.

    Args:
        year: Target year.
        month: Target month (1-12).
        max_pages: Maximum RAWG API pages to fetch.

    Returns:
        Result dict with game data.
    """
    service = RAWGService()
    games = service.fetch_and_store_monthly(year, month, max_pages=max_pages)

    # Convert to serializable format
    games_list = []
    for game in games:
        games_list.append(game.model_dump(mode="json"))

    return {
        "success": True,
        "content_type": "monthly_releases",
        "game_count": len(games_list),
        "year": year,
        "month": month,
        "games": games_list,
    }


def fetch_upcoming_games(max_pages: int = 2) -> dict:
    """
    Fetch upcoming game releases.

    Args:
        max_pages: Maximum RAWG API pages to fetch.

    Returns:
        Result dict with upcoming game data.
    """
    service = RAWGService()
    all_games = []

    for page in range(1, max_pages + 1):
        raw_games = service.get_upcoming_games(page=page)
        if not raw_games:
            break

        for raw in raw_games:
            try:
                game = service.rawg_to_game_model(raw)
                service.store_game(game)
                all_games.append(game.model_dump(mode="json"))
            except Exception as exc:
                logger.warning(
                    "Failed to process game '%s': %s", raw.get("name", "?"), exc
                )

    return {
        "success": True,
        "content_type": "upcoming_games",
        "game_count": len(all_games),
        "games": all_games,
    }


def fetch_game_for_review(game_slug: str) -> dict:
    """
    Fetch detailed data for a specific game (for AAA review).

    Args:
        game_slug: RAWG game slug or ID (e.g., "elden-ring" or "12345").

    Returns:
        Result dict with single game data.
    """
    service = RAWGService()

    try:
        raw_data = service.get_game_details(game_slug)
        game = service.rawg_to_game_model(raw_data)
        service.store_game(game)

        return {
            "success": True,
            "content_type": "aaa_review",
            "game_count": 1,
            "games": [game.model_dump(mode="json")],
        }
    except Exception as exc:
        logger.error("Failed to fetch game '%s': %s", game_slug, exc)
        return {
            "success": False,
            "error": str(exc),
            "content_type": "aaa_review",
            "game_count": 0,
            "games": [],
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch game data from RAWG.io and store in PostgreSQL."
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=["monthly_releases", "upcoming_games", "aaa_review"],
        help="Content type to fetch games for.",
    )
    parser.add_argument(
        "--year", type=int, default=date.today().year, help="Year (default: current)."
    )
    parser.add_argument(
        "--month",
        type=int,
        default=date.today().month,
        help="Month (default: current).",
    )
    parser.add_argument(
        "--game-slug", type=str, help="Game slug for AAA review (e.g., 'elden-ring')."
    )
    parser.add_argument(
        "--max-pages", type=int, default=3, help="Max RAWG API pages to fetch."
    )

    args = parser.parse_args()

    try:
        if args.type == "monthly_releases":
            result = fetch_monthly_releases(args.year, args.month, args.max_pages)
        elif args.type == "upcoming_games":
            result = fetch_upcoming_games(args.max_pages)
        elif args.type == "aaa_review":
            if not args.game_slug:
                result = {
                    "success": False,
                    "error": "--game-slug is required for aaa_review type.",
                }
            else:
                result = fetch_game_for_review(args.game_slug)
        else:
            result = {"success": False, "error": f"Unknown type: {args.type}"}

    except Exception as exc:
        logger.exception("Fatal error in fetch_game_data")
        result = {"success": False, "error": str(exc)}

    # Print clean JSON to stdout for n8n
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
