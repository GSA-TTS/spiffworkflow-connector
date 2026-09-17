"""Read and populate DOCX content controls."""

from collections.abc import Collection
from enum import Enum
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import lxml.etree as etree

from ..document_parser import DocumentParser
from .tiptap_to_wordprocessingml import (
    WORDPROCESSINGML_NAMESPACE,
    TiptapToWordprocessingML,
)

NAMESPACES = {"w": WORDPROCESSINGML_NAMESPACE}
W = f"{{{WORDPROCESSINGML_NAMESPACE}}}"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"

PACKAGE_RELATIONSHIPS_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"
HYPERLINK_RELATIONSHIP_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
NUMBERING_RELATIONSHIP_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering"
NUMBERING_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"
CONTENT_TYPES_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/content-types"

DOCUMENT_XML = "word/document.xml"
DOCUMENT_RELS_XML = "word/_rels/document.xml.rels"
NUMBERING_XML = "word/numbering.xml"
CONTENT_TYPES_XML = "[Content_Types].xml"


class ContentControlKind(Enum):
    BLOCK = "block"
    TABLE_CELL = "table_cell"


class RelationshipManager:
    def __init__(self, contents: bytes | None) -> None:
        self.root = (
            etree.fromstring(contents)
            if contents is not None
            else etree.Element(f"{{{PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationships")
        )
        self.dirty = False

    def register_hyperlink(self, url: str) -> str:
        for relationship in self.root:
            if (
                relationship.get("Type") == HYPERLINK_RELATIONSHIP_TYPE
                and relationship.get("Target") == url
                and relationship.get("TargetMode") == "External"
            ):
                relationship_id = relationship.get("Id")
                if relationship_id is not None:
                    return relationship_id

        relationship_id = self.next_id()
        relationship = etree.SubElement(
            self.root,
            f"{{{PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationship",
        )
        relationship.set("Id", relationship_id)
        relationship.set("Type", HYPERLINK_RELATIONSHIP_TYPE)
        relationship.set("Target", url)
        relationship.set("TargetMode", "External")
        self.dirty = True
        return relationship_id

    def ensure_numbering(self) -> None:
        if any(relationship.get("Type") == NUMBERING_RELATIONSHIP_TYPE for relationship in self.root):
            return
        relationship = etree.SubElement(
            self.root,
            f"{{{PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationship",
        )
        relationship.set("Id", self.next_id())
        relationship.set("Type", NUMBERING_RELATIONSHIP_TYPE)
        relationship.set("Target", "numbering.xml")
        self.dirty = True

    def next_id(self) -> str:
        used = {element.get("Id") for element in self.root}
        number = 1
        while f"rId{number}" in used:
            number += 1
        return f"rId{number}"


class NumberingManager:
    def __init__(self, contents: bytes | None) -> None:
        self._contents = contents
        self._root: etree._Element | None = None
        self.dirty = False

    @property
    def root(self) -> etree._Element:
        if self._root is None:
            self._root = (
                etree.fromstring(self._contents)
                if self._contents is not None
                else etree.Element(
                    f"{W}numbering",
                    nsmap={"w": WORDPROCESSINGML_NAMESPACE},
                )
            )
        return self._root

    def create(self, ordered: bool, start: int, level: int) -> int:
        root = self.root
        abstract_ids = [int(value) for value in root.xpath("./w:abstractNum/@w:abstractNumId", namespaces=NAMESPACES)]
        num_ids = [int(value) for value in root.xpath("./w:num/@w:numId", namespaces=NAMESPACES)]
        abstract_id = max(abstract_ids, default=-1) + 1
        num_id = max(num_ids, default=0) + 1

        self._append_abstract_numbering(
            root,
            abstract_id,
            ordered=ordered,
            start=start,
            active_level=level,
        )
        num = etree.SubElement(root, f"{W}num")
        num.set(f"{W}numId", str(num_id))
        etree.SubElement(num, f"{W}abstractNumId").set(f"{W}val", str(abstract_id))
        self.dirty = True
        return num_id

    @staticmethod
    def _append_abstract_numbering(
        root: etree._Element,
        abstract_id: int,
        *,
        ordered: bool,
        start: int,
        active_level: int,
    ) -> None:
        abstract = etree.SubElement(root, f"{W}abstractNum")
        abstract.set(f"{W}abstractNumId", str(abstract_id))
        etree.SubElement(abstract, f"{W}multiLevelType").set(f"{W}val", "multilevel")
        bullets = ("•", "◦", "▪")
        for level in range(9):
            lvl = etree.SubElement(abstract, f"{W}lvl")
            lvl.set(f"{W}ilvl", str(level))
            etree.SubElement(lvl, f"{W}start").set(f"{W}val", str(start if level == active_level else 1))
            etree.SubElement(lvl, f"{W}numFmt").set(f"{W}val", "decimal" if ordered else "bullet")
            etree.SubElement(lvl, f"{W}lvlText").set(
                f"{W}val",
                f"%{level + 1}." if ordered else bullets[level % 3],
            )
            etree.SubElement(lvl, f"{W}lvlJc").set(f"{W}val", "left")
            p_pr = etree.SubElement(lvl, f"{W}pPr")
            tabs = etree.SubElement(p_pr, f"{W}tabs")
            etree.SubElement(
                tabs,
                f"{W}tab",
                **{f"{W}val": "num", f"{W}pos": str(720 * (level + 1))},
            )
            etree.SubElement(
                p_pr,
                f"{W}ind",
                **{
                    f"{W}left": str(720 * (level + 1)),
                    f"{W}hanging": "360",
                },
            )

        # The schema requires every abstractNum to precede every num. Move the
        # new definition before the first existing numbering instance.
        root.remove(abstract)
        first_num = root.find(f"{W}num")
        if first_num is None:
            root.append(abstract)
        else:
            root.insert(root.index(first_num), abstract)


