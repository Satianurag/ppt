"""Strategist Agent — content triage and slide planning.

Wraps Step 1 (parsing) and Step 2 (triage) as a single agent role.
Inspired by PPT Master's Strategist role (references/strategist.md)
and PPTAgent's planner role (roles/planner.yaml).

Responsibilities:
  - Parse markdown into content inventory
  - Create slide plan via LLM (with retry-with-feedback)
  - Ensure all major sections are represented within slide budget
"""

from pathlib import Path

from agents.base import BaseAgent
from agents.protocol import AgentRole, MessageType, PipelineState
from step1 import MarkdownParser
from step2 import ContentTriageAgent
from llm import get_llm_client


class StrategistAgent(BaseAgent):
    """Plans presentation structure from markdown content.

    Combines parsing + LLM-based content triage into one agent.
    Uses retry-with-feedback if the plan doesn't meet quality criteria.
    """

    def __init__(self) -> None:
        super().__init__(role=AgentRole.STRATEGIST, name="Strategist")
        self.parser = MarkdownParser()

    def process(self, state: PipelineState) -> PipelineState:
        """Parse markdown and create slide plan.

        Reads: state.markdown_path
        Writes: state.inventory, state.slide_plan
        """
        md_path = Path(state.markdown_path)

        # Step 1: Parse markdown
        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.STATUS,
            {"phase": "parsing", "file": str(md_path)},
        )
        inventory = self.parser.parse_file(md_path)
        state.inventory = inventory

        self.record_turn(
            input_summary=f"Parsed {md_path.name}",
            output_summary=f"Title: {inventory.title}, Sections: {inventory.total_sections}, Tables: {inventory.total_tables}",
        )

        # Step 2: Content triage via LLM
        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.STATUS,
            {"phase": "triage", "sections": inventory.total_sections},
        )
        client = get_llm_client()
        agent = ContentTriageAgent(client=client)
        plan = agent.triage(inventory)
        state.slide_plan = plan

        self.record_turn(
            input_summary=f"Triage: {inventory.total_sections} sections → {plan.slide_budget} slide budget",
            output_summary=f"Planned {plan.total_slides} slides, {plan.charts_planned} charts",
        )

        self.send_message(
            state, AgentRole.COORDINATOR, MessageType.RESPONSE,
            {"slides_planned": plan.total_slides, "charts": plan.charts_planned},
        )

        return state
