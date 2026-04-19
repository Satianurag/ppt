"""Final quality optimization pass for slide content.

Implements SlideForge's full 6-component quality scoring system with exact
weights from aggregator.py (slide-forge-llm/rewards/aggregator.py:11-18):
  code_rules: 1.0, render_quality: 2.0, content_quality: 2.0,
  brief_reconstruction: 2.0, source_coverage: 1.5, narrative_flow: 1.0

Adapted for python-pptx context (no HTML slides — we score SlideContent objects).
"""

import re
from typing import List
from difflib import SequenceMatcher

from step2.slide_plan_models import SlideType
from .content_models import (
    SlideContent, ExtractedBullet, PresentationContent, QualityScore,
)
from llm import LLMClient
from constants import MAX_WORDS_PER_SLIDE, MAX_BULLETS_PER_SLIDE

# SlideForge aggregator.py:11-18 — exact weights
SLIDEFORGE_WEIGHTS: dict[str, float] = {
    "structural_rules": 1.0,       # code_rules
    "content_quality": 2.0,        # content_quality
    "render_quality": 2.0,         # render_quality
    "brief_reconstruction": 2.0,   # brief_reconstruction
    "source_coverage": 1.5,        # (our addition, maps to factual_grounding)
    "narrative_flow": 1.0,         # (our addition, maps to narrative flow subcomponent)
}

TOTAL_WEIGHT = sum(SLIDEFORGE_WEIGHTS.values())


