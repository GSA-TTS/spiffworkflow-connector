import json
from unittest.mock import patch

API_ENDPOINT = "/v1/do/artifacts/"


class TestArtifactsService:
    @patch("artifacts.create_s3_client")
    @patch("artifacts.get_bucket_for_storage")
    def test_generate_artifact(
        self,
        mock_get_bucket,
        mock_create_s3_client,
        client,
        mock_artifacts_env,
        mock_artifacts_generate_pdf_with_attachments,
    ):
        test_data = {
            "id": "test-artifact-123",
            "template": "test-template.html",
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "exclusionsText": "Fake NEPA Compliance Text",
                "lupDecisions": "Fake LUP Decisions Text",
                "approvers": [
                    {"name": "Approver 1", "date": "2023-09-29"},
                    {"name": "Approver 2", "date": "2023-09-29"},
                ],
            },
            "generate_links": False,
            "callback": "id",
            "storage": "s3",
        }

        mock_artifacts_generate_pdf_with_attachments.return_value = b"fake_pdf_content"
        result = client.simulate_post(f"{API_ENDPOINT}GenerateArtifact", json=test_data)

        # assert command returns valid status & response
        json_response = json.loads(result.text)
        print(json_response)
        assert json_response["command_response"]["http_status"] == "200"
        assert json_response["command_response"]["body"]["private_link"]

        # assert contents of pdf indirectly via call_args
        html_content = mock_artifacts_generate_pdf_with_attachments.call_args[0][0]

        # Verify the template was properly rendered
        assert "Test Template" in html_content
        assert "John Doe" in html_content
        assert "john@example.com" in html_content
        assert "2023-09-29" in html_content

    @patch("artifacts.create_s3_client")
    @patch("artifacts.get_bucket_for_storage")
    def test_generate_artifacts_with_presigned_link(
        self,
        mock_get_bucket,
        mock_create_s3_client,
        client,
        mock_artifacts_env,
        mock_artifacts_generate_pdf_with_attachments,
        mock_artifacts_generate_response_mock,
    ):
        test_data = {
            "id": "invoice-123",
            "template": "test-template.html",
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "exclusionsText": "Fake NEPA Compliance Text",
                "lupDecisions": "Fake LUP Decisions Text",
                "approvers": [
                    {"name": "Approver 1", "date": "2023-09-29"},
                    {"name": "Approver 2", "date": "2023-09-29"},
                ],
            },
            "generate_links": True,
            "storage": "s3",
        }

        mock_artifacts_generate_pdf_with_attachments.return_value = b"fake_pdf_content"
        mock_artifacts_generate_response_mock.return_value = {
            "private_link": "s3://test-bucket/invoice-123",
            "presigned_link": "https://example.com/presigned-url",
        }

        result = client.simulate_post(f"{API_ENDPOINT}GenerateArtifact", json=test_data)

        json_response = json.loads(result.text)
        assert json_response["command_response"]["http_status"] == "200"
        assert json_response["command_response"]["body"]["private_link"]
        assert json_response["command_response"]["body"]["presigned_link"]

        # Verify the HTML content contains invoice data
        html_content = mock_artifacts_generate_pdf_with_attachments.call_args[0][0]
        assert "Test Template" in html_content
        assert "John Doe" in html_content
        assert "john@example.com" in html_content
        assert "2023-09-29" in html_content

    def test_artifact_get_link_endpoint_exists(self, client):
        """Test that the get link endpoint exists and is routable"""
        test_data = {"id": "s3://test-bucket/test-artifact-123", "storage": "s3"}

        # This should hit the endpoint (might error due to missing S3 setup in test)
        result = client.simulate_post(
            f"{API_ENDPOINT}GetLinkToArtifact", json=test_data
        )

        # Verify endpoint exists (status could be 500 due to missing config, but not 404)
        # Make sure the response is json
        assert result.status_code != 404
        json.loads(result.text)


class TestBLMSpecificFlows:
    @patch("artifacts.create_s3_client")
    @patch("artifacts.get_bucket_for_storage")
    def test_blm_artifact_general_payload(
        self, mock_get_bucket, mock_create_s3_client, client, mock_artifacts_generate_pdf_with_attachments
    ):
        test_data = {
            "id": "test-artifact-123",
            "template": "blm-ce.html",
            "data": {
                "projectTitle": "projectTitle_val",
                "categoricalExclusionID": "categoricalExclusionID_val",
                "fieldofficeName": "fieldofficeName_val",
                "streetAddress": "streetAddress_val",
                "city": "city_val",
                "zipCode": "zipCode_val",
                "locationOfProposedAction": "locationOfProposedAction_val",
                "leaseSerialCaseFileNumber": "leaseSerialCaseFileNumber_val",
                "applicant": "applicant_val",
                "projectDescription": "projectDescription_val",
                "landUsePlanName": "landUsePlanName_val",
                "dateApproved": "dateApproved_val",
                "exclusionsText": "Fake exclusions",
                "lupDecisions": "Fake LUP decisions",
                "approvers": [
                    {"name": "Approver 1", "date": "2023-09-29"},
                    {"name": "Approver 2", "date": "2023-09-29"},
                ],
                "lupDecisions": "lupDecisions_val",
                "publicHealthImpacts": "publicHealthImpacts_val",
                "naturalResourcesImpacts": "naturalResourcesImpacts_val",
                "controversialEffects": "controversialEffects_val",
                "precedentForFutureAction": "precedentForFutureAction_val",
                "cumulativeImpacts": "cumulativeImpacts_val",
                "endangeredSpeciesImpacts": "endangeredSpeciesImpacts_val",
                "limitAccessToSacredSites": "limitAccessToSacredSites_val",
                "promoteNoxiousWeeds": "promoteNoxiousWeeds_val",
                "categoricalExclusionJustification": "categoricalExclusionJustification_val",
                "contactPerson": "contactPerson_val",
                "contactTitle": "contactTitle_val",
                "officeName": "officeName_val",
                "mailingAddress": "mailingAddress_val",
                "telephoneNumber": "telephoneNumber_val",
            },
            "generate_links": False,
            "callback": "id",
            "storage": "s3",
        }

        mock_artifacts_generate_pdf_with_attachments.return_value = b"fake_pdf_content"
        result = client.simulate_post(f"{API_ENDPOINT}GenerateArtifact", json=test_data)

        # assert command returns valid status & response
        json_response = json.loads(result.text)
        assert json_response["command_response"]["http_status"] == "200"
        assert json_response["command_response"]["body"]["private_link"]

        # assert contents of pdf indirectly via call_args
        html_content = mock_artifacts_generate_pdf_with_attachments.call_args[0][0]

        for item in test_data["data"]:
            if item not in ["lupDecisions", "approvers", "exclusionsText"]:
                assert f"{item}_val" in html_content
        assert "Approver 1, Approver 2" in html_content
        assert "2023-09-29" in html_content
