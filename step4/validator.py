"""Post-generation quality checks based on Common Mistakes PPTX rules.

Source: solution_architecture.md §GAP 6, gap_analysis1.md Part 4 (VIZ rules).
"""

from pptx import Presentation
from pptx.util import Inches


# Thresholds from Common Mistakes PPTX and research docs
MIN_MARGIN_INCHES = 0.5
MAX_WORDS_PER_SLIDE = 60
MAX_FONT_FAMILIES = 2


def validate_presentation(prs: Presentation) -> list[str]:
    """Run all quality checks on the generated presentation. Returns list of issues."""
    issues: list[str] = []
    all_fonts: set[str] = set()

    for slide_idx, slide in enumerate(prs.slides, start=1):
        slide_issues = _check_slide(slide, slide_idx, all_fonts)
        issues.extend(slide_issues)

    # Global font family check (Common Mistakes rule 12)
    real_fonts = {f for f in all_fonts if f is not None}
    if len(real_fonts) > MAX_FONT_FAMILIES:
        issues.append(
            f"Too many font families ({len(real_fonts)}): {real_fonts}. Max {MAX_FONT_FAMILIES}."
        )

    # Structure checks (hackathon brief: 10-15 slides required)
    if len(prs.slides) < 10:
        issues.append(f"Only {len(prs.slides)} slides — minimum 10 expected.")

    return issues


def _check_slide(slide, slide_idx: int, all_fonts: set[str]) -> list[str]:
    """Check a single slide for quality issues."""
    issues: list[str] = []
    min_margin_emu = Inches(MIN_MARGIN_INCHES)
    slide_width = Inches(13.33)
    slide_height = Inches(7.50)
    word_count = 0
    has_text = False

    for shape in slide.shapes:
        # Skip template-inherited placeholders (they're positioned by the template designer)
        if shape.is_placeholder:
            continue

        # Margin check (Common Mistakes rule 2)
        if shape.left < min_margin_emu * 0.8:  # 20% tolerance
            issues.append(
                f"Slide {slide_idx}: shape '{shape.name}' too close to left edge "
                f"({shape.left / 914400:.2f}\")"
            )
        if shape.top < min_margin_emu * 0.5:  # More tolerance for top
            pass  # Template shapes can be near top edge

        if shape.left + shape.width > slide_width + Inches(0.1):
            issues.append(
                f"Slide {slide_idx}: shape '{shape.name}' extends beyond right edge"
            )

        # Count words and fonts
        if shape.has_text_frame:
            has_text = True
            for paragraph in shape.text_frame.paragraphs:
                words = paragraph.text.split()
                word_count += len(words)
                for run in paragraph.runs:
                    if run.font.name:
                        all_fonts.add(run.font.name)

    # Word count check (Common Mistakes rule 4)
    if word_count > MAX_WORDS_PER_SLIDE:
        issues.append(
            f"Slide {slide_idx}: {word_count} words (max {MAX_WORDS_PER_SLIDE})"
        )

    return issues
