#!/usr/bin/env python3
"""
Save pipeline step output to the shared state file.

Usage:
    python -m pipeline.save_state <run_id> <stdout_file>

Reads the last JSON line from stdout_file and merges it into
/tmp/pipeline_state_{run_id}.json
"""
import json
import sys


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m pipeline.save_state <run_id> <stdout_file>")
        sys.exit(1)

    run_id = sys.argv[1]
    stdout_file = sys.argv[2]
    state_file = f"/tmp/pipeline_state_{run_id}.json"

    # Read stdout and find last JSON line
    with open(stdout_file, "r") as f:
        lines = f.read().strip().split("\n")

    data = {}
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

    if not data:
        return

    # Merge into state file
    state = {}
    try:
        with open(state_file, "r") as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    state.update(data)
    with open(state_file, "w") as f:
        json.dump(state, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
