import json
import os
import io
import asyncio
import urllib.parse
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

PLUGIN_PATH = "connector-pdf/src/connector_pdf"


class PDFtoS3:
    def __init__(
        self,
        bucket: str,
        object_name: str,
        template_name: str,
        headers: str,
        test_data: dict = {},
    ):
        """
        :param bucket: Bucket to upload to
        :param object_name: S3 object name.
        :return: Json Data structure containing a http status code (hopefully '200' for success..)
            and a response string.
        """
        self.bucket = bucket
        self.object_name = object_name
        self.template_name = template_name
        self.config = json.loads(headers)
        self.test_data = test_data

    def execute(self, config, task_data):
        # Use Minio client if we're in development.
        # TODO: is there a better way to write this that doesn't put dev conditionals in prod code?
        if os.environ.get("FLASK_ENV") == "development":
            from connector_pdf.modules.minio import client
            storage_type = 'minio'
        else:
            from connector_pdf.auths.simpleAuth import SimpleAuth
            storage_type = 's3'

            client = SimpleAuth("s3", config=self.config).get_resource()

        # Build the template
        template_path = os.path.abspath(f"{PLUGIN_PATH}/templates")
        env = Environment(loader=FileSystemLoader(template_path))
        template = env.get_template(self.template_name)

        # TODO: this can probably go away
        if not self.test_data:
            render_data = task_data
        else:
            render_data = self.test_data

        # Render the document
        rendered_document = template.render(render_data)
        pdf_buffer = asyncio.run(self.html_to_pdf(rendered_document))

        # take the buffer object and make a stream
        pdf_stream = io.BytesIO(pdf_buffer)
        # get the size so the client is happy
        pdf_stream.seek(0, os.SEEK_END)
        pdf_size = pdf_stream.tell()
        # put stream back at start
        pdf_stream.seek(0)
        # Upload the file
        try:
            if storage_type == "minio":
                result = client.put_object(
                    self.bucket,
                    self.object_name,
                    pdf_stream,
                    length=pdf_size,
                    content_type="application/pdf",
                )
            else:
                result = client.put_object(
                    Bucket=self.bucket,
                    Key=self.object_name,
                    Body=pdf_stream,
                )

            # If no exception, upload succeeded. Now construct the response.
            object_name = urllib.parse.quote_plus(self.object_name)

            if storage_type == "minio":
                object_url = f"http://localhost:9002/browser/{self.bucket}/{object_name}"
                
            else:
                object_url = f"https://s3-us-gov-west-1.amazonaws.com/{self.bucket}/{self.object_name}"


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
            response = json.dumps({"error": f"AWS Exception {e}"})
            status = "500"

        return {
            "response": response,
            "status": status,
            "mimetype": "application/json",
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
