import os
from io import BytesIO
from zipfile import ZipFile

import lxml.etree as etree
import pytest

from docx.extract_field_controls import DocxFieldExtractor
from docx.fill_field_controls import DocxFieldPopulator

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "controlled_field_fixture.docx",
)

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}


@pytest.fixture
def populator():
    return DocxFieldPopulator()


@pytest.fixture
def extractor():
    return DocxFieldExtractor()


@pytest.fixture
def docx_bytes():
    with open(FIXTURE_PATH, "rb") as file:
        return file.read()


@pytest.fixture
def data():
    return {
        "responsibleOfficialTitle": "Regional Administrator",
        "signatureDate": "September 10, 2026",
        "projectNameAttachment1": "Test Project",
        "grantIDAttachment1": "EPA-12345",
        "1a2yes": "☒",
        "1a2no": "☐",
    }


@pytest.fixture
def populated_docx_bytes(populator, docx_bytes, data):
    return populator.populate_fields(docx_bytes, data)


@pytest.fixture
def populated_fields(extractor, populated_docx_bytes):
    return extractor.extract_fields(populated_docx_bytes)


class TestDocxFieldPopulator:
    def test_fixture_exists(self):
        assert os.path.isfile(FIXTURE_PATH)

    def test_populate_fields_returns_bytes(self, populated_docx_bytes):
        assert isinstance(populated_docx_bytes, bytes)
        assert len(populated_docx_bytes) > 0

    def test_populated_document_is_valid_zip(self, populated_docx_bytes):
        with ZipFile(BytesIO(populated_docx_bytes)) as docx:
            assert "word/document.xml" in docx.namelist()

    def test_populates_text_fields(self, populated_fields):
        assert populated_fields["responsibleOfficialTitle"] == "Regional Administrator"
        assert populated_fields["signatureDate"] == "September 10, 2026"
        assert populated_fields["projectNameAttachment1"] == "Test Project"
        assert populated_fields["grantIDAttachment1"] == "EPA-12345"

    def test_populates_checkbox_fields(self, populated_fields):
        assert populated_fields["1a2yes"] == "☒"
        assert populated_fields["1a2no"] == "☐"

    def test_leaves_fields_not_in_data_unchanged(
        self,
        extractor,
        docx_bytes,
        populated_docx_bytes,
    ):
        original_fields = extractor.extract_fields(docx_bytes)
        populated_fields = extractor.extract_fields(populated_docx_bytes)

        assert populated_fields["ceEligibility"] == original_fields["ceEligibility"]

    def test_get_content_control_key_prefers_tag_over_alias_and_id(
        self,
        populator,
    ):
        xml = f"""
        <w:sdtPr xmlns:w="{NS["w"]}">
            <w:alias w:val="myAlias"/>
            <w:tag w:val="myTag"/>
            <w:id w:val="123"/>
        </w:sdtPr>
        """

        sdt_pr = etree.fromstring(xml)

        assert populator._get_content_control_key(sdt_pr) == "myTag"

    def test_get_content_control_key_falls_back_to_alias(
        self,
        populator,
    ):
        xml = f"""
        <w:sdtPr xmlns:w="{NS["w"]}">
            <w:alias w:val="myAlias"/>
            <w:id w:val="123"/>
        </w:sdtPr>
        """

        sdt_pr = etree.fromstring(xml)

        assert populator._get_content_control_key(sdt_pr) == "myAlias"

    def test_get_content_control_key_falls_back_to_id(
        self,
        populator,
    ):
        xml = f"""
        <w:sdtPr xmlns:w="{NS["w"]}">
            <w:id w:val="123"/>
        </w:sdtPr>
        """

        sdt_pr = etree.fromstring(xml)

        assert populator._get_content_control_key(sdt_pr) == "123"

    def test_set_content_control_value_replaces_text(
        self,
        populator,
    ):
        xml = f"""
        <w:sdtContent xmlns:w="{NS["w"]}">
            <w:r>
                <w:t>Old value</w:t>
            </w:r>
        </w:sdtContent>
        """

        content = etree.fromstring(xml)

        populator._set_content_control_value(content, "New value")

        texts = content.xpath(".//w:t/text()", namespaces=NS)

        assert texts == ["New value"]

    def test_set_content_control_value_clears_additional_text_elements(
        self,
        populator,
    ):
        xml = f"""
        <w:sdtContent xmlns:w="{NS["w"]}">
            <w:r>
                <w:t>First</w:t>
            </w:r>
            <w:r>
                <w:t>Second</w:t>
            </w:r>
            <w:r>
                <w:t>Third</w:t>
            </w:r>
        </w:sdtContent>
        """

        content = etree.fromstring(xml)

        populator._set_content_control_value(content, "Replacement")

        text_elements = content.xpath(".//w:t", namespaces=NS)

        assert text_elements[0].text == "Replacement"
        assert text_elements[1].text == ""
        assert text_elements[2].text == ""

    def test_set_content_control_value_handles_content_without_text(
        self,
        populator,
    ):
        xml = f"""
        <w:sdtContent xmlns:w="{NS["w"]}">
            <w:r/>
        </w:sdtContent>
        """

        content = etree.fromstring(xml)

        populator._set_content_control_value(content, "Replacement")

        assert content.xpath(".//w:t", namespaces=NS) == []
