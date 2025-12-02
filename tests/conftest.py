from contextlib import contextmanager, ExitStack
import pytest
from falcon import testing
import os
from main import app, artifacts
from pyfakefs.fake_filesystem_unittest import Patcher
from jinja2 import Environment, FileSystemLoader
from unittest.mock import patch


@pytest.fixture
def client():
    return testing.TestClient(app)


@pytest.fixture
def fake_filesystem():
    """Fixture that provides a fake filesystem with real templates loaded"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    real_templates_path = os.path.join(base_dir, "templates")

    with Patcher() as patcher:
        patcher.fs.add_real_directory(real_templates_path)

        # Create a generic test template
        test_template_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Template</title>
                <style>
                    body { font-family: Arial, sans-serif; }
                    .header { color: #333; }
                    .content { margin: 20px; }
                </style>
            </head>
            <body>
                <div class="content">
                    <p>Name: {{ name }}</p>
                    <p>Email: {{ email }}</p>
                    <p>Date: {{ approvalDate }}</p>
                    {% if amount %}
                    <p>Amount: ${{ amount }}</p>
                    {% endif %}
                </div>
            </body>
            </html>
        """.strip()

        patcher.fs.create_file(
            f"{real_templates_path}/test-template.html",
            contents=test_template_content,
        )

        try:
            yield patcher.fs, real_templates_path
        finally:
            pass


@pytest.fixture
def mock_artifacts_env(fake_filesystem):
    """
    A fixture for mocking the artifact templates directory
    """
    _, templates_dir = fake_filesystem
    fake_env = Environment(loader=FileSystemLoader(templates_dir))

    with patch.object(artifacts, "env", fake_env):
        yield artifacts


@pytest.fixture
def mock_artifacts_generate_pdf_with_attachments():
    """
    A fixture for mocking artifacts._generate_pdf_with_attachments
    """
    with patch.object(artifacts, "_generate_pdf_with_attachments") as mock:
        mock.return_value = b"fake_pdf_content"  # default, override in test if needed
        yield mock


@pytest.fixture
def mock_artifacts_generate_response_mock():
    """
    A fixture for mocking artifacts._generate_artifact_response
    """
    with patch.object(artifacts, "_generate_artifact_response") as mock:
        yield mock
