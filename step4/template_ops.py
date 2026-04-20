"""Template loading, preservation of fixed slides, and cover population.

The three hackathon Slide Master templates each ship with a cover layout and a
thank-you (end) layout. Under C1, slide 1 and slide 15 must remain *visually*
identical to the template (same layout, same master styling). Only the cover
receives four dynamic runtime fields: title, subtitle, presenter name, date.

This module owns everything that is template-shaped and template-sensitive.
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple, Optional

from pptx import Presentation
from pptx.util import Inches, Pt


class TemplateType(str, Enum):
    AI_BUBBLE = "AI_Bubble"
    UAE_SOLAR = "UAE_Solar"
    ACCENTURE = "Accenture"
    UNKNOWN = "unknown"


class LayoutSlot(NamedTuple):
    """A usable layout in the master, with its declared role."""
    index: int
    name: str
    role: str  # "cover" | "divider" | "content" | "end"


# Per-template layout role map. Only fixed slots (cover, end) are authoritative;
# content slots are a *pool* the scheduler picks from.
_TEMPLATE_LAYOUTS: dict[TemplateType, dict[str, list[int]]] = {
    TemplateType.AI_BUBBLE: {
        "cover": [0],
        "divider": [1],
        "content": [2, 3],   # Blank, Title only
        "end": [4],          # 1_Thank you
    },
    TemplateType.UAE_SOLAR: {
        "cover": [0],
        "divider": [1],
        "content": [2, 3],   # body layouts with 2-4 placeholders
        "end": [4],          # Thank-you text embedded in layout
    },
    TemplateType.ACCENTURE: {
        "cover": [0],
        "divider": [2],
        "content": [3, 4],   # Blank, Title only
        "end": [5],          # Thank You
    },
}


# Cover placeholder slots per template. UAE uses CENTER_TITLE (idx 0) and has no
# subtitle placeholder, so subtitle is rendered as a runtime textbox beneath it.
_COVER_PLACEHOLDERS: dict[TemplateType, dict[str, Optional[int]]] = {
    TemplateType.AI_BUBBLE: {"title": 10, "subtitle": 11},
    TemplateType.UAE_SOLAR: {"title": 0, "subtitle": None},
    TemplateType.ACCENTURE: {"title": 10, "subtitle": 11},
}


def detect_template(prs: Presentation) -> TemplateType:
    """Identify which of the three hackathon templates is loaded."""
    names = [layout.name for layout in prs.slide_masters[0].slide_layouts]
    if "Cover" in names and "Blank" in names:
        return TemplateType.AI_BUBBLE
    if any("0_Title Company" in n for n in names):
        return TemplateType.UAE_SOLAR
    if "1_Cover" in names:
        return TemplateType.ACCENTURE
    return TemplateType.UNKNOWN


def role_layout_indices(template: TemplateType, role: str) -> list[int]:
    """Return the slide-master layout indices available for a role."""
    table = _TEMPLATE_LAYOUTS.get(template)
    if table is None:
        table = _TEMPLATE_LAYOUTS[TemplateType.AI_BUBBLE]
    return list(table.get(role, []))


def get_layout(prs: Presentation, template: TemplateType, role: str, pick: int = 0):
    """Get a slide layout object for a named role (picks the first by default)."""
    indices = role_layout_indices(template, role)
    if not indices:
        raise ValueError(f"No layout registered for role {role!r} in {template.value}")
    idx = indices[min(pick, len(indices) - 1)]
    return prs.slide_masters[0].slide_layouts[idx]


def _drop_all_slides(prs: Presentation) -> None:
    """Delete every existing slide in the presentation (XML-level)."""
    xml_slides = prs.slides._sldIdLst
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    while len(xml_slides) > 0:
        r_id = xml_slides[0].get(rel_ns)
        prs.part.drop_rel(r_id)
        del xml_slides[0]


def load_blank_canvas(template_path: str) -> tuple[Presentation, TemplateType]:
    """Load a template and strip all existing demo slides.

    Returns the Presentation with zero slides plus the detected template type.
    The slide master and all layouts are preserved; only slide-level content is
    removed so we can rebuild the 15-slide spine from scratch.
    """
    prs = Presentation(template_path)
    tpl = detect_template(prs)
    _drop_all_slides(prs)
    return prs, tpl


def add_cover_slide(
    prs: Presentation,
    template: TemplateType,
    title: str,
    subtitle: Optional[str],
    presenter: str,
    presentation_date: str,
):
    """Add slide 1 using the template's cover layout and fill the dynamic fields.

    The cover retains the template's master styling entirely — we only write
    into placeholders (title, subtitle if available) and add a textbox at the
    bottom-left for the presenter name and date.
    """
    layout = get_layout(prs, template, "cover")
    slide = prs.slides.add_slide(layout)

    slots = _COVER_PLACEHOLDERS.get(template, {})
    title_idx = slots.get("title")
    subtitle_idx = slots.get("subtitle")

    subtitle_placed = False
    for ph in slide.placeholders:
        idx = ph.placeholder_format.idx
        if title_idx is not None and idx == title_idx:
            ph.text = title
        elif subtitle_idx is not None and idx == subtitle_idx and subtitle:
            ph.text = subtitle
            subtitle_placed = True

    if subtitle and not subtitle_placed:
        _add_runtime_textbox(
            slide,
            left=Inches(0.5), top=Inches(4.7),
            width=Inches(12.33), height=Inches(0.8),
            text=subtitle,
            font_size=Pt(20),
        )

    _add_runtime_textbox(
        slide,
        left=Inches(0.4), top=Inches(6.5),
        width=Inches(6.5), height=Inches(0.8),
        text=f"{presenter}\n{presentation_date}",
        font_size=Pt(14),
        line_spacing=1.15,
    )

    return slide


def add_end_slide(prs: Presentation, template: TemplateType):
    """Append slide 15 using the template's thank-you layout, unmodified."""
    layout = get_layout(prs, template, "end")
    return prs.slides.add_slide(layout)


def add_content_slide(prs: Presentation, template: TemplateType, pick: int = 0):
    """Add a body slide using a neutral content layout from the master.

    The layout is a blank-ish canvas — the slide's visual identity is produced
    by the layout renderer (which draws the geometry), while the master still
    provides theme colors, fonts, and the background chrome.
    """
    layout = get_layout(prs, template, "content", pick=pick)
    return prs.slides.add_slide(layout)


def _add_runtime_textbox(
    slide,
    left,
    top,
    width,
    height,
    text: str,
    *,
    font_size,
    bold: bool = False,
    line_spacing: float = 1.0,
) -> None:
    """Add a plain textbox with zero local styling overrides.

    Deliberately does NOT set ``font.name`` or ``font.color`` — both cascade
    from the slide master (C3). ``font.size`` is the only run-level override we
    allow, because master-inherited sizes would otherwise render the cover's
    bottom-left block too large.
    """
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0

    lines = text.split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.line_spacing = line_spacing
        for run in p.runs:
            run.font.size = font_size
            if bold:
                run.font.bold = True
