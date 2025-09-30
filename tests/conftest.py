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
    """Fixture that provides a fake filesystem with test templates"""
    with Patcher() as patcher:
        # Create templates in a known location
        templates_dir = "/tmp/test_templates"
        patcher.fs.create_dir(templates_dir)

        # Create a test template
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
              <div class="header">
                  <h1>Test Document</h1>
              </div>
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
            f"{templates_dir}/test-template.html",
            contents=test_template_content,
        )

        try:
            yield patcher.fs, templates_dir
        finally:
            pass
