import json
import os
import io
import urllib.parse
import logging
import boto3
from botocore.config import Config
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

class v1_do_pdf_connector:
    def __init__(self):
        pass

    async def on_post(self, req, resp):
        # Warn about deprecated endpoint usage
        logger.warning("The /v1/do/pdf/pdf_to_s3 endpoint is deprecated. Please use /v1/do/artifacts/GenerateArtifact instead.")
        
        params = await req.media
        error = None
        self.bucket = params.get("bucket")
        self.object_name = params.get("object_name")
        self.template_name = params.get("template_name")
        self.config = json.loads(params.get("headers"))
        self.test_data = params.get("test_data")

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.config.get("ENDPOINT_URL", None),
            aws_access_key_id=self.config.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=self.config.get("AWS_SECRET_ACCESS_KEY"),
            config=Config(
                region_name=self.config.get("AWS_DEFAULT_REGION"),
                signature_version="s3v4",
            ),
        )

        # Build the template
        template_path = os.path.abspath("./templates")
        env = Environment(loader=FileSystemLoader(template_path))
        template = env.get_template(self.template_name)

        render_data = self.test_data

        # Render the document
        rendered_document = template.render(render_data)
        pdf_buffer = await self.html_to_pdf(rendered_document)

        # take the buffer object and make a stream
        pdf_stream = io.BytesIO(pdf_buffer)
        # get the size so the client is happy
        pdf_stream.seek(0, os.SEEK_END)
        pdf_size = pdf_stream.tell()
        # put stream back at start
        pdf_stream.seek(0)
        # Upload the file
        try:
            result = self.s3_client.put_object(
                Bucket=self.bucket,
                Key=self.object_name,
                Body=pdf_stream,
            )
            # If no exception, upload succeeded. Now construct the response.
            object_name = urllib.parse.quote_plus(self.object_name)

            if "minio" in self.config.get("ENDPOINT_URL", None):
                object_url = (
                    f"http://localhost:9002/browser/{self.bucket}/{object_name}"
                )
            else:
                object_url = f"https://s3-{self.config.get('AWS_DEFAULT_REGION')}.amazonaws.com/{self.bucket}/{self.object_name}"

            response = json.dumps(
                {
                    "result": "success",
                    "url": object_url,
                    "bucket_name": self.bucket,
                    "object_name": self.object_name,
                    "etag": getattr(result, "etag", None),
                    "version_id": getattr(result, "version_id", None),
                }
            )
            status = "200"
        except Exception as e:
            response = "error"
            error = json.dumps({"error": f"AWS Exception {e}"})
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

    async def html_to_pdf(self, html_content):
        """Create the PDF using Playwright library"""
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(html_content)
            pdf_buffer = await page.pdf()
            await browser.close()
            return pdf_buffer