class ContentOptimizer:
    """Final quality checks and optimizations for presentation content.

    Quality scoring uses SlideForge's full 6-component system with exact weights.
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

        self.last_quality_scores = self._score_slides(presentation)

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

    # ── SlideForge 6-Component Scoring ──────────────────────────────

    def _score_slides(self, presentation: PresentationContent) -> List[QualityScore]:
        """Score each slide using SlideForge's full 6-component system."""
        slides = presentation.slides
        scores = []

        all_bullet_texts = []
        for slide in slides:
            all_bullet_texts.extend([b.text for b in slide.bullets])

        for i, slide in enumerate(slides):
            structural = self._score_structural_rules(slide)
            content_q = self._score_content_quality(slide, all_bullet_texts, slides, i)
            render_q = self._score_render_quality(slide)
            brief_recon = self._score_brief_reconstruction(slide, presentation.title)
            source_cov = self._score_source_coverage(slide)
            narrative = self._score_narrative_flow(slide, slides, i)

            overall = (
                SLIDEFORGE_WEIGHTS["structural_rules"] * structural
                + SLIDEFORGE_WEIGHTS["content_quality"] * content_q
                + SLIDEFORGE_WEIGHTS["render_quality"] * render_q
                + SLIDEFORGE_WEIGHTS["brief_reconstruction"] * brief_recon
                + SLIDEFORGE_WEIGHTS["source_coverage"] * source_cov
                + SLIDEFORGE_WEIGHTS["narrative_flow"] * narrative
            ) / TOTAL_WEIGHT

            scores.append(QualityScore(
                structural_rules=round(structural, 3),
                content_quality=round(content_q, 3),
                render_quality=round(render_q, 3),
                brief_reconstruction=round(brief_recon, 3),
                source_coverage=round(source_cov, 3),
                narrative_flow=round(narrative, 3),
                overall=round(overall, 3),
            ))

        return scores

    def _score_structural_rules(self, slide: SlideContent) -> float:
        """SlideForge code_rules_reward adapted for SlideContent.

        4 components (0.25 each), exact logic from code_rules.py:35-61:
        - title_present (0.25)
        - section_count_adherence (0.25)
        - word_count_adherence (0.25)
        - non_empty_sections (0.25)
        """
        score = 0.0

        # Title present
        if slide.title and slide.title.strip():
            score += 0.25

        # Section count adherence (we use bullet count as proxy)
        if slide.slide_type in (SlideType.TITLE, SlideType.THANK_YOU):
            score += 0.25
        elif slide.bullets or slide.key_points or slide.chart_data or slide.table_data:
            bullet_count = len(slide.bullets) + len(slide.key_points)
            if 2 <= bullet_count <= MAX_BULLETS_PER_SLIDE:
                score += 0.25
            elif bullet_count > 0:
                score += 0.1

        # Word count adherence
        if slide.word_count > 0:
            target = MAX_WORDS_PER_SLIDE
            ratio = min(slide.word_count, target) / max(slide.word_count, target)
            score += 0.25 * ratio
        elif slide.slide_type in (SlideType.TITLE, SlideType.THANK_YOU):
            score += 0.25

        # Non-empty sections
        has_content = (
            len(slide.bullets) > 0
            or len(slide.key_points) > 0
            or slide.chart_data is not None
            or slide.table_data is not None
        )
        if has_content or slide.slide_type in (SlideType.TITLE, SlideType.THANK_YOU):
            score += 0.25

        return score

    def _score_content_quality(
        self, slide: SlideContent, all_bullet_texts: List[str],
        all_slides: List[SlideContent], index: int
    ) -> float:
        """SlideForge content_quality_reward adapted for SlideContent.

        4 sub-components with exact weights from content_quality.py:44-90:
        - topic_relevance (0.35)
        - factual_grounding (0.25) — we score based on source_sections coverage
        - content_uniqueness (0.20)
        - narrative_flow (0.20)
        """
        if slide.slide_type in (SlideType.TITLE, SlideType.THANK_YOU):
            return 1.0

        # Topic relevance (0.35) — from content_quality.py:30-44
        topic_score = self._topic_relevance_subscore(slide)

        # Factual grounding (0.25) — we check source section references
        grounding_score = 1.0 if slide.source_sections else 0.5

        # Content uniqueness (0.20) — from content_quality.py:72-84
        uniqueness_score = self._content_uniqueness_subscore(slide, all_bullet_texts)

        # Narrative flow (0.20) — from content_quality.py:86-90
        flow_score = self._narrative_subscore(slide, all_slides, index)

        return (
            0.35 * topic_score
            + 0.25 * grounding_score
            + 0.20 * uniqueness_score
            + 0.20 * flow_score
        )

    def _topic_relevance_subscore(self, slide: SlideContent) -> float:
        """How well slide content matches its key_message."""
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

    def _content_uniqueness_subscore(
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

    def _narrative_subscore(
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

    def _score_render_quality(self, slide: SlideContent) -> float:
        """Render quality — checks structural rendering readiness.

        Adapted from SlideForge render_quality_reward. In our python-pptx
        context, we check:
        - Has a layout assigned (0.25)
        - Title within char limits (0.25)
        - Bullet/key_point text within limits (0.25)
        - Content density appropriate (0.25)
        """
        score = 0.0

        # Layout assigned
        if slide.layout:
            score += 0.25

        # Title within limits
        if slide.title and len(slide.title) <= 50:
            score += 0.25
        elif slide.title:
            score += 0.1

        # Bullet text within limits
        if slide.bullets:
            within_limit = sum(1 for b in slide.bullets if len(b.text) <= 60)
            score += 0.25 * (within_limit / len(slide.bullets))
        elif slide.slide_type in (SlideType.TITLE, SlideType.THANK_YOU):
            score += 0.25
        elif slide.chart_data or slide.table_data:
            score += 0.25

        # Content density: not too empty, not too crowded
        if slide.slide_type in (SlideType.TITLE, SlideType.THANK_YOU):
            score += 0.25
        elif slide.word_count > 0:
            if 20 <= slide.word_count <= MAX_WORDS_PER_SLIDE:
                score += 0.25
            elif slide.word_count < 20:
                score += 0.1
            else:
                ratio = MAX_WORDS_PER_SLIDE / slide.word_count
                score += 0.25 * ratio

        return score

    def _score_brief_reconstruction(self, slide: SlideContent, presentation_title: str) -> float:
        """SlideForge brief_reconstruction adapted for SlideContent.

        Exact sub-weights from brief_reconstruction.py:88-135:
        - topic_similarity (0.40)
        - audience_match (0.25) — we approximate from key_message
        - slide_count_accuracy (0.15) — always 1.0 (we control slide count)
        - theme_coverage (0.20)
        """
        if slide.slide_type in (SlideType.TITLE, SlideType.THANK_YOU):
            return 1.0

        # Topic similarity (0.40)
        title_words = self._normalize_words(presentation_title)
        slide_words = self._normalize_words(slide.title + " " + slide.key_message)

        if title_words:
            topic_overlap = len(title_words & slide_words) / len(title_words)
        else:
            topic_overlap = 0.0
        topic_score = min(topic_overlap, 1.0)

        # Audience match (0.25) — approximated by key_message coherence
        audience_score = 0.7 if slide.key_message else 0.3

        # Slide count accuracy (0.15) — always good since we control it
        count_score = 1.0

        # Theme coverage (0.20) — check if bullet content relates to title
        bullet_words = set()
        for b in slide.bullets:
            bullet_words |= self._normalize_words(b.text)
        for kp in slide.key_points:
            bullet_words |= self._normalize_words(kp.paragraph_form)

        if title_words and bullet_words:
            theme_overlap = len(title_words & bullet_words) / len(title_words)
            theme_score = min(theme_overlap * 1.5, 1.0)
        else:
            theme_score = 0.5

        return (
            0.40 * topic_score
            + 0.25 * audience_score
            + 0.15 * count_score
            + 0.20 * theme_score
        )

    def _normalize_words(self, text: str) -> set[str]:
        """Lowercase, split, strip stop words. From brief_reconstruction.py:50-53."""
        stop = {"the", "a", "an", "is", "are", "and", "or", "of", "to", "in", "for", "on", "with", "-", "&"}
        return {w for w in text.lower().split() if w not in stop and len(w) > 1}

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
        """Logical flow from previous slide (standalone component)."""
        return self._narrative_subscore(slide, all_slides, index)

    # ── Report ──────────────────────────────────────────────────────

    def generate_quality_report(self, presentation: PresentationContent) -> str:
        """Generate quality report with full SlideForge 6-component breakdown."""
        lines = [
            "QUALITY REPORT (SlideForge 6-Component Scoring):",
            "-" * 50,
        ]

        if not presentation.stats or not presentation.stats.quality_scores:
            lines.append("Quality scores not yet computed.")
            return "\n".join(lines)

        scores = presentation.stats.quality_scores
        if not scores:
            lines.append("No quality scores available.")
            return "\n".join(lines)

        n = len(scores)
        avg_overall = sum(s.overall for s in scores) / n
        avg_structural = sum(s.structural_rules for s in scores) / n
        avg_content = sum(s.content_quality for s in scores) / n
        avg_render = sum(s.render_quality for s in scores) / n
        avg_brief = sum(s.brief_reconstruction for s in scores) / n
        avg_source = sum(s.source_coverage for s in scores) / n
        avg_flow = sum(s.narrative_flow for s in scores) / n

        lines.extend([
            f"Overall Quality: {avg_overall:.2f}/1.00",
            f"  Structural Rules (w=1.0):      {avg_structural:.2f}",
            f"  Content Quality (w=2.0):       {avg_content:.2f}",
            f"  Render Quality (w=2.0):        {avg_render:.2f}",
            f"  Brief Reconstruction (w=2.0):  {avg_brief:.2f}",
            f"  Source Coverage (w=1.5):        {avg_source:.2f}",
            f"  Narrative Flow (w=1.0):         {avg_flow:.2f}",
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
                    f"(structural={score.structural_rules:.2f}, "
                    f"content={score.content_quality:.2f}, "
                    f"render={score.render_quality:.2f})"
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
