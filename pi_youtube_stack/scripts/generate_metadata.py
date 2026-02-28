#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Metadata
===================
Generates YouTube-optimized metadata (titles, description, tags, game info).
Called by n8n after script validation and approval.

Usage (n8n Execute Command):
    python3 scripts/generate_metadata.py --script-id <uuid>
    echo '{"script_id": "uuid"}' | python3 scripts/generate_metadata.py --from-stdin

Output (stdout JSON):
    {
        "success": true,
        "metadata_id": "uuid",
        "titles": [...],
        "description": "...",
        "tags": [...],
        "game_info_cards": [...],
        ...
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

from agents.metadata_agent import MetadataAgent
from database.connection import execute_query
from config.settings import settings

# ---------------------------------------------------------------------------
# Logging — stderr only
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("generate_metadata")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate YouTube metadata for a validated script."
    )
    parser.add_argument("--script-id", type=str, help="UUID of the validated script.")
    parser.add_argument(
        "--from-stdin", action="store_true", help="Read JSON input from stdin."
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
                        "error": "--script-id is required.",
                    }
                )
            )
            sys.exit(1)

        # ------------------------------------------------------------------
        # Fetch script from database
        # ------------------------------------------------------------------
        script_results = execute_query(
            "SELECT * FROM generated_scripts WHERE id = %s",
            (script_id,),
        )
        if not script_results:
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": f"Script not found: {script_id}",
                    }
                )
            )
            sys.exit(1)

        script_record = script_results[0]
        script_text = script_record["script_text"]
        content_type = script_record["content_type"]
        title = script_record.get("title", "")

        # Get associated games
        game_ids = script_record.get("game_ids", [])
        games_data = []
        if game_ids:
            placeholders = ", ".join(["%s"] * len(game_ids))
            games_data = (
                execute_query(
                    f"SELECT * FROM games WHERE id IN ({placeholders})",
                    tuple(str(gid) for gid in game_ids),
                )
                or []
            )

        # ------------------------------------------------------------------
        # Run Metadata Agent
        # ------------------------------------------------------------------
        agent = MetadataAgent()
        result = agent.execute(
            script_id=script_id,
            script_text=script_text,
            content_type=content_type,
            games_data=games_data,
            preliminary_title=title,
            pipeline_run_id=pipeline_run_id,
        )

        # ------------------------------------------------------------------
        # Save metadata to output file as well
        # ------------------------------------------------------------------
        output_dir = settings.paths.output_metadata
        output_file = output_dir / f"metadata_{script_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        logger.info("Metadata saved to: %s", output_file)

        result["success"] = True
        result["output_file"] = str(output_file)

    except Exception as exc:
        logger.exception("Fatal error in generate_metadata")
        result = {"success": False, "error": str(exc)}

    # Print clean JSON to stdout for n8n
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
