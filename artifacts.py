import os
import json
import io
import logging
from typing import Any, Optional
from playwright.async_api import Browser
import html

from io import BytesIO
import base64
from pypdf import PdfReader, PdfWriter

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright
from functools import wraps

from s3utils import (
    create_s3_client,
    get_bucket_for_storage,
    generate_private_link,
    generate_presigned_url,
)

logger = logging.getLogger(__name__)

# For a given key, specify any attachment templates associated with the main template
ASSOCIATED_DOCUMENTS_MAP = {"blm-ce.html": ["blm-id-checklist.html"]}


def command_handler(error_context: str):
    """
    A decorator to standardize error handling for endpoints
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, req, resp, *args, **kwargs):
            error = None

            try:
                response, status = await func(self, req, resp, *args, **kwargs)

            except Exception as e:
                logger.error(f"{error_context}: {e}", exc_info=True)
                response = "error"
                status = "500"
                error = json.dumps({"error": str(e)})

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

        return wrapper

    return decorator


def check_required_parameters(
    required_params: list[str], params: dict[str, Any]
) -> None:
    if not all([params[key] for key in required_params]):
        errorMessage = (
            "Missing required parameters: " + ", ".join(required_params) + " required"
        )
        raise ValueError(errorMessage)


class v1_do_artifacts_connector:
    def __init__(self):
        self.template_path = os.path.abspath("./templates")
        self.env = Environment(loader=FileSystemLoader(self.template_path))

    @command_handler("Error generating HTML Preview")
    async def on_post_generate_html_preview(self, req, resp):
        """Handle the artifacts/GenerateHtmlPreview command"""
        params = await req.media
        check_required_parameters(["template"], params)
        # Extract parameters
        template_name = params.get("template")
        template_data = params.get("data")
        task_data = params.get("spiff__task_data")

        template_data = self._format_template_data(
            template_name, template_data, task_data
        )

        rendered_document = self._render_template_html(template_name, template_data)

        # We escape and encode the HTML as base64 so it can more easily be used as a data URL in an iframe
        rendered_document_base64 = base64.b64encode(rendered_document.encode()).decode()
        rendered_document_escaped_base64 = html.escape(rendered_document_base64)

        # Generate response
        response = {"previewData": rendered_document_escaped_base64}
        status = "200"
        return response, status

    @command_handler("Error generating artifact")
    async def on_post_generate_artifact(self, req, resp):
        """Handle the artifacts/GenerateArtifact command."""
        params = await req.media
        check_required_parameters(["id", "template"], params)

        # Extract parameters
        artifact_id = params.get("id")
        template_name = params.get("template")
        template_data = params.get("data")
        generate_links = params.get("generate_links", False)
        storage = params.get("storage")
        task_data = params.get("spiff__task_data")
        attachments = template_data.get("attachments", [])

        template_data = self._format_template_data(
            template_name, template_data, task_data
        )

        # Render the HTML for the main template
        rendered_document = self._render_template_html(template_name, template_data)

        # Render the HTML for any attachments associated with the main template
        # These are attachments that are *always* added to the document, not attachments
        # a user has uploaded.
        associated_documents: list[str] = []
        for associated_document_template in ASSOCIATED_DOCUMENTS_MAP.get(
            template_name, []
        ):
            associated_documents.append(
                self._render_template_html(associated_document_template, template_data)
            )

        pdf_buffer = await self._generate_pdf_with_attachments(
            rendered_document, associated_documents, attachments
        )

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
        return response, status

    @command_handler("Error generating link")
    async def on_post_get_link(self, req, resp):
        """Handle the artifacts/GetLinkToArtifact command."""
        params = await req.media
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
        return response, status

    def _render_template_html(self, template_name, template_data) -> str:
        # Transform the data for rendering in the template
        template = self.env.get_template(template_name)
        return template.render(template_data)

    def _get_last_approval_date(self, approvers: list[dict[str, Any]]):
        return approvers[-1]["date"]

    def _generate_artifact_response(
        self, s3_client, bucket: str, key: str, include_presigned: bool
    ) -> dict[str, str]:
        """Generate the response dictionary with appropriate links."""
        response = {"private_link": generate_private_link(bucket, key)}

        if include_presigned:
            response["presigned_link"] = generate_presigned_url(s3_client, bucket, key)

        return response

    async def _generate_pdf_with_attachments(
        self, document: str, associated_documents: list[str], attachments: list[str]
    ) -> bytes:
        """
        Generate a PDF: document is the main HTML to render, associated_documents is a list
        of other HTML documents to render afterwards, and attachments is a list of
        use-uploaded documents to add as attachments.
        """
        async with async_playwright() as p:
            browser = (
                await p.chromium.launch()
            )  # Note: probably better to cache this at the class level?

            # We will merge the form-data pdf with all attachments (which we render as separate pdfs).
            form_data_pdf: bytes = await self._html_to_pdf(
                html_content=document, browser=browser
            )
            attachment_pdfs: list[bytes] = []

            async def add_attachment(attachment_pdf: bytes):
                # We create a separate header page for each attachment so that we do not have
                # to, e.g., add a header to an attachment that is already a pdf.
                attachment_cover_page_template = self.env.get_template(
                    "attachment-cover.html"
                )
                attachment_cover_page_html = attachment_cover_page_template.render(
                    {"attachmentNumber": len(attachment_pdfs) // 2 + 1}
                )
                attachment_cover_page_pdf = await self._html_to_pdf(
                    html_content=attachment_cover_page_html, browser=browser
                )
                attachment_pdfs.append(attachment_cover_page_pdf)
                attachment_pdfs.append(attachment_pdf)

            # We first render all of the associated documents as attachments
            for associated_document in associated_documents:
                attachment_pdf = await self._html_to_pdf(
                    html_content=associated_document, browser=browser
                )
                await add_attachment(attachment_pdf)

            # We then render all user-defined attachments
            for index, data_url in enumerate(attachments):
                file_type, payload_bytes = self._decode_data_url(data_url)
                if not file_type or payload_bytes is None:
                    # TODO: Better error handling!
                    logging.warning(
                        "Could not parse data URL for attachment %s", index + 1
                    )
                    continue

                # Now we get the attachment data itself as a pdf.
                attachment_pdf: Optional[bytes] = None

                if file_type.startswith("image/"):
                    # For images, we embed the image into a pdf.
                    template = self.env.get_template("image-attachment.html")
                    rendered_image = template.render({"image_data": data_url})
                    attachment_pdf = await self._html_to_pdf(
                        html_content=rendered_image, browser=browser
                    )
                elif file_type == "application/pdf":
                    # If the image is a pdf, we already have the pdf bytes.
                    attachment_pdf = payload_bytes
                else:
                    logging.warning(
                        "Unsupported attachment type %s for attachment %s",
                        file_type,
                        index + 1,
                    )

                if attachment_pdf:
                    await add_attachment(attachment_pdf)

            all_pdfs = [form_data_pdf] + attachment_pdfs
            merged_pdf_bytes = self._merge_pdfs(all_pdfs)
            await browser.close()
            return merged_pdf_bytes

    async def _html_to_pdf(self, html_content: str, browser: Browser) -> bytes:
        page = await browser.new_page()
        await page.set_content(html_content)
        pdf_buffer = await page.pdf(print_background=True)
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

    def _format_template_data(self, template_name, template_data, task_data):
        if not (template_data):
            logger.info("Template data is not provided, using task_data instead")
            template_data = task_data

        attachments = template_data.get("attachments", [])

        # This is a total hack. The issue is that the user can enter any string,
        # so we are trying to format an arbitrary string.
        template_data["exclusions"] = template_data["exclusionsText"].split("\n")
        template_data["lupDecisions"] = template_data["lupDecisions"].split("\n")

        # Parse out data from the approvers array
        template_data["responsibleOfficial"] = template_data["approvers"][-1]["name"]
        template_data["approvalDate"] = self._get_last_approval_date(
            template_data["approvers"]
        )
        # This assumes associated documents will be attachments
        template_data["numberOfAttachments"] = len(attachments) + len(
            ASSOCIATED_DOCUMENTS_MAP.get(template_name, [])
        )

        # Format the ID Team Checklist data
        all_id_team_checklist_resources = template_data["allIdTeamChecklistResources"]
        all_id_team_checklist_resources_with_survey: dict[str, Any] = template_data[
            "idTeamChecklist"
        ]

        idTeamChecklist = []
        for resource in all_id_team_checklist_resources:
            newIdTeamItem: dict[str, Any] = {}
            newIdTeamItem["resource"] = resource.replace(
                "_", " "
            )  # Warning: this is fragile. It relies on the name of the resource being the same as the name of the variable.
            if resource in all_id_team_checklist_resources_with_survey:
                # This resource had an associated survey conducted
                surveyData = all_id_team_checklist_resources_with_survey[resource]
                newIdTeamItem["selectedForReview"] = "Yes"
                newIdTeamItem["impact"] = surveyData["impact"]
                newIdTeamItem["rationale"] = surveyData["rationale"]
                newIdTeamItem["specialistName"] = surveyData["specialist"]
                newIdTeamItem["date"] = surveyData["date"]
            else:
                newIdTeamItem["selectedForReview"] = "No"
            idTeamChecklist.append(newIdTeamItem)

        def checklist_sort(item: dict[str, Any]):
            # Sort so that those with impact are listed first
            secondary_sort = item["resource"]
            if item["selectedForReview"] == "Yes" and item["impact"] == "Yes":
                primary_sort = 1
            elif item.get("impact", "No") == "Yes":
                primary_sort = 2
            elif item["selectedForReview"] == "Yes":
                primary_sort = 3
            else:
                primary_sort = 4
            return (primary_sort, secondary_sort)

        idTeamChecklist = sorted(idTeamChecklist, key=checklist_sort)

        template_data["idTeamChecklistData"] = idTeamChecklist
        return template_data
