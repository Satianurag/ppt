"""Markdown parser for creating structured content inventory."""

import re
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import mistune

from .models import (
    ContentInventory, Section, SectionType, ContentType,
    TableInfo, OverflowStatus
)
from .classifier import (
    classify_section_type, classify_content_type,
    detect_comparison, detect_process, detect_timeline,
    is_numeric_column, is_temporal_column, select_chart_type
)
from constants import SLIDE_BUDGET, MANDATORY_SLIDES, MAX_CHART_SLIDES


class MarkdownParser:
    """Parser for extracting structured content inventory from markdown."""

    def __init__(self) -> None:
        self.md_parser = mistune.create_markdown(renderer='ast', plugins=['table'])

    def parse(self, markdown_text: str) -> ContentInventory:
        """Parse markdown text into structured content inventory."""
        tokens = self.md_parser(markdown_text)

        title, subtitle = self._extract_title(tokens)
        sections = self._extract_sections(tokens)

        total_words = sum(s.word_count for s in sections)
        total_tables = sum(s.table_count for s in sections)
        total_bullets = sum(s.bullet_count for s in sections)

        has_toc = any(
            s.section_type == SectionType.SKIP and "toc" in s.heading.lower()
            for s in sections
        )
        has_exec_summary = any(s.section_type == SectionType.SUMMARY for s in sections)
        has_references = any(
            s.section_type == SectionType.SKIP and "reference" in s.heading.lower()
            for s in sections
        )
        has_appendix = any(
            s.section_type == SectionType.SKIP and "appendix" in s.heading.lower()
            for s in sections
        )

        content_sections = [s for s in sections if s.section_type != SectionType.SKIP]
        content_budget = SLIDE_BUDGET - MANDATORY_SLIDES

        data_sections = [s for s in content_sections if s.content_type == ContentType.DATA]
        chart_candidates = len(data_sections)

        overflow = OverflowStatus(
            sections_over_budget=len(content_sections) > content_budget,
            tables_over_budget=chart_candidates > MAX_CHART_SLIDES,
            charts_candidates=chart_candidates,
            recommended_chart_slots=min(MAX_CHART_SLIDES, chart_candidates),
        )

        inventory = ContentInventory(
            title=title,
            subtitle=subtitle,
            total_words=total_words,
            total_sections=len(content_sections),
            has_toc=has_toc,
            has_executive_summary=has_exec_summary,
            has_references=has_references,
            has_appendix=has_appendix,
            total_tables=total_tables,
            total_bullets=total_bullets,
            sections=sections,
            overflow=overflow,
        )
        # Store AST tokens so Step 3 can reuse them without re-parsing
        inventory.set_ast_tokens(tokens)

        return inventory

    def _extract_title(self, tokens: List[Dict]) -> Tuple[Optional[str], Optional[str]]:
        """Extract document title (H1) and optional subtitle."""
        title = None
        subtitle = None

        for i, token in enumerate(tokens):
            if token.get('type') == 'heading' and token.get('attrs', {}).get('level') == 1:
                title = self._get_text_content(token)
                if i + 1 < len(tokens) and tokens[i + 1].get('type') == 'paragraph':
                    subtitle = self._get_text_content(tokens[i + 1])
                    if len(subtitle) > 200:
                        subtitle = subtitle[:200] + "..."
                break

        return title, subtitle

    def _extract_sections(self, tokens: List[Dict]) -> List[Section]:
        """Extract content sections from tokens."""
        sections: List[Section] = []
        current_section: Optional[Section] = None
        section_counter = 0
        table_counter = 0

        for token in tokens:
            token_type = token.get('type')

            if token_type == 'heading':
                level = token.get('attrs', {}).get('level', 1)
                heading_text = self._get_text_content(token)

                if current_section:
                    sections.append(current_section)

                section_type = classify_section_type(heading_text)
                section_id = f"sec_{section_counter}"

                current_section = Section(
                    id=section_id,
                    heading=heading_text,
                    level=level,
                    section_type=section_type,
                    content_type=ContentType.TEXT,
                    parent_id=None,
                )
                section_counter += 1

            elif current_section:
                self._accumulate_content(token, current_section, table_counter)
                if token_type == 'table':
                    table_counter += 1

        if current_section:
            sections.append(current_section)

        sections = self._set_hierarchy(sections)
        sections = self._classify_section_content(sections)

        return sections

    def _accumulate_content(self, token: Dict, section: Section, table_counter: int) -> None:
        """Accumulate content metrics and raw text from a token into a section."""
        token_type = token.get('type')

        if token_type == 'paragraph':
            text = self._get_text_content(token)
            section.word_count += len(text.split())
            section.paragraph_count += 1
            section.raw_text += text + "\n"

        elif token_type == 'list':
            items = token.get('children', [])
            section.bullet_count += len(items)
            for item in items:
                text = self._get_text_content(item)
                section.word_count += len(text.split())
                section.raw_text += text + "\n"

        elif token_type == 'table':
            table_info = self._parse_table(token, table_counter)
            section.tables.append(table_info)
            section.table_count += 1

    def _parse_table(self, token: Dict, table_index: int) -> TableInfo:
        """Parse a table token into TableInfo with deterministic chart type."""
        children = token.get('children', [])

        table_head = None
        table_body = None

        for child in children:
            child_type = child.get('type')
            if child_type == 'table_head':
                table_head = child
            elif child_type == 'table_body':
                table_body = child

        if not table_head and children:
            header_row = [self._get_text_content(cell) for cell in children[0].get('children', [])]
            body_tokens = children[1:] if len(children) > 1 else []
        else:
            head_children = table_head.get('children', []) if table_head else []
            header_row = [self._get_text_content(cell) for cell in head_children]
            body_tokens = table_body.get('children', []) if table_body else []

        data_rows: List[List[str]] = []
        for row_token in body_tokens:
            row_cells = row_token.get('children', [])
            row = [self._get_text_content(cell) for cell in row_cells]
            data_rows.append(row)

        num_cols = len(header_row)
        num_rows = len(data_rows)

        column_values = []
        for col_idx in range(num_cols):
            vals = [row[col_idx] if col_idx < len(row) else "" for row in data_rows]
            column_values.append(vals)

        numeric_cols = []
        temporal_cols = []
        for col_idx in range(num_cols):
            header = header_row[col_idx] if col_idx < len(header_row) else ""
            vals = column_values[col_idx] if col_idx < len(column_values) else []

            if is_numeric_column(header, vals):
                numeric_cols.append(col_idx)
            if is_temporal_column(header, vals):
                temporal_cols.append(col_idx)

        has_numeric = len(numeric_cols) > 0
        has_temporal = len(temporal_cols) > 0

        table_info = TableInfo(
            index=table_index,
            rows=num_rows,
            cols=num_cols,
            has_numeric=has_numeric,
            has_temporal=has_temporal,
            numeric_columns=numeric_cols,
            temporal_columns=temporal_cols,
            header_row=header_row,
        )

        # Deterministic chart type selection (REUSE-4: PPT Master quickLookup pattern)
        if has_numeric:
            table_info.recommended_chart_type = select_chart_type(
                table_info, header_row, data_rows
            )

        return table_info

    def _set_hierarchy(self, sections: List[Section]) -> List[Section]:
        """Set parent-child relationships between sections."""
        if not sections:
            return sections

        stack: List[Tuple[int, str]] = []

        for section in sections:
            while stack and stack[-1][0] >= section.level:
                stack.pop()

            if stack:
                section.parent_id = stack[-1][1]

            stack.append((section.level, section.id))

        section_map = {s.id: s for s in sections}
        for section in sections:
            if section.parent_id and section.parent_id in section_map:
                parent = section_map[section.parent_id]
                parent.subsection_ids.append(section.id)

        return sections

    def _classify_section_content(self, sections: List[Section]) -> List[Section]:
        """Classify content type and detect layout hints using full section text."""
        section_map = {s.id: s for s in sections}

        for section in sections:
            has_numeric_table = any(t.has_numeric for t in section.tables)
            section.content_type = classify_content_type(
                section.table_count,
                section.bullet_count,
                has_numeric_table,
            )

            # Use full accumulated text for detection (BUG-6 fix)
            combined_text = self._get_section_combined_text(section, section_map)
            section.has_comparison = detect_comparison(section.heading, combined_text)
            section.has_process = detect_process(section.heading, combined_text)
            section.has_timeline = detect_timeline(section.heading, combined_text)

        return sections

    def _get_section_combined_text(self, section: Section, section_map: Dict[str, Section]) -> str:
        """Get combined text of a section and its subsections."""
        parts = [section.raw_text]
        for sub_id in section.subsection_ids:
            sub = section_map.get(sub_id)
            if sub:
                parts.append(sub.raw_text)
        return " ".join(parts)

    def _get_text_content(self, token: Dict) -> str:
        """Extract plain text content from a token recursively."""
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

    def parse_file(self, filepath: Path) -> ContentInventory:
        """Parse a markdown file."""
        markdown_text = filepath.read_text(encoding='utf-8')
        return self.parse(markdown_text)
