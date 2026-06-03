import logging
from io import BytesIO

import falcon.asgi
import httpx
import orjson

from artifacts import ASSOCIATED_DOCUMENTS_MAP, v1_do_artifacts_connector
from s3utils import (
    create_s3_client,
    generate_presigned_url,
    get_bucket_for_storage,
)

# TODO: change this for prod
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

http_client = httpx.AsyncClient(timeout=None)

#
# Controllers
#


class liveness:
    async def on_get(self, req, resp):
        resp.media = {"status": "ok"}


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

        # TODO: add better error handling
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

app.add_route("/liveness", liveness())
app.add_route("/v1/commands", v1_commands())

app.add_route("/v1/do/http/DeleteRequest", v1_do_http_connector("DELETE"))
app.add_route("/v1/do/http/GetRequest", v1_do_http_connector("GET"))
app.add_route("/v1/do/http/HeadRequest", v1_do_http_connector("HEAD"))
app.add_route("/v1/do/http/PatchRequest", v1_do_http_connector("PATCH"))
app.add_route("/v1/do/http/PostRequest", v1_do_http_connector("POST"))
app.add_route("/v1/do/http/PutRequest", v1_do_http_connector("PUT"))

# Add new artifact routes
artifacts = v1_do_artifacts_connector()
app.add_route("/v1/do/artifacts/GenerateArtifact", artifacts, suffix="generate_artifact")
app.add_route("/v1/do/artifacts/GenerateHtmlPreview", artifacts, suffix="generate_html_preview")
app.add_route("/v1/do/artifacts/GetLinkToArtifact", artifacts, suffix="get_link")

#
# Static Data
#

generate_artifact_params = [
    {"id": "id", "type": "str", "required": True},
    {"id": "template", "type": "str", "required": True},
    {"id": "data", "type": "dict", "required": True},
    {"id": "generate_links", "type": "bool", "required": False},
    {"id": "storage", "type": "str", "required": False},
]

generate_html_preview_params = [
    {"id": "id", "type": "str", "required": True},
    {"id": "template", "type": "str", "required": True},
    {"id": "data", "type": "dict", "required": True},
]

get_link_params = [
    {"id": "id", "type": "str", "required": True},
    {"id": "storage", "type": "str", "required": False},
]

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

embedded_connectors = [
    {"id": "http/DeleteRequest", "parameters": http_rw_params},
    {"id": "http/GetRequest", "parameters": http_ro_params},
    {"id": "http/HeadRequest", "parameters": http_ro_params},
    {"id": "http/PatchRequest", "parameters": http_rw_params},
    {"id": "http/PostRequest", "parameters": http_rw_params},
    {"id": "http/PutRequest", "parameters": http_rw_params},
    {"id": "artifacts/GenerateArtifact", "parameters": generate_artifact_params},
    {"id": "artifacts/GenerateHtmlPreview", "parameters": generate_html_preview_params},
    {"id": "artifacts/GetLinkToArtifact", "parameters": get_link_params},
]


## DIRECT ROUTES


class DirectArtifactLink:
    async def on_get(self, req, resp, artifact_id):
        import urllib.parse

        artifact_id = urllib.parse.unquote(artifact_id)
        s3_client = create_s3_client(None)
        bucket = get_bucket_for_storage(None)
        try:
            s3_client.head_object(Bucket=bucket, Key=artifact_id)
        except s3_client.exceptions.NoSuchKey:
            resp.status = falcon.HTTP_404
            resp.media = {
                "error": "not_found",
                "detail": f"Artifact '{artifact_id}' not found",
            }
            return
        except Exception as e:
            logger.exception("Error checking artifact existence")
            resp.status = falcon.HTTP_500
            resp.media = {"error": "s3_error", "detail": str(e)}
            return

        try:
            url = generate_presigned_url(s3_client, bucket, artifact_id)
        except Exception as e:
            logger.exception("Error generating presigned URL")
            resp.status = falcon.HTTP_500
            resp.media = {"error": "presign_failed", "detail": str(e)}
            return

        resp.status = falcon.HTTP_200
        resp.media = {"url": url}


app.add_route("/api/artifacts/{artifact_id:path}", DirectArtifactLink())


class DirectArtifactPost:
    async def on_post(self, req, resp):
        try:
            params = await req.media
        except Exception as e:
            resp.status = falcon.HTTP_400
            resp.media = {"error": "invalid_request", "detail": str(e)}
            return

        artifact_id = params.get("id")
        template_name = params.get("template")
        template_data = params.get("data")
        generate_links = params.get("generate_links", False)
        storage = params.get("storage", None)

        if not artifact_id or not template_name or not template_data:
            resp.status = falcon.HTTP_400
            resp.media = {
                "error": "missing_params",
                "detail": "id, template, and data are required",
            }
            return

        attachments = template_data.get("attachments", [])

        try:
            template_data = artifacts._format_template_data(template_name, template_data, [])
            rendered_document = artifacts._render_template_html(template_name, template_data)
        except Exception as e:
            logger.exception("Error rendering template")
            resp.status = falcon.HTTP_500
            resp.media = {"error": "template_error", "detail": str(e)}
            return

        associated_documents: list[str] = []
        for associated_document_template in ASSOCIATED_DOCUMENTS_MAP.get(template_name, []):
            associated_documents.append(artifacts._render_template_html(associated_document_template, template_data))

        try:
            pdf_buffer = await artifacts._generate_pdf_with_attachments(
                rendered_document, associated_documents, attachments
            )
        except Exception as e:
            logger.exception("Error generating PDF")
            resp.status = falcon.HTTP_500
            resp.media = {"error": "pdf_generation_failed", "detail": str(e)}
            return

        pdf_stream = BytesIO(pdf_buffer)
        pdf_stream.seek(0)

        s3_client = create_s3_client(storage)
        bucket = get_bucket_for_storage(storage)

        try:
            s3_client.put_object(Bucket=bucket, Key=artifact_id, Body=pdf_stream)
        except Exception as e:
            logger.exception("Error uploading artifact to S3")
            resp.status = falcon.HTTP_500
            resp.media = {"error": "upload_failed", "detail": str(e)}
            return

        try:
            response = artifacts._generate_artifact_response(s3_client, bucket, artifact_id, generate_links)
        except Exception as e:
            logger.exception("Error generating artifact response links")
            resp.status = falcon.HTTP_500
            resp.media = {"error": "response_generation_failed", "detail": str(e)}
            return

        resp.status = falcon.HTTP_200
        resp.media = response


app.add_route("/api/artifacts/GenerateArtifact", DirectArtifactPost())
