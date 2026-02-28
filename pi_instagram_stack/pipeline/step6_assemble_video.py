#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 6: Assemble Video
======================
Combines footage + voiceover + subtitles into a final Instagram Reel.
Vertical 9:16 (1080x1920), with word-by-word Arabic subtitle overlay.

Usage:
    python -m pipeline.step6_assemble_video --script-id <UUID>
                                             --voiceover-id <UUID>
                                             --footage-id <UUID>
"""

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import execute_query
from services.subtitle_service import SubtitleService
from services.video_assembler import VideoAssembler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("pipeline.assemble_video")


def main(script_id: str, voiceover_id: str, footage_id: str) -> dict:
    """
    Assemble final Instagram Reel.

    Args:
        script_id: UUID of the script
        voiceover_id: UUID of the voiceover
        footage_id: UUID of the footage

    Returns:
        dict with video_id, output_path, duration, file_size
    """
    logger.info(
        "=== Step 6: Assemble Video (script=%s, vo=%s, footage=%s) ===",
        script_id[:8],
        voiceover_id[:8],
        footage_id[:8],
    )

    # Fetch voiceover info
    vo_rows = execute_query(
        "SELECT file_path, duration, word_timestamps FROM voiceovers WHERE id = %s",
        (voiceover_id,),
        fetch=True,
    )
    if not vo_rows:
        raise ValueError(f"Voiceover not found: {voiceover_id}")

    vo_path = vo_rows[0][0]
    vo_duration = vo_rows[0][1]
    word_timestamps_raw = vo_rows[0][2]

    # Parse word timestamps
    if isinstance(word_timestamps_raw, str):
        word_timestamps = json.loads(word_timestamps_raw)
    elif isinstance(word_timestamps_raw, list):
        word_timestamps = word_timestamps_raw
    else:
        word_timestamps = []

    # Fetch footage path
    ft_rows = execute_query(
        "SELECT file_path, game_title FROM video_footage WHERE id = %s",
        (footage_id,),
        fetch=True,
    )
    if not ft_rows:
        raise ValueError(f"Footage not found: {footage_id}")

    footage_path = ft_rows[0][0]
    game_title = ft_rows[0][1] or "instagram_reel"

    # Verify files exist
    if not Path(vo_path).is_file():
        raise FileNotFoundError(f"Voiceover file missing: {vo_path}")
    if not Path(footage_path).is_file():
        raise FileNotFoundError(f"Footage file missing: {footage_path}")

    # Step 1: Generate ASS subtitle file
    subtitle_service = SubtitleService()
    subtitle_dir = Path("output/subtitles")
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    ass_path = str(subtitle_dir / f"{script_id[:8]}.ass")

    if word_timestamps:
        subtitle_service.generate_ass_file(
            word_timestamps=word_timestamps,
            output_path=ass_path,
        )
        logger.info("ASS subtitles generated: %s", Path(ass_path).name)
    else:
        logger.warning("No word timestamps — video will have no subtitles")
        ass_path = ""

    # Step 2: Assemble video
    assembler = VideoAssembler()
    result = assembler.assemble(
        footage_path=footage_path,
        voiceover_path=vo_path,
        subtitle_ass_path=ass_path,
        target_duration=vo_duration,
        title=game_title,
    )

    # Step 3: Store in database
    video_id = str(uuid.uuid4())
    execute_query(
        """
        INSERT INTO rendered_videos
            (id, script_id, voiceover_id, footage_id, file_path, duration, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'rendered')
        """,
        (
            video_id,
            script_id,
            voiceover_id,
            footage_id,
            result["output_path"],
            result["duration"],
        ),
    )

    output = {
        "video_id": video_id,
        "script_id": script_id,
        "output_path": result["output_path"],
        "duration": result["duration"],
        "file_size_mb": result["file_size_mb"],
        "resolution": result["resolution"],
    }

    logger.info(
        "Video assembled: %s (%.1fs, %.1fMB) → %s",
        video_id[:8],
        result["duration"],
        result["file_size_mb"],
        Path(result["output_path"]).name,
    )

    print(json.dumps(output, ensure_ascii=False))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assemble Instagram Reel")
    parser.add_argument("--script-id", required=True, help="Script UUID")
    parser.add_argument("--voiceover-id", required=True, help="Voiceover UUID")
    parser.add_argument("--footage-id", required=True, help="Footage UUID")
    args = parser.parse_args()
    main(
        script_id=args.script_id,
        voiceover_id=args.voiceover_id,
        footage_id=args.footage_id,
    )
