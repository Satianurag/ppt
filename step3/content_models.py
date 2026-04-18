"""Pydantic models for extracted slide content."""

from enum import Enum
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict

from step2.slide_plan_models import SlideType, LayoutType, ChartType
from step1.models import ImageInfo


class ExtractedBullet(BaseModel):
    """A single bullet point extracted for a slide."""
    
    model_config = ConfigDict(strict=True)
    
    text: str = Field(
        max_length=60,
        description="Bullet text (max ~60 chars for 8 words)"
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


class ChartData(BaseModel):
    """Structured chart data ready for python-pptx ChartData conversion."""
    
    model_config = ConfigDict(strict=True)
    
    chart_type: ChartType = Field(description="Type of chart")
    title: str = Field(max_length=50, description="Chart title")
    source_table_index: int = Field(ge=0, description="Index of source table in markdown")
    
    # Data structure
    categories: List[str] = Field(
        description="X-axis category labels"
    )
    series: List[Dict[str, Any]] = Field(
        description="Series data: [{name: str, values: List[float]}]"
    )
    
    # Formatting hints for Step 4
    number_format: str = Field(
        default="General",
        description="Number format string (e.g., '$#,##0.0M', '0.0%')"
    )
    show_legend: bool = Field(default=True)
    show_data_labels: bool = Field(default=False)
    
    # Validation metadata
    is_valid: bool = Field(
        default=True,
        description="Whether data passed validation for chart type"
    )
    validation_errors: List[str] = Field(
        default_factory=list,
        description="Any validation warnings"
    )


class TableData(BaseModel):
    """Non-chart table data for table slides."""
    
    headers: List[str] = Field(description="Column headers")
    rows: List[List[str]] = Field(description="Table rows (as strings)")
    source_table_index: int = Field(ge=0)
    
    # Styling hints
    has_numeric_columns: List[int] = Field(
        default_factory=list,
        description="Which columns have numeric data (for right-align)"
    )
    zebra_stripes: bool = Field(default=True)
    bold_headers: bool = Field(default=True)


class SlideImage(BaseModel):
    """Image assigned to a slide with positioning info."""
    
    image_info: ImageInfo = Field(description="Image metadata from inventory")
    position: Literal["left", "right", "full", "background", "inline"] = Field(
        default="inline",
        description="Suggested position on slide"
    )
    caption: Optional[str] = Field(default=None, max_length=100)
    fit_score: float = Field(
        ge=0.0,
        le=1.0,
        description="How well this image fits the slide content (0-1)"
    )


class SlideContent(BaseModel):
    """Complete content for a single slide."""
    
    model_config = ConfigDict(strict=True)
    
    # Identity
    slide_number: int = Field(ge=1, le=15)
    slide_type: SlideType
    layout: LayoutType
    
    # Text content
    title: str = Field(max_length=50)
    subtitle: Optional[str] = Field(default=None, max_length=80)
    key_message: str = Field(max_length=100)
    
    # Bullet content
    bullets: List[ExtractedBullet] = Field(
        default_factory=list,
        max_length=6,
        description="Bullet points (max 6)"
    )
    
    # Visual content
    chart_data: Optional[ChartData] = Field(default=None)
    table_data: Optional[TableData] = Field(default=None)
    images: List[SlideImage] = Field(
        default_factory=list,
        max_length=2,
        description="Assigned images (max 2)"
    )
    
    # Source tracking
    source_sections: List[str] = Field(
        default_factory=list,
        description="Section IDs that contributed to this slide"
    )
    word_count: int = Field(
        default=0,
        ge=0,
        description="Total word count for this slide"
    )
    
    # Metadata
    extraction_method: Literal["llm", "rule_based", "hybrid"] = Field(
        default="rule_based",
        description="How content was extracted"
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in extraction quality"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Any extraction warnings"
    )


class ExtractionStats(BaseModel):
    """Statistics about the extraction process."""
    
    total_slides: int
    slides_with_llm: int
    slides_rule_based: int
    charts_extracted: int
    tables_extracted: int
    images_assigned: int
    images_unassigned: int
    total_word_count: int
    avg_words_per_slide: float
    llm_api_calls: int
    llm_tokens_used: int
    extraction_time_seconds: float
    warnings: List[str]


class PresentationContent(BaseModel):
    """Complete extracted content for a presentation."""
    
    model_config = ConfigDict(strict=True)
    
    # Metadata
    title: str
    total_slides: int = Field(ge=10, le=15)
    
    # Main content
    slides: List[SlideContent] = Field(
        description="Ordered list of slide content"
    )
    
    # Reference data for Step 4
    charts: List[ChartData] = Field(
        default_factory=list,
        description="All chart data for reference"
    )
    unassigned_images: List[ImageInfo] = Field(
        default_factory=list,
        description="Images not assigned to any slide"
    )
    
    # Stats
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
    
    def get_image_slides(self) -> List[SlideContent]:
        """Get all slides with images."""
        return [s for s in self.slides if len(s.images) > 0]
    
    def validate_completeness(self) -> List[str]:
        """Validate that all planned content was extracted."""
        issues = []
        
        for slide in self.slides:
            # Check content exists
            has_bullets = len(slide.bullets) > 0
            has_chart = slide.chart_data is not None
            has_table = slide.table_data is not None
            has_images = len(slide.images) > 0
            
            if not any([has_bullets, has_chart, has_table, has_images]):
                if slide.slide_type not in [SlideType.TITLE, SlideType.THANK_YOU]:
                    issues.append(f"Slide {slide.slide_number}: No content extracted")
            
            # Check word budget
            if slide.word_count > 60:  # Allow slight overrun from 50
                issues.append(f"Slide {slide.slide_number}: Word count {slide.word_count} exceeds budget")
            
            # Check bullet constraints
            if len(slide.bullets) > 6:
                issues.append(f"Slide {slide.slide_number}: Too many bullets ({len(slide.bullets)})")
        
        return issues
