"""Layout scheduler — assigns a layout class to each content slide so that
no two adjacent slides share a geometric class (constraint C2).

The scheduler reads each ``SlideContent`` and produces a *candidate preference
list* based on the content itself (e.g. chart data → chart layouts, table data
→ table layout, comparison subtitle → two-column compare). It then walks the
15-slide spine and, for each body slide, picks the highest-preference layout
whose class differs from the previous slide's class.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from step2.slide_plan_models import LayoutType, SlideType
from step3.content_models import SlideContent

from step4.layouts import CATALOG, LayoutEntry


# Ordered preference per content signature. First match wins for the candidate
# list; scheduler filters by adjacency + usage caps afterwards.
_PREFERENCE_BY_TYPE: dict[str, list[str]] = {
    "chart":      ["chart_focused", "chart_with_bullets"],
    "table":      ["table"],
    "divider":    ["section_divider", "quote_emphasis"],
    "timeline":   ["timeline", "process"],
    "compare":    ["two_column_compare"],
    "kpi":        ["kpi_big_numbers", "four_column_icons"],
    "process":    ["process", "timeline"],
    "bullets":    ["bullet_text", "three_column_grid", "four_column_icons"],
}


def _signature(content: SlideContent) -> str:
    """Tag each slide with a content signature used to rank layouts."""
    if content.chart_data is not None:
        return "chart"
    if content.table_data is not None:
        return "table"
    if content.slide_type == SlideType.TIMELINE or content.layout == LayoutType.TIMELINE:
        return "timeline"
    if content.slide_type == SlideType.COMPARISON or content.layout == LayoutType.COMPARISON:
        return "compare"
    if content.layout == LayoutType.PROCESS:
        return "process"
    if content.slide_type == SlideType.AGENDA or content.layout == LayoutType.DIVIDER:
        return "divider"

    bullets = _all_bullet_texts(content)
    if bullets and _looks_like_kpis(bullets):
        return "kpi"
    return "bullets"


def _all_bullet_texts(content: SlideContent) -> list[str]:
    texts = [b.text for b in content.bullets]
    for kp in content.key_points:
        texts.extend(kp.bullet_form)
    return texts


def _looks_like_kpis(bullets: list[str]) -> bool:
    """Detect KPI-shaped bullets: short with a leading number or percentage."""
    import re
    if not bullets:
        return False
    matches = sum(1 for b in bullets if re.match(r"\s*[\d$]+[\d,.%MBKk]*\s", b))
    return matches >= max(2, len(bullets) // 2)


def _candidates(content: SlideContent) -> list[str]:
    sig = _signature(content)
    primary = _PREFERENCE_BY_TYPE.get(sig, ["bullet_text"])
    fallback = ["bullet_text", "three_column_grid", "two_column_compare",
                "four_column_icons", "process", "kpi_big_numbers", "quote_emphasis"]
    out: list[str] = []
    for name in primary + fallback:
        if name not in out:
            out.append(name)
    return out


def schedule(body_slides: Iterable[SlideContent]) -> list[LayoutEntry]:
    """Return a layout entry for each body slide such that no two adjacent
    slides share a geometric class and over-used classes are de-prioritised.
    """
    slides = list(body_slides)
    assigned: list[LayoutEntry] = []
    last_class: str | None = None
    usage: dict[str, int] = defaultdict(int)
    max_class_usage = max(2, (len(slides) + 1) // 3)

    for content in slides:
        chosen: LayoutEntry | None = None
        for candidate_name in _candidates(content):
            entry = CATALOG[candidate_name]
            if entry.klass == last_class:
                continue
            if usage[entry.klass] >= max_class_usage:
                continue
            chosen = entry
            break

        if chosen is None:
            for name, entry in CATALOG.items():
                if entry.klass != last_class:
                    chosen = entry
                    break

        assert chosen is not None
        assigned.append(chosen)
        usage[chosen.klass] += 1
        last_class = chosen.klass

    return assigned
