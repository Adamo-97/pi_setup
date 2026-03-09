#!/usr/bin/env python3
"""Read pipeline state IDs for shell variable export."""
import json, sys

run_id = sys.argv[1]
state = json.load(open(f"/tmp/pipeline_state_{run_id}.json"))
# Print shell-safe export lines
for key in ("script_id", "voiceover_id", "footage_id", "video_id", "run_id",
            "proposed_topic", "caption", "hashtags"):
    if key in state:
        val = str(state[key]).replace("'", "'\\''")
        print(f"{key.upper()}='{val}'")
