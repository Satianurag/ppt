"""Pydantic models for slide plan generation."""

from enum import Enum
from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field

from constants import SLIDE_BUDGET, MAX_BULLETS_PER_SLIDE, TARGET_WORDS_PER_SLIDE


class SlideType(str, Enum):
    """Classification of slide purpose."""
    TITLE = "title"
    AGENDA = "agenda"
    SUMMARY = "summary"
    CONTENT = "content"
    CHART = "chart"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    THANK_YOU = "thank_you"


class LayoutType(str, Enum):
    """Layout template selection."""
    COVER = "cover"
    DIVIDER = "divider"
    BLANK = "blank"
    TITLE_ONLY = "title_only"
    BULLET = "bullet"
    CHART_WITH_TEXT = "chart_with_text"
    TWO_COLUMN = "two_column"
    COMPARISON = "comparison"
    TIMELINE = "timeline"


class ChartType(str, Enum):
    """Chart type for data visualization."""
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    DONUT = "donut"
    HORIZONTAL_BAR = "horizontal_bar"
    GROUPED_BAR = "grouped_bar"


class ChartConfig(BaseModel):
    """Configuration for chart slides."""
    chart_type: ChartType = Field(description="Type of chart to generate")
    table_index: int = Field(ge=0, description="Index of source table in inventory")
    title: str = Field(max_length=50, description="Chart title")


class SlidePlan(BaseModel):
    """Plan for a single slide."""
    slide_number: int = Field(ge=1, le=SLIDE_BUDGET, description="Slide position in deck")
    type: SlideType = Field(description="Purpose/type of slide")
    layout: LayoutType = Field(description="Layout template to use")
    title: str = Field(max_length=50, description="Slide title")
    subtitle: Optional[str] = Field(default=None, max_length=80, description="Optional subtitle")
    source_sections: List[str] = Field(
        default_factory=list,
        description="Section IDs from ContentInventory that feed this slide"
    )
    key_message: str = Field(
        max_length=100,
        description="One sentence takeaway for this slide"
    )
    content_type: Literal["bullet", "chart", "table", "infographic", "mixed"] = Field(
        description="Primary content type"
    )
    chart_config: Optional[ChartConfig] = Field(
        default=None,
        description="Chart configuration if content_type is 'chart'"
    )
    bullet_points: List[str] = Field(
        default_factory=list,
        max_length=MAX_BULLETS_PER_SLIDE,
        description="Bullet items for slide"
    )
    max_bullets: int = Field(
        default=MAX_BULLETS_PER_SLIDE, ge=1, le=8,
        description="Maximum bullet capacity"
    )
    word_budget: int = Field(
        default=TARGET_WORDS_PER_SLIDE,
        description="Target word count for this slide"
    )


class PresentationPlan(BaseModel):
    """Complete plan for presentation generation."""
    slide_budget: int = Field(ge=10, le=SLIDE_BUDGET, description="Total slide target")
    total_slides: int = Field(ge=10, le=SLIDE_BUDGET, description="Actual slide count")
    title: str = Field(description="Presentation title")

    slides: List[SlidePlan] = Field(
        description="Ordered list of slide plans"
    )

    sections_used: int = Field(
        default=0,
        description="How many unique content sections are represented"
    )
    charts_planned: int = Field(
        default=0,
        description="How many chart slides are planned"
    )
    merge_reasoning: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of merged section IDs to explanation"
    )

    def get_slide_by_number(self, number: int) -> Optional[SlidePlan]:
        """Get slide plan by slide number."""
        for slide in self.slides:
            if slide.slide_number == number:
                return slide
        return None

    def get_chart_slides(self) -> List[SlidePlan]:
        """Return all slides with chart content."""
        return [s for s in self.slides if s.content_type == "chart"]

    def validate_section_coverage(self, inventory_section_ids: set) -> bool:
        """Check that all inventory sections are represented."""
        used_sections = set()
        for slide in self.slides:
            used_sections.update(slide.source_sections)
        return inventory_section_ids <= used_sections
