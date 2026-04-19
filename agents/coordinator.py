"""Coordinator Agent — orchestrates the multi-agent pipeline.

Manages the full pipeline: Strategist → Designer → Executor → Reviewer.
Implements retry-with-feedback loop (PPTAgent pattern) when Reviewer fails.

This is the main entry point for the multi-agent system.
"""

from pathlib import Path

from agents.base import BaseAgent
from agents.protocol import AgentRole, MessageType, PipelineState
from agents.strategist import StrategistAgent
from agents.designer import DesignerAgent
from agents.executor import ExecutorAgent
from agents.reviewer import ReviewerAgent


class CoordinatorAgent(BaseAgent):
    """Orchestrates the 4-agent pipeline with retry logic.

    Pipeline: Strategist → Designer → Executor → Reviewer
    If Reviewer fails, sends feedback to Designer for retry (up to max_retries).

    Inspired by PPTAgent's multi-role architecture and PPT Master's
    Strategist → Image_Generator → Executor pipeline.
    """

    def __init__(self, max_retries: int = 2, quality_threshold: float = 0.6) -> None:
        super().__init__(role=AgentRole.COORDINATOR, name="Coordinator")
        self.max_retries = max_retries
        self.strategist = StrategistAgent()
        self.designer = DesignerAgent()
        self.executor = ExecutorAgent()
        self.reviewer = ReviewerAgent(threshold=quality_threshold)

    def process(self, state: PipelineState) -> PipelineState:
        """Run the full multi-agent pipeline.

        Args:
            state: PipelineState with markdown_path, template_path, output_dir set.

        Returns:
            Completed PipelineState with pptx_path and quality report.
        """
        state.max_retries = self.max_retries

        print("\n" + "=" * 60)
        print("MULTI-AGENT PIPELINE")
        print("=" * 60)

        # Phase 1: Strategist — parse & plan
        print(f"\n[Agent: {self.strategist.name}] Parsing and planning...")
        state = self.strategist.process(state)
        print(f"  Planned {state.slide_plan.total_slides} slides, "
              f"{state.slide_plan.charts_planned} charts")

        # Phase 2: Designer — extract content
        print(f"\n[Agent: {self.designer.name}] Extracting content...")
        state = self.designer.process(state)
        print(f"  Extracted {len(state.presentation_content.slides)} slides")

        # Phase 3: Executor — render PPTX
        print(f"\n[Agent: {self.executor.name}] Rendering PPTX...")
        state = self.executor.process(state)
        print(f"  Saved to {state.pptx_path}")
        if state.render_issues:
            print(f"  Validation issues: {len(state.render_issues)}")

        # Phase 4: Reviewer — quality check
        print(f"\n[Agent: {self.reviewer.name}] Reviewing quality...")
        state = self.reviewer.process(state)
        print(f"  Score: {state.quality_score:.2f}")
        print(f"  Passed: {state.review_passed}")

        # Retry loop if review fails
        retry = 0
        while not state.review_passed and retry < self.max_retries:
            retry += 1
            state.total_retries = retry
            print(f"\n[Retry {retry}/{self.max_retries}] "
                  f"Feedback: {state.review_feedback}")

            # Re-run Designer with feedback context
            print(f"  [Agent: {self.designer.name}] Re-extracting with feedback...")
            self.send_message(
                state, AgentRole.DESIGNER, MessageType.FEEDBACK,
                {"feedback": state.review_feedback, "retry": retry},
            )
            state = self.designer.process(state)

            # Re-run Executor
            print(f"  [Agent: {self.executor.name}] Re-rendering...")
            state = self.executor.process(state)

            # Re-run Reviewer
            print(f"  [Agent: {self.reviewer.name}] Re-reviewing...")
            state = self.reviewer.process(state)
            print(f"  Score: {state.quality_score:.2f}, Passed: {state.review_passed}")

        # Final summary
        print("\n" + "=" * 60)
        print("PIPELINE COMPLETE")
        print("=" * 60)
        print(f"  PPTX: {state.pptx_path}")
        print(f"  Quality: {state.quality_score:.2f}")
        print(f"  Retries: {state.total_retries}")
        print(f"  Review: {'PASSED' if state.review_passed else 'NEEDS IMPROVEMENT'}")

        self.record_turn(
            input_summary=f"Pipeline: {state.markdown_path} → {state.template_path}",
            output_summary=f"Score: {state.quality_score:.2f}, Retries: {state.total_retries}",
            success=state.review_passed,
        )

        return state

    def run(
        self,
        markdown_path: str,
        template_path: str,
        output_dir: str = "./output",
    ) -> PipelineState:
        """Convenience method to run the full pipeline.

        Args:
            markdown_path: Path to input markdown file.
            template_path: Path to Slide Master PPTX template.
            output_dir: Directory for output files.

        Returns:
            Completed PipelineState.
        """
        state = PipelineState(
            markdown_path=markdown_path,
            template_path=template_path,
            output_dir=output_dir,
        )
        return self.process(state)

    def get_pipeline_report(self, state: PipelineState) -> str:
        """Generate a human-readable report of the pipeline execution."""
        lines = [
            "# Multi-Agent Pipeline Report",
            "",
            f"**Input**: {state.markdown_path}",
            f"**Template**: {state.template_path}",
            f"**Output**: {state.pptx_path}",
            "",
            "## Agent Execution History",
            "",
        ]

        all_agents = [self.strategist, self.designer, self.executor, self.reviewer]
        for agent in all_agents:
            lines.append(f"### {agent.name} ({agent.role.value})")
            for turn in agent.history:
                status = "OK" if turn.success else "RETRY"
                lines.append(f"  - [{status}] {turn.input_summary} → {turn.output_summary}")
            lines.append("")

        lines.extend([
            "## Quality Report",
            "",
            f"Score: {state.quality_score:.2f}",
            f"Passed: {state.review_passed}",
            f"Retries: {state.total_retries}",
            "",
            state.quality_report,
        ])

        lines.extend([
            "",
            "## Message Log",
            "",
        ])
        for msg in state.messages:
            lines.append(
                f"  [{msg.sender.value} → {msg.receiver.value}] "
                f"{msg.msg_type.value}: {msg.payload}"
            )

        return "\n".join(lines)
