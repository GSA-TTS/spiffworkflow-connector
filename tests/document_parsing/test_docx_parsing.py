import os
from io import BytesIO
from zipfile import ZipFile

import lxml.etree as etree
import pytest

from document_parsing.docx.docx_parser import DocxParser

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "fixtures",
    "controlled_field_fixture.docx",
)

WORDPROCESSINGML_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

NAMESPACES = {
    "w": WORDPROCESSINGML_NAMESPACE,
}


@pytest.fixture
def docx_bytes():
    with open(FIXTURE_PATH, "rb") as file:
        return file.read()


@pytest.fixture
def parser(docx_bytes):
    return DocxParser(docx_bytes)


@pytest.fixture
def document_data(parser):
    return parser.extract_data()


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
def populated_docx_bytes(parser, data):
    return parser.populate_document(data)


@pytest.fixture
def populated_document_data(populated_docx_bytes):
    return DocxParser(populated_docx_bytes).extract_data()


class TestDocxParser:
    def test_fixture_exists(self):
        assert os.path.isfile(FIXTURE_PATH)

    def test_extract_data_returns_dict(self, document_data):
        assert isinstance(document_data, dict)
        assert len(document_data) > 0

    def test_extract_data_contains_expected_fields(self, document_data):
        expected_keys = {
            "responsibleOfficialTitle",
            "signatureDate",
            "projectNameAttachment1",
            "grantIDAttachment1",
            "ceEligibility",
        }

        assert expected_keys.issubset(document_data.keys())

    def test_extract_data_extracts_checkbox_fields(self, document_data):
        assert document_data["1a2yes"] == "☐"
        assert document_data["1a2no"] == "☒"

    def test_extract_data_extracts_placeholder_values(self, document_data):
        assert document_data["responsibleOfficialTitle"] == "Click or tap here to enter text."
        assert document_data["signatureDate"] == "Click or tap to enter a date."

    def test_extract_data_extracts_long_text_field(self, document_data):
        assert document_data["ceEligibility"].startswith(
            "The EPA finds that the proposed action is eligible for exclusion"
        )

    def test_populate_document_returns_bytes(self, populated_docx_bytes):
        assert isinstance(populated_docx_bytes, bytes)
        assert len(populated_docx_bytes) > 0

    def test_populate_document_returns_valid_docx(self, populated_docx_bytes):
        with ZipFile(BytesIO(populated_docx_bytes)) as docx:
            assert "word/document.xml" in docx.namelist()

    def test_populate_document_populates_text_fields(
        self,
        populated_document_data,
    ):
        assert populated_document_data["responsibleOfficialTitle"] == "Regional Administrator"
        assert populated_document_data["signatureDate"] == "September 10, 2026"
        assert populated_document_data["projectNameAttachment1"] == "Test Project"
        assert populated_document_data["grantIDAttachment1"] == "EPA-12345"

    def test_populate_document_populates_checkbox_fields(
        self,
        populated_document_data,
    ):
        assert populated_document_data["1a2yes"] == "☒"
        assert populated_document_data["1a2no"] == "☐"

    def test_populate_document_leaves_unspecified_fields_unchanged(
        self,
        document_data,
        populated_document_data,
    ):
        assert populated_document_data["ceEligibility"] == document_data["ceEligibility"]

    def test_get_content_control_key_prefers_tag_over_alias_and_id(self, parser):
        xml = f"""
        <w:sdtPr xmlns:w="{WORDPROCESSINGML_NAMESPACE}">
            <w:alias w:val="myAlias"/>
            <w:tag w:val="myTag"/>
            <w:id w:val="123"/>
        </w:sdtPr>
        """

        sdt_pr = etree.fromstring(xml)

        assert parser._get_content_control_key(sdt_pr) == "myTag"

    def test_get_content_control_key_falls_back_to_alias(self, parser):
        xml = f"""
        <w:sdtPr xmlns:w="{WORDPROCESSINGML_NAMESPACE}">
            <w:alias w:val="myAlias"/>
            <w:id w:val="123"/>
        </w:sdtPr>
        """

        sdt_pr = etree.fromstring(xml)

        assert parser._get_content_control_key(sdt_pr) == "myAlias"

    def test_get_content_control_key_falls_back_to_id(self, parser):
        xml = f"""
        <w:sdtPr xmlns:w="{WORDPROCESSINGML_NAMESPACE}">
            <w:id w:val="123"/>
        </w:sdtPr>
        """

        sdt_pr = etree.fromstring(xml)

        assert parser._get_content_control_key(sdt_pr) == "123"

    def test_set_content_control_value_replaces_text(self, parser):
        xml = f"""
        <w:sdtContent xmlns:w="{WORDPROCESSINGML_NAMESPACE}">
            <w:r>
                <w:t>Old value</w:t>
            </w:r>
        </w:sdtContent>
        """

        content = etree.fromstring(xml)

        parser._set_content_control_value(content, "New value")

        texts = content.xpath(
            ".//w:t/text()",
            namespaces=NAMESPACES,
        )

        assert texts == ["New value"]

    def test_set_content_control_value_clears_additional_text_elements(
        self,
        parser,
    ):
        xml = f"""
        <w:sdtContent xmlns:w="{WORDPROCESSINGML_NAMESPACE}">
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

        parser._set_content_control_value(content, "Replacement")

        text_elements = content.xpath(
            ".//w:t",
            namespaces=NAMESPACES,
        )

        assert text_elements[0].text == "Replacement"
        assert text_elements[1].text == ""
        assert text_elements[2].text == ""

    def test_set_content_control_value_handles_content_without_text(
        self,
        parser,
    ):
        xml = f"""
        <w:sdtContent xmlns:w="{WORDPROCESSINGML_NAMESPACE}">
            <w:r/>
        </w:sdtContent>
        """

        content = etree.fromstring(xml)

        parser._set_content_control_value(content, "Replacement")

        assert (
            content.xpath(
                ".//w:t",
                namespaces=NAMESPACES,
            )
            == []
        )
