"""Main orchestrator for content extraction (Step 3)."""

import time
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from step1.models import ContentInventory, ImageInfo, Section
from step2.slide_plan_models import PresentationPlan, SlidePlan, SlideType, LayoutType
from .content_models import (
    PresentationContent, SlideContent, ChartData, TableData,
    SlideImage, ExtractedBullet, ExtractionStats
)
from .markdown_reparser import MarkdownReparser, SectionContent
from .chart_data_extractor import ChartDataExtractor
from .bullet_rewriter import BulletRewriter
from .image_assigner import ImageAssigner
from .content_optimizer import ContentOptimizer
from llm import get_llm_client, LLMClient


class ContentExtractor:
    """
    Main orchestrator for Step 3: Content Extraction.
    
    Transforms slide plans into slide-ready content with:
    - Extracted and rewritten bullets
    - Parsed chart data from tables
    - Assigned images
    - Quality optimization
    """
    
    def __init__(self, client: Optional[LLMClient] = None):
        """Initialize content extractor with all components."""
        self.reparser = MarkdownReparser()
        self.chart_extractor = ChartDataExtractor()
        self.bullet_rewriter = BulletRewriter(client)
        self.image_assigner = ImageAssigner()
        self.optimizer = ContentOptimizer()
        
        self.stats = {
            'llm_calls': 0,
            'tokens_used': 0,
            'start_time': None
        }
    
    def extract(
        self,
        presentation_plan: PresentationPlan,
        markdown_text: str,
        inventory: ContentInventory
    ) -> PresentationContent:
        """
        Main extraction method.
        
        Args:
            presentation_plan: Slide plan from Step 2
            markdown_text: Original markdown content
            inventory: Content inventory from Step 1
            
        Returns:
            PresentationContent with all extracted slide content
        """
        self.stats['start_time'] = time.time()
        
        # Step 1: Re-parse markdown to get raw section content
        sections_content = self.reparser.reparse_sections(markdown_text, inventory)
        
        # Step 2: Extract content for each slide
        slide_contents = []
        for slide_plan in presentation_plan.slides:
            slide_content = self._extract_slide_content(
                slide_plan,
                sections_content,
                inventory,
                markdown_text,
                presentation_plan.merge_reasoning  # Pass from parent plan
            )
            slide_contents.append(slide_content)
        
        # Step 3: Assign images to slides
        # Collect all images from inventory
        all_images = []
        for section in inventory.sections:
            all_images.extend(section.images)
        
        slide_contents, unassigned_images = self.image_assigner.assign_images(
            slide_contents,
            inventory.sections,
            all_images
        )
        
        # Collect chart data for reference
        charts = [s.chart_data for s in slide_contents if s.chart_data]
        
        # Build initial presentation content
        presentation = PresentationContent(
            title=presentation_plan.title,
            total_slides=len(slide_contents),
            slides=slide_contents,
            charts=charts,
            unassigned_images=unassigned_images
        )
        
        # Step 4: Quality optimization pass
        presentation = self.optimizer.optimize_presentation(presentation)
        
        # Step 5: Build stats
        extraction_time = time.time() - self.stats['start_time']
        presentation.stats = self._build_stats(
            presentation,
            extraction_time
        )
        
        return presentation
    
    def extract_from_file(
        self,
        presentation_plan: PresentationPlan,
        markdown_path: Path,
        inventory: ContentInventory
    ) -> PresentationContent:
        """Convenience method to extract from file."""
        markdown_text = markdown_path.read_text(encoding='utf-8')
        return self.extract(presentation_plan, markdown_text, inventory)
    
    def _extract_slide_content(
        self,
        slide_plan: SlidePlan,
        sections_content: Dict[str, SectionContent],
        inventory: ContentInventory,
        markdown_text: str,
        merge_reasoning: Dict[str, str] = None
    ) -> SlideContent:
        """Extract content for a single slide."""
        
        # Get source sections
        source_sections = []
        for section_id in slide_plan.source_sections:
            if section_id in sections_content:
                source_sections.append(sections_content[section_id])
        
        # Initialize slide content
        slide_content = SlideContent(
            slide_number=slide_plan.slide_number,
            slide_type=slide_plan.type,
            layout=slide_plan.layout,
            title=slide_plan.title,
            subtitle=slide_plan.subtitle,
            key_message=slide_plan.key_message,
            source_sections=slide_plan.source_sections,
            images=[],  # Will be assigned later
            warnings=[]
        )
        
        # Extract content based on type
        if slide_plan.content_type == "chart" and slide_plan.chart_config:
            # Extract chart data
            chart_data = self._extract_chart_content(
                slide_plan,
                inventory,
                markdown_text
            )
            slide_content.chart_data = chart_data
            
            # Also extract bullets if specified
            if slide_plan.bullet_points:
                slide_content.bullets = [
                    ExtractedBullet(
                        text=bp,
                        priority=10 - i,
                        source_section=slide_plan.source_sections[0] if slide_plan.source_sections else "auto"
                    )
                    for i, bp in enumerate(slide_plan.bullet_points[:6])
                ]
            elif source_sections:
                # Generate supporting bullets
                bullets = self._extract_bullets_for_slide(
                    source_sections,
                    slide_plan.key_message,
                    merge_reasoning
                )
                slide_content.bullets = bullets
        
        elif slide_plan.content_type == "table":
            # Extract table data
            table_data = self._extract_table_content(slide_plan, inventory, markdown_text)
            slide_content.table_data = table_data
        
        elif slide_plan.content_type == "bullet":
            # Extract/rewrite bullets
            if slide_plan.bullet_points:
                # Use pre-defined bullets from plan
                slide_content.bullets = [
                    ExtractedBullet(
                        text=bp,
                        priority=10 - i,
                        source_section=slide_plan.source_sections[0] if slide_plan.source_sections else "plan"
                    )
                    for i, bp in enumerate(slide_plan.bullet_points[:6])
                ]
            elif source_sections:
                # Generate bullets from content
                bullets = self._extract_bullets_for_slide(
                    source_sections,
                    slide_plan.key_message,
                    merge_reasoning
                )
                slide_content.bullets = bullets
        
        # For title/agenda/thank you slides, minimal content
        if slide_plan.type in [SlideType.TITLE, SlideType.THANK_YOU]:
            slide_content.extraction_method = "rule_based"
            slide_content.confidence_score = 1.0
        
        # Calculate word count
        slide_content.word_count = self._calculate_word_count(slide_content)
        
        return slide_content
    
    def _extract_chart_content(
        self,
        slide_plan: SlidePlan,
        inventory: ContentInventory,
        markdown_text: str
    ) -> Optional[ChartData]:
        """Extract chart data from table."""
        if not slide_plan.chart_config:
            return None
        
        table_index = slide_plan.chart_config.table_index
        chart_type = slide_plan.chart_config.chart_type
        chart_title = slide_plan.chart_config.title
        
        # Find table in markdown
        table_data = self.reparser.find_table_by_index(markdown_text, table_index)
        
        if not table_data:
            # Try to find table info in inventory
            table_info = None
            for section in inventory.sections:
                for t in section.tables:
                    if t.index == table_index:
                        table_info = t
                        break
                if table_info:
                    break
            
            if table_info:
                # Use inventory metadata
                table_data = [["Column"]]  # Placeholder
        
        if table_data:
            # Get table info from inventory if available
            inventory_table_info = None
            for section in inventory.sections:
                for t in section.tables:
                    if t.index == table_index:
                        inventory_table_info = {
                            'numeric_columns': t.numeric_columns,
                            'temporal_columns': t.temporal_columns
                        }
                        break
                if inventory_table_info:
                    break
            
            return self.chart_extractor.extract_chart_data(
                table_data,
                chart_type,
                table_index,
                chart_title,
                inventory_table_info
            )
        
        return None
    
    def _extract_table_content(
        self,
        slide_plan: SlidePlan,
        inventory: ContentInventory,
        markdown_text: str
    ) -> Optional[TableData]:
        """Extract non-chart table content."""
        # Find first table in source sections
        for section_id in slide_plan.source_sections:
            for inv_section in inventory.sections:
                if inv_section.id == section_id and inv_section.tables:
                    # Use first table
                    table_info = inv_section.tables[0]
                    table_data = self.reparser.find_table_by_index(
                        markdown_text, table_info.index
                    )
                    
                    if table_data and len(table_data) >= 2:
                        return TableData(
                            headers=table_data[0],
                            rows=table_data[1:],
                            source_table_index=table_info.index,
                            has_numeric_columns=table_info.numeric_columns,
                            zebra_stripes=True,
                            bold_headers=True
                        )
        
        return None
    
    def _extract_bullets_for_slide(
        self,
        source_sections: List[SectionContent],
        key_message: str,
        merge_reasoning: Optional[Dict[str, str]]
    ) -> List[ExtractedBullet]:
        """
        Extract bullets from source sections.
        
        Strategy:
        - Single section: Use LLM to rewrite
        - Multiple sections: Use LLM to synthesize
        """
        if not source_sections:
            return []
        
        # Get merge reasoning for this slide if available
        merge_reason = None
        if merge_reasoning:
            for key in merge_reasoning:
                if any(s.section_id in key for s in source_sections):
                    merge_reason = merge_reasoning[key]
                    break
        
        if len(source_sections) == 1:
            # Single section - rewrite bullets
            section = source_sections[0]
            source_text = section.get_all_text()
            
            bullets = self.bullet_rewriter.rewrite_bullets(
                source_text=source_text,
                key_message=key_message,
                section_id=section.section_id,
                max_bullets=6,
                max_words_per_bullet=8
            )
            
            self.stats['llm_calls'] += 1
            
            return bullets
        
        else:
            # Multiple sections - synthesize
            bullets = self.bullet_rewriter.rewrite_merged_sections(
                sections=source_sections,
                key_message=key_message,
                merge_reasoning=merge_reason or "Multiple sections combined",
                max_bullets=6,
                max_words_per_bullet=8
            )
            
            self.stats['llm_calls'] += 1
            
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
        extraction_time: float
    ) -> ExtractionStats:
        """Build extraction statistics."""
        slides_with_llm = sum(
            1 for s in presentation.slides
            if s.extraction_method in ["llm", "hybrid"]
        )
        
        slides_rule_based = sum(
            1 for s in presentation.slides
            if s.extraction_method == "rule_based"
        )
        
        charts = len(presentation.charts)
        tables = sum(1 for s in presentation.slides if s.table_data)
        
        images_assigned = sum(len(s.images) for s in presentation.slides)
        
        total_words = sum(s.word_count for s in presentation.slides)
        
        all_warnings = []
        for slide in presentation.slides:
            all_warnings.extend(slide.warnings)
        
        return ExtractionStats(
            total_slides=len(presentation.slides),
            slides_with_llm=slides_with_llm,
            slides_rule_based=slides_rule_based,
            charts_extracted=charts,
            tables_extracted=tables,
            images_assigned=images_assigned,
            images_unassigned=len(presentation.unassigned_images),
            total_word_count=total_words,
            avg_words_per_slide=total_words / len(presentation.slides) if presentation.slides else 0,
            llm_api_calls=self.stats['llm_calls'],
            llm_tokens_used=self.stats.get('tokens_used', 0),
            extraction_time_seconds=extraction_time,
            warnings=all_warnings
        )
    
    def generate_report(self, presentation: PresentationContent) -> str:
        """Generate a comprehensive extraction report."""
        lines = [
            "=" * 70,
            "STEP 3: CONTENT EXTRACTION REPORT",
            "=" * 70,
            ""
        ]
        
        # Overview
        lines.extend([
            f"Presentation: {presentation.title}",
            f"Total Slides: {presentation.total_slides}",
            f"Extraction Time: {presentation.stats.extraction_time_seconds:.2f}s",
            ""
        ])
        
        # Content summary
        lines.extend([
            "CONTENT SUMMARY:",
            "-" * 40,
            f"Slides with LLM rewriting: {presentation.stats.slides_with_llm}",
            f"Slides rule-based: {presentation.stats.slides_rule_based}",
            f"Charts extracted: {presentation.stats.charts_extracted}",
            f"Tables extracted: {presentation.stats.tables_extracted}",
            f"Images assigned: {presentation.stats.images_assigned}",
            f"Images unassigned: {presentation.stats.images_unassigned}",
            f"Total words: {presentation.stats.total_word_count}",
            f"Avg words/slide: {presentation.stats.avg_words_per_slide:.1f}",
            f"LLM API calls: {presentation.stats.llm_api_calls}",
            ""
        ])
        
        # Per-slide breakdown
        lines.extend([
            "PER-SLIDE BREAKDOWN:",
            "-" * 40
        ])
        
        for slide in presentation.slides:
            content_types = []
            if slide.bullets:
                content_types.append(f"{len(slide.bullets)} bullets")
            if slide.chart_data:
                content_types.append(f"chart ({slide.chart_data.chart_type.value})")
            if slide.table_data:
                content_types.append("table")
            if slide.images:
                content_types.append(f"{len(slide.images)} images")
            
            content_str = ", ".join(content_types) if content_types else "(title slide)"
            
            lines.append(
                f"Slide {slide.slide_number}: {slide.title[:40]}... "
                f"[{content_str}] ({slide.word_count} words)"
            )
        
        lines.append("")
        
        # Quality report from optimizer
        if hasattr(self, 'optimizer'):
            quality_report = self.optimizer.generate_quality_report(presentation)
            lines.append(quality_report)
        
        return "\n".join(lines)
