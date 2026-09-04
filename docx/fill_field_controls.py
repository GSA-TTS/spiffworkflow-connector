from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import lxml.etree as etree


NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}


class DocxFieldPopulator:
    def _get_w_val(self, element, attr="val"):
        return element.get(f"{{{NS['w']}}}{attr}") if element is not None else None

    def _get_content_control_key(self, sdt_pr):
        tag_el = sdt_pr.find("w:tag", namespaces=NS)
        alias_el = sdt_pr.find("w:alias", namespaces=NS)
        id_el = sdt_pr.find("w:id", namespaces=NS)

        return (
            self._get_w_val(tag_el)
            or self._get_w_val(alias_el)
            or self._get_w_val(id_el)
        )

    def _set_content_control_value(self, sdt_content, value):
        text_elements = sdt_content.xpath(".//w:t", namespaces=NS)

        if not text_elements:
            return

        text_elements[0].text = str(value)

        for text_element in text_elements[1:]:
            text_element.text = ""

    def _populate_document_xml(self, xml, data):
        root = etree.fromstring(xml)

        for sdt in root.xpath(".//w:sdt", namespaces=NS):
            sdt_pr = sdt.find("w:sdtPr", namespaces=NS)
            sdt_content = sdt.find("w:sdtContent", namespaces=NS)

            if sdt_pr is None or sdt_content is None:
                continue

            key = self._get_content_control_key(sdt_pr)

            if key not in data:
                continue

            self._set_content_control_value(sdt_content, data[key])

        return etree.tostring(
            root,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )

    def populate_fields(self, docx_bytes: bytes, data: dict[str, str]) -> bytes:
        input_buffer = BytesIO(docx_bytes)
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