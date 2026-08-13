FROM python:3.13-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1

COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/

# Trust a corporate TLS-inspecting proxy CA (e.g. Zscaler) during the build, if
# one is supplied as a BuildKit secret. No-op off-proxy / in CI: when the secret
# is absent the mount is empty and this line does nothing.
# Supply with:  docker build --secret id=zscaler_ca,src=/path/to/ca-bundle.crt ...
RUN --mount=type=secret,id=zscaler_ca,dst=/usr/local/share/ca-certificates/zscaler-shim.crt \
  (command -v update-ca-certificates >/dev/null && update-ca-certificates || true)

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y curl && \
  curl -LsSf https://astral.sh/uv/install.sh | sh && \
  apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency files
COPY pyproject.toml uv.lock ./

RUN uv run playwright install chromium --with-deps --only-shell

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy application code
COPY *.py .
COPY ./bin ./bin/
COPY ./templates ./templates/

ENV PORT="8080"

CMD ["/app/bin/boot_server_in_docker"]

