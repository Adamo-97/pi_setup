#!/usr/bin/env python3
"""
Gate helper — sends Mattermost gate approval messages to the correct channel.

Usage:
  cd /home/node/youtube_stack && python -m pipeline.gate_helper \
      --gate 0 --data-file /tmp/gate_0.json --run-id <UUID>
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

GATE_TITLES = {
    0: "خطة محتوى YouTube جديدة",
    1: "البيانات والأخبار جاهزة",
    2: "السكريبت جاهز",
    3: "التعليق الصوتي جاهز — استمع للملف",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gate", type=int, required=True)
    p.add_argument("--data-file", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--file-paths", nargs="*", default=[])
    args = p.parse_args()

    with open(args.data_file, encoding="utf-8") as f:
        gate_data = json.load(f)

    # Enrich gate data with pipeline state (topic, content_type, etc.)
    state_file = Path(f"/tmp/pipeline_state_{args.run_id}.json")
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            for key in ("proposed_topic", "proposed_content_type", "proposed_angle"):
                if key in state and key not in gate_data:
                    gate_data[key] = state[key]
        except Exception:
            pass

    from services.mattermost_service import MattermostService
    mm = MattermostService()

    file_paths = list(args.file_paths)
    for key in ("file_path", "output_path"):
        fp = gate_data.get(key, "")
        if fp and Path(fp).is_file() and fp not in file_paths:
            file_paths.append(fp)

    display_data = {k: v for k, v in gate_data.items() if k not in ("file_path", "output_path", "word_timestamps")}

    post_id = mm.send_gate_message(
        gate_number=args.gate,
        summary=GATE_TITLES.get(args.gate, f"Gate {args.gate}"),
        details=display_data,
        run_id=args.run_id,
        file_paths=file_paths,
    )
    result = {"status": "sent" if post_id else "failed", "gate": args.gate}
    if post_id:
        result["post_id"] = post_id
    print(json.dumps(result))


if __name__ == "__main__":
    main()
