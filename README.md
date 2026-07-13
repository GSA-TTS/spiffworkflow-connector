# **SpiffWorkflow Service Connector**

This repository contains a V2 (simplified) implementation of SpiffWorkflow's Service Connector Proxy. It provides an "Artifacts" service that can generate a PDF from an included HTML template and manage its storage in an S3 bucket.

## **Overview**

The Artifacts service provides two main commands:

1. `GenerateArtifact`: Takes a template name, data, and a unique ID. It generates a PDF using the Playwright library and uploads it to a configured S3 bucket.
2. `GetLinkToArtifact`: Takes an artifact ID and returns public and/or private links to the stored artifact.

This connector is designed to be flexible, supporting different S3 storage backends (like Minio for development and AWS S3 for production) through configuration.

## **Features**

- Generate PDFs from HTML templates using Jinja2 placeholders.
- Store generated artifacts in S3-compatible storage.
- Retrieve pre-signed and private links to stored artifacts.
- Returns a JSON response with artifact links.

## **Requirements**

- Python 3.12+
- Playwright library
- Jinja2 library
- S3 bucket credentials and configuration

## **Usage**

1. Install the required libraries using `pip install -r requirements.txt`.
2. Ensure your environment is configured with the necessary S3 credentials. See the Configuration section.
3. Use the `GenerateArtifact` command to create and store a PDF.
4. Use the `GetLinkToArtifact` command to retrieve links to an existing artifact.

## **Configuration**

The S3 connection is configured via environment variables. The following variables are required:

- `S3_ENDPOINT_URL`: The URL of the S3-compatible storage.
- `S3_ACCESS_KEY_ID`: The access key for the S3 bucket.
- `S3_SECRET_ACCESS_KEY`: The secret key for the S3 bucket.
- `S3_REGION`: The AWS region of the bucket.
- `S3_BUCKET`: The name of the S3 bucket to use.

If there's a Cloud Foundry-style VCAP_SERVICES environment variable, credentials for an S3 service named "artifacts", if present, will be used instead.

## **Example**

Assuming the service is running on `http://localhost:8200`, you can use the following `curl` commands.

### Generate an Artifact

This command generates a new PDF from the `blm-ce.html` template, saves it with the ID `my-test-artifact-123`, and returns links to it.

```bash
curl -X POST \
  http://localhost:8200/v1/do/artifacts/GenerateArtifact \
  -H 'Content-Type: application/json' \
  -d '{
        "id": "my-test-artifact-123",
        "template": "blm-ce.html",
        "data": {
          "some_key": "some_value"
        },
        "generate_links": true
      }'
```

### Get a Link to an Artifact

This command retrieves the links for an existing artifact.

```bash
curl -X POST \
  http://localhost:8200/v1/do/artifacts/GetLinkToArtifact \
  -H 'Content-Type: application/json' \
  -d '{
        "id": "my-test-artifact-123"
      }'
```

**NOTES:**

- Your template name must correspond to a file in the `/templates` directory.
- The `data` dictionary should contain keys that are referenced in the Jinja template placeholders.

## **Development**

To develop and test this repository, you can run `make` in a shell, which will build and start the local Docker network, including a Minio instance for storage. Running `make test` will run a test script for existing functionality.

### Building behind a TLS-inspecting proxy (e.g. Zscaler)

On a machine whose egress is intercepted by a TLS-inspecting proxy (Zscaler,
Netskope, etc.), Docker builds fail with `x509: certificate signed by unknown
authority` because the build's `RUN` steps (`apt-get`, `curl https://astral.sh`,
`uv sync`, `playwright install`) don't trust the proxy's re-signing CA.

The `Dockerfile` accepts the corporate CA as an optional BuildKit **secret**
named `zscaler_ca`. Pass your CA bundle at build time and BuildKit will trust it
for the rest of the build:

```bash
docker buildx build \
  --secret id=zscaler_ca,src=/path/to/ca-bundle.crt \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --build-arg HTTP_PROXY="$HTTP_PROXY" \
  --build-arg NO_PROXY="$NO_PROXY" \
  -t spiffworkflow-connector .
```

The CA bundle is typically the concatenation of your proxy's root/intermediate
certs (on Linux these live under `/usr/local/share/ca-certificates/*.crt`).

This is a **no-op off-proxy and in CI**: when the secret is not supplied the
mount is empty and the line does nothing, so the same `Dockerfile` stays
portable.

> BuildKit itself must also trust the CA to pull the base images (`FROM`,
> `COPY --from=ghcr.io/...`). Use a `buildx` builder whose BuildKit image trusts
> the CA. A reusable helper that wires up both boundaries automatically is
> available as `docker-zscaler-shim`.

## **Tests**

To run pytest unit tests, either exec into the connector service container and run:

```
uv run pytest -v --cov=. --cov-report=term-missing
```

or, in the root of the project, run:

```
docker exec spiffworkflow-connector-connector-1 uv run pytest -v --cov=. --cov-report=term-missing
```

## **Contributing**

Contributions are welcome! Please submit a pull request with your changes, and ensure that you have tested your code thoroughly.

## **License**

This repository is licensed under the [MIT License](https://opensource.org/licenses/MIT).
