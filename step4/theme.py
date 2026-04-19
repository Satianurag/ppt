"""Theme color handling for charts and infographics.

Charts do NOT auto-inherit theme colors — must manually assign
MSO_THEME_COLOR.ACCENT_N per series.
Source: hackathon_research_v2.md:470, hackathon_final_analysis1.md §9.1

python-pptx theme color best practice (GitHub Issue #1111):
  - Use shape.fill.fore_color.theme_color = MSO_THEME_COLOR.ACCENT_N
  - NEVER read .rgb on theme-colored elements (mutates XML, breaks inheritance)
  - For text: run.font.color.theme_color = MSO_THEME_COLOR.DARK_1
"""

from pptx.enum.dml import MSO_THEME_COLOR
from pptx.dml.color import RGBColor

# The 6 accent theme colors available in all templates
ACCENT_COLORS: list[MSO_THEME_COLOR] = [
    MSO_THEME_COLOR.ACCENT_1,
    MSO_THEME_COLOR.ACCENT_2,
    MSO_THEME_COLOR.ACCENT_3,
    MSO_THEME_COLOR.ACCENT_4,
    MSO_THEME_COLOR.ACCENT_5,
    MSO_THEME_COLOR.ACCENT_6,
]


def get_accent_color(index: int) -> MSO_THEME_COLOR:
    """Get theme accent color by index (wraps around after 6)."""
    return ACCENT_COLORS[index % len(ACCENT_COLORS)]


def apply_accent_fill(shape, index: int) -> None:
    """Apply theme accent color as solid fill to a shape.

    Uses theme_color instead of hardcoded RGB so colors adapt
    to each template's slide master palette.
    """
    shape.fill.solid()
    shape.fill.fore_color.theme_color = get_accent_color(index)


def apply_accent_font(run, index: int) -> None:
    """Apply theme accent color to a text run's font."""
    run.font.color.theme_color = get_accent_color(index)


def apply_text_color(run) -> None:
    """Apply theme text color (dark 1) to a text run.

    Uses DARK_1 which maps to the template's primary text color,
    adapting to both light and dark templates.
    """
    run.font.color.theme_color = MSO_THEME_COLOR.DARK_1


def apply_subtle_text_color(run) -> None:
    """Apply a subtle/secondary text color (dark 2)."""
    run.font.color.theme_color = MSO_THEME_COLOR.DARK_2


def apply_light_fill(shape) -> None:
    """Apply a light background fill using theme LIGHT_1 with tint.

    Used for card backgrounds, alternating rows, etc.
    Replaces hardcoded #F5F5F5 / #F0F0F0.
    """
    shape.fill.solid()
    shape.fill.fore_color.theme_color = MSO_THEME_COLOR.ACCENT_1
    shape.fill.fore_color.brightness = 0.8


# Fallback RGB values only for contexts where theme_color isn't available
FALLBACK_DARK_TEXT = RGBColor(0x33, 0x33, 0x33)
FALLBACK_SUBTLE_TEXT = RGBColor(0x66, 0x66, 0x66)
