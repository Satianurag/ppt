"""Pydantic models for extracted slide content.

Includes dual-format content (paragraph + bullet) reused from PPTAgent's
content_organizer.yaml pattern, and table font sizing heuristic from SlidesAI.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

from step2.slide_plan_models import SlideType, LayoutType, ChartType
from constants import (
    SLIDE_BUDGET, MAX_BULLETS_PER_SLIDE,
    MAX_TITLE_CHARS, MAX_SUBTITLE_CHARS, MAX_KEY_MESSAGE_CHARS, MAX_BULLET_CHARS,
    MAX_WORDS_PER_SLIDE,
)


class ExtractedBullet(BaseModel):
    """A single bullet point extracted for a slide."""

    model_config = ConfigDict(strict=True)

    text: str = Field(
        max_length=MAX_BULLET_CHARS,
        description="Bullet text"
    )
    priority: int = Field(
        ge=1,
        le=10,
        description="Importance score for ordering (10 = highest)"
    )
    source_section: str = Field(
        description="Section ID this bullet came from"
    )
    rationale: Optional[str] = Field(
        default=None,
        description="Why this bullet supports the key message"
    )


class KeyPoint(BaseModel):
    """Dual-format key point reused from PPTAgent content_organizer.yaml.

    Each key point is expressed in both paragraph form and bullet form,
    matching PPTAgent's content_organizer output structure.
    """

    point_name: str = Field(description="Name/topic of this key point")
    paragraph_form: str = Field(
        description="Paragraph form: 1-3 longer items, ~30 words each"
    )
    bullet_form: List[str] = Field(
        description="Bullet form: 3-8 shorter items, ~10 words each"
    )


class ChartData(BaseModel):
    """Structured chart data ready for python-pptx ChartData conversion."""

    model_config = ConfigDict(strict=True)

    chart_type: ChartType = Field(description="Type of chart")
    title: str = Field(max_length=MAX_TITLE_CHARS, description="Chart title")
    source_table_index: int = Field(ge=0, description="Index of source table in markdown")

    categories: List[str] = Field(description="X-axis category labels")
    series: List[Dict[str, Any]] = Field(
        description="Series data: [{name: str, values: List[float]}]"
    )

    number_format: str = Field(
        default="General",
        description="Number format string (e.g., '$#,##0.0M', '0.0%')"
    )
    show_legend: bool = Field(default=True)
    show_data_labels: bool = Field(default=False)

    is_valid: bool = Field(default=True, description="Whether data passed validation")
    validation_errors: List[str] = Field(default_factory=list)


class TableData(BaseModel):
    """Non-chart table data for table slides.

    Includes font sizing heuristic from SlidesAI (REUSE-7).
    """

    headers: List[str] = Field(description="Column headers")
    rows: List[List[str]] = Field(description="Table rows (as strings)")
    source_table_index: int = Field(ge=0)

    has_numeric_columns: List[int] = Field(
        default_factory=list,
        description="Which columns have numeric data (for right-align)"
    )
    zebra_stripes: bool = Field(default=True)
    bold_headers: bool = Field(default=True)

    # Font sizing heuristic (REUSE-7: SlidesAI pattern)
    recommended_font_size: int = Field(
        default=12,
        description="Recommended font size based on table dimensions"
    )

    def model_post_init(self, __context: Any) -> None:
        """Calculate recommended font size based on table dimensions."""
        num_rows = len(self.rows)
        num_cols = len(self.headers)
        max_cell_len = 0
        for row in self.rows:
            for cell in row:
                max_cell_len = max(max_cell_len, len(str(cell)))

        if num_rows <= 4 and num_cols <= 4:
            self.recommended_font_size = 14
        elif num_rows <= 8 and num_cols <= 6:
            self.recommended_font_size = 12
        elif num_rows <= 12 or num_cols <= 8:
            self.recommended_font_size = 10
        else:
            self.recommended_font_size = 8

        if max_cell_len > 30:
            self.recommended_font_size = min(self.recommended_font_size, 10)


class SlideContent(BaseModel):
    """Complete content for a single slide."""

    model_config = ConfigDict(strict=True)

    slide_number: int = Field(ge=1, le=SLIDE_BUDGET)
    slide_type: SlideType
    layout: LayoutType

    title: str = Field(max_length=MAX_TITLE_CHARS)
    subtitle: Optional[str] = Field(default=None, max_length=MAX_SUBTITLE_CHARS)
    key_message: str = Field(max_length=MAX_KEY_MESSAGE_CHARS)

    # Dual-format content (REUSE-2: PPTAgent content_organizer pattern)
    key_points: List[KeyPoint] = Field(
        default_factory=list,
        description="Dual-format key points (paragraph + bullet)"
    )
    bullets: List[ExtractedBullet] = Field(
        default_factory=list,
        max_length=MAX_BULLETS_PER_SLIDE,
    )

    chart_data: Optional[ChartData] = Field(default=None)
    table_data: Optional[TableData] = Field(default=None)

    source_sections: List[str] = Field(default_factory=list)
    word_count: int = Field(default=0, ge=0)

    extraction_method: Literal["llm", "hybrid"] = Field(
        default="llm",
        description="How content was extracted"
    )
    confidence_score: float = Field(
        default=1.0, ge=0.0, le=1.0,
    )
    warnings: List[str] = Field(default_factory=list)


class QualityScore(BaseModel):
    """Quality scoring per slide, reused from SlideForge's 6-component system."""

    topic_relevance: float = Field(ge=0.0, le=1.0, description="How well content matches key_message")
    content_uniqueness: float = Field(ge=0.0, le=1.0, description="No duplicate info across slides")
    source_coverage: float = Field(ge=0.0, le=1.0, description="How much source content was used")
    narrative_flow: float = Field(ge=0.0, le=1.0, description="Logical flow from previous slide")
    overall: float = Field(ge=0.0, le=1.0, description="Weighted average")


