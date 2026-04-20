"""Reviewer Agent — assertion-based quality check on the rendered PPTX.

Runs the five constraint checks (C1–C4) from ``step4.assertions`` and
combines them with a lightweight content-quality score. Any failed
constraint produces structured feedback consumed by the Designer retry.
"""

from __future__ import annotations

from agents.base import BaseAgent
from agents.protocol import AgentRole, MessageType, PipelineState
from step4.assertions import run_all


class ReviewerAgent(BaseAgent):
    PASS_THRESHOLD = 0.6

    def __init__(self, threshold: float = 0.6) -> None:
        super().__init__(role=AgentRole.REVIEWER, name="Reviewer")
        self.threshold = threshold

    def process(self, state: PipelineState) -> PipelineState:
        pptx_path = state.pptx_path
        assert pptx_path, "Reviewer: no pptx_path set by Executor"

        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.STATUS,
            {"phase": "review", "pptx": pptx_path},
        )

        results = run_all(pptx_path)
        all_issues: list[str] = []
        for r in results.values():
            all_issues.extend(r.issues)

        passed = all(r.passed for r in results.values())
        # C4 issues are non-fatal (spacing is softer than structure).
        fatal = [r for k, r in results.items() if k in ("C1", "C2", "C3") and not r.passed]

        base_score = 1.0 if passed else max(
            0.0, 1.0 - 0.15 * sum(len(r.issues) for r in results.values())
        )

        state.quality_score = base_score
        state.quality_report = _format_report(results)
        state.review_passed = len(fatal) == 0 and base_score >= self.threshold
        state.review_feedback = "; ".join(all_issues[:8])

        self.record_turn(
            input_summary=f"Review {pptx_path}",
            output_summary=(
                f"score={base_score:.2f} passed={state.review_passed} issues={len(all_issues)}"
            ),
        )
        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.RESPONSE,
            {"score": base_score, "issues": len(all_issues)},
        )
        return state


def _format_report(results: dict) -> str:
    lines: list[str] = []
    for name, r in results.items():
        status = "PASS" if r.passed else "FAIL"
        lines.append(f"[{name}] {status} ({len(r.issues)} issues)")
        for issue in r.issues[:5]:
            lines.append(f"    - {issue}")
    return "\n".join(lines)
