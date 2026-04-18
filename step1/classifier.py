"""Section and content type classification logic."""

import re
from typing import Optional
from .models import SectionType, ContentType


# Keywords for section type detection
SECTION_KEYWORDS = {
    SectionType.SKIP: [
        "table of contents", "contents", "toc", "index",
        "references", "citations", "bibliography", "sources", "works cited",
        "appendix", "appendices", "supplementary", "supplemental"
    ],
    SectionType.SUMMARY: [
        "executive summary", "key findings", "summary", "overview", "highlights",
        "at a glance", "in brief"
    ],
    SectionType.INTRODUCTION: [
        "introduction", "background", "context", "about", "preface",
        "getting started", "what is", "overview"
    ],
    SectionType.METHODOLOGY: [
        "methodology", "methods", "approach", "framework", "process",
        "procedure", "experimental setup", "research design", "analysis method"
    ],
    SectionType.CONCLUSION: [
        "conclusion", "conclusions", "final thoughts", "wrap up",
        "recommendations", "key takeaways", "synthesis"
    ],
    SectionType.FUTURE: [
        "future", "outlook", "roadmap", "next steps", "coming soon",
        "forecast", "trends", "predictions", "what's next"
    ],
}

# Keywords for content type detection
COMPARISON_KEYWORDS = [
    "vs", "versus", "compared", "comparison", "benchmarking",
    "contrast", "difference", "similarities", "trade-off", "tradeoff"
]

PROCESS_KEYWORDS = [
    "process", "steps", "framework", "methodology", "approach",
    "roadmap", "workflow", "procedure", "guide", "how to", "implementation"
]

TIMELINE_KEYWORDS = [
    "timeline", "history", "evolution", "roadmap", "forecast",
    "schedule", "phases", "stages", "milestone", "chronology"
]

# Temporal patterns for chart detection
TEMPORAL_PATTERNS = [
    r'\b20\d{2}\b',  # Years 2000-2099
    r'\b19\d{2}\b',  # Years 1900-1999
    r'\b\d{4}-\d{2}-\d{2}\b',  # ISO dates
    r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b',  # Month names
    r'\bQ[1-4]\s+20\d{2}\b',  # Quarters like Q1 2024
    r'\b\d{4}\s+Q[1-4]\b',  # Years with quarters
]


def classify_section_type(heading: str) -> SectionType:
    """Classify section type based on heading text.
    
    Args:
        heading: The section heading text
        
    Returns:
        SectionType classification
    """
    heading_lower = heading.lower()
    
    # Check each section type's keywords (in priority order)
    for section_type in [SectionType.SKIP, SectionType.SUMMARY, SectionType.INTRODUCTION,
                         SectionType.METHODOLOGY, SectionType.CONCLUSION, SectionType.FUTURE]:
        for keyword in SECTION_KEYWORDS[section_type]:
            if keyword in heading_lower:
                return section_type
    
    # Default to CONTENT for unrecognized sections
    return SectionType.CONTENT


def classify_content_type(
    table_count: int,
    image_count: int,
    bullet_count: int,
    has_numeric_table: bool
) -> ContentType:
    """Classify primary content type for layout selection.
    
    Args:
        table_count: Number of tables in section
        image_count: Number of images in section
        bullet_count: Number of bullet items
        has_numeric_table: Whether any table has numeric data
        
    Returns:
        ContentType classification
    """
    # DATA: Has numeric tables suitable for charts
    if has_numeric_table:
        return ContentType.DATA
    
    # TABLE: Has non-numeric tables
    if table_count > 0:
        return ContentType.TABLE
    
    # VISUAL: Has images (but no numeric tables)
    if image_count > 0:
        return ContentType.VISUAL
    
    # LIST: Has many bullets
    if bullet_count >= 4:
        return ContentType.LIST
    
    # Default: TEXT
    return ContentType.TEXT


def detect_comparison(heading: str, content_text: str) -> bool:
    """Detect if section contains comparison content.
    
    Args:
        heading: Section heading
        content_text: Combined content text
        
    Returns:
        True if comparison keywords found
    """
    text = f"{heading} {content_text}".lower()
    return any(kw in text for kw in COMPARISON_KEYWORDS)


def detect_process(heading: str, content_text: str) -> bool:
    """Detect if section contains process/step content.
    
    Args:
        heading: Section heading
        content_text: Combined content text
        
    Returns:
        True if process keywords found
    """
    text = f"{heading} {content_text}".lower()
    return any(kw in text for kw in PROCESS_KEYWORDS)


def detect_timeline(heading: str, content_text: str) -> bool:
    """Detect if section contains temporal/chronological content.
    
    Args:
        heading: Section heading
        content_text: Combined content text
        
    Returns:
        True if timeline keywords or temporal patterns found
    """
    text = f"{heading} {content_text}".lower()
    
    # Check keywords
    if any(kw in text for kw in TIMELINE_KEYWORDS):
        return True
    
    # Check temporal patterns
    for pattern in TEMPORAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    return False


def is_temporal_column(values: list[str]) -> bool:
    """Check if a column contains temporal data (years, dates).
    
    Args:
        values: Column values as strings
        
    Returns:
        True if column appears to be temporal
    """
    if not values:
        return False
    
    # Sample first few non-empty values
    sample = [v for v in values[:10] if v.strip()]
    if not sample:
        return False
    
    # Check if majority match temporal patterns
    temporal_count = 0
    for val in sample:
        for pattern in TEMPORAL_PATTERNS:
            if re.search(pattern, val, re.IGNORECASE):
                temporal_count += 1
                break
    
    return temporal_count >= len(sample) * 0.5


def is_numeric_column(values: list[str]) -> bool:
    """Check if a column contains numeric data.
    
    Args:
        values: Column values as strings
        
    Returns:
        True if column appears to be numeric
    """
    if not values:
        return False
    
    # Sample first few non-empty values
    sample = [v for v in values[:10] if v.strip()]
    if not sample:
        return False
    
    # Count numeric values
    numeric_patterns = [
        r'^-?\d+$',  # Integers
        r'^-?\d+\.\d+$',  # Decimals
        r'^-?\$?[\d,]+\.?\d*[KMBT]?$',  # Currency
        r'^-?\d+%$',  # Percentages
    ]
    
    numeric_count = 0
    for val in sample:
        val_clean = val.strip().replace(',', '').replace('$', '').replace('%', '')
        if any(re.match(p, val_clean) for p in numeric_patterns):
            numeric_count += 1
    
    return numeric_count >= len(sample) * 0.5
