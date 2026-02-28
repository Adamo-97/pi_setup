# -*- coding: utf-8 -*-
"""
Validator Agent
=================
Reviews generated Arabic YouTube scripts for quality, accuracy,
and YouTube optimization before human approval.

Evaluation criteria:
  - Factual accuracy (against reference game data)
  - Arabic language quality
  - Hook strength (first 15 seconds)
  - Retention potential (pattern interrupts, pacing)
  - Tone and style appropriateness
  - Structure and organization
  - Length vs. target duration
  - Call-to-action effectiveness

The Validator outputs a structured JSON review with scores,
issues, suggestions, and a pass/fail decision.
"""

import json
import logging
import uuid
from typing import Optional

from agents.base_agent import BaseAgent
from config.prompts.validator_prompts import (
    VALIDATOR_SYSTEM_PROMPT,
    VALIDATOR_REVIEW_PROMPT,
)
from config.settings import get_content_type
from database.connection import execute_query
from database.models import ValidationResult, ValidationScores

logger = logging.getLogger(__name__)


class ValidatorAgent(BaseAgent):
    """
    AI Validator Agent — reviews scripts for quality and YouTube optimization.

    Usage:
        agent = ValidatorAgent()
        result = agent.execute(
            script_id="uuid-here",
            script_text="السكريبت...",
            content_type="monthly_releases",
            games_data=[...],
            target_duration=10.0,
        )
    """

    # Minimum score to auto-approve — below this, the script is rejected
    APPROVAL_THRESHOLD = 70
    # Maximum number of revision attempts
    MAX_REVISIONS = 2

    @property
    def agent_name(self) -> str:
        return "Validator Agent"

    def execute(
        self,
        script_id: str,
        script_text: str,
        content_type: str,
        games_data: list[dict],
        target_duration: float = 10.0,
        pipeline_run_id: Optional[str] = None,
    ) -> dict:
        """
        Validate a generated script.

        Args:
            script_id: UUID of the script to validate.
            script_text: The full script text.
            content_type: Content type ID.
            games_data: Reference game data for accuracy checking.
            target_duration: Target video duration in minutes.
            pipeline_run_id: Optional pipeline run UUID.

        Returns:
            Dict with: validation_id, approved, overall_score, scores,
            critical_issues, suggestions, summary, revised_script (if any).
        """
        logger.info(
            "[%s] Starting validation: script_id=%s, type=%s",
            self.agent_name,
            script_id,
            content_type,
        )

        ct_config = get_content_type(content_type)

        # ------------------------------------------------------------------
        # Step 1: Gather context
        # ------------------------------------------------------------------
        rag_context = self.get_rag_context(
            f"مراجعة وتقييم سكريبت {ct_config.display_name}",
            content_type,
        )
        previous_feedback = self.get_previous_feedback(content_type)
        reference_data = self.format_games_data(games_data)

        # ------------------------------------------------------------------
        # Step 2: Build validation prompt
        # ------------------------------------------------------------------
        prompt = VALIDATOR_REVIEW_PROMPT.format(
            content_type_name=ct_config.display_name,
            target_duration=target_duration,
            script_text=script_text,
            reference_data=reference_data,
            rag_context=rag_context,
            previous_feedback=previous_feedback,
        )

        # ------------------------------------------------------------------
        # Step 3: Get Gemini validation (JSON response)
        # ------------------------------------------------------------------
        validation_data = self.gemini.generate_json(
            prompt=prompt,
            system_prompt=VALIDATOR_SYSTEM_PROMPT,
            temperature=0.2,  # Low temp for consistent evaluation
        )

        # ------------------------------------------------------------------
        # Step 4: Parse and validate the response
        # ------------------------------------------------------------------
        overall_score = validation_data.get("overall_score", 0)
        approved = validation_data.get("approved", False)

        # Override approval based on our threshold
        if overall_score < self.APPROVAL_THRESHOLD:
            approved = False
        elif overall_score >= self.APPROVAL_THRESHOLD and not approved:
            # If score is high enough but AI said no, we trust the AI's judgment
            logger.info(
                "[%s] Score is %d (>= %d) but AI rejected — keeping AI decision.",
                self.agent_name,
                overall_score,
                self.APPROVAL_THRESHOLD,
            )

        # Parse sub-scores
        raw_scores = validation_data.get("scores", {})
        scores = ValidationScores(
            accuracy=raw_scores.get("accuracy", 0),
            language_quality=raw_scores.get("language_quality", 0),
            hook_strength=raw_scores.get("hook_strength", 0),
            retention_potential=raw_scores.get("retention_potential", 0),
            tone_and_style=raw_scores.get("tone_and_style", 0),
            structure=raw_scores.get("structure", 0),
            length_appropriateness=raw_scores.get("length_appropriateness", 0),
            cta_effectiveness=raw_scores.get("cta_effectiveness", 0),
        )

        critical_issues = validation_data.get("critical_issues", [])
        suggestions = validation_data.get("suggestions", [])
        revised_sections = validation_data.get("revised_sections", {})
        summary = validation_data.get("summary", "")

        # ------------------------------------------------------------------
        # Step 5: Store validation in database
        # ------------------------------------------------------------------
        validation_id = str(uuid.uuid4())
        try:
            execute_query(
                """
                INSERT INTO validations
                    (id, script_id, approved, overall_score, scores,
                     critical_issues, suggestions, revised_sections, summary)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    validation_id,
                    script_id,
                    approved,
                    overall_score,
                    json.dumps(scores.model_dump(), ensure_ascii=False),
                    json.dumps(critical_issues, ensure_ascii=False),
                    json.dumps(suggestions, ensure_ascii=False),
                    json.dumps(revised_sections, ensure_ascii=False),
                    summary,
                ),
                fetch=False,
            )

            # Update script status based on validation result
            new_status = "validated" if approved else "rejected"
            execute_query(
                "UPDATE generated_scripts SET status = %s WHERE id = %s",
                (new_status, script_id),
                fetch=False,
            )

            logger.info(
                "[%s] Validation stored: id=%s, approved=%s, score=%d",
                self.agent_name,
                validation_id,
                approved,
                overall_score,
            )
        except Exception as exc:
            logger.error("[%s] Failed to store validation: %s", self.agent_name, exc)

        # ------------------------------------------------------------------
        # Step 6: Store validation in RAG for learning
        # ------------------------------------------------------------------
        rag_text = (
            f"تقييم سكريبت: {summary}\n"
            f"النتيجة: {overall_score}/100\n"
            f"المشاكل: {'; '.join(critical_issues)}\n"
            f"الاقتراحات: {'; '.join(suggestions)}"
        )
        self.store_in_rag(
            text=rag_text,
            source_type="validation",
            source_id=uuid.UUID(validation_id),
            summary=f"[validation] score={overall_score}, approved={approved}",
            metadata={
                "script_id": script_id,
                "content_type": content_type,
                "overall_score": overall_score,
                "approved": approved,
            },
        )

        # ------------------------------------------------------------------
        # Step 7: Apply revisions if needed and approved
        # ------------------------------------------------------------------
        final_script = script_text
        if approved and revised_sections:
            final_script = self._apply_revisions(script_text, revised_sections)
            logger.info(
                "[%s] Applied %d revised sections.",
                self.agent_name,
                len(revised_sections),
            )

        # ------------------------------------------------------------------
        # Output
        # ------------------------------------------------------------------
        result = {
            "validation_id": validation_id,
            "script_id": script_id,
            "approved": approved,
            "overall_score": overall_score,
            "scores": scores.model_dump(),
            "critical_issues": critical_issues,
            "suggestions": suggestions,
            "revised_sections": revised_sections,
            "summary": summary,
            "final_script": final_script,
            "pipeline_run_id": pipeline_run_id,
        }

        log_emoji = "✅" if approved else "❌"
        logger.info(
            "[%s] %s Validation complete: score=%d, approved=%s, issues=%d",
            self.agent_name,
            log_emoji,
            overall_score,
            approved,
            len(critical_issues),
        )

        return result

    @staticmethod
    def _apply_revisions(original_text: str, revised_sections: dict) -> str:
        """
        Apply revised sections to the original script.
        This is a best-effort replacement — if a section key matches
        a heading in the script, the content under it is replaced.

        Args:
            original_text: The original script text.
            revised_sections: Dict of section_name → revised_text.

        Returns:
            The script with revisions applied.
        """
        result = original_text
        for section_name, revised_text in revised_sections.items():
            # Try to find and replace the section
            # Look for the section header pattern
            if section_name in result:
                # Simple replacement of content after the section header
                # This is a heuristic — may need refinement based on actual output format
                logger.info("Applied revision for section: %s", section_name)
                result = result.replace(section_name, revised_text, 1)
        return result
