from unittest.mock import MagicMock, patch

from falcon import testing

DIRECT_GET_ENDPOINT = "/api/artifacts"
DIRECT_POST_ENDPOINT = "/api/artifacts/GenerateArtifact"


class TestDirectArtifactLink:
    """Tests for GET /api/artifacts/{artifact_id:path}"""

    @patch("main.generate_presigned_url")
    @patch("main.get_bucket_for_storage")
    @patch("main.create_s3_client")
    def test_get_artifact_link_happy_path(
        self,
        mock_create_s3,
        mock_get_bucket,
        mock_presigned_url,
        client: testing.TestClient,
    ):
        mock_s3 = MagicMock()
        mock_create_s3.return_value = mock_s3
        mock_get_bucket.return_value = "test-bucket"
        mock_presigned_url.return_value = "https://s3.example.com/presigned/my-artifact"

        result = client.simulate_get(f"{DIRECT_GET_ENDPOINT}/my-artifact")

        assert result.status_code == 200
        assert result.json == {"url": "https://s3.example.com/presigned/my-artifact"}
        mock_s3.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="my-artifact"
        )

    @patch("main.generate_presigned_url")
    @patch("main.get_bucket_for_storage")
    @patch("main.create_s3_client")
    def test_get_artifact_link_nested_path(
        self,
        mock_create_s3,
        mock_get_bucket,
        mock_presigned_url,
        client: testing.TestClient,
    ):
        """Test that nested paths like project_id/artifact_id resolve correctly"""
        mock_s3 = MagicMock()
        mock_create_s3.return_value = mock_s3
        mock_get_bucket.return_value = "test-bucket"
        mock_presigned_url.return_value = (
            "https://s3.example.com/presigned/proj-1/doc-2"
        )

        result = client.simulate_get(f"{DIRECT_GET_ENDPOINT}/proj-1/doc-2")

        assert result.status_code == 200
        assert result.json["url"] == "https://s3.example.com/presigned/proj-1/doc-2"
        mock_s3.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="proj-1/doc-2"
        )

    @patch("main.get_bucket_for_storage")
    @patch("main.create_s3_client")
    def test_get_artifact_link_not_found(
        self,
        mock_create_s3,
        mock_get_bucket,
        client: testing.TestClient,
    ):
        mock_s3 = MagicMock()
        mock_create_s3.return_value = mock_s3
        mock_get_bucket.return_value = "test-bucket"

        # Simulate S3 NoSuchKey exception
        error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3.head_object.side_effect = mock_s3.exceptions.NoSuchKey(
            error_response, "HeadObject"
        )

        result = client.simulate_get(f"{DIRECT_GET_ENDPOINT}/nonexistent-artifact")

        assert result.status_code == 404
        assert result.json["error"] == "not_found"
        assert "nonexistent-artifact" in result.json["detail"]

    @patch("main.get_bucket_for_storage")
    @patch("main.create_s3_client")
    def test_get_artifact_link_s3_error(
        self,
        mock_create_s3,
        mock_get_bucket,
        client: testing.TestClient,
    ):
        mock_s3 = MagicMock()
        mock_create_s3.return_value = mock_s3
        mock_get_bucket.return_value = "test-bucket"

        # Make NoSuchKey a distinct type so the generic Exception path is hit
        mock_s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        mock_s3.head_object.side_effect = RuntimeError("connection timeout")

        result = client.simulate_get(f"{DIRECT_GET_ENDPOINT}/some-artifact")

        assert result.status_code == 500
        assert result.json["error"] == "s3_error"
        assert "connection timeout" in result.json["detail"]

    @patch("main.generate_presigned_url")
    @patch("main.get_bucket_for_storage")
    @patch("main.create_s3_client")
    def test_get_artifact_link_presign_failure(
        self,
        mock_create_s3,
        mock_get_bucket,
        mock_presigned_url,
        client: testing.TestClient,
    ):
        mock_s3 = MagicMock()
        mock_create_s3.return_value = mock_s3
        mock_get_bucket.return_value = "test-bucket"
        mock_presigned_url.side_effect = RuntimeError("presign exploded")

        result = client.simulate_get(f"{DIRECT_GET_ENDPOINT}/some-artifact")

        assert result.status_code == 500
        assert result.json["error"] == "presign_failed"
        assert "presign exploded" in result.json["detail"]


