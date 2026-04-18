"""Theme color handling for charts and infographics.

Charts do NOT auto-inherit theme colors — must manually assign
MSO_THEME_COLOR.ACCENT_N per series.
Source: hackathon_research_v2.md:470, hackathon_final_analysis1.md §9.1
"""

from pptx.enum.dml import MSO_THEME_COLOR

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
