"""Re-parse markdown to extract raw section content.

Uses AST tokens passed through from Step 1 parser to avoid duplicate
mistune parsing (BUG-7 fix). Falls back to parsing only for
find_table_by_index when AST tokens aren't available.
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass, field

import mistune

from step1.models import ContentInventory, Section


@dataclass
class SectionContent:
    """Raw content extracted from a markdown section."""
    section_id: str
    heading: str
    level: int
    raw_text: str = ""
    paragraphs: List[str] = field(default_factory=list)
    bullet_lists: List[List[str]] = field(default_factory=list)
    tables: List[List[List[str]]] = field(default_factory=list)

    def get_all_text(self) -> str:
        """Get all text content as single string."""
        parts = [self.heading]
        parts.extend(self.paragraphs)
        for bullet_list in self.bullet_lists:
            parts.extend(bullet_list)
        return "\n\n".join(parts)

    def get_word_count(self) -> int:
        """Calculate total word count."""
        return len(self.get_all_text().split())


class MarkdownReparser:
    """Extract raw section content using AST tokens from Step 1."""

    def __init__(self) -> None:
        # Lazy-init parser only when needed for find_table_by_index
        self._md_parser = None

    @property
    def md_parser(self):
        if self._md_parser is None:
            self._md_parser = mistune.create_markdown(renderer='ast', plugins=['table'])
        return self._md_parser

    def reparse_sections(
        self,
        markdown_text: str,
        inventory: ContentInventory,
    ) -> Dict[str, SectionContent]:
        """Re-parse markdown and map content to inventory sections.

        Uses AST tokens from inventory when available (passed through
        from Step 1) to avoid duplicate mistune parsing.
        """
        tokens = inventory.get_ast_tokens()
        if tokens is None:
            tokens = self.md_parser(markdown_text)

        section_map = self._build_section_map(tokens, inventory)

        sections_content = {}
        for section in inventory.sections:
            content = self._extract_section_content(
                section, tokens, section_map.get(section.id, {})
            )
            sections_content[section.id] = content

        return sections_content

    def _build_section_map(
        self,
        tokens: List[Dict],
        inventory: ContentInventory,
    ) -> Dict[str, Dict]:
        """Build mapping of section_id -> token indices."""
        headings = []
        for i, token in enumerate(tokens):
            if token.get('type') == 'heading':
                level = token.get('attrs', {}).get('level', 1)
                text = self._get_text_content(token)
                headings.append({'index': i, 'level': level, 'text': text})

        section_map = {}
        for section in inventory.sections:
            for i, heading in enumerate(headings):
                if self._headings_match(heading['text'], section.heading):
                    start_idx = heading['index']
                    end_idx = len(tokens)

                    for j in range(i + 1, len(headings)):
                        if headings[j]['level'] <= heading['level']:
                            end_idx = headings[j]['index']
                            break

                    section_map[section.id] = {
                        'start': start_idx,
                        'end': end_idx,
                        'heading_token': heading,
                    }
                    break

        return section_map

    def _headings_match(self, text1: str, text2: str) -> bool:
        """Check if two headings match (with normalization)."""
        norm1 = re.sub(r'[^\w\s]', '', text1.lower().strip())
        norm2 = re.sub(r'[^\w\s]', '', text2.lower().strip())
        return norm1 == norm2 or norm1 in norm2 or norm2 in norm1

    def _extract_section_content(
        self,
        section: Section,
        tokens: List[Dict],
        boundaries: Dict,
    ) -> SectionContent:
        """Extract content for a specific section."""
        content = SectionContent(
            section_id=section.id,
            heading=section.heading,
            level=section.level,
        )

        if not boundaries:
            content.raw_text = section.raw_text
            if section.raw_text:
                content.paragraphs = [section.raw_text]
            return content

        start = boundaries.get('start', 0)
        end = boundaries.get('end', len(tokens))
        section_tokens = tokens[start:end]

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

    def _extract_list_items(self, token: Dict) -> List[str]:
        """Extract list items from a list token."""
        items = []
        for child in token.get('children', []):
            if child.get('type') == 'list_item':
                text = self._get_text_content(child)
                if text.strip():
                    items.append(text)
        return items

    def _extract_table_data(self, token: Dict) -> List[List[str]]:
        """Extract table as 2D array."""
        rows = []
        children = token.get('children', [])

        table_head = None
        table_body = None

        for child in children:
            if child.get('type') == 'table_head':
                table_head = child
            elif child.get('type') == 'table_body':
                table_body = child

        if table_head:
            head_children = table_head.get('children', [])
            if head_children:
                header_cells = [
                    self._get_text_content(cell)
                    for cell in head_children[0].get('children', [])
                ]
                rows.append(header_cells)

        if table_body:
            for row_token in table_body.get('children', []):
                row_cells = [
                    self._get_text_content(cell)
                    for cell in row_token.get('children', [])
                ]
                rows.append(row_cells)

        return rows

    def _tokens_to_raw_text(self, tokens: List[Dict]) -> str:
        """Convert tokens back to raw text."""
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
            if 'raw' in token:
                return token['raw']
            if 'text' in token and not isinstance(token.get('type'), str):
                return token['text']
            if 'children' in token and isinstance(token['children'], list):
                return ' '.join(self._get_text_content(child) for child in token['children'])

        return ""

    def find_table_by_index(
        self,
        markdown_text: str,
        table_index: int,
        ast_tokens: Optional[list] = None,
    ) -> Optional[List[List[str]]]:
        """Find a specific table by its index in the document."""
        tokens = ast_tokens if ast_tokens is not None else self.md_parser(markdown_text)

        table_count = 0
        for token in tokens:
            if token.get('type') == 'table':
                if table_count == table_index:
                    return self._extract_table_data(token)
                table_count += 1

        return None
