#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validate Script
=================
Runs the Validator Agent on a generated script.
Called by n8n after script generation.

This script:
  1. Reads the script from the database (by script_id)
  2. Invokes the Validator Agent for quality review
  3. If approved, triggers Mattermost notification for human approval
  4. Outputs structured JSON with validation results

Usage (n8n Execute Command):
    python3 scripts/validate_script.py --script-id <uuid>
    echo '{"script_id": "uuid", ...}' | python3 scripts/validate_script.py --from-stdin

Output (stdout JSON):
    {
        "success": true,
        "approved": true,
        "overall_score": 85,
        "summary": "...",
        "script_id": "uuid",
        "mattermost_sent": true
    }
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.validator_agent import ValidatorAgent
from database.connection import execute_query

# ---------------------------------------------------------------------------
# Logging — stderr only
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("validate_script")


def get_script_from_db(script_id: str) -> dict | None:
    """Retrieve a script from the database by ID."""
    result = execute_query(
        "SELECT * FROM generated_scripts WHERE id = %s",
        (script_id,),
    )
    return result[0] if result else None


def get_games_for_script(script_id: str) -> list[dict]:
    """Retrieve games associated with a script."""
    script = get_script_from_db(script_id)
    if not script or not script.get("game_ids"):
        return []

    game_ids = script["game_ids"]
    if not game_ids:
        return []

    # Build query for multiple game IDs
    placeholders = ", ".join(["%s"] * len(game_ids))
    query = f"SELECT * FROM games WHERE id IN ({placeholders})"
    return execute_query(query, tuple(str(gid) for gid in game_ids)) or []


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate a generated script using the Validator Agent."
    )
    parser.add_argument("--script-id", type=str, help="UUID of the script to validate.")
    parser.add_argument(
        "--from-stdin", action="store_true", help="Read JSON input from stdin."
    )
    parser.add_argument(
        "--skip-notify", action="store_true", help="Skip Mattermost notification."
    )

    args = parser.parse_args()

    try:
        # ------------------------------------------------------------------
        # Get input
        # ------------------------------------------------------------------
        if args.from_stdin:
            stdin_data = json.loads(sys.stdin.read())
            script_id = stdin_data.get("script_id", args.script_id)
            pipeline_run_id = stdin_data.get("pipeline_run_id")
        else:
            script_id = args.script_id
            pipeline_run_id = None

        if not script_id:
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": "--script-id is required (or provide via stdin JSON).",
                    }
                )
            )
            sys.exit(1)

        # ------------------------------------------------------------------
        # Fetch script from database
        # ------------------------------------------------------------------
        script_record = get_script_from_db(script_id)
        if not script_record:
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": f"Script not found: {script_id}",
                    }
                )
            )
            sys.exit(1)

        script_text = script_record["script_text"]
        content_type = script_record["content_type"]
        target_duration = script_record.get("target_duration", 10.0)
        title = script_record.get("title", "Untitled")

        # Get associated game data for accuracy checking
        games_data = get_games_for_script(script_id)

        # ------------------------------------------------------------------
        # Run Validator Agent
        # ------------------------------------------------------------------
        validator = ValidatorAgent()
        result = validator.execute(
            script_id=script_id,
            script_text=script_text,
            content_type=content_type,
            games_data=games_data,
            target_duration=target_duration,
            pipeline_run_id=pipeline_run_id,
        )

        # ------------------------------------------------------------------
        # Gate 2 approval is now handled by n8n workflow (6-Gate HITL).
        # This script only outputs JSON to stdout for n8n to parse.
        # ------------------------------------------------------------------

        # Add success flag
        result["success"] = True
        result["title"] = title

    except Exception as exc:
        logger.exception("Fatal error in validate_script")
        result = {"success": False, "error": str(exc)}

    # Print clean JSON to stdout for n8n
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
