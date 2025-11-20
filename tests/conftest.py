import pytest
from falcon import testing
import os
from main import app
from pyfakefs.fake_filesystem_unittest import Patcher


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
                    <p>Date: {{ date }}</p>
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
