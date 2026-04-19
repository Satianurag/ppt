"""Main orchestrator: iterates PresentationContent.slides and dispatches to renderers.

This is the entry point for Step 4. Takes PresentationContent from Step 3 and
a template PPTX path, produces a .pptx file.

Includes infographic-first approach (3A): before rendering bullet slides,
checks if content can be visualized as an infographic instead.
"""

from pathlib import Path

from step2.slide_plan_models import SlideType, LayoutType
from step3.content_models import PresentationContent, SlideContent
from step4.template_manager import load_template, TemplateType, LayoutRole, get_layout
from step4.grid import Grid
from step4.renderers import (
    render_cover,
    render_end,
    render_bullets,
    render_chart,
    render_table,
    render_infographic,
    render_agenda,
    _add_slide_title,
    _add_key_message_footer,
    _get_bullet_texts,
)
from step4.infographic_renderers import (
    render_timeline,
    render_comparison_columns,
    render_numbered_steps,
    render_kpi_cards,
    render_funnel,
    render_pyramid,
    render_hub_spoke,
    render_cycle_diagram,
    render_vertical_list,
    render_pros_cons,
    render_matrix_2x2,
    render_icon_grid,
)
from step4.validator import validate_presentation

# Infographic-first: keywords that trigger infographic rendering
# instead of default bullet slides (research: hackathon_research.md:68-69)
INFOGRAPHIC_KEYWORDS: dict[str, str] = {
    "process": "numbered_steps",
    "steps": "numbered_steps",
    "workflow": "numbered_steps",
    "procedure": "numbered_steps",
    "how to": "numbered_steps",
    "methodology": "numbered_steps",
    "framework": "numbered_steps",
    "timeline": "timeline",
    "history": "timeline",
    "evolution": "timeline",
    "chronology": "timeline",
    "milestone": "timeline",
    "roadmap": "timeline",
    "phases": "timeline",
    "comparison": "comparison_columns",
    "vs": "comparison_columns",
    "versus": "comparison_columns",
    "contrast": "comparison_columns",
    "benchmark": "comparison_columns",
    "pros": "pros_cons",
    "cons": "pros_cons",
    "advantages": "pros_cons",
    "disadvantages": "pros_cons",
    "strengths": "pros_cons",
    "weaknesses": "pros_cons",
    "swot": "matrix_2x2",
    "hierarchy": "pyramid",
    "pyramid": "pyramid",
    "tier": "pyramid",
    "level": "pyramid",
    "kpi": "kpi_cards",
    "metric": "kpi_cards",
    "performance": "kpi_cards",
    "dashboard": "kpi_cards",
    "funnel": "funnel",
    "conversion": "funnel",
    "pipeline": "funnel",
    "cycle": "cycle_diagram",
    "circular": "cycle_diagram",
    "recurring": "cycle_diagram",
    "hub": "hub_spoke",
    "ecosystem": "hub_spoke",
    "components": "hub_spoke",
}


def _detect_infographic_type(slide_content: SlideContent) -> str | None:
    """Infographic-first approach: check if content should be visualized.

    Returns the infographic type name or None for regular bullet rendering.
    Per research docs (hackathon_research.md:68-69): "Before placing text,
    ask: Can this be visualized?"
    """
    text = f"{slide_content.title} {slide_content.key_message}".lower()

    for keyword, infographic_type in INFOGRAPHIC_KEYWORDS.items():
        if keyword in text:
            return infographic_type

    return None


