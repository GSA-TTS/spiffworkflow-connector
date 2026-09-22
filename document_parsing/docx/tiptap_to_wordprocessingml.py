"""Convert the application's constrained TipTap HTML to WordprocessingML.

This is shamelessly bald LLM-generated code. It should be considered
safe for demo purposes only, not for production. We use it simply
for the sake of quickly spinning up something that can support upcoming
demo/testing requirements.

See ADR: https://github.com/GSA-TTS/pic-blm-cxworks/pull/1153.

This is deliberately not a general HTML-to-DOCX converter. Unsupported
structures fail loudly so that document generation never silently drops data.
"""

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from urllib.parse import urlparse

import lxml.etree as etree
import lxml.html as html

WORDPROCESSINGML_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"

W = f"{{{WORDPROCESSINGML_NAMESPACE}}}"
R = f"{{{RELATIONSHIPS_NAMESPACE}}}"


class UnsupportedRichTextError(ValueError):
    """Raised when TipTap HTML cannot be represented by this converter."""


@dataclass(frozen=True)
class RunStyle:
    bold: bool = False
    italic: bool = False
    underline: bool = False


class TiptapToWordprocessingML:
    """Render sanitized TipTap HTML as block-level WordprocessingML nodes."""

    _INLINE_TAGS = {"strong", "b", "em", "i", "u", "a", "br", "span"}
    _MAX_HTML_LENGTH = 1_000_000
    _MAX_LIST_LEVEL = 8
    _MAX_TABLE_ROWS = 1_000
    _MAX_TABLE_COLUMNS = 100

    def __init__(
        self,
        *,
        register_hyperlink: Callable[[str], str],
        create_numbering: Callable[[bool, int, int], int],
    ) -> None:
        self._register_hyperlink = register_hyperlink
        self._create_numbering = create_numbering

    def convert(
        self,
        value: str,
        *,
        paragraph_properties: etree._Element | None = None,
    ) -> list[etree._Element]:
        if len(value) > self._MAX_HTML_LENGTH:
            raise UnsupportedRichTextError(f"Rich-text HTML exceeds {self._MAX_HTML_LENGTH} characters")
        if not value.strip():
            return [self._paragraph(paragraph_properties)]

        try:
            fragment = html.fragment_fromstring(value, create_parent=True)
        except (etree.ParserError, ValueError) as error:
            raise UnsupportedRichTextError("Invalid rich-text HTML") from error

        blocks: list[etree._Element] = []
        if fragment.text and fragment.text.strip():
            paragraph = self._paragraph(paragraph_properties)
            self._append_text(paragraph, fragment.text, RunStyle())
            blocks.append(paragraph)

        for child in fragment:
            blocks.extend(self._convert_block(child, paragraph_properties))
            if child.tail and child.tail.strip():
                paragraph = self._paragraph(paragraph_properties)
                self._append_text(paragraph, child.tail, RunStyle())
                blocks.append(paragraph)

        return blocks or [self._paragraph(paragraph_properties)]

    def _convert_block(
        self,
        element: etree._Element,
        paragraph_properties: etree._Element | None,
    ) -> list[etree._Element]:
        tag = self._tag(element)
        if tag == "p":
            paragraph = self._paragraph(paragraph_properties)
            self._append_inline_children(paragraph, element, RunStyle())
            return [paragraph]
        if tag in {"ul", "ol"}:
            return self._convert_list(element, paragraph_properties, level=0)
        if tag == "table":
            return [self._convert_table(element, paragraph_properties)]
        raise UnsupportedRichTextError(f"Unsupported block element: <{tag}>")

    def _convert_list(
        self,
        element: etree._Element,
        paragraph_properties: etree._Element | None,
        *,
        level: int,
    ) -> list[etree._Element]:
        if level > self._MAX_LIST_LEVEL:
            raise UnsupportedRichTextError("Word lists support at most 9 levels")

        tag = self._tag(element)
        ordered = tag == "ol"
        start = self._ordered_list_start(element) if ordered else 1
        # Every list receives a distinct numbering instance. This makes separate
        # ordered lists restart and lets nested lists change list type safely.
        num_id = self._create_numbering(ordered, start, level)
        result: list[etree._Element] = []

        for item in element:
            item_tag = self._tag(item)
            if item_tag != "li":
                raise UnsupportedRichTextError(f"Unsupported child of <{tag}>: <{item_tag}>")
            result.extend(
                self._convert_list_item(
                    item,
                    paragraph_properties,
                    level=level,
                    num_id=num_id,
                )
            )
        return result

    def _convert_list_item(
        self,
        item: etree._Element,
        paragraph_properties: etree._Element | None,
        *,
        level: int,
        num_id: int,
    ) -> list[etree._Element]:
        result: list[etree._Element] = []
        numbered = self._numbered_paragraph(paragraph_properties, level, num_id)

        if item.text:
            self._append_text(numbered, item.text, RunStyle())

        paragraph_seen = False
        for child in item:
            tag = self._tag(child)
            if tag in {"ul", "ol"}:
                if numbered not in result:
                    result.append(numbered)
                result.extend(self._convert_list(child, paragraph_properties, level=level + 1))
            elif tag == "p":
                if not paragraph_seen:
                    self._append_inline_children(numbered, child, RunStyle())
                    if numbered not in result:
                        result.append(numbered)
                    paragraph_seen = True
                else:
                    continuation = self._continuation_paragraph(paragraph_properties, level)
                    self._append_inline_children(continuation, child, RunStyle())
                    result.append(continuation)
            elif tag in self._INLINE_TAGS:
                self._append_inline(numbered, child, RunStyle())
            else:
                raise UnsupportedRichTextError(f"Unsupported element inside <li>: <{tag}>")

            if child.tail:
                self._append_text(numbered, child.tail, RunStyle())

        if numbered not in result:
            result.insert(0, numbered)
        return result

    def _convert_table(
        self,
        source_table: etree._Element,
        paragraph_properties: etree._Element | None,
    ) -> etree._Element:
        allowed_children = {"colgroup", "thead", "tbody", "tfoot", "tr"}
        for child in source_table:
            tag = self._tag(child)
            if tag not in allowed_children:
                raise UnsupportedRichTextError(f"Unsupported child of <table>: <{tag}>")

        source_rows = source_table.xpath("./thead/tr | ./tbody/tr | ./tfoot/tr | ./tr")
        if len(source_rows) > self._MAX_TABLE_ROWS:
            raise UnsupportedRichTextError(f"Tables support at most {self._MAX_TABLE_ROWS} rows")

        table = etree.Element(f"{W}tbl")
        table_pr = etree.SubElement(table, f"{W}tblPr")
        etree.SubElement(table_pr, f"{W}tblStyle").set(f"{W}val", "TableGrid")

        for source_row in source_rows:
            source_cells = list(source_row)
            if len(source_cells) > self._MAX_TABLE_COLUMNS:
                raise UnsupportedRichTextError(f"Tables support at most {self._MAX_TABLE_COLUMNS} columns")
            row = etree.SubElement(table, f"{W}tr")
            for source_cell in source_cells:
                cell_tag = self._tag(source_cell)
                if cell_tag not in {"td", "th"}:
                    raise UnsupportedRichTextError(f"Unsupported child of <tr>: <{cell_tag}>")
                self._append_table_cell(
                    row,
                    source_cell,
                    paragraph_properties,
                    header=cell_tag == "th",
                )
        return table

    def _append_table_cell(
        self,
        row: etree._Element,
        source_cell: etree._Element,
        paragraph_properties: etree._Element | None,
        *,
        header: bool,
    ) -> None:
        colspan = self._positive_integer_attribute(source_cell, "colspan", default=1)
        rowspan = self._positive_integer_attribute(source_cell, "rowspan", default=1)
        if rowspan != 1:
            raise UnsupportedRichTextError("Table rowspan is not supported")

        cell = etree.SubElement(row, f"{W}tc")
        cell_pr = etree.SubElement(cell, f"{W}tcPr")
        if colspan > 1:
            etree.SubElement(cell_pr, f"{W}gridSpan").set(f"{W}val", str(colspan))

        block_children = [child for child in source_cell if self._tag(child) in {"p", "ul", "ol"}]
        unsupported = [self._tag(child) for child in source_cell if self._tag(child) not in {"p", "ul", "ol"}]
        if unsupported:
            raise UnsupportedRichTextError(f"Unsupported element inside table cell: <{unsupported[0]}>")

        if block_children:
            for source_block in block_children:
                tag = self._tag(source_block)
                if tag == "p":
                    paragraph = self._paragraph(paragraph_properties)
                    self._append_inline_children(
                        paragraph,
                        source_block,
                        RunStyle(bold=header),
                    )
                    cell.append(paragraph)
                else:
                    for block in self._convert_list(source_block, paragraph_properties, level=0):
                        cell.append(block)
        else:
            paragraph = self._paragraph(paragraph_properties)
            self._append_inline_children(paragraph, source_cell, RunStyle(bold=header))
            cell.append(paragraph)

    def _append_inline_children(
        self,
        container: etree._Element,
        source: etree._Element,
        style: RunStyle,
    ) -> None:
        if source.text:
            self._append_text(container, source.text, style)
        for child in source:
            self._append_inline(container, child, style)
            if child.tail:
                self._append_text(container, child.tail, style)

    def _append_inline(
        self,
        container: etree._Element,
        element: etree._Element,
        style: RunStyle,
    ) -> None:
        tag = self._tag(element)
        if tag in {"strong", "b"}:
            next_style = RunStyle(True, style.italic, style.underline)
            self._append_inline_children(container, element, next_style)
        elif tag in {"em", "i"}:
            next_style = RunStyle(style.bold, True, style.underline)
            self._append_inline_children(container, element, next_style)
        elif tag == "u":
            next_style = RunStyle(style.bold, style.italic, True)
            self._append_inline_children(container, element, next_style)
        elif tag == "span":
            self._append_inline_children(container, element, style)
        elif tag == "br":
            run = self._run(style)
            etree.SubElement(run, f"{W}br")
            container.append(run)
        elif tag == "a":
            href = self._validated_href(element.get("href", ""))
            hyperlink = etree.Element(f"{W}hyperlink")
            hyperlink.set(f"{R}id", self._register_hyperlink(href))
            self._append_inline_children(hyperlink, element, style)
            for run in hyperlink.findall(f"{W}r"):
                properties = self._ensure_first(run, "rPr")
                color = etree.Element(f"{W}color")
                color.set(f"{W}val", "0563C1")
                properties.append(color)
                if properties.find(f"{W}u") is None:
                    etree.SubElement(properties, f"{W}u").set(f"{W}val", "single")
            container.append(hyperlink)
        else:
            raise UnsupportedRichTextError(f"Unsupported inline element: <{tag}>")

    def _append_text(
        self,
        container: etree._Element,
        value: str,
        style: RunStyle,
    ) -> None:
        if not value:
            return
        run = self._run(style)
        text = etree.SubElement(run, f"{W}t")
        if value[:1].isspace() or value[-1:].isspace() or "  " in value:
            text.set(f"{{{XML_NAMESPACE}}}space", "preserve")
        text.text = value
        container.append(run)

    @staticmethod
    def _run(style: RunStyle) -> etree._Element:
        run = etree.Element(f"{W}r")
        if style.bold or style.italic or style.underline:
            properties = etree.SubElement(run, f"{W}rPr")
            if style.bold:
                etree.SubElement(properties, f"{W}b")
            if style.italic:
                etree.SubElement(properties, f"{W}i")
            if style.underline:
                etree.SubElement(properties, f"{W}u").set(f"{W}val", "single")
        return run

    @staticmethod
    def _paragraph(
        paragraph_properties: etree._Element | None,
    ) -> etree._Element:
        paragraph = etree.Element(f"{W}p")
        if paragraph_properties is not None:
            paragraph.append(deepcopy(paragraph_properties))
        return paragraph

    def _numbered_paragraph(
        self,
        paragraph_properties: etree._Element | None,
        level: int,
        num_id: int,
    ) -> etree._Element:
        paragraph = self._paragraph(paragraph_properties)
        p_pr = self._ensure_first(paragraph, "pPr")
        existing = p_pr.find(f"{W}numPr")
        if existing is not None:
            p_pr.remove(existing)
        num_pr = etree.Element(f"{W}numPr")
        # pStyle precedes numPr in the WordprocessingML pPr sequence. Placing
        # numPr here also avoids leaving it after run properties copied from
        # the template paragraph.
        p_style = p_pr.find(f"{W}pStyle")
        p_pr.insert(1 if p_style is not None else 0, num_pr)
        etree.SubElement(num_pr, f"{W}ilvl").set(f"{W}val", str(level))
        etree.SubElement(num_pr, f"{W}numId").set(f"{W}val", str(num_id))
        return paragraph

    def _continuation_paragraph(
        self,
        paragraph_properties: etree._Element | None,
        level: int,
    ) -> etree._Element:
        paragraph = self._paragraph(paragraph_properties)
        p_pr = self._ensure_first(paragraph, "pPr")
        existing = p_pr.find(f"{W}numPr")
        if existing is not None:
            p_pr.remove(existing)
        indentation = p_pr.find(f"{W}ind")
        if indentation is None:
            indentation = etree.SubElement(p_pr, f"{W}ind")
        indentation.set(f"{W}left", str(720 * (level + 1)))
        return paragraph

    @staticmethod
    def _ensure_first(
        parent: etree._Element,
        local_name: str,
    ) -> etree._Element:
        existing = parent.find(f"{W}{local_name}")
        if existing is not None:
            return existing
        child = etree.Element(f"{W}{local_name}")
        parent.insert(0, child)
        return child

    @staticmethod
    def _tag(element: etree._Element) -> str:
        if not isinstance(element.tag, str):
            raise UnsupportedRichTextError("Comments are not supported in rich text")
        return etree.QName(element).localname.lower()

    @staticmethod
    def _validated_href(href: str) -> str:
        parsed = urlparse(href)
        if parsed.scheme.lower() not in {"http", "https", "mailto"}:
            raise UnsupportedRichTextError(f"Unsupported link URL: {href!r}")
        return href

    @staticmethod
    def _ordered_list_start(element: etree._Element) -> int:
        return TiptapToWordprocessingML._positive_integer_attribute(element, "start", default=1)

    @staticmethod
    def _positive_integer_attribute(
        element: etree._Element,
        name: str,
        *,
        default: int,
    ) -> int:
        raw_value = element.get(name)
        if raw_value is None:
            return default
        try:
            value = int(raw_value)
        except ValueError as error:
            raise UnsupportedRichTextError(f"Invalid {name} value: {raw_value!r}") from error
        if value < 1:
            raise UnsupportedRichTextError(f"{name} must be at least 1")
        return value
