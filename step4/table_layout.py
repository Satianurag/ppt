"""Table layout heuristics — adapted from SlidesAI (leehomyc/SlidesAI build_slides.py:162-219).

Original function returns CSS grid classes. This adaptation returns python-pptx
compatible layout parameters (column ratios, font sizes in Pt, zoom factors).
"""

from pptx.util import Pt, Inches


def calculate_table_layout(
    text: str,
    rows: int,
    cols: int,
) -> tuple[float, Pt, float]:
    """Analyze table dimensions to return layout parameters.

    Exact heuristic logic from SlidesAI calculate_table_layout().

    Args:
        text: Accompanying text content for the slide.
        rows: Number of data rows (excluding header).
        cols: Number of columns.

    Returns:
        (text_width_ratio, table_font_size, zoom_factor)
        - text_width_ratio: fraction of slide width for text (0.3-0.5)
        - table_font_size: Pt object for table cell text
        - zoom_factor: scaling factor for table dimensions
    """
    text_len = len(text) if text else 0

    text_width_ratio = 0.5
    table_font = Pt(16)
    zoom = 0.94

    # Case A: Massive Table (8+ cols or very tall)
    if cols >= 10 or rows > 17:
        text_width_ratio = 0.3
        table_font = Pt(11)
        zoom = 0.72
    elif cols >= 8 or rows > 15:
        text_width_ratio = 0.35
        table_font = Pt(11)
        zoom = 0.80
    # Case B: Wide Table (6-7 cols)
    elif cols >= 6:
        text_width_ratio = 0.4
        table_font = Pt(13)
        zoom = 0.88
    elif cols >= 4 or rows > 8:
        table_font = Pt(14)
        zoom = 0.90

    # Case C: Text Priority (Long text + moderate table)
    if text_len > 300 and cols < 8:
        text_width_ratio = 0.5
        if cols >= 6:
            table_font = Pt(12)
            zoom = 0.84
        elif cols >= 4:
            zoom = 0.88

    return text_width_ratio, table_font, zoom


def compute_column_widths(
    table_data: list[list[str]],
    total_width: int,
) -> list[int]:
    """Proportional column widths based on max content length per column.

    Exact logic from PPTAgent apis.py:330-338.

    Args:
        table_data: 2D list of cell text (including header row).
        total_width: Total available width in EMU.

    Returns:
        List of column widths in EMU.
    """
    if not table_data or not table_data[0]:
        return []

    cols = len(table_data[0])
    max_lengths = [
        max(len(row[j]) if j < len(row) else 0 for row in table_data)
        for j in range(cols)
    ]
    total_length = sum(max_lengths) or 1

    return [int((max_lengths[j] / total_length) * total_width) for j in range(cols)]
