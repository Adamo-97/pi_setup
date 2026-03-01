#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Voiceover
====================
Generates Arabic voiceover using ElevenLabs TTS with cloned voice.
Called by n8n AFTER the human approves the script via Mattermost (Step 1).

This script:
  1. Reads the approved script from the database
  2. Sends text to ElevenLabs API
  3. Saves the .wav file to output/voiceovers/
  4. Records the voiceover in the database
  5. Sends Mattermost notification with audio file for approval (Step 2)

Usage (n8n Execute Command):
    python3 scripts/generate_voiceover.py --script-id <uuid>
    echo '{"script_id": "uuid"}' | python3 scripts/generate_voiceover.py --from-stdin

Output (stdout JSON):
    {
        "success": true,
        "script_id": "uuid",
        "file_path": "/path/to/voiceover.wav",
        "duration_seconds": 600.5,
        "mattermost_sent": true
    }
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.elevenlabs_service import ElevenLabsService
from services.mattermost_service import MattermostService
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
logger = logging.getLogger("generate_voiceover")


def clean_script_for_tts(script_text: str) -> str:
    """
    Clean script text for TTS processing.
    Removes stage directions and formatting markers,
    keeps only spoken text.

    Args:
        script_text: Raw script text with markers.

    Returns:
        Cleaned text suitable for TTS.
    """
    import re

    # Remove stage direction markers but keep their semantic meaning
    # [وقفة] → add a period for natural pause
    cleaned = script_text.replace("[وقفة]", ".")
    # [تأكيد] and [هامس] → remove (TTS will be controlled by overall settings)
    cleaned = cleaned.replace("[تأكيد]", "")
    cleaned = cleaned.replace("[هامس]", "")

    # Remove markdown-style formatting
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)  # Bold
    cleaned = re.sub(r"#{1,3}\s*", "", cleaned)  # Headings
    cleaned = re.sub(r"---+", "", cleaned)  # Dividers

    # Remove multiple consecutive newlines (keep single)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # Remove leading/trailing whitespace per line
    lines = [line.strip() for line in cleaned.split("\n")]
    cleaned = "\n".join(lines)

    return cleaned.strip()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate voiceover for an approved script using ElevenLabs."
    )
    parser.add_argument("--script-id", type=str, help="UUID of the approved script.")
    parser.add_argument(
        "--from-stdin", action="store_true", help="Read JSON from stdin."
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
                        "error": "--script-id is required.",
                    }
                )
            )
            sys.exit(1)

        # ------------------------------------------------------------------
        # Fetch approved script from database
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
        title = script_record.get("title", "Untitled")
        content_type = script_record.get("content_type", "unknown")

        # Check if a validated/revised version exists
        # Use the latest validation's final_script if available
        validation_results = execute_query(
            """
            SELECT revised_sections FROM validations
            WHERE script_id = %s AND approved = TRUE
            ORDER BY created_at DESC LIMIT 1
            """,
            (script_id,),
        )
        # If there are revised sections, they were already applied by the
        # Validator Agent, so we use the script_text as-is.

        # ------------------------------------------------------------------
        # Clean script for TTS
        # ------------------------------------------------------------------
        tts_text = clean_script_for_tts(script_text)
        logger.info(
            "Script cleaned for TTS: %d → %d chars", len(script_text), len(tts_text)
        )

        # ------------------------------------------------------------------
        # Generate voiceover
        # ------------------------------------------------------------------
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = title.replace(" ", "_")[:30]
        filename = f"{content_type}_{safe_title}_{timestamp}.wav"
        output_path = str(settings.paths.output_voiceovers / filename)

        tts_service = ElevenLabsService()
        tts_result = tts_service.generate_voiceover(
            text=tts_text,
            output_path=output_path,
        )

        if not tts_result.get("success"):
            raise RuntimeError(
                f"ElevenLabs generation failed: {tts_result.get('error', 'Unknown error')}"
            )

        # ------------------------------------------------------------------
        # Store voiceover record in database
        # ------------------------------------------------------------------
        voiceover_id = str(uuid.uuid4())
        execute_query(
            """
            INSERT INTO voiceovers
                (id, script_id, file_path, file_size_bytes, duration_seconds, status)
            VALUES (%s, %s, %s, %s, %s, 'generated')
            """,
            (
                voiceover_id,
                script_id,
                tts_result["file_path"],
                tts_result["file_size_bytes"],
                tts_result["duration_seconds"],
            ),
            fetch=False,
        )

        # Update script status
        execute_query(
            "UPDATE generated_scripts SET status = 'audio_generated' WHERE id = %s",
            (script_id,),
            fetch=False,
        )

        logger.info(
            "Voiceover generated: %s (%.1f sec, %.1f KB)",
            filename,
            tts_result["duration_seconds"],
            tts_result["file_size_bytes"] / 1024,
        )

        # ------------------------------------------------------------------
        # Send to Mattermost for audio approval (Step 2)
        # ------------------------------------------------------------------
        mattermost_sent = False
        if not args.skip_notify:
            try:
                mm = MattermostService()
                mattermost_sent = mm.send_audio_for_approval(
                    script_id=script_id,
                    title=title,
                    audio_duration=tts_result["duration_seconds"],
                    audio_file_path=tts_result["file_path"],
                    pipeline_run_id=pipeline_run_id,
                )
            except Exception as exc:
                logger.error("Failed to send Mattermost audio notification: %s", exc)

        # ------------------------------------------------------------------
        # Output
        # ------------------------------------------------------------------
        result = {
            "success": True,
            "script_id": script_id,
            "voiceover_id": voiceover_id,
            "title": title,
            "file_path": tts_result["file_path"],
            "file_size_bytes": tts_result["file_size_bytes"],
            "duration_seconds": tts_result["duration_seconds"],
            "duration_minutes": round(tts_result["duration_seconds"] / 60, 1),
            "mattermost_sent": mattermost_sent,
            "pipeline_run_id": pipeline_run_id,
        }

    except Exception as exc:
        logger.exception("Fatal error in generate_voiceover")
        result = {"success": False, "error": str(exc)}

    # Print clean JSON to stdout for n8n
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