class DocxParser(DocumentParser[bytes]):
    def _get_w_val(self, element, attr: str = "val"):
        if element is None:
            return None
        return element.get(f"{W}{attr}")

    def _get_content_control_key(self, sdt_pr):
        tag_el = sdt_pr.find("w:tag", namespaces=NAMESPACES)
        alias_el = sdt_pr.find("w:alias", namespaces=NAMESPACES)
        id_el = sdt_pr.find("w:id", namespaces=NAMESPACES)
        return self._get_w_val(tag_el) or self._get_w_val(alias_el) or self._get_w_val(id_el)

    def extract_data(self) -> dict[str, str]:
        with ZipFile(BytesIO(self.document)) as docx:
            xml = docx.read(DOCUMENT_XML)

        root = etree.fromstring(xml)
        fields: dict[str, str] = {}
        for sdt in root.xpath(".//w:sdt", namespaces=NAMESPACES):
            sdt_pr = sdt.find("w:sdtPr", namespaces=NAMESPACES)
            sdt_content = sdt.find("w:sdtContent", namespaces=NAMESPACES)
            if sdt_pr is None or sdt_content is None:
                continue
            key = self._get_content_control_key(sdt_pr)
            if key:
                texts = sdt_content.xpath(".//w:t/text()", namespaces=NAMESPACES)
                fields[key] = "".join(texts).strip()
        return fields

    def populate_document(
        self,
        data: dict[str, str],
        rich_text_fields: Collection[str] = (),
        **options: Any,
    ) -> bytes:
        input_buffer = BytesIO(self.document)
        output_buffer = BytesIO()

        with ZipFile(input_buffer, "r") as source:
            infos = source.infolist()
            entries = {item.filename: source.read(item.filename) for item in infos}

        document_root = etree.fromstring(entries[DOCUMENT_XML])
        relationships = RelationshipManager(entries.get(DOCUMENT_RELS_XML))
        numbering = NumberingManager(entries.get(NUMBERING_XML))
        converter = TiptapToWordprocessingML(
            register_hyperlink=relationships.register_hyperlink,
            create_numbering=numbering.create,
        )

        rich_text_field_set = set(rich_text_fields)
        for sdt in document_root.xpath(".//w:sdt", namespaces=NAMESPACES):
            sdt_pr = sdt.find("w:sdtPr", namespaces=NAMESPACES)
            sdt_content = sdt.find("w:sdtContent", namespaces=NAMESPACES)
            if sdt_pr is None or sdt_content is None:
                continue
            key = self._get_content_control_key(sdt_pr)
            if key not in data:
                continue

            if key in rich_text_field_set:
                self._set_rich_content_control_value(sdt, sdt_content, data[key], converter)
            else:
                self._set_content_control_value(sdt_content, data[key])

        entries[DOCUMENT_XML] = self._serialize(document_root)
        if numbering.dirty:
            entries[NUMBERING_XML] = self._serialize(numbering.root)
            relationships.ensure_numbering()
            self._ensure_numbering_content_type(entries)
        if relationships.dirty:
            entries[DOCUMENT_RELS_XML] = self._serialize(relationships.root)

        with ZipFile(output_buffer, "w", ZIP_DEFLATED) as destination:
            written: set[str] = set()
            for item in infos:
                destination.writestr(item, entries[item.filename])
                written.add(item.filename)
            for filename, contents in entries.items():
                if filename not in written:
                    destination.writestr(filename, contents)

        return output_buffer.getvalue()

    def _set_content_control_value(self, sdt_content, value: str) -> None:
        text_elements = sdt_content.xpath(".//w:t", namespaces=NAMESPACES)
        if not text_elements:
            return
        string_value = str(value)
        text_elements[0].text = string_value
        self._set_space_preservation(text_elements[0], string_value)
        for text_element in text_elements[1:]:
            text_element.text = ""
            text_element.attrib.pop(f"{{{XML_NAMESPACE}}}space", None)

    def _set_rich_content_control_value(
        self,
        sdt,
        sdt_content,
        value: str,
        converter: TiptapToWordprocessingML,
    ) -> None:
        kind = self._classify_rich_text_control(sdt, sdt_content)
        if kind is ContentControlKind.TABLE_CELL:
            self._set_rich_table_cell_content(sdt_content, value, converter)
        else:
            self._set_rich_block_content(sdt_content, value, converter)

        sdt_pr = sdt.find("w:sdtPr", namespaces=NAMESPACES)
        if sdt_pr is not None:
            text_property = sdt_pr.find("w:text", namespaces=NAMESPACES)
            if text_property is not None:
                sdt_pr.remove(text_property)

    def _classify_rich_text_control(
        self,
        sdt: etree._Element,
        sdt_content: etree._Element,
    ) -> ContentControlKind:
        parent = sdt.getparent()
        if parent is None:
            raise ValueError("Rich-text content control has no parent")
        if parent.tag == f"{W}p":
            raise ValueError("Rich-text content controls must be block-level; found one inside w:p")
        if parent.tag == f"{W}tr":
            if sdt_content.find("w:tc", namespaces=NAMESPACES) is None:
                raise ValueError("A content control inside w:tr must contain w:tc")
            return ContentControlKind.TABLE_CELL
        if parent.tag in {f"{W}body", f"{W}tc", f"{W}hdr", f"{W}ftr"}:
            return ContentControlKind.BLOCK
        parent_name = etree.QName(parent).localname
        raise ValueError(f"Unsupported rich-text content-control location: parent is w:{parent_name}")

    def _set_rich_block_content(
        self,
        sdt_content,
        value: str,
        converter: TiptapToWordprocessingML,
    ) -> None:
        placeholder = sdt_content.find("w:p", namespaces=NAMESPACES)
        paragraph_properties = placeholder.find("w:pPr", namespaces=NAMESPACES) if placeholder is not None else None
        replacement = converter.convert(value, paragraph_properties=paragraph_properties)
        for child in list(sdt_content):
            sdt_content.remove(child)
        sdt_content.extend(replacement)

    def _set_rich_table_cell_content(
        self,
        sdt_content,
        value: str,
        converter: TiptapToWordprocessingML,
    ) -> None:
        table_cell = sdt_content.find("w:tc", namespaces=NAMESPACES)
        if table_cell is None:
            raise ValueError("A content control inside w:tr must contain w:tc")
        placeholder = table_cell.find("w:p", namespaces=NAMESPACES)
        paragraph_properties = placeholder.find("w:pPr", namespaces=NAMESPACES) if placeholder is not None else None
        replacement = converter.convert(value, paragraph_properties=paragraph_properties)
        for child in list(table_cell):
            if child.tag != f"{W}tcPr":
                table_cell.remove(child)
        table_cell.extend(replacement)

    @staticmethod
    def _set_space_preservation(element: etree._Element, value: str) -> None:
        attribute = f"{{{XML_NAMESPACE}}}space"
        if value[:1].isspace() or value[-1:].isspace() or "  " in value:
            element.set(attribute, "preserve")
        else:
            element.attrib.pop(attribute, None)

    def _ensure_numbering_content_type(self, entries: dict[str, bytes]) -> None:
        content_types = etree.fromstring(entries[CONTENT_TYPES_XML])
        has_override = any(element.get("PartName") == "/word/numbering.xml" for element in content_types)
        if has_override:
            return
        override = etree.SubElement(
            content_types,
            f"{{{CONTENT_TYPES_NAMESPACE}}}Override",
        )
        override.set("PartName", "/word/numbering.xml")
        override.set("ContentType", NUMBERING_CONTENT_TYPE)
        entries[CONTENT_TYPES_XML] = self._serialize(content_types)

    @staticmethod
    def _serialize(root: etree._Element) -> bytes:
        return etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
