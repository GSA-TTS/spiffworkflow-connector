import os
import json
import io
import logging
from typing import Optional, Dict, Any

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

from config import s3_config
from s3utils import (
    create_s3_client,
    get_bucket_for_storage,
    generate_private_link,
    generate_presigned_url,
)

logger = logging.getLogger(__name__)


class v1_do_artifacts_connector:
    def __init__(self):
        self.template_path = os.path.abspath("./templates")
        self.env = Environment(loader=FileSystemLoader(self.template_path))

    async def on_post_generate_artifact(self, req, resp):
        """Handle the artifacts/GenerateArtifact command."""
        params = await req.media
        error = None

        try:
            # Extract parameters
            artifact_id = params.get("id")
            template_name = params.get("template")
            template_data = params.get("data")
            generate_links = params.get("generate_links", False)
            storage = params.get("storage")
            task_data = params.get("spiff__task_data")

            if not all([artifact_id, template_name]):
                raise ValueError(
                    "Missing required parameters: id and template are required"
                )

            if not (template_data):
                logger.info("Template data is not provided, using task_data instead")
                template_data = task_data

            # This is a total hack. The issue is that the user can enter any data whatsoever,
            # but that data is not formatted. In other words, we are trying to format an
            # arbitrary string.
            template_data["exclusions"] = template_data["exclusionsText"].split('\n')
            template_data["lupDecisions"] = template_data["lupDecisions"].split('\n')


            # Create PDF from template
            template = self.env.get_template(template_name)
            rendered_document = template.render(template_data)
            pdf_buffer = await self._html_to_pdf(rendered_document)

            # Prepare for S3 upload
            pdf_stream = io.BytesIO(pdf_buffer)
            pdf_stream.seek(0)

            # Get S3 client and bucket
            s3_client = create_s3_client(storage)
            bucket = get_bucket_for_storage(storage)

            # Upload to S3
            s3_client.put_object(Bucket=bucket, Key=artifact_id, Body=pdf_stream)

            # Generate response
            response = self._generate_artifact_response(
                s3_client, bucket, artifact_id, generate_links
            )
            status = "200"

        except Exception as e:
            logger.error(f"Error generating artifact: {e}")
            response = "error"
            error = json.dumps({"error": str(e)})
            status = "500"

        resp.media = {
            "command_response": {
                "body": response,
                "mimetype": "application/json",
                "http_status": status,
            },
            "command_response_version": 2,
            "error": error,
            "spiff__logs": [],
        }

    async def on_post_get_link(self, req, resp):
        """Handle the artifacts/GetLinkToArtifact command."""
        params = await req.media
        error = None

        try:
            # Extract parameters
            artifact_id = params.get("id")
            storage = params.get("storage")

            if not artifact_id:
                raise ValueError("Missing required parameter: id")

            # Get S3 client and bucket
            s3_client = create_s3_client(storage)
            bucket = get_bucket_for_storage(storage)

            # Verify object exists
            s3_client.head_object(Bucket=bucket, Key=artifact_id)

            # Generate response
            response = self._generate_artifact_response(
                s3_client, bucket, artifact_id, True
            )
            status = "200"

        except Exception as e:
            logger.error(f"Error generating link: {e}")
            response = "error"
            error = json.dumps({"error": str(e)})
            status = "500"

        resp.media = {
            "command_response": {
                "body": response,
                "mimetype": "application/json",
                "http_status": status,
            },
            "command_response_version": 2,
            "error": error,
            "spiff__logs": [],
        }

    def _generate_artifact_response(
        self, s3_client, bucket: str, key: str, include_presigned: bool
    ) -> Dict[str, str]:
        """Generate the response dictionary with appropriate links."""
        response = {"private_link": generate_private_link(bucket, key)}

        if include_presigned:
            response["presigned_link"] = generate_presigned_url(s3_client, bucket, key)

        return response

    async def _html_to_pdf(self, html_content: str) -> bytes:
        """Create PDF from HTML content using Playwright."""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(html_content)
            pdf_buffer = await page.pdf()
            await browser.close()
            return pdf_buffer
