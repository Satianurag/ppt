"""Re-parse markdown to extract raw section content."""

import re
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
import mistune

from step1.models import ContentInventory, Section, ImageInfo, TableInfo


@dataclass
class SectionContent:
    """Raw content extracted from a markdown section."""
    section_id: str
    heading: str
    level: int
    raw_text: str = ""  # Complete section text
    paragraphs: List[str] = field(default_factory=list)
    bullet_lists: List[List[str]] = field(default_factory=list)
    tables: List[List[List[str]]] = field(default_factory=list)  # 3D: tables[table][row][cell]
    images: List[ImageInfo] = field(default_factory=list)
    
    def get_all_text(self) -> str:
        """Get all text content as single string."""
        parts = [self.heading]
        parts.extend(self.paragraphs)
        for bullet_list in self.bullet_lists:
            parts.extend(bullet_list)
        return "\n\n".join(parts)
    
    def get_word_count(self) -> int:
        """Calculate total word count."""
        text = self.get_all_text()
        return len(text.split())


class MarkdownReparser:
    """Re-parse markdown to extract raw section content with full text."""
    
    def __init__(self):
        self.md_parser = mistune.create_markdown(renderer='ast', plugins=['table'])
    
    def reparse_sections(
        self,
        markdown_text: str,
        inventory: ContentInventory
    ) -> Dict[str, SectionContent]:
        """
        Re-parse markdown and map content to inventory sections.
        
        Returns:
            Dict mapping section_id -> SectionContent
        """
        tokens = self.md_parser(markdown_text)
        
        # Build section boundaries from inventory
        section_map = self._build_section_map(tokens, inventory)
        
        # Extract content for each section
        sections_content = {}
        for section in inventory.sections:
            content = self._extract_section_content(
                section,
                tokens,
                section_map.get(section.id, {})
            )
            sections_content[section.id] = content
        
        return sections_content
    
    def _build_section_map(
        self,
        tokens: List[Dict],
        inventory: ContentInventory
    ) -> Dict[str, Dict]:
        """
        Build mapping of section_id -> token indices.
        
        Strategy:
        1. Find heading tokens that match inventory section headings
        2. Map token ranges between headings to sections
        """
        section_map = {}
        
        # Find all heading tokens with their positions
        headings = []
        for i, token in enumerate(tokens):
            if token.get('type') == 'heading':
                level = token.get('attrs', {}).get('level', 1)
                text = self._get_text_content(token)
                headings.append({
                    'index': i,
                    'level': level,
                    'text': text
                })
        
        # Map inventory sections to heading positions
        for section in inventory.sections:
            # Find matching heading
            for i, heading in enumerate(headings):
                if self._headings_match(heading['text'], section.heading):
                    # Determine end index (next heading at same or higher level)
                    start_idx = heading['index']
                    end_idx = len(tokens)
                    
                    for j in range(i + 1, len(headings)):
                        if headings[j]['level'] <= heading['level']:
                            end_idx = headings[j]['index']
                            break
                    
                    section_map[section.id] = {
                        'start': start_idx,
                        'end': end_idx,
                        'heading_token': heading
                    }
                    break
        
        return section_map
    
    def _headings_match(self, text1: str, text2: str) -> bool:
        """Check if two headings match (with normalization)."""
        # Normalize: lowercase, strip whitespace, remove formatting
        norm1 = re.sub(r'[^\w\s]', '', text1.lower().strip())
        norm2 = re.sub(r'[^\w\s]', '', text2.lower().strip())
        
        # Exact match or one contains the other
        return norm1 == norm2 or norm1 in norm2 or norm2 in norm1
    
    def _extract_section_content(
        self,
        section: Section,
        tokens: List[Dict],
        boundaries: Dict
    ) -> SectionContent:
        """Extract content for a specific section."""
        
        content = SectionContent(
            section_id=section.id,
            heading=section.heading,
            level=section.level
        )
        
        if not boundaries:
            # No content found - use inventory summary
            return self._create_from_inventory(section, content)
        
        start = boundaries.get('start', 0)
        end = boundaries.get('end', len(tokens))
        
        # Extract tokens in range
        section_tokens = tokens[start:end]
        
        # Build raw text
        content.raw_text = self._tokens_to_raw_text(section_tokens)
        
        # Extract specific content types
        for token in section_tokens:
            token_type = token.get('type')
            
            if token_type == 'paragraph':
                text = self._get_text_content(token)
                if text.strip():
                    content.paragraphs.append(text)
            
            elif token_type == 'list':
                items = self._extract_list_items(token)
                if items:
                    content.bullet_lists.append(items)
            
            elif token_type == 'table':
                table_data = self._extract_table_data(token)
                if table_data:
                    content.tables.append(table_data)
            
            elif token_type == 'image':
                # Images will be matched from inventory
                pass
        
        # Copy images from inventory (already extracted)
        content.images = section.images.copy()
        
        return content
    
    def _create_from_inventory(
        self,
        section: Section,
        content: SectionContent
    ) -> SectionContent:
        """Create content from inventory when parsing fails."""
        # Use section heading as fallback
        content.paragraphs = [f"Section: {section.heading}"]
        content.images = section.images.copy()
        content.tables = []  # Would need to parse from raw if available
        return content
    
    def _extract_list_items(self, token: Dict) -> List[str]:
        """Extract list items from a list token."""
        items = []
        children = token.get('children', [])
        
        for child in children:
            if child.get('type') == 'list_item':
                text = self._get_text_content(child)
                if text.strip():
                    items.append(text)
        
        return items
    
    def _extract_table_data(self, token: Dict) -> List[List[str]]:
        """Extract table as 2D array."""
        rows = []
        children = token.get('children', [])
        
        # Find table head and body
        table_head = None
        table_body = None
        
        for child in children:
            if child.get('type') == 'table_head':
                table_head = child
            elif child.get('type') == 'table_body':
                table_body = child
        
        # Extract header row
        if table_head:
            head_children = table_head.get('children', [])
            if head_children:
                header_cells = [
                    self._get_text_content(cell)
                    for cell in head_children[0].get('children', [])
                ]
                rows.append(header_cells)
        
        # Extract body rows
        if table_body:
            for row_token in table_body.get('children', []):
                row_cells = [
                    self._get_text_content(cell)
                    for cell in row_token.get('children', [])
                ]
                rows.append(row_cells)
        
        return rows
    
    def _tokens_to_raw_text(self, tokens: List[Dict]) -> str:
        """Convert tokens back to raw markdown-like text."""
        parts = []
        
        for token in tokens:
            text = self._get_text_content(token)
            if text.strip():
                parts.append(text)
        
        return "\n\n".join(parts)
    
    def _get_text_content(self, token: Dict) -> str:
        """Extract plain text from token recursively."""
        if isinstance(token, str):
            return token
        
        if isinstance(token, dict):
            # 'raw' contains text in mistune v3
            if 'raw' in token:
                return token['raw']
            
            # Fallback
            if 'text' in token and not isinstance(token.get('type'), str):
                return token['text']
            
            # Recurse into children
            if 'children' in token and isinstance(token['children'], list):
                return ' '.join(self._get_text_content(child) for child in token['children'])
        
        return ""
    
    def find_table_by_index(
        self,
        markdown_text: str,
        table_index: int
    ) -> Optional[List[List[str]]]:
        """
        Find a specific table by its index in the document.
        
        Args:
            markdown_text: Full markdown
            table_index: 0-based index of table
            
        Returns:
            Table as 2D list or None if not found
        """
        tokens = self.md_parser(markdown_text)
        
        table_count = 0
        for token in tokens:
            if token.get('type') == 'table':
                if table_count == table_index:
                    return self._extract_table_data(token)
                table_count += 1
        
        return None
    
    def extract_section_by_heading(
        self,
        markdown_text: str,
        heading_text: str
    ) -> Optional[SectionContent]:
        """Extract a specific section by its heading text."""
        tokens = self.md_parser(markdown_text)
        
        # Find the heading
        start_idx = None
        level = None
        
        for i, token in enumerate(tokens):
            if token.get('type') == 'heading':
                text = self._get_text_content(token)
                if self._headings_match(text, heading_text):
                    start_idx = i
                    level = token.get('attrs', {}).get('level', 1)
                    break
        
        if start_idx is None:
            return None
        
        # Find end (next heading at same or higher level)
        end_idx = len(tokens)
        for i in range(start_idx + 1, len(tokens)):
            token = tokens[i]
            if token.get('type') == 'heading':
                token_level = token.get('attrs', {}).get('level', 1)
                if token_level <= level:
                    end_idx = i
                    break
        
        # Extract content
        section_tokens = tokens[start_idx:end_idx]
        heading = self._get_text_content(tokens[start_idx])
        
        content = SectionContent(
            section_id=f"extracted_{heading[:20].lower().replace(' ', '_')}",
            heading=heading,
            level=level
        )
        
        # Populate content
        content.raw_text = self._tokens_to_raw_text(section_tokens)
        
        for token in section_tokens:
            token_type = token.get('type')
            
            if token_type == 'paragraph':
                text = self._get_text_content(token)
                if text.strip():
                    content.paragraphs.append(text)
            
            elif token_type == 'list':
                items = self._extract_list_items(token)
                if items:
                    content.bullet_lists.append(items)
            
            elif token_type == 'table':
                table_data = self._extract_table_data(token)
                if table_data:
                    content.tables.append(table_data)
        
        return content
