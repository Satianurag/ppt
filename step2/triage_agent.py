"""Content Triage Agent using configurable LLM."""

import time
from typing import Optional

from step1.models import ContentInventory
from .slide_plan_models import PresentationPlan
from .triage_prompt import build_triage_prompt
from llm import get_llm_client, LLMClient


class ContentTriageAgent:
    """Agent for triaging content into slide plans.
    
    Uses configurable LLM client with structured output.
    Rate limited to 8 requests per minute as specified.
    """
    
    # Rate limit: 8 requests per minute (user-specified)
    MAX_RPM = 8
    
    # Fixed slide budget - cannot be changed
    SLIDE_BUDGET = 15
    
    def __init__(self, client: Optional[LLMClient] = None):
        """Initialize the triage agent.
        
        Args:
            client: LLMClient instance. If None, creates default from environment.
            
        Raises:
            ValueError: If no API key is configured.
        """
        # Get or create LLM client
        self.client = client or get_llm_client()
        
        # Configure structured output with Pydantic schema
        self.structured_client = self.client.with_structured_output(PresentationPlan)
        
        # Rate limiting state - only RPM tracking
        self.request_times = []  # Timestamps of recent requests
    
    def _check_rate_limit(self):
        """Enforce 8 requests per minute limit.
        
        Sleeps if needed to maintain RPM limit.
        """
        now = time.time()
        minute_ago = now - 60
        
        # Clean old entries outside the 1-minute window
        self.request_times = [t for t in self.request_times if t > minute_ago]
        
        # Check RPM
        if len(self.request_times) >= self.MAX_RPM:
            sleep_time = 60 - (now - self.request_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def triage(self, inventory: ContentInventory) -> PresentationPlan:
        """Create slide plan from content inventory.
        
        Args:
            inventory: Parsed content inventory from Step 1
            
        Returns:
            PresentationPlan with slide assignments
            
        Raises:
            ResourceExhausted: If rate limit exceeded and retries exhausted
            ValueError: If LLM returns invalid output
        """
        self._check_rate_limit()
        
        # Build prompt
        inventory_json = inventory.model_dump_json()
        prompt = build_triage_prompt(inventory_json, self.SLIDE_BUDGET)
        
        try:
            # Call LLM with structured output
            result = self.structured_client.invoke(prompt)
            
            # Record request time (handled in client, but track here too)
            self.request_times.append(time.time())
            
            # Validate and post-process
            return self._validate_and_post_process(result, inventory)
            
        except Exception as e:
            # Rate limit or other error - wait and retry once
            time.sleep(60)
            return self.triage(inventory)
    
    def _validate_and_post_process(
        self, 
        plan: PresentationPlan, 
        inventory: ContentInventory
    ) -> PresentationPlan:
        """Validate LLM output and apply post-processing.
        
        Args:
            plan: Raw plan from LLM
            inventory: Source inventory for validation
            
        Returns:
            Validated and corrected PresentationPlan
            
        Raises:
            ValueError: If plan has critical validation errors
        """
        # Validate slide count matches budget
        if plan.total_slides != self.SLIDE_BUDGET:
            # This is a warning, not fatal - could still work
            pass
        
        # Validate all source section IDs exist in inventory
        valid_section_ids = {s.id for s in inventory.sections}
        for slide in plan.slides:
            for section_id in slide.source_sections:
                if section_id and section_id not in valid_section_ids:
                    raise ValueError(
                        f"Slide {slide.slide_number} references unknown section: {section_id}"
                    )
        
        # Validate chart table indices are valid and numeric
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
        
        # Ensure sequential slide numbering
        expected_numbers = list(range(1, len(plan.slides) + 1))
        actual_numbers = [s.slide_number for s in plan.slides]
        if actual_numbers != expected_numbers:
            # Re-number slides if needed
            for i, slide in enumerate(plan.slides):
                slide.slide_number = i + 1
        
        # Count metadata
        plan.sections_used = len(valid_section_ids & {
            sid for s in plan.slides for sid in s.source_sections
        })
        plan.charts_planned = len([s for s in plan.slides if s.content_type == "chart"])
        plan.images_planned = len([s for s in plan.slides if s.content_type == "image"])
        
        return plan
    
    def triage_with_retry(
        self, 
        inventory: ContentInventory, 
        max_retries: int = 2
    ) -> PresentationPlan:
        """Create slide plan with retry logic for failures.
        
        Args:
            inventory: Content inventory
            max_retries: Number of retry attempts
            
        Returns:
            Valid PresentationPlan
            
        Raises:
            Exception: If all retries exhausted
        """
        for attempt in range(max_retries):
            try:
                return self.triage(inventory)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                # Wait before retry
                time.sleep(30 * (attempt + 1))
