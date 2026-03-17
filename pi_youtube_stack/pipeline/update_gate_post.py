#!/usr/bin/env python3
"""Update a Mattermost gate post after approval/rejection (remove buttons, add status)."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--post-id", required=True)
    p.add_argument("--gate", type=int, required=True)
    p.add_argument("--action", required=True, choices=["approve", "reject", "comment"])
    p.add_argument("--user", default="")
    args = p.parse_args()
    from services.mattermost_service import MattermostService
    mm = MattermostService()
    ok = mm.update_post_actions(post_id=args.post_id, action=args.action, gate_number=args.gate, user_name=args.user)
    print(json.dumps({"status": "updated" if ok else "failed", "post_id": args.post_id, "action": args.action}))

if __name__ == "__main__": main()
