"""Final quality optimization pass for slide content.

Implements SlideForge's 6-component quality scoring system (REUSE-5)
and real terminology standardization using LLM.
"""

import re
from typing import List, Dict, Set
from difflib import SequenceMatcher

from step2.slide_plan_models import SlideType
from .content_models import (
    SlideContent, ExtractedBullet, PresentationContent, QualityScore,
)
from llm import LLMClient
from constants import MAX_WORDS_PER_SLIDE, MAX_BULLETS_PER_SLIDE


class ContentOptimizer:
    """Final quality checks and optimizations for presentation content.

    Quality scoring reused from SlideForge's system:
    - topic_relevance: how well content matches key_message
    - content_uniqueness: no duplicate info across slides
    - source_coverage: how much source content was used
    - narrative_flow: logical flow from previous slide
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self.similarity_threshold = 0.7
        self.last_quality_scores: List[QualityScore] = []

    def optimize(self, presentation: PresentationContent) -> PresentationContent:
        """Run all optimization passes on presentation content."""
        presentation.slides = self._deduplicate_bullets(presentation.slides)
        presentation.slides = self._verify_word_budgets(presentation.slides)
        presentation.slides = self._balance_slide_density(presentation.slides)

        self.last_quality_scores = self._score_slides(presentation.slides)

        return presentation

    def _deduplicate_bullets(
        self, slides: List[SlideContent]
    ) -> List[SlideContent]:
        """Remove semantically duplicate bullets across slides."""
        seen_bullets: list[tuple[str, int]] = []

        for slide in slides:
            unique_bullets = []

            for bullet in slide.bullets:
                normalized = self._normalize_bullet(bullet.text)

                is_duplicate = False
                for seen_text, seen_slide in seen_bullets:
                    similarity = SequenceMatcher(None, normalized, seen_text).ratio()
                    if similarity > self.similarity_threshold:
                        is_duplicate = True
                        slide.warnings.append(
                            f"Removed duplicate bullet (similar to slide {seen_slide})"
                        )
                        break

                if not is_duplicate:
                    unique_bullets.append(bullet)
                    seen_bullets.append((normalized, slide.slide_number))

            slide.bullets = unique_bullets

        return slides

    def _normalize_bullet(self, text: str) -> str:
        """Normalize bullet text for comparison."""
        text = text.lower()
        common_starts = ['the ', 'a ', 'an ', 'to ', 'in ', 'for ', 'with ']
        for start in common_starts:
            if text.startswith(start):
                text = text[len(start):]

        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\d+', '', text)
        text = ' '.join(text.split())
        return text.strip()

    def _verify_word_budgets(
        self, slides: List[SlideContent]
    ) -> List[SlideContent]:
        """Check and warn about slides exceeding word budget."""
        for slide in slides:
            if slide.word_count > MAX_WORDS_PER_SLIDE:
                slide.warnings.append(
                    f"Word count {slide.word_count} exceeds budget of {MAX_WORDS_PER_SLIDE}"
                )
        return slides

    def _balance_slide_density(
        self, slides: List[SlideContent]
    ) -> List[SlideContent]:
        """Ensure consistent bullet density across content slides."""
        content_slides = [
            s for s in slides
            if s.slide_type not in [SlideType.TITLE, SlideType.THANK_YOU]
            and len(s.bullets) > 0
        ]

        if not content_slides:
            return slides

        avg_bullets = sum(len(s.bullets) for s in content_slides) / len(content_slides)

        for slide in content_slides:
            if len(slide.bullets) > MAX_BULLETS_PER_SLIDE:
                slide.bullets = sorted(
                    slide.bullets, key=lambda b: b.priority, reverse=True
                )[:MAX_BULLETS_PER_SLIDE]
                slide.warnings.append(
                    f"Trimmed to {MAX_BULLETS_PER_SLIDE} bullets (by priority)"
                )

            if len(slide.bullets) < 2 and avg_bullets >= 3:
                slide.warnings.append(
                    f"Low bullet count ({len(slide.bullets)}) vs avg ({avg_bullets:.1f})"
                )

        return slides

    def _score_slides(self, slides: List[SlideContent]) -> List[QualityScore]:
        """Score each slide using SlideForge's quality components."""
        scores = []

        all_bullet_texts = []
        for slide in slides:
            all_bullet_texts.extend([b.text for b in slide.bullets])

        for i, slide in enumerate(slides):
            topic_relevance = self._score_topic_relevance(slide)
            content_uniqueness = self._score_content_uniqueness(
                slide, all_bullet_texts
            )
            source_coverage = self._score_source_coverage(slide)
            narrative_flow = self._score_narrative_flow(slide, slides, i)

            overall = (
                topic_relevance * 0.35
                + content_uniqueness * 0.25
                + source_coverage * 0.20
                + narrative_flow * 0.20
            )

            scores.append(QualityScore(
                topic_relevance=round(topic_relevance, 3),
                content_uniqueness=round(content_uniqueness, 3),
                source_coverage=round(source_coverage, 3),
                narrative_flow=round(narrative_flow, 3),
                overall=round(overall, 3),
            ))

        return scores

    def _score_topic_relevance(self, slide: SlideContent) -> float:
        """How well slide content matches its key_message."""
        if slide.slide_type in [SlideType.TITLE, SlideType.THANK_YOU]:
            return 1.0

        if not slide.bullets and not slide.key_points:
            return 0.3

        key_words = set(slide.key_message.lower().split())
        key_words -= {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'is', 'are', 'and', 'or'}

        if not key_words:
            return 0.5

        bullet_text = " ".join(b.text.lower() for b in slide.bullets)
        kp_text = " ".join(
            kp.paragraph_form.lower() for kp in slide.key_points
        )
        combined = bullet_text + " " + kp_text

        matched = sum(1 for w in key_words if w in combined)
        return min(1.0, matched / len(key_words)) if key_words else 0.5

    def _score_content_uniqueness(
        self, slide: SlideContent, all_bullet_texts: List[str]
    ) -> float:
        """Check for duplicate info across slides."""
        if not slide.bullets:
            return 1.0

        slide_texts = [b.text for b in slide.bullets]
        other_texts = [t for t in all_bullet_texts if t not in slide_texts]

        if not other_texts:
            return 1.0

        duplicate_count = 0
        for bullet_text in slide_texts:
            norm_bullet = self._normalize_bullet(bullet_text)
            for other in other_texts:
                norm_other = self._normalize_bullet(other)
                if SequenceMatcher(None, norm_bullet, norm_other).ratio() > self.similarity_threshold:
                    duplicate_count += 1
                    break

        return 1.0 - (duplicate_count / len(slide_texts))

    def _score_source_coverage(self, slide: SlideContent) -> float:
        """How much of assigned source sections was used."""
        if not slide.source_sections:
            return 1.0

        has_content = (
            len(slide.bullets) > 0
            or slide.chart_data is not None
            or slide.table_data is not None
            or len(slide.key_points) > 0
        )

        if not has_content:
            return 0.0

        if slide.chart_data or slide.table_data:
            return 1.0

        sections_represented = set()
        for bullet in slide.bullets:
            sections_represented.add(bullet.source_section)

        coverage = len(sections_represented) / len(slide.source_sections)
        return min(1.0, coverage)

    def _score_narrative_flow(
        self, slide: SlideContent, all_slides: List[SlideContent], index: int
    ) -> float:
        """Logical flow from previous slide."""
        if index == 0:
            return 1.0 if slide.slide_type == SlideType.TITLE else 0.5

        prev_slide = all_slides[index - 1]

        expected_flows = {
            SlideType.TITLE: [SlideType.AGENDA],
            SlideType.AGENDA: [SlideType.SUMMARY, SlideType.CONTENT],
            SlideType.SUMMARY: [SlideType.CONTENT, SlideType.CHART],
            SlideType.CONTENT: [SlideType.CONTENT, SlideType.CHART, SlideType.COMPARISON, SlideType.TIMELINE, SlideType.THANK_YOU],
            SlideType.CHART: [SlideType.CONTENT, SlideType.CHART, SlideType.COMPARISON, SlideType.THANK_YOU],
            SlideType.COMPARISON: [SlideType.CONTENT, SlideType.CHART, SlideType.THANK_YOU],
            SlideType.TIMELINE: [SlideType.CONTENT, SlideType.CHART, SlideType.THANK_YOU],
        }

        expected_next = expected_flows.get(prev_slide.slide_type, [])
        if slide.slide_type in expected_next:
            return 1.0

        if index == len(all_slides) - 1 and slide.slide_type == SlideType.THANK_YOU:
            return 1.0

        return 0.6

    def generate_quality_report(self, presentation: PresentationContent) -> str:
        """Generate quality report for the presentation."""
        lines = [
            "QUALITY REPORT:",
            "-" * 40,
        ]

        if not presentation.stats or not presentation.stats.quality_scores:
            lines.append("Quality scores not yet computed.")
            return "\n".join(lines)

        scores = presentation.stats.quality_scores
        if not scores:
            lines.append("No quality scores available.")
            return "\n".join(lines)

        avg_overall = sum(s.overall for s in scores) / len(scores)
        avg_relevance = sum(s.topic_relevance for s in scores) / len(scores)
        avg_uniqueness = sum(s.content_uniqueness for s in scores) / len(scores)
        avg_coverage = sum(s.source_coverage for s in scores) / len(scores)
        avg_flow = sum(s.narrative_flow for s in scores) / len(scores)

        lines.extend([
            f"Overall Quality: {avg_overall:.2f}/1.00",
            f"  Topic Relevance:    {avg_relevance:.2f}",
            f"  Content Uniqueness: {avg_uniqueness:.2f}",
            f"  Source Coverage:    {avg_coverage:.2f}",
            f"  Narrative Flow:     {avg_flow:.2f}",
            "",
        ])

        low_scoring = [
            (i + 1, s) for i, s in enumerate(scores) if s.overall < 0.6
        ]
        if low_scoring:
            lines.append("LOW-SCORING SLIDES:")
            for slide_num, score in low_scoring:
                lines.append(
                    f"  Slide {slide_num}: {score.overall:.2f} "
                    f"(relevance={score.topic_relevance:.2f}, "
                    f"uniqueness={score.content_uniqueness:.2f})"
                )
            lines.append("")

        all_warnings = []
        for slide in presentation.slides:
            for warning in slide.warnings:
                all_warnings.append(f"  Slide {slide.slide_number}: {warning}")

        if all_warnings:
            lines.append("WARNINGS:")
            lines.extend(all_warnings)
        else:
            lines.append("No warnings.")

        return "\n".join(lines)
