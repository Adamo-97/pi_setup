#!/usr/bin/env python3
"""Read pipeline state and print shell-safe export lines."""
import json, sys

state = json.load(open(f"/tmp/pipeline_state_{sys.argv[1]}.json"))
for key in ("script_id", "voiceover_id", "run_id", "proposed_topic",
            "proposed_content_type", "proposed_angle", "content_type",
            "game_count", "estimated_duration_seconds"):
    if key in state:
        val = state[key]
        if isinstance(val, list): val = ",".join(str(v) for v in val)
        val = str(val).replace("'", "'\\''")
        print(f"{key.upper()}='{val}'")