class TestDirectArtifactPost:
    """Tests for POST /api/artifacts/GenerateArtifact"""

    @patch("main.artifacts._generate_artifact_response")
    @patch("main.artifacts._generate_pdf_with_attachments")
    @patch("main.artifacts._render_template_html")
    @patch("main.artifacts._format_template_data")
    @patch("main.get_bucket_for_storage")
    @patch("main.create_s3_client")
    def test_post_artifact_happy_path(
        self,
        mock_create_s3,
        mock_get_bucket,
        mock_format,
        mock_render,
        mock_pdf,
        mock_response,
        client: testing.TestClient,
    ):
        mock_s3 = MagicMock()
        mock_create_s3.return_value = mock_s3
        mock_get_bucket.return_value = "test-bucket"
        mock_format.return_value = {"name": "formatted"}
        mock_render.return_value = "<html>rendered</html>"
        mock_pdf.return_value = b"fake_pdf_bytes"
        mock_response.return_value = {
            "private_link": "s3://test-bucket/proj/doc",
            "presigned_link": "https://s3.example.com/presigned",
        }

        payload = {
            "id": "proj/doc",
            "template": "blm-ce.html",
            "data": {"name": "Test"},
            "generate_links": True,
        }

        result = client.simulate_post(DIRECT_POST_ENDPOINT, json=payload)

        assert result.status_code == 200
        assert result.json["private_link"] == "s3://test-bucket/proj/doc"
        assert result.json["presigned_link"] == "https://s3.example.com/presigned"
        mock_s3.put_object.assert_called_once()

    def test_post_artifact_missing_id(self, client: testing.TestClient):
        payload = {
            "template": "blm-ce.html",
            "data": {"name": "Test"},
        }

        result = client.simulate_post(DIRECT_POST_ENDPOINT, json=payload)

        assert result.status_code == 400
        assert result.json["error"] == "missing_params"

    def test_post_artifact_missing_template(self, client: testing.TestClient):
        payload = {
            "id": "proj/doc",
            "data": {"name": "Test"},
        }

        result = client.simulate_post(DIRECT_POST_ENDPOINT, json=payload)

        assert result.status_code == 400
        assert result.json["error"] == "missing_params"

    def test_post_artifact_missing_data(self, client: testing.TestClient):
        payload = {
            "id": "proj/doc",
            "template": "blm-ce.html",
        }

        result = client.simulate_post(DIRECT_POST_ENDPOINT, json=payload)

        assert result.status_code == 400
        assert result.json["error"] == "missing_params"

    @patch("main.artifacts._format_template_data")
    def test_post_artifact_template_error(
        self,
        mock_format,
        client: testing.TestClient,
    ):
        mock_format.side_effect = RuntimeError("template not found")

        payload = {
            "id": "proj/doc",
            "template": "nonexistent.html",
            "data": {"name": "Test"},
            "generate_links": False,
        }

        result = client.simulate_post(DIRECT_POST_ENDPOINT, json=payload)

        assert result.status_code == 500
        assert result.json["error"] == "template_error"
        assert "template not found" in result.json["detail"]

    @patch("main.artifacts._generate_pdf_with_attachments")
    @patch("main.artifacts._render_template_html")
    @patch("main.artifacts._format_template_data")
    def test_post_artifact_pdf_generation_error(
        self,
        mock_format,
        mock_render,
        mock_pdf,
        client: testing.TestClient,
    ):
        mock_format.return_value = {"name": "formatted"}
        mock_render.return_value = "<html>rendered</html>"
        mock_pdf.side_effect = RuntimeError("chromium crashed")

        payload = {
            "id": "proj/doc",
            "template": "blm-ce.html",
            "data": {"name": "Test"},
            "generate_links": False,
        }

        result = client.simulate_post(DIRECT_POST_ENDPOINT, json=payload)

        assert result.status_code == 500
        assert result.json["error"] == "pdf_generation_failed"
        assert "chromium crashed" in result.json["detail"]

    @patch("main.artifacts._generate_pdf_with_attachments")
    @patch("main.artifacts._render_template_html")
    @patch("main.artifacts._format_template_data")
    @patch("main.get_bucket_for_storage")
    @patch("main.create_s3_client")
    def test_post_artifact_upload_error(
        self,
        mock_create_s3,
        mock_get_bucket,
        mock_format,
        mock_render,
        mock_pdf,
        client: testing.TestClient,
    ):
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = RuntimeError("S3 unavailable")
        mock_create_s3.return_value = mock_s3
        mock_get_bucket.return_value = "test-bucket"
        mock_format.return_value = {"name": "formatted"}
        mock_render.return_value = "<html>rendered</html>"
        mock_pdf.return_value = b"fake_pdf_bytes"

        payload = {
            "id": "proj/doc",
            "template": "blm-ce.html",
            "data": {"name": "Test"},
            "generate_links": False,
        }

        result = client.simulate_post(DIRECT_POST_ENDPOINT, json=payload)

        assert result.status_code == 500
        assert result.json["error"] == "upload_failed"
        assert "S3 unavailable" in result.json["detail"]

    @patch("main.artifacts._generate_artifact_response")
    @patch("main.artifacts._generate_pdf_with_attachments")
    @patch("main.artifacts._render_template_html")
    @patch("main.artifacts._format_template_data")
    @patch("main.get_bucket_for_storage")
    @patch("main.create_s3_client")
    def test_post_artifact_response_generation_error(
        self,
        mock_create_s3,
        mock_get_bucket,
        mock_format,
        mock_render,
        mock_pdf,
        mock_response,
        client: testing.TestClient,
    ):
        mock_s3 = MagicMock()
        mock_create_s3.return_value = mock_s3
        mock_get_bucket.return_value = "test-bucket"
        mock_format.return_value = {"name": "formatted"}
        mock_render.return_value = "<html>rendered</html>"
        mock_pdf.return_value = b"fake_pdf_bytes"
        mock_response.side_effect = RuntimeError("link generation failed")

        payload = {
            "id": "proj/doc",
            "template": "blm-ce.html",
            "data": {"name": "Test"},
            "generate_links": True,
        }

        result = client.simulate_post(DIRECT_POST_ENDPOINT, json=payload)

        assert result.status_code == 500
        assert result.json["error"] == "response_generation_failed"
        assert "link generation failed" in result.json["detail"]
