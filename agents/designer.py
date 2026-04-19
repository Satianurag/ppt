"""Designer Agent — content extraction and layout assignment.

Wraps Step 3 (content extraction) as a dedicated agent role.
Inspired by PPTAgent's layout_selector role and PPT Master's visual style system.

Responsibilities:
  - Extract slide-ready content from markdown per slide plan
  - Assign layout types and infographic types
  - Apply verbosity control rules
  - Ensure content density is appropriate per slide
  - Read Reviewer feedback and incorporate into LLM prompts on retry
"""

from pathlib import Path

from agents.base import BaseAgent
from agents.protocol import AgentRole, MessageType, PipelineState
from step3 import ContentExtractor
from llm import get_llm_client


class DesignerAgent(BaseAgent):
    """Extracts and shapes content for each slide.

    Takes the Strategist's slide plan and produces slide-ready content
    with layout assignments, bullet text, chart data, and key messages.

    On retry: reads FEEDBACK messages from Reviewer (via PipelineState)
    and passes them as additional context to the LLM, following PPTAgent's
    retry-with-feedback pattern (agent.py:127-158).
    """

    def __init__(self) -> None:
        super().__init__(role=AgentRole.DESIGNER, name="Designer")

    def process(self, state: PipelineState) -> PipelineState:
        """Extract content per slide plan.

        Reads: state.slide_plan, state.inventory, state.markdown_path
        Writes: state.presentation_content

        On retry: checks state.get_messages_for(DESIGNER) for FEEDBACK,
        and passes feedback context to the extractor for improved output.
        """
        plan = state.slide_plan
        inventory = state.inventory
        md_text = Path(state.markdown_path).read_text(encoding="utf-8")

        # Collect feedback from Reviewer (PPTAgent retry pattern)
        feedback_context = self._collect_feedback(state)

        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.STATUS,
            {"phase": "extraction", "slides": plan.total_slides,
             "is_retry": bool(feedback_context)},
        )

        client = get_llm_client()
        extractor = ContentExtractor(client=client)
        presentation = extractor.extract(
            plan, md_text, inventory, feedback_context=feedback_context,
        )
        state.presentation_content = presentation

        stats_summary = ""
        if presentation.stats:
            stats_summary = (
                f"words={presentation.stats.total_word_count}, "
                f"llm_calls={presentation.stats.llm_api_calls}"
            )

        self.record_turn(
            input_summary=f"Extract content for {plan.total_slides} slides"
                          + (f" (retry with feedback)" if feedback_context else ""),
            output_summary=f"Extracted {len(presentation.slides)} slides, {stats_summary}",
        )

        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.RESPONSE,
            {
                "slides_extracted": len(presentation.slides),
                "charts": len(presentation.charts) if presentation.charts else 0,
            },
        )

        return state

    def _collect_feedback(self, state: PipelineState) -> str:
        """Collect all FEEDBACK messages sent to Designer by Reviewer.

        Returns a consolidated feedback string for the LLM prompt,
        or empty string if no feedback (first run).
        """
        messages = state.get_messages_for(AgentRole.DESIGNER)
        feedback_parts = []
        for msg in messages:
            if msg.msg_type == MessageType.FEEDBACK and isinstance(msg.payload, dict):
                fb_text = msg.payload.get("feedback", "")
                if fb_text:
                    feedback_parts.append(fb_text)
        return " | ".join(feedback_parts)
