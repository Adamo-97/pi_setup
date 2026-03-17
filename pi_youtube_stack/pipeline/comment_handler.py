#!/usr/bin/env python3
"""
Comment Handler — YouTube pipeline.
Stores comment in feedback_log + RAG. Gate 2 comments trigger script rewrite.
"""
import argparse, json, logging, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import execute_query
from database.rag_manager import RAGManager
from services.embedding_service import embed_text

logger = logging.getLogger("youtube.comment_handler")

GATE_NAMES = {0: "plan", 1: "news", 2: "script", 3: "voiceover"}


def main(run_id: str, gate: int, comment: str) -> dict:
    gate_name = GATE_NAMES.get(gate, f"gate_{gate}")

    # Load pipeline state
    script_id = None
    state = {}
    try:
        sf = Path(f"/tmp/pipeline_state_{run_id}.json")
        if sf.is_file():
            state = json.loads(sf.read_text())
            script_id = state.get("script_id")
    except Exception:
        pass

    # Store in feedback_log
    try:
        execute_query(
            "INSERT INTO feedback_log (script_id, feedback_type, feedback_text, source, applied) VALUES (%s, %s, %s, 'mattermost', FALSE)",
            (script_id, "comment", comment), fetch=False,
        )
    except Exception as e:
        logger.warning("feedback_log insert failed: %s", e)

    # Embed in RAG
    try:
        enriched = f"[comment] [gate:{gate_name}] [run:{run_id[:8]}] {comment}"
        embedding = embed_text(enriched[:500])
        RAGManager().store_embedding(
            source_type="feedback", content_text=enriched, embedding=embedding,
            metadata={"run_id": run_id, "gate": gate, "gate_name": gate_name, "script_id": script_id},
            content_summary=f"[comment] {comment[:100]}",
        )
    except Exception as e:
        logger.warning("RAG embed failed: %s", e)

    result = {"status": "stored", "run_id": run_id, "gate": gate, "gate_name": gate_name,
              "comment_length": len(comment), "script_id": script_id, "rewrite_triggered": False}

    # Gate 2: trigger rewrite loop
    if gate == 2 and script_id:
        try:
            from processors.writer import Writer
            from processors.validator import Validator

            rows = execute_query(
                "SELECT script_text, content_type FROM generated_scripts WHERE id = %s",
                (script_id,), fetch=True,
            )
            if rows:
                row = rows[0]
                # Budget check
                from services.redis_rate_limiter import RedisRateLimiter
                from services.budget_reader import BudgetReader
                limiter = RedisRateLimiter(platform='youtube')
                budget = BudgetReader(platform='youtube')
                est = budget.get_api_cost('gemini_script') + (Validator.MAX_REVISIONS + 1) * (budget.get_api_cost('gemini_validate') + budget.get_api_cost('gemini_script'))
                if not limiter.check_budget('gemini_script', est):
                    from services.mattermost_service import MattermostService
                    MattermostService().send_status("تعليقك محفوظ ✅ لكن إعادة الكتابة متوقفة — الميزانية غير كافية", level='warning', channel_key='script')
                    result['rewrite_skipped'] = 'budget_insufficient'
                else:
                    # Fetch games_data from state
                    games_data = state.get("games_data", [])
                    revision_feedback = (
                        f"تعليق بشري على السكريبت:\n{comment}\n\n"
                        f"## النص الحالي:\n{row['script_text']}\n\n"
                        f"أعد كتابة السكريبت الكامل من الصفر مع تطبيق الملاحظات أعلاه."
                    )
                    writer = Writer()
                    w_result = writer.execute(
                        content_type=row["content_type"], games_data=games_data,
                        trigger_source="comment", pipeline_run_id=run_id,
                    )
                    validator = Validator()
                    v_result = validator.execute(
                        script_id=w_result["script_id"], script_text=w_result["script_text"],
                        content_type=row["content_type"], games_data=games_data,
                        pipeline_run_id=run_id,
                    )
                    result["rewrite_triggered"] = True
                    result["new_script_id"] = w_result["script_id"]
                    result.update({k: v_result.get(k) for k in ("approved", "overall_score", "script_text", "generation_failed") if k in v_result})
                    # Update state
                    try:
                        state["script_id"] = w_result["script_id"]
                        Path(f"/tmp/pipeline_state_{run_id}.json").write_text(json.dumps(state, ensure_ascii=False))
                    except Exception:
                        pass
                    if v_result.get("generation_failed"):
                        from services.mattermost_service import MattermostService
                        MattermostService().send_generation_failed(run_id=run_id, gate_number=2, last_score=v_result.get("overall_score", 0), attempts=Validator.MAX_REVISIONS + 1)
                        result["generation_failed"] = True
        except Exception as e:
            logger.error("Comment rewrite failed: %s", e)
            result["rewrite_error"] = str(e)

    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--gate", type=int, required=True)
    p.add_argument("--comment", required=True)
    args = p.parse_args()
    main(run_id=args.run_id, gate=args.gate, comment=args.comment)