def build_presentation(
    content: PresentationContent,
    template_path: str,
    output_path: str,
) -> tuple[str, list[str]]:
    """Build a PPTX file from PresentationContent and a Slide Master template.

    Args:
        content: Structured slide content from Step 3.
        template_path: Path to one of the 3 Slide Master PPTX templates.
        output_path: Where to save the generated .pptx file.

    Returns:
        Tuple of (output_path, validation_issues).
    """
    prs, template_type = load_template(template_path)
    grid = Grid(template_type)

    print(f"  Template: {template_type.value}")
    print(f"  Slides to render: {len(content.slides)}")

    render_errors: list[str] = []
    for slide_content in content.slides:
        errors = _render_slide(prs, template_type, grid, slide_content, content)
        render_errors.extend(errors)

    if render_errors:
        print(f"\n  Render errors ({len(render_errors)}):")
        for err in render_errors:
            print(f"    - {err}")

    issues = validate_presentation(prs)
    issues.extend(render_errors)
    if issues:
        print(f"\n  Validation issues ({len(issues)}):")
        for issue in issues:
            print(f"    - {issue}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(output_path)
    print(f"\n  Saved: {output_path}")

    return output_path, issues


def _render_slide(
    prs,
    template_type: TemplateType,
    grid: Grid,
    slide_content: SlideContent,
    full_content: PresentationContent,
) -> list[str]:
    """Dispatch a single slide to the appropriate renderer.

    Includes infographic-first approach: before rendering bullets,
    checks if the content can be visualized as an infographic.

    VIZ-1: wraps each slide render in error protection.
    """
    errors: list[str] = []
    slide_num = slide_content.slide_number

    try:
        slide_type = slide_content.slide_type
        layout = slide_content.layout

        if slide_type == SlideType.TITLE:
            render_cover(prs, template_type, slide_content, full_content.title)
            return errors

        if slide_type == SlideType.THANK_YOU:
            render_end(prs, template_type, slide_content)
            return errors

        if slide_type == SlideType.AGENDA:
            render_agenda(prs, template_type, slide_content, grid, full_content.slides)
            return errors

        # Chart slide — has chart_data
        if slide_content.chart_data is not None:
            render_chart(prs, template_type, slide_content, grid)
            return errors

        # Table slide — has table_data but no chart
        if slide_content.table_data is not None:
            render_table(prs, template_type, slide_content, grid)
            return errors

        # Infographic layouts (comparison, timeline, process) — explicit layout
        if layout in (LayoutType.COMPARISON, LayoutType.TIMELINE, LayoutType.PROCESS):
            render_infographic(prs, template_type, slide_content, grid)
            return errors

        # Infographic-first approach: check if bullet content can be visualized
        infographic_type = _detect_infographic_type(slide_content)
        if infographic_type:
            _render_infographic_first(
                prs, template_type, slide_content, grid, infographic_type
            )
            return errors

        # Default: bullet slide
        render_bullets(prs, template_type, slide_content, grid)

    except Exception as exc:
        error_msg = f"Slide {slide_num} ({slide_content.slide_type.value}): render failed — {exc}"
        print(f"  WARNING: {error_msg}")
        errors.append(error_msg)

    return errors


def _render_infographic_first(
    prs,
    template_type: TemplateType,
    slide_content: SlideContent,
    grid: Grid,
    infographic_type: str,
) -> None:
    """Render a slide using an infographic renderer instead of plain bullets.

    This implements the infographic-first approach from the research docs:
    "Before placing text, ask: Can this be visualized?"
    """
    layout_obj = get_layout(prs, template_type, LayoutRole.CONTENT)
    slide = prs.slides.add_slide(layout_obj)

    _add_slide_title(slide, grid, template_type, slide_content.title)

    bullets = _get_bullet_texts(slide_content)

    # Convert bullet texts to items format expected by infographic renderers
    items = [{"title": b, "description": "", "label": b} for b in bullets]

    renderer_map = {
        "timeline": lambda: render_timeline(slide, grid, items),
        "comparison_columns": lambda: render_comparison_columns(
            slide, grid,
            [{"title": f"Option {i+1}", "points": [b]} for i, b in enumerate(bullets)]
        ),
        "numbered_steps": lambda: render_numbered_steps(slide, grid, items),
        "kpi_cards": lambda: render_kpi_cards(
            slide, grid,
            [{"value": str(i+1), "label": b} for i, b in enumerate(bullets)]
        ),
        "funnel": lambda: render_funnel(slide, grid, items),
        "pyramid": lambda: render_pyramid(slide, grid, bullets),
        "hub_spoke": lambda: render_hub_spoke(
            slide, grid, bullets[0] if bullets else "Center",
            bullets[1:] if len(bullets) > 1 else bullets
        ),
        "cycle_diagram": lambda: render_cycle_diagram(slide, grid, bullets),
        "vertical_list": lambda: render_vertical_list(slide, grid, items),
        "pros_cons": lambda: render_pros_cons(
            slide, grid,
            bullets[:len(bullets)//2],
            bullets[len(bullets)//2:]
        ),
        "matrix_2x2": lambda: render_matrix_2x2(
            slide, grid,
            [{"title": b, "points": []} for b in bullets[:4]]
        ),
        "icon_grid": lambda: render_icon_grid(
            slide, grid,
            [{"icon": "●", "title": b, "description": ""} for b in bullets]
        ),
    }

    renderer = renderer_map.get(infographic_type)
    if renderer:
        renderer()
    else:
        # Fallback: render as regular bullets on the already-created slide
        from step4.font_sizing import auto_font_size_pt
        from pptx.util import Pt
        txBox = slide.shapes.add_textbox(
            grid.content_left, grid.content_top,
            grid.content_width, grid.content_height,
        )
        tf = txBox.text_frame
        tf.word_wrap = True
        all_text = " ".join(bullets)
        font_size = auto_font_size_pt(all_text, "full_width")
        for i, bullet_text in enumerate(bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"• {bullet_text}"
            p.font.size = font_size
            p.space_after = Pt(8)

    _add_key_message_footer(slide, grid, slide_content.key_message)
