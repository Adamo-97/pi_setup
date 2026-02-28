#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Script
=================
Main script generation pipeline entry point.
Called by n8n after game data has been fetched.

This script:
  1. Reads game data from the database (or accepts JSON input)
  2. Invokes the Writer Agent to generate an Arabic YouTube script
  3. Outputs structured JSON for the next pipeline step (validation)

Usage (n8n Execute Command):
    python3 scripts/generate_script.py --type monthly_releases --year 2026 --month 3
    python3 scripts/generate_script.py --type aaa_review --game-slug elden-ring
    python3 scripts/generate_script.py --type upcoming_games
    python3 scripts/generate_script.py --type monthly_releases --duration 12

    # With JSON input from previous n8n node:
    echo '{"content_type": "monthly_releases", "games": [...]}' | python3 scripts/generate_script.py --from-stdin

Output (stdout JSON):
    {
        "success": true,
        "script_id": "uuid",
        "title": "...",
        "script_text": "...",
        "word_count": 1300,
        "estimated_duration": 10.0,
        ...
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

from agents.writer_agent import WriterAgent
from database.connection import execute_query

# ---------------------------------------------------------------------------
# Logging — stderr only
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("generate_script")


def get_games_from_db(
    content_type: str, year: int = None, month: int = None
) -> list[dict]:
    """
    Retrieve games from the local database based on content type.

    Args:
        content_type: Type of content being generated.
        year: Target year (for monthly releases).
        month: Target month (for monthly releases).

    Returns:
        List of game dicts.
    """
    today = date.today()
    y = year or today.year
    m = month or today.month

    if content_type == "monthly_releases":
        query = """
            SELECT * FROM games
            WHERE EXTRACT(YEAR FROM release_date) = %s
              AND EXTRACT(MONTH FROM release_date) = %s
            ORDER BY release_date ASC, rating DESC NULLS LAST
        """
        return execute_query(query, (y, m)) or []

    elif content_type == "upcoming_games":
        query = """
            SELECT * FROM games
            WHERE release_date > CURRENT_DATE
            ORDER BY release_date ASC
            LIMIT 20
        """
        return execute_query(query) or []

    elif content_type == "aaa_review":
        # For reviews, we typically target a specific game
        # Return the most recently added game as fallback
        query = """
            SELECT * FROM games
            ORDER BY created_at DESC
            LIMIT 1
        """
        return execute_query(query) or []

    return []


def get_game_by_slug(slug: str) -> list[dict]:
    """Retrieve a specific game by slug from the database."""
    query = "SELECT * FROM games WHERE slug = %s LIMIT 1"
    return execute_query(query, (slug,)) or []


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate an Arabic YouTube script using the Writer Agent."
    )
    parser.add_argument(
        "--type",
        required=False,
        choices=["monthly_releases", "aaa_review", "upcoming_games"],
        help="Content type to generate.",
    )
    parser.add_argument(
        "--year", type=int, default=None, help="Year (default: current)."
    )
    parser.add_argument(
        "--month", type=int, default=None, help="Month (default: current)."
    )
    parser.add_argument("--game-slug", type=str, help="Game slug for AAA review.")
    parser.add_argument(
        "--duration", type=float, default=10.0, help="Target duration in minutes."
    )
    parser.add_argument(
        "--trigger",
        type=str,
        default="manual",
        help="Trigger source (manual/schedule/n8n).",
    )
    parser.add_argument(
        "--from-stdin", action="store_true", help="Read JSON input from stdin."
    )

    args = parser.parse_args()

    try:
        # ------------------------------------------------------------------
        # Determine input source
        # ------------------------------------------------------------------
        if args.from_stdin:
            # Read JSON from stdin (piped from previous n8n node)
            stdin_data = json.loads(sys.stdin.read())
            content_type = stdin_data.get("content_type", args.type)
            games_data = stdin_data.get("games", [])
            game_title = stdin_data.get("game_title")
            target_duration = stdin_data.get("target_duration", args.duration)
            trigger = stdin_data.get("trigger_source", args.trigger)
        else:
            if not args.type:
                print(
                    json.dumps(
                        {
                            "success": False,
                            "error": "--type is required (or use --from-stdin).",
                        }
                    )
                )
                sys.exit(1)

            content_type = args.type
            target_duration = args.duration
            trigger = args.trigger
            game_title = None

            # Get games from database
            if args.game_slug:
                games_data = get_game_by_slug(args.game_slug)
                if games_data:
                    game_title = games_data[0].get("title")
            else:
                games_data = get_games_from_db(content_type, args.year, args.month)

        if not games_data:
            logger.warning("No games found — proceeding with empty game data.")

        # ------------------------------------------------------------------
        # Run Writer Agent
        # ------------------------------------------------------------------
        writer = WriterAgent()
        result = writer.execute(
            content_type=content_type,
            games_data=games_data,
            target_duration=target_duration,
            game_title=game_title,
            trigger_source=trigger,
        )

        # Add success flag
        result["success"] = True

    except Exception as exc:
        logger.exception("Fatal error in generate_script")
        result = {"success": False, "error": str(exc)}

    # Print clean JSON to stdout for n8n
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
