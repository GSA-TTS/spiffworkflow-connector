FROM python:3.12-slim-bookworm

WORKDIR /app

# Install system dependencies and uv
RUN apt-get update && apt-get install -y curl && \
  curl -LsSf https://astral.sh/uv/install.sh | sh && \
  apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Install Playwright browser
RUN uv run playwright install chromium --with-deps --only-shell

# Copy application code
COPY *.py .
COPY ./bin ./bin/
COPY ./templates ./templates/

ENV PORT="8080"

CMD ["/app/bin/boot_server_in_docker"]

