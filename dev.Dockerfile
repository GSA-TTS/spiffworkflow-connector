FROM python:3.14.5-slim-trixie@sha256:7a500125bc50693f2214e842a621440a1b1b9cbb2188f74ab045d29ed2ea5856

COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y wget curl ca-certificates && \
  curl -LsSf https://astral.sh/uv/install.sh | sh && \
  apt-get clean && rm -rf /var/lib/apt/lists/*

# Conditionally install custom CA certificates (e.g., Zscaler)
COPY certs/ /tmp/custom-certs/
RUN set -e && \
  if ls /tmp/custom-certs/*.pem 1>/dev/null 2>&1; then \
  for f in /tmp/custom-certs/*.pem; do \
  cp "$f" "/usr/local/share/ca-certificates/$(basename "${f%.pem}.crt")"; \
  done && \
  update-ca-certificates && \
  echo "Custom CA certificates installed"; \
  else \
  echo "No custom CA certificates found"; \
  fi && \
  rm -rf /tmp/custom-certs

# Point uv/rustls and Python requests at the system CA bundle
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

ENV PATH="/root/.cargo/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_PYTHON_DOWNLOADS=never
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install all dependencies including dev dependencies
RUN uv sync --frozen

# Install Playwright browser
RUN uv run playwright install chromium --with-deps --only-shell

COPY *.py .
COPY ./bin ./bin/
COPY ./templates ./templates/

# Install minio client
RUN wget https://dl.min.io/client/mc/release/linux-amd64/mc -O /usr/local/bin/mc && \
  chmod +x /usr/local/bin/mc

ENTRYPOINT ["./bin/run_locally"]

CMD ["uv", "run", "granian", "--reload", "--host", "0.0.0.0", "--port", "8200", "--interface", "asgi", "main:app"]
