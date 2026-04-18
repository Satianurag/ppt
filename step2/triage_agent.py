"""Content Triage Agent using configurable LLM with retry-with-feedback.

Rate limiting is handled solely by LLMClient (no duplicate tracking).
Retry uses PPTAgent's feedback pattern via StructuredLLMClient.invoke_with_retry().
"""

from typing import Optional

from step1.models import ContentInventory
from .slide_plan_models import PresentationPlan
from .triage_prompt import build_triage_prompt
from llm import get_llm_client, LLMClient
from constants import SLIDE_BUDGET


class ContentTriageAgent:
    """Agent for triaging content into slide plans."""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self.client = client or get_llm_client()
        self.structured_client = self.client.with_structured_output(PresentationPlan)

    def triage(self, inventory: ContentInventory, max_retries: int = 3) -> PresentationPlan:
        """Create slide plan from content inventory.

        Uses retry-with-feedback (PPTAgent pattern) — on failure, sends
        error + traceback back to LLM for self-correction.
        """
        inventory_json = inventory.model_dump_json()
        prompt = build_triage_prompt(inventory_json, SLIDE_BUDGET)

        result = self.structured_client.invoke_with_retry(
            prompt, max_retries=max_retries
        )

        return self._validate_and_post_process(result, inventory)

    def _validate_and_post_process(
        self,
        plan: PresentationPlan,
        inventory: ContentInventory,
    ) -> PresentationPlan:
        """Validate LLM output and apply post-processing."""
        valid_section_ids = {s.id for s in inventory.sections}
        for slide in plan.slides:
            for section_id in slide.source_sections:
                if section_id and section_id not in valid_section_ids:
                    raise ValueError(
                        f"Slide {slide.slide_number} references unknown section: {section_id}"
                    )

        data_table_indices = {
            t.index for s in inventory.sections
            for t in s.tables if t.has_numeric
        }
        for slide in plan.slides:
            if slide.chart_config:
                if slide.chart_config.table_index not in data_table_indices:
                    raise ValueError(
                        f"Slide {slide.slide_number} references invalid chart table: "
                        f"{slide.chart_config.table_index}"
                    )

        expected_numbers = list(range(1, len(plan.slides) + 1))
        actual_numbers = [s.slide_number for s in plan.slides]
        if actual_numbers != expected_numbers:
            for i, slide in enumerate(plan.slides):
                slide.slide_number = i + 1

        plan.sections_used = len(valid_section_ids & {
            sid for s in plan.slides for sid in s.source_sections
        })
        plan.charts_planned = len([s for s in plan.slides if s.content_type == "chart"])

        return plan
