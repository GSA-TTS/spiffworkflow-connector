FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.21 /uv /uvx /bin/

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y curl && \
  curl -LsSf https://astral.sh/uv/install.sh | sh && \
  apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# Install Playwright browser (before deps so this layer is cached independently)
RUN uvx playwright install chromium --with-deps --only-shell

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy application code
COPY *.py .
COPY ./bin ./bin/
COPY ./templates ./templates/

ENV PORT="8080"

CMD ["/app/bin/boot_server_in_docker"]

