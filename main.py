import logging

import falcon.asgi
import httpx
import orjson
import json
import os
import io
import urllib.parse
import boto3
from botocore.config import Config  # type: ignore
from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright

# TODO: change this for prod
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client = httpx.AsyncClient(timeout=None)

#
# Controllers
#


class v1_commands:
    async def on_get(self, req, resp):
        resp.media = embedded_connectors


class v1_do_http_connector:
    def __init__(self, request_method):
        self.request_method = request_method

    async def on_post(self, req, resp):
        params = await req.media
        auth = None
        error = None
        status = 0
        url = params.get("url")

        basic_auth_username = params.get("basic_auth_username")
        basic_auth_password = params.get("basic_auth_password")

        if basic_auth_username and basic_auth_password:
            auth = (basic_auth_username, basic_auth_password)

        # TODO: error handling
        http_response = await http_client.request(
            self.request_method,
            url,
            headers=params.get("headers"),
            params=params.get("params"),
            json=params.get("data"),
            auth=auth,
        )
        status = http_response.status_code

        content_type = http_response.headers.get("Content-Type", "")
        raw_response = http_response.text

        if "application/json" in content_type:
            command_response = orjson.loads(raw_response)
        else:
            command_response = {"raw_response": raw_response}

        resp.media = {
            "command_response": {
                "body": command_response,
                "mimetype": "application/json",
                "http_status": status,
            },
            "command_response_version": 2,
            "error": error,
            "spiff__logs": [],
        }


class v1_do_pdf_connector:
    def __init__(self):
        pass

    async def on_post(self, req, resp):
        params = await req.media
        error = None
        self.bucket = params.get("bucket")
        self.object_name = params.get("object_name")
        self.template_name = params.get("template_name")
        self.config = json.loads(params.get("headers"))
        self.test_data = params.get("test_data")

        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=self.config.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=self.config.get("AWS_SECRET_ACCESS_KEY"),
            config=Config(
                region_name=self.config.get("AWS_DEFAULT_REGION"),
                signature_version="s3v4",
                client_context_params={
                    "endpoint_url": self.config.get("S3_ENDPOINT_URL", None)
                },
            ),
        )

        # Build the template
        template_path = os.path.abspath("./templates")
        env = Environment(loader=FileSystemLoader(template_path))
        template = env.get_template(self.template_name)

        # TODO: this can probably go away
        # if not self.test_data:
        #     render_data = task_data
        # else:
        #     render_data = self.test_data

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
            # if storage_type == "minio":
            #     result = client.put_object(
            #         self.bucket,
            #         self.object_name,
            #         pdf_stream,
            #         length=pdf_size,
            #         content_type="application/pdf",
            #     )
            # else:
            #     result = client.put_object(
            #         Bucket=self.bucket,
            #         Key=self.object_name,
            #         Body=pdf_stream,
            #     )

            result = self.s3_client.put_object(
                Bucket=self.bucket,
                Key=self.object_name,
                Body=pdf_stream,
            )
            # If no exception, upload succeeded. Now construct the response.
            object_name = urllib.parse.quote_plus(self.object_name)

            # if storage_type == "minio":
            #     object_url = (
            #         f"http://localhost:9002/browser/{self.bucket}/{object_name}"
            #     )

            # else:
            #     object_url = f"https://s3-us-gov-west-1.amazonaws.com/{self.bucket}/{self.object_name}"

            object_url = f"https://s3-{self.config.get("AWS_DEFAULT_REGION")}.amazonaws.com/{self.bucket}/{self.object_name}"

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


#
# App
#


extra_handlers = {
    "application/json": falcon.media.JSONHandler(
        dumps=orjson.dumps,
        loads=orjson.loads,
    ),
}

app = falcon.asgi.App(
    cors_enable=True,
)

app.req_options.media_handlers.update(extra_handlers)
app.resp_options.media_handlers.update(extra_handlers)

app.add_route("/v1/commands", v1_commands())

app.add_route("/v1/do/http/DeleteRequest", v1_do_http_connector("DELETE"))
app.add_route("/v1/do/http/GetRequest", v1_do_http_connector("GET"))
app.add_route("/v1/do/http/HeadRequest", v1_do_http_connector("HEAD"))
app.add_route("/v1/do/http/PatchRequest", v1_do_http_connector("PATCH"))
app.add_route("/v1/do/http/PostRequest", v1_do_http_connector("POST"))
app.add_route("/v1/do/http/PutRequest", v1_do_http_connector("PUT"))

app.add_route("/v1/do/pdf/pdf_to_s3", v1_do_pdf_connector())

#
# Static Data
#


http_base_params = [
    {"id": "url", "type": "str", "required": True},
    {"id": "headers", "type": "any", "required": False},
]

http_basic_auth_params = [
    {"id": "basic_auth_username", "type": "str", "required": False},
    {"id": "basic_auth_password", "type": "str", "required": False},
]

http_ro_params = [
    *http_base_params,
    {"id": "params", "type": "any", "required": False},
    *http_basic_auth_params,
]

http_rw_params = [
    *http_base_params,
    {"id": "data", "type": "any", "required": False},
    *http_basic_auth_params,
]

pdf_to_s3_params = [
    {"id": "bucket", "type": "str", "required": True},
    {"id": "object_name", "type": "str", "required": True},
    {"id": "template_name", "type": "str", "required": True},
    {"id": "storage_type", "type": "str", "required": True},
    {"id": "headers", "type": "str", "required": True},
    {"id": "test_data", "type": "dict", "required": False},
]

embedded_connectors = [
    {"id": "http/DeleteRequest", "parameters": http_rw_params},
    {"id": "http/GetRequest", "parameters": http_ro_params},
    {"id": "http/HeadRequest", "parameters": http_ro_params},
    {"id": "http/PatchRequest", "parameters": http_rw_params},
    {"id": "http/PostRequest", "parameters": http_rw_params},
    {"id": "http/PutRequest", "parameters": http_rw_params},
    {"id": "pdf/pdf_to_s3", "parameters": pdf_to_s3_params},
]
