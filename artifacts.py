import os
import json
import io
import logging
from typing import Any, Optional

from io import BytesIO
import base64
from pypdf import PdfReader, PdfWriter

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

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

    def get_responsible_official_string(self, approvers: list[dict[str, Any]]):
        # This is fragile. We get the last two approvers from the approvers list
        # and render them like {Name 1}, {Name 2}
        return ", ".join([approver["name"] for approver in approvers[-2:]])

    def get_last_approval_date(self, approvers: list[dict[str, Any]]):
        return approvers[-1]["date"]

    def format_attachment(self, data_url: str):
        print("\n\nATTACHMENT", data_url)
        header, data = data_url.split(',', 1)
        print('\n\nHEADER', header)
        print('\n\nDATA', data)
        # if header in []:  # TODO
        #     return self.format_image_attachment(data_url, "png", 200)
        return data_url

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

            # This is a total hack. The issue is that the user can enter any string,
            # so we are trying to format an arbitrary string.
            template_data["exclusions"] = template_data["exclusionsText"].split("\n")
            template_data["lupDecisions"] = template_data["lupDecisions"].split("\n")

            # Parse out data from the approvers array
            template_data["responsibleOfficial"] = self.get_responsible_official_string(
                template_data["approvers"]
            )
            template_data["approvalDate"] = self.get_last_approval_date(
                template_data["approvers"]
            )
            template_data["attachments"] = [
                self.format_attachment(attachment)
                for attachment in template_data["attachments"]
            ]

            # Create PDF from template
            template = self.env.get_template(template_name)
            rendered_document = template.render(template_data)
            pdf_buffer = await self._generate_pdf(rendered_document, template_data["attachments"])

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
    ) -> dict[str, str]:
        """Generate the response dictionary with appropriate links."""
        response = {"private_link": generate_private_link(bucket, key)}

        if include_presigned:
            response["presigned_link"] = generate_presigned_url(s3_client, bucket, key)

        return response

    async def _generate_pdf(self, html_content: str, attachments: list[str]) -> bytes:
        """Create PDF from HTML content using Playwright."""
        form_data_pdf: bytes = await self._html_to_pdf(html_content=html_content)
        attachment_pdfs: list[bytes] = []
        for index, data_url in enumerate(attachments):
            # First, we will create a header page
            header_html = f"""
                <html>
                    <body>
                        <h4>Attachment {index + 1}</h4>
                    </body>
                </html>
            """
            header_pdf = await self._html_to_pdf(html_content=header_html)
            attachment_pdfs.append(header_pdf)
            
            file_type, payload_bytes = self._decode_data_url(data_url)
            if not file_type or payload_bytes is None:
                logging.warning("Could not parse data URL for attachment %s", index + 1)
                continue

            attachment_pdf: Optional[bytes] = None

            if file_type.startswith("image/"):
                # 2a) Image: embed via <img src="data:..."> and render with Playwright
                img_html = f"""
                    <html>
                        <body style="margin:0; padding:0;">
                            <img src="{data_url}"
                                 style="max-width:100%; max-height:100%; object-fit:contain;" />
                        </body>
                    </html>
                """
                attachment_pdf = await self._html_to_pdf(html_content=img_html)

            elif file_type == "application/pdf":
                # 2b) PDF: use bytes as-is
                attachment_pdf = payload_bytes

            else:
                # 2c) Unknown: log but don't fail
                logging.warning(
                    "Unsupported attachment type %s for attachment %s",
                    file_type,
                    index + 1,
                )

            if attachment_pdf:
                attachment_pdfs.append(attachment_pdf)

        all_pdfs = [form_data_pdf] + attachment_pdfs
        merged_pdf_bytes = self._merge_pdfs(all_pdfs)
        return merged_pdf_bytes

    async def _html_to_pdf(self, html_content) -> bytes:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(html_content)
            pdf_buffer = await page.pdf()
            await browser.close()
            return pdf_buffer

    def _decode_data_url(self, data_url: str) -> tuple[Optional[str], Optional[bytes]]:
        """
        Parse a data: URL like:
            data:image/png;base64,iVBORw0KGgoAAA...
        Returns (mime_type, raw_bytes) or (None, None) on failure.
        """
        try:
            header, b64_data = data_url.split(",", 1)
        except ValueError:
            return None, None

        if not header.startswith("data:") or ";base64" not in header:
            return None, None

        mime_type = header[5:].split(";", 1)[0]  # strip "data:" and take up to ';'

        try:
            raw_bytes = base64.b64decode(b64_data)
        except Exception:
            logging.exception("Failed to base64-decode data URL")
            return None, None

        return mime_type, raw_bytes
    
    def _merge_pdfs(self, pdf_buffers: list[bytes]) -> bytes:
        """Merge multiple PDF byte blobs into a single PDF."""
        writer = PdfWriter()

        for pdf_bytes in pdf_buffers:
            reader = PdfReader(BytesIO(pdf_bytes))
            for page in reader.pages:
                writer.add_page(page)

        output = BytesIO()
        writer.write(output)
        output.seek(0)
        return output.getvalue()