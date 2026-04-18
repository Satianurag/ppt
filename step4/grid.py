"""Pre-computed coordinate system for shape placement on slides.

All values in EMU (English Metric Units) — python-pptx's native unit.
Slide dimensions: 13.33" × 7.50" for all 3 templates (verified).

Handles CRITICAL-5: Master-level obstacle zones per template.
"""

from pptx.util import Inches, Pt

from step4.template_manager import TemplateType, MASTER_OBSTACLES


# Slide dimensions (all templates)
SLIDE_WIDTH = Inches(13.33)
SLIDE_HEIGHT = Inches(7.50)

# Margins from slide edges (Common Mistakes rule 2: ≥ 0.5")
MARGIN = Inches(0.5)
ELEMENT_GAP = Inches(0.2)

# Font sizes (from Guidelines: title > subtitle > body)
TITLE_FONT_SIZE = Pt(28)
SUBTITLE_FONT_SIZE = Pt(18)
BODY_FONT_SIZE = Pt(16)
FOOTER_FONT_SIZE = Pt(10)


class Grid:
    """Template-aware coordinate system for placing shapes on content slides."""

    def __init__(self, template_type: TemplateType) -> None:
        self.template_type = template_type
        obstacles = MASTER_OBSTACLES.get(template_type, [])

        # Calculate safe right boundary accounting for logo obstacles
        right_limit = 13.33 - 0.5  # Default: slide width - margin
        for ox, oy, ow, oh in obstacles:
            if ox > 10.0:  # Obstacle in the right region
                right_limit = min(right_limit, ox - 0.1)

        self.safe_width = Inches(right_limit - 0.5)  # Left margin subtracted

        # Title zone
        self.title_left = MARGIN
        self.title_top = MARGIN
        self.title_width = self.safe_width
        self.title_height = Inches(0.6)

        # Subtitle zone (below title)
        self.subtitle_top = Inches(1.15)
        self.subtitle_height = Inches(0.35)

        # Content zone (main area below title/subtitle)
        self.content_left = MARGIN
        self.content_top = Inches(1.60)
        self.content_width = self.safe_width
        self.content_height = Inches(5.30)

        # Chart zone (centered in content area, slightly smaller)
        self.chart_left = Inches(0.8)
        self.chart_top = Inches(1.70)
        self.chart_width = Inches(min(right_limit - 0.5 - 0.3, 11.0))
        self.chart_height = Inches(4.80)

        # Table zone (same as content)
        self.table_left = self.content_left
        self.table_top = Inches(1.70)
        self.table_width = self.safe_width
        self.table_height = Inches(5.10)

        # Footer zone (key message / source note)
        self.footer_left = MARGIN
        self.footer_top = Inches(7.00)
        self.footer_width = self.safe_width
        self.footer_height = Inches(0.30)

        # Two-column layout
        col_gap = Inches(0.3)
        col_width = Inches((right_limit - 0.5 - 0.3) / 2)
        self.left_col_left = MARGIN
        self.left_col_width = col_width
        self.right_col_left = Inches(0.5) + col_width + col_gap
        self.right_col_width = col_width

        # Infographic: process flow (horizontal chevrons)
        self.process_top = Inches(2.50)
        self.process_height = Inches(2.00)
