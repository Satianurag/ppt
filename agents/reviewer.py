"""Reviewer Agent — quality assurance using SlideForge scoring.

Wraps the quality scoring and validation systems as a dedicated agent role.
Inspired by SlideForge's 6-component reward system and PPTAgent's retry pattern.

Responsibilities:
  - Score the rendered presentation using SlideForge 6-component system
  - Validate against Common Mistakes rules (16+ checks)
  - Generate quality report
  - Decide pass/fail and provide feedback for retry
"""

from agents.base import BaseAgent
from agents.protocol import AgentRole, MessageType, PipelineState
from step3.content_optimizer import ContentOptimizer
from step4.validator import validate_presentation

from pptx import Presentation


class ReviewerAgent(BaseAgent):
    """Reviews presentation quality and decides pass/fail.

    Uses SlideForge's 6-component scoring system:
      structural_rules (1.0), content_quality (2.0), render_quality (2.0),
      brief_reconstruction (2.0), source_coverage (1.5), narrative_flow (1.0)

    Combined with 16-rule Common Mistakes validator.
    """

    PASS_THRESHOLD = 0.6

    def __init__(self, threshold: float = 0.6) -> None:
        super().__init__(role=AgentRole.REVIEWER, name="Reviewer")
        self.threshold = threshold

    def process(self, state: PipelineState) -> PipelineState:
        """Review the rendered PPTX for quality.

        Reads: state.pptx_path, state.presentation_content, state.render_issues
        Writes: state.quality_score, state.quality_report, state.review_passed, state.review_feedback
        """
        content = state.presentation_content
        pptx_path = state.pptx_path

        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.STATUS,
            {"phase": "review", "pptx": pptx_path},
        )

        # 1. Validate rendered PPTX with Common Mistakes rules
        if pptx_path:
            prs = Presentation(pptx_path)
            validation_issues = validate_presentation(prs)
        else:
            validation_issues = ["No PPTX file to validate"]

        # 2. Score content quality using SlideForge system
        optimizer = ContentOptimizer()
        quality_score = optimizer._score_slides(content.slides)
        quality_report = optimizer.generate_quality_report(content.slides)

        # 3. Compute aggregate score
        overall = quality_score.overall if quality_score else 0.0
        state.quality_score = overall
        state.quality_report = quality_report

        # 4. Determine pass/fail
        critical_issues = [i for i in validation_issues if "overflow" in i.lower() or "margin" in i.lower()]
        passed = overall >= self.threshold and len(critical_issues) == 0
        state.review_passed = passed

        # 5. Generate feedback
        feedback_parts = []
        if not passed:
            if overall < self.threshold:
                feedback_parts.append(
                    f"Quality score {overall:.2f} below threshold {self.threshold}"
                )
            if critical_issues:
                feedback_parts.append(
                    f"Critical issues: {'; '.join(critical_issues[:3])}"
                )
            if validation_issues:
                feedback_parts.append(
                    f"Validation: {len(validation_issues)} issues total"
                )

        state.review_feedback = " | ".join(feedback_parts) if feedback_parts else "PASSED"

        self.record_turn(
            input_summary=f"Review {pptx_path}",
            output_summary=f"Score: {overall:.2f}, Passed: {passed}, Issues: {len(validation_issues)}",
            success=passed,
        )

        msg_type = MessageType.RESPONSE if passed else MessageType.FEEDBACK
        self.send_message(
            state, AgentRole.COORDINATOR, msg_type,
            {
                "score": overall,
                "passed": passed,
                "validation_issues": len(validation_issues),
                "critical_issues": len(critical_issues),
                "feedback": state.review_feedback,
            },
        )

        return state
