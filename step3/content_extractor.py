"""Main orchestrator for content extraction (Step 3).

Removes all image handling. Uses AST tokens from Step 1.
Integrates dual-format content (PPTAgent content_organizer pattern).
"""

import time
from typing import List, Dict, Optional

from step1.models import ContentInventory, Section
from step2.slide_plan_models import PresentationPlan, SlidePlan, SlideType, LayoutType
from .content_models import (
    PresentationContent, SlideContent, ChartData, TableData,
    ExtractedBullet, ExtractionStats,
)
from .markdown_reparser import MarkdownReparser, SectionContent
from .chart_data_extractor import ChartDataExtractor
from .bullet_rewriter import BulletRewriter
from .content_optimizer import ContentOptimizer
from llm import LLMClient
from constants import SLIDE_BUDGET, MAX_BULLET_CHARS


class ContentExtractor:
    """Main orchestrator for Step 3: Content Extraction."""

    def __init__(self, client: LLMClient) -> None:
        """Initialize content extractor with all components.

        Args:
            client: LLMClient instance (required).
        """
        self.client = client
        self.reparser = MarkdownReparser()
        self.chart_extractor = ChartDataExtractor()
        self.bullet_rewriter = BulletRewriter(client)
        self.optimizer = ContentOptimizer()
        self.feedback_context: str = ""

        self.stats = {
            'llm_calls': 0,
            'tokens_used': 0,
            'start_time': None,
        }

    def extract(
        self,
        presentation_plan: PresentationPlan,
        markdown_text: str,
        inventory: ContentInventory,
        feedback_context: str = "",
    ) -> PresentationContent:
        """Main extraction method.

        Args:
            feedback_context: Reviewer feedback from a previous attempt (PPTAgent
                retry-with-feedback pattern). Passed to LLM prompts so the model
                can correct issues identified in the prior run.
        """
        self.stats['start_time'] = time.time()
        self.feedback_context = feedback_context

        sections_content = self.reparser.reparse_sections(markdown_text, inventory)
        ast_tokens = inventory.get_ast_tokens()

        slides: List[SlideContent] = []
        all_charts: List[ChartData] = []

        for slide_plan in presentation_plan.slides:
            source_sections = [
                sections_content[sid]
                for sid in slide_plan.source_sections
                if sid in sections_content
            ]

            merge_reasoning = presentation_plan.merge_reasoning

            slide_content = self._extract_slide_content(
                slide_plan, source_sections, inventory,
                markdown_text, merge_reasoning, ast_tokens,
            )
            slides.append(slide_content)

            if slide_content.chart_data:
                all_charts.append(slide_content.chart_data)

        # Fix 10: Enforce chart type diversity — prevent duplicate chart types
        self._enforce_chart_diversity(slides)

        # Rebuild chart list after diversity pass
        all_charts = [s.chart_data for s in slides if s.chart_data]

        presentation = PresentationContent(
            title=presentation_plan.title,
            total_slides=len(slides),
            slides=slides,
            charts=all_charts,
        )

        presentation = self.optimizer.optimize(presentation)

        extraction_time = time.time() - self.stats['start_time']
        presentation.stats = self._build_stats(presentation, extraction_time)

        return presentation

    def _extract_slide_content(
        self,
        slide_plan: SlidePlan,
        source_sections: List[SectionContent],
        inventory: ContentInventory,
        markdown_text: str,
        merge_reasoning: Optional[Dict[str, str]],
        ast_tokens: Optional[list],
    ) -> SlideContent:
        """Extract content for a single slide."""
        slide_content = SlideContent(
            slide_number=slide_plan.slide_number,
            slide_type=slide_plan.type,
            layout=slide_plan.layout,
            title=slide_plan.title,
            subtitle=slide_plan.subtitle,
            key_message=slide_plan.key_message,
            source_sections=slide_plan.source_sections,
            warnings=[],
        )

        if slide_plan.content_type == "chart" and slide_plan.chart_config:
            chart_data = self._extract_chart_content(
                slide_plan, inventory, markdown_text, ast_tokens,
            )
            slide_content.chart_data = chart_data

            if slide_plan.bullet_points:
                slide_content.bullets = [
                    ExtractedBullet(
                        text=bp[:MAX_BULLET_CHARS],
                        priority=10 - i,
                        source_section=slide_plan.source_sections[0] if slide_plan.source_sections else "auto",
                    )
                    for i, bp in enumerate(slide_plan.bullet_points[:6])
                ]
            elif source_sections:
                bullets = self._extract_bullets_for_slide(
                    source_sections, slide_plan.key_message, merge_reasoning,
                )
                slide_content.bullets = bullets

        elif slide_plan.content_type == "table":
            table_data = self._extract_table_content(
                slide_plan, inventory, markdown_text, ast_tokens,
            )
            slide_content.table_data = table_data

        elif slide_plan.content_type == "bullet":
            if slide_plan.bullet_points:
                slide_content.bullets = [
                    ExtractedBullet(
                        text=bp[:MAX_BULLET_CHARS],
                        priority=10 - i,
                        source_section=slide_plan.source_sections[0] if slide_plan.source_sections else "plan",
                    )
                    for i, bp in enumerate(slide_plan.bullet_points[:6])
                ]
            elif source_sections:
                bullets = self._extract_bullets_for_slide(
                    source_sections, slide_plan.key_message, merge_reasoning,
                )
                slide_content.bullets = bullets
                # Fix 8: Removed redundant extract_key_points() call.
                # Bullets already contain the same content — the extra LLM call
                # duplicated work and wasted ~1 API call per bullet slide.

        if slide_plan.type in [SlideType.TITLE, SlideType.THANK_YOU]:
            slide_content.confidence_score = 1.0

        slide_content.extraction_method = "llm"
        slide_content.word_count = self._calculate_word_count(slide_content)

        return slide_content

    # ── Chart diversity (Fix 10) ─────────────────────────────────────

    # Narrative priority: temporal trends first, then comparisons, then rankings
    _CHART_PRIORITY = {
        "LINE": 1,       # temporal trends — highest priority
        "BAR": 2,        # comparisons
        "HORIZONTAL_BAR": 2,
        "GROUPED_BAR": 3,
        "PIE": 4,        # proportions
        "DONUT": 4,
    }

    def _enforce_chart_diversity(self, slides: List[SlideContent]) -> None:
        """Prevent duplicate chart types and reorder by narrative priority.

        If two slides have the same chart type, the second one gets its
        chart_type swapped to an unused alternative (BAR↔HORIZONTAL_BAR,
        PIE↔DONUT, etc.).
        """
        from step2.slide_plan_models import ChartType

        seen_types: set[str] = set()
        swap_map = {
            ChartType.BAR: ChartType.HORIZONTAL_BAR,
            ChartType.HORIZONTAL_BAR: ChartType.BAR,
            ChartType.PIE: ChartType.DONUT,
            ChartType.DONUT: ChartType.PIE,
            ChartType.GROUPED_BAR: ChartType.BAR,
        }

        for slide in slides:
            if slide.chart_data is None:
                continue
            ct = slide.chart_data.chart_type
            ct_name = ct.value if hasattr(ct, 'value') else str(ct)
            if ct_name in seen_types:
                alt = swap_map.get(ct)
                if alt and alt.value not in seen_types:
                    slide.chart_data.chart_type = alt
                    ct_name = alt.value
            seen_types.add(ct_name)

    def _extract_chart_content(
        self,
        slide_plan: SlidePlan,
        inventory: ContentInventory,
        markdown_text: str,
        ast_tokens: Optional[list],
    ) -> Optional[ChartData]:
        """Extract chart data from table."""
        if not slide_plan.chart_config:
            return None

        table_index = slide_plan.chart_config.table_index
        chart_type = slide_plan.chart_config.chart_type
        chart_title = slide_plan.chart_config.title

        table_data = self.reparser.find_table_by_index(
            markdown_text, table_index, ast_tokens,
        )

        if table_data:
            inventory_table_info = None
            for section in inventory.sections:
                for t in section.tables:
                    if t.index == table_index:
                        inventory_table_info = {
                            'numeric_columns': t.numeric_columns,
                            'temporal_columns': t.temporal_columns,
                        }
                        break
                if inventory_table_info:
                    break

            # Use suggest_chart_type to validate/override the triage agent's choice
            suggested = self.chart_extractor.suggest_chart_type(table_data)
            if chart_type != suggested:
                print(f"  [Extractor] Slide {slide_plan.slide_number}: "
                      f"overriding chart type {chart_type.value} -> {suggested.value} "
                      f"(data-driven suggestion)")
                chart_type = suggested

            return self.chart_extractor.extract_chart_data(
                table_data, chart_type, table_index, chart_title, inventory_table_info,
            )

        return None

    def _extract_table_content(
        self,
        slide_plan: SlidePlan,
        inventory: ContentInventory,
        markdown_text: str,
        ast_tokens: Optional[list],
    ) -> Optional[TableData]:
        """Extract non-chart table content."""
        for section_id in slide_plan.source_sections:
            for inv_section in inventory.sections:
                if inv_section.id == section_id and inv_section.tables:
                    table_info = inv_section.tables[0]
                    table_data = self.reparser.find_table_by_index(
                        markdown_text, table_info.index, ast_tokens,
                    )

                    if table_data and len(table_data) >= 2:
                        return TableData(
                            headers=table_data[0],
                            rows=table_data[1:],
                            source_table_index=table_info.index,
                            has_numeric_columns=table_info.numeric_columns,
                            zebra_stripes=True,
                            bold_headers=True,
                        )

        return None

    def _extract_bullets_for_slide(
        self,
        source_sections: List[SectionContent],
        key_message: str,
        merge_reasoning: Optional[Dict[str, str]],
    ) -> List[ExtractedBullet]:
        """Extract bullets from source sections."""
        if not source_sections:
            return []

        merge_reason = None
        if merge_reasoning:
            for key in merge_reasoning:
                if any(s.section_id in key for s in source_sections):
                    merge_reason = merge_reasoning[key]
                    break

        feedback = self.feedback_context

        if len(source_sections) == 1:
            section = source_sections[0]
            source_text = section.get_all_text()

            bullets = self.bullet_rewriter.rewrite_bullets(
                source_text=source_text,
                key_message=key_message,
                section_id=section.section_id,
                feedback_context=feedback,
            )
            self.stats['llm_calls'] += 1
        else:
            bullets = self.bullet_rewriter.rewrite_merged_sections(
                sections=source_sections,
                key_message=key_message,
                merge_reasoning=merge_reason or "Multiple sections combined",
                feedback_context=feedback,
            )
            self.stats['llm_calls'] += 1

        # Polish pass for consistency and impact
        if bullets:
            raw_texts = [b.text for b in bullets]
            polished = self.bullet_rewriter.polish_bullets(raw_texts, key_message)
            self.stats['llm_calls'] += 1
            for i, b in enumerate(bullets):
                if i < len(polished):
                    b.text = polished[i]

        return bullets

    def _calculate_word_count(self, slide: SlideContent) -> int:
        """Calculate total word count for slide."""
        count = len(slide.title.split())

        if slide.subtitle:
            count += len(slide.subtitle.split())

        for bullet in slide.bullets:
            count += len(bullet.text.split())

        return count

    def _build_stats(
        self,
        presentation: PresentationContent,
        extraction_time: float,
    ) -> ExtractionStats:
        """Build extraction statistics."""
        slides_with_llm = len(presentation.slides)
        charts = len(presentation.charts)
        tables = sum(1 for s in presentation.slides if s.table_data)
        total_words = sum(s.word_count for s in presentation.slides)

        all_warnings = []
        for slide in presentation.slides:
            all_warnings.extend(slide.warnings)

        return ExtractionStats(
            total_slides=len(presentation.slides),
            slides_with_llm=slides_with_llm,
            charts_extracted=charts,
            tables_extracted=tables,
            total_word_count=total_words,
            avg_words_per_slide=total_words / len(presentation.slides) if presentation.slides else 0,
            llm_api_calls=self.stats['llm_calls'],
            llm_tokens_used=self.stats.get('tokens_used', 0),
            extraction_time_seconds=extraction_time,
            warnings=all_warnings,
        )

