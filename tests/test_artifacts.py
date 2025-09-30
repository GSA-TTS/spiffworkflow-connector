import json
from unittest.mock import patch, MagicMock


class TestArtifactsService:
    @patch("artifacts.create_s3_client")
    @patch("artifacts.get_bucket_for_storage")
    def test_generate_artifact(
        self, mock_get_bucket, mock_create_s3_client, client, fake_filesystem
    ):
        """Integration test for artifacts generation endpoint"""
        fake_fs, templates_dir = fake_filesystem

        # Mock S3 dependencies
        mock_s3_client = MagicMock()
        mock_create_s3_client.return_value = mock_s3_client
        mock_get_bucket.return_value = "test-bucket"

        # Test data
        test_data = {
            "id": "test-artifact-123",
            "template": "test-template.html",
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "date": "2023-09-29",
            },
            "generate_links": False,
            "storage": "s3",
        }

        # Create a new Jinja2 environment with the fake templates directory
        from jinja2 import Environment, FileSystemLoader

        fake_env = Environment(loader=FileSystemLoader(templates_dir))

        # Get the artifacts instance from the app
        from main import artifacts

        with (
            patch.object(artifacts, "env", fake_env),
            patch.object(artifacts, "_html_to_pdf") as mock_html_to_pdf,
        ):

            mock_html_to_pdf.return_value = b"fake_pdf_content"

            # This will test the actual endpoint routing and basic flow
            result = client.simulate_post(
                "/v1/do/artifacts/GenerateArtifact", json=test_data
            )

            # assert command returns valid status & response
            json_response = json.loads(result.text)
            assert json_response["command_response"]["http_status"] == "200"
            assert json_response["command_response"]["body"]["private_link"]

            # assert contents of pdf indirectly via call_args
            html_content = mock_html_to_pdf.call_args[0][0]

            # Verify the template was properly rendered
            assert "John Doe" in html_content
            assert "john@example.com" in html_content
            assert "2023-09-29" in html_content
            assert "Test Document" in html_content

    @patch("artifacts.create_s3_client")
    @patch("artifacts.get_bucket_for_storage")
    def test_generate_artifacts_with_presigned_link(
        self, mock_get_bucket, mock_create_s3_client, client, fake_filesystem
    ):
        """Test artifacts generation with presigned link"""
        fake_fs, templates_dir = fake_filesystem

        # Mock S3 dependencies
        mock_s3_client = MagicMock()
        mock_create_s3_client.return_value = mock_s3_client
        mock_get_bucket.return_value = "test-bucket"

        # Test data for invoice
        test_data = {
            "id": "invoice-123",
            "template": "test-template.html",
            "data": {
                "name": "John Doe",
                "email": "john@example.com",
                "date": "2023-09-29",
            },
            "generate_links": True,
            "storage": "s3",
        }

        # Create a new Jinja2 environment with the fake templates directory
        from jinja2 import Environment, FileSystemLoader

        fake_env = Environment(loader=FileSystemLoader(templates_dir))

        # Get the artifacts instance from the app
        from main import artifacts

        with (
            patch.object(artifacts, "env", fake_env),
            patch.object(artifacts, "_html_to_pdf") as mock_html_to_pdf,
            patch.object(
                artifacts, "_generate_artifact_response"
            ) as mock_generate_response,
        ):

            mock_html_to_pdf.return_value = b"fake_pdf_content"
            mock_generate_response.return_value = {
                "private_link": "s3://test-bucket/invoice-123",
                "presigned_link": "https://example.com/presigned-url",
            }

            result = client.simulate_post(
                "/v1/do/artifacts/GenerateArtifact", json=test_data
            )

            json_response = json.loads(result.text)
            assert json_response["command_response"]["http_status"] == "200"
            assert json_response["command_response"]["body"]["private_link"]
            assert json_response["command_response"]["body"]["presigned_link"]

            # Verify the HTML content contains invoice data
            html_content = mock_html_to_pdf.call_args[0][0]
            assert "John Doe" in html_content
            assert "john@example.com" in html_content
            assert "2023-09-29" in html_content
            assert "Test Document" in html_content

    def test_artifact_get_link_endpoint_exists(self, client):
        """Test that the get link endpoint exists and is routable"""
        test_data = {"id": "s3://test-bucket/test-artifact-123", "storage": "s3"}

        # This should hit the endpoint (might error due to missing S3 setup in test)
        result = client.simulate_post(
            "/v1/do/artifacts/GetLinkToArtifact", json=test_data
        )

        # Verify endpoint exists (status could be 500 due to missing config, but not 404)
        assert result.status_code != 404

        json_response = json.loads(result.text)
