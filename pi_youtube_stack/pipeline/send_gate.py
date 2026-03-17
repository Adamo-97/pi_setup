#!/usr/bin/env python3
"""Send a gate approval message to Mattermost. Called by n8n."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

gate = int(sys.argv[1])
run_id = sys.argv[2]
summary = sys.argv[3] if len(sys.argv) > 3 else ""
details_json = sys.argv[4] if len(sys.argv) > 4 else "{}"

from services.mattermost_service import MattermostService
mm = MattermostService()
mm.send_gate_message(gate, summary, json.loads(details_json), run_id)
print(json.dumps({"ok": True, "gate": gate}))
