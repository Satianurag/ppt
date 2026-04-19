"""Auto font sizing — exact copy from SlidesAI (leehomyc/SlidesAI build_slides.py:42-88).

Four variants for different layout contexts:
- auto_font_size: standard scaling for general content
- auto_font_size_gentle: minimal shrinking for full-width text slides
- auto_font_size_aggressive: moderate shrinking for 2-column slides
- auto_font_size_aggressive2: maximum shrinking for tight 2-column layouts
"""

from pptx.util import Pt


def auto_font_size(text: str, base: float = 27.0, min_size: float = 17.0, max_chars: float = 250.0) -> float:
    """Automatically scales text size based on character count.

    Exact copy from SlidesAI build_slides.py:75-88.

    Args:
        text: The text content to size.
        base: Default font size when text is short.
        min_size: Minimum allowed font size.
        max_chars: Number of characters before scaling kicks in.

    Returns:
        Computed font size as a float (in points).
    """
    length = len(text)
    if length <= max_chars:
        return base

    ratio = max(min_size / base, max_chars / length)
    return int(base * ratio)


def auto_font_size_gentle(text: str, base: float = 27.0, min_size: float = 20.0, max_chars: float = 350.0) -> float:
    """Shrink very gently for full-width text slides.

    Exact copy from SlidesAI build_slides.py:64-72.
    """
    if not text:
        return base
    length = len(text)
    if length <= max_chars:
        return base
    ratio = max(min_size / base, max_chars / length)
    return int(base * ratio)


def auto_font_size_aggressive(text: str, base: float = 24.0, min_size: float = 14.0, max_chars: float = 170.0) -> float:
    """Shrink more aggressively for 2-column slides.

    Exact copy from SlidesAI build_slides.py:53-61.
    """
    if not text:
        return base
    length = len(text)
    if length <= max_chars:
        return base
    ratio = max(min_size / base, max_chars / length)
    return max(int(base * ratio), int(min_size))


def auto_font_size_aggressive2(text: str, base: float = 24.0, min_size: float = 13.0, max_chars: float = 150.0) -> float:
    """Shrink most aggressively for tight 2-column layouts.

    Exact copy from SlidesAI build_slides.py:42-50.
    """
    if not text:
        return base
    length = len(text)
    if length <= max_chars:
        return base
    ratio = max(min_size / base, max_chars / length)
    return max(int(base * ratio), int(min_size))


def auto_font_size_pt(text: str, context: str = "body") -> Pt:
    """Convenience wrapper returning Pt for python-pptx integration.

    Args:
        text: The text content.
        context: One of 'body', 'full_width', 'two_col', 'tight_col', 'table'.
    """
    sizing_map = {
        "body": auto_font_size,
        "full_width": auto_font_size_gentle,
        "two_col": auto_font_size_aggressive,
        "tight_col": auto_font_size_aggressive2,
        "table": lambda t: auto_font_size_aggressive2(t, base=18.0, min_size=10.0, max_chars=100.0),
    }
    fn = sizing_map.get(context, auto_font_size)
    size = fn(text)
    return Pt(size)
