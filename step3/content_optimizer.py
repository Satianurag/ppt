"""Content mutation pass — runs before rendering.

Performs three deterministic passes on the extracted ``PresentationContent``:

1. Deduplicate semantically similar bullets across slides.
2. Warn when word count exceeds budget.
3. Balance slide density by trimming over-full slides by bullet priority.

Quality scoring lives in ``step4.assertions`` — this module is pure mutation.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List

from step2.slide_plan_models import SlideType

from .content_models import PresentationContent, SlideContent
from constants import MAX_BULLETS_PER_SLIDE, MAX_WORDS_PER_SLIDE


_COMMON_STARTS = ("the ", "a ", "an ", "to ", "in ", "for ", "with ")


def _normalize_bullet(text: str) -> str:
    text = text.lower()
    for start in _COMMON_STARTS:
        if text.startswith(start):
            text = text[len(start):]
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\d+", "", text)
    return " ".join(text.split()).strip()


def _deduplicate_bullets(slides: List[SlideContent], similarity_threshold: float = 0.7) -> List[SlideContent]:
    seen: list[tuple[str, int]] = []
    for slide in slides:
        uniq = []
        for bullet in slide.bullets:
            norm = _normalize_bullet(bullet.text)
            duplicate = False
            for seen_text, seen_slide in seen:
                if SequenceMatcher(None, norm, seen_text).ratio() > similarity_threshold:
                    duplicate = True
                    slide.warnings.append(
                        f"Removed duplicate bullet (similar to slide {seen_slide})"
                    )
                    break
            if not duplicate:
                uniq.append(bullet)
                seen.append((norm, slide.slide_number))
        slide.bullets = uniq
    return slides


def _verify_word_budgets(slides: List[SlideContent]) -> List[SlideContent]:
    for slide in slides:
        if slide.word_count > MAX_WORDS_PER_SLIDE:
            slide.warnings.append(
                f"Word count {slide.word_count} exceeds budget of {MAX_WORDS_PER_SLIDE}"
            )
    return slides


def _balance_slide_density(slides: List[SlideContent]) -> List[SlideContent]:
    content_slides = [
        s for s in slides
        if s.slide_type not in (SlideType.TITLE, SlideType.THANK_YOU) and s.bullets
    ]
    if not content_slides:
        return slides

    for slide in content_slides:
        if len(slide.bullets) > MAX_BULLETS_PER_SLIDE:
            slide.bullets = sorted(slide.bullets, key=lambda b: b.priority, reverse=True)[:MAX_BULLETS_PER_SLIDE]
            slide.warnings.append(f"Trimmed to {MAX_BULLETS_PER_SLIDE} bullets (by priority)")
    return slides


class ContentOptimizer:
    """Stateless wrapper around the three mutation passes."""

    def __init__(self) -> None:
        pass

    def optimize(self, presentation: PresentationContent) -> PresentationContent:
        presentation.slides = _deduplicate_bullets(presentation.slides)
        presentation.slides = _verify_word_budgets(presentation.slides)
        presentation.slides = _balance_slide_density(presentation.slides)
        return presentation
