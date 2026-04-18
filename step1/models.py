"""Pydantic models for content inventory."""

from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class SectionType(str, Enum):
    """Classification of section role in presentation."""
    SKIP = "skip"  # TOC, References, Appendix
    SUMMARY = "summary"  # Executive Summary
    INTRODUCTION = "introduction"
    METHODOLOGY = "methodology"
    CONTENT = "content"  # Main body sections
    CONCLUSION = "conclusion"
    FUTURE = "future"  # Future outlook, roadmap


class ContentType(str, Enum):
    """Primary content type for layout selection."""
    DATA = "data"  # Numeric tables suitable for charts
    TABLE = "table"  # Non-numeric tables
    VISUAL = "visual"  # Has images
    LIST = "list"  # Bullet/numbered lists dominant
    TEXT = "text"  # Paragraph text dominant


class TableInfo(BaseModel):
    """Information about a table in the markdown."""
    
    index: int = Field(description="Sequential index of table in document")
    rows: int = Field(description="Number of data rows (excluding header)")
    cols: int = Field(description="Number of columns")
    has_numeric: bool = Field(description="Contains numeric data suitable for charts")
    has_temporal: bool = Field(description="Contains date/year columns")
    numeric_columns: List[int] = Field(default_factory=list, description="Indices of numeric columns")
    temporal_columns: List[int] = Field(default_factory=list, description="Indices of temporal columns")
    header_row: List[str] = Field(default_factory=list, description="Header row values")


class ImageInfo(BaseModel):
    """Information about an image in the markdown."""
    
    index: int = Field(description="Sequential index of image in document")
    image_type: Literal["base64", "url", "local"] = Field(description="Image source type")
    format: str = Field(description="Image format: png, jpg, svg, etc.")
    source: str = Field(description="Original source (base64 data or URL)")
    extracted_path: Optional[str] = Field(default=None, description="Path to extracted image file")
    alt_text: Optional[str] = Field(default=None, description="Alt text from markdown")


class Section(BaseModel):
    """A content section extracted from markdown."""
    
    id: str = Field(description="Unique identifier for the section")
    heading: str = Field(description="Section heading text")
    level: int = Field(ge=1, le=6, description="Heading level 1-6")
    section_type: SectionType = Field(description="Classification of section role")
    content_type: ContentType = Field(description="Primary content type for layout")
    
    # Content metrics
    word_count: int = Field(default=0, ge=0)
    bullet_count: int = Field(default=0, ge=0)
    paragraph_count: int = Field(default=0, ge=0)
    
    # Visual elements
    table_count: int = Field(default=0, ge=0)
    image_count: int = Field(default=0, ge=0)
    tables: List[TableInfo] = Field(default_factory=list)
    images: List[ImageInfo] = Field(default_factory=list)
    
    # Hierarchy
    parent_id: Optional[str] = Field(default=None, description="Parent section ID for nested structure")
    subsection_ids: List[str] = Field(default_factory=list, description="Child subsection IDs")
    
    # Content hints for layout selection
    has_comparison: bool = Field(default=False, description="Contains comparison keywords")
    has_process: bool = Field(default=False, description="Contains process/step keywords")
    has_timeline: bool = Field(default=False, description="Contains temporal/chronological content")


class OverflowStatus(BaseModel):
    """Indicates if content exceeds slide budget."""
    
    sections_over_budget: bool = Field(description="More sections than available slide slots")
    tables_over_budget: bool = Field(description="More chart candidates than available chart slots")
    charts_candidates: int = Field(ge=0, description="Number of tables suitable for chart conversion")
    recommended_chart_slots: int = Field(default=5, ge=0, le=11, description="Recommended max chart slides")


class ContentInventory(BaseModel):
    """Complete structured inventory of markdown content."""
    
    # Document metadata
    title: Optional[str] = Field(default=None, description="Document title from H1")
    subtitle: Optional[str] = Field(default=None, description="Document subtitle if present")
    total_words: int = Field(default=0, ge=0)
    total_sections: int = Field(default=0, ge=0)
    
    # Structural flags
    has_toc: bool = Field(default=False, description="Has Table of Contents section")
    has_executive_summary: bool = Field(default=False, description="Has Executive Summary")
    has_references: bool = Field(default=False, description="Has References/Citations section")
    has_appendix: bool = Field(default=False, description="Has Appendix section")
    
    # Content counts
    total_tables: int = Field(default=0, ge=0)
    total_images: int = Field(default=0, ge=0)
    total_bullets: int = Field(default=0, ge=0)
    
    # Main content
    sections: List[Section] = Field(default_factory=list, description="All content sections")
    
    # Analysis
    overflow: OverflowStatus = Field(description="Content overflow indicators")
    
    def get_content_sections(self) -> List[Section]:
        """Return sections that are not SKIP type (usable for slides)."""
        return [s for s in self.sections if s.section_type != SectionType.SKIP]
    
    def get_summary_section(self) -> Optional[Section]:
        """Return the executive summary section if present."""
        for s in self.sections:
            if s.section_type == SectionType.SUMMARY:
                return s
        return None
    
    def get_data_sections(self) -> List[Section]:
        """Return sections with chart-worthy data."""
        return [s for s in self.sections if s.content_type == ContentType.DATA]
