"""Markdown parser for creating structured content inventory."""

import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import mistune

from .models import (
    ContentInventory, Section, SectionType, ContentType,
    TableInfo, ImageInfo, OverflowStatus
)
from .classifier import (
    classify_section_type, classify_content_type,
    detect_comparison, detect_process, detect_timeline,
    is_numeric_column, is_temporal_column
)
from .image_extractor import extract_all_images


class MarkdownParser:
    """Parser for extracting structured content inventory from markdown."""
    
    def __init__(self, image_output_dir: Path = Path("./extracted_images")):
        self.image_output_dir = image_output_dir
        # Enable table plugin for proper table parsing
        self.md_parser = mistune.create_markdown(renderer='ast', plugins=['table'])
        
    # Fixed slide budget - cannot be changed
    SLIDE_BUDGET = 15
    
    def parse(self, markdown_text: str) -> ContentInventory:
        """Parse markdown text into structured content inventory.
        
        Args:
            markdown_text: Raw markdown content
            
        Returns:
            ContentInventory with all parsed and classified content
        """
        # Step 1: Extract images and update markdown
        modified_md, images = extract_all_images(markdown_text, self.image_output_dir)
        
        # Step 2: Parse to AST
        tokens = self.md_parser(modified_md)
        
        # Step 3: Extract document metadata
        title, subtitle = self._extract_title(tokens)
        
        # Step 4: Extract sections with content
        sections = self._extract_sections(tokens, images)
        
        # Step 5: Calculate totals
        total_words = sum(s.word_count for s in sections)
        total_tables = sum(s.table_count for s in sections)
        total_images = sum(s.image_count for s in sections)
        total_bullets = sum(s.bullet_count for s in sections)
        
        # Step 6: Detect structural flags
        has_toc = any(s.section_type == SectionType.SKIP and "toc" in s.heading.lower() 
                      for s in sections)
        has_exec_summary = any(s.section_type == SectionType.SUMMARY for s in sections)
        has_references = any(s.section_type == SectionType.SKIP and "reference" in s.heading.lower()
                            for s in sections)
        has_appendix = any(s.section_type == SectionType.SKIP and "appendix" in s.heading.lower()
                          for s in sections)
        
        # Step 7: Calculate overflow
        content_sections = [s for s in sections if s.section_type != SectionType.SKIP]
        content_budget = self.SLIDE_BUDGET - 4  # Reserve for title, agenda, summary, thank you
        
        data_sections = [s for s in content_sections if s.content_type == ContentType.DATA]
        chart_candidates = len(data_sections)
        
        overflow = OverflowStatus(
            sections_over_budget=len(content_sections) > content_budget,
            tables_over_budget=chart_candidates > 5,  # Max 5 chart slides recommended
            charts_candidates=chart_candidates,
            recommended_chart_slots=min(5, chart_candidates)
        )
        
        return ContentInventory(
            title=title,
            subtitle=subtitle,
            total_words=total_words,
            total_sections=len(content_sections),
            has_toc=has_toc,
            has_executive_summary=has_exec_summary,
            has_references=has_references,
            has_appendix=has_appendix,
            total_tables=total_tables,
            total_images=total_images,
            total_bullets=total_bullets,
            sections=sections,
            overflow=overflow
        )
    
    def _extract_title(self, tokens: List[Dict]) -> Tuple[Optional[str], Optional[str]]:
        """Extract document title (H1) and optional subtitle."""
        title = None
        subtitle = None
        
        for i, token in enumerate(tokens):
            if token.get('type') == 'heading' and token.get('attrs', {}).get('level') == 1:
                title = self._get_text_content(token)
                # Check if next token is a paragraph (potential subtitle)
                if i + 1 < len(tokens) and tokens[i + 1].get('type') == 'paragraph':
                    subtitle = self._get_text_content(tokens[i + 1])
                    # Limit subtitle length
                    if len(subtitle) > 200:
                        subtitle = subtitle[:200] + "..."
                break
        
        return title, subtitle
    
    def _extract_sections(self, tokens: List[Dict], all_images: List[ImageInfo]) -> List[Section]:
        """Extract content sections from tokens."""
        sections = []
        current_section = None
        section_counter = 0
        table_counter = 0
        image_path_map = self._build_image_index_map(tokens, all_images)
        
        for token in tokens:
            token_type = token.get('type')
            
            # Start new section on heading
            if token_type == 'heading':
                level = token.get('attrs', {}).get('level', 1)
                heading_text = self._get_text_content(token)
                
                # Save previous section
                if current_section:
                    sections.append(current_section)
                
                # Create new section
                section_type = classify_section_type(heading_text)
                section_id = f"sec_{section_counter}"
                
                current_section = Section(
                    id=section_id,
                    heading=heading_text,
                    level=level,
                    section_type=section_type,
                    content_type=ContentType.TEXT,  # Will be updated later
                    parent_id=None,  # Will be set based on hierarchy
                )
                section_counter += 1
                
            # Accumulate content in current section
            elif current_section:
                self._accumulate_content(token, current_section, image_path_map, table_counter)
                if token_type == 'table':
                    table_counter += 1
        
        # Don't forget the last section
        if current_section:
            sections.append(current_section)
        
        # Post-process: set parent relationships and classify content types
        sections = self._set_hierarchy(sections)
        sections = self._classify_section_content(sections)
        
        return sections
    
    def _accumulate_content(self, token: Dict, section: Section, 
                           image_path_map: Dict[str, ImageInfo], 
                           table_counter: int) -> None:
        """Accumulate content metrics from a token into a section."""
        token_type = token.get('type')
        
        if token_type == 'paragraph':
            # Check for nested images in paragraphs (common in mistune v3)
            for child in token.get('children', []):
                if child.get('type') == 'image':
                    self._process_image_token(child, section, image_path_map)
            
            # Count paragraph text
            text = self._get_text_content(token)
            section.word_count += len(text.split())
            section.paragraph_count += 1
            
        elif token_type == 'list':
            items = token.get('children', [])
            section.bullet_count += len(items)
            for item in items:
                text = self._get_text_content(item)
                section.word_count += len(text.split())
                
        elif token_type == 'table':
            table_info = self._parse_table(token, table_counter)
            section.tables.append(table_info)
            section.table_count += 1
            
        elif token_type == 'image':
            # Images can be at top level or nested in paragraphs
            self._process_image_token(token, section, image_path_map)
    
    def _process_image_token(self, token: Dict, section: Section, 
                            image_path_map: Dict[str, ImageInfo]) -> None:
        """Process an image token and add to section if found."""
        # Images use 'url' in mistune v3, not 'src'
        attrs = token.get('attrs', {})
        src = attrs.get('url', '') or attrs.get('src', '')
        
        if src and src in image_path_map:
            img = image_path_map[src]
            # Avoid duplicate images in same section
            if img not in section.images:
                section.images.append(img)
                section.image_count += 1
    
    def _parse_table(self, token: Dict, table_index: int) -> TableInfo:
        """Parse a table token into TableInfo.
        
        Handles mistune v3 structure with table_head and table_body.
        """
        children = token.get('children', [])
        
        # Find table_head and table_body
        table_head = None
        table_body = None
        
        for child in children:
            child_type = child.get('type')
            if child_type == 'table_head':
                table_head = child
            elif child_type == 'table_body':
                table_body = child
        
        # Fallback: direct children might be rows (older mistune versions)
        if not table_head and children:
            header_row = [self._get_text_content(cell) for cell in children[0].get('children', [])]
            body_tokens = children[1:] if len(children) > 1 else []
        else:
            # Extract from table_head
            head_children = table_head.get('children', []) if table_head else []
            header_row = [self._get_text_content(cell) for cell in head_children]
            
            # Extract from table_body
            body_tokens = table_body.get('children', []) if table_body else []
        
        cols = len(header_row)
        if cols == 0:
            return TableInfo(index=table_index, rows=0, cols=0, 
                           has_numeric=False, has_temporal=False)
        
        # Extract data rows
        rows = len(body_tokens)
        all_data = []
        for row_token in body_tokens:
            row_cells = row_token.get('children', [])
            row_data = [self._get_text_content(cell) for cell in row_cells]
            all_data.append(row_data)
        
        # Analyze columns for numeric/temporal data
        numeric_columns = []
        temporal_columns = []
        
        for col_idx in range(cols):
            col_values = [row[col_idx] if col_idx < len(row) else "" 
                         for row in all_data]
            
            if is_numeric_column(col_values):
                numeric_columns.append(col_idx)
            elif is_temporal_column(col_values):
                temporal_columns.append(col_idx)
        
        return TableInfo(
            index=table_index,
            rows=rows,
            cols=cols,
            has_numeric=len(numeric_columns) > 0,
            has_temporal=len(temporal_columns) > 0,
            numeric_columns=numeric_columns,
            temporal_columns=temporal_columns,
            header_row=header_row
        )
    
    def _build_image_index_map(self, tokens: List[Dict], all_images: List[ImageInfo]) -> Dict[str, ImageInfo]:
        """Build a mapping from image path to image info.
        
        Images are often nested inside paragraphs in mistune v3.
        """
        # Build map from extracted path to ImageInfo
        map_dict = {}
        
        for img in all_images:
            if img.extracted_path:
                map_dict[img.extracted_path] = img
        
        return map_dict
    
    def _set_hierarchy(self, sections: List[Section]) -> List[Section]:
        """Set parent-child relationships between sections."""
        if not sections:
            return sections
        
        # Stack to track parent sections by level
        stack = []  # (level, section_id)
        
        for section in sections:
            # Pop sections from stack that are same or deeper level
            while stack and stack[-1][0] >= section.level:
                stack.pop()
            
            # Set parent if stack not empty
            if stack:
                section.parent_id = stack[-1][1]
            
            # Push current section
            stack.append((section.level, section.id))
        
        # Build subsection lists
        section_map = {s.id: s for s in sections}
        for section in sections:
            if section.parent_id and section.parent_id in section_map:
                parent = section_map[section.parent_id]
                parent.subsection_ids.append(section.id)
        
        return sections
    
    def _classify_section_content(self, sections: List[Section]) -> List[Section]:
        """Classify content type and detect layout hints for each section."""
        for section in sections:
            # Classify primary content type
            has_numeric_table = any(t.has_numeric for t in section.tables)
            section.content_type = classify_content_type(
                section.table_count,
                section.image_count,
                section.bullet_count,
                has_numeric_table
            )
            
            # Detect layout hints from combined content
            combined_text = self._get_section_combined_text(section, sections)
            section.has_comparison = detect_comparison(section.heading, combined_text)
            section.has_process = detect_process(section.heading, combined_text)
            section.has_timeline = detect_timeline(section.heading, combined_text)
        
        return sections
    
    def _get_section_combined_text(self, section: Section, all_sections: List[Section]) -> str:
        """Get combined text content of a section and its subsections."""
        # For now, return heading as proxy
        # Full implementation would require storing raw content during parse
        return section.heading
    
    def _get_text_content(self, token: Dict) -> str:
        """Extract plain text content from a token recursively.
        
        Mistune v3 uses 'raw' for text content, 'text' is for token type.
        """
        if isinstance(token, str):
            return token
        
        if isinstance(token, dict):
            # 'raw' contains the actual text in mistune v3
            if 'raw' in token:
                return token['raw']
            
            # Fallback to 'text' for older versions
            if 'text' in token and not isinstance(token.get('type'), str):
                return token['text']
            
            # Recurse into children
            if 'children' in token and isinstance(token['children'], list):
                return ' '.join(self._get_text_content(child) for child in token['children'])
        
        return ""
    
    def parse_file(self, filepath: Path) -> ContentInventory:
        """Parse a markdown file.
        
        Args:
            filepath: Path to markdown file
            
        Returns:
            ContentInventory
        """
        markdown_text = filepath.read_text(encoding='utf-8')
        return self.parse(markdown_text)
