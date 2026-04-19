"""Main orchestrator: iterates PresentationContent.slides and dispatches to renderers.

This is the entry point for Step 4. Takes PresentationContent from Step 3 and
a template PPTX path, produces a .pptx file.
"""

from pathlib import Path

from step2.slide_plan_models import SlideType, LayoutType
from step3.content_models import PresentationContent, SlideContent
from step4.template_manager import load_template, TemplateType
from step4.grid import Grid
from step4.renderers import (
    render_cover,
    render_end,
    render_bullets,
    render_chart,
    render_table,
    render_infographic,
    render_agenda,
)
from step4.validator import validate_presentation


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
    # Load template, detect type, delete demo slides
    prs, template_type = load_template(template_path)
    grid = Grid(template_type)

    print(f"  Template: {template_type.value}")
    print(f"  Slides to render: {len(content.slides)}")

    # Render each slide based on type and content (VIZ-1: error-protected)
    render_errors: list[str] = []
    for slide_content in content.slides:
        errors = _render_slide(prs, template_type, grid, slide_content, content)
        render_errors.extend(errors)

    if render_errors:
        print(f"\n  Render errors ({len(render_errors)}):")
        for err in render_errors:
            print(f"    - {err}")

    # Validate
    issues = validate_presentation(prs)
    issues.extend(render_errors)
    if issues:
        print(f"\n  Validation issues ({len(issues)}):")
        for issue in issues:
            print(f"    - {issue}")

    # Save
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

    Returns a list of error messages (empty if successful).
    VIZ-1: wraps each slide render in error protection so one failure
    doesn't crash the entire pipeline.
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

        # Infographic layouts (comparison, timeline, process)
        if layout in (LayoutType.COMPARISON, LayoutType.TIMELINE, LayoutType.PROCESS):
            render_infographic(prs, template_type, slide_content, grid)
            return errors

        # Default: bullet slide
        render_bullets(prs, template_type, slide_content, grid)

    except Exception as exc:
        error_msg = f"Slide {slide_num} ({slide_content.slide_type.value}): render failed — {exc}"
        print(f"  WARNING: {error_msg}")
        errors.append(error_msg)

    return errors
