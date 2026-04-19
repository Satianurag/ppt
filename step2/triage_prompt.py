"""Prompt template for content triage agent."""

from constants import (
    SLIDE_BUDGET,
    MANDATORY_SLIDES,
    MAX_CHART_SLIDES,
    MAX_BULLETS_PER_SLIDE,
    MAX_WORDS_PER_BULLET,
)

TRIAGE_PROMPT_TEMPLATE = """You are an expert presentation strategist. Create a slide plan from the content inventory below.

PRESENTATION REQUIREMENTS:
- Total slides: {slide_budget}
- Mandatory slides: Title (1), Agenda (1), Executive Summary (1), Conclusion/Thank You (1)
- Content slides available: {content_budget}
- Max chart slides (soft): {max_chart_slides} — pick the most data-rich tables
- Max bullets per slide: {max_bullets} items, up to {max_words_per_bullet} words each
- Title length: max 50 characters
- Key message: 1 sentence summarizing the slide's main point
- NO images — this presentation uses text, charts, and tables only

CONTENT INVENTORY:
{inventory_json}

DECISION RULES - FOLLOW STRICTLY:

1. SECTION MERGING (when sections > content slots):
   - Merge adjacent sections with similar topics (Introduction + Background)
   - Merge small sections (< 200 words each)
   - Merge same content types (TEXT + TEXT, not DATA + DATA)
   - Never merge DATA sections - each chart needs its own slide
   - Document merge reasons in output

2. SLIDE ALLOCATION:
   - Give own slide to: DATA sections, Executive Summary, Conclusion, sections > 500 words
   - Merge: small adjacent TEXT sections, related topics
   - Skip: TOC, References, Appendix (already filtered in inventory)

3. CHART SELECTION (max {max_chart_slides}):
   - Select tables with has_numeric=true
   - Use the recommended_chart_type from inventory when available
   - Prioritize: temporal data > comparisons > rankings > simple values

4. LAYOUT SELECTION:
   - Title slide: COVER
   - Agenda: DIVIDER or BULLET
   - Executive Summary: BULLET
   - Data slides: CHART_WITH_TEXT (if chart) or BULLET (if table)
   - Comparison sections: COMPARISON
   - Timeline sections: TIMELINE
   - Conclusion: BULLET or TITLE_ONLY

5. SLIDE ORDER:
   - Slide 1: Title (COVER)
   - Slide 2: Agenda (BULLET or DIVIDER)
   - Slide 3: Executive Summary (BULLET)
   - Slides 4 to N-1: Content (interleave bullet and chart slides)
   - Slide N: Conclusion/Thank You (BULLET or TITLE_ONLY)

6. CONTENT TYPE RULES:
   - DATA sections → chart slides (if table selected) or table slides
   - TABLE sections → table slides
   - LIST sections → bullet slides
   - TEXT sections → bullet slides

OUTPUT FORMAT:
Return a valid JSON object matching the PresentationPlan schema with:
- slide_budget: {slide_budget}
- total_slides: actual count (must equal slide_budget)
- title: from inventory title
- slides: array of SlidePlan objects
- sections_used: count of unique section IDs used
- charts_planned: count of chart slides
- merge_reasoning: map explaining why sections were merged

Example slide plan structure:
{{{{
  "slide_budget": {slide_budget},
  "total_slides": {slide_budget},
  "title": "Example Presentation",
  "slides": [
    {{{{
      "slide_number": 1,
      "type": "title",
      "layout": "cover",
      "title": "Example Presentation",
      "source_sections": [],
      "key_message": "Overview of key findings",
      "content_type": "bullet",
      "bullet_points": []
    }}}},
    {{{{
      "slide_number": 3,
      "type": "summary",
      "layout": "bullet",
      "title": "Executive Summary",
      "source_sections": ["exec_summary"],
      "key_message": "Revenue increased 25% driven by AI adoption",
      "content_type": "bullet",
      "bullet_points": ["25% revenue growth", "15% market share", "92% satisfaction"]
    }}}},
    {{{{
      "slide_number": 7,
      "type": "content",
      "layout": "chart_with_text",
      "title": "Market Growth Trends",
      "source_sections": ["sec_5"],
      "key_message": "Market growing at 15% CAGR through 2025",
      "content_type": "chart",
      "chart_config": {{{{
        "chart_type": "line",
        "table_index": 12,
        "title": "Annual Market Growth"
      }}}},
      "bullet_points": ["2022: $100M", "2023: $115M", "2024: $132M"]
    }}}}
  ]
}}}}

IMPORTANT:
- All section IDs from inventory must appear in at least one slide's source_sections
- Each DATA section with numeric table should ideally become a chart slide
- Do not exceed {max_chart_slides} chart slides total
- Merge sections when needed to fit budget, but explain merges
- Ensure slide_number is sequential from 1 to total_slides
"""


def build_triage_prompt(inventory_json: str, slide_budget: int = SLIDE_BUDGET) -> str:
    """Build the triage prompt with inventory data."""
    content_budget = slide_budget - MANDATORY_SLIDES

    return TRIAGE_PROMPT_TEMPLATE.format(
        slide_budget=slide_budget,
        content_budget=content_budget,
        max_chart_slides=MAX_CHART_SLIDES,
        max_bullets=MAX_BULLETS_PER_SLIDE,
        max_words_per_bullet=MAX_WORDS_PER_BULLET,
        inventory_json=inventory_json,
    )
