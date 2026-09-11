from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import lxml.etree as etree

from ..document_parser import DocumentParser

WORDPROCESSINGML_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

NAMESPACES = {
    "w": WORDPROCESSINGML_NAMESPACE,
}


class DocxParser(DocumentParser[bytes]):
    def _get_w_val(self, element, attr="val"):
        if element is None:
            return None

        return element.get(f"{{{WORDPROCESSINGML_NAMESPACE}}}{attr}")

    def _get_content_control_key(self, sdt_pr):
        tag_el = sdt_pr.find("w:tag", namespaces=NAMESPACES)
        alias_el = sdt_pr.find("w:alias", namespaces=NAMESPACES)
        id_el = sdt_pr.find("w:id", namespaces=NAMESPACES)

        return self._get_w_val(tag_el) or self._get_w_val(alias_el) or self._get_w_val(id_el)

    def extract_data(self) -> dict[str, str]:
        with ZipFile(BytesIO(self.document)) as docx:
            xml = docx.read("word/document.xml")

        root = etree.fromstring(xml)
        fields = {}

        for sdt in root.xpath(".//w:sdt", namespaces=NAMESPACES):
            sdt_pr = sdt.find("w:sdtPr", namespaces=NAMESPACES)
            sdt_content = sdt.find("w:sdtContent", namespaces=NAMESPACES)

            if sdt_pr is None or sdt_content is None:
                continue

            key = self._get_content_control_key(sdt_pr)

            if key:
                texts = sdt_content.xpath(
                    ".//w:t/text()",
                    namespaces=NAMESPACES,
                )
                fields[key] = "".join(texts).strip()

        return fields

    def populate_document(self, data: dict[str, str]) -> bytes:
        input_buffer = BytesIO(self.document)
        output_buffer = BytesIO()

        with (
            ZipFile(input_buffer, "r") as source,
            ZipFile(output_buffer, "w", ZIP_DEFLATED) as destination,
        ):
            for item in source.infolist():
                contents = source.read(item.filename)

                if item.filename == "word/document.xml":
                    contents = self._populate_document_xml(contents, data)

                destination.writestr(item, contents)

        return output_buffer.getvalue()

    def _populate_document_xml(
        self,
        xml: bytes,
        data: dict[str, str],
    ) -> bytes:
        root = etree.fromstring(xml)

        for sdt in root.xpath(".//w:sdt", namespaces=NAMESPACES):
            sdt_pr = sdt.find("w:sdtPr", namespaces=NAMESPACES)
            sdt_content = sdt.find("w:sdtContent", namespaces=NAMESPACES)

            if sdt_pr is None or sdt_content is None:
                continue

            key = self._get_content_control_key(sdt_pr)

            if key not in data:
                continue

            self._set_content_control_value(
                sdt_content,
                data[key],
            )

        return etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )

    def _set_content_control_value(self, sdt_content, value: str):
        text_elements = sdt_content.xpath(
            ".//w:t",
            namespaces=NAMESPACES,
        )

        if not text_elements:
            return

        text_elements[0].text = str(value)

        for text_element in text_elements[1:]:
            text_element.text = ""
