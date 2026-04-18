"""Template loading, detection, demo slide deletion, and layout mapping.

Handles:
- CRITICAL-1: UAE Solar has no Blank layout
- CRITICAL-2: Must delete existing demo slides
- CRITICAL-3: think-cell OLE objects (left alone)
- CRITICAL-6: UAE Solar duplicate layout names → index-based lookup
- GAP-9: Auto-detect template type from layout structure
"""

from enum import Enum
from typing import NamedTuple

from pptx import Presentation
from pptx.util import Inches


class TemplateType(str, Enum):
    AI_BUBBLE = "AI_Bubble"
    UAE_SOLAR = "UAE_Solar"
    ACCENTURE = "Accenture"
    UNKNOWN = "unknown"


class LayoutRole(str, Enum):
    COVER = "cover"
    DIVIDER = "divider"
    CONTENT = "content"
    END = "end"


class LayoutEntry(NamedTuple):
    index: int
    role: LayoutRole
    has_title_placeholder: bool
    has_body_placeholder: bool


# Index-based layout maps — never use name-based lookup (CRITICAL-6)
LAYOUT_MAPS: dict[TemplateType, dict[LayoutRole, int]] = {
    TemplateType.AI_BUBBLE: {
        LayoutRole.COVER: 0,
        LayoutRole.DIVIDER: 1,
        LayoutRole.CONTENT: 2,    # "Blank" — 0 shapes, our canvas
        LayoutRole.END: 4,        # "1_Thank you"
    },
    TemplateType.UAE_SOLAR: {
        LayoutRole.COVER: 0,
        LayoutRole.DIVIDER: 1,
        LayoutRole.CONTENT: 2,    # Has title, subtitle, body, slide# placeholders
        LayoutRole.END: 0,        # Reuse title layout for end (no dedicated thank-you)
    },
    TemplateType.ACCENTURE: {
        LayoutRole.COVER: 0,
        LayoutRole.DIVIDER: 2,
        LayoutRole.CONTENT: 3,    # "Blank" — 0 shapes, our canvas
        LayoutRole.END: 5,        # "Thank You"
    },
}

# Cover slide placeholder indices per template (VIZ-6)
COVER_PLACEHOLDERS: dict[TemplateType, dict[str, int | None]] = {
    TemplateType.AI_BUBBLE: {"title": 10, "subtitle": 11},
    TemplateType.UAE_SOLAR: {"title": 0, "subtitle": None},
    TemplateType.ACCENTURE: {"title": 10, "subtitle": 11},
}

# Master-level obstacle zones per template (CRITICAL-5)
# (left, top, width, height) in inches — shapes to avoid overlapping
MASTER_OBSTACLES: dict[TemplateType, list[tuple[float, float, float, float]]] = {
    TemplateType.AI_BUBBLE: [
        (12.25, 0.43, 0.70, 0.33),  # Logo top-right
    ],
    TemplateType.UAE_SOLAR: [],  # Only think-cell at 0,0 — no visual obstacles
    TemplateType.ACCENTURE: [
        (12.15, 0.38, 0.80, 0.27),  # Logo top-right
    ],
}


def detect_template(prs: Presentation) -> TemplateType:
    """Auto-detect template type from slide layout structure (GAP-9)."""
    layout_names = [layout.name for layout in prs.slide_masters[0].slide_layouts]
    if "Cover" in layout_names and "Blank" in layout_names:
        return TemplateType.AI_BUBBLE
    if any("0_Title Company" in n for n in layout_names):
        return TemplateType.UAE_SOLAR
    if "1_Cover" in layout_names:
        return TemplateType.ACCENTURE
    return TemplateType.UNKNOWN


def delete_demo_slides(prs: Presentation) -> None:
    """Delete all existing demo slides from the template (CRITICAL-2).

    python-pptx has no delete_slide() API — must manipulate XML directly.
    """
    xml_slides = prs.slides._sldIdLst
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    while len(xml_slides) > 0:
        r_id = xml_slides[0].get(rel_ns)
        prs.part.drop_rel(r_id)
        del xml_slides[0]


def get_layout(prs: Presentation, template_type: TemplateType, role: LayoutRole):
    """Get a slide layout by role using index-based lookup (CRITICAL-6)."""
    layout_map = LAYOUT_MAPS.get(template_type)
    if layout_map is None:
        layout_map = LAYOUT_MAPS[TemplateType.AI_BUBBLE]
    idx = layout_map[role]
    return prs.slide_masters[0].slide_layouts[idx]


def load_template(template_path: str) -> tuple[Presentation, TemplateType]:
    """Load template, detect type, delete demo slides."""
    prs = Presentation(template_path)
    template_type = detect_template(prs)
    delete_demo_slides(prs)
    return prs, template_type
