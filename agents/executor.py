"""Executor Agent — PPTX rendering and assembly.

Wraps Step 4 (build_presentation) as a dedicated agent role.
Inspired by PPT Master's Executor role (3 style variants)
and PPTAgent's content_organizer role.

Responsibilities:
  - Render PresentationContent into PPTX using python-pptx
  - Apply template theme, grid system, infographic-first approach
  - Handle per-slide error protection (VIZ-1)
  - Report render issues to Reviewer
"""

from pathlib import Path

from agents.base import BaseAgent
from agents.protocol import AgentRole, MessageType, PipelineState
from step4 import build_presentation


class ExecutorAgent(BaseAgent):
    """Renders the final PPTX file from extracted content.

    Uses the full rendering pipeline: template detection, grid system,
    infographic-first approach, auto font sizing, and chart rendering.
    """

    def __init__(self) -> None:
        super().__init__(role=AgentRole.EXECUTOR, name="Executor")

    def process(self, state: PipelineState) -> PipelineState:
        """Render PPTX from presentation content.

        Reads: state.presentation_content, state.template_path, state.output_dir
        Writes: state.pptx_path, state.render_issues
        """
        content = state.presentation_content
        template_path = state.template_path
        output_dir = Path(state.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        md_stem = Path(state.markdown_path).stem
        pptx_file = str(output_dir / f"{md_stem}.pptx")

        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.STATUS,
            {"phase": "rendering", "slides": len(content.slides), "template": template_path},
        )

        pptx_path, issues = build_presentation(content, template_path, pptx_file)
        state.pptx_path = pptx_path
        state.render_issues = issues

        self.record_turn(
            input_summary=f"Render {len(content.slides)} slides → {pptx_file}",
            output_summary=f"Saved to {pptx_path}, {len(issues)} validation issues",
        )

        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.RESPONSE,
            {"pptx_path": pptx_path, "issues": len(issues)},
        )

        return state
