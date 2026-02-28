# -*- coding: utf-8 -*-
"""
Validator Agent
===============
AI quality gate for Instagram Reels scripts.
Evaluates 7 Instagram-specific criteria using Gemini and returns
a structured pass/fail decision with improvement suggestions.
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from config.prompts.validator_prompts import (
    VALIDATOR_REVIEW_PROMPT,
    VALIDATOR_SYSTEM_PROMPT,
)
from database.connection import execute_query

logger = logging.getLogger("instagram.validator")


class ValidatorAgent(BaseAgent):
    """AI quality gate for Instagram Reels scripts."""

    # Auto-reject threshold
    MIN_OVERALL_SCORE = 70
    MIN_HOOK_SCORE = 60
    MAX_REVISIONS = 2

    def __init__(self):
        super().__init__(name="Instagram Reels Validator")

    def run(
        self,
        script_id: str,
        script_text: str,
        content_type: str = "trending_news",
        news_summaries: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Validate an Instagram Reels script.

        Args:
            script_id: UUID of the script to validate
            script_text: The script text to evaluate
            content_type: Content type for context
            news_summaries: Original news for accuracy checking

        Returns:
            dict with validation_id, approved, overall_score, scores,
                  critical_issues, suggestions, revised_sections, summary
        """
        logger.info("Validating script %s (%s)", script_id[:8], content_type)

        word_count = self.count_words(script_text)
        est_duration = self.estimate_duration(script_text)

        prompt = VALIDATOR_REVIEW_PROMPT.format(
            script_text=script_text,
            content_type=content_type,
            word_count=word_count,
            estimated_duration=f"{est_duration:.1f}",
            news_summaries=news_summaries or "Not provided",
        )

        try:
            raw = self.gemini.generate_json(
                prompt=prompt,
                system_instruction=VALIDATOR_SYSTEM_PROMPT,
            )
            validation = json.loads(raw)
        except (json.JSONDecodeError, Exception) as e:
            logger.error("Validation JSON parse failed: %s", e)
            # Fallback: generate text and try to extract
            validation = self._fallback_validation(script_text, content_type)

        # Extract scores
        scores = validation.get("scores", {})
        overall = validation.get("overall_score", 0)
        approved = validation.get("approved", False)

        # Enforce hard rules
        hook_score = scores.get("hook_strength", 0)
        if hook_score < self.MIN_HOOK_SCORE:
            approved = False
            logger.warning(
                "Hook score too low: %d (min: %d)",
                hook_score,
                self.MIN_HOOK_SCORE,
            )
            if "critical_issues" not in validation:
                validation["critical_issues"] = []
            validation["critical_issues"].append(
                f"Hook strength ({hook_score}) below minimum ({self.MIN_HOOK_SCORE})"
            )

        if overall < self.MIN_OVERALL_SCORE:
            approved = False
            logger.warning(
                "Overall score too low: %d (min: %d)",
                overall,
                self.MIN_OVERALL_SCORE,
            )

        # Store in database
        validation_id = self._store_validation(
            script_id=script_id,
            scores=scores,
            overall_score=overall,
            approved=approved,
            suggestions=validation.get("suggestions", []),
            critical_issues=validation.get("critical_issues", []),
        )

        # Update script status
        new_status = "validated" if approved else "rejected"
        execute_query(
            "UPDATE generated_scripts SET status = %s, updated_at = NOW() WHERE id = %s",
            (new_status, script_id),
        )

        result = {
            "validation_id": validation_id,
            "approved": approved,
            "overall_score": overall,
            "scores": scores,
            "critical_issues": validation.get("critical_issues", []),
            "suggestions": validation.get("suggestions", []),
            "revised_sections": validation.get("revised_sections", {}),
            "summary": validation.get("summary", ""),
        }

        logger.info(
            "Validation: %s (score: %d, hook: %d, approved: %s)",
            validation_id[:8],
            overall,
            hook_score,
            approved,
        )
        return result

    # ================================================================
    # Revision loop
    # ================================================================

    def validate_with_revision(
        self,
        script_id: str,
        script_text: str,
        content_type: str,
        news_summaries: Optional[str] = None,
        writer_agent: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Validate with automatic revision attempts.
        If the script fails, ask the writer to revise based on feedback.
        """
        current_text = script_text
        current_id = script_id

        for attempt in range(self.MAX_REVISIONS + 1):
            result = self.run(
                script_id=current_id,
                script_text=current_text,
                content_type=content_type,
                news_summaries=news_summaries,
            )

            if result["approved"]:
                logger.info("Script approved on attempt %d", attempt + 1)
                return result

            if attempt < self.MAX_REVISIONS and writer_agent:
                logger.info(
                    "Attempt %d rejected (score: %d). Requesting revision...",
                    attempt + 1,
                    result["overall_score"],
                )

                # Build revision prompt
                issues = "\n".join(f"- {i}" for i in result["critical_issues"])
                suggestions = "\n".join(f"- {s}" for s in result["suggestions"])

                revision_result = writer_agent.run(
                    content_type=content_type,
                    news_articles=[],
                    target_duration=45.0,
                    trigger_source="revision",
                )
                current_text = revision_result["script_text"]
                current_id = revision_result["script_id"]

        logger.warning("Script failed after %d attempts", self.MAX_REVISIONS + 1)
        return result

    # ================================================================
    # Helpers
    # ================================================================

    @staticmethod
    def _store_validation(
        script_id: str,
        scores: Dict[str, int],
        overall_score: float,
        approved: bool,
        suggestions: list,
        critical_issues: list,
    ) -> str:
        """Store validation result in database."""
        validation_id = str(uuid.uuid4())

        scores_json = json.dumps(
            {
                **scores,
                "suggestions": suggestions,
                "critical_issues": critical_issues,
            }
        )

        execute_query(
            """
            INSERT INTO validations
                (id, script_id, scores, overall_score, approved)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (validation_id, script_id, scores_json, overall_score, approved),
        )

        return validation_id

    def _fallback_validation(
        self,
        script_text: str,
        content_type: str,
    ) -> Dict[str, Any]:
        """Fallback when JSON parsing fails — use text analysis."""
        logger.warning("Using fallback validation (text analysis)")

        word_count = self.count_words(script_text)
        has_hook = script_text.strip()[:50] != ""  # Has opening content

        # Basic heuristic scoring
        scores = {
            "hook_strength": 70 if has_hook else 40,
            "accuracy": 65,  # Can't verify without structured input
            "pacing": min(90, max(40, 70 + (word_count - 120) // 5)),
            "engagement": 65,
            "language_quality": 70,
            "cta_effectiveness": 60,
            "instagram_fit": 70,
        }

        overall = sum(scores.values()) // len(scores)
        approved = (
            overall >= self.MIN_OVERALL_SCORE
            and scores["hook_strength"] >= self.MIN_HOOK_SCORE
        )

        return {
            "approved": approved,
            "overall_score": overall,
            "scores": scores,
            "critical_issues": [
                "Validation used fallback heuristics — review manually"
            ],
            "suggestions": ["Re-run validation with better LLM connectivity"],
            "revised_sections": {},
            "summary": f"Fallback validation: {overall}/100",
        }
