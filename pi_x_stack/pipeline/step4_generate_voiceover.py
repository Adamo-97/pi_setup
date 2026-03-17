#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 4: Generate Voiceover
===========================
Uses ElevenLabs to generate Arabic voiceover with word-level timestamps.
Saves .wav audio + timestamps for subtitle sync.

Usage:
    python -m pipeline.step4_generate_voiceover --script-id <UUID>
"""

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import execute_query
from services.elevenlabs_service import ElevenLabsService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pipeline.voiceover")


def main(script_id: str) -> dict:
    """
    Generate voiceover for an approved script.

    Args:
        script_id: UUID of the approved script

    Returns:
        dict with voiceover_id, file_path, duration, word_timestamps
    """
    logger.info("=== Step 4: Generate Voiceover (%s) ===", script_id[:8])

    # Fetch approved script
    rows = execute_query(
        "SELECT id, script_text, status FROM generated_scripts WHERE id = %s",
        (script_id,),
        fetch=True,
    )
    if not rows:
        raise ValueError(f"Script not found: {script_id}")

    script_text = rows[0][1]
    status = rows[0][2]

    if status not in ("validated", "draft"):
        logger.warning("Script status is '%s' (expected 'validated')", status)

    # Clean script for TTS (remove stage directions)
    import re

    tts_text = re.sub(r"\[.*?\]", "", script_text)
    tts_text = re.sub(r"\s+", " ", tts_text).strip()

    if not tts_text:
        raise ValueError("Script has no speakable text after cleaning")

    # Generate voiceover
    tts = ElevenLabsService()
    output_dir = Path("output/voiceovers")
    output_dir.mkdir(parents=True, exist_ok=True)

    vo_id = str(uuid.uuid4())
    output_path = str(output_dir / f"{vo_id[:8]}.wav")

    result = tts.generate_voiceover(
        text=tts_text,
        output_path=output_path,
    )

    if not result or not Path(result["file_path"]).is_file():
        raise RuntimeError("Voiceover generation failed — no audio file produced")

    # Store in database
    word_timestamps_json = json.dumps(
        result.get("word_timestamps", []),
        ensure_ascii=False,
    )

    execute_query(
        """
        INSERT INTO voiceovers
            (id, script_id, file_path, duration, word_timestamps, sample_rate)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            vo_id,
            script_id,
            result["file_path"],
            result["duration"],
            word_timestamps_json,
            result.get("sample_rate", 44100),
        ),
    )

    # Update script status
    execute_query(
        "UPDATE generated_scripts SET status = 'voiced', updated_at = NOW() WHERE id = %s",
        (script_id,),
    )

    output = {
        "voiceover_id": vo_id,
        "script_id": script_id,
        "file_path": result["file_path"],
        "duration": result["duration"],
        "word_timestamps": result.get("word_timestamps", []),
        "word_count": len(result.get("word_timestamps", [])),
    }

    logger.info(
        "Voiceover generated: %s (%.1fs, %d words) → %s",
        vo_id[:8],
        result["duration"],
        len(result.get("word_timestamps", [])),
        Path(result["file_path"]).name,
    )

    # Print for n8n
    print(json.dumps(output, ensure_ascii=False))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate voiceover")
    parser.add_argument("--script-id", required=True, help="Approved script UUID")
    args = parser.parse_args()
    main(script_id=args.script_id)