class ExtractionStats(BaseModel):
    """Statistics about the extraction process."""

    total_slides: int
    slides_with_llm: int
    charts_extracted: int
    tables_extracted: int
    total_word_count: int
    avg_words_per_slide: float
    llm_api_calls: int
    llm_tokens_used: int
    extraction_time_seconds: float
    quality_scores: Optional[List[QualityScore]] = Field(default=None)
    warnings: List[str] = Field(default_factory=list)


class PresentationContent(BaseModel):
    """Complete extracted content for a presentation."""

    model_config = ConfigDict(strict=True)

    title: str
    total_slides: int = Field(ge=10, le=SLIDE_BUDGET)

    slides: List[SlideContent] = Field(description="Ordered list of slide content")
    charts: List[ChartData] = Field(default_factory=list)

    stats: Optional[ExtractionStats] = Field(default=None)

    def get_slide(self, number: int) -> Optional[SlideContent]:
        """Get slide content by slide number."""
        for slide in self.slides:
            if slide.slide_number == number:
                return slide
        return None

    def get_chart_slides(self) -> List[SlideContent]:
        """Get all slides with chart data."""
        return [s for s in self.slides if s.chart_data is not None]

    def validate_completeness(self) -> List[str]:
        """Validate that all planned content was extracted."""
        issues = []

        for slide in self.slides:
            has_bullets = len(slide.bullets) > 0
            has_chart = slide.chart_data is not None
            has_table = slide.table_data is not None
            has_key_points = len(slide.key_points) > 0

            if not any([has_bullets, has_chart, has_table, has_key_points]):
                if slide.slide_type not in [SlideType.TITLE, SlideType.THANK_YOU]:
                    issues.append(f"Slide {slide.slide_number}: No content extracted")

            if slide.word_count > MAX_WORDS_PER_SLIDE:
                issues.append(
                    f"Slide {slide.slide_number}: Word count {slide.word_count} exceeds budget"
                )

            if len(slide.bullets) > MAX_BULLETS_PER_SLIDE:
                issues.append(
                    f"Slide {slide.slide_number}: Too many bullets ({len(slide.bullets)})"
                )

        return issues
