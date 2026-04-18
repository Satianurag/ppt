"""Final quality optimization pass for slide content."""

from typing import List, Dict, Set, Tuple, Optional
from difflib import SequenceMatcher

from step2.slide_plan_models import LayoutType
from .content_models import SlideContent, ExtractedBullet, PresentationContent


class ContentOptimizer:
    """Final quality checks and optimizations for presentation content."""
    
    def __init__(self):
        self.similarity_threshold = 0.7  # For deduplication
    
    def optimize_presentation(
        self,
        presentation: PresentationContent
    ) -> PresentationContent:
        """
        Run all optimization passes on presentation content.
        
        Optimizations:
        1. Deduplicate bullets across slides
        2. Ensure consistent terminology
        3. Verify word budgets
        4. Balance slide density
        5. Check narrative flow
        """
        # Run optimizations in sequence
        presentation.slides = self._deduplicate_bullets(presentation.slides)
        presentation.slides = self._standardize_terminology(presentation.slides)
        presentation.slides = self._verify_word_budgets(presentation.slides)
        presentation.slides = self._balance_slide_density(presentation.slides)
        
        # Update overall word count
        total_words = sum(s.word_count for s in presentation.slides)
        if presentation.stats:
            presentation.stats.total_word_count = total_words
            presentation.stats.avg_words_per_slide = total_words / len(presentation.slides) if presentation.slides else 0
        
        return presentation
    
    def _deduplicate_bullets(
        self,
        slides: List[SlideContent]
    ) -> List[SlideContent]:
        """
        Remove semantically duplicate bullets across slides.
        
        Uses simple string similarity. For production, could use embeddings.
        """
        seen_bullets = []  # List of (normalized_text, slide_number)
        
        for slide in slides:
            unique_bullets = []
            
            for bullet in slide.bullets:
                normalized = self._normalize_bullet(bullet.text)
                
                # Check for duplicates
                is_duplicate = False
                for seen_text, seen_slide in seen_bullets:
                    similarity = SequenceMatcher(None, normalized, seen_text).ratio()
                    if similarity > self.similarity_threshold:
                        is_duplicate = True
                        # Add warning
                        slide.warnings.append(
                            f"Bullet '{bullet.text[:30]}...' similar to slide {seen_slide}"
                        )
                        break
                
                if not is_duplicate:
                    unique_bullets.append(bullet)
                    seen_bullets.append((normalized, slide.slide_number))
            
            slide.bullets = unique_bullets
        
        return slides
    
    def _normalize_bullet(self, text: str) -> str:
        """Normalize bullet text for comparison."""
        # Lowercase
        text = text.lower()
        
        # Remove common leading words
        common_starts = ['the ', 'a ', 'an ', 'to ', 'in ', 'for ', 'with ']
        for start in common_starts:
            if text.startswith(start):
                text = text[len(start):]
        
        # Remove numbers and punctuation
        import re
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\d+', '', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text.strip()
    
    def _standardize_terminology(
        self,
        slides: List[SlideContent]
    ) -> List[SlideContent]:
        """
        Ensure consistent terminology across slides.
        
        Example: If slide 1 uses "revenue" and slide 3 uses "sales",
        standardize to the most common term.
        """
        # Collect all terms used
        term_variations = {
            'revenue': ['revenue', 'sales', 'income', 'turnover'],
            'cost': ['cost', 'expense', 'spend', 'expenditure'],
            'profit': ['profit', 'earnings', 'margin', 'bottom line'],
            'growth': ['growth', 'increase', 'expansion', 'rise'],
            'customer': ['customer', 'client', 'buyer', 'consumer'],
        }
        
        # Count occurrences of each variation
        variation_counts = {}
        for slide in slides:
            text = f"{slide.title} {' '.join(b.text for b in slide.bullets)}".lower()
            
            for standard, variations in term_variations.items():
                for var in variations:
                    if var in text:
                        if standard not in variation_counts:
                            variation_counts[standard] = {}
                        variation_counts[standard][var] = variation_counts[standard].get(var, 0) + 1
        
        # Determine most common variation for each concept
        preferred_terms = {}
        for standard, counts in variation_counts.items():
            if counts:
                preferred_terms[standard] = max(counts, key=counts.get)
        
        # Apply standardization (optional - could add warnings instead)
        # For now, just track what we found
        
        return slides
    
    def _verify_word_budgets(
        self,
        slides: List[SlideContent]
    ) -> List[SlideContent]:
        """
        Verify and adjust word budgets per slide.
        
        Target: 50 words per slide
        Max: 60 words (with warning)
        """
        for slide in slides:
            # Calculate actual word count
            total_words = len(slide.title.split())
            if slide.subtitle:
                total_words += len(slide.subtitle.split())
            for bullet in slide.bullets:
                total_words += len(bullet.text.split())
            
            slide.word_count = total_words
            
            # Check budget
            if total_words > 60:
                slide.warnings.append(
                    f"Word count {total_words} exceeds recommended 50 (max 60)"
                )
            elif total_words > 50:
                slide.warnings.append(
                    f"Word count {total_words} slightly over 50-word target"
                )
        
        return slides
    
    def _balance_slide_density(
        self,
        slides: List[SlideContent]
    ) -> List[SlideContent]:
        """
        Balance content density across slides.
        
        Flags slides that are too heavy or too light compared to average.
        Suggests layout changes if needed.
        """
        if len(slides) <= 2:
            return slides
        
        # Calculate average bullet count
        bullet_counts = [len(s.bullets) for s in slides if s.bullets]
        if not bullet_counts:
            return slides
        
        avg_bullets = sum(bullet_counts) / len(bullet_counts)
        
        # Flag outliers
        for slide in slides:
            num_bullets = len(slide.bullets)
            
            if num_bullets > avg_bullets + 3:
                # Heavy slide - suggest layout change
                slide.warnings.append(
                    f"High density: {num_bullets} bullets (avg: {avg_bullets:.1f}). "
                    f"Consider TWO_COLUMN layout or splitting."
                )
                
                # Auto-suggest layout change
                if slide.layout == LayoutType.BULLET:
                    # Note: Not changing automatically, just suggesting
                    pass
            
            elif num_bullets == 0 and slide.chart_data is None and len(slide.images) == 0:
                # Empty slide (except title/thank you)
                if slide.slide_type.value not in ['title', 'thank_you']:
                    slide.warnings.append(
                        "Low density: No bullets, chart, or images. Consider adding content."
                    )
        
        return slides
    
    def check_narrative_flow(
        self,
        slides: List[SlideContent]
    ) -> List[str]:
        """
        Check narrative flow across slides.
        
        Returns warnings for:
        - Sudden topic jumps
        - Missing transitions
        - Repetitive structures
        """
        warnings = []
        
        if len(slides) < 3:
            return warnings
        
        # Check for repetitive structures
        layouts = [s.layout.value for s in slides]
        
        # Count consecutive identical layouts
        consecutive_same = 1
        for i in range(1, len(layouts)):
            if layouts[i] == layouts[i-1]:
                consecutive_same += 1
                if consecutive_same == 4:
                    warnings.append(
                        f"Slides {i-2}-{i+1}: 4+ consecutive {layouts[i]} layouts. "
                        f"Consider varying layouts for visual interest."
                    )
            else:
                consecutive_same = 1
        
        # Check for missing transitions (very basic check)
        for i in range(1, len(slides)):
            prev_slide = slides[i-1]
            curr_slide = slides[i]
            
            # Check for related content (simple keyword overlap)
            prev_keywords = set(self._extract_keywords(prev_slide.key_message))
            curr_keywords = set(self._extract_keywords(curr_slide.key_message))
            
            if prev_keywords and curr_keywords:
                overlap = len(prev_keywords & curr_keywords)
                total = len(prev_keywords | curr_keywords)
                
                if total > 0 and overlap / total < 0.1:
                    warnings.append(
                        f"Slide {curr_slide.slide_number}: Large topic jump from previous. "
                        f"Consider adding transition."
                    )
        
        return warnings
    
    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract significant keywords."""
        import re
        
        if not text:
            return set()
        
        text = text.lower()
        words = re.findall(r'\b[a-z]{5,}\b', text)  # 5+ char words
        
        stop_words = {
            'about', 'above', 'across', 'after', 'against', 'along', 'among',
            'around', 'because', 'before', 'behind', 'below', 'beneath',
            'beside', 'between', 'beyond', 'during', 'except', 'inside',
            'outside', 'through', 'throughout', 'toward', 'under', 'within'
        }
        
        return set(w for w in words if w not in stop_words)
    
    def suggest_layout_changes(
        self,
        slides: List[SlideContent]
    ) -> Dict[int, LayoutType]:
        """
        Suggest better layouts based on content analysis.
        
        Returns:
            Dict mapping slide_number -> suggested_layout
        """
        suggestions = {}
        
        for slide in slides:
            current = slide.layout
            suggested = None
            
            # High bullet count -> TWO_COLUMN
            if len(slide.bullets) >= 5 and current == LayoutType.BULLET:
                suggested = LayoutType.TWO_COLUMN
            
            # Chart + many bullets -> Keep chart but flag for pruning
            elif slide.chart_data and len(slide.bullets) >= 4:
                # Current layout is probably fine, but content might need pruning
                pass
            
            # Single image + bullets -> TWO_COLUMN
            elif len(slide.images) == 1 and len(slide.bullets) >= 3:
                if current == LayoutType.BULLET:
                    suggested = LayoutType.TWO_COLUMN
            
            # Comparison content -> COMPARISON layout
            elif self._is_comparison_content(slide) and current != LayoutType.COMPARISON:
                suggested = LayoutType.COMPARISON
            
            # Timeline content -> TIMELINE layout
            elif self._is_timeline_content(slide) and current != LayoutType.TIMELINE:
                suggested = LayoutType.TIMELINE
            
            if suggested:
                suggestions[slide.slide_number] = suggested
        
        return suggestions
    
    def _is_comparison_content(self, slide: SlideContent) -> bool:
        """Check if slide has comparison keywords."""
        text = f"{slide.title} {slide.key_message}".lower()
        comparison_words = ['vs', 'versus', 'compared', 'comparison', 'difference',
                          'contrast', 'trade-off', 'tradeoff', 'pros', 'cons',
                          'advantage', 'disadvantage', 'before', 'after']
        return any(w in text for w in comparison_words)
    
    def _is_timeline_content(self, slide: SlideContent) -> bool:
        """Check if slide has timeline keywords."""
        text = f"{slide.title} {slide.key_message}".lower()
        timeline_words = ['timeline', 'roadmap', 'phases', 'stages', 'steps',
                         'schedule', 'milestone', 'progress', 'phase', 'stage']
        return any(w in text for w in timeline_words)
    
    def generate_quality_report(
        self,
        presentation: PresentationContent
    ) -> str:
        """Generate a human-readable quality report."""
        lines = [
            "=" * 60,
            "CONTENT QUALITY REPORT",
            "=" * 60,
            ""
        ]
        
        # Overall stats
        total_warnings = sum(len(s.warnings) for s in presentation.slides)
        lines.extend([
            f"Total Slides: {len(presentation.slides)}",
            f"Total Warnings: {total_warnings}",
            f"Total Words: {sum(s.word_count for s in presentation.slides)}",
            f"Unassigned Images: {len(presentation.unassigned_images)}",
            ""
        ])
        
        # Per-slide issues
        for slide in presentation.slides:
            if slide.warnings:
                lines.append(f"Slide {slide.slide_number} ({slide.title}):")
                for warning in slide.warnings:
                    lines.append(f"  - {warning}")
                lines.append("")
        
        # Narrative flow
        flow_warnings = self.check_narrative_flow(presentation.slides)
        if flow_warnings:
            lines.extend([
                "NARRATIVE FLOW:",
                "-" * 40
            ])
            for warning in flow_warnings:
                lines.append(f"  - {warning}")
            lines.append("")
        
        # Layout suggestions
        layout_suggestions = self.suggest_layout_changes(presentation.slides)
        if layout_suggestions:
            lines.extend([
                "LAYOUT SUGGESTIONS:",
                "-" * 40
            ])
            for slide_num, suggested in layout_suggestions.items():
                lines.append(f"  - Slide {slide_num}: Consider {suggested.value} layout")
            lines.append("")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
