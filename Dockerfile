FROM python:3.14.5-slim-trixie@sha256:7a500125bc50693f2214e842a621440a1b1b9cbb2188f74ab045d29ed2ea5856

COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/

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

