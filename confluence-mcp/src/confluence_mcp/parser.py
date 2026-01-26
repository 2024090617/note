"""
Confluence Content Parser

Handles parsing complex Confluence elements:
- Multi-tab groups (structured with tabs)
- Tables (with cell formatting)
- Macros (code, info boxes, etc.)
- Nested content
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from html import unescape
from bs4 import BeautifulSoup, Tag, NavigableString


# =========================================================================
# Data Models for Confluence Elements
# =========================================================================

@dataclass
class TableCell:
    """Represents a table cell"""
    content: str
    is_header: bool = False
    colspan: int = 1
    rowspan: int = 1
    attributes: dict = field(default_factory=dict)


@dataclass
class TableRow:
    """Represents a table row"""
    cells: list[TableCell]
    is_header: bool = False


@dataclass
class Table:
    """Represents a Confluence table"""
    rows: list[TableRow]
    title: Optional[str] = None
    
    def to_markdown(self) -> str:
        """Convert table to Markdown format"""
        if not self.rows:
            return ""
        
        lines = []
        
        # Markdown table header
        header_row = self.rows[0]
        header_cells = [cell.content for cell in header_row.cells]
        lines.append("| " + " | ".join(header_cells) + " |")
        lines.append("|" + "|".join(["---"] * len(header_cells)) + "|")
        
        # Markdown table rows
        for row in self.rows[1:]:
            row_cells = [cell.content for cell in row.cells]
            lines.append("| " + " | ".join(row_cells) + " |")
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        """Convert table to dict format"""
        rows_data = []
        for row in self.rows:
            row_data = {
                "cells": [
                    {
                        "content": cell.content,
                        "header": cell.is_header,
                        "colspan": cell.colspan,
                        "rowspan": cell.rowspan,
                    }
                    for cell in row.cells
                ],
                "is_header": row.is_header,
            }
            rows_data.append(row_data)
        
        return {
            "type": "table",
            "title": self.title,
            "rows": rows_data,
        }


@dataclass
class Tab:
    """Represents a single tab in a tab group"""
    title: str
    content: str
    identifier: str = ""


@dataclass
class TabGroup:
    """Represents a group of tabs in Confluence"""
    tabs: list[Tab] = field(default_factory=list)
    title: Optional[str] = None
    
    def to_markdown(self) -> str:
        """Convert tab group to Markdown (as headings + content)"""
        lines = []
        
        for i, tab in enumerate(self.tabs):
            # Use ## for tabs
            lines.append(f"### {tab.title}")
            lines.append("")
            lines.append(tab.content)
            lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        """Convert tab group to dict format"""
        return {
            "type": "tabs",
            "title": self.title,
            "tabs": [
                {
                    "title": tab.title,
                    "content": tab.content,
                    "identifier": tab.identifier,
                }
                for tab in self.tabs
            ],
        }


@dataclass
class CodeBlock:
    """Represents a code block"""
    code: str
    language: str = ""
    title: Optional[str] = None
    
    def to_markdown(self) -> str:
        """Convert to Markdown code block"""
        fence = "```" + self.language
        return f"{fence}\n{self.code}\n```"


@dataclass
class InfoBox:
    """Represents an info/warning box"""
    content: str
    box_type: str = "info"  # info, warning, note, error
    title: Optional[str] = None


# =========================================================================
# Content Parser
# =========================================================================

class ContentParser:
    """Parse Confluence storage format (XHTML) into structured content"""
    
    def __init__(self):
        self.soup: Optional[BeautifulSoup] = None
    
    def parse(self, html: str) -> dict:
        """
        Parse Confluence storage format HTML
        
        Args:
            html: Confluence storage format XHTML
        
        Returns:
            Structured content dict with elements
        """
        self.soup = BeautifulSoup(html, "lxml-xml")
        
        content = {
            "text": self._parse_text(),
            "tables": self._parse_tables(),
            "tabs": self._parse_tabs(),
            "code_blocks": self._parse_code_blocks(),
            "info_boxes": self._parse_info_boxes(),
            "raw_html": html,
        }
        
        return content
    
    def _parse_text(self) -> str:
        """Extract plain text content"""
        if not self.soup:
            return ""
        
        # Get text content, preserving structure
        text_parts = []
        
        for element in self.soup.find_all(True):
            if element.name in ["p", "div", "h1", "h2", "h3", "h4", "h5", "h6"]:
                text = element.get_text(strip=True)
                if text:
                    text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    def _parse_tables(self) -> list[dict]:
        """Parse all tables from content"""
        if not self.soup:
            return []
        
        tables = []
        
        for table_elem in self.soup.find_all("table"):
            table = self._parse_table(table_elem)
            if table.rows:
                tables.append(table.to_dict())
        
        return tables
    
    def _parse_table(self, table_elem: Tag) -> Table:
        """Parse a single table element"""
        rows = []
        
        for row_elem in table_elem.find_all("tr"):
            row = self._parse_table_row(row_elem)
            rows.append(row)
        
        return Table(rows=rows)
    
    def _parse_table_row(self, row_elem: Tag) -> TableRow:
        """Parse a table row"""
        cells = []
        is_header = False
        
        # Check if this is a header row
        if row_elem.find("th"):
            is_header = True
        
        for cell_elem in row_elem.find_all(["th", "td"]):
            cell = self._parse_table_cell(cell_elem)
            cells.append(cell)
        
        return TableRow(cells=cells, is_header=is_header)
    
    def _parse_table_cell(self, cell_elem: Tag) -> TableCell:
        """Parse a table cell"""
        # Get cell content (text and nested formatting)
        content = self._get_element_text_with_formatting(cell_elem)
        
        # Get attributes
        colspan = int(cell_elem.get("colspan", 1))
        rowspan = int(cell_elem.get("rowspan", 1))
        
        is_header = cell_elem.name == "th"
        
        return TableCell(
            content=content,
            is_header=is_header,
            colspan=colspan,
            rowspan=rowspan,
            attributes={
                "class": cell_elem.get("class", []),
                "style": cell_elem.get("style", ""),
            },
        )
    
    def _parse_tabs(self) -> list[dict]:
        """Parse tab groups from content"""
        if not self.soup:
            return []
        
        tab_groups = []
        
        # Confluence uses structured-macro for tabs
        for macro in self.soup.find_all("ac:structured-macro"):
            if macro.get("ac:name") == "tabs":
                tab_group = self._parse_tab_macro(macro)
                if tab_group.tabs:
                    tab_groups.append(tab_group.to_dict())
        
        return tab_groups
    
    def _parse_tab_macro(self, macro_elem: Tag) -> TabGroup:
        """Parse a tabs structured macro"""
        tabs = []
        
        # Find all tab elements
        for tab_elem in macro_elem.find_all("ac:structured-macro"):
            if tab_elem.get("ac:name") == "tab":
                tab = self._parse_single_tab(tab_elem)
                if tab:
                    tabs.append(tab)
        
        return TabGroup(tabs=tabs)
    
    def _parse_single_tab(self, tab_elem: Tag) -> Optional[Tab]:
        """Parse a single tab element"""
        # Get tab title from parameter
        title_param = tab_elem.find("ac:parameter", {"ac:name": "title"})
        title = title_param.get_text(strip=True) if title_param else "Untitled"
        
        # Get tab content
        body = tab_elem.find("ac:rich-text-body")
        content = ""
        
        if body:
            content = self._get_element_text_with_formatting(body)
        
        return Tab(title=title, content=content)
    
    def _parse_code_blocks(self) -> list[dict]:
        """Parse code blocks from content"""
        if not self.soup:
            return []
        
        code_blocks = []
        
        # Find code macros
        for macro in self.soup.find_all("ac:structured-macro"):
            if macro.get("ac:name") == "code":
                code_block = self._parse_code_macro(macro)
                if code_block:
                    code_blocks.append({
                        "type": "code",
                        "language": code_block.language,
                        "title": code_block.title,
                        "code": code_block.code,
                    })
        
        return code_blocks
    
    def _parse_code_macro(self, macro_elem: Tag) -> Optional[CodeBlock]:
        """Parse a code block macro"""
        # Get language
        lang_param = macro_elem.find("ac:parameter", {"ac:name": "language"})
        language = lang_param.get_text(strip=True) if lang_param else ""
        
        # Get title
        title_param = macro_elem.find("ac:parameter", {"ac:name": "title"})
        title = title_param.get_text(strip=True) if title_param else None
        
        # Get code content
        body = macro_elem.find("ac:plain-text-body")
        code = body.get_text() if body else ""
        
        if code:
            return CodeBlock(code=code, language=language, title=title)
        
        return None
    
    def _parse_info_boxes(self) -> list[dict]:
        """Parse info/warning/note boxes"""
        if not self.soup:
            return []
        
        boxes = []
        
        # Find info, warning, note, error macros
        for macro_type in ["info", "warning", "note", "error"]:
            for macro in self.soup.find_all("ac:structured-macro"):
                if macro.get("ac:name") == macro_type:
                    box = self._parse_info_macro(macro, macro_type)
                    if box:
                        boxes.append({
                            "type": "infobox",
                            "box_type": box.box_type,
                            "title": box.title,
                            "content": box.content,
                        })
        
        return boxes
    
    def _parse_info_macro(self, macro_elem: Tag, box_type: str) -> Optional[InfoBox]:
        """Parse an info/warning/note macro"""
        title_param = macro_elem.find("ac:parameter", {"ac:name": "title"})
        title = title_param.get_text(strip=True) if title_param else None
        
        body = macro_elem.find("ac:rich-text-body")
        content = self._get_element_text_with_formatting(body) if body else ""
        
        if content:
            return InfoBox(content=content, box_type=box_type, title=title)
        
        return None
    
    def _get_element_text_with_formatting(self, elem: Tag) -> str:
        """
        Get text from element preserving formatting hints
        (bold, italic, links, lists)
        """
        text_parts = []
        
        for child in elem.descendants:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    text_parts.append(text)
            elif isinstance(child, Tag):
                if child.name == "strong" or child.name == "b":
                    text_parts.append(f"**{child.get_text()}**")
                elif child.name == "em" or child.name == "i":
                    text_parts.append(f"*{child.get_text()}*")
                elif child.name == "a":
                    href = child.get("href", "")
                    text = child.get_text()
                    text_parts.append(f"[{text}]({href})")
                elif child.name == "li":
                    text = child.get_text().strip()
                    if text:
                        text_parts.append(f"- {text}")
                elif child.name == "br":
                    text_parts.append("\n")
        
        return " ".join(text_parts)
    
    def extract_markdown(self) -> str:
        """Convert parsed content to Markdown format"""
        if not self.soup:
            return ""
        
        lines = []
        
        # Add main text content
        text = self._parse_text()
        if text:
            lines.append(text)
        
        # Add code blocks
        for code_block_data in self._parse_code_blocks():
            code = CodeBlock(
                code=code_block_data["code"],
                language=code_block_data["language"],
                title=code_block_data["title"],
            )
            lines.append(code.to_markdown())
        
        # Add info boxes
        for box_data in self._parse_info_boxes():
            lines.append(f"\n> **[{box_data['box_type'].upper()}]** {box_data['content']}\n")
        
        # Add tables
        for table_data in self._parse_tables():
            table_rows = [
                TableRow(
                    cells=[
                        TableCell(
                            content=cell["content"],
                            is_header=cell["header"],
                        )
                        for cell in row["cells"]
                    ],
                    is_header=row["is_header"],
                )
                for row in table_data["rows"]
            ]
            table = Table(rows=table_rows)
            lines.append(table.to_markdown())
        
        # Add tabs
        for tab_group_data in self._parse_tabs():
            tabs = [
                Tab(
                    title=tab["title"],
                    content=tab["content"],
                    identifier=tab["identifier"],
                )
                for tab in tab_group_data["tabs"]
            ]
            tab_group = TabGroup(tabs=tabs)
            lines.append(tab_group.to_markdown())
        
        return "\n\n".join(filter(None, lines))
