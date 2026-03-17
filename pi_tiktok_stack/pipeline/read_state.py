#!/usr/bin/env python3
"""Read pipeline state IDs for shell variable export."""
import json, sys

run_id = sys.argv[1]
state = json.load(open(f"/tmp/pipeline_state_{run_id}.json"))
# Print shell-safe export lines
for key in ("script_id", "voiceover_id", "footage_id", "video_id", "run_id",
            "proposed_topic", "proposed_content_type", "proposed_angle",
            "visual_hook", "estimated_duration_seconds", "caption", "hashtags",
            "game_slugs"):
    if key in state:
        raw_val = state[key]
        if isinstance(raw_val, list):
            raw_val = ",".join(str(v) for v in raw_val)
        val = str(raw_val).replace("'", "'\\''")
        print(f"{key.upper()}='{val}'")
