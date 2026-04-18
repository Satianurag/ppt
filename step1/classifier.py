"""Section and content type classification logic.

Includes deterministic chart type selection reused from PPT Master's quickLookup
pattern (hackathon_research_v3.md:403-418) and hackathon_final_analysis1.md:326-344.
"""

import re
from typing import List, Optional
from .models import SectionType, ContentType, TableInfo


# Keywords for section type detection
# Complete list per gap_analysis1.md:156 — includes footnotes, glossary,
# acknowledgments, about the author, methodology note, disclaimer, endnotes
SECTION_KEYWORDS = {
    SectionType.SKIP: [
        "table of contents", "contents", "toc", "index",
        "references", "citations", "bibliography", "sources", "works cited",
        "appendix", "appendices", "supplementary", "supplemental",
        "footnotes", "endnotes", "glossary",
        "acknowledgments", "acknowledgements",
        "about the author", "about the authors",
        "methodology note", "disclaimer",
    ],
    SectionType.SUMMARY: [
        "executive summary", "key findings", "summary", "highlights",
        "at a glance", "in brief",
    ],
    SectionType.INTRODUCTION: [
        "introduction", "background", "context", "about", "preface",
        "getting started", "what is", "overview",
    ],
    SectionType.METHODOLOGY: [
        "methodology", "methods", "approach", "framework",
        "procedure", "experimental setup", "research design", "analysis method",
    ],
    SectionType.CONCLUSION: [
        "conclusion", "conclusions", "final thoughts", "wrap up",
        "recommendations", "key takeaways", "synthesis",
    ],
    SectionType.FUTURE: [
        "future", "outlook", "roadmap", "next steps", "coming soon",
        "forecast", "trends", "predictions", "what's next",
    ],
}

COMPARISON_KEYWORDS = [
    "vs", "versus", "compared", "comparison", "benchmarking",
    "contrast", "difference", "similarities", "trade-off", "tradeoff",
]

PROCESS_KEYWORDS = [
    "process", "steps", "framework", "methodology", "approach",
    "roadmap", "workflow", "procedure", "guide", "how to", "implementation",
]

TIMELINE_KEYWORDS = [
    "timeline", "history", "evolution", "roadmap", "forecast",
    "schedule", "phases", "stages", "milestone", "chronology",
]

TEMPORAL_PATTERNS = [
    r'\b20\d{2}\b',
    r'\b19\d{2}\b',
    r'\b\d{4}-\d{2}-\d{2}\b',
    r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b',
    r'\bQ[1-4]\s+20\d{2}\b',
    r'\b\d{4}\s+Q[1-4]\b',
]


def classify_section_type(heading: str) -> SectionType:
    """Classify section type based on heading text."""
    heading_lower = heading.lower()

    for section_type in [SectionType.SKIP, SectionType.SUMMARY, SectionType.INTRODUCTION,
                         SectionType.METHODOLOGY, SectionType.CONCLUSION, SectionType.FUTURE]:
        for keyword in SECTION_KEYWORDS[section_type]:
            if keyword in heading_lower:
                return section_type

    return SectionType.CONTENT


def classify_content_type(
    table_count: int,
    bullet_count: int,
    has_numeric_table: bool,
) -> ContentType:
    """Classify primary content type for layout selection."""
    if has_numeric_table:
        return ContentType.DATA

    if table_count > 0:
        return ContentType.TABLE

    if bullet_count >= 4:
        return ContentType.LIST

    return ContentType.TEXT


def detect_comparison(heading: str, content_text: str) -> bool:
    """Detect if section contains comparison content."""
    text = f"{heading} {content_text}".lower()
    return any(kw in text for kw in COMPARISON_KEYWORDS)


def detect_process(heading: str, content_text: str) -> bool:
    """Detect if section contains process/step content."""
    text = f"{heading} {content_text}".lower()
    return any(kw in text for kw in PROCESS_KEYWORDS)


def detect_timeline(heading: str, content_text: str) -> bool:
    """Detect if section contains temporal/chronological content."""
    text = f"{heading} {content_text}".lower()

    if any(kw in text for kw in TIMELINE_KEYWORDS):
        return True

    for pattern in TEMPORAL_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def is_numeric_column(header: str, values: List[str]) -> bool:
    """Check if a column contains primarily numeric data."""
    if not values:
        return False

    numeric_pattern = re.compile(r'^[\s$€£¥]*-?[\d,.]+\s*[%KMBT]?\s*$', re.IGNORECASE)
    numeric_count = sum(1 for v in values if numeric_pattern.match(v.strip()))
    return numeric_count / len(values) > 0.5


def is_temporal_column(header: str, values: List[str]) -> bool:
    """Check if a column contains temporal/date data."""
    header_lower = header.lower()
    temporal_headers = ["year", "date", "month", "quarter", "period", "time", "fiscal"]
    if any(t in header_lower for t in temporal_headers):
        return True

    for value in values[:5]:
        for pattern in TEMPORAL_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                return True

    return False


def select_chart_type(table_info: TableInfo, header_row: List[str], data_rows: List[List[str]]) -> str:
    """Deterministic chart type selection based on data shape.

    Reused from PPT Master's quickLookup pattern (hackathon_research_v3.md:403-418)
    and hackathon_final_analysis1.md:326-344.

    Rules:
    - temporal + numeric → line_chart
    - 1 category + 1 numeric, ≤6 rows → bar
    - 1 category + 1 numeric, >6 rows → horizontal_bar
    - 1 category + ≥2 numeric → grouped_bar
    - 2 cols, values sum to ~100 → donut
    - else → table (keep as-is)
    """
    has_temporal = table_info.has_temporal
    num_numeric = len(table_info.numeric_columns)
    num_cols = table_info.cols
    num_rows = table_info.rows

    num_category_cols = num_cols - num_numeric
    if has_temporal:
        num_category_cols -= len(table_info.temporal_columns)

    if has_temporal and num_numeric >= 1:
        return "line"

    if num_category_cols >= 1 and num_numeric == 1:
        if num_rows <= 6:
            return "bar"
        return "horizontal_bar"

    if num_category_cols >= 1 and num_numeric >= 2:
        return "grouped_bar"

    if num_cols == 2 and num_numeric == 1 and num_rows >= 2:
        # Check if values sum to approximately 100 (parts-of-whole)
        try:
            numeric_col = table_info.numeric_columns[0]
            values = []
            for row in data_rows:
                if numeric_col < len(row):
                    val_str = re.sub(r'[^\d.]', '', row[numeric_col])
                    if val_str:
                        values.append(float(val_str))
            total = sum(values)
            if 95 <= total <= 105:
                return "donut"
        except (ValueError, IndexError):
            pass

    if num_numeric >= 1:
        return "bar"

    return "bar"
