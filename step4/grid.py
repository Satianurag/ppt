"""Pre-computed coordinate system for shape placement on slides.

All values in EMU (English Metric Units) — python-pptx's native unit.
Slide dimensions: 13.33" × 7.50" for all 3 templates (verified).

Handles CRITICAL-5: Master-level obstacle zones per template.

Dynamic grid layouts (3B from hackathon_research_v3.md:506-508):
  1 item  → full-width
  2 items → side-by-side
  3+ items → grid

Proportional space filling (3C from Common Mistakes):
  Shapes should fill ≥40% of the safe content area.
"""

from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN

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
    """Template-aware coordinate system for placing shapes on content slides.

    Includes dynamic grid layout helpers (3B) and proportional space filling (3C).
    """

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

    # ── Dynamic Grid Layouts (3B) ────────────────────────────────────
    # hackathon_research_v3.md:506-508:
    #   1 item → full-width
    #   2 items → side-by-side
    #   3+ items → grid

    def dynamic_layout(self, n_items: int, gap: float = 0.25) -> list[tuple[int, int, int, int]]:
        """Compute (left, top, width, height) for n items using dynamic grid.

        Returns list of (left, top, width, height) tuples in EMU.
        """
        if n_items <= 0:
            return []

        gap_emu = Inches(gap)

        if n_items == 1:
            return [(self.content_left, self.content_top,
                     self.content_width, self.content_height)]

        if n_items == 2:
            col_width = int((self.content_width - gap_emu) / 2)
            return [
                (self.content_left, self.content_top,
                 col_width, self.content_height),
                (self.content_left + col_width + gap_emu, self.content_top,
                 col_width, self.content_height),
            ]

        # 3+ items: grid layout
        if n_items <= 4:
            cols = 2
        elif n_items <= 6:
            cols = 3
        elif n_items <= 9:
            cols = 3
        else:
            cols = 4

        rows = (n_items + cols - 1) // cols
        cell_width = int((self.content_width - gap_emu * (cols - 1)) / cols)
        cell_height = int((self.content_height - gap_emu * (rows - 1)) / rows)

        positions = []
        for idx in range(n_items):
            row = idx // cols
            col = idx % cols
            left = self.content_left + int(col * (cell_width + gap_emu))
            top = self.content_top + int(row * (cell_height + gap_emu))
            positions.append((left, top, cell_width, cell_height))

        return positions

    def proportional_fill(self, n_items: int) -> float:
        """Calculate what fraction of safe area n items would fill.

        Returns ratio (0.0-1.0). Target is ≥0.40 per Common Mistakes.
        """
        if n_items <= 0:
            return 0.0

        positions = self.dynamic_layout(n_items)
        total_area = sum(w * h for _, _, w, h in positions)
        safe_area = int(self.content_width) * int(self.content_height)
        return total_area / safe_area if safe_area > 0 else 0.0


# ── PPTAgent merge_cells — exact copy from pptagent/apis.py:345-353 ──

def merge_cells(merge_area: list[tuple[int, int, int, int]], table) -> None:
    """Merge cells in a python-pptx table.

    Exact copy from PPTAgent (pptagent/apis.py:345-353).

    Args:
        merge_area: List of (row1, col1, row2, col2) tuples defining merge regions.
        table: A python-pptx GraphicFrame (table shape).
    """
    if merge_area is None or len(merge_area) == 0:
        return
    for x1, y1, x2, y2 in merge_area:
        table.table.cell(x1, y1).merge(table.table.cell(x2, y2))
        for x, y in zip(range(x1, x2 + 1), range(y1, y2 + 1)):
            tf = table.table.cell(x, y).text_frame
            for p in tf.paragraphs:
                p.alignment = PP_ALIGN.CENTER
