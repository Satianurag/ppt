"""Executor Agent — builds the 15-slide PPTX via step4.deck_builder."""

from __future__ import annotations

from pathlib import Path

from agents.base import BaseAgent
from agents.protocol import AgentRole, MessageType, PipelineState
from step4.deck_builder import build_deck


class ExecutorAgent(BaseAgent):
    """Render the final PPTX. Owns template preservation + scheduling."""

    def __init__(self) -> None:
        super().__init__(role=AgentRole.EXECUTOR, name="Executor")

    def process(self, state: PipelineState) -> PipelineState:
        content = state.presentation_content
        assert content is not None, "Executor: presentation_content is empty"

        output_path = state.output_path
        if not output_path:
            output_dir = Path(state.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            stem = Path(state.markdown_path).stem
            output_path = str(output_dir / f"{stem}.pptx")

        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.STATUS,
            {"phase": "rendering", "slides": len(content.slides),
             "template": state.template_path},
        )

        pptx_path = build_deck(
            content=content,
            template_path=state.template_path,
            output_path=output_path,
            presenter=state.presenter,
            presentation_date=state.presentation_date,
        )
        state.pptx_path = pptx_path
        state.render_issues = []

        self.record_turn(
            input_summary=f"Render {len(content.slides)} slides → {output_path}",
            output_summary=f"Saved to {pptx_path}",
        )
        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.RESPONSE,
            {"pptx_path": pptx_path},
        )
        return state
