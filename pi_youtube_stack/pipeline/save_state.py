#!/usr/bin/env python3
"""Merge step output JSON into /tmp/pipeline_state_{run_id}.json"""
import json, sys

def main():
    run_id, stdout_file = sys.argv[1], sys.argv[2]
    state_file = f"/tmp/pipeline_state_{run_id}.json"
    with open(stdout_file) as f:
        content = f.read().strip()
    data = {}
    # Try parsing the entire content as JSON first (handles pretty-printed output)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Fall back to finding a single-line JSON
        for line in reversed(content.split("\n")):
            line = line.strip()
            if line.startswith("{"):
                try: data = json.loads(line); break
                except json.JSONDecodeError: continue
    if not data: return
    state = {}
    try:
        with open(state_file) as f: state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): pass
    state.update(data)
    with open(state_file, "w") as f: json.dump(state, f, ensure_ascii=False)

if __name__ == "__main__": main()
