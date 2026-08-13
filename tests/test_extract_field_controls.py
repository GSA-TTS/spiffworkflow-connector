import os

import pytest

from extract_field_controls import DocxFieldExtractor

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "fixtures",
    "controlled_field_fixture.docx",
)


@pytest.fixture
def extractor():
    return DocxFieldExtractor()


@pytest.fixture
def controls(extractor):
    return extractor._extract_content_controls(FIXTURE_PATH)


@pytest.fixture
def fields(extractor, controls):
    return extractor._content_controls_to_dict(controls)


class TestDocxFieldExtractor:
    def test_fixture_exists(self):
        assert os.path.isfile(FIXTURE_PATH)

    def test_extract_content_controls_returns_list(self, controls):
        assert isinstance(controls, list)
        assert len(controls) > 0

    def test_each_control_has_expected_keys(self, controls):
        for control in controls:
            assert set(control.keys()) == {"alias", "tag", "id", "value"}

    def test_content_controls_to_dict_returns_dict(self, fields):
        assert isinstance(fields, dict)
        assert len(fields) > 0

    def test_expected_fields_present(self, fields):
        expected_keys = {
            "responsibleOfficialTitle",
            "signatureDate",
            "projectNameAttachment1",
            "grantIDAttachment1",
            "ceEligibility",
        }
        assert expected_keys.issubset(fields.keys())

    def test_checkbox_fields_extracted(self, fields):
        # Checkbox content controls render as ballot box glyphs.
        assert fields["1a2yes"] == "\u2610"  # empty ballot box
        assert fields["1a2no"] == "\u2612"  # ballot box with X

    def test_text_placeholder_values(self, fields):
        assert fields["responsibleOfficialTitle"] == "Click or tap here to enter text."
        assert fields["signatureDate"] == "Click or tap to enter a date."

    def test_long_text_field_content(self, fields):
        assert fields["ceEligibility"].startswith(
            "The EPA finds that the proposed action is eligible for exclusion"
        )

    def test_dict_keys_prefer_tag_over_alias_and_id(self, extractor):
        controls = [
            {"tag": "myTag", "alias": "myAlias", "id": "123", "value": "v"},
            {"tag": None, "alias": "aliasOnly", "id": "456", "value": "v2"},
            {"tag": None, "alias": None, "id": "789", "value": "v3"},
        ]
        result = extractor._content_controls_to_dict(controls)
        assert result["myTag"] == "v"
        assert result["aliasOnly"] == "v2"
        assert result["789"] == "v3"

    def test_dict_skips_controls_without_key(self, extractor):
        controls = [{"tag": None, "alias": None, "id": None, "value": "orphan"}]
        result = extractor._content_controls_to_dict(controls)
        assert result == {}
