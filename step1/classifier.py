"""Section and content type classification logic.

Chart type selection uses the FULL quickLookup from PPT Master's
charts_index.json (hugohe3/ppt-master templates/charts/charts_index.json).
All 18 semantic categories are mapped.
Also includes hackathon_final_analysis1.md:326-344 deterministic rules.
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


# PPT Master quickLookup — exact copy from hugohe3/ppt-master
# templates/charts/charts_index.json (all 18 semantic categories)
QUICK_LOOKUP: dict[str, list[str]] = {
    "ranking": ["horizontal_bar", "bar", "pareto"],
    "comparison": ["bar", "grouped_bar", "butterfly", "dumbbell"],
    "trend": ["line", "area", "stacked_area", "dual_axis_line"],
    "composition": ["donut", "pie", "treemap"],
    "kpi": ["kpi_cards", "bullet", "gauge", "progress_bar"],
    "conversion": ["funnel", "sankey", "waterfall"],
    "distribution": ["box_plot", "heatmap", "scatter", "bubble"],
    "correlation": ["scatter", "bubble", "radar"],
    "roadmap": ["gantt", "timeline", "process_flow"],
    "relationship": ["org_chart", "sankey", "matrix_2x2"],
    "flow": ["process_flow", "sankey", "waterfall"],
    "strategy": ["swot_analysis", "porter_five_forces", "matrix_2x2"],
    "hierarchy": ["pyramid", "isometric_stairs", "org_chart", "concentric_circles"],
    "infographic": ["icon_grid", "numbered_steps", "cycle_diagram", "venn_diagram",
                    "pros_cons", "mind_map", "hub_spoke", "sector_diagram",
                    "word_cloud", "vertical_list"],
    "pros_cons": ["pros_cons", "butterfly", "swot_analysis", "comparison_table",
                  "comparison_columns"],
    "cause_effect": ["fishbone_diagram", "process_flow"],
    "journey": ["snake_flow", "timeline", "roadmap_vertical", "chevron_process"],
    "pricing": ["comparison_columns", "comparison_table"],
}

# Semantic keywords that map headings/content to quickLookup categories
SEMANTIC_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "ranking": ["ranking", "rank", "top", "best", "worst", "leading", "largest", "highest",
               "lowest", "bottom", "leaderboard"],
    "comparison": ["comparison", "compare", "vs", "versus", "benchmark", "competitive",
                   "relative", "against"],
    "trend": ["trend", "growth", "decline", "over time", "annual", "quarterly",
              "monthly", "year-over-year", "yoy", "cagr", "forecast", "projection"],
    "composition": ["share", "proportion", "percentage", "breakdown", "composition",
                    "distribution", "mix", "allocation", "split"],
    "kpi": ["kpi", "metric", "target", "actual", "performance", "score",
            "achievement", "dashboard", "indicator"],
    "conversion": ["funnel", "conversion", "pipeline", "stage", "drop-off",
                   "waterfall", "bridge"],
    "distribution": ["distribution", "spread", "variance", "outlier", "histogram",
                     "quartile", "median", "deviation"],
    "correlation": ["correlation", "relationship", "regression", "scatter",
                    "association", "r-squared"],
    "flow": ["flow", "process", "workflow", "pipeline", "sequence"],
    "hierarchy": ["hierarchy", "pyramid", "tier", "level", "organizational",
                  "structure", "layered"],
    "pros_cons": ["pros", "cons", "advantages", "disadvantages", "strengths",
                  "weaknesses", "benefits", "drawbacks", "swot"],
    "journey": ["journey", "roadmap", "milestone", "phase", "timeline",
                "chronology", "evolution", "history"],
}


def classify_semantic_category(heading: str, content_text: str) -> Optional[str]:
    """Classify content into a PPT Master quickLookup semantic category.

    Returns the category name (e.g. 'trend', 'comparison') or None.
    """
    text = f"{heading} {content_text}".lower()
    best_category = None
    best_score = 0

    for category, keywords in SEMANTIC_CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category if best_score > 0 else None


def select_chart_type(table_info: TableInfo, header_row: List[str], data_rows: List[List[str]]) -> str:
    """Deterministic chart type selection using PPT Master's full quickLookup.

    Three-step process:
    1. Try semantic classification from header text → quickLookup category
    2. Apply data-shape rules (hackathon_final_analysis1.md:326-344)
    3. Fallback to 'bar' if nothing matches

    The quickLookup returns ordered preferences — pick the first chart type
    that our renderer supports (ChartType enum).
    """
    has_temporal = table_info.has_temporal
    num_numeric = len(table_info.numeric_columns)
    num_cols = table_info.cols
    num_rows = table_info.rows

    num_category_cols = num_cols - num_numeric
    if has_temporal:
        num_category_cols -= len(table_info.temporal_columns)

    # Step 1: Semantic category from header text
    header_text = " ".join(header_row)
    semantic_cat = classify_semantic_category(header_text, "")
    if semantic_cat and semantic_cat in QUICK_LOOKUP:
        preferred = QUICK_LOOKUP[semantic_cat]
        # Map quickLookup names to our ChartType enum values
        for pref in preferred:
            if pref in _RENDERABLE_CHART_TYPES:
                return pref

    # Step 2: Data-shape rules (hackathon_final_analysis1.md:326-344)
    if has_temporal and num_numeric >= 1:
        return "line"

    if num_category_cols >= 1 and num_numeric == 1:
        if num_rows <= 6:
            return "bar"
        return "horizontal_bar"

    if num_category_cols >= 1 and num_numeric >= 2:
        return "grouped_bar"

    if num_cols == 2 and num_numeric == 1 and num_rows >= 2:
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


# Chart types our python-pptx renderer can handle
_RENDERABLE_CHART_TYPES = {
    "bar", "horizontal_bar", "grouped_bar", "line", "pie", "donut",
    "area", "stacked_bar", "stacked_area",
}
