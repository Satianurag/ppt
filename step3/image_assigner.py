"""Smart image-to-slide assignment algorithm."""

import re
from typing import List, Dict, Tuple, Optional
from difflib import SequenceMatcher

from step2.slide_plan_models import LayoutType
from .content_models import SlideContent, SlideImage
from step1.models import ImageInfo, Section


class ImageAssigner:
    """Assign extracted images to appropriate slides."""
    
    def __init__(self):
        self.max_images_per_slide = 2
    
    def assign_images(
        self,
        slides: List[SlideContent],
        sections: List[Section],
        all_images: List[ImageInfo]
    ) -> Tuple[List[SlideContent], List[ImageInfo]]:
        """
        Assign images to slides and return unassigned images.
        
        Algorithm:
        1. Direct section match: Image in section → assign to that slide
        2. Proximity match: Image in subsection → assign to parent slide
        3. Keyword match: Image alt text matches slide title
        4. Layout fit: Assign based on slide layout type
        5. Distribute remaining images evenly
        
        Returns:
            (updated_slides, unassigned_images)
        """
        # Track assignments
        assigned_images = set()  # ImageInfo indices that are assigned
        
        # Build section → slides mapping
        section_to_slides = self._build_section_slide_map(slides)
        
        # Pass 1: Direct section matches
        for slide in slides:
            for section_id in slide.source_sections:
                # Find images from this section
                section_images = [
                    img for img in all_images
                    if hasattr(img, 'section_id') and img.section_id == section_id
                ]
                
                for img in section_images:
                    if img.index in assigned_images:
                        continue
                    if len(slide.images) >= self.max_images_per_slide:
                        break
                    
                    fit_score = self._score_image_slide_fit(img, slide, sections)
                    slide.images.append(SlideImage(
                        image_info=img,
                        position=self._suggest_position(slide, img),
                        fit_score=fit_score
                    ))
                    assigned_images.add(img.index)
        
        # Pass 2: Keyword matching for unassigned images
        unassigned = [img for img in all_images if img.index not in assigned_images]
        
        for img in unassigned:
            if len(assigned_images) >= len(all_images):
                break
            
            best_slide = None
            best_score = 0.3  # Minimum threshold
            
            for slide in slides:
                if len(slide.images) >= self.max_images_per_slide:
                    continue
                
                score = self._score_keyword_match(img, slide)
                if score > best_score:
                    best_score = score
                    best_slide = slide
            
            if best_slide:
                best_slide.images.append(SlideImage(
                    image_info=img,
                    position=self._suggest_position(best_slide, img),
                    fit_score=best_score
                ))
                assigned_images.add(img.index)
        
        # Pass 3: Distribute remaining to content slides
        remaining = [img for img in all_images if img.index not in assigned_images]
        content_slides = [s for s in slides 
                         if s.slide_type.value in ['content', 'comparison', 'timeline'] 
                         and len(s.images) < self.max_images_per_slide]
        
        if content_slides and remaining:
            # Distribute evenly
            images_per_slide = max(1, len(remaining) // len(content_slides))
            
            slide_idx = 0
            for img in remaining:
                if slide_idx >= len(content_slides):
                    slide_idx = 0
                
                slide = content_slides[slide_idx]
                if len(slide.images) < self.max_images_per_slide:
                    slide.images.append(SlideImage(
                        image_info=img,
                        position=self._suggest_position(slide, img),
                        fit_score=0.5  # Neutral score for distributed assignment
                    ))
                    assigned_images.add(img.index)
                    
                    if len([s for s in slides if any(i.image_info.index == img.index for i in s.images)]) >= images_per_slide:
                        slide_idx += 1
        
        # Collect unassigned
        unassigned_final = [img for img in all_images if img.index not in assigned_images]
        
        # Sort images within each slide by fit score
        for slide in slides:
            slide.images.sort(key=lambda x: x.fit_score, reverse=True)
        
        return slides, unassigned_final
    
    def _build_section_slide_map(
        self,
        slides: List[SlideContent]
    ) -> Dict[str, List[int]]:
        """Build mapping from section_id to slide numbers."""
        mapping = {}
        for slide in slides:
            for section_id in slide.source_sections:
                if section_id not in mapping:
                    mapping[section_id] = []
                mapping[section_id].append(slide.slide_number)
        return mapping
    
    def _get_section_images(
        self,
        section_id: str,
        sections: List[Section],
        all_images: List[ImageInfo]
    ) -> List[ImageInfo]:
        """Get images associated with a specific section."""
        section = None
        for s in sections:
            if s.id == section_id:
                section = s
                break
        
        if not section:
            return []
        
        # Get images from section and subsections
        image_indices = set()
        for img in section.images:
            image_indices.add(img.index)
        
        # Find subsections
        for s in sections:
            if s.parent_id == section_id:
                for img in s.images:
                    image_indices.add(img.index)
        
        return [img for img in all_images if img.index in image_indices]
    
    def _score_image_slide_fit(
        self,
        image: ImageInfo,
        slide: SlideContent,
        sections: List[Section]
    ) -> float:
        """Score how well an image fits a slide (0-1)."""
        score = 0.0
        
        # Direct section match: +0.4
        for section_id in slide.source_sections:
            section_images = self._get_section_images(section_id, sections, [])
            if any(img.index == image.index for img in section_images):
                score += 0.4
                break
        
        # Keyword match: +0.3
        score += self._score_keyword_match(image, slide, sections) * 0.3
        
        # Layout preference: +0.2 for image-friendly layouts
        if slide.layout in [LayoutType.TWO_COLUMN, LayoutType.BLANK, LayoutType.COMPARISON]:
            score += 0.2
        
        # Space available: +0.1 if slide has no images yet
        if len(slide.images) == 0:
            score += 0.1
        
        return min(1.0, score)
    
    def _score_keyword_match(
        self,
        image: ImageInfo,
        slide: SlideContent,
        sections: List[Section] = None
    ) -> float:
        """Score keyword match between image and slide."""
        if not image.alt_text:
            return 0.0
        
        # Keywords to match
        slide_keywords = set(self._extract_keywords(slide.title))
        slide_keywords.update(self._extract_keywords(slide.key_message))
        
        image_keywords = set(self._extract_keywords(image.alt_text))
        
        if not slide_keywords or not image_keywords:
            return 0.0
        
        # Calculate overlap
        overlap = len(slide_keywords & image_keywords)
        total = len(slide_keywords | image_keywords)
        
        if total == 0:
            return 0.0
        
        return overlap / len(slide_keywords) if slide_keywords else 0.0
    
    def _extract_keywords(self, text: Optional[str]) -> List[str]:
        """Extract significant keywords from text."""
        if not text:
            return []
        
        # Normalize
        text = text.lower()
        
        # Remove common words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been',
            'this', 'that', 'these', 'those', 'it', 'its', 'as', 'from'
        }
        
        # Extract words
        words = re.findall(r'\b[a-z]{4,}\b', text)  # 4+ char words
        keywords = [w for w in words if w not in stop_words]
        
        return keywords
    
    def _suggest_position(
        self,
        slide: SlideContent,
        image: ImageInfo
    ) -> str:
        """Suggest best position for image on slide."""
        layout = slide.layout
        current_images = len(slide.images)
        
        # Layout-specific positioning
        if layout == LayoutType.TWO_COLUMN:
            return "right" if current_images == 0 else "left"
        
        elif layout == LayoutType.COMPARISON:
            return "left" if current_images == 0 else "right"
        
        elif layout == LayoutType.CHART_WITH_TEXT:
            # Small image inline or to side
            return "inline" if current_images == 0 else "right"
        
        elif layout == LayoutType.BLANK:
            return "full" if current_images == 0 else "inline"
        
        elif slide.slide_type.value == 'title':
            return "background"
        
        else:
            # Default: inline for single, left/right for multiple
            if current_images == 0:
                return "right"
            else:
                return "left"
    
    def suggest_images_for_slide(
        self,
        slide: SlideContent,
        available_images: List[ImageInfo],
        sections: List[Section],
        top_n: int = 3
    ) -> List[Tuple[ImageInfo, float]]:
        """
        Suggest the best images for a specific slide.
        
        Returns:
            List of (image, fit_score) tuples, sorted by score
        """
        scored = []
        
        for img in available_images:
            score = self._score_image_slide_fit(img, slide, sections)
            if score > 0.2:  # Minimum relevance threshold
                scored.append((img, score))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return scored[:top_n]
