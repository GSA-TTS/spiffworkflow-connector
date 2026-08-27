from io import BytesIO
from zipfile import ZipFile

import lxml.etree as etree

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}


class DocxFieldExtractor:

    def _get_w_val(self, element, attr="val"):
        return (
            element.get(f"{{{NS['w']}}}{attr}")
            if element is not None
            else None
        )

    def _get_text_from_element(self, element):
        texts = element.xpath(".//w:t/text()", namespaces=NS)
        return "".join(texts).strip()

    def _content_controls_to_dict(self, controls):
        fields = {}

        for control in controls:
            key = control.get("tag") or control.get("alias") or control.get("id")
            value = control.get("value")

            if key:
                fields[key] = value

        return fields

    def _extract_content_controls(self, docx_bytes: bytes):
        controls = []

        with ZipFile(BytesIO(docx_bytes)) as docx:
            xml = docx.read("word/document.xml")

        root = etree.fromstring(xml)

        for sdt in root.xpath(".//w:sdt", namespaces=NS):
            sdt_pr = sdt.find("w:sdtPr", namespaces=NS)
            sdt_content = sdt.find("w:sdtContent", namespaces=NS)

            if sdt_pr is None or sdt_content is None:
                continue

            alias_el = sdt_pr.find("w:alias", namespaces=NS)
            tag_el = sdt_pr.find("w:tag", namespaces=NS)
            id_el = sdt_pr.find("w:id", namespaces=NS)

            controls.append(
                {
                    "alias": self._get_w_val(alias_el),
                    "tag": self._get_w_val(tag_el),
                    "id": self._get_w_val(id_el),
                    "value": self._get_text_from_element(sdt_content),
                }
            )

        return controls

    def extract_fields(self, docx_bytes: bytes):
        controls = self._extract_content_controls(docx_bytes)
        return self._content_controls_to_dict(controls)