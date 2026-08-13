FROM python:3.13-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1

COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/

WORKDIR /app

COPY certs/ /tmp/custom-certs/

RUN <<'EOF'
set -eu

mkdir -p /usr/local/share/ca-certificates
found=0

for f in /tmp/custom-certs/*; do
  if [ ! -f "$f" ]; then
    continue
  fi

  case "$f" in
    *.crt)
      found=1
      name="$(basename "$f")"
      echo "Installing custom CA certificate: $f -> /usr/local/share/ca-certificates/$name"
      cp "$f" "/usr/local/share/ca-certificates/$name"
      ;;
    *)
      echo "Skipping non-CRT file: $f"
      ;;
  esac
done

if [ "$found" = "1" ]; then
  update-ca-certificates
  echo "Custom CA certificates installed"
else
  echo "No custom CRT certificates found; continuing"
fi

rm -rf /tmp/custom-certs
EOF

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

ENV PATH="/root/.cargo/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_PYTHON_DOWNLOADS=never
ENV PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

RUN uv run playwright install chromium --with-deps --only-shell

COPY *.py .
COPY ./bin ./bin/
COPY ./templates ./templates/

# Install minio client (architecture agnostic)
RUN set -eux; \
  arch="$(uname -m)"; \
  case "$arch" in \
  x86_64) mc_arch="amd64" ;; \
  aarch64|arm64) mc_arch="arm64" ;; \
  *) echo "Unsupported architecture: $arch"; exit 1 ;; \
  esac; \
  curl -fsSL "https://dl.min.io/client/mc/release/linux-${mc_arch}/mc" -o /usr/local/bin/mc; \
  chmod +x /usr/local/bin/mc; \
  /usr/local/bin/mc --version

ENTRYPOINT ["./bin/run_locally"]

CMD ["uv", "run", "granian", "--reload", "--host", "0.0.0.0", "--port", "8200", "--interface", "asgi", "main:app"]
